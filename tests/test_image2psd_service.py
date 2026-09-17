"""图片分层服务自测：分层 -> 栅格化 -> 导出 PSD / 预览。

验证点：
1. 颜色聚类拆出的全画布图层能无损还原原图（分层正确性）
2. 变换 / 调色 / 蒙板擦除 / 阴影 / 文字层 / 字体回退都能落到 PSD 与预览
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image, ImageDraw

import image2psd_service as svc


def build_sample(path: str) -> None:
    W, H = 1022, 1538
    img = Image.new("RGB", (W, H), (243, 240, 233))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 90], fill=(28, 23, 18))
    d.text((40, 30), "SAMPLE POSTER 2026", fill=(255, 255, 255))
    d.ellipse([300, 300, 720, 900], fill=(206, 178, 140))
    d.rectangle([120, 1000, 460, 1300], fill=(120, 78, 44))
    d.rectangle([560, 1000, 900, 1300], fill=(60, 60, 64))
    d.text((120, 1420), "Made with Infinite Canvas", fill=(40, 40, 40))
    img.save(path)


def natural_layers(result: dict) -> list[dict]:
    canvas = result["canvas"]
    items = []
    for item in result["layers"]:
        items.append({
            "type": "image", "name": item["name"],
            "path": svc.asset_path(result["project"], os.path.basename(item["url"])),
            "x": 0, "y": 0, "w": canvas["width"], "h": canvas["height"], "opacity": 1,
        })
    return items


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="i2p-test-")
    source = os.path.join(tmp, "sample.png")
    build_sample(source)

    print("=== bggg info ===")
    print(json.dumps(svc.bggg_info(), ensure_ascii=False))

    print("=== fonts ===")
    fonts = svc.scan_fonts()
    print("font count:", len(fonts), "| default:", svc.default_font_family())
    print("MiSans ->", json.dumps(svc.resolve_font("MiSans"), ensure_ascii=False))
    print("不存在字体 ->", json.dumps(svc.resolve_font("NoSuchFont-XYZ"), ensure_ascii=False))

    print("=== layerize colors (quantize) ===")
    result = svc.layerize_colors(source, num_colors=6, method="quantize")
    print("project:", result["project"], "canvas:", result["canvas"], "layers:", len(result["layers"]))
    for item in result["layers"]:
        print("  ", item["name"], item["url"], item["coverage"])
    project = result["project"]

    print("=== 无损还原校验 ===")
    layers = [svc.build_layer(spec, (result["canvas"]["width"], result["canvas"]["height"]))[0]
              for spec in natural_layers(result)]
    comp = svc.composite_layers(layers, (255, 255, 255)).convert("RGB")
    original = Image.open(source).convert("RGB")
    diff = np.abs(np.asarray(comp, np.int16) - np.asarray(original, np.int16))
    print("mean abs diff:", round(float(diff.mean()), 4), "| max:", int(diff.max()))
    comp.save(os.path.join(tmp, "reconstruct.png"))

    print("=== layerize kmeans ===")
    result_k = svc.layerize_colors(source, num_colors=5, method="kmeans")
    print("project:", result_k["project"], "layers:", len(result_k["layers"]))

    print("=== export psd（含变换/调色/蒙板/阴影/文字层）===")
    layer_paths = [svc.asset_path(project, os.path.basename(i["url"])) for i in result["layers"]]
    spec = {
        "canvas": {"width": result["canvas"]["width"], "height": result["canvas"]["height"],
                   "background": "#ffffff"},
        "layers": [
            {"type": "image", "name": "背景层", "path": layer_paths[0], "x": 0, "y": 0,
             "w": result["canvas"]["width"], "h": result["canvas"]["height"], "opacity": 1},
            {"type": "image", "name": "主体层", "path": layer_paths[1], "x": 0, "y": 0,
             "w": result["canvas"]["width"], "h": result["canvas"]["height"],
             "opacity": 0.9, "blend": "normal",
             "adjust": {"brightness": 5, "contrast": 10, "saturate": 15, "hue": 10},
             "mask": {"strokes": [{"size": 60, "points": [[150, 350], [300, 450], [420, 360]]}]},
             "shadow": {"color": "#000000", "x": 10, "y": 14, "blur": 16}},
            {"type": "text", "name": "文本层 1", "text": "小米 MiSans 中文标题\nSecond line",
             "x": 120, "y": 1180, "font_size": 64, "color": "#1c1712", "font": "MiSans",
             "max_width": 700, "align": "left", "line_spacing": 1.3, "letter_spacing": 2,
             "shadow": {"color": "#000000", "x": 2, "y": 3, "blur": 6}},
            {"type": "text", "name": "文本层 2", "text": "回退字体测试 Fallback",
             "x": 120, "y": 1400, "font_size": 40, "color": "#8a5a2b", "font": "不存在的字体ABC"},
        ],
    }
    out = svc.export_psd(project, spec)
    print(json.dumps(out, ensure_ascii=False, indent=2))

    print("=== render preview ===")
    data, name = svc.render_preview(project, spec, scale=1.0)
    print("png bytes:", len(data), name)
    with open(os.path.join(tmp, "render.png"), "wb") as handle:
        handle.write(data)

    psd = os.path.join(svc.project_dir(project), "output.psd")
    with open(psd, "rb") as handle:
        head = handle.read(4)
    print("psd signature:", head, "size:", os.path.getsize(psd))
    print("tmp dir:", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
