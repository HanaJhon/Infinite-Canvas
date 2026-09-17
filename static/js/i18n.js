(function(){
    // 版本号从自身的 <script src="...i18n.js?v=xxx"> 上取。服务端把 i18n.js 的版本设成
    // static/js/i18n/ 目录里最新的 mtime，所以任何词条改动都会换 URL。原来这里写死
    // '2026.07.04.rec-ui.1'，子包 URL 永不变化，而 /static 下的 JS 没有任何缓存头，
    // 浏览器会按 Last-Modified 做启发式缓存 —— 结果就是改了词条前端仍读旧字典。
    const FALLBACK_VERSION = '2026.07.04.rec-ui.1';
    const VERSION = (function(){
        try {
            const tag = document.currentScript
                || Array.from(document.scripts).find(s => /\/i18n\.js(\?|$)/.test(s.src || ''));
            const v = tag && new URL(tag.src, location.href).searchParams.get('v');
            return v || FALLBACK_VERSION;
        } catch(e) {
            return FALLBACK_VERSION;
        }
    })();
    const scripts = [
        '/static/js/i18n-core.js',
        '/static/js/i18n/common.js',
        '/static/js/i18n/studio.js',
        '/static/js/i18n/api-settings.js',
        '/static/js/i18n/canvas.js',
        '/static/js/i18n/smart-canvas.js',
        '/static/js/i18n/comfyui-settings.js',
    ];
    const tags = scripts.map(src => '<script src="' + src + '?v=' + VERSION + '"></script>').join('');
    if(document.readyState === 'loading' && document.currentScript){
        document.write(tags);
        return;
    }
    scripts.reduce((promise, src) => promise.then(() => new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src + '?v=' + VERSION;
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    })), Promise.resolve()).then(() => window.StudioI18n?.apply?.()).catch(err => console.error('Failed to load i18n modules', err));
})();
