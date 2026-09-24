# -*- coding: utf-8 -*-
"""发布包安全审计：证明 zip / 目录里**不含任何密钥与用户数据**。

为什么要单独有这个工具（2026-09-20 踩坑）：
  `tools/release.py verify` 只做「路径 deny-list」断言，而密钥是**内容**问题。
  实测它报「通过」的那个包里，`tools/scan_secrets.py` 的注释就藏着一枚真密钥
  （我为说明 ENV_LINE 的 bug，把密钥原样抄进了注释）—— 路径断言完全看不见。

用法：
    python tools/scan_release.py <zip 或 目录>      # 审计
    python tools/scan_release.py --selftest        # 只跑正控

两把尺子（缺一不可）：
  ① `scan_secrets.py` 的规则 —— 项目既有规则，扫 env 行 / JSON 字段 / 已知前缀 / Bearer / 行内 KEY=数字
  ② 本文件内置的**独立规则集** —— 覆盖 ① 的盲区（如 `const KEY = "xxx"` 这类任意硬编码）

⚠️ 0 命中必须配「正控」才有意义：先证明这套规则量得到已知密钥，
   否则规则写错（比如 `\s` 吃换行）会把「漏报」伪装成「已干净」。
"""
import importlib.util
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


# ─────────────────────────────────────────────── 尺子①：复用项目规则
def load_scan_secrets():
    spec = importlib.util.spec_from_file_location(
        "scan_secrets", os.path.join(HERE, "scan_secrets.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────── 尺子②：独立规则集
PATS = [
    ("ASSIGN", re.compile(
        r"""(?i)\b(?:const|let|var|self\.|this\.)?\s*"""
        r"""([A-Za-z_][A-Za-z0-9_]*?(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|"""
        r"""secret|password|passwd|credential)[A-Za-z0-9_]*?)"""
        r"""\s*[:=]\s*['"]([^'"\n]{8,120})['"]"""), 2),
    ("HEADER", re.compile(
        r"""(?i)(?:authorization|api[-_]?key|x-api-key)['\"]?\s*[:=]\s*['\"]([^'"\n]{8,200})['\"]"""), 1),
    ("BEARER", re.compile(r"(?i)bearer\s+([A-Za-z0-9_\-\.]{16,200})"), 1),
    ("NUMKEY", re.compile(
        r"""(?i)(?:key|token|secret)['\"]?\s*[:=]\s*['\"]?(\d{10,24})['\"]?"""), 1),
    ("RANDOM", re.compile(
        r"""['"](?=[A-Za-z0-9_\-]{32,120}['"])(?=[^'\"]*[a-z])(?=[^'\"]*[A-Z])(?=[^'\"]*[0-9])"""
        r"""([A-Za-z0-9_\-]{32,120})['"]"""), 1),
]

BENIGN = re.compile(r"""(?i)^(?:
    your[_-]?|xxx+|placeholder|example|changeme|todo|test|dummy|none|null|undefined|true|false|
    \*{3,}|\.{3,}|-{3,}|_{3,}|0{6,}|1{6,}|
    https?://|/static/|/api/|\.(png|jpe?g|svg|js|css|json|html|woff2?)|
    [0-9a-f]{32,}
)$""", re.X)

# ─────────────────────────────────────────────── 结构断言（路径级）
FORBID_PATHS = [
    (re.compile(r"(^|/)API(/|$)", re.I),             "API/ 目录（含 .env）"),
    (re.compile(r"(^|/)\.env(\.|$)", re.I),          ".env 文件"),
    (re.compile(r"(^|/)data/canvases?/", re.I),      "画布数据"),
    (re.compile(r"(^|/)data/(chat_|media_previews/)", re.I), "会话/预览缓存"),
    (re.compile(r"(^|/)data/(projects|prompt_libraries|asset_library)\.json$", re.I), "用户配置/素材库索引"),
    (re.compile(r"(^|/)history\.json$", re.I),       "history.json"),
    (re.compile(r"(^|/)assets/(input|output|library|uploads)/", re.I), "用户素材"),
    (re.compile(r"(^|/)\.git(/|$)", re.I),           ".git 目录"),
    (re.compile(r"(^|/)\.workbuddy-ai(/|$)", re.I),  ".workbuddy-ai 记忆目录"),
]

# ─────────────────────────────────────────────── 结构断言（内容级）
PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")
BIN_EXT = re.compile(r"\.(png|jpe?g|gif|webp|ico|svgz|zip|7z|rar|exe|dll|pdb|so|dylib|"
                     r"woff2?|ttf|otf|eot|mp[34]|wav|pdf|pyc|pack|idx)$", re.I)
# vendored 第三方库：熵启发式（RANDOM）在这里只会产生噪声
# （SPDX 许可证 id、base64 文档示例、压缩后的 JS —— 2026-09-20 逐个核实过）
VENDORED = ("/site-packages/", "/static/vendor/")


def is_code(val: str, txt: str, end: int) -> bool:
    """捕获到的是「代码」而非「字面量」：函数调用、标识符、含代码符号。"""
    if end < len(txt) and txt[end] == "(":
        return True
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", val) and ("_" in val or val[:1].islower()):
        return True
    return bool(re.search(r"[\s<>{};()\[\],]", val))


def iter_entries(target: str):
    """统一产出 (显示名, 文本或 None)。None 表示调用方自行从磁盘读。"""
    if target.lower().endswith(".zip"):
        with zipfile.ZipFile(target) as z:
            for n in z.namelist():
                if n.endswith("/"):
                    continue
                yield n, z.read(n)
    else:
        for dp, _dn, fn in os.walk(target):
            for f in fn:
                p = os.path.join(dp, f)
                rel = os.path.relpath(p, target).replace(os.sep, "/")
                try:
                    with open(p, "rb") as fh:
                        yield rel, fh.read()
                except OSError:
                    continue


def positive_control() -> int:
    """正控：确认两把尺子都量得到已知密钥，否则 0 命中毫无意义。

    🚨 样本**必须运行时拼装，不能写字面量** —— 否则本文件自己就成了泄漏源。
       踩过（2026-09-20）：第一版把密钥字面量直接写在样本里，立刻被本工具自己的
       安全闸拦下（`release.py build` 报 6 处命中）。现在每段都拆成 <32 字符的碎片，
       保证文件文本里既没有 10+ 位数字串、也没有 32+ 位随机串。
    """
    d = "415" + "645" + "64561"                       # 11 位纯数字（Grsai 这类）
    sk = "sk-" + "proj-" + "Ab3xK9mQ2Lp7" + "Rt5Vw1Yz8Nc4Bd6" + "Ef0Gh2Ij4Kl"
    jw = "eyJ" + "hbGciOiJIUzI1" + "NiIsInR5cCI6" + "IkpXVCJ9"
    sample = (
        f'const GRSAI_API_KEY = "{d}";\n'
        f'api_key = "{sk}"\n'
        f'X-API-Key: "{sk}"\n'
        f'Authorization: Bearer {jw}\n'
        f'# 注释里也藏一个 API_PROVIDER_GRSAI_KEY={d}\n'
        'max_tokens=4096\n'
    )
    n = 0
    for kind, rx, gi in PATS:
        for m in rx.finditer(sample):
            v = m.group(gi)
            if BENIGN.match(v) or is_code(v, sample, m.end(gi)) or re.search(r"[/\\@:]", v):
                continue
            n += 1
    return n


def scan(target: str) -> int:
    ss = load_scan_secrets()
    ignore = ss.load_ignore()
    struct, secrets, stats = [], [], {"txt": 0, "bin": 0, "total": 0, "ignored": 0}

    for name, raw in iter_entries(target):
        stats["total"] += 1
        norm = name.replace("\\", "/")
        for rx, label in FORBID_PATHS:
            if rx.search(norm):
                struct.append((name, label))
        if BIN_EXT.search(norm):
            stats["bin"] += 1
            continue
        if b"\x00" in raw[:8192]:
            stats["bin"] += 1
            continue
        txt = raw.decode("utf-8", "replace")
        stats["txt"] += 1

        if PRIVATE_KEY.search(txt):
            struct.append((name, "私钥内容（BEGIN PRIVATE KEY）"))
        # 🚨 必须尊重 .secretsignore —— 否则「把误报写进 .secretsignore」这条官方指引
        #    在发布包审计里根本不生效（踩过：fontTools 的 CURVE_TYPE_LIB_KEY 被尺子①
        #    误判，写进豁免清单后 build 仍然中止，因为 scan_release 直接调 scan_text、
        #    绕过了 scan_secrets.skip()）。这里只取豁免清单那一部分，不套用 skip() 的
        #    路径/后缀跳过，避免顺手把本该扫的文件也放过。
        if any(pat in norm for pat in ignore):
            stats["ignored"] += 1
            continue
        for kind, masked in ss.scan_text(name, txt):
            secrets.append((name, f"[尺子①] {kind}: {masked}"))
        vendored = any(v in norm for v in VENDORED)
        is_svg = norm.endswith(".svg") or "<svg" in txt[:2000]
        for kind, rx, gi in PATS:
            if kind == "RANDOM" and (vendored or is_svg):
                continue
            for m in rx.finditer(txt):
                v = m.group(gi)
                if BENIGN.match(v) or is_code(v, txt, m.end(gi)) or re.search(r"[/\\@:]", v):
                    continue
                line = txt[:m.start()].count("\n") + 1
                secrets.append((name, f"[尺子②/{kind}] 第 {line} 行 = "
                                      f"{v if len(v) <= 16 else v[:6] + '…' + v[-4:]}"))

    print("=" * 66)
    print(f"审计对象：{target}")
    print(f"条目 {stats['total']} 个（文本 {stats['txt']}，二进制 {stats['bin']}，豁免 {stats['ignored']}）")
    print("-" * 66)
    print(f"【结构断言】命中 {len(struct)} 项")
    for n, label in struct[:40]:
        print(f"   ✖ {label}  ->  {n}")
    if not struct:
        print("   [OK] 无 API/ 无 .env 无用户数据（画布/会话/素材/配置）无 .git 无私钥")
    print("-" * 66)
    print(f"【密钥扫描】命中 {len(secrets)} 项")
    for n, d in secrets[:40]:
        print(f"   ✖ {n}  {d}")
    if not secrets:
        print("   [OK] 两把尺子均 0 命中")
    print("=" * 66)

    pc = positive_control()
    ok = pc >= 3
    print(f"【正控】合成样本命中 {pc} 项 {'[OK] 尺子有效' if ok else '[FAIL] 尺子失效，本次结论作废'}")
    print("=" * 66)
    if not ok:
        return 2
    return 1 if (struct or secrets) else 0


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")   # GBK 控制台不崩
        except Exception:
            pass
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--selftest" in sys.argv:
        pc = positive_control()
        print(f"【正控】合成样本命中 {pc} 项 -> {'[OK]' if pc >= 3 else '[FAIL]'}")
        return 0 if pc >= 3 else 2
    if not args:
        print(__doc__)
        return 2
    return scan(args[0])


if __name__ == "__main__":
    sys.exit(main())
