#!/usr/bin/env python3
"""bench_tail_ab.py — 尾延迟策略的离线 A/B 回放台（方案 A 的验收工具）。

## 为什么需要它（而不是再写一个调参脚本）

尾宽这条线上的教训是：**参数改动必须在同一份日志上先跑出数字**。2026-10-15
与 2026-10-19 两次 A/B 结论相反，原因是每次都换了一批线上流量、换了一个
估计量，最后只能判「噪声非信号」。本脚本把「候选策略」和「团队现行策略」
放在同一条回放时间线上算，输入是本地 ``usage_log/query.jsonl`` 与
``adaptive.db`` 的 7 天延迟分布——零网络、可复现、可对拍。

## 两种运行模式

* ``--dry-run``（默认）：只打印回放表格。**不做任何结论**，不写状态。
* ``--record``：把这次的候选值写进 ``docs-local/tail_ab_<日期>.json``，
  供下一次跑同一个 bench 时直接对拍（「上次结论是什么」不再靠记忆）。

## 用法

    python3 scripts/bench_tail_ab.py                  # 回放：现行 vs 候选
    python3 scripts/bench_tail_ab.py --candidate 0.6  # 换一个候选尾宽

候选策略刻意只开一个**常数**轴（尾宽上限），因为要回答的问题只有一个：
「把尾宽从 1.5s 收到 X，在 2 引擎查询上省多少墙钟、丢掉多少慢源交付？」
其余旋钮（起步窗、分层档位）不动——多变量同时动就没法归因，这正是前两次
对拍失败的机制原因。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics as st
import sys
import time
from collections import defaultdict
from pathlib import Path

try:  # 与生产同源的路径解析（测试域可被 ARGO_STATE_DIR 重定向）
    from argo_paths import state_path
except ImportError:  # pragma: no cover - 直接 python3 运行时的兜底
    def state_path(*parts: str) -> Path:
        return Path.home() / ".cache" / "unified-search" / Path(*parts)

BASE_TAIL = 1.5      # 现行固定尾宽
START_WINDOW = 0.8   # 现行对冲起步窗
_SYNTHETIC = {"dead_primary", "dead_backup", "fast_backup", "slow_backup",
              "slow_primary", "quick_primary", "fast_primary", "parallel"}


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * q))]


def load_p75(db_path: Path) -> dict[str, float]:
    """引擎 → 7 天窗「正常交付」延迟的 P75（毫秒）；样本 <5 的引擎不给值。"""
    if not db_path.exists():
        return {}
    lat: dict[str, list[float]] = defaultdict(list)
    with sqlite3.connect(db_path) as conn:
        for eng, ms in conn.execute(
                "SELECT engine, latency_ms FROM engine_perf "
                "WHERE success = 1 AND empty = 0"):
            lat[eng].append(float(ms or 0))
    return {e: st.quantiles(v, n=4)[2] for e, v in lat.items() if len(v) >= 5}


def load_host_bodies(state: Path) -> dict[str, float]:
    """站点 → 本地全文缓存里该站正文的中位字节数（「这个站被真正抓过、有料」的代理）。

    数据来源是 ``fulltext/index.jsonl``（抓取正文的追加式索引）。用途只有一个：
    判断被放弃的那条交付**有没有在被放弃之前进过正文流水线**。没进过的站点，
    尾宽再宽也不会自动变成正文——这是「省下的墙钟到底是不是白等」的判据。
    """
    idx = state / "fulltext" / "index.jsonl"
    if not idx.exists():
        return {}
    per: dict[str, list[float]] = defaultdict(list)
    with idx.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = str(rec.get("url") or "")
            host = url.split("/")[2] if "://" in url else ""
            if host:
                per[host].append(float(rec.get("bytes") or 0))
    return {h: st.median(v) for h, v in per.items() if v}


def load_queries(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    out = []
    with log_path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            top = rec.get("engine_latency_top") or []
            if any(isinstance(x, list) and x and x[0] in _SYNTHETIC for x in top):
                continue  # 合成引擎（基准/混沌）不是真实流量，别混进来
            out.append(rec)
    return out


def replay(queries: list[dict], p75: dict[str, float], tail_s: float) -> dict:
    """在候选尾宽下重算每条查询的墙钟，返回新旧两组的对比。"""
    old_walls: list[float] = []
    new_walls: list[float] = []
    lost_delivery = 0          # 候选策略下慢源「来不及」的次数
    for rec in queries:
        wall = rec.get("elapsed_ms") or 0
        if wall <= 0:
            continue
        top = sorted((x for x in (rec.get("engine_latency_top") or [])
                      if isinstance(x, list) and len(x) == 2 and isinstance(x[1], (int, float))),
                     key=lambda x: x[1])
        n_eng = len(rec.get("engines_used") or [])
        if len(top) < 2 or n_eng < 2:
            old_walls.append(wall)
            new_walls.append(wall)
            continue
        fast_ms = top[0][1]
        slow_ms = top[-1][1]
        # 现行：慢源若在自己回来之前就已交付则无等待，否则最多再等 BASE_TAIL
        # 已经交付的等待是**沉没成本**：慢源在窗口内回来的那条路径，两套口径
        # 都不产生「额外等待」，也就都不该被算成可省时间。只有「慢源还没回来、
        # 我们决定不再等」那一段才是真省下来的墙钟。
        wait_old = BASE_TAIL * 1000 if slow_ms - fast_ms >= BASE_TAIL * 1000 else 0
        wait_new = tail_s * 1000 if slow_ms - fast_ms >= BASE_TAIL * 1000 else 0
        if wait_new < wait_old and slow_ms - fast_ms > tail_s * 1000:
            lost_delivery += 1          # 候选策略会放弃这次慢源交付
        old_walls.append(wall)
        new_walls.append(max(0, wall - (wait_old - wait_new)))
    return {
        "n": len(old_walls),
        "old": {"p50": st.median(old_walls) if old_walls else 0,
                "p90": _percentile(old_walls, .90)},
        "new": {"p50": st.median(new_walls) if new_walls else 0,
                "p90": _percentile(new_walls, .90)},
        "saved_ms_total": sum(o - n for o, n in zip(old_walls, new_walls)),
        "slow_delivery_lost": lost_delivery,
    }


def lost_deliveries(queries: list[dict], p75: dict[str, float],
                    tail_s: float) -> list[dict]:
    """候选尾宽下**会被丢掉**的慢源交付明细（引擎 / 多等了多少 / 当时省了多少）。

    为什么单独成函数：取舍不能只看总数。「224 次」里如果九成是同一台慢源，
    那它早该被自适应降权（另一条已存在的机制），尾宽只是替它擦屁股；如果
    分散在很多源身上，缩尾宽就是在系统性地牺牲长尾覆盖。两种结论的动作完全不同。
    """
    rows: list[dict] = []
    for rec in queries:
        top = sorted((x for x in (rec.get("engine_latency_top") or [])
                      if isinstance(x, list) and len(x) == 2), key=lambda x: x[1])
        if len(top) < 2 or len(rec.get("engines_used") or []) < 2:
            continue
        fast_ms, (slow_eng, slow_ms) = top[0][1], top[-1]
        if slow_ms - fast_ms >= BASE_TAIL * 1000 and slow_ms - fast_ms >= tail_s * 1000:
            rows.append({"engine": slow_eng,
                         "extra_wait_ms": slow_ms - fast_ms,
                         "p75_ms": p75.get(slow_eng),
                         "query": (rec.get("query") or "")[:40]})
    return rows


def quality_report(lost: list[dict], host_bodies: dict[str, float],
                   state: Path, p75: dict[str, float] | None = None) -> str:
    """被放弃的那批交付「值不值得等」——用两条**互不冒充**的证据回答。

    1. **相关度代理**（结果层）：``adaptive.db`` 里该引擎的质量分。口径是
       ``result_relevance``——词面覆盖率，**不是内容正确性**；它只能说明
       「结果和查询沾不沾边」，不能说明「结果对不对」。
    2. **相对基线**（横向可比）：只看绝对值会误判——同一套代理分数在中文查询上
       天然偏低。所以同时给出「该引擎质量 − 全部引擎均质量」，正数=比平均更相关。
    3. **正文缓存覆盖**（证据层）：本地 ``fulltext`` 索引里该站点有没有被抓过正文。
       没进过的站点，尾宽再宽也不会自动变成正文。

    读法：相关度代理明显低于均线 **且** 从未进过正文缓存 → 早收工合理；
    相关度不低于均线 → 放弃它就是在拿准确性换速度。
    """
    from collections import Counter
    db = state / "adaptive.db"
    per: dict[str, list[float]] = defaultdict(list)
    if db.exists():
        with sqlite3.connect(db) as conn:
            for eng, qv in conn.execute(
                    "select engine, quality from engine_perf where quality > 0"):
                per[eng].append(float(qv))
    q_mean = {e: st.mean(v) for e, v in per.items() if len(v) >= 5}
    baseline = st.mean(q_mean.values()) if q_mean else 0.0

    lines = ["", "=== 被放弃交付的质量画像 ===",
             f"质量口径：result_relevance 词面覆盖代理；全库均线 {baseline:.3f}",
             f"{'engine':16s} {'次数':>5s} {'相关度代理':>9s} {'相对均线':>9s} {'P75ms':>7s}"]
    for eng, n in Counter(r["engine"] for r in lost).most_common():
        q = q_mean.get(eng)
        p = (p75 or {}).get(eng)
        lines.append(
            f"{eng:16s} {n:5d} {(f'{q:.3f}' if q is not None else 'n/a'):>9s} "
            f"{(f'{q - baseline:+.3f}' if q is not None else '-'):>9s} "
            f"{(f'{p:.0f}' if p else '-'):>7s}")
    hosts = set(host_bodies)
    lines.append("")
    lines.append(f"本地正文缓存覆盖 {len(hosts)} 个站点（fulltext/index.jsonl）")
    lines.append("读法：相对均线为负且从未进过正文缓存 → 早收工合理；"
                 "相对均线不为负 → 放弃它是在拿准确性换速度。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="尾宽策略离线 A/B 回放")
    ap.add_argument("--candidate", type=float, default=0.6,
                    help="候选尾宽（秒），默认 0.6")
    ap.add_argument("--record", action="store_true",
                    help="把本次回放写进 docs-local/tail_ab_<日期>.json")
    ap.add_argument("--detail", action="store_true",
                    help="扫表时附带「被放弃交付」的引擎分布（判断该缩尾宽还是该降权）")
    ap.add_argument("--quality", action="store_true",
                    help="附带质量评估：被放弃的那批交付里，有多少本来会变成正文证据")
    ap.add_argument("--sweep", default="",
                    help="逗号分隔的候选尾宽，一次性扫一遍（如 0.4,0.6,0.8,1.0）")
    args = ap.parse_args(argv)

    state = state_path()
    queries = load_queries(state / "usage_log" / "query.jsonl")
    p75 = load_p75(state / "adaptive.db")
    if not queries:
        print("没有可回放的查询日志（usage_log/query.jsonl 为空）；"
              "先跑几次 argo search 再来。")
        return 1
    if args.sweep:
        print(f"{'尾宽(s)':>8} {'p50(ms)':>8} {'p90(ms)':>8} {'总省(s)':>8} {'放弃交付':>8}")
        for cand in [float(x) for x in args.sweep.split(",") if x.strip()]:
            r = replay(queries, p75, cand)
            print(f"{cand:8.2f} {r['new']['p50']:8.0f} {r['new']['p90']:8.0f} "
                  f"{r['saved_ms_total'] / 1000:8.1f} {r['slow_delivery_lost']:8d}")
        print("（扫表是给人看的：选型要同时看「省多少」和「丢掉多少慢源交付」）")
        if args.detail:
            lost = lost_deliveries(queries, p75, float(args.sweep.split(",")[0]))
            from collections import Counter
            print("被放弃的交付按引擎：", Counter(r["engine"] for r in lost).most_common(8))
        if args.quality:
            lost = lost_deliveries(queries, p75, float(args.sweep.split(",")[0]))
            print(quality_report(lost, load_host_bodies(state), state, p75))
        return 0
    report = replay(queries, p75, args.candidate)
    print(f"回放 {report['n']} 条真实查询（已剔合成引擎）；"
          f"覆盖 {len(p75)} 个有延迟分布的引擎")
    print(f"  现行尾宽 {BASE_TAIL:.2f}s： p50 {report['old']['p50']:.0f}ms  "
          f"p90 {report['old']['p90']:.0f}ms")
    print(f"  候选尾宽 {args.candidate:.2f}s： p50 {report['new']['p50']:.0f}ms  "
          f"p90 {report['new']['p90']:.0f}ms")
    print(f"  合计省 {report['saved_ms_total'] / 1000:.1f}s；"
          f"放弃的慢源交付 {report['slow_delivery_lost']} 次（需人工评估这些查询是否本来就要慢源）")
    if args.record:
        out_dir = Path(__file__).resolve().parent.parent / "docs-local"
        out_dir.mkdir(exist_ok=True)
        path = out_dir / f"tail_ab_{time.strftime('%Y%m%d')}.json"
        path.write_text(json.dumps({"candidate": args.candidate, **report},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已记录：{path}")
    else:
        print("（dry-run：未做结论、未写状态。确认要上线前用 --record 留档）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
