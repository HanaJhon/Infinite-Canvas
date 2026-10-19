import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw

import main

# 🚨 元素级重构（方案《豆包式元素级拆分图层完全重构方案-V2》§2.1 / §14 P0）：
#    main 默认**冻结**旧拆分写接口。本文件验证的是**旧实现本身**（P5 阶段才删除），
#    所以整个模块显式解冻；「冻结行为」由 tests/test_element_freeze.py 专门验证 ——
#    两件事不要混在一起测（一个测「旧算法还对」，一个测「旧入口进不来」）。
main.LEGACY_SPLIT_WRITES_FROZEN = False


class ProductTaskApiTests(unittest.TestCase):
    def test_product_mask_revision_keeps_solid_background(self):
        source = Image.new("RGBA", (48, 32), "white")
        ImageDraw.Draw(source).rectangle((12, 6, 28, 25), fill=(40, 80, 120, 255))
        task_id = "split_product_api_test"
        payload = main.SplitLayersRequest(
            image_url="/assets/input/test.png",
            task_mode="product",
            background_mode="solid",
            background_color="#ffffff",
            budget=9,
        )
        old_save = main.split_save_png

        async def fake_save(_image, prefix="split_layer_"):
            return f"/assets/{prefix}test.png"

        async def exercise():
            main.split_save_png = fake_save
            main.CANVAS_TASKS[task_id] = {
                "id": task_id, "status": "queued", "result": None,
            }
            try:
                result = await main.build_product_split_result(
                    task_id, payload, "test.png", source, {"sha256": "test"}, lambda *_: None
                )
                main.CANVAS_TASKS[task_id]["result"] = result
                main.CANVAS_TASKS[task_id]["status"] = "review"
                before = result["layers"][1]["quality"]["contract"]["revision"]
                response = await main.update_split_layers_mask(
                    task_id,
                    main.SplitLayersMaskRequest(
                        layer_id="product", expected_revision=before,
                        hints={"include": [[8, 8, 2]]}
                    ),
                )
                state = main.split_state_get(task_id)
                self.assertEqual(response["mask_revision"], before + 1)
                self.assertEqual(state["product_contract"]["revision"], before + 1)
                self.assertEqual(state["masks"]["product"].mode, "L")
                self.assertEqual(state["product_contract"]["background"], [255, 255, 255])
                self.assertTrue(all(lo == hi for lo, hi in state["plates"]["bg"].getextrema()))
                self.assertEqual(
                    state["entries"][1]["quality"]["product"]["status"],
                    "needs_local_correction",
                )
                with self.assertRaises(main.HTTPException) as conflict:
                    await main.update_split_layers_mask(
                        task_id,
                        main.SplitLayersMaskRequest(
                            layer_id="product", expected_revision=before,
                            hints={"exclude": [[8, 8, 2]]}
                        ),
                    )
                self.assertEqual(conflict.exception.status_code, 409)
                with self.assertRaises(main.HTTPException) as repair:
                    await main.repair_split_layers_task(
                        task_id, main.SplitLayersRepairRequest(budget=0)
                    )
                self.assertEqual(repair.exception.status_code, 409)
                with self.assertRaises(main.HTTPException) as incomplete:
                    await main.confirm_product_quality(
                        task_id,
                        main.SplitLayersQualityConfirmRequest(
                            expected_revision=before + 1,
                            checks={"white": True},
                        ),
                    )
                self.assertEqual(incomplete.exception.status_code, 422)
                confirmed = await main.confirm_product_quality(
                    task_id,
                    main.SplitLayersQualityConfirmRequest(
                        expected_revision=before + 1,
                        checks={"white": True, "dark": True,
                                "checker": True, "structure": True},
                    ),
                )
                self.assertTrue(confirmed["quality_confirmed"])
                self.assertEqual(main.CANVAS_TASKS[task_id]["status"], "succeeded")
            finally:
                main.CANVAS_TASKS.pop(task_id, None)
                main.SPLIT_TASK_STATE.pop(task_id, None)
                main.split_save_png = old_save

        asyncio.run(exercise())


class ProductFailureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.task_id = "split_product_failure_test"
        self.source = Image.new("RGBA", (48, 32), "white")
        ImageDraw.Draw(self.source).rectangle((12, 6, 28, 25), fill=(40, 80, 120, 255))
        self.source.putpixel((30, 10), (251, 251, 251, 255))
        self.save = patch.object(main, "split_save_png", return_value="/assets/fake.png")
        self.save_mock = self.save.start()
        self.payload = main.SplitLayersRequest(
            image_url="/assets/input/test.png", task_mode="product", budget=9)
        self.result = await main.build_product_split_result(
            self.task_id, self.payload, "test.png", self.source,
            {"sha256": "fixture"}, lambda *_: None)
        main.CANVAS_TASKS[self.task_id] = {
            "id": self.task_id, "task_mode": "product", "status": "review", "result": self.result}

    async def asyncTearDown(self):
        self.save.stop()
        main.CANVAS_TASKS.pop(self.task_id, None)
        main.SPLIT_TASK_STATE.pop(self.task_id, None)

    def mask_request(self, revision=1, **hints):
        return main.SplitLayersMaskRequest(
            layer_id="product", expected_revision=revision, hints=hints)

    def quality_request(self, revision=1):
        return main.SplitLayersQualityConfirmRequest(
            expected_revision=revision,
            checks=dict.fromkeys(("white", "dark", "checker", "structure"), True))

    async def test_soft_alpha_survives_and_new_mask_invalidates_confirmation(self):
        before = main.split_state_get(self.task_id)["masks"]["product"].getpixel((30, 10))
        self.assertTrue(0 < before < 255)
        await main.confirm_product_quality(self.task_id, self.quality_request())
        response = await main.update_split_layers_mask(
            self.task_id, self.mask_request(include=[[8, 8, 2]]))
        state = main.split_state_get(self.task_id)
        self.assertEqual(state["masks"]["product"].getpixel((30, 10)), before)
        self.assertIsNone(state["quality_confirmation"])
        self.assertEqual(response["audit"]["checks"]["product"]["checks"],
                         dict.fromkeys(("white", "dark", "checker", "structure"), False))
        self.assertFalse(main.CANVAS_TASKS[self.task_id]["result"]["quality_confirmed"])
        with self.assertRaises(main.HTTPException) as error:
            await main.confirm_product_quality(self.task_id, self.quality_request())
        self.assertEqual(error.exception.status_code, 409)

    async def test_asset_failure_and_invalid_input_leave_old_revision_untouched(self):
        original_state = main.split_state_get(self.task_id)
        original_result = main.CANVAS_TASKS[self.task_id]["result"]
        original_bytes = original_state["masks"]["product"].tobytes()
        for hints in ({"strokes": ["invalid"]}, {"include": [[0, 0, "bad"]]},
                      {"exclude": [[24, 16, 100]]}, {"include": [[24, 16, 100]]}):
            with self.assertRaises(main.HTTPException) as error:
                await main.update_split_layers_mask(self.task_id, self.mask_request(**hints))
            self.assertEqual(error.exception.status_code, 400)
            self.assertIs(main.split_state_get(self.task_id), original_state)
        self.save_mock.side_effect = ["/assets/new-product.png", OSError("fixture write failure")]
        with self.assertRaises(OSError):
            await main.update_split_layers_mask(
                self.task_id, self.mask_request(include=[[8, 8, 2]]))
        self.assertIs(main.split_state_get(self.task_id), original_state)
        self.assertIs(main.CANVAS_TASKS[self.task_id]["result"], original_result)
        self.assertEqual(original_state["masks"]["product"].tobytes(), original_bytes)

    async def test_concurrent_mask_requests_only_commit_one_revision(self):
        entered, release = asyncio.Event(), asyncio.Event()
        count = 0

        async def interleaved_save(_image, prefix="split_layer_"):
            nonlocal count
            count += 1
            if count == 1:
                entered.set()
                await release.wait()
            return f"/assets/{count}.png"

        self.save_mock.side_effect = interleaved_save
        first = asyncio.create_task(main.update_split_layers_mask(
            self.task_id, self.mask_request(include=[[8, 8, 2]])))
        await entered.wait()
        await main.update_split_layers_mask(
            self.task_id, self.mask_request(include=[[35, 8, 2]]))
        release.set()
        with self.assertRaises(main.HTTPException) as conflict:
            await first
        self.assertEqual(conflict.exception.status_code, 409)
        state = main.split_state_get(self.task_id)
        self.assertEqual(state["product_contract"]["revision"], 2)
        self.assertEqual(state["masks"]["product"].getpixel((8, 8)), 0)
        self.assertEqual(state["masks"]["product"].getpixel((35, 8)), 255)

    async def test_confirm_requires_current_revision_and_actual_exact_background(self):
        with self.assertRaises(main.HTTPException) as error:
            await main.confirm_product_quality(
                self.task_id, main.SplitLayersQualityConfirmRequest(
                    checks=self.quality_request().checks))
        self.assertEqual(error.exception.status_code, 422)
        state = main.split_state_get(self.task_id)
        state["plates"]["bg"].putpixel((0, 0), (254, 255, 255, 255))
        with self.assertRaises(main.HTTPException) as error:
            await main.confirm_product_quality(self.task_id, self.quality_request())
        self.assertEqual(error.exception.status_code, 422)

    async def test_create_and_full_run_need_no_provider_and_never_call_models(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oriented.jpg"
            exif = Image.Exif()
            exif[274] = 6
            self.source.convert("RGB").save(path, exif=exif)
            with patch.object(main, "output_file_from_url", return_value=str(path)), \
                    patch.object(main, "split_analyze", side_effect=AssertionError("analysis forbidden")), \
                    patch.object(main, "split_call_image_model", side_effect=AssertionError("image call forbidden")):
                response = await main.create_split_layers_task(self.payload)
                task_id = response["task_id"]
                try:
                    for _ in range(20):
                        await asyncio.sleep(0)
                        task = main.CANVAS_TASKS[task_id]
                        if task["status"] in ("review", "failed"):
                            break
                    self.assertEqual(task["status"], "review", task.get("error"))
                    self.assertEqual(task["result"]["canvas"], {"width": 32, "height": 48})
                    self.assertEqual(task["result"]["budget"]["limit"], 0)
                    self.assertTrue(task["result"]["audit"]["checks"]["background_exact"])
                    reference = next(item for item in task["result"]["layers"] if item.get("role") == "reference")
                    self.assertTrue(reference["locked"] and reference["hidden"])
                finally:
                    main.CANVAS_TASKS.pop(task_id, None)
                    main.SPLIT_TASK_STATE.pop(task_id, None)


if __name__ == "__main__":
    unittest.main()
