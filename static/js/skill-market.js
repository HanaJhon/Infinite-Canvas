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
            + '<div class="asm-cats" data-asm="cats"></div>'
            + '<div class="asm-tabs" data-asm="tabs"></div>'
            + '<div class="asm-meta" data-asm="meta"></div>'
            + '<div class="asm-list" data-asm="list"></div>';
        document.body.appendChild(overlay);
        ['title', 'refresh', 'close', 'search', 'sort', 'cats', 'tabs', 'meta', 'list'].forEach(function (key) {
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
            scheduleRemoteSearch();
            render();
        });
        nodes.sort.addEventListener('change', function () {
            state.sort = nodes.sort.value || 'hot';
            state.limit = RENDER_STEP;
            render();
            resetListScroll();
        });
    }

    // ---------- 状态 ----------

    var state = {
        skills: [], meta: null, query: '', sort: 'hot', tag: '', cat: '',
        // taxonomy = 后端给的「大分类 → 子分类」静态结构（前端不硬编码分类表）
        taxonomy: [],
        loading: false, loaded: false, refreshing: false, error: '', limit: 0,
        // —— 全站搜索（SkillsMP 服务端过滤）——
        // remoteQuery 是 remote 对应的关键词：与当前输入不一致就视为过期，
        // 用户改了字不该再看到旧结果。remoteBusy 只是「正在查」的指示。
        remote: null, remoteQuery: '', remoteBusy: false, remoteNote: '', remoteTimer: 0,
        // —— 中文简介的联网补译（只对离线表里没有的 Skill 触发，见 ensureSummaries）——
        i18nBusy: false, i18nNote: '', i18nAsked: ''
    };
    var busy = new Set();
    var RENDER_STEP = 120;   // 一次最多渲染多少张卡片（清单可达上千条，全量塞 DOM 会卡）
    // 本地清单只有 615 条内置快照，搜不到快照之外的 Skill（如 caveman）→ 输入够长就走
    // 服务端全站搜索。⚠️ 阈值必须与后端 SKILL_MARKET_SEARCH_MIN_CHARS 保持一致。
    var REMOTE_MIN_CHARS = 2;
    var REMOTE_DEBOUNCE_MS = 450;   // 打字防抖：既省请求，也避免撞 SkillsMP 的限流

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
    function catLabel(key) {
        var text = T('smart.asmCat.' + key);
        return text === 'smart.asmCat.' + key ? key : text;
    }

    // 当前列表来源：全站搜索结果 or 本机清单
    function currentSource() { return remoteActive() ? state.remote : state.skills; }

    // 某个大分类下允许出现的子分类（'' = 全部大分类 → 所有子分类，按 taxonomy 顺序）
    function subTagsOf(catKey) {
        var out = [];
        (state.taxonomy || []).forEach(function (item) {
            if (catKey && item.key !== catKey) return;
            (item.tags || []).forEach(function (t) { if (out.indexOf(t) < 0) out.push(t); });
        });
        return out;
    }

    // 子分类 → 大分类 的反查（由 taxonomy 派生，别手写）
    function tagCatOf(tag) {
        var found = '';
        (state.taxonomy || []).forEach(function (item) {
            if (!found && (item.tags || []).indexOf(tag) >= 0) found = item.key;
        });
        return found;
    }

    // 卡片上显示哪些标签：**只显示与该条记录同一个大分类的子分类**。
    // 卡片本来就挂在某个大分类下（或在「全部」里带着自己的 category），把别的
    // 大分类的子分类也贴上来是噪声 —— 实测「视觉」里会冒出「后端服务」这种芯片。
    // 过滤后为空就回落到原标签（宁可多显示，也别让卡片光秃秃）。
    function cardTags(s) {
        var all = s.tags || [];
        var own = s.category || 'other';
        var same = all.filter(function (t) { return (tagCatOf(t) || 'other') === own; });
        return same.length ? same : all;
    }

    // 大分类计数：**按当前列表算**（不是按整份清单），否则全站搜索时计数会对不上
    function categoryCounts() {
        var out = {};
        (currentSource() || []).forEach(function (s) {
            var key = s.category || 'other';
            out[key] = (out[key] || 0) + 1;
        });
        return out;
    }

    // 当前是否在展示「全站搜索结果」（关键词够长 且 有对应该关键词的结果）
    function remoteActive() {
        var q = state.query.trim();
        return q.length >= REMOTE_MIN_CHARS && !!state.remote && state.remoteQuery === q;
    }

    // ---------- 同仓错峰 ----------
    // 🚨 为什么必须有这一步：star / fork / 热度**都是仓库级指标**（同一个仓库下的每条 Skill
    // 数值完全相同），所以按分数排序后，同一仓库的条目必然连成一片。实测 `openclaw/openclaw`
    // 一个仓库就有 11 条、且分数并列全站第一 —— 于是「按热度 / 按 star 数 / 按收藏数」的前
    // **14 条一模一样**，用户切换排序时整个首屏毫无变化，会直接判定「排序坏了」
    //（老板 2026-09-22 原话：「右上角的筛选功能失去了效果」）。
    // 做法：同一仓库**连续出现不超过 2 条**，超了就往后顺延找下一个别家仓库的条目。
    // ⚠️ 只打散「并列块」的展示顺序，主排序不变 —— 分数高的整体仍然靠前；
    //    没触到上限时（绝大多数仓库只有 1~2 条）顺序与严格排序完全一致。
    var REPO_RUN_MAX = 2;
    function spreadByRepo(list) {
        if (!list || list.length < 3) return list;
        var rest = list.slice(), out = [], lastRepo = null, streak = 0;
        while (rest.length) {
            var pick = -1;
            for (var i = 0; i < rest.length; i++) {
                var repo = rest[i].repo || '';
                if (repo !== lastRepo || streak < REPO_RUN_MAX) { pick = i; break; }
            }
            if (pick < 0) pick = 0;                     // 全是同一家 → 只能继续
            var item = rest.splice(pick, 1)[0];
            var own = item.repo || '';
            streak = own === lastRepo ? streak + 1 : 1;
            lastRepo = own;
            out.push(item);
        }
        return out;
    }

    function visible() {
        var q = state.query.trim().toLowerCase();
        var remote = remoteActive();
        var list = (remote ? state.remote : state.skills).slice();
        // 大分类 / 子分类筛选对**本地与全站结果都生效**：后端给每条记录都打了
        // category 与 tags，所以全站结果也能筛（早先「全站搜索时隐藏标签行」的做法已废弃）。
        if (state.cat) {
            list = list.filter(function (s) { return (s.category || 'other') === state.cat; });
        }
        if (state.tag) {
            list = list.filter(function (s) { return (s.tags || []).indexOf(state.tag) >= 0; });
        }
        if (!remote && q) {
            // 全站结果已由服务端过滤，不再套本地子串过滤（那只对内置清单有意义）
            list = list.filter(function (s) {
                return [s.title, s.name, s.summary, s.summary_zh, s.repo, (s.tags || []).join(' ')]
                    .join(' ').toLowerCase().indexOf(q) >= 0;
            });
        }
        // 全站结果由后端按「名字命中 > 说明命中 > 其余」排好序 —— 默认排序下**保持原序**。
        // 这里若照常按热度重排，巨仓会重新霸榜（搜 cave 的前 5 名会变成无关 Skill）。
        if (remote && state.sort === 'hot') return list;
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
        // 排完再错峰，否则同一仓库（分数完全相同）会占满整个首屏，换排序看不出变化
        return spreadByRepo(list);
    }

    // ---------- 全站搜索（输入防抖 → /api/skills/search）----------

    function resetRemote() {
        if (state.remoteTimer) { clearTimeout(state.remoteTimer); state.remoteTimer = 0; }
        state.remote = null;
        state.remoteQuery = '';
        state.remoteBusy = false;
        state.remoteNote = '';
    }

    function scheduleRemoteSearch() {
        if (state.remoteTimer) { clearTimeout(state.remoteTimer); state.remoteTimer = 0; }
        var q = state.query.trim();
        if (q.length < REMOTE_MIN_CHARS) { resetRemote(); render(); return; }
        if (state.remote && state.remoteQuery === q) return;    // 这个词已经有结果了
        state.remoteTimer = setTimeout(function () {
            state.remoteTimer = 0;
            remoteSearch(q);
        }, REMOTE_DEBOUNCE_MS);
    }

    async function remoteSearch(q) {
        if (state.remoteQuery === q && state.remote) return;
        state.remoteBusy = true;
        state.remoteNote = '';
        render();
        try {
            var res = await fetch('/api/skills/search?q=' + encodeURIComponent(q));
            if (!res.ok) throw new Error(await errorMessage(res, T('smart.asmLoadFail')));
            var data = await res.json();
            // 用户已经改了字 → 这份结果过期，直接丢掉（否则会闪回旧结果）
            if (state.query.trim() !== q) return;
            state.remote = Array.isArray(data.skills) ? data.skills : [];
            state.remoteQuery = q;
            state.remoteNote = data.note || '';
            // 全站结果是离线表覆盖不到的主要来源 → 补一次中文简介
            ensureSummaries(state.remote);
        } catch (e) {
            if (state.query.trim() !== q) return;
            state.remote = null;
            state.remoteQuery = '';
            state.remoteNote = T('smart.asmSearchFail');
        } finally {
            if (state.query.trim() === q) state.remoteBusy = false;
            render();
        }
    }

    // ---------- 中文简介的联网补译（只补离线表里没有的）----------
    // 内置 615 条走随包离线表（零配置、断网可用）；**全站搜索搜出来的新 Skill** 离线表里没有，
    // 这里把它们丢给 /api/skills/i18n，后端用老板配置的对话模型翻好并缓存到 data/。
    // 没配对话模型时后端返回 ok=false + note，这里只把 note 显示出来，绝不反复重试。

    async function ensureSummaries(list) {
        var missing = (list || []).filter(function (s) {
            return !String(s.summary_zh || '').trim() && String(s.summary || '').trim();
        });
        if (!missing.length) return;
        var key = missing.map(function (s) { return s.id; }).sort().join(',');
        if (state.i18nAsked === key) return;      // 同一批只问一次，避免失败后反复打后端
        state.i18nAsked = key;
        state.i18nBusy = true;
        state.i18nNote = '';
        render();
        try {
            var res = await fetch('/api/skills/i18n', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    items: missing.slice(0, 48).map(function (s) {
                        return { id: s.id, summary: s.summary };
                    })
                })
            });
            if (!res.ok) throw new Error(await errorMessage(res, T('smart.asmLoadFail')));
            var data = await res.json();
            var map = data.items || {};
            var hit = 0;
            [state.skills, state.remote].forEach(function (arr) {
                (arr || []).forEach(function (s) {
                    if (map[s.id]) { s.summary_zh = map[s.id]; hit++; }
                });
            });
            // 一条都没翻到 → 把后端的原因（通常是「未配置对话模型」）留在 meta 行上
            if (!hit) state.i18nNote = data.note || T('smart.asmTranslateFail');
        } catch (e) {
            state.i18nNote = T('smart.asmTranslateFail');
        } finally {
            state.i18nBusy = false;
            render();
        }
    }

    function cardHtml(s) {
        var tags = cardTags(s).map(function (t) {
            return '<span class="asm-tag">' + esc(tagLabel(t)) + '</span>';
        }).join('');
        // 简介优先显示中文：summary_zh 来自随包离线表或 /api/skills/i18n 的联网补译；
        // 两者都没有时回落英文原文（并把原文挂到 title 上，鼠标悬停仍可看全）
        var zh = String(s.summary_zh || '').trim();
        var en = String(s.summary || '').trim();
        var summaryHtml = '<div class="asm-card-summary' + (zh ? ' is-zh' : '') + '"'
            + (zh && en ? ' title="' + esc(en) + '"' : '') + '>' + esc(zh || en) + '</div>';
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
            +   summaryHtml
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
        // 全站搜索状态：进行中 / 命中数 / 降级原因（限流、断网、关键词太短）
        if (remoteActive()) {
            html += '<br><span class="asm-online">'
                + esc(Tf('smart.asmSearchOnline', { q: state.remoteQuery, n: state.remote.length }))
                + '</span>';
        } else if (state.remoteBusy) {
            html += '<br><span class="asm-online">'
                + esc(Tf('smart.asmSearching', { q: state.query.trim() })) + '</span>';
        }
        if (state.remoteNote) html += '<br><span class="asm-warn">' + esc(state.remoteNote) + '</span>';
        // 中文简介的补译：**只显示「正在翻译」这一个瞬时状态**。
        // 🚨 不要在这里回显 state.i18nNote（「简介翻译失败，暂时显示英文原文」）：
        //    离线表已覆盖 826/827 条，只差一两条没译文也会触发补译；没配对话模型时后端
        //    返回 ok=false，这行黄字就**常驻**挂在面板上，看着像出错了 —— 老板 2026-09-22
        //    反馈的「黄色文字」就是它。绝大多数卡片本来就有中文简介，这行提示纯噪声。
        if (state.i18nBusy) {
            html += '<br><span class="asm-online">' + esc(T('smart.asmTranslateBusy')) + '</span>';
        }
        nodes.meta.innerHTML = html;
    }

    // 第一行：大分类（全部 / 实用 / 设计 / 视觉 / 其他）
    function renderCats() {
        if (!nodes.cats) return;
        var counts = categoryCounts();
        var html = '<button class="asm-cat' + (state.cat ? '' : ' active') + '" type="button" data-asm-cat="">'
            + esc(T('smart.asmAll')) + '</button>';
        html += (state.taxonomy || []).map(function (item) {
            var n = counts[item.key] || 0;
            return '<button class="asm-cat' + (state.cat === item.key ? ' active' : '')
                + (n ? '' : ' is-empty') + '" type="button" data-asm-cat="' + esc(item.key) + '">'
                + esc(catLabel(item.key)) + '<span class="asm-cat-n">' + n + '</span></button>';
        }).join('');
        nodes.cats.innerHTML = html;
        nodes.cats.querySelectorAll('[data-asm-cat]').forEach(function (btn) {
            btn.onclick = function () {
                state.cat = btn.dataset.asmCat || '';
                // ⚠️ 换大分类必须清掉子分类：旧的子分类不属于新大分类，
                // 留着会变成「选了实用 + 设计子分类」这种筛不出东西的组合。
                state.tag = '';
                state.limit = RENDER_STEP;
                render();
                resetListScroll();
            };
        });
    }

    // 第二行：子分类（只显示当前大分类下的，且只在当前列表里真有内容时才显示）
    function renderTabs() {
        if (!nodes.tabs) return;
        var allowed = subTagsOf(state.cat);
        var counts = {};
        (currentSource() || []).forEach(function (s) {
            (s.tags || []).forEach(function (t) {
                if (allowed.indexOf(t) < 0) return;
                counts[t] = (counts[t] || 0) + 1;
            });
        });
        var tags = allowed.filter(function (t) { return counts[t]; });
        if (!tags.length) { nodes.tabs.innerHTML = ''; return; }
        var html = '<button class="asm-tab' + (state.tag ? '' : ' active') + '" type="button" data-asm-tag="">'
            + esc(T('smart.asmAllSub')) + '</button>';
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
                resetListScroll();
            };
        });
    }

    // 换排序 / 换筛选后把列表滚回顶部：否则用户停在第 5 屏时重排，视口还停在中间那段，
    // 看起来「没变化」——内容其实变了，只是没回到顶部。
    function resetListScroll() {
        if (nodes.list) nodes.list.scrollTop = 0;
    }

    function render() {
        renderMeta();
        renderCats();
        renderTabs();
        if (!nodes.list) return;
        if (!state.skills.length) {
            nodes.list.innerHTML = '<div class="asm-empty"><i data-lucide="loader" class="asm-spin"></i><span>'
                + esc(T('smart.asmLoading')) + '</span></div>';
        } else {
            var list = visible();
            if (!list.length) {
                if (state.remoteBusy) {
                    // 本地也没命中、全站结果还没回来 → 明确告诉用户在查全站，别显示「没有匹配」
                    nodes.list.innerHTML = '<div class="asm-empty"><i data-lucide="loader" class="asm-spin"></i><span>'
                        + esc(T('smart.asmSearchingShort')) + '</span></div>';
                } else {
                    nodes.list.innerHTML = '<div class="asm-empty"><i data-lucide="search-x"></i><span>'
                        + esc(T(remoteActive() ? 'smart.asmEmptyOnline' : 'smart.asmEmpty')) + '</span></div>';
                }
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
            // 大分类 → 子分类 的结构由后端下发（前端不硬编码分类表，改规则只改 main.py）
            if (Array.isArray(data.taxonomy) && data.taxonomy.length) state.taxonomy = data.taxonomy;
            state.loaded = true;
            state.limit = RENDER_STEP;
        } catch (e) {
            state.error = T('smart.asmLoadFail') + '：' + String(e && e.message ? e.message : e).slice(0, 200);
        } finally {
            state.loading = false;
            state.refreshing = false;
            render();
        }
        // 清单里若有没中文简介的（联网缓存里新收录的），补一次翻译
        ensureSummaries(state.skills);
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
        // 上次是带着关键词关掉的 → 重开时补一次全站搜索（结果可能已被缓存，几乎瞬时）
        if (state.query.trim().length >= REMOTE_MIN_CHARS && !state.remote) scheduleRemoteSearch();
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
