// 设置页：服务地址 + 登录/退出。地址和令牌都存在 chrome.storage.local（baseUrl / token）。
const el = {
  baseUrl: document.getElementById('baseUrl'),
  baseMsg: document.getElementById('baseMsg'),
  autoBtn: document.getElementById('autoBtn'),
  saveBaseBtn: document.getElementById('saveBaseBtn'),
  testBtn: document.getElementById('testBtn'),
  userMsg: document.getElementById('userMsg'),
  loginForm: document.getElementById('loginForm'),
  loginName: document.getElementById('loginName'),
  loginPassword: document.getElementById('loginPassword'),
  loginBtn: document.getElementById('loginBtn'),
  loginMsg: document.getElementById('loginMsg'),
  logoutBtn: document.getElementById('logoutBtn'),
};

async function refreshAuth() {
  let result;
  try {
    result = await IC.send({ type: 'ic.me' });
  } catch (err) {
    el.userMsg.textContent = `读取登录状态失败：${err.message}`;
    el.userMsg.className = 'msg err';
    return;
  }
  if (result.user) {
    el.userMsg.textContent = `当前账号：${result.user.name}（${result.user.role || 'member'}）`;
    el.userMsg.className = 'msg ok';
    el.loginForm.hidden = true;
    el.logoutBtn.hidden = false;
  } else {
    el.userMsg.textContent = result.error ? `未登录：${result.error}` : '未登录';
    el.userMsg.className = 'msg';
    el.loginForm.hidden = false;
    el.logoutBtn.hidden = true;
  }
}

async function loadSettings() {
  const stored = await chrome.storage.local.get({ baseUrl: IC.DEFAULT_BASE, token: '', baseUrlSource: '' });
  el.baseUrl.value = stored.baseUrl || IC.DEFAULT_BASE;
  // 没手动改过地址就自动找一次（用户在浏览器里开着画布时这一下就够了）
  if (stored.baseUrlSource !== 'manual') await autoDetect(true);
  await refreshAuth();
}

// silent=true 时不弹成功提示，只把结果写回输入框
async function autoDetect(silent) {
  IC.showMsg(el.baseMsg, '正在查找无限画布…');
  let result;
  try {
    result = await IC.send({ type: 'ic.discover' });
  } catch (err) {
    IC.showMsg(el.baseMsg, `检测失败：${err.message}`, 'err');
    return false;
  }
  el.baseUrl.value = result.baseUrl || el.baseUrl.value;
  if (result.error) {
    IC.showMsg(el.baseMsg, `${result.error}。请确认无限画布已启动（默认 http://127.0.0.1:3000）`, 'warn');
    return false;
  }
  IC.showMsg(el.baseMsg, silent && !result.changed
    ? `已连接 ${result.baseUrl}`
    : `已自动识别地址：${result.baseUrl}`, 'ok');
  return true;
}

async function saveBaseUrl() {
  const raw = el.baseUrl.value.trim() || IC.DEFAULT_BASE;
  if (!/^https?:\/\/[^\s]+$/i.test(raw)) {
    IC.showMsg(el.baseMsg, '地址要以 http:// 或 https:// 开头', 'err');
    return false;
  }
  const normalized = raw.replace(/\/+$/, '');
  // 手动保存过就记住「别再自动改我的」
  await chrome.storage.local.set({ baseUrl: normalized, baseUrlSource: 'manual' });
  el.baseUrl.value = normalized;
  IC.showMsg(el.baseMsg, '已保存', 'ok');
  return true;
}

el.autoBtn.addEventListener('click', async () => {
  if (await autoDetect(false)) await refreshAuth();
});

el.saveBaseBtn.addEventListener('click', async () => {
  if (await saveBaseUrl()) await refreshAuth();
});

el.testBtn.addEventListener('click', async () => {
  if (!(await saveBaseUrl())) return;
  IC.showMsg(el.baseMsg, '正在连接…');
  try {
    const result = await IC.send({ type: 'ic.me' });
    if (result.user) IC.showMsg(el.baseMsg, `连接正常，已登录 ${result.user.name}`, 'ok');
    else if (result.error && /连不上/.test(result.error)) IC.showMsg(el.baseMsg, result.error, 'err');
    else IC.showMsg(el.baseMsg, '服务可连接，但当前未登录', 'warn');
  } catch (err) {
    IC.showMsg(el.baseMsg, err.message, 'err');
  }
  await refreshAuth();
});

IC.bindLogin({
  nameEl: el.loginName,
  passEl: el.loginPassword,
  btn: el.loginBtn,
  msgEl: el.loginMsg,
  onDone: async () => {
    el.loginPassword.value = '';
    await refreshAuth();
  },
});

el.logoutBtn.addEventListener('click', async () => {
  try {
    await IC.send({ type: 'ic.logout' });
    IC.showMsg(el.loginMsg, '已退出登录', 'ok');
  } catch (err) {
    IC.showMsg(el.loginMsg, `退出失败：${err.message}`, 'err');
  }
  await refreshAuth();
});

loadSettings();
