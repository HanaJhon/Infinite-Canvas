"""关掉 LLM 就不能再用上一次的 LLM 结果生图（老板 2026-11-13）。

三条护栏都在 static/js/smart-canvas.js 里，这里只做静态断言：谁把它们改回去就红。
真机复现路径：选 LLM → 跑一次图 → 关 LLM → 再跑，提交的必须是左栏用户原文。
"""
import io
import re
import sys

SRC = 'static/js/smart-canvas.js'


def main():
    src = io.open(SRC, encoding='utf-8').read()

    # 1) 关掉的早退分支只能回用户原文
    assert 'if(!s?.llmEnabled) return prompt;' in src, '关掉 LLM 后仍在回放上次 LLM 结果'
    assert 'return readyFinal || prompt;' not in src, 'readyFinal 兜底又回来了'

    # 2) LLM 开关必须落到正在操作的节点（activeComposerNode 为空时用选中节点）
    assert 'activeComposerNode() || (isSmartRunnableNode(selectedNode()) ? selectedNode() : null)' in src, \
        'persistActiveSmartSettings 丢了开关'

    # 3) 上游取文本：图片节点要遵守自己的 LLM 开关
    assert "return nodeLlmSwitchOn(node) ? nodeLlmFinalPrompt(node) : '';" in src, \
        'textForNode 又把旧 LLM 结果交给下游'

    # 4) 开关判定函数存在且提示词节点走自己的 llmEnabled
    assert 'function nodeLlmSwitchOn(node){' in src
    body = re.search(r'function nodeLlmSwitchOn\(node\)\{(.*?)\n\}', src, re.S).group(1)
    assert 'promptNodeLlmActive(node)' in body
    assert 'llmEnabled' in body

    print('OK 关掉 LLM 后不再回放上一次的 LLM 结果')


if __name__ == '__main__':
    sys.exit(main())
