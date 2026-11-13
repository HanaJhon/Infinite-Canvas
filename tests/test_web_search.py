"""联网搜索解析层的自检（不联网，只喂固定 HTML）。

覆盖三处踩过的坑：
1. 必应 /ck/a?u=a1<base64url> 是点击统计壳，不还原的话 web_read 只能读到跳转脚本。
2. 搜狗 href 是 /link?url=<加密串>，解析器必须认出来（真链在后面的 330 字节页面里）。
3. 必应被限流时会返回"只命中查询里一个词"的泛结果，_filter_relevant 必须挡住。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

BING_PAGE = '''
<ol id="b_results">
<li class="b_algo"><h2><a href="https://www.bing.com/ck/a?!&amp;&amp;p=x&amp;u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9h">OpenAI News</a></h2>
<div class="b_caption"><p>openai 官方新闻</p></div></li>
<li class="b_ad"><h2><a href="https://ads.example.com">广告别进来</a></h2></li>
</ol>
'''

SOGOU_PAGE = '''
<div class="vrwrap"><h3 class="vr-title"><a href="/link?url=abc">\u559c\u5267\u4e4b\u738b \u5267\u7248</a></h3>
<div class="fz-mid space-txt">\u5468\u661f\u9a70 \u5ba2\u4e32\u7684\u8bf4\u6cd5</div></div>
<div class="vrwrap"><div class="sdmb_ad">\u5e7f\u544a\u6a2a\u5e45</div></div>
'''


def test_bing_unwrap():
    items = main._parse_bing(BING_PAGE)
    assert len(items) == 1, items  # 广告位 b_ad 不是 b_algo，天然排除
    assert items[0]["url"] == "https://example.com/a", items[0]["url"]
    assert items[0]["title"] == "OpenAI News"


def test_sogou_parse():
    original = main._sogou_target
    main._sogou_target = lambda href, timeout=4: "https://example.com/sg"  # 不联网
    try:
        items = main._parse_sogou(SOGOU_PAGE)
    finally:
        main._sogou_target = original
    # 只有 h3 的那个块算结果；真链还原失败时整条丢掉（不留没法读的跳转链接）
    assert len(items) == 1, items
    assert items[0]["title"] == "\u559c\u5267\u4e4b\u738b \u5267\u7248"
    assert "snippet" in items[0]


def test_relevance_gate():
    tokens = main._query_tokens("nano banana 2 release date")
    junk = [{"title": "nano \u6587\u672c\u7f16\u8f91\u5668\u6559\u7a0b", "url": "https://a", "snippet": ""}]
    good = [{"title": "Nano Banana 2 release date", "url": "https://b", "snippet": ""}]
    assert main._filter_relevant(junk, tokens) == []
    assert len(main._filter_relevant(good, tokens)) == 1


def test_parse_handles_garbage():
    # 被反爬验证页替换时，解析器必须安静地返回空，而不是抛异常
    for parser in (main._parse_bing, main._parse_ddg_lite, main._parse_sogou):
        assert parser("<html><body>\u8bf7\u9a8c\u8bc1\u4f60\u662f\u4eba\u7c7b</body></html>") == []


ARGO_STUB = """
import json, sys
print(json.dumps({"count": 2, "engines_used": ["anysearch"], "results": [
    {"title": "A", "url": "https://a.example/x", "snippet": "snip a"},
    {"title": "B", "url": "not-a-url", "snippet": "drop me"},
    {"title": "", "url": "https://b.example/y", "snippet": ""},
]}))
"""


def test_argo_parse_and_filter():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        runner = os.path.join(tmp, "runner.py")
        with open(runner, "w", encoding="utf-8") as fh:
            fh.write(ARGO_STUB)
        original = main.ARGO_RUNNER
        main.ARGO_RUNNER = runner
        try:
            items, error = main._argo_search("x", 5)
        finally:
            main.ARGO_RUNNER = original
    # 非 http 的条目要丢掉；空 title 用 url 顶上，别让模型看到空标题
    assert error == "", error
    assert [i["url"] for i in items] == ["https://a.example/x", "https://b.example/y"]
    assert items[1]["title"] == "https://b.example/y"


def test_argo_missing_runner_degrades():
    original = main.ARGO_RUNNER
    main.ARGO_RUNNER = os.path.join(main.BASE_DIR, "tools", "__nope__.py")
    try:
        items, error = main._argo_search("x")
    finally:
        main.ARGO_RUNNER = original
    assert items == [] and error  # 装不上 argo 也要能回落到原引擎，不能抛


def test_result_payload_format():
    data = main._web_results_payload(
        [{"title": "T", "url": "https://t", "snippet": "s"}], "argo")
    assert data["ok"] and data["engine"] == "argo"
    assert "1. T" in data["output"] and "https://t" in data["output"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
