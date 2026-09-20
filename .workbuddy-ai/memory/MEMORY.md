# 项目长期记忆 · Infinite-Canvas

> 索引式硬规则，细节下沉 `REFERENCE.md`（A 启动器 / B `.git` / C 胶囊 / D Key 残留 / E+G 磁盘清理 / F Grsai / H 3D 白模 / I 保存 / J 前端 / K 3D 界面 / L 服务与 git / M three.js）；过程见 `YYYY-MM-DD.md`。

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
- ⚠️ **绝不要 `git rm <文件>`**（实测整个父目录消失）；用 Python `os.remove` + `git add -A <目录>/`。
- 🚨 `.git` 曾于 2026-09-17 被递归搬进回收站（已还原）。防护：维护前 `git bundle create ../repo-<日期>.bundle --all`；瘦身在项目外副本做。
- ⚠️ **工具会话内 `git push` 会无限挂起** → 推送必须由老板本人终端执行（裸 `git` 不可用，真身在 PortableGit 1.2.0）。详见 B/L。
