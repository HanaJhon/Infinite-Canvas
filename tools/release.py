#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""发布打包脚本：产出「干净包」（不含任何用户数据）。

为什么需要它
------------
历史上发布包是把工作目录整包压缩的，结果把作者私有数据一起发了出去：

    798.14 MB 的 Official.v1.1.zip 里含
      · .git/                    528.3 MB（完整 git 历史，含已公开的密钥 blob）
      · assets/output/online_*   135.6 MB（作者生成的个人图片）
      · data/canvases/*.json     8 个画布
      · history.json             使用历史
      · assets/input/*           参考图

本脚本用「白名单复制 + 黑名单断言」彻底避免这类事故：只复制认识的程序文件，
复制完再扫一遍，一旦命中任何用户数据路径就直接报错退出。

用法
----
    python tools/release.py list                 # 只列出会进包的文件，不写盘
    python tools/release.py verify <zip 或目录>  # 校验已有包/目录是否含用户数据
    python tools/release.py build                # 生成干净包 + update.json
    python tools/release.py build --build-exe    # 先重编启动器 exe 再打包
    python tools/release.py build --notes-file RELEASE_NOTES.md

产物（默认写到 output/release/<版本>/）
--------------------------------------
    Infinite-Canvas-Full-<版本>.zip      完整程序包（首次安装 / 跨版本）
    Infinite-Canvas-Update-<版本>.zip    增量包（只含与上一版本相比有变化的文件）
    update.json                          更新清单（放到 GitHub Release 资产里）
    file-hashes.json                     本次的文件指纹，作为下次增量包的基线
    release-summary.txt                  人类可读的汇总 + gh release 命令

注意
----
* 默认**不会**重编 exe。单文件 publish 不是字节可复现的，每次重编都会改动被 git
  跟踪的 `Lochou启动器.exe`。需要重编时显式加 `--build-exe`，重编后记得提交。
* 本脚本不联网、不调用 git，只读本地文件。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE_ROOT = os.path.join(ROOT, "output", "release")

# 包内顶层目录名，与历史发布包保持一致（用户解压得到一个文件夹）
PACKAGE_TOP = "Infinite-Canvas"

# ---------------------------------------------------------------------------
# 程序文件清单（白名单）
# ---------------------------------------------------------------------------

# 根目录下的程序文件
ROOT_FILES = [
    "Lochou启动器.exe",
    "main.py",
    "VERSION",
    "requirements.txt",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "build-launcher.ps1",
    "get-pip.py",
    "run.bat",
    "安装依赖.bat",
    "安装即梦CLI.bat",
    "登录即梦CLI.bat",
    "安装即梦CLI.command",
    "登录即梦CLI.command",
    "mac-安装依赖.sh",
    "mac-启动服务.sh",
    "mac-启动服务.command",
    "mac-修复权限.command",
    "Windows用户双击Lochou启动器启动.md",
    "MAC-使用说明.md",
    "赞赏.png",
]

# 整个目录纳入包（递归）
PROGRAM_DIRS = [
    "static",
    "dist",
    "launcher",
    "tools",
    "workflows",
    "tests",
    "CLI",
    "packages",
    "python",
]

# data/ 是「混装目录」：里面既有用户数据（api_providers.json 含 API 密钥、
# canvases/ 画布、chat_*.json 会话、update_backups/ 恢复点……），也有少数
# 随程序分发的只读内置数据。所以不能整目录复制，只能逐个登记。
#
# ⚠️ 登记前必须确认两件事：
#   1) 该文件不含任何用户内容（密钥 / 画布 / 会话 / 本机路径）
#   2) 覆盖安装时覆盖它不会损坏用户状态
#
# 📌 因此 data/asset_library.json **不在**清单里：
#    它是素材库索引，用户新增素材后会被写回（items 不再是空数组）。
#    虽然仓库里那份是「默认资产库 + 3 个空分类」的出厂骨架，但一旦随包分发，
#    用户覆盖安装就会被清回空骨架 —— 素材文件还在 assets/library/ 下，
#    索引却没了，等于素材库凭空清空。
#    而且 main.py 的 load_asset_library() 在文件缺失时会自建默认库并落盘，
#    本就不需要随包提供。见 main.py:7913-7917。
DATA_SHIPPED_FILES = [
    "data/inspire_prompt_zh.json",   # 灵感库中文提示词词典（665 KB），纯只读程序资源
]

# 白名单目录里需要剔除的构建产物 / 临时物（相对项目根）
EXCLUDE_PREFIXES = [
    "launcher/bin/",
    "launcher/obj/",
    "dist/dist/",
    "tools/__pycache__/",
]

# ---------------------------------------------------------------------------
# 黑名单（安全网）：任何命中项都视为「用户数据泄漏」，直接中止
# ---------------------------------------------------------------------------

DENY_PREFIXES = [
    ".git/",
    ".workbuddy-ai/",
    ".claude/",
    "API/",
    "assets/",
    "output/",
    "data/",          # 由 DATA_SHIPPED_FILES 单独放行
]

DENY_EXACT = {
    "history.json",
    "inspire_image_dims.json",
    "API/.env",
    "Lochou启动器.exe.WebView2",
}

DENY_SUBSTRINGS = [
    "/__pycache__/",
    ".exe.WebView2/",
]

DENY_SUFFIXES = [
    ".pyc",
    ".pyo",
]

# 必须存在的文件（缺任何一个说明包不完整）
REQUIRED = [
    "main.py",
    "VERSION",
    "Lochou启动器.exe",
    "static/index.html",
    "dist/launcher/index.html",
]


def rel_norm(path: str) -> str:
    return str(path).replace("\\", "/").lstrip("/")


def is_denied(rel: str) -> tuple[bool, str]:
    """返回 (是否禁止, 原因)。"""
    r = rel_norm(rel)
    if r in DENY_EXACT:
        return True, "黑名单精确命中"
    for p in DENY_PREFIXES:
        if r == p.rstrip("/") or r.startswith(p):
            # data/ 的两个内置文件单独放行
            if p == "data/" and r in DATA_SHIPPED_FILES:
                return False, ""
            return True, f"黑名单前缀 {p}"
    for s in DENY_SUBSTRINGS:
        if s in r:
            return True, f"黑名单片段 {s}"
    for s in DENY_SUFFIXES:
        if r.endswith(s):
            return True, f"黑名单后缀 {s}"
    if r.startswith("static/__") and r.endswith(".html"):
        return True, "一次性验证探针页"
    return False, ""


def is_excluded(rel: str) -> bool:
    r = rel_norm(rel)
    return any(r == p.rstrip("/") or r.startswith(p) for p in EXCLUDE_PREFIXES)


def collect_files() -> tuple[list[str], list[str]]:
    """返回 (入选的相对路径列表, 被黑名单拦下的路径列表)。"""
    picked: list[str] = []
    blocked: list[str] = []

    def add(rel: str) -> None:
        rel = rel_norm(rel)
        if is_excluded(rel):
            return
        denied, reason = is_denied(rel)
        if denied:
            blocked.append(f"{rel}  <- {reason}")
            return
        full = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.isfile(full):
            return
        picked.append(rel)

    for f in ROOT_FILES:
        add(f)

    for f in DATA_SHIPPED_FILES:
        add(f)

    for d in PROGRAM_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dp, dn, fn in os.walk(base):
            dn[:] = [x for x in dn if x not in ("__pycache__", ".git")]
            for name in fn:
                full = os.path.join(dp, name)
                add(os.path.relpath(full, ROOT))

    return sorted(set(picked)), blocked


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def human(n: int) -> str:
    return f"{n / 1048576:.2f} MB"


# ---------------------------------------------------------------------------
# 版本与说明
# ---------------------------------------------------------------------------

VERSION_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")


def read_version() -> str:
    path = os.path.join(ROOT, "VERSION")
    if not os.path.isfile(path):
        sys.exit("[FATAL] 找不到 VERSION 文件")
    text = open(path, encoding="utf-8").read().strip().splitlines()
    version = text[0].strip() if text else ""
    if not VERSION_RE.match(version):
        sys.exit(f"[FATAL] VERSION 格式应为 YYYY.MM.DD，实际为 {version!r}")
    return version


def version_key(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))


def extract_notes_from_changelog() -> list[str]:
    """从 CHANGELOG.md 顶部第一个 #### 段落抓更新说明。"""
    path = os.path.join(ROOT, "CHANGELOG.md")
    if not os.path.isfile(path):
        return []
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    notes: list[str] = []
    started = False
    for line in lines:
        s = line.strip()
        if s.startswith("#### "):
            if started:
                break
            started = True
            notes.append(s[5:].strip())
            continue
        if not started:
            continue
        if s.startswith("#"):
            break
        if s.startswith(("-", "*", "·")):
            item = s.lstrip("-*· ").strip()
            if item:
                notes.append(item)
        elif s.startswith("**") and s.endswith("**") and len(s) > 4:
            item = s.strip("*").strip().rstrip("：:").strip()
            if item:
                notes.append(item)
    return notes[:40]


def read_notes_file(path: str) -> list[str]:
    text = open(path, encoding="utf-8", errors="replace").read().splitlines()
    out = []
    for line in text:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            out.append(s.lstrip("# ").strip())
        else:
            out.append(s.lstrip("-*· ").strip())
    return out[:60]


# ---------------------------------------------------------------------------
# 打包
# ---------------------------------------------------------------------------

def write_zip(zip_path: str, files: list[str], top: str = PACKAGE_TOP) -> None:
    """写 zip。条目时间固定，保证内容相同则产物字节相同。"""
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    fixed = (2026, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel in files:
            src = os.path.join(ROOT, rel.replace("/", os.sep))
            info = zipfile.ZipInfo(f"{top}/{rel}", date_time=fixed)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(src, "rb") as f:
                z.writestr(info, f.read())


def find_previous_baseline(current_version: str) -> tuple[str, dict] | None:
    """找比当前版本小的、最新的 file-hashes.json 作为增量基线。"""
    if not os.path.isdir(RELEASE_ROOT):
        return None
    best: tuple[str, dict] | None = None
    for name in os.listdir(RELEASE_ROOT):
        if not VERSION_RE.match(name) or name == current_version:
            continue
        if version_key(name) >= version_key(current_version):
            continue
        path = os.path.join(RELEASE_ROOT, name, "file-hashes.json")
        if not os.path.isfile(path):
            continue
        if best is None or version_key(name) > version_key(best[0]):
            import json
            best = (name, json.load(open(path, encoding="utf-8")))
    return best


def maybe_build_exe(enable: bool) -> None:
    """可选：重编启动器 exe（会改动被 git 跟踪的 Lochou启动器.exe）。"""
    if not enable:
        exe = os.path.join(ROOT, "Lochou启动器.exe")
        src = os.path.join(ROOT, "launcher", "Program.cs")
        if os.path.isfile(exe) and os.path.isfile(src):
            if os.path.getmtime(src) > os.path.getmtime(exe):
                print("[WARN] launcher/Program.cs 比 Lochou启动器.exe 新，exe 可能是旧版。")
                print("       需要重编请加 --build-exe（重编后 exe 会变动，记得提交）。")
        return

    print("[exe ] 重编启动器 ...")
    script = os.path.join(ROOT, "build-launcher.ps1")
    if os.path.isfile(script):
        rc = subprocess.call(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
            cwd=ROOT,
        )
        if rc != 0:
            sys.exit(f"[FATAL] build-launcher.ps1 退出码 {rc}")
    else:
        sys.exit("[FATAL] 找不到 build-launcher.ps1")


# ---------------------------------------------------------------------------
# 命令
# ---------------------------------------------------------------------------

def cmd_list(args) -> int:
    files, blocked = collect_files()
    total = sum(os.path.getsize(os.path.join(ROOT, f.replace("/", os.sep))) for f in files)
    print(f"会进包的文件：{len(files)} 个，{human(total)}")
    print(f"被黑名单拦下：{len(blocked)} 个（正常情况应为 0，这些路径本来就不该在包内）")
    for b in blocked[:40]:
        print(f"  [deny] {b}")
    print()
    groups: dict[str, list[str]] = {}
    for f in files:
        groups.setdefault(f.split("/")[0] if "/" in f else "(根文件)", []).append(f)
    for g in sorted(groups, key=lambda k: -sum(
            os.path.getsize(os.path.join(ROOT, x.replace("/", os.sep))) for x in groups[k])):
        sz = sum(os.path.getsize(os.path.join(ROOT, x.replace("/", os.sep))) for x in groups[g])
        print(f"  {g:<24}{len(groups[g]):>6} 文件  {human(sz):>12}")
    print()
    missing = [r for r in REQUIRED if r not in files]
    if missing:
        print(f"[FATAL] 缺少必需文件：{missing}")
        return 1
    print("必需文件齐全。")
    return 0


def cmd_verify(args) -> int:
    target = args.target
    names: list[str] = []
    label = target
    if os.path.isfile(target):
        with zipfile.ZipFile(target) as z:
            names = z.namelist()
        label = f"{target}（zip）"
    elif os.path.isdir(target):
        for dp, dn, fn in os.walk(target):
            dn[:] = [d for d in dn if d not in ("__pycache__",)]
            for f in fn:
                names.append(os.path.relpath(os.path.join(dp, f), target).replace(os.sep, "/"))
        label = f"{target}（目录）"
    else:
        sys.exit(f"[FATAL] 路径不存在：{target}")

    # 去掉包内顶层目录前缀（zip 里通常是 Infinite-Canvas/）
    stripped = []
    for n in names:
        if n.endswith("/"):
            continue
        parts = n.split("/")
        stripped.append("/".join(parts[1:]) if len(parts) > 1 else parts[0])

    hits = []
    for rel in stripped:
        denied, reason = is_denied(rel)
        if denied:
            hits.append((rel, reason))

    print(f"检查对象：{label}")
    print(f"条目数：{len(stripped)}")
    print()
    if not hits:
        print("==> 未发现用户数据路径，通过。")
        return 0

    agg: dict[str, list[str]] = {}
    for rel, reason in hits:
        key = reason
        agg.setdefault(key, []).append(rel)
    print(f"==> 发现 {len(hits)} 条用户数据路径，不通过：")
    for key in sorted(agg):
        sample = agg[key][:5]
        print(f"  {key}：{len(agg[key])} 条")
        for s in sample:
            print(f"      {s}")
    return 1


def cmd_build(args) -> int:
    version = read_version()
    out_dir = os.path.join(RELEASE_ROOT, version)
    os.makedirs(out_dir, exist_ok=True)

    maybe_build_exe(args.build_exe)

    files, blocked = collect_files()
    if blocked:
        print("[FATAL] 白名单里出现了黑名单路径，说明清单写错了，已中止：")
        for b in blocked:
            print(f"  [deny] {b}")
        return 1

    missing = [r for r in REQUIRED if r not in files]
    if missing:
        print(f"[FATAL] 缺少必需文件：{missing}")
        return 1

    # main.py 语法自检，避免把坏文件打进包
    main_py = os.path.join(ROOT, "main.py")
    try:
        compile(open(main_py, "rb").read(), main_py, "exec")
    except SyntaxError as exc:
        print(f"[FATAL] main.py 语法错误，已中止：{exc}")
        return 1

    hashes = {rel: sha256_file(os.path.join(ROOT, rel.replace("/", os.sep))) for rel in files}
    total = sum(os.path.getsize(os.path.join(ROOT, f.replace("/", os.sep))) for f in files)

    print(f"[info] 版本 {version}")
    print(f"[info] 入选 {len(files)} 个文件，合计 {human(total)}")
    print()

    # 完整包
    full_name = f"Infinite-Canvas-Full-{version}.zip"
    full_path = os.path.join(out_dir, full_name)
    write_zip(full_path, files)
    full_size = os.path.getsize(full_path)
    print(f"[pack] {full_name}  {human(full_size)}")

    # 增量包
    packages = [{
        "kind": "full",
        "name": full_name,
        "size": full_size,
        "sha256": sha256_file(full_path),
        "from_version": "",
    }]

    baseline = find_previous_baseline(version)
    if baseline:
        base_ver, base_hashes = baseline
        changed = sorted(
            rel for rel, h in hashes.items()
            if base_hashes.get(rel) != h
        )
        removed = sorted(set(base_hashes) - set(hashes))
        if not changed:
            print(f"[info] 与基线 {base_ver} 相比没有任何文件变化，不产出增量包。")
        elif removed:
            # 增量包只覆盖「新增/修改」，表达不了「删除」——用户目录里被删的文件会残留，
            # 而残留的旧 JS/CSS 会和新版本混跑，比不更新更危险。有删除就只发完整包。
            print(f"[info] 与基线 {base_ver} 相比有 {len(removed)} 个文件被删除"
                  f"（{', '.join(removed[:5])}{' …' if len(removed) > 5 else ''}），"
                  "增量包无法表达删除，本次只产出完整包。")
        else:
            delta_name = f"Infinite-Canvas-Update-{version}.zip"
            delta_path = os.path.join(out_dir, delta_name)
            write_zip(delta_path, changed)
            delta_size = os.path.getsize(delta_path)
            print(f"[pack] {delta_name}  {human(delta_size)}  "
                  f"（基线 {base_ver}：变更 {len(changed)} 个）")
            packages.insert(0, {
                "kind": "delta",
                "name": delta_name,
                "size": delta_size,
                "sha256": sha256_file(delta_path),
                "from_version": base_ver,
            })
    else:
        print("[info] 没有更早的 file-hashes.json，本次不产出增量包（只有完整包）。")

    # 清单
    notes = read_notes_file(args.notes_file) if args.notes_file else extract_notes_from_changelog()
    manifest = {
        "format": 1,
        "channel": args.channel,
        "version": version,
        "tag": args.tag or f"Official.{version}",
        "published_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "min_launcher_version": args.min_launcher or "",
        "notes": notes,
        "packages": packages,
    }
    import json
    manifest_path = os.path.join(out_dir, "update.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    hashes_path = os.path.join(out_dir, "file-hashes.json")
    with open(hashes_path, "w", encoding="utf-8") as f:
        json.dump(hashes, f, ensure_ascii=False, indent=2, sort_keys=True)

    # 汇总
    lines = [
        f"版本：{version}",
        f"tag：{manifest['tag']}",
        f"通道：{manifest['channel']}",
        f"入选文件：{len(files)} 个，{human(total)}（未压缩）",
        "",
        "产物：",
    ]
    for p in packages:
        lines.append(f"  {p['kind']:<6} {p['name']}  {human(p['size'])}  sha256={p['sha256'][:16]}…")
    lines += [
        f"  manifest update.json",
        "",
        "发布命令（在你自己终端执行，工具会话内 gh/git push 会挂起）：",
        "",
        "  gh release create " + manifest["tag"] + " \\",
    ]
    for p in packages:
        lines.append(f"    \"{out_dir}\\{p['name']}\" \\")
    lines += [
        f"    \"{out_dir}\\update.json\" \\",
        f"    --title \"{manifest['tag']}\" --notes-file RELEASE_NOTES.md",
        "",
        "注意：update.json 必须作为 Release 资产上传，启动器会用",
        "      https://github.com/HanaJhon/Infinite-Canvas/releases/latest/download/update.json 取它。",
    ]
    summary = "\n".join(lines)
    with open(os.path.join(out_dir, "release-summary.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n")

    print()
    print(summary)
    print()
    print(f"产物目录：{out_dir}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Infinite-Canvas 干净发布打包")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出会进包的文件")
    p_list.set_defaults(func=cmd_list)

    p_ver = sub.add_parser("verify", help="校验已有包/目录是否含用户数据")
    p_ver.add_argument("target")
    p_ver.set_defaults(func=cmd_verify)

    p_build = sub.add_parser("build", help="生成干净包")
    p_build.add_argument("--build-exe", action="store_true",
                         help="先重编启动器 exe（会改动被 git 跟踪的 exe）")
    p_build.add_argument("--channel", default="stable", choices=["stable", "beta"])
    p_build.add_argument("--tag", default="", help="Release tag，默认 Official.<版本>")
    p_build.add_argument("--min-launcher-version", dest="min_launcher", default="")
    p_build.add_argument("--notes-file", dest="notes_file", default="",
                         help="更新说明文件；不传则从 CHANGELOG.md 顶部抓")
    p_build.set_defaults(func=cmd_build)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
