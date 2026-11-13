#!/usr/bin/env python3
"""bench_general_pool.py — 通用层选源的 static/dynamic 交错对拍。

用途：`source_selection.GENERAL_PRIORS` 的先验不是拍脑袋写的，重测/改表
前后用这个脚本给出同一网络时刻的两臂读数。两臂各自使用**独立的隔离状态
目录**，并关闭路由缓存——否则静态臂先跑会把 decision 缓存给动态臂，
两臂读到同一组合，A/B 变成自欺（2026-10-26 实测踩中）。

    python3 scripts/bench_general_pool.py --rounds 2
    python3 scripts/bench_general_pool.py --queries "git commit,上海 地铁 线路图" --json

输出：每条查询的墙钟、结果数、词面相关代理（query_signals.result_relevance）
与贡献引擎；末尾给两臂的 p50/mean/相关均值。词面相关只是代理，不等于内容
正确性——要看正确性得走 `--verify` 核正文。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from query_signals import result_relevance  # noqa: E402

DEFAULT_QUERIES = [
    "git commit",
    "quiet mechanical keyboard office use review",
    "ergonomic keyboard wrist pain 2026",
    "best budget laptop 2026",
    "how to clean a cast iron pan",
    "nanjing food recommendations",
    "Как написать скрипт",
    "software architecture review checklist",
]


def _run(argo: str, query: str, static: bool, state_dir: str,
         timeout: float) -> dict:
    env = dict(os.environ, ARGO_USAGE_LOG="0", ARGO_ROUTE_CACHE="0",
               ARGO_STATE_DIR=state_dir)
    for key in ("ARGO_GENERAL_FALLBACK_STATIC", "ARGO_GENERAL_FALLBACK_LEAD",
                "ARGO_GENERAL_FALLBACK_LEGACY"):
        env.pop(key, None)
    if static:
        env["ARGO_GENERAL_FALLBACK_STATIC"] = "1"
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            [argo, "search", query, "--json", "--no-cache", "-n", "8"],
            capture_output=True, text=True, encoding="utf-8",
            timeout=timeout, env=env)
        elapsed = int((time.perf_counter() - started) * 1000)
        payload = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
        results = [r for r in (payload.get("results") or [])
                   if isinstance(r, dict) and "error" not in r]
    except Exception as exc:  # 超时/非 JSON：如实记失败，不替它编读数
        return {"ms": int((time.perf_counter() - started) * 1000),
                "n": 0, "rel": None, "engines": [], "error": repr(exc)[:160]}
    return {
        "ms": elapsed,
        "n": len(results),
        # agent 档真实字节：与 drift 门禁同一口径（stdout 的实际大小）。
        # 排序不读它（见 source_selection 的说明），但 A/B 必须能量出来，
        # 否则「体积换速度」的取舍永远只能凭感觉。
        "bytes": len(proc.stdout.encode("utf-8")),
        "rel": result_relevance(query, results) if results else None,
        "engines": payload.get("engines_used") or [],
    }


def _summary(rows: list[dict]) -> dict:
    latencies = sorted(r["ms"] for r in rows)
    rels = [r["rel"] for r in rows if r.get("rel") is not None]
    if not latencies:
        return {"n": 0}
    sizes = [r.get("bytes", 0) for r in rows if r.get("bytes")]
    return {
        "n": len(rows),
        "p50_ms": latencies[len(latencies) // 2],
        "mean_ms": round(sum(latencies) / len(latencies)),
        "mean_bytes": round(sum(sizes) / len(sizes)) if sizes else None,
        "rel_mean": round(sum(rels) / len(rels), 3) if rels else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="通用层选源 static/dynamic 对拍")
    parser.add_argument("--queries", help="逗号分隔；默认 8 条混合中英查询")
    parser.add_argument("--rounds", type=int, default=2,
                        help="每臂轮数；两轮交错臂顺序，抵消网络漂移")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--argo", default=os.path.expanduser("~/.local/bin/argo"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    queries = ([q.strip() for q in args.queries.split(",") if q.strip()]
               if args.queries else DEFAULT_QUERIES)
    root = tempfile.mkdtemp(prefix="argo-bench-gp-")
    state = {"static": os.path.join(root, "static"),
             "dynamic": os.path.join(root, "dynamic")}
    for path in state.values():
        os.makedirs(path, exist_ok=True)

    rows: list[dict] = []
    for rnd in range(max(1, args.rounds)):
        for query in queries:
            order = [True, False] if rnd % 2 == 0 else [False, True]
            for static in order:
                arm = "static" if static else "dynamic"
                reading = _run(args.argo, query, static, state[arm], args.timeout)
                reading.update(query=query, arm=arm, round=rnd)
                rows.append(reading)
                if not args.json:
                    print(f"r{rnd} {query[:30]:30s} {arm:7s} "
                          f"{reading['ms']:5d}ms n={reading['n']} "
                          f"bytes={reading.get('bytes', 0)} "
                          f"rel={reading['rel']} {reading['engines']}", flush=True)

    report = {
        "state_root": root,
        "queries": queries,
        "rounds": max(1, args.rounds),
        "static": _summary([r for r in rows if r["arm"] == "static"]),
        "dynamic": _summary([r for r in rows if r["arm"] == "dynamic"]),
        "rows": rows,
    }
    if args.json:
        # 紧凑 stdout：仓库门禁禁止脚本向终端输出 pretty JSON（上下文预算）。
        print(json.dumps(report, ensure_ascii=False))
    else:
        print("\n=== summary ===")
        for arm in ("static", "dynamic"):
            print(arm, report[arm])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
