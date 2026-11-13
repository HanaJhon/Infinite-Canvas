#!/usr/bin/env python3
"""dispatch_result.py — 引擎编排的产出对象与墙钟记账（2026-10-21 从 engine_dispatch 拆出）。

拆出原因：module size 门禁要求 engine_dispatch 只能减不能增，而 2026-10-21 的
尾等待记账需要同时扩数据类与汇总逻辑。两者都是**纯数据**（无 IO、无调度依赖），
放在调度器里只会让「调度策略」和「记账口径」继续互相遮挡。

记账口径（为什么不是一个数）：
  - `useful_ms`：最后一个**贡献结果**的引擎完成时刻（答案从这一刻起已在手里）。
  - `first_sufficient_ms`：早停判据首次成立（结果够用）的时刻；no_early 域没有
    这个时刻，保持 0。
  - `tail_wait_ms`：结果已可交付后仍在等的时间。有早停时刻用它算，没有就用
    「首条结果时刻」算——后者正是 no_early 域白等的来源。
  - `abandoned_engine_ms`：被早停弃置的引擎已花的墙钟**之和**。它是并行资源
    浪费，不等于用户多等的时间（两个引擎并行跑到最后，赢家交结果、输家被弃置，
    用户没有任何额外等待）。`wasted_ms` 保留为它的别名，兼容旧读法。

历史教训：旧 `wasted_ms` 口径换过三次，前两版分别是「非 ok 引擎 latency 之和」
（并行时必然大于墙钟）与 `wall - useful`（有界并发下恒为 0）。两版都让仪表看
起来正常、却无法指向任何动作。这次拆成两个互不重叠的量，各自对应一个旋钮：
tail 指向收工时机，abandoned 指向并发/对冲预算。
"""

from __future__ import annotations

from typing import Any

__all__ = ["DispatchResult", "summarize_dispatch"]


class DispatchResult:
    """编排产出 + 两个钩子（融合后仍要补搜的路径用）。

    `run_one` / `ingest` 必须外露：macro_data 域的 D6 证据下限补搜在融合之后，
    它要跑单个引擎并把结果并进同一份账（raw_results / engine_outcomes /
    engine_latency / abandoned 计数），另起一份会让 engines_used 与配额记账对不上。

    `budget_used_ms` / `budget_total_ms`：本次编排的实际墙钟消耗与总预算
    （deep 等无预算模式 total 为 None）。搜索输出把它挂进 timing.budget，
    让「这次离预算上限还有多远」可观测，而不必反推 process_ms。

    `stranded`：早停弃置且仍存活的引擎 ``[(engine, holder, now_fn), ...]``，
    交 tail_completion 后台收割（学习器记真实成绩 + 合并写 L2 缓存）。主响应
    与 cancelled 记账不受它影响——它改的是「交付被丢弃」这一件事。

    记账字段的语义与历史见模块 docstring；`wasted_ms` 仅为兼容别名。
    """

    __slots__ = ("raw_results", "engine_outcomes", "engine_latency",
                 "wasted_ms", "early_stopped", "run_one", "ingest",
                 "budget_used_ms", "budget_total_ms", "useful_ms",
                 "first_sufficient_ms", "tail_wait_ms", "abandoned_engine_ms",
                 "stranded")

    def __init__(self, raw_results: Any, engine_outcomes: Any,
                 engine_latency: Any, wasted_ms: int, early_stopped: bool,
                 run_one: Any, ingest: Any, budget_used_ms: int | None = None,
                 budget_total_ms: int | None = None, useful_ms: int = 0,
                 first_sufficient_ms: int = 0, tail_wait_ms: int = 0,
                 abandoned_engine_ms: int | None = None,
                 stranded: Any = ()) -> None:
        self.raw_results = raw_results
        self.engine_outcomes = engine_outcomes
        self.engine_latency = engine_latency
        self.wasted_ms = wasted_ms
        self.early_stopped = early_stopped
        self.run_one = run_one
        self.ingest = ingest
        self.budget_used_ms = budget_used_ms
        self.budget_total_ms = budget_total_ms
        self.useful_ms = useful_ms
        self.first_sufficient_ms = first_sufficient_ms
        self.tail_wait_ms = tail_wait_ms
        # 旧调用方只传 wasted_ms：别名取同一值，不引入第二个真源。
        self.abandoned_engine_ms = (wasted_ms if abandoned_engine_ms is None
                                    else abandoned_engine_ms)
        self.stranded = tuple(stranded or ())


def summarize_dispatch(*, wall_ms: int, contributed_ms: list[float],
                       first_result_at: float | None,
                       first_sufficient_at: float | None,
                       base: float, abandoned_ms: list[float]) -> dict[str, int]:
    """把调度器的事件时刻折算成对外记账字段（纯函数，便于单测）。

    `base` 是本次编排的单调钟起点；两个 `*_at` 都是绝对时刻。没有可交付结果
    （全失败）时尾等待记 0：没有东西可交付，那段等待不是「可省的」。
    """
    useful_ms = int(min(max(contributed_ms), wall_ms)) if contributed_ms else 0

    def _rel(at: float | None) -> int:
        if at is None:
            return 0
        return int(min(max(at - base, 0.0), wall_ms / 1000.0) * 1000)

    first_result_ms = _rel(first_result_at)
    first_sufficient_ms = _rel(first_sufficient_at)
    anchor = first_sufficient_ms or first_result_ms
    return {
        "useful_ms": useful_ms,
        "first_result_ms": first_result_ms,
        "first_sufficient_ms": first_sufficient_ms,
        "tail_wait_ms": max(0, wall_ms - anchor) if anchor else 0,
        "abandoned_engine_ms": int(sum(abandoned_ms)),
    }
