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
    python tools/bump_version.py                 # 先升版本号（改 VERSION），再打包
    python tools/release.py list                 # 只列出会进包的文件，不写盘
    python tools/release.py verify <zip 或目录>  # 校验已有包/目录是否含用户数据
    python tools/release.py build                # 生成干净包 + update.json
    python tools/release.py build --build-exe    # 先重编启动器 exe 再打包
    python tools/release.py build --notes-file output/RELEASE_NOTES-<版本>.md

产物（默认写到 output/release/<版本>/）
--------------------------------------
    Infinite-Canvas-Full-<版本>.zip      完整程序包（首次安装 / 跨版本 / 自动更新）
    Infinite-Canvas-Update-<版本>.zip    增量包（只含与上一版本相比有变化的文件；
                                          仅当本次没有文件被删除时才产出，且启动器
                                          目前只接受完整包 kind=full）
    update.json                          更新清单（放到 GitHub Release 资产里）
    包内 release-manifest.json           虚拟条目，更新执行器的唯一权威来源
                                          {format,version,kind,prune_roots,files:{路径:sha256}}
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
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from versioning import (  # noqa: E402
    ACCEPTED_RE,
    is_canonical,
    is_legacy_date,
    normalize_version,
    parse_version,
)

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
    # 内置 Skill（只读，随包分发）：main.py 的 BUILTIN_SKILLS_DIR 指这里。
    # 不能放 data/agent_skills/ —— data/ 是用户数据目录，被 DENY_PREFIXES 整目录排除。
    "skills",
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
    # ⚠️ build-launcher.ps1（以及等价的 dotnet publish -o dist）会把启动器的发布
    #    产物写进根 dist\。其中 dist\InfiniteCanvasLauncher.exe 是 69 MB 的**重复
    #    exe** —— 用户实际运行的是根目录的 Lochou启动器.exe，这个副本永远用不到，
    #    随包分发会让安装包凭空涨 70 MB。
    #    踩过（2026-09-18）：重编 exe 后打包，包体积从 111 MB 虚涨到 175 MB。
    "dist/InfiniteCanvasLauncher.",
    "dist/Microsoft.Web.WebView2.",
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

# VERSION 可接受的写法：三段式（1.1.1）或日期制遗留（2026.09.20）。
# 规则与进位逻辑见 tools/versioning.py。
VERSION_RE = ACCEPTED_RE


def read_version() -> str:
    """读 VERSION 并折算成规范式。

    规范式 = 按「满十进位」规则折算后的形式（1.1.10 → 1.2.0）。

    ⚠️ 若 VERSION 里不是规范式，这里会**改写 VERSION 文件**。必须这么做：
    update.json 的 version 与包内 VERSION 必须逐字一致，否则客户端装完新版
    VERSION 仍是 1.1.10、比对结果永远是「有新版」，陷入更新死循环。
    改写后会打印 [warn]，记得把它一起提交。
    """
    path = os.path.join(ROOT, "VERSION")
    if not os.path.isfile(path):
        sys.exit("[FATAL] 找不到 VERSION 文件")
    text = open(path, encoding="utf-8").read().strip().splitlines()
    version = text[0].strip() if text else ""
    if not version:
        sys.exit("[FATAL] VERSION 文件是空的")
    if not VERSION_RE.match(version):
        sys.exit(f"[FATAL] VERSION 格式无法识别：{version!r}\n"
                 f"        应为三段式（如 1.1.1），或日期制遗留（如 2026.09.20）")

    if is_legacy_date(version):
        print(f"[warn] VERSION 仍是日期制遗留值 {version}，本次会按这个版本号打包。\n"
              f"       若要切到三段式，请先执行："
              f"python tools/bump_version.py --set 1.1.1")
        return version

    if not is_canonical(version):
        canonical = normalize_version(version)
        print(f"[warn] VERSION 不是规范式：{version} → {canonical}"
              f"（已写回 VERSION 文件，记得一并提交）")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(canonical + "\n")
        return canonical
    return version


def version_key(v: str) -> tuple:
    """版本排序键：按数字段逐段比较。

    日期制遗留值天然排在前面（2026.09.20 → (2026, 9, 20) > (1, 1, 1)），
    所以切到三段式后，旧的日期目录不会成为增量基线（find_previous_baseline
    里另有显式跳过）。
    """
    return tuple(parse_version(v))


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


_MD_INLINE = [
    (re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)"), r"\1"),   # [文字](链接) -> 文字
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),             # **粗体**
    (re.compile(r"__([^_]+)__"), r"\1"),
    (re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)"), r"\1"),    # *斜体*
    (re.compile(r"`([^`]+)`"), r"\1"),                   # `行内代码` -> 纯文字
]
_LIST_MARKER = re.compile(r"^(?:[-*+·]|\d+[.)])\s+")
# Markdown 水平分隔线（`---` / `***` / `___`）。它们是**排版结构**，不是内容 ——
# 漏进 body 会在更新面板里变成一个「---」圆点。踩过（2026-09-24，1.1.7）：
# 说明里加了 3 条 `---`，面板就多了 3 个「---」条目，还把真实条目挤出了 24 条上限。
_HR_LINE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")


