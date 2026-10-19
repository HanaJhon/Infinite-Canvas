# -*- coding: utf-8 -*-
"""背景区域闭环的纯逻辑测试：覆盖账本 / 有效写入范围 / 状态机 / 候选质量门禁。

对应方案《背景AI修补仍未生效-原因与最优调整方案-20261016》§4/§5/§6/§7。
全部零模型调用。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw

from backend.split_bg_regions import (
    REGION_STATES, WriteScopeError, asset_reusable, background_coverage,
    build_region_protect_mask, candidate_quality, candidate_record,
    coverage_ledger_lines, derive_background_status, effective_write_mask,
    mask_pixels, mask_union, region_state, region_unknown_pixels, union_pixels,
)
from backend.split_surfaces import build_clean_plate


def _mask(size, box):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rectangle(box, fill=255)
    return m


class RegionStateTests(unittest.TestCase):
    def test_explicit_state_wins(self):
        self.assertEqual(region_state({"state": "approved", "source": "unknown"}), "approved")
        self.assertEqual(region_state({"state": "superseded"}), "superseded")

    def test_legacy_records_derive_state_from_source(self):
        # 本轮之前生成的资产没有 `state` 字段，必须仍能被账本正确统计
        self.assertEqual(region_state({"source": "original"}), "approved")
        self.assertEqual(region_state({"source": "copied"}), "approved")
        self.assertEqual(region_state({"source": "fitted"}), "approved")
        self.assertEqual(region_state({"source": "inpainted"}), "candidate_ready")
        self.assertEqual(region_state({"source": "unknown"}), "unknown")
        self.assertEqual(region_state({}), "unknown")

    def test_unknown_pixels_falls_back_to_region_size(self):
        self.assertEqual(region_unknown_pixels({"state": "unknown", "pixels": 40}), 40)
        self.assertEqual(region_unknown_pixels(
            {"state": "unknown", "pixels": 40, "unknownPixels": 12}), 12)
        # approved 的区域不贡献未知像素
        self.assertEqual(region_unknown_pixels({"state": "approved", "pixels": 40}), 0)

    def test_region_states_constant_covers_the_machine(self):
        for name in ("unknown", "generating", "candidate_ready", "approved",
                     "rejected", "superseded", "failed", "stale"):
            self.assertIn(name, REGION_STATES)


class CoverageLedgerTests(unittest.TestCase):
    """方案 §7/§9.5：账本必须能回答「还剩多少像素没被可信结果覆盖」。"""

    def _regions(self):
        return [
            {"id": "region-original", "source": "original", "state": "approved",
             "pixels": 0},
            {"id": "region-1-aaaa", "source": "copied", "state": "approved", "pixels": 6000},
            {"id": "region-2-bbbb", "source": "unknown", "state": "unknown",
             "pixels": 5000, "unknownPixels": 5000},
        ]

    def test_sum_of_buckets_equals_canvas_area(self):
        cov = background_coverage(self._regions(), width=200, height=200)
        total = (cov["originalPixels"] + cov["deterministicPixels"] + cov["confirmedPixels"]
                 + cov["candidatePixels"] + cov["uncoveredPixels"])
        self.assertEqual(total, 200 * 200)
        self.assertEqual(cov["totalPixels"], 40000)
        self.assertEqual(cov["deterministicPixels"], 6000)
        self.assertEqual(cov["uncoveredPixels"], 5000)
        self.assertEqual(cov["originalPixels"], 40000 - 6000 - 5000)

    def test_uncovered_uses_mask_union_not_sum(self):
        """相交的区域不能重复计数（方案 §9.5）。

        两个 unknown 区域各 10000 像素，但 mask 重叠 5000 ⇒ 未覆盖必须是 15000 而不是 20000。
        """
        a = _mask((200, 200), (0, 0, 99, 99))          # 100×100
        b = _mask((200, 200), (50, 50, 149, 149))      # 100×100，与 a 重叠 50×50
        self.assertEqual(mask_pixels(a), 10000)
        self.assertEqual(union_pixels([a, b], (200, 200)), 17500)
        regions = [
            {"id": "region-original", "source": "original", "state": "approved", "pixels": 0},
            {"id": "u1", "source": "unknown", "state": "unknown", "pixels": 10000},
            {"id": "u2", "source": "unknown", "state": "unknown", "pixels": 10000},
        ]
        cov = background_coverage(regions, width=200, height=200,
                                  region_masks={"u1": a, "u2": b})
        self.assertEqual(cov["uncoveredPixels"], 17500)
        self.assertTrue(cov["maskBased"])
        # 账目仍然平
        self.assertEqual(cov["originalPixels"], 40000 - 17500)

    def test_region_gaps_are_not_missed(self):
        """区域之间有缝隙时，并把两块的 mask 并起来仍然不漏计（方案 §9.5）。"""
        a = _mask((200, 200), (0, 0, 49, 199))
        b = _mask((200, 200), (150, 0, 199, 199))
        regions = [
            {"id": "region-original", "source": "original", "state": "approved", "pixels": 0},
            {"id": "u1", "source": "unknown", "state": "unknown", "pixels": 10000},
            {"id": "u2", "source": "unknown", "state": "unknown", "pixels": 10000},
        ]
        cov = background_coverage(regions, width=200, height=200,
                                  region_masks={"u1": a, "u2": b})
        self.assertEqual(cov["uncoveredPixels"], 20000)

    def test_candidate_and_confirmed_are_separate_buckets(self):
        regions = [
            {"id": "region-original", "source": "original", "state": "approved", "pixels": 0},
            {"id": "r-cand", "source": "unknown", "state": "candidate_ready", "pixels": 3000},
            {"id": "r-ok", "source": "inpainted", "state": "approved", "pixels": 2000},
        ]
        cm = _mask((100, 100), (0, 0, 49, 49))        # 2500
        cov = background_coverage(regions, width=100, height=100,
                                  region_masks={"r-cand": cm})
        self.assertEqual(cov["candidatePixels"], 2500)
        self.assertEqual(cov["confirmedPixels"], 2000)
        self.assertEqual(cov["uncoveredPixels"], 0)
        self.assertFalse(cov["complete"], "有未采纳候选 ⇒ 还不算完成")

    def test_outside_changed_is_reported_and_blocks_completion(self):
        regions = [{"id": "region-original", "source": "original", "state": "approved",
                    "pixels": 400}]
        cov = background_coverage(regions, width=20, height=20, region_masks={},
                                  outside_changed=7)
        self.assertEqual(cov["outsideChanged"], 7)

    def test_budget_is_reported_when_available(self):
        class B:
            limit = 5
            remaining = 2

        regions = [{"id": "region-original", "source": "original", "state": "approved",
                    "pixels": 400}]
        cov = background_coverage(regions, width=20, height=20, budget=B(), budget_used=3)
        self.assertEqual(cov["aiCalls"], 3)
        self.assertEqual(cov["budgetLimit"], 5)
        self.assertEqual(cov["budgetRemaining"], 2)

    def test_ledger_lines_match_the_plan_wording(self):
        regions = [
            {"id": "region-original", "source": "original", "state": "approved", "pixels": 0},
            {"id": "region-7", "source": "unknown", "state": "unknown", "pixels": 900},
        ]
        cov = background_coverage(regions, width=100, height=100,
                                  region_masks={"region-7": _mask((100, 100), (0, 0, 29, 29))})
        lines = coverage_ledger_lines(cov)
        self.assertEqual(lines["pending"], 900)
        self.assertEqual(lines["rebuilt"], "9100 / 10000")
        self.assertIn("region-7", lines["regionIds"])


class StatusAndReuseTests(unittest.TestCase):
    def test_status_only_from_region_ledger(self):
        def status(regions, masks=None, **kw):
            cov = background_coverage(regions, width=100, height=100,
                                      region_masks=masks or {}, **kw)
            return derive_background_status(regions, cov)

        self.assertEqual(status([{"id": "region-original", "source": "original",
                                  "state": "approved", "pixels": 10000}],
                                {"region-original": _mask((100, 100), (0, 0, 99, 99))}),
                         "original_plus_deterministic")
        self.assertEqual(status([{"id": "u", "source": "unknown", "state": "unknown",
                                  "pixels": 400}],
                                {"u": _mask((100, 100), (0, 0, 19, 19))}),
                         "needs_manual_repair")
        self.assertEqual(status([{"id": "c", "source": "unknown",
                                  "state": "candidate_ready", "pixels": 400}],
                                {"c": _mask((100, 100), (0, 0, 19, 19))}),
                         "candidate")
        self.assertEqual(status([{"id": "i", "source": "inpainted",
                                  "state": "approved", "pixels": 400}],
                                {"i": _mask((100, 100), (0, 0, 19, 19))}),
                         "reviewed_inpaint")
        self.assertEqual(status([{"id": "f", "source": "unknown", "state": "failed",
                                  "pixels": 0}]), "needs_manual_repair")
        # stale 优先于一切（依赖的前景 / 源图 revision 变了）
        self.assertEqual(status([{"id": "s", "source": "copied", "state": "stale",
                                  "pixels": 0}]), "stale")

    def test_reusable_requires_a_trustworthy_ledger(self):
        clean = [{"id": "region-original", "source": "original", "state": "approved",
                  "pixels": 10000}]
        self.assertTrue(asset_reusable(clean, background_coverage(
            clean, width=100, height=100, region_masks={})))
        # ① 有未知区域却没有它的 mask ⇒ 账本不可信（只能退回像素求和，重复计数会失真）⇒ 不许入库
        bad = [{"id": "u", "source": "unknown", "state": "unknown", "pixels": 100}]
        cov_no_mask = background_coverage(bad, width=100, height=100)
        self.assertFalse(cov_no_mask["maskBased"])
        self.assertFalse(asset_reusable(bad, cov_no_mask))
        # ② 有未知像素 ⇒ 不许入库（即便有 mask）
        cov = background_coverage(bad, width=100, height=100,
                                  region_masks={"u": _mask((100, 100), (0, 0, 9, 9))})
        self.assertTrue(cov["maskBased"])
        self.assertFalse(asset_reusable(bad, cov))
        # ③ 还有未采纳候选 ⇒ 也不许入库（方案 §9.8）
        cand = [{"id": "c", "source": "unknown", "state": "candidate_ready", "pixels": 100}]
        self.assertFalse(asset_reusable(cand, background_coverage(
            cand, width=100, height=100,
            region_masks={"c": _mask((100, 100), (0, 0, 9, 9))})))
        # ④ 遮罩外被改写 ⇒ 不许入库
        self.assertFalse(asset_reusable(clean, background_coverage(
            clean, width=100, height=100, region_masks={}, outside_changed=3)))


class WriteScopeTests(unittest.TestCase):
    """方案 §5.1：effectiveWriteMask = userWriteMask ∩ regionMask − protectMask。"""

    def setUp(self):
        self.size = (100, 100)
        self.region = _mask(self.size, (20, 20, 59, 59))     # 1600 px

    def test_default_write_scope_is_the_region(self):
        eff, info = effective_write_mask(self.region, None, None, size=self.size)
        self.assertEqual(info["effectivePixels"], 1600)
        self.assertEqual(mask_pixels(eff), 1600)
        self.assertEqual(len(info["effectiveHash"]), 64)

    def test_user_write_is_intersected_and_protect_is_subtracted(self):
        write = _mask(self.size, (0, 0, 79, 99))      # 用户画了一大片（含区域外，但不是全画布）
        protect = _mask(self.size, (20, 20, 29, 59))  # 保护左侧 10 列
        # 用户遮罩超出区域 ⇒ 阻断（这是「陈旧/错误遮罩」的判据）
        with self.assertRaises(WriteScopeError) as err:
            effective_write_mask(self.region, write, protect, size=self.size)
        self.assertEqual(err.exception.code, "mask_outside_region")
        # 夹进区域内之后正常
        clipped = Image.new("L", self.size, 0)
        clipped.paste(write, (0, 0), self.region)
        eff, info = effective_write_mask(self.region, clipped, protect, size=self.size)
        self.assertEqual(info["writePixels"], 1600)
        self.assertEqual(info["protectPixels"], 400)     # 区域内被保护的那 10×40
        self.assertEqual(info["effectivePixels"], 1200)
        self.assertEqual(mask_pixels(eff), 1200)

    def test_empty_and_full_canvas_are_blocked(self):
        with self.assertRaises(WriteScopeError) as err:
            effective_write_mask(self.region, Image.new("L", self.size, 0), None,
                                 size=self.size)
        self.assertEqual(err.exception.code, "mask_empty")
        with self.assertRaises(WriteScopeError) as err:
            effective_write_mask(self.region, Image.new("L", self.size, 255), None,
                                 size=self.size)
        self.assertEqual(err.exception.code, "mask_full_canvas")

    def test_protect_eating_everything_is_blocked(self):
        """扣掉保护区后什么都不剩 ⇒ 阻断（否则白花一次预算）。"""
        with self.assertRaises(WriteScopeError) as err:
            effective_write_mask(self.region, None, self.region, size=self.size)
        self.assertEqual(err.exception.code, "mask_effective_empty")

    def test_stale_revision_is_blocked(self):
        with self.assertRaises(WriteScopeError) as err:
            effective_write_mask(self.region, None, None, size=self.size,
                                 expected_revision=2, revision=5)
        self.assertEqual(err.exception.code, "revision_stale")

    def test_size_mismatch_is_blocked(self):
        with self.assertRaises(WriteScopeError) as err:
            effective_write_mask(self.region, Image.new("L", (50, 50), 255), None,
                                 size=self.size)
        self.assertEqual(err.exception.code, "mask_dimensions")

    def test_default_protect_mask_unions_inputs(self):
        keep = _mask(self.size, (0, 0, 9, 9))
        prot = _mask(self.size, (60, 60, 79, 79))
        out = build_region_protect_mask(self.size, protect_mask=prot, keep_mask=keep)
        self.assertEqual(mask_pixels(out), 100 + 400)


class CandidateQualityTests(unittest.TestCase):
    """方案 §5.3 第 5 步 / §9.2 / §9.3：遮罩外与保护区必须逐像素不变。"""

    def setUp(self):
        self.size = (80, 80)
        self.base = Image.new("RGB", self.size, (120, 120, 120))
        self.write = _mask(self.size, (30, 30, 49, 49))

    def test_clean_patch_passes(self):
        merged = self.base.copy()
        noise = Image.new("RGB", (20, 20), (122, 118, 121))
        merged.paste(noise, (30, 30))
        q = candidate_quality(self.base, merged, self.write)
        self.assertTrue(q["ok"], q)
        self.assertEqual(q["metrics"]["outsideChanged"], 0)
        self.assertEqual(q["metrics"]["protectedChanged"], 0)

    def test_outside_mask_change_is_rejected(self):
        merged = self.base.copy()
        merged.paste(Image.new("RGB", (10, 10), (255, 0, 0)), (0, 0))
        q = candidate_quality(self.base, merged, self.write)
        self.assertFalse(q["ok"])
        self.assertIn("outside_changed", q["reasons"])
        self.assertEqual(q["metrics"]["outsideChanged"], 100)

    def test_protected_area_change_is_rejected(self):
        protect = _mask(self.size, (30, 30, 39, 49))
        merged = self.base.copy()
        noise = Image.new("RGB", (20, 20), (121, 119, 122))
        merged.paste(noise, (30, 30))
        merged.paste(Image.new("RGB", (10, 20), (0, 0, 0)), (30, 30))
        # 写入范围 = 区域 − 保护区，所以保护区内的改动会被算到「遮罩外」
        write = _mask(self.size, (40, 30, 49, 49))
        q = candidate_quality(self.base, merged, write, protect)
        self.assertFalse(q["ok"])
        self.assertIn("protected_changed", q["reasons"])

    def test_tone_jump_is_flagged(self):
        merged = self.base.copy()
        merged.paste(Image.new("RGB", (20, 20), (250, 250, 250)), (30, 30))
        q = candidate_quality(self.base, merged, self.write)
        self.assertFalse(q["ok"])
        self.assertIn("tone", q["reasons"])
        self.assertGreater(q["metrics"]["tone"], 30)

    def test_empty_write_mask_is_rejected(self):
        with self.assertRaises(WriteScopeError):
            candidate_quality(self.base, self.base.copy(), Image.new("L", self.size, 0))


class CandidateRecordTests(unittest.TestCase):
    def test_record_keeps_every_field_the_plan_requires(self):
        rec = candidate_record(
            candidate_id="cand_x", task_id="t", region_id="r", operation_id="op",
            provider="p", model="m", mask_revision=2, document_revision=1,
            write_hash="wh", protect_hash="ph", effective_hash="eh", source_hash="sh",
            status="ready", created_at=1.0)
        for key in ("candidateId", "taskId", "regionId", "operationId", "provider",
                    "model", "maskRevision", "documentRevision", "writeMaskHash",
                    "protectMaskHash", "effectiveMaskHash", "sourceHash", "outputHash",
                    "status", "decision", "quality", "url", "diffUrl", "appliedPixels"):
            self.assertIn(key, rec, key)


class StableRegionIdTests(unittest.TestCase):
    """方案 §6：区域 id 不能依赖数组序号，否则重分割后候选会贴错区域。"""

    def _plate(self):
        img = Image.new("RGBA", (96, 96), (200, 200, 200, 255))
        ImageDraw.Draw(img).rectangle((36, 36, 59, 59), fill=(30, 30, 30, 255))
        hole = Image.new("L", (96, 96), 0)
        ImageDraw.Draw(hole).rectangle((36, 36, 59, 59), fill=255)
        return img, hole

    def test_ids_are_stable_and_not_array_indexed(self):
        img, hole = self._plate()
        _, regions_a, _ = build_clean_plate(img, hole)
        _, regions_b, _ = build_clean_plate(img, hole)
        ids_a = [r["id"] for r in regions_a]
        ids_b = [r["id"] for r in regions_b]
        self.assertEqual(ids_a, ids_b, "同样输入必须给出同样的区域 id")
        self.assertNotIn("region-1", ids_a)
        rebuilt = [r for r in regions_a if r.get("source") != "original"]
        for r in rebuilt:
            self.assertRegex(r["id"], r"^region-\d+-[0-9a-f]{8}$")

    def test_every_region_carries_a_state(self):
        img, hole = self._plate()
        _, regions, _ = build_clean_plate(img, hole)
        for r in regions:
            self.assertIn(r.get("state"), REGION_STATES, r.get("id"))
            self.assertIn("unknownPixels", r)


if __name__ == "__main__":
    unittest.main()
