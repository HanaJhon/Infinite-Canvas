# -*- coding: utf-8 -*-
"""生成 Skill 市场的中文简介表（static/skills-i18n-zh.json）。

**为什么需要它**：`static/skills-catalog.json` 由 `tools/build_skills_catalog.py` 重刷，
每次重刷都可能带进新 id —— 新 id 在离线中文表里没有对应译文，市场里就会显示英文。
重刷快照后跑一遍本工具即可补齐（已译的会跳过，可随时中断续跑）。

用法（密钥只走环境变量，**不要写进仓库**）：

    set SKILL_I18N_API_KEY=sk-xxx
    set SKILL_I18N_BASE_URL=https://api.example.com/v1     # 可选，默认取 SKILL_I18N_BASE_URL 或报错
    set SKILL_I18N_MODEL=deepseek-v4.1-flash               # 可选，逗号分隔可给多个（按顺序降级）
    ./python/python.exe tools/translate_skills.py

    # 本机已把可用通道写在 ~/.codex/config.toml 时（省去手工配环境变量；token 不会入库）：
    ./python/python.exe tools/translate_skills.py --from-codex-config

    # 不联网：只用已有译文 + tools/skills_i18n_manual.json 重写中文表
    ./python/python.exe tools/translate_skills.py --table-only

产物：static/skills-i18n-zh.json —— 随包发布，**离线可用**。
联网搜到的、表里没有的 Skill 由后端 `POST /api/skills/i18n` 按需翻译（见 main.py）。

⚠️ 源文按 MAX_SRC 截断后再翻：卡片本来就只显示三四行，整段译出来又长又慢。
   译文因此是「原说明开头的简明译文」，不是全文逐字翻译。
⚠️ 模型会**漏译**：一批 12 条偶尔只回 8~11 条，跑完看输出的「仍有 N 条没有译文」，
   直接**再跑一遍**（断点续跑只补缺的）；反复翻不出来的极少数条目写进
   `tools/skills_i18n_manual.json` 手工兜底（那份文件进 git，可评审）。
"""
import os, re, sys, json, threading, concurrent.futures, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, 'static', 'skills-catalog.json')
OUT_FILE = os.path.join(ROOT, 'static', 'skills-i18n-zh.json')
WORK_FILE = os.path.join(ROOT, 'output', '_skill_i18n_work.json')   # 断点续跑用（output/ 已 gitignore）
MANUAL_FILE = os.path.join(ROOT, 'tools', 'skills_i18n_manual.json')  # 手工兜底译文（进 git）

BATCH = 12          # 单请求条数：实测 12 条（body ~2.5KB）在快模型上约 5s；再大容易上游超时
WORKERS = 4         # 并发；实测 4 并发不触发限流
MAX_SRC = 320       # 源文截断长度
REQUEST_TIMEOUT = 90

SYS_PROMPT = (
    "你是技术文档译者。把用户给的 JSON 里每个 value（英文 Skill 简介）译成简体中文。"
    "硬性要求：① 只输出 JSON，不要 Markdown 代码块、不要任何解释；② key 原样保留；"
    "③ 技术名词、产品名、命令、文件名保持英文原文；④ 每条译文不超过 60 个汉字，"
    "只译核心意思（原文可能被截断，按能读到的部分译，不要脑补）；"
    "⑤ 保持原文语气：名词短语译成名词短语，祈使句译成祈使句。"
)

# ⚠️ 顺序即优先级：实测 deepseek-v4.1-flash 单批 12 条约 5s，而 glm-5.3-flash 单批 6 条要 54s、
# 12 条直接 90s 超时。慢模型是「能返回」而不是「不能用」，所以**不会自动降级**到下一个 ——
# 必须靠排序避开，否则 800 条会从「3 分钟」变成「1.5 小时」。
DEFAULT_MODELS = ['deepseek-v4.1-flash', 'glm-5.3-flash', 'glm-5.3']
CODEX_CONFIG = os.path.expanduser('~/.codex/config.toml')


