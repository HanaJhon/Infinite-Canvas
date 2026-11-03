// 自查：扩展的服务地址自动识别逻辑（extension/background.js）。
// 运行：node tools/check_extension_discover.js   （需要本机 3000 上真的跑着无限画布）
// 只做最小验证：能探到在跑的服务、探不到死端口、空配置能自愈、手动地址不被覆盖。
const fs = require('fs');
const path = require('path');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'extension', 'background.js'), 'utf8');

function makeHarness(initial, opts) {
  const options = opts || {};
  const store = Object.assign({}, initial || {});
  const created = [];
  const chrome = {
    storage: {
      local: {
        get: async (defaults) => {
          const out = Object.assign({}, defaults);
          for (const key of Object.keys(defaults || {})) {
            if (key in store) out[key] = store[key];
          }
          return out;
        },
        set: async (patch) => { Object.assign(store, patch); },
        remove: async (keys) => {
          for (const key of [].concat(keys)) delete store[key];
        },
      },
    },
    runtime: {
      onInstalled: { addListener() {} },
      onMessage: { addListener() {} },
      onStartup: { addListener() {} },
      getManifest: () => ({ version: '1.0.7' }),
      getURL: (p) => `chrome-extension://fake/${p}`,
    },
    contextMenus: { onClicked: { addListener() {} }, removeAll: (cb) => cb && cb(), create() {} },
    windows: {
      getLastFocused: async () => options.lastFocused || ({ left: 0, top: 0, width: 1280, height: 800 }),
      create: async (spec) => {
        if (options.windowsCreateThrows) throw new Error('window blocked');
        created.push(spec);
        return { id: 1 };
      },
    },
    tabs: {
      query: async () => [],
      create: async (spec) => { created.push(Object.assign({ viaTab: true }, spec)); return { id: 2 }; },
    },
    scripting: { executeScript: async () => [] },
  };
  const factory = new Function(
    'chrome', 'fetch', 'AbortController', 'setTimeout', 'clearTimeout', 'console',
    `${SRC}\n;return { probeBase, discoverBase, onDetected, me, getConfig, openCaptureWindow, HANDLERS };`,
  );
  const api = factory(chrome, fetch, AbortController, setTimeout, clearTimeout, { log() {}, error() {} });
  // background.js 顶层会 fire-and-forget 一次 discoverBase()，等它跑完再断言，免得互相干扰
  return api.discoverBase().catch(() => null).then(() => ({ api, store, created }));
}

(async () => {
  const live = 'http://127.0.0.1:3000';
  const dead = 'http://127.0.0.1:4999';
  const dead2 = 'http://127.0.0.1:4998';
  const fails = [];
  const check = (name, cond) => { if (!cond) fails.push(name); };

  // 1) 在跑的服务能探到，死端口探不到
  const a = await makeHarness({ baseUrl: dead });
  check('probe_live', await a.api.probeBase(live) === true);
  check('probe_dead', await a.api.probeBase(dead) === false);
  check('probe_garbage', await a.api.probeBase('not-a-url') === false);

  // 2) 存着死地址 → 自动落回在跑的那台（顶层 discover 已经跑过一次，这里重置）
  a.store.baseUrl = dead;
  a.store.baseUrlSource = 'auto';
  const found = await a.api.discoverBase();
  check('discover_changed', found.changed === true);
  check('discover_base', found.baseUrl === live);
  check('discover_persisted', a.store.baseUrl === live && a.store.baseUrlSource === 'auto');

  // 3) 存着活地址 → 不再改动
  const b = await makeHarness({ baseUrl: live, baseUrlSource: 'auto' });
  const kept = await b.api.discoverBase();
  check('discover_stable', kept.changed === false && kept.baseUrl === live);

  // 4) 画布页报上来的地址能被采纳；手动设过就不覆盖；探不通的忽略
  const c = await makeHarness();
  c.store.baseUrl = dead;
  c.store.baseUrlSource = 'auto';
  const det = await c.api.onDetected(live);
  check('detected_adopted', det.detected === true && c.store.baseUrl === live);
  const d = await makeHarness();
  d.store.baseUrl = dead;
  d.store.baseUrlSource = 'manual';
  const det2 = await d.api.onDetected(live);
  check('detected_manual_kept', det2.ignored === true && d.store.baseUrl === dead);
  const e = await makeHarness();
  e.store.baseUrl = live;
  e.store.baseUrlSource = 'auto';
  const det3 = await e.api.onDetected(dead2);
  check('detected_unreachable_ignored', det3.ignored === true && e.store.baseUrl === live);

  // 5) me()：连不上时先自愈地址，能连上就报未登录而不是「连不上」
  const f = await makeHarness();
  f.store.baseUrl = dead;
  f.store.baseUrlSource = 'auto';
  f.store.token = 'stale-token';
  const meRes = await f.api.me();
  check('me_selfheals', meRes.user === null && /登录|连不上/.test(String(meRes.error || '')) && f.store.baseUrl === live);

  // 6) 采集窗口：拖图那条路走的是 ic.openCapture，窗口被拒时退化成标签页，不能静默失败
  const g = await makeHarness();
  const opened = await g.api.HANDLERS['ic.openCapture']({ src: 'https://x.test/a.png' });
  check('capture_window', opened.opened === 'window');
  check('capture_src', g.created.length === 1
    && String(g.created[0].url).includes('capture.html?src=https%3A%2F%2Fx.test%2Fa.png')
    && g.created[0].type === 'popup'
    && typeof g.created[0].left === 'number');
  const h = await makeHarness({}, { windowsCreateThrows: true });
  const fallback = await h.api.HANDLERS['ic.openCapture']({ src: 'https://x.test/b.png' });
  check('capture_fallback_tab', fallback.opened === 'tab' && h.created.length === 1 && h.created[0].viaTab === true);
  // 副屏（负坐标）时不传 left/top，别把弹窗放到屏幕外
  const i = await makeHarness({}, { lastFocused: { left: -1920, top: -200, width: 1280, height: 800 } });
  await i.api.HANDLERS['ic.openCapture']({ src: 'https://x.test/c.png' });
  check('capture_offscreen_guard', i.created.length === 1 && i.created[0].left === undefined && i.created[0].top === undefined);

  if (fails.length) {
    console.log(`CHECK=FAILED ${fails.join(',')}`);
    process.exit(1);
  }
  console.log('CHECK=ALL_OK');
})();
