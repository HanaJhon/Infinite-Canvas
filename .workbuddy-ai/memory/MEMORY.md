# 项目长期记忆 · Infinite-Canvas

> 只留长期有效的硬规则与结论；细节附录见同目录 `REFERENCE.md`，过程记录见 `YYYY-MM-DD.md`。

## 一、画布数据安全（最高优先级）

- `data/canvases/<32hex>.json` **没有回收站、没有历史版本、没纳入 git**。删节点是硬删（`deleteNode()` → 整份覆盖 PUT），撤销栈只在内存。已发生「陈旧页面把 45 个节点整份抹掉」事故。
- **写画布数据前**：先停服务 / 确认没有画布页面开着；备份 + `md5sum` 记哈希；测试一律用一次性画布（`POST /api/canvases` → 收尾 `DELETE .../purge`）。
- **收尾三件事**：删临时页 `static/__*.html`、purge 一次性画布、`md5sum -c` 比对真实画布哈希。命令中途报错时 `POST` 可能已建好画布，要按标题扫 `data/canvases/` 找孤儿。
- 详细流程见技能 `infinite-canvas-verify`。

## 二、保存接口语义（`PUT /api/canvases/{id}`）

- **全量替换**：`nodes`/`connections`/`logs`/`settings` 无条件覆盖，**不传等于清空**。
- **必须传 `base_updated_at`**。两道守卫：①旧 base → 409；②「静默丢节点」守卫（base 不一致且本次写入会删服务端已有节点）→ 409。前端收 409 会按 id 取并集合并后用服务端 `updated_at` 重存，不死循环。
- 只改标题/图标另有 `POST /api/canvases/{id}/meta`（不 bump `updated_at`）。
- **`GET /api/canvases/{id}` 返回 `{"canvas": {...}}`**（包了一层）。
- ⚠️ **清空 `logs`**：走 PUT 并**全量回传** `title/icon/nodes/connections/viewport/settings`，只把 `logs` 置 `[]`；少传 `settings` 会一起清掉几十项设置。
- ⚠️ **「旧页面把 logs 写回来」的坑**：`applyMergedServerCanvas()`（`smart-canvas.js:6122`）409 时只合并 nodes/connections、不合并 logs；随后 `saveCanvas` 重试（`:6837`）带旧 logs 且 base 已更新 → 守卫放行、日志被写回。**清完 logs 必须让用户刷新页面。**

## 三、前端要点

- `static/` 下全项目只有一份 `smart-canvas.html/js/css`。`canvas.html` **不带 `?id=` 会跳选画布页**。
- 节点根元素 `.image-node[data-id="<nodeId>"]`（不是 `[data-node-id]`）。提示词节点 `.prompt-node-card`/`.prompt-node-text`/`.prompt-llm-toggle`。
- lucide 名在 `static/vendor/js/lucide.js` 存 **PascalCase**，kebab-case 是运行时派生 → `includes('clapperboard')` 判存在会误报。
- 改 i18n 必跑 `node static/js/i18n/validate-i18n.js`（未解析 key 就 exit 1）。**约定**：JS 动态文案要监听 `studio-lang-change` 重画；`t()` **不做 `{name}` 插值**；后端提示除中文原文再回一份 `warning_codes`。
- **静态资源缓存**：`/static` 默认无缓存头，已加中间件对 `.js`/`.css` 加 `no-cache, must-revalidate`；`i18n.js` 从自身 script 的 `?v=` 取版本。**验证前端改动务必用全新 `--user-data-dir`**。
- 节点类型 `smart-image`（=「快速生图」）/`smart-group`/`smart-prompt`/`smart-loop`/`smart-minimax`/`smart-3d`（3D预览）/`smart-container`（legacy）。连接 `canvas.connections=[{from,to,kind}]`，`kind` ∈ `input`/`flow`；`node.inputNodeIds` 同步维护。
- ⚠️ **非空节点的 `.node-head`/`.node-title`/`.node-hint` 被全局隐藏**（CSS 574/575/702 行）。**新增非图片节点类型必须显式重新显示**，否则节点名、提示、拖动把手都看不到。同理 `.image-node.selected:not(...)` 长 `:not` 链要补新型号。
- ⚠️ **节点拖拽在 `beginNodeDrag`（`el.onmousedown`）里用「排除选择器」判断**。节点内任何需自吃鼠标事件的区域（如 3D 舞台）必须加进排除列表，否则会被节点拖拽抢走。
- **视觉识别管线已通、无需后端改动**：`POST /api/canvas-llm`（`main.py:3453`）的 `images` 支持 `/output/*.png`、`/assets/*.png`、http(s)、data URL，最多 8 张。
- **three.js 已内置**：`static/vendor/js/three-0.160.0.module.js`（r160）；`static/angle.html` 有现成 importmap 写法。
- **`render()`（`smart-canvas.js:9166`）是节点渲染主入口，147 处调用、无节流** → WebGL 查看器 DOM 必须复用（浏览器上限约 16 个上下文）。

## 四、模型下拉与 Grsai 的模型清单

