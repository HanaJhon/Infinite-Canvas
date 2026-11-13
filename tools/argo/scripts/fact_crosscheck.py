#!/usr/bin/env python3
"""fact_crosscheck.py — 数字交叉验证（方案 A）。

问题：多源搜索结果中，同一数字可能不一致（如「营收 100 亿」vs「营收 120 亿」），
Agent 无法判断哪个可信。本模块用纯 stdlib 做本地对比，零外部服务。

设计约束：
  - 零外部依赖，只用 stdlib（re）
  - 纯函数，无全局状态
  - 输出：{has_conflict, conflict(别名), indicator, sources, values, suggestion}
    ——sources[i] 与 values[i] 同序配对（第 i 个值来自第 i 个源）

防复发说明（2026-10-16 重建）：
  旧文件因多次 Edit 追加 _CORE_INDICATORS 导致 2420 行、集合未闭合、
  尾部函数体丢失。本文件把指标词表收敛到最小核心（~30 词，去重），
  全文件 <200 行，受 test_module_size_gate.py（1000 行上限）约束。
"""
from __future__ import annotations

import re
from typing import Any

# 数字提取正则：匹配「数字 + 单位」模式
_NUMBER_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(亿|万|千|百|元|美元|股|%|％|倍|年|月|日|个|家|人|吨|克|千克|米|千米|平方|立方)?"
)

# 核心指标词表：唯一来源 backends/text_lexicon.json（经 text_lexicon 延迟加载）。
# 原则：宁缺勿滥——未知词走 ""（无指标），不误报；新增词改 JSON + 补测试用例，不改代码。
def _core_indicators() -> frozenset[str]:
    from text_lexicon import core_indicators
    return core_indicators()

# 时间/口径范围词：不同口径的数字不得直接对比（防「生涯 350 vs 单季 15」误报）。
_CAREER_MARKERS = ("职业生涯", "生涯", "历史总", "累计", "总数")
_YEAR_RE = re.compile(r"(19|20)\d{2}")
_SEASON_RE = re.compile(r"\d{4}\s*赛季|赛季|单季|本季")


def _normalize_value(value: float, unit: str) -> float:
    """归一化到同一量级。未知单位原样返回。"""
    if unit == "亿":
        return value * 1e8
    if unit == "万":
        return value * 1e4
    if unit == "千":
        return value * 1e3
    if unit == "百":
        return value * 1e2
    return float(value)


def _extract_indicator(text: str) -> str:
    """从文本中提取第一个命中的核心指标，无命中返回 ""。长词优先。"""
    if not text:
        return ""
    for ind in sorted(_core_indicators(), key=len, reverse=True):
        if ind and ind in text:
            return ind
    return ""


def _extract_scope(text: str) -> str:
    """提取口径范围，用于判断两个数字是否可比。

    返回：career / 年份如 "2024" / season / ""（无口径信息）。
    """
    if not text:
        return ""
    if any(m in text for m in _CAREER_MARKERS):
        return "career"
    m = _YEAR_RE.search(text)
    if m:
        return m.group(0)
    if _SEASON_RE.search(text):
        return "season"
    return ""


