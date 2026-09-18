# 项目参考细节 · Infinite-Canvas

> `MEMORY.md` 的细节附录。MEMORY.md 只留硬规则与结论；这里放可查证的参数、路径、代码位置。
> **按需读取，不自动注入。**

## A. 启动器（Lochou Launcher）细节

- 前端源码：`E:\claude\skill\canvas-launcher`（Vite + React 19 + TS + Tailwind 4）；仓库内只有构建产物。
- `launcher/Program.cs:455-466` 按候选路径找 `index.html`，取第一个命中：
  `root\dist\launcher` → `BaseDir\dist\launcher` → `root\launcher\dist` → `BaseDir\launcher\dist` → `root\dist` → `BaseDir\dist`。
  → 只改页面文案无需重编 exe。
- `ResolveProjectRoot()`：`BaseDir` 有 `main.py` 用它；否则父目录有 `main.py` 用父目录；再否则 `BaseDir`。实测「根目录 exe」与「`dist\InfiniteCanvasLauncher.exe`」都命中 `dist\launcher`。
- 产物同步 3 处：`launcher/dist`、`dist/launcher`、`dist`（`build-launcher.ps1` 负责）；`launcher\bin\...\win-x64\dist` 是中间副本，顺手同步避免「同一 exe 两份界面」。
- ⚠️ `dist\dist\` 是垃圾（不在候选列表、永不被读，旧 hash bundle 残留）→ 见到就删，别再递归复制整个 dist。
- ⚠️ 清理旧 bundle 的脚本必须用 Windows 绝对路径（`r'D:\...'`）。Bash 的 `$PWD` 是 POSIX 形式，交给原生 Windows Python 会 `FileNotFoundError`，删除静默失败。
- `build-launcher.ps1`：同步 web 资源 → `dotnet publish` → 复制 exe 为根目录 `Lochou启动器.exe`。
  - ⚠️ 第 60 行用「UTF-8 字节数组」硬编码产物名（绕开 PowerShell 5.1 无 BOM 时按 GBK 解码中文乱码）。改名必须改字节数组；明文 grep「一键启动」0 命中是「看起来无人引用」的假象来源。判据：搜字节 `0xE4,0xB8,0x80` 或 `Parser::ParseFile` 求值。
  - 当前字节序列（= `Lochou启动器.exe`）：
    `0x4C,0x6F,0x63,0x68,0x6F,0x75,0xE5,0x90,0xAF,0xE5,0x8A,0xA8,0xE5,0x99,0xA8,0x2E,0x65,0x78,0x65`
- 根目录只保留 `Lochou启动器.exe`（2026-09-17 删同内容副本 `一键启动.exe`，省 68.9 MB）。`Lochou启动器.exe.WebView2/` 是它的 WebView2 用户数据，保留。
- ⚠️ 删 `launcher/obj/` 让构建链变冷（不会坏，重建需先 restore 约 2s）；仅 10 MB，建议保留。
- 变更流程（页面文案）：改源码 → `npm run build` → 同步 dist 3 处 + 清旧 hash bundle → 需要时重发 exe。
  **收尾校验**：① 三处 `index.html` 指向新 hash 且文件存在；② 旧 `index-<hash>.js` 残留为 0；③ 复刻 `ResolveProjectRoot()`+候选列表确认各 exe 位置命中的是新包；④ 新包 grep **运行时常量**确认改动进包（压缩后标识符会重命名，别用源码变量名 grep bundle）。

## B. `.git` 事故取证（2026-09-17）

完整报告：`output/git-gc事故根因取证报告-2026-09-17.md`。

- `.git` 于 18:32 被整个递归搬进回收站（已完整还原，零丢失）。
- `git gc` 跑 18:32:39.87→18:32:55.68（15.8s，exit 0）；破坏窗口 18:32:41.3→18:32:55.0（13.7s / 1167.8 MB / 25 条记录）**完全落在 gc 窗口内**。
- **gc 不是元凶**：`__git_gc.py` 已还原，只有「量大小 → gc → 量大小」。同机完整副本在工作区内跑 gc：exit 0 / **65.2 秒** / 正常。成功要 65 秒、事故只 15.8 秒 → 那次 gc 被中途掏空并提前终止。
- **已推翻**「工作区位置是触发器」（四种组合全部正常）。
- **已确认机制**：本机「删除即入回收站」拦截层（`genie-trash` + `GENIE_TRASH_DIR`、`BASH_ENV` 注入 `rm/unlink/rmdir` 函数、`sitecustomize.py` 拦 Python、`node-safe-delete-shim.cjs` 拦 Node）。事故是 **4 条整目录搬移**（`multi-pack-index` → `objects/pack` → `objects` → `.git`），自底向上、父目录在子内容搬空后才搬走 —— **递归移入回收站的特征，git 不会这么干**。触发进程**未闭合**（报告第五节已诚实标注）。

## C. 项目工作台与项目胶囊（canvas-list）细节

- `static/canvas-list.html` 是**父页面**（项目工作台），画布页跑在 `#canvasFrame` iframe 里。
- **项目数据与增删改全在父页面** `static/js/canvas-list.js`（`/api/projects`）；iframe 内那颗「默认项目」胶囊只是画布自带的 `#smartTitle`，**没有**项目数据。
- 正确做法：**父页面自己渲染胶囊 + 浮窗**，iframe 内原胶囊 `visibility:hidden` 隐藏（**不能 `display:none`**，要保留布局盒供实测位置）。
- ⚠️ **父子缩放不同**：父 `.workspace` 用 `zoom`，iframe 内由 `theme.js` 算 `--studio-ui-scale` 用 `transform: scale()`。实测 1080×720 下 **父 0.680 / 内 0.902** → 胶囊位置必须**实测 iframe 内 `#smartTitle` 的 `getBoundingClientRect()` 再反推**（硬编码 `top:22px` 实测偏到 14.96px，正确 19.8px）。
- 胶囊与浮窗挂在 **`<body>` 下**（避开 zoom），用 `--pc-x/--pc-y/--pc-h/--pc-fs/--pc-padx` 接收实测值；`resize` 与 `studio-ui-scale-change` 重测。
- 原左侧栏 DOM id **全部保留复用**（`#projectList`/`#newProjectBtn`/`#trashEntry`/`#trashBadge`/`#trashPanel`），只换容器。
- 点在 iframe 内的 `mousedown` **不冒泡到父页面** → 收起浮窗的监听**直接挂到 iframe 的 document**。
- 浮窗用 `.open` 类 + `visibility/opacity/transform` 过渡；**不要写 `hidden` 属性**（与过渡冲突）。
- ⚠️ **浮窗必须绝对定位**：关闭态 `visibility:hidden` 仍占位，参与 flex 会把容器撑成 268×204，形成**拦截鼠标的幽灵点击区**。用 `position:absolute; left:0; top:calc(100% + 6px)`。验证用 `elementFromPoint(x,y)`。
- **项目回收站（软删除）**：`DELETE /api/projects/{id}` 打 `deleted_at` 并连带其画布；`/api/projects` 已排除已删。恢复 `POST /api/projects/{id}/restore`、永久删 `DELETE /api/projects/{id}/purge`、列表 `GET /api/projects/trash`（含 `retention_days:30`）。读取时 `cleanup_expired_project_trash()` 清除满 30 天项目及画布。**默认项目不可删。**

## D. API Key 残留排查

删通道 ≠ key 消失。逐处核对：

- `data/api_providers.json`（**不存 key**）
- `API/.env`（真身，`API_PROVIDER_<ID大写>_KEY`，内置通道 `MODELSCOPE_API_KEY`/`ARK_API_KEY`/`RUNNINGHUB_API_KEY`/`COMFLY_API_KEY`）
- ⚠️ `*.exe.WebView2\...\Web Data`（**Chromium 自动填充 SQLite，明文存输入过的 key**，查 `autofill*` 表）
- `...\Code Cache`/`Cache_Data`；Local/Session Storage、IndexedDB（实测干净）
- `%LOCALAPPDATA%\InfiniteCanvasLauncher\preferences.json`（无 key）
- 用户级环境变量（`GRSAI_API_KEY`/`MEDIA_API_KEY`，Bash 读不到，用 `[Environment]::GetEnvironmentVariable(name,'User')`）
- **git 历史**（`API/.env` 已于 `18b4dcd` 取消跟踪；加入跟踪是 `b36ab39`、`67e7b89`。⚠️ 2026-09-18 复核修正：历史里**唯一的真 key 是 `API_PROVIDER_GRSAI_KEY`（11 位纯数字，blob `b76dd86274`，提交 `74b5c8c` / `9bdb54c`）**；`MODELSCOPE_API_KEY` 在历史里一直是**掩码占位符** `ms-token-***`，不是真 key。这些 blob **均已在 `origin/main`** → 只能轮换）

- `CleanOrphanedEnvKeys()`（`Program.cs:1351`）删通道时**只置空孤立 key 的值、不删整行**，且只处理 `API_PROVIDER_` 前缀 → **内置通道 key 不会被清**。
- 清 WebView2 残留前确认进程归属：`Get-CimInstance Win32_Process` 看 `--user-data-dir`（`wmic` 被安全策略拉黑）；在跑的 `msedgewebview2.exe` 往往属于别的程序。