- **模型下拉的唯一数据源是 `chatApiProviders()`（`smart-canvas.js:3049`）**，**只认 `chat_models`** —— `image_models`（生图）与 `video_models`（视频）永远不会出现在对话/视觉下拉里。3D 节点用 `chatModelOptions()`，**不做视觉过滤**。
- **Grsai（`https://grsai.dakka.com.cn`）对话模型 = GPT 4 个 + Gemini 10 个 = 14 个**；4 个 GPT（`gpt-6-astra`/`gpt-5.6-terra`/`gpt-5.6-sol`/`gpt-5.5`）**全部支持读图**。完整清单、已排除名字与探测方法见 `REFERENCE.md` F。
- ⚠️ **命名 = OpenAI 官方模型 ID，不是中转站别名**（GPT-5.6 官方三档 Sol/Terra/Luna；GPT-6 旗舰 `gpt-6-astra`）。**查名字要查官方型号，别自己编后缀。**
- ⚠️ **三个踩过的坑**：① 按通用命名试 `gpt-4o`/`gpt-5` 全 400 就误判「网关没有 GPT」，被老板**连续纠正两次**；② **别用高并发扫模型名**（限流会把已知可用的也扫成失败）→ **必须串行 + 间隔 1~1.5s**；③ **慢或偶发 400 ≠ 模型不存在；判「存在」看 200，判「不存在」必须看到 `model not found`**。
- **权威线索优先级**：内置预设 `RECOMMENDED_APIS`（`api-settings.js:163`）→ 官方型号命名（WebSearch）→ 串行探测。Grsai **没有** `/v1/models`（全 404），设置页「从上游拉取模型」对它无效，**只能手填**。
- 后端 `model_list_from_values()`（`main.py:959`）只去重 + `selected_model()` 校验，**不校验模型是否真实存在** → 加错名字不报错，只在调用时 400。
- **老板另有 Aizzz 网关**（`~/.codex/config.toml`）：`https://api.aizzz.xyz/v1`，有「请求体 ≥2000 token」门槛。**Grsai 已够用，此路仅备选。**

## 五、3D 预览节点（`smart-3d`）

- **定位**：上游只能是「快速生图」（`smart-image`），下游也只能是「快速生图」；与 prompt/loop/group 双向都拒绝（`canAutoConnectDraggedNode()` + `connectInputNode()` 双处硬校验，两处都要改）。
- **生成路线**：上游图片 → `POST /api/canvas-llm`（系统提示词 `SMART_3D_SYSTEM_PROMPT`，`smart-canvas.js:8909`）→ `smart3DParseSceneJson()`（含围栏与尾随逗号容错）→ `normalize3DScene()` → 存进 `node.scene3d`。7 种图元：box/sphere/cylinder/cone/torus/capsule/plane。
- **节点字段**：`scene3d`、`scene3dRaw`（截 20k）、`scene3dError`、`camera`（`{position,target,fov}`，跨刷新恢复）、`scene3dSnapshotUrl`、`model`/`provider`。截图 dataURL 只放内存 `smart3DSnapshotData`，**不进画布 JSON**。
- **FOV 滑块（2026-09-18 加上）**：`.smart3d-bar` 里 `[data-3d-fov]` 范围 20°–90° 步进 1，读数同步显示「XX° · XXmm」（35mm 全画幅等效：`f = 12 / tan(fov/2)`，由 `smart3DFocalMm()` 计算）。滑块 `input` 实时改 `viewer.camera.fov` + `updateProjectionMatrix()` + 脏标记；`change` 写 `node.camera.fov` + `scheduleSave()`（点 `change` 才落盘，避免拖动过程每次 200ms 触发 debounce 风暴）。`apply3DSceneToViewer` 优先用 `node.camera.fov`（覆盖场景默认）；`persist3DCamera` 把 `fov` 一并写入 `node.camera`（拖拽改角后也会落）。绑定事件里要 `stopPropagation` 防节点拖拽抢走；`el.querySelectorAll('[data-3d-provider],...')` 排除链要补 `[data-3d-fov]`。
- **查看器**：`smart3DViewers: Map<nodeId, viewer>`，动态 `import('/static/vendor/js/three-0.160.0.module.js')`，自写环绕（pointerdown/move/up + wheel，无 OrbitControls 依赖），rAF 脏标记渲染，`render()` 后由 `sync3DViewers()` 把 canvas 搬回新舞台。**上限 6 个同时存活**，节点删除即 `dispose3DViewer()`。
- **下游取图**：`outputImagesForNode()` 的 `smart-3d` 分支返回 `node.scene3dSnapshotUrl`；该 URL 由「场景建好后 + 拖拽/滚轮停下后（防抖 520ms）」调 `snapshot3DNode()` → `/api/ai/upload-base64` 刷新。截图 `preserveDrawingBuffer:true`。
- ⚠️ **三个已修的坑**：① 场景字段缺失会让 `spec.rotation[0]` 抛错并拖垮整个查看器 → 应用前必须 `normalize3DScene()` 规范化并写回节点；② `persist3DCamera()` 若直接读 `camera.position`，在环绕角刚改、渲染循环还没跑到时是旧值 → 落盘前先 `apply3DCamera(viewer)`；③ **验证探针里手动 `nodes.push()` 会被异步 `loadCanvas` 覆盖**（onload 后约 3s 才完成 fetch+赋值）→ 注入前必须 `await sleep(3000+)`，或用真实 `create3DNode()` + `scheduleSave()` 让节点走服务端重载。
- **视觉风格（2026-09-18 当前）**：**修改前的纯白 `#ffffff` 视口 + 灰白石膏白模 + 原工作室环境光**；查看器保留 PMREM `scene.environment`，使用 `HemisphereLight(0.34)` 和主/辅/轮廓三盏 `DirectionalLight(1.35/0.46/0.60)`，主光阴影半径为 `3`；3D 查看器隐藏 `GridHelper`，地面仅使用透明度 `0.20` 的 `ShadowMaterial` 接触阴影。所有图元统一使用灰白 `#d9dce1` 材质，场景 JSON 只保留几何与相机；FOV 滑块与相机姿态持久化保留。
- **无头 Edge 验证（2026-09-18 落地）**：必须 `--enable-unsafe-swiftshader --use-gl=angle --use-angle=swiftshader`（`--disable-gpu` 会让 WebGL 兜底直接失效，`hasScene` 假）。虚拟时间三分钟，跑 3D 节点必须用真实 `create3DNode()` 而非手动 push。完整探针写法见 `infinite-canvas-verify`。
- **节点外框布局约定（2026-09-18 定稿）**：① `.image-node.smart3d-node` 加 `padding-top:0`，让标题栏贴齐节点顶部（其他节点内缩 12px，3D 节点标题栏必须顶到边）；② **3D 节点必须跳过 `.floating-node-actions` 浮动删除按钮**（渲染模板里加 `&& !is3D`）——标题栏被专门显示后两者会重叠，浮动按钮落在覆盖层下方不可点击；③ 底部 `.node-hint` 用独立 flex 说明区（`min-height:24px`、`padding:5px 32px 5px 12px`，右侧 32px 是删除按钮安全区），文字必须与节点内控制条（`.smart3d-meta`/`.smart3d-select`/`.smart3d-run`/`.smart3d-fovval`）同规格：**`font-size:10px; line-height:normal`**（全局 `.node-hint` 是 10.5px/1.35，3D 节点需显式覆盖）。

