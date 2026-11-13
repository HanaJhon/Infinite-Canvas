"""系统提示词必须带上今天的时间，否则模型会按训练数据里的年份瞎猜。"""

import datetime
import io
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import main  # noqa: E402


class _Payload:
    def __init__(self, system_prompt=""):
        self.system_prompt = system_prompt


class CurrentDateTest(unittest.TestCase):
    def test_default_prompt_carries_today(self):
        now = datetime.datetime.now()
        text = main.chat_system_prompt(_Payload())
        self.assertIn(now.strftime("%Y年%m月%d日"), text)
        self.assertIn("星期" + "一二三四五六日"[now.weekday()], text)
        self.assertIn("【当前时间】", text)
        # 原有提示词不能被顶掉
        self.assertIn(main.SYSTEM_PROMPT.strip()[:20], text)

    def test_custom_prompt_also_carries_today(self):
        now = datetime.datetime.now()
        text = main.chat_system_prompt(_Payload("你是测试用的系统提示词。"))
        self.assertTrue(text.startswith("你是测试用的系统提示词。"))
        self.assertIn(now.strftime("%Y年%m月%d日"), text)

    def test_block_is_computed_per_call(self):
        # 长跑的服务不能把启动那天的日期一直发出去
        calls = []
        for _ in range(2):
            calls.append(main.current_time_block())
        self.assertEqual(calls[0], calls[1])
        self.assertFalse(hasattr(main, "_CACHED_TIME_BLOCK"))


if __name__ == "__main__":
    unittest.main()
