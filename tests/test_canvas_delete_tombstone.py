"""删除节点后不能被「冲突合并」复活。

合并服务器快照是并集语义（`mergeSmartNodeLists`：仅对方存在的节点也加入），
所以本机刚删掉的节点会因为服务器旧副本、`POST .../touch` 顶新的 updated_at
触发的 409 合并、WS `canvas_updated`、meta 轮询而被重新加回来。
修法：`deleteNode()` 记墓碑 `deletedNodeIds`，合并时按墓碑过滤；撤销时清空（撤销可能合法地找回）。
这里只钉这三处，不测视觉。
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


def test_tombstone_declared():
    src = read('static/js/smart-canvas.js')
    assert 'const deletedNodeIds = new Set();' in src


def test_delete_records_tombstone():
    body = _function_body(read('static/js/smart-canvas.js'), 'deleteNode')
    assert 'deletedNodeIds.add(' in body, 'deleteNode 必须记墓碑，否则合并会把它复活'


def test_merge_filters_tombstone():
    body = _function_body(read('static/js/smart-canvas.js'), 'applyMergedServerCanvas')
    # 远端节点先过墓碑，再进并集合并
    assert 'deletedNodeIds.has(' in body
    assert re.search(r'deletedNodeIds\.has\(node\.id\).*?\n\s*const mergedNodes = mergeSmartNodeLists', body, re.S)


def test_undo_clears_tombstone():
    body = _function_body(read('static/js/smart-canvas.js'), 'performUndo')
    assert 'deletedNodeIds.clear();' in body


if __name__ == '__main__':
    test_tombstone_declared()
    test_delete_records_tombstone()
    test_merge_filters_tombstone()
    test_undo_clears_tombstone()
    print('OK canvas-delete-tombstone')
