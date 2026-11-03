// 采集界面：待采集缩略图列表 + 选素材库/分类 + 新建分类 + 确认采集。
// 网络请求全部交给 background（见 background.js 的消息分发）。
const state = {
  items: [],
  libraries: [],
  activeLibraryId: '',
  user: null,
};

const el = {
  userLabel: document.getElementById('userLabel'),
  loginPanel: document.getElementById('loginPanel'),
  mainPanel: document.getElementById('mainPanel'),
  loginName: document.getElementById('loginName'),
  loginPassword: document.getElementById('loginPassword'),
  loginBtn: document.getElementById('loginBtn'),
  loginMsg: document.getElementById('loginMsg'),
  urlInput: document.getElementById('urlInput'),
  addUrlBtn: document.getElementById('addUrlBtn'),
  scanBtn: document.getElementById('scanBtn'),
  countLabel: document.getElementById('countLabel'),
  clearBtn: document.getElementById('clearBtn'),
  thumbList: document.getElementById('thumbList'),
  librarySelect: document.getElementById('librarySelect'),
  categorySelect: document.getElementById('categorySelect'),
  newCatBtn: document.getElementById('newCatBtn'),
  newCatRow: document.getElementById('newCatRow'),
  newCatName: document.getElementById('newCatName'),
  createCatBtn: document.getElementById('createCatBtn'),
  confirmBtn: document.getElementById('confirmBtn'),
  statusMsg: document.getElementById('statusMsg'),
};

// ---------------------------------------------------------------- 列表

function addItem(rawUrl, silent) {
  const url = String(rawUrl || '').trim();
  if (!/^https?:\/\//i.test(url)) {
    if (!silent) {
      IC.showMsg(el.statusMsg, /^data:/i.test(url)
        ? '这张图是网页内嵌的 data 地址，暂不支持，请在网页上右键另存后改用它所在的原图地址'
        : '只支持 http/https 图片地址', 'err');
    }
    return false;
  }
  if (state.items.some((item) => item.url === url)) {
    if (!silent) IC.showMsg(el.statusMsg, '这张图片已经在列表里了');
    return false;
  }
  state.items.push({ url, name: defaultItemName(url) });
  renderThumbs();
  if (!silent) IC.showMsg(el.statusMsg, `已添加 ${state.items.length} 张`);
  return true;
}

