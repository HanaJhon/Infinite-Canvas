/* 图文分层编辑（image2psd）窗口。
 *
 * 分层与 PSD 写出走后端内置的 bggg-creator-image2psd 脚本；
 * 这里负责窗口交互、图层模型、画布预览、文字层与导出。
 *
 * 依赖 smart-canvas.js 暴露的全局：nodes / toast / tr / escapeHtml / escapeAttr /
 * refreshIcons / apiProviders / chatProviderOptions / chatModelOptions /
 * resolveChatProviderId / resolveChatModel / imageForDisplay / displayMediaUrl
 */
(function () {
    'use strict';

    const FONT_PREFIX = 'I2P_';
    const MAX_LLM_IMAGE_EDGE = 1536;
    const BLEND_OP = { normal: 'source-over', multiply: 'multiply', screen: 'screen', overlay: 'overlay' };

    const state = {
        open: false,
        nodeId: '',
        imageIndex: 0,
        sourceUrl: '',
        sourceName: '',
        project: '',
        mode: 'colors',
        numColors: 8,
        canvas: { width: 0, height: 0, background: '#ffffff' },
        zoom: 1,
        exportScale: 1,
        layers: [],
        selectedId: '',
        tool: 'select',
        brushSize: 48,
        llm: { provider: '', model: '' },
        fonts: [],
        fontDefault: '',
        fontsReady: false,
        drawing: null,
        dragging: null,
        contentCache: new Map(),
        imageCache: new Map(),
        imagePromises: new Map(),
        busy: false,
        dirty: false,
    };

    let els = null;
    let uidSeed = 0;
    const uid = (prefix) => `${prefix || 'l'}_${Date.now().toString(36)}_${(++uidSeed).toString(36)}`;

    // ---------------------------------------------------------------- 工具

    function q(id) { return document.getElementById(id); }

    function clamp(value, min, max) { return Math.min(max, Math.max(min, value)); }

    function num(value, fallback) {
        // 注意 Number(null) === 0：null/空串必须走默认值，否则 newTextLayer(null) 会得到字号 0。
        if (value === null || value === undefined || value === '') return fallback || 0;
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : (fallback || 0);
    }

    function selectedLayer() {
        return state.layers.find((layer) => layer.id === state.selectedId) || null;
    }

    function topDownLayers() {
        return state.layers.slice().reverse();
    }

    function setBusy(text) {
        if (!els) return;
        state.busy = !!text;
        els.busy.hidden = !text;
        if (text) els.busyText.textContent = text;
    }

    function toastSafe(text) {
        if (typeof toast === 'function') toast(text);
    }

    /** 取词条并做 {name} 占位替换。i18n-core 的 t() 不做插值，所以在这里补一层。 */
    function t(key, params) {
        let text = typeof tr === 'function' ? tr(key) : key;
        if (params) {
            Object.keys(params).forEach((name) => {
                text = text.split('{' + name + '}').join(String(params[name]));
            });
        }
        return text;
    }

    /** 后端已知告警码 → 词条；未知码回落到后端原文（中文）。 */
    const WARNING_KEYS = { empty_layer: 'i2p.warnEmptyLayer', text_raster: 'i2p.warnTextRaster' };

    function warningText(code, fallback) {
        const key = WARNING_KEYS[code && code.code];
        if (!key) return String(fallback || '');
        return t(key, { layer: (code && code.layer) || '' });
    }

    async function postJson(url, body) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {}),
        });
        const text = await response.text();
        let data = null;
        try { data = text ? JSON.parse(text) : null; } catch (error) { data = null; }
        if (!response.ok) {
            const detail = (data && (data.detail || data.message)) || text || `HTTP ${response.status}`;
            throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
        }
        return data;
    }

    function parseJsonLoose(text) {
        let raw = String(text || '').trim();
        const fence = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
        if (fence) raw = fence[1].trim();
        const start = raw.search(/[[{]/);
        if (start > 0) raw = raw.slice(start);
        const end = Math.max(raw.lastIndexOf('}'), raw.lastIndexOf(']'));
        if (end >= 0) raw = raw.slice(0, end + 1);
        try { return JSON.parse(raw); } catch (error) { return null; }
    }

    function loadImage(url, timeout) {
        if (!url) return Promise.reject(new Error(t('i2p.errNoUrl')));
        // imageCache 只放「已解码完成」的 Image；promise 单独放 imagePromises。
        // 混在一起会让渲染路径拿到 Promise 而画不出东西。
        if (state.imageCache.has(url)) return Promise.resolve(state.imageCache.get(url));
        if (state.imagePromises.has(url)) return state.imagePromises.get(url);
        const promise = new Promise((resolve, reject) => {
            const img = new Image();
            const timer = window.setTimeout(() => {
                state.imagePromises.delete(url);
                reject(new Error(t('i2p.errImgTimeout')));
            }, timeout || 20000);
            img.onload = () => {
                window.clearTimeout(timer);
                img.__loaded = true;
                state.imageCache.set(url, img);
                resolve(img);
            };
            img.onerror = () => {
                window.clearTimeout(timer);
                state.imagePromises.delete(url);
                reject(new Error(t('i2p.errImgLoad')));
            };
            img.src = url;
        });
        state.imagePromises.set(url, promise);
        return promise;
    }

    /** 取源图（用于喂给视觉模型）。源图地址不可用时退回第一张图层图。 */
    async function sourceImage() {
        const candidates = [state.sourceUrl];
        const first = state.layers.find((layer) => layer.type === 'image' && layer.url);
        if (first) candidates.push(first.url);
        for (const url of candidates) {
            try { return await loadImage(url); } catch (error) { /* 换下一个候选 */ }
        }
        throw new Error(t('i2p.errSourceLoad'));
    }

    function imageToDataUrl(img, maxEdge) {
        const scale = Math.min(1, maxEdge / Math.max(img.naturalWidth || img.width, img.naturalHeight || img.height));
        const width = Math.max(1, Math.round((img.naturalWidth || img.width) * scale));
        const height = Math.max(1, Math.round((img.naturalHeight || img.height) * scale));
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, width, height);
        return canvas.toDataURL('image/jpeg', 0.92);
    }

    function downloadUrl(url, filename) {
        const anchor = document.createElement('a');
        anchor.href = url;
        if (filename) anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
    }

    // ---------------------------------------------------------------- 字体

    /** 字体下拉渲染与语言无关的部分：切换语言时需要重画（分组标题要跟着变）。 */
    function renderFontOptions() {
        if (!els.fontFamily || !state.fontsReady) return;
        const current = els.fontFamily.value;
        const groups = [
            { label: t('i2p.fontGroupCjk'), items: state.fonts.filter((font) => font.cjk) },
            { label: t('i2p.fontGroupOther'), items: state.fonts.filter((font) => !font.cjk) },
        ];
        els.fontFamily.innerHTML = groups
            .filter((group) => group.items.length)
            .map((group) => `<optgroup label="${escapeAttr(group.label)}">${group.items
                .map((font) => `<option value="${escapeAttr(font.family)}">${escapeHtml(font.family)}${font.style && font.style !== 'Regular' ? ' · ' + escapeHtml(font.style) : ''}</option>`)
                .join('')}</optgroup>`)
            .join('');
        if (current) els.fontFamily.value = current;
    }

    async function loadFontList() {
        if (state.fontsReady) { renderFontOptions(); return; }
        const data = await fetch('/api/image2psd/fonts').then((response) => response.json());
        state.fonts = Array.isArray(data.fonts) ? data.fonts : [];
        state.fontDefault = data.default || '';
        state.fontsReady = true;
        renderFontOptions();
    }

    /** LLM 平台下拉：沿用画布里的对话模型列表；一个都没配时给出默认平台兜底，避免空下拉。 */
    function llmProviderOptionsHtml(selected) {
        const html = chatProviderOptions(selected);
        if (html) return html;
        const id = resolveChatProviderId(selected) || 'comfly';
        return `<option value="${escapeAttr(id)}">${escapeHtml(id)}${escapeHtml(t('i2p.defaultPlatform'))}</option>`;
    }

    function syncLlmSelects() {
        state.llm.provider = resolveChatProviderId(state.llm.provider || '');
        state.llm.model = resolveChatModel(state.llm.model || '', state.llm.provider);
        els.extractProvider.innerHTML = llmProviderOptionsHtml(state.llm.provider);
        els.extractModel.innerHTML = chatModelOptions(state.llm.model, state.llm.provider);
        state.llm.provider = els.extractProvider.value || state.llm.provider;
        state.llm.model = els.extractModel.value || state.llm.model;
    }

    async function ensureFont(family) {        const name = String(family || '').trim();
        if (!name) return '';
        const cssName = FONT_PREFIX + name;
        if (document.fonts && document.fonts.check(`16px "${cssName}"`)) return cssName;
        try {
            const face = new FontFace(cssName, `url("/api/image2psd/font?family=${encodeURIComponent(name)}")`);
            await face.load();
            document.fonts.add(face);
        } catch (error) {
            /* 字体加载失败就退回浏览器默认字体渲染，后端导出仍会用真实字体 */
        }
        return cssName;
    }

    // ---------------------------------------------------------------- 图层模型

    function newImageLayer(source, index) {
        return {
            id: uid('img'),
            type: 'image',
            name: source.name || `${t('i2p.imageLayer')} ${index + 1}`,
            url: source.url,
            color: source.color || '',
            visible: true,
            x: 0, y: 0,
            w: state.canvas.width, h: state.canvas.height,
            rotation: 0, opacity: 1, blend: 'normal',
            adjust: { brightness: 0, contrast: 0, saturate: 0, hue: 0 },
            mask: { strokes: [] },
            shadow: { color: '#000000', x: 0, y: 0, blur: 0 },
        };
    }

    function newTextLayer(seed) {
        const layer = {
            id: uid('txt'),
            type: 'text',
            name: (seed && seed.name) || t('i2p.textLayer'),
            visible: true,
            x: num(seed && seed.x, 60),
            y: num(seed && seed.y, 60),
            w: 200, h: 60,
            rotation: 0, opacity: 1, blend: 'normal',
            text: (seed && seed.text) || t('i2p.textPlaceholder'),
            font: (seed && seed.font) || state.fontDefault || '',
            fontSize: Math.max(8, Math.round(num(seed && seed.fontSize, 48))),
            color: (seed && seed.color) || '#111111',
            align: (seed && seed.align) || 'left',
            lineSpacing: 1.25,
            letterSpacing: 0,
            maxWidth: Math.max(0, Math.round(num(seed && seed.maxWidth, 0))),
            shadow: { color: '#000000', x: 0, y: 0, blur: 0 },
        };
        measureTextLayer(layer);
        return layer;
    }

    function layerById(id) {
        return state.layers.find((layer) => layer.id === id) || null;
    }

    function invalidate(layer) {
        if (!layer) return;
        state.contentCache.delete(layer.id);
        state.dirty = true;
    }

    // ---------------------------------------------------------------- 文字排版

    function textFontSpec(layer) {
        return `${layer.fontSize}px "${FONT_PREFIX}${layer.font || 'sans-serif'}", "Microsoft YaHei", sans-serif`;
    }

    function wrapTextLines(ctx, layer) {
        const raw = String(layer.text || '');
        const lines = raw.split('\n');
        const maxWidth = layer.maxWidth > 0 ? layer.maxWidth : 0;
        ctx.font = textFontSpec(layer);
        if (ctx.letterSpacing !== undefined) ctx.letterSpacing = `${layer.letterSpacing || 0}px`;
        if (!maxWidth) return lines;
        const out = [];
        lines.forEach((line) => {
            if (!line) { out.push(''); return; }
            let buffer = '';
            line.split(/(\s+)/).forEach((token) => {
                if (!token) return;
                const trial = buffer + token;
                if (buffer && ctx.measureText(trial.trim()).width > maxWidth) {
                    out.push(buffer.trim());
                    buffer = token.replace(/^\s+/, '');
                } else {
                    buffer = trial;
                }
            });
            out.push(buffer.trim());
        });
        return out;
    }

    function measureTextLayer(layer) {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        ctx.font = textFontSpec(layer);
        if (ctx.letterSpacing !== undefined) ctx.letterSpacing = `${layer.letterSpacing || 0}px`;
        const lines = wrapTextLines(ctx, layer);
        const lineHeight = Math.max(1, Math.round(layer.fontSize * layer.lineSpacing));
        let width = 0;
        lines.forEach((line) => { width = Math.max(width, ctx.measureText(line || ' ').width); });
        layer.lines = lines;
        layer.w = Math.max(4, Math.round(layer.maxWidth > 0 ? layer.maxWidth : width));
        layer.h = Math.max(4, lines.length * lineHeight);
        layer.lineHeight = lineHeight;
        invalidate(layer);
    }

    // ---------------------------------------------------------------- 图层内容渲染

    function applyAdjustFilter(ctx, adjust) {
        const parts = [];
        const brightness = num(adjust && adjust.brightness, 0);
        const contrast = num(adjust && adjust.contrast, 0);
        const saturate = num(adjust && adjust.saturate, 0);
        const hue = num(adjust && adjust.hue, 0);
        if (brightness) parts.push(`brightness(${clamp(1 + brightness / 100, 0, 3)})`);
        if (contrast) parts.push(`contrast(${clamp(1 + contrast / 100, 0, 3)})`);
        if (saturate) parts.push(`saturate(${clamp(1 + saturate / 100, 0, 4)})`);
        if (hue) parts.push(`hue-rotate(${hue}deg)`);
        ctx.filter = parts.length ? parts.join(' ') : 'none';
    }

    function paintMaskStrokes(ctx, strokes) {
        if (!strokes || !strokes.length) return;
        ctx.save();
        ctx.globalCompositeOperation = 'destination-out';
        ctx.strokeStyle = '#000';
        ctx.fillStyle = '#000';
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        strokes.forEach((stroke) => {
            if (!stroke) return;
            if (stroke.type === 'rect') {
                ctx.fillRect(num(stroke.x, 0), num(stroke.y, 0), num(stroke.w, 0), num(stroke.h, 0));
                return;
            }
            const points = Array.isArray(stroke.points) ? stroke.points : [];
            if (!points.length) return;
            ctx.lineWidth = Math.max(1, num(stroke.size, state.brushSize));
            if (points.length === 1) {
                ctx.beginPath();
                ctx.arc(points[0][0], points[0][1], ctx.lineWidth / 2, 0, Math.PI * 2);
                ctx.fill();
                return;
            }
            ctx.beginPath();
            ctx.moveTo(points[0][0], points[0][1]);
            for (let index = 1; index < points.length; index += 1) ctx.lineTo(points[index][0], points[index][1]);
            ctx.stroke();
        });
        ctx.restore();
    }

    function maskSignature(layer) {
        const strokes = (layer.mask && layer.mask.strokes) || [];
        return strokes.map((stroke) => {
            if (stroke.type === 'rect') return `r${Math.round(stroke.x)},${Math.round(stroke.y)},${Math.round(stroke.w)},${Math.round(stroke.h)}`;
            const points = stroke.points || [];
            return `${Math.round(stroke.size || 0)}:${points.length}:${points.length ? Math.round(points[points.length - 1][0]) + ',' + Math.round(points[points.length - 1][1]) : ''}`;
        }).join('|');
    }

    function layerContent(layer) {
        const width = Math.max(1, Math.round(layer.w));
        const height = Math.max(1, Math.round(layer.h));
        if (layer.type === 'text') {
            const signature = [layer.text, layer.font, layer.fontSize, layer.color, layer.align,
                layer.lineSpacing, layer.letterSpacing, layer.maxWidth, width, height].join('~');
            const cached = state.contentCache.get(layer.id);
            if (cached && cached.signature === signature) return cached.canvas;
            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;
            const ctx = canvas.getContext('2d');
            ctx.font = textFontSpec(layer);
            if (ctx.letterSpacing !== undefined) ctx.letterSpacing = `${layer.letterSpacing || 0}px`;
            ctx.textBaseline = 'top';
            ctx.fillStyle = layer.color || '#111111';
            const lines = layer.lines || wrapTextLines(ctx, layer);
            const lineHeight = layer.lineHeight || Math.max(1, Math.round(layer.fontSize * layer.lineSpacing));
            lines.forEach((line, index) => {
                const measured = ctx.measureText(line || ' ').width;
                let x = 0;
                if (layer.maxWidth > 0 && layer.align === 'center') x = (width - measured) / 2;
                else if (layer.maxWidth > 0 && layer.align === 'right') x = width - measured;
                ctx.fillText(line, x, index * lineHeight);
            });
            state.contentCache.set(layer.id, { signature, canvas });
            return canvas;
        }
        const adjust = layer.adjust || {};
        const signature = [layer.url, width, height, JSON.stringify(adjust), maskSignature(layer)].join('~');
        const cached = state.contentCache.get(layer.id);
        if (cached && cached.signature === signature) return cached.canvas;
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        const img = state.imageCache.get(layer.url);
        if (img && img.__loaded) {
            ctx.save();
            applyAdjustFilter(ctx, adjust);
            ctx.drawImage(img, 0, 0, width, height);
            ctx.restore();
            paintMaskStrokes(ctx, layer.mask && layer.mask.strokes);
        }
        state.contentCache.set(layer.id, { signature, canvas });
        return canvas;
    }

    function drawLayer(ctx, layer, zoom) {
        const content = layerContent(layer);
        const width = Math.max(1, layer.w);
        const height = Math.max(1, layer.h);
        ctx.save();
        ctx.globalAlpha = clamp(num(layer.opacity, 1), 0, 1);
        ctx.globalCompositeOperation = BLEND_OP[layer.blend] || 'source-over';
        const shadow = layer.shadow || {};
        if (num(shadow.x, 0) || num(shadow.y, 0) || num(shadow.blur, 0)) {
            ctx.shadowColor = shadow.color || '#000000';
            ctx.shadowBlur = num(shadow.blur, 0) * zoom;
            ctx.shadowOffsetX = num(shadow.x, 0) * zoom;
            ctx.shadowOffsetY = num(shadow.y, 0) * zoom;
        }
        ctx.translate((layer.x + width / 2) * zoom, (layer.y + height / 2) * zoom);
        if (num(layer.rotation, 0)) ctx.rotate((num(layer.rotation, 0) * Math.PI) / 180);
        ctx.drawImage(content, (-width * zoom) / 2, (-height * zoom) / 2, width * zoom, height * zoom);
        ctx.restore();
    }

    function drawSelection(ctx, zoom) {
        const layer = selectedLayer();
        if (!layer) return;
        const width = layer.w * zoom;
        const height = layer.h * zoom;
        ctx.save();
        ctx.translate((layer.x + layer.w / 2) * zoom, (layer.y + layer.h / 2) * zoom);
        if (num(layer.rotation, 0)) ctx.rotate((num(layer.rotation, 0) * Math.PI) / 180);
        ctx.strokeStyle = '#0ea5e9';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([6, 4]);
        ctx.strokeRect(-width / 2, -height / 2, width, height);
        ctx.setLineDash([]);
        ctx.restore();
    }

    // ---------------------------------------------------------------- 画布

    function renderCanvas() {
        if (!els) return;
        const zoom = clamp(num(state.zoom, 1), 0.05, 8);
        const width = Math.max(1, Math.round(state.canvas.width * zoom));
        const height = Math.max(1, Math.round(state.canvas.height * zoom));
        const canvas = els.canvas;
        if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
        }
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        canvas.classList.toggle('tool-erase', state.tool === 'erase');
        canvas.classList.toggle('tool-select', state.tool === 'select');
        const ctx = canvas.getContext('2d');
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = state.canvas.background || '#ffffff';
        ctx.fillRect(0, 0, width, height);
        state.layers.forEach((layer) => {
            if (layer.visible === false) return;
            if (layer.type === 'image' && !state.imageCache.has(layer.url)) {
                loadImage(layer.url).then(() => { invalidate(layer); renderCanvas(); }).catch(() => {});
                return;
            }
            drawLayer(ctx, layer, zoom);
        });
        drawSelection(ctx, zoom);
        updateFootInfo();
    }

    function updateFootInfo() {
        if (!els) return;
        const visible = state.layers.filter((layer) => layer.visible !== false).length;
        els.footInfo.textContent = t('i2p.footInfo', {
            v: visible,
            t: state.layers.length,
            w: state.canvas.width,
            h: state.canvas.height,
            z: Math.round(state.zoom * 100),
        });
        els.layerCount.textContent = String(state.layers.length);
    }

    function fitView() {
        if (!els || !state.canvas.width) return;
        const box = els.stageScroll.getBoundingClientRect();
        const available = { width: Math.max(120, box.width - 40), height: Math.max(120, box.height - 40) };
        const zoom = clamp(Math.min(available.width / state.canvas.width, available.height / state.canvas.height), 0.05, 4);
        state.zoom = Math.round(zoom * 100) / 100;
        syncCanvasPanel();
        renderCanvas();
    }

    function canvasPointFromEvent(event) {
        const rect = els.canvas.getBoundingClientRect();
        return {
            x: (event.clientX - rect.left) / state.zoom,
            y: (event.clientY - rect.top) / state.zoom,
        };
    }

    function hitTest(point) {
        for (const layer of topDownLayers()) {
            if (layer.visible === false) continue;
            let x = point.x - layer.x;
            let y = point.y - layer.y;
            if (num(layer.rotation, 0)) {
                const rad = (-num(layer.rotation, 0) * Math.PI) / 180;
                const cx = layer.w / 2;
                const cy = layer.h / 2;
                const dx = x - cx;
                const dy = y - cy;
                x = dx * Math.cos(rad) - dy * Math.sin(rad) + cx;
                y = dx * Math.sin(rad) + dy * Math.cos(rad) + cy;
            }
            if (x >= 0 && y >= 0 && x <= layer.w && y <= layer.h) return layer;
        }
        return null;
    }

    function localPoint(layer, point) {
        let x = point.x - layer.x;
        let y = point.y - layer.y;
        if (num(layer.rotation, 0)) {
            const rad = (-num(layer.rotation, 0) * Math.PI) / 180;
            const cx = layer.w / 2;
            const cy = layer.h / 2;
            const dx = x - cx;
            const dy = y - cy;
            x = dx * Math.cos(rad) - dy * Math.sin(rad) + cx;
            y = dx * Math.sin(rad) + dy * Math.cos(rad) + cy;
        }
        return [Math.round(x * 10) / 10, Math.round(y * 10) / 10];
    }

    // ---------------------------------------------------------------- 图层列表

    function layerThumbHtml(layer) {
        if (layer.type === 'text') {
            return '<i data-lucide="type"></i>';
        }
        return `<img src="${escapeAttr(layer.url)}" alt="" loading="lazy">`;
    }

    function renderLayerList() {
        if (!els) return;
        els.layerList.innerHTML = topDownLayers().map((layer) => {
            const meta = layer.type === 'text'
                ? `${escapeHtml(String(layer.text || '').slice(0, 14))}`
                : `${layer.w}×${layer.h}${layer.color ? ' · ' + escapeHtml(layer.color) : ''}`;
            return `<div class="i2p-layer${layer.id === state.selectedId ? ' selected' : ''}" data-layer-id="${escapeAttr(layer.id)}">
                <button type="button" class="i2p-layer-vis${layer.visible === false ? ' off' : ''}" data-layer-act="vis" title="${escapeAttr(t('i2p.actVis'))}"><i data-lucide="${layer.visible === false ? 'eye-off' : 'eye'}"></i></button>
                <div class="i2p-layer-thumb">${layerThumbHtml(layer)}</div>
                <div>
                    <div class="i2p-layer-name">${escapeHtml(layer.name)}</div>
                    <div class="i2p-layer-meta">${meta}</div>
                </div>
                <div class="i2p-layer-ops">
                    <button type="button" data-layer-act="up" title="${escapeAttr(t('i2p.actUp'))}"><i data-lucide="chevron-up"></i></button>
                    <button type="button" data-layer-act="down" title="${escapeAttr(t('i2p.actDown'))}"><i data-lucide="chevron-down"></i></button>
                    <button type="button" data-layer-act="rename" title="${escapeAttr(t('i2p.actRename'))}"><i data-lucide="pencil"></i></button>
                    <button type="button" data-layer-act="delete" title="${escapeAttr(t('i2p.actDelete'))}"><i data-lucide="trash-2"></i></button>
                </div>
            </div>`;
        }).join('');
        refreshIcons();
        updateFootInfo();
    }

    function selectLayer(id) {
        state.selectedId = id;
        renderLayerList();
        syncPanel();
        renderCanvas();
    }

    function addTextLayer(seed, options) {
        const layer = newTextLayer(seed);
        state.layers.push(layer);
        invalidate(layer);
        if (!options || options.select !== false) selectLayer(layer.id);
        else renderLayerList();
        renderCanvas();
        return layer;
    }

    // ---------------------------------------------------------------- 右侧面板

    function setSectionVisible() {
        const layer = selectedLayer();
        els.emptyHint.hidden = !!layer;
        ['colorSection', 'textSection', 'transformSection', 'effectSection'].forEach((key) => {
            els[key].hidden = !layer;
        });
        if (!layer) return;
        els.colorSection.hidden = layer.type !== 'image';
        els.textSection.hidden = layer.type !== 'text';
    }

    function syncCanvasPanel() {
        els.canvasW.value = state.canvas.width;
        els.canvasH.value = state.canvas.height;
        els.zoomInput.value = Math.round(state.zoom * 100) / 100;
        els.exportScale.value = String(state.exportScale);
    }

    function syncPanel() {
        syncCanvasPanel();
        setSectionVisible();
        const layer = selectedLayer();
        if (!layer) return;
        els.posX.value = Math.round(layer.x);
        els.posY.value = Math.round(layer.y);
        els.sizeW.value = Math.round(layer.w);
        els.sizeH.value = Math.round(layer.h);
        els.rotation.value = Math.round(layer.rotation);
        els.rotationLabel.textContent = `${Math.round(layer.rotation)}°`;
        els.blend.value = layer.blend;
        els.opacity.value = Math.round(layer.opacity * 100);
        els.opacityLabel.textContent = `${Math.round(layer.opacity * 100)}%`;
        const shadow = layer.shadow || {};
        els.shadowColor.value = shadow.color || '#000000';
        els.shadowX.value = Math.round(num(shadow.x, 0));
        els.shadowY.value = Math.round(num(shadow.y, 0));
        els.shadowBlur.value = Math.round(num(shadow.blur, 0));
        if (layer.type === 'image') {
            const adjust = layer.adjust || {};
            els.brightness.value = Math.round(num(adjust.brightness, 0));
            els.contrast.value = Math.round(num(adjust.contrast, 0));
            els.saturate.value = Math.round(num(adjust.saturate, 0));
            els.hue.value = Math.round(num(adjust.hue, 0));
            els.brightnessLabel.textContent = els.brightness.value;
            els.contrastLabel.textContent = els.contrast.value;
            els.saturateLabel.textContent = els.saturate.value;
            els.hueLabel.textContent = `${els.hue.value}°`;
        } else {
            els.textContent.value = layer.text || '';
            if (layer.font) els.fontFamily.value = layer.font;
            els.fontSize.value = Math.round(layer.fontSize);
            els.textColor.value = layer.color || '#111111';
            els.textAlign.value = layer.align || 'left';
            els.lineSpacing.value = layer.lineSpacing;
            els.letterSpacing.value = layer.letterSpacing;
            els.textMaxWidth.value = Math.round(num(layer.maxWidth, 0));
            els.fontHint.textContent = state.fontDefault
                ? t('i2p.fontHintFallback', { font: state.fontDefault })
                : t('i2p.fontHint');
        }
    }

    function mutate(mutator, options) {
        const layer = selectedLayer();
        if (!layer) return;
        mutator(layer);
        invalidate(layer);
        if (!options || options.remeasure !== false) {
            if (layer.type === 'text') measureTextLayer(layer);
        }
        if (!options || options.list !== false) renderLayerList();
        syncPanel();
        renderCanvas();
    }

    // ---------------------------------------------------------------- 分层

    async function detectRegions() {
        const img = await sourceImage();
        const dataUrl = imageToDataUrl(img, MAX_LLM_IMAGE_EDGE);
        const prompt = t('i2p.promptRegions', { w: state.canvas.width, h: state.canvas.height });
        const data = await postJson('/api/canvas-llm', {
            message: prompt,
            provider: state.llm.provider,
            model: state.llm.model,
            images: [dataUrl],
        });
        const parsed = parseJsonLoose(data && data.text);
        const regions = parsed && Array.isArray(parsed.regions) ? parsed.regions : [];
        if (!regions.length) throw new Error(t('i2p.errNoRegions'));
        return regions.slice(0, 8).map((region, index) => ({
            name: String(region.name || `${t('i2p.region')} ${index + 1}`).slice(0, 40),
            x: Math.round(num(region.x, 0)),
            y: Math.round(num(region.y, 0)),
            width: Math.max(1, Math.round(num(region.width, state.canvas.width))),
            height: Math.max(1, Math.round(num(region.height, state.canvas.height))),
        }));
    }

    async function runLayerize() {
        const body = {
            url: state.sourceUrl,
            name: state.sourceName,
            mode: state.mode,
            num_colors: state.numColors,
            method: 'quantize',
            project: state.project || '',
        };
        if (state.mode === 'regions') {
            setBusy(t('i2p.busyDetectRegions'));
            body.regions = await detectRegions();
            body.include_source = false;
        }
        setBusy(t('i2p.busyLayerize'));
        const result = await postJson('/api/image2psd/layerize', body);
        state.project = result.project;
        state.canvas = {
            width: num(result.canvas && result.canvas.width, 0),
            height: num(result.canvas && result.canvas.height, 0),
            background: '#ffffff',
        };
        state.layers = (result.layers || []).map((item, index) => newImageLayer(item, index));
        state.selectedId = state.layers.length ? state.layers[state.layers.length - 1].id : '';
        state.contentCache.clear();
        renderLayerList();
        syncPanel();
        renderCanvas();
        return result;
    }

    // ---------------------------------------------------------------- 提取文本

    async function extractText() {
        if (!state.layers.length) { toastSafe(t('i2p.needLayersFirst')); return; }
        const img = await sourceImage();
        const dataUrl = imageToDataUrl(img, MAX_LLM_IMAGE_EDGE);
        const prompt = t('i2p.promptTexts', { w: state.canvas.width, h: state.canvas.height });
        const data = await postJson('/api/canvas-llm', {
            message: prompt,
            provider: state.llm.provider,
            model: state.llm.model,
            images: [dataUrl],
        });
        const parsed = parseJsonLoose(data && data.text);
        const texts = parsed && Array.isArray(parsed.texts) ? parsed.texts : [];
        if (!texts.length) { toastSafe(t('i2p.noTextFound')); return; }

        const erase = !!(els.eraseOrigin && els.eraseOrigin.checked);
        const created = [];
        texts.forEach((item) => {
            const content = String(item.text || '').trim();
            if (!content) return;
            const height = Math.max(8, num(item.height, 48));
            const width = Math.max(8, num(item.width, 0));
            const layer = newTextLayer({
                name: `${t('i2p.textLayer')} ${created.length + 1}`,
                text: content,
                x: num(item.x, 0),
                y: num(item.y, 0),
                color: /^#[0-9a-f]{6}$/i.test(String(item.color || '')) ? item.color : '#111111',
                fontSize: Math.max(8, Math.round(height * 0.86)),
                align: ['left', 'center', 'right'].includes(item.align) ? item.align : 'left',
                maxWidth: width > 8 ? Math.round(width * 1.06) : 0,
            });
            state.layers.push(layer);
            invalidate(layer);
            created.push({ layer, box: { x: num(item.x, 0), y: num(item.y, 0), width, height } });
        });

        if (!created.length) { toastSafe(t('i2p.noUsableText')); return; }

        if (erase) {
            const pad = 4;
            state.layers.forEach((layer) => {
                if (layer.type !== 'image') return;
                created.forEach((item) => {
                    layer.mask.strokes.push({
                        type: 'rect',
                        x: Math.max(0, item.box.x - pad - layer.x),
                        y: Math.max(0, item.box.y - pad - layer.y),
                        w: item.box.width + pad * 2,
                        h: item.box.height + pad * 2,
                    });
                });
                invalidate(layer);
            });
        }

        selectLayer(created[0].layer.id);
        renderLayerList();
        renderCanvas();
        toastSafe(t('i2p.textExtracted', { n: created.length }));
    }

    // ---------------------------------------------------------------- 导出

    function buildSpec() {
        return state.layers
            .filter((layer) => layer.visible !== false)
            .map((layer) => {
                const base = {
                    type: layer.type,
                    name: layer.name,
                    x: num(layer.x, 0),
                    y: num(layer.y, 0),
                    rotation: num(layer.rotation, 0),
                    opacity: clamp(num(layer.opacity, 1), 0, 1),
                    blend: layer.blend || 'normal',
                    shadow: layer.shadow || {},
                };
                if (layer.type === 'text') {
                    return Object.assign(base, {
                        text: layer.text || '',
                        font: layer.font || '',
                        font_size: layer.fontSize,
                        color: layer.color || '#111111',
                        max_width: layer.maxWidth > 0 ? Math.round(layer.maxWidth) : null,
                        align: layer.align || 'left',
                        line_spacing: num(layer.lineSpacing, 1.25),
                        letter_spacing: num(layer.letterSpacing, 0),
                    });
                }
                return Object.assign(base, {
                    url: layer.url,
                    w: Math.round(layer.w),
                    h: Math.round(layer.h),
                    adjust: layer.adjust || {},
                    mask: layer.mask || { strokes: [] },
                });
            });
    }

    function exportBody() {
        return {
            project: state.project,
            canvas: {
                width: state.canvas.width,
                height: state.canvas.height,
                background: state.canvas.background || '#ffffff',
            },
            layers: buildSpec(),
        };
    }

    async function exportImage() {
        if (!state.layers.length) { toastSafe(t('i2p.noLayersToExport')); return; }
        setBusy(t('i2p.busyExportImage'));
        try {
            const response = await fetch('/api/image2psd/render', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(Object.assign(exportBody(), { scale: state.exportScale })),
            });
            if (!response.ok) throw new Error((await response.text()) || t('i2p.exportFailed'));
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            downloadUrl(url, `${state.project}-${state.exportScale}x.png`);
            setTimeout(() => URL.revokeObjectURL(url), 8000);
            toastSafe(t('i2p.imageExported', { scale: state.exportScale }));
        } catch (error) {
            toastSafe(t('i2p.imageExportFailed', { msg: error.message || error }));
        } finally {
            setBusy(null);
        }
    }

    async function exportPsd() {
        if (!state.layers.length) { toastSafe(t('i2p.noLayersToExport')); return; }
        setBusy(t('i2p.busyExportPsd'));
        try {
            const result = await postJson('/api/image2psd/export-psd', exportBody());
            downloadUrl(result.psd_url, `${state.project}.psd`);
            const warnings = Array.isArray(result.warnings) ? result.warnings : [];
            const codes = Array.isArray(result.warning_codes) ? result.warning_codes : [];
            const fallbacks = Array.isArray(result.font_fallbacks) ? result.font_fallbacks : [];
            if (codes.length) {
                toastSafe(t('i2p.psdExportedNote', {
                    n: result.layer_count,
                    note: warningText(codes[0], warnings[0]),
                }));
            } else {
                toastSafe(t('i2p.psdExported', { n: result.layer_count }));
            }
            if (fallbacks.length) {
                const item = fallbacks[0];
                els.fontHint.textContent = t('i2p.fontFallbackInfo', {
                    layer: item.layer,
                    requested: item.requested || t('i2p.unspecified'),
                    used: item.used,
                });
            }
        } catch (error) {
            toastSafe(t('i2p.psdExportFailed', { msg: error.message || error }));
        } finally {
            setBusy(null);
        }
    }

    // ---------------------------------------------------------------- 事件绑定

    function bindNumber(el, handler) {
        if (!el) return;
        el.addEventListener('change', () => handler(num(el.value, 0)));
        el.addEventListener('input', () => {
            if (el.value === '' || el.value === '-') return;
            handler(num(el.value, 0));
        });
    }

    function bindSlider(el, label, handler, suffix) {
        if (!el) return;
        el.addEventListener('input', () => {
            const value = num(el.value, 0);
            if (label) label.textContent = `${value}${suffix || ''}`;
            handler(value);
        });
    }

    function bindEvents() {
        els.closeBtn.addEventListener('click', close);
        els.modal.addEventListener('mousedown', (event) => { if (event.target === els.modal) close(); });
        document.addEventListener('keydown', onKeyDown);

        els.layerMode.addEventListener('change', () => { state.mode = els.layerMode.value; });
        els.numColors.addEventListener('change', () => {
            state.numColors = clamp(Math.round(num(els.numColors.value, 8)), 2, 32);
            els.numColors.value = state.numColors;
        });
        els.relayerBtn.addEventListener('click', async () => {
            if (state.busy) return;
            try {
                await runLayerize();
                fitView();
                toastSafe(t('i2p.relayered'));
            } catch (error) {
                toastSafe(t('i2p.layerizeFailed', { msg: error.message || error }));
            } finally {
                setBusy(null);
            }
        });
        els.addTextBtn.addEventListener('click', () => addTextLayer(null));

        els.layerList.addEventListener('click', (event) => {
            const row = event.target.closest('.i2p-layer');
            if (!row) return;
            const id = row.getAttribute('data-layer-id');
            const actionBtn = event.target.closest('[data-layer-act]');
            if (!actionBtn) { selectLayer(id); return; }
            event.stopPropagation();
            const action = actionBtn.getAttribute('data-layer-act');
            const layer = layerById(id);
            if (!layer) return;
            if (action === 'vis') { layer.visible = layer.visible === false; invalidate(layer); }
            else if (action === 'delete') {
                state.layers = state.layers.filter((item) => item.id !== id);
                state.contentCache.delete(id);
                if (state.selectedId === id) state.selectedId = state.layers.length ? state.layers[state.layers.length - 1].id : '';
            } else if (action === 'up' || action === 'down') {
                const index = state.layers.findIndex((item) => item.id === id);
                const target = action === 'up' ? index + 1 : index - 1;
                if (target >= 0 && target < state.layers.length) {
                    state.layers.splice(index, 1);
                    state.layers.splice(target, 0, layer);
                }
            } else if (action === 'rename') {
                const name = window.prompt(t('i2p.layerName'), layer.name);
                if (name != null && String(name).trim()) layer.name = String(name).trim().slice(0, 60);
            }
            renderLayerList();
            syncPanel();
            renderCanvas();
        });

        els.canvas.addEventListener('pointerdown', onCanvasPointerDown);
        els.canvas.addEventListener('pointermove', onCanvasPointerMove);
        els.canvas.addEventListener('pointerup', onCanvasPointerUp);
        els.canvas.addEventListener('pointercancel', onCanvasPointerUp);
        els.canvas.addEventListener('wheel', (event) => {
            if (!event.ctrlKey && !event.metaKey && !event.altKey) return;
            event.preventDefault();
            const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1;
            state.zoom = clamp(state.zoom * factor, 0.05, 8);
            syncCanvasPanel();
            renderCanvas();
        }, { passive: false });

        document.querySelectorAll('[data-i2p-tool]').forEach((button) => {
            button.addEventListener('click', () => {
                state.tool = button.getAttribute('data-i2p-tool');
                document.querySelectorAll('[data-i2p-tool]').forEach((item) => item.classList.toggle('active', item === button));
                renderCanvas();
            });
        });
        els.brushSize.addEventListener('input', () => {
            state.brushSize = num(els.brushSize.value, 48);
            els.brushLabel.textContent = String(state.brushSize);
        });
        els.maskClearBtn.addEventListener('click', () => {
            const layer = selectedLayer();
            if (!layer || layer.type !== 'image') { toastSafe(t('i2p.needImageLayer')); return; }
            layer.mask = { strokes: [] };
            invalidate(layer);
            renderCanvas();
            toastSafe(t('i2p.maskCleared'));
        });

        els.extractProvider.addEventListener('change', () => {
            state.llm.provider = els.extractProvider.value;
            state.llm.model = resolveChatModel('', state.llm.provider);
            els.extractModel.innerHTML = chatModelOptions(state.llm.model, state.llm.provider);
            state.llm.model = els.extractModel.value || state.llm.model;
        });
        els.extractModel.addEventListener('change', () => { state.llm.model = els.extractModel.value; });
        els.extractBtn.addEventListener('click', async () => {
            if (state.busy) return;
            els.extractBtn.disabled = true;
            els.extractBtn.textContent = t('i2p.busyExtracting');
            setBusy(t('i2p.busyDetectText'));
            try {
                await extractText();
            } catch (error) {
                toastSafe(t('i2p.extractFailed', { msg: error.message || error }));
            } finally {
                setBusy(null);
                els.extractBtn.disabled = false;
                els.extractBtn.textContent = t('i2p.extractRun');
            }
        });

        bindNumber(els.canvasW, (value) => { state.canvas.width = Math.max(1, Math.round(value)); syncCanvasPanel(); renderCanvas(); });
        bindNumber(els.canvasH, (value) => { state.canvas.height = Math.max(1, Math.round(value)); syncCanvasPanel(); renderCanvas(); });
        bindNumber(els.zoomInput, (value) => { state.zoom = clamp(value, 0.05, 8); syncCanvasPanel(); renderCanvas(); });
        els.exportScale.addEventListener('change', () => { state.exportScale = num(els.exportScale.value, 1); });
        els.zoom100.addEventListener('click', () => { state.zoom = 1; syncCanvasPanel(); renderCanvas(); });
        els.fitViewBtn.addEventListener('click', fitView);
        els.resetTransform.addEventListener('click', () => {
            mutate((layer) => {
                layer.x = 0; layer.y = 0;
                layer.rotation = 0;
                layer.opacity = 1;
                layer.blend = 'normal';
                layer.shadow = { color: '#000000', x: 0, y: 0, blur: 0 };
                if (layer.type === 'image') {
                    layer.w = state.canvas.width;
                    layer.h = state.canvas.height;
                    layer.adjust = { brightness: 0, contrast: 0, saturate: 0, hue: 0 };
                }
            });
        });

        bindNumber(els.posX, (value) => mutate((layer) => { layer.x = Math.round(value); }, { list: false, remeasure: false }));
        bindNumber(els.posY, (value) => mutate((layer) => { layer.y = Math.round(value); }, { list: false, remeasure: false }));
        bindNumber(els.sizeW, (value) => mutate((layer) => { layer.w = Math.max(1, Math.round(value)); }, { list: false }));
        bindNumber(els.sizeH, (value) => mutate((layer) => { layer.h = Math.max(1, Math.round(value)); }, { list: false }));
        bindSlider(els.rotation, els.rotationLabel, (value) => mutate((layer) => { layer.rotation = value; }, { list: false, remeasure: false }), '°');

        els.blend.addEventListener('change', () => mutate((layer) => { layer.blend = els.blend.value; }, { list: false, remeasure: false }));
        bindSlider(els.opacity, els.opacityLabel, (value) => mutate((layer) => { layer.opacity = value / 100; }, { list: false, remeasure: false }), '%');
        els.shadowColor.addEventListener('input', () => mutate((layer) => { layer.shadow.color = els.shadowColor.value; }, { list: false, remeasure: false }));
        bindNumber(els.shadowX, (value) => mutate((layer) => { layer.shadow.x = Math.round(value); }, { list: false, remeasure: false }));
        bindNumber(els.shadowY, (value) => mutate((layer) => { layer.shadow.y = Math.round(value); }, { list: false, remeasure: false }));
        bindNumber(els.shadowBlur, (value) => mutate((layer) => { layer.shadow.blur = Math.max(0, Math.round(value)); }, { list: false, remeasure: false }));

        bindSlider(els.brightness, els.brightnessLabel, (value) => mutate((layer) => { layer.adjust.brightness = value; }, { list: false, remeasure: false }));
        bindSlider(els.contrast, els.contrastLabel, (value) => mutate((layer) => { layer.adjust.contrast = value; }, { list: false, remeasure: false }));
        bindSlider(els.saturate, els.saturateLabel, (value) => mutate((layer) => { layer.adjust.saturate = value; }, { list: false, remeasure: false }));
        bindSlider(els.hue, els.hueLabel, (value) => mutate((layer) => { layer.adjust.hue = value; }, { list: false, remeasure: false }), '°');
        els.adjustReset.addEventListener('click', () => mutate((layer) => {
            layer.adjust = { brightness: 0, contrast: 0, saturate: 0, hue: 0 };
        }, { list: false, remeasure: false }));

        els.textContent.addEventListener('input', () => mutate((layer) => { layer.text = els.textContent.value; }));
        els.fontFamily.addEventListener('change', async () => {
            const family = els.fontFamily.value;
            await ensureFont(family);
            mutate((layer) => { layer.font = family; });
        });
        bindNumber(els.fontSize, (value) => mutate((layer) => { layer.fontSize = clamp(Math.round(value), 4, 800); }));
        bindNumber(els.lineSpacing, (value) => mutate((layer) => { layer.lineSpacing = clamp(value, 0.6, 3); }));
        bindNumber(els.letterSpacing, (value) => mutate((layer) => { layer.letterSpacing = clamp(value, -20, 80); }));
        els.textColor.addEventListener('input', () => mutate((layer) => { layer.color = els.textColor.value; }));
        els.textAlign.addEventListener('change', () => mutate((layer) => { layer.align = els.textAlign.value; }));
        bindNumber(els.textMaxWidth, (value) => mutate((layer) => { layer.maxWidth = Math.max(0, Math.round(value)); }));

        els.exportImageBtn.addEventListener('click', exportImage);
        els.exportPsdBtn.addEventListener('click', exportPsd);
    }

    function onKeyDown(event) {
        if (!state.open) return;
        if (event.key === 'Escape') { close(); return; }
        if (event.key === 'Delete' || event.key === 'Backspace') {
            const target = event.target;
            if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
            const layer = selectedLayer();
            if (!layer) return;
            event.preventDefault();
            state.layers = state.layers.filter((item) => item.id !== layer.id);
            state.contentCache.delete(layer.id);
            state.selectedId = state.layers.length ? state.layers[state.layers.length - 1].id : '';
            renderLayerList();
            syncPanel();
            renderCanvas();
        }
    }

    function onCanvasPointerDown(event) {
        if (!state.layers.length) return;
        const point = canvasPointFromEvent(event);
        const layer = selectedLayer();
        if (state.tool === 'erase') {
            if (!layer || layer.type !== 'image') { toastSafe(t('i2p.maskImageOnly')); return; }
            state.drawing = { layer, stroke: { size: state.brushSize, points: [localPoint(layer, point)] } };
            layer.mask.strokes.push(state.drawing.stroke);
            invalidate(layer);
            renderCanvas();
            els.canvas.setPointerCapture(event.pointerId);
            return;
        }
        const hit = hitTest(point);
        if (!hit) return;
        if (hit.id !== state.selectedId) selectLayer(hit.id);
        state.dragging = { layer: hit, start: point, originX: hit.x, originY: hit.y };
        els.canvas.setPointerCapture(event.pointerId);
    }

    function onCanvasPointerMove(event) {
        if (state.drawing) {
            const point = localPoint(state.drawing.layer, canvasPointFromEvent(event));
            const points = state.drawing.stroke.points;
            const last = points[points.length - 1];
            if (!last || Math.hypot(point[0] - last[0], point[1] - last[1]) > 1.5) {
                points.push(point);
                invalidate(state.drawing.layer);
                renderCanvas();
            }
            return;
        }
        if (state.dragging) {
            const point = canvasPointFromEvent(event);
            const layer = state.dragging.layer;
            layer.x = Math.round(state.dragging.originX + point.x - state.dragging.start.x);
            layer.y = Math.round(state.dragging.originY + point.y - state.dragging.start.y);
            invalidate(layer);
            renderCanvas();
            els.posX.value = Math.round(layer.x);
            els.posY.value = Math.round(layer.y);
        }
    }

    function onCanvasPointerUp(event) {
        if (state.drawing) {
            const layer = state.drawing.layer;
            state.drawing = null;
            invalidate(layer);
            renderCanvas();
        }
        if (state.dragging) {
            state.dragging = null;
            syncPanel();
        }
        try { els.canvas.releasePointerCapture(event.pointerId); } catch (error) { /* ignore */ }
    }

    // ---------------------------------------------------------------- 开关

    async function open(nodeId, imageIndex) {
        // 注意：nodes / apiProviders 这些是 smart-canvas.js 里用 let 声明的全局「词法」绑定，
        // 不会挂到 window 上（函数声明才会）。所以只能用裸标识符访问，不能写 window.nodes。
        const list = (typeof nodes !== 'undefined' && Array.isArray(nodes)) ? nodes : [];
        const node = list.find((item) => item.id === nodeId);
        const item = imageForDisplay(node && node.images ? node.images[imageIndex] : null);
        if (!item || !item.url) { toastSafe(t('i2p.noImageInNode')); return; }
        els = els || collectEls();
        resetState();
        state.open = true;
        state.nodeId = nodeId;
        state.imageIndex = imageIndex;
        state.sourceUrl = item.url;
        state.sourceName = item.name || (node && node.title) || 'image';
        els.modal.classList.add('open');
        els.layerList.innerHTML = '';
        syncCanvasPanel();
        refreshIcons();
        setBusy(t('i2p.busyPrepare'));
        try {
            await loadFontList();
            syncLlmSelects();
            if (els.fontFamily.options.length) {
                els.fontFamily.value = state.fontDefault || els.fontFamily.options[0].value;
            }
            // 源图只用于喂视觉模型，不阻塞打开流程；图层图各自加载。
            loadImage(state.sourceUrl).then((img) => { img.__loaded = true; }).catch(() => {});
            await runLayerize();
            fitView();
        } catch (error) {
            const message = (error && error.message) || String(error);
            const text = t('i2p.layerizeFailed', { msg: message });
            toastSafe(text);
            if (els.stageHint) els.stageHint.textContent = text;
        } finally {
            setBusy(null);
        }
        refreshEngineTag();
    }

    async function refreshEngineTag() {
        try {
            const info = await fetch('/api/image2psd/info').then((response) => response.json());
            const engine = info && info.engine ? info.engine : {};
            els.engineTag.textContent = t('i2p.engineTag', {
                name: engine.name || 'image2psd',
                font: info.default_font || '-',
            });
        } catch (error) {
            els.engineTag.textContent = 'image2psd';
        }
    }

    function resetState() {
        state.project = '';
        state.canvas = { width: 0, height: 0, background: '#ffffff' };
        state.layers = [];
        state.selectedId = '';
        state.zoom = 1;
        state.tool = 'select';
        state.drawing = null;
        state.dragging = null;
        state.contentCache.clear();
        state.imageCache.clear();
        state.imagePromises.clear();
        state.mode = els.layerMode.value || 'colors';
        state.numColors = clamp(Math.round(num(els.numColors.value, 8)), 2, 32);
        els.numColors.value = state.numColors;
        document.querySelectorAll('[data-i2p-tool]').forEach((button) => {
            button.classList.toggle('active', button.getAttribute('data-i2p-tool') === 'select');
        });
    }

    function close() {
        if (!els) return;
        state.open = false;
        state.drawing = null;
        state.dragging = null;
        els.modal.classList.remove('open');
    }

    function collectEls() {
        return {
            modal: q('i2pModal'),
            closeBtn: q('i2pCloseBtn'),
            engineTag: q('i2pEngineTag'),
            layerList: q('i2pLayerList'),
            layerCount: q('i2pLayerCount'),
            layerMode: q('i2pLayerMode'),
            numColors: q('i2pNumColors'),
            relayerBtn: q('i2pRelayerBtn'),
            addTextBtn: q('i2pAddTextBtn'),
            stageScroll: q('i2pStageScroll'),
            stageHint: q('i2pStageHint'),
            canvas: q('i2pCanvas'),
            brushSize: q('i2pBrushSize'),
            brushLabel: q('i2pBrushLabel'),
            maskClearBtn: q('i2pMaskClearBtn'),
            busy: q('i2pBusy'),
            busyText: q('i2pBusyText'),
            extractProvider: q('i2pExtractProvider'),
            extractModel: q('i2pExtractModel'),
            extractBtn: q('i2pExtractBtn'),
            eraseOrigin: q('i2pEraseOrigin'),
            canvasW: q('i2pCanvasW'),
            canvasH: q('i2pCanvasH'),
            zoomInput: q('i2pZoomInput'),
            exportScale: q('i2pExportScale'),
            zoom100: q('i2pZoom100'),
            resetTransform: q('i2pResetTransform'),
            fitViewBtn: q('i2pFitView'),
            transformSection: q('i2pTransformSection'),
            posX: q('i2pPosX'),
            posY: q('i2pPosY'),
            sizeW: q('i2pSizeW'),
            sizeH: q('i2pSizeH'),
            rotation: q('i2pRotation'),
            rotationLabel: q('i2pRotationLabel'),
            blend: q('i2pBlend'),
            opacity: q('i2pOpacity'),
            opacityLabel: q('i2pOpacityLabel'),
            shadowColor: q('i2pShadowColor'),
            shadowX: q('i2pShadowX'),
            shadowY: q('i2pShadowY'),
            shadowBlur: q('i2pShadowBlur'),
            colorSection: q('i2pColorSection'),
            brightness: q('i2pBrightness'),
            brightnessLabel: q('i2pBrightnessLabel'),
            contrast: q('i2pContrast'),
            contrastLabel: q('i2pContrastLabel'),
            saturate: q('i2pSaturate'),
            saturateLabel: q('i2pSaturateLabel'),
            hue: q('i2pHue'),
            hueLabel: q('i2pHueLabel'),
            adjustReset: q('i2pAdjustReset'),
            textSection: q('i2pTextSection'),
            textContent: q('i2pTextContent'),
            fontFamily: q('i2pFontFamily'),
            fontSize: q('i2pFontSize'),
            textColor: q('i2pTextColor'),
            textAlign: q('i2pTextAlign'),
            lineSpacing: q('i2pLineSpacing'),
            letterSpacing: q('i2pLetterSpacing'),
            textMaxWidth: q('i2pTextMaxWidth'),
            fontHint: q('i2pFontHint'),
            emptyHint: q('i2pEmptyHint'),
            effectSection: q('i2pEffectSection'),
            footInfo: q('i2pFootInfo'),
            exportImageBtn: q('i2pExportImageBtn'),
            exportPsdBtn: q('i2pExportPsdBtn'),
        };
    }

    /** 语言切换时重画「由 JS 生成」的文案；静态部分交给 i18n 的 apply()。 */
    function refreshI18n() {
        if (!els || !state.open) return;
        renderFontOptions();
        renderLayerList();
        syncPanel();
        refreshEngineTag();
        if (els.extractBtn) els.extractBtn.textContent = t('i2p.extractRun');
    }

    function init() {
        els = collectEls();
        if (!els.modal || !els.canvas) return;
        bindEvents();
        els.brushLabel.textContent = String(state.brushSize);
        window.addEventListener('studio-lang-change', refreshI18n);
    }

    window.openImage2PsdEditor = function (nodeId, imageIndex) {
        if (!els) init();
        open(nodeId, imageIndex || 0);
    };
    window.Image2PsdEditor = { open, close, state };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