## 六、本地服务（main.py / uvicorn）

- 启动：`./python/python.exe main.py`（cwd = 项目根，**端口 3000**，单进程、无 reload）。
- ⚠️ **必须用「后台 Bash 任务」方式启动**，否则命令结束会被沙箱回收。`subprocess.Popen(..., DETACHED_PROCESS|...)` 启动的实测被清掉。
- 日志重定向 `output/server.log`；末行 `ConnectionResetError [WinError 10054]` 是断连噪声。本机 `curl` 不可用（RTK 代理返回假 502），验证改用 Python `socket`/`urllib` 直发 HTTP。
- ⚠️ **启动时 `sync_static_html_versions()`（`main.py:1743`）把 `static/*.html` 的 `?v=` 重写为 `<VERSION>.<资源mtime>` 并写回磁盘** → 每次重启让十几个 html 变 modified。**这是缓存破坏参数，必须保持最新，不要为 git 干净去 `git checkout` 还原** —— 踩过：还原后浏览器继续用缓存旧 JS，而新 CSS 已隐藏 iframe 内原胶囊 → 两个胶囊都不显示，表现为「项目功能整个消失」。

## 七、磁盘与 git 硬红线

- ⚠️ **本机「删除即入回收站」→ 清理不释放磁盘空间**（`shutil.rmtree`、`SHFileOperationW`、`git gc` 删旧 pack 都只是搬进回收站）。**真正释放 = 清空回收站**，汇报成果必须同时给回收站占用。
- ⚠️ **绝不要用 `git rm <文件>`** —— 实测让**整个父目录消失**（`packages/` 41 文件、`tests/` 两次复现）。恢复用 `git checkout HEAD -- <目录>/`；**正确做法**是 Python `os.remove` / ctypes `DeleteFileW` 删文件再 `git add -A <目录>/`。
- 🚨 **`.git` 曾于 2026-09-17 被整个递归搬进回收站**（已完整还原，零丢失）。**已排除 gc 为元凶**；机制是回收站拦截层的递归整目录搬移，取证见 `REFERENCE.md` B。🛡️ **防护（按红线对待）**：① 维护前 `git bundle create ../repo-<日期>.bundle --all`；② 瘦身在**项目外副本**做，验证 `git log`/`git fsck` 后再替换；③ 优先 `git push` 当备份。
- **裸 `git` 不可用**（RTK hook 改写成 `rtk git`，rtk 解析不到）。真身：`C:/Users/Administrator/.workbuddy-ai/binaries/PortableGit/versions/1.2.0/mingw64/bin/git.exe`。`git status --cached` 非法，看暂存用 `git diff --cached --name-status`。
- 其余磁盘/清理细节（`core.quotepath` 坑、判孤儿的权威引用源、**不要动的文件清单**、API Key 残留排查）见 `REFERENCE.md` D/E/G。
