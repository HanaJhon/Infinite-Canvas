#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""密钥扫描器 —— 防止 API key 再次被提交进 git。

用法：
  python tools/scan_secrets.py                # 扫「暂存区」（pre-commit 钩子用）
  python tools/scan_secrets.py --tree         # 扫工作区里所有被 git 跟踪的文件
  python tools/scan_secrets.py --history      # 扫全部提交历史（含标签，慢）
  python tools/scan_secrets.py --path API     # 扫指定文件/目录（无论是否跟踪）

退出码：0 = 干净；1 = 发现疑似密钥。

规则说明（2026-09-20 定）：
  ⚠️ **不要只按 `sk-` 前缀找密钥**。本项目踩过的坑就是「正则太窄」——一枚 11 位纯数字的
  Grsai key 因此被漏掉，得出了「历史里没有真密钥」的错误结论。
  这里同时覆盖四类：`.env` 的 `NAME=VALUE`、JSON 的 `"api_key": "..."`、
  内联的 `sk-`/`ms-`/`AKIA` 等已知前缀、以及 `Bearer <token>`。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- 扫描规则
SENSITIVE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)", re.I)

ENV_LINE = re.compile(r"^[ \t]*([A-Za-z_][A-Za-z0-9_]{2,})\s*[:=]\s*(.+?)[ \t]*$", re.M)
JSON_FIELD = re.compile(
    r'"(api_?key|apikey|api_?secret|token|access_?token|secret|password|bearer)"'
    r'\s*:\s*"?([^",\s}]{6,})"?', re.I)
# ⚠️ 已知前缀必须给足长度下限，否则会把 CSS 类名（ms-row / ms-input）和
#    JS 变量名当成密钥 —— 实测放宽到 10 字符时，仅 static/ 目录就产生 60+ 误报。
INLINE = re.compile(
    r"\b(sk-[A-Za-z0-9_\-]{20,}|sk-ant-[A-Za-z0-9_\-]{20,}|ms-[A-Za-z0-9_\-]{25,}"
    r"|xox[baprs]-[A-Za-z0-9_\-]{10,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}"
    r"|AIza[0-9A-Za-z_\-]{33})\b")
BEARER = re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]{20,})")

# 占位符/示例值，命中即放过
PLACEHOLDER = re.compile(
    r"xxx|your|mock|example|placeholder|todo|changeme|dummy|sample|fake|redact"
    r"|\*{2,}|^<.*>$|^\{\{.*\}\}$|^\$\{.*\}$|^none$|^null$|^true$|^false$"
    r"|^[a-z_]*key$|^[a-z_]*token$|^[a-z_]*secret$", re.I)
MODEL_HINT = re.compile(r"^[\w\.\-/]+(,[\w\.\-/]+)+$")
URL_HINT = re.compile(r"^https?://", re.I)

# 这些路径不扫（二进制/依赖/缓存）
SKIP_PATH = re.compile(
    r"(^|/)(\.git|\.workbuddy-ai|\.claude|__pycache__|node_modules|"
    r"bin|obj|python|packages)(/|$)", re.I)
SKIP_EXT = re.compile(r"\.(png|jpe?g|gif|webp|ico|svgz|zip|7z|rar|exe|dll|pdb|so|dylib|"
                      r"woff2?|ttf|otf|mp4|mp3|wav|pdf|pyc|pack|bin)$", re.I)

# 允许清单：本文件自身、示例配置、文档里的写法
ALLOW_FILE = re.compile(
    r"(scan_secrets\.py|\.env\.example|\.env\.sample|README|SECURITY\.md|"
    r"\.secretsignore)$", re.I)


def mask(v: str) -> str:
    v = str(v)
    if len(v) <= 6:
        return "*" * len(v) + f"(len={len(v)})"
    return f"{v[:3]}…{v[-3:]}(len={len(v)})"


