// 无限画布素材采集扩展 —— 后台 service worker。
// 所有网络请求都在这里做：扩展跨站请求带不上 SameSite=Lax 的 cookie，统一用 X-IC-Session 头。
// 页面端（capture / options / popup）只发消息拿结果，不直接 fetch。

const DEFAULT_BASE = 'http://127.0.0.1:3000';
const MIME_EXT = {
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'image/webp': '.webp',
  'image/gif': '.gif',
  'image/svg+xml': '.svg',
  'image/avif': '.avif',
  'image/bmp': '.bmp',
};

// ---------------------------------------------------------------- 基础请求

async function getConfig() {
  const stored = await chrome.storage.local.get({ baseUrl: DEFAULT_BASE, token: '' });
  const baseUrl = String(stored.baseUrl || DEFAULT_BASE).trim().replace(/\/+$/, '') || DEFAULT_BASE;
  return { baseUrl, token: String(stored.token || '') };
}

function fail(message, status) {
  const err = new Error(message);
  err.status = status || 0;
  return err;
}

async function readJson(res) {
  try {
    return await res.json();
  } catch (_) {
    return null;
  }
}

function detailOf(data, status) {
  const detail = data && data.detail;
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (Array.isArray(detail) && detail.length) return '请求参数不正确';
  return `请求失败（HTTP ${status}）`;
}

async function api(path, { method = 'GET', body, auth = true } = {}) {
  const { baseUrl, token } = await getConfig();
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (auth && token) headers['X-IC-Session'] = token;
  let res;
  try {
    res = await fetch(baseUrl + path, {
      method,
      headers,
      credentials: 'include',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (_) {
    throw fail(`连不上服务 ${baseUrl}（确认「无限画布」已启动，或到设置里改服务地址）`, 0);
  }
  const data = await readJson(res);
  if (!res.ok) {
    if (res.status === 401 && auth) await chrome.storage.local.remove('token');
    throw fail(detailOf(data, res.status), res.status);
  }
  return data || {};
}

// ---------------------------------------------------------------- 地址自动识别
// 用户装完扩展最常卡在「服务地址填什么」。这里三条路自动解决：
// ① 画布页里跑的 content.js 把自身 origin 报上来（最准）；② 没有就试本机 3000 端口；
// ③ 探测走公开的 /api/auth/status（/api/app-info 之类都要登录，探不了）。
const PROBE_TIMEOUT = 2500;
const PROBE_PATHS = ['/api/auth/status'];

async function probeBase(origin) {
  const base = String(origin || '').trim().replace(/\/+$/, '');
  if (!/^https?:\/\/[^\s]+$/i.test(base)) return false;
  for (const path of PROBE_PATHS) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), PROBE_TIMEOUT);
    try {
      const res = await fetch(base + path, { signal: ctrl.signal, credentials: 'include' });
      if (!res.ok) continue;
      const data = await readJson(res);
      if (data && typeof data.has_users !== 'undefined') return true;
    } catch (_) {
      // 端口没开/不是无限画布，换下一个候选
    } finally {
      clearTimeout(timer);
    }
  }
  return false;
}

async function rememberBase(origin) {
  const base = String(origin || '').trim().replace(/\/+$/, '');
  await chrome.storage.local.set({ baseUrl: base, baseUrlSource: 'auto' });
  return base;
}

// 依次试：当前存的 → 页面报上来的 → 127.0.0.1:3000 → localhost:3000
async function discoverBase() {
  const stored = await chrome.storage.local.get({ baseUrl: '', baseUrlSource: '', detectedBase: '' });
  const current = String(stored.baseUrl || '').trim();
  if (current && await probeBase(current)) return { baseUrl: current, changed: false };
  const candidates = [stored.detectedBase, DEFAULT_BASE, 'http://localhost:3000'];
  for (const candidate of candidates) {
    if (!candidate) continue;
    if (await probeBase(candidate)) {
      return { baseUrl: await rememberBase(candidate), changed: true };
    }
  }
  return { baseUrl: current || DEFAULT_BASE, changed: false, error: '没有找到在跑的无限画布' };
}

