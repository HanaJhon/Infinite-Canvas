# -*- coding: utf-8 -*-
"""文档契约的接口级测试（方案 §5.1 / §6 / §13）。

覆盖：
  ① 新旧两个命名空间都能读到同一份 schemaVersion 3 文档；
  ② 任务详情接口附带文档；
  ③ 旧记录（有 AI 调用、无区域映射）被标成「无法确认覆盖范围」且不进可复用状态；
  ④ 任务不存在 → 404；
  ⑤ 通道能力登记表接口。
零模型调用。
"""

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

import main
from backend.split_document import DOCUMENT_SCHEMA_VERSION


def _state():
    return {
        "src_path": "t.png", "width": 64, "height": 48,
        "source": {"sha256": "s", "url": "/src.png"},
        "entries": [
            {"id": "bg", "kind": "bg", "z": 0, "name": "背景", "provenance": "copied"},
            {"id": "L1", "kind": "element", "z": 1, "name": "主体", "importance": 0.9,
             "url": "/l1.png"},
            {"id": "T1", "kind": "text", "z": 2, "name": "标题", "text": "Hi"},
            {"id": "source", "kind": "element", "z": 9, "role": "reference"},
        ],
        "bg_regions": [{"id": "region-1", "state": "approved", "source": "copied"}],
        "bg_coverage": {"totalPixels": 3072, "uncoveredPixels": 0, "candidatePixels": 0,
                        "aiCalls": 1, "openRegions": 0, "pendingRegions": 0,
                        "openRegionIds": [], "maskBased": True},
        "bg_doc_revision": 3,
        "operations": [],
    }


def _result():
    return {
        "version": 2, "phase": "review", "sidecar": True,
        "source": {"url": "/src.png", "sha256": "s", "width": 64, "height": 48},
        "canvas": {"width": 64, "height": 48},
        "budget": {"limit": 3, "used": 1, "remaining": 2},
        "layers": _state()["entries"],
        "audit": {"issues": [{"id": "a", "layer_id": "L1"}], "checks": {}},
        "background_asset": {"assetId": "bg1", "url": "/bg.png", "status": "candidate",
                             "reusable": False},
        "coverage": {"totalPixels": 3072, "uncoveredPixels": 0, "candidatePixels": 0,
                     "aiCalls": 1},
    }