### D.1 2026-09-18 全量排查结果（删通道后）

**真残留三处**：
1. 🔴 **git 历史**：`API_PROVIDER_GRSAI_KEY` = 11 位纯数字（blob `b76dd86274`，提交 `74b5c8c`/`9bdb54c`），已推送 → 轮换。
2. 🟠 **WebView2 自动填充**：`Lochou启动器.exe.WebView2/EBWebView/Default/Web Data` 的
   `autofill_edge_field_values` 有 4 行（`domain=launcher.local`），label 分别是
   「通道名称 / 接口协议类型 / 接口基础地址 / **API 密钥 (API Key / Token)**」；
   值依次为 `Grsai`、`grsai`、`https://grsai.dakka.com.cn`、**20 位纯数字（`is_masked=1`）**。
   注意 `autofill` 表是 **0 行**、`Login Data` **0 条**、`Cookies` **0 条** —— 别只看这几张表就下结论。
3. 🟠 **用户级环境变量 4 个**：`GRSAI_API_KEY`(35, `sk-2b6`)、`MEDIA_API_KEY`(51, `sk-pkc`)、
   `GPT_IMAGE_API_KEY`(67, `sk-0ae`)、`AMAZON_IMAGE_STUDIO_PLANNER_API_KEY`(67, `sk-7c3`)。
   系统级（Machine）**无**。

**已确认干净**：`data/api_providers.json` = `[]`；当前 `API/.env` 所有 `API_PROVIDER_*_KEY` 全空
且 `MODELSCOPE_API_KEY` 仅占位符；`data/api_providers.json.bak-20260918`（备份）字段只有
`id/name/base_url/protocol/enabled/primary/*_models`，**无 key 字段**；源码 608 文件扫描 61 处
命中全是误报；WebView2 `Local State`/`Preferences` 0 命中；`%LOCALAPPDATA%\InfiniteCanvasLauncher\preferences.json`
(56 B) 无 key；`data/conversations/` 空；7 个画布 JSON 含 `logs` 全扫干净；`output/backup/`、
`output/server.log`、`data/media_previews/`、`asset_library.json`/`projects.json`/`prompt_libraries.json` 0 命中；
`static/runninghub/api_providers.json` 是预设模板无 key；git **HEAD 不跟踪任何** `WebView2`/`API/`/`.env`，
`.gitignore` 已含 `API/.env`、`*.exe.WebView2/`；历史 `.workbuddy-ai/memory/` 唯一命中
`sk-ant-api03-xxxxxxxxxxxxxxxxxxxx` 是**文档化的占位符**（原文标注「非真 key」）。

**项目外同源两处**（顺带发现）：`~/.workbuddy-ai/secrets/media-api.env` 的 `MEDIA_API_KEY`(51, `sk-pkc`)；
`~/.codex/config.toml` 的 `experimental_bearer_token`(51, `sk-WD`)。

**方法论四坑（都踩过）**：
- 🚨 **别用 `\s*` 匹配 `.env` 的 `=` 两侧** —— `\s` 含换行，会把「空值 + 下一行变量名」误判成值
  （本次一度误报 `ARK_API_KEY = RUNNINGHUB_API_KEY`）。**必须逐行按 `=` 切分后只看本行右侧**。
- **识别掩码占位符**：含 `*` 的（`ms-token-***`）不是 key。报「长度 + 是否含 `*` + 字符构成」即可区分。
- **`ms-` 前缀在 ModelScope 语境下大量误报**：模型 ID（`ms-custom-*`/`ms-lora-*`）、CSS 类名
  （`ms-custom-model-select`）都会命中。
- ⚠️ **全库 `git log --all --diff-filter=A` / 全 blob 遍历会超时**（被 SIGTERM 杀过两次），
  且 `git cat-file --batch` 一次性写全部 sha 到 stdin 会**管道死锁**。改用**定向 pathspec**
  （`API/.env`、`.workbuddy-ai`、`*WebView2*`）+「先 `--batch-check` 拿大小、再从文件喂 `--batch`」。
- **判断 blob 是否已公开**：`git log origin/main --oneline --find-object=<blob>`，有输出即已推送 → 只能轮换。

完整报告：`output/API-Key残留排查报告-2026-09-18.md`。


## E. 磁盘清理历史（2026-09-17）

- 项目约 **1.4 GB**。已删（A/B 类）：`一键启动.exe.WebView2`、`launcher/bin/`、`Lochou启动器.exe.WebView2/`、`__pycache__/`、output 下验证截图。**`output/backup/` 必须保留**。
- `assets/input/`：被引用 17 个 / 135.8 MB（唯一引用源 `history.json`），无引用 66 个 / 342.8 MB。
- 汇报清理成果必须同时给出回收站占用。实证：A/B/C 清理约 830 MB + gc 639 MB，回收站累积 **9.31 GB**，磁盘几乎没变。**真正释放 = 清空回收站**。
- 统计回收站见 `win-recyclebin-forensics` skill；**`$I` 残留而 `$R` 已消失的条目不占空间，必须 `os.path.exists($R)` 过滤**；`$I` 时间是 **FILETIME(UTC)，+8h 才是北京时**；遍历必须 `os.walk`（`os.listdir` 在 SID 目录抛 `WinError 5`）。
- ✅ **上传去重已实现**（2026-09-18 核实）：`find_duplicate_upload(content, category)`（`main.py:12580`）做内容级 MD5 去重，只对同尺寸候选算哈希；`/api/ai/upload`（`:12645`）与 `/api/ai/upload-base64`（`:12681`）上传前都先查重，命中则复用已有文件名。**旧结论「上传不按内容去重、assets 无限膨胀」已过时**，该函数的 docstring 记录了修复动机（同一张 17.5MB 图曾被存 11 份）。

## F. Grsai 通道模型清单与探测记录（2026-09-18）

通道 `ep_1789698073689`「Grsai」，`base_url=https://grsai.dakka.com.cn`，key 在 `API/.env` 的 `API_PROVIDER_EP_1789698073689_KEY`（35 字符）。后端读入时 `protocol: grsai` 会归一成 `openai`。

### F.1 `chat_models`（对话 / 视觉，共 14 个，已写入配置）

GPT 家族 4 个，**全部实测支持读图**（测试图 = 白底 + 蓝色大圆 + 黄色小方块）：

| 模型 | 文本 ping | 直连网关读图 | 经 `/api/canvas-llm` 读图 | 回复内容 |
|---|---|---|---|---|
| `gpt-6-astra` | 200 / 3.9s | 200 | 200 / 4.6s | "A yellow square centered inside a blue circle on a white background." |
| `gpt-5.6-terra` | 200 / 2.3s | 200 / 7.2s | 200 / 6.2s | "A large blue circle with a small yellow square in the center." |
| `gpt-5.6-sol` | 200 / 2.2s | 200 / 2.5s | 200 / 21.2s | "A large blue circle containing a smaller yellow square." |
| `gpt-5.5` | 200 / 5.0s | 200 / 3.5s | — | "A large blue circle with a small yellow square inside." |

Gemini 家族 10 个：`gemini-3.1-pro`、`gemini-2.5-pro`、`gemini-3-flash`、`gemini-3-pro`、`gemini-2.5-flash`、`gemini-3.5-flash`、`gemini-3.1-flash-lite`、`gemini-3.5-flash-lite`、`gemini-3.7-flash`、`gemini-3.8-flash`（`gemini-3.8-flash` 读图实测 200 / 6.6s）。

### F.2 实测**不存在**的名字（400 `model not found`）

- OpenAI 旧命名：`gpt-4o`、`gpt-4o-mini`、`gpt-4.1`、`gpt-5`、`gpt-5.1`、`o3`、`o4-mini`
- 裸版本号：`gpt-5.6`、`gpt-6`
- GPT-5.6 家族的 Luna 档：`gpt-5.6-luna`（官方有 Sol/Terra/Luna 三档，Grsai 只上了 Sol/Terra）
- GPT-6 的衍生：`gpt-6-sol`、`gpt-6-terra`、`gpt-6-astra-mini`、`gpt-6-astra-pro`
- `gpt-5.6-*` / `gpt-5.5-*` 的 26 种后缀变体（terra/sol 除外）：`-luna`/`-nova`/`-aria`/`-iris`/`-orion`/`-atlas`/`-vega`/`-lyra`/`-flare`/`-sunburst`/`-mini`/`-pro`/`-cli`/`-fast`/`-lite`/`-auto`/`-max`/`-turbo`/`-plus`/`-flash`/`-edge`/`-core`/`-zenith`/`-quantum`/`-vision`/`-codex`/`-review`
- 其他家族（非穷举，仅试了一批）：`claude-sonnet-4.5`、`claude-opus-4.1`、`grok-4`、`grok-4-fast`、`deepseek-v3.2`、`kimi-k2`、`qwen3-max`、`glm-4.6`

→ **Grsai 的对话模型只有 GPT + Gemini 两个家族。**

### F.3 `image_models`（17 个，生图）与 `video_models`（1 个）

