import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import Request
from fastapi.responses import PlainTextResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from backend.security import (
    configured_cors_origins,
    is_control_plane_request,
    origin_matches_host,
    websocket_origin_allowed,
)
from backend.split_budget import SplitLayersBudget, normalize_budget


def make_request(path, method="GET", host="192.168.1.20", headers=None):
    headers = {"Host": "192.168.1.20:3000", **(headers or {})}
    raw_headers = [
        (str(key).lower().encode("latin-1"), str(value).encode("latin-1"))
        for key, value in headers.items()
    ]
    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": raw_headers,
        "client": (host, 3000),
        "scheme": "http",
        "server": (host, 3000),
    })


class SecurityControlTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, request):
        async def next_call(_request):
            return PlainTextResponse("ok")

        return await main.protect_control_plane(request, next_call)

    async def test_token_endpoint_never_returns_plaintext_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "global_config.json"
            config_path.write_text(json.dumps({"modelscope_token": "server-secret-value"}), encoding="utf-8")
            with patch.object(main, "GLOBAL_CONFIG_FILE", str(config_path)), patch.object(main, "modelscope_api_key", return_value="server-secret-value"):
                payload = await main.get_global_token()

        self.assertTrue(payload["has_token"])
        self.assertNotIn("server-secret-value", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("token_mask", payload)

    async def test_remote_read_endpoints_remain_available(self):
        for path in ("/api/config/token", "/api/providers", "/api/agent/tools"):
            response = await self.invoke(make_request(path))
            self.assertEqual(response.status_code, 200, path)

    async def test_remote_management_request_requires_control_token(self):
        with patch.dict(os.environ, {}, clear=True):
            response = await self.invoke(make_request("/api/providers", method="PUT"))
        self.assertEqual(response.status_code, 403)

    async def test_remote_management_request_rejects_wrong_token(self):
        with patch.dict(os.environ, {"INFINITE_CANVAS_CONTROL_TOKEN": "control-secret"}, clear=False):
            response = await self.invoke(make_request(
                "/api/providers",
                method="PUT",
                headers={"X-Admin-Token": "wrong"},
            ))
        self.assertEqual(response.status_code, 403)

    async def test_cross_site_management_request_is_rejected(self):
        with patch.dict(os.environ, {"INFINITE_CANVAS_CONTROL_TOKEN": "control-secret"}, clear=False):
            response = await self.invoke(make_request(
                "/api/providers",
                method="PUT",
                headers={"X-Admin-Token": "control-secret", "Origin": "https://evil.example"},
            ))
        self.assertEqual(response.status_code, 403)

    async def test_localhost_cross_site_management_request_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            response = await self.invoke(make_request(
                "/api/providers",
                method="PUT",
                host="127.0.0.1",
                headers={"Host": "127.0.0.1:3000", "Origin": "https://evil.example"},
            ))
        self.assertEqual(response.status_code, 403)

    async def test_remote_management_request_accepts_correct_token(self):
        with patch.dict(os.environ, {"INFINITE_CANVAS_CONTROL_TOKEN": "control-secret"}, clear=False):
            response = await self.invoke(make_request(
                "/api/providers",
                method="PUT",
                headers={"X-Admin-Token": "control-secret"},
            ))
        self.assertEqual(response.status_code, 200)

    async def test_remote_management_request_accepts_same_lan_origin(self):
        with patch.dict(os.environ, {"INFINITE_CANVAS_CONTROL_TOKEN": "control-secret"}, clear=False):
            response = await self.invoke(make_request(
                "/api/providers",
                method="PUT",
                headers={"X-Admin-Token": "control-secret", "Origin": "http://192.168.1.20:3010"},
            ))
        self.assertEqual(response.status_code, 200)

    def test_cors_defaults_to_explicit_origins_only(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(configured_cors_origins(), [])
        with patch.dict(os.environ, {
            "INFINITE_CANVAS_CORS_ORIGINS":
                "http://192.168.1.20:3000, https://editor.example/ *"
        }, clear=True):
            self.assertEqual(
                configured_cors_origins(),
                ["http://192.168.1.20:3000", "https://editor.example"],
            )

    def test_dynamic_management_routes_require_control_token(self):
        protected = (
            ("PUT", "/api/runninghub/workflows/demo"),
            ("DELETE", "/api/runninghub/workflows/demo"),
            ("POST", "/api/workflows"),
            ("PUT", "/api/workflows/custom/demo.json/config"),
            ("DELETE", "/api/workflows/custom/demo.json"),
        )
        for method, path in protected:
            self.assertTrue(is_control_plane_request(method, path), (method, path))
        self.assertFalse(is_control_plane_request("POST", "/api/workflows/custom/demo.json/run"))
        self.assertFalse(is_control_plane_request("POST", "/api/runninghub/workflows/fetch"))

    def test_websocket_origin_policy_allows_native_clients_and_same_lan_host(self):
        native = SimpleNamespace(headers={}, client=("192.168.1.20", 3000))
        same_host = SimpleNamespace(
            headers={"origin": "http://192.168.1.20:3010", "host": "192.168.1.20:3000"},
            client=("192.168.1.20", 3000),
        )
        cross_site = SimpleNamespace(
            headers={"origin": "https://evil.example", "host": "192.168.1.20:3000"},
            client=("192.168.1.20", 3000),
        )
        self.assertTrue(websocket_origin_allowed(native))
        self.assertTrue(websocket_origin_allowed(same_host))
        self.assertFalse(websocket_origin_allowed(cross_site))

    def test_origin_policy_handles_ipv6_and_malformed_hosts(self):
        self.assertTrue(origin_matches_host("http://[::1]:3010", "[::1]:3000"))
        self.assertTrue(origin_matches_host("http://localhost:3010", "localhost:3000"))
        self.assertFalse(origin_matches_host("http://[::1]:3010", "127.0.0.1:3000"))
        self.assertFalse(origin_matches_host("not-an-origin", "[::1]:3000"))
        self.assertFalse(origin_matches_host("http://[broken", "localhost:3000"))
        self.assertFalse(origin_matches_host("http://localhost", "[broken"))
        self.assertFalse(origin_matches_host("", ""))
        self.assertFalse(origin_matches_host("javascript://localhost", "localhost:3000"))

    def test_public_provider_drops_credential_shaped_legacy_fields(self):
        provider = {
            "id": "legacy",
            "name": "Legacy",
            "api_key": "plaintext-api-key",
            "wallet_api_key": "plaintext-wallet-key",
            "volcengine_secret_access_key": "plaintext-secret",
            "custom_token": "plaintext-token",
            "image_models": ["demo"],
        }
        with patch.object(main, "provider_env_key_value", return_value=""):
            payload = main.public_provider(provider)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("plaintext-api-key", encoded)
        self.assertNotIn("plaintext-wallet-key", encoded)
        self.assertNotIn("plaintext-secret", encoded)
        self.assertNotIn("plaintext-token", encoded)
        self.assertEqual(payload["id"], "legacy")

    async def test_image_model_budget_is_atomic_before_upstream_request(self):
        payload = SimpleNamespace(
            image_provider_id="demo",
            image_model="image-model",
            provider_id="",
            model="",
        )
        budget = main.SplitLayersBudget(1)

        async def fake_save(*_args, **_kwargs):
            return "/output/reference.png"

        async def fake_build(_request):
            return {"images": ["https://example.invalid/result.png"]}

        with patch.object(main, "split_save_png", side_effect=fake_save), \
                patch.object(main, "split_candidate_channels", return_value=[("demo", "image-model")]), \
                patch.object(main, "build_online_image_result", side_effect=fake_build) as call:
            await main.split_call_image_model(
                payload, main.Image.new("RGBA", (16, 16), (0, 0, 0, 255)),
                "keep the image unchanged", budget=budget,
            )
            with self.assertRaises(main.HTTPException) as error:
                await main.split_call_image_model(
                    payload, main.Image.new("RGBA", (16, 16), (0, 0, 0, 255)),
                    "keep the image unchanged", budget=budget,
                )

        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(budget.snapshot(), {"limit": 1, "used": 1, "remaining": 0})

    async def test_repair_helpers_forward_shared_budget_to_upstream_boundary(self):
        payload = SimpleNamespace(
            image_provider_id="demo",
            image_model="image-model",
            provider_id="",
            model="",
        )
        image = main.Image.new("RGBA", (32, 32), (120, 120, 120, 255))
        mask = main.Image.new("L", image.size, 0)
        mask.paste(255, (8, 8, 24, 24))
        budget = main.SplitLayersBudget(2)
        forwarded = []

        async def fake_call(_payload, _img, _prompt, extra_images=None, budget=None, **_kwargs):
            forwarded.append(budget)
            return "https://example.invalid/result.png"

        async def fake_save(*_args, **_kwargs):
            return "/output/reference.png"

        with patch.object(main, "split_call_image_model", side_effect=fake_call), \
                patch.object(main, "split_save_png", side_effect=fake_save), \
                patch.object(main, "output_file_from_url", return_value="result.png"), \
                patch.object(main.Image, "open", return_value=main.Image.new("RGBA", (384, 384))):
            await main.split_ai_repair(
                payload, image, 32, 32,
                {"id": "e1", "bbox": [4, 4, 16, 16]},
                image.copy(), {"kind": "edge"}, budget)
            await main.split_erase_elements(
                payload, image, 32, 32, None,
                mask=mask, budget=budget)

        self.assertEqual(forwarded, [budget, budget])
        self.assertEqual(budget.snapshot(), {"limit": 2, "used": 0, "remaining": 2})

    async def test_fallback_channels_share_the_attempt_limit(self):
        payload = SimpleNamespace()
        image = main.Image.new("RGBA", (16, 16))
        candidates = [("first", "model"), ("second", "model"), ("third", "model")]
        for limit in (1, 2):
            budget = SplitLayersBudget(limit)
            responses = [
                main.HTTPException(status_code=401, detail="invalid api key"),
                {"images": ["/output/result.png"]},
            ]
            with patch.object(main, "split_candidate_channels", return_value=candidates), \
                    patch.object(main, "split_save_png", return_value="/output/reference.png"), \
                    patch.object(main, "build_online_image_result", side_effect=responses) as call:
                if limit == 1:
                    with self.assertRaises(main.HTTPException) as caught:
                        await main.split_call_image_model(payload, image, "repair", budget=budget)
                    self.assertEqual(caught.exception.status_code, 429)
                else:
                    result = await main.split_call_image_model(payload, image, "repair", budget=budget)
                    self.assertEqual(result, "/output/result.png")
            self.assertEqual(call.call_count, limit)
            self.assertEqual(budget.snapshot()["used"], limit)

    async def test_timeout_consumes_budget_without_automatic_retry(self):
        budget = SplitLayersBudget(3)
        with patch.object(main, "split_candidate_channels", return_value=[("first", "model"), ("second", "model")]), \
                patch.object(main, "split_save_png", return_value="/output/reference.png"), \
                patch.object(main, "build_online_image_result",
                             side_effect=main.HTTPException(status_code=504, detail="timeout")) as call:
            with self.assertRaises(main.HTTPException):
                await main.split_call_image_model(
                    SimpleNamespace(), main.Image.new("RGBA", (16, 16)), "repair", budget=budget)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(budget.snapshot()["used"], 1)

    async def test_split_context_disables_hidden_post_retries(self):
        client = SimpleNamespace(request=AsyncMock(side_effect=main.httpx.ReadTimeout("stub timeout")))
        token = main.SPLIT_IMAGE_BUDGET_ACTIVE.set(True)
        try:
            with self.assertRaises(main.httpx.ReadTimeout):
                await main.httpx_request_with_transient_retries(
                    client, "POST", "https://example.invalid/images", attempts=3)
            self.assertEqual(client.request.call_count, 1)
            with patch.object(main, "get_api_provider",
                              return_value={"id": "stub", "image_models": ["stub"]}), \
                    patch.object(main, "generate_ai_image",
                                 side_effect=main.httpx.ReadTimeout("stub timeout")) as generate:
                with self.assertRaises(main.HTTPException):
                    await main.build_online_image_result(main.OnlineImageRequest(
                        provider_id="stub", model="stub", prompt="synthetic test"))
                self.assertEqual(generate.call_count, 1)
        finally:
            main.SPLIT_IMAGE_BUDGET_ACTIVE.reset(token)

    async def test_repair_statistics_include_failed_and_fallback_attempts(self):
        for produces_image in (False, True):
            image = main.Image.new("RGBA", (32, 32), (20, 40, 60, 255))
            state = {
                "src_rgba": image, "width": 32, "height": 32,
                "entries": [{"id": "bg"}], "plates": {"bg": image.copy()},
                "issues": [{"id": "issue", "layer_id": "bg", "kind": "background"}],
            }

            async def fake_erase(*_args, budget=None, **_kwargs):
                self.assertIsNotNone(budget)
                self.assertTrue(budget.spend())
                self.assertTrue(budget.spend())
                if not produces_image:
                    raise main.HTTPException(status_code=502, detail="no result")
                return main.Image.new("RGBA", image.size, (100, 120, 140, 255))

            task_id = "__test_budget_statistics__"
            with patch.dict(main.CANVAS_TASKS, {task_id: {"result": {}}}), \
                    patch.object(main, "split_state_get", return_value=state), \
                    patch.object(main, "split_state_put"), \
                    patch.object(main, "split_foreground_hole", return_value=main.Image.new("L", image.size)), \
                    patch.object(main, "split_erase_elements", side_effect=fake_erase), \
                    patch.object(main, "split_issue_score", return_value=0), \
                    patch.object(main, "split_quality_check", return_value=({}, [])), \
                    patch.object(main, "split_edge_check", return_value={}), \
                    patch.object(main, "split_save_png", return_value="/output/background.png"):
                await main.run_split_repair_task(task_id, main.SplitLayersRepairRequest(budget=2))
                task = main.CANVAS_TASKS[task_id]
                self.assertEqual(task["status"], "succeeded", task.get("error"))
                self.assertEqual(task["result"]["repairs"][0]["cost"], 2)
                self.assertEqual(task["result"]["stats"]["ai_calls"], 2)
                self.assertEqual(task["result"]["budget"]["used"], 2)
                state["issues"] = [{"id": "again", "layer_id": "bg", "kind": "background"}]
                await main.run_split_repair_task(task_id, main.SplitLayersRepairRequest(budget=2))
                self.assertEqual(task["result"]["budget"]["used"], 2,
                                 "repeating repair must not refill an exhausted task")

    def test_budget_normalization_handles_invalid_and_extreme_values(self):
        self.assertEqual(normalize_budget(None), 3)
        self.assertEqual(normalize_budget("not-a-number"), 3)
        self.assertEqual(normalize_budget(float("inf")), 3)
        self.assertEqual(normalize_budget(-4), 0)
        self.assertEqual(normalize_budget(1000), 64)

    def test_budget_snapshot_never_exceeds_limit(self):
        budget = SplitLayersBudget(2)
        self.assertTrue(budget.spend())
        self.assertTrue(budget.spend())
        self.assertFalse(budget.spend())
        self.assertEqual(budget.snapshot(), {"limit": 2, "used": 2, "remaining": 0})


if __name__ == "__main__":
    unittest.main()
