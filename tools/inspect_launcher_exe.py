# -*- coding: utf-8 -*-
"""检查启动器 exe 里「有没有 / 还有没有」某个字符串或常量名。

为什么需要它：`InfiniteCanvasLauncher.csproj` 开了 `EnableCompressionInSingleFile`，
**单文件包是压缩的** → 直接 grep exe 一定搜不到任何东西，「搜不到」本身不是证据。
本脚本解析 .NET single-file bundle、解出内嵌 dll，再按正确的编码搜：
  · 字符串**字面量**  → `#US` 堆     → **UTF-16LE**
  · 方法名/类型名/常量名 → `#Strings` 堆 → **UTF-8**

🔑 用法要点：**必须带对照组**。只搜一个词、搜不到，无法区分「真的没了」和「搜法错」。
所以本脚本总是同时报「你给的词」和「兄弟常量」的命中数，并支持 `--compare` 对比新旧 exe。

示例（2026-09-21 移除 CS_DROPSHADOW 的取证）：
    # 对比旧 exe 与新建 exe
    python tools/inspect_launcher_exe.py CS_DROPSHADOW \
        --compare dist/InfiniteCanvasLauncher.exe output/_launcher_build/InfiniteCanvasLauncher.exe
    # 只查编译中间产物（未压缩，最快）
    python tools/inspect_launcher_exe.py CS_DROPSHADOW --dll

退出码：0 = 至少一个目标里找到了该词；1 = 全部没找到；2 = 用法/文件错误。
（用它做「是否消失」的判断时，**看打印出来的对照表**，不要只看退出码。）
"""
import argparse
import os
import re
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DLL = os.path.join(
    ROOT, "launcher/bin/Release/net8.0-windows/win-x64/InfiniteCanvasLauncher.dll")
BUNDLED_DLL_NAME = "InfiniteCanvasLauncher.dll"

# 对照组：同一类型里长期存在、不会被删的成员 —— 它们必须始终命中，
# 否则说明「搜不到」是搜法/解包出了问题，而不是目标真的没了。
CONTROLS = ("CreateParams", "WS_MINIMIZEBOX", "WS_MAXIMIZEBOX")


def extract_bundled_dll(exe_path):
    """从 .NET single-file bundle 里取出内嵌的 InfiniteCanvasLauncher.dll 原始字节。

    条目结构（实测）：off(int64) + size(int64) + csize(int64) + type(1 字节) + name(7-bit 长度 + UTF-8)。
    `re.search` 命中的是 name 的**长度前缀字节**，字段区在其前 25 字节；因为匹配点定义上有
    ±3 的歧义，这里对 `base = pos - 28 + a`（a ∈ -8..8）逐个试，取「inflate 长度 == size
    且以 MZ 开头」的那组，不依赖硬编码对齐。
    """
    with open(exe_path, "rb") as f:
        data = f.read()
    needle = ("\x1a" + BUNDLED_DLL_NAME).encode("utf-8")
    for m in re.finditer(re.escape(needle), data):
        pos = m.start()
        for a in range(-8, 9):
            base = pos - 28 + a
            if base < 0:
                continue
            try:
                off = int.from_bytes(data[base:base + 8], "little")
                size = int.from_bytes(data[base + 8:base + 16], "little")
                csize = int.from_bytes(data[base + 16:base + 24], "little")
                if not (0 < size < 512 * 1024 * 1024 and 0 < csize <= size):
                    continue
                if off + csize > len(data):
                    continue
                raw = zlib.decompress(data[off:off + csize], -15)
                if len(raw) == size and raw[:2] == b"MZ":
                    return raw
            except Exception:
                continue
    return None


def count(buf, token):
    """返回 (utf8 命中数, utf16le 命中数)。"""
    return (buf.count(token.encode("utf-8")), buf.count(token.encode("utf-16-le")))


def report(label, buf, tokens):
    print("  %s  (%d bytes)" % (label, len(buf)))
    rows = []
    for t in tokens:
        n8, n16 = count(buf, t)
        rows.append((t, n8, n16))
        flag = "HIT " if (n8 + n16) else "MISS"
        print("    [%s] %-22s utf8=%d  utf16le=%d" % (flag, t, n8, n16))
    return rows


def main():
    ap = argparse.ArgumentParser(description="检查启动器 exe / dll 里是否含某个字符串或常量名")
    ap.add_argument("tokens", nargs="+", help="要查的词（常量名 / 方法名 / 字符串字面量）")
    ap.add_argument("--dll", action="store_true",
                    help="只查未压缩的编译中间产物 dll（最快）")
    ap.add_argument("--dll-path", default=DEFAULT_DLL, help="覆盖中间产物 dll 路径")
    ap.add_argument("--exe", action="append", default=[],
                    help="要解包的 exe（可重复）。不传且未加 --dll 时，默认查根目录 exe。")
    ap.add_argument("--compare", nargs="+", metavar="EXE",
                    help="对比多个 exe（通常是「旧 exe 新 exe」，用来证明某词消失了）")
    args = ap.parse_args()

    tokens = list(args.tokens) + [c for c in CONTROLS if c not in args.tokens]
    targets = []

    if args.compare:
        targets = [("exe", p) for p in args.compare]
    elif args.exe:
        targets = [("exe", p) for p in args.exe]
    if args.dll or not targets:
        targets.insert(0, ("dll", args.dll_path))

    any_hit = False
    control_ok = False
    for kind, path in targets:
        if not os.path.exists(path):
            print("!! 文件不存在: %s" % path)
            continue
        if kind == "dll":
            with open(path, "rb") as f:
                buf = f.read()
            label = os.path.relpath(path, ROOT)
        else:
            buf = extract_bundled_dll(path)
            if buf is None:
                print("!! 解包失败（不是 single-file bundle？）: %s" % path)
                continue
            label = "%s → %s" % (os.path.relpath(path, ROOT), BUNDLED_DLL_NAME)
        print("=" * 72)
        rows = report(label, buf, tokens)
        for t, n8, n16 in rows:
            if t in args.tokens and (n8 + n16):
                any_hit = True
            if t in CONTROLS and (n8 + n16):
                control_ok = True

    print("=" * 72)
    if not control_ok:
        print("⚠️ 对照组（%s）一个都没命中 → 解包或搜法有问题，"
              "本次「搜不到」不可作为证据！" % "/".join(CONTROLS))
        return 2
    print("对照组命中 ✅（说明解包与搜法有效，MISS 才算证据）")
    return 0 if any_hit else 1


if __name__ == "__main__":
    sys.exit(main())