class DocumentEndpointTests(unittest.TestCase):
    def setUp(self):
        self.task_id = "split_document_api_test"
        main.SPLIT_TASK_STATE.pop(self.task_id, None)
        main.CANVAS_TASKS.pop(self.task_id, None)

    def tearDown(self):
        main.SPLIT_TASK_STATE.pop(self.task_id, None)
        main.CANVAS_TASKS.pop(self.task_id, None)

    def _install(self, result=None, state=None):
        main.split_state_put(self.task_id, state if state is not None else _state())
        main.CANVAS_TASKS[self.task_id] = {"id": self.task_id, "status": "review",
                                           "result": result if result is not None else _result()}

    def _run(self, coro):
        return asyncio.run(coro)

    def test_document_endpoint_returns_schema_v3(self):
        self._install()
        out = self._run(main.get_split_layers_document(self.task_id))
        doc = out["document"]
        self.assertEqual(doc["schemaVersion"], DOCUMENT_SCHEMA_VERSION)
        self.assertEqual(doc["taskId"], self.task_id)
        self.assertEqual(doc["documentRevision"], 3)
        self.assertEqual(doc["canvas"], {"width": 64, "height": 48})
        kinds = [layer["kind"] for layer in doc["layers"]]
        self.assertIn("background", kinds)
        self.assertIn("subject", kinds)
        self.assertIn("text", kinds)
        self.assertIn("source_ref", kinds)

    def test_document_is_json_serializable(self):
        import json
        self._install()
        doc = self._run(main.get_split_layers_document(self.task_id))["document"]
        json.dumps(doc, ensure_ascii=False)

    def test_task_detail_carries_document(self):
        self._install()
        task = self._run(main.get_split_layers_task(self.task_id))
        self.assertIn("document", task)
        self.assertEqual(task["document"]["schemaVersion"], DOCUMENT_SCHEMA_VERSION)

    def test_missing_task_is_404(self):
        with self.assertRaises(HTTPException) as ctx:
            self._run(main.get_split_layers_document("split_missing_000"))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_legacy_result_is_flagged_and_downgraded(self):
        # 旧记录：有图像调用、没有任何区域映射 ⇒ 不许当成「已完成」
        legacy = {"version": 2, "phase": "review",
                  "image_calls": [{"operation_id": "x"}],
                  "budget": {"limit": 3, "used": 3, "remaining": 0},
                  "layers": _state()["entries"],
                  "background_asset": {"assetId": "bg1", "url": "/bg.png",
                                       "status": "reviewed_inpaint", "reusable": True}}
        legacy_state = {k: v for k, v in _state().items() if k != "bg_regions"}
        self._install(result=legacy, state=legacy_state)
        doc = self._run(main.get_split_layers_document(self.task_id))["document"]
        self.assertTrue(doc["compat"]["unverifiableBackground"])
        self.assertTrue(doc["compat"]["requiresResplit"])
        self.assertEqual(doc["backgroundAsset"]["status"], "needs_manual_repair")
        self.assertFalse(doc["backgroundAsset"]["reusable"])

    def test_current_result_is_not_flagged(self):
        self._install()
        doc = self._run(main.get_split_layers_document(self.task_id))["document"]
        self.assertFalse(doc["compat"]["unverifiableBackground"])

    def test_document_without_state_still_builds(self):
        # 服务重启后内存态没了，只要任务结果还在就要能读文档（降级不报错）
        main.CANVAS_TASKS[self.task_id] = {"id": self.task_id, "status": "succeeded",
                                           "result": _result()}
        doc = self._run(main.get_split_layers_document(self.task_id))["document"]
        self.assertEqual(len(doc["layers"]), 4)
        self.assertEqual(doc["documentRevision"], 0)

    def test_capabilities_endpoint(self):
        out = self._run(main.get_split_layers_provider_capabilities())
        self.assertTrue(out["ok"])
        self.assertEqual(out["capabilities"], {})
        self.assertIn("显式采纳", out["note"])


class DocumentEffectTests(unittest.TestCase):
    """文档契约必须对**真实像素路径**生效，不只是能读。"""

    def test_bump_keeps_legacy_counter_in_sync(self):
        state = {"bg_doc_revision": 7}
        main.bump_document_revision(state)
        self.assertEqual(state["document_revision"], 8)
        self.assertEqual(state["bg_doc_revision"], 8)

    def test_track_operation_is_tolerant_of_missing_log(self):
        # 旧任务没有 operation 日志 ⇒ 静默跳过，不抛异常
        self.assertIsNone(main.split_track_operation({}, "op-1", "candidate_ready"))

    def test_track_operation_advances_real_record(self):
        state = {}
        main.operation_new(state, kind="k", operation_id="op-1")
        main.split_track_operation(state, "op-1", "candidate_ready", candidateId="c1")
        self.assertEqual(state["operations"][0]["state"], "candidate_ready")
        self.assertEqual(state["operations"][0]["candidateId"], "c1")

    def test_track_operation_swallows_illegal_transition(self):
        state = {}
        main.operation_new(state, kind="k", operation_id="op-1")
        main.split_track_operation(state, "op-1", "candidate_ready")
        main.split_track_operation(state, "op-1", "accepted")
        # accepted 是终态；再推 rejected 非法，但**不能**让调用方炸掉
        main.split_track_operation(state, "op-1", "rejected")
        self.assertEqual(state["operations"][0]["state"], "accepted")


if __name__ == "__main__":
    unittest.main()