def from_codex_config():
    """从 ~/.codex/config.toml 读本机已配置的中转通道（token 只读进内存，不落盘、不回显）。"""
    try:
        text = open(CODEX_CONFIG, encoding='utf-8-sig').read()
    except Exception as exc:
        sys.exit('读不到 %s：%s' % (CODEX_CONFIG, exc))
    token = re.search(r'experimental_bearer_token\s*=\s*["\']([^"\']+)["\']', text)
    base = re.search(r'base_url\s*=\s*["\']([^"\']+)["\']', text)
    if not token or not base:
        sys.exit('%s 里找不到 base_url / experimental_bearer_token' % CODEX_CONFIG)
    return token.group(1), base.group(1).rstrip('/'), list(DEFAULT_MODELS)


def config(from_codex=False):
    key = str(os.getenv('SKILL_I18N_API_KEY') or '').strip()
    base = str(os.getenv('SKILL_I18N_BASE_URL') or '').strip().rstrip('/')
    models = [m.strip() for m in str(os.getenv('SKILL_I18N_MODEL') or '').split(',') if m.strip()]
    if key and base and models:
        return key, base, models
    if from_codex:
        return from_codex_config()
    sys.exit('请先设置 SKILL_I18N_API_KEY / SKILL_I18N_BASE_URL / SKILL_I18N_MODEL 三个环境变量，'
             '或加 --from-codex-config 复用 ~/.codex/config.toml 里的通道')


def trim(text):
    """截断到 MAX_SRC，尽量切在句末，避免把单词劈成两半。"""
    text = str(text or '').strip()
    if len(text) <= MAX_SRC:
        return text
    head = text[:MAX_SRC]
    cut = max(head.rfind('. '), head.rfind('! '), head.rfind('? '))
    if cut >= 80:
        return head[:cut + 1]
    cut = head.rfind(' ')
    return (head[:cut] if cut > 0 else head) + '…'