// 图片地址里的文件名往往是无意义的哈希，给个能改的默认名：优先 URL 的文件名
function defaultItemName(rawUrl) {
  try {
    const base = decodeURIComponent(new URL(rawUrl).pathname.split('/').pop() || '');
    return base.replace(/\.[a-z0-9]{2,5}$/i, '').replace(/[\\/:*?"<>|#%]+/g, '_').slice(0, 60);
  } catch (_) {
    return '';
  }
}

function renderThumbs() {
  el.countLabel.textContent = String(state.items.length);
  el.thumbList.textContent = '';
  if (!state.items.length) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = '还没有图片';
    el.thumbList.appendChild(empty);
    return;
  }
  state.items.forEach((item, index) => {
    const card = document.createElement('div');
    card.className = 'thumb';

    const img = document.createElement('img');
    img.src = item.url;
    img.alt = '';
    img.loading = 'lazy';
    img.referrerPolicy = 'no-referrer';

    const name = document.createElement('input');
    name.className = 'thumb-name';
    name.type = 'text';
    name.maxLength = 60;
    name.placeholder = '给这张图起个名字';
    name.value = item.name || '';
    name.addEventListener('input', () => {
      if (state.items[index]) state.items[index].name = name.value;
    });

    const del = document.createElement('button');
    del.className = 'thumb-del';
    del.type = 'button';
    del.title = '移除这张';
    del.textContent = '×';
    del.addEventListener('click', () => {
      state.items.splice(index, 1);
      renderThumbs();
      IC.showMsg(el.statusMsg, '');
    });

    card.appendChild(img);
    card.appendChild(name);
    card.appendChild(del);
    el.thumbList.appendChild(card);
  });
}

// ---------------------------------------------------------------- 素材库 / 分类

function renderCategories(preferId) {
  const library = state.libraries.find((item) => item.id === el.librarySelect.value);
  el.categorySelect.textContent = '';
  const cats = library ? library.categories : [];
  cats.forEach((cat) => {
    const option = document.createElement('option');
    option.value = cat.id;
    option.textContent = cat.name;
    el.categorySelect.appendChild(option);
  });
  if (!cats.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = '（该素材库没有图片分类，请先新建）';
    el.categorySelect.appendChild(option);
  } else if (preferId && cats.some((cat) => cat.id === preferId)) {
    el.categorySelect.value = preferId;
  }
}

function renderLibraries(preferCategoryId) {
  const picked = el.librarySelect.value;
  el.librarySelect.textContent = '';
  state.libraries.forEach((library) => {
    const option = document.createElement('option');
    option.value = library.id;
    option.textContent = library.name;
    el.librarySelect.appendChild(option);
  });
  const wanted = state.libraries.some((item) => item.id === picked) ? picked : state.activeLibraryId;
  if (wanted && state.libraries.some((item) => item.id === wanted)) el.librarySelect.value = wanted;
  renderCategories(preferCategoryId);
}

async function loadLibraries(preferCategoryId) {
  const result = await IC.send({ type: 'ic.libraries' });
  state.libraries = result.libraries || [];
  state.activeLibraryId = result.active_library_id || '';
  renderLibraries(preferCategoryId);
}

// ---------------------------------------------------------------- 登录状态

async function refreshAuth() {
  let result;
  try {
    result = await IC.send({ type: 'ic.me' });
  } catch (err) {
    result = { user: null, error: err.message };
  }
  state.user = result.user || null;
  const loggedIn = !!state.user;
  el.userLabel.textContent = loggedIn ? state.user.name : '未登录';
  el.loginPanel.hidden = loggedIn;
  el.mainPanel.hidden = !loggedIn;
  if (!loggedIn && result.error) IC.showMsg(el.loginMsg, result.error, 'err');
  return loggedIn;
}

async function afterLogin() {
  await refreshAuth();
  if (!state.user) return;
  try {
    await loadLibraries();
    IC.showMsg(el.statusMsg, '已登录，可以采集了', 'ok');
  } catch (err) {
    IC.showMsg(el.statusMsg, `读取素材库失败：${err.message}`, 'err');
  }
}

// ---------------------------------------------------------------- 确认采集

function selectedText(select) {
  const option = select.selectedOptions[0];
  return option ? option.textContent : '';
}

async function confirmCapture() {
  if (!state.user) {
    IC.showMsg(el.statusMsg, '请先登录', 'err');
    await refreshAuth();
    return;
  }
  if (!state.items.length) {
    IC.showMsg(el.statusMsg, '请先添加要采集的图片', 'err');
    return;
  }
  const libraryId = el.librarySelect.value;
  const categoryId = el.categorySelect.value;
  if (!libraryId || !categoryId) {
    IC.showMsg(el.statusMsg, '请选择素材库和图片分类', 'err');
    return;
  }

  el.confirmBtn.disabled = true;
  const uploaded = [];
  const failed = [];
  const failedItems = [];
  try {
    for (let index = 0; index < state.items.length; index += 1) {
      const item = state.items[index];
      IC.showMsg(el.statusMsg, `正在处理 ${index + 1}/${state.items.length}…`);
      try {
        const result = await IC.send({ type: 'ic.uploadImage', url: item.url, name: item.name || '', index });
        uploaded.push(result.file);
      } catch (err) {
        failed.push(err.message);
        failedItems.push(item);
        if (err.status === 401) {
          await refreshAuth();
          throw new Error('登录已失效，请重新登录后再采集');
        }
      }
    }

    if (!uploaded.length) throw new Error(`全部失败：${failed.join('；')}`);

    const added = await IC.send({
      type: 'ic.addItems',
      library_id: libraryId,
      category_id: categoryId,
      items: uploaded,
    });

    const where = `${selectedText(el.librarySelect)} / ${selectedText(el.categorySelect)}`;
    let text = `已采集 ${added.count || uploaded.length} 张到 ${where}`;
    if (failed.length) text += `；${failed.length} 张失败：${failed.join('；')}`;
    IC.showMsg(el.statusMsg, text, failed.length ? 'warn' : 'ok');

    // 成功的从列表里移除，失败的留着方便重试
    state.items = failedItems;
    renderThumbs();
  } catch (err) {
    const detail = failed.length ? `；失败原因：${failed.join('；')}` : '';
    IC.showMsg(el.statusMsg, `${err.message}${detail}`, 'err');
    state.items = failedItems.length ? failedItems : state.items;
    renderThumbs();
  } finally {
    el.confirmBtn.disabled = false;
  }
}

// ---------------------------------------------------------------- 初始化

async function addPendingImages() {
  let stored;
  try {
    stored = await chrome.storage.local.get('pendingImages');
  } catch (_) {
    return;
  }
  const pending = stored && stored.pendingImages;
  if (!pending || !Array.isArray(pending.urls) || !pending.urls.length) return;
  await chrome.storage.local.remove('pendingImages');
  if (Date.now() - Number(pending.ts || 0) > 10 * 60 * 1000) return;
  pending.urls.forEach((url) => addItem(url, true));
  renderThumbs();
  if (state.items.length) IC.showMsg(el.statusMsg, `已从当前网页带入 ${state.items.length} 张图片`);
}

async function scanCurrentPage() {
  el.scanBtn.disabled = true;
  IC.showMsg(el.statusMsg, '正在扫描网页图片…');
  try {
    const result = await IC.send({ type: 'ic.collectImages' });
    const urls = result.urls || [];
    let added = 0;
    urls.forEach((url) => {
      if (addItem(url, true)) added += 1;
    });
    if (!added) IC.showMsg(el.statusMsg, '这张网页没找到可采集的图片（也可能是页面还没加载完）', 'warn');
    else IC.showMsg(el.statusMsg, `已从网页加入 ${added} 张图片`, 'ok');
  } catch (err) {
    IC.showMsg(el.statusMsg, err.message, 'err');
  } finally {
    el.scanBtn.disabled = false;
  }
}

function wireEvents() {
  IC.bindLogin({
    nameEl: el.loginName,
    passEl: el.loginPassword,
    btn: el.loginBtn,
    msgEl: el.loginMsg,
    onDone: afterLogin,
  });

  el.addUrlBtn.addEventListener('click', () => {
    if (addItem(el.urlInput.value)) el.urlInput.value = '';
  });
  el.urlInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && addItem(el.urlInput.value)) el.urlInput.value = '';
  });

  el.scanBtn.addEventListener('click', scanCurrentPage);

  el.clearBtn.addEventListener('click', () => {
    state.items = [];
    renderThumbs();
    IC.showMsg(el.statusMsg, '列表已清空');
  });

  el.librarySelect.addEventListener('change', () => renderCategories());

  el.newCatBtn.addEventListener('click', () => {
    el.newCatRow.hidden = !el.newCatRow.hidden;
    if (!el.newCatRow.hidden) el.newCatName.focus();
  });

  el.createCatBtn.addEventListener('click', async () => {
    const name = el.newCatName.value.trim();
    if (!name) {
      IC.showMsg(el.statusMsg, '请输入新分类名称', 'err');
      return;
    }
    if (!el.librarySelect.value) {
      IC.showMsg(el.statusMsg, '请先选择素材库', 'err');
      return;
    }
    el.createCatBtn.disabled = true;
    try {
      const result = await IC.send({
        type: 'ic.createCategory',
        name,
        library_id: el.librarySelect.value,
      });
      state.libraries = result.libraries || [];
      renderLibraries(result.category_id);
      el.newCatName.value = '';
      el.newCatRow.hidden = true;
      IC.showMsg(el.statusMsg, `已新建分类「${name}」`, 'ok');
    } catch (err) {
      IC.showMsg(el.statusMsg, `新建分类失败：${err.message}`, 'err');
    } finally {
      el.createCatBtn.disabled = false;
    }
  });

  el.confirmBtn.addEventListener('click', confirmCapture);
}

async function init() {
  wireEvents();
  renderThumbs();
  const loggedIn = await refreshAuth();
  if (loggedIn) {
    try {
      await loadLibraries();
    } catch (err) {
      IC.showMsg(el.statusMsg, `读取素材库失败：${err.message}`, 'err');
    }
  }

  const src = new URLSearchParams(location.search).get('src');
  if (src) {
    if (addItem(src)) {
      IC.showMsg(el.statusMsg, '已加入右键采集的图片，选好素材库和分类后点「确认采集」');
    }
    return;
  }

  await addPendingImages();
  if (!state.items.length) {
    IC.showMsg(el.statusMsg, '把网页图片拖到页面中间投放区，或右键图片采集；也可以直接粘贴图片地址');
  }
}

init();
