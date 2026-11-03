/* 采集扩展主题：07:00–18:00 浅色，其余时间深色；点顶栏右侧图标手动切换并记住（ic_theme）。
   popup / capture / options 三个页面共用这一份，图标按钮由这里注入到 .bar。 */
(function () {
  const KEY = 'ic_theme';
  const LIGHT_FROM = 7;
  const LIGHT_TO = 18;

  const ICONS =
    '<svg class="theme-ico theme-ico-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    + '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>'
    + '<svg class="theme-ico theme-ico-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    + '<circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line>'
    + '<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>'
    + '<line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line>'
    + '<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>';

  function storedTheme() {
    try {
      const value = localStorage.getItem(KEY);
      return value === 'light' || value === 'dark' ? value : '';
    } catch (e) {
      return '';
    }
  }

  function autoTheme() {
    const hour = new Date().getHours();
    return hour >= LIGHT_FROM && hour < LIGHT_TO ? 'light' : 'dark';
  }

  function currentTheme() {
    return storedTheme() || autoTheme();
  }

  function apply(theme) {
    const next = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    document.querySelectorAll('[data-theme-toggle]').forEach((btn) => {
      btn.title = next === 'dark' ? '切换到浅色' : '切换到深色';
      btn.setAttribute('aria-label', btn.title);
    });
  }

  function set(theme) {
    const next = theme === 'dark' ? 'dark' : 'light';
    try {
      localStorage.setItem(KEY, next);
    } catch (e) {}
    apply(next);
  }

  // 清掉手动选择，回到按时间自动
  function setAuto() {
    try {
      localStorage.removeItem(KEY);
    } catch (e) {}
    apply(currentTheme());
  }

  function toggle() {
    set(currentTheme() === 'dark' ? 'light' : 'dark');
  }

  function mountToggles() {
    document.querySelectorAll('.bar').forEach((bar) => {
      if (bar.querySelector('[data-theme-toggle]')) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'bar-theme';
      btn.setAttribute('data-theme-toggle', '');
      btn.innerHTML = ICONS;
      btn.addEventListener('click', toggle);
      bar.appendChild(btn);
    });
    apply(currentTheme());
  }

  window.IcTheme = { key: KEY, get: currentTheme, getAuto: autoTheme, set: set, setAuto: setAuto, toggle: toggle, apply: apply };

  apply(currentTheme());
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountToggles);
  } else {
    mountToggles();
  }

  // 页面一直开着，跨过 07:00 / 18:00 也要换（只有跟随时间时才动）
  setInterval(() => {
    if (!storedTheme() && document.documentElement.dataset.theme !== autoTheme()) apply(autoTheme());
  }, 60 * 1000);
})();
