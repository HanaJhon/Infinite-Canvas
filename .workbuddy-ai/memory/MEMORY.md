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
- **发布脚本**：`build-launcher.ps1`（同步 web 资源 → `dotnet publish` → 把 exe 复制为根目录 `Lochou启动器.exe`）。
  - ⚠️ **脚本第 60 行用「UTF-8 字节数组」硬编码产物名**（原作者用意：绕开 PowerShell 5.1 在无 BOM 的 UTF-8 脚本下按 GBK 解码导致中文乱码）。2026-09-17 已把字节数组从 `一键启动.exe` 改为 `Lochou启动器.exe`。
  - ⚠️ **改产物名必须改字节数组**，明文 grep「一键启动」**0 命中**（这正是「看起来无人引用」的假象来源）。判据：搜字节模式 `0xE4, 0xB8, 0x80`，或直接 `Parser::ParseFile` 求值验证。
  - 当前字节序列（= `Lochou启动器.exe`）：`0x4C,0x6F,0x63,0x68,0x6F,0x75,0xE5,0x90,0xAF,0xE5,0x8A,0xA8,0xE5,0x99,0xA8,0x2E,0x65,0x78,0x65`
- **根目录 exe 只保留 `Lochou启动器.exe`**（2026-09-17 删除同内容副本 `一键启动.exe`，省 68.9 MB —— 两者 md5 曾完全相同 `590fbcab...`）。`Lochou启动器.exe.WebView2/`（41 MB / 337 文件）是它的 WebView2 运行时用户数据，**保留**；`一键启动.exe.WebView2/` 已随之清除。
- **本机 dotnet 注意事项（2026-09-17 已定位根因）**：
  - `dotnet` 报 `Value cannot be null. (Parameter 'path1')` 的真根因是 **WorkBuddy 工具会话缺失 17 个标准 Windows 环境变量**（`APPDATA`/`ProgramFiles(x86)`/`ProgramData` 等），不是中文路径、不是 SDK 10.0.301 的 bug。
  - ⚠️ **`--no-restore` 绕过无效**（已实测推翻）：缺变量时它照样失败，报 `NETSDK1060: 读取资产文件时出错: 加载锁定文件 ...project.assets.json 时出现错误: Value cannot be null. (Parameter 'path1')`。
  - **唯一有效手段**：用 Python 补齐 17 个环境变量再 exec dotnet —— 脚本 `~/.workbuddy-ai/skills/launcher-web-sync/scripts/dotnet_env.py`。实测 `restore` 1.8s / `build -c Release` 13.5s / `publish -r win-x64 --self-contained -p:PublishSingleFile=true` 12s，全部 EXIT=0（仅剩 1 个无害的 `MSB3277` WindowsBase 版本统一警告）。
  - 老板自己的 PowerShell 窗口变量齐全，直接跑 `build-launcher.ps1` 正常；该问题**只影响工具会话内调用**。
  - 脚本内 `Get-Command dotnet` 可能找不到，已加绝对路径兜底。
- ⚠️ **删 `launcher/obj/` 会让构建链"变冷"**（但不会真的坏）：重建需先 `restore`（补齐环境变量后约 2s）。`launcher/obj/` 只有 10MB，**建议保留**以免每次构建都要 restore。

## 清理与磁盘空间（2026-09-17 实证）

- ⚠️ **本机「删除即入回收站」→ 清理操作不释放磁盘空间。** 所有删除（含 `git gc` 删旧 pack、`shutil.rmtree`、`SHFileOperationW`）都只是把数据搬进回收站，**磁盘可用空间分毫未变**。
- **汇报清理成果时必须同时给出回收站占用**，否则会误导。实证：A/B/C 三轮清理约 830 MB + `.git` 的 gc 省 639 MB，回收站却累积到 **9.31 GB**，磁盘几乎没变化。
- **真正释放空间 = 清空回收站**。清空前先核对里面有没有还需保留的东西（实证发现里面有 `Infinite-Canvas-for-lochou-Launcher-Beta.V0.1.zip` 1.48 GB 发布包）。
- 统计回收站占用用 `win-recyclebin-forensics` skill 的「统计回收站占用」小节；**注意 `$I` 残留而 `$R` 已消失的条目不占空间，必须过滤**。

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

## 磁盘占用与可精简项（2026-09-17 全量审计）

