"""墓碑必须跟着画布落盘（服务端行为）。

只放内存挡不住：另一个标签页本地还有这些节点，它保存时会按「仅本地存在」把节点并回来；
刷新也会从服务器旧副本恢复。所以 `PUT /api/canvases/{id}` 要收 `deleted_node_ids` 并持久化，
同时把「本次就是要删掉这些节点」的保存从丢节点护栏里放行。
"""
import asyncio
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402

STORE = {}


def _install_fakes():
    def fake_load(canvas_id):
        return copy.deepcopy(STORE['canvas'])

    def fake_save(canvas):
        canvas['updated_at'] = int(canvas.get('updated_at') or 0) + 1
        STORE['canvas'] = copy.deepcopy(canvas)

    main.load_canvas = fake_load
    main.save_canvas = fake_save


def _seed(nodes):
    STORE['canvas'] = {
        'id': 'test', 'title': 't', 'kind': 'smart', 'nodes': copy.deepcopy(nodes),
        'connections': [], 'logs': [], 'settings': {}, 'updated_at': 5,
    }
    return 5


def _save(nodes, tombstones, base):
    payload = main.CanvasSaveRequest(
        title='t', nodes=nodes, connections=[], viewport={}, logs=[], settings={},
        base_updated_at=base, deleted_node_ids=tombstones,
    )
    return asyncio.run(main.update_canvas('test', payload))


def test_delete_is_allowed_and_persisted():
    _install_fakes()
    base = _seed([{'id': 'A'}, {'id': 'B'}])
    _save([{'id': 'A'}], ['B'], base)
    assert STORE['canvas']['deleted_node_ids'] == ['B']
    assert [n['id'] for n in STORE['canvas']['nodes']] == ['A']


def test_untombstoned_drop_still_409():
    _install_fakes()
    _seed([{'id': 'A'}, {'id': 'B'}])
    # 陈旧 base（别人又存过）且没带墓碑 ⇒ 按丢节点拦下，防止旧页面抹掉别人的节点
    try:
        _save([{'id': 'A'}], [], 4)
    except main.HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError('陈旧 base 且没有墓碑的丢节点保存必须 409')


def test_tombstone_survives_and_undo_releases():
    _install_fakes()
    base = _seed([{'id': 'A'}, {'id': 'B'}])
    _save([{'id': 'A'}], ['B'], base)
    # 另一个标签页还没收到广播：它带着 B 保存，墓碑不能被它抹掉…… 这里模拟「没带 B 也没带墓碑」
    _save([{'id': 'A'}], [], STORE['canvas']['updated_at'])
    assert STORE['canvas']['deleted_node_ids'] == ['B']
    # 撤销把 B 找回来 ⇒ 墓碑放行
    _save([{'id': 'A'}, {'id': 'B'}], [], STORE['canvas']['updated_at'])
    assert STORE['canvas']['deleted_node_ids'] == []


if __name__ == '__main__':
    test_delete_is_allowed_and_persisted()
    test_untombstoned_drop_still_409()
    test_tombstone_survives_and_undo_releases()
    print('OK canvas-tombstone-save')
