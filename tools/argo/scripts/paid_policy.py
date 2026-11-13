#!/usr/bin/env python3
"""paid_policy.py — 付费搜索的自动对冲位（2026-10-21，方案一）。

只解决一件事：在**已证明有优势的域**里，把付费引擎放到 combo 第二位当对冲，
而不是让它进通用候选池（那会被 TF-IDF/兜底带到任意查询并扣费）。

策略：
  - `ARGO_PAID_SEARCH=off` → 完全关闭；缺省 `auto`。
  - 该域在 `PAID_DOMAIN_HEDGES` 里，且引擎 key 就绪、月度预算未用完
    → 返回该引擎；预算用完/无 key → 回落 `tinyfish`（免费、带日期），
    再不行返回空，由原 combo 继续。
  - `fast`/`budget` 模式不参与（与 quota 的成本纪律一致）。

当前只开三个域：`english_tech`、`intl_news_flash`、`global_event`。
依据 2026-10-21 多引擎实测：DeepSeek 在英文技术/英文新闻上 p50 515ms、
日期覆盖 23/39，明显优于 anysearch/Exa/Tavily；中文宽泛新闻与金融原文
反而更差，故不纳入。

2026-10-27（issue #23）追加**语言条件**：`general_search` 且
`primary_lang=en` 时同样常驻第二位。实测该查询 DeepSeek 589ms/5 条/
7,064B/5 条带 authority，比免费领队的 1.4–3.0s 更快、比中文长摘要源
体积小一半；费用 ¥0.005/次（5 元/月≈1000 次），预算耗尽自动跳过。中文
通用仍不加——按 10-21 的实测结论走。
"""

from __future__ import annotations

import os

__all__ = ["PAID_DOMAIN_HEDGES", "hedge_for", "insert_hedge"]

PAID_DOMAIN_HEDGES: dict[str, str] = {
    "english_tech": "deepseek_search",
    "intl_news_flash": "deepseek_search",
    # 2026-10-26：英文新闻里 `US election latest` / `Middle East ceasefire`
    # 实际落在这个域（不是 intl_news_flash）；不加这一条，DeepSeek 拿不到
    # 这类查询。新闻域的收益最明确，放在第二位。
    "global_event": "deepseek_search",
}

# 插入位置默认第二位。english_tech 可选用 ARGO_PAID_HEDGE_DEFER=1 降到
# 第三位（wave-1 只跑免费源，不够才付费）。2026-10-26 四臂实测：
#   常驻第二位 p50 726ms / 均值 967ms / 权威覆盖 0.83；
#   条件第三位 p50 749ms / 均值 1246ms / 权威覆盖 0.50，DeepSeek 调用少 75%。
# p50 打平、均值与权威覆盖常驻更好，而 5 元/月额度足够覆盖这两个域，
# 故默认常驻；预算紧张或要严格省钱时再开 DEFER。
# general_search 的英文对冲同样受 DEFER 控制：DEFER=1 时降到第三位，
# 免费源够用就完全不付费（1000 次/月的额度也能再省一道）。
_DEFER_DOMAINS = frozenset({"english_tech", "general_search"})

_FREE_FALLBACK = "tinyfish"


def _flag(name: str, default: bool = False) -> bool:
    try:
        from engine_env import env_flag
        return bool(env_flag(name, default=default))
    except Exception:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return raw.strip().lower() not in ("", "0", "false", "no", "off")


def _hedge_position(domain: str) -> int:
    """付费对冲插入位置：默认第二位；ARGO_PAID_HEDGE_DEFER=1 时
    english_tech 降到第三位（免费源先跑，不达标才付费）。

    位置决定「免费源够用时是否还付费」，是速度与成本的直接旋钮；默认值
    由 2026-10-26 四臂实测决定，见上方注释。
    """
    if _flag("ARGO_PAID_HEDGE_DEFER") and str(domain or "") in _DEFER_DOMAINS:
        return 2
    return 1


