# 项目长期记忆 · Infinite-Canvas

> **索引式硬规则**，细节下沉 `REFERENCE.md`（A 启动器 / B `.git` / C 胶囊 / D Key 残留与扫描器 / E+G 磁盘清理 / F Grsai / H 3D 白模 / I 保存 / J 前端 / K 3D 界面 / L 服务与 git / M three.js / N 发布打包与更新）；过程见 `YYYY-MM-DD.md`。
> ⚠️ **写本文件/日志/注释/报告一律用掩码值**（如 `415***561`），**绝不写密钥明文** —— 本目录曾在公开仓库里带进过真密钥。

## 一、画布数据安全（最高优先级）

- `data/canvases/<32hex>.json` **无回收站、无历史版本、未纳入 git**；删节点是硬删（整份覆盖 PUT），撤销栈只在内存。
- 写画布前：停服务 / 确认无画布页开着 → 备份 + 记 `md5sum` → 测试一律用一次性画布（`POST /api/canvases` → 收尾 `DELETE .../purge`）。
- 收尾三件事：删 `static/__*.html`、purge 一次性画布、`md5sum -c` 比对哈希。⚠️ 哈希不符时**先排除「老板自己开着画布页」**（看 `assets/input/` 最近文件时间是否落在窗口内，3D 节点拖拽后会防抖截图），再判事故。见技能 `infinite-canvas-verify`。

## 二、保存接口（`PUT /api/canvases/{id}`）

- **全量替换**：`nodes`/`connections`/`logs`/`settings` 不传等于清空；**必须传 `base_updated_at`**，两道 409 守卫。`GET` 返回 `{"canvas": {...}}`；只改标题走 `POST .../meta`。
- ⚠️ 清 `logs` 要全量回传其余字段（少传 `settings` 会连设置一起清）；清完**必须让用户刷新页面**。详见 I。

## 三、前端要点

- 全项目只有一份 `static/smart-canvas.html/js/css`；`canvas.html` 不带 `?id=` 会跳选画布页。节点根元素 `.image-node[data-id]`。
- ⚠️ 非空节点的 `.node-head`/`.node-title`/`.node-hint` 被全局隐藏（CSS 574/575/702）→ **新增非图片节点类型必须显式重显**；`.image-node.selected:not(...)` 长 `:not` 链要补新型号。
- ⚠️ 节点拖拽靠 `beginNodeDrag` 的「排除选择器」判断，自吃鼠标事件的区域（如 3D 舞台）必须加进排除列表。
- 改 i18n 必跑 `validate-i18n.js`；`t()` **不做 `{name}` 插值**；动态文案要监听 `studio-lang-change` 重画。
- **验证前端改动务必用全新 `--user-data-dir`**；`render()` 无节流 → WebGL 查看器 DOM 必须复用。其余见 J。

## 四、模型下拉与 Grsai

- 下拉唯一数据源是 `chatApiProviders()`（`smart-canvas.js:3049`），**只认 `chat_models`**；3D 节点用 `chatModelOptions()`。
- **Grsai 对话模型 14 个**（GPT 4 + Gemini 10），4 个 GPT 全支持读图；命名 = **OpenAI 官方模型 ID**。清单见 F.1。
- ⚠️ 探测三坑（F.4）：① 别按通用命名猜；② **禁止并发扫** → 串行 + 间隔 1~1.5s；③ **判「不存在」必须看到 `model not found`**。Grsai 无 `/v1/models`。
- ⚠️ **画布下拉与启动器清单是两套，必须一致**：画布读 `data/api_providers.json` 的 `chat_models`；启动器读 **C# 硬编码** `GrsaiCuratedModels()`（`launcher/Program.cs:904`）。🚨 **不要因为一次 400 就把模型从清单剔掉** —— `a94a050` 把 4 个 GPT 全剔了，启动器 3 天拉不到任何 GPT 对话模型。改清单前**必读同文件顶部注释**。见 F.6。
- ⚠️ 改 `launcher/Program.cs`（C#）**必须重编 exe**。exe 是压缩单文件包 → **grep 搜不到字符串**，验证要查未压缩的 `.../InfiniteCanvasLauncher.dll`。见 F.6 / 技能 `launcher-web-sync`。