`image_models`：`gpt-image-2.5`、`gpt-image-2.5-sunburst`、`gpt-image-2.5-flare`、`gpt-image-2-vip`、`gpt-image-2`、`nano-banana`、`nano-banana-fast`、`nano-banana-2`、`nano-banana-2-lite`、`nano-banana-2-cl`、`nano-banana-2-2k-cl`、`nano-banana-2-4k-cl`、`nano-banana-pro`、`nano-banana-pro-vt`、`nano-banana-pro-cl`、`nano-banana-pro-vip`、`nano-banana-pro-4k-vip`。
`video_models`：`minimax-h3`。

⚠️ 这些 `gpt-image-*` 是**生图模型**，不会出现在对话/视觉模型下拉里。

### F.4 探测方法（可复用）

1. **先找权威来源，别猜名字**：① 应用内置预设 `RECOMMENDED_APIS`（`static/js/api-settings.js:163`）—— Grsai 那条原本就写着 `chat_models: ['gpt-5.6-terra']`；② WebSearch 查官方模型命名（GPT-5.6 = Sol/Terra/Luna；GPT-6 旗舰 = Astra）。
2. **网关模型列表端点**：Grsai 的 `/v1/models`、`/api/models`、`/api/v1/models`、`/v1/api/models` **全 404**，此路不通。
3. **串行探测**：`POST /v1/chat/completions`，`{'model': m, 'messages':[{'role':'user','content':'pong'}], 'max_tokens':5}`，**间隔 1~1.5s**。
   - ⚠️ **绝不要用并发扫**：12 线程扫 216 个名字时，已知可用的 `gpt-5.5`/`gpt-5.6-terra` 也被扫成失败（限流），得出「只找到 1 个」的假结果。
   - ⚠️ **上游不稳**：`gpt-5.5` 曾 400 `openai api error, please try again`；`gpt-5.6-sol` 一次 2.2s 一次 46.9s。**判「存在」看 200，判「不存在」必须看到 `model not found`**，慢或偶发 400 不能当不存在。
4. **视觉能力探测**：`content` 用 `[{'type':'text',...},{'type':'image_url','image_url':{'url':'data:image/png;base64,...'}}]`，问「What shapes and colors are in this image?」，看回复是否描述正确。
5. **端到端**：起服务 → `GET /api/config` 看 `api_providers[].chat_models` → `POST /api/canvas-llm`（`{'message','images':[dataURL],'model','provider'}`）→ 停服务。改配置前必须先确认 3000 端口没服务在跑。

### F.5 变更记录

- `data/api_providers.json`：改前 md5 `3848b2a08944bbe45c02e4da1c60d280`（1035 bytes）→ 补 3 个 GPT 后 `670b3807ebabb2d1eb25bc91c2f5e4b1`（1099 bytes）→ 补 `gpt-6-astra` 后 `f4778fa8165dea2dd16aea05c041ddd6`。备份 `data/api_providers.json.bak-20260918`（= 改前状态）。
- `static/js/api-settings.js:177` 的 `RECOMMENDED_APIS` Grsai 预设：`['gpt-5.6-terra']` → `['gpt-6-astra','gpt-5.6-terra','gpt-5.6-sol','gpt-5.5']`。

## G. 磁盘/清理补充细节

- ⚠️ **`git ls-files` 默认 `core.quotepath=true`，中文名被转义成八进制** → `os.path.getsize` 静默跳过（曾漏掉两个 68.9 MB exe）。**必须 `-c core.quotepath=false` 且 `-z`**。
- 判孤儿不能只看文件名是否出现在源码里（可能被运行时拼接）；`ai_ref_*`/`online_*` 名字是随机 hash，**权威引用源是数据文件**（画布 `nodes`/`logs`、`history.json`）。
- **不要动**：`get-pip.py`（`Program.cs` 引用）、`inspire_image_dims.json`（`main.py` 引用）、`history.json`、`python/`、`packages/`、`static/`、`data/`、`workflows/`、`tools/`、`CLI/.../*-arm64-*.tgz`、`output/backup/`。
- 删通道 ≠ API key 消失（`api_providers.json` **不存 key**，真身在 `API/.env`）。逐处核对清单见本文档 D。

### G.1 2026-09-18 二次全量盘点（「哪些能删」）

**结论**：项目内部「零风险可清」只剩 **≈76 MB**（历次清理已把大头拿走）；真正的大头在**项目之外**。

**A 类 纯缓存 / 自动重建（零影响）**
- `data/media_previews/` 5.8 MB / 203 个 —— `main.py:7614 media_preview_cache_paths()` 的 key =
  `sha1(绝对路径|mtime_ns|size|宽度)`，`:7656 media_preview()` 未命中**现算现存** → 纯缩略图缓存。
- `python/**/__pycache__/` 11.9 MB / 152 目录 / 1309 文件（全在 `site-packages` 下）。
- `.git.broken-20260917/`（`.git` 事故的空壳标记，**已被 git 跟踪**）、`nuget.temp.config`（197 B，也已被跟踪）。

**B 类 运行/构建产物（先关启动器）**
- `Lochou启动器.exe.WebView2/` 38.9 MB（`.gitignore` 自己写着「用户级运行状态，非源码」）。
  🎁 删它**同时清掉 D.1 里那条「API 密钥」自动填充**。
- `launcher/obj/` 9.3 MB（含 `singlefilehost.exe`）、`dist/` 1.8 MB —— `build-launcher.ps1` 可重建。

**C 类 `output/`**：108 文件 / 8.8 MB，其中 74 张历轮验证 PNG 占 8.66 MB 可删；
**`output/backup/` 必须留**；9 个 `.md` 报告建议留。

**D 类 不要删（会破坏功能或视觉）**
- ⚠️ **`assets/output/` 16 个文件 / 135.6 MB 全部被 `history.json` 引用**
  （`"images": ["/assets/output/online_xxx.png"]`）→ 是生图历史本体，删了历史列表裂图。
- `python/`（`run.bat` → `python\python.exe`）、`Lochou启动器.exe`（68.9 MB，已跟踪，分发用）、
  `static/`、`Picture/`、`get-pip.py`、`data/*`、`output/backup/`。
- 与旧结论一致、**再次确认不要动**：`packages/`、`CLI/**/*.tgz`、`inspire_image_dims.json`。
  （我一度把后三者列进「可删」，复核 `Program.cs` 引用后收回 —— `inspire_image_dims.json` 删了
  会让灵感页首次访问同步等最多 6 秒，`INSPIRE_DIMS_PROBE_BUDGET=6.0`。）
- 唯一确认可删的用户数据：`assets/input/` 里 **112 个无引用 `ai_ref_*.png` / 4.4 MB**
  （116 个里只有 4 个被引用）。

