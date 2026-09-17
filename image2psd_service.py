"""图片分层（图文分层编辑）后端服务。

复用 `vendor/bggg-creator-image2psd/scripts/image2psd.py` 的分层与 PSD 写出能力，
在其上补齐本产品需要的一层：

- 项目目录管理（沿用 bggg 的 `projects/YYYYMMDD_slug/` 约定，落在 output/image2psd 下）
- 系统字体库扫描与解析（识别不到用户系统字体时回退 MiSans）
- 图层栅格化：变换 / 调色 / 蒙板擦除 / 阴影 / 混合模式 / 不透明度
- 合成预览与 PSD 导出

本模块不依赖 FastAPI，纯逻辑，便于单独测试。
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.join(BASE_DIR, "vendor", "bggg-creator-image2psd")
BGGG_SCRIPT = os.path.join(VENDOR_DIR, "scripts", "image2psd.py")
WORK_ROOT = os.path.join(BASE_DIR, "output", "image2psd")
FONT_CACHE_FILE = os.path.join(BASE_DIR, "data", "image2psd_fonts.json")

# 回退字体族：用户系统里找不到目标字体时依次尝试
FALLBACK_FAMILIES = ("MiSans", "MiSans Normal", "MiSans Regular", "MiSans Medium")
# 再退一步时的 CJK 兜底（各家系统自带）
CJK_FALLBACK_HINTS = (
    "Noto Sans SC", "Source Han Sans", "Microsoft YaHei", "微软雅黑", "PingFang SC",
    "Heiti SC", "SimHei", "黑体", "SimSun", "宋体", "Noto Sans CJK SC",
)
FONT_EXTS = (".ttf", ".otf", ".ttc", ".otc")
# 字体扫描结果的缓存结构版本；判定逻辑变了就 +1，强制重建缓存
FONT_CACHE_VERSION = 2


# --------------------------------------------------------------------------
# bggg 脚本装载
# --------------------------------------------------------------------------

_bggg_module: Any = None


def bggg():
    """装载内置的 bggg-creator-image2psd 脚本。

    必须先把模块注册进 sys.modules —— 该脚本用了 `from __future__ import annotations`
    且带 @dataclass，dataclasses 解析字符串注解时要能在 sys.modules 里找到它，
    否则报 `AttributeError: 'NoneType' object has no attribute '__dict__'`。
    """
    global _bggg_module
    if _bggg_module is not None:
        return _bggg_module
    name = "bggg_image2psd"
    if name in sys.modules:
        _bggg_module = sys.modules[name]
        return _bggg_module
    if not os.path.isfile(BGGG_SCRIPT):
        raise RuntimeError(f"内置分层脚本缺失：{BGGG_SCRIPT}")
    spec = importlib.util.spec_from_file_location(name, BGGG_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("内置分层脚本无法加载")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _bggg_module = module
    return module


def bggg_info() -> dict:
    return {
        "name": "bggg-creator-image2psd",
        "path": BGGG_SCRIPT,
        "available": os.path.isfile(BGGG_SCRIPT),
        "numpy": getattr(np, "__version__", ""),
    }


# --------------------------------------------------------------------------
# 字体库
# --------------------------------------------------------------------------

_font_cache: dict[str, Any] | None = None


def _font_dirs() -> list[str]:
    dirs: list[str] = []
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR") or r"C:\Windows"
        dirs.append(os.path.join(windir, "Fonts"))
        local = os.environ.get("LOCALAPPDATA") or ""
        if local:
            dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    elif sys.platform == "darwin":
        dirs += ["/System/Library/Fonts", "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
    else:
        dirs += ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
                 os.path.expanduser("~/.local/share/fonts")]
    return [d for d in dirs if os.path.isdir(d)]


def _read_font_family(path: str, index: int = 0) -> tuple[str, str] | None:
    try:
        font = ImageFont.truetype(path, 12, index=index)
        family, style = font.getname()
        return (str(family or "").strip(), str(style or "").strip())
    except Exception:
        return None


def _supports_cjk(path: str, index: int = 0) -> bool:
    """判断字体是否真的带中文字形。

    不能只看 `getmask('中')` 有没有内容——缺字时 FreeType 会回退到 .notdef（空心方框），
    一样有 bbox。所以拿私用区的字符做对照：字形与 .notdef 完全一致说明这个字是缺的。
    """
    try:
        font = ImageFont.truetype(path, 24, index=index)

        def signature(char: str) -> tuple[bytes, tuple[int, int]]:
            mask = font.getmask(char, mode="L")
            return bytes(mask), tuple(mask.size)  # type: ignore[arg-type]

        target = signature("\u4e2d")
        if not any(target[0]):
            return False
        for probe in ("\ue000", "\uf8ff"):
            if signature(probe) == target:
                return False
        return True
    except Exception:
        return False


def _ttc_count(path: str) -> int:
    """粗略探测 .ttc/.otc 内含几个字面（Windows 上多为 1~2 个）。"""
    try:
        with open(path, "rb") as handle:
            head = handle.read(12)
        if len(head) < 12 or head[:4] != b"ttcf":
            return 1
        return max(1, min(16, int.from_bytes(head[8:12], "big")))
    except Exception:
        return 1


def scan_fonts(force: bool = False) -> list[dict]:
    """扫描用户字体库，返回可用的字体族列表（带缓存）。"""
    global _font_cache
    if _font_cache is not None and not force:
        return _font_cache["fonts"]

    signature: list[tuple[str, float]] = [("__version__", float(FONT_CACHE_VERSION))]
    for folder in _font_dirs():
        try:
            signature.append((folder, os.path.getmtime(folder)))
        except OSError:
            continue
    cache_key = json.dumps(signature, ensure_ascii=False)

    if not force and os.path.isfile(FONT_CACHE_FILE):
        try:
            with open(FONT_CACHE_FILE, "r", encoding="utf-8") as handle:
                cached = json.load(handle)
            if cached.get("key") == cache_key and cached.get("fonts"):
                _font_cache = {"fonts": cached["fonts"], "key": cache_key}
                return _font_cache["fonts"]
        except Exception:
            pass

    fonts: list[dict] = []
    seen: set[str] = set()
    for folder in _font_dirs():
        for root, dirnames, filenames in os.walk(folder):
            # 只下探一层，字体目录一般不会更深
            if root != folder:
                dirnames[:] = []
            for filename in sorted(filenames):
                ext = os.path.splitext(filename)[1].lower()
                if ext not in FONT_EXTS:
                    continue
                path = os.path.join(root, filename)
                if path in seen:
                    continue
                seen.add(path)
                for index in range(_ttc_count(path) if ext in (".ttc", ".otc") else 1):
                    named = _read_font_family(path, index)
                    if not named:
                        continue
                    family, style = named
                    if not family:
                        continue
                    fonts.append({
                        "family": family,
                        "style": style,
                        "file": path,
                        "name": os.path.basename(path),
                        "index": index,
                        "ext": ext,
                        "cjk": _supports_cjk(path, index),
                    })
    # 同族去重：保留字重最接近 Regular 的一条
    def weight_rank(item: dict) -> int:
        style = item["style"].lower()
        if "regular" in style or "normal" in style or not style:
            return 0
        if "medium" in style:
            return 1
        if "book" in style:
            return 2
        return 3

    best: dict[str, dict] = {}
    for item in fonts:
        key = item["family"].lower()
        if key not in best or weight_rank(item) < weight_rank(best[key]):
            best[key] = item
    result = sorted(best.values(), key=lambda item: (not item["cjk"], item["family"].lower()))
    _font_cache = {"fonts": result, "key": cache_key}
    try:
        os.makedirs(os.path.dirname(FONT_CACHE_FILE), exist_ok=True)
        with open(FONT_CACHE_FILE, "w", encoding="utf-8") as handle:
            json.dump({"key": cache_key, "fonts": result}, handle, ensure_ascii=False)
    except Exception:
        pass
    return result


def default_font_family() -> str:
    fonts = scan_fonts()
    for hint in FALLBACK_FAMILIES:
        for item in fonts:
            if item["family"].lower() == hint.lower():
                return item["family"]
    for item in fonts:
        if item["family"].lower().startswith("misans"):
            return item["family"]
    for hint in CJK_FALLBACK_HINTS:
        for item in fonts:
            if item["family"].lower() == hint.lower():
                return item["family"]
    for item in fonts:
        if item["cjk"]:
            return item["family"]
    return fonts[0]["family"] if fonts else ""


def resolve_font(family: str) -> dict:
    """解析字体族到具体字体文件，附带回退链结果。"""
    fonts = scan_fonts()
    if not fonts:
        return {"family": family or "", "path": "", "used": "", "fallback": False, "reason": "no-fonts"}
    wanted = (family or "").strip().lower()
    if wanted:
        for item in fonts:
            if item["family"].lower() == wanted:
                return {"family": item["family"], "path": item["file"], "used": item["family"],
                        "fallback": False, "reason": "exact"}
        for item in fonts:
            if wanted in item["family"].lower():
                return {"family": item["family"], "path": item["file"], "used": item["family"],
                        "fallback": True, "reason": "fuzzy"}
    for hint in FALLBACK_FAMILIES:
        for item in fonts:
            if item["family"].lower() == hint.lower():
                return {"family": item["family"], "path": item["file"], "used": item["family"],
                        "fallback": bool(wanted), "reason": "misans"}
    for hint in CJK_FALLBACK_HINTS:
        for item in fonts:
            if item["family"].lower() == hint.lower():
                return {"family": item["family"], "path": item["file"], "used": item["family"],
                        "fallback": True, "reason": "cjk"}
    item = fonts[0]
    return {"family": item["family"], "path": item["file"], "used": item["family"],
            "fallback": True, "reason": "first"}


# --------------------------------------------------------------------------
# 项目目录
# --------------------------------------------------------------------------

def _slugify(value: str, fallback: str = "layer") -> str:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", str(value or "")).strip("-").lower()
    text = text[:32]
    return text or fallback


def create_project(source_name: str = "") -> tuple[str, str]:
    stamp = time.strftime("%Y%m%d")
    slug = _slugify(os.path.splitext(os.path.basename(source_name or ""))[0], "layer")
    name = f"{stamp}_{slug}"
    path = os.path.join(WORK_ROOT, name)
    suffix = 1
    while os.path.exists(path):
        suffix += 1
        name = f"{stamp}_{slug}-{suffix}"
        path = os.path.join(WORK_ROOT, name)
    os.makedirs(path, exist_ok=True)
    return name, path


def project_dir(project: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z._\u4e00-\u9fff-]", "", str(project or ""))
    if not safe or safe in (".", ".."):
        raise ValueError("非法项目名")
    path = os.path.abspath(os.path.join(WORK_ROOT, safe))
    if os.path.commonpath([os.path.abspath(WORK_ROOT), path]) != os.path.abspath(WORK_ROOT):
        raise ValueError("非法项目名")
    return path


def asset_url(project: str, filename: str) -> str:
    return f"/api/image2psd/asset/{project}/{filename}"


def asset_path(project: str, filename: str) -> str:
    safe = os.path.basename(str(filename or ""))
    if not safe:
        raise ValueError("非法文件名")
    return os.path.join(project_dir(project), safe)


# --------------------------------------------------------------------------
# 分层
# --------------------------------------------------------------------------

def _write_layer_pngs(layers: Sequence[Any], folder: str) -> list[dict]:
    os.makedirs(folder, exist_ok=True)
    written: list[dict] = []
    for idx, layer in enumerate(layers, start=1):
        filename = f"layer_{idx:02d}.png"
        layer.image.convert("RGBA").save(os.path.join(folder, filename))
        written.append({"index": idx, "name": layer.name, "filename": filename})
    return written


def _alpha_pixels(image: Image.Image) -> int:
    return int(np.count_nonzero(np.asarray(image.getchannel("A"))))


def layerize_colors(
    source_path: str,
    *,
    num_colors: int = 8,
    method: str = "quantize",
    ignore_color: str | None = None,
    ignore_tolerance: float = 24.0,
    project: str | None = None,
) -> dict:
    """按颜色聚类把一张平面图拆成多个全画布透明图层。

    直接复用 bggg 脚本的 quantized_labels / kmeans_labels / Layer / write_psd。
    """
    mod = bggg()
    source_path = os.path.abspath(source_path)
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"源图不存在：{source_path}")

    project_name, folder = (project, project_dir(project)) if project else create_project(os.path.basename(source_path))
    os.makedirs(folder, exist_ok=True)

    source = mod.image_from_path(Path(source_path))
    original_name = "original_reference.png"
    source.convert("RGBA").save(os.path.join(folder, original_name))

    rgba = np.asarray(source.convert("RGBA"), dtype=np.uint8)
    rgb = source.convert("RGB")
    rgb_arr = np.asarray(rgb, dtype=np.uint8)

    colors = max(2, min(32, int(num_colors or 8)))
    if str(method).lower() == "kmeans":
        labels, palette = mod.kmeans_labels(rgb_arr, colors)
    else:
        labels, palette = mod.quantized_labels(rgb, colors)

    ignore = mod.parse_color(ignore_color) if ignore_color else None
    alpha_source = rgba[:, :, 3]
    layers: list[Any] = []
    for idx, color in enumerate(palette):
        if mod.should_ignore_color(color, ignore, float(ignore_tolerance)):
            continue
        mask = labels == idx
        if not np.any(mask):
            continue
        arr = np.zeros_like(rgba)
        arr[:, :, :3][mask] = rgba[:, :, :3][mask]
        arr[:, :, 3][mask] = alpha_source[mask]
        hex_color = mod.color_hex(color)
        layers.append(mod.Layer(name=f"颜色层 {idx + 1} {hex_color}", image=Image.fromarray(arr, "RGBA")))

    if not layers:
        raise RuntimeError("颜色聚类没有产出任何图层，请调整颜色数")

    # 小面积在上：面积大的先画（背景类），细节层后画
    layers.sort(key=lambda item: _alpha_pixels(item.image), reverse=True)

    written = _write_layer_pngs(layers, folder)
    total = float(source.width * source.height) or 1.0
    items = []
    for meta, layer in zip(written, layers):
        pixels = _alpha_pixels(layer.image)
        match = re.search(r"#([0-9A-Fa-f]{6})", layer.name)
        items.append({
            "name": layer.name,
            "url": asset_url(project_name, meta["filename"]),
            "width": source.width,
            "height": source.height,
            "color": f"#{match.group(1)}" if match else "",
            "coverage": round(pixels / total, 4),
        })

    return {
        "project": project_name,
        "mode": "colors",
        "canvas": {"width": source.width, "height": source.height},
        "source": asset_url(project_name, original_name),
        "layers": items,
        "generated_at": int(time.time() * 1000),
    }


def layerize_regions(
    source_path: str,
    regions: Sequence[dict],
    *,
    project: str | None = None,
    include_source: bool = True,
) -> dict:
    """按给定的矩形区域把平面图裁成多个全画布透明图层（语义/区域拆层的近似实现）。

    每个区域输出与原图同尺寸的透明 PNG，区域之外全透明，保证 Photoshop 里按 (0,0)
    叠放即可对齐——这正是 bggg 技能里推荐的“保留相对位置”做法。
    """
    mod = bggg()
    source_path = os.path.abspath(source_path)
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"源图不存在：{source_path}")

    project_name, folder = (project, project_dir(project)) if project else create_project(os.path.basename(source_path))
    os.makedirs(folder, exist_ok=True)

    source = mod.image_from_path(Path(source_path)).convert("RGBA")
    original_name = "original_reference.png"
    source.save(os.path.join(folder, original_name))
    width, height = source.size

    layers: list[Any] = []
    if include_source:
        background = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        background.alpha_composite(source)
        layers.append(mod.Layer(name="原图", image=background))

    for idx, region in enumerate(regions or [], start=1):
        try:
            x = int(round(float(region.get("x", 0))))
            y = int(round(float(region.get("y", 0))))
            w = int(round(float(region.get("width", 0))))
            h = int(round(float(region.get("height", 0))))
        except (TypeError, ValueError):
            continue
        x = max(0, min(width - 1, x))
        y = max(0, min(height - 1, y))
        w = max(1, min(width - x, w))
        h = max(1, min(height - y, h))
        name = str(region.get("name") or f"区域 {idx}").strip()[:60] or f"区域 {idx}"
        piece = source.crop((x, y, x + w, y + h))
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.alpha_composite(piece, (x, y))
        layers.append(mod.Layer(name=name, image=canvas))

    if not layers:
        raise RuntimeError("没有可用的区域，无法分层")

    written = _write_layer_pngs(layers, folder)
    items = []
    for meta, layer in zip(written, layers):
        items.append({
            "name": layer.name,
            "url": asset_url(project_name, meta["filename"]),
            "width": width,
            "height": height,
        })

    return {
        "project": project_name,
        "mode": "regions",
        "canvas": {"width": width, "height": height},
        "source": asset_url(project_name, original_name),
        "layers": items,
        "generated_at": int(time.time() * 1000),
    }


# --------------------------------------------------------------------------
# 图层栅格化
# --------------------------------------------------------------------------

def _hex_to_rgb(value: str | None, default: tuple[int, int, int] = (0, 0, 0)) -> tuple[int, int, int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return default
    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return default


def _paste_over(dest: Image.Image, src: Image.Image, x: int, y: int) -> None:
    """把 src 以 source-over 方式叠到 dest 的 (x, y)，允许越界（自动裁切）。"""
    sx0 = max(0, -x)
    sy0 = max(0, -y)
    dx0 = max(0, x)
    dy0 = max(0, y)
    width = min(src.width - sx0, dest.width - dx0)
    height = min(src.height - sy0, dest.height - dy0)
    if width <= 0 or height <= 0:
        return
    dest.alpha_composite(src.crop((sx0, sy0, sx0 + width, sy0 + height)), (dx0, dy0))


def _hue_rotate(image: Image.Image, degrees: float) -> Image.Image:
    if not degrees:
        return image
    hsv = image.convert("HSV")
    hue, sat, val = hsv.split()
    shift = int(round((degrees % 360.0) / 360.0 * 255.0)) % 256
    hue = hue.point(lambda value: (value + shift) % 256)
    return Image.merge("HSV", (hue, sat, val)).convert("RGB")


def _adjust_rgba(image: Image.Image, adjust: dict | None) -> Image.Image:
    adjust = adjust or {}
    brightness = float(adjust.get("brightness") or 0)
    contrast = float(adjust.get("contrast") or 0)
    saturate = float(adjust.get("saturate") or 0)
    hue = float(adjust.get("hue") or 0)
    if not any((brightness, contrast, saturate, hue)):
        return image
    alpha = image.getchannel("A")
    rgb = image.convert("RGB")
    if brightness:
        rgb = ImageEnhance.Brightness(rgb).enhance(max(0.0, 1.0 + brightness / 100.0))
    if contrast:
        rgb = ImageEnhance.Contrast(rgb).enhance(max(0.0, 1.0 + contrast / 100.0))
    if saturate:
        rgb = ImageEnhance.Color(rgb).enhance(max(0.0, 1.0 + saturate / 100.0))
    if hue:
        rgb = _hue_rotate(rgb, hue)
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def _apply_mask_strokes(image: Image.Image, strokes: Sequence[dict] | None, canvas: tuple[int, int]) -> Image.Image:
    """蒙板擦除：把笔画覆盖到的区域 alpha 置 0。

    笔画坐标是「图层局部坐标」（左上角为原点、单位与画布像素一致），
    这样蒙板会跟着图层一起移动/旋转，和前端预览的语义保持一致。
    支持两种笔画：`{type:'rect', x, y, w, h}` 与 `{size, points:[[x,y], ...]}`。
    """
    if not strokes:
        return image
    mask = Image.new("L", canvas, 255)
    draw = ImageDraw.Draw(mask)
    painted = False
    for stroke in strokes:
        if not isinstance(stroke, dict):
            continue
        if str(stroke.get("type") or "") == "rect":
            try:
                rx = float(stroke.get("x") or 0)
                ry = float(stroke.get("y") or 0)
                rw = float(stroke.get("w") or stroke.get("width") or 0)
                rh = float(stroke.get("h") or stroke.get("height") or 0)
            except (TypeError, ValueError):
                continue
            if rw <= 0 or rh <= 0:
                continue
            draw.rectangle([rx, ry, rx + rw, ry + rh], fill=0)
            painted = True
            continue
        points: list[tuple[float, float]] = []
        for point in stroke.get("points") or []:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                try:
                    points.append((float(point[0]), float(point[1])))
                except (TypeError, ValueError):
                    continue
        if not points:
            continue
        try:
            size = max(1, int(round(float(stroke.get("size") or 24))))
        except (TypeError, ValueError):
            size = 24
        radius = size / 2.0
        if len(points) > 1:
            draw.line(points, fill=0, width=size, joint="curve")
        for px, py in points:
            draw.ellipse([px - radius, py - radius, px + radius, py + radius], fill=0)
        painted = True
    if not painted:
        return image
    alpha = ImageChops.multiply(image.getchannel("A"), mask)
    out = image.copy()
    out.putalpha(alpha)
    return out


def _apply_shadow(image: Image.Image, shadow: dict | None) -> Image.Image:
    shadow = shadow or {}
    try:
        offset_x = int(round(float(shadow.get("x") or 0)))
        offset_y = int(round(float(shadow.get("y") or 0)))
        blur = float(shadow.get("blur") or 0)
    except (TypeError, ValueError):
        return image
    if not any((offset_x, offset_y, blur)):
        return image
    color = _hex_to_rgb(shadow.get("color"), (0, 0, 0))
    alpha = image.getchannel("A")
    tint = Image.new("RGBA", image.size, (*color, 255))
    silhouette = Image.composite(tint, Image.new("RGBA", image.size, (0, 0, 0, 0)), alpha)
    if blur > 0:
        silhouette = silhouette.filter(ImageFilter.GaussianBlur(blur / 2.0))
    out = Image.new("RGBA", image.size, (0, 0, 0, 0))
    _paste_over(out, silhouette, offset_x, offset_y)
    _paste_over(out, image, 0, 0)
    return out


def _draw_spaced_text(draw: ImageDraw.ImageDraw, position: tuple[float, float], text: str,
                      font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
                      fill: tuple[int, int, int, int], spacing: float) -> None:
    if not spacing:
        draw.text(position, text, font=font, fill=fill)
        return
    x, y = position
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        try:
            advance = draw.textlength(char, font=font)
        except Exception:
            advance = font.size if hasattr(font, "size") else 8
        x += advance + spacing


def _measure_spaced(draw: ImageDraw.ImageDraw, text: str,
                    font: ImageFont.FreeTypeFont | ImageFont.ImageFont, spacing: float) -> float:
    if not spacing:
        try:
            return float(draw.textlength(text, font=font))
        except Exception:
            box = draw.textbbox((0, 0), text, font=font)
            return float(box[2] - box[0])
    total = 0.0
    for char in text:
        try:
            total += float(draw.textlength(char, font=font))
        except Exception:
            total += font.size if hasattr(font, "size") else 8
        total += spacing
    return max(0.0, total - spacing)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int | None, spacing: float) -> list[str]:
    raw_lines = text.splitlines() or [text]
    if not max_width:
        return raw_lines
    lines: list[str] = []
    for raw in raw_lines:
        if not raw:
            lines.append("")
            continue
        # 中文没有空格，按字符累积换行；英文优先按空格断
        buffer = ""
        for token in re.findall(r"\s+|[^\s]+", raw):
            trial = buffer + token
            if buffer and _measure_spaced(draw, trial.strip(), font, spacing) > max_width:
                lines.append(buffer.strip())
                buffer = token.lstrip()
            else:
                buffer = trial
        if buffer.strip():
            lines.append(buffer.strip())
    return lines or [text]


def render_text_layer(spec: dict, canvas: tuple[int, int]) -> tuple[Image.Image, dict]:
    family = str(spec.get("font") or "")
    resolved = resolve_font(family)
    resolved["requested"] = family
    size = max(1, int(round(float(spec.get("font_size") or 48))))
    font: Any
    if resolved.get("path"):
        try:
            font = ImageFont.truetype(resolved["path"], size)
        except Exception:
            font = ImageFont.load_default()
    else:
        font = ImageFont.load_default()

    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    draw = ImageDraw.Draw(out)
    text = str(spec.get("text") or "")
    color = _hex_to_rgb(spec.get("color") or "#111111", (17, 17, 17))
    fill = (*color, 255)
    x = float(spec.get("x") or 0)
    y = float(spec.get("y") or 0)
    max_width_raw = spec.get("max_width")
    max_width = int(float(max_width_raw)) if max_width_raw else None
    line_spacing = float(spec.get("line_spacing") or 1.25)
    letter_spacing = float(spec.get("letter_spacing") or 0)
    align = str(spec.get("align") or "left").lower()

    lines = _wrap_text(draw, text, font, max_width, letter_spacing)
    line_height = max(1, round(size * line_spacing))
    for index, line in enumerate(lines):
        line_width = _measure_spaced(draw, line, font, letter_spacing)
        tx = x
        if max_width and align == "center":
            tx = x + (max_width - line_width) / 2.0
        elif max_width and align == "right":
            tx = x + max_width - line_width
        _draw_spaced_text(draw, (tx, y + index * line_height), line, font, fill, letter_spacing)

    return out, resolved


def render_image_layer(spec: dict, canvas: tuple[int, int]) -> Image.Image:
    path = str(spec.get("path") or "")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"图层文件不存在：{path}")
    image = Image.open(path).convert("RGBA")
    try:
        width = int(round(float(spec.get("w") or image.width)))
        height = int(round(float(spec.get("h") or image.height)))
    except (TypeError, ValueError):
        width, height = image.width, image.height
    width = max(1, width)
    height = max(1, height)
    if (width, height) != image.size:
        image = image.resize((width, height), Image.LANCZOS)

    image = _adjust_rgba(image, spec.get("adjust") if isinstance(spec.get("adjust"), dict) else {})

    # 蒙板在图层局部坐标系里擦除，之后再旋转/摆放——这样蒙板跟着图层一起动。
    mask = spec.get("mask") if isinstance(spec.get("mask"), dict) else {}
    image = _apply_mask_strokes(image, mask.get("strokes") if isinstance(mask, dict) else None, image.size)

    try:
        rotation = float(spec.get("rotation") or 0)
    except (TypeError, ValueError):
        rotation = 0.0
    x = float(spec.get("x") or 0)
    y = float(spec.get("y") or 0)
    if rotation:
        rotated = image.rotate(-rotation, expand=True, resample=Image.BICUBIC)
        center_x = x + width / 2.0
        center_y = y + height / 2.0
        px = int(round(center_x - rotated.width / 2.0))
        py = int(round(center_y - rotated.height / 2.0))
        image = rotated
    else:
        px, py = int(round(x)), int(round(y))

    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    _paste_over(out, image, px, py)
    return out


def build_layer(spec: dict, canvas: tuple[int, int]) -> tuple[Any, dict]:
    mod = bggg()
    layer_type = str(spec.get("type") or "image").lower()
    name = str(spec.get("name") or ("文本层" if layer_type == "text" else "图像层"))
    font_info: dict = {}
    if layer_type == "text":
        image, font_info = render_text_layer(spec, canvas)
    else:
        image = render_image_layer(spec, canvas)

    image = _apply_shadow(image, spec.get("shadow") if isinstance(spec.get("shadow"), dict) else {})
    try:
        opacity = max(0.0, min(1.0, float(spec.get("opacity", 1) or 0)))
    except (TypeError, ValueError):
        opacity = 1.0
    if opacity < 1.0:
        image = mod.apply_opacity(image, opacity)
    blend = str(spec.get("blend") or spec.get("blend_mode") or "normal").lower()
    if blend not in ("normal", "multiply", "screen", "overlay"):
        blend = "normal"
    return mod.Layer(name=name, image=image, blend_mode=blend, opacity=opacity), font_info


_BLEND_KEYS = ("normal", "multiply", "screen", "overlay")


def composite_layers(layers: Sequence[Any], background: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """按混合模式合成。bggg 自带的 composite_layers 只做 alpha_composite，会丢掉混合模式。"""
    if not layers:
        raise RuntimeError("没有可合成的图层")
    canvas = layers[0].image.size
    comp = Image.new("RGBA", canvas, (*background, 255))
    for layer in layers:
        src = layer.image.convert("RGBA")
        mode = str(getattr(layer, "blend_mode", "normal") or "normal").lower()
        if mode not in _BLEND_KEYS or mode == "normal":
            comp.alpha_composite(src)
            continue
        base = np.asarray(comp, dtype=np.float32) / 255.0
        top = np.asarray(src, dtype=np.float32) / 255.0
        alpha = top[:, :, 3:4]
        if mode == "multiply":
            blended = base[:, :, :3] * top[:, :, :3]
        elif mode == "screen":
            blended = 1.0 - (1.0 - base[:, :, :3]) * (1.0 - top[:, :, :3])
        else:  # overlay
            low = base[:, :, :3] <= 0.5
            blended = np.where(low, 2.0 * base[:, :, :3] * top[:, :, :3],
                               1.0 - 2.0 * (1.0 - base[:, :, :3]) * (1.0 - top[:, :, :3]))
        rgb = base[:, :, :3] * (1.0 - alpha) + blended * alpha
        out = np.concatenate([rgb, base[:, :, 3:4]], axis=2)
        comp = Image.fromarray((np.clip(out, 0.0, 1.0) * 255.0).astype(np.uint8), "RGBA")
    return comp


# --------------------------------------------------------------------------
# 导出
# --------------------------------------------------------------------------

def _process_notes(project_name: str, layers: Sequence[Any], summary: dict, warnings: Sequence[str]) -> str:
    lines = [
        f"# {project_name} 分层处理记录",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 工具：bggg-creator-image2psd（内置脚本 `{os.path.relpath(BGGG_SCRIPT, BASE_DIR)}`）",
        f"- 画布：{summary.get('width')} × {summary.get('height')}",
        f"- 图层数：{len(layers)}",
        "",
        "## 图层（自下而上）",
        "",
    ]
    for index, layer in enumerate(layers, start=1):
        lines.append(f"{index}. {layer.name}（混合模式 {getattr(layer, 'blend_mode', 'normal')}）")
    lines += ["", "## 验证", "", f"- PSD：{summary.get('output')}", f"- 预览：{summary.get('preview')}",
              f"- 文件大小：{summary.get('bytes')} 字节", ""]
    if warnings:
        lines += ["## 已知限制", ""] + [f"- {item}" for item in warnings] + [""]
    return "\n".join(lines)


def export_psd(project: str, spec: dict) -> dict:
    """把编辑器状态导出成 PSD。spec.layers 为自下而上的图层数组。"""
    mod = bggg()
    folder = project_dir(project)
    os.makedirs(folder, exist_ok=True)

    canvas_spec = spec.get("canvas") if isinstance(spec.get("canvas"), dict) else {}
    try:
        width = int(round(float(canvas_spec.get("width") or 0)))
        height = int(round(float(canvas_spec.get("height") or 0)))
    except (TypeError, ValueError):
        width = height = 0
    if width <= 0 or height <= 0:
        raise ValueError("画布尺寸无效")
    canvas = (width, height)

    background = _hex_to_rgb(canvas_spec.get("background") or "#ffffff", (255, 255, 255))

    raw_layers = spec.get("layers")
    if not isinstance(raw_layers, list) or not raw_layers:
        raise ValueError("没有可导出的图层")

    layers: list[Any] = []
    warnings: list[str] = []
    # warning_codes 与 warnings 一一对应（顺序一致）：前端按 code 取词条做本地化，
    # warnings 里的中文原文留给 process_notes.md 与老客户端兜底。
    warning_codes: list[dict] = []
    font_fallbacks: list[dict] = []
    for item in raw_layers:
        if not isinstance(item, dict):
            continue
        if item.get("visible") is False:
            continue
        layer, font_info = build_layer(item, canvas)
        if font_info and font_info.get("fallback"):
            font_fallbacks.append({
                "layer": layer.name,
                "requested": font_info.get("requested") or font_info.get("family") or "",
                "used": font_info.get("used") or "",
                "reason": font_info.get("reason") or "",
            })
        if _alpha_pixels(layer.image) == 0:
            warnings.append(f"图层「{layer.name}」内容为空，已跳过")
            warning_codes.append({"code": "empty_layer", "layer": layer.name})
            continue
        layers.append(layer)

    if not layers:
        raise ValueError("所有图层都是空的，无法导出 PSD")

    output_path = os.path.join(folder, "output.psd")
    preview_path = os.path.join(folder, "output.preview.png")
    summary = mod.write_psd(__import__("pathlib").Path(output_path), layers, background)
    composite_layers(layers, background).convert("RGB").save(preview_path)
    summary["preview"] = preview_path

    layer_dir = os.path.join(folder, "psd_full_canvas_layers")
    mod.save_layer_pngs(layers, __import__("pathlib").Path(layer_dir))

    has_text = any(str(item.get("type") or "").lower() == "text" for item in raw_layers if isinstance(item, dict))
    if has_text:
        warnings.append("文字层在 PSD 中是栅格图层（bggg 脚本不写 Photoshop 可编辑文字对象），"
                        "需要改字请回到分层编辑器里修改后重新导出")
        warning_codes.append({"code": "text_raster"})

    manifest = {
        "canvas": {"width": width, "height": height,
                   "composite_background": "#%02x%02x%02x" % background},
        "output": "output.psd",
        "preview": "output.preview.png",
        "save_layers_dir": "psd_full_canvas_layers",
        "layers": [
            {k: v for k, v in {
                "name": layer.name,
                "blend_mode": layer.blend_mode,
                "opacity": getattr(layer, "opacity", 1.0),
            }.items() if v is not None}
            for layer in layers
        ],
    }
    try:
        with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
        with open(os.path.join(folder, "process_notes.md"), "w", encoding="utf-8") as handle:
            handle.write(_process_notes(project, layers, summary, warnings))
    except Exception:
        pass

    return {
        "project": project,
        "psd_url": asset_url(project, "output.psd"),
        "preview_url": asset_url(project, "output.preview.png"),
        "layer_count": len(layers),
        "width": width,
        "height": height,
        "bytes": os.path.getsize(output_path),
        "layers": [{"name": layer.name, "blend_mode": layer.blend_mode} for layer in layers],
        "warnings": warnings,
        "warning_codes": warning_codes,
        "font_fallbacks": font_fallbacks,
    }


def render_preview(project: str, spec: dict, scale: float = 1.0) -> tuple[bytes, str]:
    """后端渲染合成图（PNG 字节流），用于导出图像时与 PSD 保持同一套栅格化逻辑。"""
    folder = project_dir(project)
    canvas_spec = spec.get("canvas") if isinstance(spec.get("canvas"), dict) else {}
    width = int(round(float(canvas_spec.get("width") or 0)))
    height = int(round(float(canvas_spec.get("height") or 0)))
    if width <= 0 or height <= 0:
        raise ValueError("画布尺寸无效")
    canvas = (width, height)
    background = _hex_to_rgb(canvas_spec.get("background") or "#ffffff", (255, 255, 255))
    raw_layers = spec.get("layers")
    if not isinstance(raw_layers, list) or not raw_layers:
        raise ValueError("没有可导出的图层")

    layers: list[Any] = []
    for item in raw_layers:
        if not isinstance(item, dict) or item.get("visible") is False:
            continue
        layer, _ = build_layer(item, canvas)
        if _alpha_pixels(layer.image) == 0:
            continue
        layers.append(layer)
    if not layers:
        raise ValueError("所有图层都是空的，无法渲染")

    image = composite_layers(layers, background).convert("RGB")
    scale = max(0.05, min(8.0, float(scale or 1.0)))
    if abs(scale - 1.0) > 0.001:
        image = image.resize((max(1, int(round(width * scale))), max(1, int(round(height * scale)))), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), f"{project}-{int(round(scale * 100))}x.png"


def project_meta(project: str) -> dict:
    folder = project_dir(project)
    if not os.path.isdir(folder):
        raise FileNotFoundError("项目不存在")
    files = sorted(os.listdir(folder))
    return {
        "project": project,
        "dir": folder,
        "files": files,
        "psd": os.path.isfile(os.path.join(folder, "output.psd")),
        "preview": os.path.isfile(os.path.join(folder, "output.preview.png")),
    }
