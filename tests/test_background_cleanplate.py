# -*- coding: utf-8 -*-
"""背景 clean plate 测试（方案 §4 阶段 D / §12 交付验收 / §14 P2）。

覆盖：removeMask 合并口径 / 可控膨胀与保护闸门 / 洞分区与账目守恒 /
纯色证据（含被邻元素污染的环带）/ 重复纹理检测 / 移除后空位测试 /
候选越界门禁 / 逐区域打分 / 验收五项 / fixture 全链路 / 落文档门禁 / JSON 摘要。

全部纯 PIL，零模型调用、零网络、零磁盘写。
"""

import json
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from _element_scene import load_scene, render_source, scene_entries
from backend.background_cleanplate import (
    MAX_DILATE, MIN_CANDIDATE_SCORE, CANDIDATE_LABELS, CleanPlateError,
    attach_to_document, background_hole, build_cleanplate, compose_plate,
    empty_slot_test, expand_remove, flat_evidence, generate_candidates,
    remove_mask, repeat_texture_check, score_candidate, select_candidate, summarize,
    verify_cleanplate)
from backend.element_document import (
    create_document, get_document, register_asset, reset_stores, set_ownership,
    asset_kind)
from backend.element_ownership import resolve_ownership
from backend.split_bg_regions import mask_pixels

BG = (200, 200, 200)
SUBJECT = (20, 20, 20)
SIZE = (120, 120)
RECT = (30, 30, 70, 90)


def rect_mask(size, rect):
    img = Image.new("L", size, 0)
    ImageDraw.Draw(img).rectangle((rect[0], rect[1], rect[2] - 1, rect[3] - 1), fill=255)
    return img


def striped(size, period=8, dark=40, light=210):
    """横条纹图（周期性纹理，用来测重复纹理检测）。

    🚨 完整周期是 `2 * period`（深 period 行 + 浅 period 行），不是 `period`。
    """
    img = Image.new("RGB", size, (light, light, light))
    px = img.load()
    for y in range(size[1]):
        if (y // period) % 2 == 0:
            for x in range(size[0]):
                px[x, y] = (dark, dark, dark)
    return img


def noisy(size, seed=7):
    """均匀随机噪声：**没有任何一种颜色占多数**，纯色证据必然拿不到。

    ⚠️ 不能用条纹来测「拿不到证据」：条纹在**局部**（一个只覆盖浅色行的区域）
    确实是一种颜色，那里拿到纯色证据是对的，常量填充也是对的。
    真正没有纯色证据的是「任何一块里都找不到主色」的那种纹理。
    """
    rnd = random.Random(seed)
    img = Image.new("RGB", size)
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                 for _ in range(size[0] * size[1])])
    return img


def synthetic(size=SIZE, bg=BG, rect=RECT, color=SUBJECT, confidence=0.9):
    """「纯色底 + 一个深色矩形主体」，返回 (source, ownership, mask)。"""
    mask = rect_mask(size, rect)
    source = Image.new("RGB", size, bg)
    source.paste(Image.new("RGB", size, color), (0, 0), mask)
    ownership = resolve_ownership(
        [{"elementId": "el_subject", "mask": mask, "confidence": confidence,
          "type": "object"}], size)
    return source, ownership, mask


def scene(size=SIZE):
    source, ownership, mask = synthetic()
    return {"source": source, "ownership": ownership, "mask": mask,
            "hole": expand_remove(mask, 3)["mask"], "size": size}


def single_region(sc):
    """一个区域 + 空保护区的 `hole_result`（多数单元测试的最小输入）。"""
    return background_hole(sc["source"], sc["hole"])


# ---------------------------------------------------------------------------
# ① removeMask
# ---------------------------------------------------------------------------

class RemoveMaskTests(unittest.TestCase):
    def setUp(self):
        self.size = SIZE
        self.a = rect_mask(self.size, (10, 10, 30, 30))
        self.b = rect_mask(self.size, (40, 40, 60, 60))
        self.unknown = rect_mask(self.size, (80, 80, 100, 100))
        self.ownership = resolve_ownership(
            [{"elementId": "el_a", "mask": self.a, "confidence": 0.9},
             {"elementId": "el_b", "mask": self.b, "confidence": 0.9}], self.size)
        self.ownership["unknown"] = self.unknown

    def test_unions_every_element_mask(self):
        rm = remove_mask(self.ownership, size=self.size)
        self.assertEqual(rm["stats"]["corePixels"], 800)
        # 全部元素都要走 ⇒ unknown 一并清掉（它只可能是被移除元素的残边）。
        self.assertEqual(rm["stats"]["removePixels"], 1200)
        self.assertEqual(sorted(rm["elementIds"]), ["el_a", "el_b"])
        self.assertEqual(mask_pixels(rm["core"]), 800)
        self.assertEqual(rm["unknown"].histogram()[255], 400)

    def test_unknown_is_kept_when_only_some_elements_are_removed(self):
        rm = remove_mask(self.ownership, ["el_a"], size=self.size)
        # 🚨 留下的 el_b 有可能正是 unknown 的归属者，清掉等于给它挖个洞。
        self.assertEqual(rm["stats"]["unknownPixels"], 0)
        self.assertEqual(rm["stats"]["removePixels"], 400)
        # el_b 的遮罩必须原封不动（400 px 完好），没被顺手清掉。
        self.assertEqual(self.ownership["masks"]["el_b"].histogram()[255], 400)

    def test_explicit_include_unknown_overrides_the_default(self):
        rm = remove_mask(self.ownership, ["el_a"], include_unknown=True, size=self.size)
        self.assertEqual(rm["stats"]["unknownPixels"], 400)
        self.assertEqual(rm["stats"]["removePixels"], 800)

    def test_all_elements_plus_unknown_can_be_excluded(self):
        rm = remove_mask(self.ownership, include_unknown=False, size=self.size)
        self.assertEqual(rm["stats"]["removePixels"], 800)
        self.assertEqual(rm["stats"]["includeUnknown"], False)

    def test_extra_masks_go_into_remove_but_not_into_core(self):
        shadow = rect_mask(self.size, (5, 5, 8, 8))
        rm = remove_mask(self.ownership, ["el_a"], extra=[shadow], size=self.size)
        self.assertEqual(rm["stats"]["corePixels"], 400)
        self.assertEqual(rm["stats"]["extraPixels"], 9)
        self.assertEqual(rm["stats"]["removePixels"], 409)

    def test_unknown_element_id_is_loud(self):
        # 静默跳过 = 那个元素的主体像素留在背景里，而且没人知道。
        with self.assertRaises(CleanPlateError):
            remove_mask(self.ownership, ["el_nope"], size=self.size)

    def test_empty_ownership_is_loud(self):
        with self.assertRaises(CleanPlateError):
            remove_mask({"masks": {}}, size=self.size)

    def test_mask_size_mismatch_is_loud(self):
        with self.assertRaises(CleanPlateError):
            remove_mask({"masks": {"el_x": rect_mask((10, 10), (0, 0, 5, 5))}}, size=self.size)


