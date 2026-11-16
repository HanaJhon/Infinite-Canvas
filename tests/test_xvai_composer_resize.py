"""小抽AI 输入栏可向上拖动变高。

抓手放在 `.agent-onebox` 顶部（composer 的上边框），拖动时改 `#agentInput` 的 inline height；
composer 是底部锚定的 flex 项，所以高度变大时上边框上移。高度记忆在 localStorage。
拖动本身用无头 Edge + CDP 鼠标事件验证过（input 107→193px，composer top 599→512）。
这里只钉源码约定，防止抓手被挪走或夹高度上限把拖动吃掉。
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with io.open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def test_grip_markup():
    html = read('static/xvai.html')
    box = html.index('<div class="agent-onebox">')
    grip = html.index('id="xvResizeGrip"')
    # 抓手必须是 onebox 的第一个子元素：在 onebox 开始之后、顶部工具条之前
    toolbar = html.index('class="agent-topbar', box)
    assert box < grip < toolbar, '抓手必须在 .agent-onebox 顶部（工具条之前）'


def test_grip_css_and_height_cap():
    css = read('static/css/xvai-agent.css')
    assert '.xv-resize-grip' in read('static/xvai.html')
    assert 'cursor:ns-resize' in read('static/xvai.html')
    # 默认 200px 会把拖动结果夹住
    assert re.search(r'html \.xv-agent \.agent-input-rich \{[^}]*max-height:55vh', css)


def test_drag_handler():
    html = read('static/xvai.html')
    start = html.index('bindComposerResize')
    body = html[start:start + 1600]
    assert "grip.addEventListener('pointerdown'" in body
    assert 'startH - (e.clientY - startY)' in body, '向上拖必须变高（反向差值）'
    assert 'localStorage.setItem(KEY' in body
    assert 'xvai-input-height' in body


if __name__ == '__main__':
    test_grip_markup()
    test_grip_css_and_height_cap()
    test_drag_handler()
    print('OK xvai-composer-resize')
