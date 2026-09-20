# 项目长期记忆 · Infinite-Canvas

> 索引式硬规则，细节下沉 `REFERENCE.md`（A 启动器 / B `.git` / C 胶囊 / D Key 残留 / E+G 磁盘清理 / F Grsai / H 3D 白模 / I 保存 / J 前端 / K 3D 界面 / L 服务与 git / M three.js / N 发布打包与更新）；过程见 `YYYY-MM-DD.md`。

## 一、画布数据安全（最高优先级）

- `data/canvases/<32hex>.json` **无回收站、无历史版本、未纳入 git**；删节点是硬删（整份覆盖 PUT），撤销栈只在内存。
- 写画布前：停服务 / 确认无画布页开着 → 备份 + 记 `md5sum` → 测试一律用一次性画布（`POST /api/canvases` → 收尾 `DELETE .../purge`）。
- 收尾三件事：删 `static/__*.html`、purge 一次性画布、`md5sum -c` 比对哈希。⚠️ 哈希不符时**先排除「老板自己开着画布页」**（看 `assets/input/` 最近文件时间是否落在窗口内，3D 节点拖拽后会防抖截图），再判事故。流程见技能 `infinite-canvas-verify`。

## 二、保存接口（`PUT /api/canvases/{id}`）

- **全量替换**：`nodes`/`connections`/`logs`/`settings` 不传等于清空；**必须传 `base_updated_at`**，两道 409 守卫（旧 base / 静默丢节点）。`GET` 返回 `{"canvas": {...}}`；只改标题走 `POST .../meta`。
- ⚠️ 清 `logs` 要全量回传其余字段（少传 `settings` 会连设置一起清）；清完**必须让用户刷新页面**。详见 I。

## 三、前端要点

- 全项目只有一份 `static/smart-canvas.html/js/css`；`canvas.html` 不带 `?id=` 会跳选画布页。节点根元素 `.image-node[data-id]`。
- ⚠️ 非空节点的 `.node-head`/`.node-title`/`.node-hint` 被全局隐藏（CSS 574/575/702）→ **新增非图片节点类型必须显式重显**；`.image-node.selected:not(...)` 长 `:not` 链要补新型号。
- ⚠️ 节点拖拽靠 `beginNodeDrag` 的「排除选择器」判断，自吃鼠标事件的区域（如 3D 舞台）必须加进排除列表。
- 改 i18n 必跑 `validate-i18n.js`；`t()` **不做 `{name}` 插值**；动态文案要监听 `studio-lang-change` 重画。
- **验证前端改动务必用全新 `--user-data-dir`**；`render()` 无节流 → WebGL 查看器 DOM 必须复用。其余见 J。

## 四、模型下拉与 Grsai

- 下拉唯一数据源是 `chatApiProviders()`（`smart-canvas.js:3049`），**只认 `chat_models`**；3D 节点用 `chatModelOptions()`，不做视觉过滤。
- **Grsai 对话模型 14 个**（GPT 4 + Gemini 10），4 个 GPT 全支持读图；命名 = **OpenAI 官方模型 ID**，别自己编后缀。清单见 F。
- ⚠️ 探测三坑（F.4）：① 别按通用命名猜；② **禁止并发扫** → 串行 + 间隔 1~1.5s；③ **判「不存在」必须看到 `model not found`**。Grsai 无 `/v1/models` 只能手填。
- ⚠️ **画布下拉与启动器清单是两套，必须一致**：画布读 `data/api_providers.json` 的 `chat_models`；启动器「拉取并自动归类模型」读 **C# 硬编码** `GrsaiCuratedModels()`（`launcher/Program.cs:904`，Grsai 无 `/models` → 短路返回 `source="curated"`）。**两处不一致就是 bug 信号**。🚨 **不要因为一次 400 就把模型从清单剔掉** —— `a94a050`（2026-09-17）就这么干的，把 4 个 GPT 全剔了，导致启动器 3 天拉不到任何 GPT 对话模型。改清单前**必读同文件顶部注释**。见 F.6。
- ⚠️ 改 `launcher/Program.cs`（C#）**必须重编 exe**，同步 web 资源无效。exe 是压缩单文件包（`EnableCompressionInSingleFile=true`）→ **grep 搜不到字符串**，验证要查未压缩的 `launcher/bin/Release/net8.0-windows/win-x64/InfiniteCanvasLauncher.dll`，或解 bundle（字段区在 name 前 25 字节、type 1 字节）。构建命令见 F.6 / 技能 `launcher-web-sync`。

