#!/usr/bin/env python3
"""digup_bridge.py — DigUp 本地语义搜索的 CLI 桥（声明式引擎用，无网络）。

DigUp（github.com/ARahim3/DigUp）在设备端用 EmbeddingGemma 2 给本地文件建
多模态向量索引（照片/截图/PDF/文档/音频/视频，命中精确到页/秒/行）。它的
`search --json` 输出的是 path/kind/score/excerpt 行，不是 argo 契约的
title/url——本桥做一次纯本地映射，让 engines/specs/digup.yaml 走通用 cli
builder，不新增 Python 特例分支（与 train/realtime_index 同形态）。

用法（spec 调用形如）：
  python3 scripts/digup_bridge.py "<query>" -n 5

digup 二进制定位（先到先得）：
  --bin 参数 > $DIGUP_BIN > PATH 里的 digup
  > /Applications/DigUp.app/Contents/Helpers/digup（brew cask / DMG 装的 App）

索引定位：--index 参数 > $DIGUP_INDEX > digup 默认
（~/Library/Application Support/DigUp/index.noindex）。

输出：单个 JSON {"results": [...]}（argo cli builder 的自动 JSON 路径）。
任何失败都输出空 results 并 exit 0——引擎层语义：本源此刻无结果，而不是
整次检索报错。诊断信息走 stderr。
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

# digup 自身首查要加载 ~250MB text-only 模型（冷启实测 0.4–0.8s），再留检索
# 与进程开销。引擎层 spec timeout=30 兜底，这里取小于它的值，保证被卡时
# 桥先返回结构化空结果而不是被引擎层整体杀掉。
_DIGUP_TIMEOUT_S = 25

_APP_HELPERS = (
    "/Applications/DigUp.app/Contents/Helpers/digup",
    os.path.expanduser("~/Applications/DigUp.app/Contents/Helpers/digup"),
)

_KIND_ZH = {
    "screenshot": "截图",
    "image": "图片",
    "pdf": "PDF",
    "doc": "文档",
    "audio": "音频",
    "video": "视频",
    "code": "代码",
}


def resolve_bin(explicit: str | None = None) -> str:
    """定位 digup 可执行文件（显式 > $DIGUP_BIN > PATH > App Helpers）；找不到返回空串。"""
    candidates = []
    if explicit:
        candidates.append(explicit)
    env_bin = os.environ.get("DIGUP_BIN", "").strip()
    if env_bin:
        candidates.append(env_bin)
    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    found = shutil.which("digup")
    if found:
        return found
    for path in _APP_HELPERS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return ""


def _clock(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def _loc_hint(row: dict) -> str:
    """digup 的命中位置（页/秒/段/行）转中文后缀；无定位返回空。"""
    segment = row.get("segment") or ""
    loc = row.get("loc")
    if loc is None:
        return " · 图内文字" if segment == "ocr" else ""
    if segment in ("page", "pageImage"):
        return f" · 第{int(loc)}页"
    if segment == "audio":
        return f" · {_clock(loc)}（声音）"
    if segment == "frame":
        return f" · {_clock(loc)}"
    if segment == "chunk":
        return f" · 第{int(loc)}段"
    if segment == "lines":
        end = row.get("loc_end")
        return f" · 第{int(loc)}–{int(end)}行" if end else f" · 第{int(loc)}行"
    if segment == "cells":
        end = row.get("loc_end")
        return f" · 单元格{int(loc)}–{int(end)}" if end else f" · 单元格{int(loc)}"
    return ""


def _url(row: dict) -> str:
    """file:// 链接；PDF 带 #page=N、音视频带 #t=start,end（Preview/QuickTime
    认这两个 fragment，也让同文件不同页/时刻的命中不被 argo 按 url 去重合并）。"""
    path = row.get("path") or ""
    if not path:
        return ""
    url = "file://" + path
    segment = row.get("segment") or ""
    loc = row.get("loc")
    if loc is None:
        return url
    if segment in ("page", "pageImage"):
        return f"{url}#page={int(loc)}"
    if segment in ("audio", "frame"):
        end = row.get("loc_end")
        return f"{url}#t={int(loc)},{int(end if end is not None else loc)}"
    return url


def _snippet(row: dict) -> str:
    """excerpt 优先（剥掉 digup 的高亮记号 «»）；无 excerpt（图像/纯名命中）
    给「类型 · 位置描述」或所在目录，保证 snippet 永远不为空。"""
    excerpt = str(row.get("excerpt") or "").replace("«", "").replace("»", "")
    excerpt = " ".join(excerpt.split())
    if excerpt:
        return excerpt[:300]
    kind = _KIND_ZH.get(row.get("kind") or "", "文件")
    hint = _loc_hint(row)
    if hint:
        return f"{kind}{hint.lstrip(' ·')} · 内容语义匹配"
    folder = os.path.dirname(row.get("path") or "")
    home = os.path.expanduser("~")
    if folder.startswith(home):
        folder = "~" + folder[len(home):]
    return f"{kind} · 关键词命中 · {folder or '本地文件'}"[:300]


def map_row(row: dict, rank: int) -> dict:
    """digup 结果行 → argo 结果契约（title/url/snippet/source 必需）。"""
    path = row.get("path") or ""
    title = (os.path.basename(path) if path else "") + _loc_hint(row)
    result = {
        "title": title[:200],
        "url": _url(row),
        "snippet": _snippet(row),
        "source": "digup",
        # 与其他 cli builder 一致的展示分（rrf_merge 按名次融合，score 只作展示）
        "score": round(max(1.0 - 0.1 * rank, 0.1), 4),
    }
    # digup --json 不带 modified（SearchHit 序列化面没有它），桥自己 stat：
    # 文件被移动/删除时拿不到就算了，不硬造日期。
    if path:
        try:
            mtime = os.stat(path).st_mtime
            result["published_at"] = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
        except OSError:
            pass
    return result


def search(query: str, n: int, bin_path: str, index_dir: str | None) -> list[dict]:
    cmd = [bin_path, "search", query, "--json", "-n", str(n)]
    if index_dir:
        cmd += ["--index", index_dir]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=_DIGUP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        print(f"digup_bridge: digup 超时(>{_DIGUP_TIMEOUT_S}s)", file=sys.stderr)
        return []
    except OSError as e:
        print(f"digup_bridge: 无法执行 digup: {e}", file=sys.stderr)
        return []
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-200:]
        print(f"digup_bridge: digup rc={proc.returncode}: {tail}", file=sys.stderr)
        return []
    try:
        rows = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        print("digup_bridge: digup 输出不是 JSON", file=sys.stderr)
        return []
    if not isinstance(rows, list):
        print("digup_bridge: digup 输出不是结果数组", file=sys.stderr)
        return []
    return [map_row(r, i) for i, r in enumerate(rows) if isinstance(r, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DigUp → argo 结果契约（本地映射，无网络）")
    parser.add_argument("query", help="搜索词（自然语言描述文件内容）")
    parser.add_argument("-n", type=int, default=5, help="返回条数")
    parser.add_argument("--bin", default=None, help="digup 可执行文件路径（默认自动定位）")
    parser.add_argument("--index", default=None, help="索引目录（默认 digup 自身默认值）")
    args = parser.parse_args(argv)

    bin_path = resolve_bin(args.bin)
    if not bin_path:
        print("digup_bridge: 找不到 digup 可执行文件（装 App、放进 PATH，"
              "或设 DIGUP_BIN / --bin），返回空结果", file=sys.stderr)
        print(json.dumps({"results": []}))
        return 0
    index_dir = args.index or os.environ.get("DIGUP_INDEX", "").strip() or None
    print(json.dumps({"results": search(args.query, max(1, args.n), bin_path, index_dir)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
