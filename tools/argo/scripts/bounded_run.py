#!/usr/bin/env python3
"""bounded_run.py — 有界并发执行：总墙钟时间一到就返回，不被慢任务拖住。

背景
----
仓库里多处用 ``with ThreadPoolExecutor(...) as ex:`` 配合
``as_completed(futures, timeout=T)`` 想实现「最多等 T 秒」。但 ``with`` 退出时
会执行 ``shutdown(wait=True)``，把所有还在跑的任务 join 完才真正返回——即使
``as_completed`` 已经超时，调用方仍会被一个卡住的网络读拖住，T 秒预算形同虚设
（实测单查询被拖到 76s）；而且超时抛出的 TimeoutError 若没人接，会直接中断整次
调用，已经拿到的结果也丢了。

做法
----
改用 daemon 线程加轮询：

* 任务跑在 daemon 线程上，到点就返回已完成的结果，**不去 join 还没完成的任务**
  （daemon 线程不会阻止进程退出，各任务内部仍有自己的超时保底）；
* 单个任务抛异常只记成该任务失败，不影响其它任务；
* 总墙钟时间被 ``wait_s`` 硬性约束，不会超出。

时间来源（2026-10-24）
----------------------
本模块读时间只经 ``clock()``、等待只经 ``fetch_sleep()`` / ``poll_wait()``
（见 ``tests/_measure.py``）。原因是实测：调度类用例红过多次，根因全是
「把机器有多忙当成调度对不对」——轮询周期本身会吃掉十几毫秒，于是
「等比累加 sleep 时长」与真实墙钟之间出现系统性偏差。现在一律按**剩余时间**
（deadline 语义）判断还等不等，单次轮询抖动不再累加。

「完成」的判据与池化
--------------------
判定某任务完成一律看 ``holder["done"]``，**不看** ``Thread.is_alive()``：
线程跑完最后一行到被主循环观测之间有一段窗口，is_alive() 会把这段窗口里的
任务误判成「还在跑」，旧实现因此在全量套件里间歇性把已完成结果记成超时。
主循环改为：补发 → 收成 → 判断是否够（enough）→ 判断是否到点 → 再等一拍。
「到点再收一次」放在循环尾部，保证最后一批结果不会被预算边界吃掉。
"""

from __future__ import annotations

import contextlib
import threading
import time
from typing import Any, Callable, Generic, TypeVar

try:  # 测试域由 tests/_measure 注入虚拟时钟；运行期退回真实时间
    from _measure import clock, fetch_sleep, poll_wait, task_deadline  # type: ignore
except ImportError:  # pragma: no cover - 生产路径
    clock = time.monotonic
    fetch_sleep = time.sleep

    def poll_wait(seconds: float, evt: threading.Event | None = None) -> None:
        (evt.wait(seconds) if evt is not None else time.sleep(seconds))

    @contextlib.contextmanager
    def task_deadline(_deadline: float | None = None, *, budget_s: float | None = None):
        yield

I = TypeVar("I")
O = TypeVar("O")


class TaskError(Generic[I]):
    """单个任务执行时抛了异常。用对象而非魔法字符串承载，避免和任务正常返回值混淆。"""

    __slots__ = ("exc", "item")

    def __init__(self, item: I, exc: BaseException):
        self.item = item
        self.exc = exc

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"TaskError(item={self.item!r}, exc={self.exc!r})"


