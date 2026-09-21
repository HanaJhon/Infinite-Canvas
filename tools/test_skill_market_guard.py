# -*- coding: utf-8 -*-
"""验证 Skill 市场刷新的四道防线（不联网，全部打桩）。

跑法：./python/python.exe tools/test_skill_market_guard.py
"""
import os, sys, json, time, shutil

# main.py 的 DATA_DIR/STATIC_DIR 基于 __file__（绝对路径），所以不必 chdir；
# 只需保证能从仓库根导入 main。
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import main as app

FAILED = []
def check(name, cond, extra=""):
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAILED.append(name)

CACHE = app.SKILLS_MARKET_CACHE
STATE = app.SKILLS_MARKET_STATE
BACKUP = CACHE + ".testbak"

def reset(remove_cache=True, remove_state=True):
    """⚠️ remove_state 必须独立控制 —— 否则想测「冷却期内不联网」时会被自己清掉状态。"""
    if os.path.exists(BACKUP):
        shutil.move(BACKUP, CACHE)
    if remove_cache and os.path.exists(CACHE):
        os.remove(CACHE)
    if remove_state and os.path.exists(STATE):
        os.remove(STATE)

def read_cache():
    if not os.path.exists(CACHE):
        return None
    with open(CACHE, encoding="utf-8") as f:
        return json.load(f)

# 备份老板机器上可能存在的真实缓存
if os.path.exists(CACHE):
    shutil.copy2(CACHE, BACKUP)

real_fetch_all = app.skillsmp_fetch_all
real_fetch_page = app.skillsmp_fetch_page
real_pace = app.skill_market_pace

def stub_fetch(rows, stats):
    def _f(sort, pages, guard_state=None):
        return list(rows), dict(stats)
    return _f

# ⚠️ build_skills_catalog_ex 会先「探一页」，探针走的是 skillsmp_fetch_page ——
# 不打桩就会真的联网。默认让探针成功，专测探针的用例再单独覆盖。
def probe_ok(sort, page):
    return [], None
app.skillsmp_fetch_page = probe_ok

print("\n=== A. 缓存被污染（194 条）时应回落到内置快照 615 条 ===")
reset(remove_cache=False)
if not os.path.exists(CACHE):
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"skills": [{"id": "x%d" % i, "stars": 1} for i in range(194)],
                   "refreshed_at": time.time()}, f)
pay = app.skills_market_payload(refresh=False)
check("污染缓存仍在 → 会显示 194 条（说明必须删掉它）", pay["total"] == 194, pay["total"])

os.remove(CACHE)
pay = app.skills_market_payload(refresh=False)
check("删掉污染缓存后 → 615 条内置快照", pay["total"] == 615, pay["total"])
check("source=skillsmp", pay["source"] == "skillsmp")
check("online=False（快照模式）", pay["online"] is False)
check("refresh_note 为空", pay["refresh_note"] == "")

