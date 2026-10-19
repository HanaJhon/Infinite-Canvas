# -*- coding: utf-8 -*-
"""背景资产（方案 §5/§6）的像素级与坐标级测试。全部零模型调用。"""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw

from backend.split_background import (
    BACKGROUND_KINDS, REUSABLE_STATUS,
    background_provenance, background_status_of, build_background,
    detect_background_kind, mirror_extend, neighborhood_inpaint, solid_background,
)


def _solid_fixture(size=(120, 90), bg=(250, 250, 250), subject=(40, 80, 120)):
    img = Image.new("RGBA", size, bg + (255,))
    d = ImageDraw.Draw(img)
    d.rectangle((40, 25, 80, 70), fill=subject + (255,))
    hole = Image.new("L", size, 0)
    ImageDraw.Draw(hole).rectangle((40, 25, 80, 70), fill=255)
    return img, hole


def _gradient_fixture(size=(160, 120)):
    img = Image.new("RGBA", size)
    px = img.load()
    for y in range(size[1]):
        for x in range(size[0]):
            t = (x + y) / float(size[0] + size[1])
            px[x, y] = (int(30 + 200 * t), int(40 + 180 * t), int(60 + 150 * t), 255)
    hole = Image.new("L", size, 0)
    ImageDraw.Draw(hole).rectangle((60, 40, 100, 85), fill=255)
    return img, hole


