/* ==================== Skill 市场（共享模块） ====================
   数据源 = GET /api/skills/market（后端从 SkillsMP 抓取），安装 / 卸载由后端落盘到
   data/agent_skills/，安装后会被拼进 Agent 的系统提示词。

   ⚠️ 为什么抽成独立文件：项目里有**两个页面**都需要这个入口 ——
     · static/smart-canvas.html —— 画布页 AI Agent 工具栏（原来只有它有）
     · static/gpt-chat.html     —— GPT 对话页（原来只有「本机工具」，没有市场）
   而它依赖的三样东西（tr / toast / escapeHtml）在两个页面里名字和实现都不一样，
   所以这里全部自带一份最小实现，只在页面恰好提供时才复用（见 T / pageToast）。

   页面接入方式（两步）：
     1) <link rel="stylesheet" href="/static/css/skill-market.css">
        <script src="/static/js/skill-market.js"></script>
     2) 任意按钮加 data-skill-market-open 属性 —— 模块会自己绑定开关。
   浮层 DOM 由本模块创建，页面不需要写任何市场相关的 HTML。 */
(function () {
    'use strict';
    if (window.SkillMarket) return;   // 防重复注入

    // ---------- 页面无关的小工具 ----------

    var ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    function esc(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) { return ESC_MAP[ch]; });
    }

    // i18n：两个页面都会通过 /static/js/i18n.js 加载 i18n-core，暴露 window.StudioI18n。
    // ⚠️ i18n.js 是异步加载的，本脚本执行时 StudioI18n 可能还不存在 → 必须每次现取。
    function T(key) {
        try {
            var i18n = window.StudioI18n;
            if (i18n && typeof i18n.t === 'function') return i18n.t(key);
        } catch (e) { /* 忽略 */ }
        return key;
    }
    // 带 {name} 占位符的文案：项目的 t()/tr() 都**不做插值**，必须自己替换。
    function Tf(key, vars) {
        var text = T(key);
        Object.keys(vars || {}).forEach(function (name) {
            text = text.split('{' + name + '}').join(String(vars[name]));
        });
        return text;
    }

    // toast：优先复用页面自己的实现，没有就自建一个（gpt-chat 页没有全局 toast）。
    var fallbackToastEl = null;
    function pageToast(message) {
        var text = String(message == null ? '' : message);
        for (var i = 0; i < 2; i++) {
            var fn = i === 0 ? window.toast : window.showToast;
            if (typeof fn === 'function') {
                try { fn(text); return; } catch (e) { /* 落到自建 */ }
            }
        }
        if (!fallbackToastEl) {
            fallbackToastEl = document.createElement('div');
            fallbackToastEl.setAttribute('data-skill-market-toast', '');
            fallbackToastEl.style.cssText = 'position:fixed;left:50%;bottom:36px;transform:translateX(-50%);'
                + 'max-width:min(560px,calc(100vw - 48px));padding:9px 16px;border-radius:10px;'
                + 'background:rgba(17,24,39,.94);color:#fff;font-size:12.5px;line-height:1.5;'
                + 'z-index:2147483000;pointer-events:none;opacity:0;transition:opacity .18s ease;';
            document.body.appendChild(fallbackToastEl);
        }
        fallbackToastEl.textContent = text;
        fallbackToastEl.style.opacity = '1';
        clearTimeout(fallbackToastEl._timer);
        fallbackToastEl._timer = setTimeout(function () {
            if (fallbackToastEl) fallbackToastEl.style.opacity = '0';
        }, 2600);
    }

    async function errorMessage(res, fallback) {
        try {
            var data = await res.json();
            var detail = data && (data.detail || data.message || data.error);
            if (detail) return typeof detail === 'string' ? detail : JSON.stringify(detail);
        } catch (e) { /* 忽略 */ }
        return fallback + '（HTTP ' + res.status + '）';
    }

    // ---------- 浮层 DOM ----------

    var overlay = null;
    var nodes = {};

    function buildOverlay() {
        overlay = document.createElement('div');
        overlay.id = 'agentSkillMarket';
        overlay.className = 'agent-skill-market';
        overlay.hidden = true;
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'false');
        overlay.innerHTML =
            '<div class="asm-head">'
            +   '<div class="asm-title"><i data-lucide="store"></i><span data-asm="title"></span></div>'
            +   '<button class="asm-icon-btn" type="button" data-asm="refresh"><i data-lucide="refresh-cw"></i></button>'
            +   '<button class="asm-icon-btn" type="button" data-asm="close"><i data-lucide="x"></i></button>'
            + '</div>'
            + '<div class="asm-toolbar">'
            +   '<label class="asm-search"><i data-lucide="search"></i><input type="search" data-asm="search" autocomplete="off"></label>'
            +   '<select class="asm-select" data-asm="sort">'
            +     '<option value="hot" data-asm-opt="asmSortHot"></option>'
            +     '<option value="stars" data-asm-opt="asmSortStars"></option>'
            +     '<option value="forks" data-asm-opt="asmSortDownloads"></option>'
            +     '<option value="installed" data-asm-opt="asmSortInstalled"></option>'
            +   '</select>'
            + '</div>'
            + '<div class="asm-tabs" data-asm="tabs"></div>'
            + '<div class="asm-meta" data-asm="meta"></div>'
            + '<div class="asm-list" data-asm="list"></div>';
        document.body.appendChild(overlay);
        ['title', 'refresh', 'close', 'search', 'sort', 'tabs', 'meta', 'list'].forEach(function (key) {
            nodes[key] = overlay.querySelector('[data-asm="' + key + '"]');
        });
        nodes.title.textContent = T('smart.asmTitle');
        nodes.refresh.title = T('smart.asmRefresh');
        nodes.close.title = T('common.close');
        nodes.search.placeholder = T('smart.asmSearch');
        nodes.sort.title = T('smart.asmSort');
        overlay.querySelectorAll('[data-asm-opt]').forEach(function (opt) {
            opt.textContent = T('smart.' + opt.dataset.asmOpt);
        });
        nodes.refresh.addEventListener('click', onRefreshClick);
        nodes.close.addEventListener('click', close);
        nodes.search.addEventListener('input', function () {
            state.query = nodes.search.value || '';
            state.limit = RENDER_STEP;
            render();
        });
        nodes.sort.addEventListener('change', function () {
            state.sort = nodes.sort.value || 'hot';
            state.limit = RENDER_STEP;
            render();
        });
    }

    // ---------- 状态 ----------

    var state = {
        skills: [], meta: null, query: '', sort: 'hot', tag: '',
        loading: false, loaded: false, refreshing: false, error: '', limit: 0
    };
    var busy = new Set();
    var RENDER_STEP = 120;   // 一次最多渲染多少张卡片（清单可达上千条，全量塞 DOM 会卡）

    function count(n) {
        var v = Number(n) || 0;
        if (v >= 1000000) return (v / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
        if (v >= 1000) return (v / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
        return String(v);
    }
    function timeText(ts) {
        var n = Number(ts) || 0;
        if (!n) return T('smart.asmNeverRefreshed');
        var d = new Date(n);
        var p = function (x) { return String(x).padStart(2, '0'); };
        return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
            + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
    }
    function skillById(id) { return state.skills.find(function (s) { return s.id === id; }) || null; }
    function tagLabel(tag) {
        var text = T('smart.asmTag.' + tag);
        return text === 'smart.asmTag.' + tag ? tag : text;   // 没有词条时回落到原始标签
    }

    function visible() {
        var q = state.query.trim().toLowerCase();
        var list = state.skills.slice();
        if (state.tag) list = list.filter(function (s) { return (s.tags || []).indexOf(state.tag) >= 0; });
        if (q) {
            list = list.filter(function (s) {
                return [s.title, s.name, s.summary, s.repo, (s.tags || []).join(' ')]
                    .join(' ').toLowerCase().indexOf(q) >= 0;
            });
        }
        // 热度 = star + 收藏 × 2（与后端一致），同分再比 star、再比名称，保证顺序稳定
        var hot = function (a, b) {
            return (b.hotness - a.hotness) || (b.stars - a.stars)
                || String(a.title).localeCompare(String(b.title));
        };
        if (state.sort === 'stars') list.sort(function (a, b) { return (b.stars - a.stars) || hot(a, b); });
        else if (state.sort === 'forks') list.sort(function (a, b) { return (b.forks - a.forks) || hot(a, b); });
        else if (state.sort === 'installed') {
            list.sort(function (a, b) { return (Number(!!b.installed) - Number(!!a.installed)) || hot(a, b); });
        } else list.sort(hot);
        return list;
    }

    function cardHtml(s) {
        var tags = (s.tags || []).map(function (t) {
            return '<span class="asm-tag">' + esc(tagLabel(t)) + '</span>';
        }).join('');
        var isBusy = busy.has(s.id);
        var action = s.installed
            ? '<button class="asm-btn danger" type="button" data-asm-uninstall="' + esc(s.id) + '"'
              + (isBusy ? ' disabled' : '') + '>' + esc(isBusy ? T('smart.asmUninstalling') : T('smart.asmUninstall')) + '</button>'
            : '<button class="asm-btn primary" type="button" data-asm-install="' + esc(s.id) + '"'
              + (isBusy ? ' disabled' : '') + '>' + esc(isBusy ? T('smart.asmInstalling') : T('smart.asmInstall')) + '</button>';
        return '<div class="asm-card' + (s.installed ? ' installed' : '') + '">'
            + '<div class="asm-card-main">'
            +   '<div class="asm-card-head"><span class="asm-card-title">' + esc(s.title) + '</span>'
            +     (s.installed ? '<span class="asm-badge">' + esc(T('smart.asmInstalled')) + '</span>' : '')
            +   '</div>'
            +   '<div class="asm-card-summary">' + esc(s.summary) + '</div>'
            +   '<div class="asm-card-foot">'
            +     '<span class="asm-stat" title="' + esc(T('smart.asmStarsTip')) + '"><i data-lucide="star"></i>' + count(s.stars) + '</span>'
            +     '<span class="asm-stat" title="' + esc(T('smart.asmDownloadsTip')) + '"><i data-lucide="git-fork"></i>' + count(s.forks) + '</span>'
            +     '<span class="asm-repo" title="' + esc(T('smart.asmRepo')) + '">' + esc(s.repo || '') + '</span>'
            +     tags
            +   '</div>'
            + '</div>'
            + '<div class="asm-card-side">' + action + '</div>'
            + '</div>';
    }

    function renderMeta() {
        if (!nodes.meta) return;
        var meta = state.meta || {};
        var installedCount = state.skills.filter(function (s) { return s.installed; }).length;
        var repos = new Set(state.skills.map(function (s) { return s.repo; })).size;
        // 先转义模板，再塞入 <b> —— 顺序不能反，否则占位符会被转义掉
        var html = esc(T('smart.asmMeta'))
            .replace('{total}', '<b>' + state.skills.length + '</b>')
            .replace('{repos}', '<b>' + repos + '</b>')
            .replace('{installed}', '<b>' + installedCount + '</b>');
        html += '<br>' + esc(T('smart.asmSource'));
        html += ' · ' + esc(T('smart.asmUpdated')) + timeText(meta.refreshed_at);
        if (meta.snapshot_at) html += esc(Tf('smart.asmSnapshot', { date: meta.snapshot_at }));
        if (state.refreshing) html += ' <span class="asm-warn">· ' + esc(T('smart.asmRefreshing')) + '</span>';
        else if (meta.stale) html += ' <span class="asm-warn">· ' + esc(T('smart.asmNeedRefresh')) + '</span>';
        if (state.error) html += '<br><span class="asm-warn">' + esc(state.error) + '</span>';
        // 后端拒绝刷新时的说明（限流冷却 / 抓取不完整 / 结果缩水）—— 常驻显示，不随 toast 消失
        else if (meta.refresh_note) html += '<br><span class="asm-warn">' + esc(meta.refresh_note) + '</span>';
        nodes.meta.innerHTML = html;
    }

    function renderTabs() {
        if (!nodes.tabs) return;
        var tags = [];
        state.skills.forEach(function (s) {
            (s.tags || []).forEach(function (t) { if (tags.indexOf(t) < 0) tags.push(t); });
        });
        tags.sort(function (a, b) { return String(a).localeCompare(String(b)); });
        var html = '<button class="asm-tab' + (state.tag ? '' : ' active') + '" type="button" data-asm-tag="">'
            + esc(T('smart.asmAll')) + '</button>';
        html += tags.map(function (t) {
            return '<button class="asm-tab' + (state.tag === t ? ' active' : '') + '" type="button" data-asm-tag="'
                + esc(t) + '">' + esc(tagLabel(t)) + '</button>';
        }).join('');
        nodes.tabs.innerHTML = html;
        nodes.tabs.querySelectorAll('[data-asm-tag]').forEach(function (btn) {
            btn.onclick = function () {
                state.tag = btn.dataset.asmTag || '';
                state.limit = RENDER_STEP;
                render();
            };
        });
    }

    function render() {
        renderMeta();
        renderTabs();
        if (!nodes.list) return;
        if (!state.skills.length) {
            nodes.list.innerHTML = '<div class="asm-empty"><i data-lucide="loader" class="asm-spin"></i><span>'
                + esc(T('smart.asmLoading')) + '</span></div>';
        } else {
            var list = visible();
            if (!list.length) {
                nodes.list.innerHTML = '<div class="asm-empty"><i data-lucide="search-x"></i><span>'
                    + esc(T('smart.asmEmpty')) + '</span></div>';
            } else {
                var shown = list.slice(0, state.limit || RENDER_STEP);
                var html = shown.map(cardHtml).join('');
                if (list.length > shown.length) {
                    html += '<button class="asm-more" type="button" data-asm-more>'
                        + esc(Tf('smart.asmMore', { n: list.length - shown.length })) + '</button>';
                }
                nodes.list.innerHTML = html;
                var more = nodes.list.querySelector('[data-asm-more]');
                if (more) {
                    more.onclick = function () {
                        state.limit = (state.limit || RENDER_STEP) + RENDER_STEP;
                        render();
                    };
                }
            }
        }
        if (window.lucide && typeof window.lucide.createIcons === 'function') window.lucide.createIcons();
        nodes.list.querySelectorAll('[data-asm-install]').forEach(function (btn) {
            btn.onclick = function () { install(btn.dataset.asmInstall); };
        });
        nodes.list.querySelectorAll('[data-asm-uninstall]').forEach(function (btn) {
            btn.onclick = function () { uninstall(btn.dataset.asmUninstall); };
        });
    }

    function applyInstalled(installed) {
        var map = {};
        (installed || []).forEach(function (item) { map[String(item.id)] = item; });
        state.skills.forEach(function (s) {
            var hit = map[s.id];
            s.installed = !!hit;
            s.installed_at = hit ? hit.installed_at : null;
            s.installed_bytes = hit ? hit.bytes : null;
        });
    }

    async function load(refresh) {
        if (state.loading) return;
        state.loading = true;
        state.error = '';
        if (refresh) state.refreshing = true;
        render();
        try {
            var res = await fetch('/api/skills/market' + (refresh ? '?refresh=1' : ''));
            if (!res.ok) throw new Error(await errorMessage(res, T('smart.asmLoadFail')));
            var data = await res.json();
            state.skills = Array.isArray(data.skills) ? data.skills : [];
            state.meta = data;
            state.loaded = true;
            state.limit = RENDER_STEP;
        } catch (e) {
            state.error = T('smart.asmLoadFail') + '：' + String(e && e.message ? e.message : e).slice(0, 200);
        } finally {
            state.loading = false;
            state.refreshing = false;
            render();
        }
    }

    async function install(id) {
        if (!id || busy.has(id)) return;
        busy.add(id);
        render();
        try {
            var res = await fetch('/api/skills/install', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: id })
            });
            if (!res.ok) throw new Error(await errorMessage(res, T('smart.asmInstallFail')));
            var data = await res.json();
            applyInstalled(data.installed || []);
            var skill = skillById(id);
            pageToast(T('smart.asmInstallDone') + ((skill && skill.title) || id));
        } catch (e) {
            pageToast(T('smart.asmInstallFail') + '：' + String(e && e.message ? e.message : e).slice(0, 200));
        } finally {
            busy.delete(id);
            render();
        }
    }

    async function uninstall(id) {
        if (!id || busy.has(id)) return;
        busy.add(id);
        render();
        try {
            var res = await fetch('/api/skills/uninstall', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: id })
            });
            if (!res.ok) throw new Error(await errorMessage(res, T('smart.asmUninstallFail')));
            var data = await res.json();
            applyInstalled(data.installed || []);
            pageToast(T('smart.asmUninstallDone'));
        } catch (e) {
            pageToast(T('smart.asmUninstallFail') + '：' + String(e && e.message ? e.message : e).slice(0, 200));
        } finally {
            busy.delete(id);
            render();
        }
    }

    async function onRefreshClick() {
        var before = (state.meta && state.meta.refreshed_at) || 0;
        await load(true);
        var after = (state.meta && state.meta.refreshed_at) || 0;
        var note = (state.meta && state.meta.refresh_note) || '';
        if (state.error) pageToast(T('smart.asmRefreshFail') + '：' + state.error);
        // ⚠️ 后端可能**拒绝**这次刷新（限流冷却 / 抓取不完整 / 结果缩水）并回一句人话 ——
        // 此时 refreshed_at 不变，绝不能静默，否则用户以为「刷新按钮坏了」。
        else if (note) pageToast(note);
        else if (after && after !== before) pageToast(T('smart.asmRefreshDone'));
    }

    // ---------- 开关 ----------

    var lastTrigger = null;

    // ⚠️ 浮层必须挂在 document.body 下：画布页的 #agentPanel 上有 transform（开合动画），
    // 它会给 position:fixed 当**包含块** —— 浮层会被居中对齐到 382px 宽的面板里并跟着缩放
    // （实测 780px 被压成 728px、中心跑到 x=1212）。gpt-chat 页同理（工具浮层踩过同一个坑）。
    function detach() {
        if (overlay && overlay.parentElement !== document.body) document.body.appendChild(overlay);
    }

    function open(trigger) {
        if (!overlay) buildOverlay();
        lastTrigger = trigger || lastTrigger;
        detach();
        overlay.hidden = false;
        nodes.search.value = state.query;
        nodes.sort.value = state.sort;
        render();
        // ⚠️ 这里曾有一句 `nodes.search.focus()`。**不要加回来**：
        // 文本框一旦获得焦点就必然命中 `:focus-visible`（规范如此，鼠标/程序化聚焦也算），
        // 会在框外 2px 处画一圈近白色描边 → 面板一打开就像「搜索框被选中」，
        // 老板 2026-09-21 反馈的「选中白框」就是它。焦点指示改由
        // .asm-search:focus-within 的边框变色承担（见 skill-market.css）。
        if (!state.loaded) load(false);
        else if (state.meta && state.meta.stale) load(true);
    }

    function close() {
        if (!overlay) return;
        overlay.hidden = true;
        try { if (lastTrigger && lastTrigger.isConnected) lastTrigger.focus(); } catch (e) { /* 忽略 */ }
    }

    function isOpen() { return !!(overlay && !overlay.hidden); }
    function toggle(trigger) { if (isOpen()) close(); else open(trigger); }

    function wireButtons() {
        document.querySelectorAll('[data-skill-market-open]').forEach(function (btn) {
            if (btn.dataset.skillMarketWired) return;
            btn.dataset.skillMarketWired = '1';
            btn.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                toggle(btn);
            });
        });
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && isOpen()) { e.stopPropagation(); close(); }
    }, true);
    document.addEventListener('mousedown', function (e) {
        if (!isOpen()) return;
        if (overlay.contains(e.target)) return;
        if (e.target.closest && e.target.closest('[data-skill-market-open]')) return;
        close();
    });
    // 语言切换后必须重画：标签页 / 统计文案 / 卡片按钮 / 排序项都是 JS 生成的，
    // StudioI18n.apply() 只扫 data-i18n 属性，覆盖不到。
    window.addEventListener('studio-lang-change', function () {
        if (!overlay) return;
        nodes.title.textContent = T('smart.asmTitle');
        nodes.refresh.title = T('smart.asmRefresh');
        nodes.close.title = T('common.close');
        nodes.search.placeholder = T('smart.asmSearch');
        nodes.sort.title = T('smart.asmSort');
        overlay.querySelectorAll('[data-asm-opt]').forEach(function (opt) {
            opt.textContent = T('smart.' + opt.dataset.asmOpt);
        });
        if (state.loaded || isOpen()) render();
    });

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wireButtons);
    else wireButtons();

    window.SkillMarket = {
        open: open,
        close: close,
        toggle: toggle,
        isOpen: isOpen,
        refresh: function () { return load(true); },
        state: state,
        _esc: esc,
        _t: T
    };
})();
