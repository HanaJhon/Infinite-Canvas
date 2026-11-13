#!/usr/bin/env python3
"""text_lexicon.py — 文本词表唯一来源的延迟加载器。

backends/text_lexicon.json 是词表的唯一真源（地域词 / 公司名 / 核心指标），
fact_crosscheck 只经本模块读取，不再各硬编码一份（2026-10-16：另一消费者 query_signals_v2 已按方案一回收，其「不是X」否定补进 query_understanding，模块本体移入 .trash/）。

性能纪律：模块级不读文件（import 零成本），首次调用时读一次并缓存；
JSON 缺失/损坏时退化到内嵌最小保底，保证纯函数模块永不因词表崩溃。
测试隔离：设 ARGO_TEXT_LEXICON 指向另一份 JSON 即可换表，调 reload_lexicon() 生效。
"""
from __future__ import annotations

import functools
import json
import os
from pathlib import Path
from typing import Any

ENV_LEXICON_PATH = "ARGO_TEXT_LEXICON"

# 内嵌最小保底：仅保证核心断言（茅台≠地域、非同期≠否定、营收可比）成立。
# 正常安装永远走 JSON，这里只是「文件被删也不崩」的保险。
_FALLBACK: dict[str, frozenset[str]] = {
    "geo_keywords": frozenset({"北京", "上海", "广州", "深圳", "美国", "日本"}),
    "company_names": frozenset({"贵州茅台", "云南白药", "中国石化", "中国石油"}),
    "core_indicators": frozenset({
        "营收", "收入", "净利润", "利润", "GDP", "CPI", "PMI",
        "进球", "助攻", "价格", "市值", "ROE", "同比", "环比",
    }),
}


def _lexicon_path() -> Path:
    override = os.environ.get(ENV_LEXICON_PATH, "").strip()
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parent.parent / "backends" / "text_lexicon.json"


@functools.lru_cache(maxsize=1)
def _load() -> dict[str, frozenset[str]]:
    try:
        raw: dict[str, Any] = json.loads(_lexicon_path().read_text(encoding="utf-8"))
        out: dict[str, frozenset[str]] = {}
        for key in ("geo_keywords", "company_names", "core_indicators"):
            vals = raw.get(key) or []
            out[key] = frozenset(str(v) for v in vals if str(v).strip())
        if not any(out.values()):
            raise ValueError("empty lexicon")
        return out
    except Exception:
        return dict(_FALLBACK)


def reload_lexicon() -> None:
    """清缓存（换 ARGO_TEXT_LEXICON 后或测试中调用）。"""
    _load.cache_clear()


def geo_keywords() -> frozenset[str]:
    """地域词（城市/省份/国家）。"""
    return _load()["geo_keywords"]


def company_names() -> frozenset[str]:
    """公司名词典（地域判定时优先排除这些词内部的地名）。"""
    return _load()["company_names"]


def core_indicators() -> frozenset[str]:
    """核心指标词（数字交叉验证用）。"""
    return _load()["core_indicators"]