- 项目总计约 **1.85 GB**。**零风险可删（约 419 MB，均已被 .gitignore）**：`一键启动.exe.WebView2/`(197MB)、`launcher/bin/`(162MB)、`Lochou启动器.exe.WebView2/`(44MB)、`launcher/obj/`(10MB)、`__pycache__/`。前三者都是运行时/构建产物，会重建。**`output/backup/` 必须保留**（画布备份）。
- ✅ **A 类已于 2026-09-17 执行完毕**：`418.7 MB / 1664 文件`，零失败。项目体积 **1853.2 MB → 1434.4 MB**（5241 文件）。实际删除清单：`一键启动.exe.WebView2/`(197.2MB/602)、`Lochou启动器.exe.WebView2/`(44.0MB/533)、`launcher/bin/`(162.3MB/479)、`launcher/obj/`(10.1MB/28)、`__pycache__/`(1.9MB/3)、`debug-inspire-promptwall.png`、`debug-inspire-seaart.png`、`output/` 下 17 个验证截图。
  - **保留**：`output/backup/`、`output/server.log`、`output/recovered-prompts-7bc696dc.md`、`output/restored-prompt-nodes.md`、`output/step1~4_*.png`（这几个被 git 跟踪）。
  - 核验：35 项关键文件全部存在、6 个画布文件完好、服务 4 个端点均 200。
  - ⚠️ **收尾插曲**：删 `launcher/obj/` 后我以为构建链断了（`--no-restore` 报 `NETSDK1060 path1`），追查后发现是**工具会话缺环境变量**这个既有问题，与删除无关。验证构建已用 `dotnet_env.py` 跑通 `build` + `publish`。**`launcher/obj/` 已由验证构建重新生成（10MB）并保留**，`launcher/bin/` 已再次删除。
- ⚠️ **两个 exe 都被 git 跟踪且在 HEAD 里**：`Lochou启动器.exe` 与 `一键启动.exe` 各 68.89MB、**md5 完全相同**（`dist/InfiniteCanvasLauncher.exe` 也是同一份）。`.gitignore` 没有 exe 规则，所以 `git status` 不会提示。文档指向 `Lochou启动器.exe`，而 `build-launcher.ps1:60` 生成的是 `一键启动.exe`。
- `.git` pack 432 MB = 4 个 exe(≈275MB) + 曾被跟踪的 WebView2 缓存(≈130MB) + numpy whl(12MB)；另有 207 MB 松散对象（`git gc` 可回收）。真正瘦身需重写历史，风险高。
- `assets/input/` 里**同一张图被反复复制**（上传/导入无去重）：11 份 17.1MB、6 份 2.8MB、16 份 0.2MB… 去重可省约 200 MB。`assets/library/`、`assets/uploads/` 为空，`data/asset_library.json` 三个分类 items 全为 `[]`。
- **不要动**：`get-pip.py`（被 `Program.cs` 引用）、`inspire_image_dims.json`（被 `main.py` 引用）、`history.json`（应用读，且是 assets 的主要引用者）、`python/`、`packages/`、`static/`、`data/`、`workflows/`、`tools/`、`CLI/.../*-arm64-*.tgz`（installer 按架构选）。
- ⚠️ **`git ls-files` 默认 `core.quotepath=true`，中文文件名会被转义成八进制**，直接拿去 `os.path.getsize` 会静默跳过 → 曾因此漏掉两个 68.9MB 的 exe，误判成"未被跟踪"。**必须加 `-c core.quotepath=false` 并用 `-z` 分隔**。
- 判定静态资源是否孤儿，**不能只看"文件名是否出现在源码里"** —— `assets/`、`data/media_previews/` 可能被运行时动态拼接访问。运行时生成的资源（`ai_ref_*` / `online_*`）名字是随机 hash，**权威引用源是数据文件**（画布 `nodes` / `logs` / `history.json`）。
- ✅ **assets 孤儿已于 2026-09-17 权威判定**（全项目 131 个文本文件全文匹配文件名，排除 `assets/` 自身、`python/`、`.git/`、`dist/`、`launcher/`、`packages/`）：**被引用 17 个 / 135.8 MB**（唯一引用源 = `history.json`），**无引用 66 个 / 342.8 MB**（其中 11 组重复可省 248.1 MB）。
  - **关键安全检查**：`output/backup/` 两个备份引用的恰好是同一批 17 个，**与孤儿完全不相交** → 删孤儿不影响备份可恢复性。
  - **没有目录枚举**（已实证）：全项目 `os.listdir`/`os.scandir`/`os.walk` 的目标里**没有** `assets/input`；`local_media_file_by_basename()`（`main.py:7728`）是按文件名查不枚举；`scan_shared_tree()`（`main.py:8426`）扫的是用户配置的共享文件夹。→ **界面不存在会列出这些文件的「素材库/上传历史」**。
- ⚠️ **`/api/ai/upload`（`main.py:12580`）与 `/api/ai/upload-base64`（`main.py:12629`）不做内容去重**：固定用 `ai_ref_{uuid4().hex[:12]}{ext}` 生成新名，每次上传必落一份新文件。实测同一张 17.5 MB PNG 在 2 分钟内被上传 11 次（占 192.5 MB），一张 226 KB webp 横跨三天上传 11 次。**这是 assets 无限膨胀的根因**；永久修复 = 上传时算 content md5，命中已有文件则复用其 URL。

## 本机 git 注意事项

- **裸 `git` 不可用**（RTK hook 把它改写成 `rtk git`，而 rtk 解析不到）。真身：
  `C:/Users/Administrator/.workbuddy-ai/binaries/PortableGit/versions/1.2.0/mingw64/bin/git.exe`（2.55.0）。
