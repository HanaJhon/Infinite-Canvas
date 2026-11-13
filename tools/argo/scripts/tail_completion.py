"""tail_completion.py — 早停后台补全：慢源交付从「丢弃」变「补齐」。

## 为什么（2026-10-25）

七天窗口 1185 条真实查询里 74% 发生 early-stop。被放弃的交付不是低质货：
离线回放（bench_tail_ab --quality）显示被放弃交付 81% 来自 anysearch，相关度
代理比全库均线高 0.125；五条对照查询里四条「唯一有结果的就是慢源」（证据与
口径见 docs/QUALITY_OF_SLOW_SOURCES.md）。早停省的是**用户等待**，不该连
**交付**一起丢——那是在拿准确性换速度。缩尾宽已被实证否决，本模块是拍板的
正确方向：慢源不拖住快源（早交付），但慢源的交付进缓存（后台补全）。

## 做什么

engine_dispatch 在早停弃置引擎时把 (engine, holder, now_fn) 交给本模块——
主响应与既有记账逐位不变（cancelled outcome / abandoned_ms 照记）。本模块
起一个 daemon 收割线程，在主流程返回后继续等被弃置的引擎，宽限内完成的：

1. 学习器记真实成绩（success / latency / quality / 场景分桶标签）——此前
   cancelled 被 cache_guard.should_record_adaptive 跳过，慢源的真实表现
   从没进过学习器，场景分桶（engine×domain×lang）也少一笔真数据；
2. 把交付合并写回 L2 combo 缓存（URL 去重、新条目追加、缺省 score 用词面
   相关度）——同查询第二次免费拿到「快源+慢源」的全量覆盖。

timeout 弃置不收：那是引擎确实超窗（甚至卡死），补全等于鼓励慢源；
cancelled 是「编排收工决定，引擎没失败」——两者语义不同（见
engine_dispatch._settle_pending 的注释）。

## 进程语义

收割线程是 daemon；CLI 进程退出前由 atexit 宽限等待（hand_off 首次调用时
注册，无 stranded 的进程零成本、不注册）。MCP/daemon 常驻进程不退出，
自然收割全部。宽限从**入队时刻**起算整批（job 级 deadline），不做逐引擎
累加——实测被放弃交付从早停时刻起的剩余等待 p50 2306ms / p90 3883ms。

## 开关

ARGO_TAIL_COMPLETE_S：宽限秒数（默认 3.0；0=禁用整个机制，行为回到
纯丢弃）。改动记得同步 references/usage.md 的开关总表（usage_doc_gates）。
"""

from __future__ import annotations

import atexit
import os
import threading

_LOCK = threading.Lock()
_JOBS: list[dict] = []
_WORKER: threading.Thread | None = None
_ATEXIT_REGISTERED = False
_STATS = {"salvaged": 0, "expired": 0, "recorded": 0}
_POLL_INTERVAL_S = 0.05


def grace_seconds() -> float:
    """收割宽限（ARGO_TAIL_COMPLETE_S，默认 3.0；<=0 禁用）。"""
    try:
        return float(os.environ.get("ARGO_TAIL_COMPLETE_S", "3.0") or 3.0)
    except ValueError:
        return 3.0


def hand_off(stranded, *, query, cache_engine_key, max_results,
             domain, mode, depth, decision, skip_cache=False,
             cache_instance=None) -> None:
    """把早停弃置的引擎交给后台收割。

    ``stranded`` 是 engine_dispatch 产出的 ``[(engine, holder, now_fn), ...]``：
    holder["r"] 出现即完成（与 _ingest_holder 同判据），now_fn 用于算真实
    latency（dispatch 可能跑在单调钟上，收割线程不能用墙钟去减）。
    ``cache_instance`` 是本次请求的缓存实例（req.cache）：补全读写的必须是
    同一实例（L1 内存态 + L2 落盘一致），模块级没有全局缓存可拿。
    其余参数与 finalize 的 cache.set / learner.record 同源同口径。
    任何异常 fail-open：补全失败只丢「锦上添花」，不影响主响应。
    """
    grace = grace_seconds()
    if grace <= 0 or not stranded:
        return
    global _ATEXIT_REGISTERED
    with _LOCK:
        if not _ATEXIT_REGISTERED:
            atexit.register(wait_for_completion)
            _ATEXIT_REGISTERED = True
        _JOBS.append({
            "stranded": list(stranded),
            "deadline": _now_wall() + grace,
            "query": query, "cache_engine_key": cache_engine_key,
            "max_results": max_results, "domain": domain,
            "mode": mode, "depth": depth, "decision": decision or {},
            "skip_cache": bool(skip_cache) or cache_instance is None,
            "cache": cache_instance,
        })
        _start_worker_locked()