**E 类 项目之外 `D:\工作\无限画布\`（共 7.4 GB，最大头）**
- 🥇 `Infinite-Canvas-agent-main/` **3318.7 MB** —— **2026-09-04 的旧项目整份副本，无 `.git`**，
  内含 `assets/` 2422.7 MB、`一键启动.exe.WebView2/` 431.7 MB、`launcher/` 171.7 MB。
  当前工作项目是 `Infinite-Canvas/`（新一代，用 `Lochou启动器.exe`）。
- `Infinite-Canvas.v0.1.zip` 1614 MB、`Infinite-Canvas.for.lochou.launcher.Official.v1.0.zip` 807.8 MB、
  `repo-20260918.bundle` 452.7 MB、`repo-20260918-b4msgfix.bundle` 452.7 MB（本次留底）、`icon/` 15.3 MB。

**方法**：把 `history.json` + `data/asset_library.json` + `data/projects.json` +
`data/prompt_libraries.json` + `data/inspire_prompt_zh.json` + 7 个画布 JSON 合并成 441 KB
引用文本，逐文件名比对；再回读源码确认目录用途。
**回收站**：本次测得 1401 条目 / **0.01 GB**（几乎空）—— 注意「删除即入回收站」，删完必须清空才真释放。

报告：`output/可精简文件分析报告-2026-09-18.md`。

### G.2 零风险批 + 孤儿清理执行（2026-09-18，commit `bbb7ab1`）

老板批准后落地。**363 路径 / 82.67 MB** 全部走回收站，逐组残留 **0**。

| 组 | 目标 | 体积 |
|---|---|---|
| A1 | `data/media_previews/` | 5.84 MB |
| A2 | `python/**/__pycache__/`（152 目录 / 1309 文件） | 11.87 MB |
| A3 | `.git.broken-20260917/`（1 字节空壳，2 个跟踪文件） | 1 B |
| A4 | `nuget.temp.config` | 197 B |
| B1 | `Lochou启动器.exe.WebView2/` | 40.20 MB |
| B2 | `launcher/obj/` | 9.99 MB |
| B3 | `dist/` | 1.83 MB |
| C1 | `output/` 探针产物 94 项 | 8.57 MB |
| D1 | `assets/input/` 孤儿图 111 个 | 4.37 MB |

**两处前置验证（都很关键）**

1. **`dist/` 是启动器 UI 的「第 1 顺位」资源目录**，不是纯构建垃圾。候选链见 A 节；
   删前逐文件比对 `dist/launcher` 与 `launcher/dist` **各 7 文件 md5 全同**（含
   `index-Bm2vKWq7.js` / `index-Nr2NHwCT.css`）→ 删后命中第 3 顺位兜底副本，UI 零差异。
   根 `dist` 另有 4 个非 web 产物（`InfiniteCanvasLauncher.pdb` + 3 个 WebView2 `.xml`）。
2. **`assets/input` 引用统计口径**：G.1 只扫 `history.json` → 「4 个被引用 / 112 孤儿」；
   本次改扫**全项目 119 个文本文件**（含 `data/canvases/*.json` 与记忆文档）→ 实为
   **5 个被引用 / 111 孤儿**。少删的 1 个是 `ai_ref_8c91feac569b.png`（被记忆文档引用）。
   **教训：判「孤儿」必须把画布 JSON 与文档一起纳入扫描范围，只扫 `history.json` 会误删。**

**验证（8 项全过）**：7 个画布 md5 逐一不变；5 个受保护图片 md5 不变；`launcher/dist` 兜底在；
`/api/canvases` HTTP 200（7 画布）；fastapi/uvicorn/PIL 可导入（删 `__pycache__` 无影响）；
`/api/media-preview` 请求 200 / 4336 字节且 `data/media_previews` **按需自建**。

**回收站**：执行前 **721 条目 / 0.011 GB** → 执行后 **3121 条目 / 0.092 GB**
（**+2400 条目 / +82.7 MB**，与计划 82.67 MB 吻合 → 证明真入回收站而非硬删）。
⚠️ **磁盘未释放**，需清空回收站才真释放。D: 可用 3726.01 GB。

**正向副作用**：`Lochou启动器.exe.WebView2/` 的 `Web Data` 里 `autofill_edge_field_values`
4 行（`domain=launcher.local`，其中「API 密钥」= 20 位纯数字、`is_masked=1`）随该目录删除一并消失
→ D 节残留清单中的「WebView2 自动填充」一项**已消除**。

**方法**：`SHFileOperationW` + `FOF_ALLOWUNDO|FOF_NOCONFIRMATION|FOF_SILENT|FOF_NOERRORUI`，
`pFrom` 用 NUL 分隔、双 NUL 结尾，每 40 个一批。⚠️ 返回码可能报 `2`（`ERROR_FILE_NOT_FOUND`），
但**判成功要看「回收站增量 = 计划体积」+「逐路径存在性复查」**，不要被返回码误导。
已跟踪文件（`.git.broken-20260917` 2 个 + `nuget.temp.config` + 4 个早于 `.gitignore` 被跟踪的
`output/step*.png`）用 **`git add -u`** 暂存后提交 —— `output/` 被 gitignore，
`git add -A output/...` 会直接报 ignored 并 exit 1。

报告：`output/零风险清理执行报告-2026-09-18.md`。

## H. 3D 预览：恢复修改前基础白模工作室方案（2026-09-18）

当前按老板要求固定为修改前已验证的视觉方案：**纯白 `#ffffff` 视口 + 灰白基础白模 + 原工作室环境光 + 隐藏坐标网格**。

### H.1 当前实现

- 环境：每个 WebGL 查看器独立创建 PMREM 摄影棚环境贴图，并绑定 `scene.environment`；销毁查看器时释放环境目标，避免跨 WebGL 上下文复用。
- 灯光：`HemisphereLight(0.34)` + 主/辅/轮廓三盏 `DirectionalLight(1.35 / 0.46 / 0.60)`；主光位置 `[5.5, 9, 6.5]` 并开启阴影。
- 坐标网格：查看器不创建 `GridHelper`，3D 舞台内部不显示坐标网格；画布外围点阵属于主画布背景，不属于 3D 网格。
- 地面：`ShadowMaterial({opacity:0.2})` 平面，只接收接触阴影；背景固定纯白。
- 对象材质：所有图元统一灰白石膏材质 `#d9dce1`、roughness `0.62`，plane 使用双面材质克隆。
- `normalize3DScene()` 对旧场景做几何字段兼容，返回值只保留相机和图元；FOV 滑块与相机姿态持久化继续保留。

### H.2 已撤回方案

柔化参数和默认 `AmbientLight + DirectionalLight` 方案已撤回；场景自带 `background/lights/ground` 和对象材质方案仍保留在历史提交 `ca4cd1a` 中。

<!--
### H.1 旧版常量（历史记录）

```js
const SMART_3D_STUDIO = {
    background: '#ffffff',
    clay: '#d9dce1', clayRoughness: 0.62, clayMetalness: 0, envIntensity: 0.50,
    groundShadow: 0.2,
    hemisphere: {sky:'#ffffff', ground:'#e9ecf1', intensity:0.34},
    key:  {color:'#ffffff', intensity:1.35, position:[5.5, 9, 6.5]},
    fill: {color:'#ffffff', intensity:0.46, position:[-6.5, 4.2, 3.5]},
    rim:  {color:'#ffffff', intensity:0.60, position:[-2.5, 5.5, -7.5]}
};
```

### H.2 四个硬约束（都是实测踩出来的）

1. **`toneMapping` 必须是 `NoToneMapping`** —— 否则线性值 1.0 经 `LinearToneMapping`(exposure=1) 被压成 `1/1.05≈0.952` → sRGB ≈ **250**，背景就不是精确 255。`outputColorSpace = SRGBColorSpace` 保留。
2. **`scene.environment` 不必是 `<canvas>`** —— `renderer.copyFramebufferToTexture()` 接受任何 `Texture`（`WebGLTextures.setTexture2D` 用 GL 绑定，不看纹理源类型），所以可用 `PMREMGenerator.fromScene()` 生成 **LDR 环境贴图**（`HalfFloatType` 渲染目标，内部用 `RGBFormat` 效果，**保留 >1 值**）。
3. **`PMREMGenerator.fromScene()` 的环境场景**：手搭「白色摄影棚」——浅灰房间 `BoxGeometry(14,14,14)`（`MeshBasicMaterial`，`side:BackSide`，`Color.setScalar(0.82)`）+ 三块纯白柔光板（`Color.setScalar(gain)` 给 >1 亮度）。当前 gain：顶光柔光箱 `2.0`（`7×7`，水平朝下）、主光柔光箱 `1.6`（`6×5`，右前上）、辅光柔光箱 `1.1`（`6×5`，左前）。`pmrem.fromScene(envScene, 0.04)` 后**必须 dispose 环境场景的 geometry/material**。
4. ⚠️ **环境贴图必须按渲染器创建**（`build3DStudioEnvironment(THREE, renderer)`）—— 贴图绑定各自的 WebGL 上下文，**跨查看器复用会失效**。`dispose3DViewer()` 里要 `scene.environment = null` + `envTarget.dispose()`。

### H.3 光照与地面

- 4 盏灯：`HemisphereLight(0.34)` + `DirectionalLight` 主 `1.35`（**唯一 castShadow**）/ 辅 `0.46` / 轮廓 `0.60`。主光 shadow：`mapSize 1024²`、`bias -0.0006`、`normalBias 0.022`、`radius 3`、正交视锥 `±6 / near 0.5 / far 44`。
- 地面用 **`ShadowMaterial({opacity:0.2})`**：`unlit`、`transparent`、`color 0x000000`、`depthWrite=false`，只在被遮挡处着色 → 白背景下产出纯灰接触阴影，**地面本身不可见**（`PlaneGeometry(80,80)` 绕 X 转 -90°）。
- 所有图元共用同一份灰白石膏材质；`plane` 图元用 `side: DoubleSide` 的克隆。

### H.4 过曝调参记录（第一版严重过曝）

- ❌ 初版 `key 2.2 / fill 0.75 / rim 1.05 / hemi 0.55 / envIntensity 0.85` + 环境板 gain `3.0/2.2/1.4` → `pureWhitePct 99.41%`、`nonWhite` 仅 2885 px，模型几乎全糊进白背景。**根因**：半球光给所有面一个 `0.55*albedo` 常量项，加三个方向光在 `NdotL≈1` 处叠加，再乘环境贴图 → 远超 1.0 被白色夹断。
- ✅ 降到 `hemi 0.30 / key 1.20 / fill 0.42 / rim 0.55 / envIntensity 0.45`、房间 `0.82`、板 gain `2.0/1.6/1.1`、`clay` 改 `#d9dce1` → `pureWhitePct 87.53%`、`nonWhite 61407`。
- ✅ 再微调一档到 `hemi 0.34 / key 1.35 / fill 0.46 / rim 0.60 / envIntensity 0.50` → `lightGreyMean [204,207,212]`、`darkestChannel 160`、四角精确 `[255,255,255]`。

### H.5 场景 JSON 与提示词的相应收缩

- `SMART_3D_SYSTEM_PROMPT` 已去掉 background/lights/ground/color/metalness/roughness/opacity 字段，明确告诉模型「viewer 统一渲染为纯白背景 + 灰白白模 + 固定工作室光，**不要输出颜色/材质/灯光/地面/网格/背景**」。
- `normalize3DScene()` 对象 spec 只留 `type/name/position/rotation` + 几何字段；返回值只留 `background`（固定白）+ `camera` + `objects`。
- 已删除死函数 `smart3DColor()`、`smart3DUnit()`。

### H.6 ⚠️ 未验证的潜在风险

- 当前用 `PCFSoftShadowMap`（`shadowMapType: 2`）。推断 `shadow.radius` 在该分支**不生效**（`WebGLProgram` 注入 `PCF_SOFT_SHADOWMAP` define，固定 9 次偏移采样，`shadowRadius = shadowMapSize.x`），薄几何（如 `plane` 图元）可能有**漏光条带**。若老板反馈阴影脏 → 改 `THREE.BasicShadowMap` 或调大 `shadowMapSize`。
- 探针实测数据（774×636 画布，4 图元合成场景）：`background "#ffffff"`、四角 `[255,255,255]`；`lights 4`（hemi 0.34 + 1.35/0.46/0.60）、`shadowCastingLights 1`、`shadowMapEnabled true`、`toneMapping 0`、`outputColorSpace "srgb"`、`envMap true`；`children 9`（4 灯 + ShadowMaterial 地面 + 4 网格）、`gridHelpers 0`、`groundUsesShadowMaterial true`；`clayColor "#d9dce1"`；`pureWhitePct 87.53%`、`midGrey 0`、`dark 0`、`subjectBBox {x:281,y:94,w:231,h:366}`；`reuse {sameCanvas:true, viewers:1}`。
- 截图：`output/3d-white-clay.png`（浅色主题）、`output/3d-white-clay-dark.png`（深色主题）。

## I. 保存接口语义与 logs 坑（从 MEMORY.md 下沉）

- **`PUT /api/canvases/{id}` 是全量替换**：`nodes`/`connections`/`logs`/`settings` 无条件覆盖，**不传等于清空**。
- **必须传 `base_updated_at`**。两道守卫：①旧 base → 409；②「静默丢节点」守卫（base 不一致且本次写入会删服务端已有节点）→ 409。前端收 409 会按 id 取并集合并后用服务端 `updated_at` 重存，不死循环。
- 只改标题/图标另有 `POST /api/canvases/{id}/meta`（不 bump `updated_at`）。
- **`GET /api/canvases/{id}` 返回 `{"canvas": {...}}`**（包了一层）。
- ⚠️ **清空 `logs`**：走 PUT 并**全量回传** `title/icon/nodes/connections/viewport/settings`，只把 `logs` 置 `[]`；少传 `settings` 会一起清掉几十项设置。
- ⚠️ **「旧页面把 logs 写回来」的坑**：`applyMergedServerCanvas()`（`smart-canvas.js:6122`）409 时只合并 nodes/connections、不合并 logs；随后 `saveCanvas` 重试（`:6837`）带旧 logs 且 base 已更新 → 守卫放行、日志被写回。**清完 logs 必须让用户刷新页面。**

## J. 前端要点（从 MEMORY.md 下沉）

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

## K. 3D 预览节点界面约定（从 MEMORY.md 下沉）

- **定位**：上游只能是「快速生图」（`smart-image`），下游也只能是「快速生图」；与 prompt/loop/group 双向都拒绝（`canAutoConnectDraggedNode()` + `connectInputNode()` 双处硬校验，两处都要改）。
- **生成路线**：上游图片 → `POST /api/canvas-llm`（系统提示词 `SMART_3D_SYSTEM_PROMPT`，`smart-canvas.js:8909`）→ `smart3DParseSceneJson()`（含围栏与尾随逗号容错）→ `normalize3DScene()` → 存进 `node.scene3d`。7 种图元：box/sphere/cylinder/cone/torus/capsule/plane。
- **节点字段**：`scene3d`、`scene3dRaw`（截 20k）、`scene3dError`、`camera`（`{position,target,fov}`，跨刷新恢复）、`scene3dSnapshotUrl`、`model`/`provider`。截图 dataURL 只放内存 `smart3DSnapshotData`，**不进画布 JSON**。
- **FOV 滑块（2026-09-18 加上）**：`.smart3d-bar` 里 `[data-3d-fov]` 范围 20°–90° 步进 1，读数同步显示「XX° · XXmm」（35mm 全画幅等效：`f = 12 / tan(fov/2)`，由 `smart3DFocalMm()` 计算）。滑块 `input` 实时改 `viewer.camera.fov` + `updateProjectionMatrix()` + 脏标记；`change` 写 `node.camera.fov` + `scheduleSave()`（点 `change` 才落盘，避免拖动过程每次 200ms 触发 debounce 风暴）。`apply3DSceneToViewer` 优先用 `node.camera.fov`（覆盖场景默认）；`persist3DCamera` 把 `fov` 一并写入 `node.camera`（拖拽改角后也会落）。绑定事件里要 `stopPropagation` 防节点拖拽抢走；`el.querySelectorAll('[data-3d-provider],...')` 排除链要补 `[data-3d-fov]`。
- **查看器**：`smart3DViewers: Map<nodeId, viewer>`，动态 `import('/static/vendor/js/three-0.160.0.module.js')`，自写环绕（pointerdown/move/up + wheel，无 OrbitControls 依赖），rAF 脏标记渲染，`render()` 后由 `sync3DViewers()` 把 canvas 搬回新舞台。**上限 6 个同时存活**，节点删除即 `dispose3DViewer()`。
- **下游取图**：`outputImagesForNode()` 的 `smart-3d` 分支返回 `node.scene3dSnapshotUrl`；该 URL 由「场景建好后 + 拖拽/滚轮停下后（防抖 520ms）」调 `snapshot3DNode()` → `/api/ai/upload-base64` 刷新。截图 `preserveDrawingBuffer:true`。
- ⚠️ **三个已修的坑**：① 场景字段缺失会让 `spec.rotation[0]` 抛错并拖垮整个查看器 → 应用前必须 `normalize3DScene()` 规范化并写回节点；② `persist3DCamera()` 若直接读 `camera.position`，在环绕角刚改、渲染循环还没跑到时是旧值 → 落盘前先 `apply3DCamera(viewer)`；③ **验证探针里手动 `nodes.push()` 会被异步 `loadCanvas` 覆盖**（onload 后约 3s 才完成 fetch+赋值）→ 注入前必须 `await sleep(3000+)`，或用真实 `create3DNode()` + `scheduleSave()` 让节点走服务端重载。
- **无头 Edge 验证**：必须 `--enable-unsafe-swiftshader --use-gl=angle --use-angle=swiftshader`（`--disable-gpu` 会让 WebGL 兜底直接失效，`hasScene` 假）。虚拟时间三分钟，跑 3D 节点必须用真实 `create3DNode()` 而非手动 push。完整探针写法见 `infinite-canvas-verify` 技能。

### K.1 节点外框布局约定（2026-09-18 定稿）

① `.image-node.smart3d-node` 加 `padding-top:0`，让标题栏贴齐节点顶部（其他节点内缩 12px，3D 节点标题栏必须顶到边）；② **3D 节点必须跳过 `.floating-node-actions` 浮动删除按钮**（渲染模板里加 `&& !is3D`）——标题栏被专门显示后两者会重叠，浮动按钮落在覆盖层下方不可点击；③ **交互说明放在标题栏内，3D 节点不渲染底部 `.node-hint`**：`render()` 里用 `headSub` 把 `<span class="node-head-sub">` 插到 `.node-head` 中、紧跟 `.node-title` 之后，同时把 `hint` 置空并改成条件渲染 `${hint ? '<div class="node-hint">…</div>' : ''}`。⚠️ **`headSub` 必须以 `is3D && smart3DHasScene(node)` 为条件**——空场景/生成失败时那句话（`smart.3dEmptyHint`「连接快速生图后点生成」）已由舞台中央占位层显示，再放进标题栏就是重复，且生成失败时会显示错误引导。`.node-head-sub` 是 `--faint` 灰色小字（`font-size:10px; font-weight:700; line-height:normal`，与 `.smart3d-meta`/`.smart3d-select`/`.smart3d-run`/`.smart3d-fovval` 同规格），`flex:1 1 auto` 负责顶开右侧删除按钮；对应地 3D 的 `.node-title` 由 `flex:1 1 auto` 改为 `flex:0 0 auto`。腾出的约 25px 高度由 `.node-body{flex:1 1 auto}` 自动吸收，3D 视口随之变高，节点总高不变。

### K.2 标题栏对齐与删除按钮（2026-09-18 第三轮打磨，commit 955b64d）

3D 节点是**唯一会显示标题栏的非空节点**，所以 `.node-head` 的默认值（为「隐藏标题栏」场景设计的）在这里全部会露出来，必须逐条覆盖：

| 项 | 默认 | 3D 节点改为 | 原因 |
|---|---|---|---|
| `.node-head` padding | `0 10px 0 12px` | `0` | 加上节点自身 `padding:12px`，标题会比舞台多缩进 12px（实测标题 x=145 vs 舞台 x=133） |
| `.node-head` border-bottom | `1px solid var(--line)` | `0` | 与舞台 `border-top:1px solid rgba(148,163,184,.32)` 间距为 0，叠成 2px 双线 |
| `.node-delete` box-shadow | `.mini-x` 的 `rgba(15,23,42,.12) 0 8px 18px` | `none` | 背景已被全局 `.image-node:not(.empty-node) .node-delete` 置为 transparent，阴影留在实心标题栏里就是一块悬空灰晕 |
| `.node-delete` backdrop-filter | `.mini-x` 的 `blur(10px)` | `none` | 同上，没有背景时只会产生一个 backdrop 根 |
| `.node-delete` hover | 无（被 3 类规则压住） | `color:#dc2626; background:#fee2e2` | 全局 `.image-node:not(.empty-node) .node-delete`（3 个类）优先级 > `.mini-x:hover`（2 个类），不显式覆盖则 hover 只剩 1px 位移 |
| `.smart3d-fovrow` padding | `0 2px` | `0` | 左侧图标、右侧「45°·29mm」会与上方控件行左右边缘各错开 2px |

**验收锚点（真实 DOM，`?v=` 缓存必须刷新）**：`.node-title` 左边缘 == `.smart3d-stage` 左边缘；`.node-actions .node-delete` 右边缘 == 舞台右边缘 == `.smart3d-bar` 右边缘 == `.smart3d-fovval` 右边缘；`.node-head` 的 `borderBottomWidth` 为 `0px`；`.node-delete` 的 `boxShadow`/`backdropFilter` 为 `none`；舞台顶边在 2x 截图上只有 1px 线（(221,225,232)）。节点高/舞台高必须仍是 470/348（无回归）。

**同时已删的死规则**：`.smart3d-node .node-hint { color:var(--faint) }` —— 3D 节点已不渲染 `.node-hint`（`hint` 被置空且改为条件渲染）。注意 `render()` 里 `world.innerHTML=''` 之后那段是**不可达死代码**（前面有 `return;`），它仍然会渲染 `.node-hint`，改样式时别被它误导。

**遗留待定项**：`.node-head-sub` 用 `--faint`，浅色对比度只有 2.55:1（`#94a3b8` on ~`#feffff`）、深色 3.47:1，10px 小字低于 WCAG AA 4.5:1。老板明确要求「灰色小字」，故保留；若要提升可换 `--muted`（浅色 4.76:1）。

### K.3 状态文案与「查看模型输出」（2026-09-18 第四轮打磨，commit 4b14e8b）

**4 个状态必须分别造数据验证**（`smart3DBodyHtml` 里 `emptyText = errorText || tr('smart.3dEmptyHint')`，两者共用 `.smart3d-placeholder`，很容易做成一模一样）：

| 状态 | 触发 | 表现 |
|---|---|---|
| 成功 | `scene3d` 有 objects | 舞台渲染白模；`scene3dRaw` **也会被写入**（`:9628`），所以「查看模型输出」常驻 |
| 解析失败 | `normalize3DScene(smart3DParseSceneJson(raw))` 返回 null → `smart.3dInvalid` | 占位层显示错误文案 + `triangle-alert` |
| 请求失败 | fetch/HTTP 失败 → `error.message.slice(0,200)`（可能是长上游报错）+ `toast()` | 同上 |
| 空场景 | `scene3d: null`、无 error | 占位层显示 `smart.3dEmptyHint` + `rotate-3d` |

- ⚠️ **失败态必须加 `is-error`**，否则与中性空态**同色**（实测两者都是 `#8b95a8`），上游报错几乎看不出来。`.smart3d-placeholder.is-error` 走 `#dc2626` + `pointer-events:auto; user-select:text`（长报错要能选中复制）；空态保持 `pointer-events:none`，不抢舞台拖拽（`beginNodeDrag` 的排除链本来就含 `.smart3d-stage`，放开命中不改拖拽行为）。
- 🚨 **不要给「永远白底」的表面按主题切色**：`.theme-dark .smart3d-stage { background:#ffffff }` 是既定白模工作室风格，深色主题下舞台仍是纯白。第一版写的 `.theme-dark .smart3d-placeholder.is-error { color:#f87171 }` 在白底只有 **2.76:1**，比浅色 `#dc2626`（**4.85:1**）更差。**规律：`--faint`/`--muted` 这类随主题变色的 token 只适用于背景也跟着变色的表面；固定白底区域一律按白底算对比度。**
- **「查看模型输出」`.smart3d-raw` 收起态要退化成一行小字**：默认面板形态（`border`+`background`+`padding:6px 8px`）高 28px，加 `.smart3d-body` 的 8px gap 共吃 **36px 视口高度**（比把操作说明挪进标题栏省下的 25px 还多）。改法是把面板样式挪到 `.smart3d-raw[open]`，收起态只剩 summary 的 14px 行盒；实测舞台高 312 → **326**。
- 验收锚点：失败态 `.smart3d-placeholder` 的 computed color 为 `rgb(220,38,38)`（两主题一致）；空态为 `rgb(139,149,168)`；`.smart3d-raw` 收起 `h=14`、展开 `h≈47.5` 且 `borderTopWidth=1px`、`backgroundColor=rgb(248,250,252)`；`stage.h` 有 raw=326 / 无 raw=348；节点高恒为 470。

### K.4 窄节点控件行折叠（2026-09-18 第五轮 commit 21a00ed / 第六轮 commit 2147bca）

**问题**：节点缩到最小尺寸 320×280 时，`.smart3d-bar` 总宽只有 294px。`.smart3d-meta`（「已识别 N 个对象」）是 `flex:0 0 auto` + `white-space:nowrap`，独占 **106.8px（36%）**，把 `flex:1 1 0` 的两个 `.smart3d-select` 压到各 **45.1px** —— 下拉里只能看到 `"G.."` / `"g.."`，读不出选的是 `gemini-3.1-pro` 还是 `gemini-2.5-pro`。

**改法**：`smart3DBodyHtml()` 给 `.smart3d-body` 加 `is-narrow`，CSS 隐藏 `.smart3d-meta > span` 与 `.smart3d-run > span`（都只留图标），文案移进 `title` 保留可达性。

```css
.smart3d-body.is-narrow .smart3d-meta { padding:0 7px; }
.smart3d-body.is-narrow .smart3d-meta > span { display:none; }
.smart3d-body.is-narrow .smart3d-run { padding:0 8px; }
.smart3d-body.is-narrow .smart3d-run > span { display:none; }
```
⚠️ **`.smart3d-meta` / `.smart3d-run` 内部必须各包一层 `<span>`**（原来是裸文本 + `<i>`），否则没有可隐藏的钩子。`title` 属性是折叠后唯一的文案出口，不能省。

🚨 **阈值绝不能写死像素**（第五轮写死 420 是错的，第六轮已修）。`.smart3d-meta` / `.smart3d-run` 都是 `flex:0 0 auto` + `nowrap`，**自然宽度随语言变化**：

| 元素 | 中文 | 英文 |
|---|---|---|
| `.smart3d-meta` | 106.8px | 139.3px |
| `.smart3d-run` | 79px | 95.9px |

写死 420 会让英文界面出现**「越宽越挤」的反常区间**：英文 420px 未折叠 → 下拉只剩 **70.4px**，比中文 320px 已折叠的 84.5px 还差。

**正确做法：按实测文案宽度算阈值**（`smart3DTextWidth` / `smart3DBarNeedWidth`，`smart-canvas.js` 紧随 `smart3DFocalMm` 之后）：

```js
const SMART3D_SELECT_MIN_W = 110;   // 实测 <104px 时 "gemini-3.1-pro" 被截断
function smart3DTextWidth(text, weight){ /* canvas 2D + getComputedStyle(document.body).fontFamily */ }
function smart3DBarNeedWidth(metaText, runText){
    const metaW = 12 + 5 + smart3DTextWidth(metaText, '800') + 16 + 2;
    const runW  = 12 + 5 + smart3DTextWidth(runText, '850') + 22;
    return metaW + runW + 18 + SMART3D_SELECT_MIN_W * 2;
}
// narrow = smart3DLayoutSize(node).width - 24 < smart3DBarNeedWidth(objectsText, runWidest)
```
- **字体必须取 `getComputedStyle(document.body).fontFamily`**（`'Inter',-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif`）。用「Microsoft YaHei」量同一串会得 76px vs 实际 71.1px，定标偏大。
- **run 的三种文案宽度不同**（生成 3D / 重新生成 / 识别中…），取最宽的算阈值，否则点「生成」瞬间阈值变化会让节点闪一下布局。

**验收锚点（320~560px 共 9 档 × 中英双语 × 有/无场景）**：

| 断言 | 结果 |
|---|---|
| 下拉截断（判定式 `selW < textW + 33`） | **0 处** |
| `.smart3d-bar` 横向溢出 | **0 处** |
| 折叠翻转点 | 中文 445~460px、英文 502~520px（**随语言自动变化**） |
| 英文 480px（修复前截断） | 折叠 → 下拉 190px，`gemini-3.1-pro` 完整显示 |
| 中文 480px（展开） | 下拉 125.1px 完整 + `已识别 0 个对象` + `生成 3D` |
| 560px 默认节点 | 下拉 165.1px，meta / run 文案均显示（无回归） |

- 写入 200×150 的节点会被 `smart3DLayoutSize()` 钳到 **320×280**（`SMART_3D_MIN_W/H`），窄态是真实可达的边界。
- 320×280 + 超长上游报错 + 展开 raw 时 `.smart3d-placeholder` 156/156 无溢出。

### K.5 `<select>` 截断的检测与定标（2026-09-18 第六轮）

🚨 **`<select>` 的文字截断无法用 DOM 检测**：`sel.scrollWidth === sel.clientWidth` **恒成立**（92~130px 全扫过）。用 `need > clientWidth - padding - border` 判定会得出**错误结论**（实测：报「英文 480px 未截断」，截图却是 `gemini-3.1…`）。

真因：**原生下拉箭头独占约 19px**，既不算 padding 也不算 border。

**定标方法（可复用）**：单独造一页，同规格 `<select>` 宽度 96→120 步进 2（每行一个），`--force-device-scale-factor=3` 截图，按「**墨迹右边缘是否随宽度增长**」判定：
- 未截断 → 墨迹右边缘**恒定**（= 左内边距 + 文本宽）；
- 截断 → 省略号贴住文本区右缘，墨迹右边缘**随宽度线性增长**。

⚠️ 判据里要**排除箭头**：箭头是 `rgba(148,163,184,.34)` 叠白 ≈ (219,227,235)，用 `r<150 and g<150 and b<150` 阈值即可只取文字（`#111827`）。
定标结果：文本 71.1px 时 **104px 起完整显示**（104 − 2 边框 − 12 内边距 − 71.1 = **18.9 ≈ 箭头宽**）。代码取 110。