def _indicator_near(text: str, start: int, end: int, window: int = 12) -> str:
    """取数字邻近窗口内的指标（防标题词污染片段词）。

    例：标题「进球总数」+ 片段「助攻 350 次」→ 数字 350 邻近的是「助攻」，
    不得取标题里的「进球」。无命中返回 ""（宁缺勿滥，不误报）。
    """
    lo = max(0, start - window)
    hi = min(len(text), end + window // 2)
    win = text[lo:hi]
    num_pos = start - lo  # 数字在窗口内的偏移
    best = ""
    best_key = None  # (距离, -长度)
    for ind in _core_indicators():
        if not ind:
            continue
        pos = win.find(ind)
        while pos != -1:
            dist = abs(pos - num_pos)
            key = (dist, -len(ind))
            if best_key is None or key < best_key:
                best_key = key
                best = ind
            pos = win.find(ind, pos + 1)
    return best


def _extract_numbers(text: str) -> list[dict[str, Any]]:
    """从文本提取数字列表，每项 {value, unit, raw, indicator, scope}。"""
    if not text:
        return []
    scope = _extract_scope(text)
    out: list[dict[str, Any]] = []
    for m in _NUMBER_RE.finditer(text):
        try:
            value = float(m.group(1))
        except ValueError:
            continue
        unit = m.group(2) or ""
        # 跳过年份/日期数字（防「2024 营收」里的 2024 参与数值对比）
        if unit in ("年", "月", "日") and 1900 <= value <= 2100:
            continue
        if not unit and 1900 <= value <= 2100 and len(m.group(1)) == 4:
            continue
        indicator = _indicator_near(text, m.start(), m.end())
        out.append({
            "value": value,
            "unit": unit,
            "raw": m.group(0),
            "indicator": indicator,
            "scope": scope,
        })
    return out


def _values_conflict(vals: list[float], rel_tol: float = 0.05) -> bool:
    """归一化后最大值与最小值相对差异超过 rel_tol 即判冲突。"""
    if len(vals) < 2:
        return False
    lo, hi = min(vals), max(vals)
    base = max(abs(hi), 1e-9)
    return (hi - lo) / base > rel_tol


def _comparable_buckets(
    items: list[tuple[float, str, str]],
) -> list[list[tuple[float, str]]]:
    """把 (值, scope, 源) 列表切成可比桶。

    口径兼容规则（docstring 口径，唯一实现）：
      - 有 scope 的只与同 scope 比；
      - scope 为空（无口径信息）的与每个有口径组分别比；
      - 全无 scope 时合成一桶互相比。

    返回的每桶是 [(值, 源)]，桶内同序配对。
    """
    scoped: dict[str, list[tuple[float, str]]] = {}
    for norm, scope, src in items:
        scoped.setdefault(scope or "__none__", []).append((norm, src))
    nones = scoped.get("__none__", [])
    buckets: list[list[tuple[float, str]]] = []
    for scope, lst in scoped.items():
        if scope != "__none__":
            buckets.append(lst + nones)
    if nones and not buckets:
        buckets.append(nones)
    return buckets


def crosscheck_numbers(
    query: str, candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    """交叉验证候选中的数字是否矛盾。

    可比条件（同时满足才比较）：
      1. 候选数字的 indicator 相同且非空；
      2. 若 query 能提取到指标，只比较与 query 同指标的数字
        （防「查进球、片段里助攻 350 vs 15」误报）；
      3. scope 兼容：至少一方无口径信息，或双方口径相同。
         career 与具体年份/赛季视为不兼容。

    Returns:
        {has_conflict, conflict(别名), sources, values, suggestion, indicator}
    """
    empty: dict[str, Any] = {
        "has_conflict": False,
        "conflict": False,
        "sources": [],
        "values": [],
        "suggestion": "",
        "indicator": "",
    }
    if not candidates:
        return empty

    query_ind = _extract_indicator(query or "")

    # 按 (indicator) 分组收集
    groups: dict[str, list[tuple[float, str, str]]] = {}
    for c in candidates:
        text = f"{c.get('title', '')} {c.get('snippet', '')}"
        for n in _extract_numbers(text):
            ind = n["indicator"]
            if not ind:
                continue
            if query_ind and ind != query_ind:
                continue
            norm = _normalize_value(n["value"], n["unit"])
            groups.setdefault(ind, []).append(
                (norm, n["scope"], str(c.get("source", "")))
            )

    for ind, items in groups.items():
        for bucket in _comparable_buckets(items):
            vals = [v for v, _ in bucket]
            if _values_conflict(vals):
                srcs = [s for _, s in bucket]
                sug = (
                    f"同一指标「{ind}」下多源数值分歧 "
                    f"（{min(vals):g} ~ {max(vals):g}），建议 fetch 原文核对口径后再引用。"
                )
                return {
                    "has_conflict": True,
                    "conflict": True,
                    "sources": srcs,
                    "values": vals,
                    "suggestion": sug,
                    "indicator": ind,
                }

    return empty