def _md_to_plain(s: str) -> str:
    """把一行 Markdown 压成纯文字。

    更新说明最终是给**启动器更新面板**当纯文本列表项显示的（不是渲染 Markdown），
    所以反引号、粗体星号、链接语法都会原样露出，必须在这里剥掉。
    """
    for pat, repl in _MD_INLINE:
        s = pat.sub(repl, s)
    return re.sub(r"\s+", " ", s).strip()


# 「收尾话术」章节的标题关键词。这些章节写的是怎么升级/怎么装，不是本次改了什么，
# 混进更新面板就会变成「推荐在启动器里点胶囊一键更新」这种冒充新功能的条目。
# ⚠️ 只跳过**认识的**标题 —— 不认识的标题一律保留，宁可多显示也不悄悄漏掉真实条目。
_SKIP_SECTION_KEYS = (
    "升级", "安装", "下载", "注意", "说明",
    "upgrade", "install", "download", "notes",
)


def read_notes_file(path: str) -> list[str]:
    """读 `--notes-file` 指定的 Markdown，产出**适合直接显示**的纯文本条目。

    ⚠️ 标题行（`#` / `##`）**不产出条目** —— 面板把每条渲染成一个圆点，
    标题当圆点就是「本次更新」「升级方式」这类噪音，还会把真正的内容挤出显示窗口。
    只在「整份文件只有标题」时才退回用标题，避免产出空列表。

    ⚠️ 「升级方式」这类收尾章节的正文也**不产出条目**，见 `_SKIP_SECTION_KEYS`。

    ⚠️ 水平分隔线（`---`）同样**不产出条目**，见 `_HR_LINE`。

    🚨 **返回值硬截断到 24 条**（面板显示窗口有限）。所以 `--notes-file` 的
    **正文行数必须 ≤ 24**，否则排在后面的章节会被**静默丢掉** —— 踩过
    （2026-09-24，1.1.7）：正文 33 行，新加的两节落在第 25~30 行，全被截掉，
    面板上完全看不到本次最想说的改动。写完记得数一下正文行数。
    """
    headings, body = [], []
    skipping = False
    for line in open(path, encoding="utf-8", errors="replace").read().splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            t = _md_to_plain(s.lstrip("# ").strip())
            if t:
                headings.append(t)
            low = t.lower()
            skipping = any(k in low for k in _SKIP_SECTION_KEYS)
            continue
        if skipping:
            continue
        if _HR_LINE.match(s):
            continue
        s = s.lstrip(">").strip()             # 引用块
        s = _LIST_MARKER.sub("", s)           # - / * / 1. 列表符号
        s = _md_to_plain(s)
        if s:
            body.append(s)
    return (body or headings)[:24]



# ---------------------------------------------------------------------------
# 打包
# ---------------------------------------------------------------------------

def write_zip(zip_path: str, files: list[str], top: str = PACKAGE_TOP,
              extra: dict[str, bytes] | None = None) -> None:
    """写 zip。条目时间固定，保证内容相同则产物字节相同。

    `extra` 是「虚拟条目」（内容在内存里、磁盘上没有对应文件），
    用于把 release-manifest.json 塞进包内。
    """
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
        for name, data in sorted((extra or {}).items()):
            info = zipfile.ZipInfo(f"{top}/{name}", date_time=fixed)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)


