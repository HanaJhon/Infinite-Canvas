// 校验「生图产物一律直出原图、不走缩略图代理」这条规则（node tools/check_media_preview.js）
// 直接从真实源码里抽出预览 URL 函数来求值，避免测试自己抄一遍规则。
const fs = require('fs');

function extract(file, startMark, endMark) {
  const src = fs.readFileSync(file, 'utf8');
  const a = src.indexOf(startMark);
  const b = src.indexOf(endMark, a + startMark.length);
  if (a < 0 || b < 0) throw new Error(`无法在 ${file} 里定位 ${startMark}`);
  return src.slice(a, b);
}

const ident = (x) => (typeof x === 'object' && x ? x.url : x);

// --- 画布页（static/js/smart-canvas.js）
const smartCode = extract('static/js/smart-canvas.js', 'function smartMediaPreviewUrl(', '\nfunction smartPreviewImgHtml(');
const smartMediaPreviewUrl = new Function('smartOriginalMediaUrl', 'displayMediaUrl', `${smartCode}\nreturn smartMediaPreviewUrl;`)(ident, ident);

// --- 经典编辑器页（static/js/canvas.js）
const canvasCode = extract('static/js/canvas.js', 'function canvasMediaPreviewUrl(', '\nfunction canvasPreviewImgHtml(');
const canvasMediaPreviewUrl = new Function('canvasOriginalMediaUrl', 'canvasDisplayMediaUrl', `${canvasCode}\nreturn canvasMediaPreviewUrl;`)(ident, ident);

const isProxy = (u) => u.startsWith('/api/media-preview?');
const cases = [];
const check = (name, actual, expect) => cases.push({ name, actual, expect, ok: actual === expect });

for (const [label, fn] of [['smart', smartMediaPreviewUrl], ['canvas', canvasMediaPreviewUrl]]) {
  // 生图产物：原图直出
  check(`${label} png 直出`, fn('/output/abc.png', 512), '/output/abc.png');
  check(`${label} jpg 直出`, fn('/output/abc.jpg', 512), '/output/abc.jpg');
  check(`${label} webp 直出`, fn('/output/abc.webp', 512), '/output/abc.webp');
  check(`${label} gif 直出`, fn('/output/abc.gif', 512), '/output/abc.gif');
  // 视频仍要代理（代理负责抽封面帧，直接给 <img> 打 mp4 会白）
  check(`${label} mp4 走代理`, isProxy(fn('/output/clip.mp4', 512)), true);
  // 素材库缩略图保留代理
  check(`${label} assets 走代理`, isProxy(fn('/assets/library/a.png', 512)), true);
  // 外部 / data URI 不碰
  check(`${label} 外链原样`, fn('https://cdn.example.com/a.png', 512), 'https://cdn.example.com/a.png');
  check(`${label} data 原样`, fn('data:image/png;base64,AAA', 512), 'data:image/png;base64,AAA');
}

const bad = cases.filter((c) => !c.ok);
bad.forEach((c) => console.log(`FAIL ${c.name}: got ${c.actual} expect ${c.expect}`));
console.log(bad.length ? `MEDIA_PREVIEW_CHECK=FAIL (${bad.length}/${cases.length})` : `MEDIA_PREVIEW_CHECK=OK (${cases.length} 项)`);
process.exit(bad.length ? 1 : 0);
