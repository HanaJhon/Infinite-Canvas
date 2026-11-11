"""小抽AI 回溯编辑自检：POST /api/chat/agent 带 rewind_message_id 时，
后端必须先把这条 user 消息及其之后的消息丢掉，再追加新提问。

不需要真实 LLM 凭据：截断发生在调用上游之前，上游失败不影响断言。
用一个临时会话（注入到 data/sessions.json，跑完还原）+ 一次性对话文件。
"""
import json, os, shutil, subprocess, sys, time, urllib.request, urllib.error

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
DATA = os.path.join(BASE, "data")
UID = "u_ee306dc0833a2bff"
TOKEN = "__xvai_selftest__"
PORT = 3017
CONV_ID = "__selftest_rewind__"
CONV_PATH = os.path.join(DATA, "users", UID, "conversations", "ip-127.0.0.1", CONV_ID + ".json")
SESSION_PATH = os.path.join(DATA, "sessions.json")

def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Cookie", f"ic_session={TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")

def main():
    backup = SESSION_PATH + ".selftest.bak"
    shutil.copy2(SESSION_PATH, backup)
    os.makedirs(os.path.dirname(CONV_PATH), exist_ok=True)
    proc = subprocess.Popen(
        [os.path.join(BASE, "python", "python.exe"), "main.py", "--port", str(PORT)],
        cwd=BASE, stdout=open(os.path.join(BASE, "output", "_selftest_server.log"), "w"),
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/login.html", timeout=1).read()
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise SystemExit("服务没起来，看 output/_selftest_server.log")

        with open(SESSION_PATH, encoding="utf-8") as f:
            sessions = json.load(f)
        now = int(time.time())
        sessions[TOKEN] = {"uid": UID, "created_at": now, "expires_at": now + 3600}
        with open(SESSION_PATH, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)

        with open(CONV_PATH, "w", encoding="utf-8") as f:
            json.dump({"id": CONV_ID, "title": "自检", "created_at": now, "updated_at": now,
                       "messages": [{"id": "m1", "role": "user", "content": "第一问"},
                                    {"id": "m2", "role": "user", "content": "第二问"},
                                    {"id": "m3", "role": "assistant", "content": "第二答"}]},
                      f, ensure_ascii=False)

        # 回溯到 m2：m2/m3 必须被丢掉，最终只剩 m1 + 新提问
        code, _ = call("POST", "/api/chat/agent", {
            "conversation_id": CONV_ID, "message": "改成第二问的另一种说法",
            "rewind_message_id": "m2", "provider": "none", "model": "none",
        })
        code2, got = call("GET", f"/api/conversations/{CONV_ID}")
        msgs = (got.get("conversation") or {}).get("messages") or []
        assert code2 == 200, f"取会话失败 {code2} {got}"
        assert len(msgs) == 2, f"预期 2 条消息，实际 {len(msgs)}: {[m.get('content') for m in msgs]}"
        assert msgs[0]["id"] == "m1", msgs[0]
        assert msgs[1]["role"] == "user" and msgs[1]["content"] == "改成第二问的另一种说法", msgs[1]
        print(f"SELF-CHECK OK（上游返回 {code}，截断在调用上游之前已完成）")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:
            proc.kill()
        if os.path.exists(CONV_PATH):
            os.remove(CONV_PATH)
        shutil.move(backup, SESSION_PATH)

main()