def build_package_manifest(version: str, kind: str, files: list[str],
                           hashes: dict[str, str],
                           deleted: list[str] | None = None) -> bytes:
    """生成包内清单 release-manifest.json。

    这是更新器（启动器 applier）的**唯一权威来源**：它靠 `files` 的 sha256
    判断哪些文件要被覆盖（先备份旧的）、靠 `prune_roots` 判断可以删哪些
    旧版残留。之所以放进包内而不是让 C# 再维护一份目录清单，是为了避免
    「两处清单不一致」这类已经踩过的 bug。

    `prune_roots` 只取 PROGRAM_DIRS 里真实出现过的顶层目录 ——
    即**程序独占目录**。`data/` / `assets/` / `output/` / `API/` 永不在其中，
    所以 applier 不可能误删用户数据。

    `deleted` 仅增量包 (delta) 使用：列出本版相对基线「被移除」的文件，
    启动器会按它把它们从安装目录删掉（不能靠剪枝表达，因为 delta 不剪枝）。
    """
    roots = sorted({f.split("/")[0] for f in files if "/" in f} & set(PROGRAM_DIRS))
    manifest = {
        "format": 1,
        "version": version,
        "kind": kind,                 # full | delta
        "prune_roots": roots,
        "files": {rel: hashes[rel] for rel in sorted(files)},
        "deleted": sorted(deleted or []),
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")


MANIFEST_NAME = "release-manifest.json"


def find_previous_baseline(current_version: str) -> tuple[str, dict] | None:
    """找比当前版本小的、最新的 file-hashes.json 作为增量基线。"""
    if not os.path.isdir(RELEASE_ROOT):
        return None
    best: tuple[str, dict] | None = None
    for name in os.listdir(RELEASE_ROOT):
        if not VERSION_RE.match(name) or name == current_version:
            continue
        # 日期制遗留目录（如 2026.09.20）不作为三段式的增量基线：
        # 那个版本号没有真实用户装过，拿它做基线只会产出「没人能装」的增量包。
        if is_legacy_date(name):
            continue
        if version_key(name) >= version_key(current_version):
            continue
        path = os.path.join(RELEASE_ROOT, name, "file-hashes.json")
        if not os.path.isfile(path):
            continue
        if best is None or version_key(name) > version_key(best[0]):
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

    # 完整包（内含 release-manifest.json，供启动器 applier 备份与剪枝）
    full_name = f"Infinite-Canvas-Full-{version}.zip"
    full_path = os.path.join(out_dir, full_name)
    manifest_bytes = build_package_manifest(version, "full", files, hashes)
    write_zip(full_path, files, extra={MANIFEST_NAME: manifest_bytes})
    full_size = os.path.getsize(full_path)
    print(f"[pack] {full_name}  {human(full_size)}")
    _m = json.loads(manifest_bytes)
    print(f"[mani] 包内 {MANIFEST_NAME}：{len(_m['files'])} 个文件哈希，"
          f"可剪枝目录 {_m['prune_roots']}")

    # 🔒 安全闸：证明包内不含任何密钥 / 用户数据。
    #    为什么不能只靠上面的 deny-list 断言 —— 它是**路径**断言，而密钥是**内容**问题。
    #    踩过（2026-09-20）：`tools/scan_secrets.py` 的注释里藏着一枚真密钥，
    #    路径断言照样报「通过」，是第二把尺子才发现。详见 tools/scan_release.py。
    #    正控失败（尺子自身失效）或命中任何一项，都直接中止打包。
    audit = os.path.join(ROOT, "tools", "scan_release.py")
    if os.path.isfile(audit):
        rc = subprocess.call([sys.executable, audit, full_path])
        if rc != 0:
            print(f"[FATAL] 发布包安全审计未通过（rc={rc}），已中止。"
                  f"请看上方明细；若确认误报，把它写进 .secretsignore 或修正规则。")
            return 1
    else:
        print("[WARN] 找不到 tools/scan_release.py，跳过密钥审计（不推荐）。")

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
        # changed 已包含「新增 + 修改」；removed 是基线有、本版没有（被删）的文件
        removed = sorted(set(base_hashes) - set(hashes))
        if not changed and not removed:
            print(f"[info] 与基线 {base_ver} 相比没有任何文件变化，不产出增量包。")
        else:
            # 增量包：zip 内只放「变更文件」（新增/修改）；被删文件走 manifest.deleted，
            # 由启动器就地删除。这样哪怕本版删了文件，用户也能走增量更新，而不是被迫下全量包。
            delta_name = f"Infinite-Canvas-Update-{version}.zip"
            delta_path = os.path.join(out_dir, delta_name)
            # 清单仍带完整 files（applier 据此判断哪些要备份）与 deleted（待删文件）
            write_zip(delta_path, changed,
                      extra={MANIFEST_NAME: build_package_manifest(version, "delta", files, hashes, deleted=removed)})
            delta_size = os.path.getsize(delta_path)
            print(f"[pack] {delta_name}  {human(delta_size)}  "
                  f"（基线 {base_ver}：变更 {len(changed)} 个"
                  + (f"、删除 {len(removed)} 个" if removed else "")
                  + "）")
            packages.insert(0, {
                "kind": "delta",
                "name": delta_name,
                "size": delta_size,
                "sha256": sha256_file(delta_path),
                "from_version": base_ver,
                "deleted": len(removed),
            })
    else:
        print("[info] 没有更早的 file-hashes.json，本次不产出增量包（只有完整包）。")

    # 清单
    if args.notes_file:
        notes = read_notes_file(args.notes_file)
        notes_source = os.path.abspath(args.notes_file)
    else:
        notes = extract_notes_from_changelog()
        notes_source = os.path.join(ROOT, "CHANGELOG.md")
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
        f"    --title \"{manifest['tag']}\" --notes-file \"{notes_source}\"",
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
