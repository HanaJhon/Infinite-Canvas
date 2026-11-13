"""工具轮数用尽的防线：最后一轮必须撤掉工具，逼模型拿已有结果给结论。

老板截图里的事故：模型连搜 14 次，8 轮跑满后只丢一句「已达到工具调用轮数上限」，
整轮白跑。现在最后一轮不再传 tools，改为塞一条「给结论」的系统提示。
"""
import asyncio
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import main  # noqa: E402


class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.content = b"{}"
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Client:
    """记录每轮请求体，按脚本回 tool_calls 或正文。"""

    def __init__(self, bodies, script):
        self.bodies = bodies
        self.script = script
        self.n = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self.bodies.append(json)
        step = self.script[min(self.n, len(self.script) - 1)]
        self.n += 1
        return _Resp({"choices": [{"message": step}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}})


def _run(max_rounds, script):
    bodies = []
    payload = types.SimpleNamespace(message="查一下某某新闻", reasoning_effort="", provider="p", model="m",
                                    ms_model="", images=[], videos=[], attachments=[], mode="agent")

    async def fake_post(url, headers=None, json=None):
        bodies.append(json)
        step = script[min(len(bodies) - 1, len(script) - 1)]
        return _Resp({"choices": [{"message": step}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}})

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        post = staticmethod(fake_post)

    orig = {
        "httpx": main.httpx,
        "maybe_auto_compress": main.maybe_auto_compress,
        "chat_system_prompt": main.chat_system_prompt,
        "agent_profile_block": main.agent_profile_block,
        "installed_skills_prompt_block": main.installed_skills_prompt_block,
        "agent_file_capability_block": main.agent_file_capability_block,
        "run_agent_tool": main.run_agent_tool,
    }

    class FakeHttpx:
        AsyncClient = FakeClient
        HTTPStatusError = orig["httpx"].HTTPStatusError

    async def fake_compress(conversation, payload, user_id=None):
        return [{"role": "user", "content": "查一下某某新闻"}], False

    async def fake_tool(name, args):
        return {"ok": True, "summary": "6 条结果（argo）", "output": "url1"}

    main.httpx = FakeHttpx
    main.maybe_auto_compress = fake_compress
    main.chat_system_prompt = lambda payload: "system"
    main.agent_profile_block = lambda: ""
    main.installed_skills_prompt_block = lambda q: ""
    main.agent_file_capability_block = lambda: ""
    main.run_agent_tool = fake_tool
    try:
        reply = asyncio.run(main.build_chat_text_reply_with_tools(
            payload,
            {"messages": []},
            {},
            True,          # is_apimart=True → 走非流式 client.post，测试更好搭
            "http://stub",
            {},
            "m",
            {"enabled": True, "max_rounds": max_rounds},
        ))
    finally:
        main.httpx = orig["httpx"]
        main.maybe_auto_compress = orig["maybe_auto_compress"]
        main.chat_system_prompt = orig["chat_system_prompt"]
        main.agent_profile_block = orig["agent_profile_block"]
        main.installed_skills_prompt_block = orig["installed_skills_prompt_block"]
        main.agent_file_capability_block = orig["agent_file_capability_block"]
        main.run_agent_tool = orig["run_agent_tool"]
    return reply, bodies


CALL = {"content": "", "tool_calls": [{"id": "c1", "type": "function",
                                        "function": {"name": "web_search", "arguments": '{"query":"x"}'}}]}


def test_final_round_drops_tools_and_forces_conclusion():
    # 模型一直想搜；最后一轮（第 rounds 次之后）必须被逼出结论
    reply, bodies = _run(2, [CALL, CALL, {"content": "结论：某某新闻发生在周三。", "tool_calls": []}])
    assert len(bodies) == 3, bodies            # 2 轮工具 + 1 轮收尾
    assert "tools" in bodies[0] and "tools" in bodies[1]
    assert "tools" not in bodies[2], "最后一轮必须撤掉工具"
    hint = bodies[2]["messages"][-1]
    assert hint["role"] == "system" and "工具轮数已用完" in hint["content"]
    assert "已达到工具调用轮数上限" not in reply["content"]
    assert reply["content"].startswith("结论：")
    assert len(reply["tool_events"]) == 2


def test_single_round_still_works():
    reply, bodies = _run(8, [{"content": "直接回答", "tool_calls": []}])
    assert len(bodies) == 1 and "tools" in bodies[0]
    assert reply["content"] == "直接回答"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