print("\n=== B. 抓取不完整（3/24 页失败 = 12.5%... 用 5/24 触发）→ 拒绝覆盖 ===")
reset()
baseline_before = app.market_baseline_count()
check("基准条数 = 615", baseline_before == 615, baseline_before)
rows = [{"name": "s%d" % i, "stars": 100 - i, "route": {"ownerSlug": "o%d" % (i // 3),
        "repoSlug": "r", "sourceSkillPath": "SKILL.md", "routeSlug": "rs"}} for i in range(300)]
app.skillsmp_fetch_all = stub_fetch(rows, {"ok": 19, "fail": 5, "throttled": 5})
cache, note = app.refresh_skills_market(force=True)
check("返回了 note", bool(note), note)
check("note 说明不完整", "不完整" in (note or ""), note)
check("缓存未被写入", read_cache() is None)
st = app.load_skills_market_state()
check("已进入冷却", float(st.get("cooldown_until") or 0) > time.time())
check("冷却原因 = 抓取不完整", st.get("reason") == "抓取不完整", st.get("reason"))
app.skillsmp_fetch_all = real_fetch_all

print("\n=== C. 冷却期内不再联网（不调用 fetch）===")
reset(remove_cache=False, remove_state=False)   # 保留 state，验证冷却生效
called = [0]
def bomb(sort, pages, guard_state=None):
    called[0] += 1
    return [], {"ok": 0, "fail": 24, "throttled": 24, "aborted": False}
app.skillsmp_fetch_all = bomb
cache, note = app.refresh_skills_market(force=True)
check("fetch 完全没被调用", called[0] == 0, called[0])
check("note 提示冷却中", "冷却" in (note or ""), note)
app.skillsmp_fetch_all = real_fetch_all

print("\n=== D. 全部失败（429）→ 冷却 30 分钟 ===")
reset()
app.skillsmp_fetch_all = bomb
cache, note = app.refresh_skills_market(force=True)
check("note 提示抓取失败", "抓取失败" in (note or ""), note)
st = app.load_skills_market_state()
span = float(st.get("cooldown_until") or 0) - time.time()
check("冷却约 30 分钟", 1700 < span <= 1800, round(span))
check("缓存未写入", read_cache() is None)
app.skillsmp_fetch_all = real_fetch_all

print("\n=== E. 结果缩水（300 < 615×0.75）→ 拒绝覆盖 ===")
reset()
app.skillsmp_fetch_all = stub_fetch(rows, {"ok": 24, "fail": 0, "throttled": 0})
cache, note = app.refresh_skills_market(force=True)
check("note 提示缩水", "只返回" in (note or ""), note)
check("缓存未写入", read_cache() is None)
app.skillsmp_fetch_all = real_fetch_all

print("\n=== F. 正常成功（615+ 条）→ 写入缓存 + 清冷却 ===")
reset()
big = [{"name": "s%d" % i, "stars": 500 - i, "route": {"ownerSlug": "o%d" % (i // 3),
        "repoSlug": "r", "sourceSkillPath": "SKILL.md", "routeSlug": "rs"}} for i in range(900)]
app.skillsmp_fetch_all = stub_fetch(big, {"ok": 24, "fail": 0, "throttled": 0})
cache, note = app.refresh_skills_market(force=True)
check("成功时 note 为 None", note is None, note)
c = read_cache()
check("缓存已写入", bool(c and c.get("skills")))
check("缓存条数 ≥ 615", len(c.get("skills") or []) >= 615, len(c.get("skills") or []))
check("缓存带 stats", isinstance(c.get("stats"), dict), c.get("stats"))
st = app.load_skills_market_state()
check("冷却已清空", float(st.get("cooldown_until") or 0) == 0)
pay = app.skills_market_payload(refresh=False)
check("payload online=True", pay["online"] is True)
check("payload total = 缓存条数", pay["total"] == len(c.get("skills") or []), pay["total"])
app.skillsmp_fetch_all = real_fetch_all

print("\n=== G. 节流闸：并发下最小间隔仍然生效 ===")
app.SKILL_MARKET_MIN_INTERVAL = 0.3
app._SKILL_MARKET_LAST[0] = 0.0
t0 = time.time()
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(lambda _: app.skill_market_pace(), range(5)))
el = time.time() - t0
check("5 次请求耗时 ≥ 4×0.3s（并发未绕过闸门）", el >= 1.2, round(el, 2))

print("\n=== H. 连续限流 → 快速中止（不把 20 页全跑完）===")
reset()
import urllib.error
app.skillsmp_fetch_page = real_fetch_page       # 本用例要测真实的分页逻辑
calls = [0]
def boom(url, timeout=None):
    calls[0] += 1
    time.sleep(0.05)
    raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
real_get = app.skill_http_get
app.skill_http_get = boom
app.SKILL_MARKET_MIN_INTERVAL = 0.01
app.SKILL_MARKET_THROTTLE_RETRY = 0      # 去掉退避等待，单独验证「中止」逻辑
t0 = time.time()
rows, stats = app.skillsmp_fetch_all("recent", 20)
el = time.time() - t0
check("返回 0 行", rows == [])
check("全部失败且 ok=0", stats["fail"] > 0 and stats["ok"] == 0, stats)
check("已标记 aborted", stats["aborted"] is True, stats)
check("实际请求数 ≤ 10（远少于 20 页）", calls[0] <= 10, calls[0])
check("耗时 < 3s（未逐页退避死等）", el < 3, round(el, 2))
app.skill_http_get = real_get
app.SKILL_MARKET_THROTTLE_RETRY = 1

print("\n=== I. 网络异常（非 429）不触发中止，逐页重试 ===")
reset()
calls2 = [0]
def netdown(url, timeout=None):
    calls2[0] += 1
    raise urllib.error.URLError("temporary failure in name resolution")
app.skill_http_get = netdown
app.SKILL_MARKET_RETRY = 0
rows, stats = app.skillsmp_fetch_all("stars", 4)
check("4 页都尝试了", calls2[0] >= 4, calls2[0])
check("未标记 aborted（非限流不中止）", stats["aborted"] is False, stats)
check("fail = 4", stats["fail"] == 4, stats)
app.skill_http_get = real_get
app.SKILL_MARKET_RETRY = 2

print("\n=== J. 探针失败 → 直接放弃，不发起批量抓取（最坏路径 ~16s 而非 2 分钟）===")
reset()
batch_calls = [0]
def batch_spy(sort, pages, guard_state=None):
    batch_calls[0] += 1
    return [], {"ok": pages, "fail": 0, "throttled": 0, "aborted": False}
def probe_429(sort, page):
    return [], urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
app.skillsmp_fetch_all = batch_spy
app.skillsmp_fetch_page = probe_429
cache, note = app.refresh_skills_market(force=True)
check("批量抓取一次都没被调用", batch_calls[0] == 0, batch_calls[0])
check("note 提示抓取失败", "抓取失败" in (note or ""), note)
st = app.load_skills_market_state()
span = float(st.get("cooldown_until") or 0) - time.time()
check("限流 → 冷却 30 分钟", 1700 < span <= 1800, round(span))
check("缓存未写入", read_cache() is None)
app.skillsmp_fetch_all = real_fetch_all
app.skillsmp_fetch_page = probe_ok

print("\n=== K. 探针成功但中途被限流 → stars 中止后 recent 直接跳过 ===")
reset()
seq = []
krows = [{"name": "k%d" % i, "stars": 10 - (i % 5),
          "route": {"ownerSlug": "o%d" % i, "repoSlug": "r",
                    "sourceSkillPath": "SKILL.md", "routeSlug": "rs"}} for i in range(50)]
def batch_seq(sort, pages, guard_state=None):
    seq.append(sort)
    # 第一次（stars）返回失败并把 guard 置为 abort，模拟「连续 2 页限流」
    if guard_state is not None:
        guard_state["abort"] = True
    return list(krows), {"ok": 0, "fail": pages, "throttled": pages, "aborted": True}
app.skillsmp_fetch_all = batch_seq
cache, note = app.refresh_skills_market(force=True)
check("只调用了 stars 一个批次", seq == ["stars"], seq)
check("note 提示不完整", "不完整" in (note or ""), note)
check("缓存未写入", read_cache() is None)
app.skillsmp_fetch_all = real_fetch_all

print("\n=== L. 探针成功 + 批量全成功 → 统计口径正确（ok 含探针那一页）===")
reset()
seen_stats = {}
def batch_ok(sort, pages, guard_state=None):
    return [], {"ok": pages, "fail": 0, "throttled": 0, "aborted": False}
app.skillsmp_fetch_all = batch_ok
app.skillsmp_fetch_page = probe_ok
# 用真实的 build_skills_catalog_ex 走一遍统计逻辑（raw 为空 → 返回 [], stats）
_, stats = app.build_skills_catalog_ex()
seen_stats.update(stats)
check("total_pages = 1(探针) + 4 + 20 = 25", stats["total_pages"] == 25, stats)
check("ok = 25", stats["ok"] == 25, stats)
check("fail = 0", stats["fail"] == 0, stats)
check("aborted = False", stats["aborted"] is False, stats)
app.skillsmp_fetch_all = real_fetch_all

# 收尾：还原
reset(remove_cache=True)
if os.path.exists(BACKUP):
    shutil.move(BACKUP, CACHE)
if os.path.exists(STATE):
    os.remove(STATE)

print("\n" + ("全部通过 ✅" if not FAILED else "失败项: %s ❌" % FAILED))
sys.exit(1 if FAILED else 0)
