#!/usr/bin/env python3
"""ab_eval — 交错 A/B 实测（逐对随机化运行顺序，防顺序偏差）。

为什么存在（2026-10-07 教训）：非交错基准里，暖连接红利让「后跑的一组」
系统性变慢/变快，造出过 37% 的假阳性——本仓历史同类假阳性至少三次
（roundtrip 第三次假阳性、benchmark 阈值改旗标、10-07 事件化证伪轮）。
本工具把正确测量固化成可复用能力：**逐对抛硬币定运行序**，逐对差值出
统计量（中位差、A 胜率、精确二项符号检验），单次快慢不作数。

与 ab_eval_p0p1.py 的分工：那是 P0/P1 优化轮的一次性验收脚本（固定场景
清单）；本工具是通用 A/B 测量器——两条带 {query} 占位符的命令即可对测
（不同引擎组合、开关、参数档）。

用法：
  python3 scripts/ab_eval.py --pairs 10 \
    --cmd-a "python3 scripts/search.py {query} --json --fields agent" \
    --cmd-b "python3 scripts/search.py {query} --json --fields agent --verify 2" \
    --query "蓝牙耳机推荐"

子进程默认注入 ARGO_USAGE_LOG=0：A/B 用的是合成查询对，不进生产使用账本
（口径同 10-10 评测隔离原则）；--usage-log 保留写入。

输出 stdout 单个 JSON：per_pair（含当对运行序）+ stats。exit 恒 0（测量
工具不是门禁）；质量守卫字段 count_median_a/b 供人工判断结果数回退。

尾判据（2026-10-15 增补，B-4）：stats 里除中位差/符号检验外，还给
p90_a/b、max_a/b 与 tail_verdict。**中位差不等于改动可用**——中位由最快的
那个引擎决定，把并发从 3 提到 6 只可能动尾部（上游限流、连接竞争）：中位纹
丝不动而 p90/max 翻倍的改动，只看中位会被放行。判据因此是「尾不退化」：
p90 与 max 各自不超过容忍倍数才 passed。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import shlex
import statistics
import subprocess
import sys
import time

_RUN_TIMEOUT_S = 120

# 尾退化容忍倍数：p90 允许 +10%、max 允许 +25%（单点极值天然更抖，给宽些）。
# 判据是「不退化」而不是「必须变快」：并发上调的收益在中位/成功率，不在尾部。
_DEFAULT_P90_TOL = 1.10
_DEFAULT_MAX_TOL = 1.25


def percentile_nearest_rank(values: list[float], p: float) -> float | None:
    """最近秩分位数（ceil(p·n) 取第 k 小），与 adaptive.latency_percentile 同口径。

    不用 statistics.quantiles：它要求 n≥2 且走插值，n=10 的 p90 会取到第 9 与
    第 10 个样本之间的值——尾判据要的是「真实观测到的第 90 百分位」，插值会
    把单点极值摊薄。
    """
    vals = sorted(float(v) for v in values)
    if not vals:
        return None
    k = max(1, min(len(vals), math.ceil(float(p) * len(vals))))
    return vals[k - 1]


def tail_verdict(a_ms: list[float], b_ms: list[float], *,
                 p90_tol: float = _DEFAULT_P90_TOL,
                 max_tol: float = _DEFAULT_MAX_TOL) -> dict:
    """B 相对 A 的尾延迟判定：p90 与 max 都不超容忍倍数才算 passed。

    只比同一批配对的耗时样本（A/B 各自独立取数，不配对相减——尾延迟关心的是
    「最坏那一档变成了多少」，不是逐对差值的分布）。
    """
    a_p90 = percentile_nearest_rank(a_ms, 0.9)
    b_p90 = percentile_nearest_rank(b_ms, 0.9)
    a_max = max(a_ms) if a_ms else None
    b_max = max(b_ms) if b_ms else None

    def _ratio(a, b):
        if a is None or b is None or a <= 0:
            return None
        return round(b / a, 3)

    r90, rmax = _ratio(a_p90, b_p90), _ratio(a_max, b_max)
    reasons = []
    if r90 is not None and r90 > p90_tol:
        reasons.append(f"p90 退化 {r90:.2f}x > {p90_tol:.2f}x")
    if rmax is not None and rmax > max_tol:
        reasons.append(f"max 退化 {rmax:.2f}x > {max_tol:.2f}x")
    if a_p90 is None or b_p90 is None:
        reasons.append("样本不足，无法判定")
    return {
        "p90_a_ms": a_p90, "p90_b_ms": b_p90, "p90_ratio": r90,
        "max_a_ms": a_max, "max_b_ms": b_max, "max_ratio": rmax,
        "p90_tol": p90_tol, "max_tol": max_tol,
        "passed": not reasons,
        "reason": "；".join(reasons) or "尾延迟未退化",
    }


def _run_once(cmd: str, query: str, keep_usage: bool) -> dict:
    # {query} 由本函数负责加引号（shlex.quote）：含空格查询此前会把命令拆成
    # 多个 argv，argparse 直接 rc=2——占位符两侧不要再自行加引号。
    substituted = cmd.replace("{query}", shlex.quote(query))
    env = dict(os.environ)
    if not keep_usage:
        env["ARGO_USAGE_LOG"] = "0"
    t0 = time.monotonic()
    try:
        proc = subprocess.run(substituted, shell=True, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=_RUN_TIMEOUT_S, env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": f"timeout>{_RUN_TIMEOUT_S}s"}
    wall_ms = round((time.monotonic() - t0) * 1000)
    if proc.returncode != 0:
        return {"ok": False, "reason": f"rc={proc.returncode}",
                "stderr_tail": proc.stderr[-200:], "wall_ms": wall_ms}
    try:
        d = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "reason": "stdout 非 JSON", "wall_ms": wall_ms,
                "stdout_head": proc.stdout[:120]}
    timing = d.get("timing") or {}
    return {"ok": True, "elapsed_ms": timing.get("elapsed_ms", wall_ms),
            "count": d.get("count"), "wall_ms": wall_ms}


def _sign_test_p(wins: int, losses: int) -> float:
    """精确二项双尾符号检验（无平局计入 n）。"""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(_comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def _comb(n: int, k: int) -> float:
    from math import comb
    return comb(n, k)


def evaluate(cmd_a: str, cmd_b: str, query: str, pairs: int, seed: int | None,
             keep_usage: bool) -> dict:
    rng = random.Random(seed)
    per_pair = []
    for i in range(pairs):
        a_first = rng.random() < 0.5
        runs = {}
        for label in (("a", "b") if a_first else ("b", "a")):
            cmd = cmd_a if label == "a" else cmd_b
            runs[label] = _run_once(cmd, query, keep_usage)
        per_pair.append({"pair": i + 1, "a_first": a_first,
                         "a": runs["a"], "b": runs["b"]})
    diffs, a_wins, b_wins, ties = [], 0, 0, 0
    for r in per_pair:
        a, b = r["a"], r["b"]
        if not (a.get("ok") and b.get("ok")):
            continue  # 失败对不进统计，账面保留
        d = a["elapsed_ms"] - b["elapsed_ms"]
        diffs.append(d)
        if d < 0:
            a_wins += 1
        elif d > 0:
            b_wins += 1
        else:
            ties += 1
    counts_a = [r["a"]["count"] for r in per_pair
                if r["a"].get("ok") and r["a"].get("count") is not None]
    counts_b = [r["b"]["count"] for r in per_pair
                if r["b"].get("ok") and r["b"].get("count") is not None]
    elapsed_a = [r["a"]["elapsed_ms"] for r in per_pair
                 if r["a"].get("ok") and r["a"].get("elapsed_ms") is not None]
    elapsed_b = [r["b"]["elapsed_ms"] for r in per_pair
                 if r["b"].get("ok") and r["b"].get("elapsed_ms") is not None]
    verdict = tail_verdict(elapsed_a, elapsed_b)
    stats = {
        "valid_pairs": len(diffs),
        "failed_pairs": pairs - len(diffs),
        "median_diff_ms": statistics.median(diffs) if diffs else None,
        "mean_diff_ms": round(statistics.fmean(diffs), 1) if diffs else None,
        "a_wins": a_wins, "b_wins": b_wins, "ties": ties,
        "sign_test_p": round(_sign_test_p(a_wins, b_wins), 4),
        "count_median_a": statistics.median(counts_a) if counts_a else None,
        "count_median_b": statistics.median(counts_b) if counts_b else None,
        "p90_a_ms": verdict["p90_a_ms"], "p90_b_ms": verdict["p90_b_ms"],
        "p90_ratio": verdict["p90_ratio"],
        "max_a_ms": verdict["max_a_ms"], "max_b_ms": verdict["max_b_ms"],
        "max_ratio": verdict["max_ratio"],
        # 尾判据与中位判据并列给出：两者结论不一致时以 tail_verdict 为准
        # （中位不动的改动同样可能把 p90/max 拉爆）。
        "tail_verdict": verdict,
    }
    return {"query": query, "pairs": pairs, "seed": seed,
            "order": "逐对随机（a_first 字段记录当对顺序）",
            "per_pair": per_pair, "stats": stats}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="交错 A/B 实测（随机化逐对顺序）")
    ap.add_argument("--cmd-a", required=True, help="A 变体命令，含 {query} 占位")
    ap.add_argument("--cmd-b", required=True, help="B 变体命令，含 {query} 占位")
    ap.add_argument("--query", required=True)
    ap.add_argument("--pairs", type=int, default=10)
    ap.add_argument("--seed", type=int, default=None,
                    help="固定种子可复现当轮运行序")
    ap.add_argument("--usage-log", action="store_true",
                    help="子进程查询写入生产使用账本（默认不写）")
    args = ap.parse_args(argv)
    report = evaluate(args.cmd_a, args.cmd_b, args.query, args.pairs,
                      args.seed, args.usage_log)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