## 五、3D 预览节点（`smart-3d`）

- 上下游都只能接「快速生图」，与 prompt/loop/group 双向拒绝（`canAutoConnectDraggedNode()` + `connectInputNode()` **两处都要改**）。视觉风格见 H。
- **three.js 本地 r160（2023-12）、官方最新 r186（2026-09）**；升级清单见 M。
- 外框/标题栏/窄节点折叠/四态见 K。最易踩两条：
  ① 🚨 **折叠阈值必须按实测文案宽度算**（`smart3DBarNeedWidth`），**不能写死像素** —— 英文比中文宽 20~30px；模型名完整显示需 select ≥104px（原生箭头占 19px，DOM 量不出截断）。
  ② ⚠️ 失败态必须加 `.is-error`，否则与中性空态同色；`.smart3d-nomodel` 是阻断性告警必须读得全（`nowrap`+`overflow:hidden` 会硬切）。
- **取色方向随挂载面而定**：挂在**节点面板**（随主题变色）的**必须**按主题取色；挂在**恒白舞台**的**绝不能**按主题切。10px 小字按 AA **4.5:1**。基线表 K.9。
- **键盘焦点必须可见**（WCAG 2.4.7 AA）：`outline:none` 必配替代环；写法 `:focus` 给环 + `:focus:not(:focus-visible)` 撤环，色取 `var(--strong)`。见 K.10。

## 六、本地服务