**DOM 侧的等价判据**：`selW < textW + 12 + 2 + 19`（textW 用 canvas 2D 按实际字体量）。用它做全量扫描比逐张截图快得多。

### K.6 选中态（2026-09-18 第五轮同批验证）

`.image-node.smart3d-node.selected` 走全局规则 `border-color:var(--strong); box-shadow:0 0 0 1px var(--strong), 0 14px 36px var(--shadow)`，实测 `borderTopColor` 由 `rgb(232,237,243)` → **`rgb(17,24,39)`**、`boxShadow` → **`rgb(17,24,39) 0 0 0 1px, rgba(15,23,42,.08) 0 14px 36px`**，正常。

⚠️ **探针坑**：选中会触发 `render()` **重建节点 DOM**，之前缓存的元素引用立刻脱离文档 —— 表现为 `document.querySelectorAll('.selected').length === 1` 但 `cachedEl.classList.contains('selected') === false`、`getComputedStyle(cachedEl)` 返回**空串**。探针里一律用 `const q = (id) => d.querySelector(...)` **每次现取**。

### K.7 未配置读图模型的告警（2026-09-18 第七轮，commit 39a0495）

`smart3DModelControlsHtml()` 在 `chatApiProviders().length === 0` 时渲染 `.smart3d-nomodel` 红条，替代两个下拉。**这是阻断性告警，是「为什么点生成没反应」的唯一解释，必须读得全。**