# ---------------------------------------------------------------------------
# ② 可控膨胀
# ---------------------------------------------------------------------------

class ExpandRemoveTests(unittest.TestCase):
    def setUp(self):
        self.size = (64, 64)
        self.mask = rect_mask(self.size, (20, 20, 30, 30))   # 10×10 = 100 px

    def test_radius_zero_is_a_noop(self):
        out = expand_remove(self.mask, 0, size=self.size)
        self.assertEqual(out["stats"]["expandedPixels"], 100)
        self.assertEqual(out["grownPixels"], 0)

    def test_dilation_grows_by_the_expected_amount(self):
        # 10×10 按 5×5 核膨胀 → 14×14 = 196；增量 96。
        out = expand_remove(self.mask, 2, size=self.size)
        self.assertEqual(out["stats"]["expandedPixels"], 196)
        self.assertEqual(out["grownPixels"], 96)

    def test_radius_is_clamped_to_the_cap(self):
        out = expand_remove(self.mask, 9999, size=self.size)
        self.assertEqual(out["radius"], MAX_DILATE)

    def test_protect_clamps_growth_and_never_eats_the_base(self):
        # 🚨 保护带必须**紧贴但不重叠**主体：重叠是入参错误（见下一条用例），
        #    这里要测的是「扩张被挡住」，不是「重叠被拦住」。
        protect = rect_mask(self.size, (31, 0, 64, 64))
        out = expand_remove(self.mask, 3, protect=protect, size=self.size)
        self.assertGreater(out["clampedByProtect"], 0)
        # 原始 100 像素一个都不能少 —— 少了就是把主体留在背景里。
        self.assertEqual(mask_pixels(self.mask), 100)
        self.assertGreaterEqual(out["mask"].histogram()[255], 100)
        # 保护带里一个像素都不许被扩进来。
        overlap = Image.composite(out["mask"], Image.new("L", self.size, 0), protect)
        self.assertEqual(mask_pixels(overlap), 0)

    def test_protect_overlapping_remove_is_loud(self):
        with self.assertRaises(CleanPlateError):
            expand_remove(self.mask, 3, protect=rect_mask(self.size, (25, 25, 28, 28)),
                          size=self.size)

    def test_gate_limits_expansion_but_never_eats_the_base(self):
        gate = rect_mask(self.size, (0, 0, 12, 64))          # 左边一条允许扩张的通道
        out = expand_remove(self.mask, 3, gate=gate, size=self.size)
        self.assertGreater(out["clampedByGate"], 0)
        self.assertGreaterEqual(out["mask"].histogram()[255], 100)


# ---------------------------------------------------------------------------
# ③ 纯色证据
# ---------------------------------------------------------------------------

class FlatEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.size = (100, 100)
        self.source = Image.new("RGB", self.size, BG)
        self.region = rect_mask(self.size, (40, 40, 60, 60))
        self.hole = self.region

    def test_flat_ring_passes_and_reports_the_color(self):
        ev = flat_evidence(self.source, self.region, hole=self.hole)
        self.assertTrue(ev["ok"])
        self.assertEqual(tuple(ev["color"]), BG)
        self.assertEqual(ev["spread"], 0.0)
        self.assertGreaterEqual(ev["majority"], 0.99)

    def test_majority_threshold_is_reported(self):
        ev = flat_evidence(self.source, self.region, hole=self.hole)
        self.assertAlmostEqual(ev["majority"], 1.0, places=2)
        self.assertGreaterEqual(ev["ringPixels"], ev["pixels"])

    def test_neighbour_minority_does_not_break_flatness(self):
        """🚨 环带被邻近元素污染是常态：指针周围混进秒针的红色。

        按整个环带的色散判会让纯色填充永远拿不到证据（实测 spread 26.3）。
        多数簇口径必须扛住这种少数派污染。
        """
        img = self.source.copy()
        stripe = rect_mask(self.size, (40, 40, 60, 44))      # 环带内的 4px 异色条
        img.paste(Image.new("RGB", self.size, (200, 40, 40)), (0, 0), stripe)
        ev = flat_evidence(img, self.region, hole=self.hole)
        self.assertTrue(ev["ok"], ev)
        self.assertEqual(tuple(ev["color"]), BG)
        self.assertGreater(ev["majority"], 0.8)

    def test_mixed_context_is_rejected(self):
        # 异色块必须**盖住环带的一部分**才有意义：整块落在 region 里时，
        # 环带依旧全是底色，那不是「混合上下文」，是「干净的上下文」。
        img = self.source.copy()
        half = rect_mask(self.size, (30, 30, 70, 48))
        img.paste(Image.new("RGB", self.size, (10, 10, 10)), (0, 0), half)
        ev = flat_evidence(img, self.region, hole=self.hole)
        self.assertFalse(ev["ok"], ev)
        self.assertIn(ev["reason"], ("mixed_context", "ring_too_small"))

    def test_textured_ring_is_rejected(self):
        ev = flat_evidence(striped(self.size), self.region, hole=self.region)
        self.assertFalse(ev["ok"])

    def test_color_drift_is_rejected(self):
        """近处是 A 色、更外一圈是 B 色 ⇒ 常量填充会在边界留下色斑。

        🚨 `near` 必须**小于**更外一圈的半径（12px）：异色若只铺到环带外一点点，
        中位色仍会落在近处的底色上，drift 恒为 0，这条恰恰测不出问题。
        """
        img = Image.new("RGB", self.size, (60, 60, 60))
        near = rect_mask(self.size, (35, 35, 65, 65))
        img.paste(Image.new("RGB", self.size, BG), (0, 0), near)
        ev = flat_evidence(img, self.region, hole=self.hole)
        self.assertFalse(ev["ok"])
        self.assertEqual(ev["reason"], "color_drift")
        self.assertGreater(ev["drift"], 0)

    def test_ring_too_small_has_no_evidence(self):
        ev = flat_evidence(self.source, rect_mask(self.size, (0, 0, 100, 100)),
                           hole=rect_mask(self.size, (0, 0, 100, 100)))
        self.assertFalse(ev["ok"])
        self.assertEqual(ev["reason"], "ring_too_small")

    def test_hole_pixels_are_never_used_as_context(self):
        """上下文只取「洞外的原始像素」：洞内是要被换掉的内容，不能当背景色。

        洞盖住环带的上半圈（里面是深色待换内容），证据必须仍来自下半圈的底色。
        """
        img = Image.new("RGB", self.size, BG)
        hole = rect_mask(self.size, (30, 30, 70, 55))
        img.paste(Image.new("RGB", self.size, (10, 10, 10)), (0, 0), hole)
        ev = flat_evidence(img, self.region, hole=hole)
        self.assertTrue(ev["ok"], ev)
        self.assertEqual(tuple(ev["color"]), BG)

    def test_fully_covered_ring_has_no_evidence(self):
        """环带被洞整个盖住 ⇒ 一点可用上下文都没有 ⇒ 宁可判 ring_too_small。

        🚨 真实链路上 `region ⊆ hole` 恒成立，所以这不是构造出来的边角情况：
           大洞的中心区域就是拿不到上下文。此时**不许**退而求其次去用洞内像素，
           更不许编一个颜色 —— 修不了就明确报待修复洞（§D.8）。
        """
        img = Image.new("RGB", self.size, BG)
        hole = rect_mask(self.size, (30, 30, 70, 70))
        img.paste(Image.new("RGB", self.size, (10, 10, 10)), (0, 0), hole)
        ev = flat_evidence(img, self.region, hole=hole)
        self.assertFalse(ev["ok"])
        self.assertEqual(ev["reason"], "ring_too_small")


# ---------------------------------------------------------------------------
# ④ 洞分区
# ---------------------------------------------------------------------------

class BackgroundHoleTests(unittest.TestCase):
    def test_regions_partition_the_hole_exactly(self):
        sc = scene()
        result = background_hole(sc["source"], sc["hole"])
        self.assertEqual(result["stats"]["unlabeledPixels"], 0)
        union = Image.new("L", SIZE, 0)
        for region in result["regions"]:
            union = Image.composite(Image.new("L", SIZE, 255), union, region["mask"])
        self.assertEqual(mask_pixels(union), mask_pixels(sc["hole"]))

    def test_region_ids_are_derived_from_masks_not_indices(self):
        sc = scene()
        first = background_hole(sc["source"], sc["hole"])
        second = background_hole(sc["source"], sc["hole"])
        self.assertEqual([r["regionId"] for r in first["regions"]],
                         [r["regionId"] for r in second["regions"]])
        self.assertTrue(all(r["regionId"].startswith("region-") for r in first["regions"]))

    def test_protect_is_subtracted_from_the_hole(self):
        sc = scene()
        protect = rect_mask(SIZE, (30, 30, 70, 45))
        result = background_hole(sc["source"], sc["hole"], protect=protect)
        self.assertGreater(result["stats"]["protectedPixels"], 0)
        kept = Image.composite(result["hole"], Image.new("L", SIZE, 0), protect)
        self.assertEqual(mask_pixels(kept), 0)

    def test_empty_hole_yields_no_regions(self):
        sc = scene()
        result = background_hole(sc["source"], Image.new("L", SIZE, 0))
        self.assertEqual(result["regions"], [])
        self.assertEqual(result["stats"]["holePixels"], 0)

    def test_local_repair_never_writes_outside_the_hole(self):
        sc = scene()
        result = background_hole(sc["source"], sc["hole"])
        self.assertEqual(result["localRepair"]["meta"]["outsideChanged"], 0)


