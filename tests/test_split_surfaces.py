# -*- coding: utf-8 -*-
"""clean plate（表面分区 / 同表面取样 / 按表面最小算法）的像素级测试。

对应方案《非纯色背景重建与可复用背景资产方案-20261016》§1/§3/§4/§5/§8。
全部零模型调用。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageChops, ImageDraw, ImageStat

from backend.split_surfaces import (
    REGION_SOURCES, SURFACE_TYPES, build_clean_plate, classify_surface,
    segment_surfaces, surface_summary,
)


def _base_panel(size=(240, 160)):
    """浅灰底 + 一块深色面板：**跨表面**场景。"""
    img = Image.new("RGBA", size, (232, 230, 226, 255))
    ImageDraw.Draw(img).rectangle((120, 20, 220, 140), fill=(28, 30, 36, 255))
    hole = Image.new("L", size, 0)
    ImageDraw.Draw(hole).rectangle((100, 60, 180, 110), fill=255)
    return img, hole


def _gradient(size=(300, 220)):
    img = Image.new("RGBA", size)
    px = img.load()
    for y in range(size[1]):
        for x in range(size[0]):
            t = (x + 0.6 * y) / 480.0
            px[x, y] = (int(36 + 190 * t), int(60 + 160 * t), int(110 + 130 * t), 255)
    hole = Image.new("L", size, 0)
    ImageDraw.Draw(hole).rectangle((110, 70, 200, 150), fill=255)
    return img, hole


def _dotgrid(size=(240, 180), step=16, dot=4):
    img = Image.new("RGBA", size, (238, 236, 232, 255))
    d = ImageDraw.Draw(img)
    for i in range(6, size[0], step):
        for j in range(6, size[1], step):
            d.rectangle((i, j, i + dot - 1, j + dot - 1), fill=(198, 196, 190, 255))
    hole = Image.new("L", size, 0)
    ImageDraw.Draw(hole).rectangle((70, 50, 170, 130), fill=255)
    return img, hole


def _dark_count(img, box):
    return sum(1 for y in range(box[1], box[3]) for x in range(box[0], box[2])
               if img.getpixel((x, y))[0] < 225)


class SurfaceSamplingTests(unittest.TestCase):
    def test_hole_spanning_two_surfaces_does_not_mix_colors(self):
        """🚨 本方案的核心：洞横跨两种表面时，两侧必须各取**自己那种表面**的像素。

        旧实现把整个洞当一块补，实测两侧都被填成 (230,230,230) —— 这就是
        「大块突兀补丁 / 跨表面取样」的根因。
        """
        img, hole = _base_panel()
        plate, regions, meta = build_clean_plate(img, hole)
        left = plate.getpixel((105, 85))[:3]
        right = plate.getpixel((175, 85))[:3]
        self.assertLess(max(abs(left[i] - (232, 230, 226)[i]) for i in range(3)), 12, left)
        self.assertLess(max(abs(right[i] - (28, 30, 36)[i]) for i in range(3)), 12, right)
        self.assertGreater(max(abs(left[i] - right[i]) for i in range(3)), 100)
        self.assertEqual(meta["outsideChanged"], 0)
        self.assertGreater(meta["surfaceCount"], 1)
        # 均匀表面走中位色（参数化、与距离无关），不是从远处复制像素
        self.assertTrue(all(r["source"] in ("fitted", "copied") for r in regions if r["kind"] == "rebuilt"))

    def test_outside_write_mask_is_pixel_identical(self):
        for img, hole in (_base_panel(), _gradient(), _dotgrid()):
            plate, _regions, meta = build_clean_plate(img, hole)
            self.assertEqual(meta["outsideChanged"], 0)
            diff = ImageChops.difference(plate.convert("RGB"), img.convert("RGB")).convert("L")
            outside = ImageChops.multiply(diff, ImageChops.invert(hole))
            self.assertEqual(sum(outside.histogram()[1:]), 0)

    def test_gradient_is_fitted_not_flattened(self):
        img, hole = _gradient()
        plate, regions, meta = build_clean_plate(img, hole)
        kinds = {r["surfaceType"] for r in regions if r["kind"] == "rebuilt"}
        self.assertIn("gradient", kinds, kinds)
        self.assertTrue(any(r["source"] == "fitted" for r in regions))
        diff = ImageChops.multiply(
            ImageChops.difference(plate.convert("RGB"), img.convert("RGB")).convert("L"), hole)
        self.assertLess(ImageStat.Stat(diff, hole).mean[0], 1.0)
        self.assertEqual(meta["unknownPixels"], 0)

    def test_grid_texture_is_phase_aligned_not_smeared(self):
        """点阵纹理必须按周期相位对齐复制 —— 抹平纹理等于把背景毁掉。"""
        img, hole = _dotgrid()
        plate, regions, meta = build_clean_plate(img, hole)
        self.assertTrue(any(r["surfaceType"] == "grid" for r in regions),
                        [r["surfaceType"] for r in regions])
        box = (70, 50, 170, 130)
        self.assertEqual(_dark_count(plate, box), _dark_count(img, box))
        self.assertEqual(meta["outsideChanged"], 0)

    def test_protect_mask_is_never_written(self):
        img, hole = _base_panel()
        protect = Image.new("L", img.size, 0)
        ImageDraw.Draw(protect).rectangle((150, 70, 175, 100), fill=255)
        plate, _regions, meta = build_clean_plate(img, hole, protect_mask=protect)
        changed = 0
        for y in range(70, 100):
            for x in range(150, 175):
                if plate.getpixel((x, y))[:3] != img.getpixel((x, y))[:3]:
                    changed += 1
        self.assertEqual(changed, 0)
        self.assertEqual(meta["outsideChanged"], 0)

    def test_insufficient_evidence_is_unknown_and_not_written(self):
        """方案 §10 P0：信息不足时**不许生成假背景** —— 标 unknown 且不写入。"""
        # 🚨 真·信息不足 = 「要重建的面积远超该表面可见证据」：
        #    环住大洞的细边只剩几千像素证据，洞却有 3 万多 —— 靠距离扣分只压到 0.33，
        #    仍然越过门槛被当可信写入（实测踩过），所以必须有面积比硬闸。
        img = Image.new("RGBA", (200, 200), (30, 32, 38, 255))
        d = ImageDraw.Draw(img)
        for i in range(0, 200, 7):
            for j in range(0, 200, 7):
                if 8 <= i <= 192 and 8 <= j <= 192:
                    continue
                d.point((i, j), fill=(70, 72, 80, 255))
        hole = Image.new("L", (200, 200), 0)
        ImageDraw.Draw(hole).rectangle((8, 8, 192, 192), fill=255)
        plate, regions, meta = build_clean_plate(img, hole)
        unknown = [r for r in regions if r["source"] == "unknown"]
        self.assertTrue(unknown, [(r["id"], r["source"], r["confidence"]) for r in regions])
        self.assertGreater(meta["unknownPixels"], 0)
        self.assertEqual(meta["writtenPixels"], 0)
        # unknown 区域必须保留原图像素（没有写入）
        r = unknown[0]
        x = r["bbox"][0] + r["bbox"][2] // 2
        y = r["bbox"][1] + r["bbox"][3] // 2
        self.assertEqual(plate.getpixel((x, y))[:3], img.getpixel((x, y))[:3])

    def test_region_masks_and_summary_are_consistent(self):
        img, hole = _base_panel()
        masks = {}
        plate, regions, meta = build_clean_plate(img, hole, region_masks=masks)
        rebuilt = [r for r in regions if r["kind"] == "rebuilt"]
        self.assertEqual(len(masks), len(rebuilt))
        for r in rebuilt:
            mask = masks[r["id"]]
            self.assertEqual(mask.size, img.size)
            self.assertEqual(mask.histogram()[255], r["pixels"])
        summary = surface_summary(regions)
        # surfaceSummary 按**表面类型**汇总；原图保留区不是「表面」，归在 n/a 下
        self.assertIn("n/a", summary)
        self.assertEqual(summary["n/a"]["sources"], {"original": 1})
        self.assertEqual(sum(v["pixels"] for v in summary.values()),
                         img.size[0] * img.size[1])
        for r in regions:
            self.assertIn(r["source"], REGION_SOURCES)
            self.assertIn(r["surfaceType"], SURFACE_TYPES + ("n/a",))
            self.assertIn("polygon", r)
            self.assertEqual(len(r["polygon"]), 4)

    def test_region_ids_and_kinds_are_stable(self):
        img, hole = _base_panel()
        _p1, regions, _m = build_clean_plate(img, hole)
        _p2, regions2, _m2 = build_clean_plate(img, hole)
        self.assertEqual([r["id"] for r in regions], [r["id"] for r in regions2])
        self.assertEqual(regions[0]["kind"], "original")
        self.assertEqual(regions[0]["source"], "original")

    def test_empty_hole_returns_original_region(self):
        img, _ = _base_panel()
        empty = Image.new("L", img.size, 0)
        plate, regions, meta = build_clean_plate(img, empty)
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]["source"], "original")
        self.assertEqual(meta["writtenPixels"], 0)
        self.assertEqual(plate.getpixel((5, 5))[:3], img.getpixel((5, 5))[:3])


class SurfaceClassifyTests(unittest.TestCase):
    def test_surface_classification_rules(self):
        self.assertEqual(classify_surface({"n": 4}), "unknown")
        flat = {"n": 5000, "spread": 2.0, "planeResid": 0.5, "structure": 0.3,
                "outlierRatio": 0.0, "edgeDensity": 0.0, "thinRatio": 1.0,
                "width": 80, "height": 60, "pts": []}
        self.assertEqual(classify_surface(flat), "panel")
        small_flat = dict(flat, n=500)
        self.assertEqual(classify_surface(small_flat), "flat")
        grad = dict(flat, spread=60.0, planeResid=1.2)
        self.assertEqual(classify_surface(grad), "gradient")
        # 🚨 稀疏点阵：平均残差很小，但离群比例高 ⇒ 必须判成纹理，不能判成渐变
        dots = dict(flat, spread=40.0, planeResid=2.5, outlierRatio=0.06, edgeDensity=0.05)
        self.assertEqual(classify_surface(dots), "texture")
        line = dict(flat, thinRatio=20.0, width=3, height=200)
        self.assertEqual(classify_surface(line), "line")

    def test_segment_surfaces_merges_quantization_bands(self):
        """渐变被量化切成条带时必须合并，否则每个条带都是 flat、走不到平面拟合。"""
        img, hole = _gradient()
        label_map, surfaces, known = segment_surfaces(img.convert("RGB"), hole)
        self.assertLessEqual(len(surfaces), 3, {k: v["mean"] for k, v in surfaces.items()})


if __name__ == "__main__":
    unittest.main()