// content.js 在画布页里报上来的地址。用户手动改过就不覆盖。
async function onDetected(origin) {
  const base = String(origin || '').trim().replace(/\/+$/, '');
  if (!/^https?:\/\/[^\s]+$/i.test(base)) return { ignored: true };
  await chrome.storage.local.set({ detectedBase: base });
  const stored = await chrome.storage.local.get({ baseUrl: DEFAULT_BASE, baseUrlSource: '' });
  if (stored.baseUrlSource === 'manual') return { ignored: true };
  if (String(stored.baseUrl || '') === base) return { same: true };
  if (!(await probeBase(base))) return { ignored: true };
  return { baseUrl: await rememberBase(base), detected: true };
}

// ---------------------------------------------------------------- 账号

async function me() {
  // 不再「没令牌就直接说未登录」：浏览器里已经登录过无限画布的话，api() 带上的
  // ic_session cookie 就够用（credentials: 'include'），用户根本不用在扩展里再登一次。
  try {
    const data = await api('/api/auth/me');
    return { user: data.user || null };
  } catch (err) {
    // 连不上服务也要能显示原因；401 时 api() 已经清掉令牌。
    if (err.status === 401) return { user: null, error: '登录已失效，请重新登录' };
  }
  // 连不上：多半是地址没填或换了端口。自动找一次再试，三个页面（弹窗/采集/设置）都受用。
  const found = await discoverBase().catch(() => null);
  if (found && found.changed) {
    try {
      const data = await api('/api/auth/me');
      return { user: data.user || null };
    } catch (err2) {
      return { user: null, error: err2.message };
    }
  }
  return { user: null, error: '连不上服务，请确认无限画布已启动' };
}

async function login(name, password) {
  const userName = String(name || '').trim();
  if (!userName || !password) throw fail('请填写用户名和密码', 0);
  const data = await api('/api/auth/login', {
    method: 'POST',
    body: { name: userName, password: String(password) },
    auth: false,
  });
  if (!data.token) throw fail('登录响应里没有令牌，服务版本可能较旧', 0);
  await chrome.storage.local.set({ token: String(data.token), userName });
  return { user: data.user || null };
}

async function logout() {
  const { token } = await getConfig();
  if (token) {
    try {
      await api('/api/auth/logout', { method: 'POST' });
    } catch (_) {
      // 服务没开/令牌已失效也无所谓，本地清掉就行
    }
  }
  await chrome.storage.local.remove(['token', 'userName']);
  return {};
}

// ---------------------------------------------------------------- 素材库

// 素材库列表：过滤掉 type === "style"（风格库），分类只保留能收图片的 type === "image"。
async function libraries() {
  const data = await api('/api/asset-library');
  const lib = data.library || {};
  const list = (lib.libraries || [])
    .filter((item) => item && item.type !== 'style')
    .map((item) => ({
      id: String(item.id || ''),
      name: String(item.name || '素材库'),
      categories: (item.categories || [])
        .filter((cat) => cat && cat.type === 'image')
        .map((cat) => ({ id: String(cat.id || ''), name: String(cat.name || '分类') })),
    }))
    .filter((item) => item.id);
  const active = String(lib.active_library_id || '');
  const activeId = list.some((item) => item.id === active) ? active : (list[0] && list[0].id) || '';
  return { libraries: list, active_library_id: activeId };
}

async function createCategory(name, libraryId) {
  const catName = String(name || '').trim();
  if (!catName) throw fail('请输入分类名称', 0);
  if (!libraryId) throw fail('请先选择素材库', 0);
  const data = await api('/api/asset-library/categories', {
    method: 'POST',
    body: { name: catName, type: 'image', library_id: String(libraryId) },
  });
  const fresh = await libraries();
  const newId = String((data.category && data.category.id) || '');
  return { libraries: fresh.libraries, active_library_id: fresh.active_library_id, category_id: newId };
}

// ---------------------------------------------------------------- 采集