🚨 **原实现会把它从中间硬切且无省略号**：`height:26px` + `white-space:nowrap` + `overflow:hidden`，且**没写 `text-overflow`**（默认 `clip`）。实测：

| 语言 | 文案宽 | 320px（可用 224px） | 560px 默认（可用 285px） |
|---|---|---|---|
| 中文 | 224px | 刚好卡住、**零余量** | 够 |
| 英文 | 303px | **切掉 79px** | **仍切掉 18px** |

→ **英文用户在任何尺寸下都看不全**。

**改法**：允许换行（`height:auto; min-height:26px; padding:4px 8px; white-space:normal; line-height:1.35; overflow-wrap:anywhere`）。罕见错误态，且此时舞台本来就是空的，让位给文案合理。
**验收锚点**：中英 × 320/560px 四组 `scrollWidth == clientWidth`（`clippedPx = 0`）；英文 chip 高 **37px**（两行）、中文 320px 两行 / 560px **26px**（一行）；控件行高 28 → 37px，舞台矮 0~11px。

### K.8 其余已验分支的锚点（2026-09-18 第七轮同批）

| 分支 | 触发 | 验收锚点 |
|---|---|---|
| 生成中 | `node.running = true` | 320px 折叠后按钮 **28px**、560px **79.6px**（中）/ **111.2px**（英）；`disabled=true`、`is-running` 类、`animation: smart3d-spin` 均生效 |
| 空场景（英文长文案） | `scene3d: null`、无 error | `Connect a Quick Image node, then generate` 宽 236.9px，320px 下 `ovX=False`、`ovY=False`（`.smart3d-placeholder` 会换行，不溢出） |
| FOV 行（最小尺寸） | 任意 | 320px 下 `input` 203px + 读数 62px（`45° · 29mm`），`scrollW == clientW`，无横向溢出 |

