/* ============================================================
 * 积分徽标（通用版）
 * 把「这次运行大概扣多少积分」显示在 运行 / 生成 / 发送 按钮上。
 *
 * 数据：GET /api/credits/me → public.models（键是「供应商::模型」，也兼容只有模型名的旧数据）
 * 用法：
 *   icCredits.mount(document.getElementById('genBtn'), function(){
 *       return {model: selectedModel, provider: selectedProvider, kind: 'image', count: 1};
 *   });
 * 返回的 update() 可随时手动刷新；按钮重新渲染后重新 mount 即可。
 * ============================================================ */
(function (global) {
  'use strict';
  if (global.icCredits) return;

  var state = { data: null, loading: false, requested: false, listeners: [] };

  function num(v) {
    var n = Number(v || 0);
    return isFinite(n) ? n : 0;
  }
  function fmt(v) {
    var n = num(v);
    if (!n) return '';
    // 小额单价（生图 0.015 / LLM 0.00008）两位小数看不出差别，1 积分以下留 4 位小数
    if (n >= 1) return String(Math.round(n * 100) / 100);
    var fixed = n.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
    return (fixed && fixed !== '0') ? fixed : '<0.0001';
  }

  function load(force) {
    if (state.loading) return state.pending || Promise.resolve(state.data);
    if (state.data && !force) return Promise.resolve(state.data);
    state.loading = true;
    state.requested = true;
    state.pending = fetch('/api/credits/me', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d && d.public) state.data = d.public;
        return state.data;
      })
      .catch(function () { return state.data; })
      .then(function (data) {
        state.loading = false;
        state.pending = null;
        state.listeners.forEach(function (fn) { try { fn(); } catch (e) {} });
        return data;
      });
    return state.pending;
  }

  function models() {
    return (state.data && state.data.models && typeof state.data.models === 'object') ? state.data.models : {};
  }

  // 单价查询：先「供应商::模型」，再裸模型名（仅当该模型没有按供应商单独配过价）
  function entry(model, provider) {
    var map = models();
    var name = String(model || '').trim();
    if (!name) return null;
    var pid = String(provider || '').trim();
    if (pid && map[pid + '::' + name]) return map[pid + '::' + name];
    var scoped = false;
    var suffix = '::' + name;
    for (var k in map) {
      if (Object.prototype.hasOwnProperty.call(map, k) && k !== name && k.slice(-suffix.length) === suffix) { scoped = true; break; }
    }
    if (scoped) return null;
    if (map[name]) return map[name];
    var short = name.split('::').pop();
    if (short && map[short]) return map[short];
    return null;
  }

  function resolveKind(opts, e) {
    var kind = String(opts.kind || (e && e.kind) || 'image').toLowerCase();
    if (kind === 'chat' || kind === 'text') kind = 'llm';
    return kind;
  }

  // 粗略 token 计数：中日韩字符 ≈1 token/字，其余 ≈4 字符/token
  function estimateTokens(text) {
    var s = String(text == null ? '' : text);
    if (!s) return 0;
    var cjk = s.match(/[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]/g);
    var wide = cjk ? cjk.length : 0;
    return Math.round(wide + (s.length - wide) / 4);
  }

  /** 语言模型费用：输入 / 缓存命中 / 输出 三段各自计价（老板 m22656） */
  function llmCost(entry, opts) {
    if (!entry) return null;
    opts = opts || {};
    var fresh = num(opts.input_tokens) || estimateTokens(opts.inputText);
    var cached = num(opts.cache_tokens) || estimateTokens(opts.contextText);
    // 没配缓存单价时，缓存部分按输入价算（多数网关没有独立缓存价）
    var cachePrice = num(entry.cache) || num(entry.input);
    var out = num(opts.output_tokens) || num(opts.max_tokens) || Math.max(1, Math.round(fresh / 2));
    var credits = fresh / 1e6 * num(entry.input) + cached / 1e6 * cachePrice + out / 1e6 * num(entry.output);
    return { credits: credits, tokens: { input: fresh, cache: cached, output: out } };
  }

  /** 单价表只有 480p/720p/1080p，模型的 768p 按 720p、2k/4k 按 1080p 计价 */
  function videoTier(resolution) {
    var raw = String(resolution || '').trim().toLowerCase();
    if (!raw) return '720p';
    if (raw === '768p') return '720p';
    if (raw === '2k' || raw === '4k' || raw === '2160p') return '1080p';
    return raw.replace(/p$/, '') + 'p';
  }

  /** 估算积分：返回 {credits, kind, model} 或 null（未配置单价时返回 null，前端不显示徽标） */
  function cost(opts) {
    opts = opts || {};
    var e = entry(opts.model, opts.provider);
    if (!e) return null;
    var kind = resolveKind(opts, e);
    var credits = 0;
    if (kind === 'image') {
      var count = Math.max(1, num(opts.count || 1));
      credits = num(e.per_image) * count;
    } else if (kind === 'video') {
      var seconds = Math.max(0, num(opts.seconds || 5));
      var table = e.per_second || {};
      var per = num(table[videoTier(opts.resolution)]);
      if (!per) per = num(table['720p']);
      if (!per) {
        var firstKey = Object.keys(table)[0];
        if (firstKey) per = num(table[firstKey]);
      }
      credits = per * seconds;
    } else {
      var llm = llmCost(e, opts);
      credits = llm ? llm.credits : 0;
    }
    if (!credits) return null;
    return { credits: credits, kind: kind, model: String(opts.model || '') };
  }

  /** 文本形式，例如 "12.5 积分"；未配置返回 '' */
  function text(opts) {
    var c = cost(opts);
    if (!c) return '';
    var t = fmt(c.credits);
    return t ? t + ' 积分' : '';
  }

  var STYLE_ID = 'ic-credit-badge-style';
  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var st = document.createElement('style');
    st.id = STYLE_ID;
    st.textContent =
      '.ic-credit-badge{display:inline-flex;align-items:center;margin-left:8px;padding:0 7px;height:19px;' +
      'border-radius:999px;font-size:11px;font-weight:700;line-height:19px;letter-spacing:.02em;' +
      'background:rgba(148,163,184,.22);border:1px solid rgba(148,163,184,.42);color:inherit;' +
      'opacity:.95;white-space:nowrap;vertical-align:middle}' +
      '.ic-credit-badge[hidden]{display:none}';
    (document.head || document.documentElement).appendChild(st);
  }

  /** 把徽标挂到按钮上；getOpts 每次刷新时调用（读当前模型 / 张数等） */
  function mount(btn, getOpts) {
    if (!btn) return function () {};
    ensureStyle();
    var span = btn.querySelector('.ic-credit-badge');
    if (!span) {
      span = document.createElement('span');
      span.className = 'ic-credit-badge';
      span.hidden = true;
      btn.appendChild(span);
    }
    function update() {
      var opts;
      try { opts = (typeof getOpts === 'function' ? getOpts() : getOpts) || {}; } catch (e) { opts = {}; }
      var label = opts.label;
      var t = text(opts);
      span.textContent = label ? (t ? label + ' ' + t : label) : t;
      span.hidden = !span.textContent;
      return t;
    }
    update();
    if (!state.requested) load();
    state.listeners.push(update);
    return update;
  }

  global.icCredits = {
    load: load,
    entry: entry,
    cost: cost,
    text: text,
    format: fmt,
    mount: mount,
    estimateTokens: estimateTokens,
    llmCost: llmCost,
    get data() { return state.data; }
  };
})(window);
