"""上下文自动压缩阈值 + 联网搜索的代理绕过。

老板要求：上下文缓存用到窗口 80% 就自动压缩，并压到最低（只留最近 2 条 + 摘要），
否则请求会被上游 400。另：搜索必须绕开系统代理，本机代理会让一次必应请求慢到 30s+。
"""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


class AutoCompressTests(unittest.IsolatedAsyncioTestCase):
    def test_threshold_is_80_percent_of_window(self):
        # 缓存用到窗口 80% 就压，不封顶：1M 窗口 800K，128K 窗口 102.4K
        self.assertEqual(main.auto_compress_threshold("gpt-5"), 800_000)
        self.assertEqual(main.auto_compress_threshold("gemini-2.5-pro"), 800_000)
        self.assertEqual(main.auto_compress_threshold("deepseek-chat"), 102_400)

    async def test_compress_triggers_and_keeps_recent(self):
        async def fake_summarize(text, payload):
            return "摘要：" + text[:20]

        payload = types.SimpleNamespace(model="gpt-5", provider="x", ms_model="")
        long_text = "这是一段很长的历史对话内容。" * 4000  # 单条 ≈ 60K token
        messages = [{"role": "user", "content": f"{i}:{long_text}"} for i in range(8)]
        conversation = {"id": "t", "messages": messages, "updated_at": 0}

        with patch.object(main, "llm_summarize", fake_summarize):
            window, did = await main.maybe_auto_compress(conversation, payload)

        self.assertTrue(did)
        self.assertEqual(len(window), main.COMPRESS_KEEP_RECENT + 1)  # 摘要 + 最近 N 条
        self.assertEqual(window[0]["role"], "system")
        self.assertIn("[对话历史摘要", window[0]["content"])
        self.assertTrue(conversation.get("_auto_compressed"))

    async def test_short_conversation_untouched(self):
        payload = types.SimpleNamespace(model="gpt-5", provider="x", ms_model="")
        conversation = {"id": "t", "messages": [{"role": "user", "content": "你好"}], "updated_at": 0}
        window, did = await main.maybe_auto_compress(conversation, payload)
        self.assertFalse(did)
        self.assertEqual(len(window), 1)


class WebProxyBypassTests(unittest.TestCase):
    def test_web_get_uses_proxy_less_opener(self):
        # urllib 会读注册表里的 ProxyServer；这个 opener 必须显式清空代理，
        # 否则本机代理会把 1s 的搜索拖成 30s+ 超时。
        import urllib.request
        handlers = [h for h in main._WEB_DIRECT_OPENER.handlers
                    if isinstance(h, urllib.request.ProxyHandler)]
        # 显式传了空 ProxyHandler 后，opener 里连代理 handler 都不会有
        self.assertEqual([h.proxies for h in handlers if h.proxies], [])


if __name__ == "__main__":
    unittest.main()
