"""内置 Skill 要能在 / 面板里点到：接口要吐出来，/skill 要真能激活。

事故：小抽AI 的 / 面板只读 /api/skills/installed（市场里装的），随程序分发的
ego-browser / office-* / ponytail 根本不在列表里，用户看不到也点不到。
"""
import asyncio
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import main  # noqa: E402


def _payload():
    return types.SimpleNamespace(message="x", model="m", provider="", reasoning_effort="")


def test_builtin_list_includes_ego_browser():
    data = asyncio.run(main.skills_builtin())
    ids = [s["id"] for s in data["skills"]]
    assert "builtin:ego-browser" in ids, ids
    # 只给标题，别把几万字正文塞进面板请求
    for s in data["skills"]:
        assert set(s) == {"id", "name", "title", "builtin"}, s


def test_slash_skill_activates_builtin():
    conv = {"messages": [], "active_skill": None}
    for arg in ("ego-browser", "builtin:ego-browser"):
        conv["active_skill"] = None
        note = asyncio.run(main.handle_chat_slash_command("/skill " + arg, _payload(), conv, None))
        active = conv.get("active_skill") or {}
        assert active.get("id") == "builtin:ego-browser", (arg, active)
        assert len(active.get("text") or "") > 200        # SKILL.md 正文读进来了
        assert "已激活" in note["content"]


def test_unknown_skill_still_reports_not_found():
    conv = {"messages": [], "active_skill": None}
    note = asyncio.run(main.handle_chat_slash_command("/skill nope-does-not-exist", _payload(), conv, None))
    assert conv.get("active_skill") is None
    assert "未找到" in note["content"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
