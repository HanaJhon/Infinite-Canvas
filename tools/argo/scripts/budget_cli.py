#!/usr/bin/env python3
"""budget_cli.py — `argo budget`：按引擎的月度预算读写口。

用法：
  argo budget list [--json]
  argo budget set <engine> <amount> [--currency CNY|USD] [--period month|day]
  argo budget unset <engine>

预算存在 ~/.config/argo/budgets.json（`ARGO_BUDGET_FILE` 可覆盖）；`quota.py`
启动时读取，按引擎原生币种与调用成本比较。默认只有 DeepSeek ¥5/月。
"""

from __future__ import annotations

import argparse
import sys

import budget
from cli_io import dumps


def _cmd_list(args: argparse.Namespace) -> int:
    items = budget.load_budgets()
    try:
        from quota import get_quota_manager
        stats = get_quota_manager().get_stats()
    except Exception:
        stats = {}
    rows = []
    for engine, entry in sorted(items.items()):
        st = stats.get(engine) or {}
        rows.append({
            "engine": engine,
            "amount": entry["amount"],
            "currency": entry["currency"],
            "period": entry["period"],
            "cost_used": st.get("cost_used"),
            "cost_per_call": st.get("cost_per_call"),
            "available": st.get("available"),
        })
    if args.json:
        print(dumps({"file": str(budget.budget_file()), "budgets": rows}))
    else:
        print(f"预算文件：{budget.budget_file()}")
        if not rows:
            print("（无预算；引擎沿用 quota_profiles.json 的次数额度）")
        for r in rows:
            print(f"  {r['engine']:<20} {r['amount']:>8.2f} {r['currency']}/"
                  f"{r['period']}  已用 {r['cost_used']}  可用={r['available']}")
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    try:
        entry = budget.set_budget(args.engine, args.amount,
                                  currency=args.currency,
                                  period=args.period)
    except ValueError as exc:
        print(f"设置失败：{exc}", file=sys.stderr)
        return 2
    print(f"已设置 {args.engine}: {entry['amount']} {entry['currency']}/{entry['period']}"
          f"（{budget.budget_file()}）")
    return 0


def _cmd_unset(args: argparse.Namespace) -> int:
    ok = budget.unset_budget(args.engine)
    print(("已删除 " if ok else "未找到 ") + args.engine)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="argo budget",
                                 description="按引擎的月度预算（原生币种）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list", help="列出预算与本月已用")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=_cmd_list)
    p_set = sub.add_parser("set", help="设置某引擎预算")
    p_set.add_argument("engine")
    p_set.add_argument("amount", type=float)
    p_set.add_argument("--currency", default="CNY")
    p_set.add_argument("--period", default="month", choices=["day", "month"])
    p_set.set_defaults(func=_cmd_set)
    p_unset = sub.add_parser("unset", help="删除某引擎预算")
    p_unset.add_argument("engine")
    p_unset.set_defaults(func=_cmd_unset)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
