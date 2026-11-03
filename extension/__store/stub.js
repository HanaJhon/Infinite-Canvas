// 仅供商店截图使用：把 chrome.* 换成假数据，让采集页/设置页在普通网页里也能渲染出成品样子。
(() => {
  const SHOT = window.__SHOT__ || {};
  const abs = (u) => { try { return new URL(u, location.href).href; } catch (_) { return u; } };
  SHOT.seed = (SHOT.seed || []).map(abs);
  try { localStorage.setItem('ic_theme', SHOT.theme || 'dark'); } catch (_) {}

  const LIBS = {
    libraries: [{
      id: 'default',
      name: '默认素材库',
      categories: [{ id: 'c1', name: '参考图' }, { id: 'c2', name: '角色' }, { id: 'c3', name: '场景' }],
    }],
    active_library_id: 'default',
  };
  const replies = {
    'ic.me': () => ({ ok: true, user: { name: SHOT.me || 'Lochou' } }),
    'ic.libraries': () => Object.assign({ ok: true }, LIBS),
    'ic.login': () => ({ ok: true, user: { name: SHOT.me || 'Lochou' } }),
    'ic.collectImages': () => ({ ok: true, urls: (SHOT.seed || []).slice() }),
  };
  const send = (msg, cb) => {
    const fn = replies[msg && msg.type] || (() => ({ ok: true }));
    let payload;
    try { payload = fn(msg); } catch (err) { payload = { ok: false, error: String(err) }; }
    if (cb) setTimeout(() => cb(payload), 8);
    return Promise.resolve(payload);
  };
  window.chrome = {
    runtime: {
      sendMessage: send,
      getURL: (p) => '/' + String(p),
      getManifest: () => ({ version: '1.0.6' }),
      lastError: null,
      onMessage: { addListener() {} },
      onInstalled: { addListener() {} },
    },
    storage: {
      local: {
        get: (k, cb) => { const v = { token: 'demo', userName: 'Lochou', baseUrl: 'http://127.0.0.1:3000' }; if (cb) cb(v); return Promise.resolve(v); },
        set: (v, cb) => { if (cb) cb(); return Promise.resolve(); },
        remove: (k, cb) => { if (cb) cb(); return Promise.resolve(); },
      },
      sync: {
        get: (k, cb) => { if (cb) cb({}); return Promise.resolve({}); },
        set: (v, cb) => { if (cb) cb(); return Promise.resolve(); },
      },
    },
    tabs: {
      query: async (q) => (q && q.active ? [{ id: 1, url: 'https://example.com/gallery', title: '示例图片站' }] : [{ id: 1 }]),
      create: async () => ({ id: 9 }),
    },
    windows: { getLastFocused: async () => ({ left: 0, top: 0, width: 1440, height: 900 }), create: async () => ({ id: 9 }) },
    contextMenus: { create() {}, removeAll(cb) { if (cb) cb(); }, onClicked: { addListener() {} } },
    scripting: { executeScript: async () => [{ result: [] }] },
  };

  // 采集页：走真实的「添加」按钮路径，缩略图才是真渲染
  if (SHOT.seed && SHOT.seed.length) {
    setTimeout(() => {
      const input = document.getElementById('urlInput');
      const btn = document.getElementById('addUrlBtn');
      if (!input || !btn) return;
      SHOT.seed.forEach((url, i) => setTimeout(() => { input.value = url; btn.click(); }, i * 70));
    }, 280);
  }

  // 网页投放区：造一次「拖图进来」，让投放区显示成激活态
  if (SHOT.dropzone) {
    setTimeout(() => {
      try {
        const dt = new DataTransfer();
        dt.setData('text/uri-list', (SHOT.seed && SHOT.seed[0]) || 'http://127.0.0.1:3099/__store/薄荷人像.png');
        document.dispatchEvent(new DragEvent('dragenter', { bubbles: true, dataTransfer: dt }));
      } catch (_) {}
    }, 320);
  }
})();
