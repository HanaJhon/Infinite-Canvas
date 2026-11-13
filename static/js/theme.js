(function(){
    const KEY = 'studio_theme';
    const LEGACY_KEY = 'canvas_theme';
    const SCALE_KEY = 'studio_ui_scale_mode';
    const SCALE_OPTIONS = ['auto', '60', '65', '70', '75', '80', '85', '90', '95', '100', '115', '125', '140'];

    function currentTheme(){
        return localStorage.getItem(KEY) || localStorage.getItem(LEGACY_KEY) || 'light';
    }

    function applyTheme(theme){
        const next = theme === 'dark' ? 'dark' : 'light';
        const dark = next === 'dark';
        document.documentElement.classList.toggle('studio-theme-dark', dark);
        document.documentElement.classList.toggle('theme-dark', dark);
        if(document.body){
            document.body.classList.toggle('studio-theme-dark', dark);
            document.body.classList.toggle('theme-dark', dark);
        }
        window.dispatchEvent(new CustomEvent('studio-theme-change', { detail: { theme: next } }));
    }

    function ensureScaleStyle(){
        if(document.getElementById('studio-scale-style')) return;
        const style = document.createElement('style');
        style.id = 'studio-scale-style';
        style.textContent = `
            html.studio-scale-managed {
                --studio-ui-scale: 1;
            }
            html.studio-ui-scaled,
            html.studio-ui-scaled body {
                overscroll-behavior-x: none;
            }
            html.studio-ui-scaled {
                overflow-x: hidden !important;
            }
            html.studio-ui-scaled::-webkit-scrollbar:horizontal,
            html.studio-ui-scaled body::-webkit-scrollbar:horizontal {
                height: 0 !important;
            }
            html.studio-ui-scaled body:not(.studio-scale-host) {
                width: calc(100% / var(--studio-ui-scale)) !important;
                min-height: calc(100vh / var(--studio-ui-scale)) !important;
                transform: scale(var(--studio-ui-scale));
                transform-origin: 0 0;
            }
            html.studio-ui-scaled body.studio-scale-viewport:not(.studio-scale-host) {
                height: calc(100vh / var(--studio-ui-scale)) !important;
            }
            html.studio-ui-scaled body:not(.studio-scale-host) > .app-shell,
            html.studio-ui-scaled body:not(.studio-scale-host) > .shell,
            html.studio-ui-scaled body:not(.studio-scale-host) > .asset-page {
                width: 100% !important;
            }
            html.studio-ui-scaled body:not(.studio-scale-host) > .app-shell,
            html.studio-ui-scaled body:not(.studio-scale-host) > .shell {
                height: calc(100vh / var(--studio-ui-scale)) !important;
            }
            html.studio-ui-scaled body:not(.studio-scale-host) > .asset-page {
                min-height: calc(100vh / var(--studio-ui-scale)) !important;
            }
        `;
        document.head.appendChild(style);
    }

    function isFramed(){
        try {
            return window.self !== window.top;
        } catch(e) {
            return true;
        }
    }

    function normalizeScaleMode(mode){
        return SCALE_OPTIONS.includes(mode) ? mode : 'auto';
    }

    function currentScaleMode(){
        try {
            return normalizeScaleMode(localStorage.getItem(SCALE_KEY) || 'auto');
        } catch(e) {
            return 'auto';
        }
    }

    function autoScale(){
        const dpr = Math.max(1, Number(window.devicePixelRatio || 1));
        const viewportWidth = Math.max(320, Number(window.innerWidth || 0));
        const viewportHeight = Math.max(320, Number(window.innerHeight || 0));
        const compactRatio = Math.min(viewportWidth / 1500, viewportHeight / 940);
        if(compactRatio < 1) {
            return Math.max(0.68, Math.min(1, compactRatio));
        }
        const screenLong = Math.max(window.screen?.width || 0, window.screen?.height || 0);
        const viewportLong = Math.max(viewportWidth, viewportHeight);
        const longEdge = Math.max(screenLong, viewportLong);
        if(dpr >= 1.35) return 1;
        if(longEdge >= 3600) return 1.22;
        if(longEdge >= 3000) return 1.16;
        if(longEdge >= 2500 && dpr <= 1.15) return 1.1;
        return 1;
    }

    function scaleForMode(mode){
        const next = normalizeScaleMode(mode);
        if(next === 'auto' && Number.isFinite(externalScaleValue)) return externalScaleValue;
        if(next === 'auto') return autoScale();
        return Math.max(0.58, Math.min(1.4, Number(next) / 100));
    }

    let externalScaleValue = null;
    function normalizeExternalScale(value){
        const next = Number(value);
        return Number.isFinite(next) ? Math.max(0.58, Math.min(1.4, next)) : null;
    }

    function appliedScale(){
        const cssValue = Number(getComputedStyle(document.documentElement).getPropertyValue('--studio-ui-scale'));
        return Number.isFinite(cssValue) && cssValue > 0 ? cssValue : scaleForMode(currentScaleMode());
    }

    function updateScaleBodyClasses(){
        if(!document.body) return;
        const hasFrameHost = !!document.querySelector('.app-shell iframe, iframe.active');
        document.body.classList.toggle('studio-scale-host', hasFrameHost && !isFramed());
        const computed = window.getComputedStyle(document.body);
        const viewportLocked = computed.overflow === 'hidden' || computed.overflowY === 'hidden' || !!document.querySelector('.app-shell, .shell');
        document.body.classList.toggle('studio-scale-viewport', viewportLocked);
    }

    function scaleOptedOut(){
        return document.documentElement.dataset.studioScale === 'off';
    }

    function contentFitOptedOut(){
        return document.documentElement.dataset.studioFitScale === 'off';
    }

    let horizontalScrollLockPending = false;
    function lockScaledHorizontalScroll(){
        if(horizontalScrollLockPending || !document.documentElement.classList.contains('studio-ui-scaled')) return;
        if(Math.abs(window.scrollX || 0) < 1) return;
        horizontalScrollLockPending = true;
        requestAnimationFrame(() => {
            horizontalScrollLockPending = false;
            if(document.documentElement.classList.contains('studio-ui-scaled') && Math.abs(window.scrollX || 0) >= 1) {
                window.scrollTo(0, window.scrollY || 0);
            }
        });
    }

    let contentFitTimer = null;
    function scheduleContentFit(mode){
        clearTimeout(contentFitTimer);
        if(mode !== 'auto' || scaleOptedOut() || contentFitOptedOut() || Number.isFinite(externalScaleValue)) return;
        contentFitTimer = setTimeout(() => {
            const root = document.documentElement;
            if(!root.classList.contains('studio-ui-scaled')) return;
            const current = Number(getComputedStyle(root).getPropertyValue('--studio-ui-scale')) || 1;
            const viewportWidth = Math.max(320, Number(window.innerWidth || 0));
            const contentWidth = Math.max(
                viewportWidth,
                root.scrollWidth || 0,
                document.body?.scrollWidth || 0,
                document.body?.offsetWidth || 0
            );
            const fitted = Math.max(0.58, Math.min(current, viewportWidth / contentWidth));
            if(fitted < current - 0.006) {
                root.style.setProperty('--studio-ui-scale', fitted.toFixed(3));
                lockScaledHorizontalScroll();
            }
        }, 80);
    }

    function applyScale(mode){
        ensureScaleStyle();
        const next = normalizeScaleMode(mode);
        const optedOut = scaleOptedOut();
        const value = scaleForMode(next);
        const scaled = !optedOut && Math.abs(value - 1) > 0.01;
        document.documentElement.classList.add('studio-scale-managed');
        document.documentElement.classList.toggle('studio-ui-scaled', scaled);
        document.documentElement.style.setProperty('--studio-ui-scale', value.toFixed(3));
        updateScaleBodyClasses();
        lockScaledHorizontalScroll();
        scheduleContentFit(next);
        window.dispatchEvent(new CustomEvent('studio-ui-scale-change', { detail: { mode: next, scale: value } }));
    }

    function broadcastScale(mode){
        const scale = appliedScale();
        document.querySelectorAll('iframe').forEach(frame => {
            try {
                frame.contentWindow?.postMessage({ type: 'studio-ui-scale', mode, scale }, '*');
            } catch(e) {}
        });
    }

    function setScaleMode(mode, shouldBroadcast = true){
        const next = normalizeScaleMode(mode);
        try {
            localStorage.setItem(SCALE_KEY, next);
        } catch(e) {}
        applyScale(next);
        if(shouldBroadcast) broadcastScale(next);
    }

    let resizeTimer = null;
    let autoScalePausedUntil = 0;
    function pauseAutoScale(duration = 650){
        autoScalePausedUntil = Math.max(autoScalePausedUntil, Date.now() + Math.max(0, Number(duration) || 0));
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(scheduleAutoScaleRefresh, Math.max(0, autoScalePausedUntil - Date.now()) + 40);
    }

    function scheduleAutoScaleRefresh(){
        clearTimeout(resizeTimer);
        const wait = autoScalePausedUntil - Date.now();
        if(wait > 0) {
            resizeTimer = setTimeout(scheduleAutoScaleRefresh, wait + 40);
            return;
        }
        resizeTimer = setTimeout(() => {
            if(currentScaleMode() === 'auto') {
                applyScale('auto');
                broadcastScale('auto');
            }
        }, 160);
    }

    window.StudioTheme = {
        key: KEY,
        get: currentTheme,
        apply: applyTheme,
        set(theme){
            const next = theme === 'dark' ? 'dark' : 'light';
            localStorage.setItem(KEY, next);
            localStorage.setItem(LEGACY_KEY, next);
            applyTheme(next);
        }
    };

    window.StudioScale = {
        key: SCALE_KEY,
        options: SCALE_OPTIONS.slice(),
        getMode: currentScaleMode,
        getScale: () => scaleForMode(currentScaleMode()),
        apply: applyScale,
        set: setScaleMode
    };

    applyTheme(currentTheme());
    applyScale(currentScaleMode());

    // 每个功能页右下角的「小抽AI Chat」入口，跳到独立页 /ai
    function mountXvaiEntry() {
        if (document.getElementById('xvai-entry')) return;
        // 🚨 被首页 shell 用 iframe 内嵌时必须跳过：index.html 的 stage 有 16px 外边距，
        // iframe 里的胶囊会右上错开 16px，和外层那颗叠成「重影」（2026-11-13 老板反馈「重叠」）。
        if (isFramed()) return;
        const path = (location.pathname || '').replace(/\/+$/, '');
        if (path === '/ai' || /\/xvai\.html$/.test(path)) return;
        // 2026-11-13 老板：原来的青→靛渐变胶囊跟整体风格格格不入，屏幕上还会出现一层重影。
        // 两条教训：
        // ① 颜色写死，不要用 var(--card)/var(--line) —— 这些变量在部分页面只定义在 body 上，
        //    胶囊挂在 <html> 上就取不到，背景变全透明，看着像个鬼影。
        // ② 不要 backdrop-filter / transition / 大投影 —— 透明底 + 阴影会再叠一层轮廓。
        const style = document.createElement('style');
        style.textContent = '#xvai-entry{position:fixed;right:18px;bottom:18px;z-index:9998;display:inline-flex;'
            + 'align-items:center;gap:6px;height:34px;padding:0 13px;border-radius:12px;'
            + 'border:1px solid #e2e8f0;background:#fff;color:#0f172a;'
            + 'font:600 12.5px/1 Inter,system-ui,"Microsoft YaHei",sans-serif;text-decoration:none;'
            + 'box-shadow:0 2px 8px rgba(15,23,42,.06)}'
            + '#xvai-entry:hover{border-color:#cbd5e1;background:#f8fafc}'
            + '#xvai-entry i{font-style:normal;font-size:13px;line-height:1}'
            + '#xvai-entry span{white-space:nowrap}'
            + 'html.theme-dark #xvai-entry{border-color:#2a3446;background:#1b2130;color:#e8eefc}'
            // 2026-11-13 老板：画布右下角的常驻「?」复习中心已经自己上移到 bottom:66px
            // （见 canvas-tour.css .ct-hub），胶囊不用再让位，保持默认右下角即可。
            + 'html.theme-dark #xvai-entry:hover{border-color:#3b475c;background:#222a3a}';
        document.head.appendChild(style);
        const a = document.createElement('a');
        a.id = 'xvai-entry';
        a.href = '/ai';
        a.title = '打开小抽AI Chat';
        a.innerHTML = '<i>\u2728</i><span>\u5c0f\u62bdAI Chat</span>';
        // 挂到 <html> 上：body 在 studio-ui-scaled 下有 transform，fixed 会跟着 body 缩放/偏移
        document.documentElement.appendChild(a);
    }

    document.addEventListener('DOMContentLoaded', () => {
        applyTheme(currentTheme());
        applyScale(currentScaleMode());
        mountXvaiEntry();
    });
    window.addEventListener('message', event => {
        if(event.data?.type === 'studio-theme') applyTheme(event.data.theme);
        if(event.data?.type === 'studio-ui-scale') {
            const incomingScale = normalizeExternalScale(event.data.scale);
            if(incomingScale !== null) externalScaleValue = incomingScale;
            setScaleMode(event.data.mode, false);
        }
        if(event.data?.type === 'studio-ui-scale-pause') pauseAutoScale(event.data.duration);
    });
    window.addEventListener('storage', event => {
        if(event.key === KEY || event.key === LEGACY_KEY) applyTheme(currentTheme());
        if(event.key === SCALE_KEY) applyScale(currentScaleMode());
    });
    window.addEventListener('resize', scheduleAutoScaleRefresh);
    window.addEventListener('scroll', lockScaledHorizontalScroll, { passive: true });
})();
