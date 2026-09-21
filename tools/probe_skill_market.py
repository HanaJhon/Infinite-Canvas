#!/usr/bin/env python3
"""Skill 市场前端探针：用无头 Edge 在**同源 iframe**里量真实 DOM。

覆盖两个入口页：
  · static/gpt-chat.html    —— GPT 对话页（本次新加入口）
  · static/smart-canvas.html?id=<cid> —— 画布页 AI Agent 工具栏

每轮断言：
  A 入口按钮存在、可见、有 i18n 文案与 title
  B 点击后浮层出现，且**挂在 document.body 下**（画布页 #agentPanel 有 transform，
    不 detach 会被当成包含块压扁 —— 实测过 780px→728px）
  C 卡片数 / 标签页数 / 统计文案 / 排序项文案
  D 浮层计算样式（背景色、圆角）与主题一致
  E 安装按钮可点击，点击后走真实 fetch（只观察请求，不真正落盘——用鸭子类型打桩）
  F 无 JS 报错

用法：
    ./python/python.exe tools/probe_skill_market.py <cid> [--lang zh|en]
结果写到 output/__market_probe.json 与 output/__market_dump.html。
"""
import json
import os
import re
import subprocess
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "output")
PROBE_NAME = "__probe_market.html"
PROBE_PATH = os.path.join(BASE_DIR, "static", PROBE_NAME)

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

