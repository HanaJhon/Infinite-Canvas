#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""版本号规则：三段式 + 满十进位（作者口径）。

规则
----
版本号形如 a.b.c，从 1.1.1 起算，每发一版末段 +1：

    1.1.1 → 1.1.2 → … → 1.1.9 → 1.2.0    末段满 10：中段 +1、末段归 0（仍是三段）
    1.2.9 → 1.3.0                        同上
    1.9.9 → 2.0                          中段也满：首段 +1，丢掉归零的末段（缩成两段）
    2.9   → 3.0
    9.9   → 10                           首段满 10 不再进位，缩成一段后继续 11、12…
    10    → 11

一句话：**每多进一级就少一段**，段数只减不增（3 → 2 → 1）。

为什么要独立成模块
------------------
VERSION 文件是全项目唯一的版本来源，被四处消费：

    main.py   current_app_version()   → /api/app-info、/api/check-update、静态资源 ?v=
    launcher  LocalVersion()          → 胶囊上的 V 号、更新比对
    launcher  HandleCheckUpdateAsync  → CompareVersion(latest, current)
    release.py read_version()         → 包名、Release tag、update.json.version

进位一旦靠人手算，就会出现「VERSION 写 1.1.10、update.json 写 1.2.0」这种
不一致 —— 客户端装完新版 VERSION 仍是 1.1.10，比对结果永远是「有新版」，
陷入**更新死循环**。所以规则集中在这里。

C# 侧有一份等价实现 `launcher/VersionUtil.cs`；两边的自测向量表共用
`tools/version_vectors.json`，任何一边改了规则都必须同时过测（否则测试会红）。
"""

from __future__ import annotations

import json
import os
import re

VECTORS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "version_vectors.json")

# 日期制遗留（老安装的 VERSION，如 2026.09.20）。
# 这类值**不参与**进位换算，原样保留：否则 2026.09.20 会被算成 2027.1，
# 胶囊上显示成 V2027.1，更新比对也会跟着错乱。
LEGACY_DATE_RE = re.compile(r"^\d{4}\.\d{1,2}\.\d{1,2}$")

# 规范式：1~3 段数字。首段允许 ≥10（如 10、10.0），因为首段满 10 不再进位。
CANONICAL_RE = re.compile(r"^\d+(?:\.\d+){0,2}$")

# 可接受的 VERSION 写法 = 规范式 或 日期制遗留
ACCEPTED_RE = re.compile(r"^\d{4}\.\d{1,2}\.\d{1,2}$|^\d+(?:\.\d+){0,2}$")


def parse_version(value) -> list[int]:
    """取出所有数字段。'1.1.10' → [1, 1, 10]。"""
    return [int(x) for x in re.findall(r"\d+", str(value or ""))]


def is_legacy_date(value) -> bool:
    """是否为日期制遗留版本（如 2026.09.20）。"""
    return bool(LEGACY_DATE_RE.match(str(value or "").strip()))


def normalize_version(value) -> str:
    """把任意写法的版本号折算成「进位后」的规范式（幂等）。

    >>> normalize_version("1.1.10")
    '1.2.0'
    >>> normalize_version("1.10.0")
    '2.0'
    >>> normalize_version("1.2.0")
    '1.2.0'
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    if is_legacy_date(raw):
        return raw
    parts = parse_version(raw)
    if not parts:
        return ""

    while True:
        over = [i for i, x in enumerate(parts) if x >= 10]
        if not over:
            break
        i = over[-1]                       # 最靠右的溢出位
        if i == 0:
            # 首段溢出：没有更高位可进，不再进位（9.9 -> 10），并把多出来的段丢掉
            parts = parts[:1]
            break
        carry, parts[i] = divmod(parts[i], 10)
        parts[i - 1] += carry
        if i < len(parts) - 1:
            # 中间位溢出：它右边那些段已归零，按「每多进一级少一段」丢掉
            parts = parts[:i + 1]

    return ".".join(str(x) for x in parts)


def bump_version(value) -> str:
    """返回下一个版本号。日期制遗留值返回空串（需先 --set 切到三段式）。"""
    raw = str(value or "").strip()
    if not raw or is_legacy_date(raw):
        return ""
    parts = parse_version(raw)
    if not parts:
        return ""
    parts[-1] += 1
    return normalize_version(".".join(str(x) for x in parts))


def is_canonical(value) -> bool:
    """是否已经是规范式（折算后与自身完全相同）。"""
    raw = str(value or "").strip()
    return bool(raw) and normalize_version(raw) == raw


def load_vectors() -> dict:
    with open(VECTORS_PATH, encoding="utf-8") as f:
        return json.load(f)


def run_selftest(verbose: bool = True) -> int:
    """跑共用向量表。返回 0 通过 / 1 失败。"""
    vec = load_vectors()
    bad: list[str] = []

    for case in vec.get("normalize", []):
        raw, want = case[0], case[1]
        got = normalize_version(raw)
        if got != want:
            bad.append(f"normalize({raw!r}) = {got!r}，期望 {want!r}")

    for case in vec.get("bump", []):
        raw, want = case[0], case[1]
        got = bump_version(raw)
        if got != want:
            bad.append(f"bump({raw!r}) = {got!r}，期望 {want!r}")

    total = len(vec.get("normalize", [])) + len(vec.get("bump", []))
    if verbose:
        if bad:
            for line in bad:
                print("[FAIL] " + line)
            print(f"[FAIL] 版本规则自测：{len(bad)}/{total} 条向量未通过")
        else:
            print(f"[OK] 版本规则自测：{total} 条向量全部通过")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(run_selftest())
