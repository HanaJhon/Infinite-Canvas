#!/usr/bin/env python3
"""usage_log_clean — 生产使用日志的夹具污染隔离（维护工具，隔离不删除）。

背景（2026-10-10 侦察轮发现、10-11 实测定性）：本仓 benchmark/评测曾直写
生产状态目录，query.jsonl 的 982 条真实记录混入 334 条夹具引擎条目
（slow_primary / fast_garbage / g1 / fast_backup 等），P50/P90 与引擎频次
统计全部失真。脚本侧已于 10-10 接 isolate_state_dir（防新增）；本工具清
历史存量——夹具行原样移入 <stream>.jsonl.quarantine-<ts>，主文件只留
真实条目，数据零丢失。

引擎名真值来源：engines.available_engines()（与路由同源，253 个）。
engines_used 出现任何表外名即判夹具。两处历史别名显式豁免（引擎改名前的
旧条目，不是夹具）：openlibrary→open_library、bing→bing_rss。
recovery.jsonl 无 engines_used 字段，2026-10-11 全文扫描零夹具命中，
不在本工具处理范围。

用法（建议 argo 空闲时跑；写回前会重读并把窗口内新追加的行接回 kept，
不再静默丢失——但仍建议停掉 daemon/MCP 等持续写入方，避免夹具判定
跨窗口不一致）：
  python3 scripts/usage_log_clean.py            # 干跑：只报告不动文件
  python3 scripts/usage_log_clean.py --apply    # 实际隔离
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engines import available_engines  # noqa: E402
from usage_log import usage_log_dir  # noqa: E402
import argo_paths  # noqa: E402

# 引擎改名前的历史别名：表外但真实，豁免隔离（维护者注释留在账上）
_ALIAS_KEEP = frozenset({"openlibrary", "bing"})

_STREAM = "query"


def _fixture_engines(used: list) -> list[str]:
    """一条记录的表外引擎名（别名豁免后）。"""
    return [e for e in used if e not in _ALIAS_KEEP and e not in _CANON]


_CANON = frozenset(available_engines())


def _clean(path: Path, apply: bool) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept: list[str] = []
    quarantine: list[str] = []
    bad_names: Counter = Counter()
    for line in lines:
        if not line.strip():
            continue
        try:
            used = json.loads(line).get("engines_used") or []
        except json.JSONDecodeError:
            kept.append(line)  # 读不动的行不是隔离对象，原样保留
            continue
        bad = _fixture_engines(used)
        if bad:
            bad_names.update(bad)
            quarantine.append(line)
        else:
            kept.append(line)
    report = {
        "stream": _STREAM,
        "path": str(path),
        "total": len(kept) + len(quarantine),
        "kept": len(kept),
        "quarantined": len(quarantine),
        "fixture_engines": dict(bad_names.most_common()),
        "applied": False,
    }
    if apply and quarantine:
        # 写回前重读一次，把「快照读」与「原子写」之间并发追加的新行接在
        # kept 之后——否则这段窗口里落进的真实查询会被静默吞掉（旧实现
        # 整文件替换为读时的旧视图，docstring 的错误承诺正好相反）。
        # 追加行夹在既有行之后，无法用「是否为快照行」区分，只能按行数增量
        # 取尾部；夹具行本工具只报一次，多余不影响数据（它们仍会进下次账）。
        try:
            current = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            current = lines
        appended = current[len(lines):] if len(current) > len(lines) else []
        kept = kept + [ln for ln in appended if ln.strip()]
        stamp = time.strftime("%Y%m%d-%H%M%S")
        q_path = path.with_name(f"{path.name}.quarantine-{stamp}")
        argo_paths.atomic_write_text(q_path, "\n".join(quarantine) + "\n")
        argo_paths.atomic_write_text(path, "\n".join(kept) + "\n")
        report["applied"] = True
        report["quarantine_path"] = str(q_path)
        report["appended_kept"] = len(appended)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="使用日志夹具污染隔离（维护工具）")
    ap.add_argument("--apply", action="store_true",
                    help="实际执行隔离；默认干跑只报告")
    args = ap.parse_args(argv)
    path = usage_log_dir() / f"{_STREAM}.jsonl"
    print(json.dumps(_clean(path, apply=args.apply), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
