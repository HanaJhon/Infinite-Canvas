#!/usr/bin/env python3
"""
cache_similarity.py — 缓存侧的查询归一化与近重复判定（2026-10-16 从 cache.py 拆出）

拆出原因：拆分前 cache.py 1382 行（祖父上限），是全仓仅次于源声明构建器的
大文件，module size 门禁的既定结论是「按键 / 存储 / 命中策略三段拆，并把
上限调低」。本模块承载三段里的「命中策略」判据层——**纯函数、零 IO、零
sqlite 依赖**：

  - normalize_query        缓存键归一化（空白/全半角/大小写）
  - query_similarity       字符 n-gram minhash 近似 Jaccard（软命中的判据）
  - split_qualifiers       限定符（site: / keywords:）与载荷拆分
  - is_freshness_sensitive_query  时效敏感查询检测（TTL 帽的输入）

为什么整段搬而不是只搬一半：这四件事共用同一套「查询字符串 → 可比签名」
的变换，`find_similar` 的每一次软命中判定都要依序走完它们；留一半在
cache.py 只会让「判据在哪」重新变成两处。搬走后 cache.py 只保留存储实现
（L1/L2）与 SearchCache 门面。

兼容约定（拆模块的两条老规矩，与 cache_guard / cache_key_vdom 一致）：
  - cache.py 显式 re-export 本模块全部公开名，`from cache import
    query_similarity` 等既有 import 点零改动；
  - 测试 monkeypatch 的面仍在 cache.py（`cache.is_freshness_sensitive_query`），
    调用方经模块全局名查找，patch 照常生效。
"""

from __future__ import annotations

import functools
import re

__all__ = [
    "normalize_query",
    "query_similarity",
    "split_qualifiers",
    "is_freshness_sensitive_query",
    "FRESHNESS_QUERY_RE",
]


@functools.lru_cache(maxsize=4096)
def normalize_query(query: str) -> str:
    """缓存键用查询归一化：折叠空白、全半角空格、两端 trim、小写英文字母。

    不改变语义实体大小写敏感场景时仍用 lower；中文不受影响。
    目标：同一问句不同空白/大小写命中同一 key。
    """
    if not query:
        return ""
    # 全角空格 → 半角；连续空白折叠
    q = query.replace("\u3000", " ").strip()
    q = re.sub(r"\s+", " ", q)
    return q.casefold()


# ── 近重复查询检测（minhash 字符 n-gram）────────────────────────────────────

_NGRAM_N = 3
# 置换数。**看起来偏低，但不要单独调它**——它与下游软命中阈值 0.7 是一套
# 标定，动一个必须同时重标另一个，否则会把「检索上一年的缓存」放进来。
#
# 2026-09-19 实测记录（起因是「提到 32 更准」，结论是**保持 8 不改**）：
# K=8 的估计确实有偏且方差大——四条中文对的真实 Jaccard 是
# 0.275/0.444/0.500/0.375，K=8 估成 0.250/0.750/0.375/0.375（最大误差 0.306，
# 双向发散）；换 32 后为 0.281/0.438/0.562/0.375，明显贴住真值。
# 成本也不是障碍：`_signature` 带 lru_cache，比对是逐位比较（实测 0.41us/次，
# 不随 K 变），提高 K 只增加一次性签名成本（K=8:0.171ms、K=32:0.832ms 每条
# 查询，相对 1000–3000ms 的单次搜索可忽略）。
#
# 拦路石在**阈值**：0.7 正是照着 K=8 的偏高估计定的（下方 find_similar 的
# docstring 写「单字差异约 0.75」，而真值只有 0.444）。把 K 提到 32 后，要维持
# 原有软命中范围就得把阈值降到 ~0.35，而实测该阈值下
#     苹果 2025 营收 ↔ 苹果 2024 营收 = 0.469 ≥ 0.35 → 命中
# 即「今年的查询会命中去年的缓存」。这比「估计偏一点」严重得多——软命中的
# 前提是结果集可互换，年份不同则不可互换。两侧一起保持原状。
#
# 要走这条路，正确顺序是先换能区分数字/年份的判据（词级或数字感知 shingle），
# 再重标阈值；单独提 K 只是把偏差从「估计层」搬到「阈值层」。
_MINHASH_PERM = 8  # 置换数（越多越准，越少越快；8 对查询级足够）