# ---------------------------------------------------------------------------
# ⑤ 重复纹理检测
# ---------------------------------------------------------------------------

class RepeatTextureTests(unittest.TestCase):
    """🚨 窗口必须够大：`_profile_period` 只在 lag ≤ n/2 里找峰（n = 掩码覆盖的行/列数），
    所以 20×20 的区域测不出周期 16 —— 那不是「没有纹理」，是**窗口太小没量到**。
    这里统一用 60×60 的区域（n=60 ⇒ 可测到周期 30）。"""

    def _region(self):
        return rect_mask((120, 120), (30, 30, 90, 90))

    def test_flat_pair_passes(self):
        img = Image.new("RGB", (120, 120), BG)
        out = repeat_texture_check(img, img, self._region())
        self.assertTrue(out["ok"])
        self.assertEqual(out["reasons"], [])

    def test_broken_texture_is_flagged(self):
        """周边是规则纹理、补完的区域量不出周期 ⇒ 纹理节奏断了（补丁被揉平）。"""
        region = self._region()
        # `striped(period=4)` 的完整周期是 8（4 深 + 4 浅）。
        ctx = striped((120, 120), period=4)
        plate = ctx.copy()
        plate.paste(Image.new("RGB", (120, 120), BG), (0, 0), region)
        out = repeat_texture_check(ctx, plate, region)
        self.assertFalse(out["ok"], out)
        self.assertIn("texture_broken", out["reasons"])

    def test_stamped_repeat_is_flagged(self):
        """周边不是周期纹理、补完的区域突然有强周期 ⇒ 把同一块复制贴上。"""
        region = self._region()
        plate = Image.new("RGB", (120, 120), BG)
        plate.paste(striped((120, 120), period=4), (0, 0), region)
        out = repeat_texture_check(plate, plate, region)
        self.assertFalse(out["ok"], out)
        self.assertIn("stamped_repeat", out["reasons"])

    def test_matching_period_passes(self):
        img = striped((120, 120), period=10)                 # 完整周期 20
        out = repeat_texture_check(img, img, self._region())
        self.assertTrue(out["ok"], out)
        # 不能是「两边都量不出周期所以通过」那种假绿：必须真的量到了周期。
        self.assertTrue(out["metrics"]["checked"])
        self.assertIsNotNone(out["metrics"]["regionPeriod"][1])

    def test_period_mismatch_is_flagged(self):
        region = self._region()
        ctx = striped((120, 120), period=4)                  # 完整周期 8
        plate = ctx.copy()
        plate.paste(striped((120, 120), period=9), (0, 0), region)   # 完整周期 18
        out = repeat_texture_check(ctx, plate, region)
        self.assertFalse(out["ok"], out)
        self.assertTrue(any(r.startswith("period_") for r in out["reasons"]), out["reasons"])

    def test_tiny_region_is_skipped_not_failed(self):
        img = striped((120, 120), period=8)
        out = repeat_texture_check(img, img, rect_mask((120, 120), (10, 10, 12, 12)))
        self.assertTrue(out["ok"])
        self.assertFalse(out["metrics"]["checked"])


# ---------------------------------------------------------------------------
# ⑥ 移除后空位测试
# ---------------------------------------------------------------------------

class EmptySlotTests(unittest.TestCase):
    def setUp(self):
        self.sc = scene()
        self.core = self.sc["mask"]

    def test_unchanged_subject_reports_residue(self):
        out = empty_slot_test(self.sc["source"], self.sc["source"], self.core)
        self.assertFalse(out["ok"])
        self.assertIn("subject_residue", out["reasons"])
        self.assertEqual(out["metrics"]["residuePixels"], out["metrics"]["mustChangePixels"])

    def test_filled_plate_has_no_residue_and_no_ghost(self):
        plate = self.sc["source"].copy()
        plate.paste(Image.new("RGB", SIZE, BG), (0, 0), self.core)
        out = empty_slot_test(self.sc["source"], plate, self.core)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["metrics"]["residuePixels"], 0)
        self.assertEqual(out["metrics"]["ghostCorr"], 0.0)

    def test_faded_copy_is_reported_as_ghost(self):
        """半透明淡化：像素都变了（不是残留），但整块与周边背景明显不同 ⇒ 轮廓还在。

        🚨 这条**测不到相关系数**：淡化后核心区每个像素都变成同一个值，方差为 0，
        相关系数必然算成 0。只有「区域主色 vs 周边背景色」的色差能把它量出来 ——
        两条证据缺一条，这一整类缺陷就漏掉了。
        """
        plate = Image.blend(self.sc["source"], Image.new("RGB", SIZE, (255, 255, 255)), 0.5)
        out = empty_slot_test(self.sc["source"], plate, self.core)
        self.assertEqual(out["metrics"]["residuePixels"], 0)
        self.assertIn("ghost", out["reasons"])
        self.assertGreater(out["metrics"]["regionContrast"], 50)

    def test_blurred_copy_is_reported_as_residue(self):
        plate = self.sc["source"].filter(ImageFilter.GaussianBlur(2))
        out = empty_slot_test(self.sc["source"], plate, self.core)
        self.assertFalse(out["ok"])

    def test_low_contrast_element_is_not_falsely_accused(self):
        """白色反光贴在白色表盘上：与背景同色，要求它「必须变」是没有意义的。"""
        source, _, mask = synthetic(bg=(250, 250, 252), color=(255, 255, 255))
        out = empty_slot_test(source, source, mask)
        self.assertEqual(out["metrics"]["mustChangePixels"], 0)
        self.assertEqual(out["metrics"]["residuePixels"], 0)
        self.assertTrue(out["ok"], out)

    def test_semi_transparent_edge_is_flagged(self):
        plate = self.sc["source"].convert("RGBA")
        alpha = Image.new("L", SIZE, 255)
        ImageDraw.Draw(alpha).rectangle((40, 40, 60, 60), fill=128)
        plate.putalpha(alpha)
        out = empty_slot_test(self.sc["source"], plate, self.core)
        self.assertIn("semi_transparent", out["reasons"])
        self.assertGreater(out["metrics"]["alphaHoles"], 0)

    def test_empty_core_is_ok(self):
        out = empty_slot_test(self.sc["source"], self.sc["source"], Image.new("L", SIZE, 0))
        self.assertTrue(out["ok"])
        self.assertEqual(out["metrics"]["corePixels"], 0)

    def test_required_change_mask_marks_only_subject_pixels(self):
        out = empty_slot_test(self.sc["source"], self.sc["source"], self.core)
        # 主体 40×60 = 2400；膨胀出来的边角本来就是底色，不算「必须改变」。
        self.assertEqual(mask_pixels(out["requiredChange"]), 2400)