**探针技巧**：要触发「未配置模型」分支，**不要改 `data/api_providers.json`**（真实用户数据）。`chatApiProviders` 是函数声明、**可写**，直接打桩：
```js
window.__orig = chatApiProviders; chatApiProviders = function(){ return []; }; render();
// 量完后：chatApiProviders = window.__orig; render();
```

### K.9 深色主题验证（2026-09-18 第八轮，commit d346199 / 原 a082fad）

**主题机制**：`.theme-dark`（`smart-canvas.css:7`）重定义 11 个变量
（`--text:#e5e9f0 / --muted:#8f9aab / --faint:#657286 / --line:#2a3444 / --soft:#111722
/ --strong:#d8dee9 / --strong-text:#10141d`）。`applyTheme()`（`smart-canvas.js:1766`）把
`theme-dark` + `studio-theme-dark` 同时加在 `documentElement` 与 `body`；
`smart-canvas.html` 头部内联脚本在 CSS 前就按 `localStorage.studio_theme` 加类（防闪白）。
探针拿深色初始态的最简方式：**在 iframe 加载前写 `localStorage.studio_theme='dark'`**。

**对比度怎么量**（canvas 2D 量不出颜色）：解析 `getComputedStyle(el).color`，
再沿 `parentElement` 链把每层 `backgroundColor` 按 alpha **从外到内**合成成实际背景
（`over(fg,bg)` 递归），最后 `(Lmax+.05)/(Lmin+.05)`。舞台内元素会在 `.smart3d-stage`
的 `#ffffff` 处终止，天然得到白底。

**修复后的两主题对比度基线**（10px 小字按 AA 4.5:1）：

| 元素 | 深色 | 浅色 |
|---|---|---|
| `.node-title` | 5.98 | 4.74 |
| `.smart3d-meta` / `.smart3d-meta > span` | 6.31 | 4.55 |
| `.smart3d-select`（两个下拉） | 14.27 | 17.71 |
| `.smart3d-run` / `> span` | 13.64 | 17.74 |
| `.smart3d-fovicon` | 5.98 | 4.74 |
| `.smart3d-fovval` | **5.98**（修前 3.49） | 4.74 |
| `.node-delete` | 16.26 | 17.66 |
| `.smart3d-nomodel` | **5.62**（修前 4.13） | **5.66**（修前 3.29） |
| `.smart3d-placeholder`（空态） | 3.02 | 3.02 |
| `.smart3d-placeholder.is-error` | 4.83 | 4.83 |
| `.node-head-sub` / `.smart3d-raw > summary` | 3.49 | 2.55 |

**取色方向的两条相反规则（务必别搞混）**：
- `.smart3d-nomodel` 挂在**随主题变色的节点面板**上 → **必须**按主题取色
  （浅 `#b91c1c` / 深 `#f87171`）。原来的 `#ef4444` 两档都不达标。
- `.smart3d-placeholder.is-error` 挂在**恒白舞台**上 → **绝不能**按主题切色
  （深色换 `#f87171` 会掉到 2.76:1；`#dc2626` 在白底是 4.85:1）。
- `.smart3d-fovval` 曾有一条 `.theme-dark { color:var(--faint) }` 覆盖，**是反的**
  （深色 3.49 < 浅色 4.74）—— 已删除，两主题统一走 `--muted`。

**未处理（等老板拍板）**：`.node-head-sub`、`.smart3d-raw > summary`、`.smart3d-placeholder`
三项都在 2.55~3.49:1。它们都用 `--faint`（空态是写死的 `#8b95a8`），是「灰色小字」的既定风格。
若要达标：前两者换 `--muted`（浅 4.55 / 深 5.93），空态换 `#6b7280`（白底 4.83:1）。

**深色下的两项像素检查（均通过，勿再折腾）**：
- `<select>` 原生箭头：`color-scheme` 计算值是 `normal`，但 Chrome 实际画的是**浅色箭头** ——
  实测右侧 22px 条带里 `rgb(176,176,184)` 14px + `rgb(224,232,240)` 8px，对比下拉底色
  `rgb(19,27,41)` 为 8.01:1 / 13.95:1。**可见**。
- FOV 滑块拇指：最亮像素 `rgb(255,255,255)`，对轨道 `rgb(42,52,68)` 12.55:1 ✓。
  轨道对面板仅 1.34:1（浅色 1.18:1），是两主题一致的「细轨道 + 亮拇指」设计，非回归。

**深色下布局零回归**：320/560px × 深/浅 × 6 状态，`barOverflow` 全 0；320px `is-narrow`
照常折叠、下拉 110px ≥ 106.09px；`.smart3d-nomodel` `scrollHeight == clientHeight`
（560px 24px 一行 / 320px 35px 两行，无裁切）；舞台高 298 / 158 / 276 不变。

**⚠️ 收尾对哈希时的新变量**：老板可能同时开着自己的浏览器在操作画布。本轮
`data/canvases/2c794fa4….json` 的 md5 变了、`updated_at` 正好落在探针窗口内，
一度疑似数据事故；查证是**老板自己在拖 3D 节点** —— 该画布 3D 节点的
`scene3dSnapshotUrl`（`assets/input/ai_ref_8c91feac569b.png`）写入时间 19:24:33，
前后 19:24:26~33 有一簇上传，正是「拖拽/滚轮停下后防抖 520ms 截图」的产物。
**判据**：先看 `assets/input/` 最近文件时间是否落在窗口内，再决定是不是事故。

