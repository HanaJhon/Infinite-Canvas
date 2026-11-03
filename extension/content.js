// 页面内脚本：拖拽图片时在右下角显示「拖到这里采集」投放区，松手后交给后台开采集窗口。
// 🚨 不要在 dragstart 里就要求拿到图片地址：网页里拖的根本不一定是 <img>（常是外层卡片），
//    而且 Chrome 在 dragstart 阶段经常读不出 dataTransfer 内容。拿不到地址就 return 的话，
//    用户看到的现象是「投放区根本不出现」＝拖图没反应。所以：先无条件显示，松手时再解析。
(() => {
  const ZONE_ID = 'ic-capture-dropzone';
  const IMAGE_URL_RE = /^(https?:|data:image)/i;
  let zone = null;
  let dragUrl = '';
  let hideTimer = 0;

  // 2026-11-03 老板：资产库里要有「安装采集插件」入口 —— 网页没法直接装扩展，
  // 只能引导手动加载。装好之后靠这个标记让画布页知道「已经装过了」（值＝扩展版本号）。
  try {
    const manifest = chrome.runtime.getManifest();
    document.documentElement.dataset.icCaptureExt = String(manifest.version || '1');
  } catch (_) {}

  // 反向：如果当前页就是无限画布自己，把地址报给后台 —— 用户装完扩展不用再手工填服务地址。
  // 判据用画布页特有的安装入口按钮，或页面标题（index / canvas 页标题都带「无限画布」字样）。
  try {
    if (window.top === window) {
      const isCanvasApp = document.getElementById('assetExtInstallBtn')
        || /无限画布|Infinite Canvas/i.test(document.title || '');
      if (isCanvasApp) {
        chrome.runtime.sendMessage({ type: 'ic.detected', origin: location.origin }, () => void chrome.runtime.lastError);
      }
    }
  } catch (_) {}

  function absoluteUrl(value) {
    if (!value) return '';
    try {
      return new URL(String(value), location.href).href;
    } catch (_) {
      return '';
    }
  }

  function imageSrc(el) {
    const raw = el.currentSrc || el.src || el.getAttribute('data-src')
      || el.getAttribute('data-original') || el.getAttribute('data-lazy-src') || '';
    return IMAGE_URL_RE.test(raw) ? absoluteUrl(raw) : '';
  }

  function backgroundSrc(el) {
    try {
      const bg = getComputedStyle(el).backgroundImage || '';
      const match = bg.match(/url\(["']?(.+?)["']?\)/i);
      return match && IMAGE_URL_RE.test(match[1]) ? absoluteUrl(match[1]) : '';
    } catch (_) {
      return '';
    }
  }

  // 从拖拽起点往上找 3 层：很多站点的 <img> 外面套了链接/卡片，dragstart 的 target 是外层
  function urlFromElement(el) {
    for (let node = el, depth = 0; node && depth < 3; depth += 1, node = node.parentElement) {
      if (node.tagName === 'IMG') {
        const url = imageSrc(node);
        if (url) return url;
      }
      const bg = backgroundSrc(node);
      if (bg) return bg;
    }
    return '';
  }

  function urlFromTransfer(dt) {
    if (!dt) return '';
    try {
      const uriList = (dt.getData('text/uri-list') || '')
        .split(/\r?\n/)
        .find((line) => line && !line.startsWith('#'));
      if (uriList && /^https?:\/\//i.test(uriList.trim())) return absoluteUrl(uriList.trim());
      const html = dt.getData('text/html') || '';
      const match = html.match(/<img[^>]+src\s*=\s*["']([^"']+)["']/i);
      if (match) return absoluteUrl(match[1]);
      const text = (dt.getData('text/plain') || '').trim();
      if (IMAGE_URL_RE.test(text)) return absoluteUrl(text);
    } catch (_) {
      // 某些页面/浏览器拒绝读拖拽数据，忽略即可
    }
    return '';
  }

  // 拖着文件、图片、超链接或富文本都值得给投放区；读不到类型时也先显示（拖拽数据可能不可读）
  function looksLikeImageDrag(dt) {
    if (!dt) return true;
    const types = Array.from(dt.types || []);
    if (!types.length) return true;
    return types.some((type) => /files|uri-list|html|image/i.test(type));
  }

  function ensureZone() {
    if (zone && zone.isConnected) return zone;
    zone = document.createElement('div');
    zone.id = ZONE_ID;
    zone.innerHTML = '<div class="ic-zone-inner">'
      + '<div class="ic-zone-icon">⤓</div>'
      + '<div class="ic-zone-title">拖到这里采集</div>'
      + '<div class="ic-zone-sub">松手后打开采集窗口</div>'
      + '</div>';
    zone.addEventListener('dragenter', onZoneOver, true);
    zone.addEventListener('dragover', onZoneOver, true);
    zone.addEventListener('dragleave', () => zone && zone.classList.remove('ic-active'));
    zone.addEventListener('drop', onZoneDrop, true);
    (document.body || document.documentElement).appendChild(zone);
    return zone;
  }

  function setZoneSub(text) {
    const sub = zone && zone.querySelector('.ic-zone-sub');
    if (sub) sub.textContent = text || '松手后打开采集窗口';
  }

  function showZone() {
    clearTimeout(hideTimer);
    setZoneSub('');
    ensureZone().classList.add('ic-visible');
  }

  function hideZone() {
    if (!zone) return;
    zone.classList.remove('ic-visible', 'ic-active');
  }

  function warnNoUrl() {
    if (!zone) return;
    setZoneSub('没抓到图片地址，请改用右键菜单采集');
    zone.classList.add('ic-visible');
    hideTimer = setTimeout(hideZone, 2600);
  }

  function onZoneOver(event) {
    event.preventDefault();
    event.stopPropagation();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
    if (zone) zone.classList.add('ic-active');
  }

  // 松手这一刻是唯一能稳定读到 dataTransfer 的时机，所以这里再解析一次。
  // 🚨 投放区只是个 320×180 的提示框，用户松手常常落在框外 —— 所以真正的判定放在
  //    window 级 drop 里（见文件末尾），框内框外都算，别让一次拖拽白拖。
  function handleDrop(event) {
    const url = dragUrl || urlFromTransfer(event.dataTransfer) || urlFromElement(event.target);
    dragUrl = '';
    zone && zone.classList.remove('ic-active');
    if (url) {
      sendToBackground(url);
      return true;
    }
    warnNoUrl();
    return false;
  }

  function onZoneDrop(event) {
    event.preventDefault();
    event.stopPropagation();
    handleDrop(event);
  }

  function warnFailure(message) {
    if (!zone) return;
    setZoneSub(`打开采集窗口失败：${message || '未知原因'}`);
    zone.classList.add('ic-visible');
    hideTimer = setTimeout(hideZone, 4000);
  }

  // 🚨 消息类型必须跟 background.js 的 HANDLERS 键一字不差（`ic.` 前缀），
  //    写成 'openCapture' 会被判成「未知的请求类型」返回 ok:false，页面这边毫无反应。
  function sendToBackground(src) {
    setZoneSub('正在打开采集窗口…');
    try {
      chrome.runtime.sendMessage({ type: 'ic.openCapture', src }, (response) => {
        const lastError = chrome.runtime.lastError;
        if (lastError) {
          warnFailure(lastError.message);
          return;
        }
        if (response && response.ok === false) {
          warnFailure(response.error);
          return;
        }
        // 成功了也给个回执：弹窗被浏览器放到别的屏幕/别的窗口后面时，用户否则会以为没反应
        if (zone) {
          setZoneSub('已打开采集窗口（没看到就找下任务栏）');
          zone.classList.add('ic-visible');
          clearTimeout(hideTimer);
          hideTimer = setTimeout(hideZone, 3000);
        }
      });
    } catch (error) {
      // 扩展被重载后页面里的旧脚本会失效
      warnFailure((error && error.message) || '扩展已重新加载，请刷新本页');
    }
  }

  window.addEventListener('dragstart', (event) => {
    if (!looksLikeImageDrag(event.dataTransfer) && !urlFromElement(event.target)) return;
    dragUrl = urlFromElement(event.target) || urlFromTransfer(event.dataTransfer);
    showZone();
  }, true);

  // 从别的窗口/标签页/桌面拖进来时不会有 dragstart，靠 dragenter 兜底
  window.addEventListener('dragenter', (event) => {
    if (!looksLikeImageDrag(event.dataTransfer)) return;
    if (!dragUrl) dragUrl = urlFromTransfer(event.dataTransfer);
    showZone();
  }, true);

  window.addEventListener('dragend', () => {
    dragUrl = '';
    hideZone();
  }, true);

  // 页面里别处松手也算拖拽结束（延迟到本帧事件处理完再隐藏，避免挡掉投放区自己的 drop）
  window.addEventListener('drop', (event) => {
    // 落在投放区里的 drop 由 onZoneDrop 自己收尾（否则「没抓到地址」的提示会被立刻隐藏）
    if (zone && event.target instanceof Node && zone.contains(event.target)) return;
    // 框外松手：只要拖拽期间显示过投放区，就当成「拖到页面里采集」，别静默丢掉
    if (!zone || !zone.classList.contains('ic-visible')) return;
    event.preventDefault();
    handleDrop(event);
  }, true);
})();