# ---------------------------------------------------------------------------
# ⑦ 候选择优与打分门禁
# ---------------------------------------------------------------------------

class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.sc = scene()
        self.hole = background_hole(self.sc["source"], self.sc["hole"])

    def _candidate(self, plate, write, algo="flat_fill"):
        return {"algo": algo, "label": CANDIDATE_LABELS["flat_fill"],
                "candidateId": f"cp-{algo}-test", "plate": plate, "writeMask": write,
                "entries": [], "skipped": [], "meta": {},
                "status": "ready", "writePixels": mask_pixels(write)}

    def test_flat_fill_writes_the_evidenced_region(self):
        candidates = generate_candidates(self.sc["source"], self.hole)
        flat = next(c for c in candidates if c["algo"] == "flat_fill")
        self.assertEqual(flat["writePixels"], mask_pixels(self.sc["hole"]))
        self.assertEqual(flat["skipped"], [])

    def test_flat_fill_skips_a_region_without_evidence(self):
        source = noisy(SIZE)
        hole = background_hole(source, rect_mask(SIZE, (30, 30, 70, 90)))
        candidates = generate_candidates(source, hole)
        flat = next(c for c in candidates if c["algo"] == "flat_fill")
        self.assertEqual(flat["writePixels"], 0)
        self.assertEqual(flat["status"], "skipped")
        self.assertTrue(flat["skipped"])

    def test_local_repair_is_offered_too(self):
        candidates = generate_candidates(self.sc["source"], self.hole)
        self.assertEqual(sorted(c["algo"] for c in candidates),
                         ["flat_fill", "local_repair"])

    def test_keeping_the_original_is_rejected(self):
        """§16：不许把原始主体像素当成功背景。"""
        candidate = self._candidate(self.sc["source"].copy(), self.sc["hole"])
        report = score_candidate(self.sc["source"], candidate, self.hole)
        self.assertFalse(report["ok"])
        self.assertTrue(any("subject_residue" in r for r in report["reasons"]))

    def test_writing_outside_the_mask_is_flagged(self):
        plate = self.sc["source"].copy()
        plate.paste(Image.new("RGB", SIZE, BG), (0, 0), self.sc["hole"])
        plate.putpixel((0, 0), (123, 45, 67))                # 越出 writeMask
        candidate = self._candidate(plate, self.sc["hole"])
        report = score_candidate(self.sc["source"], candidate, self.hole)
        self.assertFalse(report["ok"])
        self.assertTrue(any(r.startswith("writes_outside_mask") for r in report["reasons"]))

    def test_writing_into_the_protect_area_is_flagged(self):
        protect = rect_mask(SIZE, (30, 30, 70, 45))
        hole = background_hole(self.sc["source"], self.sc["hole"], protect=protect)
        plate = self.sc["source"].copy()
        plate.paste(Image.new("RGB", SIZE, BG), (0, 0), self.sc["hole"])
        candidate = self._candidate(plate, self.sc["hole"])
        report = score_candidate(self.sc["source"], candidate, hole, protect=protect)
        self.assertTrue(any(r.startswith("protected_changed") for r in report["reasons"]))

    def test_write_mask_beyond_the_hole_is_flagged(self):
        plate = self.sc["source"].copy()
        plate.paste(Image.new("RGB", SIZE, BG), (0, 0), self.sc["hole"])
        write = Image.new("L", SIZE, 255)                     # 整幅画都可写 = 越界
        candidate = self._candidate(plate, write)
        report = score_candidate(self.sc["source"], candidate, self.hole)
        self.assertTrue(any(r.startswith("write_outside_hole") for r in report["reasons"]))

    def test_region_without_writes_is_reported_as_pending(self):
        candidate = self._candidate(self.sc["source"].copy(), Image.new("L", SIZE, 0))
        report = score_candidate(self.sc["source"], candidate, self.hole)
        self.assertTrue(any(r.startswith("unrepaired_region") for r in report["reasons"]))
        self.assertEqual(report["regions"][0]["state"], "pending")

    def test_unwritten_but_already_correct_pixels_are_not_a_defect(self):
        """填色恰好等于原底色时，边角像素「没被写入」是对的，不能算缺陷。"""
        candidate = self._candidate(self.sc["source"].copy(), self.sc["hole"])
        report = score_candidate(self.sc["source"], candidate, self.hole)
        self.assertFalse(any("pending_region_pixels" in r for r in report["reasons"]))

    def test_candidate_id_is_derived_from_content(self):
        first = generate_candidates(self.sc["source"], self.hole)
        second = generate_candidates(self.sc["source"], self.hole)
        self.assertEqual([c["candidateId"] for c in first],
                         [c["candidateId"] for c in second])


