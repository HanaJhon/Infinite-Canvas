#!/usr/bin/env python3
"""重新生成 static/skills-catalog.json（Skill 市场内置快照）。

数据源 = SkillsMP（skillsmp.com）。快照随发布包分发，用户**离线**也能看到完整清单；
联网刷新的结果落在 data/skills_market_cache.json，优先于这份快照。

用法（在项目根目录）：
    ./python/python.exe tools/build_skills_catalog.py              # 全量重建（24 页，约 50~70s）
    ./python/python.exe tools/build_skills_catalog.py --supplement # 只补抓设计/视觉类并并进现有快照
    ./python/python.exe tools/build_skills_catalog.py --no-supplement  # 全量重建但不补抓

⚠️ 一次要抓 24 页（并发 5），实测约 50~70s。抓取全部失败时**保留原快照**并以 1 退出。
⚠️ 全量榜单天然缺电商/设计类 Skill（star 榜与最近更新榜几乎全是开发者工具），
   所以默认会再跑一轮**定向补抓**（见 main.SKILL_CATALOG_SUPPLEMENTS）填「视觉」大分类。
"""
import argparse
import datetime
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
import main as app  # noqa: E402  （main.py 模块级只建 FastAPI app，不起服务，导入约 1s）


def write_catalog(payload):
    out = app.SKILLS_CATALOG_FILE
    # ⚠️ 落盘前按**当前**规则重算一遍标签：快照里的 `tags` 是生成时按当时的规则算好的，
    # 改了分类规则而这里不重算，快照就会残留旧子分类（实测 frontend / media / mobile），
    # 打印出来的分布也就跟着骗人。（前端读的是 market_record() 的现算值，所以只是自洽性问题。）
    for skill in payload.get("skills") or []:
        name, summary = skill.get("name") or "", skill.get("summary") or ""
        if name or summary:
            skill["tags"] = app.skill_tags_cached(name, summary)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    skills = payload["skills"]
    repos = {s["repo"] for s in skills}
    size = os.path.getsize(out)
    print(f"写入 {out}")
    print(f"  {len(skills)} 个 Skill / {len(repos)} 个仓库 / {size / 1024:.1f} KB")

    tags = {}
    for skill in skills:
        for tag in skill["tags"]:
            tags[tag] = tags.get(tag, 0) + 1
    print("  标签分布: " + ", ".join(f"{k}={v}" for k, v in sorted(tags.items(), key=lambda p: -p[1])))
    cats = {}
    for skill in skills:
        key = app.skill_category(skill.get("tags") or [])
        cats[key] = cats.get(key, 0) + 1
    print("  大分类: " + ", ".join(f"{k}={cats.get(k, 0)}" for k in app.SKILL_CATEGORY_KEYS))
    langs = {}
    for skill in skills:
        langs[skill["language"]] = langs.get(skill["language"], 0) + 1
    print("  语言分布: " + ", ".join(f"{k or '?'}={v}" for k, v in sorted(langs.items(), key=lambda p: -p[1])[:8]))
    print("  star 区间: %d ~ %d" % (min(s["stars"] for s in skills), max(s["stars"] for s in skills)))
    return out


def reindex():
    """不联网：把现有快照按当前分类规则重算标签后重写。"""
    payload = app.load_skills_catalog()
    if not payload.get("skills"):
        print("现有快照为空，无可重算。")
        return 1
    write_catalog(payload)
    return 0


def supplement(payload):
    """定向补抓并合并；被限流/全失败时原样返回（不破坏已有快照）。"""
    stats = {}
    t0 = time.time()
    extra = app.build_skills_catalog_supplement(stats=stats)
    print(f"定向补抓: {stats['queries']} 个查询 / 原始 {stats['raw']} 条 / 保留 {stats['kept']} 条 / "
          f"失败 {stats['fail']} 个 / 耗时 {time.time() - t0:.1f}s"
          + ("（被限流）" if stats["throttled"] else ""))
    if not extra:
        return payload, 0
    merged, added = app.supplement_skills_catalog(payload, extra)
    print(f"  并入 {added} 条新 Skill（去重后）")
    return merged, added


def build(supplement_only=False, with_supplement=True):
    t0 = time.time()
    if supplement_only:
        payload = app.load_skills_catalog()
        if not payload.get("skills"):
            print("现有快照为空，无法只补抓；请先跑一次全量构建。")
            return 1
        print(f"读入现有快照: {payload['total']} 条 / snapshot_at={payload.get('snapshot_at')}")
    else:
        skills = app.build_skills_catalog()
        if not skills:
            print("抓取失败：SkillsMP 没有返回任何数据，已保留原快照。")
            return 1
        payload = {
            "schema": 2,
            "source": "skillsmp",
            "source_url": app.SKILLSMP_SITE,
            "snapshot_at": datetime.date.today().isoformat(),
            "star_pages": app.SKILLSMP_STAR_PAGES,
            "recent_pages": app.SKILLSMP_RECENT_PAGES,
            "per_repo_limit": app.SKILL_PER_REPO_LIMIT,
            "total": len(skills),
            "repo_count": len({s["repo"] for s in skills}),
            "skills": skills,
        }

    if with_supplement:
        payload, _added = supplement(payload)

    write_catalog(payload)
    print(f"  耗时 {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="生成 static/skills-catalog.json")
    ap.add_argument("--supplement", action="store_true",
                    help="只做定向补抓并并进现有快照（不重跑全量榜单）")
    ap.add_argument("--reindex", action="store_true",
                    help="不联网：只把现有快照按当前分类规则重算标签后重写")
    ap.add_argument("--no-supplement", action="store_true",
                    help="全量重建但跳过定向补抓")
    args = ap.parse_args()
    if args.reindex:
        raise SystemExit(reindex())
    raise SystemExit(build(supplement_only=args.supplement,
                           with_supplement=not args.no_supplement))
