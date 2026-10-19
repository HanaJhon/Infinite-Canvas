# -*- coding: utf-8 -*-
"""背景资产（方案 §5/§6/§9）的接口级测试：完整画布、状态机、素材库复用、stale。"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw

import main

# 🚨 元素级重构（方案 §2.1 / §14 P0）：main 默认冻结旧拆分写接口。
#    本文件验证的是**旧实现本身**（P5 阶段才删除），所以整个模块显式解冻；
#    「冻结行为」由 tests/test_element_freeze.py 专门验证。
main.LEGACY_SPLIT_WRITES_FROZEN = False
from backend.split_background import build_background


class BackgroundAssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_bg_dir = main.BACKGROUND_ASSET_DIR
        self.old_bg_index = main.BACKGROUND_ASSET_INDEX
        self.old_upload = main.LOCAL_UPLOAD_DIR
        main.BACKGROUND_ASSET_DIR = os.path.join(self.tmp.name, "backgrounds")
        main.BACKGROUND_ASSET_INDEX = os.path.join(main.BACKGROUND_ASSET_DIR, "index.json")
        main.LOCAL_UPLOAD_DIR = os.path.join(self.tmp.name, "uploads")

    def tearDown(self):
        main.BACKGROUND_ASSET_DIR = self.old_bg_dir
        main.BACKGROUND_ASSET_INDEX = self.old_bg_index
        main.LOCAL_UPLOAD_DIR = self.old_upload
        self.tmp.cleanup()

    # ---------- 商品模式：确定性底板 + 完整资产 ----------

    def test_product_background_asset_is_complete_and_reusable(self):
        source = Image.new("RGBA", (48, 32), "white")
        ImageDraw.Draw(source).rectangle((12, 6, 28, 25), fill=(40, 80, 120, 255))
        task_id = "split_bg_asset_test"
        payload = main.SplitLayersRequest(image_url="/assets/input/t.png",
                                          task_mode="product", budget=9)
        old_save = main.split_save_png

        async def fake_save(_image, prefix="split_layer_"):
            return f"/assets/{prefix}t.png"

        async def exercise():
            main.split_save_png = fake_save
            main.CANVAS_TASKS[task_id] = {"id": task_id, "status": "queued", "result": None}
            try:
                result = await main.build_product_split_result(
                    task_id, payload, "t.png", source, {"sha256": "abc"}, lambda *_: None)
                main.CANVAS_TASKS[task_id]["result"] = result
                main.CANVAS_TASKS[task_id]["status"] = "review"
                asset = result["background_asset"]
                # §6：必须是**完整画布尺寸**，不是主体周围的小裁切
                self.assertEqual((asset["width"], asset["height"]), source.size)
                self.assertTrue(asset["complete"])
                self.assertEqual(asset["status"], "original_plus_deterministic")
                self.assertTrue(asset["reusable"])
                self.assertEqual(asset["kind"], "solid")
                # 四件套都在磁盘上
                folder = main._bg_asset_dir(asset["assetId"])
                for name in ("background.png", "background-preview.jpg",
                             "background-mask.png", "background-provenance.json"):
                    self.assertTrue(os.path.exists(os.path.join(folder, name)), name)
                # background.png 逐像素等于目标色（§5.1）
                with Image.open(os.path.join(folder, "background.png")) as bg_img:
                    self.assertEqual(bg_img.size, source.size)
                    self.assertEqual(bg_img.convert("RGBA").getextrema(),
                                     ((255, 255), (255, 255), (255, 255), (255, 255)))
                # §4.4 三背景验收预览 + 客观结论
                self.assertEqual(set(result["verify_previews"]),
                                 {"white", "dark", "checker"})
                self.assertEqual(set(result["objective"]),
                                 {"white", "dark", "checker", "structure"})
                # GET /api/assets/{id}
                got = await main.get_background_asset(asset["assetId"])
                self.assertEqual(got["asset"]["assetId"], asset["assetId"])
                self.assertEqual(got["provenance"]["qualityState"], "original_plus_deterministic")
                self.assertEqual(got["provenance"]["colorSpace"], "sRGB")
                self.assertEqual(len(got["provenance"]["plateSha256"]), 64)
                # download
                resp = await main.download_background_asset(asset["assetId"], "background")
                self.assertTrue(str(getattr(resp, "path", "")).endswith("background.png"))
                prov = await main.download_background_asset(asset["assetId"], "provenance")
                self.assertTrue(str(getattr(prov, "path", "")).endswith("background-provenance.json"))
                with self.assertRaises(main.HTTPException) as bad:
                    await main.download_background_asset(asset["assetId"], "nope")
                self.assertEqual(bad.exception.status_code, 400)
                # 存素材库 → 供其他画布复用
                saved = await main.save_background_asset_to_library(asset["assetId"])
                self.assertTrue(saved["item"]["url"].startswith("/api/storage-files/local/"))
                self.assertTrue(os.path.exists(
                    os.path.join(main.LOCAL_UPLOAD_DIR, saved["item"]["file"])))
                self.assertEqual(saved["asset"]["libraryItem"]["id"], saved["item"]["id"])
            finally:
                main.CANVAS_TASKS.pop(task_id, None)
                main.SPLIT_TASK_STATE.pop(task_id, None)
                main.split_save_png = old_save

        asyncio.run(exercise())

    def test_speculative_asset_is_blocked_from_library(self):
        plate = Image.new("RGBA", (16, 16), (10, 20, 30, 255))
        asset = main.split_background_asset_write(
            plate, None, source_hash="x", meta={"kind": "complex",
                                                "method": "neighborhood_inpaint",
                                                "status": "candidate",
                                                "detail": "test"},
            revision=0, task_id="t", label="背景")
        self.assertFalse(asset["reusable"])

        async def run():
            with self.assertRaises(main.HTTPException) as err:
                await main.save_background_asset_to_library(asset["assetId"])
            self.assertEqual(err.exception.status_code, 422)

        asyncio.run(run())

    def test_missing_asset_is_404(self):
        async def run():
            with self.assertRaises(main.HTTPException) as err:
                await main.get_background_asset("deadbeef")
            self.assertEqual(err.exception.status_code, 404)

        asyncio.run(run())


class BackgroundRebuildTests(unittest.TestCase):
    """海报 / 复杂场景：重建背景必须只写主体区域，遮罩外逐像素等于原图。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_bg_dir = main.BACKGROUND_ASSET_DIR
        self.old_bg_index = main.BACKGROUND_ASSET_INDEX
        main.BACKGROUND_ASSET_DIR = os.path.join(self.tmp.name, "backgrounds")
        main.BACKGROUND_ASSET_INDEX = os.path.join(main.BACKGROUND_ASSET_DIR, "index.json")
        self.task_id = "split_bg_rebuild_test"
        # 渐变底 + 一个方形主体
        self.source = Image.new("RGBA", (64, 48))
        px = self.source.load()
        for y in range(48):
            for x in range(64):
                px[x, y] = (40 + 2 * x, 60 + y, 120, 255)
        ImageDraw.Draw(self.source).rectangle((24, 14, 40, 34), fill=(10, 10, 10, 255))
        alpha = Image.new("L", (64, 48), 0)
        ImageDraw.Draw(alpha).rectangle((24, 14, 40, 34), fill=255)
        plate = self.source.copy()
        plate.putalpha(alpha)
        self.entries = [
            {"id": "bg", "kind": "element", "z": 0, "name": "背景",
             "bbox": [0, 0, 64, 48], "url": "/x.png", "provenance": "source_background",
             "status": "clean"},
            {"id": "L1", "kind": "element", "z": 1, "name": "主体",
             "bbox": [24, 14, 17, 21], "url": "/y.png", "provenance": "source",
             "method": "local"},
        ]
        main.split_state_put(self.task_id, {
            "src_path": "t.png", "src_rgba": self.source, "width": 64, "height": 48,
            "source": {"sha256": "s"}, "entries": self.entries,
            "plates": {"bg": self.source.copy(), "L1": plate},
            "masks": {"L1": alpha}, "issues": [], "checks": {},
            "text_hole": Image.new("L", (64, 48), 0), "pure_background": True,
        })
        main.CANVAS_TASKS[self.task_id] = {
            "id": self.task_id, "status": "review",
            "result": {"layers": self.entries, "phase": "review"},
        }

    def tearDown(self):
        main.BACKGROUND_ASSET_DIR = self.old_bg_dir
        main.BACKGROUND_ASSET_INDEX = self.old_bg_index
        main.SPLIT_TASK_STATE.pop(self.task_id, None)
        main.CANVAS_TASKS.pop(self.task_id, None)
        self.tmp.cleanup()

    def test_rebuild_writes_only_subject_region(self):
        async def run():
            out = await main.rebuild_split_background(
                self.task_id, main.SplitLayersBackgroundRequest(kind="auto"))
            self.assertTrue(out["ok"])
            asset = out["asset"]
            self.assertEqual((asset["width"], asset["height"]), self.source.size)
            self.assertIn(asset["status"], ("original_plus_deterministic", "candidate"))
            plate = main.split_state_get(self.task_id)["plates"]["bg"]
            from PIL import ImageChops
            hole = main.split_removed_hole(64, 48, self.entries,
                                           main.split_state_get(self.task_id)["plates"])
            diff = ImageChops.difference(plate.convert("RGB"),
                                         self.source.convert("RGB")).convert("L")
            outside = ImageChops.multiply(diff, ImageChops.invert(hole))
            self.assertEqual(sum(outside.histogram()[1:]), 0,
                             "遮罩外必须逐像素等于原图（方案 §10）")
            # 主体位置被改写了（否则背景没被移除）
            self.assertNotEqual(plate.getpixel((30, 24)), self.source.getpixel((30, 24)))
            # 第二次重建 → revision 递增，同一个 assetId（URL 稳定）
            out2 = await main.rebuild_split_background(
                self.task_id, main.SplitLayersBackgroundRequest(kind="solid",
                                                                color="#ff0000"))
            self.assertEqual(out2["asset"]["assetId"], asset["assetId"])
            self.assertEqual(out2["asset"]["revision"], asset["revision"] + 1)
            self.assertEqual(out2["asset"]["status"], "original_plus_deterministic")

        asyncio.run(run())

    def test_stale_when_foreground_changes_but_background_is_ai_repaired(self):
        async def run():
            out = await main.rebuild_split_background(
                self.task_id, main.SplitLayersBackgroundRequest(kind="auto"))
            asset_id = out["asset"]["assetId"]
            # 模拟「背景是模型补出来的」→ 前景一变就不再生效
            state = main.split_state_get(self.task_id)
            state["plates"]["bg"] = state["plates"]["bg"]
            for e in state["entries"]:
                if e["id"] == "bg":
                    e["provenance"] = "ai_repaired_background"
            main.split_state_put(self.task_id, state)
            await main.update_split_layers_mask(
                self.task_id,
                main.SplitLayersMaskRequest(layer_id="L1", hints={"exclude": [[30, 24, 2]]}))
            after = main.split_background_asset_get(asset_id)
            self.assertEqual(after["status"], "stale")
            self.assertFalse(after["reusable"])

        asyncio.run(run())

    def test_solid_region_scope_does_not_touch_outside(self):
        plate, meta = build_background(self.source, Image.new("L", (64, 48), 0),
                                       kind="solid", color=(255, 0, 0), solid_scope="region")
        self.assertEqual(meta["outside_changed"], 0)
        self.assertEqual(meta["scope"], "region")
        full, meta2 = build_background(self.source, Image.new("L", (64, 48), 0),
                                       kind="solid", color=(255, 0, 0), solid_scope="full")
        self.assertEqual(meta2["scope"], "full")
        self.assertEqual(full.getextrema(), ((255, 255), (0, 0), (0, 0), (255, 255)))


if __name__ == "__main__":
    unittest.main()
