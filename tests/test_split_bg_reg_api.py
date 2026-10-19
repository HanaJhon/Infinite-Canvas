# -*- coding: utf-8 -*-
"""背景区域闭环的接口级测试（方案《背景AI修补仍未生效》§9 验收标准 1—4、8）。

覆盖：
  ① unknown 区域 → 保存写入范围（revision 递增、非法遮罩阻断）；
  ② 生成候选 → **主背景资产完全不变**；
  ③ 采纳 → 只在 effectiveWriteMask 内改动、未知像素减少、状态升级；
  ④ 拒绝 / 失败 → 主背景不变；
  ⑤ 遮罩 revision 变了 ⇒ 旧候选不可采纳（superseded）；
  ⑥ 还有未知像素 ⇒ 不许进素材库。
全部零真实模型调用（`split_call_image_model` 用桩）。
"""

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageChops, ImageDraw

import main

# 🚨 元素级重构（方案 §2.1 / §14 P0）：main 默认冻结旧拆分写接口。
#    本文件验证的是**旧实现本身**（P5 阶段才删除），所以整个模块显式解冻；
#    「冻结行为」由 tests/test_element_freeze.py 专门验证。
main.LEGACY_SPLIT_WRITES_FROZEN = False
from backend.split_budget import SplitLayersBudget
from backend.split_surfaces import build_clean_plate

# 64×64 纯色 + 只剩 4px 可信边（pad=4）⇒ 确定性地产出 1 个 unknown 区域 3136px。
# 这个构型是实测挑出来的：pad≤2 时洞外无可信样本、pad≥8 时证据足够会被正常补上。
_SIZE = (64, 64)
_PAD = 4


def _build_task(task_id):
    """搭一个带 unknown 背景区域的真实任务状态。"""
    src = Image.new("RGBA", _SIZE, (180, 180, 180, 255))
    hole = Image.new("L", _SIZE, 0)
    ImageDraw.Draw(hole).rectangle((_PAD, _PAD, _SIZE[0] - 1 - _PAD,
                                    _SIZE[1] - 1 - _PAD), fill=255)
    region_masks = {}
    plate, regions, meta = build_clean_plate(src, hole, region_masks=region_masks)
    unknown = [r for r in regions if r["source"] == "unknown"]
    assert unknown, "测试构型必须产出 unknown 区域"
    coverage = main.background_coverage(
        regions, width=_SIZE[0], height=_SIZE[1], region_masks=region_masks)
    # 真写一份资产进索引：素材库闸门要按账本自证干净，不能只摆一个内存字典
    asset = main.split_background_asset_write(
        plate, hole, source_hash="s",
        meta={**meta, "status": "needs_manual_repair", "coverage": coverage,
              "kind": "clean_plate", "method": "surface_aware_clean_plate",
              "detail": "test"},
        revision=1, task_id=task_id, asset_id="bgtest0001", label="背景",
        regions=regions, write_mask=hole,
        protect_mask=Image.new("L", _SIZE, 0))
    entries = [
        {"id": "bg", "kind": "element", "z": 0, "name": "背景",
         "bbox": [0, 0, _SIZE[0], _SIZE[1]], "url": asset["url"],
         "provenance": "local_repaired_background", "status": "pending",
         "background_asset": asset},
        {"id": "L1", "kind": "element", "z": 1, "name": "主体",
         "bbox": [_PAD, _PAD, 8, 8], "url": "/l.png", "provenance": "source",
         "method": "local"},
    ]
    state = {
        "src_path": "t.png", "src_rgba": src,
        "width": _SIZE[0], "height": _SIZE[1], "source": {"sha256": "s"},
        "entries": entries,
        "plates": {"bg": plate, "L1": Image.new("RGBA", _SIZE, (0, 0, 0, 0))},
        "masks": {"L1": Image.new("L", _SIZE, 0)},
        "issues": [], "checks": {},
        "text_hole": Image.new("L", _SIZE, 0),
        "pure_background": True,
        "budget_limit": 3, "budget_obj": SplitLayersBudget(3),
        "payload": main.SplitLayersRequest(image_url="/assets/in.png", budget=3),
        "background_asset": entries[0]["background_asset"],
        "bg_regions": regions,
        "bg_region_masks": region_masks,
        "bg_removed_hole": hole,
        "bg_write_mask": hole,
        "bg_protect_mask": Image.new("L", _SIZE, 0),
        "bg_diff": ImageChops.difference(plate.convert("RGB"),
                                         src.convert("RGB")).convert("L"),
        "bg_clean_meta": {**meta, "outsideChanged": 0},
        "bg_coverage": coverage,
        "bg_status": "needs_manual_repair",
        "bg_region_write": {}, "bg_region_protect": {}, "bg_region_revision": {},
        "bg_candidates": {}, "bg_candidate_ids": {}, "bg_candidate_images": {},
        "bg_doc_revision": 0,
    }
    main.split_state_put(task_id, state)
    main.CANVAS_TASKS[task_id] = {"id": task_id, "status": "review",
                                 "result": {"layers": entries, "phase": "review"}}
    return state, unknown[0], region_masks[unknown[0]["id"]]


class BgRegionLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_bg_dir = main.BACKGROUND_ASSET_DIR
        self.old_bg_index = main.BACKGROUND_ASSET_INDEX
        self.old_upload = main.LOCAL_UPLOAD_DIR
        main.BACKGROUND_ASSET_DIR = os.path.join(self.tmp.name, "backgrounds")
        main.BACKGROUND_ASSET_INDEX = os.path.join(main.BACKGROUND_ASSET_DIR, "index.json")
        main.LOCAL_UPLOAD_DIR = os.path.join(self.tmp.name, "uploads")
        self.task_id = "split_bg_loop_test"
        self.old_save = main.split_save_png
        self.old_call = main.split_call_image_model
        self.old_channels = main.split_candidate_channels
        self.old_from_url = main.output_file_from_url
        self.calls = []

    def tearDown(self):
        main.BACKGROUND_ASSET_DIR = self.old_bg_dir
        main.BACKGROUND_ASSET_INDEX = self.old_bg_index
        main.LOCAL_UPLOAD_DIR = self.old_upload
        main.split_save_png = self.old_save
        main.split_call_image_model = self.old_call
        main.split_candidate_channels = self.old_channels
        main.output_file_from_url = self.old_from_url
        main.SPLIT_TASK_STATE.pop(self.task_id, None)
        main.CANVAS_TASKS.pop(self.task_id, None)
        self.tmp.cleanup()

    def _stub(self, *, fill=(210, 120, 60), fail=False):
        """桩：模型返回一张把「黄色遮罩区」涂成 fill 的图（模拟模型补出的内容）。"""
        path = os.path.join(self.tmp.name, "model_out.png")
        async def fake_call(payload, img, prompt, extra_images=None, budget=None,
                            operation=None):
            self.calls.append(operation or {})
            if fail:
                raise RuntimeError("stub failure")
            out = img.convert("RGB").copy()
            mask = extra_images[0].convert("RGBA")
            yellow = Image.new("L", out.size, 0)
            yp = yellow.load()
            mp = mask.load()
            for y in range(out.size[1]):
                for x in range(out.size[0]):
                    r, g, b, _a = mp[x, y]
                    if r > 200 and g > 150 and b < 80:
                        yp[x, y] = 255
            out.paste(Image.new("RGB", out.size, fill), (0, 0), yellow)
            out.save(path, format="PNG")
            return path
        main.split_call_image_model = fake_call
        main.output_file_from_url = lambda url: url

        async def fake_save(image, prefix="split_layer_"):
            safe = os.path.join(self.tmp.name, f"{prefix}out.png")
            image.convert("RGBA").save(safe, format="PNG")
            return safe
        main.split_save_png = fake_save
        main.split_candidate_channels = lambda kind, payload: [("stub", "model")]

    def _run(self, coro):
        return asyncio.run(coro)

    # ------------------------------------------------------------------

    def test_coverage_starts_with_uncovered_pixels(self):
        async def run():
            _, region, _ = _build_task(self.task_id)
            out = await main.get_background_state(self.task_id)
            self.assertGreater(out["coverage"]["uncoveredPixels"], 0)
            self.assertEqual(out["status"], "needs_manual_repair")
            self.assertEqual(out["coverage"]["openRegionIds"], [region["id"]])
            # 账本账目必须平
            cov = out["coverage"]
            self.assertEqual(
                cov["originalPixels"] + cov["deterministicPixels"]
                + cov["confirmedPixels"] + cov["candidatePixels"]
                + cov["uncoveredPixels"], _SIZE[0] * _SIZE[1])
            # ⑨ 有未知像素 ⇒ 不许进素材库
            with self.assertRaises(main.HTTPException) as err:
                await main.save_background_asset_to_library("bgtest0001")
            self.assertEqual(err.exception.status_code, 422)
        self._run(run())

    def test_save_write_scope_bumps_revision_and_rejects_bad_masks(self):
        async def run():
            _, region, rmask = _build_task(self.task_id)
            rid = region["id"]
            out = await main.update_background_region_mask(
                self.task_id, rid,
                main.SplitLayersBgMaskRequest(region_id=rid, hints={}, reset=True,
                                              expected_revision=0))
            self.assertEqual(out["revision"], 1)
            self.assertEqual(out["region"]["maskRevision"], 1)
            # 陈旧 revision 被阻断
            with self.assertRaises(main.HTTPException) as err:
                await main.update_background_region_mask(
                    self.task_id, rid,
                    main.SplitLayersBgMaskRequest(region_id=rid, expected_revision=0))
            self.assertEqual(err.exception.status_code, 409)
            # 画到区域外 → 夹进区域内（用户笔刷越界不算错误）
            out2 = await main.update_background_region_mask(
                self.task_id, rid,
                main.SplitLayersBgMaskRequest(
                    region_id=rid, hints={"strokes": [
                        {"mode": "include", "points": [[0, 0, 40], [63, 63, 40]]}]},
                    expected_revision=1))
            self.assertLessEqual(out2["writeMask"]["writePixels"],
                                 out2["writeMask"]["regionPixels"])
        self._run(run())

    def test_candidate_does_not_touch_main_asset(self):
        async def run():
            state, region, _ = _build_task(self.task_id)
            self._stub()
            rid = region["id"]
            before_plate = state["plates"]["bg"].copy()
            before_asset = dict(state["entries"][0]["background_asset"])
            out = await main.create_background_candidate(
                self.task_id, rid, main.SplitLayersBgCandidateRequest(region_id=rid))
            self.assertTrue(out["ok"], out)
            cand = out["candidate"]
            # ① 能追到唯一 region id 与遮罩 hash
            self.assertEqual(cand["regionId"], rid)
            self.assertEqual(len(cand["writeMaskHash"]), 64)
            self.assertEqual(len(cand["effectiveMaskHash"]), 64)
            self.assertEqual(cand["status"], "ready")
            self.assertEqual(cand["maskEditMode"], "local_edit")
            # ② 主资产完全没变
            after = main.split_state_get(self.task_id)
            self.assertEqual(after["entries"][0]["background_asset"]["revision"],
                             before_asset["revision"])
            self.assertTrue(ImageChops.difference(
                after["plates"]["bg"].convert("RGB"),
                before_plate.convert("RGB")).getbbox() is None,
                "生成候选阶段绝不允许改动主背景")
            # 候选计入账本，未知像素随之变成「待确认候选」
            cov = out["coverage"]
            self.assertGreater(cov["candidatePixels"], 0)
            self.assertEqual(cov["uncoveredPixels"], 0)
            self.assertEqual(out["status"], "candidate")
            # ③ 模型调用带上了候选 id（可追溯）
            self.assertEqual(self.calls[0].get("candidate_id"), cand["candidateId"])
        self._run(run())

    def test_accept_applies_only_inside_write_mask(self):
        async def run():
            state, region, _ = _build_task(self.task_id)
            self._stub(fill=(220, 130, 70))
            rid = region["id"]
            before = state["plates"]["bg"].copy()
            made = await main.create_background_candidate(
                self.task_id, rid, main.SplitLayersBgCandidateRequest(region_id=rid))
            cand_id = made["candidate"]["candidateId"]
            out = await main.accept_background_candidate(self.task_id, cand_id)
            self.assertTrue(out["ok"])
            self.assertGreater(out["appliedPixels"], 0)
            # ② 未知像素归零、状态升级
            self.assertEqual(out["coverage"]["uncoveredPixels"], 0)
            self.assertEqual(out["status"], "reviewed_inpaint")
            after = main.split_state_get(self.task_id)["plates"]["bg"]
            diff = ImageChops.difference(after.convert("RGB"),
                                         before.convert("RGB")).convert("L")
            # ③ 只在写入范围内改变：区域外必须逐像素不变
            region_mask = main.split_state_get(self.task_id)["bg_region_masks"][rid]
            outside = ImageChops.multiply(diff, ImageChops.invert(region_mask))
            self.assertEqual(sum(outside.histogram()[1:]), 0,
                             "采纳候选后区域外必须逐像素等于改动前的背景")
            self.assertIsNotNone(diff.getbbox(), "区域内应该确实被改写了")
            # 资产 revision 递增、账本进资产、状态可复用
            self.assertEqual(out["asset"]["revision"], 2)
            self.assertEqual(out["asset"]["coverage"]["uncoveredPixels"], 0)
            saved = await main.save_background_asset_to_library(out["asset"]["assetId"])
            self.assertTrue(saved["item"]["url"].startswith("/api/storage-file"))
        self._run(run())

    def test_reject_keeps_main_asset_and_restores_region_state(self):
        async def run():
            state, region, _ = _build_task(self.task_id)
            self._stub()
            rid = region["id"]
            before = state["plates"]["bg"].copy()
            made = await main.create_background_candidate(
                self.task_id, rid, main.SplitLayersBgCandidateRequest(region_id=rid))
            cand_id = made["candidate"]["candidateId"]
            out = await main.reject_background_candidate(self.task_id, cand_id)
            self.assertEqual(out["candidate"]["status"], "rejected")
            self.assertGreater(out["coverage"]["uncoveredPixels"], 0)
            self.assertEqual(out["status"], "needs_manual_repair")
            after = main.split_state_get(self.task_id)["plates"]["bg"]
            self.assertTrue(ImageChops.difference(after.convert("RGB"),
                                                  before.convert("RGB")).getbbox() is None)
        self._run(run())

    def test_new_mask_revision_supersedes_old_candidate(self):
        async def run():
            _, region, _ = _build_task(self.task_id)
            self._stub()
            rid = region["id"]
            made = await main.create_background_candidate(
                self.task_id, rid, main.SplitLayersBgCandidateRequest(region_id=rid))
            cand_id = made["candidate"]["candidateId"]
            # 用户改了写入范围 → 旧候选作废
            await main.update_background_region_mask(
                self.task_id, rid,
                main.SplitLayersBgMaskRequest(region_id=rid, reset=True,
                                              expected_revision=0))
            got = await main.get_background_candidate(self.task_id, cand_id)
            self.assertEqual(got["candidate"]["status"], "superseded")
            with self.assertRaises(main.HTTPException) as err:
                await main.accept_background_candidate(self.task_id, cand_id)
            self.assertEqual(err.exception.status_code, 409)
        self._run(run())

    def test_failed_generation_leaves_main_asset_intact(self):
        async def run():
            state, region, _ = _build_task(self.task_id)
            self._stub(fail=True)
            rid = region["id"]
            before = state["plates"]["bg"].copy()
            out = await main.create_background_candidate(
                self.task_id, rid, main.SplitLayersBgCandidateRequest(region_id=rid))
            self.assertFalse(out["ok"])
            self.assertEqual(out["candidate"]["status"], "failed")
            after = main.split_state_get(self.task_id)["plates"]["bg"]
            self.assertTrue(ImageChops.difference(after.convert("RGB"),
                                                  before.convert("RGB")).getbbox() is None)
        self._run(run())

    def test_budget_exhausted_is_429_and_protects_main_asset(self):
        async def run():
            state, region, _ = _build_task(self.task_id)
            self._stub()
            state["budget_obj"] = SplitLayersBudget(0)
            rid = region["id"]
            with self.assertRaises(main.HTTPException) as err:
                await main.create_background_candidate(
                    self.task_id, rid, main.SplitLayersBgCandidateRequest(region_id=rid))
            self.assertEqual(err.exception.status_code, 429)
            self.assertEqual(len(self.calls), 0, "预算为 0 时不许调用模型")
        self._run(run())

    def test_restore_region_returns_original_pixels(self):
        async def run():
            state, region, _ = _build_task(self.task_id)
            rid = region["id"]
            out = await main.restore_background_region(self.task_id, rid)
            self.assertEqual(out["region"]["source"], "original")
            self.assertEqual(out["coverage"]["uncoveredPixels"], 0)
            self.assertEqual(out["status"], "original_plus_deterministic")
            plate = main.split_state_get(self.task_id)["plates"]["bg"]
            self.assertEqual(plate.getpixel((30, 30)), state["src_rgba"].getpixel((30, 30)))
        self._run(run())

    def test_unknown_region_is_isolated_not_silently_showing_subject(self):
        """方案 §4：clean plate 视图里不能在 unknown 区域静默显示原主体。"""
        async def run():
            _build_task(self.task_id)
            out = await main.get_background_state(self.task_id)
            cov = out["coverage"]
            # 待处理区域必须能被前端单独拿到（画棋盘格 / 醒目标记）
            self.assertTrue(cov["openRegionIds"])
            folder = main._bg_asset_dir("bgtest0001")
            self.assertTrue(os.path.isdir(folder))
        self._run(run())


if __name__ == "__main__":
    unittest.main()