## 五、3D 预览节点（`smart-3d`）

- 上下游都只能接「快速生图」，与 prompt/loop/group 双向拒绝（`canAutoConnectDraggedNode()` + `connectInputNode()` **两处都要改**）。视觉风格见 H。
- **three.js 本地 r160（2023-12）、官方最新 r186（2026-09）**；升级清单见 M。
- 外框 / 标题栏 / 窄节点折叠 / 四态约定全部见 K。最易踩的两条：
  ① 🚨 **折叠阈值必须按实测文案宽度算**（`smart3DBarNeedWidth`），**不能写死像素** —— 英文比中文宽 20~30px；模型名完整显示需 select ≥104px（原生箭头占 19px，DOM 量不出截断）。
  ② ⚠️ 失败态必须加 `.is-error`，否则与中性空态同色；`.smart3d-nomodel` 是阻断性告警必须读得全（`nowrap`+`overflow:hidden` 会硬切，已改允许换行）。
- **取色方向随挂载面而定**：挂在**节点面板**（随主题变色）的**必须**按主题取色；挂在**恒白舞台**的（如 `.smart3d-placeholder.is-error`）**绝不能**按主题切。10px 小字按 AA **4.5:1**。基线表 K.9。
- **键盘焦点必须可见**（WCAG 2.4.7 AA）：`outline:none` 必配替代环；写法 `:focus` 给环 + `:focus:not(:focus-visible)` 撤环（只写后者在个别浏览器会退回「无指示」），色取 `var(--strong)`。见 K.10。

## 六、本地服务

