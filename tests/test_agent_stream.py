"""小抽AI 思考内容流式增量（_stream_chat_completion）回归测试。

跑法：./python/python.exe tests/test_agent_stream.py

守的是什么：上游按 SSE 一段段吐 delta 时，思考内容要边收边推给前端
（append=True 的增量事件），工具调用参数要能跨段拼起来，
上游忽略 stream 直接回整包时也不能报错。
"""
import sys
import unittest

sys.path.insert(0, ".")   # 嵌入式 Python 的 sys.path 不带脚本目录

import main  # noqa: E402


def _sse(*chunks):
    return [(c if isinstance(c, str) else "data: " + c) for c in chunks]


class _Resp:
    def __init__(self, lines, ctype="text/event-stream", status=200, body=""):
        self._lines = lines
        self.headers = {"content-type": ctype}
        self.status_code = status
        self._body = body
        self.request = None

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return self._body.encode("utf-8")


class _Ctx:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return False


class _Client:
    def __init__(self, resp):
        self._resp = resp

    def stream(self, method, url, headers=None, json=None):
        return _Ctx(self._resp)


class StreamThinkingTest(unittest.IsolatedAsyncioTestCase):
    async def test_thinking_deltas_are_appended_incrementally(self):
        lines = _sse(
            '{"choices":[{"delta":{"reasoning_content":"先看' '"}}]}',
            '{"choices":[{"delta":{"reasoning_content":"一下画布"}}]}',
            '{"choices":[{"delta":{"reasoning_content":"，再决定调用哪个工具。"}}]}',
            '{"choices":[{"delta":{"content":"好了"}}]}',
            "data: [DONE]",
        )
        events = []
        result = await main._stream_chat_completion(
            _Client(_Resp(lines)), "http://x/chat/completions", {}, {}, events.append
        )
        self.assertEqual(result["content"], "好了")
        self.assertEqual(result["reasoning"], "先看一下画布，再决定调用哪个工具。")
        appended = [e for e in events if e.get("type") == "thinking"]
        self.assertGreaterEqual(len(appended), 2, "思考内容要边收边推，不能攒到最后一次性给")
        self.assertTrue(all(e.get("append") for e in appended))
        self.assertEqual("".join(e["text"] for e in appended), result["reasoning"])

    async def test_tool_call_arguments_join_across_chunks(self):
        lines = _sse(
            '{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"web_search","arguments":"{\\"que"}}]}}]}',
            '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"ry\\":\\"雪场\\"}"}}]}}]}',
            '{"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
            "data: [DONE]",
        )
        result = await main._stream_chat_completion(_Client(_Resp(lines)), "http://x", {}, {})
        calls = result["tool_calls"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["id"], "c1")
        self.assertEqual(calls[0]["function"]["name"], "web_search")
        self.assertEqual(main.agent_parse_tool_args(calls[0]["function"]["arguments"]), {"query": "雪场"})

    async def test_upstream_ignoring_stream_still_parses(self):
        body = '{"choices":[{"message":{"content":"整包回复","reasoning_content":"整包思考"}}],"usage":{"total_tokens":9}}'
        events = []
        result = await main._stream_chat_completion(
            _Client(_Resp([], ctype="application/json", body=body)), "http://x", {}, {}, events.append
        )
        self.assertEqual(result["content"], "整包回复")
        self.assertEqual(result["usage"], {"total_tokens": 9})
        self.assertEqual([e["text"] for e in events], ["整包思考"])
        self.assertNotIn("append", events[0], "整包解析就不该标成增量")


if __name__ == "__main__":
    unittest.main()
