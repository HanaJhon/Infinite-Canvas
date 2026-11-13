#!/usr/bin/env python3
"""article_meta.py — 从已抓取的 HTML 里提取文章级元数据与正文链接。

为什么要单独一层（2026-10-22，对标 open-websearch 的 includeLinks/byline）：
`readability_extract` 只交付正文文本，链接、作者、站点名、摘要这些**结构化
线索**在提取时被丢掉。Agent 要顺着文章里的引用继续取证，只能再抓一次页面；
研究/报告场景里作者与站点名也是引用格式的必需字段。它们都在同一份 HTML 里，
一次解析就能拿到，不该让调用方付第二次网络往返。

2026-10-26 补 JSON-LD（对标 pagesift 的结构化数据提取）：新闻站的日期与
作者最可靠来源是 <script type="application/ld+json"> 的 datePublished/author，
很多站没有 article:published_time meta 却一定有 JSON-LD。同一次解析顺手拿到，
零新增请求。meta 标签与 JSON-LD 同时存在时 meta 优先（既有行为不变）。

边界：
  - 纯标准库 HTMLParser，毫秒级；不做正文判定（那是 readability 的职责）。
  - 链接只取 <article>/<main> 内。没有语义容器时宁可不给，也不把
    nav/header/footer 的导航链接当正文引用；相对链接按页面 URL 解析。
  - 标题/摘要/站点名只读 meta 与 JSON-LD，不从正文猜；猜错比缺失更糟。
  - JSON-LD 日期解析不出时交空串丢弃，不透传原文（原样透传「有字段但读不出
    日期」比缺失更糟，同 engines_builders_batch15._norm_date 的教训）。
  - 全部字段都可能缺失，调用方按 key 是否存在判断，不返回空字符串占位。
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

MAX_LINKS = 30
MAX_TEXT = 300
_SKIP_TAGS = {"nav", "header", "footer", "aside", "script", "style", "noscript"}
_META_KEYS = {
    "author": "byline",
    "article:author": "byline",
    "og:article:author": "byline",
    "og:site_name": "site_name",
    "application-name": "site_name",
    "og:description": "excerpt",
    "description": "excerpt",
    "twitter:description": "excerpt",
    "article:published_time": "published_at",
}
_LDJSON_TYPE = "application/ld+json"
_LD_SCRIPT_CAP = 8          # 只吃前 8 段 ld+json，防御性上限
_LD_SCRIPT_MAX = 262144     # 单段 256KB，防御超大内联 JSON
_LD_ARTICLE_HINTS = ("article", "posting", "news", "blog", "report",
                     "webpage", "itempage")


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.article_links: list[dict[str, str]] = []
        self.ld_jsons: list[str] = []
        self._in_article = 0
        self._skip = 0
        self._href: str | None = None
        self._text: list[str] = []
        self._ld_active = False
        self._ld_buf: list[str] = []
        self._ld_len = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "meta":
            data = {k.lower(): (v or "") for k, v in attrs if k}
            key = (data.get("property") or data.get("name") or "").strip().lower()
            value = data.get("content") or ""
            field = _META_KEYS.get(key)
            if field and value and field not in self.meta:
                self.meta[field] = value.strip()[:MAX_TEXT]
            return
        if tag == "script":
            data = {k.lower(): (v or "") for k, v in attrs if k}
            self._ld_active = (data.get("type") or "").strip().lower() == _LDJSON_TYPE
            self._ld_buf = []
            self._ld_len = 0
        if tag in _SKIP_TAGS:
            self._skip += 1
            return
        if tag in ("article", "main"):
            self._in_article += 1
        elif tag == "a" and self._skip == 0:
            href = ""
            for k, v in attrs:
                if k.lower() == "href" and v:
                    href = v.strip()
                    break
            if href:
                self._href = href
                self._text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script":
            if self._ld_active:
                self._ld_active = False
                if self._ld_buf:
                    self.ld_jsons.append("".join(self._ld_buf))
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if tag in ("article", "main"):
            self._in_article = max(0, self._in_article - 1)
        elif tag == "a" and self._href is not None:
            text = " ".join("".join(self._text).split())[:120]
            if self._in_article:
                self.article_links.append({"url": self._href, "text": text})
            self._href = None
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._ld_active:
            if self._ld_len < _LD_SCRIPT_MAX:
                self._ld_buf.append(data)
                self._ld_len += len(data)
            return
        if self._href is not None and self._skip == 0:
            self._text.append(data)


# ─── JSON-LD 展开与字段提取 ─────────────────────────────────────────────────

def _iter_ld_nodes(data) -> list[dict]:
    """展开 ld+json 常见容器：顶层数组、@graph（含嵌套），保持文档顺序。"""
    out: list[dict] = []
    queue = [data]
    while queue:
        cur = queue.pop(0)
        if isinstance(cur, list):
            queue.extend(cur)
        elif isinstance(cur, dict):
            out.append(cur)
            graph = cur.get("@graph")
            if graph is not None:
                queue.extend(graph if isinstance(graph, list) else [graph])
    return out


def _ld_is_article(node: dict) -> bool:
    t = node.get("@type")
    if isinstance(t, list):
        t = " ".join(str(x) for x in t)
    t = str(t or "").lower()
    return any(h in t for h in _LD_ARTICLE_HINTS)


def _ld_name(value) -> str:
    """author/publisher 的形态归一：str / {name} / [{name},...]。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        name = value.get("name")
        return name.strip() if isinstance(name, str) else ""
    if isinstance(value, list):
        parts = [n for n in (_ld_name(v) for v in value) if n]
        return ", ".join(parts)
    return ""