# ---------------------------------------------------------------------------
# ⑧ 拼板与验收
# ---------------------------------------------------------------------------

class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.sc = scene()
        self.required = self.sc["mask"]
        self.write = self.sc["hole"]

    def test_untouched_subject_is_reported(self):
        # 🚨 writeMask 只盖住主体上半截：待修复洞 = 「该改但不在 writeMask 里」的像素，
        #    给一张覆盖全洞的 writeMask 是量不出 pending_holes 的。
        partial = rect_mask(SIZE, (30, 30, 70, 50))
        out = verify_cleanplate(self.sc["source"], self.sc["source"], self.required,
                                write_mask=partial)
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "needs_manual_repair")
        codes = {i["code"] for i in out["issues"]}
        self.assertIn("subject_residue", codes)
        self.assertIn("pending_holes", codes)
        self.assertGreater(out["stats"]["pendingPixels"], 0)

    def test_clean_plate_passes(self):
        plate = self.sc["source"].copy()
        plate.paste(Image.new("RGB", SIZE, BG), (0, 0), self.write)
        out = verify_cleanplate(plate, self.sc["source"], self.required,
                                write_mask=self.write, remove=self.write)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["status"], "original_plus_deterministic")

    def test_residue_is_reported(self):
        plate = self.sc["source"].copy()
        plate.paste(Image.new("RGB", SIZE, BG), (0, 0), self.write)
        plate.paste(self.sc["source"], (0, 0), rect_mask(SIZE, (50, 50, 55, 55)))
        out = verify_cleanplate(plate, self.sc["source"], self.required,
                                write_mask=self.write)
        self.assertTrue(any(i["code"] == "subject_residue" for i in out["issues"]))

    def test_outside_write_is_reported(self):
        plate = self.sc["source"].copy()
        plate.paste(Image.new("RGB", SIZE, BG), (0, 0), self.write)
        plate.putpixel((5, 5), (1, 2, 3))
        out = verify_cleanplate(plate, self.sc["source"], self.required,
                                write_mask=self.write)
        self.assertTrue(any(i["code"] == "outside_written" for i in out["issues"]))

    def test_protected_write_is_reported(self):
        plate = self.sc["source"].copy()
        plate.paste(Image.new("RGB", SIZE, BG), (0, 0), self.write)
        plate.putpixel((5, 5), (1, 2, 3))
        out = verify_cleanplate(plate, self.sc["source"], self.required,
                                write_mask=self.write,
                                protect=rect_mask(SIZE, (0, 0, 10, 10)))
        self.assertTrue(any(i["code"] == "protected_written" for i in out["issues"]))

    def test_unrepaired_is_informational_only(self):
        """膨胀边角里值已经正确的像素「没被写入」不算缺陷。"""
        plate = self.sc["source"].copy()
        plate.paste(Image.new("RGB", SIZE, BG), (0, 0), self.required)
        out = verify_cleanplate(plate, self.sc["source"], self.required,
                                write_mask=self.required, remove=self.write)
        self.assertTrue(out["ok"], out)
        self.assertGreater(out["stats"]["unrepairedPixels"], 0)
        self.assertFalse(any(i["code"] == "unrepaired" for i in out["issues"]))


# ---------------------------------------------------------------------------
# ⑨ 全链路（fixture：一块表）
# ---------------------------------------------------------------------------

class ScenePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = load_scene()
        cls.size = tuple(cls.scene["canvas"])
        cls.source = render_source(cls.scene)
        cls.ownership = resolve_ownership(scene_entries(cls.scene), cls.size)

    def test_pointer_removal_fills_with_the_dial_color(self):
        """§3.3：拖走 / 隐藏指针后，原位置必须通过空位测试，不能出现旧指针。"""
        result = build_cleanplate(self.source, self.ownership,
                                  element_ids=["el_pointer_01"])
        self.assertEqual(result["plate"].convert("RGB").getpixel((120, 100)), (250, 250, 252))
        self.assertEqual(self.source.convert("RGB").getpixel((120, 100)), (24, 28, 36))
        self.assertEqual(result["checks"]["stats"]["residuePixels"], 0)
        self.assertEqual(result["status"], "original_plus_deterministic")

    def test_pointer_removal_passes_every_check(self):
        result = build_cleanplate(self.source, self.ownership,
                                  element_ids=["el_pointer_01"])
        self.assertTrue(result["checks"]["ok"], result["checks"])
        self.assertEqual(result["pendingHoles"], [])
        self.assertEqual(result["stats"]["writePixels"], mask_pixels(result["hole"]))

    def test_kept_elements_are_protected(self):
        result = build_cleanplate(self.source, self.ownership,
                                  element_ids=["el_pointer_01"])
        diff = ImageChops.difference(result["plate"].convert("RGB"),
                                     self.source.convert("RGB")).convert("L")
        for eid in result["keptElementIds"]:
            kept = self.ownership["masks"][eid]
            self.assertEqual(
                mask_pixels(Image.composite(diff, Image.new("L", self.size, 0), kept)), 0,
                f"{eid} 所在区域被背景改写了")

    def test_pointer_original_position_passes_the_empty_slot_test(self):
        result = build_cleanplate(self.source, self.ownership,
                                  element_ids=["el_pointer_01"])
        core = (self.ownership["masks"]["el_pointer_01"])
        out = empty_slot_test(self.source, result["plate"], core)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["metrics"]["mustChangePixels"], 640)
        self.assertEqual(out["metrics"]["residuePixels"], 0)
        self.assertEqual(out["metrics"]["ghostCorr"], 0.0)

    def test_removing_every_element_rebuilds_the_scene_background(self):
        result = build_cleanplate(self.source, self.ownership)
        plate = result["plate"].convert("RGB")
        for point in ((120, 100), (60, 70), (30, 30), (170, 140)):
            self.assertEqual(plate.getpixel(point), tuple(self.scene["background"]),
                             f"{point} 没有回到底色")
        self.assertTrue(result["checks"]["ok"], result["checks"])
        self.assertEqual(result["status"], "original_plus_deterministic")

    def test_texture_background_does_not_use_constant_fill(self):
        """纹理背景：纯色证据不成立，常量填充必须**不写**。"""
        base = striped(self.size, period=12)
        content = render_source(self.scene)
        # 把场景主体贴在条纹底上，构造「纹理背景 + 深色主体」。
        mask = Image.new("L", self.size, 0)
        for element in self.scene["elements"]:
            hole = element.get("hole")
            piece = rect_mask(self.size, element["rect"])
            if hole:
                piece = Image.composite(Image.new("L", self.size, 0), piece,
                                        rect_mask(self.size, hole))
            mask = Image.composite(Image.new("L", self.size, 255), mask, piece)
        source = base.copy()
        source.paste(content, (0, 0), mask)
        ownership = resolve_ownership([{"elementId": "el_thing", "mask": mask,
                                        "confidence": 0.9}], self.size)
        result = build_cleanplate(source, ownership)
        flat = next(c for c in result["candidates"] if c["algo"] == "flat_fill")
        self.assertEqual(flat["writePixels"], 0)
        self.assertEqual(flat["status"], "skipped")

    def test_plate_is_untouched_where_nothing_is_removed(self):
        result = build_cleanplate(self.source, self.ownership,
                                  element_ids=["el_pointer_01"])
        diff = ImageChops.difference(result["plate"].convert("RGB"),
                                     self.source.convert("RGB")).convert("L")
        # 变化的像素必须全部落在 writeMask 内 ⇒ 保护区与洞外一个像素都没动。
        written = ImageChops.subtract(diff.point(lambda v: 255 if v else 0),
                                      result["writeMask"])
        self.assertEqual(mask_pixels(written), 0)


# ---------------------------------------------------------------------------
# ⑩ 选候选 / 落文档 / 摘要
# ---------------------------------------------------------------------------

class SelectCandidateTests(unittest.TestCase):
    def test_select_candidate_recomposes_with_that_candidate(self):
        sc = scene()
        result = build_cleanplate(sc["source"], sc["ownership"])
        other = next(c for c in result["candidates"]
                     if c["candidateId"] != result["bestCandidateId"])
        picked = select_candidate(result, other["candidateId"], sc["source"])
        self.assertEqual(picked["bestCandidateId"], other["candidateId"])
        self.assertNotEqual(id(picked), id(result))
        self.assertIn(picked["status"], ("original_plus_deterministic", "needs_manual_repair"))

    def test_unknown_candidate_id_is_loud(self):
        sc = scene()
        result = build_cleanplate(sc["source"], sc["ownership"])
        with self.assertRaises(CleanPlateError):
            select_candidate(result, "cp-nope", sc["source"])


class DocumentAttachTests(unittest.TestCase):
    def setUp(self):
        reset_stores()
        sc = scene()
        self.sc = sc
        self.result = build_cleanplate(sc["source"], sc["ownership"])
        source_ref = register_asset("source", image=sc["source"])
        self.doc = create_document(source_ref["id"], width=SIZE[0], height=SIZE[1])

    def test_attach_registers_assets_and_accepts_a_clean_plate(self):
        out = attach_to_document(self.doc, self.result)
        self.assertEqual(out["status"], "accepted")
        self.assertEqual(out["plateStatus"], "original_plus_deterministic")
        self.assertEqual(asset_kind(out["assetId"]), "background")
        self.assertEqual(asset_kind(out["maskAssetId"]), "background_mask")
        doc = get_document(self.doc["documentId"])
        self.assertEqual(doc["background"]["status"], "accepted")
        self.assertEqual(doc["background"]["assetId"], out["assetId"])
        self.assertGreater(doc["documentRevision"], 0)

    def test_attach_refuses_to_accept_a_pending_plate(self):
        """§D.8 硬门禁：还有待修复洞的背景不许进 accepted。"""
        pending = dict(self.result)
        pending["status"] = "needs_manual_repair"
        with self.assertRaises(CleanPlateError):
            attach_to_document(self.doc, pending, accept=True)
        out = attach_to_document(self.doc, pending, accept=False)
        self.assertEqual(out["status"], "candidate")
        self.assertEqual(get_document(self.doc["documentId"])["background"]["status"],
                         "candidate")

    def test_attach_carries_the_quality_ledger(self):
        out = attach_to_document(self.doc, self.result)
        quality = out["quality"]
        self.assertEqual(quality["plateStatus"], "original_plus_deterministic")
        self.assertIn("stats", quality)
        self.assertEqual(quality["pendingHoles"], 0)


