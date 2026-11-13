#!/usr/bin/env python3
"""rrf_classic.py — 经典 RRF 融合（weighted=False 路径）。

所有引擎列表在同一个池中竞争，每个列表独立贡献排名。
为什么单独成模块：search_rank.py 已压着祖父上限，经典 RRF 路径
作为独立模块拆出后，search_rank.py 只留调用点。
"""

from __future__ import annotations

from typing import Any


def rrf_classic(
    ranked_lists: list[list[dict[str, Any]]],
    k: int = 60,
    lang: str | None = None,
    _canonical_url=None,
) -> list[dict[str, Any]]:
    """经典 RRF：所有结果在同一个池中竞争，不分组。

    _canonical_url 由调用方（search_rank）传入，避免本模块反向依赖。
    """
    if _canonical_url is None:
        from url_canon import canonical_url as _canonical_url

    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}
    for _li, results in enumerate(ranked_lists):
        for i, r in enumerate(results):
            key = (
                _canonical_url(r.get("url", ""))
                or (f"__title__:{r.get('title', '')}" if r.get("title") else "")
                or (f"__card__:{r.get('card_type', '')}" if r.get("card_type") else "")
                or f"__idx__:{_li}:{i}"
            )
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + i + 1)
            eng = r.get("_engine") or r.get("source", "") or ""
            if key not in items:
                item = dict(r)
                item["_rrf_score"] = 0.0
                cons: list[str] = []
                if eng:
                    cons.append(eng)
                item["consensus_engines"] = cons
                items[key] = item
            else:
                cur = items[key]
                new_txt = f"{r.get('title', '')} {r.get('snippet', '')}"
                cur_txt = f"{cur.get('title', '')} {cur.get('snippet', '')}"
                if len(new_txt) > len(cur_txt):
                    cur["title"] = r.get("title", cur.get("title"))
                    cur["snippet"] = r.get("snippet", cur.get("snippet"))
                sources = {cur.get("source", ""), r.get("source", "")}
                cur["source"] = "/".join(s for s in sources if s)
                cons = list(cur.get("consensus_engines") or [])
                if eng and eng not in cons:
                    cons.append(eng)
                cur["consensus_engines"] = cons
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    out = []
    for key, _ in ranked:
        item = items[key]
        item["_rrf_score"] = round(scores[key], 6)
        out.append(item)
    return out