def run_bounded(
    items: list[I],
    worker: Callable[[I], O],
    wait_s: float,
    max_workers: int = 3,
    *,
    enough: Callable[[list[tuple[I, Any]]], bool] | None = None,
    stagger_s: float = 0.0,
    poll: float = 0.01,
) -> tuple[list[tuple[I, Any]], list[I]]:
    """并发执行 ``worker(item)``，总等待不超过 ``wait_s`` 秒。

    返回 ``(finished, unfinished)``：

    * ``finished``：已完成任务的 ``(item, value)`` 列表，按完成先后排列；
      任务抛异常时 ``value`` 是 :class:`TaskError`，调用方按需转成失败占位。
    * ``unfinished``：到点仍没完成（或被 ``enough`` 提前收尾时还在跑）的 item
      列表。这些任务不会被 join，本函数因此能准时返回。

    ``enough(finished)`` 返回 True 时提前收尾：不再启动排队中的剩余任务，已在跑
    的任务归入 unfinished。``max_workers`` 限制同时在跑的任务数。

    ``stagger_s`` 起步间隔（秒），单调：0 = 不节流（立即填满并发位）；值越大越
    接近严格串行（大于单任务超时上限即完全退回串行）。仅在**有任务在跑**时节制
    ——对冲语义（首任务先跑，宽限窗内交付就只付一次调用），而非无条件串行化；
    在跑任务数为 0 时立即补发（前一个已返回，没有可对冲的对象，等满窗纯属浪费）。
    engine_dispatch 的 hedged race 与 search_pipeline 的恢复链是同一哲学的两个
    配置：改这里的起步语义，两边同时生效。
    """
    queue = list(items)
    running: list[tuple[threading.Thread, I, dict]] = []
    finished: list[tuple[I, Any]] = []
    # 预算锚点必须在启动任何线程之前取：线程一推进时钟，deadline 就跟着漂。
    t0 = clock()
    deadline = t0 + max(0.0, float(wait_s))
    last_start: float | None = None
    done_evt = threading.Event()

    def _start(item: I) -> None:
        holder: dict = {}

        def _work() -> None:
            try:
                # 任务的等待继承本轮预算：超过预算仍未回来，测试域会立刻指认
                # 「这次等待越过了预算」，而不是让调用方事后拿墙钟去猜。
                # 用**相对预算**而不是外围算好的绝对 deadline：那个 deadline
                # 取自 clock()，与本层真实模式下的 monotonic 不同源（实测混用会
                # 得到「已过期 65 秒」的假锚点，把正常等待判成越界）。
                with task_deadline(budget_s=max(0.0, deadline - t0)):
                    holder["v"] = worker(item)
            except BaseException as exc:  # noqa: BLE001 - 任意任务异常都要隔离
                holder["v"] = TaskError(item, exc)
            finally:
                holder["done"] = True
                done_evt.set()

        th = threading.Thread(target=_work, daemon=True)
        th.start()
        running.append((th, item, holder))

    def _harvest() -> bool:
        """收已完成的任务，返回本轮是否收到新结果。"""
        got = False
        for entry in list(running):
            th, item, holder = entry
            if not holder.get("done"):
                continue
            running.remove(entry)
            finished.append((item, holder.get(
                "v", TaskError(item, RuntimeError("任务结束但没有返回值")))))
            got = True
        return got

    while queue or running:
        done_evt.clear()
        # 1) 补发排队任务（受并发上限与 stagger 节流约束）
        while queue and len(running) < max(1, int(max_workers)):
            if (stagger_s > 0 and running and last_start is not None
                    and (clock() - last_start) < stagger_s):
                break  # 起步节流：等满 stagger 再补发（对冲）
            _start(queue.pop(0))
            last_start = clock()
        # 2) 收成。注意不能因为收到结果就 `continue`：那会跳过本轮的
        #    enough 判定与到点判定，把「够了就收工」变成「等下一个任务也回来」。
        _harvest()
        # 3) 够了就提前收工：排队中的任务不再启动（它们是主动放弃，不是超时）
        if enough is not None and enough(finished):
            queue.clear()
            break
        # 4) 到点必须收工——但先再收一次，别把预算边界上刚好完成的结果丢掉
        if clock() >= deadline:
            _harvest()
            break
        # 5) 等一拍：按**剩余时间**算，不让单次抖动累加成常驻偏差
        if not queue and not running:
            break
        remain = deadline - clock()
        wait_step = remain
        if queue and stagger_s > 0 and last_start is not None:
            wait_step = min(wait_step, max(0.0, stagger_s - (clock() - last_start)))
        step = min(poll, wait_step) if poll > 0 else wait_step
        poll_wait(step, done_evt)

    # 收尾：再收一次（线程与观测之间有时间差），其余不 join、计入 unfinished。
    _harvest()
    # 没排上起跑的任务（仍在 queue）与新起跑但没回来的任务（running）都要进
    # unfinished：前者只是没轮到，但也确实没结果，悄悄丢掉会让调用方以为
    # 「全部拿到了」。两者的区别用 downstream 的 enough 提前收尾路径处理：
    # 那条路径上 queue 已被清空，所以不会有误报。
    unfinished: list[I] = list(queue) + [item for _th, item, _h in running]
    return finished, unfinished
