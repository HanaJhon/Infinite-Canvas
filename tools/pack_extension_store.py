"""把 extension/ 打成 Edge 加载项商店（Partner Center）可上传的 zip。

和 /api/extension/download 的区别：商店要求 manifest.json 在 zip 根目录，
而站内下载的包是 infinite-canvas-capture/ 子目录（给"加载解压缩的扩展"用）。

用法：./python/python.exe tools/pack_extension_store.py
输出：output/edge-store/infinite-canvas-capture-<version>.zip
"""

import json
import os
import sys
import zipfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "extension")
OUT_DIR = os.path.join(BASE_DIR, "output", "edge-store")

# 商店包里不要的东西：说明文档、探针/截图用的临时目录
SKIP_FILES = {"README.md"}
SKIP_PREFIXES = ("__",)


def main():
    manifest_path = os.path.join(SRC_DIR, "manifest.json")
    with open(manifest_path, encoding="utf-8") as fp:
        manifest = json.load(fp)
    version = str(manifest.get("version") or "0.0.0")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"infinite-canvas-capture-{version}.zip")

    added = []
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(SRC_DIR):
            dirs[:] = sorted(d for d in dirs if not d.startswith(SKIP_PREFIXES))
            for name in sorted(files):
                if name in SKIP_FILES or name.startswith(SKIP_PREFIXES):
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, SRC_DIR).replace(os.sep, "/")
                zf.write(full, rel)
                added.append(rel)

    # 商店硬要求：manifest.json 在根目录
    with zipfile.ZipFile(out_path) as zf:
        names = zf.namelist()
        assert "manifest.json" in names, "zip 根目录缺少 manifest.json"
        packed = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert packed.get("version") == version, "zip 内版本号与源文件不一致"

    size = os.path.getsize(out_path)
    print(f"OUT={out_path}")
    print(f"VERSION={version} FILES={len(names)} BYTES={size}")
    for rel in added:
        print(f"  {rel}")
    print("PACK_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