function fileNameFor(name, url, mime, index) {
  // 采集界面里用户改过名字就用它；没写后缀的按 mime 补一个
  const typed = String(name || '').trim().replace(/[\\/:*?"<>|#%]+/g, '_').slice(0, 60);
  if (typed) {
    return /\.[a-z0-9]{2,5}$/i.test(typed) ? typed : typed + (MIME_EXT[mime] || '.png');
  }
  let base = '';
  try {
    base = decodeURIComponent(new URL(url).pathname.split('/').pop() || '');
  } catch (_) {
    base = '';
  }
  base = base.replace(/[\\/:*?"<>|#%]+/g, '_').slice(0, 60);
  if (!/\.[a-z0-9]{2,5}$/i.test(base)) {
    base = (base || `采集图_${Number(index || 0) + 1}`) + (MIME_EXT[mime] || '.png');
  }
  return base;
}

// 取图字节 → POST /api/ai/upload（multipart，字段名必须是 files，不要手写 Content-Type）。
async function uploadImage(url, name, index) {
  const target = String(url || '').trim();
  if (!/^https?:\/\//i.test(target)) throw fail('只支持 http/https 图片地址', 0);

  let res;
  try {
    res = await fetch(target, { credentials: 'include' });
  } catch (_) {
    throw fail('取图失败：无法访问该图片（可能需要登录或开了防盗链）', 0);
  }
  if (!res.ok) throw fail(`取图失败（HTTP ${res.status}）`, 0);
  const blob = await res.blob();
  if (!blob.size) throw fail('取图失败：图片内容为空', 0);
  const mime = String(blob.type || '').split(';')[0].trim() || 'image/png';
  if (!mime.startsWith('image/')) throw fail(`不是图片（${mime}）`, 0);

  const { baseUrl, token } = await getConfig();
  const form = new FormData();
  form.append('files', new File([blob], fileNameFor(name, target, mime, index), { type: mime }));

  let up;
  try {
    up = await fetch(baseUrl + '/api/ai/upload', {
      method: 'POST',
      headers: token ? { 'X-IC-Session': token } : {},
      body: form,
    });
  } catch (_) {
    throw fail('上传失败：连不上服务', 0);
  }
  const data = await readJson(up);
  if (!up.ok) {
    if (up.status === 401) await chrome.storage.local.remove('token');
    throw fail(detailOf(data, up.status), up.status);
  }
  const file = (data && Array.isArray(data.files) && data.files[0]) || null;
  if (!file || !file.url) throw fail('上传失败：服务没有返回文件地址', 0);
  return { file: { url: String(file.url), name: String(name || file.name || '') } };
}

async function addItems(libraryId, categoryId, items) {
  if (!libraryId || !categoryId) throw fail('请选择素材库和分类', 0);
  const payload = (items || [])
    .filter((item) => item && item.url)
    .map((item) => ({ url: String(item.url), name: String(item.name || '采集图片') }));
  if (!payload.length) throw fail('没有可入库的图片', 0);
  const data = await api('/api/asset-library/items/batch', {
    method: 'POST',
    body: { library_id: String(libraryId), category_id: String(categoryId), items: payload },
  });
  return { count: Array.isArray(data.items) ? data.items.length : payload.length };
}

// ---------------------------------------------------------------- 页面图片扫描

// 注入到网页执行（会被序列化成源码，不能引用外部变量）：取可见的 http(s) 图片地址。
function collectImagesInPage() {
  const urls = [];
  const seen = new Set();
  const imgs = document.querySelectorAll('img');
  for (const img of imgs) {
    const src = img.currentSrc || img.src;
    if (!src || !/^https?:\/\//i.test(src) || seen.has(src)) continue;
    const rect = img.getBoundingClientRect();
    if (rect.width < 80 || rect.height < 80) continue;
    seen.add(src);
    urls.push(src);
    if (urls.length >= 60) break;
  }
  return urls;
}

async function pickSourceTab(tabId) {
  if (tabId) return tabId;
  const tabs = await chrome.tabs.query({});
  const pages = tabs
    .filter((tab) => tab.id && /^https?:/i.test(tab.url || ''))
    .sort((a, b) => (b.lastAccessed || 0) - (a.lastAccessed || 0));
  return pages.length ? pages[0].id : null;
}

async function collectImages(tabId) {
  const id = await pickSourceTab(tabId);
  if (!id) throw fail('没有找到可扫描的网页（当前窗口不是普通网页）', 0);
  let results;
  try {
    results = await chrome.scripting.executeScript({
      target: { tabId: id },
      func: collectImagesInPage,
    });
  } catch (err) {
    throw fail(`无法读取该网页（${(err && err.message) || '权限不足'}）`, 0);
  }
  const urls = (results && results[0] && Array.isArray(results[0].result)) ? results[0].result : [];
  return { urls, tabId: id };
}

// ---------------------------------------------------------------- 窗口

const CAPTURE_WIDTH = 520;
const CAPTURE_HEIGHT = 660;

// 采集窗口开在当前窗口正中（不传 left/top 时由系统决定，会跑到角落去）
async function centeredBounds() {
  try {
    const current = await chrome.windows.getLastFocused();
    if (!current || typeof current.width !== 'number') return {};
    const left = Math.round((current.left || 0) + Math.max(0, (current.width - CAPTURE_WIDTH) / 2));
    const top = Math.round((current.top || 0) + Math.max(0, (current.height - CAPTURE_HEIGHT) / 2));
    // 副屏在主屏左侧/上方时坐标是负数，照搬过去窗口会落在屏幕外（老板实测「弹了但看不见」）。
    // 算不出可靠坐标就干脆不传，交给系统放置。
    if (!Number.isFinite(left) || !Number.isFinite(top) || left < 0 || top < 0) return {};
    return { left, top };
  } catch (_) {
    return {};
  }
}

async function openCaptureWindow(src) {
  const query = src ? `?src=${encodeURIComponent(String(src))}` : '';
  const url = chrome.runtime.getURL(`capture.html${query}`);
  const bounds = await centeredBounds();
  try {
    await chrome.windows.create({ url, type: 'popup', width: CAPTURE_WIDTH, height: CAPTURE_HEIGHT, ...bounds });
    return { opened: 'window' };
  } catch (_) {
    // 少数环境禁弹独立窗口（企业策略/无窗口环境），退化成标签页，至少别让用户点完没反应
    await chrome.tabs.create({ url, active: true });
    return { opened: 'tab' };
  }
}

chrome.contextMenus.onClicked.addListener((info) => {
  if (info.menuItemId !== 'ic-capture-image' || !info.srcUrl) return;
  openCaptureWindow(info.srcUrl);
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create(
      { id: 'ic-capture-image', title: '采集到无限画布素材库', contexts: ['image'] },
      () => void chrome.runtime.lastError,
    );
  });
  // 装完先自己找一次地址，免得用户第一眼就卡在「服务地址」填空
  discoverBase();
});

// ---------------------------------------------------------------- 消息分发

const HANDLERS = {
  'ic.discover': () => discoverBase(),
  'ic.detected': (msg) => onDetected(msg.origin),
  'ic.me': () => me(),
  'ic.login': (msg) => login(msg.name, msg.password),
  'ic.logout': () => logout(),
  'ic.libraries': () => libraries(),
  'ic.createCategory': (msg) => createCategory(msg.name, msg.library_id),
  'ic.uploadImage': (msg) => uploadImage(msg.url, msg.name, msg.index),
  'ic.addItems': (msg) => addItems(msg.library_id, msg.category_id, msg.items),
  'ic.collectImages': (msg) => collectImages(msg.tabId),
  'ic.openCapture': (msg) => openCaptureWindow(msg.src || ''),
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const handler = msg && HANDLERS[msg.type];
  if (!handler) {
    sendResponse({ ok: false, error: `未知的请求类型：${(msg && msg.type) || ''}`, status: 0 });
    return false;
  }
  Promise.resolve()
    .then(() => handler(msg, sender))
    .then((result) => sendResponse(Object.assign({ ok: true }, result || {})))
    .catch((err) => sendResponse({
      ok: false,
      error: (err && err.message) || '操作失败',
      status: (err && err.status) || 0,
    }));
  return true;
});

// service worker 每次唤醒顺手校验一次地址：存的那个不在跑了就重新找（换了端口/换了机器也能自愈）
discoverBase().catch(() => {});
