#!/usr/bin/env python3
"""rerank_tfidf.py — 零依赖 TF-IDF 语义重排（方案 A）。

问题：Bocha Reranker 无 API Key 时，top-20 候选缺语义重排，SERP 壳链
可能靠 RRF 高分重回顶部。本模块用纯 Python TF-IDF 余弦相似度对 top-k
候选做轻量重排，零外部依赖，单次调用 <5ms。

设计约束：
  - 零外部依赖，只用 stdlib（re, math, collections）+ rank_signals 的
    既有判据（标题堆砌惩罚经它收敛，不另造第二套实现）
  - 纯函数，无全局可变状态
  - 中文用字符二元组（CJK bigram），英文用词（word）
  - 融合公式：final = 0.3 * tfidf + 0.4 * credibility_fast + 0.3 * rrf，
    再乘标题堆砌惩罚（rank_signals.title_stuffing_penalty）
  - 开关（ARGO_TFIDF_RERANK）在调用方 search_pipeline，本模块不读环境变量

2026-10-16 修复记录（方案二梳理）：
  - 删除本地 _title_stuffing_penalty 的「分隔符模式」：原实现凡标题含
    `|`/`_`/`——` 即 ×0.6，实测把官方文档「asyncio --- 异步 I/O — Python
    3.14.7 文档」这类合法标题压 40%（tfidf 第二高、排序垫底）。该类误杀
    是 separator 存在性与堆砌无关，故整段删除，堆砌判据统一走
    rank_signals 的查询单元重复计数（下限 0.35）；
  - rerank 与 rerank_offline 的打分循环原本两份拷贝（漂移风险），提取
    _score_candidates 单一实现；
  - 删除未被调用的 get_env/_env_flag 死代码（门控在 search_pipeline）。

用法：
  from rerank_tfidf import rerank
  ranked = rerank(query, candidates, top_k=10)
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from rank_signals import relevance_units, title_stuffing_penalty

# 中文停用字（与 rank_signals.CJK_STOPCHARS 保持一致）
_STOPCHARS = frozenset(
    "的了是和与或在有为被把对从到就都也还很更最之其此这那一个"
    "个们我你他她它上下中里外前后时和及等所可能够会要"
    "怎幺么样如选哪个多少何呢吗吧啊哦呀嘛"
)

# 中文单字正则
_CJK_CHAR_RE = re.compile(r"[一-鿿]")
# 英文/数字词正则
_WORD_RE = re.compile(r"[a-zA-Z0-9]+")


def _tokenize(text: str) -> list[str]:
    """分词：中文取字符二元组（CJK bigram），英文取小写词。

    例：「贵州茅台股价」→ ['贵州', '茅台, '台股', '股价']
        "Python asyncio" → ['python', 'asyncio']
    """
    if not text:
        return []
    text = text.lower()
    tokens: list[str] = []
    # 中文 bigram
    cjk_chars = _CJK_CHAR_RE.findall(text)
    for i in range(len(cjk_chars) - 1):
        bg = cjk_chars[i] + cjk_chars[i + 1]
        # 过滤含停用字的 bigram
        if bg[0] not in _STOPCHARS and bg[1] not in _STOPCHARS:
            tokens.append(bg)
    # 英文/数字词
    for w in _WORD_RE.findall(text):
        if len(w) > 1:  # 过滤单字符
            tokens.append(w)
    return tokens


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    """计算 TF-IDF 向量（词 → 权重）。"""
    if not tokens:
        return {}
    tf = Counter(tokens)
    total = len(tokens)
    return {term: (count / total) * idf.get(term, 0.0) for term, count in tf.items()}


def _cosine_sim(a: dict[str, float], b: dict[str, float]) -> float:
    """两个稀疏 TF-IDF 向量的余弦相似度。"""
    if not a or not b:
        return 0.0
    # 遍历较短的向量
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _compute_idf(docs: list[list[str]]) -> dict[str, float]:
    """计算 IDF（逆文档频率）。"""
    n = len(docs)
    if n == 0:
        return {}
    df: Counter = Counter()
    for doc in docs:
        for term in set(doc):
            df[term] += 1
    return {term: math.log((n + 1) / (freq + 1)) + 1.0 for term, freq in df.items()}


def _score_candidates(
    query: str, candidates: list[dict[str, Any]], k: int
) -> list[dict[str, Any]]:
    """打分核心：给前 k 条写 _tfidf_score/_rerank_score 并按融合分重排（原地）。

    rerank 与 rerank_offline 共用本函数——此前两份拷贝各有一遍融合公式与
    堆砌惩罚，任一侧改动都会静默漂移。
    """
    # 构建文档集：查询 + top_k 候选
    query_tokens = _tokenize(query)
    doc_tokens_list = []
    for c in candidates[:k]:
        text = f"{c.get('title', '')} {c.get('snippet', '')}"
        doc_tokens_list.append(_tokenize(text))

    # 计算 IDF
    all_docs = [query_tokens] + doc_tokens_list
    idf = _compute_idf(all_docs)

    # 查询向量
    q_vec = _tfidf_vector(query_tokens, idf)

    # 计算每个候选的 TF-IDF 相似度
    tfidf_scores = []
    for tokens in doc_tokens_list:
        d_vec = _tfidf_vector(tokens, idf)
        sim = _cosine_sim(q_vec, d_vec)
        tfidf_scores.append(sim)

    # 归一化 RRF 分数到 0-1
    rrf_raw = [c.get("_rrf_score", 0.0) for c in candidates[:k]]
    rrf_max = max(rrf_raw) if rrf_raw else 1.0
    rrf_norm = [s / rrf_max if rrf_max > 0 else 0.0 for s in rrf_raw]

    # 堆砌判据走 rank_signals 唯一实现（查询单元重复计数，见该函数 docstring
    # 的降级说明：只按标题算、是主密度判据的补充）。查询单元取 set——惩罚
    # 内部按「标题命中单元数 / 查询单元数」超额计数。
    query_units = set(relevance_units(query or ""))

    for i, c in enumerate(candidates[:k]):
        tfidf_s = tfidf_scores[i]
        cred = c.get("credibility_fast", 0.0) or 0.0
        rrf_s = rrf_norm[i]
        base_score = 0.3 * tfidf_s + 0.4 * cred + 0.3 * rrf_s
        penalty = title_stuffing_penalty(c.get("title", "") or "", query_units)
        final = base_score * penalty
        c["_tfidf_score"] = round(tfidf_s, 6)
        c["_rerank_score"] = round(final, 6)

    # 按融合分数排序
    candidates[:k] = sorted(candidates[:k], key=lambda x: x.get("_rerank_score", 0.0), reverse=True)
    return candidates


def rerank(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int = 10,
    mode: str = "auto",
) -> list[dict[str, Any]]:
    """对 top-k 候选做 TF-IDF 语义重排。

    融合公式：
      final = 0.3 * tfidf_score + 0.4 * credibility_fast + 0.3 * rrf_score，
      再乘 rank_signals.title_stuffing_penalty 的堆砌惩罚

    其中：
      - tfidf_score: 查询与候选（title+snippet）的 TF-IDF 余弦相似度
      - credibility_fast: 候选的 credibility_fast 字段（0-1）
      - rrf_score: 候选的 _rrf_score 字段（0-1，归一化后）

    Args:
        query: 原始查询字符串
        candidates: 候选结果列表（每条需有 title/snippet 字段）
        top_k: 只重排前 top_k 条
        mode: 搜索模式（fast/auto/deep/budget）

    Returns:
        重排后的候选列表（原地修改 + 返回）
    """
    if not candidates or not query:
        return candidates

    # fast/budget 模式跳过重排（零延迟）
    if mode in ("fast", "budget"):
        return candidates

    # 只重排 top_k
    k = min(top_k, len(candidates))
    if k <= 1:
        return candidates

    return _score_candidates(query, candidates, k)


def rerank_offline(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """离线评估入口（供 matrix_search_eval.py 调用）。

    与 rerank 相同逻辑，但不读环境变量，纯函数。打分核心与 rerank 共用
    _score_candidates（2026-10-16 去重前这里是第二份拷贝）。
    """
    if not candidates or not query:
        return candidates

    k = min(top_k, len(candidates))
    if k <= 1:
        return candidates

    return _score_candidates(query, candidates, k)
