"""浏览器控制授权：开关没打开时，工具不能出现在模型眼前、也不能被调用。"""
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


class BrowserControlPermissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.file = Path(self.temp.name) / "browser_control.json"
        self.patches = [
            patch.object(main, "BROWSER_CONTROL_FILE", str(self.file)),
            patch.object(main, "BROWSER_PROFILE_DIR", str(Path(self.temp.name) / "profile")),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def tool_names(self):
        return [spec["function"]["name"] for spec in main.agent_always_on_tool_schemas()]

    def test_default_is_off(self):
        self.assertFalse(main.load_browser_control_settings()["enabled"])
        self.assertNotIn("browser", self.tool_names())
        self.assertEqual(main.agent_browser_hint(), "")

    async def test_enable_grants_tool_and_hint(self):
        main.save_browser_control_settings(True)
        self.assertIn("browser", self.tool_names())
        self.assertIn("browser", main.agent_browser_hint())
        # 落盘可读回，服务重启后授权还在
        on_disk = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertTrue(on_disk["enabled"])

    async def test_disabled_refuses_call(self):
        result = await main.agent_tool_browser({"action": "read"})
        self.assertFalse(result["ok"])
        self.assertIn("没有授权", result["summary"])

    async def test_label_resolves(self):
        self.assertEqual(main.agent_tool_label("browser"), "浏览器操作")


if __name__ == "__main__":
    unittest.main()
