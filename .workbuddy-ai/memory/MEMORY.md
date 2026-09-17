# 项目长期记忆 · Infinite-Canvas

## 启动器（Lochou Launcher）架构与构建

- **前端源码不在本仓库**，位于 `E:\claude\skill\canvas-launcher`（Vite + React 19 + TS + Tailwind 4）。仓库内只有构建产物。
- **exe 不内嵌网页资源**：`launcher/Program.cs:455-466` 运行时按候选路径查找 `index.html`，**取第一个存在 `index.html` 的目录**：
  1. `root\dist\launcher`  2. `BaseDir\dist\launcher`  3. `root\launcher\dist`  4. `BaseDir\launcher\dist`  5. `root\dist`  6. `BaseDir\dist`
  因此**只改页面文案时无需重编 exe**，更新 `dist\launcher` 即可生效；重编 exe 只是为了产物一致。
- **`root` 的推导**（`ResolveProjectRoot()`）：`BaseDir` 有 `main.py` → 用 `BaseDir`；否则父目录有 `main.py` → 用父目录；再否则用 `BaseDir`。
  所以 exe 放在 `dist\` 里时 `root` 仍会上溯到项目根 —— 实测「根目录 exe」与「`dist\InfiniteCanvasLauncher.exe`」**都命中 `dist\launcher`**。
- **产物需同步到 3 处**：`launcher/dist`、`dist/launcher`、`dist`（`build-launcher.ps1` 负责）。另外 `launcher\bin\...\win-x64\dist` 是构建中间产物副本，从那里跑 exe 会读它，顺手同步一下可避免「同一个 exe 两份界面」。
- ⚠️ **`dist\dist\` 是垃圾**：不在候选列表里、永远不会被读取，是某次同步把 dist 复制进 dist 造成的嵌套（里面会残留旧 hash bundle）。见到就删，别再往 `dist` 里递归复制整个 dist。
- ⚠️ **清理旧 bundle 的脚本必须用 Windows 绝对路径**（`r'D:\...'`）。Bash 里 `$PWD` 是 POSIX 形式 `/d/工作/...`，交给原生 Windows 的 Python 会 `FileNotFoundError`，**删除会静默失败、旧包残留**。
- **发布脚本**：`build-launcher.ps1`（同步 web 资源 → `dotnet publish` → 把 exe 复制为根目录 `Lochou启动器.exe`）。注意脚本第 60 行解码出的产物名是 `一键启动.exe`。
- **本机 dotnet 注意事项**：
  - `dotnet restore` 会报 `Value cannot be null. (Parameter 'path1')`，用 `--no-restore` 绕过（脚本已内置重试）。
  - 脚本内 `Get-Command dotnet` 可能找不到，已加绝对路径兜底。

## 变更流程（页面文案类）

1. 改 `E:\claude\skill\canvas-launcher\src\...`
2. `npm run build`
3. 同步 `dist` 到上述 3 个位置（+ 可选的 `launcher\bin\...\win-x64\dist`），并清理旧 hash bundle（用 Windows 绝对路径的 Python 脚本）
4. 需要时重发 exe；验证可用本地静态服务 + Edge 无头截图
5. **收尾校验**：① 三处 `index.html` 都指向新 hash 且引用的文件存在；② 全项目 `index-<旧hash>.js` 残留计数为 0；③ 用脚本复刻 `ResolveProjectRoot()` + 候选列表，确认各 exe 位置实际命中的目录里就是新包；④ 新包里 grep 运行时常量（如 `` `${e.channel}::${e.name}` ``）确认改动真的进了包（压缩后标识符会被重命名，**别用源码里的变量名去 grep bundle**）。

## i18n 约定

- JS 生成的动态文案不会自动跟随语言，要监听 `studio-lang-change` 重画。
- `i18n-core` 的 `t()` **不做 `{name}` 插值**，带变量的文案要用编辑器里的 `t(key, params)`。
- 后端用户可见提示除中文原文外再回一份 `warning_codes`，前端按 code 取词条。

## 画布数据安全（硬规则）

- `data/canvases/<32hex>.json` **没有回收站、没有历史版本、没纳入 git**。删节点是硬删（`deleteNode()` → 整份覆盖 PUT），撤销栈只在内存里。已发生过一次「陈旧页面把 45 个节点整份抹掉」的事故。
- **写画布数据前**：先停服务 / 确认没有画布页面开着；备份 + `md5sum` 记哈希；测试一律用一次性画布（`POST /api/canvases` → 收尾 `DELETE .../purge`）。
- **收尾三件事**：删临时页 `static/__*.html`、purge 一次性画布、`md5sum -c` 比对真实画布哈希。命令中途报错时 `POST` 可能已建好画布，要按标题扫 `data/canvases/` 找孤儿。
- 详细流程与坑见技能 `infinite-canvas-verify`（`~/.workbuddy-ai/skills/infinite-canvas-verify`）。

## 画布保存接口语义（`PUT /api/canvases/{id}`）

- **全量替换**：`nodes` / `connections` / `logs` / `settings` 都是无条件覆盖。**不传就等于清空**（`canvas.js` 改标题/改图标曾因此清掉日志和设置）。任何调用方都必须带上完整的 `logs` / `settings`。
- **必须传 `base_updated_at`**。`update_canvas()` 有两道守卫：①旧 base → 409；②新增「静默丢节点」守卫——`base` 与当前不一致且本次写入会删掉服务端已有节点 → 409。前端收到 409 会按 id 取并集合并后用服务端 `updated_at` 重存，所以不会死循环。
- 只想改标题/图标时，另有专用轻量接口 `POST /api/canvases/{id}/meta`（不 bump `updated_at`、不碰 nodes/logs/settings）。当前 `canvas.js` 仍走 PUT 以保持列表排序行为。
- **`GET /api/canvases/{id}` 返回的是 `{"canvas": {...}}`**（包了一层），不是裸画布对象 —— 写脚本时别直接 `json["logs"]`。
- ⚠️ **想清空 `logs`（生成日志）**：必须走 PUT 并**全量回传** `title/icon/nodes/connections/viewport/settings`，只把 `logs` 置 `[]`，`base_updated_at` 用当前值。少传 `settings` 会把几十项设置一起清掉。
- ⚠️ **「旧页面把 logs 写回来」的坑**：`applyMergedServerCanvas()`（`smart-canvas.js:6122`）在 409 冲突时**只合并 nodes/connections，不合并 logs**，页面内存里的旧 logs 会原样保留；随后 `saveCanvas` 的重试（`:6837`）带上这些旧 logs（`:6812`），且 base 已被更新为服务端最新值 → **守卫放行、日志被写回**。所以**清完 logs 必须让用户刷新页面**。

## 前端调试要点

- `static/` 下全项目只有一份 `smart-canvas.html/js/css`，改这里即可。
- `canvas.html` **不带 `?id=` 会 `location.replace` 跳到选画布页**，测经典编辑器必须带 `?id=`。
- 画布节点根元素选择器是 `.image-node[data-id="<nodeId>"]`（不是 `[data-node-id]`）。提示词节点：`.prompt-node-card` / `.prompt-node-text` / `.prompt-llm-toggle`。
- 提示词节点高度由内容自适应（238 / 421 两档），不能按 `h` 字段排版。
- 图标名在 `static/vendor/js/lucide.js` 里存 PascalCase（`Clapperboard`），kebab-case 是运行时派生的，用 `includes('clapperboard')` 判存在会误报。
- 改 i18n 后必跑 `node static/js/i18n/validate-i18n.js`（有未解析 key 就 exit 1）。
- **静态资源缓存（重要）**：`/static` 是 `StaticFiles` 挂载，**默认无缓存头**；`no_cache_html_middleware` 原本只覆盖 `.html`。`static/js/i18n.js` 的 `VERSION` 曾写死 → 7 个子包 URL 永不变化 → 改了词条前端仍读缓存里的旧字典，**界面上直接显示 i18n key**。已修：中间件对 `.js`/`.css` 加 `no-cache, must-revalidate`；`i18n.js` 从自身 script 的 `?v=` 取版本并传给子包；`main.py` 的 `static_asset_mtime()` 让 `i18n.js` 的版本取 `static/js/i18n/*.js` 的最大 mtime。**验证前端改动务必用全新 `--user-data-dir`**，否则量到旧文件。

## 项目工作台布局与项目胶囊（canvas-list）

- `static/canvas-list.html` 是**父页面**（项目工作台），画布页 `canvas.html` 跑在 `#canvasFrame` iframe 里。
- **项目数据与增删改逻辑全在父页面** `static/js/canvas-list.js`（`/api/projects`）；iframe 内那颗「默认项目」胶囊只是画布自带的 `#smartTitle`，它**没有**项目数据。
- 所以「把项目功能收进胶囊」的正确做法是：**父页面自己渲染胶囊 + 浮窗**，把 iframe 内原胶囊用 `visibility:hidden` 隐藏。**不能用 `display:none`** —— 必须保留布局盒，父页面才能实测它的位置/尺寸来对齐。
- ⚠️ **父子缩放系数不同**：父页面 `.workspace` 用 `zoom`，iframe 内由 `theme.js` 自己算 `--studio-ui-scale` 用 `transform: scale()`。实测 1080×720 下 **父 0.680 / 内 0.902**。所以胶囊位置必须**实测 iframe 内 `#smartTitle` 的 `getBoundingClientRect()` 再反推**；硬编码 `top:22px` 会偏（实测落到 14.96px，而正确值 19.8px）。
- 胶囊与浮窗挂在 **`<body>` 下**（避开 `.workspace` 的 zoom，按真实视觉像素定位），通过 CSS 变量 `--pc-x / --pc-y / --pc-h / --pc-fs / --pc-padx` 接收实测值；`resize` 与 `studio-ui-scale-change` 时重测。
- 原左侧栏的 DOM id **全部保留复用**（`#projectList` / `#newProjectBtn` / `#trashEntry` / `#trashBadge` / `#trashPanel` …），只换容器，JS 逻辑无需重写。
- 点在 iframe 内的 `mousedown` **不会冒泡到父页面** → 收起浮窗的监听要**直接挂到 iframe 的 document 上**。
- 浮窗开合用 `.open` 类 + `visibility/opacity/transform` 过渡；**不要在 HTML 上写 `hidden` 属性**，会和过渡冲突。
- ⚠️ **浮窗必须绝对定位**：关闭态是 `visibility:hidden`（仍占位），若参与 flex 布局会把容器撑成 268×204，在胶囊右侧/下方形成**拦截鼠标事件的幽灵点击区**。用 `position:absolute; left:0; top:calc(100% + 6px)` 让容器尺寸收敛为胶囊本身（128×40）。
- 验证这类问题用 `elementFromPoint(x, y)`：取按钮右下方一点，确认命中的不是胶囊容器。
- **项目回收站（软删除，2026-09-17 新增）**：`DELETE /api/projects/{id}` 是**软删除**（打 `deleted_at`），并把它下画布一并打 `deleted_at`；`/api/projects` 列表已排除已删项目。恢复 `POST /api/projects/{id}/restore`、永久删除 `DELETE /api/projects/{id}/purge`、列表 `GET /api/projects/trash`（含 `retention_days:30`）。读取时 `cleanup_expired_project_trash()` 自动清除满 30 天的项目及其画布（镜像画布回收站的 `cleanup_expired_canvas_trash`）。前端回收站面板分「项目」「画布」两组卡片，角标 = 已删画布数 + 已删项目数之和。**默认项目不可删。**

## API Key 都存在于哪些地方（排查残留时的完整清单）

删通道 ≠ key 消失。逐处核对，别只看配置文件：

| 位置 | 说明 |
|---|---|
| `data/api_providers.json` | 通道配置。**不存 key**（只有 id/name/base_url/protocol/模型列表） |
| `API/.env` | key 真身。`API_PROVIDER_<ID大写>_KEY`；内置通道走固定名：`MODELSCOPE_API_KEY` / `ARK_API_KEY`(volcengine) / `RUNNINGHUB_API_KEY` / `COMFLY_API_KEY` |
| `*.exe.WebView2\EBWebView\Default\Web Data` | ⚠️ **Chromium 自动填充库（SQLite），会明文存表单里输入过的 API Key**。查 `autofill` / `autofill_edge_field_values` / `autofill_edge_field_client_info` 表（后者的 `label` 会写「API Key (Bearer Token)」） |
| `*.exe.WebView2\...\Code Cache` / `Cache_Data` | HTTP/JS 响应缓存，可能含 key 副本 |
| Local Storage / Session Storage / IndexedDB | 实测**干净**（启动器不往这里写 key），但仍应扫一遍 |
| `%LOCALAPPDATA%\InfiniteCanvasLauncher\preferences.json` | 只存窗口状态（如 `{"Action":"exit"}`），无 key |
| 用户级环境变量 | `GRSAI_API_KEY` / `MEDIA_API_KEY` 等，供 skill 用；Bash 工具环境读不到，要用 `[Environment]::GetEnvironmentVariable(name,'User')` |
| git 历史 | `API/.env` 已于 `18b4dcd` 取消跟踪 + 被 `.gitignore` 覆盖，但**历史里的删不掉**（`9bdb54c` 有 Grsai key，`74b5c8c`/`3041576` 有 ModelScope key）。仓库已推 GitHub → 泄露过的 key 只能轮换 |

- `CleanOrphanedEnvKeys()`（`Program.cs:1351`）删通道时**只把孤立 key 的值置空、不删整行**，所以 `API/.env` 会留下空壳行；且它只处理 `API_PROVIDER_` 前缀，**内置通道的 key（如 `MODELSCOPE_API_KEY`）不会被清**。
- 清理 WebView2 残留前先确认进程归属：`Get-CimInstance Win32_Process` 看 `--user-data-dir`（`wmic` 在本机被安全策略拉黑，别用）。在跑的 `msedgewebview2.exe` 往往属于别的程序（cc-switch / GameViewer）。

## 本地服务（main.py / uvicorn）

- 启动：`./python/python.exe main.py`（cwd = 项目根，端口 3000，**单进程 uvicorn，无 reload**）。
- ⚠️ **必须用「后台 Bash 任务」方式启动**，否则会在命令结束/脚本退出时被沙箱回收。用 `subprocess.Popen(..., creationflags=DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW)` 启动的进程实测会被清掉（`port 3000 reachable: False`）。
- 日志重定向到 `output/server.log`（`output/` 已 gitignore）。
- ⚠️ **启动时 `sync_static_html_versions()`（`main.py:1743`）会把 `static/*.html` 的 `?v=` 重写为 `<VERSION>.<资源mtime>` 并写回磁盘** → 每次重启服务都会让十几个 html 在 git 里变 modified（纯版本号差异）。
  **这是缓存破坏参数，必须保持最新，不要为了 git 干净去 `git checkout` 还原它** —— 2026-09-17 踩过：还原后 `canvas-list.js` 的 URL 没变，浏览器继续用缓存里的旧 JS，而新 CSS 已隐藏 iframe 内的原胶囊 → **两个胶囊都不显示，表现为「项目功能整个消失」**。
  正确做法：让它保持最新并**提交**（或接受工作区有这几个文件的 diff）。
- 本机 `curl` 不可用（RTK 代理会返回假 502），验证服务改用 Python `socket` 直发 HTTP 请求。

## 本机 git 注意事项

- **裸 `git` 不可用**（RTK hook 把它改写成 `rtk git`，而 rtk 解析不到）。真身：
  `C:/Users/Administrator/.workbuddy-ai/binaries/PortableGit/versions/1.2.0/mingw64/bin/git.exe`（2.55.0）。
- ⚠️ **绝不要用 `git rm <文件>` 删文件** —— 实测会让**整个父目录消失**。两次复现：
  `git rm packages/<19个whl>` 后 `packages/` 41 个文件全没了（`ls` 报 `No such file or directory`）；更早一次 `tests/` 同样整体消失。
  - **恢复**：`git checkout HEAD -- <目录>/` 可一次完整还原（文件都在 git 对象里，没丢）。
  - **正确做法**：用 Python `os.remove` / ctypes `DeleteFileW` 删文件，再 `git add -A <目录>/` 记录删除，然后提交。
- `git status --cached` 不是合法选项；看暂存清单用 `git diff --cached --name-status`。
- 离线包冗余判据：`pip install --no-index --find-links=packages --dry-run --ignore-installed -r requirements.txt`，
  末尾 `Would install ...` 列出的就是唯一会被选中的集合，不在其中的即冗余。
