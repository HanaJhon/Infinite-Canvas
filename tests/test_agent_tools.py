"""工具表冒烟：改工具/删功能后最容易漏的是「某处还引用着已删掉的常量」，
这种 NameError 要到真正跑起来那一刻才炸（2026-11-13 删内置浏览器时就是这样）。
这里把工具名挨个过一遍 label 与 schema 组装，静态常量掉队会直接报错。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


def test_every_tool_has_label():
    specs = main.AGENT_TOOL_SPECS + main.AGENT_ALWAYS_ON_TOOL_SPECS
    assert specs
    for spec in specs:
        label = main.agent_tool_label(spec["name"])
        assert label and label != spec["name"], spec["name"]


def test_schemas_and_hints_build():
    schemas = main.agent_tool_schemas("full")
    assert schemas and all(s["function"]["name"] for s in schemas)
    always = [s["function"]["name"] for s in main.agent_always_on_tool_schemas()]
    assert always, always
    hints = main.agent_always_on_hints()
    assert isinstance(hints, str) and hints.strip()


def test_unknown_tool_label_falls_back():
    assert main.agent_tool_label("no_such_tool") == "no_such_tool"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
