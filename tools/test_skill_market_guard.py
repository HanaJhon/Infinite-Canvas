# -*- coding: utf-8 -*-
"""验证 Skill 市场刷新的四道防线（不联网，全部打桩）。

跑法：./python/python.exe tools/test_skill_market_guard.py
"""
import os, sys, json, time, shutil, asyncio, urllib.error

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

# ⚠️ 内置快照的条数**不要硬编码**：快照会随「定向补抓」增长（615 → 827），
# 写死数字会让一堆无关用例跟着红。
SNAP_N = len(app.load_skills_catalog().get("skills") or [])

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

print("\n=== A. 缓存被污染（194 条）时应回落到内置快照 %d 条 ===" % SNAP_N)
reset(remove_cache=False)
if not os.path.exists(CACHE):
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"skills": [{"id": "x%d" % i, "stars": 1} for i in range(194)],
                   "refreshed_at": time.time()}, f)
pay = app.skills_market_payload(refresh=False)
check("污染缓存仍在 → 会显示 194 条（说明必须删掉它）", pay["total"] == 194, pay["total"])

os.remove(CACHE)
pay = app.skills_market_payload(refresh=False)
check("删掉污染缓存后 → %d 条内置快照" % SNAP_N, pay["total"] == SNAP_N, pay["total"])
check("source=skillsmp", pay["source"] == "skillsmp")
check("online=False（快照模式）", pay["online"] is False)
check("refresh_note 为空", pay["refresh_note"] == "")

print("\n=== B. 抓取不完整（3/24 页失败 = 12.5%... 用 5/24 触发）→ 拒绝覆盖 ===")
reset()
baseline_before = app.market_baseline_count()
check("基准条数 = %d" % SNAP_N, baseline_before == SNAP_N, baseline_before)
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

print("\n=== E. 结果缩水（300 < %d×0.75）→ 拒绝覆盖 ===" % SNAP_N)
reset()
app.skillsmp_fetch_all = stub_fetch(rows, {"ok": 24, "fail": 0, "throttled": 0})
cache, note = app.refresh_skills_market(force=True)
check("note 提示缩水", "只返回" in (note or ""), note)
check("缓存未写入", read_cache() is None)
app.skillsmp_fetch_all = real_fetch_all

