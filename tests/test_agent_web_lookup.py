"""画布 Agent 的联网开关：判断函数 + 流式路径接线（老板 2026-11-13）。"""
import io, os, re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(HERE, 'main.py')
JS = os.path.join(HERE, 'static', 'js', 'smart-canvas.js')


def load_helper():
    src = io.open(MAIN, encoding='utf-8').read()
    m = re.search(r'^_WEB_LOOKUP_HINTS = \(.*?\n\)\n\n\ndef agent_needs_web_lookup.*?\n    return .*?\n', src, re.S | re.M)
    assert m, '找不到 agent_needs_web_lookup'
    ns = {}
    exec(m.group(0), ns)
    return ns['agent_needs_web_lookup']


def main():
    needs = load_helper()
    # 该联网的
    for q in ["gpt-6 最新版本是多少", "帮我查一下 nano-banana 的价格", "搜一下今天的 AI 新闻", "current price of X"]:
        assert needs(q), q
    # 不该联网的
    for q in ["帮我画一张赛博朋克城市", "把这张图改成水彩风格", "整理成 3 个方向"]:
        assert not needs(q), q

    src = io.open(MAIN, encoding='utf-8').read()
    stream = src.split('async def canvas_llm_stream', 1)[1].split('\nasync def ', 1)[0]
    assert 'agent_needs_web_lookup(payload.message)' in stream, '流式路径没有接联网判断'
    # 非流式路径本来就把常开联网工具挂上了，别被改掉
    plain = src.split('async def canvas_llm(payload', 1)[1]
    assert 'agent_always_on_tool_schemas()' in plain, '非流式路径丢了常开工具'

    js = io.open(JS, encoding='utf-8').read()
    assert '【联网能力】' in js and 'web_search' in js, '系统提示词里没有告诉模型能联网'

    print('OK agent-web-lookup')


if __name__ == '__main__':
    main()
