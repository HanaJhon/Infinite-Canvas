"""对话记录防丢的三道锁（老板 2026-11-13：任何修改都不能动到用户记录）。

只在源码层面钉住约定，因为真正的写盘路径需要登录态才能跑。
跑法：./python/python.exe -c "import sys;sys.path.insert(0,'tests');import test_agent_state_guard as t;t.main()"
"""
import io, os, re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(HERE, 'main.py')
CANVAS_JS = os.path.join(HERE, 'static', 'js', 'smart-canvas.js')


def main():
    main_src = io.open(MAIN, encoding='utf-8').read()
    js = io.open(CANVAS_JS, encoding='utf-8').read()

    # 1. 服务端：覆盖成空状态前必须留 .bak
    put = main_src.split('async def agent_state_put', 1)[1].split('\n@app.', 1)[0]
    assert 'path + ".bak"' in put, 'PUT 覆盖前没有留 .bak'
    assert 'not (new_convs or new_msgs)' in put, '没有按「新状态为空才备份」的规则判断'
    assert put.index('.bak') < put.index('os.replace(tmp, path)'), '备份必须在写入之前'

    # 2. 服务端：能读回备份
    assert '/api/agent/state/{canvas_id}/bak' in main_src, '缺少读取 .bak 的接口'

    # 3. 前端：localStorage 解析失败先另存原文，且本次不写盘
    assert "__bak__" in js, '前端没有备份钥匙'
    assert '_storageUnreadable' in js, '前端没有「原文损坏就别写盘」的标记'
    load = js.split('function loadAgentState()', 1)[1].split('function ', 1)[0]
    assert '_storageUnreadable = true' in load, '解析失败时没打标记'
    save = js.split('function saveAgentState()', 1)[1].split('function ', 1)[0]
    assert 'if(!agentState._storageUnreadable){' in save, '损坏状态下仍在写盘'
    assert 'localStorage.setItem(agentStorageKey() + \'__bak__\'' in save, '清空覆盖前没留本地备份'

    print('OK agent-state-guard')


if __name__ == '__main__':
    main()