def call(base, key, model, payload):
    body = json.dumps({
        'model': model, 'temperature': 0, 'stream': False,
        'messages': [{'role': 'system', 'content': SYS_PROMPT},
                     {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
    }, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        base + '/chat/completions', data=body, method='POST',
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key,
                 'User-Agent': 'InfiniteCanvasLauncher/1.0'})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.loads(resp.read().decode('utf-8', 'replace'))
    return ((data.get('choices') or [{}])[0].get('message') or {}).get('content') or ''


def parse_reply(text):
    """从模型回复里抠出 {id: 中文}。只收含中文的条目（防模型原样回显英文）。"""
    raw = str(text or '').strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```[a-zA-Z]*\s*', '', raw)
        raw = re.sub(r'```\s*$', '', raw).strip()
    try:
        data = json.loads(raw)
    except Exception:
        start, end = raw.find('{'), raw.rfind('}')
        if start < 0 or end <= start:
            return {}
        try:
            data = json.loads(raw[start:end + 1])
        except Exception:
            return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        clean = str(v or '').strip()
        if k and clean and re.search(r'[\u4e00-\u9fff]', clean):
            out[str(k)] = clean
    return out


def load_manual():
    """手工兜底译文（模型反复翻不出来的条目）。任何异常都退化成空表，绝不中断流程。"""
    try:
        data = json.load(open(MANUAL_FILE, encoding='utf-8'))
    except Exception:
        return {}
    entries = data.get('entries') if isinstance(data, dict) else None
    if not isinstance(entries, dict):
        return {}
    return {str(k): str(v).strip() for k, v in entries.items()
            if str(v or '').strip() and re.search(r'[\u4e00-\u9fff]', str(v))}


def write_table(skills, done, manual):
    """按清单 id 顺序落成随包中文表。"""
    entries = {}
    for skill in skills:
        sid = str(skill.get('id') or '')
        text = str(done.get(sid) or manual.get(sid) or '').strip()
        if text and re.search(r'[\u4e00-\u9fff]', text):
            entries[sid] = text
    payload = {
        'schema': 1,
        'source': 'skillsmp',
        'lang': 'zh',
        'note': '内置 Skill 市场清单的中文简介；由 tools/translate_skills.py 生成。'
                '源文为英文说明的开头部分（截断后译），非全文逐字翻译。',
        'count': len(entries),
        'entries': entries,
    }
    with open(OUT_FILE, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return payload, [str(s.get('id')) for s in skills if str(s.get('id')) not in entries]


def main(table_only=False, from_codex=False):
    skills = json.load(open(CATALOG, encoding='utf-8-sig'))['skills']
    manual = load_manual()
    done = {}
    if os.path.exists(WORK_FILE):
        try:
            done = json.load(open(WORK_FILE, encoding='utf-8'))
        except Exception:
            done = {}

    if not table_only:
        key, base, models = config(from_codex)
        todo = [s for s in skills
                if str(s.get('id')) not in done and str(s.get('id')) not in manual]
        print('清单 %d 条，已有译文 %d 条，手工兜底 %d 条，待译 %d 条（%d 并发）'
              % (len(skills), len(done), len(manual), len(todo), WORKERS), flush=True)
        if todo:
            batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
            lock = threading.Lock()
            stat = {'ok': 0, 'fail': 0, 'n': 0}

            def run_batch(chunk):
                payload = {str(s['id']): trim(s.get('summary')) for s in chunk}
                last = ''
                for model in models:
                    try:
                        got = {k: v for k, v in parse_reply(call(base, key, model, payload)).items()
                               if k in payload}
                        if got:
                            return got, model, ''
                        last = '%s 返回空/无中文' % model
                    except Exception as exc:
                        detail = ''
                        if isinstance(exc, urllib.error.HTTPError):
                            try:
                                detail = exc.read().decode('utf-8', 'replace')[:100]
                            except Exception:
                                detail = ''
                        last = '%s %s %s' % (model, type(exc).__name__, detail)
                return {}, '', last

            with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
                for fut in concurrent.futures.as_completed([pool.submit(run_batch, b) for b in batches]):
                    got, model, err = fut.result()
                    with lock:
                        if got:
                            done.update(got)
                            os.makedirs(os.path.dirname(WORK_FILE), exist_ok=True)
                            with open(WORK_FILE, 'w', encoding='utf-8') as f:
                                json.dump(done, f, ensure_ascii=False, indent=1)
                            stat['ok'] += 1
                        else:
                            stat['fail'] += 1
                        stat['n'] += 1
                        print('[批 %d/%d] +%d 累计 %d 失败 %d %s'
                              % (stat['n'], len(batches), len(got), len(done), stat['fail'],
                                 ('via ' + model) if got else err), flush=True)
            print('抓取完成：成功批 %d，失败批 %d' % (stat['ok'], stat['fail']), flush=True)

    payload, missing = write_table(skills, done, manual)
    size = os.path.getsize(OUT_FILE) / 1024
    print('已写出 %s（%d / %d 条，%.1f KB）' % (OUT_FILE, payload['count'], len(skills), size), flush=True)
    if missing:
        print('⚠️ 仍有 %d 条没有译文（这些会显示英文原文）：%s'
              % (len(missing), ', '.join(missing[:8])), flush=True)
        print('   再跑一遍本工具补缺；反复翻不出来的写进 %s' % MANUAL_FILE, flush=True)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='生成 Skill 市场中文简介表')
    ap.add_argument('--table-only', action='store_true',
                    help='不联网：只用已有译文 + 手工兜底重写中文表')
    ap.add_argument('--from-codex-config', action='store_true',
                    help='从 ~/.codex/config.toml 读通道（免配环境变量；token 不会入库）')
    args = ap.parse_args()
    main(table_only=args.table_only, from_codex=args.from_codex_config)
