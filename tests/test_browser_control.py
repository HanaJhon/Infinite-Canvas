"""内置浏览器：工具始终可用、提示词告诉模型画面是公开的、手动输入走 CDP。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import browser_control
import main


class BrowserBuiltinTests(unittest.TestCase):
    def tool_names(self):
        return [spec["function"]["name"] for spec in main.agent_always_on_tool_schemas()]

    def test_tool_always_available(self):
        # 不再有「授权开关」：工具一直挂在模型面前，否则等于骗它去调不存在的工具
        self.assertIn("browser", self.tool_names())
        self.assertIn("browser", main.agent_always_on_hints())
        self.assertIn("面板", main.agent_always_on_hints())

    def test_label_resolves(self):
        self.assertEqual(main.agent_tool_label("browser"), "浏览器操作")

    def test_manual_input_model(self):
        req = main.BrowserInputRequest(type="click", x=10.5, y=20)
        self.assertEqual((req.type, req.x, req.y), ("click", 10.5, 20))

    def test_session_singleton_is_reusable(self):
        first = browser_control.get_session("D:/tmp/profile")
        self.assertIs(first, browser_control.get_session("D:/tmp/profile"))


if __name__ == "__main__":
    unittest.main()
