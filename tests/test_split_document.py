# -*- coding: utf-8 -*-
"""拆分图层文档契约的纯逻辑测试（方案 §5.1 / §12 / §13）。

覆盖：图层类型推导 / 字段归一 / revision / 背景状态归一 / 账本口径 /
五类资产分离 / 旧数据兼容 / operation 状态机 / 文档读写往返。
全部零模型调用、零像素。
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.split_document import (
    ASSET_ROLES, DOCUMENT_SCHEMA_VERSION, LAYER_KINDS, OPERATION_STATES,
    OperationTransitionError, adapt_legacy_result, asset_refs,
    build_background_asset, build_document, build_quality, bump_document_revision,
    compat_flags, document_revision, is_legacy_unverifiable, layer_kind,
    layer_quality_state, normalize_background_status, normalize_layer,
    operation_new, operation_path, operation_transition, operation_advance,
    operations_of, region_mapping_count,
)


def _entries():
    return [
        {"id": "bg", "kind": "bg", "name": "背景", "z": 0, "provenance": "copied"},
        {"id": "e1", "kind": "element", "name": "花卉茶壶", "z": 1, "importance": 0.9},
        {"id": "e2", "kind": "element", "name": "分隔线", "z": 2, "importance": 0.15},
        {"id": "t1", "kind": "text", "name": "右侧说明文字", "z": 3, "text": "Hello"},
        {"id": "source", "kind": "element", "name": "原图", "z": 9, "role": "reference"},
        {"id": "s1", "kind": "element", "name": "投影", "z": 4, "shadow": True},
    ]


class LayerKindTests(unittest.TestCase):
    def test_background_and_text_and_reference(self):
        self.assertEqual(layer_kind({"id": "bg", "kind": "bg"}), "background")
        self.assertEqual(layer_kind({"id": "t1", "kind": "text"}), "text")
        self.assertEqual(layer_kind({"id": "source", "role": "reference"}), "source_ref")
        self.assertEqual(layer_kind({"id": "s1", "shadow": True}), "shadow")

    def test_importance_splits_subject_from_structure(self):
        self.assertEqual(layer_kind({"id": "e1", "kind": "element", "importance": 0.9}), "subject")
        self.assertEqual(layer_kind({"id": "e2", "kind": "element", "importance": 0.15}), "structure")
        # 边界：0.4 刚好算主体
        self.assertEqual(layer_kind({"kind": "element", "importance": 0.4}), "subject")
        self.assertEqual(layer_kind({"kind": "element", "importance": 0.39}), "structure")
        # 没有 importance 时按 0.5 兜底 → 主体（不凭空降级成结构）
        self.assertEqual(layer_kind({"kind": "element"}), "subject")

    def test_explicit_kind_wins(self):
        self.assertEqual(layer_kind({"kind": "element", "layerKind": "structure"}), "structure")
        self.assertEqual(layer_kind({"kind": "element", "layer_kind": "shadow"}), "shadow")
        # 非法显式值忽略，回落推导
        self.assertEqual(layer_kind({"kind": "element", "layerKind": "nonsense",
                                     "importance": 0.9}), "subject")


class NormalizeLayerTests(unittest.TestCase):
    def test_required_fields_and_defaults(self):
        layer = normalize_layer({"id": "e1", "kind": "element", "importance": 0.9}, 0)
        for key in ("id", "kind", "name", "z", "visible", "locked", "bbox",
                    "transform", "assetId", "maskRevision", "provenance", "qualityState"):
            self.assertIn(key, layer)
        self.assertEqual(layer["kind"], "subject")
        self.assertTrue(layer["visible"])
        self.assertFalse(layer["locked"])
        self.assertEqual(layer["qualityState"], "ok")
        self.assertEqual(layer["provenance"], "source")
        self.assertEqual(layer["assetId"], "e1")

    def test_legacy_kind_is_preserved(self):
        layer = normalize_layer({"id": "t1", "kind": "text"}, 0)
        self.assertEqual(layer["kind"], "text")
        self.assertEqual(layer["legacyKind"], "text")

    def test_hidden_maps_to_visible_false_and_edit_maps_to_transform(self):
        layer = normalize_layer({"id": "e1", "hidden": True, "edit": {"x": 3, "scale": 2}}, 1)
        self.assertFalse(layer["visible"])
        self.assertEqual(layer["transform"], {"x": 3, "scale": 2})

    def test_extensions_are_kept(self):
        layer = normalize_layer({"id": "t1", "kind": "text", "text": "Hi",
                                 "font_family": "Inter", "mask_url": "/a.png"}, 0)
        self.assertEqual(layer["text"], "Hi")
        self.assertEqual(layer["font_family"], "Inter")
        self.assertEqual(layer["mask_url"], "/a.png")

    def test_mask_revision_inherits_state_value(self):
        layer = normalize_layer({"id": "e1"}, 0, mask_revision=7)
        self.assertEqual(layer["maskRevision"], 7)

    def test_quality_state_reads_existing_fields(self):
        self.assertEqual(layer_quality_state({"status": "pending"}), "pending")
        self.assertEqual(layer_quality_state({"quality": "stale"}), "stale")
        self.assertEqual(layer_quality_state({"qualityState": "failed"}), "failed")
        self.assertEqual(layer_quality_state({"status": "unknown_value"}), "ok")


class RevisionTests(unittest.TestCase):
    def test_read_from_state_first(self):
        self.assertEqual(document_revision({"document_revision": 4}, {"version": 2}), 4)
        self.assertEqual(document_revision({"bg_doc_revision": 3}), 3)
        self.assertEqual(document_revision({}, {}), 0)

    def test_bump_keeps_both_keys_in_sync(self):
        state = {"bg_doc_revision": 3}
        self.assertEqual(bump_document_revision(state), 4)
        self.assertEqual(state["document_revision"], 4)
        self.assertEqual(state["bg_doc_revision"], 4)
        self.assertEqual(document_revision(state), 4)

    def test_bump_from_empty(self):
        state = {}
        self.assertEqual(bump_document_revision(state), 1)


class BackgroundStatusTests(unittest.TestCase):
    def test_legacy_names_upgrade(self):
        self.assertEqual(normalize_background_status("deterministic"), "original_plus_deterministic")
        self.assertEqual(normalize_background_status("reviewed_repair"), "reviewed_inpaint")
        self.assertEqual(normalize_background_status("speculative"), "candidate")

    def test_known_names_pass_through(self):
        for name in ("original_plus_deterministic", "reviewed_inpaint", "candidate",
                     "needs_manual_repair", "stale", "failed"):
            self.assertEqual(normalize_background_status(name), name)

    def test_unknown_never_becomes_completed(self):
        # 🚨 方案 §13：未知状态一律 needs_manual_repair，禁止映射成「已完成」
        for raw in ("", None, "completed", "done", "finished", "看不太懂"):
            self.assertEqual(normalize_background_status(raw), "needs_manual_repair")


class QualityTests(unittest.TestCase):
    def test_foreground_and_background_are_separate_groups(self):
        result = {
            "audit": {"issues": [{"id": "a", "layer_id": "e1"}, {"id": "b", "layer_id": "e2"}],
                      "checks": {"reconstruction": {"score": 1}}},
            "coverage": {"totalPixels": 1000, "uncoveredPixels": 100, "candidatePixels": 50,
                         "aiCalls": 2, "openRegions": 1, "pendingRegions": 1,
                         "openRegionIds": ["region-1"]},
        }
        quality = build_quality(result)
        self.assertEqual(quality["foreground"]["total"], 2)
        self.assertEqual(quality["background"]["uncoveredPixels"], 100)
        self.assertEqual(quality["background"]["rebuiltPixels"], 850)

    def test_ignored_issues_are_excluded_and_fixed_counted(self):
        result = {
            "audit": {"issues": [{"id": "a", "fixed": True}, {"id": "b"}, {"id": "c"}]},
            "ignored_issues": ["c"],
        }
        quality = build_quality(result)
        self.assertEqual(quality["foreground"]["total"], 2)
        self.assertEqual(quality["foreground"]["fixed"], 1)

    def test_rebuilt_is_clamped_at_zero(self):
        quality = build_quality({"coverage": {"totalPixels": 10, "uncoveredPixels": 100}})
        self.assertEqual(quality["background"]["rebuiltPixels"], 0)

    def test_mask_based_flag_is_passed_through(self):
        self.assertFalse(build_quality({"coverage": {"maskBased": False}})["background"]["maskBased"])
        self.assertTrue(build_quality({"coverage": {}})["background"]["maskBased"])


class AssetSeparationTests(unittest.TestCase):
    def test_five_roles_are_present(self):
        refs = asset_refs({}, {}, [])
        self.assertEqual(tuple(refs.keys()), ASSET_ROLES)

    def test_source_is_immutable_and_candidates_are_separate(self):
        result = {"source": {"url": "/src.png", "sha256": "abc"},
                  "background_asset": {"assetId": "bg1", "url": "/bg.png", "status": "candidate"}}
        state = {"bg_candidates": {"c1": {"candidateId": "c1", "regionId": "region-1",
                                          "status": "candidate_ready", "url": "/c1.png"}}}
        refs = asset_refs(result, state, [])
        self.assertTrue(refs["sourceOriginal"]["immutable"])
        self.assertEqual(refs["sourceOriginal"]["url"], "/src.png")
        self.assertEqual(refs["backgroundCurrent"]["url"], "/bg.png")
        # 候选绝不能和当前背景共用同一个 URL
        self.assertNotEqual(refs["backgroundCandidate"]["items"][0]["url"], "/bg.png")
        self.assertEqual(refs["backgroundCandidate"]["items"][0]["status"], "candidate_ready")

    def test_foreground_excludes_background_and_reference(self):
        layers = [{"id": "bg", "kind": "background"}, {"id": "source", "kind": "source_ref"},
                  {"id": "e1", "kind": "subject", "url": "/e1.png"}]
        refs = asset_refs({}, {}, layers)
        ids = [item["layerId"] for item in refs["foregroundAsset"]["items"]]
        self.assertEqual(ids, ["e1"])

    def test_reusable_requires_known_good_status(self):
        good = build_background_asset({"background_asset": {"status": "reviewed_inpaint",
                                                            "reusable": True}})
        bad = build_background_asset({"background_asset": {"status": "needs_manual_repair",
                                                           "reusable": True}})
        self.assertTrue(good["reusable"])
        self.assertFalse(bad["reusable"])

    def test_unknown_asset_status_is_normalized(self):
        asset = build_background_asset({"background_asset": {"status": "whatever"}})
        self.assertEqual(asset["status"], "needs_manual_repair")


class LegacyCompatTests(unittest.TestCase):
    def test_legacy_unverifiable_needs_calls_without_regions(self):
        self.assertTrue(is_legacy_unverifiable({"image_calls": [{"a": 1}]}))
        self.assertTrue(is_legacy_unverifiable({"budget": {"used": 3}}))
        self.assertFalse(is_legacy_unverifiable({"image_calls": [{"a": 1}],
                                                 "regions": [{"id": "r1"}]}))
        self.assertFalse(is_legacy_unverifiable({}))

    def test_region_mapping_found_in_every_real_location(self):
        # 🚨 区域在真实数据里有多个落脚点，只查 result["regions"] 会误判全部记录
        self.assertEqual(region_mapping_count({"regions": [{"id": "r1"}]}), 1)
        self.assertEqual(region_mapping_count(
            {"background_asset": {"regions": [{"id": "r1"}, {"id": "r2"}]}}), 2)
        self.assertEqual(region_mapping_count(
            {"background_asset": {"regionCount": 7}}), 7)
        self.assertEqual(region_mapping_count(
            {"layers": [{"id": "bg", "regions": [{"id": "r1"}]}]}), 1)
        self.assertEqual(region_mapping_count({}, {"bg_regions": [{"id": "r1"}]}), 1)
        self.assertEqual(region_mapping_count({}), 0)

    def test_modern_result_with_regions_in_state_is_not_legacy(self):
        # 现在的结果把区域放在内存态 / 背景图层里 —— 不能被当成「无法追溯」
        result = {"image_calls": [{"a": 1}]}
        state = {"bg_regions": [{"id": "r1"}]}
        self.assertFalse(is_legacy_unverifiable(result, state))
        self.assertFalse(compat_flags(result, state)["unverifiableBackground"])

    def test_modern_result_with_region_count_is_not_legacy(self):
        result = {"image_calls": [{"a": 1}], "background_asset": {"regionCount": 3}}
        self.assertFalse(is_legacy_unverifiable(result))

    def test_adapt_forces_needs_manual_repair(self):
        adapted = adapt_legacy_result({"image_calls": [{"a": 1}],
                                       "background_asset": {"status": "reviewed_inpaint",
                                                            "reusable": True}})
        self.assertEqual(adapted["background_asset"]["status"], "needs_manual_repair")
        self.assertFalse(adapted["background_asset"]["reusable"])
        self.assertTrue(adapted["compat"]["requiresResplit"])
        self.assertIn("旧记录", adapted["compat"]["reason"])

    def test_adapt_does_not_mutate_input(self):
        original = {"image_calls": [{"a": 1}], "background_asset": {"status": "candidate"}}
        adapt_legacy_result(original)
        self.assertEqual(original["background_asset"]["status"], "candidate")
        self.assertNotIn("compat", original)

    def test_compat_flags_for_current_result(self):
        flags = compat_flags({"version": 2, "schemaVersion": 3})
        self.assertFalse(flags["unverifiableBackground"])
        self.assertFalse(flags["requiresResplit"])

    def test_old_schema_version_is_flagged(self):
        self.assertTrue(compat_flags({"schemaVersion": 2})["legacy"])
        self.assertTrue(compat_flags({"version": 1})["legacy"])


class OperationTests(unittest.TestCase):
    def test_new_is_idempotent_by_operation_id(self):
        state = {}
        first = operation_new(state, kind="bg_region_candidate", operation_id="op-1")
        again = operation_new(state, kind="bg_region_candidate", operation_id="op-1")
        self.assertIs(first, again)
        self.assertEqual(len(operations_of(state)), 1)

    def test_full_happy_path(self):
        state = {}
        record = operation_new(state, kind="bg_region_candidate", operation_id="op-1")
        self.assertEqual(record["state"], "created")
        for target in ("validated", "budget_reserved", "submitted", "candidate_ready"):
            operation_transition(state, "op-1", target)
        accepted = operation_transition(state, "op-1", "accepted", candidateId="c1")
        self.assertEqual(accepted["state"], "accepted")
        self.assertEqual(accepted["candidateId"], "c1")
        self.assertEqual(len(accepted["history"]), 6)

    def test_illegal_transition_rejected(self):
        state = {}
        operation_new(state, kind="k", operation_id="op-1")
        with self.assertRaises(OperationTransitionError):
            operation_transition(state, "op-1", "accepted")   # 不能从 created 直接采纳

    def test_terminal_state_is_locked(self):
        state = {}
        operation_new(state, kind="k", operation_id="op-1")
        for target in ("validated", "budget_reserved", "submitted", "candidate_ready", "rejected"):
            operation_transition(state, "op-1", target)
        # 拒绝之后再「采纳同一候选」必须失败，否则就是账本造假
        with self.assertRaises(OperationTransitionError):
            operation_transition(state, "op-1", "accepted")

    def test_unknown_can_still_land_on_candidate(self):
        # 方案 §12.1：进程重启后未完成 operation 恢复为 unknown，迟到结果仍可落地
        state = {}
        operation_new(state, kind="k", operation_id="op-1")
        for target in ("validated", "budget_reserved", "submitted", "unknown"):
            operation_transition(state, "op-1", target)
        self.assertEqual(operation_transition(state, "op-1", "candidate_ready")["state"],
                         "candidate_ready")

    def test_missing_operation_raises(self):
        with self.assertRaises(OperationTransitionError):
            operation_transition({}, "nope", "validated")

    def test_all_states_are_declared(self):
        self.assertIn("candidate_ready", OPERATION_STATES)
        self.assertIn("superseded", OPERATION_STATES)
        self.assertIn("cancelled", OPERATION_STATES)


class OperationPathTests(unittest.TestCase):
    def test_path_walks_the_documented_chain(self):
        self.assertEqual(operation_path("created", "candidate_ready"),
                         ["validated", "budget_reserved", "submitted", "candidate_ready"])
        self.assertEqual(operation_path("created", "accepted"),
                         ["validated", "budget_reserved", "submitted", "candidate_ready", "accepted"])
        self.assertEqual(operation_path("created", "created"), [])

    def test_unreachable_path_is_none(self):
        self.assertIsNone(operation_path("accepted", "candidate_ready"))
        self.assertIsNone(operation_path("failed", "accepted"))

    def test_advance_fills_intermediate_steps(self):
        state = {}
        operation_new(state, kind="bg_region_candidate", operation_id="op-1")
        record = operation_advance(state, "op-1", "candidate_ready", candidateId="c1")
        self.assertEqual(record["state"], "candidate_ready")
        self.assertEqual(record["candidateId"], "c1")
        self.assertEqual([h["state"] for h in record["history"]],
                         ["created", "validated", "budget_reserved", "submitted", "candidate_ready"])
        # 中间步骤不应该带上终态才有的字段
        self.assertEqual(record["history"][1]["state"], "validated")

    def test_advance_cannot_skip_validation(self):
        state = {}
        operation_new(state, kind="k", operation_id="op-1")
        operation_advance(state, "op-1", "candidate_ready")
        operation_advance(state, "op-1", "accepted")
        with self.assertRaises(OperationTransitionError):
            operation_advance(state, "op-1", "rejected")

    def test_advance_missing_operation_raises(self):
        with self.assertRaises(OperationTransitionError):
            operation_advance({}, "nope", "candidate_ready")

    def test_advance_to_failed_from_created(self):
        state = {}
        operation_new(state, kind="k", operation_id="op-1")
        self.assertEqual(operation_advance(state, "op-1", "failed")["state"], "failed")


class BuildDocumentTests(unittest.TestCase):
    def _result(self):
        return {
            "version": 2, "phase": "review",
            "source": {"url": "/src.png", "sha256": "deadbeef", "width": 100, "height": 80},
            "canvas": {"width": 100, "height": 80},
            "budget": {"limit": 3, "used": 1, "remaining": 2},
            "layers": _entries(),
            "audit": {"issues": [{"id": "a", "layer_id": "e1"}], "checks": {}},
            "background_asset": {"assetId": "bg1", "url": "/bg.png", "status": "candidate",
                                 "reusable": False},
            "coverage": {"totalPixels": 8000, "uncoveredPixels": 500, "candidatePixels": 100,
                         "aiCalls": 1, "openRegions": 1, "openRegionIds": ["region-1"]},
        }

    def test_document_shape_and_version(self):
        doc = build_document("split_x", self._result(), {})
        self.assertEqual(doc["schemaVersion"], DOCUMENT_SCHEMA_VERSION)
        self.assertEqual(doc["taskId"], "split_x")
        self.assertEqual(doc["source"]["hash"], "deadbeef")
        self.assertEqual(doc["canvas"], {"width": 100, "height": 80})
        self.assertEqual(len(doc["layers"]), len(_entries()))
        for layer in doc["layers"]:
            self.assertIn(layer["kind"], LAYER_KINDS)

    def test_layers_sorted_by_z(self):
        doc = build_document("split_x", self._result(), {})
        zs = [layer["z"] for layer in doc["layers"]]
        self.assertEqual(zs, sorted(zs))

    def test_json_round_trip(self):
        doc = build_document("split_x", self._result(), {"bg_doc_revision": 5})
        text = json.dumps(doc, ensure_ascii=False)
        back = json.loads(text)
        self.assertEqual(back, doc)
        self.assertEqual(back["documentRevision"], 5)

    def test_revision_from_state_not_result(self):
        doc = build_document("split_x", self._result(), {"bg_doc_revision": 5})
        self.assertEqual(doc["documentRevision"], 5)
        doc2 = build_document("split_x", self._result(), {})
        self.assertEqual(doc2["documentRevision"], 0)

    def test_operations_included(self):
        state = {}
        operation_new(state, kind="bg_region_candidate", operation_id="op-1")
        doc = build_document("split_x", self._result(), state)
        self.assertEqual(len(doc["operations"]), 1)
        self.assertEqual(doc["operations"][0]["operationId"], "op-1")

    def test_result_falls_back_to_state(self):
        state = {"width": 64, "height": 48, "entries": [{"id": "e1", "kind": "element"}],
                 "source": {"sha256": "s"}, "bg_regions": [{"id": "r1"}]}
        doc = build_document("split_t", {}, state)
        self.assertEqual(doc["canvas"], {"width": 64, "height": 48})
        self.assertEqual(len(doc["layers"]), 1)
        self.assertEqual(doc["backgroundAsset"]["regions"], [{"id": "r1"}])


if __name__ == "__main__":
    unittest.main()
