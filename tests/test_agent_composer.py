"""画布 Agent 输入栏：可调高度 + 附件胶囊能换位置 + 编辑后不再跑到句尾。

以前的两处根因：
1. `.agent-input-rich` 只有一行高，长提示词看不全（现在 min-height:40px + 原生 resize:vertical）。
2. `agentBeginEditMessage` / `agentResendMessage` 先把 `[图:xxx]` token 从正文里抹掉，
   再让 `syncAgentInlineChips()` 把胶囊补回输入框 —— 补回来只会 append，
   所以用户写在句子中间的附件，编辑一次就全长到句尾。
   现在改成 `agentInputSetRich(带 token 的原文)`，按 token 原位重建。
这里只钉源码约定与关键分支，拖动本身用无头 Edge 验证过（caretRangeFromPoint 落点换位）。
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _function_body(src, name):
    start = src.index(f'function {name}(')
    depth = 0
    i = src.index('{', start)
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise AssertionError(f'{name} 花括号不闭合')


def test_set_rich_rebuilds_chips_in_place():
    src = read('static/js/smart-canvas.js')
    body = _function_body(src, 'agentInputSetRich')
    assert 'agentMakeChipEl' in body, '必须按 token 位置造胶囊，而不是交给 syncAgentInlineChips 追加'
    assert 'AGENT_MSG_TOKEN_RE' in body


def test_edit_paths_use_set_rich():
    src = read('static/js/smart-canvas.js')
    for fn in ('agentBeginEditMessage', 'agentResendMessage'):
        body = _function_body(src, fn)
        assert 'agentInputSetRich(' in body, f'{fn} 必须用 agentInputSetRich 回填，否则附件落到句尾'
        assert "AGENT_MSG_TOKEN_RE.source, 'g'), ' ')" not in body, f'{fn} 不能在回填前把 token 抹成空格'


def test_chips_are_draggable():
    src = read('static/js/smart-canvas.js')
    body = _function_body(src, 'agentMakeChipEl')
    assert 'draggable = true' in body
    assert "addEventListener('drop'" in src and 'agentDraggingChip' in src


def test_input_resizable():
    css = read('static/css/smart-canvas.css')
    rule = re.search(r'\.agent-input-rich \{[^}]*\}', css).group(0)
    assert 'resize:vertical' in rule.replace(' ', '')
    assert 'min-height:40px' in rule.replace(' ', '')