def _ngrams(s: str, n: int = _NGRAM_N) -> set[str]:
    """字符级 n-gram（中文按字，英文按字符，无需分词）。"""
    s = re.sub(r"\s+", "", s)
    return {s[i:i + n] for i in range(max(len(s) - n + 1, 1))}


def _hash_token(t: str, seed: int) -> int:
    """带种子的简单哈希（minhash 置换模拟）。"""
    h = seed * 1315423911
    for c in t:
        h = (h ^ ord(c)) * 1099511628211 & 0xFFFFFFFFFFFFFFFF
    return h


@functools.lru_cache(maxsize=8192)
def _signature(s: str) -> tuple[int, ...]:
    """查询的 minhash 签名：每个置换下全部 n-gram 的最小哈希。

    这是「查询 → 签名」的纯函数，按查询串记忆化。提出来的意义在于：
    `query_similarity(q1, q2)` 会被拿去和缓存里**多条**候选比对，旧写法每次
    都重算两边的签名——一次搜索实测 28,552 次 `_hash_token` 调用，绝大多数
    是同一批 token 的重复置换。签名化后每条查询的签名全进程只算一次，
    且比对本身从 O(K × |tokens|) 降到 O(K)（K=置换数=8）。
    长驻进程（MCP server）里同一查询反复比对时收益为常数级。
    """
    grams = _ngrams(s)
    if not grams:
        return ()
    return tuple(min(_hash_token(t, seed) for t in grams)
                 for seed in range(_MINHASH_PERM))


def query_similarity(q1: str, q2: str) -> float:
    """两查询的字符 n-gram minhash 近似 Jaccard 相似度（0-1）。

    中文「苹果 2025 营收」vs「苹果 2025 年营收」这类近重复查询
    会得到高相似度（>0.7），用于语义缓存软命中。

    实现 = 两个签名逐位置相等的比例（minhash 估计 Jaccard 的标准做法）。
    """
    a = _signature(q1)
    b = _signature(q2)
    if not a or not b:
        return 0.0
    hits = sum(1 for x, y in zip(a, b) if x == y)
    return hits / _MINHASH_PERM


# 结构化限定符（keywords:pi-package / site:zhihu.com / author:bcoe）。
# 值里不含 `/` 是刻意的：URL 的 `https:` 因此不被当成限定符——fetch/evidence
# 的 URL 近重复软命中（`.../x` 与 `.../x.md`，相似度 0.875）是既有的正确
# 行为，不能被这次修复误伤。键以字母开头则排除 `10:30` 这类时间写法。
_QUALIFIER_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_.-]*:[A-Za-z0-9_*.+-]+")


def split_qualifiers(query: str) -> tuple[frozenset[str], str]:
    """把查询拆成（限定符集合，载荷）。

    限定符是**过滤器**而不是内容：两条查询的限定符集合不同，结果全集就不同，
    再高的词面相似度也不构成可互换的理由。

    为什么要拆：字符 n-gram 相似度会被长公共前缀主导。实测
    `keywords:pi-package mcp` 与 `keywords:pi-package memory` 整串相似度
    0.875（远超 0.7 阈值），而判别词只占几个字符——两条不同的检索需求被判成
    近重复，软命中把 memory 的结果当成 mcp 的结果交了出去（2026-09-18 修复）。
    拆开后比的是载荷（`mcp` vs `memory`，相似度 0.000），判据恢复有效。
    """
    text = query or ""
    quals = frozenset(q.lower() for q in _QUALIFIER_RE.findall(text))
    payload = re.sub(r"\s+", " ", _QUALIFIER_RE.sub(" ", text)).strip()
    return quals, payload


# 时效敏感查询正则：延迟编译（import 期编译正则对冷启动是纯税，见函数内判断）。
FRESHNESS_QUERY_RE = None


def is_freshness_sensitive_query(query: str) -> bool:
    """检测查询是否时效敏感（今日/实时/盘中/快讯等）。"""
    global FRESHNESS_QUERY_RE
    if FRESHNESS_QUERY_RE is None:
        FRESHNESS_QUERY_RE = re.compile(
            r"(今日|今天|昨晚|昨夜|本周|本月|实时|即时|最新|刚刚|"
            r"盘中|盘前|盘后|快讯|直播|热点新闻|头条|"
            r"today|tonight|breaking|live\s*update|just\s*now|"
            r"right\s*now|this\s*(morning|week|month))",
            re.I,
        )
    return bool(FRESHNESS_QUERY_RE.search(query or ""))