- 🚨 **本项目 `.git` 于 2026-09-17 18:32 被整个递归搬进回收站（已完整还原，零丢失）。根因已取证，详见 `output/git-gc事故根因取证报告-2026-09-17.md`。**
  - **精确时间线**：`git gc` 跑 18:32:39.87→18:32:55.68（15.8s，exit 0）；破坏窗口 18:32:41.287→18:32:55.025（13.7s，1167.8 MB，25 条回收站记录）——**完全落在 gc 窗口内**。
  - **`git gc` 不是元凶（已实证）**：`__git_gc.py` 源码已从会话记录还原，只有「量大小 → `git gc` → 量大小」，无删除代码。
    同机同仓库复现：完整 `.git` 副本在工作区**内**跑 gc → `exit 0` / **65.2 秒** / `.git` 41 文件 528.8 MB / `rev-parse HEAD`=`5454e649` / `fsck rc=0` **全部正常**。
    ⚠️ **成功的一次要 65 秒，事故那次只跑 15.8 秒 → 事故的 gc 是被中途掏空并提前终止的。**
  - **⚠️ 已推翻上一轮的结论**：上一轮写的「触发器是『在项目工作区内』」**是错的**。微型仓库（工作区内/外）+ 完整仓库（工作区内/外）四种组合跑 gc **全部正常**。工作区位置不是触发器。
  - **已排除**：`sandbox-cli-gc`（PID 33044，全程 `无需删除`，且循环在 18:31:52→18:38:22 卡顿 6.5 分钟正好覆盖事故窗口）、WorkBuddy 检查点/回滚子系统（`changes-index` 中 `.git` 仅命中 `.gitignore`）、`main.py`（无任何触碰 `.git` 的代码、无后台线程、server.log 在 18:32:41 无请求）。
  - **已确认机制**：本机有「删除即入回收站」拦截层（`genie-trash/win32-x64.exe` + `GENIE_TRASH_DIR`；`cli/vendor/shim/safe-bin/*` + `safe-delete-common.sh`；`BASH_ENV` 把 `rm/unlink/rmdir` 定义成函数注入每个非交互 bash；`sitecustomize.py`/`node-safe-delete-shim.cjs` 分别拦 Python/Node 的 fs 删除；`safe-delete-bulk-guard.cjs` 阈值 50 要二次确认）。
    事故那次是 **4 条整目录搬移**（`multi-pack-index` → `objects/pack`(1007MB) → `objects`(217MB) → `.git`(30 文件)），自底向上、父目录在子内容搬空后才搬走 —— 这是**递归移入回收站**的实现特征，**git 不会这么干**。
    `$I` 体积证明快照发生在 gc 中途：`objects/pack` 里同时有新 pack + 旧 pack（`-d` 未跑），`objects` 里还有全部 1538 个松散对象（`prune-packed` 未跑）。
  - **未闭合**：触发那次整目录搬移的**具体进程/代码路径无法从现有日志唯一确定**（CLI 主日志事故窗口只有模型流式 + Edit + TaskOutput，无第二条 Bash 命令；沙箱日志只有连接抖动）。已诚实标注在报告第五节。
  - **救援**：`.git` 全在 `D:\$Recycle.Bin\<SID>\$R*` 里可还原。需取四部分：`.git\objects` + `.git\objects\pack` + **路径正好等于 `.git` 的目录快照**（含 HEAD/config/packed-refs/index/logs/hooks）+ `.git\refs\**`。⚠️ 用 `os.walk` 遍历回收站（`os.listdir` 在 SID 目录上 PermissionError）；`$I` 删除时间戳是 **FILETIME(UTC)，要 +8h 才是北京时间**（上一轮就是因为漏了 +8h 把 18:32 误读成 10:32）。完整 `$I` 格式见 `~/.workbuddy-ai/MEMORY.md`。
  - 🛡️ **防护（低概率高后果，按红线对待）**：① 维护前先 `git bundle create ../repo-<日期>.bundle --all`；② 要瘦身就在**项目外副本**上 gc，验证 `git log`/`git fsck` 后再替换回来；③ 优先用 `git push` 当备份。现成的干净副本：`D:\工作\无限画布\_InfiniteCanvas-git-backup-20260917`（41 文件 / 528.8 MB，已验证可用）——换上去可省 639 MB。
- ⚠️ **绝不要用 `git rm <文件>` 删文件** —— 实测会让**整个父目录消失**。两次复现：
  `git rm packages/<19个whl>` 后 `packages/` 41 个文件全没了（`ls` 报 `No such file or directory`）；更早一次 `tests/` 同样整体消失。
  - **恢复**：`git checkout HEAD -- <目录>/` 可一次完整还原（文件都在 git 对象里，没丢）。
  - **正确做法**：用 Python `os.remove` / ctypes `DeleteFileW` 删文件，再 `git add -A <目录>/` 记录删除，然后提交。
- `git status --cached` 不是合法选项；看暂存清单用 `git diff --cached --name-status`。
- 离线包冗余判据：`pip install --no-index --find-links=packages --dry-run --ignore-installed -r requirements.txt`，
  末尾 `Would install ...` 列出的就是唯一会被选中的集合，不在其中的即冗余。
