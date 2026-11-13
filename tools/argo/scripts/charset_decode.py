#!/usr/bin/env python3
"""charset_decode.py — 响应体解码：响应头声明 > HTML meta 嗅探 > 严格猜测链。

为什么独立成模块（2026-10-26，对标 pagesift 的字符集检测）：HTTP 头缺失
charset 是常态（老站尤甚），此前 http_client 对这些响应一律 utf-8 replace，
GBK/GB2312 页面解出满屏 U+FFFD（实测 zol/4399/pconline 三站各 1.6 万~5 万个）。
解码层是纯函数、无网络依赖，拆出既让 http_client 体积门禁随动下调，也让
fetch_v3/article.py 的 urllib 兜底车道能直接复用（它们在 http_client 不可
导入时同样要能正确解码）。

解码顺序：
  1. 响应头显式声明且 codec 已注册 → 信任头（与浏览器一致），即使解出替换符
     也不回退猜测——显式声明的二进制残余不许被误猜成别的编码；
  2. 头缺失/不可识别 → 按 WHATWG prescan 语义嗅探 HTML 前 2KB 的 <meta>
     声明（content-type meta 的 content 值优先于 charset 属性；带 content 的
     其他 meta 跳过——description 正文里的「charset=」是数据不是声明）；
  3. 仍无果 → 严格猜测链：utf-8 严格成功即原样；失败且高字节占比达标
     （西文页零星弯引号 <2%，GBK 中文页即便混排标记也 >10%）时依次试
     gb18030/big5（严格）；全败 utf-8 replace 兜底，任何失败不丢 body。

gb18030 是 GBK/GB2312 的超集，一个 codec 覆盖中文生态，无需 chardet 依赖。
纯标准库，零 pip 依赖。
"""

from __future__ import annotations

import re


def _header_charset(content_type: str) -> str | None:
    """Content-Type 头里可用（codec 已注册）的 charset；缺失或不可识别返回 None。

    None 与显式 "utf-8" 语义不同：前者允许进入嗅探/猜测链，后者必须信任头。
    未知编码必须先判定再解码：`bytes.decode("x-unknown-8bit")` 会抛 LookupError，
    而 LookupError 不是 OSError 子类，会被 HttpClient.get 的 `except Exception`
    吞掉并返回 status=0——一个正常的 200 响应被静默降级成「连接失败」，
    还被归因为 network。运维现实里 `charset=x-unknown-8bit`、
    `charset=gb2312;` 这类脏头并不罕见。
    """
    import codecs
    if "charset=" in content_type:
        charset = content_type.split("charset=")[-1].strip().split(";")[0].strip().strip('"\'')
        try:
            codecs.lookup(charset)
            return charset
        except (LookupError, ValueError):
            pass
    return None


def _charset_of(content_type: str) -> str:
    """从 Content-Type 解析 charset；缺失或无法识别时回落 utf-8。"""
    return _header_charset(content_type) or "utf-8"


# ─── HTML 字符集嗅探（对标 pagesift 的 mojibake 防线）────────────────────────

_PRESCAN_WINDOW = 2048
_HIGH_BYTE_SAMPLE = 65536
_HIGH_BYTE_RATIO = 0.1  # 西文页零星弯引号 <2%，GBK 中文页即便混排标记也 >10%
_META_TAG_RE = re.compile(rb"<meta\b[^>]*>", re.I)
_META_CHARSET_ATTR_RE = re.compile(
    rb"""[\s"']charset\s*=\s*["']?\s*([a-zA-Z0-9._\-]+)""", re.I)
_CONTENT_TYPE_META_RE = re.compile(
    rb"""(?:http-equiv|name)\s*=\s*["']?content-type["']?""", re.I)
_CONTENT_ATTR_RE = re.compile(
    rb"""content\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)


def _sniff_meta_charset(raw_body: bytes) -> str:
    """从 HTML 前 2KB 嗅探 <meta> 声明的字符集；无声明或 codec 不存在返回空。

    按 WHATWG prescan 语义：content-type meta（http-equiv/name 均收，现实里
    两种写法都有）的 content 值优先，其次 charset 属性。只做字节层正则，
    不建 DOM，毫秒级；声明不可信的残留 damage 由 errors="replace" 兜住。
    """
    window = raw_body[:_PRESCAN_WINDOW]
    if b"<meta" not in window.lower():
        return ""
    candidates: list[str] = []
    for tag in _META_TAG_RE.finditer(window):
        tag_bytes = tag.group(0)
        if _CONTENT_TYPE_META_RE.search(tag_bytes):
            m = _CONTENT_ATTR_RE.search(tag_bytes)
            if m:
                value = next(g for g in m.groups() if g is not None)
                text = value.decode("ascii", "ignore")
                idx = text.lower().find("charset=")
                if idx >= 0:
                    name = text[idx + 8:].split(";")[0].strip().strip("\"'")
                    candidates.append(name)
            continue
        if _CONTENT_ATTR_RE.search(tag_bytes):
            continue
        m = _META_CHARSET_ATTR_RE.search(b" " + tag_bytes)
        if m:
            candidates.append(m.group(1).decode("ascii", "ignore"))
    import codecs
    for name in candidates:
        try:
            codecs.lookup(name)
            return name
        except (LookupError, ValueError):
            continue
    return ""


def decode_response_body(raw_body: bytes, content_type: str) -> str:
    """按「响应头声明 > HTML meta 嗅探 > 严格解码链」解出文本，任何失败都不丢 body。"""
    declared = _header_charset(content_type)
    if declared is not None:
        return raw_body.decode(declared, errors="replace")
    sniffed = _sniff_meta_charset(raw_body)
    if sniffed and sniffed.lower() not in ("utf-8", "utf8", "ascii", "us-ascii"):
        return raw_body.decode(sniffed, errors="replace")
    try:
        return raw_body.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        pass
    sample = raw_body[:_HIGH_BYTE_SAMPLE]
    if sample and sum(1 for b in sample if b >= 0x80) / len(sample) >= _HIGH_BYTE_RATIO:
        for enc in ("gb18030", "big5"):
            try:
                return raw_body.decode(enc, errors="strict")
            except (UnicodeDecodeError, ValueError):
                continue
    return raw_body.decode("utf-8", errors="replace")