- 启动 `./python/python.exe main.py`（端口 3000，**必须后台 Bash 任务**，日志 `output/server.log`；本机 `curl` 不可用，改用 Python `urllib`）。
- ⚠️ 启动会重写 `static/*.html` 的 `?v=`，**不要为 git 干净去还原**（否则浏览器用旧 JS，表现为「功能整个消失」）。
- **启动器 UI 资源候选链**（`launcher/Program.cs:456-466`，取第一个含 `index.html` 的目录）：`dist\launcher` → `BaseDir\dist\launcher` → `launcher\dist` → `BaseDir\launcher\dist` → `dist` → `BaseDir\dist`。**exe 不内嵌网页资源** → 只改前端无需重编 exe。根 `dist\` 可删（落到 `launcher\dist` 兜底，两处 7 文件 md5 一致），但**清完要重跑 `sync_verify.py sync` 恢复「四处一致」**。仓库里只有 `Lochou启动器.exe` 一个 exe（`一键启动.exe`/`dist\*.exe` 已不存在）。见 A / 技能 `launcher-web-sync`。

## 七、磁盘与 git 硬红线

- ⚠️ 本机「删除即入回收站」→ 清理不释放空间；**真正释放 = 清空回收站**，汇报成果必须同时给回收站占用。
- **清理走回收站**：`SHFileOperationW` + `FOF_ALLOWUNDO|FOF_NOCONFIRMATION|FOF_SILENT|FOF_NOERRORUI`，`pFrom` 用 NUL 分隔 / 双 NUL 结尾，每 40 个一批（返回码可能是 2，但**以「回收站增量 = 计划体积」为成功判据**）。删除前先跑安全白名单（路径必须在项目根下、不得命中 `python/ data/ static/ assets/ launcher/ output/ API/ .git/` 与项目根本身）。
- ⚠️ **`git add -A <被 gitignore 的目录>/...` 会报 ignored 而失败** → 删已跟踪文件用 **`git add -u`**（`output/` 被 gitignore，其下 4 个 `step*.png` 却是跟踪状态）。
- 2026-09-18 已执行零风险清理（363 路径 / 82.67 MB，commit `bbb7ab1`）；回收站 3121 条目 / 0.092 GB。清单与判据见 E+G。
- ⚠️ **判「密钥残留」不能只认 `sk-` 前缀** —— `.env` 类文件必须同时按 `NAME=VALUE` 逐行解析，否则会漏掉纯数字/异形 key（踩过：漏掉 11 位纯数字的真 key，得出「无残留」假结论）。**查 git 暴露面必须连标签一起查**（`git log <tag> --find-object=<blob>`），只看分支会低估。项目内已无真 key；唯一真 key 在 git 历史且**已公开**（Public 仓库 + 4 标签）→ 只能轮换。见 D.2。
- ⚠️ **绝不要用裸 `git rm <文件>` / `git rm -r`**（实测整个父目录连磁盘文件一起消失）；删文件用 Python `os.remove` + `git add -A <目录>/`。
- ✅ **只想「取消跟踪、保留磁盘文件」→ 用 `git rm --cached <文件>`**（index-only，2026-09-20 实测安全）。**必须先做父目录快照**（文件名 + 大小 + md5 全量），操作后逐项比对，一致才算过；不一致立刻 `git reset -- <文件>` 回滚。别用裸 `git rm` 试。
- 🚨 `.git` 曾于 2026-09-17 被递归搬进回收站（已还原）。防护：维护前 `git bundle create ../repo-<日期>.bundle --all`；瘦身在项目外副本做。
- ⚠️ **工具会话内 `git push` 会无限挂起** → 推送必须由老板本人终端执行（裸 `git` 不可用，真身在 PortableGit 1.2.0）。详见 B/L。

## 八、发布打包硬红线（2026-09-20）

- 🚨 **绝不能把工作目录整包压缩当发布包**。实测 `...Official.v1.1.zip`（798 MB）含 **528 MB `.git`**（含已公开的 Grsai 密钥 blob）+ 8 个作者画布 + `history.json` + **135.6 MB 作者个人图片**（`assets/output/online_*.png`）。→ 用户下载即得到作者私有数据，且更新功能会反复分发。
- ✅ **打包脚本 = `tools/release.py`**（子命令 `list` / `verify <zip|目录>` / `build`），**allow-list 复制 + deny-list 断言**。实测 **2011 文件 / 111.40 MB**（比预估的 150~200 MB 更好）。
  - **allow-list 是主防线**（只复制认识的程序路径），deny-list 只是兜底断言 —— deny-list 漏写一项就出事。
  - `build` 会 `compile()` 自检 `main.py`、断言 `REQUIRED` 齐全、校验 VERSION 格式；zip 条目时间固定 (2026,1,1) → 同内容可复现。
  - **默认不重编 exe**（否则每次打包都改动被跟踪的 `Lochou启动器.exe`）；仅当 `launcher/Program.cs` 比 exe 新时 WARN，加 `--build-exe` 才真编。
  - ⚠️ **有文件删除时不产出增量包**：增量包只表达「新增/修改」，表达不了「删除」→ 被删的旧 JS/CSS 会残留在用户目录与新版本混跑，**比不更新更危险**。
- ⚠️ **不能简单「用 git 树当更新包」**：`dist/`（启动器 UI 资源）虽是程序文件，却被 `.gitignore` 忽略、不在 git 里。
- 🚨 **混装的是 `data/` 不是 `assets/`**（2026-09-20 实测，推翻此前判断）：
  - `assets/` **100% 是用户数据**（`input/` + `output/`，`library/`、`uploads/` 为空），无任何程序资源 → **整目录排除本来就是对的，无需拆分**。
  - `data/` 13 个文件里 12 个是用户数据（`api_providers.json` 含密钥、`canvases/`、`chat_*.json`、`projects.json`、`prompt_libraries.json`、`media_previews/`），只有 `inspire_prompt_zh.json`（665 KB 灵感库中文词典）是随程序资源 → 只能**逐文件登记**（`DATA_SHIPPED_FILES`）。
  - 🚨 **`data/asset_library.json` 是素材库索引，绝不能随包分发**：用户新增素材后会被写回，覆盖安装会把它清回空骨架 → 素材文件还在 `assets/library/` 下、索引却没了，表现为**素材库凭空清空**。且 `load_asset_library()`（`main.py:7913-7917`）在文件缺失时会自建默认库并落盘，本就不需要随包提供。它同时也已**取消 git 跟踪**（`.gitignore` 的 `data/*` 本就忽略它，只有 `inspire_prompt_zh.json` 有 `!` 例外）—— 否则老板往素材库加东西，`git add -A` 就会把索引推到公开仓库。
- 🚨 **更新源曾指向别人的 fork**（已修）：`main.py:207-210` 原指 `raw.githubusercontent.com/mufanmu/Infinite-Canvas-agent`（实测是 `hero8152/Infinite-Canvas` 的 fork）→ 往自己仓库推版本软件内检测不到。2026-09-20 已改回 `HanaJhon/Infinite-Canvas`，**前端 `static/index.html` 另有 4 处硬编码 + `tools/` 3 处链接同样指向旧 fork，一并改了** —— 查更新源**必须连前端与 tools 一起查**，只改后端会漏。
- 🚨 **上游留了引流广告**：`static/update-notes.json` 原文「此项目已停更，全新版本请前往：DX-OS.com下载。」，会被 `read_local_update_notes()` 读取并经 `GITHUB_UPDATE_NOTES_URL` 拉取 → 用户点「检查更新」直接看到，等于把用户往上游引流。已改写。同类残留还有 `static/css/api-settings.css` 146 行 `.dx-os-banner` 死 CSS、孤儿 `static/images/dx-os-logo.svg`（均已删）。
- 网页端自更新**只覆盖 `main.py` / `VERSION` / `static/**`**（`update_allowed_file()`，`main.py:2479`）；启动器本体、`python/`、`tools/`、`CLI/` 都更新不到。`launcher/Program.cs` **零更新逻辑**（阶段 2 待做）。
- ⚠️ **发布流程必须老板本人执行**：工具会话内 `git push` / `gh` 会挂起。`release-summary.txt` 里已生成可直接执行的 `gh release create` 命令。
- 📌 `update.json` **必须作为 Release 资产上传** → 启动器从 `releases/latest/download/update.json` 取（该路径**不消耗** GitHub API 配额；实测 `api.github.com` 匿名调用已 403 rate limit）。
- 🚨 **启动器执行器不要用 `.cmd` / `.ps1`** —— 安装路径含中文，脚本极易因编码毁文件名。做法是 **exe 自身 `--apply-update` 模式**：启动器复制自己到 `<root>/data/_apply_update_<pid>.exe` 再派生该副本（在 `data/` 下 → 可覆盖安装目录里的正本 exe），自己退出；副本用完无法自删，由**下次启动的启动器**清理。⚠️ `Main(string[] args)` 里 `--apply-update` 分支**必须排在单实例互斥量之前**（否则旧启动器没退干净时会被挡下弹「已在运行中」）。
- **包内 `release-manifest.json`**（`tools/release.py` 生成的虚拟 zip 条目）= `{format, version, kind, prune_roots, files:{relpath: sha256}}`，是执行器**唯一权威来源**：按 `files` 的 sha256 决定备份哪些旧文件、按 `prune_roots`（由 `PROGRAM_DIRS` 派生）决定可删哪些残留。**不要再在 C# 里维护第二份目录清单**。
- ⚠️ **`UPDATE_START` 必须立刻返回**，下载放后台任务：前端 `callNative` 超时只有 **30s**，而完整包 111 MB 下载远超此值。进度/错误统一走 `UPDATE_PROGRESS` 推送（`download`/`verify`/`done`/`error`）。
- ⚠️ **执行器只支持完整包**（`kind=full`）；回滚只做到「旧文件备份到 `data/update_backups/`」，回滚 UI 未做（阶段 3）。
- 🚨 **验执行器必须复现生产路径**：把 exe **复制到 `<install>/data/_apply_update_<pid>.exe` 再用那个副本跑** `--apply-update`。拿仓库根的 exe 直接跑等于没测到「副本在 `data/` 下才能覆盖安装目录里的正本 exe」这条设计（2026-09-20 用真实 111 MB 包补测，15/15 通过）。
- ⚠️ **`TryDelete` 是静默的** → 删不掉就残留。已加 `CleanupStaleDownloads(root)`（启动时跑）：`*.part` 无条件删、`*.zip` 只清 **2 天前**的。🚨 **不能无条件删 `*.zip`** —— 用户点完更新又立刻重开启动器时执行器正在读那个包。
- ⚠️ **`HandleStartUpdateAsync` 开头有并发保险** `Program.IsUpdateInProgress(root)`：点完更新启动器 1.5s 内退出，用户马上重开再点一次会起**第二个执行器同时往同一目录解包 → 目录写坏**。判据是「正在运行的映像文件删不掉」。（跨类调用时该方法必须 `internal`，`private static` 报 CS0122。）
- ⚠️ **`dist/` 与 `launcher/dist` 被 `.gitignore` 忽略** → 启动器前端 bundle **不在 git 里**，只在发布包与工作区。仓库不自包含启动器界面（既有状态）；所以**发布包必须从工作区构建，不能从 git 树构建**。
- **启动器首页胶囊 = 更新入口**（2026-09-20，提交 `9e0b1e6`）：胶囊上的 `V` 号取自 C# 新增的 **`GET_VERSION`**（只读本地 `VERSION`，**不走网络**）；🚨 **不要拿 `UPDATE_CHECK` 当版本号来源**（要联网、25s 超时，断网就空）。启动时**静默**自动检查一次（不显示 loading、不把网络错误抛界面 —— 未发版前 `update.json` 必然 404），有新版本则胶囊右上角亮红点 + 胶囊换青色。
  - 🚨 **更新浮层必须挂在 hero 横幅外面**：横幅有 `overflow-hidden`，放里面会被裁掉；只能 `position:fixed` 挂 body 再用 `getBoundingClientRect()` 定位。
  - ⚠️ **Tailwind 4 的 `getComputedStyle().backgroundColor` 返回 `oklch()`/`oklab()` 而不是 `rgb()`** → 用 `rgba?\((\d+)` 正则判颜色一定漏判（实测 `bg-red-500` = `oklch(0.637 0.237 25.331)`）。量颜色要建 1×1 canvas 归一化成 rgb。
  - 更新区块抽成 `UpdateSection` 组件，首页浮层与设置弹窗**共用**，改一处即两处生效。
- 详见 N / `output/更新功能设计方案-2026-09-20.md`（§9 阶段 1、§10 阶段 2 执行结果）。

## 九、版本号与更新判定硬红线（2026-09-20）

- 🚨 **不要手改 `VERSION`** —— 升版本一律 `python tools/bump_version.py`（`--dry-run` / `--times N` / `--set X` / `--self-test`）。规则：三段式起于 `1.1.1`，**每多进一级就少一段**（段数 3→2→1，只减不增）：`1.1.9`→`1.2.0`、`1.9.9`→`2.0`、`9.9`→`10`、`10`→`11`（**首段满 10 不再进位**）。
- 🚨 **规则只有一份权威实现**：`tools/versioning.py`（Python）+ `launcher/VersionUtil.cs`（C#），自测向量共用 `tools/version_vectors.json`（32 条）。`main.py` 用 `version_rules()` 动态导入，取不到 tools/ 时退回「原样返回」。**改规则必须两边同改 + 跑两边向量**。
- 🚨 **非规范式会造成「更新死循环」**：`VERSION` 写 `1.1.10` 而 `update.json` 写 `1.2.0` → 用户装完新版、`VERSION` 仍是 `1.1.10` → 比对永远「有新版」→ 无限提示更新。所以 `release.py:read_version()` 读到非规范式会**自动折算并写回 `VERSION` 文件**（会改文件，记得一并提交）。
- 🚨 **跨「日期制遗留 ↔ 三段式」绝不能比数值**：`2026.08.30` 数值恒大于 `1.1.1`。判定必须**对称** —— 两边体系不同时**只认「远端是新方案、本地是旧日期」**这一个方向（`main.py` 的 `check_update()` 与 `Program.cs` 的 `HandleCheckUpdateAsync` **两处同步**）。日期制值**不参与进位换算**（`is_legacy_date()` 原样保留，否则 `2026.09.20` 会被算成 `2027.1`）。
- 🚨 **`dist/InfiniteCanvasLauncher.*` 与 `dist/Microsoft.Web.WebView2.*` 不得进包**：`dotnet publish -o dist` 会把 68.91 MB **重复 exe** + `.pdb` + 3 个 WebView2 `.xml` 写进根 `dist\`，而 `dist` 在 `PROGRAM_DIRS` 白名单里 → 包从 111 MB **虚涨到 175 MB**。已加进 `EXCLUDE_PREFIXES`。
- 🚨 **`read_notes_file()` 必须跳过收尾章节**（`升级`/`安装`/`下载`/`注意`/`说明`/`upgrade`/`install`/`download`/`notes`）：否则「升级方式」的正文会在更新面板里**冒充新功能**。只跳**认识的**标题，不认识的一律保留（宁可多显示也不悄悄漏真条目）。
- ⚠️ **同一文件的多处 `Edit` 绝不能并行** —— 并行写会互相覆盖。本次丢了 3 处（`main.py` 的 `version_rules()` 定义 → `/api/check-update` 500 `NameError`；`Program.cs` 的 `LocalVersion` 规范化；`release.py` 的用法注释）。改完必须用 `re.findall` 逐条断言「期望 N 处 / 期望 0 处」。
- ⚠️ **无头 Edge 探针：`--virtual-time-budget` 会被真实外链挂住**。启动器 `index.html` 的 `https://font.sec.miui.com/...` 字体请求让虚拟时钟迟迟不 settled → `--dump-dom` 在 React 回填数据前就结束，测到 `V—`（**而截图里明明正常**）。探针副本必须**剔除所有 `http(s)://` 外链**并把 budget 提到 40000。异步状态（`GET_VERSION`/`UPDATE_CHECK`）本就慢，别只靠加等待。**数据自相矛盾时先怀疑测量环境**。