def _ld_date(value) -> str:
    """JSON-LD 日期 → ISO 前缀规整；解析不出交空串（原样透传比空更糟）。

    ISO 带时区的（datePublished 主流形态）原样保留；`2026/10/1`、
    `2026年10月1日` 规整成 `2026-10-01`；裸时间补 T。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if not m:
        m = re.match(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", text)
    if not m:
        return ""
    y, mo, d = (int(g) for g in m.groups())
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return ""
    tail = text[m.end():].strip()
    if tail and (tail[0].isdigit() or tail[0].isspace()):
        tail = "T" + tail.lstrip()  # `2026-10-01 08:00` → ISO 的 T 分隔
    return f"{y:04d}-{mo:02d}-{d:02d}" + tail


def _ld_fields(raw_list: list[str]) -> dict:
    """从 ld+json 原文里提取元数据字段；文章类节点优先，缺失字段再放宽到全节点。"""
    nodes: list[dict] = []
    for raw in raw_list[:_LD_SCRIPT_CAP]:
        try:
            nodes.extend(_iter_ld_nodes(json.loads(raw)))
        except Exception:
            continue  # 非法 JSON／非容器：跳过这一段，不影响其余
    if not nodes:
        return {}
    article_nodes = [n for n in nodes if _ld_is_article(n)]
    fields: dict[str, str] = {}

    def harvest(pool: list[dict]) -> None:
        for node in pool:
            if "published_at" not in fields:
                d = _ld_date(node.get("datePublished"))
                if d:
                    fields["published_at"] = d
            if "headline" not in fields:
                h = node.get("headline")
                if isinstance(h, str) and h.strip():
                    fields["headline"] = h.strip()[:MAX_TEXT]
            if "byline" not in fields:
                a = _ld_name(node.get("author") or node.get("creator"))
                if a:
                    fields["byline"] = a[:MAX_TEXT]
            if "site_name" not in fields:
                s = _ld_name(node.get("publisher"))
                if not s:
                    # 无 publisher 时，WebSite/Organization 的 name 即站点名；
                    # WebPage/Product 等的 name 是页面标题/商品名，不收
                    t = str(node.get("@type") or "").lower()
                    if "website" in t or "organization" in t:
                        s = _ld_name(node.get("name"))
                if s:
                    fields["site_name"] = s[:MAX_TEXT]
            if "excerpt" not in fields:
                e = node.get("description")
                if isinstance(e, str) and e.strip():
                    fields["excerpt"] = " ".join(e.split())[:MAX_TEXT]

    harvest(article_nodes)
    if len(fields) < 5 and len(article_nodes) < len(nodes):
        rest = [n for n in nodes if n not in article_nodes]
        harvest(rest)
    return fields


def extract_article_meta(html: str, base_url: str,
                         max_links: int = MAX_LINKS) -> dict:
    """返回 {byline, excerpt, site_name, published_at, headline, links}，缺失的键不出现。

    headline 仅 JSON-LD 提供（meta 标签没有对应声明位）；其余字段 meta 与
    JSON-LD 双源，meta 优先。
    links: [{"url": 绝对 URL, "text": 锚文本}]，按出现顺序去重，最多 max_links。
    同页锚点、javascript/mailto、非 http(s)、空文本一律丢弃。
    """
    if not html:
        return {}
    p = _MetaParser()
    try:
        p.feed(html)
        p.close()
    except Exception:
        return {}
    out: dict = dict(p.meta)
    for key, value in _ld_fields(p.ld_jsons).items():
        if value and key not in out:
            out[key] = value  # meta 已有的字段不被 JSON-LD 覆盖（缺失才补）
    raw_links = p.article_links
    if raw_links:
        links: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in raw_links:
            href = item["url"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            url = urljoin(base_url, href)
            if urlparse(url).scheme not in ("http", "https"):
                continue
            if url.split("#", 1)[0] == base_url.split("#", 1)[0]:
                continue
            text = item["text"]
            if len(text) < 2 or url in seen:
                continue
            seen.add(url)
            links.append({"url": url, "text": text})
            if len(links) >= max(1, int(max_links)):
                break
        if links:
            out["links"] = links
    return out