def wait_for_completion(timeout_s: float | None = None) -> None:
    """等收割线程收尾（atexit 出口 / 测试用）。宽限耗尽即返回，不无限等。"""
    t = _WORKER
    if t is not None and t.is_alive():
        budget = timeout_s if timeout_s is not None else grace_seconds() + 0.5
        t.join(timeout=budget)


def stats() -> dict:
    """收割计数（可观测口，供诊断；不改任何行为）。"""
    with _LOCK:
        return dict(_STATS)


def _now_wall() -> float:
    import time
    return time.time()


def _start_worker_locked() -> None:
    global _WORKER
    if _WORKER is not None and _WORKER.is_alive():
        return
    _WORKER = threading.Thread(target=_worker, daemon=True,
                               name="argo-tail-completion")
    _WORKER.start()


def _worker() -> None:
    """串行收割队列：宽限内完成的记学习器+合并缓存，超宽限标 expired。"""
    import time
    while True:
        with _LOCK:
            if not _JOBS:
                return
            job = _JOBS.pop(0)
        for eng, holder, now_fn in job["stranded"]:
            remaining = job["deadline"] - _now_wall()
            while holder.get("r") is None and remaining > 0:
                time.sleep(min(_POLL_INTERVAL_S, remaining))
                remaining = job["deadline"] - _now_wall()
            res = (holder.get("r") or (None,))[1] if holder.get("r") else None
            if res is None:
                with _LOCK:
                    _STATS["expired"] += 1
                continue
            goods = [r for r in (res or [])
                     if isinstance(r, dict) and "error" not in r]
            with _LOCK:
                _STATS["salvaged"] += 1
            try:
                _record_adaptive(eng, goods, holder, now_fn, job)
            except Exception:
                pass
            if not job["skip_cache"]:
                try:
                    _merge_into_cache(eng, goods, job)
                except Exception:
                    pass


def _record_adaptive(eng, goods, holder, now_fn, job) -> None:
    """学习器记真实成绩（口径与 search_pipeline.finalize 对齐）。"""
    from adaptive import get_learner, scenario_of
    from query_signals import result_relevance
    success = bool(goods)
    try:
        lat_ms = float((now_fn() - holder.get("t0", now_fn())) * 1000.0)
    except Exception:
        lat_ms = 0.0
    quality = None
    if success:
        try:
            quality = result_relevance(job["query"], goods)
        except Exception:
            quality = None
    with _LOCK:
        _STATS["recorded"] += 1
    get_learner().record(eng, success=success, latency_ms=max(0.0, lat_ms),
                         cost=0.001, empty=not success, quality=quality,
                         **scenario_of(job["decision"]))


def _merge_into_cache(eng, goods, job) -> None:
    """交付合并写回 L2 combo 缓存：读现条目 → URL 去重追加 → 同 key 覆盖。

    只在已有缓存条目时合并（本机制补的是「快源已写的那份」）；主缓存被守卫
    拒写时这里不硬造。score 缺省用词面相关度，保证追加条目有可排序的分数。
    """
    from query_signals import result_relevance
    cache = job["cache"]
    cur = cache.get(job["query"], job["cache_engine_key"],
                    job["max_results"], domain=job["domain"],
                    mode=job["mode"], depth=job["depth"])
    if not cur or not isinstance(cur.get("results"), list) or not goods:
        return
    existing = {r.get("url") for r in cur["results"]
                if isinstance(r, dict)}
    new: list[dict] = []
    for r in goods:
        if not isinstance(r, dict) or r.get("url") in existing:
            continue
        item = dict(r)
        if "score" not in item:
            try:
                item["score"] = round(float(result_relevance(job["query"], [r])), 4)
            except Exception:
                item["score"] = 0.3
        new.append(item)
    if not new:
        return
    payload = dict(cur)
    payload["results"] = list(cur["results"]) + new
    payload["engines_used"] = sorted({*(cur.get("engines_used") or []), eng})
    cache.set(job["query"], job["cache_engine_key"], job["max_results"],
              payload, domain=job["domain"], mode=job["mode"],
              depth=job["depth"])
