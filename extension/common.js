// 页面端公共工具：和后台 service worker 通信、登录表单绑定、提示文案。
const IC = {
  DEFAULT_BASE: 'http://127.0.0.1:3000',

  // 发消息给 background；后台返回 {ok:false,error} 时转成异常，方便各页面统一 try/catch。
  send(message) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(message, (resp) => {
        const lastError = chrome.runtime.lastError;
        if (lastError) {
          reject(new Error(`扩展后台无响应（${lastError.message}）`));
          return;
        }
        if (!resp) {
          reject(new Error('扩展后台无响应'));
          return;
        }
        if (resp.ok === false) {
          const err = new Error(resp.error || '操作失败');
          err.status = resp.status || 0;
          reject(err);
          return;
        }
        resolve(resp);
      });
    });
  },

  showMsg(el, text, kind) {
    if (!el) return;
    el.textContent = text || '';
    el.className = 'msg' + (kind ? ` ${kind}` : '');
  },

  // 给 capture / options 共用的登录表单接线。
  bindLogin({ nameEl, passEl, btn, msgEl, onDone }) {
    const submit = async () => {
      const name = nameEl.value.trim();
      const password = passEl.value;
      if (!name || !password) {
        IC.showMsg(msgEl, '请填写用户名和密码', 'err');
        return;
      }
      btn.disabled = true;
      IC.showMsg(msgEl, '登录中…');
      try {
        const result = await IC.send({ type: 'ic.login', name, password });
        IC.showMsg(msgEl, '登录成功', 'ok');
        if (onDone) onDone(result.user || null);
      } catch (err) {
        IC.showMsg(msgEl, err.message, 'err');
      } finally {
        btn.disabled = false;
      }
    };
    btn.addEventListener('click', submit);
    [nameEl, passEl].forEach((el) => {
      el.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') submit();
      });
    });
  },
};