def _checker_fixture(size=(160, 120), cell=8):
    img = Image.new("RGBA", size)
    d = ImageDraw.Draw(img)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            on = ((x // cell) + (y // cell)) % 2 == 0
            d.rectangle((x, y, x + cell - 1, y + cell - 1),
                        fill=(200, 210, 220, 255) if on else (120, 130, 150, 255))
    hole = Image.new("L", size, 0)
    ImageDraw.Draw(hole).rectangle((60, 40, 100, 85), fill=255)
    return img, hole


class BackgroundKindTests(unittest.TestCase):
    def test_solid_detected_and_plate_is_exact(self):
        img, hole = _solid_fixture()
        det = detect_background_kind(img, hole)
        self.assertEqual(det["kind"], "solid", det)
        plate, meta = build_background(img, hole)
        self.assertEqual(meta["kind"], "solid")
        self.assertEqual(meta["method"], "deterministic_plate")
        self.assertEqual(meta["status"], "original_plus_deterministic")
        self.assertIn(meta["status"], REUSABLE_STATUS)
        # §5.1：每个像素都必须写成目标颜色（含 Alpha=255）
        self.assertEqual(plate.getextrema(), ((250, 250), (250, 250), (250, 250), (255, 255)))
        self.assertEqual(plate.size, img.size)

    def test_explicit_color_overrides_sampled_color(self):
        img, hole = _solid_fixture()
        plate, meta = build_background(img, hole, kind="solid", color=(255, 255, 255))
        self.assertEqual(meta["color"], [255, 255, 255])
        self.assertEqual(plate.getextrema(), ((255, 255), (255, 255), (255, 255), (255, 255)))

    def test_gradient_fitted_and_outside_untouched(self):
        img, hole = _gradient_fixture()
        det = detect_background_kind(img, hole)
        self.assertIn(det["kind"], ("gradient", "radial"), det)
        plate, meta = build_background(img, hole)
        self.assertEqual(meta["status"], "original_plus_deterministic")
        # §10：遮罩外逐像素等于原图
        self.assertEqual(meta["outside_changed"], 0, meta)
        self.assertEqual(plate.getpixel((0, 0)), img.getpixel((0, 0)))
        # 洞内被填成了渐变（不再是原来的纯色块），且与原渐变接近
        cx, cy = 80, 60
        want = img.getpixel((0, 0))
        got = plate.getpixel((cx, cy))[:3]
        self.assertLess(max(abs(got[i] - want[i]) for i in range(3)), 120)

    def test_textured_mirror_keeps_outside(self):
        img, hole = _checker_fixture()
        mirrored, left = mirror_extend(img, hole)
        self.assertEqual(mirrored.convert("RGB").getpixel((0, 0)), img.convert("RGB").getpixel((0, 0)))
        self.assertLess(left.histogram()[255], hole.histogram()[255])

    def test_complex_marked_speculative_and_outside_untouched(self):
        img, hole = _solid_fixture()
        # 噪声背景 → 说不清，必须标 speculative（不能冒充完成）
        px = img.load()
        seed = 12345
        for y in range(img.size[1]):
            for x in range(img.size[0]):
                if hole.getpixel((x, y)):
                    continue
                seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
                n = seed % 90
                px[x, y] = (60 + n, 90 + (n * 7) % 90, 140 + (n * 3) % 90, 255)
        plate, meta = build_background(img, hole)
        self.assertIn(meta["kind"], ("complex", "textured"), meta)
        if meta["kind"] == "complex":
            self.assertEqual(meta["status"], "candidate")
            self.assertNotIn(meta["status"], REUSABLE_STATUS)
        self.assertEqual(meta["outside_changed"], 0, meta)
        self.assertEqual(plate.size, img.size)

    def test_empty_hole_is_noop(self):
        img, _ = _solid_fixture()
        empty = Image.new("L", img.size, 0)
        plate, meta = build_background(img, empty, kind="complex")
        self.assertEqual(meta["outside_changed"], 0)
        self.assertEqual(plate.getpixel((5, 5)), img.getpixel((5, 5)))


class InpaintConstraintTests(unittest.TestCase):
    def test_only_writes_write_mask_and_respects_protect(self):
        img, hole = _solid_fixture()
        write = Image.new("L", img.size, 0)
        ImageDraw.Draw(write).rectangle((30, 20, 90, 75), fill=255)
        protect = Image.new("L", img.size, 0)
        ImageDraw.Draw(protect).rectangle((70, 60, 90, 75), fill=255)
        out, stat = neighborhood_inpaint(img, write, protect)
        # protect 内逐像素不变
        self.assertEqual(out.getpixel((80, 70)), img.getpixel((80, 70)))
        # write 且非 protect 的洞内像素被改写（原为白底 250 → 被主体色影响）
        self.assertNotEqual(out.getpixel((50, 45)), img.getpixel((50, 45)))
        self.assertEqual(stat["outside_changed"], 0, stat)

    def test_large_hole_stays_fast(self):
        """自适应降采样：1200×900、600px 宽的洞必须在秒级完成。"""
        img = Image.new("RGBA", (1200, 900), (240, 240, 240, 255))
        ImageDraw.Draw(img).rectangle((300, 150, 900, 750), fill=(30, 60, 90, 255))
        hole = Image.new("L", (1200, 900), 0)
        ImageDraw.Draw(hole).rectangle((300, 150, 900, 750), fill=255)
        t0 = time.time()
        plate, meta = build_background(img, hole)
        cost = time.time() - t0
        self.assertLess(cost, 25.0, f"背景生成耗时 {cost:.1f}s，太慢")
        self.assertEqual(meta["outside_changed"], 0, meta)
        self.assertEqual(plate.size, (1200, 900))


class ProvenanceTests(unittest.TestCase):
    def test_provenance_records_state_and_hashes(self):
        img, hole = _solid_fixture()
        plate, meta = build_background(img, hole)
        prov = background_provenance(plate, asset_id="bg_test", source_hash="a" * 64,
                                     size=img.size, meta=meta, hole=hole, revision=3,
                                     created_at=1234.5)
        self.assertEqual(prov["assetId"], "bg_test")
        self.assertEqual(prov["kind"], "background")
        self.assertEqual((prov["width"], prov["height"]), img.size)
        self.assertEqual((prov["pixelSize"]["width"], prov["pixelSize"]["height"]), img.size)
        self.assertEqual(prov["qualityState"], "original_plus_deterministic")
        self.assertTrue(prov["reusable"])
        self.assertTrue(prov["complete"])
        self.assertEqual(prov["documentRevision"], 3)
        self.assertEqual(len(prov["plateSha256"]), 64)
        self.assertEqual(len(prov["maskSha256"]), 64)

    def test_stale_wins_over_recorded_state(self):
        self.assertEqual(background_status_of({"status": "original_plus_deterministic"}, stale=True), "stale")
        self.assertEqual(background_status_of({"status": "bogus"}), "failed")
        self.assertEqual(background_status_of(None), "failed")
        self.assertEqual(background_status_of({"status": "reviewed_inpaint"}), "reviewed_inpaint")
        # 旧状态名自动升级（读旧资产不能因为改名就变 failed）
        self.assertEqual(background_status_of({"status": "deterministic"}),
                         "original_plus_deterministic")
        self.assertEqual(background_status_of({"status": "speculative"}), "candidate")

    def test_solid_background_rejects_bad_color(self):
        with self.assertRaises(ValueError):
            solid_background((4, 4), None)
        with self.assertRaises(ValueError):
            solid_background((4, 4), [1, 2])

    def test_kind_whitelist_covers_plan(self):
        for kind in ("solid", "gradient", "radial", "textured", "complex"):
            self.assertIn(kind, BACKGROUND_KINDS)


if __name__ == "__main__":
    unittest.main()