def _enabled() -> bool:
    try:
        from engine_env import get_env
        raw = get_env("ARGO_PAID_SEARCH", "auto")
    except Exception:
        raw = os.environ.get("ARGO_PAID_SEARCH", "auto")
    return raw.strip().lower() not in ("off", "0", "false", "no")


def _key_ready(engine: str) -> bool:
    try:
        from engine_env import missing_env_for
        return not missing_env_for(engine)
    except Exception:
        return False


def _budget_ok(engine: str) -> bool:
    try:
        from quota import get_quota_manager
        return not get_quota_manager().is_hard_down(engine)
    except Exception:
        # 预算层读失败时 fail-closed：宁可不自动花钱
        return False


def _healthy_and_enabled(engine: str, enabled: set[str] | None) -> bool:
    if enabled is not None and engine not in enabled:
        return False
    try:
        from route_combo import _breaker_blocked
        if _breaker_blocked(engine):
            return False
    except Exception:
        pass
    return True


def _env_allowed(engine: str) -> bool:
    """尊重 ENABLE/DISABLE 环境开关（付费例外只豁免 explicit_only）。"""
    try:
        from engine_env import is_engine_allowed_by_env
        return bool(is_engine_allowed_by_env(engine))
    except Exception:
        return True


def _admission_ok(engine: str) -> bool:
    try:
        from engine_admission import is_blocked
        return not is_blocked(engine)
    except Exception:
        return True


def _paid_hedge_ready(engine: str) -> bool:
    """白名单里的付费引擎：豁免 explicit_only，其余门槛一个不少。

    为什么不能只查 `engine in enabled`：`deepseek_search` 声明了
    `explicit_only`，而 `config._routable_filter` 正是把它从 enabled 里剔掉
    的那一处（防付费源被 TF-IDF/兜底带到任意查询）。付费对冲是**显式白名单**
    （PAID_DOMAIN_HEDGES），成员资格不能再用 enabled 判一次，否则策略从
    2026-10-21 起就是死代码。这里改为逐项检查：env 禁用、准入拉黑、熔断、
    key、月度预算，仍全部生效。
    """
    if not _env_allowed(engine) or not _admission_ok(engine):
        return False
    try:
        from route_combo import _breaker_blocked
        if _breaker_blocked(engine):
            return False
    except Exception:
        pass
    return _key_ready(engine) and _budget_ok(engine)


def hedge_for(domain: str, mode: str = "auto",
              enabled: set[str] | None = None,
              lang: str = "") -> list[str]:
    """返回该域应插入的付费/回落引擎（0 或 1 个）。永不抛异常。

    `lang` 只对 general_search 生效：英文通用查询才加 DeepSeek 对冲，
    中文通用按 10-21 实测结论不加（中文宽泛查询它更差）。
    """
    if not _enabled() or mode in ("fast", "budget"):
        return []
    domain = str(domain or "")
    engine = PAID_DOMAIN_HEDGES.get(domain)
    if not engine and domain == "general_search" and str(lang or "") == "en":
        engine = "deepseek_search"
    if not engine:
        return []
    try:
        if _paid_hedge_ready(engine):
            return [engine]
        # 付费位不可用：TinyFish 是免费且带发布日期的回落位。回落位不是
        # 白名单付费源，仍须在 enabled 里（不在说明本机没注册/被禁用）。
        if (_healthy_and_enabled(_FREE_FALLBACK, enabled)
                and _key_ready(_FREE_FALLBACK) and _budget_ok(_FREE_FALLBACK)):
            return [_FREE_FALLBACK]
    except Exception:
        return []
    return []


def insert_hedge(combo: list[str], domain: str, mode: str = "auto",
                 enabled: set[str] | None = None,
                 lang: str = "") -> list[str]:
    """把付费/回落引擎插到该域声明的位置（原地改并返回）。

    默认第二位；english_tech 第三位（免费源先跑，不够才付费）。位置不参与
    排序，只是 combo 的插入下标，后续 wave 调度按位置分波。
    """
    position = _hedge_position(domain)
    for engine in reversed(hedge_for(domain, mode, enabled=enabled, lang=lang)):
        if engine not in combo:
            combo.insert(min(max(0, position), len(combo)), engine)
    return combo
