# -*- coding: utf-8 -*-
"""图像 provider 能力声明的纯逻辑测试（方案 §12.4）。

核心断言：**没登记的通道按最保守能力处理**，绝不因为「名字看着像」就授予
原生遮罩或自动采纳权限。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.split_providers import (
    MASK_EDIT_MODES, REGISTRY, UNKNOWN_CAPABILITY, can_auto_accept, capability_table,
    declare, mask_edit_mode, provider_capability,
)


class RegistryResetMixin:
    def setUp(self):
        self._saved = dict(REGISTRY)
        REGISTRY.clear()

    def tearDown(self):
        REGISTRY.clear()
        REGISTRY.update(self._saved)


class DefaultCapabilityTests(RegistryResetMixin, unittest.TestCase):
    def test_unregistered_is_conservative(self):
        cap = provider_capability("some-provider", "some-model")
        self.assertFalse(cap.supports_masked_edit)
        self.assertFalse(cap.returns_aligned_crop)
        self.assertEqual(cap.output_size_behavior, "unknown")
        # 但**本地对齐适配**是服务端自己实现的，默认可用 ⇒ 仍可做局部候选
        self.assertTrue(cap.local_edit_ok)
        self.assertEqual(cap.mask_edit_mode, "local_edit")

    def test_empty_provider_falls_back(self):
        self.assertIs(provider_capability(""), UNKNOWN_CAPABILITY)

    def test_registry_ships_empty(self):
        # 🚨 一个通道都没实测过 ⇒ 登记表必须是空的，不许凭空写 true
        self.assertEqual(REGISTRY, {})
        self.assertEqual(capability_table(), {})


class MaskEditModeTests(RegistryResetMixin, unittest.TestCase):
    def test_unknown_channel_can_still_do_local_edit(self):
        # 与旧 `split_mask_edit_mode()` 口径一致：未登记通道默认 local_edit
        self.assertEqual(mask_edit_mode("acme", "img-1"), "local_edit")

    def test_explicitly_broken_channel_is_global_only(self):
        declare("acme", "img-1", local_edit_ok=False,
                note="实测返回固定尺寸缩略图，连本地适配也救不回来")
        self.assertEqual(mask_edit_mode("acme", "img-1"), "global_only")

    def test_aligned_local_edit_is_local_edit(self):
        declare("acme", "img-1", returns_aligned_crop=True, output_size_behavior="same_as_input")
        self.assertEqual(mask_edit_mode("acme", "img-1"), "local_edit")

    def test_native_mask_wins(self):
        declare("acme", "img-1", supports_masked_edit=True, returns_aligned_crop=True,
                output_size_behavior="same_as_input")
        self.assertEqual(mask_edit_mode("acme", "img-1"), "native_mask")

    def test_mode_is_always_declared_value(self):
        declare("acme", "img-1", returns_aligned_crop=True, output_size_behavior="same_as_input")
        declare("acme", "img-2", supports_masked_edit=True)
        declare("acme", "img-3", local_edit_ok=False)
        for provider, model in (("acme", "img-1"), ("acme", "img-2"), ("acme", "img-3"),
                                ("nobody", "x")):
            self.assertIn(mask_edit_mode(provider, model), MASK_EDIT_MODES)


class AutoAcceptTests(RegistryResetMixin, unittest.TestCase):
    def test_unregistered_cannot_auto_accept(self):
        self.assertFalse(can_auto_accept("acme", "img-1"))

    def test_native_mask_but_unaligned_cannot_auto_accept(self):
        declare("acme", "img-1", supports_masked_edit=True, returns_aligned_crop=False)
        self.assertFalse(can_auto_accept("acme", "img-1"))

    def test_aligned_but_no_native_mask_cannot_auto_accept(self):
        declare("acme", "img-1", supports_masked_edit=False, returns_aligned_crop=True)
        self.assertFalse(can_auto_accept("acme", "img-1"))

    def test_both_flags_enable_auto_accept(self):
        declare("acme", "img-1", supports_masked_edit=True, returns_aligned_crop=True)
        self.assertTrue(can_auto_accept("acme", "img-1"))


class LookupTests(RegistryResetMixin, unittest.TestCase):
    def test_exact_match_beats_wildcard(self):
        declare("acme", "*", returns_aligned_crop=True, output_size_behavior="same_as_input")
        declare("acme", "special", supports_masked_edit=True)
        self.assertEqual(mask_edit_mode("acme", "other"), "local_edit")
        self.assertEqual(mask_edit_mode("acme", "special"), "native_mask")

    def test_lookup_is_case_and_space_insensitive(self):
        declare("ACME", "IMG-1", returns_aligned_crop=True, output_size_behavior="same_as_input")
        self.assertEqual(mask_edit_mode(" acme ", " img-1 "), "local_edit")

    def test_declare_merges_over_existing(self):
        declare("acme", "img-1", returns_aligned_crop=True, output_size_behavior="same_as_input")
        declare("acme", "img-1", supports_alpha_mask=True)
        cap = provider_capability("acme", "img-1")
        self.assertTrue(cap.supports_alpha_mask)
        self.assertTrue(cap.returns_aligned_crop)   # 未被覆盖的字段保留

    def test_as_dict_shape(self):
        declare("acme", "img-1", supports_masked_edit=True, returns_aligned_crop=True)
        payload = provider_capability("acme", "img-1").as_dict()
        for key in ("provider", "model", "supports_masked_edit", "supports_alpha_mask",
                    "input_size_constraints", "output_size_behavior", "returns_aligned_crop",
                    "supports_idempotency_or_job_query", "local_edit_ok", "maskEditMode"):
            self.assertIn(key, payload)


if __name__ == "__main__":
    unittest.main()
