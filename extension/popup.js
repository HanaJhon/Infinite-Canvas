// 工具栏弹窗：登录状态 + 一键采集当前页图片 + 打开设置。
const el = {
  userLabel: document.getElementById('userLabel'),
  captureBtn: document.getElementById('captureBtn'),
  openCaptureBtn: document.getElementById('openCaptureBtn'),
  openOptionsBtn: document.getElementById('openOptionsBtn'),
  siteToggleWrap: document.getElementById('siteToggleWrap'),
  siteToggle: document.getElementById('siteToggle'),
  msg: document.getElementById('msg'),
};

// 「在本网站禁用拖拽采集」：状态存 chrome.storage.local.disabledHosts（hostname 数组），
// content.js 读到就整页不弹投放区；这里改完顺手给当前标签页发消息，不必刷新页面。
async function setupSiteToggle() {
  let host = '';
  let tabId = 0;
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs && tabs[0];
    tabId = tab && tab.id;
    host = /^https?:/i.test((tab && tab.url) || '') ? new URL(tab.url).hostname : '';
  } catch (_) {}
  if (!host) return;
  el.siteToggleWrap.hidden = false;
  const data = await chrome.storage.local.get('disabledHosts');
  const list = Array.isArray(data.disabledHosts) ? data.disabledHosts : [];
  el.siteToggle.checked = list.includes(host);
  el.siteToggle.addEventListener('change', async () => {
    const next = new Set(list);
    if (el.siteToggle.checked) next.add(host);
    else next.delete(host);
    await chrome.storage.local.set({ disabledHosts: [...next] });
    try {
      await chrome.tabs.sendMessage(tabId, {
        type: 'ic.setSiteDisabled',
        host,
        disabled: el.siteToggle.checked,
      });
    } catch (_) {
      // 扩展刚装/刚重载时页面里还没有 content script，下次刷新自然生效
    }
    IC.showMsg(el.msg, el.siteToggle.checked
      ? `已在本网站禁用拖拽采集（${host}）`
      : `已在本网站恢复拖拽采集（${host}）`, 'ok');
  });
}

// 地址自动识别在后台的 me() 里统一处理（连不上就先找一次），这里只管显示。
async function refreshAuth() {
  try {
    const result = await IC.send({ type: 'ic.me' });
    if (result.user) {
      el.userLabel.textContent = result.user.name;
      IC.showMsg(el.msg, '');
    } else {
      el.userLabel.textContent = '未登录';
      IC.showMsg(el.msg, result.error || '请先在浏览器里登录无限画布（或在设置页登录）', 'warn');
    }
  } catch (err) {
    el.userLabel.textContent = '未连接';
    IC.showMsg(el.msg, err.message, 'err');
  }
}

// 扫描当前标签页的可见图片，暂存后开采集窗口让用户确认。
async function collectFromCurrentTab() {
  el.captureBtn.disabled = true;
  IC.showMsg(el.msg, '正在扫描当前网页…');
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs && tabs[0];
    if (!tab || !tab.id) throw new Error('没有找到当前标签页');
    if (!/^https?:/i.test(tab.url || '')) {
      throw new Error('当前页面不是普通网页（浏览器内部页面无法读取）');
    }
    const result = await IC.send({ type: 'ic.collectImages', tabId: tab.id });
    const urls = result.urls || [];
    if (!urls.length) {
      IC.showMsg(el.msg, '这个网页没找到较大的可见图片，试试右键单张采集', 'warn');
      return;
    }
    await chrome.storage.local.set({ pendingImages: { urls, ts: Date.now() } });
    await IC.send({ type: 'ic.openCapture' });
    window.close();
  } catch (err) {
    IC.showMsg(el.msg, err.message, 'err');
  } finally {
    el.captureBtn.disabled = false;
  }
}

el.captureBtn.addEventListener('click', collectFromCurrentTab);

el.openCaptureBtn.addEventListener('click', async () => {
  try {
    await IC.send({ type: 'ic.openCapture' });
    window.close();
  } catch (err) {
    IC.showMsg(el.msg, err.message, 'err');
  }
});

el.openOptionsBtn.addEventListener('click', () => {
  chrome.runtime.openOptionsPage();
  window.close();
});

refreshAuth();
setupSiteToggle();
