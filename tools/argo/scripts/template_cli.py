#!/usr/bin/env python3
"""template_cli.py — argo template 子命令：查询模板的发现、展开与执行。

用法：
  argo template --list [--json]                列出全部模板（按分组）
  argo template <id> --dry-run [--json]        只看展开后的命令与查询串，不执行
  argo template <id> [--add 词 ...] [转发参数]  展开并执行

设计要点：
  - 模板是「命名查询模式」，执行面只有一步：展开 → 转发给该模板的 command。
  - 转发参数原样透传（--engine/--mode/-n/--since/--json …），搜索的语义与开关
    仍由 search.py / x_search.py 各自持有——本模块**不复制**任何搜索开关定义，
    否则就是「同一个开关两处声明、改一处漏一处」的老病。
  - 加载/合并/展开是纯逻辑，全在 query_templates.py；本文件只做参数面与输出面
    （分工同 citations.py / cite_cli.py）。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli_io import dumps  # noqa: E402
from query_templates import (  # noqa: E402
    TemplateError, expand, get_template, list_templates, load_templates)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# command → (脚本, 默认参数)。默认参数与 bin/argo 的 dispatcher 保持一致：
# `argo search` 恒带 --json（其输出契约就是 JSON），x-search 默认人读、--json 选开。
_COMMAND_SCRIPTS = {
    "search": ("search.py", ["--json"]),
    "x-search": ("x_search.py", []),
}


def _run_list(registry: dict, as_json: bool) -> int:
    rows = list_templates(registry)
    if as_json:
        print(dumps(rows))
        return 0
    if not rows:
        print("（注册表为空）")
        return 0
    cur = None
    for t in rows:
        if t["category"] != cur:
            cur = t["category"]
            print(f"\n{cur}")
        print(f"  {t['id']:<20} {t['description']}")
    print(f"\n共 {len(rows)} 个模板。展开看命令：argo template <id> --dry-run")
    return 0


def _run_template(tid: str, adds: list[str], dry_run: bool,
                  as_json: bool, forwarded: list[str], registry: dict) -> int:
    t = get_template(registry, tid)
    query = expand(t, adds)
    command = t["command"]
    script, defaults = _COMMAND_SCRIPTS[command]

    if dry_run:
        if as_json:
            print(dumps({"id": tid, "command": command,
                         "query": query, "script": script}))
        else:
            print(f"# 模板: {tid}  →  {command}")
            print(query)
        return 0

    argv = [sys.executable, os.path.join(SCRIPTS_DIR, script)]
    argv += defaults + [query] + forwarded
    proc = subprocess.run(argv, encoding="utf-8", errors="replace")
    return proc.returncode


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="argo template",
        description="查询模板：命名好的检索模式，一步展开并执行",
        epilog="示例：\n"
               "  argo template --list\n"
               "  argo template ai_model_release --add \"GPT-5\" -n 20\n"
               "  argo template ai_zh --sort top --json",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("template", nargs="?", help="模板 id（见 --list）")
    ap.add_argument("--list", action="store_true", help="列出全部模板")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印展开后的命令与查询串，不执行")
    ap.add_argument("--add", action="append", default=[], metavar="词",
                    help="追加检索词（可多次；空格即 AND），与模板 query 组合")
    # --json 在此声明以便 --list 消费；非列表场景下会被重新塞回转发参数，
    # 让底层命令拿到它（`argo template <id> --json` = 要 JSON 结果）。
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args, forwarded = ap.parse_known_args(argv)

    try:
        registry = load_templates()
    except TemplateError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    if args.list:
        return _run_list(registry, args.json)

    if not args.template:
        ap.print_help()
        return 1

    fwd = list(forwarded)
    if args.json:
        fwd.append("--json")

    try:
        return _run_template(args.template, args.add, args.dry_run,
                             args.json, fwd, registry)
    except TemplateError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
