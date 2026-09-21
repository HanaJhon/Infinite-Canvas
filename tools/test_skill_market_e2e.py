# -*- coding: utf-8 -*-
"""用本地假 SkillsMP 服务跑通「健康路径」全链路（真实 HTTP + 真实线程 + 真实节流）。

为什么需要它：真 IP 被限流后，成功路径没法在真接口上复现；而成功路径才是常态。
这里用一个本地 HTTP 服务扮演 /api/skills，验证：
  · 探针 + 两批次共 25 次请求全部走通
  · 节流闸确实把并发压成 1/1.2s 的速率
  · 去重 / 单仓库限量 / 排序 / 标签 都正确
  · 抓够条数后正常写入缓存并清冷却

跑法：./python/python.exe tools/test_skill_market_e2e.py
"""
import os, sys, json, time, threading, shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import main as app

FAILED = []
def check(name, cond, extra=""):
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAILED.append(name)

CACHE, STATE = app.SKILLS_MARKET_CACHE, app.SKILLS_MARKET_STATE
BACKUP = CACHE + ".e2ebak"
if os.path.exists(CACHE):
    shutil.copy2(CACHE, BACKUP)
for p in (CACHE, STATE):
    if os.path.exists(p):
        os.remove(p)

# ---------- 假 SkillsMP：每页 48 条，共 60 页；记录请求时刻用于验证节流 ----------
PAGE_SIZE = 48
TOTAL_PAGES = 60
hits = []            # 每次请求的 (时刻, 排序, 页码)
hit_lock = threading.Lock()

def make_skill(sort, page, idx):
    n = (page - 1) * PAGE_SIZE + idx
    # 让仓库分布既有巨型仓库也有大量小仓库，才能验证「单仓库限量」
    if sort == "stars":
        owner, repo = ("mega/repo", "main") if n % 3 else ("big/tool", "main")
    else:
        owner, repo = ("dev%d/pkg%d" % (n % 40, n % 7), "main")
    name = "%s-skill-%d" % (sort, n)
    return {
        "id": "raw-%s-%d" % (sort, n),
        "name": name,
        "author": owner.split("/")[0],
        "description": "A %s helper for testing design and data workflows" % sort,
        "contentLanguage": "en",
        "githubUrl": "https://github.com/%s/%s" % (owner, repo),
        "stars": 400000 - n if sort == "stars" else 5000 - (n % 4000),
        "forks": 80000 - n if sort == "stars" else 1000 - (n % 900),
        "updatedAt": 1789000000 - n * 60,
        "path": "skills/%s/SKILL.md" % name,
        "branch": repo,
        "route": {"ownerSlug": owner, "repoSlug": repo, "routeSlug": name,
                  "sourceSkillPath": "skills/%s/SKILL.md" % name},
    }

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a):
        pass
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        sort = (q.get("sortBy") or ["stars"])[0]
        page = int((q.get("page") or ["1"])[0])
        limit = int((q.get("limit") or ["48"])[0])
        if limit > 48:
            self.send_response(400); self.end_headers(); return
        with hit_lock:
            hits.append((time.time(), sort, page))
        rows = [make_skill(sort, page, i) for i in range(min(limit, PAGE_SIZE))]
        body = json.dumps({"skills": rows,
                           "pagination": {"total": TOTAL_PAGES * PAGE_SIZE,
                                          "page": page, "maxResults": 1200}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
print("假 SkillsMP 已启动: http://127.0.0.1:%d/api/skills" % port)

real_api = app.SKILLSMP_API
app.SKILLSMP_API = "http://127.0.0.1:%d/api/skills" % port
app.SKILL_MARKET_MIN_INTERVAL = 0.12      # 真值是 1.2s，测试里缩到 1/10 省时间

print("\n=== 健康路径全链路 ===")
t0 = time.time()
cache, note = app.refresh_skills_market(force=True)
el = time.time() - t0
check("刷新成功（note 为空）", note is None, note)
check("耗时 > 25×0.12s（节流生效）", el > 25 * 0.12, round(el, 2))

skills = (cache or {}).get("skills") or []
check("抓到足够条数（≥ 500）", len(skills) >= 500, len(skills))
check("缓存已落盘", os.path.exists(CACHE))
st = app.load_skills_market_state()
check("冷却已清空", float(st.get("cooldown_until") or 0) == 0)

stats = (cache or {}).get("stats") or {}
check("探针 + 24 页 = 25 次成功", stats.get("total_pages") == 25, stats)
check("失败 0 页", stats.get("fail") == 0, stats)
check("未中止", stats.get("aborted") is False, stats)

print("\n=== 节流闸真的把并发压住了 ===")
hits_sorted = sorted(hits, key=lambda h: h[0])
gaps = [round(hits_sorted[i + 1][0] - hits_sorted[i][0], 3) for i in range(len(hits_sorted) - 1)]
check("请求数 = 25（探针 1 + stars 4 + recent 20）", len(hits_sorted) == 25, len(hits_sorted))
check("最小间隔 ≥ 0.10s（约等于设定值，允许调度误差）", min(gaps) >= 0.10, min(gaps))
check("平均间隔 ≈ 0.12s", 0.10 <= sum(gaps) / len(gaps) <= 0.35, round(sum(gaps) / len(gaps), 3))

print("\n=== 归一化 / 去重 / 限量 ===")
ids = [s["id"] for s in skills]
check("id 无重复", len(ids) == len(set(ids)))
repos = {}
for s in skills:
    repos[s["repo"]] = repos.get(s["repo"], 0) + 1
check("单仓库不超过 8 条", max(repos.values()) <= 8, max(repos.values()))
check("仓库数 > 100（多样性）", len(repos) > 100, len(repos))
check("按 star 降序", all(skills[i]["stars"] >= skills[i + 1]["stars"] for i in range(len(skills) - 1)))
check("都带 raw_url", all(s["raw_url"].startswith("https://raw.githubusercontent.com/") for s in skills))
check("都带 source_url", all("/creators/" in s["source_url"] for s in skills))
check("都打了标签", all(s["tags"] for s in skills))
check("标题已 Title Case", skills[0]["title"] == skills[0]["title"].title() or " " in skills[0]["title"],
      skills[0]["title"])

print("\n=== 落盘的 payload ===")
pay = app.skills_market_payload(refresh=False)
check("total = 缓存条数", pay["total"] == len(skills), (pay["total"], len(skills)))
check("online = True", pay["online"] is True)
check("hotness = stars + forks×2", pay["skills"][0]["hotness"] ==
      pay["skills"][0]["stars"] + pay["skills"][0]["forks"] * 2)
check("refresh_note 为空", pay["refresh_note"] == "")
check("按 hotness 降序", all(pay["skills"][i]["hotness"] >= pay["skills"][i + 1]["hotness"]
                             for i in range(len(pay["skills"]) - 1)))

print("\n=== 二次刷新走 TTL 不联网 ===")
n_before = len(hits)
cache2, note2 = app.refresh_skills_market(force=False)
check("未发新请求", len(hits) == n_before, (n_before, len(hits)))
check("note 为空", note2 is None)

srv.shutdown()
app.SKILLSMP_API = real_api

# 收尾
for p in (CACHE, STATE):
    if os.path.exists(p):
        os.remove(p)
if os.path.exists(BACKUP):
    shutil.move(BACKUP, CACHE)

print("\n" + ("全部通过 ✅" if not FAILED else "失败项: %s ❌" % FAILED))
sys.exit(1 if FAILED else 0)