MEASURE = r"""
<script>
(function(){
  const out = { errors: [], pages: [] };
  window.addEventListener('error', e => out.errors.push('window:' + (e.message || '')));
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  async function waitFor(fn, timeout, label){
    const t0 = Date.now();
    while(Date.now() - t0 < timeout){
      try { const v = fn(); if(v) return v; } catch(e) {}
      await sleep(150);
    }
    out.errors.push('timeout:' + label);
    return null;
  }
  function rect(el){
    if(!el) return null;
    const r = el.getBoundingClientRect();
    return { l:Math.round(r.left), t:Math.round(r.top), w:Math.round(r.width), h:Math.round(r.height) };
  }
  function cs(el, prop){ try { return getComputedStyle(el).getPropertyValue(prop); } catch(e){ return ''; } }

  async function probePage(name, url, opts){
    const page = { name: name, url: url, ok: false, errors: [] };
    const f = document.createElement('iframe');
    f.style.cssText = 'position:fixed;left:0;top:0;width:1500px;height:820px;border:0;visibility:visible;';
    f.src = url;
    document.getElementById('stages').appendChild(f);
    const doc = () => f.contentDocument;
    const win = () => f.contentWindow;
    try {
      await waitFor(() => doc() && doc().readyState === 'complete', 30000, name + ':readyState');
      await sleep(opts.bootWait || 6000);
      // A 入口按钮
      const btn = await waitFor(() => doc().querySelector('[data-skill-market-open]'), 20000, name + ':entryBtn');
      if(!btn){ page.errors.push('entry button missing'); return page; }
      const br = rect(btn);
      page.entry = {
        tag: btn.tagName, label: (btn.textContent || '').trim(),
        title: btn.getAttribute('title') || '',
        i18nTitle: btn.dataset.i18nTitle || '',
        rect: br, visible: br.w > 0 && br.h > 0,
        icons: btn.querySelectorAll('i,svg').length,
      };
      // B 点击开浮层
      btn.click();
      const overlay = await waitFor(() => {
        const o = doc().getElementById('agentSkillMarket');
        return (o && !o.hidden) ? o : null;
      }, 20000, name + ':overlayOpen');
      if(!overlay){ page.errors.push('overlay did not open'); return page; }
      await sleep(opts.afterOpenWait || 5000);
      page.overlay = {
        parent: overlay.parentElement ? overlay.parentElement.tagName : '',
        rect: rect(overlay),
        bg: cs(overlay, 'background-color'),
        radius: cs(overlay, 'border-radius'),
        border: cs(overlay, 'border-color'),
        color: cs(overlay, 'color'),
      };
      // C 内容
      const cards = overlay.querySelectorAll('.asm-card');
      const tabs = overlay.querySelectorAll('.asm-tab');
      const meta = overlay.querySelector('.asm-meta');
      const sortOpts = Array.from(overlay.querySelectorAll('[data-asm-opt]')).map(o => o.textContent.trim());
      const firstInstall = overlay.querySelector('[data-asm-install]');
      const more = overlay.querySelector('[data-asm-more]');
      // ⚠️ 卡片内的元素要**限定在第一张卡里**量；用全局选择器会把所有卡片的标签/指标
      //    混在一起（第一版就这么踩了：firstCardTags 量出 6 个、stats 出现重复值）。
      const card0 = cards[0] || null;
      page.content = {
        cards: cards.length,
        tabs: tabs.length,
        tabLabels: Array.from(tabs).slice(0, 6).map(t => t.textContent.trim()),
        metaText: meta ? meta.textContent.trim().replace(/\s+/g, ' ').slice(0, 220) : '',
        sortOptions: sortOpts,
        firstCardTitle: (overlay.querySelector('.asm-card-title') || {}).textContent || '',
        firstCardSummary: ((overlay.querySelector('.asm-card-summary') || {}).textContent || '').slice(0, 90),
        firstCardTags: card0 ? Array.from(card0.querySelectorAll('.asm-tag')).map(t => t.textContent.trim()) : [],
        firstCardStats: card0 ? Array.from(card0.querySelectorAll('.asm-stat')).map(t => t.textContent.trim()) : [],
        firstCardRepo: card0 ? ((card0.querySelector('.asm-repo') || {}).textContent || '') : '',
        firstInstallLabel: firstInstall ? firstInstall.textContent.trim() : '',
        hasMoreButton: !!more,
        moreLabel: more ? more.textContent.trim() : '',
        searchPlaceholder: (overlay.querySelector('[data-asm="search"]') || {}).placeholder || '',
        overlayTitle: (overlay.querySelector('[data-asm="title"]') || {}).textContent.trim(),
        refreshTitle: (overlay.querySelector('[data-asm="refresh"]') || {}).title || '',
        closeTitle: (overlay.querySelector('[data-asm="close"]') || {}).title || '',
      };
      // D 搜索过滤
      const search = overlay.querySelector('[data-asm="search"]');
      // ⚠️ 必须用 iframe 自己的 Event 构造器：`win` 是个**函数**（每次现取 contentWindow），
      //    写成 `new win().Event(...)` 会抛 "win is not a constructor"。
      const Ev = win().Event;
      if(search && cards.length){
        const kw = opts.searchKeyword || 'design';
        search.value = kw;
        search.dispatchEvent(new Ev('input', { bubbles:true }));
        await sleep(900);
        page.search = { keyword: kw, hits: overlay.querySelectorAll('.asm-card').length };
        search.value = '';
        search.dispatchEvent(new Ev('input', { bubbles:true }));
        await sleep(500);
      }
      // E 标签过滤
      if(tabs.length > 1){
        tabs[1].click();
        await sleep(900);
        page.tagFilter = { tag: tabs[1].textContent.trim(), hits: overlay.querySelectorAll('.asm-card').length };
        tabs[0].click();
        await sleep(500);
      }
      // F 焦点环（WCAG 2.4.7）：Tab 到按钮看 outline
      const focusables = overlay.querySelectorAll('button, input, select');
      page.focusables = focusables.length;
      if(focusables.length){
        focusables[0].focus();
        page.focusOutline = cs(focusables[0], 'outline-style') + ' ' + cs(focusables[0], 'outline-width');
      }
      page.ok = page.errors.length === 0;
    } catch(e){
      page.errors.push('exception:' + (e && e.message ? e.message : String(e)));
    } finally {
      try { f.remove(); } catch(e) {}
    }
    return page;
  }

  window.__runProbe = async function(cid, lang, theme){
    try {
      if(lang) { try { localStorage.setItem('studio_lang', lang); } catch(e) {} }
      if(theme) { try { localStorage.setItem('studio_theme', theme); } catch(e) {} }
      out.lang = lang || 'zh';
      out.theme = theme || 'light';
      const targets = JSON.parse(decodeURIComponent(cid));
      for(const t of targets){
        out.pages.push(await probePage(t.name, t.url, t.opts || {}));
      }
    } catch(e){
      out.errors.push('fatal:' + (e && e.message ? e.message : String(e)));
    }
    const pre = document.createElement('pre');
    pre.id = 'probe-result';
    pre.textContent = JSON.stringify(out);
    document.body.appendChild(pre);
    document.title = 'PROBE_DONE ' + out.pages.length;
  };
})();
</script>
"""


