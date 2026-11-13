#!/usr/bin/env python3
"""query_templates.py — 查询模板注册表：加载、合并、展开（纯逻辑）。

职责单一：把 YAML 注册表读成内存结构，按 id 取模板，把模板 + 追加词展开成
最终查询串。**不碰 IO 输出面、不 spawn 子进程**——那些在 template_cli.py
（分工同 citations.py / cite_cli.py）。

两个注册表合并（这是「未知使用需求」的普适性所在）：
  1. 随包注册表  references/query-templates.yaml（随 argo 升级更新，勿手改）
  2. 用户注册表  $XDG_CONFIG_HOME/argo/query-templates.yaml（缺省 ~/.config/argo/）
     或 ARGO_TEMPLATES_FILE 指定的路径
用户表按 id 合并：新 id 追加，同名 id 覆盖随包条目；`disabled: true` 停用随包条目。
于是新增一个领域只要加几行 YAML，零代码、零改仓。

为什么注册表是数据而非代码：模板的本质是「命名查询模式」——一个纯数据问题。
放 YAML 才能让用户零门槛扩展、让 git 管版本、让 --list 自动派生。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
SHIPPED_PATH = SKILL_DIR / "references" / "query-templates.yaml"

# command 白名单：模板只能转发到这些 argo 子命令。用户注册表可写，若不设白名单，
# 一个被篡改/误写的注册表就能借 `argo template` 转发到任意命令——模板是数据，
# 不该有执行任意命令的能力。
COMMANDS = ("search", "x-search")
DEFAULT_COMMAND = "search"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")


class TemplateError(Exception):
    """注册表缺失/损坏、id 未知、字段非法。"""


def user_registry_path() -> Path | None:
    """用户注册表路径（存在才返回）。优先级：ARGO_TEMPLATES_FILE > 平台配置根 > ~/.config。

    与 engine_env._envfile_paths 同源思路（复用 _platform_config_root，避免
    「Windows 取哪个目录」这类平台逻辑在本模块再写一份）。
    """
    explicit = os.environ.get("ARGO_TEMPLATES_FILE", "").strip()
    if explicit:
        return Path(os.path.expanduser(explicit))
    cands: list[Path] = []
    try:
        from engine_env import _platform_config_root
        root = _platform_config_root()
        if root is not None:
            cands.append(root / "argo" / "query-templates.yaml")
    except Exception:
        pass
    cands.append(Path(os.path.expanduser("~/.config/argo/query-templates.yaml")))
    for p in cands:
        if p.exists():
            return p
    return None


def _read_yaml(path: Path) -> dict[str, Any]:
    from yaml_load import load as _yaml_load
    try:
        data = _yaml_load(path)
    except FileNotFoundError:
        raise TemplateError(f"注册表不存在: {path}")
    except Exception as e:  # yaml.YAMLError 等
        raise TemplateError(f"注册表解析失败 {path}: {e}")
    if not isinstance(data, dict):
        raise TemplateError(f"注册表顶层必须是映射: {path}")
    return data


def _normalize(entry: Any, tid: str, src: str) -> dict[str, Any]:
    """校验并规范化单条模板。返回 None 之外的 dict。"""
    if not isinstance(entry, dict):
        raise TemplateError(f"{src}: 模板 {tid} 必须是映射")
    if entry.get("disabled"):
        return {"__disabled__": True}
    query = entry.get("query")
    if not isinstance(query, str) or not query.strip():
        raise TemplateError(f"{src}: 模板 {tid} 缺非空 query")
    command = entry.get("command") or DEFAULT_COMMAND
    if command not in COMMANDS:
        raise TemplateError(
            f"{src}: 模板 {tid} 的 command「{command}」不在白名单 {COMMANDS}")
    return {
        "id": tid,
        "description": str(entry.get("description") or "").strip(),
        "category": str(entry.get("category") or "未分组").strip(),
        "command": command,
        "query": query.strip(),
        "tags": [str(t) for t in (entry.get("tags") or []) if str(t).strip()],
        "note": str(entry.get("note") or "").strip(),
        "source": src,
    }


def _merge_into(registry: dict[str, dict], data: dict[str, Any], src: str) -> None:
    templates = data.get("templates")
    if templates is None:
        return
    if not isinstance(templates, dict):
        raise TemplateError(f"{src}: templates 必须是映射")
    for tid, entry in templates.items():
        tid = str(tid)
        if not _ID_RE.match(tid):
            raise TemplateError(f"{src}: 模板 id 非法（须 [a-z0-9_]）: {tid!r}")
        norm = _normalize(entry, tid, src)
        if norm.get("__disabled__"):
            registry.pop(tid, None)   # 用户表可用 disabled 停用随包模板
            continue
        registry[tid] = norm


def load_templates(*, include_user: bool = True,
                   shipped: Path | None = None,
                   user: Path | None = None) -> dict[str, dict]:
    """加载并合并注册表。返回 {id: 模板}；缺失随包表按空处理（不抛）。

    include_user=False 或显式传 user=None 且不查环境，用于测试与「只看随包」场景。
    """
    registry: dict[str, dict] = {}
    ship = shipped if shipped is not None else SHIPPED_PATH
    if ship.exists():
        _merge_into(registry, _read_yaml(ship), str(ship))
    if include_user:
        up = user if user is not None else user_registry_path()
        if up is not None and up.exists() and up != ship:
            _merge_into(registry, _read_yaml(up), str(up))
    return registry


def list_templates(registry: dict[str, dict]) -> list[dict]:
    """按 (category, id) 排序的模板清单（--list 用）。"""
    return sorted(registry.values(),
                  key=lambda t: (t.get("category", ""), t.get("id", "")))


def get_template(registry: dict[str, dict], tid: str) -> dict:
    """按 id 取模板；未知 id 抛 TemplateError（带 did-you-mean 建议）。"""
    t = registry.get(tid)
    if t is not None:
        return t
    import difflib
    near = difflib.get_close_matches(tid, list(registry), n=3, cutoff=0.4)
    hint = f"（最接近: {', '.join(near)}）" if near else ""
    raise TemplateError(f"未知模板「{tid}」{hint} —— 全部模板见 argo template --list")


def expand(template: dict, adds: list[str] | None = None) -> str:
    """模板 query + 追加词 → 最终查询串。

    追加词以空格拼接（X 语法里空格即 AND）。空追加词/空白被丢弃，不产生
    多余空格。这是模板「可组合」的实现：模板给基线，--add 给具体对象。
    """
    parts = [template.get("query", "")]
    for a in adds or []:
        a = str(a).strip()
        if a:
            parts.append(a)
    return " ".join(p for p in parts if p)