print("\n=== F. 正常成功（%d+ 条）→ 写入缓存 + 清冷却 ===" % SNAP_N)
reset()
big = [{"name": "s%d" % i, "stars": 500 - i, "route": {"ownerSlug": "o%d" % (i // 3),
        "repoSlug": "r", "sourceSkillPath": "SKILL.md", "routeSlug": "rs"}} for i in range(900)]
app.skillsmp_fetch_all = stub_fetch(big, {"ok": 24, "fail": 0, "throttled": 0})
cache, note = app.refresh_skills_market(force=True)
check("成功时 note 为 None", note is None, note)
c = read_cache()
check("缓存已写入", bool(c and c.get("skills")))
check("缓存条数 ≥ %d" % SNAP_N, len(c.get("skills") or []) >= SNAP_N, len(c.get("skills") or []))
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

print("\n=== M. 全站搜索：关键词太短 → 不联网，只给 note ===")
reset()
app._SKILL_MARKET_SEARCH_CACHE.clear()
hits = [0]
def spy_get(url, timeout=None):
    hits[0] += 1
    raise AssertionError("不该联网")
app.skill_http_get = spy_get
pay = app.search_skills_market("z")
check("skills 为空", pay["skills"] == [])
check("online=False", pay["online"] is False)
check("note 说明字符数下限", "2 个字符" in pay["note"], pay["note"])
check("一次请求都没发", hits[0] == 0, hits[0])
pay = app.search_skills_market("")
check("空串同样不联网", hits[0] == 0 and pay["skills"] == [])

print("\n=== N. 全站搜索：正常返回 + 记录形状与市场清单一致 ===")
reset()
app._SKILL_MARKET_SEARCH_CACHE.clear()

def api_row(name, stars, owner, repo, path, desc=""):
    return {"name": name, "stars": stars, "forks": 3, "description": desc,
            "contentLanguage": "en", "updatedAt": 1700000000, "branch": "main",
            "route": {"ownerSlug": owner, "repoSlug": repo,
                      "sourceSkillPath": path, "routeSlug": "rs"}}

SEARCH_ROWS = [
    # star 极高但名字不命中 —— 模拟「巨仓描述里含 caveat 导致全部命中」
    api_row("prediction-market-oracle", 260918, "affaan-m", "ecc", "skills/pm/SKILL.md",
            "forecast with a caveat about noise"),
    api_row("caveman", 106187, "juliusbrussee", "caveman", "skills/caveman/SKILL.md",
            "ultra-compressed communication"),
    api_row("cavecrew", 587, "stevesolun", "ctx", "skills/cavecrew/SKILL.md", "crew of agents"),
    # 同一仓库同名、不同路径 → 必须去重成一条
    api_row("caveman", 106187, "juliusbrussee", "caveman",
            "plugins/caveman/skills/caveman/SKILL.md", "ultra-compressed communication"),
]
def search_ok(url, timeout=None):
    hits[0] += 1
    return json.dumps({"skills": SEARCH_ROWS, "pagination": {}, "filters": {}}).encode("utf-8")
hits[0] = 0
app.skill_http_get = search_ok
pay = app.search_skills_market("cave")
check("online=True", pay["online"] is True)
check("cached=False（首次）", pay["cached"] is False)
check("note 为空", pay["note"] == "")
check("同名同仓库已去重（4 条 → 3 条）", pay["total"] == 3, pay["total"])
names = [s["name"] for s in pay["skills"]]
check("名字命中排在巨仓之前（相关性优先于 star）", names[0] in ("caveman", "cavecrew"), names)
check("star 260918 的无关条目被压到末位", names[-1] == "prediction-market-oracle", names)
first = pay["skills"][0]
for key in ("id", "name", "title", "summary", "tags", "repo", "stars", "forks",
            "hotness", "installed", "raw_url", "source_url", "repo_url"):
    check("记录含字段 " + key, key in first)
check("hotness = stars + forks×2", first["hotness"] == first["stars"] + first["forks"] * 2,
      first["hotness"])
check("未安装 → installed=False", first["installed"] is False)
check("raw_url 已拼好", first["raw_url"].startswith("https://raw.githubusercontent.com/"), first["raw_url"])

print("\n=== O. 全站搜索：结果缓存（5 分钟内不再联网）+ 大小写不敏感 ===")
before = hits[0]
pay2 = app.search_skills_market("cave")
check("第二次 cached=True", pay2["cached"] is True)
check("没有新增请求", hits[0] == before, (before, hits[0]))
check("条数一致", pay2["total"] == pay["total"])
pay3 = app.search_skills_market("CAVE")
check("大小写不敏感，共用缓存", pay3["cached"] is True and hits[0] == before, hits[0])

print("\n=== P. 全站搜索：无结果（服务端真过滤）→ 0 条且无 note ===")
app._SKILL_MARKET_SEARCH_CACHE.clear()
def search_empty(url, timeout=None):
    hits[0] += 1
    return json.dumps({"skills": [], "pagination": {}, "filters": {}}).encode("utf-8")
app.skill_http_get = search_empty
pay = app.search_skills_market("zzzznope")
check("0 条", pay["total"] == 0)
check("online=True（请求成功）", pay["online"] is True)
check("note 为空（不是失败）", pay["note"] == "", pay["note"])

print("\n=== Q. 全站搜索：429 → 写冷却 + 提示；冷却期内不再联网 ===")
reset()
app._SKILL_MARKET_SEARCH_CACHE.clear()
def search_429(url, timeout=None):
    hits[0] += 1
    raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
app.skill_http_get = search_429
pay = app.search_skills_market("caveman")
check("降级为空", pay["skills"] == [] and pay["online"] is False)
check("note 提到限流", "限流" in pay["note"], pay["note"])
st = app.load_skills_market_state()
span = float(st.get("cooldown_until") or 0) - time.time()
check("已写冷却 30 分钟", 1700 < span <= 1800, round(span))
app._SKILL_MARKET_SEARCH_CACHE.clear()
before = hits[0]
pay = app.search_skills_market("kubernetes")
check("冷却期内零请求", hits[0] == before, (before, hits[0]))
check("冷却期 note 说明原因", "冷却" in pay["note"], pay["note"])

print("\n=== R. 全站搜索：网络异常（非 429）→ 提示但不写冷却 ===")
reset()
app._SKILL_MARKET_SEARCH_CACHE.clear()
def search_down(url, timeout=None):
    raise urllib.error.URLError("temporary failure in name resolution")
app.skill_http_get = search_down
pay = app.search_skills_market("caveman")
check("降级为空", pay["skills"] == [])
check("note 提到失败", "失败" in pay["note"], pay["note"])
st = app.load_skills_market_state()
check("未写冷却（非限流）", float(st.get("cooldown_until") or 0) == 0)

print("\n=== S. 全站搜索：超长 query 被截断到上限 ===")
app._SKILL_MARKET_SEARCH_CACHE.clear()
seen_url = [""]
def search_capture(url, timeout=None):
    seen_url[0] = url
    return json.dumps({"skills": [], "pagination": {}, "filters": {}}).encode("utf-8")
app.skill_http_get = search_capture
long_q = "a" * 500
pay = app.search_skills_market(long_q)
check("query 被截断到 %d 字符" % app.SKILL_MARKET_SEARCH_MAX_CHARS,
      len(pay["query"]) == app.SKILL_MARKET_SEARCH_MAX_CHARS, len(pay["query"]))
check("URL 里的 search 也是截断后的长度",
      ("search=" + "a" * app.SKILL_MARKET_SEARCH_MAX_CHARS) in seen_url[0], seen_url[0][:120])

print("\n=== T. 两级分类：标签只来自新分类表（旧 frontend/media/mobile 必须消失） ===")
allowed = set(app.SKILL_TAG_CATEGORY.keys())
check("分类表非空（>= 20 个子分类）", len(allowed) >= 20, len(allowed))
t_web = app.skill_tags("frontend-design", "Design a responsive landing page with CSS and Tailwind")
check("网页设计类命中 web-design", "web-design" in t_web, t_web)
check("不再产出旧标签 frontend", "frontend" not in t_web, t_web)
t_img = app.skill_tags("meme-maker", "Search meme templates and generate images")
check("图像类命中 image-video", "image-video" in t_img, t_img)
check("旧标签 media 已消失", "media" not in t_img, t_img)
check("所有标签都在分类表里", all(t in allowed for t in t_web + t_img), t_web + t_img)

print("\n=== T2. 关键词命中必须是「整词」，不是裸子串（2026-09-22 重写） ===")
# 裸子串判定的实测代价（全部来自真实清单）：api→rapid/apify、test→latest、
# dom→domain/domestic/subdomain、ux→linux/lux、ios→scenarios、qa→qatar。
check("整词：api 不命中 rapid / apify",
      not app.skill_keyword_hit("api", "rapid prototyping with apify"), "")
check("整词：api 命中 api / apis",
      app.skill_keyword_hit("api", "a rest api") and app.skill_keyword_hit("api", "two apis"), "")
check("整词：test 不命中 latest", not app.skill_keyword_hit("test", "the latest release"), "")
check("整词：test 命中 testing / tester",
      app.skill_keyword_hit("test", "testing") and app.skill_keyword_hit("test", "a tester"), "")
check("整词：dom 不命中 domain / domestic / subdomain",
      not app.skill_keyword_hit("dom", "domain domestic subdomain"), "")
check("整词：ux 不命中 linux / lux", not app.skill_keyword_hit("ux", "linux luminance lux"), "")
check("整词：ios 不命中 scenarios", not app.skill_keyword_hit("ios", "two scenarios"), "")
check("整词：qa 不命中 qatar", not app.skill_keyword_hit("qa", "qatar airways"), "")
check("整词：ui 不命中 build / quick / guide",
      not app.skill_keyword_hit("ui", "build a quick guide"), "")
check("前缀词：accessib* 命中 accessibility", app.skill_keyword_hit("accessib*", "improve accessibility"), "")
check("前缀词：compress* 命中 compressed", app.skill_keyword_hit("compress*", "ultra compressed mode"), "")
check("前缀词：deploy* 命中 deployment", app.skill_keyword_hit("deploy*", "the deployment pipeline"), "")
check("前缀词：verif* 命中 verify / verification",
      app.skill_keyword_hit("verif*", "verify this") and app.skill_keyword_hit("verif*", "verification"), "")
check("中文按子串：电商 命中 跨境电商", app.skill_keyword_hit("电商", "跨境电商平台"), "")
check("多词短语容忍连字符：frontend design 命中 frontend-design",
      app.skill_keyword_hit("frontend design", "the frontend-design skill"), "")
check("多词短语容忍空格：frontend design 命中 frontend design",
      app.skill_keyword_hit("frontend design", "a frontend design skill"), "")

print("\n=== T3. 技术栈不当分类 + 裸品牌词必须限定语境（实测错分全修复） ===")
check("纯技术栈不再归 app-page-design",
      app.skill_tags("android-clean-architecture", "Clean Architecture for Android and Kotlin") == [],
      app.skill_tags("android-clean-architecture", "Clean Architecture for Android and Kotlin"))
check("提到 flutter 的 PR 自动化不再归设计",
      app.skill_tags("shepherd-prs", "Automate landing open PRs in the flutter/flutter repository")
      == ["productivity"],
      app.skill_tags("shepherd-prs", "Automate landing open PRs in the flutter/flutter repository"))
check("提到 react/css 的虚拟滚动库不再归设计",
      "web-design" not in app.skill_tags("with-tanstack-virtual", "Preact Table through React compatibility and css"),
      app.skill_tags("with-tanstack-virtual", "Preact Table through React compatibility and css"))
check("Amazon GuardDuty（AWS 云服务）不进跨境电商",
      "cross-border" not in app.skill_tags(
          "detecting-cloud-threats", "Deploy Amazon GuardDuty for AWS S3, EKS and Lambda"),
      app.skill_tags("detecting-cloud-threats", "Deploy Amazon GuardDuty for AWS S3, EKS and Lambda"))
check("Shopify Admin API 工具不进电商页",
      "ecommerce-page" not in app.skill_tags(
          "shopify", "Query Shopify Admin/Storefront GraphQL APIs via curl"),
      app.skill_tags("shopify", "Query Shopify Admin/Storefront GraphQL APIs via curl"))
check("爬虫（Apify）不进电商页",
      "ecommerce-page" not in app.skill_tags(
          "apify", "Scrapes social platforms, business data, and e-commerce via Apify actors"),
      app.skill_tags("apify", "Scrapes social platforms, business data, and e-commerce via Apify actors"))
check("股债商品配置不进电商页",
      "ecommerce-page" not in app.skill_tags(
          "macro-asset-allocation", "生成股票、债券、商品配置策略"),
      app.skill_tags("macro-asset-allocation", "生成股票、债券、商品配置策略"))
check("走私 / 数据跨境合规不进跨境电商",
      "cross-border" not in app.skill_tags(
          "border-crossing", "Cross-border logistics: smuggling, border, customs, concealment"),
      app.skill_tags("border-crossing", "Cross-border logistics: smuggling, border, customs, concealment"))
check("排障工具（提到 Control UI / iOS / Android）不再归设计",
      app.skill_tags("node-connect",
                     "Diagnose OpenClaw Control UI browser and native Android, iOS node failures") == [],
      app.skill_tags("node-connect",
                     "Diagnose OpenClaw Control UI browser and native Android, iOS node failures"))
check("真电商主图仍命中 product-shot",
      "product-shot" in app.skill_tags("ecom-shot", "e-commerce product photography main image"),
      app.skill_tags("ecom-shot", "e-commerce product photography main image"))

print("\n=== U. 大分类判定：按大分类累加子分类权重（+ 软标签不单独决定） ===")
check("UI 设计 → design", app.skill_category(["design", "ui-design"]) == "design")
check("电商详情页 → visual（不能被宽泛的 design 抢走）",
      app.skill_category(["design", "ecommerce-page", "product-shot"]) == "visual")
check("产品主图 → visual", app.skill_category(["image-video", "product-shot"]) == "visual")
check("Token 节省 → utility", app.skill_category(["token-save", "docs"]) == "utility")
check("Agent 优化 → utility", app.skill_category(["agent-optimize"]) == "utility")
check("小程序设计 → design", app.skill_category(["miniprogram-design"]) == "design")
check("无标签 → other", app.skill_category([]) == "other")
check("未知标签 → other", app.skill_category(["nope"]) == "other")
check("单票否决已修：一个 web-design 压不过 test+productivity",
      app.skill_category(["test", "web-design", "productivity"]) == "utility")
check("软标签不单独决定：design+research → utility",
      app.skill_category(["design", "research"]) == "utility")
check("软标签不单独决定：design+docs → utility",
      app.skill_category(["design", "docs"]) == "utility")
check("只有软标签时退回软标签：design → design",
      app.skill_category(["design"]) == "design")
check("只有软标签时退回软标签：image-video → visual",
      app.skill_category(["image-video"]) == "visual")

print("\n=== V. market_record：标签现算（不吃清单里的旧标签）+ category + summary_zh ===")
stale = {"id": "s1", "name": "caveman", "title": "Caveman",
         "summary": "Ultra-compressed communication mode that cuts output tokens",
         "tags": ["frontend", "media"], "stars": 10, "forks": 2, "repo": "a/b"}
rec = app.market_record(stale, {}, {})
check("tags 已按新规则重算", "frontend" not in rec["tags"] and "media" not in rec["tags"], rec["tags"])
check("token-save 命中", "token-save" in rec["tags"], rec["tags"])
check("category=utility", rec["category"] == "utility", rec["category"])
check("summary_zh 默认空串", rec["summary_zh"] == "", repr(rec["summary_zh"]))
rec2 = app.market_record(stale, {}, {"s1": "极致压缩的沟通模式，减少输出 token。"})
check("summary_zh 取自传入译表", rec2["summary_zh"] == "极致压缩的沟通模式，减少输出 token。", rec2["summary_zh"])
check("英文原文仍保留（给 title 悬停用）", rec2["summary"].startswith("Ultra-compressed"), rec2["summary"][:30])

print("\n=== W. 市场载荷带 taxonomy / categories / translated ===")
pay = app.skills_market_payload(refresh=False)
check("taxonomy 有 4 个大分类", len(pay["taxonomy"]) == 4, len(pay["taxonomy"]))
check("大分类顺序 = utility/design/visual/other",
      [x["key"] for x in pay["taxonomy"]] == ["utility", "design", "visual", "other"],
      [x["key"] for x in pay["taxonomy"]])
check("除 other 外每个大分类都有子分类",
      all(len(x["tags"]) > 0 for x in pay["taxonomy"] if x["key"] != "other"))
check("categories 计数之和 = 清单总数",
      sum(x["count"] for x in pay["categories"]) == pay["total"],
      (sum(x["count"] for x in pay["categories"]), pay["total"]))
check("每条记录都有合法 category",
      all(r.get("category") in app.SKILL_CATEGORY_KEYS for r in pay["skills"]))
check("translated 字段存在且 <= total", 0 <= pay["translated"] <= pay["total"], pay["translated"])
meta = app.skill_category_meta([{"category": "utility", "tags": ["token-save", "design"]},
                                {"category": "design", "tags": ["design"]}])
utility = next(x for x in meta if x["key"] == "utility")
design = next(x for x in meta if x["key"] == "design")
check("utility 计数 = 1", utility["count"] == 1, utility["count"])
check("跨分类的 design 标签不计入 utility 的子分类",
      [t["key"] for t in utility["tags"]] == ["token-save"], utility["tags"])
check("design 子分类含 design", [t["key"] for t in design["tags"]] == ["design"], design["tags"])

print("\n=== X. 中文简介：联网缓存覆盖离线表；缺文件不炸 ===")
i18n_cache = app.SKILLS_MARKET_I18N_CACHE
i18n_backup = i18n_cache + ".testbak"
had_cache = os.path.exists(i18n_cache)
if had_cache:
    shutil.move(i18n_cache, i18n_backup)
try:
    app._SKILL_I18N_CACHE["stamps"] = None
    table = app.load_skills_i18n()
    check("没有缓存时也能读（不抛错）", isinstance(table, dict), type(table).__name__)
    with open(i18n_cache, "w", encoding="utf-8") as f:
        json.dump({"schema": 1, "entries": {"s2": "只有缓存有", "dup": "缓存版"}}, f, ensure_ascii=False)
    app._SKILL_I18N_CACHE["stamps"] = None
    table = app.load_skills_i18n()
    check("读到联网缓存", table.get("s2") == "只有缓存有", table.get("s2"))
    with open(i18n_cache, "w", encoding="utf-8") as f:
        f.write("{ 这不是 JSON")
    app._SKILL_I18N_CACHE["stamps"] = None
    table = app.load_skills_i18n()
    check("缓存损坏 → 退化成离线表，不抛错", isinstance(table, dict), type(table).__name__)
finally:
    if os.path.exists(i18n_cache):
        os.remove(i18n_cache)
    if had_cache and os.path.exists(i18n_backup):
        shutil.move(i18n_backup, i18n_cache)
    app._SKILL_I18N_CACHE["stamps"] = None
check("离线表路径在 static/ 下", app.SKILLS_I18N_FILE.endswith(os.path.join("static", "skills-i18n-zh.json")),
      app.SKILLS_I18N_FILE)

print("\n=== Y. 翻译端点：无可用模型 → 降级；回复解析兜住围栏/客套话 ===")
real_providers = app.load_api_providers
try:
    app.load_api_providers = lambda: []
    # ⚠️ translate_skill_summaries 是 async 的（端点里 await 它），测试必须自己跑事件循环
    res = asyncio.run(app.translate_skill_summaries([{"id": "zzz-none", "summary": "Some English text"}]))
    check("ok=False", res["ok"] is False, res.get("ok"))
    check("note 说明未配置模型", "未配置" in res["note"], res["note"])
    check("items 为空", res["items"] == {})
    res2 = asyncio.run(app.translate_skill_summaries([]))
    check("空请求 → ok=True 且零条", res2["ok"] is True and res2["translated"] == 0, res2)
finally:
    app.load_api_providers = real_providers
check("解析 ```json 围栏", app.parse_translation_reply('```json\n{"a":"译文"}\n```') == {"a": "译文"})
check("解析夹带客套话的回复", app.parse_translation_reply('好的：\n{"a":"译文"}\n以上') == {"a": "译文"})
check("非 JSON → 空字典", app.parse_translation_reply("抱歉我无法完成") == {})
check("纯英文回显被丢弃（译文必须含中文）", app.parse_translation_reply('{"a":"hello"}') == {})

print("\n=== Z. pick_translate_provider：跳过 CLI / gemini / 无对话模型 / 无 Key ===")
real_headers = app.api_headers
def make_prov(pid, protocol, models):
    return {"id": pid, "name": pid, "protocol": protocol, "chat_models": models,
            "base_url": "https://example.com/v1", "enabled": True}
try:
    app.api_headers = lambda json_body=True, provider=None, model="": {"Authorization": "Bearer test"}
    app.load_api_providers = lambda: [make_prov("codex-x", "codex", ["m"])]
    check("全 CLI → None", app.pick_translate_provider() is None)
    app.load_api_providers = lambda: [make_prov("g", "gemini", ["m"])]
    check("gemini 协议被跳过（请求体形状不同）", app.pick_translate_provider() is None)
    app.load_api_providers = lambda: [make_prov("n", "openai", [])]
    check("没有对话模型 → None", app.pick_translate_provider() is None)
    app.load_api_providers = lambda: [make_prov("ok-one", "openai", ["m"])]
    check("有模型 + 有头 → 选中它", (app.pick_translate_provider() or {}).get("id") == "ok-one")
    def boom(json_body=True, provider=None, model=""):
        raise app.HTTPException(status_code=400, detail="未配置 Key")
    app.api_headers = boom
    app.load_api_providers = lambda: [make_prov("nokey", "openai", ["m"])]
    check("没配 Key → None", app.pick_translate_provider() is None)
finally:
    app.api_headers = real_headers
    app.load_api_providers = real_providers

print("\n=== AA. 定向补抓：只收设计/视觉、去重、单仓库限量、限流即中止 ===")
def fake_search(rows_by_query):
    """替身：按查询词返回预置行。"""
    def _search(query):
        return list(rows_by_query.get(query, [])), None
    return _search

def throttle_error():
    """⚠️ 必须用 urllib 的 HTTPError —— skill_market_is_throttle() 只认它，
    拿 FastAPI 的 HTTPException 冒充 429 是判不出来的（实测踩过）。"""
    return urllib.error.HTTPError("https://skillsmp.com/api/skills", 429, "Too Many Requests", {}, None)

def smp_row(name, desc, owner="o", repo="r"):
    return {"name": name, "description": desc, "stars": 10, "forks": 0,
            "updatedAt": 1700000000, "contentLanguage": "en",
            "route": {"ownerSlug": owner, "repoSlug": repo,
                      "sourceSkillPath": "skills/%s/SKILL.md" % name, "routeSlug": name}}

check("补充查询词非空且无重复",
      bool(app.SKILL_CATALOG_SUPPLEMENTS)
      and len(set(app.SKILL_CATALOG_SUPPLEMENTS)) == len(app.SKILL_CATALOG_SUPPLEMENTS))
check("keep 集合只含设计/视觉子分类",
      app.SKILL_CATALOG_SUPPLEMENT_KEEP
      == frozenset(t for c, subs in app.SKILL_TAXONOMY if c in ("design", "visual")
                   for t, _ in subs),
      sorted(app.SKILL_CATALOG_SUPPLEMENT_KEEP))

real_search = app.skillsmp_search
try:
    rows = {
        "q1": [smp_row("ecommerce-image-workflow", "Reference-product ecommerce image workflow for generation"),
               smp_row("plain-backend-thing", "Query the Admin GraphQL API for orders", owner="o", repo="r2")],
        "q2": [smp_row("ecommerce-image-workflow", "Reference-product ecommerce image workflow for generation")],
    }
    app.skillsmp_search = fake_search(rows)
    stats = {}
    got = app.build_skills_catalog_supplement(queries=("q1", "q2"), stats=stats)
    names = [g["name"] for g in got]
    check("命中设计/视觉的留下", "ecommerce-image-workflow" in names, names)
    check("后端类被过滤（补抓只填设计/视觉盲区）", "plain-backend-thing" not in names, names)
    check("跨查询按 id 去重", len(got) == 1, names)
    check("stats 计数正确",
          stats["queries"] == 2 and stats["raw"] == 3 and stats["kept"] == 1 and stats["fail"] == 0, stats)

    # 单仓库限量
    many = [smp_row("ec-shot-%d" % i, "ecommerce product image packshot %d" % i, owner="big", repo="repo")
            for i in range(10)]
    app.skillsmp_search = fake_search({"q1": many})
    got2 = app.build_skills_catalog_supplement(queries=("q1",))
    check("单仓库限量 %d 条" % app.SKILL_CATALOG_SUPPLEMENT_PER_REPO,
          len(got2) == app.SKILL_CATALOG_SUPPLEMENT_PER_REPO, len(got2))

    # 限流 → 立刻中止剩余查询
    calls = []
    def counting_search(query):
        calls.append(query)
        return [], throttle_error()
    app.skillsmp_search = counting_search
    stats2 = {}
    got3 = app.build_skills_catalog_supplement(queries=("a", "b", "c", "d"), stats=stats2)
    check("限流时只发了 1 个查询就中止", len(calls) == 1, calls)
    check("限流被标记", stats2["throttled"] is True and stats2["fail"] == 1, stats2)
    check("限流时返回空列表", got3 == [])
finally:
    app.skillsmp_search = real_search

print("\n=== AB. supplement_skills_catalog：并进快照、保原条目、重算统计 ===")
base = {"schema": 2, "skills": [{"id": "a", "name": "a", "stars": 5, "repo": "x/y"}], "total": 1}
extra = [{"id": "b", "name": "b", "stars": 99, "repo": "z/w"},
         {"id": "a", "name": "a-dup", "stars": 1, "repo": "x/y"}]
merged, added = app.supplement_skills_catalog(base, extra)
ids = [s["id"] for s in merged["skills"]]
check("新增 1 条", added == 1, added)
check("已存在的条目保留原样（不被搜索结果覆盖）",
      [s for s in merged["skills"] if s["id"] == "a"][0]["name"] == "a")
check("按 star 降序", ids == ["b", "a"], ids)
check("total / repo_count 重算", merged["total"] == 2 and merged["repo_count"] == 2, merged)
check("原 payload 未被就地改写", base["total"] == 1 and len(base["skills"]) == 1)
empty_merged, zero = app.supplement_skills_catalog(base, [])
check("无补充条目 → 原样返回", zero == 0 and empty_merged is base)

# 收尾：还原
app.skill_http_get = real_get
app._SKILL_MARKET_SEARCH_CACHE.clear()
reset(remove_cache=True)
if os.path.exists(BACKUP):
    shutil.move(BACKUP, CACHE)
if os.path.exists(STATE):
    os.remove(STATE)

print("\n" + ("全部通过 ✅" if not FAILED else "失败项: %s ❌" % FAILED))
sys.exit(1 if FAILED else 0)
