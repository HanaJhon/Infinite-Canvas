"""画布 Agent 与小抽AI 用同一套后台（老板 2026-11-13：换成小抽AI 的 agent，默认全权限）。"""
import io, json, os, re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = io.open(os.path.join(HERE, 'main.py'), encoding='utf-8').read()
JS = io.open(os.path.join(HERE, 'static', 'js', 'smart-canvas.js'), encoding='utf-8').read()


def _node_check_trace():
    """把 handleAgentLlmEventMessage 抠出来，用 node 真跑一遍，确认事件→trace 行的逻辑。"""
    import subprocess, tempfile
    start = JS.index('function handleAgentLlmEventMessage(data){')
    end = JS.index('\n}\n', start) + 3
    fn = JS[start:end]
    script = f"""
let _agentStreamTaskId = 't1';
let _agentStreamCancelled = false;
let _agentStreamTrace = [];
const _agentStreamPendingTrace = new Map();
function renderAgentStreamBubble() {{}}
{fn}
// 思考：只留最新一条
handleAgentLlmEventMessage({{task_id:'t1', event:{{phase:'thinking', text:'第 1 轮推理中…'}}}});
handleAgentLlmEventMessage({{task_id:'t1', event:{{phase:'thinking', text:'第 2 轮推理中…'}}}});
handleAgentLlmEventMessage({{task_id:'t1', event:{{phase:'tool_start', name:'run_shell', label:'执行命令'}}}});
handleAgentLlmEventMessage({{task_id:'t1', event:{{phase:'tool_end', name:'run_shell', label:'执行命令', ok:true, summary:'完成'}}}});
// 别的任务先缓存
handleAgentLlmEventMessage({{task_id:'t2', event:{{phase:'thinking', text:'x'}}}});
const out = {{
  lines: _agentStreamTrace.map(t => t.text),
  pending: _agentStreamPendingTrace.get('t2')?.length || 0,
  ignored: _agentStreamTrace.filter(t => t.text.indexOf('t2') >= 0).length,
}};
console.log(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile('w', suffix='.mjs', delete=False, encoding='utf-8') as f:
        f.write(script)
        path = f.name
    raw = subprocess.run(['node', path], capture_output=True, text=True, encoding='utf-8').stdout.strip()
    os.unlink(path)
    data = json.loads(raw)
    assert data['lines'] == ['第 2 轮推理中…', '执行 执行命令…', '执行命令 完成 · 完成'], data['lines']
    assert data['pending'] == 1 and data['ignored'] == 0, data


def main():
    # 1. 默认全权限：run_shell / write_file 默认就该在工具集里
    assert 'CODEX_DEFAULT_PERMISSION = "danger-full-access"' in MAIN
    assert re.search(r'denied = \{"read-only": \{"run_shell", "write_file"\}\}', MAIN), '权限裁剪逻辑被改了'

    # 2. 画布 Agent 与小抽AI 共用同一套能力块
    canvas = MAIN.split('async def canvas_llm(payload', 1)[1]
    for needle in ('agent_tool_schemas()', 'agent_always_on_tool_schemas()',
                   'installed_skills_prompt_block', 'agent_file_capability_block',
                   'AGENT_TOOLS_SYSTEM_HINT', 'agent_always_on_hints()'):
        assert needle in canvas, f'画布 Agent 缺少 {needle}'

    # 3. 执行过程实时推给前端（和小抽AI 的 trace 对齐）
    assert 'async def broadcast_agent_llm_event' in MAIN
    assert '"type": "agent_llm_event"' in MAIN
    assert 'async def _agent_trace' in MAIN
    for phase in ('"phase": "thinking"', '"phase": "tool_start"', '"phase": "tool_end"'):
        assert phase in canvas, f'缺少 {phase} 事件'
    assert 'result = await canvas_llm(payload, task_id=task_id)' in MAIN

    # 4. 前端：收事件 + 渲染在流式气泡里
    assert "data?.type === 'agent_llm_event'" in JS
    assert 'function handleAgentLlmEventMessage' in JS
    assert 'agent-stream-trace' in JS
    assert '_agentStreamTrace = [];' in JS

    # 5. 本机工具跑得久，5 分钟硬超时会把正常任务判死
    assert '30 * 60 * 1000' in JS

    _node_check_trace()

    print('OK agent-backend-parity')


if __name__ == '__main__':
    main()
