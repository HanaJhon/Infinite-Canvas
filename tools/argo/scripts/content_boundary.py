#!/usr/bin/env python3
"""content_boundary.py — 不可信网页内容的边界标记与清洗。

为什么需要单独一层：Argo 对 Agent 输出的是 JSON，不能像纯文本工具那样简单
把整段响应包进 <untrusted-web-content>（会破坏 JSON 解析）。所以这里只做
两件确定能做的事：

1. **清洗**：任何来自上游的标题/摘要/正文在进入输出前，剥掉其中的边界标记
   字样——否则网页正文里自带的 `</untrusted-web-content>` 可以提前闭合边界，
   把后续内容伪装成可信指令（dsh-free-search 的同类防护）。
2. **声明**：调用方在响应里带 `content_trust: "untrusted"`，让模型与宿主
   知道这批文本的信任级别；文本边界由宿主（DSH/MCP 客户端）按自己的渲染
   形态加，不在 JSON 契约里硬塞。

不引入依赖、不做 HTML 清洗：正文已经是纯文本摘要，这里只管边界标记这一类
可被利用的结构字符。
"""

from __future__ import annotations

import re
from typing import Any

CONTENT_TRUST_UNTRUSTED = "untrusted"

# 大小写、属性、空白都按「可能的变体」处理；只剥标记本身，不动正文其余字符。
_BOUNDARY_RE = re.compile(
    r"<\s*/?\s*untrusted-web-content\b[^>]*>", re.IGNORECASE)


def strip_boundary_markers(text: Any, limit: int | None = None) -> str:
    """剥掉正文里的边界标记（含变体），可选截断。"""
    out = _BOUNDARY_RE.sub("", str(text or ""))
    if limit is not None and limit >= 0 and len(out) > limit:
        out = out[:limit]
    return out


def sanitize_results_boundary(results: Any) -> None:
    """就地清洗结果列表每条的 title/snippet 边界标记（CLI/Agent/MCP 共用单一出口）。"""
    for item in results or []:
        if not isinstance(item, dict):
            continue
        for key in ("title", "snippet"):
            if isinstance(item.get(key), str):
                item[key] = strip_boundary_markers(item[key])
