"""画布 Agent 的技能入口（2026-11-13）。

老板反馈「skill 里缺少 ego-browser」：内置 Skill 后端会自动注入系统提示词，
但 `/` 面板只列 `/api/skills/installed`，画布侧也没有任何技能入口。
这里静态盯住两条契约，防止以后又被「Skill 改为随包内置、界面不暴露」的说法删掉。
"""
import io
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = io.open(ROOT / "static/js/smart-canvas.js", encoding="utf-8").read()
HTML = io.open(ROOT / "static/smart-canvas.html", encoding="utf-8").read()


def test_slash_palette_lists_builtin_skills():
    assert "fetch('/api/skills/builtin')" in JS, "/ 面板必须列内置 Skill"
    assert "builtin: true" in JS
    assert "内置 Skill [${name}] 随程序分发" in JS, "内置 Skill 被选中时不能说「已安装」"


def test_toolbar_has_skill_button_wired_to_market():
    assert 'id="agentSkillBtn"' in HTML
    assert "data-skill-market-open" in HTML, "市场浮层靠这个属性自动绑定"
    assert "/static/js/skill-market.js" in HTML