### K.10 键盘焦点可见性（2026-09-18 第九轮，commit d2625de）

**发现的唯一真实缺陷**：`.smart3d-fov`（焦距滑块）原本只有 `.smart3d-fov:focus { outline:none }`，
抹掉了 UA 焦点环却没有任何替代指示 → 键盘用户看不出焦点停在哪，**WCAG 2.4.7（焦点可见，AA）违规**。
实测该元素 `focusable=True`、`:focus-visible=True`，但 `hasIndicator=NO`
（focus 前后 outline / border / box-shadow 全无变化）；而节点内另外 5 个可 Tab 元素
（两个下拉、生成按钮、raw 摘要、删除按钮）都有指示 —— 只有这一个漏了。

**改法**（`static/css/smart-canvas.css` 约 2144 行）：
```css
.smart3d-fov:focus { outline:2px solid var(--strong); outline-offset:3px; border-radius:6px; }
.smart3d-fov:focus:not(:focus-visible) { outline:none; }
```
- 取色 `var(--strong)`（浅 `#111827` / 深 `#d8dee9`），与同节点
  `.smart3d-select:focus { border-color:var(--strong) }` 用同一个焦点色，对各自面板都远超非文本对比 3:1。
- ⚠️ **不要只用 `:focus-visible` 单写**：个别浏览器/脚本聚焦下它不匹配，会退回「完全没有指示」。
  用「`:focus` 给环 + `:focus:not(:focus-visible)` 撤环」两条规则的**并集**，保证键盘一定有环、
  鼠标点进来拖动滑块不会闪环。
- ⚠️ 项目里 `.smart-video-play:focus-visible` 的蓝 `rgba(59,130,246,.72)` 在浅色面板只有
  **2.48:1**，**不能照抄到节点内**。

**验证**：浅色 `outline none → solid 2px rgb(17,24,39)`、深色 `none → solid 2px rgb(216,222,233)`，
`outlineOffset` 均 `0 → 3px`；截图像素扫到 y425~438 两条约 **445px** 宽的横向环边
（与滑块宽度吻合），深浅两主题下环均完整可见、未被裁切。

**⚠️ 探针报「无焦点指示」的两个非缺陷**：`.smart3d-stage`（`div`，`tabIndex=-1`）与
`.smart3d-canvas` 都**不可 Tab**，报 `missing` 属正常，不用管。

### K.11 提交信息被 bash 吞掉的事故与修复（2026-09-18）

**事故**：用外层 bash 的 `python -c "..."` 传**含反引号**的提交信息 → bash 先做命令替换，
反引号内的整段文字被删除（stderr 报 `:focus: command not found`、
`syntax error near unexpected token '('`）。`a082fad`、`85a8b34` 两条提交信息因此缺字
（**代码改动本身无误**，只有 message 受损）。

**修复**：只改 message、不动树 —— 用 `git commit-tree` 重建 commit 对象：
```
用 GIT_AUTHOR_* / GIT_COMMITTER_* 环境变量还原原作者与提交时间
NEW=$(git commit-tree <原 tree> -p <新父提交> -F <msg 文件>)
git update-ref refs/heads/main $NEW
```
`a082fad → d346199`、`bee62fa → e1ab191`、`85a8b34 → d2625de`。
校验：`git diff 85a8b34 d2625de` **输出为空**（树逐字一致）、`git status` 干净、
`git fsck` 无异常。当时本地尚未 push，无远端冲突。

**教训（通用）**：**任何含反引号 / `$` / `!` 的文本，一律先 Write 成文件再用 `-F` 引用，
绝不通过 shell 字符串传递。** 重写历史前必须 `git bundle create ../repo-<日期>.bundle --all` 留底
（本次 452.7 MB，`bundle verify` 通过）。

## L. 本地服务与 git 红线补充（从 MEMORY.md 下沉）

- ⚠️ **启动时 `sync_static_html_versions()`（`main.py:1743`）把 `static/*.html` 的 `?v=` 重写为 `<VERSION>.<资源mtime>` 并写回磁盘** → 每次重启让十几个 html 变 modified。**这是缓存破坏参数，必须保持最新，不要为 git 干净去 `git checkout` 还原** —— 踩过：还原后浏览器继续用缓存旧 JS，而新 CSS 已隐藏 iframe 内原胶囊 → 两个胶囊都不显示，表现为「项目功能整个消失」。
- ⚠️ **本机「删除即入回收站」→ 清理不释放磁盘空间**（`shutil.rmtree`、`SHFileOperationW`、`git gc` 删旧 pack 都只是搬进回收站）。**真正释放 = 清空回收站**，汇报成果必须同时给回收站占用。
- ⚠️ **绝不要用 `git rm <文件>`** —— 实测让**整个父目录消失**（`packages/` 41 文件、`tests/` 两次复现）。恢复用 `git checkout HEAD -- <目录>/`；**正确做法**是 Python `os.remove` / ctypes `DeleteFileW` 删文件再 `git add -A <目录>/`。
- **裸 `git` 不可用**（RTK hook 改写成 `rtk git`，rtk 解析不到）。真身：`C:/Users/Administrator/.workbuddy-ai/binaries/PortableGit/versions/1.2.0/mingw64/bin/git.exe`。`git status --cached` 非法，看暂存用 `git diff --cached --name-status`。
- ⚠️ **工具会话内 `git push` 会无限挂起**：系统级 `credential.helper=helper-selector`（GUI 助手）无界面时静默挂起；`git credential fill` → `could not read Username ... terminal prompts disabled`。**`ls-remote` 成功是假信号**（公开仓库匿名可读）。已排除直连出口、代理、HTTP/1.1、postBuffer、数据量（仅 138 对象）。结论：**推送必须由老板本人终端执行**。

## M. three.js 版本与升级清单（2026-09-18 核查）

| 项 | 值 |
|---|---|
| 本地 | `static/vendor/js/three-0.160.0.module.js`，`REVISION = '160'`，1,272,972 bytes |
| r160 发布 | **2023-12-22** |
| 官方最新 | **r186（0.186.0）**，**2026-09-08** |
| 差距 | 落后 26 个版本 / 约 2 年 9 个月 |

引用点 3 处：`static/angle.html:29`（importmap `?v=2026.08.30`）、`smart-canvas.js:9063`（3D 节点，**无 `?v=`**）、`smart-canvas.js:12382`（全景，`?v=2026.05.30` **已过期**）。⚠️ 同一文件两个动态 import 的 `?v=` 不一致，替换文件时全景路径可能继续吃旧缓存。

### 升级必须改的 2 处代码

1. 🚨 **`envMapIntensity` 语义变化（r163）**：`scene.environment` 的强度不再受 `MeshStandardMaterial.envMapIntensity` 控制，改用 `Scene.environmentIntensity`。本项目 `smart-canvas.js:9262` 用 `envMapIntensity: SMART_3D_STUDIO.envIntensity`（**0.50**）衰减工作室环境光 → 升级后**失效、环境照明近似翻倍、白模变亮失去石膏质感**。修法：`scene.environmentIntensity = SMART_3D_STUDIO.envIntensity`（`:9388` 附近）。
2. ⚠️ **`PCFSoftShadowMap` 在 WebGLRenderer 下废弃（r182）** → 改 `THREE.PCFShadowMap`。位置 `smart-canvas.js:9381`。

### 升级必然带来的观感偏移（需重调参）

**r181 PBR 材质能量守恒 + PMREM 反射改进** → 粗糙材质（`clayRoughness: 0.62`）更亮更物理正确，`SMART_3D_STUDIO` 的灯光/环境数值需要重新调，并重跑七轮视觉验收。

### 经核对**不受影响**的

- `new THREE.CapsuleGeometry(spec.radius, spec.length, 10, 22)`（`:9126`）—— r176 只改**形参名** `length`→`height`，**位置顺序未变**，按位置传参不受影响。
- `outputColorSpace` / `toneMapping` / `PMREMGenerator` / `ShadowMaterial` / `MeshBasicMaterial` / 三盏灯 / `SRGBColorSpace` / `NoToneMapping` / `DoubleSide`/`BackSide` / 其余几何体 / `GridHelper` / `TextureLoader` —— r161~r186 无破坏性变更。
- 未用 `THREE.Source`（r186 改名 `TextureSource`）、未用 `useLegacyLights`、未用 OrbitControls / GLTFLoader / 后处理 / WebGPU。
- r163 起不再支持 WebGL 1 —— 现代浏览器均可，影响可忽略。

### 工程变化：单文件 → 双文件

r186 的 `build/` 已拆分，**不能单文件 vendoring**：`three.core.js`（1,458,113 B，含 `REVISION='186'`）+ `three.module.js`（662,772 B，**`import ... from './three.core.js'`**），合计 **2.02 MB（+67%）**。两文件须同目录，**importmap 条目本身不用改**。

**结论**：值得升、但不紧急，**不建议在 3D 节点打磨中途升**（r160 无安全问题、功能够用；升级必然改观感）。等告一段落再一次性完成「换 2 个文件 + 改 2 处代码 + 重调 `SMART_3D_STUDIO` + 重跑视觉验收」。
