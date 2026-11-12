"""小抽AI 执行过程实时推送（/api/chat/agent/stream 的 trace 事件）回归测试。

跑法：./python/python.exe tests/test_agent_trace.py
（tests 不是包，不能用 -m unittest tests.x）

守的是什么：工具循环里 on_event 推出来的「调了什么工具 / 想了什么」，
必须能在 SSE 流里按发生顺序出现在 done 之前 —— 页面据此实时列执行过程。
"""
import asyncio
import shutil
import sys
import unittest

sys.path.insert(0, ".")   # 嵌入式 Python 的 sys.path 不带脚本目录

import main  # noqa: E402


class _Req:
    client = None


async def _fake_decide(payload, conversation, refs):
    return {"action": "chat", "reply": ""}


def _make_fake_reply(events):
    async def _fake_reply(payload, conversation, user_id=None, on_event=None):
        on_event({"type": "tool_start", "name": "web_search", "label": "联网搜索", "args": "美国雪山"})
        await asyncio.sleep(0.02)
        on_event({"type": "tool_end", "name": "web_search", "label": "联网搜索", "ok": True, "summary": "搜索到 35 个网页"})
        on_event({"type": "thinking", "text": "先查滑雪场"})
        return {
            "id": "m1", "role": "assistant", "content": "答案", "created_at": 0,
            "model": "m1", "raw_usage": {}, "tool_events": [],
        }
    return _fake_reply


class AgentTraceTest(unittest.TestCase):
    UID = "__t_agent_trace__"

    def tearDown(self):
        shutil.rmtree(main.user_dir(self.UID), ignore_errors=True)

    def test_trace_events_stream_before_done(self):
        original_decide, original_reply = main.decide_chat_agent_action, main.build_chat_text_reply
        main.decide_chat_agent_action = _fake_decide
        main.build_chat_text_reply = _make_fake_reply(None)
        try:
            payload = main.ChatRequest(message="美国雪山推荐", mode="agent", provider="p", model="m")

            async def run():
                return [ev async for ev in main.chat_agent_events(payload, _Req(), self.UID)]

            events = asyncio.get_event_loop().run_until_complete(run())
        finally:
            main.decide_chat_agent_action, main.build_chat_text_reply = original_decide, original_reply

        kinds = [ev["event"] for ev in events]
        self.assertEqual(kinds[-1], "done")
        traces = [ev["trace"]["type"] for ev in events if ev["event"] == "trace"]
        # 顺序 = 发生顺序；且都在 done 之前（kinds 里 done 是最后一个）
        self.assertEqual(traces, ["tool_start", "tool_end", "thinking"])
        self.assertNotIn("trace", kinds[:kinds.index("trace")] if "trace" in kinds else [])

    def test_emit_swallows_broken_callback(self):
        def boom(_ev):
            raise RuntimeError("回调炸了")
        main._emit(boom, {"type": "tool_start"})   # 不应抛出


if __name__ == "__main__":
    unittest.main(verbosity=2)
