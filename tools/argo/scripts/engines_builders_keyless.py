#!/usr/bin/env python3
"""免 key（keyless）通道构建器：官方匿名额度源。

与计费通道分开注册的理由：同上游、不同经济模型。匿名额度不读 key，
按 IP/匿名池限流；与账号档混在一个引擎里会让配额与成本记账失真
（与 parallel / parallel_free 的既有处理一致）。
"""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

from engines_base import http_open, safe_search

from engines_builders_tech import _mcp_error_of, _parse_mcp_wire


# ── Keenable 免 key 通道（官方 MCP 匿名额度）────────────────────────────────

_KEENABLE_MCP_URL = "https://api.keenable.ai/mcp"
_KEENABLE_BLOCK_RE = re.compile(r"\n\s*-{3,}\s*\n")


def _keenable_block_to_result(block: str) -> dict[str, Any] | None:
    """Keenable MCP 的纯文本块 → 统一结果。字段以行首标签分隔。"""
    text = (block or "").strip()
    if not text:
        return None
    title = re.search(r"(?m)^Title:\s*(.+?)\s*$", text)
    url = re.search(r"(?m)^URL:\s*(\S+)\s*$", text)
    if not title or not url:
        return None
    published = re.search(r"(?m)^Published:\s*(\S+)", text)
    body = ""
    m = re.search(r"(?ms)^Snippets:\s*\n?(.*)$", text)
    if m:
        body = m.group(1)
    body = re.sub(r"\[\.\.\.\]", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    row: dict[str, Any] = {
        "title": title.group(1).strip()[:200],
        "url": url.group(1).strip(),
        "snippet": body[:300],
        "source": "keenable_free",
    }
    if published:
        row["published_at"] = published.group(1).strip()[:32]
    return row


def _build_keenable_free_engine(spec: dict[str, Any]) -> Any:
    """Keenable 免 key：POST 官方 MCP（tools/call search_web_pages）。

    为什么单独成引擎而不是让 keenable 回退：与 tavily_free / parallel_free
    同一条口径——keyless 是匿名额度通道，与按 credits 计费的 REST 通道
    经济模型不同，合进一个引擎会让配额与成本记账混在一起。

    上游返回纯文本块（Title/URL/Published/Snippets，`---` 分隔），不是
    JSON；解析失败按「带 error 的记录」上报，让调度层知道是通道/格式问题，
    而不是「网上没有」。
    """
    timeout = spec.get("timeout", 20)

    @safe_search
    def _engine(query: str, n: int = 5, _timeout: float | None = None,
                **kwargs) -> list[dict[str, Any]]:
        to = _timeout or timeout
        body = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "search_web_pages",
                       "arguments": {"query": query, "mode": "realtime"}},
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        }
        req = urllib.request.Request(_KEENABLE_MCP_URL, data=body, headers=headers)
        try:
            with http_open(req, timeout=to, engine=spec.get("_name", "")) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except Exception as e:
            return [{"error": f"keenable_free mcp: {type(e).__name__}: {e}",
                     "source": "keenable_free"}]
        data = _parse_mcp_wire(raw)
        if not isinstance(data, dict):
            return [{"error": "keenable_free: 响应不是可解析的 MCP 应答",
                     "source": "keenable_free"}]
        mcp_err = _mcp_error_of(data)
        if mcp_err:
            return [{"error": mcp_err, "source": "keenable_free"}]
        content = ((data.get("result") or {}).get("content") or [])
        text = "".join(str(b.get("text") or "") for b in content
                       if isinstance(b, dict))
        if not text.strip():
            return []
        out: list[dict[str, Any]] = []
        for block in _KEENABLE_BLOCK_RE.split("\n" + text):
            row = _keenable_block_to_result(block)
            if row:
                out.append(row)
            if len(out) >= max(1, int(n)):
                break
        return out

    return _engine
