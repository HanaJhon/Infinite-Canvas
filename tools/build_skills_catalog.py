#!/usr/bin/env python3
"""重新生成 static/skills-catalog.json（Skill 市场内置快照）。

数据源 = SkillsMP（skillsmp.com）。快照随发布包分发，用户**离线**也能看到完整清单；
联网刷新的结果落在 data/skills_market_cache.json，优先于这份快照。

用法（在项目根目录）：
    ./python/python.exe tools/build_skills_catalog.py

⚠️ 一次要抓 24 页（并发 5），实测约 50~70s。抓取全部失败时**保留原快照**并以 1 退出。
"""
import datetime
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
import main as app  # noqa: E402  （main.py 模块级只建 FastAPI app，不起服务，导入约 1s）


def build():
    t0 = time.time()
    skills = app.build_skills_catalog()
    if not skills:
        print("抓取失败：SkillsMP 没有返回任何数据，已保留原快照。")
        return 1

    repos = {s["repo"] for s in skills}
    payload = {
        "schema": 2,
        "source": "skillsmp",
        "source_url": app.SKILLSMP_SITE,
        "snapshot_at": datetime.date.today().isoformat(),
        "star_pages": app.SKILLSMP_STAR_PAGES,
        "recent_pages": app.SKILLSMP_RECENT_PAGES,
        "per_repo_limit": app.SKILL_PER_REPO_LIMIT,
        "total": len(skills),
        "repo_count": len(repos),
        "skills": skills,
    }
    out = app.SKILLS_CATALOG_FILE
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(out)
    print(f"写入 {out}")
    print(f"  {len(skills)} 个 Skill / {len(repos)} 个仓库 / {size / 1024:.1f} KB / 耗时 {time.time() - t0:.1f}s")

    tags = {}
    for skill in skills:
        for tag in skill["tags"]:
            tags[tag] = tags.get(tag, 0) + 1
    print("  标签分布: " + ", ".join(f"{k}={v}" for k, v in sorted(tags.items(), key=lambda p: -p[1])))
    langs = {}
    for skill in skills:
        langs[skill["language"]] = langs.get(skill["language"], 0) + 1
    print("  语言分布: " + ", ".join(f"{k or '?'}={v}" for k, v in sorted(langs.items(), key=lambda p: -p[1])[:8]))
    print("  star 区间: %d ~ %d" % (min(s["stars"] for s in skills), max(s["stars"] for s in skills)))
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
