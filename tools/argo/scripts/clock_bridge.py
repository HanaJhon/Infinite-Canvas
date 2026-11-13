#!/usr/bin/env python3
"""clock_bridge.py — 统一时钟的一行入口（2026-10-24）。

计时断言与「预算夹紧」判定不该取决于机器快慢：测试域用 tests/_measure 的
虚拟时钟，生产路径就是 ``time.monotonic``。各模块从这里取 ``clock``，不再各自
复制一段 try/except（那会让千行文件更难拆，也容易只改一半——本文件对应的
fetch_v3 就曾因「预算夹在超时请求上、耗时却按真实墙钟算」而被测出击穿）。

与 ``tests/_measure.py`` 的关系：那个模块定义语义（虚拟/真实、预算锚点、
确定性时间线），本模块只做「生产环境安全地取到它」这一件事。
"""

from __future__ import annotations

import time

try:  # 测试域：虚拟时钟（见 tests/_measure.py）
    from _measure import clock  # type: ignore
except ImportError:  # pragma: no cover - 生产路径
    clock = time.monotonic

__all__ = ["clock"]