- 启动 `./python/python.exe main.py`（端口 3000，**必须后台 Bash 任务**，日志 `output/server.log`；本机 `curl` 不可用，改用 Python `urllib`）。
- ⚠️ 启动会重写 `static/*.html` 的 `?v=`，**不要为 git 干净去还原**（否则浏览器用旧 JS，表现为「功能整个消失」）。
- **启动器 UI 资源候选链**（`launcher/Program.cs:456-466`，取第一个含 `index.html` 的目录）：`dist\launcher` → `BaseDir\dist\launcher` → `launcher\dist` → `BaseDir\launcher\dist` → `dist` → `BaseDir\dist`。**exe 不内嵌网页资源** → 只改前端无需重编 exe。根 `dist\` 可删，但**清完要重跑 `sync_verify.py sync` 恢复「四处一致」**。见 A / 技能 `launcher-web-sync`。

## 七、磁盘与 git 硬红线

- ⚠️ 本机「删除即入回收站」→ 清理不释放空间；**真正释放 = 清空回收站**，汇报成果必须同时给回收站占用。
- **清理走回收站**：`SHFileOperationW` + `FOF_ALLOWUNDO|FOF_NOCONFIRMATION|FOF_SILENT|FOF_NOERRORUI`，`pFrom` 用 NUL 分隔 / 双 NUL 结尾，每 40 个一批（**以「回收站增量 = 计划体积」为成功判据**）。删除前先跑安全白名单（路径须在项目根下、不得命中 `python/ data/ static/ assets/ launcher/ output/ API/ .git/` 与项目根本身）。
- ⚠️ **`git add -A <被 gitignore 的目录>/...` 会报 ignored 而失败** → 删已跟踪文件用 **`git add -u`**。
- ⚠️ **绝不要用裸 `git rm <文件>` / `git rm -r`**（实测整个父目录连磁盘文件一起消失）；删文件用 Python `os.remove` + `git add -A <目录>/`。
- ✅ **只想「取消跟踪、保留磁盘文件」→ `git rm --cached <文件>`**（index-only，实测安全）。**必须先做父目录快照**（文件名+大小+md5 全量），操作后逐项比对；不一致立刻 `git reset -- <文件>` 回滚。
- 🚨 `.git` 曾于 2026-09-17 被递归搬进回收站（已还原）。防护：维护前 `git bundle create ../repo-<日期>.bundle --all`。
- ⚠️ **工具会话内 `git push` 会无限挂起** → 推送必须由老板本人终端执行（裸 `git` 不可用，真身在 PortableGit 1.2.0）。详见 B/L。
- ⚠️ **同一文件的多处 `Edit` 绝不能并行**（会互相覆盖）→ 改完必须用 `re.findall` 断言「期望 N 处 / 期望 0 处」。

## 八、发布打包与更新（⚠️ 本章只留最高频规则，**动手前必读 N.1–N.12**）

- ✅ **打包脚本 = `tools/release.py`**（`list` / `verify <zip|目录>` / `build` / `build --build-exe`）。**allow-list 复制 + deny-list 断言**；`build` 会自检 `main.py` 语法、断言 `REQUIRED`、校验 VERSION。基线 **2019 文件 / 156.64 MB → 111.53 MB**。
- 🔒 **`build` 写完包自动跑 `tools/scan_release.py` 安全审计，不通过即中止**（**内容级**，补 `verify` 路径断言之不足 —— 见第十章）。
- 🚨 **绝不能把工作目录整包压缩当发布包**（历史事故：798 MB 包里含 **528 MB `.git`** + 8 个作者画布 + `history.json` + 135.6 MB 作者个人图片）。
- 🚨 **`assets/` 100% 是用户数据 → 整目录排除；`data/` 是混装目录** → 只有 `inspire_prompt_zh.json` 逐文件登记。🚨 **`data/asset_library.json` 绝不能随包分发**（覆盖安装会把它清回空骨架 → **素材库凭空清空**）。
- 🚨 **`dist/InfiniteCanvasLauncher.*` 与 `dist/Microsoft.Web.WebView2.*` 不得进包**（`dotnet publish -o dist` 会写进 68.91 MB **重复 exe** → 包虚涨到 175 MB）。
- ⚠️ **有文件删除时不产出增量包**；**执行器只支持 `kind=full`**；**不能「用 git 树当更新包」**（`dist/`、`launcher/dist` 被 gitignore）→ **发布包必须从工作区构建**。
- 📌 **包内 `release-manifest.json` 是执行器唯一权威来源**（`{format,version,kind,prune_roots,files:{relpath:sha256}}`）。**不要再在 C# 里维护第二份目录清单**。
- 🚨 **更新源必须指向 `HanaJhon/Infinite-Canvas`**，**前端 `static/index.html` + `tools/` 里也有硬编码链接** → 必须一起查。📌 `update.json` **必须作为 Release 资产上传**。⚠️ **发布必须老板本人执行**（工具会话内 `gh`/`git push` 挂起）。
- 🚨 **启动器执行器不要用 `.cmd`/`.ps1`**（路径含中文易毁文件名）→ 用 **exe 自身 `--apply-update` 模式**：复制自己到 `<root>/data/_apply_update_<pid>.exe` 再派生。⚠️ 该分支**必须排在单实例互斥量之前**；⚠️ **验执行器必须复现生产路径**。
- ⚠️ **`UPDATE_START` 必须立刻返回**（前端 `callNative` 超时仅 **30s**）；⚠️ **`TryDelete` 是静默的** → `CleanupStaleDownloads()`（`*.part` 无条件删、`*.zip` 只清 2 天前）；⚠️ **`HandleStartUpdateAsync` 有并发保险**（跨类调用须 `internal`），否则两个执行器同时解包 → **目录写坏**。
- **启动器首页胶囊 = 更新入口**：版本号取自 **`GET_VERSION`**（只读本地 `VERSION`，**不走网络**）；🚨 **不要拿 `UPDATE_CHECK` 当版本号来源**。⚠️ **更新浮层必须挂在 hero 横幅外面**（`overflow-hidden` 会裁掉）。⚠️ **Tailwind 4 的 `backgroundColor` 返回 `oklch()`** → `rgba?\((\d+)` 正则一定漏判。

## 九、版本号硬红线（⚠️ **动手前必读 N.11**）

- 🚨 **不要手改 `VERSION`** —— 一律 `python tools/bump_version.py`。规则：三段式起于 `1.1.1`，**每多进一级就少一段**（只减不增）：`1.1.9`→`1.2.0`、`1.9.9`→`2.0`、`9.9`→`10`、`10`→`11`（**首段满 10 不再进位**）。
- 🚨 **规则只有一份权威实现**：`tools/versioning.py` + `launcher/VersionUtil.cs`，向量共用 `tools/version_vectors.json`（32 条）。**改规则必须两边同改 + 跑两边向量**。
- 🚨 **非规范式会造成「更新死循环」** → `release.py:read_version()` 读到非规范式会**自动折算并写回 `VERSION`**（记得一并提交）。
- 🚨 **跨「日期制遗留 ↔ 三段式」绝不能比数值**（`2026.08.30` 恒大于 `1.1.1`）→ 只认「远端新方案、本地旧日期」这一个方向（`main.py:check_update()` 与 `Program.cs:HandleCheckUpdateAsync` **两处同步**）。
- 🚨 **`read_notes_file()` 必须跳过收尾章节**（升级/安装/下载/注意/说明/upgrade/install/download/notes），否则「升级方式」正文会**冒充新功能**。
- ⚠️ **无头 Edge 探针：`--virtual-time-budget` 会被真实外链挂住** → 探针副本必须**剔除所有 `http(s)://` 外链**并把 budget 提到 40000。**数据自相矛盾时先怀疑测量环境**。

## 十、密钥防泄漏（⚠️ **动手前必读 D.3**）

- **结论：`git` 里的泄露密钥清不掉，只能轮换。** 唯一真密钥 = `API_PROVIDER_GRSAI_KEY`（`API/.env`，11 位纯数字），提交 `9bdb54c`，**5 个标签全可达**；远端 **public**。**实测已失效**。清历史救不了：GitHub 不可达对象**仍可按 SHA 访问**；fork/clone 已持有；重写会改掉**全部提交 SHA**；`.git` **859 MB** 且 `filter-repo` 未装。
- **预防三件套**：`tools/scan_secrets.py`（`--staged`/`--tree`/`--history`/`--path`）+ `tools/git-hooks/pre-commit`（`git config core.hooksPath tools/git-hooks`）+ `.secretsignore`；`.gitignore` 已扩成 `.env`/`.env.*`/`*.env`。
- 🚨 **钩子脚本输出绝不能有非 ASCII 符号** —— `✔`/`✖` 在 **GBK 控制台**抛 `UnicodeEncodeError` → 钩子崩溃 → **所有提交被堵死**。→ ASCII 标记 + `reconfigure(errors="replace")` + **fail-open**。
- 🚨 **`ENV_LINE` 分隔符两侧只许 `[ \t]`，绝不能写 `\s`**（吃换行 → **假阴性**）。
- 🚨 **规则收紧后必须用「已知含密钥的样本」做正控** —— 否则会把「漏报」误当成「已干净」。
- 🚨 **`--history` 曾「从未真正扫描」**（路径带 ` @ <sha>` 过不了 `isfile` → 全被 `continue` → **永远报「干净」**）。**新增任何扫描来源都要拿已知阳性确认它真扫到了。**
- 🚨 **扫描器自己会成泄漏源**：① `ALLOW_FILE` 含 `scan_secrets.py` → **它从不扫自己**；② `ENV_LINE` 只在**行首**匹配 → 注释行里的 `KEY=数字` 看不见。**任何「豁免自身」的设计都会让校验器成为盲区。**
- 🚨 **绝不把密钥明文写进注释/文档/日志/报告** —— 我为讲清 bug 把密钥抄进注释，结果它随发布包分发、还被提交进公开仓库。**一律用掩码 `415***561`**。
- 🚨 **远端 4 个旧 Release 资产 = 比 git 历史更大的暴露面**（公开可下、合计 **3.49 GB**，两个内含**整个 `.git`**、四个都含**作者画布 + `history.json`**）。**已拍板全部删掉**（`output/删除旧Release-命令.sh`）。
- 📌 **查远端 Release 不必消耗 API 配额**：用 `releases/download/<tag>/<asset>` 的 **HEAD** 量体积、**Range** 读 zip 中央目录。⚠️ **ZIP 中央目录偏移**：压缩方式 **10**、压缩大小 **20**、未压缩大小 **24**、本地头偏移 **42**。
- ⚠️ `git cat-file --batch` 要处理 `<sha> missing`（2 字段）头（写成 `!= 3: break` 会**静默截断后续对象**）；`SENSITIVE` 里 `AUTH` 要写 `(?<!o)AUTH`。
- ⚠️ **`.workbuddy-ai/memory/` 6 个文件在公开仓库被跟踪**（`.gitignore` 未覆盖）→ 含内部推理与路径，已实际带进过密钥。**待老板决定是否加 `.gitignore` + `git rm --cached`**（做法见第七章）。
