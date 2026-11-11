"""小抽AI 技能面板后端自检：自建 Skill → 读原文 → 出现在已安装 → 卸载干净。

用临时会话（注入 data/sessions.json，跑完还原）+ 跑完删掉自检建出来的 Skill 目录，
不碰老板的真实 Skill 索引（index.json 前后逐字节还原）。
"""
import json, os, shutil, subprocess, time, urllib.request, urllib.error

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE)
DATA = os.path.join(BASE, "data")
UID = "u_ee306dc0833a2bff"
TOKEN = "__xvai_skills_selftest__"
PORT = 3018
NAME = "__自检Skill__"
SESSION_PATH = os.path.join(DATA, "sessions.json")
INDEX_PATH = os.path.join(DATA, "agent_skills", "index.json")


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Cookie", f"ic_session={TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def main():
    session_bak = SESSION_PATH + ".selftest.bak"
    shutil.copy2(SESSION_PATH, session_bak)
    index_bak = None
    if os.path.exists(INDEX_PATH):
        index_bak = INDEX_PATH + ".selftest.bak"
        shutil.copy2(INDEX_PATH, index_bak)
    skill_id = ""
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

        body = "# 自检 Skill\n\n只在自检脚本运行时存在，用来验证自建/读取/卸载三条路径。"
        code, got = call("POST", "/api/skills/create", {"name": NAME, "content": body})
        assert code == 200, f"创建失败 {code} {got}"
        skill_id = got["skill"]["id"]
        assert skill_id.startswith("custom-"), skill_id
        assert any(s["id"] == skill_id for s in got["installed"]), "创建后没进已安装列表"

        code, got = call("GET", f"/api/skills/{skill_id}/content")
        assert code == 200 and got.get("exists") is True, f"读原文失败 {code} {got}"
        assert "自检 Skill" in got["content"], got["content"][:80]

        code, got = call("GET", "/api/skills/installed")
        assert code == 200 and any(s["id"] == skill_id for s in got["skills"]), "已安装列表里没有"

        code, got = call("POST", "/api/skills/uninstall", {"id": skill_id})
        assert code == 200 and got.get("ok"), f"卸载失败 {code} {got}"
        assert not any(s["id"] == skill_id for s in got["installed"]), "卸载后仍在列表里"
        assert not os.path.isdir(os.path.join(DATA, "agent_skills", skill_id)), "卸载后目录还在"

        print("SELF-CHECK OK：自建 / 读原文 / 已安装 / 卸载 四条路径")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:
            proc.kill()
        if skill_id:
            shutil.rmtree(os.path.join(DATA, "agent_skills", skill_id), ignore_errors=True)
        if index_bak and os.path.exists(index_bak):
            shutil.move(index_bak, INDEX_PATH)
        shutil.move(session_bak, SESSION_PATH)


main()
