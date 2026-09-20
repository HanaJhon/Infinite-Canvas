#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""版本号递增工具：读 VERSION → 按规则 +1 → 写回。

用法
----
    python tools/bump_version.py                    # 升一版并写回 VERSION
    python tools/bump_version.py --dry-run          # 只打印，不写盘
    python tools/bump_version.py --times 3          # 连升 3 版（用来预览连续进位）
    python tools/bump_version.py --set 1.1.10       # 把 VERSION 规范成 1.2.0
    python tools/bump_version.py --self-test        # 只跑版本规则自测

规则见 tools/versioning.py 顶部注释。**不要手改 VERSION**：手写 1.1.10 这种
非规范式会让 update.json 与包内 VERSION 对不上，客户端会陷入更新死循环。
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from versioning import (  # noqa: E402
    bump_version,
    is_legacy_date,
    normalize_version,
    run_selftest,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(ROOT, "VERSION")


def read_current() -> str:
    if not os.path.isfile(VERSION_FILE):
        sys.exit("[FATAL] 找不到 VERSION 文件")
    lines = open(VERSION_FILE, encoding="utf-8").read().strip().splitlines()
    return lines[0].strip() if lines else ""


def write_version(value: str) -> None:
    # 显式 newline="\n"：Windows 上避免写成 CRLF，让 VERSION 在各平台逐字一致
    with open(VERSION_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(value + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="按「三段式 + 满十进位」规则递增 VERSION",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写盘")
    ap.add_argument("--times", type=int, default=1, help="连续升几版（默认 1）")
    ap.add_argument("--set", dest="set_to", default="",
                    help="直接把 VERSION 设为该值（会先做规范化）")
    ap.add_argument("--self-test", action="store_true", help="只跑版本规则自测")
    args = ap.parse_args()

    if args.self_test:
        return run_selftest()

    current = read_current()
    if not current:
        sys.exit("[FATAL] VERSION 文件是空的")

    # --set：把任意写法折算成规范式
    if args.set_to:
        new = normalize_version(args.set_to)
        if not new:
            sys.exit(f"[FATAL] 无法规范化 {args.set_to!r}")
        if new == current:
            print(f"当前版本已是 {current}，无需改动")
            return 0
        print(f"规范化：{args.set_to} → {new}")
        if args.dry_run:
            print("[dry-run] 未写盘")
            return 0
        write_version(new)
        print(f"[OK] 已写入 VERSION：{current} → {new}")
        return 0

    if args.times < 1:
        sys.exit("[FATAL] --times 至少为 1")

    if is_legacy_date(current):
        sys.exit(
            f"[FATAL] 当前 VERSION 是日期制遗留（{current}），无法按三段式进位。\n"
            f"        请先切到三段式：python tools/bump_version.py --set 1.1.1"
        )

    seq = [current]
    cur = current
    for _ in range(args.times):
        nxt = bump_version(cur)
        if not nxt:
            sys.exit(f"[FATAL] 无法从 {cur!r} 推进版本")
        seq.append(nxt)
        cur = nxt

    print(f"当前版本：{current}")
    print(f"下一版本：{seq[1]}")
    if args.times > 1:
        print("连续进位：" + " → ".join(seq))

    if args.dry_run:
        print("[dry-run] 未写盘")
        return 0

    write_version(seq[1])
    print(f"[OK] 已写入 VERSION：{current} → {seq[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