class SummarizeTests(unittest.TestCase):
    def test_summarize_is_json_serializable(self):
        sc = scene()
        result = build_cleanplate(sc["source"], sc["ownership"])
        payload = summarize(result)
        text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        self.assertIn("plateStatus", text)

    def test_summarize_has_no_image_payload(self):
        sc = scene()
        result = build_cleanplate(sc["source"], sc["ownership"])
        text = json.dumps(summarize(result), ensure_ascii=False)
        self.assertNotIn("base64", text)
        self.assertNotIn("PIL", text)

    def test_summarize_of_nothing_is_present_false(self):
        self.assertFalse(summarize(None)["present"])


class ComposePlateTests(unittest.TestCase):
    def test_only_passing_regions_are_composed(self):
        sc = scene()
        result = build_cleanplate(sc["source"], sc["ownership"])
        candidate = result["candidateRaw"][result["bestCandidateId"]]
        repaired = compose_plate(sc["source"], candidate,
                                 [{"state": "repaired", "mask": sc["hole"]}])
        skipped = compose_plate(sc["source"], candidate,
                                [{"state": "pending", "mask": sc["hole"]}])
        self.assertEqual(mask_pixels(repaired[1]), mask_pixels(sc["hole"]))
        self.assertEqual(mask_pixels(skipped[1]), 0)

    def test_score_threshold_is_meaningful(self):
        self.assertGreater(MIN_CANDIDATE_SCORE, 0.0)
        self.assertLess(MIN_CANDIDATE_SCORE, 1.0)


class PendingHoleGateTests(unittest.TestCase):
    """§D.8 的可执行断言：修不了的时候必须报「待修复洞」，不许报「确定性完成」。

    🚨 这一组是**回归用例**：探针 `output/spike/verify_cleanplate.py` 在真实尺寸场景上
       跑出过两个 bug，都是「把没修好的当修好了」——
       ① 区域只要被写过就标 `repaired`，连检查没过的也一起拼进 plate；
       ② 验收用的「必须改变」取自候选自己声明的 `requiredChange`（只覆盖它写过的区域），
          没写过的区域被静默漏掉。
       两者合起来的效果是：**修了一半的背景被报成 original_plus_deterministic**。
    """

    def _unrepairable(self):
        """噪声底 + 一个深色方块：没有任何一种算法能可靠重建 ⇒ 只可能报待修复。"""
        source = noisy(SIZE)
        mask = rect_mask(SIZE, RECT)
        ownership = resolve_ownership(
            [{"elementId": "el_subject", "mask": mask, "confidence": 0.9}], SIZE)
        return source, ownership

    def test_unrepairable_background_is_never_reported_as_done(self):
        source, ownership = self._unrepairable()
        result = build_cleanplate(source, ownership)
        self.assertNotEqual(result["status"], "original_plus_deterministic")
        self.assertTrue(result["pendingHoles"])
        self.assertFalse(result["checks"]["ok"])

    def test_pending_pixels_show_up_as_both_residue_and_pending_holes(self):
        source, ownership = self._unrepairable()
        result = build_cleanplate(source, ownership)
        self.assertGreater(result["checks"]["stats"]["residuePixels"], 0)
        self.assertGreater(result["checks"]["stats"]["pendingPixels"], 0)
        codes = {i["code"] for i in result["checks"]["issues"]}
        self.assertIn("subject_residue", codes)
        self.assertIn("pending_holes", codes)

    def test_a_region_that_failed_its_checks_is_not_called_repaired(self):
        source, ownership = self._unrepairable()
        result = build_cleanplate(source, ownership)
        best = next(c for c in result["candidates"]
                    if c["candidateId"] == result["bestCandidateId"])
        self.assertEqual([r for r in best["regions"] if r["state"] == "repaired"], [])
        self.assertEqual(best["score"], 0.0)

    def test_plate_keeps_the_original_where_the_region_is_pending(self):
        """没过的区域必须保持原样，不许把「候选的猜测」当成果交上去。"""
        source, ownership = self._unrepairable()
        result = build_cleanplate(source, ownership)
        self.assertEqual(mask_pixels(result["writeMask"]), 0)
        self.assertIsNone(ImageChops.difference(
            result["plate"].convert("RGB"), source.convert("RGB")).getbbox())

    def test_region_with_nothing_to_change_is_not_a_pending_hole(self):
        """低对比元素（白反光贴白表盘）：与背景同色 ⇒ 无需修改 ⇒ 不是待修复洞。

        🚨 与上面几条互为反面：把「没写入」一律当缺陷，就会把这种情况错报成待修复。
        """
        source, ownership, _ = synthetic(bg=(250, 250, 252), color=(255, 255, 255))
        result = build_cleanplate(source, ownership)
        self.assertEqual(result["pendingHoles"], [])
        self.assertEqual(result["status"], "original_plus_deterministic")


if __name__ == "__main__":
    unittest.main()