def _setup_io() -> None:
    """把 stdout/stderr 调成「绝不抛异常」。

    🚨 踩过的坑（2026-09-20）：脚本原来用 `✔` / `✖`（U+2714 / U+2716）做状态标记，
    在 **GBK 控制台（Windows 代码页 936）** 下直接抛
        UnicodeEncodeError: 'gbk' codec can't encode character '\u2714'
    —— 而 pre-commit 钩子正是由 git 客户端以 GBK 环境拉起的，
    结果钩子崩溃、**所有提交都被拦下**。所以：① 状态标记一律用 ASCII；
    ② 这里再兜一层 errors='replace'，任何字符编不出来也只是变成 '?'，不会崩。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


PREFIX = re.compile(r"^(sk-|ms-|gh[pousr]_|xox[baprs]-|AKIA|AIza)", re.I)


def looks_real(name: str, value: str) -> bool:
    """判断是「疑似真密钥」还是占位符/普通字符串。

    ⚠️ 长度下限是刻意收紧的：本项目的 Grsai key 是 **11 位纯数字**，所以纯数字要
       放到 ≥10 才收得住；而 `ms-`/`sk-` 这类前缀必须给足长度，否则 CSS 类名
       （`ms-row`、`ms-input`）会全部误报。宁可漏报几个弱的，也不要误报一片。
    """
    v = value.strip().strip('"').strip("'")
    if not v or PLACEHOLDER.search(v):
        return False
    if MODEL_HINT.match(v) or URL_HINT.match(v) or re.search(r"\s", v):
        return False
    if v.lower() == name.lower():
        return False
    if not re.fullmatch(r"[A-Za-z0-9_\-\.:/+]{8,}", v):
        return False
    if v.isdigit():                       # 纯数字（Grsai 这类）
        return len(v) >= 10
    if PREFIX.match(v):                   # 已知前缀（sk- / ms- / AKIA …）
        return len(v) >= 20
    if len(v) >= 32 and any(c.isdigit() for c in v):
        return True                       # 长 hex / base64 类
    if len(v) < 16:
        return False
    return any(c.isdigit() for c in v) and (
        any(c.isupper() for c in v) or any(c in "_-./:+" for c in v))


def load_ignore() -> list[str]:
    """读 .secretsignore（每行一个 glob 片段，子串匹配即可）。"""
    p = os.path.join(ROOT, ".secretsignore")
    if not os.path.isfile(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(s)
    return out


def scan_text(path: str, text: str) -> list[tuple[str, str]]:
    """返回 [(变量名, 脱敏值), ...]（同一值被多条规则命中时只留一条）"""
    hits: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(name: str, val: str) -> None:
        if not looks_real(name, val):
            return
        m = mask(val)
        if m in seen:
            return
        seen.add(m)
        hits.append((name, m))

    for m in ENV_LINE.finditer(text):
        if SENSITIVE.search(m.group(1)):
            add(m.group(1), m.group(2))
    for m in JSON_FIELD.finditer(text):
        add(m.group(1), m.group(2))
    for m in INLINE.finditer(text):
        add("(inline)", m.group(1))
    for m in BEARER.finditer(text):
        add("(bearer)", m.group(1))
    return hits


def skip(path: str, ignore: list[str]) -> bool:
    norm = path.replace("\\", "/")
    if SKIP_PATH.search(norm) or SKIP_EXT.search(norm) or ALLOW_FILE.search(norm):
        return True
    return any(pat in norm for pat in ignore)


def git(*args: str) -> str:
    return subprocess.run(["git"] + list(args), cwd=ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL).stdout.decode("utf-8", "replace")


def iter_staged():
    for line in git("diff", "--cached", "--name-only", "--diff-filter=ACM").splitlines():
        if line.strip():
            yield line.strip(), None


def iter_tree():
    for line in git("ls-files").splitlines():
        if line.strip():
            yield line.strip(), None


def iter_paths(targets: list[str]):
    for t in targets:
        p = os.path.join(ROOT, t)
        if os.path.isfile(p):
            yield t, p
        elif os.path.isdir(p):
            for base, _dirs, files in os.walk(p):
                for fn in files:
                    full = os.path.join(base, fn)
                    yield os.path.relpath(full, ROOT).replace("\\", "/"), full


def iter_history():
    """扫全部提交历史里的 blob（含标签）。"""
    lines = git("rev-list", "--all", "--objects").splitlines()
    shas = [l.split(" ", 1) for l in lines if re.fullmatch(r"[0-9a-f]{40}", l.split(" ")[0])]
    blobs = [(s[0], s[1] if len(s) > 1 else "") for s in shas]
    proc = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT,
                          input="\n".join(b[0] for b in blobs).encode(),
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    data, pos, i = proc.stdout, 0, 0
    while pos < len(data) and i < len(blobs):
        nl = data.find(b"\n", pos)
        if nl < 0:
            break
        header = data[pos:nl].decode("utf-8", "replace")
        pos = nl + 1
        parts = header.split()
        if len(parts) != 3:
            break
        size = int(parts[2])
        raw = data[pos:pos + size]
        pos += size + 1
        sha, path = parts[0], blobs[i][1]
        i += 1
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        yield f"{path} @ {sha[:12]}", text


def main() -> int:
    ap = argparse.ArgumentParser(description="扫描疑似 API 密钥")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true", help="只扫暂存区（默认）")
    g.add_argument("--tree", action="store_true", help="扫工作区被跟踪文件")
    g.add_argument("--history", action="store_true", help="扫全部提交历史（含标签，慢）")
    g.add_argument("--path", nargs="+", metavar="P", help="扫指定文件/目录")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="脚本自身出错时也返回非 0（默认出错放行，避免把提交彻底堵死）")
    args = ap.parse_args()

    _setup_io()
    ignore = load_ignore()
    if args.history:
        src = iter_history()
        label = "提交历史"
    elif args.tree:
        src = ((p, None) for p, _ in iter_tree())
        label = "工作区被跟踪文件"
    elif args.path:
        src = iter_paths(args.path)
        label = "指定路径"
    else:
        src = iter_staged()
        label = "暂存区"

    total = 0
    for path, full in src:
        if skip(path, ignore):
            continue
        if full is None:
            full = os.path.join(ROOT, path)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, "rb") as f:
                text = f.read().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for name, masked in scan_text(path, text):
            total += 1
            print(f"  [疑似密钥] {path}\n              {name} = {masked}")

    if total:
        print(f"\n[FAIL] 在{label}发现 {total} 处疑似密钥。")
        print("  如果确认是误报，把路径写进 .secretsignore；否则请移除后再提交。")
        print("  临时绕过（确认误报时）：git commit --no-verify")
        return 1
    if not args.quiet:
        print(f"[OK] {label}未发现疑似密钥。")
    return 0


def _run() -> int:
    """包一层兜底：脚本自身出错时不要把用户的提交彻底堵死。"""
    try:
        return main()
    except SystemExit:
        raise
    except Exception as exc:      # noqa: BLE001
        _setup_io()
        print(f"[WARN] 密钥扫描器自身出错，本次跳过检查：{type(exc).__name__}: {exc}")
        print("       这不是密钥告警。如需严格模式请加 --strict。")
        return 1 if "--strict" in sys.argv else 0


if __name__ == "__main__":
    sys.exit(_run())
