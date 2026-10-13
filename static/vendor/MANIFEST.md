# Local Vendor Assets

This folder contains third-party assets mirrored locally so the app can load without CDN access.

## JavaScript

- `js/tailwindcss-cdn.js`: local mirror of `https://cdn.tailwindcss.com`
- `js/lucide.js`: local mirror of `https://unpkg.com/lucide@latest`
- `js/three-0.160.0.module.js`: local mirror of `https://unpkg.com/three@0.160.0/build/three.module.js`
- `js/three-gltf-loader.module.js`: local mirror of `https://unpkg.com/three@0.160.0/examples/jsm/loaders/GLTFLoader.js`（混元3D 节点的 GLB 加载；import 路径已改写为相对 `./three-0.160.0.module.js`，**必须从 `static/vendor/js/` 同目录解析**）
- `js/three-buffer-geometry-utils.module.js`: local mirror of `https://unpkg.com/three@0.160.0/examples/jsm/utils/BufferGeometryUtils.js`（GLTFLoader 的唯一依赖，同上）
- `js/photopea.min.js`: local mirror of `https://cdn.jsdelivr.net/npm/photopea@1.1.1/dist/photopea.min.js` (MIT, PhotopeaAPI by yikuansun). Promise wrapper around Photopea's Live Messaging API; the Photopea editor itself is loaded in an iframe from `https://www.photopea.com/#<config>`.
  - ⚠️ **不要**直接打开裸 `https://www.photopea.com/` —— 那是营销落地页，不是编辑器。只有带 `#` 的地址才会启动编辑器；本项目所有调用点都显式传 config（见 `static/js/smart-canvas.js` 的 `SPLIT_LAYERS_PEA_CONFIG` / `SPLIT_LAYERS_PEA_FALLBACK_CONFIG`）。
  - 本文件是上游镜像，**不要就地改**（改了就对不上 jsDelivr 的版本了）；需要换默认地址请从调用侧传 config。

## CSS

- `css/fonts.css`: local `@font-face` declarations used by all pages.

## Fonts

- `fonts/inter-5.ttf`: Inter 300
- `fonts/inter-4.ttf`: Inter 400
- `fonts/inter-3.ttf`: Inter 500
- `fonts/inter-2.ttf`: Inter 600
- `fonts/inter-1.ttf`: Inter 800
- `fonts/jetbrains-mono-7.ttf`: JetBrains Mono 400
- `fonts/jetbrains-mono-6.ttf`: JetBrains Mono 700
- `fonts/space-grotesk-9.ttf`: Space Grotesk 300
- `fonts/space-grotesk-10.ttf`: Space Grotesk 500
- `fonts/space-grotesk-8.ttf`: Space Grotesk 700