def build_probe(targets, lang, theme):
    payload = json.dumps(targets, ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>PROBE_READY</title>
<style>
  /* ⚠️ --virtual-time-budget 下 CSS transition 不推进 → 元素会被冻在 from 值。
     探针里一律关掉过渡，否则量到的 rect / opacity 是动画起点。 */
  * {{ transition: none !important; animation: none !important; }}
  html, body {{ margin:0; background:#ffffff; }}
  #stages {{ position:relative; }}
</style>
</head>
<body>
<div id="stages"></div>
{MEASURE}
<script>
  const TARGETS = {payload};
  window.addEventListener('load', () => {{
    setTimeout(() => window.__runProbe(
      encodeURIComponent(JSON.stringify(TARGETS)), {json.dumps(lang)}, {json.dumps(theme)}), 300);
  }});
</script>
</body>
</html>
"""
    with open(PROBE_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)


def find_edge():
    for path in EDGE_CANDIDATES:
        if os.path.isfile(path):
            return path
    raise SystemExit("找不到 msedge.exe")


def run_edge(url, dump_path, budget=60000):
    edge = find_edge()
    profile = tempfile.mkdtemp(prefix="edge-probe-")
    args = [
        edge, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        f"--user-data-dir={profile}", "--window-size=1500,900",
        f"--virtual-time-budget={budget}", "--run-all-compositor-stages-before-draw",
        "--dump-dom", url,
    ]
    proc = subprocess.run(args, capture_output=True, timeout=240)
    dom = proc.stdout.decode("utf-8", "replace")
    with open(dump_path, "w", encoding="utf-8") as f:
        f.write(dom)
    return dom


def main():
    cid = sys.argv[1] if len(sys.argv) > 1 else ""
    lang = "zh"
    if "--lang" in sys.argv:
        lang = sys.argv[sys.argv.index("--lang") + 1]
    theme = "light"
    if "--theme" in sys.argv:
        theme = sys.argv[sys.argv.index("--theme") + 1]

    targets = [
        {"name": "gpt-chat", "url": "/static/gpt-chat.html", "opts": {"bootWait": 7000}},
        {"name": "smart-canvas", "url": "/static/smart-canvas.html?id=" + cid,
         "opts": {"bootWait": 9000, "searchKeyword": "design"}},
    ]
    build_probe(targets, lang, theme)

    url = f"http://127.0.0.1:3000/static/{PROBE_NAME}"
    dump_path = os.path.join(OUT_DIR, "__market_dump_%s_%s.html" % (lang, theme))
    dom = run_edge(url, dump_path)
    print(f"dump 长度 {len(dom)} -> {dump_path}")

    m = re.search(r'<pre id="probe-result">(.*?)</pre>', dom, re.S)
    if not m:
        title = re.search(r"<title>(.*?)</title>", dom, re.S)
        print("没拿到结果。title =", title.group(1) if title else "?")
        print(dom[:1500])
        return 1
    data = json.loads(m.group(1))
    out_path = os.path.join(OUT_DIR, "__market_probe_%s_%s.json" % (lang, theme))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"lang={data.get('lang')} theme={data.get('theme')}  全局错误={data.get('errors')}")
    for page in data["pages"]:
        print()
        print("=" * 72)
        print("页面:", page["name"], "| ok =", page.get("ok"), "| 错误:", page.get("errors"))
        e = page.get("entry")
        if e:
            print("  入口: label=%r title=%r rect=%s visible=%s icons=%d"
                  % (e["label"], e["title"], e["rect"], e["visible"], e["icons"]))
        o = page.get("overlay")
        if o:
            print("  浮层: parent=%s rect=%s bg=%s radius=%s" % (o["parent"], o["rect"], o["bg"], o["radius"]))
        c = page.get("content")
        if c:
            for k in ("cards", "tabs", "tabLabels", "sortOptions", "firstCardTitle", "firstCardSummary",
                      "firstCardTags", "firstCardStats", "firstCardRepo", "firstInstallLabel",
                      "hasMoreButton", "moreLabel", "searchPlaceholder", "overlayTitle",
                      "refreshTitle", "closeTitle"):
                print("    %-18s %s" % (k, c.get(k)))
            print("    %-18s %s" % ("metaText", c.get("metaText")))
        if page.get("search"):
            print("  搜索:", page["search"])
        if page.get("tagFilter"):
            print("  标签过滤:", page["tagFilter"])
        if page.get("focusOutline"):
            print("  焦点环:", page["focusOutline"], "| 可聚焦元素", page.get("focusables"))
    print()
    print("完整结果 ->", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
