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

### D.2 2026-09-18 清除执行（老板指示「只动项目内的」）

**结论：项目内已无任何真实密钥值；唯一的真 key 在 git 历史且已公开 → 只能轮换。**

已清：
- `API/.env` —— 17 行 key 变量行全部移除（16 个空行 + `MODELSCOPE_API_KEY=ms-token-***` 掩码），
  仅留 `MODELSCOPE_CHAT_MODELS`。**依据**：`main.py:769 provider_key_env()` 由 provider id 拼变量名、
  `:797 provider_env_key_value()` = `os.getenv(k) or read_api_env_value(k)` **按名按需读** →
  应用**不枚举** env 行；`:1451` 的 `has_key` 只对 `api_providers.json` 里已存在的通道求值（该文件 `[]`）。
  HKCU 里也无任何 `API_PROVIDER_*` 变量。
- `data/api_providers.json.bak-20260918` → 回收站（3149→3150 条目）。

未处理（按指示）：HKCU 4 个环境变量、项目外 3 个凭据文件、WorkBuddy 本地记录约 80 个含真 key 的文件
（`logs/` 1.5 GB、`traces/` 813 MB、`projects/` 250 MB、`cache/`、`file-history/`、`models.json`；
其中 `cache/` 可再生、可安全删）。

#### 那枚 key 的全部事实

| 项 | 值 |
|---|---|
| 变量名 / 形态 | `API_PROVIDER_GRSAI_KEY` = **11 位纯数字**（`415…61`）；该文件当时其余 key 全空 |
| blob / 提交 | `b76dd86274`；`9bdb54c`(2026-09-03)、`74b5c8c`(2026-09-16) |
| 远端 | **`origin/main` 含**（`github.com/HanaJhon/Infinite-Canvas`，**Public**）；`upstream/main` 不含 |
| 标签 | **4 个标签全含**：`Infinite-Canvas-for-lochou-Launcher-Beta.V0.1`(2)、`…-V0.1`(1)、`Official.v0.1`(2)、`archive-image2psd-20260917`(2) |

**删历史为何无效**：① 已公开约 15 天，可 clone/fork，无法召回；② GitHub 对已推送对象仍可按 SHA 取一段时间；
③ 4 个标签 + 任何 fork 都持有该对象，清理需 force-push + 重建标签且对 fork 无效。
→ **唯一有效处置 = 轮换**。（该值 11 位纯数字与 Grsai 现行 `sk-` 前缀 35 位格式不符，可能是早期格式/测试值，但仍按已泄露处理。）

#### ⚠️ 本轮最大的方法论坑

**判「密钥」绝不能只认 `sk-` 前缀。** 首轮扫描正则只覆盖 `sk-`/`Bearer`/`AIza`/`xox` 等前缀，
**把 11 位纯数字的真 key 整个漏掉**，得出「历史中无真实密钥值」的**假结论**（差点据此收工）。
→ **`.env` 类文件必须同时按 `NAME=VALUE` 逐行解析**：key 类变量名下的任何非空值都要报出，不管格式。

另两条：① 宽正则 `[A-Za-z0-9]{32,}` 一次 4064 个假命中（几乎全是 32 位 md5）→ 先按前缀收紧再排除纯十六进制；
② **查暴露面别只看分支，必须查标签**（`git log <tag> --find-object=<blob>`）。

报告：`output/API-Key残留清除报告-2026-09-18.md`。

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

### F.6 启动器内置清单漏 GPT 事故（2026-09-17 引入 → 2026-09-20 修复）

**结论：Grsai 无 `/models` 端点，启动器返回的清单是 C# 硬编码的 `GrsaiCuratedModels()`（`launcher/Program.cs` 约 `:904`），
由 `HandleFetchModelsAsync` 的 `IsGrsaiProvider(...)` 短路分支返回（`source="curated"`）。
这份清单**必须与 F.1 的 14 个对话模型保持一致**。**

- **引入**：commit `a94a050`（2026-09-17 17:27）依据一次探测，把 `gpt-6-astra`/`gpt-5.6-terra`/`gpt-5.6-sol`/`gpt-5.5`
  从清单里剔除，注释写「实测返回 400，已剔除」。那次 400 是**上游抖动**（见 F.4 第 3 条）。
  后果：启动器「拉取并自动归类模型」**永远拉不到任何 GPT 对话模型**，只剩 10 个 Gemini。
- **修复**：2026-09-20 串行复测（间隔 1.5s）4 个模型全部 200（18.6~25.2s）；负对照
  `gpt-5.6-luna`/`gpt-5.6`/`gpt-6`/`gpt-5.5-pro`/`gpt-4o` 全部明确 `model not found` → 补回清单并重写注释。
- **前端无需改动**：拉取后 `qe(e.models)` 按关键词归类（视频 17 词：video/runway/gen-3/gen3/gen-2/luma/kling/sora/
  cogvideo/hailuo/minimax-h3/pika/vidu/animate/svd/ltx/hunyuanvideo；图像 13 词：image/flux/dall-e/dalle/sdxl/
  stable-diffusion/midjourney/kolors/paint/draw/diffusion/banana/art；**其余归 chat**）。
  4 个 GPT 名字不含任何 image/video 关键词 → 正确落入「聊天对话模型」。
  ⚠️ 注意 `art` 是图像关键词，但 `astra` 不含 `art` 子串，安全。
- **验证 exe 的技巧**：`csproj` 有 `EnableCompressionInSingleFile=true` → **grep exe 搜不到字符串**（UTF-8/UTF-16LE 都不行）。
  ① 最快：查未压缩的 `launcher/bin/Release/net8.0-windows/win-x64/InfiniteCanvasLauncher.dll`（字符串在 `#US` 堆，UTF-16LE）；
  ② 端到端：解 single-file bundle —— manifest 条目 = `off(8)+size(8)+csize(8)+type(1)+name`，
  **字段区在 name 前 25 字节**（⚠️ type 是 **1 字节**，按 28 对齐读出来全是垃圾），
  `zlib.decompress(d[off:off+csize], -15)` 后校验 `len==size` 且以 `MZ` 开头。
- **提交惯例**：`git log -- Lochou启动器.exe` 只有 2 个提交，**都在发布点**。常规修复默认只提交源码；
  是否把重编的 exe 一起提交需老板拍板（每个 exe blob 约 68.9 MB）。

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
- 节点类型 `smart-image`（=「上传」，**1.1.7 前叫「快速生图」**；中间曾短暂改成「快速执行」，未对外发布）/`smart-group`/`smart-prompt`/`smart-loop`/`smart-minimax`/`smart-3d`（3D预览）/`smart-container`（legacy）。连接 `canvas.connections=[{from,to,kind}]`，`kind` ∈ `input`/`flow`；`node.inputNodeIds` 同步维护。
- ⚠️ **非空节点的 `.node-head`/`.node-title`/`.node-hint` 被全局隐藏**（CSS 574/575/702 行）。**新增非图片节点类型必须显式重新显示**，否则节点名、提示、拖动把手都看不到。同理 `.image-node.selected:not(...)` 长 `:not` 链要补新型号。
- ⚠️ **节点拖拽在 `beginNodeDrag`（`el.onmousedown`）里用「排除选择器」判断**。节点内任何需自吃鼠标事件的区域（如 3D 舞台）必须加进排除列表，否则会被节点拖拽抢走。
- **视觉识别管线已通、无需后端改动**：`POST /api/canvas-llm`（`main.py:3453`）的 `images` 支持 `/output/*.png`、`/assets/*.png`、http(s)、data URL，最多 8 张。
- **three.js 已内置**：`static/vendor/js/three-0.160.0.module.js`（r160）；`static/angle.html` 有现成 importmap 写法。
- **`render()`（`smart-canvas.js:9166`）是节点渲染主入口，147 处调用、无节流** → WebGL 查看器 DOM 必须复用（浏览器上限约 16 个上下文）。

## K. 3D 预览节点界面约定（从 MEMORY.md 下沉）

- **定位**：上游只能是「上传」（`smart-image`），下游也只能是「上传」；与 prompt/loop/group 双向都拒绝（`canAutoConnectDraggedNode()` + `connectInputNode()` 双处硬校验，两处都要改）。
- **生成路线**：上游图片 → `POST /api/canvas-llm`（系统提示词 `SMART_3D_SYSTEM_PROMPT`，`smart-canvas.js:8909`）→ `smart3DParseSceneJson()`（含围栏与尾随逗号容错）→ `normalize3DScene()` → 存进 `node.scene3d`。7 种图元：box/sphere/cylinder/cone/torus/capsule/plane。
- **节点字段**：`scene3d`、`scene3dRaw`（截 20k）、`scene3dError`、`camera`（`{position,target,fov}`，跨刷新恢复）、`scene3dSnapshotUrl`、`model`/`provider`。截图 dataURL 只放内存 `smart3DSnapshotData`，**不进画布 JSON**。
- **FOV 滑块（2026-09-18 加上）**：`.smart3d-bar` 里 `[data-3d-fov]` 范围 20°–90° 步进 1，读数同步显示「XX° · XXmm」（35mm 全画幅等效：`f = 12 / tan(fov/2)`，由 `smart3DFocalMm()` 计算）。滑块 `input` 实时改 `viewer.camera.fov` + `updateProjectionMatrix()` + 脏标记；`change` 写 `node.camera.fov` + `scheduleSave()`（点 `change` 才落盘，避免拖动过程每次 200ms 触发 debounce 风暴）。`apply3DSceneToViewer` 优先用 `node.camera.fov`（覆盖场景默认）；`persist3DCamera` 把 `fov` 一并写入 `node.camera`（拖拽改角后也会落）。绑定事件里要 `stopPropagation` 防节点拖拽抢走；`el.querySelectorAll('[data-3d-provider],...')` 排除链要补 `[data-3d-fov]`。
- **查看器**：`smart3DViewers: Map<nodeId, viewer>`，动态 `import('/static/vendor/js/three-0.160.0.module.js')`，自写环绕（pointerdown/move/up + wheel，无 OrbitControls 依赖），rAF 脏标记渲染，`render()` 后由 `sync3DViewers()` 把 canvas 搬回新舞台。**上限 6 个同时存活**，节点删除即 `dispose3DViewer()`。
- **下游取图**：`outputImagesForNode()` 的 `smart-3d` 分支返回 `node.scene3dSnapshotUrl`；该 URL 由「场景建好后 + 拖拽/滚轮停下后（防抖 520ms）」调 `snapshot3DNode()` → `/api/ai/upload-base64` 刷新。截图 `preserveDrawingBuffer:true`。
- ⚠️ **三个已修的坑**：① 场景字段缺失会让 `spec.rotation[0]` 抛错并拖垮整个查看器 → 应用前必须 `normalize3DScene()` 规范化并写回节点；② `persist3DCamera()` 若直接读 `camera.position`，在环绕角刚改、渲染循环还没跑到时是旧值 → 落盘前先 `apply3DCamera(viewer)`；③ **验证探针里手动 `nodes.push()` 会被异步 `loadCanvas` 覆盖**（onload 后约 3s 才完成 fetch+赋值）→ 注入前必须 `await sleep(3000+)`，或用真实 `create3DNode()` + `scheduleSave()` 让节点走服务端重载。
- **无头 Edge 验证**：必须 `--enable-unsafe-swiftshader --use-gl=angle --use-angle=swiftshader`（`--disable-gpu` 会让 WebGL 兜底直接失效，`hasScene` 假）。虚拟时间三分钟，跑 3D 节点必须用真实 `create3DNode()` 而非手动 push。完整探针写法见 `infinite-canvas-verify` 技能。

### K.1 节点外框布局约定（2026-09-18 定稿）

① `.image-node.smart3d-node` 加 `padding-top:0`，让标题栏贴齐节点顶部（其他节点内缩 12px，3D 节点标题栏必须顶到边）；② **3D 节点必须跳过 `.floating-node-actions` 浮动删除按钮**（渲染模板里加 `&& !is3D`）——标题栏被专门显示后两者会重叠，浮动按钮落在覆盖层下方不可点击；③ **交互说明放在标题栏内，3D 节点不渲染底部 `.node-hint`**：`render()` 里用 `headSub` 把 `<span class="node-head-sub">` 插到 `.node-head` 中、紧跟 `.node-title` 之后，同时把 `hint` 置空并改成条件渲染 `${hint ? '<div class="node-hint">…</div>' : ''}`。⚠️ **`headSub` 必须以 `is3D && smart3DHasScene(node)` 为条件**——空场景/生成失败时那句话（`smart.3dEmptyHint`「连接上传后点生成」）已由舞台中央占位层显示，再放进标题栏就是重复，且生成失败时会显示错误引导。`.node-head-sub` 是 `--faint` 灰色小字（`font-size:10px; font-weight:700; line-height:normal`，与 `.smart3d-meta`/`.smart3d-select`/`.smart3d-run`/`.smart3d-fovval` 同规格），`flex:1 1 auto` 负责顶开右侧删除按钮；对应地 3D 的 `.node-title` 由 `flex:1 1 auto` 改为 `flex:0 0 auto`。腾出的约 25px 高度由 `.node-body{flex:1 1 auto}` 自动吸收，3D 视口随之变高，节点总高不变。

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

## N. 发布打包与更新机制细节（2026-09-20 调研）

### N.1 网页端自更新（已存在，`main.py`）

| 接口 | 位置 | 作用 |
|---|---|---|
| `GET /api/check-update` | `:2432` | 拉远端 `VERSION` 比对 → `update_available` + 更新说明 |
| `POST /api/update-from-github` | `:2915` | 下载 → 暂存 → 校验 → 备份 → 替换 → 可选自动重启 |
| `GET /api/update-backups` | `:3099` | 列恢复点 |
| `POST /api/update-rollback` | `:3108` | 回滚 |
| `GET /api/update-connectivity` | `:2369` | 探测更新源连通性（另有 `/probe`） |

- 白名单 `update_allowed_file()`（`:2479`）= **`main.py` / `VERSION` / `static/**`**，别的一律拒绝。
- 暂存校验 `validate_staged_update()`（`:2768`）：`compile()` 编译 `main.py` + 校验 `VERSION` 格式 + 逐文件存在性。
- 恢复点 `data/update_backups/<时间戳>/`，`manifest.json`（`format:2`、`kind`、`from_version`、`target_version`、`parent_backup`），保留 **10** 个（`UPDATE_BACKUP_RETENTION`）。
- 自重启 `schedule_self_restart()`（`:2620`）：Windows 派生 `_self_restart.bat`（`chcp 65001` + `timeout` + `taskkill /F /PID` + `start` 拉起 `启动服务.bat`/`start.bat`，否则回退 `python\python.exe main.py`），POSIX 派生 `_self_restart.sh`。
- GitHub 侧用 `api.github.com/.../git/trees/main?recursive=1` 取文件树（带 ETag 缓存 600s），文件走 `raw.githubusercontent.com` 下载；支持 `GITHUB_TOKEN` 把限额 60/h 提到 5000/h。
- ModelScope 源：`MODELSCOPE_*`，**当前被 `UPDATE_SOURCE_MODELSCOPE_ENABLED` 禁用**，`normalize_update_source()` 会把任何 modelscope 请求降级为 github。

### N.2 启动器（`launcher/Program.cs`）可复用的能力

- UI = **WebView2** 加载 `dist/launcher/index.html`（React）；原生通信走 `window.chrome.webview.postMessage` + 30s 超时 + `Qe(e,t)` fallback。
- `private Process? server`（`:221`）**已持有 python 服务 PID**；`:1259` 有 `try { if (!server.HasExited) server.Kill(true); } catch {}`。
- `ResolveProjectRoot()` 可定位项目根 → 能直接读 `<root>/VERSION`。
- **零更新逻辑**：grep `VERSION|Version|更新|update|Update` 只命中 WinForms 的 `UpdateFormRegion()` 和注册表 Run 键。

### N.3 版本号现状（三套并存）

| 来源 | 值 |
|---|---|
| `VERSION` 文件 | `2026.09.20`（2026-09-20 由 `2026.08.30` bump，用于发布干净版） |
| git tag | `Official.v1.1`（另有 `Official.v0.1`、`…Beta.V0.1`、`…-V0.1`、`archive-image2psd-20260917`） |
| `main.py:204 APP_VERSION` | `"2026.08.29"`（兜底，与 VERSION 文件不一致） |

建议收敛到 `VERSION` 文件为唯一真相（格式 `YYYY.MM.DD`）。

### N.4 发布包实测分析（`Infinite-Canvas.for.lochou.launcher.Official.v1.1.zip`，798.14 MB）

顶层唯一目录 `Infinite-Canvas/`，3432 条目。体积 top：

| 条目 | 体积 |
|---|---|
| `.git/objects/pack/pack-65e5…pack` | 452.53 MB |
| `.git/objects/pack/pack-c22a…pack` | 75.74 MB |
| `Lochou启动器.exe` | 68.89 MB |
| `assets/output/online_*.png` × 17 | 合计 135.60 MB |
| `assets/input/*` × 6 | 合计 0.71 MB |

含 `.git`（623 条目，含 `refs/heads/main`、`refs/remotes/upstream/*`、`refs/tags/`）、8 个 `data/canvases/*.json`（含 54 KB 的 `7bc696dc…`）、`history.json`。
`API/.env` 已是清理后 1 行（无密钥）；`data/api_providers.json` = `[]`。

### N.5 本地/远端发布资产

| 位置 | 名称 | 体积 |
|---|---|---|
| `D:\工作\无限画布\` | `Infinite-Canvas.for.lochou.launcher.Official.v1.1.zip` | 798.14 MB |
| GitHub Release `Official.v1.1` | 同名 | 836,907,605 B |
| GitHub Release `Official.v0.1`（名称显示 `Official.v1.0`，**tag 与 name 不一致**） | `…Official.v1.0.zip` | 847,084,831 B |
| GitHub Release `…Beta.V0.1` | `Infinite-Canvas-for-lochou-Launcher-Beta.V0.1.zip` | 1,551,677,919 B |
| GitHub Release `…-V0.1` | `Infinite-Canvas-agent-for-lochou-Windows-x86-Portable-v0.1.zip` | 424,023,165 B |

另有本地目录 `D:\工作\无限画布\Infinite-Canvas-agent-main\`（下载的 mufanmu fork 解压副本，含 `dist/InfiniteCanvasLauncher.exe` 68.78 MB）。

### N.6 设计方案要点（完整版见 `output/更新功能设计方案-2026-09-20.md`）

- **不需要安装包**；便携目录 + 自更新。Inno Setup 只在需要快捷方式/卸载项时才做。
- 清单 `update.json` 放 Release 资产，用 **`releases/latest/download/update.json`** 取（**不消耗 API 配额、无需鉴权**）。
- 包分 `delta`（日常，2~15 MB）与 `full`（首次/跨版本）；都带 `size` + `sha256`。**实测 full = 111.40 MB**（见 N.7）。
- **覆盖正在运行的 exe 必失败** → 必须派生独立进程（`.cmd` 或小 `updater.exe`）。
- 替换阶段用 **allow-list**（只复制认识的程序路径），不用 deny-list。
- 回滚复用网页端 `data/update_backups/`，让两处更新共用一套恢复点。
- `API/.env` 只能追加缺失键，**绝不整文件覆盖**。

### N.7 阶段 1 执行细节（2026-09-20）

**提交**：`276623f`（更新源）/ `92305b3`（清上游引流）/ `ebd3420`（`tools/release.py` + VERSION）/ `8d74ae5`（`asset_library.json` 取消跟踪与分发）。

**`tools/release.py` 关键设计**

| 常量 | 内容 |
|---|---|
| `ROOT_FILES` | 22 个根文件（含 `Lochou启动器.exe`、`main.py`、`VERSION`、各平台脚本、`赞赏.png`） |
| `PROGRAM_DIRS` | `static` `dist` `launcher` `tools` `workflows` `tests` `CLI` `packages` `python` |
| `DATA_SHIPPED_FILES` | **只有** `data/inspire_prompt_zh.json`（`asset_library.json` 已剔除，见下） |
| `EXCLUDE_PREFIXES` | `launcher/bin/` `launcher/obj/` `dist/dist/` `tools/__pycache__/` |
| `DENY_PREFIXES` | `.git/` `.workbuddy-ai/` `.claude/` `API/` `assets/` `output/` `data/` |
| `DENY_EXACT` | `history.json` `inspire_image_dims.json` `API/.env` `Lochou启动器.exe.WebView2` |
| `REQUIRED` | `main.py` `VERSION` `Lochou启动器.exe` `static/index.html` `dist/launcher/index.html` |

- **allow-list 是主防线**，deny-list 只作兜底断言 —— deny-list 漏写一项就出事。`build` 时若白名单里出现黑名单路径会**直接中止**（说明清单写错了）。
- zip 条目时间固定 `(2026,1,1,0,0,0)` + `external_attr = 0o644 << 16` → 同内容可复现。
- 增量包：与更早的 `file-hashes.json` 比对，**`changed` 为空不产出**；`removed` 非空**照常产出**，删除清单写进 manifest 的 `deleted`（1.1.3 起，见下「增量更新落地」）。
- `--notes-file` 指定更新说明；不传则从 `CHANGELOG.md` 顶部第一个 `####` 段抓。
- 实测：`list` 2011 文件 / 156.51 MB；`verify` 新包通过、旧包 798 条用户数据路径不通过；`build` 111.40 MB。

**两个真 bug（本次修掉）**

1. **有删除时产出增量包** → 被删的旧 JS/CSS 残留在用户目录与新版本混跑，比不更新更危险。当时改为 `removed` 非空即跳过；**1.1.3 起改为「增量包携带 `deleted` 清单 + 执行器负责删除」**（见下「增量更新落地」）。
2. **`data/asset_library.json` 随包分发** → 它是**素材库索引**（用户新增素材后会被写回），覆盖安装会把它清回空骨架 → 素材文件还在 `assets/library/` 下、索引却没了 = **素材库凭空清空**。而 `load_asset_library()`（`main.py:7913-7917`）在文件缺失时会自建默认库并落盘，本就不需要随包提供。

**增量更新落地（1.1.3，2026-09-20）**

- 触发原因：此前每次更新都下 111 MB 全量包。`release.py` 其实**早已产出** `kind=delta`，但**启动器只认 `full`**、执行器 `UpdateApplier` 还显式拒绝非 full 包 → 增量包从未被用过。
- 三处改动（**缺一即退化回全量**，必须同时成立）：
  1. `launcher/Program.cs`（`HandleCheckUpdateAsync`）：遍历 `packages`，**只在 `VersionUtil.CompareVersion(from_version, current) == 0` 时接受 delta**（跨版本 / 跳过一版必须用 full，否则落点不完整）；优先 delta，无匹配回退 full；响应加 `isDelta`。
  2. `launcher/UpdateApplier.cs`：`kind` 允许 `full|delta`；delta **只覆盖 zip 内条目、绝不剪枝**（剪枝按全量清单删其余文件 → 会把安装清空）；按 `manifest.deleted` 删除被移除文件（受 `ForbiddenRoots` 保护）；`BackupChangedFiles` 新增 `restrictRels` 参数，delta 只备份 zip 内那几个文件（否则把 2018 个文件全备份一遍）。
  3. `tools/release.py`：`build_package_manifest` 增 `deleted` 字段；有变更就产出 delta（含删除场景）。
- ⚠️ **改 `launcher/*.cs` 必须重编 exe**：`dotnet_env.py publish … -o dist` → 复制 `dist/InfiniteCanvasLauncher.exe` 到根 `Lochou启动器.exe`。exe 进包也进 git。
- ⚠️ **delta 体积取决于启动器 exe 是否变化**：exe 是单文件自包含 ~69 MB，只要它变了，delta 也有 ~64 MB（本次 1.1.3 即如此，63.92 MB）；只有 js/css/html/py 变化时才可能小到几 MB。
- ✅ **e2e 取证（3 场景全过，24 项断言）**：① 合成 delta —— 只覆盖变更 / 不剪枝 / 按 `deleted` 删 / 用户数据保留；② 真实 full 回归 —— 覆盖 + 剪枝 + 用户数据保留；③ **真实 1.1.2 完整包解压成安装目录 → 打真实 1.1.3 delta → 2018 个程序文件与 1.1.3 完整包逐字节一致，被移除的 3 个文件已清除，用户 `data/`、`assets/` 原样**。
- 📌 测试执行器必须**复现生产路径**：把 exe 复制成 `<install>/data/_apply_update_<pid>.exe` 再派生（`launchExe` 传空串时 `Relaunch` 只记警告、不影响退出码）。

**混装目录结论（推翻原判断）**

- `assets/` **100% 是用户数据**（`input/` 5 文件 0.71 MB、`output/` 16 文件 135.60 MB，`library/`、`uploads/` 空）→ 整目录排除本来就对，**无需拆分**。
- `data/` 13 文件里 12 个是用户数据（`api_providers.json` 含密钥、`canvases/` 7 个、`chat_*.json`、`projects.json`、`prompt_libraries.json`、`media_previews/`），只有 `inspire_prompt_zh.json`（665 KB）是程序资源 → 只能**逐文件登记**。
- `data/asset_library.json` 已 `git rm --cached` 取消跟踪（`.gitignore` 的 `data/*` 本就忽略它，只有 `inspire_prompt_zh.json` 有 `!` 例外）。**安全做法**：操作前对父目录做「文件名 + 大小 + md5」全量快照，操作后逐项比对，一致才算过；不一致 `git reset -- <文件>` 回滚。备份存 `output/_backup/asset_library.json.bak`。

**上游引流残留（已清）**

- `static/update-notes.json` 原文「此项目已停更，全新版本请前往：DX-OS.com下载。」→ 会被 `read_local_update_notes()`（`main.py:1648`）读取 + 经 `GITHUB_UPDATE_NOTES_URL` 拉取，用户点「检查更新」原样看到。已改写。
- `static/css/api-settings.css` 146 行 `.dx-os-banner` 系列死 CSS（`index.html` 与 `static/js/` 零引用）；孤儿 `static/images/dx-os-logo.svg`。
- ⚠️ **删 CSS 块的坑**：用「找下一个以 `}` 结尾的行」定位块尾会匹配到内层规则的收尾 `}`，少删 1 行留下孤立 `}`；且**搜关键字查不出来**（孤立大括号不含关键字）→ **删结构化文本必须做结构校验**（本次补了括号配平：最终深度 0、最低深度 0）。

**更新源修正范围（易漏）**

后端 4 个 `GITHUB_*` 常量之外，`static/index.html` 另有 4 处硬编码（`:1685` `PROJECT_URL`、`:2240/:2241` 连通性检测兜底 URL、`:2340/:2343` 提示文案），`tools/` 另有 3 处（`chrome-local-asset-importer/{popup,sidepanel}.html` 的按钮 title、`photoshop-asset-connector/js/app.js:399`）。**查更新源必须连前端与 tools 一起查。**

**可达性实测**

```
raw.githubusercontent.com/HanaJhon/Infinite-Canvas/main/VERSION             → 200  2026.09.20
raw.githubusercontent.com/HanaJhon/Infinite-Canvas/main/static/update-notes.json → 200
api.github.com/repos/HanaJhon/Infinite-Canvas                               → 403  rate limit
```
→ 更新流程**不该依赖 GitHub API**；版本比对走 raw 静态文件、清单走 `releases/latest/download/`。

### N.8 阶段 2 实现细节（2026-09-20，提交 `3b40339`）

**执行器 = exe 自身**（`launcher/UpdateApplier.cs`，374 行）

```
<exe> --apply-update <zip> <destDir> <waitPids,逗号分隔> <launchExe>
```
1. 等 PID（120s 超时；超时即中止、不改盘）→ 2. 读包内 `release-manifest.json`
（`kind` 必须 `full`）→ 3. 只备份 sha256 会变的旧文件到
`data/update_backups/<yyyyMMdd-HHmmss>/` → 4. 解压（剥顶层目录 + 路径越界校验）
→ 5. 按 `prune_roots` 剪枝（禁用名单二次防线：`data`/`assets`/`output`/`API`/`.git`/`.workbuddy-ai`）
→ 6. 删包 + 备份保留 10 → 拉起启动器。
日志：`%LOCALAPPDATA%\InfiniteCanvasLauncher\update.log`。

**启动器侧（`launcher/Program.cs`）**

| 项 | 位置/要点 |
|---|---|
| `Main(string[] args)` | `--apply-update` 分支在单实例互斥量**之前**，且不调 `ApplicationConfiguration.Initialize()` |
| `CleanupStaleAppliers(root)` | 启动时删 `data/_apply_update_*.exe`（跑着的那份删不掉，正常） |
| `UpdateManifestUrl` | `https://github.com/HanaJhon/Infinite-Canvas/releases/latest/download/update.json`，⚠️ 与 `main.py` 的 `GITHUB_*` 必须一致 |
| `UpdateAssetBaseUrl` | `.../releases/latest/download/` + asset 名（同样不耗 API 配额） |
| `CompareVersion(a,b)` | 点分数字逐段比 |
| `HandleCheckUpdateAsync` | 读 `<root>/VERSION` + 拉清单 → `{ok,current,latest,updateAvailable,notes,size,sha256,assetName,url}` |
| `HandleStartUpdateAsync` | **立刻返回** `{ok,started}`，`Task.Run(RunUpdateAsync(...))` |
| `RunUpdateAsync` | 下载（`HttpCompletionOption.ResponseHeadersRead` + 256 KB 缓冲 + 百分比推送）→ 校验体积+sha256 → 复制自己到 `data/_apply_update_<pid>.exe` → 派生 → `ScheduleExit(1500)` |
| `PrepareForUpdate` | 杀掉 `server` 进程，返回 `[自己PID, 服务PID]` |
| `SendToWebView(type,payload)` | 通用推送；`SendLog` 是它的特例（`type="LOG"`） |

**包内清单生成（`tools/release.py`）**

- `write_zip(zip_path, files, top, extra)` 的 `extra` 支持虚拟条目
- `build_package_manifest(version, kind, files, hashes)` 产出 `release-manifest.json`
- `MANIFEST_NAME = "release-manifest.json"`；完整包与增量包都带。字段 = `format/version/kind/prune_roots/files/deleted`。增量包带**全量** `files`（供备份判断）但**不剪枝**；`deleted` 列出本版已移除、要由执行器删除的文件。
- ⚠️ `cmd_build` 里**不要**再写局部 `import json`（会遮蔽模块级，触发 `UnboundLocalError`）

**前端（`E:\claude\skill\canvas-launcher`）**

- `App.tsx`：设置弹窗内「软件更新」区块 + `updateInfo`/`updatePhase`/`updatePercent` 状态
  + `UPDATE_PROGRESS` 监听 + `handleCheckUpdate`/`handleStartUpdate`；模块级 `formatBytes()`
- `nativeBridge.ts`：`getMockNativeResponse` 补 `UPDATE_CHECK`/`UPDATE_START`（浏览器预览用）
- 设置弹窗容器加 `max-h-[86vh] overflow-y-auto`（新增区块后防溢出）
- bundle `index-Bm2vKWq7` → `index-D8EkQHII`

**端到端实测脚本要点（可复用）**

- ⚠️ **applier 用完会删包** → 必须复制副本再测，不能拿真产物测
- 假安装目录要同时放：会被覆盖的旧程序文件、程序目录里的旧残留、以及
  `data/canvases/*`、`data/api_providers.json`、`data/asset_library.json`、
  `assets/output/*`、`assets/input/*`、`API/.env`、`history.json`、`output/*` 等用户数据
- 校验六件事：用户数据 md5 未变 / 程序文件 sha256 == 清单 / 残留被删 /
  备份内容 == 旧版 / 包被删 / 全量 2011 文件哈希一致
- 传空字符串当 `waitPids`（无等待进程）；`launchExe` 指向不存在的路径以跳过真实拉起
- 构造假安装目录时注意**别复用同名目录变量做 rmtree**（踩过：把刚复制的测试包删了）

---

### N.9 启动器胶囊更新入口（2026-09-20，提交 `9e0b1e6`）

**位置**：首页 hero 横幅左上角那颗胶囊 `Infinite Canvas for Lochou Launcher [V…]`。

**C# 侧（`launcher/Program.cs`）**

| 项 | 内容 |
|---|---|
| `GET_VERSION` | 消息 switch 里新增，紧挨 `UPDATE_CHECK` 之前。返回 `{ok:true, version: LocalVersion()}` |
| 为什么单独加 | `LocalVersion()` 只读 `<root>/VERSION`，**不走网络**。胶囊版本号要即时显示，`UPDATE_CHECK` 有 25s 超时且断网为空 |

**前端（`E:\claude\skill\canvas-launcher\src\App.tsx`）**

| 项 | 内容 |
|---|---|
| 类型 | 模块级 `export type UpdateInfo` / `UpdatePhase` |
| `UpdateSection` | 模块级组件（不是 App 内联），props：`info/checking/phase/percent/error/onCheck/onStart/showHeader?`。设置弹窗与首页浮层**共用** |
| `runUpdateCheck(silent)` | `silent=true` 时不显示 loading、不把网络错误写进 `updateError`，但结果照常 `setUpdateInfo` |
| 启动自动检查 | 挂载时 `GET_VERSION` → `setAppVersion`，再 `runUpdateCheck(true)` |
| `appVersion` | 本地版本，`displayVersion = updateInfo?.current || appVersion` |
| `versionBadgeRef` | 指向胶囊外层 `div.relative.inline-flex`（红点是它的兄弟节点） |
| `anchorPanelTo(el)` | `left = clamp(12, r.left, innerWidth - 400 - 12)`，`top = r.bottom + 10` |
| 浮层 | `fixed z-[60] w-[400px]`；遮罩 `fixed inset-0 z-[55]` 点击关闭；ESC 关闭；`resize` + `scroll(capture)` 重新贴合 |
| 红点 | 两个 `<span class="absolute -top-0.5 -right-0.5 w-3 h-3 rounded-full bg-red-500">`，一个带 `animate-ping` |
| `nativeBridge.ts` | `getMockNativeResponse` 补 `GET_VERSION` |

**bundle 演进**：`index-D8EkQHII` → `index-BGiB8RcL`（首版）→ `index-V7XPP4EC`（加钳制后定稿）。

**端到端实测：在无头浏览器里驱动 WebView2 托管的 SPA**

1. 复制 `dist/launcher` 到临时目录（**不要**在真 `dist/launcher` 里加探针文件 —— `sync_verify.py check`
   会把 `index-*.js` 残留算成异常）。
2. 复制 `index.html` 当探针页，在 `<script type="module">` **之前**注入假的 `window.chrome.webview`：
   ```js
   var listeners = [];
   window.chrome = { webview: {
     addEventListener: (t,h) => { if (t==='message') listeners.push(h); },
     removeEventListener: (t,h) => { var i=listeners.indexOf(h); if(i>=0) listeners.splice(i,1); },
     postMessage: (msg) => {
       var payload = { requestId: msg.requestId, success: true, result: CANNED[msg.type] || {}, error: null };
       setTimeout(() => listeners.slice().forEach(h => h({data:payload})), 0);
     }
   }};
   ```
   → 走的是**真实 `callNative` 路径**（不是 `nativeBridge` 的 mock，那个写死 `updateAvailable:false`，
   永远看不到红点）。用 `?nou=1` 切「已最新」态。
3. 量完把结果塞 `document.title = 'TAG=' + JSON.stringify(out)`，`--dump-dom` 后
   `re.search(r'<title>TAG=(.*?)</title>')` + `html.unescape` + `json.loads`。
4. 探针里注入 `*{transition:none!important;animation:none!important}`（`--virtual-time-budget`
   不推进 transition，且关掉 `animate-ping` 反而让红点稳定可见）。

**两条必记的坑**

- 🚨 **Tailwind 4 的计算色是 `oklch()`/`oklab()`**，不是 `rgb()`。判色必须用 canvas 归一化：
  ```js
  var cv=document.createElement('canvas'); cv.width=cv.height=1;
  var ctx=cv.getContext('2d');
  function toRgb(c){ ctx.clearRect(0,0,1,1); ctx.fillStyle='#000'; ctx.fillStyle=c;
    ctx.fillRect(0,0,1,1); var d=ctx.getImageData(0,0,1,1).data; return [d[0],d[1],d[2],d[3]/255]; }
  ```
- ⚠️ **侧栏折叠时设置按钮没有文字**，`aside button:last-of-type` 会命中导航里最后一个按钮
  （切走 tab），要按 `svg` 的 `lucide-settings` 类找。

**断言清单**：胶囊文本含 `V` + 本地版本、不含 `V0.1`；红点数量 ≥1 且
`right ≥ badge.right-3 && top ≤ badge.top+4`；浮层 `width===400`、`top - badge.bottom === 10`、
`left ≈ badge.left`、完全在视口内；有更新态含「有新版本/立即更新」，已最新态不含「立即更新」；
ESC 与遮罩均可关闭；设置弹窗里「软件更新」叶子节点**只出现 1 次**（复用组件没重复渲染）。

---

### N.10 真实发布包端到端验证（2026-09-20，提交 `d470724`）

**脚本骨架**（跑完即删，放 `output/`）：`_e2e_real_pkg.py`

```python
# ① 假安装目录：旧程序文件 + 用户数据 + prune_roots 内的旧残留
OLD_FILES  = main.py / VERSION / static/index.html / tools/release.py / data/inspire_prompt_zh.json
USER_DATA  = data/api_providers.json(含假 key) / data/canvases/*.json / data/asset_library.json /
             data/keepme.json / history.json / assets/output/*.png / assets/input/*.png / API/.env /
             output/*.png / my_notes.txt(根目录)
STALE      = static/js/obsolete.js / tools/gone/old.txt / launcher/obsolete.dll /
             dist/launcher/assets/index-OLDHASH.js / python/old_pkg/stale.py
# ② 读真实包清单后 **必须关掉 ZipFile**（见坑 1），再把包复制到测试目录
# ③ 把真实 exe 复制成 <install>/data/_apply_update_999999.exe，用**它**跑：
#    [applier, "--apply-update", pkg, install, "", ""]     ← 空 waitPids / 空 launchExe
#    （Relaunch 对不存在的 launchExe 有兜底，只会记一条 warning）
# ④ 断言 A~I（见下）
```

**断言清单**

| 编号 | 内容 |
|---|---|
| A | 用户数据 10 项 md5 全部未变 |
| B | 清单里全部文件就位且 sha256 一致（缺失 0 / 不符 0） |
| C | `prune_roots` 内的旧残留全部被剪 |
| D | `prune_roots` 外的文件（根目录 `my_notes.txt`、`data/keepme.json`）未被误删 |
| E | 随包资源 `data/inspire_prompt_zh.json` 已更新 |
| F | 备份目录存在、被覆盖文件都备份了、备份内容 == 旧版、有 `apply-info.json` |
| G | 更新包已被删除 |
| H | 退出码 0 |
| I | **`<install>/Lochou启动器.exe` sha256 == 包内 exe** ← 这条才是核心 |

实测 15/15，耗时 46.9s（111 MB / 2012 文件）。

**清理逻辑单独验**（`_e2e_cleanup.py`）：启动真 exe 12s 后杀掉，检查
`data/update_download/` → `*.part` 已删、5 天前 zip 已删、**刚下完的 zip 保留**、用户数据未动。

**坑（都踩过）**

1. 🚨 **测试脚本自己开着 `ZipFile` 句柄会让执行器的删包静默失败** → 断言 G 假失败。
   读清单一定用 `with zipfile.ZipFile(p) as z:`，**跑执行器之前句柄必须已关闭**。
2. ⚠️ **验证「代码是否进 DLL」要分清两个元数据堆**：
   - 字符串**字面量** → `#US` 堆，**UTF-16LE**（如 `'已有一个更新正在进行中'.encode('utf-16-le')`）
   - **方法名** → `#Strings` 堆，**UTF-8**（如 `'IsUpdateInProgress'.encode('utf-8')`）
   搜方法名用 UTF-16 会 MISS，**别据此判定「没编进去」**。
3. **跨类调用**：`LauncherHost` 调 `Program` 的静态方法，被调方必须 `internal`
   （`private static` → CS0122）。
4. `shutil.rmtree` 删 2012 文件 + WebView2 目录（191 文件）会被 SIGTERM 打断 →
   **放后台任务跑**，加 `onerror` 重试。
5. 顺带确认 exe 能起 WebView2（用户数据目录 `<exe名>.WebView2` 会生成上百个文件），
   可用于判断「不是启动即崩」。



### N.11 版本号规则与双端规范化（2026-09-20，提交 `36051f0`）

**规则（唯一一条）**：三段式起于 `1.1.1`，**每多进一级就少一段**（段数 3→2→1，只减不增）。
首段满 10 **不再进位**。

| 输入 | 输出 | 说明 |
|---|---|---|
| `1.1.9` → bump | `1.2.0` | 末段满 10 → 中段 +1、末段归 0，**保持三段** |
| `1.1.10` → normalize | `1.2.0` | 同上（老板原话的写法） |
| `1.9.9` → bump | `2.0` | 中段也满 → 首段 +1，**丢掉归零的末段**（缩成两段） |
| `1.10.0` → normalize | `2.0` | 同上（老板原话的写法） |
| `9.9` → bump | `10` | 首段满 10 → 缩成一段，**继续迭代** |
| `10` → bump | `11` | 不再进位 |
| `1.10.10` → normalize | `2.1` | 先处理末段、再处理中段 |
| `10.0` → normalize | `10` | 首段溢出截断，丢掉右边归零段 |
| `2026.09.20` → normalize | `2026.09.20` | 日期制遗留**原样保留**，不换算（否则变 `2027.1`） |

**状态机**

```
parts = [a,b,c]
loop:
  over = [i for i,x in enumerate(parts) if x >= 10]
  if not over: break
  i = over[-1]                          # 取最靠右的溢出位
  if i == 0: parts = parts[:1]; break   # 首段溢出 → 截断，不再进位
  carry, parts[i] = divmod(parts[i], 10)
  parts[i-1] += carry
  if i < len(parts)-1: parts = parts[:i+1]   # 丢掉右边已归零的段
```

200 步连续进位实测：严格递增 ✓ / 规范式幂等 ✓ / 段数只减不增 ✓。
节点：第 8 版 `1.1.9` → 第 9 版 `1.2.0`；第 19 版 `1.3.0`；第 89 版 `2.0`；
第 169 版 `10`；第 170 版 `11`；第 200 版 `41`。

**文件分工**

| 文件 | 职责 |
|---|---|
| `tools/versioning.py` | 规则**单一权威**：`parse_version` / `is_legacy_date` / `normalize_version` / `bump_version` / `is_canonical` / `load_vectors` / `run_selftest` |
| `tools/version_vectors.json` | Python + C# **共用** 32 条向量（normalize 16 / bump 16） |
| `tools/bump_version.py` | CLI：`--dry-run` / `--times N` / `--set X` / `--self-test`；`newline="\n"` 防 CRLF |
| `launcher/VersionUtil.cs` | C# 等价实现（`internal static`）：`IsLegacyDate` / `ParseVersion` / `NormalizeVersion` / `CompareVersion` |
| `main.py` | `version_rules()` 动态导入 `tools/versioning.py`（取不到 tools/ 退回原样返回）；`current_app_version()` 规范化 |
| `tools/release.py` | `VERSION_RE = ACCEPTED_RE`；`read_version()` 非规范式**自动折算并写回 VERSION** |

**为什么必须规范化**：`VERSION` 写 `1.1.10` 而 `update.json` 写 `1.2.0` → 用户装完新版
`VERSION` 仍是 `1.1.10` → 比对永远「有新版」→ **更新死循环**。

**跨版本体系判定必须对称**（`main.py:check_update()` / `Program.cs:HandleCheckUpdateAsync`）：

```python
if is_legacy_date(current) != is_legacy_date(remote):
    update_available = not is_legacy_date(remote)   # 只认「远端是新方案」这一个方向
else:
    update_available = version_gt(remote, current)
```

⚠️ 最初写成**不对称**（`version_gt(...) or (is_legacy_date(current) and not is_legacy_date(remote))`）
→ 远端 `2026.08.30` 数值恒大于 `1.1.1` → **误报「有新版本」**。6 象限交叉验证后修正。

**验证方式**：C# 自测项目**直接把生产源编进来**
（`<Compile Include="../../launcher/VersionUtil.cs" />`），测的是真实现而非副本 → 45 条向量全过。

**`read_notes_file()` 章节过滤**：更新面板把每条渲染成圆点，「升级方式」章节的正文混进去会
**冒充新功能**（实测 9 条里 3 条是升级说明）。只跳过**认识的**标题关键词
（`升级`/`安装`/`下载`/`注意`/`说明`/`upgrade`/`install`/`download`/`notes`），
**不认识的标题一律保留**（宁可多显示也不悄悄漏真实条目）。

🚨 **发布说明有「两个数据源」，发版时必须同步改，否则两条展示路径不一致**：
| 数据源 | 谁读它 | 生效位置 |
|---|---|---|
| `static/update-notes.json` | `main.py` 的 `read_local_update_notes()` + `GITHUB_UPDATE_NOTES_URL` | **网页端**更新面板（进包） |
| `output/RELEASE_NOTES-<版本>.md`（`--notes-file`） | `release.py` → 写进 `update.json` 的 `notes` | **启动器**更新面板（走 Release 资产） |

- 只改一个 → 网页端与启动器显示的更新内容**不一样**。
- 两边的「本次更新」条目应逐条对齐；md 里保留 `## 升级方式` 独立标题（正文会被过滤掉）。
- `update-notes.json` 的 `updated_at` 与 `version` 也要同步改（`version` 必须 == `VERSION`）。


## D.3 扫描器自噬事故与规则补强（2026-09-20）

### 事故：`tools/scan_secrets.py` 自己成了泄漏源

为说明 `ENV_LINE` 的假阴性 bug（`\s` 吃换行），把真密钥**原样抄进了本文件第 37~38 行的注释**。
该文件随发布包分发 → 用户拿到的包里带着一枚真密钥。

**为什么既有防线全都漏了**：
| 防线 | 为何失效 |
|---|---|
| `release.py verify` | 只做**路径** deny-list 断言；密钥是**内容**问题 |
| `scan_secrets.py --staged` | `ALLOW_FILE` 里含 `scan_secrets.py` → **它从不扫自己** |
| `ENV_LINE` 规则 | 只在**行首**匹配；注释行以 `#` 开头 → 行内 `KEY=数字` 完全看不见 |

**三处修复**：
1. 注释改掩码 `415***561`；加硬规则：**写注释/文档/日志一律用掩码值**。
2. `ALLOW_FILE` 移除 `scan_secrets.py`（实测它**并不自匹配**：`sk-`/`AKIA` 等前缀在源码里
   后面跟的是 `{20,}` 这类正则元字符，凑不满长度下限）。
3. 新增 `KEYED_NUMBER` 规则 —— 抓**行内**（含注释）的「键名=数字」，不受占位符豁免影响：
   `(?i)[A-Za-z0-9_]{0,32}(?:key|token|secret|password|passwd|credential)[A-Za-z0-9_]{0,32}[ \t]*[:=][ \t]*['\"]?(\d{10,32})['\"]?(?![0-9])`

### 我自己把密钥又提交进了 git 历史（诚实记录）

全量扫（`rev-list --objects --all` + `cat-file --batch`，6571 对象）→ **6 个 blob 含该 key**：
`API/.env`（原有）、`tools/scan_secrets.py` × 3 blob（提交 `8e522e1`/`e04d0b9`/`cd2ebe3`）、
`.workbuddy-ai/memory/2026-09-20.md` × 2 blob（提交 `0a6308c`/`34b166d`）。
→ 该 key **已失效 + 已公开 17 天**，无新增实际风险；已推送公开仓库，按既定决策 fix-forward。

📌 **通用教训**：`ALLOW_FILE` 这类「豁免自身」的设计，会让**扫描器/校验器本身成为盲区**。
新增任何豁免都要问一句：「豁免对象自己出问题，谁来看见？」

## N.12 发布包安全审计闸（`tools/scan_release.py`，2026-09-20，提交 `ab03d8d`）

`release.py build` 写完完整包后**自动调审计，不通过即中止**（不再产出脏包）。

```
python tools/scan_release.py <zip 或 目录>
python tools/scan_release.py --selftest      # 只跑正控
```

- **两把尺子**：① 复用 `scan_secrets` 规则（env 行 / JSON 字段 / 已知前缀 / Bearer / 行内 KEY=数字）；
  ② 独立规则集（ASSIGN / HEADER / BEARER / NUMKEY / RANDOM），覆盖 `const KEY = "xxx"` 这类盲区。
- **结构断言按「内容」判**，不按路径 —— 否则会误报：
  - `python/Lib/site-packages/certifi/cacert.pem` = **公共根证书库**（删了 HTTPS 就崩）→ 必须保留；
  - `static/runninghub/api_providers.json` = **程序内置 RunningHub 预设模板**（`chat_models` 为空、无密钥字段）；
  - 真私钥改按 `-----BEGIN … PRIVATE KEY-----` **内容**判。
- 🚨 **内置正控**：先证明规则量得到已知密钥，否则 0 命中作废（防「`\s` 吃换行」那类假阴性）。
  **正控样本必须运行时拼装**（每段 <32 字符）—— 第一版写字面量，立刻被自己的闸拦下 6 处命中。
- 熵启发式（`RANDOM`）**只对第一方代码生效**，跳过 `site-packages/` 与 `static/vendor/`
  （那里全是 SPDX 许可证 id、base64 文档示例、压缩 JS —— 2026-09-20 逐个核实过）。

**2026-09-20 实测基线**（`Infinite-Canvas-Full-1.1.1.zip`）：
2020 条目 / 111.53 MB / sha256 `60f02db9…2d0d`；结构 0 / 密钥 0 / 正控 8 项有效。

---

## O. 补充事实（2026-09-20 精简 `MEMORY.md` 时下沉，原先只在索引里）

### O.1 发布包体积数字（N.4 / N.12 的对照值）

- 工作目录整包压缩 = **798.14 MB**（含 **528 MB `.git`** + 作者画布 + `history.json` + 个人图片）—— 这就是「绝不能整包压缩」的事故样本。
- 干净发布包基线：工作目录 **156.64 MB** → 包 **111.53 MB**（2019～2020 条目）。
- `dotnet publish -o dist` 会在 `dist/` 写进 **68.91 MB 的重复 exe** → 若不排除，包会**虚涨到 175 MB**。

### O.2 `CleanupStaleDownloads()` 的清理规则

`TryDelete` 是**静默**的（失败不报错），所以必须有一个兜底清扫：

- `*.part` → **无条件删**（都是没下载完的残片）；
- `*.zip` → **只清 2 天前的**（保留刚下好、可能还没解包的包）。

### O.3 工具会话 `git push` 挂起的复测记录

2026-09-20 复测：加 `GIT_TERMINAL_PROMPT=0` / `GCM_INTERACTIVE=never` 后**仍然 1 分 39 秒零输出**。
→ 结论不变：**推送必须老板本人在终端执行**（本机常驻 GitHub Desktop，点 **Push origin** 最省事）。

### O.4 `.workbuddy-ai/memory/` 取消 git 跟踪（2026-09-20，提交 `133109b`）

- 弯路：`b098299` 曾被 `git reset 1b5a734` 撤销 → `adad117` 又把内容推回了公开仓库。
- **四重验证**：父目录快照比对 + `git rm --cached` + **`git ls-files` 反查跟踪状态归零** + `git check-ignore`。
- 🚨 教训：**`git status` 干净 ≠ 意图达成**，必须**反查「跟踪状态」本身**；**`.gitignore` 对已跟踪文件无效**。
- 要恢复共享：`git add -f .workbuddy-ai/memory/`。本目录是**项目数据不是缓存，不要删**。

### O.5 2026-09-20 Web UI 改版（logo + favicon）

- 需求：把 `http://127.0.0.1:3000/` 的**页面 logo 与标签 logo（favicon）换成启动器图标**。
- 做法：`static/images/logo.png` ← `launcher/dist/icon.png` 的**逐字节副本**（256×256，md5 `4ecab922…`）；旧文件（150×150，md5 `903c38f6…`）备份在 `output/logo-backup/logo.png.bak`。
- `static/index.html` 的 `.logo-ring` 由「描边圆环 + 中心小圆点」改为 **`<img class="logo-mark">`**；原 `#logo-dot` 保留为**右下角标**（队列忙碌指示）。
- ⚠️ **favicon 必须先手加一个 `?v=` 种子**（本项目 11 处 `<link rel="icon">`）。
  **更正（2026-09-20 读源码后）**：`sync_static_html_versions()`（`main.py:1772`）分两步 ——
  ① `versioned_static_html()`（`main.py:1752`）的正则**只匹配 `/static/**.(js|css|html)`**，会给它们**自动补或替换** `?v=<VERSION>.<mtime>`；
  ② 随后再跑 `re.sub(r'([?&]v=)[^"\'`\s<>)]*', …)`，**无条件替换所有「已存在」的 `?v=`，不限扩展名**。
  → 所以 `.png` / `.svg` / 字体这类**只有原本就带 `?v=` 时才会被跟着刷新**；**首次不加就永远是 `Last-Modified` 启发式缓存**（这才是「换了 favicon 不生效」的真因，不是「服务端不管 `.png`」）。
  实测：手写 `?v=1.1.1` 的 11 处 favicon，在升版到 1.1.2 重启后**自动变成 `?v=1.1.2`**。
- ⚠️ **`static/css/theme.css` 的暗色覆盖会反向压掉新设计**：原 `#logo-dot{background:#d8dee9 !important}` 会让「排队蓝点」失效 → 改成 `.logo-ring:not(.is-queue-busy) #logo-dot`。
- 顺手修掉一个旧 bug：固定态（`.is-pinned`）曾把圆点 `scale(1.35)` → 溢出色环。

### O.6 Codex 权限开关（agent 装 / 用 Skill）

- 根因：`main.py:run_codex_cli()` 把 `--sandbox workspace-write` **写死**，而 Codex 的 `workspace-write` 沙箱**默认禁网** → agent 无法 `npx skills add …` 安装/使用 Skill。
- 方案：按 `data/codex_permissions.json` 的 `level` 拼参数，4 档：

  | level | 沙箱 | 联网 | 额外可写目录 |
  |---|---|---|---|
  | `read-only` | `read-only` | ✗ | — |
  | `workspace-write`（默认） | `workspace-write` | ✗ | — |
  | `workspace-write-network` | `workspace-write` | ✓ | `~/.codex`、`%APPDATA%/npm`、`%LOCALAPPDATA%/npm-cache`（仅取存在的） |
  | `danger-full-access` | `danger-full-access` | ✓ | — |

- 关键实现：`main.py` 的 `CODEX_PERMISSION_LEVELS` / `codex_permission_args()` / `load_codex_permission()` / `save_codex_permission()`；`GET|POST /api/codex/permissions`（非法 level → 400）。
- 联网档拼的是 `-c sandbox_workspace_write.network_access=true` 与 `-c sandbox_workspace_write.writable_roots=[...]`（官方配置键，见 codex config-reference）。
- ⚠️ **TOML 数组用单引号字面量**（`['C:\a\b']`）—— 规避 Windows 反斜杠转义；含单引号的路径**安全剔除**。已用 `tomllib` 往返验证逐字一致。
- ⚠️ **不改用户的全局 `~/.codex/config.toml`**，一律用 `-c` 覆盖；该文件里有**明文 bearer token，绝不复制/提交/回显**。
- 前端：`static/api-settings.html` 的 `#codexCliPanel` 内新增 `.codex-perm` 区块 + `static/js/api-settings.js` 的 `loadCodexPermission()` / `onCodexPermissionChange()`。
- 🚨 **该面板只在选中 `protocol=codex` 的 provider 时才显示** → 用户要先点 **「GPT CLI」快捷按钮**添加（`addCliProvider('codex')`）才看得到开关。`data/api_providers.json` 为空时看不到，**不是 bug**。
- 📌 `data/*` 已被 gitignore → `codex_permissions.json` 不进 git、也不在发布包 allow-list 内。
- 📌 项目 Python 是 **3.10.11 → 没有 `tomllib`**（3.11+ 才有）→ 相关校验脚本要用托管 Python 3.13 跑；**项目代码本身不依赖 tomllib**。

### O.7 无头 Edge 探针：`--virtual-time-budget` 会冻住 CSS transition（重要更正）

- 症状：探针里 `getComputedStyle(dot).opacity` 恒读 `0`，`getBoundingClientRect()` 恒读 `scale(.6)` 的尺寸（9px 读成 5px）—— 连**内联 `style="opacity:1"` 都读成 0**。
- **真因**：`--virtual-time-budget` 下 **CSS transition 不推进**，元素被冻在 **from 值**。
  → 此前记的「无头里 `getComputedStyle` 不可信」是**误判**，它读的是**真实的冻结值**。
- ✅ 解法：往**被测文档**注入 `*,*::before,*::after{transition:none !important;animation:none !important;}`，过渡立刻到位，尺寸/颜色都能量准。
- 📌 判别顺序：先量**截图像素**（dpr=1 时 1 CSS px = 1 设备 px），再用 DOM 交叉验证。
- 📌 另一坑：`--dump-dom` **不含 iframe 内容** → 量 iframe 内部要用**同源父页 iframe + `f.contentDocument`**，把结论写进父页 `title`/`<pre>` 再 dump。
- 📌 **要验证「应用自己的代码路径」就 `f.contentWindow.fetch` 打桩**：例如让 `/api/queue_status` 返回 `{position:2,total:3}`，让 `index.html` 自己的 `syncStatus()` 去加 `is-queue-busy`。
  ⚠️ **手动加类取证无效** —— `setInterval(syncStatus, 2000)`（`index.html:1903`）在无队列时会**主动把它摘掉**。

### O.8 零散小事实（原先只在 `MEMORY.md` 里，2026-09-20 下沉）

- `.gitignore` 已把密钥文件扩成三条：**`.env` / `.env.*` / `*.env`**（配合 D.3 的预防三件套）。
- 主题模块是 `window.StudioTheme`（`static/js/theme.js`）：`StudioTheme.get()` 取当前主题；`index.html:1908` 的 `syncThemeToFrame(iframe)` 负责把主题同步给 iframe；语言变更事件是 `studio-lang-change`。
- `static/index.html` 的 `--studio-ui-scale` 默认 **0.9167**（`index.html:171` 用 `zoom` 施加）→ 量 DOM 时 36px 的盒子会读成 **33px 物理像素**，**这不是 bug**。

## P. 2026-09-20 下沉：启动器高分屏圆角 + agent 本机工具

### P.1 启动器圆角在高分屏（4K）下锯齿（提交 `5a1d054`）

- **本机是 Windows 10 build 19045**（不是 Win11）→ `DwmSetWindowAttribute(hwnd, 33, DWMWA_WINDOW_CORNER_PREFERENCE)` 在 Win10 上是**空操作**，圆角**完全**靠 `SetWindowRgn(CreateRoundRectRgn(...))`。而 Region 是 **1 位掩码、没有任何抗锯齿** → 天生台阶状。
- 第二个（更关键的）问题：`CornerRadius = 24` 是**写死的设备像素**，且被当**直径**用 → 实际半径 12 设备像素。**实测本机缩放 175%**（`GetDpiForWindow = 168`）→ 12 设备像素 = 6.9 逻辑像素，圆角又小又毛糙。
- 第三个问题：csproj **没有** `ApplicationHighDpiMode` → .NET 默认 `SystemAware`，在非系统 DPI 的显示器上会被 Windows 整体位图拉伸（文字发虚、圆角被放大成块状锯齿）。
- 修复（3 处）：
  1. `launcher/InfiniteCanvasLauncher.csproj` 加 `<ApplicationHighDpiMode>PerMonitorV2</ApplicationHighDpiMode>`。
  2. `launcher/Program.cs`：常量改 `CornerRadiusDip = 12`（逻辑像素），`UpdateFormRegion()` 里 `diameter = round(CornerRadiusDip * DeviceDpi / 96) * 2`。
  3. 构造函数订阅 `DpiChanged` → 跨显示器时重算区域。
- 实测取证：启动启动器 → `GetProcessDpiAwareness` = **2 (PER_MONITOR_DPI_AWARE)**（修复前 SystemAware=1）；`GetDpiForWindow` = **168（175%）**；窗口 1100×620。圆角圆弧 12 设备像素 → 21 设备像素。
- ⚠️ **没能在无头/后台环境里截到启动器窗口**：`PrintWindow` 对 WebView2（DirectComposition）返回全黑；`SetWindowPos(HWND_TOPMOST)` + 屏幕抓取仍抓到的是前景的 Photoshop（z 序抢不到）。**结论：启动器的视觉验证只能由老板本人看**，别在这上面耗时间。
- ⚠️ **`ApplicationHighDpiMode` 不进 exe 内嵌清单**（它是喂给 WinForms 源生成器的「编译器可见属性」，生成的是 `ApplicationConfiguration.Initialize()` 里的**运行时调用**）→ 「grep 清单没有 dpiAwareness」**不能**作为「没生效」的证据，必须实跑 `GetProcessDpiAwareness`。
- 同批改动：`static/index.html:8` `<title>AI Studio</title>` → `<title>Infinite Canvas for Lochou</title>`（全项目只有这一处；其余 11 个 html 的 title 是各功能页自己的名字）。

### P.2 agent 本机工具：实现要点（提交 `bd1e576`）

- 背景：「agent」原本 = `POST /api/chat/agent`，只做**意图判定**（chat / 生图 / 改图），**无工具调用**。终端能力**只**在 provider 为 `protocol=codex` 时经 `run_codex_cli`（`main.py:5599`）存在。
- 老板选 **A 原生工具循环**（不引入 agent-zero，无 Docker 依赖）。
- 后端结构（`main.py`，插在 `codex_permission_payload()` 之后）：
  - `AGENT_TOOL_SPECS`（4 份 spec，含 `label`/`desc`/`parameters`）→ 同时供 `agent_tool_schemas(level)`（**OpenAI tools 格式**）与 `agent_tools_payload()`（前端清单）使用。
    🚨 **取名字必须用 `item["function"]["name"]`**，不是 `spec["name"]` —— 踩过 `KeyError: 'name'`。
  - 常量：`AGENT_TOOL_OUTPUT_LIMIT=12_000`、`AGENT_TOOL_READ_BYTES=200_000`、`AGENT_TOOL_SHELL_TIMEOUT=120`（上限 600）、`AGENT_TOOL_PATH_MAX=4096`、轮数默认 8 / 上限 20。
  - `agent_allowed_roots()` 返 `None` = 不限制（仅 `danger-full-access`）；否则 `[BASE_DIR]`（+ network 档的 extra roots）。`agent_resolve_path()` 越界 → `HTTPException(403)`。
  - `agent_decode_bytes()`：UTF-8 → GBK → replace（**Win10 `cmd.exe` 输出是 GBK**）。
  - `agent_tool_run_shell()` 用 `asyncio.create_subprocess_shell` + `wait_for(timeout)`；超时 kill 并返回 `命令超时（Ns 未结束）`。
  - `run_agent_tool()` 统一把任何异常转成 `ok=False`，**绝不打断对话**。
- tool-calling 循环 `build_chat_text_reply_with_tools()`（插在 `build_chat_text_reply` 之前）：
  - `for round_index in range(rounds + 1)`：请求 → 有 `tool_calls` 就执行并回灌 → 再请求；否则返回文字。
  - 回灌格式：`{"role":"assistant","content":…,"tool_calls":[…]}` + 每条 `{"role":"tool","tool_call_id":…,"content":…}`。
  - 达到上限时返回提示文案 + 已收集的 `tool_events`。
- **优雅回退** `agent_tools_unsupported(body)`：上游 400 且消息含 `not support`/`unsupported`/`unrecognized`/`unknown`/`invalid`/`unexpected` → 清空 `tools` **对同一轮重试**（不消耗轮次、不报错）。
- 接口 `GET|POST /api/agent/tools`（`enabled` / `level` / `max_rounds`）；设置存 `data/agent_tools.json`（gitignore 内，不进包）。
- 前端 `static/gpt-chat.html`：
  - 输入区「本机工具」按钮 + 浮层（总开关 / 四档权限 / 轮数 / 可用工具胶囊）；助手气泡内 `<details class="tool-call">` 可折叠卡片（参数 / 输出 / 错误态 `.is-error`）。
  - `msg.tool_events` 随消息**落库**（刷新后仍在）；`applyLanguage` 与 `studio-lang-change` 都要 `renderAgentTools()` + 重画含 `tool_events` 的消息。
  - 🚨 **`.composer` 有 `overflow:hidden`** → 浮层必须 `position:fixed` + 搬 `document.body`（同 `.model-picker-popover`），外部点击判定要加 `popover.contains(event.target)`。
  - ⚠️ `t()` 不做 `{name}` 插值 → 前端自加 `trf(key, values)`；新增 18 条词条在 `static/js/i18n/studio.js`。
- 验证手法：技能 `infinite-canvas-verify` **§8 假上游 e2e**（脚本 `agent-tools-fake-upstream.py` / `agent-tools-e2e-client.py` 已随技能保存）。
  - ⚠️ **别把测试脚本放进仓库**：`tools/` 与 `tests/` 都在 `release.py` 的 `PROGRAM_DIRS` 里 → 会污染发布面。
  - ⚠️ 测权限档位时 `POST {'level': X}` **不会自动开开关**（上一轮刚设 `enabled=False` 会让只读档测出假阴性）→ 请求体要同时带 `{'enabled': True, 'level': X}`。
- 顺手修掉的既有问题：`sync_verify.py check` 发现根 `dist/` 与 `dist/launcher/` 仍是**旧包**（`index-UBURn_P-.js`），而 `launcher/dist` 已是 `index-CIpLBbBA.js` —— 1.1.3 重编启动器 UI（17:55）后**没回同步**。`dist/` 会进发布包、且 exe 候选链优先读 `dist\launcher` → 等于发旧 UI。已跑 `sync_verify.py sync`，四处一致。

## Q. 2026-09-21：画布页 Agent 对齐 + Skill 市场 + 启动器圆角换真抗锯齿

### Q.1 「画布页 AI Agent 没有变化」的根因 = 项目里有两套 agent

- `static/gpt-chat.html`（左侧「GPT 对话」页，`static/index.html:1603` 的 `#frame-gpt-chat` iframe）→ `POST /api/chat/agent`（`main.py:19251`）→ `build_chat_text_reply_with_tools()`。`bd1e576` 的本机工具**只加在这里**。
- `static/smart-canvas.html` 的 **`#agentPanel`** → `POST /api/agent-llm-task`（`main.py:16445`，异步任务 + 轮询/WebSocket）→ `run_agent_llm_task()`（`main.py:16409`）→ `canvas_llm()` / `canvas_llm_stream()`。**此前完全没接工具循环** —— 这就是老板说「没变化」的原因。
- 结论：**以后改 agent 能力，必须两套都改**。现在两边共用 `agent_tool_schemas()` / `run_agent_tool()` / `AGENT_TOOLS_SYSTEM_HINT` / `installed_skills_prompt_block()`。
- 画布页原有「Skill」只是手动挂一个本地 `.md`（`agentState.skills` 拼进提示词，`AGENT_SKILL_MAX_BYTES = 512*1024`），**没有市场、没有 star/下载量**。

### Q.2 工具循环接进 canvas_llm 的实现要点

- `canvas_llm()`（`main.py:18013` 起）请求段从「单次请求」改成 `for round_index in range(rounds + 1)`：
  - `rounds = max(1, int(tool_settings.get("max_rounds") or AGENT_TOOLS_DEFAULT_MAX_ROUNDS)) if tools else 1`
  - 每轮把 `tool_calls` 追加为 `assistant` 消息、把执行结果追加为 `role=tool` 消息（`tool_call_id` 对齐）。
  - `for...else: exhausted = True` → 超轮数返回提示文字（**不抛异常**）。
  - 返回体新增 `"tool_events": tool_events`。
- 🚨 **上游不支持 tools 的优雅回退**：捕获 `httpx.HTTPStatusError` → 若 `tools and not tool_events and agent_tools_unsupported(body)` → `tools = []` 并 `continue`（对**同一轮**重试）。断言 B 实测通过。
- 🚨 **工具循环与逐 token 流式无法混用** → `canvas_llm_stream()`（`main.py:17911`）在 `load_agent_tools_settings()["enabled"]` 时**整体回退非流式** `canvas_llm(payload)`，拿到结果后 `broadcast_agent_llm_token()` 一次性广播，前端表现一致。断言 D 实测通过。
- 前端：`assistantMsg` 增加 `toolEvents`（随消息落盘）；`agentMessageHtml()` 渲染 `<details class="agent-tool-call">`（参数/输出两段 `<pre>`、失败加 `.failed`）。
- 🚨 `.agent-msg` 是 shrink-to-fit（实测 180px）→ 带工具的消息要 `.agent-msg.has-tools { align-self:stretch; max-width:100% }`（复测 306px）。

### Q.3 Skill 市场（后端）

- 常量：`SKILLS_CATALOG_FILE = static/skills-catalog.json`（**随包分发的程序资源**）、`AGENT_SKILLS_DIR = data/agent_skills`、`AGENT_SKILLS_INDEX`、`SKILLS_MARKET_CACHE = data/skills_market_cache.json`、`SKILLS_MARKET_TTL = 6h`、`SKILL_MARKET_TIMEOUT = 12`、`SKILL_MARKET_WORKERS = 4`、`SKILL_DOWNLOAD_BYTES = 512KB`、`SKILL_INJECT_CHARS = 40000`、`SKILL_MARKET_UA = "InfiniteCanvasLauncher/1.0"`。
- 数据源调研：**GitHub API 未登录 403 限流**（本机实测 `rate limit exceeded`）→ 改用 **shields.io**：`https://img.shields.io/github/stars/<owner/repo>.json` 返 `{"value":"289k"}`；`/github/downloads/<repo>/total.json`。**单次 5~16s**。`raw.githubusercontent.com` 可达（下 SKILL.md）；`github.com/search` 网页被二级限流。
- 实测真实热度（2026-09-21）：`obra/superpowers` **289k**、`anthropics/skills` **177k**、`sickn33/antigravity-awesome-skills` **47k**。
- 函数：`load_skills_catalog()` / `skill_raw_url()` / `skill_http_get()` / `parse_shields_value()`（`'289k'→289000`）/ `shields_metric()` / `load|save_skills_market_cache()` / `refresh_skills_market(force)`（**ThreadPoolExecutor 并发拉 3 仓库 × 2 指标**）/ `load|save_installed_skills()` / `agent_skill_dir()`（防目录穿越）/ `skills_market_payload(refresh)` / `install_market_skill()` / `uninstall_market_skill()` / `installed_skills_prompt_block()`。
- 🚨 **`skills_market_payload()` 默认不联网**（联网 20.68s vs 秒回 0.02s），只有 `refresh=True` 才拉；返回 `stale` 标记供前端后台补刷。
- 🚨 **`refreshed_at` 单位**：缓存内部秒 → **对外 `int(refreshed_at * 1000)`**（毫秒，与 `now_ms()` 一致）。踩过：不转换 → 前端显示 1970-01-22。
- 🚨 **`ThreadPoolExecutor` 导入踩坑**：同一文件两处 `Edit` **并行**执行 → 导入行被另一处覆盖丢失 → `刷新 Skill 市场指标失败: name 'ThreadPoolExecutor' is not defined`。**再次印证「同一文件多处 Edit 绝不能并行」。**
- 接口：`GET /api/skills/market?refresh=`、`GET /api/skills/installed`、`POST /api/skills/install`、`POST /api/skills/uninstall`（请求体 `AgentSkillRequest{id}`）。重复卸载 → 404「该 Skill 尚未安装」。
- 热度公式 `hotness = stars + downloads * 2`（前后端一致）；同分比 star 再比名称。
- 安装 = 下载 SKILL.md 到 `data/agent_skills/<id>/`；卸载 = 删目录。`data/agent_skills/` 是**用户数据**（已 gitignore，不进包）；`static/skills-catalog.json` 是**程序资源**（进包）。
- `installed_skills_prompt_block()` 拼进 system prompt（`canvas_llm` 与 `canvas_llm_stream` 两处都注入），保证「安装即生效」。

### Q.4 Skill 市场（前端）

- 入口：`#agentSkillMarketBtn`（工具栏）+ 居中浮层 `#agentSkillMarket`（`.asm-*` 全套：head/toolbar/search/sort/tabs/meta/list）。
- 🚨 **`#agentPanel` 上有 `transform` → 会给 `position:fixed` 当包含块**：浮层被「居中对齐到 382px 的 agent 面板」并跟着缩放（实测 780px 被缩成 728px、中心跑到 x=1212）。修法 = `asmDetach()` 把浮层搬到 `document.body`（复测 `{l:310,t:120,w:780,h:660}`、`parent:"BODY"`）。
- 🚨 **`asmOpen`/`asmClose` 等不在全局作用域**（探针 `w.eval('typeof asmClose')` 返 `'undefined'`）→ 探针别用 `eval` 调它们，直接改 DOM。
- i18n：新增 39 个 `smart.asm*` 键（`static/js/i18n/smart-canvas.js`，只有 zh/en）；HTML 侧用 `data-i18n`/`data-i18n-title`/`data-i18n-placeholder`，JS 侧用 `tr()`；**带 `{total}`/`{n}`/`{date}` 的键要自己 `.replace()`**；语言切换要重画（监听 `studio-lang-change`）。`validate-i18n.js` 1096 → 1135 keys。

### Q.5 启动器圆角：换「逐像素透明」真抗锯齿方案

- 根因：`SetWindowRgn(CreateRoundRectRgn(...))` 是 **1 位掩码、天生无抗锯齿**；`DwmSetWindowAttribute(33, 圆角偏好)` 在 **Win10 19045 是空操作**。→ `5a1d054` 的「按 DPI 缩放 + PerMonitorV2」只是让锯齿颗粒变小，**消不掉**（老板已推翻）。
- 新方案（4 处联动，缺一不可）：
  1. `DwmExtendFrameIntoClientArea(hwnd, MARGINS{-1,-1,-1,-1})`（`launcher/Program.cs` 的 `EnablePerPixelCorners()`）→ DWM 按客户区 alpha 逐像素合成。
  2. `Form.BackColor = Color.Black`（**纯黑 = 透明色**；填 `#090a0f` 就透不出桌面）。
  3. `webView.DefaultBackgroundColor = Color.Transparent` → WebView2 交出网页真实 alpha。
  4. 注入 CSS：`html, body { background: transparent !important }` + `#root { border-radius: var(--launcher-corner, 18px) !important; overflow: hidden !important; background-color: #090a0f !important }`。
- 🚨 **与 `WS_EX_LAYERED` 互斥**：`Form.Opacity` 淡入用的 `LWA_ALPHA` 是整窗统一透明度，会盖掉逐像素 alpha（圆角退化成方块）→ 淡入收尾 + `RestoreWindow()` 都要调 `LauncherForm.EnsurePerPixelAlpha()` 摘掉该样式（`SetWindowLong(GWL_EXSTYLE)` + `SetWindowPos(SWP_FRAMECHANGED)`）。
- 🚨 **窗体不能直接引用 `webView`**（它是宿主 Program 的静态字段）→ 用 `LauncherForm.CornerRadiusChanged` 回调注入；`CornerRadiusCss` 改成 `public const`。
- 最大化/还原：不再动 Region，改为改 CSS 变量 `--launcher-corner`（`UpdateFormRegion()` 只在 `rounded` 状态翻转时才发 JS）。
- ⚠️ **兜底**：`InitializeLauncherAsync` 的 catch 里把 `BackColor` 改回不透明深色 —— 否则页面没加载出来时窗口会「一片透明」像没启动。
- ⚠️ 旧的 `SetWindowRgn`/`CreateRoundRectRgn`/`DeleteObject` 三个 P/Invoke 已删；**回退时不能只把它们加回来**（还要改 OnHandleCreated / UpdateFormRegion / WebView2 背景色 / 注入 CSS）。
- ✅ **网页侧可无头验证**：`~/.workbuddy-ai/skills/launcher-web-sync/scripts/verify-launcher-corners-web.py` —— 从 `Program.cs` **抽出注入 CSS 原文**，套在**真实 `dist/launcher/index.html`** 上量计算样式。实测 PASS：`htmlBg/bodyBg = rgba(0,0,0,0)`、`rootBg = rgb(9,10,15)`、`rootRadius 18px → 0px（最大化）→ 18px`。说明注入 CSS 压得过 dist 自带的 `!important` 与行内 style。
- ⚠️ **窗口视觉仍只能老板本人看**（WebView2 的 `PrintWindow` 全黑，见 P.1）。

### Q.6 无头探针的新坑

- 🚨 **`innerHTML` 重渲染后，之前缓存的节点会变成游离旧节点** → 读它的 `textContent`/`classList` 永远是旧值。我据此误判过「点击安装无效」（实际点击链路是通的）。**每步都要按 id 从实时 DOM 重查**（`#asmList [data-asm-install="<id>"]`）。
- 🚨 **`new w.Response(...)` 打桩不稳** → 异常会被应用自己的 `try/catch` 吞掉，表现为「点了没反应」的假阴性。改用鸭子类型 `{ok:true, status:200, json:()=>Promise.resolve(obj)}`。
- 🚨 **`--dump-dom` 输出写到 `/tmp/xxx` 后 Python 读不到**（MSYS 路径 vs Windows 路径）→ 写到仓库内（如 `output/`）再读。
- 🚨 **探针脚本插在 `<head>` 时 `document.body` 还是 `null`** → 读 body 行内 style 抛 `TypeError`，`title` 永远拿不到结果。**测量脚本放 `</body>` 前**。
- 📌 **静态资源在 `/static/` 前缀**：探针 URL 是 `http://127.0.0.1:3000/static/__probe.html`，写 `/__probe.html` 会 404。

### Q.7 本轮端到端取证（画布页工具循环，5 条断言全过）

- 脚本：技能 `infinite-canvas-verify/scripts/canvas-agent-tools-e2e.py`（新增）+ `agent-tools-fake-upstream.py`（增强：记录 `system_len`/`system_has_skill_block`/`system_skill_titles`）。
- A 工具真的被执行（`run_shell` exit=0 输出含 `E2E_OK`、`list_dir` 7 项）且结果回灌到最终文字。
- B 不支持 tools 的模型**优雅回退**（不报错、有文字）。
- C 关掉开关后不调工具。
- D **流式路径 + 工具** = 2 个 events、文字非空。
- E **已安装 Skill 真的注入 system_prompt**（`system_len=29621`、注入 `['需求探索（头脑风暴）','画布视觉设计']`）。
- ⚠️ 假上游 provider 的 key **不走 `api_providers.json` 字段**，而是 `provider_env_key_value()`（环境变量 `API_PROVIDER_<ID>_KEY` 或 `API/.env` 同名键）→ 脚本临时往 `.env` 追加一行，**finally 里整份拷回并核对 md5**（`.env` 含真密钥，只追加不读取回显）。

### Q.8 1.1.4 打包结果（2026-09-21 11:35）

- `release.py build --build-exe --notes-file static/update-notes.json` → 入选 2019 文件 / 156.30 MB。
- full `Infinite-Canvas-Full-1.1.4.zip` **111.11 MB**；delta `Infinite-Canvas-Update-1.1.4.zip` **64.58 MB**（相对 1.1.3：变更 30 个、删除 4 个 —— delta 大是因为**重编了 exe**，单文件自包含约 69 MB）。
- `scan_release.py` 审计：结构断言 0 命中、密钥扫描 0 命中、正控 8 命中（尺子有效）。
- ⚠️ 1.1.4 已本地提交（`8cc92ca`）但**未打 tag、未推送** → 发布必须老板本人执行（工具会话里 `git push` 会挂起、也没有 `gh`）。

## R. 2026-09-21（下午）：SkillsMP 数据源 + 限流加固 + 启动器第三处边

### R.1 SkillsMP 接口实测（`https://skillsmp.com/api/skills`）

- `GET /api/skills?sortBy=<stars|recent>&limit=<n>&page=<p>`；返回 `{skills:[…], pagination:{total, maxResults:1200}, filters}`。
- **硬限制**：`limit ≤ 48`（50 直接 400 `INVALID_LIMIT`）；不传 `search` 时总量**封顶 `maxResults=1200`**（`isCapped:true`，且 `page=26` 会**静默回退到 page 25** 不报错）；**只有 `stars` / `recent` 有效**，`updated`/`downloads`/`forks`/`name`/`trending`/`popular`/`newest`/`random` 全部**静默回退成 stars**。
- 🚨 **`search` 参数可用**（**2026-09-22 复测推翻本条旧结论**：R.1 原写「`search` 是坏的，8 个关键词全返回 `total=3`」—— 那是**错的**，或 API 在 09-21 之后修好了）。正确用法与证据：
  - 参数名就是 **`search`**；`q` / `query` / `keyword` **全部无效**（静默返回未过滤榜单）。
  - 实证：`search=zzzznope` → `total=0` / `totalIsExact:true` / **0 条**；`search=kubernetes` → **21 条**且结果语义相关（`k8s-security-policies`/`gitops-workflow`/`helm-chart-scaffolding`/`deployment-patterns`）；`search=caveman` → 48 条，含 `JuliusBrussee/caveman` 的 16 个 skill。
  - **能突破 1200 上限**：搜出的 caveman 覆盖 458~106187 star 的几十个仓库，而 1200 条榜单尾部全是 246398 star 的巨仓条目 → caveman 根本不在榜单内。**这是「全站搜索」唯一可行路径**（单纯加大抓取页数没用）。
  - ⚠️ **同时匹配 name 与 description** → 有噪声（搜 `caveman` 会混进 `orch`/`ultimate`/`sphinx`）。
  - ⚠️ `pagination.total` **不可信**（`totalIsExact:false`：limit=5→total=6、limit=3&page=2→total=7）；**翻页只认 `hasNext`**。
  - `search` 与 `sortBy=stars|recent` 可组合（`recent` 会多出 `caveman-handoff`/`caveman-help` 等 `stars` 排序里没有的条目）。
- `language=zh|ja|en` 有效（`total=480`）。`robots.txt` 允许；无 `/v1/models` 这类端点。
- **必须带浏览器式 UA**（站点在 Cloudflare 后）。
- **多样性**：`sortBy=stars` 被巨型仓库霸榜（1200 条只来自 4~7 个仓库，`affaan-m/ecc` 一家 903 条）；`sortBy=recent` 覆盖 **278 个不同仓库** → **两个排序都要抓 + 按仓库限量（8）**。
- **raw 地址拼法**（实测 5/5）：`https://raw.githubusercontent.com/{route.ownerSlug}/{route.repoSlug}/{branch}/{route.sourceSkillPath}`；来源页 `https://skillsmp.com/creators/{owner}/{repo}/{routeSlug}`。
- 快照现状：**615 个 Skill / 218 个仓库 / 540 KB**，13 个领域标签，star 0~389030。

### R.2 🚨 429 限流是「按 IP 累计惩罚」（本次事故）

- **现象**：连抓 24 页（并发 5、无节流、无重试）若干轮后，**15 页 429** → 清单从 615 缩到 194、仓库 218→64，而旧 `refresh` **把不完整结果直接覆盖了缓存**。
- **更关键**：惩罚是累计的 —— 之后**并发 2 + 间隔 1.0s 仍 24/24 全 429**，**单页请求也持续 429**，冷却以十分钟计。**且 429 响应本身要 ~16s 才返回**（不是立即拒绝）。
- **重试无效**：被限流时 429 重试**从不成功**，只是把用户干等时间翻倍。
- **四道防线（缺一不可，已落地 `main.py`）**：
  1. **全局节流闸** `skill_market_pace()`：**持锁 sleep**（并发只用来吃网络延迟，不提速率）→ 实测 25 次请求平均间隔 0.127s（设定 0.12s）。
  2. **429 不重试**（`SKILL_MARKET_THROTTLE_RETRY = 0`）；普通网络异常仍重试 2 次。
  3. **先探一页 + 快速中止**：批量前先抓 1 页，失败就直接放弃；批内连续 2 页限流即中止，且 `guard` 跨两个排序共享（`stars` 中止 → `recent` 直接跳过）。**最坏路径从 120s 压到 16.2s**。
  4. **防缩水 + 冷却**：失败页占比 > 15% 或条数 < `max(缓存, 快照) × 0.75` → **保留旧数据、绝不覆盖**；失败后写 `data/skills_market_state.json` 的 `cooldown_until`（30 min），期间不再联网，并在 payload 的 `refresh_note` 里给用户一句人话。
- ⚠️ **基准要用 `max(缓存, 快照)`**，不能用「当前生效清单」—— 缓存可能已被污染，内置快照反而是可信底线。
- 🚨 **刷新失败后必须删掉被污染的缓存**：`market_skill_source()` **缓存优先于快照** → 不删就真的缩水。
- ⚠️ `pool.map` 会**预提交所有任务**，中止标志只能拦住「尚未被 worker 取走」的页 → 小批次（4 页）会全部跑完，大批次（20 页）实测只跑 4 页。够用，但别指望「立即」。
- 回归测试（进包，`tools/`）：
  - `tools/test_skill_market_guard.py` —— 43 条断言，全打桩（污染缓存回落、不完整拒绝、冷却不联网、全失败冷却 30min、缩水拒绝、成功写缓存、节流闸、快速中止、探针短路、跨批次跳过、统计口径）。
  - `tools/test_skill_market_e2e.py` —— 本地假 SkillsMP（`ThreadingHTTPServer`）跑通健康路径：25 次请求 / 976 Skill / 282 仓库 / 单仓库 ≤8 / 节流实测。

### R.3 🚨 `CS_DROPSHADOW` = 启动器「三个角奇怪的边」根因

- `CS_DROPSHADOW`（`0x20000`）画的是**右下偏移投影**（"shadow is drawn on the right and bottom edges"），**按窗口矩形**投射 → 网页圆角外侧的透明区被方形阴影填成浅色角 → 命中**右上/左下/右下**三个角（左上干净）。
- 像素取证（读老板截图）：四角圆弧本身**完全对称平滑**（左右内缩量 18/17→12/11→9/7→6/5→4/2→2/1→1/0），但**右边和底边各多一条 4~6px 浅灰渐变带**（亮度 12→45→156→193→229→247→255），左边/上边完全没有。
- ⇒ **圆角窗口绝不能加 `CS_DROPSHADOW`**；想要阴影只能用「窗口比内容大一圈 + 网页 `box-shadow` 自绘」。已在 `Program.cs` 两处（常量 + `CreateParams`）写入防回退注释。

### R.4 证明「某个常量真的从 exe 里消失了」

单文件包压缩 → 直接 grep exe 搜不到任何字符串。做法：**解析 single-file bundle 取出内嵌 dll 再搜**（`tools/release.py` 无关，脚本见本轮 `output/__verify_corner_fix.py`）：

- 条目结构：`off`(int64) + `size`(int64) + `csize`(int64) + `type`(**1 字节**) + `name`(7-bit 长度前缀 + UTF-8) → 字段区在 `name` 前 **28 字节**；用 `re.search(rb'\x1a<DllName>', data)` 定位，对 `base = pos-28+a`（a 取 -8..8）逐个试 `zlib.decompress(..., -15)`，取「长度 == size 且以 `MZ` 开头」的那组。
- 🔑 **必须带对照组**：同时搜同文件的**兄弟常量**（如 `WS_MINIMIZEBOX`）。本次实测：旧 exe 的 dll 里 `CS_DROPSHADOW` **命中 1**、新 exe **命中 0**，而 `WS_MINIMIZEBOX`/`WS_MAXIMIZEBOX`/`CreateParams` 两边都在 → 证明「搜不到」不是搜法错。
- 私有常量名在 `#Strings` 堆是 **UTF-8**（`CS_DROPSHADOW` utf8=1 / utf16le=0）。

### R.5 其他本轮事实

- 📌 **`release.collect_files()` 返回 `(路径列表, [])` 元组** —— 第一项才是文件清单（按 `files[0]` 取，直接迭代会 `IndexError`）。
- 📌 **已手工 publish 过 exe 就不要再传 `--build-exe`** —— 它会跑 `build-launcher.ps1`，把 `E:\claude\skill\canvas-launcher\dist` 一起同步进来（会动 web 目录）。只改 C# 时用技能里的最小 publish（`dotnet_env.py publish … -o output/_launcher_build`）再只拷 exe。
- ✅ 共享浮层的 CSS **必须自带变量兜底**（`var(--card, #fff)`）：`smart-canvas.css` 在 `:root`/`.theme-dark` 定义全套变量，而 `theme.css` **只在 `body.studio-theme-dark .shell.theme-dark` 下定义** → **gpt-chat 的浅色主题根本没有 `--strong/--muted/--strong-text`**。
- ✅ `/static/js/i18n.js` 是**异步加载器**（`document.write` 注入 7 个子文件）→ 两个页面都已加载 `i18n/smart-canvas.js`，所以共享模块能直接用 `smart.asm*` 词条。`validate-i18n.js` **只校验缺失/乱码/未解析，不报未使用键** → 可安全加键。
- ✅ 1.1.4 二次打包（含 SkillsMP + 限流加固 + 第三处边修复）：full **111.27 MB**、delta **64.74 MB**（变更 36 / 删除 4）、`scan_release.py` 结构 0 / 密钥 0 / 正控 8。

## S. 2026-09-21（傍晚）：选中白框 + 启动器「四个角弧度不统一」定位与修复

> MEMORY.md 第二节/第五节引用的 `S.1`/`S.2–S.3`/`S.4` 指本节。

### S.1 文本框「选中白框」= `outline` 焦点环被程序化 `.focus()` 命中

- 症状：点进输入框后外围出现一圈**白色方框**（老板报「这个选中白框还需要帮我移除」）。
- 根因：焦点环用 `outline` 实现，而 `:focus-visible` **不只由键盘触发** ——
  程序化 `.focus()`（自动聚焦、打开面板时抢焦点）同样会命中 → 白框在任何输入方式下都出现。
- ✅ 解法：**文本框不要用 `outline` 做焦点环**，改在容器上用
  `label:focus-within { border-color: … }`（边框变色代替描边）。
  启动器侧另在注入样式里统一压掉：`*:focus, *:focus-visible { outline: none !important; box-shadow: none !important; }`。
  ⚠️ 但**键盘焦点可见性是 WCAG 2.4.7 AA 要求** → 画布 3D 节点那类必须保留可见焦点
  （见 K.10：`outline:none` 必配替代环，`:focus` 给环 + `:focus:not(:focus-visible)` 撤环）。

### S.2 🚨 四角弧度不统一的真根因：`border-radius` 贴住合成表面右/下边缘被**压平**

老板截图 `output/__c2.jpg`（1920×1087）经 `AskUserQuestion` 确认为「四个角的弧度不统一」。
⚠️ 上一轮曾判断「`#root` 用 `100vw/100vh` 溢出可见视口」—— **该结论已作废**：
用 `--dump-dom` + `#vp{position:fixed;inset:0}` 作视口基准实测 `100vw/100vh` 与视口
**Δw=0.0000 / Δh=0.0000**，完全一致。

**真根因**：`border-radius` 盒子**贴住 Chromium 合成表面的右/下边缘**时，那两角的弧会被削平。
（布局视口比合成表面宽出约 1.4 CSS px → `100vw` 盒子的右/下边缘被表面裁掉，弧在相切点附近被削。）
与 DWM、窗口尺寸、`overflow` 都无关，是**页面侧光栅化**行为。

面积法实测（dsf=1.665、窗口 1161×730，单位 CSS px）：

| 方案 | TL | TR | BL | BR | 极差 |
|---|---|---|---|---|---|
| 贴边（原状） | 18.16 | 15.87 | 14.87 | 12.39 | **5.76** |
| **右/下各内缩 2px** | 18.16 | 18.18 | 18.14 | 18.15 | **0.04** |
| 只缩右 | 18.16 | 18.18 | 14.87 | 14.89 | 3.30 |
| 只缩下 | 18.16 | 15.87 | 18.14 | 15.85 | 2.30 |

⇒ 右、下两条边**各自独立**触发压平。老板截图（面积法）实测 `21.17 / 17.04 / 17.40 / 12.61`（极差 8.56），
与无头复现**同一模式**（TL 最完整、BR 最残缺、TR/BL 居中）→ 与 DWM 无关，确系页面侧。

**内缩量阈值实测**：`-0.3px`/`-0.6px` 无效（仍 5.76）；`-0.9px`→3.58；`-1.2px`→1.24；
**`-1.8px` 起 → 0.04** → 取 **2px** 留余量。

**已排除的方案**（逐个实测无效）：
`mask-image`（内联 SVG 圆角矩形 / 四个 `radial-gradient`）、`clip-path: inset(0 round 18px)`、
去掉 `overflow:hidden`、给 `html` 也加圆角、`position:fixed;inset:0`（等价贴边）。
整数尺寸 1000×600 **有效但不可取**（窗口尺寸不固定）。
⚠️ `clip-path: url(#svg)` 在**隔离测试**里有效（四角 9/9/9/9），但在**真实启动器页面**上仍被压平
（9/8/8/7）→ **不可靠，未采用**。

### S.3 ✅ 现方案（第二轮定案）：内缩 = **2 设备px**（`2/dpr` CSS px）+ 相切端**渐显**补条

> ⚠️ 第一轮曾定案「内缩 2 **CSS** px + 纯矩形补条」→ 老板第二轮反馈
> 「启动器圆角边缘（除左上角）都还存在小尖角」。原因见 S.3.1。

落地在 `launcher/Program.cs` 注入脚本里（`--launcher-corner` / `--launcher-inset` 两个 CSS 变量）：

```css
html, body { background: transparent !important; }   /* ⚠️ 还要行内 !important，见 S.3.2 */
#root {
    border-radius: var(--launcher-corner, 18px) !important;
    overflow: hidden !important;
    background-color: #090a0f !important;
    width:  calc(100vw - var(--launcher-inset, 0px)) !important;
    height: calc(100vh - var(--launcher-inset, 0px)) !important;
}
body::before, body::after { content: ''; position: fixed; background-color: #090a0f; pointer-events: none; }
/* 竖条补右：相切点一端用 linear-gradient 渐显（透明 → 不透明，高度 = inset） */
body::before {
    right: 0; top: var(--launcher-corner, 18px);
    bottom: calc(var(--launcher-corner, 18px) + var(--launcher-inset, 0px));
    width: var(--launcher-inset, 0px);
    background: linear-gradient(to top, #090a0f 0, #090a0f calc(100% - var(--launcher-inset, 0px)),
                                transparent 100%);
}
body::after { /* 横条补底，同构，方向 to left */ }
```

- `--launcher-inset` 由注入的 `__launcherApplyCornerInset()` 在加载 / resize / 主题变化时按
  **`(2 / devicePixelRatio) + 'px'`** 写入 —— 🚨 **绝不能写死 `2px`**：
  写死时 125% 偏小（弧仍被压平）、150% 偏大（把本来正常的四角反而弄坏，极差 0 → 2）。
- 最大化（`--launcher-corner` = `0px`）时内缩归零 → 补条宽/高归零自然消失。
  🚨 `--launcher-corner` **未设置**时必须按「有圆角」处理（`var(..., 18px)` 就是这个语义），
  否则初始状态下不内缩 → 弧照样被压平。
- 🚨 **补条必须是纯矩形**（加圆角会被压平得更狠：15.85 / 12.15）。

#### S.3.1 🚨 第二轮「小尖角」的根因：补条在相切点留下 90° 台阶

矩形补条只在弧的**相切点之下**才覆盖 → 形状边界在 1 行内从「弧（内缩 2px）」**突跳**到
「直边（贴边）」，留下一个约 2 设备px 的 90° 台阶。**左上角两条边都不内缩、没有补条，所以只有它干净** ——
与老板「除左上角」的描述完全吻合。

正解：补条**相切点那一端用 `linear-gradient` 渐显**（透明 → 不透明，渐变长度 = `--launcher-inset`），
把剩余缝宽压到亚像素、台阶消失。

**四角实测（无头 Edge，窗口 1161×730；判据 = 四角对角透明长度 `d` 的极差 / 直边段缝宽，单位设备px）**：

| dsf | 贴边（内缩 0） | 内缩 2 | 内缩 3 | 内缩 4 |
|---|---|---|---|---|
| 1.25  | 极差 2 / 缝 0 | **0 / 0** | 1 / 1 | 2 / 2 |
| 1.5   | **0 / 0** | 2 / 1 | 3 / 2 | 4 / 3 |
| 1.665 | 3 / 0 | **1 / 0** | 0 / 1 | 1 / 2 |
| 1.75  | — | **0 / 0** | — | — |

⇒ **内缩 2 设备px 是跨 dsf 的综合最优**（最差极差 2，只有 1.5 会退化；1.25 / 1.665 / 1.75 都 ≤1）。
⚠️ 内缩 ≤1 设备px 没用（1.25 下极差仍 2）；≥3 设备px 会让 1.25 / 1.5 明显变差。

**机制定量**：**「布局视口宽 × dpr」比合成表面（截图）宽约 2.3 设备px** → `100vw` 盒子的右/下边缘
超出表面 → 弧的相切点附近被裁掉。与 DWM、窗口尺寸、`overflow` 都无关。

#### S.3.2 🚨 两个「看起来无关」但会毁掉整件事的坑

1. **`html`/`body` 的背景要压成透明 —— 靠的是「源顺序」，不是特异性**。真实
   `dist/launcher/index.html` 自带内联 `<style>html,body,#root{background-color:#090a0f!important}</style>`
   （在 `<head>` 里、**早于**注入样式）。⚠️ 它是**选择器列表**：对 `html` 元素只有 `html` 这一支生效，
   特异性 **`(0,0,1)`**，与注入的 `html, body`（对 `html` 也是 `(0,0,1)`）**打平** →
   按**源顺序**决胜，**注入样式必须追加在 head 末尾**（`document.head.appendChild(style)` /
   `</head>` 前插入）才赢。
   ❌ 曾写成「页面那条含 `#root`、特异性 (1,0,2)，压不过它」—— **错的**（把选择器列表当成单一选择器算）。
   实测：**只注入样式表、完全不跑 JS**，`getComputedStyle(html).backgroundColor` 就是 `rgba(0,0,0,0)`
   （技能脚本 `verify-launcher-corners-web.py` 的输出即此）。
   另用**行内 + `!important`** 再兜一层（author 层最高优先级），防以后页面把 `<style>` 挪后或加更强规则：
   `document.documentElement.style.setProperty('background-color','transparent','important')`（body 同理）。
   ⚠️ 只压 `html`/`body`，**`#root` 那条 (1,0,0) 不能压掉**（圆角盒的背景要留着）。
2. **C# verbatim 字符串陷阱（两轮各踩一次）**：
   - 里面写 `content: "";` 会被解成 JS 的 `content: ";` → **CSS 声明失效、补条整条不生效**
     ⇒ **CSS 里的字符串一律用单引号**（`content: '';`）。
   - 注释里写 `@"..."` 会让 verbatim 字符串**提前终止** → 编译报 `private 无效` / `EOF`。

**取证方法（用技能脚本，别手搓）**：

```bash
python -m http.server 8125 --directory dist/launcher          # 先起静态服务
./python/python.exe ~/.workbuddy-ai/skills/launcher-web-sync/scripts/verify-launcher-corners-geometry.py
./python/python.exe .../verify-launcher-corners-geometry.py --maximized
```

它从 `Program.cs` 抽**真实注入脚本**套在**真实 `dist/launcher/index.html`** 上渲染，量四角 + 台阶。

- ✅ **判据一 = 四角「对角透明长度」`d`**：从角像素沿 45° 往里走，遇到不透明像素的步数。
  理想半径 `r` 时 `d = r(1−1/√2) ≈ 0.2929r`。18px CSS @dsf1.665 ≈ 30 设备px → `d ≈ 9`。
  **四角 `d` 极差 ≤1 设备px 即合格**。
- ✅ **判据二 = 台阶**：沿 TR 角逐行量「右边界内缩量」，找 `y >= 20` 区间内相邻两行差 > 1 设备px 的位置。
  修好后应为**空**（`y < 20` 的跳变是弧本身的形状，正常）。
- ❌ **不要用轮廓拟合法**（Kasa 自由圆拟合 / 单参数切圆扫描）：在**理想合成图**上就有 ±2 设备px
  系统偏差，会伪造出「TL>TR≈BL>BR」的假象。面积法（缺角面积 `r²(1−π/4)`）在满幅大盒上准（±0.26），
  但在**内缩盒**上会被内缩缝隙污染 → 只用对角法。
- 🚨 **无头 Edge 会缓存复用同一 URL 的页面** → 所有候选渲染出**完全相同**的结果。
  每次渲染**必须带 `?v=<递增>` cache-buster**（脚本已内置）。
- 🚨 **抽注入脚本的终止锚点必须把 `})();` 一起切进来**（`s.index('})();";') + len('})();')`）：
  少切这一段 → 抽出的 JS 缺结尾 → **整个 IIFE 语法错误、浏览器静默不执行** →
  现象是「注入完全没生效」（四角 `d` 全 0、`#root` 的 `border-radius` 读到 `0px`）。
  排查时先 `node --check` 抽出的 JS。
- ⚠️ **`--dump-dom` 与 `--screenshot` 的视口不同**（1130×635 vs 1161×730）→ 跨模式几何数据**不可混用**；
  要读运行时几何就在页面里画成**诊断面板**再从截图里读。
  （`innerWidth` 在 `--force-device-scale-factor` 下是**错误报告值**，别拿它当视口宽。）
- 基准命令：`--headless=new --force-device-scale-factor=1.665 --window-size=1161,730
  --default-background-color=00000000 --screenshot=<绝对路径>` → RGBA **1933×1215**。

### S.4 第二轮验证结论与产物状态（2026-09-21 深夜）

- ✅ **还原态**（真实页 + 真实注入脚本）：四角 `d` = **9/9/8/8（极差 1）**；右边界内缩
  y=0→23 / 20→1 / 25 起 0（补条接上），**y≥20 区间台阶跳变 = 无**。
- ✅ **四个 dpr 全部通过**：`dsf=1.25` 极差 2→**1**、`1.5` 0→**0**、`1.665` 3→**1**、`1.75` →**0**；
  **所有 dsf 下 y≥20 的台阶跳变全部为「无」**。
- ✅ **最大化态**：四角 `d` 全 0（直角）、右/下透明区间为空、全图半透明像素 **0**。
- ✅ **exe 已重编**：最小 publish（`dotnet_env.py publish … -o output/_launcher_build` 再只拷 exe），
  已覆盖 `Lochou启动器.exe`（根，**发布包实际分发的那个**）与 `dist/InfiniteCanvasLauncher.exe`。
  取证：新 exe 内嵌 dll 里 `__launcherApplyCornerInset` / `linear-gradient` **均 HIT**；旧 exe **MISS**。
- 📌 旧 exe 备份留在 `output/_old_exe_0803.exe`（回滚路径，老板目视确认后可删）。
- 📌 `tools/release.py` 的包**排除** `dist/InfiniteCanvasLauncher.*`，**实际分发根目录的 `Lochou启动器.exe`**
  → 两个都要更新（本次已同时更新）。
- ✅ **技能 `launcher-web-sync` 已同步**：`SKILL.md` 4.3.1 节整体重写（压平根因 / 四角实测表 /
  已排除方案 / 现方案 / 两个 verbatim 陷阱 / 两条判据 / cache-buster / 锚点 bug）；
  `verify-launcher-corners-geometry.py` 新增 `corner_steps()` **台阶判据**并纳入 PASS 条件。
- ⚠️ **窗口最终观感仍须老板本人确认**（无头截不到启动器窗口，`PrintWindow` 全黑）。

## T. 两个已修的启动器陷阱（2026-09-21 晚，**务必别踩回去**）

### T.1 `webView.BeginInvoke` 陷阱 —— 后台线程给 WebView2 推消息会**静默丢包**

**症状**：更新进度条整程停在 `0%`，日志区也一片空白；但下载本身成功、更新备份也写了。
（非常容易被误判成「前端 bug」或「`total` 为 0」。）

**根因**：WebView2 的 **HWND 是异步创建的**。在句柄尚未创建/就绪时调用
`webView.BeginInvoke(...)` 会抛 `InvalidOperationException`；外层若是
`catch {}`，**所有** `UPDATE_PROGRESS` / `LOG` 推送就被静默吞掉。

**正确写法**（`launcher/Program.cs` 的 `PostJsonToWebView`）：
```csharp
void Deliver() {
    try { var core = webView?.CoreWebView2; if (core != null) core.PostWebMessageAsJson(json); }
    catch { }
}
if (form.InvokeRequired) {
    if (form.IsHandleCreated) form.BeginInvoke((Action)Deliver);   // 首选：窗体句柄在 Application.Run 前已创建
    else uiContext?.Post(_ => Deliver(), null);                     // 降级：SynchronizationContext
} else Deliver();
// catch 里再 uiContext.Post 兜一次 —— 宁可在非 UI 线程投，也不静默丢
```
配套：构造函数里 `uiContext = SynchronizationContext.Current;`
（构造函数由 `Application.Run` 的线程调用，此处拿到的就是 `WindowsFormsSynchronizationContext`）。

**排查手法（可复用）**：不要猜前端。打桩 `window.chrome.webview`
（实现 `postMessage` + `addEventListener`），按 C# 真实字段名回放
`UPDATE_PROGRESS`，再用 headless Edge `--dump-dom` 读 DOM 文案。
若回放能逐级渲染出正确百分比 ⇒ **前端没问题，问题在宿主推送**。

**回放实测（前端正常时应看到）**：
`0.0% → 524 KB / 63.9 MB（0.8%）→ 7.7 MB（12.1%）→ 21.6 MB（33.8%）→ 37.1 MB（58.1%）→ 50.6 MB（79.2%）→ 61.9 MB（96.8%）`

**另有两条**：`form.BeginInvoke` 本身在**窗体关闭中**也会抛，所以 `catch` 里必须还有兜底；
`ScheduleExit` 里也在用 `form.BeginInvoke` —— 那是既有代码，功能正常，别顺手改。

### T.2 端口复用不校验 root —— 会读**别人目录**的配置

**症状**：启动器里保存的 API 服务，在 `127.0.0.1:3000` 里读不到；
`/api/providers` 只返回 `default_api_providers()`（runninghub + volcengine）。

**根因**：`HandleStartServerAsync` 只要 `ProbeAsync(appUrl)` 为真
（3000 上有**任何** HTTP 服务）就无条件复用并打开浏览器。
若那个服务是从**另一个目录**起的（老板：安装目录的启动器 vs 开发仓库的 `main.py`），
它读的就是**那个目录**的 `data/api_providers.json`。

**正确做法**：复用前先**验身份**。`main.py` 的 `/api/app-info` 现额外返回
`app_root`(= `BASE_DIR`)、`root_fingerprint`、`pid`；启动器比对指纹，三支分支：
同源 → 复用；不同源 → 不复用 + 换空闲端口；无身份信息 → 不复用 + 换空闲端口。

**跨语言指纹必须逐字节对齐**（两侧已验，同目录 5 种写法结果一致）：
```
Python : sha1(os.path.normcase(os.path.realpath(BASE_DIR)).encode("utf-8","surrogatepass")).hexdigest()[:16]
C#     : sha1( Encoding.UTF8.GetBytes( Path.GetFullPath(p).Replace('/','\').TrimEnd('\').ToLowerInvariant() ) ) → 前 8 字节 → x2 hex
```
注意：`obj\Release\...\InfiniteCanvasLauncher.dll` 里的字符串是 **UTF-16LE**，可直接
`"某中文".encode("utf-16-le") in data` 验证改动是否编入；但**单文件 bundle（publish 出的
exe）是压缩的，明文搜不到** —— 别用 exe 做 grep 判据，会得到「没编进去」的假阴性。

**顺带的坑**：`appUrl` 原是 `readonly`。要支持换端口必须改成可变字段，并同步新增
`int port`（`ParsePortFromUrl` 从 URL 取），`StartServer` 传 `main.py --port {port}`；
`main.py` 侧用 `argparse` + `parse_known_args`（**默认仍 3000**，别破坏既有用法）。

## U. 从 MEMORY.md 下沉（2026-09-21，为容纳启动器红线腾空间）

### U.1 前端铁律（原 MEMORY.md 第二节）

- `PUT /api/canvases/{id}` **全量替换** + **必须传 `base_updated_at`**；只改标题走 `POST .../meta`。
  ⚠️ 清 `logs` 要**全量回传**其余字段，清完让用户刷新。详见 I.
- 只有一份 `static/smart-canvas.html/js/css`；节点根 `.image-node[data-id]`；
  `canvas.html` 不带 `?id=` 跳选画布页。
- 🚨 改前端必查三条：
  ① **新增非图片节点类型必须显式重显**（`.node-head`/`.node-title`/`.node-hint` 被全局隐藏）；
  ② **自吃鼠标事件的区域（如 3D 舞台）须加进 `beginNodeDrag` 排除选择器**；
  ③ **改 i18n 必跑 `validate-i18n.js`**。
- `render()` 无节流 → WebGL 查看器 DOM 必须复用；验证用**全新 `--user-data-dir`**。

### U.2 启动器构建 / 发布要点（原 MEMORY.md 第六、七节相关行）

- 🚨 **工具会话内 `git push` 无限挂起** → **推送必须老板本人执行**；工具会话**没有 `gh`**
  → 发 Release 只能网页界面。
- ✅ **打包 = `tools/release.py`**（`list`/`verify`/`build [--build-exe] [--notes-file <md>]`）；
  `build` 后**自动跑 `scan_release.py`，不通过即中止**。技能 `infinite-canvas-release`。
- 🚨 **发布包必须从工作区构建**；**改 `launcher/*.cs` 必须重编 exe**。
  🚨 **发版前必核对「包内 exe sha256 == 当前 exe」** —— `output/release/<版本>/` 里可能躺着
  **早先打的同版本包**（内含旧 exe），直接发出去等于没修。
- 🚨 **最小 publish 优先**（`dotnet publish … -o <tmp>` 再只拷 exe），
  **别在只想重编 exe 时跑 `build-launcher.ps1`** —— 它会 `Copy-Item E:\claude\skill\canvas-launcher\dist\*`
  覆盖 `dist/launcher`。技能 `launcher-web-sync`。
- 🚨 **四条排除铁律**：`assets/` 整目录；`data/` 只留 `inspire_prompt_zh.json`
  （**`asset_library.json` 绝不能随包分发**）；`dist/InfiniteCanvasLauncher.*` 与
  `dist/Microsoft.Web.WebView2.*` 不得进包；`static/__*.html` 排除。
- 🚨 **更新源 = `HanaJhon/Infinite-Canvas`**；`update.json` **必须作为 Release 资产上传**；
  **发布老板本人做**。⚠️ `releases/latest` 不切到新版 → 启动器会一直显示「已是最新」。
- 🚨 **不要手改 `VERSION`** → `python tools/bump_version.py`；**权威实现 = `tools/versioning.py`
  + `launcher/VersionUtil.cs`**（向量 `tools/version_vectors.json`）→ **改规则两边同改 + 跑两边向量**。
  ⚠️ **跨「日期制 ↔ 三段式」绝不能比数值**。
- 🚨 **无头验证走技能 `infinite-canvas-verify`**；**证明「常量从 exe 消失」** →
  解 bundle 取内嵌 dll 再搜 + **带兄弟常量对照**。
- 🚨 **Codex 权限** 4 档（`data/codex_permissions.json`）；`#codexCliPanel` **只在
  `protocol=codex` 时显示**（不是 bug）；⚠️ **不改全局 `~/.codex/config.toml`**（含**明文 token**）。

### U.3 模型下拉 / Grsai 与 Agent 市场（原 MEMORY.md 第三、八节）

- 下拉唯一数据源 `chatApiProviders()`（`smart-canvas.js:3049`），**只认 `chat_models`**；
  3D 用 `chatModelOptions()`。Grsai 对话模型 **14 个**、命名 = **OpenAI 官方模型 ID**（F.1）。
- 🚨 **画布下拉与启动器清单是两套、必须一致**：启动器读 **C# 硬编码** `GrsaiCuratedModels()`
  （`Program.cs:904`）。**别因一次 400 就剔模型**。F.4 三坑：别按通用命名猜 / **禁并发扫** /
  判「不存在」必须见 `model not found`。
- 🚨 **两套互不相干的 agent**：`gpt-chat.html` → `POST /api/chat/agent`；
  `smart-canvas.html` 的 `#agentPanel` → `POST /api/agent-llm-task`。**改 agent 能力必须两套都改**
  （工具循环已共用）。
- ✅ 本机工具 `run_shell`/`read_file`/`write_file`/`list_dir`；开关 `GET|POST /api/agent/tools`
  （`data/agent_tools.json`，默认关 / 8 轮 / 上限 20）。🚨 **上游不支持 tools 要优雅回退**；
  **工具循环与流式不能混用** → 回退非流式。
- ✅ **Skill 市场 = SkillsMP**：快照 `static/skills-catalog.json` + 缓存
  `data/skills_market_cache.json`（**优先于快照**）；共享 `static/js/skill-market.js` + 同名 css。
  🚨 **`refreshed_at` 对外 ×1000**；**限流按 IP 累计惩罚**，四道防线缺一不可，
  **刷新失败必须删污染缓存**。

## V. 回退功能（更新回滚，2026-09-22 新增）

**入口两处（都在启动器 UI；前端源码在 `E:\claude\skill\canvas-launcher\src\App.tsx`）**：
设置弹窗 `UpdateSection` 之后、首页胶囊浮层（`showHeader={false}` 之后），组件 `RollbackSection`。
命令协议 `ROLLBACK_LIST` / `ROLLBACK_START`（`Program.cs` → `HandleRollbackList()` /
`HandleStartRollbackAsync()`）。

### V.1 恢复点格式：统一 `manifest.json`（format 2）

- 目录：`<root>/data/update_backups/<YYYYMMDD-HHMMSS>/`。**启动器与网页端共用同一目录**。
- 网页端**早已有** `GET /api/update-backups` + `POST /api/update-rollback`；本轮才补启动器侧。
- 字段：`format`(=2) / `state`(ready) / `kind` / `created_at` / `from_version` / `target_version` /
  `source` / `parent_backup` / `update_notes` / `root_files{rel:{existed}}` /
  `static_snapshot{exists,complete,file_count}` / `affected_files`。
- ⚠️ **`root_files` 不含 `static/`**（与 `main.py` 的 `clean_root_files` 对齐）。
- 🚨 **`existed=false` 语义**：该文件「更新前不存在」= 更新**新增**的 → 回退时**要删掉它**。
  这是「完整还原」的关键；`apply` 阶段必须**先算 deleteList，再建恢复点**，否则被删的文件
  **进不了备份**（`UpdateApplier.Run` 顺序：`CollectStaleFiles` → `CreateUpdateRestorePoint`
  → `ExtractOverwrite` → `DeleteFiles`）。
- legacy 格式 = `apply-info.json`（`{kind:"launcher-apply", target_version, applied_at, replaced_files}`）
  → **只备份被覆盖的文件**，只能「部分还原」→ UI 标 `旧格式（部分还原）`（`RestorePointInfo.Partial`）。

### V.2 🚨 数据丢失隐患（本轮最重要修复）：`static_snapshot.complete`

- 老 `rollback_update` 只要发现 `备份/static/` 存在就 `rmtree(static)` + `copytree`。
- 但 **legacy 恢复点只备份部分 static**（实测 `20260920-165128`=18 文件/2MB、
  `20260920-183530`=14/1MB、`20260921-174211`=18/3MB；而 static 全量 = **74 文件 / 9.1MB**）
  → 一旦用网页端回退启动器恢复点，会**把 static 里未被备份的文件全删掉**。
- **修法**：`static_snapshot.complete == true` 才允许整目录替换；否则**逐文件复制，绝不删除**
  （`main.py:rollback_update` 的 `static_complete` 分支 / `UpdateApplier.RestoreStatic`）。
- 本侧 `SnapshotRestorePoint(..., snapshotStatic: …)` 仅在 `snapshotStatic && hasStatic` 时标
  `complete=true`。

### V.3 🚨 回退白名单比更新白名单**更宽**（`rollback_allowed_file`）

- 更新的信任边界 = 从网络下载 → `update_allowed_file()` = `{main.py, VERSION}` 或 `static/` 前缀。
- 回退来源 = **本机恢复点**，信任边界不同 → 新增 `rollback_allowed_file()`（+ `safe_rollback_target`）。
  否则回退启动器备份时 `Lochou启动器.exe` / `launcher/` / `tools/` 会被**静默跳过**。
- 两边都要有 **`ForbiddenRoots` / `ROLLBACK_FORBIDDEN_ROOTS`**
  = `{data, assets, output, API, .git, .workbuddy-ai}` —— **永不写入/删除**。
- `create_update_backup(..., wide_scope=True)`：回退路径用它，使**安全快照**能涵盖
  `Lochou启动器.exe`（否则「回退的回退」救不回 exe）。

### V.4 回退执行架构（与更新同构）+ 可再回退

- 启动器把**自己复制**成 `<root>/data/_apply_update_<pid>.exe`，以
  `--rollback <name> <destDir> <waitPids> <launchExe>` 派生脱离进程 → 等所有 PID 退出 →
  还原 → `Relaunch`。启动器本体 `ScheduleExit(1500)`。
- **回退前安全快照**（`rollback_safety`）：先把当前状态存成新恢复点，名字带 **`rollback-`** 前缀
  → 使「回退可再回退」。
- 🚨 **`TrimBackups` 不能按目录名排序**：`rollback-` 前缀里 `r` > `2`，会让安全快照**永远排最前**，
  结果被裁掉的反而是真正更新的更新恢复点。正解：按清单 `created_at`（缺失退回目录 mtime）
  排序，与 `main.py:prune_update_backups` 一致。
- 保留数 `BackupRetention = 10`。单个恢复点可达 **~73MB**（exe 是主体，故 static 全量代价可忽略）。

### V.5 验证

- 端到端脚本（临时，已清理）用真实 exe 跑 `--apply-update` / `--rollback`，覆盖
  apply / rollback / legacy 三阶段，**29/29 PASS**。
- legacy 回归要点：`L1` static **未被整目录抹掉**、`L4`/`L5` 元数据
  （`apply-info.json` / `manifest.json`）**未被还原到安装目录**。
- 关键断言：`R6` 生成 `rollback_safety` 安全快照；`R6c` 安全快照含 exe/根文件（`wide_scope` 生效）。

### V.6 本轮同时改动

- `main.py` 新增 `--port`（默认 3000，`parse_known_args`）；`/api/app-info` 增
  `app_root` / `root_fingerprint` / `pid`（启动器复用 3000 前先验身份，见 T.2）。
- `nativeBridge.ts` 修掉**硬编码旧版本**：`GET_VERSION` 的 `version` 与 `UPDATE_CHECK` 的
  `current`/`latest` 由 `'1.1.1'` 改为 `''`（前端预览兜底桥不再显示假版本号）。

### V.7 legacy 恢复点元数据回落（2026-09-22 修）

- 🚨 `ReadBackupManifest` **只读 `manifest.json`**，不认 legacy 的 `apply-info.json`。
  不回落的话，从安装目录打开启动器时 legacy 恢复点会显示成「（版本未知）」+ **虚高文件数**
  （`CountFiles()` 把 `static/` 与元数据都算进去，实测 26 而非 25）。
- 修法：`LegacyApplyInfo` DTO（`kind` / `target_version` / `applied_at` / `replaced_files`）
  + `ReadLegacyApplyInfo()` + `ParseIsoSeconds()`；`manifest is null` 时回落，
  `AffectedCount` 用 `replaced_files` 而非 `CountFiles()`，`CreatedAt` 用 `applied_at`。
- ⚠️ `apply-info.json` **不记录「更新前版本」** → `FromVersion` 只能为空，
  UI 显示「（版本未知） → V\<target\>」，这是诚实的（不要瞎猜成上一版）。
- ✅ **诊断出口**：`Lochou启动器.exe --list-restore-points <安装目录>` → 打印恢复点 JSON 后退出
  （不建窗口、不抢单实例互斥量；GUI 子系统无控制台，故直接写 `Console.OpenStandardOutput()` 的
  UTF-8 字节）。用途：界面显示「暂无恢复点」时，确认「到底扫到几个、是 format 2 还是 legacy」。

### V.8 ⚠️ 别搞混「开发仓库」与「安装目录」两个 root

- 启动器的 root = **exe 所在目录**。从开发仓库跑 `Lochou启动器.exe`，读的就是**开发仓库的 `data/`**
  （`api_providers.json` 只有 2 字节 = 空 → 走内置默认通道），且**看不到**安装目录的恢复点。
- 🚨 **两处的 `VERSION` 可能完全相同**（实测安装目录也是 1.1.4，只是文件夹名还叫 `-Full-1.1.1`）
  → **不能用版本号区分两者**。可靠判据：
  - `Lochou启动器.exe.WebView2` 目录的**最近写入时间** → 判断「谁在被跑」；
  - `Lochou启动器.exe` 的 **md5** → 判断「跑的是哪个构建」。
- 老板的真实安装目录：`D:\工作\无限画布\Infinite-Canvas-Full-1.1.1\Infinite-Canvas\`。

### V.9 ⚠️ 预览截图用「假数据」会掩盖真实缺陷

- 2026-09-22 给回退面板做预览截图时，`__preview.js` 里的恢复点是我**手编的**（legacy 点带了
  `fromVersion`/`targetVersion`）→ 截图看起来很完美，**掩盖了 C# 侧根本没读 `apply-info.json` 的 bug**
  （见 V.7）。
- **正确做法**：先用**真实** exe 的命令行出口（如 `--list-restore-points`）导出真实数据，
  再把这份 JSON 喂给预览桥。这样预览才是「真实渲染结果」，否则只是「我以为的渲染结果」。
- 同一面板建议出**两张**图：一张演示数据（展示完整形态，如 `rollback_safety` 标签），
  一张真实数据（验证当前状态）。文件名要能区分，避免日后张冠李戴。

### V.10 「最新版本」低于「当前版本」的显示歧义（2026-09-22 修）

- 现象：开发机 `VERSION=1.1.4` 而线上 `releases/latest` 仍是 `1.1.3` → 面板显示
  「当前版本 1.1.4 / 最新版本 1.1.3 / 已是最新」，看着像数字填错了。
  **数据本身是对的**（1.1.4 确实还没发 Release），是**文案有歧义**。
- 🚨 **版本比较只留在 C# 侧**：`tools/versioning.py` + `launcher/VersionUtil.cs` 是两处权威，
  **不要在前端 TS 里再写一份**（会变第三份真相；跨「日期制 ↔ 三段式」比数值必错）。
  C# 的 `UPDATE_CHECK` 返回体新增 `localAhead`：
  ```csharp
  localAhead = !string.IsNullOrWhiteSpace(current) && !string.IsNullOrWhiteSpace(latest)
      && !VersionUtil.IsLegacyDate(current) && !VersionUtil.IsLegacyDate(latest)
      && VersionUtil.CompareVersion(current, latest) > 0,
  ```
  ⚠️ **必须挡空串**：`CompareVersion("1.1.4", "")` 返回 **1**（空侧按 0 补位），
  不加守卫会把「清单没写版本号」误报成「本机版本更高」。
- 前端三处文案（`UpdateInfo.localAhead`）：表头标签 `最新版本`→`线上最新`；
  `当前 X · 最新 Y`→`当前 X · 线上最新 Y`；
  状态行补「本机版本高于线上最新版，无需更新。」
- 相关事实：**线上最新 Release = 1.1.3**（`Official.1.1.3`，2026-09-20 10:34），**1.1.4 从未发布**。

### V.11 ⚠️ 两个「看着像 bug 其实是环境」的排查套路

- **「暂无恢复点」**：启动器 root = exe 所在目录。从开发仓库跑就读开发仓库的 `data/`，
  看不到安装目录的恢复点。判据见 V.8（WebView2 目录写入时间 + exe md5）。
- **`sync_verify.py check` 报残留**：`dotnet publish` 会把 `dist/` 一并拷进**输出目录**
  （如 `output/_launcher_build/dist/assets/index-<旧hash>.js`）→ 报「旧包残留 1 个」是**假阳性**，
  该目录是临时产物、不随包发布。清理 `_launcher_build` 后自然消失，**不用管**。
- **要实测回退功能，安装目录需同时换两样**：`Lochou启动器.exe` **和** `dist/launcher/`。
  只换 exe 时界面不会出现回退面板（旧 bundle 里没有 `ROLLBACK_LIST`/`版本回退`）。

## W. Skill 市场：两级分类 + 中文简介 + 内置清单定向补抓（2026-09-22）

### W.1 两级分类（大分类 → 子分类）

- 权威表 = `main.py:SKILL_TAXONOMY`（4 大分类 / 23 子分类）。**派生三张表，别手写**：
  `SKILL_TAG_CATEGORY`（子分类→大分类反查）、`SKILL_TAG_RULES`（扁平化，`skill_tags()` 只认它）、
  `SKILL_CATEGORY_KEYS = ("utility","design","visual","other")`（前端大分类顺序，other 恒最后）。
- 🚨 **归属必须取「权重最高的子分类」所属大分类**（`skill_category()` 读 `SKILL_TAG_WEIGHT`），
  **不能取 `tags[0]`**：tags 按得分排序，而宽泛标签（design / image / video）得分往往更高 ——
  实测「电商详情页」类会被打成 `[design, ecommerce-page, product-shot]`，取 `tags[0]` 就归到「设计」了，
  而老板要的是「视觉」。
- 🚨 **`design` / `image-video` 的权重必须保持 1**：它俩关键词（design / image / video）太常见，
  给 2 会把电商视觉与图像生成类**大批抢到「设计」**（实测「视觉」从 129 掉到 16）。给 2~3 的只应是
  **具体**子分类（ecommerce-page / product-shot / product-detail / cross-border / miniprogram-design /
  token-save = 3；agent-optimize / ui-design / ux-design / product-design / web-design / app-page-design = 2）。
- 🚨 **标签必须「现算」**：`skill_tags()` 是**子串包含**判定（不是分词），而内置快照与联网缓存里存的
  `tags` 是**生成时按当时规则**算好的。`market_record()` 里读旧值 → 改规则「不生效」（实测残留
  `frontend` / `media` / `mobile`，接口 133 条设计 vs 直算 120 条）。**正解**：`market_record()` 每次调
  `skill_tags_cached(name, summary)`；只有 name 与 summary **都为空**时才退回存的那份。
- ⚠️ **子串判定会误伤**：短词写不得（`api` 命中 `rapid`、`review` 命中 `preview`、`cave` 命中 `caveat`）。
  规则里宁可写长短语。
- ⚠️ `skill_category_meta()` 统计子分类计数时**只算属于该大分类的标签**，否则「实用」下面会冒出「设计」芯片。
- 性能：`skill_tags_cached()` 带 memo（上限 4000 条，超了整表清空）。827 条每次请求重算要 ~18 万次
  子串判定，不缓存会白烧几十毫秒。

### W.2 中文简介（双通道 + 模型兜底）

- 通道① **随包离线表** `static/skills-i18n-zh.json`（按 skill id 索引，**独立文件** ——
  写进 `skills-catalog.json` 会被 `build_skills_catalog.py` 重刷清掉）。
- 通道② **联网缓存** `data/skills_market_i18n.json`，**优先于离线表**（同 id 以缓存为准）；
  存全站搜索搜到的、离线表里没有的新 Skill 的译文。
- 通道③ **兜底端点** `POST /api/skills/i18n` → `translate_skill_summaries()`：`pick_translate_provider()`
  挑平台（**跳过 CLI 协议 / gemini 协议 / 无 chat_models / 无 Key**），分批 24 条调 `/chat/completions`，
  `parse_translation_reply()` 抠 JSON（兜住 ```json 围栏与客套话）。
- 🚨 **`parse_translation_reply()` 只收含中文的条目**（`re.search(r"[\u4e00-\u9fff]")`）：
  模型原样回显英文时必须丢弃，否则「英文被当译文缓存 → 永远不再重试」。
- ⚠️ **gemini 协议必须跳过**：它的 base 是 `/v1beta` + `generateContent`，请求体形状与 OpenAI 兼容调用
  完全不同，硬发过去只会 400。
- `load_skills_i18n()` 按两个文件的 **mtime** 做进程内缓存（一次请求要问 827 次译文）；
  任何异常都退化成「没有译文」（前端回落英文原文），绝不让市场因此打不开。
- 生成工具 = `tools/translate_skills.py`（正式工具）：
  - `--from-codex-config` 复用 `~/.codex/config.toml` 的通道（token 只进内存，**不入库**）；
  - 断点续跑写 `output/_skill_i18n_work.json`（**gitignore，别删**，重译一遍要几分钟）；
  - 手工兜底 = `tools/skills_i18n_manual.json`（**进 git，可评审**）：模型反复翻不出来的极少数条目；
  - `--table-only` 不联网重写中文表（改手工译文后用它）。
- 🚨 **模型顺序即优先级**：实测 `deepseek-v4.1-flash` 单批 12 条 ~5s，`glm-5.3-flash` 单批 6 条 **54s**、
  12 条直接 90s 超时。慢模型是「能返回」而不是「不能用」→ **不会自动降级**，必须靠 `DEFAULT_MODELS` 排序
  避开（否则 800 条从 3 分钟变成 1.5 小时）。
- ⚠️ **模型会漏译**：一批 12 条偶尔只回 8~11 条 → 跑完看「仍有 N 条没有译文」，**直接再跑一遍**（只补缺的）。
- 现状：827 条里 826 条有中文，唯一例外 `abc-2-d356ae0d`（其 summary 原文就是 `abc`，无实义）。

### W.3 内置清单定向补抓（填「视觉」大分类）

- 🚨 **问题**：内置快照 = 「star 榜 4 页 + 最近更新 20 页」，**天然偏向开发者工具**。实测原 615 条里
  `主图` / `详情页` / `packshot` / `product photo` / `product image` **全部 0 命中** → 老板点名的
  「产品主图 / 产品详情页」两个子分类**恒为空**（不是规则写错，是清单里根本没有这类 Skill）。
- ✅ **解法**：`main.py:SKILL_CATALOG_SUPPLEMENTS`（15 个查询词）+ `build_skills_catalog_supplement()`，
  用 SkillsMP 的 **`search=` 全站过滤**按主题补抓。实测 `电商` → ecommerce-full-pipeline /
  ecommerce-copywriter / 数字人带货视频；`ecommerce listing` → ecommerce-image-workflow / fal-tryon /
  product(审详情页)。
- ⚠️ **查询词要具体**：`主图` / `详情页` 这种单词在 SkillsMP 上退化成泛匹配（返回 Swift 并发、知识星球笔记…），
  而 `电商` / `ecommerce listing` / `shopify` 效果好。
- ⚠️ 补抓只保留落在**设计 / 视觉**子树上的结果（`SKILL_CATALOG_SUPPLEMENT_KEEP`），
  别把 `shopify` 顺带捞到的 Admin API 后端 Skill 也塞进快照；单仓库限 3 条（`..._PER_REPO`）。
- ⚠️ 补抓走 `skillsmp_search()` → **共用同一道全局节流闸**；被限流（429）**立刻中止剩余查询**。
- 用法：`build_skills_catalog.py --supplement`（只补抓，不重跑 24 页榜单，约 20s）
  / `--no-supplement`（全量重建但不补抓）/ `--reindex`（**不联网**，按当前规则重算标签后重写）。
- 🚨 **`write_catalog()` 落盘前会按当前规则重算全部标签** —— 否则快照会残留旧子分类
  （实测 `frontend`/`media`/`mobile`），打印出来的标签分布也跟着骗人。
- 效果：615 → **827 条 / 344 仓库**；大分类 `utility 427 / design 184 / visual 144 / other 72`；
  视觉下 5 个子分类全部有内容（ecommerce-page 107 / cross-border 44 / image-video 25 /
  product-detail 15 / product-shot 14）；设计下 7 个全有内容。

### W.4 前端（`static/js/skill-market.js` + `skill-market.css`）

- 浮层两行筛选：`.asm-cats`（大分类，带计数与 `.is-empty`）+ `.asm-tabs`（子分类，**单行横向滚动**
  `flex-wrap:nowrap; overflow-x:auto`，`:empty{display:none}`）。
- `renderTabs()` **只显示当前大分类下、且当前列表里真有内容的子分类** → 空子分类不会留下死芯片。
  切大分类会清 `state.tag`。
- `visible()` 的大分类/子分类筛选**对本地清单与全站搜索结果都生效**（后端给每条记录都打了
  `category` 与 `tags`）。
- 🚨 **卡片上的标签只显示与该条记录同一个大分类的子分类**（`cardTags()`）：
  卡片本来就挂在某个大分类下，把别的大分类的子分类也贴上来是噪声 ——
  实测「视觉」里会冒出「后端服务」这种芯片。过滤后为空才回落到原标签。
- `ensureSummaries(list)`：对缺 `summary_zh` 的记录 POST `/api/skills/i18n`，**同一批只问一次**
  （`state.i18nAsked` 去重），回填 `state.skills` / `state.remote`。
- 卡片简介优先 `summary_zh`（`.is-zh` 类），英文原文挂 `title` 悬停可见。
- ⚠️ 改 i18n 词条必跑 `static/js/i18n/validate-i18n.js`（**不在 `tools/` 下**，别记错路径）。
- 单测：`tools/test_skill_market_guard.py`（A–AB 共 28 段）。⚠️ **别硬编码内置快照条数**
  （会随补抓增长，实测 615 → 827 让一堆无关用例跟着红），用 `SNAP_N = len(app.load_skills_catalog()['skills'])`。
  ⚠️ 打桩限流必须抛 **`urllib.error.HTTPError`** —— `skill_market_is_throttle()` 只认它，
  拿 FastAPI 的 `HTTPException` 冒充 429 判不出来。

## X. Skill 市场面板：三个「看起来坏了」的真因（2026-09-22 下午）

老板截图反馈：「右上角的筛选功能失去了效果，隐藏多余无用的滑条和黄色文字」。
逐条实测（无头 Edge + 临时同源探针量 DOM）后是**三个互不相干**的问题。

### X.1 排序「失去效果」——不是坏了，是并列块太大

- 实测（`/api/skills/market` 827 条）：`hot` / `stars` / `installed` 的前 **14 条完全相同**，
  `forks` 到第 11 条才变。
- 根因：🚨 **star / fork / 热度都是「仓库级」指标** —— 同一个仓库下的每条 Skill 数值完全相同。
  `openclaw/openclaw` 一个仓库 11 条，star=389030 / fork=81745 / hot=552520，并列全站第一，
  任何排序都把它们顶在最前；并列内部按 `title.localeCompare` 排 → 首屏 7 张卡片一字不差。
- 修法：`visible()` 末尾加 `spreadByRepo(list)`「同仓错峰」—— 同一仓库**连续出现不超过 2 条**，
  超了往后顺延找别家仓库。实测 hot↔forks 首个不同位 **14 → 2**（第 3 张卡片就变）。
  ⚠️ 只打散并列块，主排序不变；绝大多数仓库只有 1~2 条，不触上限时与严格排序**完全一致**。
- ⚠️ `hot` 与 `stars` 前 10 仍相同：热度 = star + 收藏×2，仓库级 fork/star 比例相近，
  两个指标本身就高度相关。**这不是 bug，别去「修」它**。
- ⚠️ **大分类 / 子分类筛选本来就是好的**（实测 utility→Autoreview…、design→Node Connect…、
  visual→Meme Maker…、other 72 条；24 个子分类芯片都能筛）。别被「筛选失去效果」这句话带偏。

### X.2 「多余无用的滑条」= 子分类行被压成 0.69px

- 实测 `.asm-tabs` 内容高 **0.6875px**、`scrollHeight=24`；按钮 `box-sizing:border-box` 高 8px
  （= padding 3×2 + border 1×2，内容高 0），24 个芯片文字全被裁掉，原位只留一条横向滚动条。
- 根因：🚨 **列方向 flex 容器里所有子项默认 `flex-shrink:1`；而 `overflow-x:auto` 会把
  `overflow-y` 一并算成 `auto`（CSS 规范如此），于是这一行成了「滚动容器」，而滚动容器的
  `min-height:auto` 解析为 0** —— 别的固定行是「内容高度」压不动，只有它被压扁。
- 修法：`.asm-tabs` 改 **`flex-wrap:wrap` 换行铺开** + **`flex:0 0 auto`**，并去掉 overflow。
  实测 3 行 / 24 芯片 / h=80px，滑条自然消失；固定行 +48px，列表仍显示 6 张卡片。
- 验证探针写法：`SkillMarket.open()` 并等 `state.loaded` 后，量 `.asm-tabs` 的
  `getBoundingClientRect()` 与每个 `.asm-tab` 的高度；「候选修法对比」可在探针里逐个注入
  `<style>` 再量（`void el.offsetHeight` 强制 reflow），一次 headless 就能比出哪条修法有效。

### X.3 黄字 = 常驻的补译失败提示

- 离线表已覆盖 826/827 条，只差 1 条也会触发 `ensureSummaries()`；没配对话模型时后端
  返回 `ok=false` → `state.i18nNote` 有值 → 这行 `asm-warn`（深色主题 `#fbbf24`）**常驻**。
- 修法：`renderMeta()` **不再回显 `state.i18nNote`**（保留瞬时态 `i18nBusy`）。
  `state.error` / `meta.refresh_note` / `meta.stale` 等真告警**保留**。

### X.4 顺带修的与踩到的

- 换排序 / 换大分类 / 换子分类后 `resetListScroll()` 把列表滚回顶部 —— 原来停在第 5 屏再重排，
  视口不动，看起来「没生效」。
- 🚨 **`static/*.html` 的 `?v=` 只有服务启动时才同步**（`sync_static_html_versions()`）。
  不想重启老板的服务时，可用 `importlib` 加载 `main.py` 后直接调它（实测 2s、无副作用）；
  否则工作区里 html 的版本号会一直指向旧 css/js。
- 🚨 **改了 `main.py` 必须重启服务才生效**：本轮端口 3000 的进程是 16:01 启动的，而 `main.py`
  16:18 才改 → API 仍返回**旧分类**（utility 427 / design 184 / visual 144 / other 72），
  上一轮的分类重写看起来「没生效」。**判别方法**：比对 `static/*.html` 的 mtime（服务启动时会
  重写 `?v=`）与 `main.py` 的 mtime；或 `Get-Process python | Select-Object StartTime`。
  进程由启动器 WebView2 托管，**别擅自杀**。
- ⚠️ **`rm -rf` 会被安全钩子拦**（`SAFE_DELETE_BULK_CONFIRM_REQUIRED`，阈值 50 个文件）→
  批量删项目内可再生文件一律走技能 `safe-recycle-cleanup` 的 `scripts/recycle.py`
  （回收站、可还原、幂等；单个大目录可能被工具会话 SIGTERM 打断，**重跑即可**）。
- ⚠️ `release-delta-e2e.py` 的 `E2E` 目录硬编码在 `output/_e2e_release`；上一次失败留下的
  半成品目录会让下一次解包报 `FileNotFoundError`（路径仅 119 字符，**不是** MAX_PATH ——
  包内最长路径也只有 164 字符）。**先清干净再跑**；脚本里的 `rmtree_retry()` 会静默吞掉失败，
  别指望它。

## Y. Skill 市场安装链路：全站搜索结果装不上（2026-09-22 傍晚）

**现象**：搜 `caveman` → 44 条结果 → 点「安装」→「市场清单里没有这个 Skill（可能已下架）」。

**根因（两处叠加，缺一不可）**：
1. 后端 `install_market_skill()` 只认 `find_market_skill()`（联网缓存 + 内置快照）。
   全站搜索的结果**两处都不在** → 必然 404。实测内置清单含 `caveman` 的记录 **0 条**。
2. 前端 `AgentSkillRequest` 只有 `id`，安装时只发 `{id}` → 后端拿不到 `raw_url`，无从兜底。

**契约（以后改这条链路必守）**：
- 🚨 **全站搜索的记录只活在 `state.remote` 里**，`state.skills` 只有本机清单 ——
  前端找记录必须用 `recordById()`（两处都查）；`skillById()` 只查 `state.skills`，对全站结果返回 null。
- 🚨 **安装请求必须回传整条记录**（`raw_url` / `name` / `title` / `summary` / `repo`）；
  后端 `install_market_skill(skill_id, hint)` 的语义 = **内置清单优先，找不到才用 hint**。
- 🚨 **`raw_url` 必须过 `skill_raw_url_ok()` 白名单**（只允许 `raw.githubusercontent.com`）：
  hint 里的 URL 会让本机去 GET，不校验就等于开放任意 URL 请求（SSRF）。实测内置 827 条的
  raw_url **全部**是该域名，白名单有据可依。

**三层验证法（全程不碰 `data/agent_skills/`）**：
1. 函数级 —— monkeypatch `agent_skill_dir` 到临时目录 + `save_installed_skills` 空操作；
2. 路由级 —— `fastapi.testclient.TestClient(m.app)`，验证 Pydantic 新字段真能解析（不只是签名对）；
3. 前端 —— 无头探针读 `SkillMarket.state`，确认 `remote` 记录**带 raw_url** 且 `skills` 里**没有**它。

## Z. Skill 市场全站搜索的降级判定：`!!state.remote` 是陷阱（2026-09-22 傍晚）

**现象**：限流冷却期间搜 `caveman` → 列表**一片空白**（连本机清单里明明有的 Skill 也不显示），
中间大字还写着「SkillsMP 全站也没有匹配的 Skill」。

**根因**：限流时后端**仍返回 HTTP 200**，只是 `skills = []` + `note = "限流冷却中…"`。
前端 `remoteActive()` 写的是 `!!state.remote` —— **空数组是 truthy** → 被误判成「正在展示全站结果」。
两个后果：① `currentSource()` / `visible()` 拿到空数组 → 不再回落本机清单 → 列表空白；
② 空态走 `asmEmptyOnline` → 谎报「全站也没有」（而实际根本没搜成）。

**契约**：
- 🚨 **判断「是否真的联网搜成功」不能只看 `!!state.remote`**，必须
  `Array.isArray(state.remote) && remoteQuery === q && !state.remoteNote`（= `remoteSearched()`）。
- 🚨 **`remoteActive()`（当数据源用的那个）还要 `length > 0`** —— 空结果必须回落 `state.skills`。
- 🚨 **`remoteNote` 非空 = 降级中**（限流/失败），此时不该报「命中 N 个」。
- ⚠️ **刷新（24 页 ≈ 29s）与搜索共享同一冷却状态**（`SKILL_MARKET_COOLDOWN`）——
  一次刷新撞 429 会连带搜索一起进冷却。这是**有意的保护**（429 按 IP 累计，越撞越久），
  别改成各管各的。
- ⚠️ 验证限流行为**拦截 fetch 假装限流**即可（返回 `skills: [], note: '…'`），**不要真打上游**；
  尤其别在老板使用期间起第二个实例 —— 冷却状态落盘共享，但 `skill_market_pace()` 节流闸
  **是进程内的**，两个进程会各自计时却共用同一个 IP 配额，反而加剧限流。


## AA. 画布 Agent：任务相关建议 + 输入区重排 + 「思考 / 画布控制」命名（2026-09-23）

### AA.1 「一味的给生图风格建议」——三处叠加的真因

老板输入「在画布中创建一个上传节点」，AI 回「你的输入比较简略，请先选择一个风格方向…」并抛
水墨风 / 油画风 / 赛博朋克 / Q版卡通。三条独立原因叠在一起：

1. **`isVagueImageRequest(text)` 判据太粗**（`smart-canvas.js:21711`）：只看「长度 < 25 且无风格关键词」。
   这句话 15 字、不含风格词 → 判为「模糊生图请求」。
   → 触发 `processAgentLlmResult` 内**三处硬编码风格选项**：`hasAnyIntent` 前的 1.5 兜底、`replyLooksLikeJson`
   的「格式异常」兜底、以及 2. 默认 prompt 兜底里的 `isVagueImageRequest` 分支。
2. **OFF 模式上传路径吞掉请求**（`isFastPath`，`smart-canvas.js:23532`）：
   `_hasGenVerb = /画|生成|设计|创作|…/` 里的**裸 `画`** 被「画**布**」命中 → 整句被当生图原文
   直接执行，**根本不走 LLM**。
3. **思考模式系统提示词**把「风格 (画风/艺术流派)」列为第一追问维度 → 从源头鼓励问画风。

### AA.2 修法（可复用的四个抓手）

- 新增 `isCanvasOpRequest(text)`：
  - 画布结构名词（`节点|连线|工作流|流程图`）或 `画布`；
  - **结构性动词**刻意**不含「改成 / 改为」**——那通常是在改图而不是改节点；
  - 提到结构名词时：结构性动词 **或** 节点类型词（`上传节点|快速执行|快速生图|提示词节点|循环节点|视频节点|3d|分组`）即成立
    （所以「生成一个提示词节点」也能识别，而「在画布上画一只猫」不会误判）；
    ⚠️ 裸「上传」**刻意不收**（太常用，「上传一张图」会误判），只认「上传节点」；两个旧名保留兼容。
  - 只提到 `画布` 时：**必须**有结构性动词。
- 新增 `agentCanvasOpSuggestions()`（节点操作建议）与 `looksLikeStyleSuggestions(options)`（识别跑偏选项）。
- `isVagueImageRequest()` 加两条**早退**：画布操作请求、提到 `节点|工作流|流程图|连线` 的请求，都不算「模糊生图」。
- `processAgentLlmResult()` 顶部新增 `_canvasOpTask = parsed.canvas_ops.length > 0 || isCanvasOpRequest(text)`，
  并把三处生图兜底全部加 `!_canvasOpTask`；同时把 options 归一化成节点操作建议。
- OFF 模式在 `parseAgentIntentRoute` 之后新增**建议归一化**（识别到画布操作请求 → 替换风格选项；
  「画布控制」未开时回「请先点开输入框下方的『画布控制』开关」）；`isFastPath` 加 `!_isCanvasTask`。
- 思考模式系统提示词**最前面**插入「★★★ 前置判断：先分清任务类型」，禁止对非生图任务追问画风。

### AA.3 输入区新结构（HTML 顺序即视觉顺序）

```
.agent-input-area
  ├─ #agentInputResize            上拉放大手柄（顶部）
  └─ .agent-onebox
       ├─ .agent-topbar           #agentModelBtn + #agentParamsBtn（胶囊芯片，24px 高）
       ├─ #agentAttachRow
       ├─ textarea#agentInput
       └─ .agent-toolbar          #agentAttachBtn / #agentSkillMarketBtn / #agentThinkingBtn
                                  / #agentDevModeBtn / .agent-toolbar-spacer / #agentSendBtn
```

- `.agent-topbar .agent-toolbar-btn` = 圆角胶囊（`--soft` 底、999px 圆角、24px 高）。
- `.agent-thinking-btn` 是「图标 + 文字」胶囊（`flex:0 1 auto; min-width:0`，label 带 ellipsis 兜底）。
- 🚨 **英文标签比中文宽，会把工具栏挤成两行**（实测内容 313.6px > 可用 302px）。
  解法：**按钮文案与气泡标题分开用两个 key** ——
  `smart.agentSkillLabel`（en `Skills`）/ `smart.agentDevModeLabel`（en `Canvas`）只给按钮，
  `smart.asmTitle` / `smart.agentDevModeTitle`（en `Skill Market` / `Canvas Control`）留给气泡。
  改后中文 254px、英文 243px，均单行。
- ⚠️ **判「工具栏是否单行」必须过滤高度 ≤ 1px 的子元素**：`.agent-toolbar-spacer` 高 0，
  在 `align-items:center` 下它的 `rect.top` 落在行中线（实测 846 vs 其他 833），
  不过滤就会把 rows 数成 2（**假阳性**）。

### AA.4 命名与 i18n

- 「开发模式」→ **画布控制**（`smart.agentDevModeTitle` zh 改「画布控制」，新增 `smart.agentDevModeLabel`）。
- 「思维模式」→ **思考**（新增 `smart.agentThinkingTitle` / `smart.agentThinkingSub`，zh 思考 / en Think）。
- `smart-canvas.js` 两处 toast 文案同步改名。
- 改完必跑 `node static/js/i18n/validate-i18n.js`（本轮 1190 keys）。

### AA.5 无头验证套路（本轮新增，很省事）

**A. 量真实 DOM**：写同源探针 `static/__ui_probe.html`，iframe 加载
`/static/smart-canvas.html?id=<一次性画布>`，注入 `transition:none`，`w.toggleAgentPanel(true)`，
再量 `.agent-input-area` 各段 rect 与工具栏子元素 top。**中英双语各量一遍**。
- 截图用 `--force-device-scale-factor=2` + PIL 裁切放大，深浅两主题各看一遍。

**B. 桩住 LLM 跑真实 `sendAgentMessage`（`mode=e2e`）**：
拦截 `/api/agent-llm-task`：POST 回 `{task_id:'T-E2E'}`；GET 回
`{status:'succeeded', result:{text: JSON.stringify(payload)}}`。实测两条断言：
- devMode=off + LLM 返回风格 clarify → LLM **确实被调用**（证明快速路径不再吞掉请求）、
  回复被改成「请先点开画布控制」、options 全为节点操作建议、`styleOptionCount === 0`；
- devMode=on + LLM 返回 `canvas_op` → **`nodes.length` 真实 +1**（画布操作端到端生效）。

🚨 **无头里 `apiProviders` 是空的**（`chatApiProviders()` 返回 0）→ `sendAgentMessage` 会在
`if(!chatApiProviders().length){ toast(...); return; }` 处**静默 return**。
症状：**user 消息 push 了，但没有 assistant 消息、LLM 一次都没被调用**（`llmCalls === []`）。
解法：探针里 `win.eval('apiProviders = [{id:"stub",name:"Stub",enabled:true,chat_models:["stub-model"],image_models:["stub-img"],image_model:"stub-img"}]')`
注入桩 provider（只影响探针会话，不落盘）。

## AB. 「启动器保存的 API 通道读不到」= 3000 被别的 root 占用（2026-09-23）

### AB.1 一句话
`/api/providers` 只有内置默认、模型全空 → **先查 3000 上跑的是哪个 root**，别读代码。

### AB.2 三步定位
1. `GET http://127.0.0.1:3000/api/app-info` → 看 `app_root` / `root_fingerprint` / `pid`；
2. `netstat -ano` 过滤 `:30xx` LISTENING 拿 PID（本机 `grep` 被 rtk 劫持 → 用 Python 跑 netstat 再自己过滤）；
3. 查该 PID 的命令行与父进程 → **PowerShell 工具**执行
   `Get-CimInstance Win32_Process | Where-Object {...} | Select ProcessId,ParentProcessId,Name,CommandLine`
   写进文件再用 Read 读（PowerShell 工具常吞 stdout；`wmic` 在安全黑名单里）。

### AB.3 本次数据（留档）
| 项 | 开发仓库（错的那份） | 安装目录（老板真实在用的） |
|---|---|---|
| root | `D:\工作\无限画布\Infinite-Canvas` | `D:\工作\无限画布\Infinite-Canvas-Full-1.1.4\Infinite-Canvas` |
| fingerprint | `43c5720d9219b130` | `6471b56fe8f953f3` |
| VERSION | 1.1.6 | 1.1.6（目录名残留 1.1.4） |
| `data/api_providers.json` | `[]` 2B | 2003B / 3 条通道 |
| `API/.env` | 2 个 key **值为空** | 3 个真实 key（51/35/54 字符） |

启动器 exe：两处 **sha256 相同** `df948755a1d912a014d70f6a`（72270630 B）→ 说明「串台」与 exe 版本无关。

### AB.4 复用判定（`Program.cs:1515-1584`，逻辑正确，勿改）
`ProbeAsync(3000)` 活 → `FetchRemoteIdentityAsync` 取 `app_root` / `root_fingerprint` →
- 指纹相同 → 复用 + 打开浏览器（`reused=true`）；
- 指纹不同 / 取不到 → **不复用**，`PickFreePort()` 换空闲端口，用**本目录** root 起服务。

指纹算法（两边必须同构）：`normcase(realpath(path))` → UTF-8 → `sha1[:16]` 小写十六进制；
Python 侧 `main.py::_root_fingerprint()` 用 `surrogatepass`，C# 侧 `ComputeRootFingerprint()` 用 `ToLowerInvariant()` + `Replace('/','\\')`。

### AB.5 修复动作（可复用）
```bash
# 1. 停掉占着 3000 的「别的 root」服务
taskkill /F /PID <pid>
# 2. 用正确 root 在 3000 起服务
cd "D:\工作\无限画布\Infinite-Canvas-Full-1.1.4\Infinite-Canvas" && ./python/python.exe main.py --port 3000
# 3. 验证：/api/providers 应回老板的通道；/api/app-info 的 root_fingerprint 应等于该目录指纹
```
无头验证 URL 一定要带 `/static/`：`http://127.0.0.1:3000/static/canvas.html?id=<画布id>`。

## AC. 遮罩局部重绘：裁切 → 生成 → 回贴（2026-09-24，1.1.8）

### AC.1 管线一句话
`遮罩 bbox → 保持中心扩到最近标准比例 → 裁 crop + crop_mask → 按该比例出图 → 用 crop_mask 把结果抠出羽化贴回原图 → 合并图落「新的一张」图片`

### AC.2 后端可复用纯函数（`main.py:17745` 起）
- `inpaint_nearest_ratio` 用**对数距离**（比线性更贴近人的比例直觉）
- `inpaint_size_for_ratio` 优先命中 `CHAT_RATIO_SIZE_OPTIONS`，兜底在 16 倍数里**从大到小搜、误差打平保留更大尺寸**
- `inpaint_feather_for_bbox` = 短边 ×1.5%，夹 `[2,48]`
- `inpaint_mask_bbox` = `convert("L").point(lambda v: 255 if v>=128 else 0).getbbox()`
- 🚨 **`Image.paste(im, box, mask)` 语义 = `base*(1-m) + patch*m`** → 天然等于「只保留遮罩内 + 边缘羽化」，**不需要 `ImageChops`**
- 🚨 `inpaint_composite` 收到的 `mask` 必须是**已按 bbox 裁好**的；`compose_inpaint_result` 里有兜底：`if mask.size != (w,h) and mask.size == base.size: mask = mask.crop(bbox)`（防上游把遮罩当整图回传）
- `POST /api/image-mask-prepare` 空遮罩 → **400「遮罩是空的，请先涂抹要修改的区域」**

### AC.3 前端铁律（`smart-canvas.js`）
- 🚨 **`node.inpaint` 的有效性判定必须「index + base_key 双匹配」**（`validNodeInpaint`）—— 只比 index 会在换图/挪图后拿**旧 bbox 去贴新图**
- 🚨 **`replaceEditedImage` 里不能用 `validNodeInpaint` 判**（此时 url 已换、必然失效），要用 `Math.round(Number(_maskMeta.index||0)) === Number(index)`
- 🚨 遮罩**不再 push 进 `node.images`**；参考图改成 `[crop, crop_mask(role:'mask')]`
- 🚨 节点事件委托的排除列表 `.image-delete,.image-name-badge` 必须**带上 `.node-mask-badge`**，否则点「遮罩」标记会误触发删图
- CSS 提特异性：`.image-wrap >` / `.thumb-item >` 前缀（`.thumb-item img` 会把 width 压回 auto）；`.image-wrap > img` 等 6 条规则加 `:not(.node-mask-overlay)`

### AC.4 无头探针（注入式）的 6 个坑
1. **必须等画布异步加载完**再建节点（`nodes` 会被整体替换）→ 轮询 `canvas.id===CID`
2. 节点根选择器是 **`.image-node[data-id=...]`**（不是 `[data-node-id]`）
3. 底图真实地址在 **`data-original-src`**（`src` 是 `/api/media-preview?...`）
4. **不要用 `loadNodePromptDraftToInput`**（会写坏 `promptInput.innerHTML`）→ 用 `setPromptDraftForNode`
5. `window.fetch = realFetch` 还原要放到**最末**，否则漏抓
6. `EXPECT` 表必须**缺失即失败**（`data.get(k,'<missing>') != v`），否则探针早退会**假绿**

### AC.5 发版红线补充
- 🚨 **启动器只比版本号、不比文件哈希**（`Program.cs:1822`）→ **同版本号覆盖发布 = 已装该版本的人永远收不到更新提示**。想让所有存量用户收到，**必须升版本号**。
- 🚨 版本号 +1 后必须**重启服务刷新 `?v=`** 再打包（`sync_static_html_versions()` 只在启动时跑一次）
- 🚨 `output/RELEASE_NOTES-x.y.z.md` 正文**硬上限 24 行**（`read_notes_file()` 截断 `[:24]`），卡上限要逐行数

### AC.6 参考图组装（2026-09-24 补，随 1.1.8 原地重发）
- 🚨 **`reference_images` 顺序 = `[crop, crop_mask, ...用户其它参考图]`**：`crop` 必须**排第一**（上游把第一张图当基准图、mask 作用在它身上）。
- 🚨 原实现只发 `[crop, crop_mask]`，**把用户选的其它参考图全丢了** → 「涂遮罩换方向盘 + 参考方向盘特写」这类多图用法直接失效。
- 剔除规则：被遮罩那张原图本身（`base_key`/`base_url`/`mask_url`/`crop_url`/`overlay_url`）、任何 `role==='mask'`、任何 `*_mask.png`；按 url 去重；总数受 `providerMaxReferenceImages()` 限制。
- 🚨 **遮罩上传给 `/images/edits` 必须做两件事**（`prepare_mask_for_multipart()`）：
  1. **尺寸与基准图一致** —— 基准图会被 `prepare_reference_for_multipart()` 缩到 1536，遮罩原来原样上传 → 大图裁切时尺寸不匹配；
  2. **RGBA 双约定** —— `Image.merge("RGBA",(l,l,l,invert(l)))` → 可改区 `(255,255,255,0)`、其余 `(0,0,0,255)`。画布约定是**白=可改**，OpenAI 约定是**透明=可改**，这样两种解释同时成立。
  （同款约定转换的既有先例：`midjourney_modal_mask_url()` `main.py:18220`。）
- ⚠️ **Grsai 的 nano-banana 走 `is_grsai_nano` 分支，`mask` 字段根本不会发**（只发 `images`）→ 那条通道上只靠「回贴时只保留遮罩内」兜底，**不是完整语义的局部重绘**；要真遮罩得选 `gpt-image-2 / 2.5`（openai-compatible → `/images/edits` multipart）。
- 探针三个坑：**没有全局 `connections`**（在 `canvas.connections`，`{from,to,kind}`）；**参考图只走 `kind==='input'` 的连线**（`'flow'` 只在 workflow 模式算输入）；`buildPromptRequest()` 的 refs 带 `role:'image_N'`，**编号随上游参考图数量变化，断言别写死**。

## AD. 🚨 增量包基线被污染 = 静默漏发主程序与前端（2026-09-24，1.1.8 事故）

### AD.1 机制
`release.py:find_previous_baseline()` 只扫 `output/release/` 下**版本号最大且小于本版**的目录，读它的 `file-hashes.json`；
`changed = [rel for rel,h in hashes.items() if base_hashes.get(rel) != h]`，**delta 包里只放 `changed`**。

### AD.2 事故
遮罩重构完成后，**在 VERSION 还是 1.1.7 时先跑过一次 `build`**（`output/release/1.1.7/` 被新内容覆盖），
随后 bump 到 1.1.8 再 build → 1.1.8 的 delta 认为「main.py / 全部 js / css 都没变」，
**只有 16 个条目**：13 个 `static/*.html`（`?v=` 变了）+ `VERSION` + `update-notes.json` + `release-manifest.json`。
老板更新后：版本号 1.1.8、HTML 是新的，**但后端没新接口、前端还是旧脚本** → 「功能完全没生效」。
`from_version` 检查、`verify`、体积检查**全都过得去**。

### AD.3 识别（症状）
- `data/update_backups/<ts>/` 里的 `VERSION` + `manifest.json` 说是新版，但 `static/js/*.js` 的 sha256 **既不是工作区那份、也不等于本版包内那份**（安装目录 manifest 记录 vs 盘上实际文件不一致）
- delta 体积小得离谱（几 MB 而不是十几 MB）；`build` 日志「变更 N 个」远小于预期

### AD.4 修法与预防
- **修法**：把被污染的版本目录**移出 `output/release/`**（如 `output/release-archive/<ver>/`）→ 基线回退到**上一个未被污染的版本** → 重新 build（本次 1.1.6 基线 → 变更 1144 个）
- **预防**：① **不要为已发布过的版本号重新 build**；要重打先把它移出 `output/release/`；② 每次发版做「增量包内容核对」（关键文件必须在包里，见技能 `infinite-canvas-release` §6）
- 🚨 **启动器只接受 `from_version == 当前版本` 的 delta**（`Program.cs:1788`），不匹配就退回**完整包**
  → **把基线往回退一版 = 让所有存量用户走完整包**，这正是「已知旧安装状态不干净、必须装完整」时想要的兜底。
  （本次刻意用 1.1.6 基线：老板是「坏的 1.1.8」，与 1.1.6 不匹配 → 自动走完整包 → 一定装完整。）

### AD.5 「包坏了但版本号没坏」怎么发：**原地重发同一版本号**
- 事故的版本号（1.1.8）**已经被老板装到机器上了**，此时**升版本号是错的方向**：老板明确要求「不要构建新的版本，在 1.1.8 基础上继续改」。
- 正确做法：**保持 `VERSION` 不变**，只把 `update-notes.json` / `RELEASE_NOTES-*.md` 内容更新（加一条「本次重新发布的 1.1.8 修复了首版增量包漏发的问题」），**重新 build 同一版本号的包**，发布时用
  `gh release upload <已存在的 tag> <资产> --clobber` **覆盖**（`Official.1.1.8` 已存在 → **不是** `gh release create`）。
- ⚠️ `update.json` **必须一起替换**：启动器读的是 `releases/latest/download/update.json`，不换等于没发。
- ⚠️ 若中途已经 bump 过新版本号（本次曾到 1.1.9）：`bump_version.py --set <原版本>` 退回、把新版本号的 release 目录移入 `release-archive/`、删掉对应 `RELEASE_NOTES-*.md`；**提交用 `git commit --amend`** 把工作区改回去（未推送时），别留一个「VERSION=新版本号」的历史提交。

### AD.6 🚨 另一类半成品安装：**更新时文件被占用 → 解压中途崩溃**（2026-09-24，第二次踩）
> 与 AD 的「基线污染」症状几乎一样（版本号新、功能没变），但**根因完全不同**，必须分开诊断。

**症状**：安装目录 = 「后端新 + 前端旧」。
**铁证**：安装目录 `main.py` 的 sha256 == 工作区那份（最新），但 `static/js/smart-canvas.js` 是旧版、`static/*.html` 的 `?v=` 还是上一版的版本号前缀。

**两个真 bug（本轮已修）**：
1. 🚨 **`Program.cs:PrepareForUpdate()` 只杀「自己拉起的」服务**（`server` 对象）。**孤儿服务进程**（上次启动器崩溃/被强杀后活下来的 `python.exe`）不会被杀，它一直占着 `python\Lib\site-packages` 下的 `.pyd`（PIL）→ full 包解压到一半 `IOException`。
   - 实测：3000 端口那个服务**启动于 10:12**，而**启动器根本不在运行** → 孤儿；`update.log` 里**从未出现「已停止服务进程」** → 这条路径一直没生效。
   - **修**：新增 `KillProcessesUnderRoot(root)` —— 按「可执行文件位于安装目录内」兜底结束 `python*` / `Lochou*` / `_apply_update_*`（`Process.GetProcesses()` + `MainModule.FileName`，逐项 try/catch 防权限/位数异常）。
2. 🚨 **`UpdateApplier.ExtractOverwrite()` 遇到任何 IO 异常就整体中止** → 留下半成品（无重试、无自动回滚）。
   - **修**：① `FindLockedTargets()` **预检** —— 解压前逐文件试 `FileStream(..., FileShare.None)`，**被占用就一个字节都不写直接中止**（先退避重试 6 轮 × 800ms）；② `ExtractOverwrite(..., out failed)` 逐文件退避重试 5 次 × 500ms；③ 预检通过后仍中途失败 → `RestoreFromRestorePoint()` **从刚建的恢复点整体还原**，绝不留半成品。返回码：6=预检被占用、7=中途失败已还原。

**诊断手法（照这个顺序查，别猜）**：
1. **问服务它是谁**：`GET /api/app-info` → `app_root` + `pid`（比读代码可靠）
2. **看更新日志**：`%LOCALAPPDATA%\InfiniteCanvasLauncher\update.log` —— 有 `已写入 N 个文件`、`已创建恢复点`、`[异常] IOException ... because it is being used by another process` 原文，**是还原老板操作序列最直接的证据**
3. **看备份时间线**：安装目录 `data/update_backups/` —— `rollback-<ts>` = 回退前安全快照，`<ts>` = 每次更新前
4. **判前端新旧**：`static/js/smart-canvas.js` 里有没有 `inpaintReferenceImages` / `maskOverlayHtml`（新版有）
5. **判遮罩是新是旧**（看画布 JSON）：旧版 = `node.images` 里多一条 `role:'mask'`、name 以 `_mask.png` 结尾；新版 = 存在 `node.inpaint`（遮罩**不进** `node.images`）
6. ⚠️ **`release-manifest.json` 的 `files` 是「全量清单」（3139 条），不是「本次变更数」** → **不能用它判断装了多少**，必须看 update.log 的 `已写入 N 个文件`
7. 安装目录文件 mtime 全 `01-01 00:00:00` = zip 解压特征；工作区文件有真实 mtime
8. **验证「C# 改动是否真进了 exe」**：单文件 bundle **压缩存储**，明文 grep 连对照组都搜不到（假阴性）。正确做法见 R.4 —— 解 bundle 取内嵌程序集再搜，**必须带兄弟常量对照**。
   - 取内嵌程序集：**footer 不在文件末尾**（末尾是清单里最后一条的条目名）。用 `data.find(bytes([len(name)]) + name.encode())` 定位条目名，读它**前 25~1 字节**的 3 个 int64 = (Offset, Size, CompressedSize)，再 `zlib.decompressobj(-15).decompress(data[off:off+csize])`。
   - ⚠️ C# 字符串是 **UTF-16LE**，搜 UTF-8 必然 0 处；且**插值字符串会被拆成多个字面量**（`$"…{x}…"` 搜整句搜不到），断言要挑**纯字面量片段**。
   - 实测：解出的内嵌 dll 大小 243,200 B == `launcher/bin/Release/net8.0-windows/win-x64/InfiniteCanvasLauncher.dll`，7 条新增字符串全命中。

## AE. 2026-10-09 下沉：3D 节点 + Agent/Skill 市场（为 `MEMORY.md` 回到 8KB 以内）

### 3D 预览节点 `smart-3d`

- 上下游**只接「上传」节点**（`smart-image`，旧名「快速生图」，中间短暂叫过「快速执行」未发布）。
  改连线规则时 `canAutoConnectDraggedNode()` 与 `connectInputNode()` **两处都要改**。
- 三条硬约束：① **折叠阈值按实测文案宽度**（不能拍脑袋）；② **失败态必须加 `.is-error`**；③ **取色随挂载面**（深浅主题）。
- 🔄 **迭代流程已回退（2026-10-08 16:05，老板要求）**：现为**原版一次成型**（一次请求出几何 + 原 three.js 交互）。
  回退前那套「细节清单 → 质量门 → 3 轮生成/渲染/截图/视觉自检 + 四维徽章」完整实现备份在
  `output/backup-3d-rework-20261008-1605/`（含 `3d-rework.patch` + 三个源文件 + 恢复说明）。
  ⚠️ 回退只动代码，**画布 `data/canvases` 未受影响**：3D 节点的 `node.scene3d` 仍在，原版照常渲染；
  残留的 `node.smart3d` 字段原版代码**完全不读**（已核 9 处 `.smart3d` 全是 CSS 类名）。
- ⚠️ 日后重做那套迭代流程，三条**已踩过的坑**先读备份 README：
  ① 细节清单**带序号**喂给自检会让模型把序号抄进 `name` → **整批对不上**、界面显示假的 `细节 0/M`
  （需归一化 + 位置兜底 + 诚实标记）；② 相机对齐只在提示词里写一句 `Set "camera" ...` **模型不会执行**；
  ③ 每轮生成后**必须等两帧再截图**，否则自检输入是空白图。
- 🚨 **`coder` 通道不稳**（与回退无关，仍成立）：实测 22 次 `/api/canvas-llm` 里 **524×6 + 502×2 全在 `coder`**，
  同期 `grsai` 零失败；524 = 中转前的 Cloudflare 读超时（~100s）。3D 节点一次请求就可能超 100 秒，用 `coder` 容易失败。
- 🚨 **徽章语义（老板误读后改定）**：未评 = 灰底 `circle`；进行中 = 蓝底 `loader-2`；
  已评 = **直接显示分数**（绿通过 / 黄需修）。**`triangle-alert` 只允许出现在真错误态**
  （曾用它表示「未达标」被读成报错）。阶段文字必须区分 已完成 / 失败 / 已中断。
  开跑时 `dims` 清空、旧分数挪进 `lastDims`（否则「处理前/后」都是黄的）。

### Agent 两套 + Skill 市场

- 🚨 **分类规则**：命中按**整词**（中文裸子串 / `词*` 前缀 / 英文词边界）；**技术栈不当分类**、
  **裸品牌词必限语境**；大分类 = **累加子分类权重**（最高单标签会**单票否决**）；
  `design`/`image-video` = 软标签；**标签现算**。
- 🚨 **市场两坑**：① star/fork/热度是**仓库级** → 同仓并列占满首屏 → `spreadByRepo()` 同仓错峰；
  ② 列 flex 里的横向滚动容器 `min-height:auto`=0 被压扁 → 改 `flex-wrap:wrap`。
- 🚨 **两套 agent 必须同时改**：`gpt-chat.html` → `/api/chat/agent`；
  `smart-canvas.html` `#agentPanel` → `/api/agent-llm-task`。
- ✅ 本机工具 `run_shell` / `read_file` / `write_file` / `list_dir`；
  开关 `GET|POST /api/agent/tools`（默认关 / 8 轮 / 上限 20）。
  🚨 **上游不支持 tools 要优雅回退**；**工具循环与流式不能混用**。
- ✅ **Skill 市场 = SkillsMP**（`skills-catalog.json` + 缓存 `skills_market_cache.json`，**缓存优先**）。
  🚨 **`refreshed_at` 要 ×1000**；**刷新失败要删污染缓存**；**搜索走服务端全站，按相关性排**。

### 发布/安全两条补充（原 `MEMORY.md` 第七节尾部）

- 🚨 **无头验证走技能 `infinite-canvas-verify`**；**证明「常量从 exe 消失」** → 解 bundle 取内嵌 dll 再搜 +
  **兄弟常量对照**（单文件 bundle 压缩，明文 grep 假阴性，见 R.4）。
- 🚨 **Codex 权限 4 档**（`data/codex_permissions.json`）；`#codexCliPanel` **只在 `protocol=codex` 时显示**；
  ⚠️ **不改全局 `~/.codex/config.toml`**（含明文 token）。O.6。

## AF. 2026-10-09 下沉（第二批：为 `MEMORY.md` 回到 8KB 以内）

### 启动器联网更新 Grsai 模型清单（原 `MEMORY.md` 第三节）

- ✅ **启动器每次运行会联网更新 Grsai 清单（2026-10-09 加）**：Grsai **没有任何 `/models` 接口**
  （穷举 30+ 路径全 404；只有 `POST /v1/api/generate` + `GET /v1/api/result`），官网也是纯营销站
  （sitemap 仅 4 条）。**唯一可联网来源 = 它自己的控制台文档页 `grsai.ai/zh/dashboard/documents/chat`**，
  把「支持模型」以纯文本内嵌在 `_next/static/chunks/*.js` 里（实测 32 个，比内置多 `gpt-5.4`/`nano-banana-2.1`）。
  落地：缓存 `%LOCALAPPDATA%\InfiniteCanvasLauncher\grsai-models.json` + **只增不减**并进
  `data/api_providers.json` 的 Grsai 通道（写前备份，无新增不写）。
- 🚨 **扫 chunk 必须并行**（单请求 TTFB 5~16s，串行 16 个要 3 分 20 秒，`Chunk(4)` 后 ~2 秒）。
- 🚨 **分类关键词表必须与前端 `Qe()` 逐字一致**。
- 🚨 缓存放 `%LOCALAPPDATA%` **不放项目 `data/`**（release 扫描只允许留 `inspire_prompt_zh.json`）。
- 诊断：`Lochou启动器.exe --probe-grsai-models [配置副本路径]`。细节 `2026-10-09.md §1`。

### 「更新后功能没变」两类根因（原 `MEMORY.md` 第五节）

- 🚨 **症状一样、必须分开查**（AD.5/AD.6）：
  ① **增量基线被污染**（见 AD）→ 版本号变了但关键文件不在 delta 里；
  ② **更新时文件被占用 → 解压中途崩**（孤儿 `python.exe` 占 `PIL/_avif.pyd`，或残留启动器占自己的 exe）
  → 留下「后端新、前端旧」的半成品。
- **排查顺序**：先看 `%LOCALAPPDATA%\InfiniteCanvasLauncher\update.log`（找 `已写入 N 个文件` 与
  `[异常] IOException`）与 `data/update_backups/` 的时间线，再看 `GET /api/app-info` 的 `app_root`/`pid`。
- ⚠️ **`release-manifest.json` 的 `files` 是「全量清单」（3139），不是变更数** —— 别拿它判增量。
- **判前端新旧**：看 js 里有没有 `inpaintReferenceImages`。**判遮罩新旧**：看节点有没有 `node.inpaint`
  （旧形态 = `node.images` 里多一条 `role:'mask'`）。

### 进程枚举与启动器窗口（原 `MEMORY.md` 第五节尾部）

- ✅ **枚举「某目录内的进程」用 ctypes**（`CreateToolhelp32Snapshot` + `QueryFullProcessImageNameW`）
  才能拿到 exe 路径；`tasklist` 没有路径，图形化命令行工具会被沙箱拦或吞 stdout。
  ⚠️ **本机 PowerShell 的 `Get-Process` 会静默无输出**（工具返回 exit 0 但 stdout 为空）→ 改用 ctypes。
  ✅ 读单个 pid 的启动时间也可用 ctypes `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetProcessTimes`
  —— 判断「重启有没有拿到新代码」时很有用。
- 🚨 **窗口圆角**：只能**逐像素透明**（与 `WS_EX_LAYERED` 互斥）+ `#root{border-radius}`；
  **绝不可加 `CS_DROPSHADOW`**；内缩 = `2/devicePixelRatio`。⚠️ **无头截不到启动器窗口**。Q.5/S.2–S.4。

### 静态资源版本号 `?v=` 的离线补法（2026-10-09 新增）

- 背景：`sync_static_html_versions()` **只在服务启动时跑**，会把 `static/*.html` 里**已存在**的 `?v=`
  改写成 `1.1.8.<该文件 mtime>`。**改了前端却没重启 → 页面还挂旧 `?v=` → 浏览器吃缓存旧 JS/CSS，改动根本不生效。**
- ✅ **不想重启服务时的离线补法**：跑 `output/spike/resync_static_v.py`（把 `versioned_static_html` +
  `sync_static_html_versions` 两步逻辑原样搬出来，只改盘上的 html，与启动行为逐字一致）。
  `static/*.html` 是**每请求从盘上读**的（`static_html_response` + `no-cache`）→ 改完**刷新页面即可**，无需重启。
- ⚠️ 它**不会**给 `.png`/`.svg`/字体加 `?v=`（正则只匹配 `.js|.css|.html`）→ 这些首次要手加种子（O.5）。

## AG. 2026-10-09 下沉（第三批：拆分图层自研画板，为 `MEMORY.md` 回到 8KB 以内）

> 原 `MEMORY.md` 第九节。触发背景：老板反馈「页面太杂乱 / 右侧只该显示图层内容 / 失败要给反馈 /
> 背景层不是纯背景 / 文字层找不到 / 图层不能简易缩放」六条，一轮全部落地。

### 六条诉求 → 落地方式

1. **页面太杂乱** → 右侧默认换成**自研轻量画板**（`.sl-board`，按 z 叠放 + 透明棋盘格底）；
   Photopea 降级为**按需**「精细编辑」按钮（`#splitLayersPeaBtn` → `splitLayersTogglePea()`），
   **不用就完全不创建 iframe**（顺带消掉自带菜单栏与右侧两条 €15 广告）。
2. **只显示图层内容** → 画板不选中时就是干净效果图，选中才出控制点。
3. **失败反馈** → 后端 `error_detail{phase, phase_label, message, advice, tried}`；
   前端失败卡片三行「卡在 / 原因 / 建议」+「已尝试：通道/模型」+「换个模型重试」。
4. **纯背景** → `split_element_mask` + `split_erase_elements`（见下）。
5. **文字层定位** → 列表缩略图叠红框 `.sl-spot`（百分比定位，`Math.max(6,…)` 保底可见）
   + 选中时画板高亮描边并 `.flash` 闪两下 + 列表 `scrollIntoView`。
6. **简易编辑** → 拖动位移 / 四角缩放 / 顶部圆点旋转 / 不透明度滑块 / 复位 / 旋转 ±90° / 适应窗口。

### 纯背景（`split_element_mask` / `split_erase_elements`）

> ⚠️ **2026-10-09 二次返工**：老板反馈「背景跟原图不同所以是不对的」。
> 现场取证：`assets/output/split_in_65281f03eb.png`（原图 = 花园里端茶的女人）vs
> `split_base_09810054ed.png`（产出的「背景」= **一张构图都变了的新花园**）。
> **根因**：把**整幅图 + 遮罩**交给生图模型，让它「重画一张干净底图」——
> gpt-image 这类模型拿到全画幅生成任务会**把整帧重绘**，提示词写
> 「black regions must stay pixel-identical」也拦不住。
> **修法见下**（局部重绘 + 只贴回遮罩区）。

- 「背景层」**原来的语义 = 原图只抹掉文字**（`base_rgba`），**前景元素原封不动留在里面**
  → 隐藏前景层时会看到重复物体。这就是老板说的「背景层混了前后景」。
- 做法：把全部前景元素 bbox 合成一张**黑白遮罩**（白 = 要移除、黑 = 保留），
  与原图一起交给生图模型做 object removal，产出真正的纯背景层。
  沿用项目既有的局部重绘约定（白 = 可改、黑 = 保留）。
- 🚨 **必须「局部重绘 + 只贴回遮罩区」**（第二轮修的）：
  1. 遮罩 union bbox 外扩 `pad = max(64, 长边 × 0.25)` → `crop` + `crop_mask`；
  2. `split_square_pad(crop, min_side=384)` 补方，**遮罩用同一套补方偏移**
     （`mask_sq.paste(mask_up, offset)`），否则模型看到的 1、2 两图位置对不上；
  3. 出图 → `split_unpad` → resize 回 `crop.size`；
  4. **`out = base_rgba.convert("RGBA").copy()` 后 `out.paste(patch, (x0, y0), feather)`**
     —— **遮罩外的像素直接沿用原图，逐字节相同**。这是「背景跟原图一致」的硬保证。
- 提示词要写明局部裁切语境：`Image 1 is a CROP of a larger photo` +
  **`Do not re-render, re-style, re-compose, zoom or crop the picture`**。
- 🚨 **羽化半径是个坑**：`ImageFilter.GaussianBlur(σ)` 内部换算成 **3 次盒模糊**，
  实际影响半径 ≈ `3 × σ × 3√(2π)/4 ≈ 5.6σ`。
  **实测**：σ=8 → 遮罩外溢 **43px**；σ=3 → 外溢 **8~32px**。
  那圈正是「背景跟原图不一样」最容易露馅的地方 → 最终定 **σ=3**。
- 🚨 **遮罩外扩是必要的**：模型 bbox 本来就偏（实测 ~41px 量级），紧贴会把物体边缘留下。
  `pad = max(8, max(w,h) * 0.06)`。
- 🚨 **PIL `ImageDraw.rectangle` 两端是闭区间**（会多盖 1px）→ 右下角**减 1**，
  覆盖范围才精确等于 `[x-pad, x+w+pad) × [y-pad, y+h+pad)`。
- 🚨 **遮罩覆盖 >= 0.98 直接跳过**（那已经不是「去前景」而是「重画整张图」，做了白花钱）。
- 🚨 **一次整图调用**，不是逐元素各打一次（耗时与费用按元素数线性上升）。
- 失败 → 返回 `None`，回落 `base_rgba` 并把 `bg_pure` 记成 `false`（诚实标记，不假装是纯背景）。
- 与「文字精修 refine」**并发跑**（一个用对话模型、一个用生图模型，不争抢资源）。
  🚨 `try/finally` 里必须 `pure_bg = await bg_task`，否则 refine 抛异常时会留
  「Task exception was never retrieved」这种难查的噪音。

### 阶段追踪与失败文案

- `phase` 变量在 `run_split_layers_task` 里逐段改写，`except` 里据此出建议：
  `prepare`(读取图片) → `analyze`(分析画面元素) → `erase`(抹除文字) → `background`(生成纯背景)
  → `refine`(校准文字位置) → `extract`(提取图层)。
- 建议按**能力类型**分：`analyze`/`refine` 是**对话/视觉模型**（换「分析通道/模型」，优先多模态）；
  `erase`/`background`/`extract` 是**生图模型**（换「生图通道/模型」，优先 gpt-image 系列，
  错误里出现 credits/quota/余额 = 额度用尽）。
- `tried` 挂在异常对象上（`err.tried = [f"{pid}/{mdl}", …]`），在 `split_call_image_model`
  与 `split_analyze` **两处**都要挂。
- 🚨 **`splitLayersFail()` 的状态栏恒写「拆分失败」**（只有 toast 带 `message`）
  → **看到笼统的「拆分失败」基本就是前端超时**（后端失败必带非空 `error`）。

### 画板：transform 与合成必须同一套顺序

- 🚨 **CSS transform 与 canvas 合成必须逐字对应**，否则「画板上看到的」≠「导出的」：
  `translate(cx+tx, cy+ty) → rotate → scale → translate(-cx, -cy)`
  （对应 CSS `transform-origin: center center`）。
- 🚨 **`--sl-hs` 反向缩放**：画板整体 `scale(fit)`（大图 fit ≈ 0.31），控制点/描边若不定向放大
  就只剩 3px 抓不住。JS 往 board 写 `--sl-hs = 1/fit`，CSS 用 `calc(10px * var(--sl-hs, 1))`。
- 🚨 **`data-split-layer`（列表）与 `data-split-node`（画板）必须分开**：否则点画板上的层
  会被列表的 click 处理再接一遍，选中逻辑跑两次。
- 🚨 **画布节点只能存服务端 URL** → 烘焙后的图走 `POST /api/ai/upload-base64`
  （`{data, content_type, name}` → `{files:[{url}]}`）；identity（没动过）时直接用原图，省一次重编码。
- 手势细节：`pointerdown` 时若未选中**先选中再继续本次手势**（否则要「点一次选中、再点一次才拖」）；
  `move` 时 tx/ty 要**除以 fit**；角控制点用「到中心距离比」算 scale。

### 不透明度与文字层编辑（2026-10-09 二次返工）

- 🚨 **不透明度「没有实质作用」是真 bug**：`splitLayersApplyLiveTransform()` 原先
  **只写 `node.style.transform`**，没写 `opacity`。滑块 → `splitLayersSetOpacity` → 只调这个函数，
  于是 `layer.edit.opacity` 变了、数值也变了，**但 DOM 上的 opacity 永远不变**，画面纹丝不动。
  修法：该函数同时写 `transform` 与 `opacity`（拖拽路径也共用它，无副作用）。
- ✅ **文字层可编辑**：新增 `#splitLayersTextBar`（夹在 `.sl-stage-bar` 与 `.sl-board-wrap` 之间），
  **只在选中 `kind === 'text'` 的层时出现**：文案输入框 + 字号 + 颜色 + 加粗 + 对齐。
  - 新增 JS：`splitLayersTextAlignOf`（归一化 left/center/right）、
    `splitLayersRenderTextTools`（显隐 + 回填）、`splitLayersEditText`（写字段 + 重排）。
    在 `splitLayersRenderSelTools()` 末尾调 `splitLayersRenderTextTools()`，任何重排都会同步。
  - 🚨 **不回写正在输入的控件**（`el !== active` 才写 value）：每敲一个字都会重排画板，
    回写 value 会把光标弹到末尾，中文输入法还会把候选词打断。
  - 🚨 **`[hidden]` 必须显式写 `display:none`**：作者样式 `.sl-text-bar{display:flex}` 会盖掉
    UA 的 `[hidden]{display:none}`（作者表优先于 UA 表），漏了这条编辑栏永远收不起来。
  - 🚨 编辑栏占掉一行 → 显隐变化时要重跑 `splitLayersFitBoard()`，否则画板溢出/留白。
  - 改的都是 layer 上的字段，**导出 / 合成 / 铺到画布读同一份数据**，画板改完两边自动一致。
- 🚨 **文字在画板与 canvas 合成里必须同样「不自动换行」**：画板用 DOM 渲染、导出用 `ctx.fillText`。
  CSS 用 `white-space: pre` + `.sl-layer.text{overflow:visible}`，合成端按 `\n` 拆分逐行 `fillText`。
  任何一边加了自动换行，都会「所见 ≠ 所得」。

### 其它仍成立的红线

- 入口：上传节点顶部菜单 `splitLayers`；弹层 `#splitLayersModal`（**必须挂 `#shell` 之外**，
  否则被父级 `transform` 影响定位）；后端 `POST|GET /api/split-layers-tasks`。
- ✅ **auto 太慢已修**：**erase/refine/extract 三段全有界并发**（`split_run_limited`，3/3/4），
  原串行 ~35 分 > 前端 20 分超时 → 界面全空；现全链路 **332.5s**。
  🚨 单元素失败不拖垮整任务；**并发别往高调**（上游易 524）。
- ✅ **层数 + 模型可选**：`target_layers` 2–12，`N` = 背景 1 + 前景 (N-1)，**文字不占层数**。
  🚨 **背景层必须后端兜底**（抹文字后的 `base_rgba` 落盘，`method='base'`），**绝不让模型产**。
  🚨 模型选择 = **照 Agent 面板的「通道 + 模型」两级联动**（4 个下拉）；
  🚨 **实时读通道、绝不写死通道 id**（实测 `grsai` 中途被换给别的通道，Grsai 变成 `ep_<时间戳>`）；
  复用 Agent 的 helper，存 `slChatSel`/`slImageSel`(JSON)。
  🚨 层数下拉叫 `splitLayersLayerSelect`（曾与侧栏 `splitLayersCount` 撞名）。
- 🚨 **Photopea 嵌入**：iframe 指向 `photopea.com`（**必须联网**）；跨域读不到本地图
  → 图层一律 **data URI + `app.open(uri,null,true)`**；**`doc.layers[0]` 是最上层** → **按 z 升序注入**。
- 🚨 **喂图会缩到长边 1024，且只缩不放** → 模型回报的 **bbox 与 font_size 都要按 `sx,sy` 还原**
  （font_size 漏还原过一次）。**图像模型还会改输出尺寸** → 元素层一律
  「裁切 → 重绘 → 贴回原位、产出全画布尺寸」。
- 🚨 **模型 bbox 偏 ~41px** → `split_refine_text`（裁局部自放大 2–3× 再问）压到 ~19px；
  **但字号只认整图那次**（放大后反而更差）。
- 🚨 **本机无头 Edge 已废**（**单实例委派**：44 个 `msedge.exe` 的父进程是老板的常规会话）
  → 前端验证改走 **Node 从源码抽真实函数 + 最小桩跑断言**（`output/spike/verify_split_board.js` 31/31、
  `verify_split_models.js` 21/21）或**静态一致性核对**
  （`output/spike/check_split_static.py`：id 唯一 / JS 引用 id 全在 / `data-split-*` 不混用 /
  onclick 全有定义 / i18n key 全在 / lucide 按 **PascalCase** 查 / 失败卡片 id / `--sl-hs` 两端一致）；
  **不杀老板的 Edge**。
- 🚨 **通道兜底**（`split_candidate_channels` + `split_rejected`）：**被拒类**错误
  （credits/quota/余额/unauthorized/not found）才自动换下一个；**超时类 524/502 故意不换**
  （可能已扣费，重复花钱）。实测：grsai 生图余额不足时自动落到 `coder/gpt-image-2.5`。
  ⚠️ **grsai 的对话额度与生图额度分开**：同一个 key 对话能通、生图报 `credits not enough`；
  且 **`nano-banana-pro` 成功也不吐透明图**，能出真透明的只有 **`coder/gpt-image-2.5`**。
- ⚠️ 上一轮遗留的模型质量瑕疵（analyze 重复文字块拆分、refine 后 bbox 覆盖前一块）**尚未处理**。


## AH. 2026-10-09 下沉（第四批：拆分图层「像素优先」—— 还原度根治）

**触发**：老板「@截图 功能是对上了，但是**对比原图的还原度还是不够**，有没有更好的方案」。
老板选定三项口径：文字层「**默认像素，可切编辑态**」／元素层「**只用原图像素抠图**」／背景层「**移除元素层补全背景**」。

### AH.1 先用取证把「漂移源」钉死，再改代码

不要凭感觉调参。用 PIL 把上一轮真实产出逐像素比：

| 比对 | 结果 |
| --- | --- |
| 背景层 `split_base_cf4526d99b.png` vs 输入图 `split_in_e1557a2ae5.png` | **md5 完全相同**（这次背景就是原图本身） |
| 元素层 `split_layer_65c80fa003.png` 不透明区 RGB vs 原图 | **偏差 0/255** |
| 背景 + 元素层叠加 vs 原图 | **平均 0.000 / 最大 0** |

→ 结论：**背景层与元素层本来就是像素保持的，唯一的漂移源是文字层** ——
前端 `ctx.fillText` + 系统字体重画，字体 / 字重 / 字距 / 描边 / 发光全对不上，
位置还是模型猜的（偏 ~41px）。

### AH.2 核心原则：模型只回答「哪里有什么」，像素一律从原图裁

新增五个函数（`main.py`，插在 `split_unpad` 之后）：

| 函数 | 职责 | 关键约束 |
| --- | --- | --- |
| `split_layer_hole(alpha)` | 图层 alpha → 「背景要挖的洞」 | **必须二值化**（`>0 → 255`）：留半透明像素，背景补丁会透出来，叠加就不再恒等 |
| `split_local_fill(img, hole)` | 洞里用「降采样再放大」的低频内容补上 | 纯 PIL、**不调模型**；**洞的边界不羽化**（否则补丁溢出洞外，在元素层旁露一圈非原图颜色） |
| `split_pixel_layer(src, W, H, item, …)` | 从**原图**裁这块 + 本地抠图 alpha，产出**全画布尺寸**透明层 | 像素取 `src_rgba`（**不是**抹过文字的底图）；抠不出透明区就整块保留；外扩 `pad` 是必须的（`split_local_cutout` 靠四边 flood-fill，贴边的框没有背景可吃） |
| `split_background_plate(src, W, H, plates)` | 背景层 = 原图减各层覆盖范围 + 本地补洞 | 以原图为底、**强制不透明**（`putalpha(255)`，否则画板透棋盘格）；洞 = `ImageChops.lighter` 各层 alpha |
| `split_reconstruction_check(src, plates)` | 各层按 z 叠加 vs 原图逐像素比 | 输出 `{mean, max, bad_ratio, ok}`，阈值 `mean<1.0 and bad<0.002` |

**为什么这套一定对**：只要每层像素都取自原图**同一坐标**，叠加就**恒等于原图**，
**与 bbox 准不准无关** —— 把原图像素原样贴回原处 = 什么都没变。
（`verify_split_pixel.py` 第 6 节把 bbox 整体偏 17px，还原度仍然 `mean=0/max=0`，这就是这条性质的回归测试。）

### AH.3 编排改动（`run_split_layers_task`）

- **删掉 erase 阶段**（`payload.erase_text` 保留字段但不再读，前端已改传 `false`）：
  文字是从原图裁出的像素层，背景又是「原图减各层」，文字自然不在背景里；
  而抹文字会改掉底图像素，**反而让叠加不再等于原图**。
- **删掉 `refine_all` / `pure_background` 两条并发 task**：不再有生图调用，没有资源可争。
- 元素层与文字层都走 `split_pixel_layer`（`want_redraw = mode == "model"` 时才走 `split_extract_element`）。
- 背景层走 `split_background_plate`（`payload.pure_background` 关掉就退化成整幅原图）。
- 新增 `plate_by_id` 记账 + `result.reconstruction` + `stats.redraw/model/local`。
- 文字层产出 `textMode: "pixel"` + `url`。
- `split_erase_text` / `split_erase_elements` **保留实现**但 docstring 标注「已不在默认流程里」
  （它们是项目里「用模型补平 / object removal」的唯一完整实现，`verify_split_*` 与本文仍在引用）。

### AH.4 前端契约：文字层「像素态 / 编辑态」

- 判定 `splitLayersIsPixelText(layer)` = `kind==='text' && textMode!=='edit' && !!url`。
- **判定必须排在 `kind==='text'` 之前**，三条路径都要：
  - `splitLayersTextNodeHtml`（画板 DOM）→ `<img>`
  - `splitLayersCompositeTo`（导出/铺画布）→ `drawImage`
  - `splitLayersBuildDocument`（注入 Photopea）→ `splitLayersInjectImage`
  任何一条漏了，那条路径就退回系统字体重画，还原度当场归零。
- 🚨 **像素文字层的 url 是全画布尺寸的 PNG，而盒子是 OCR bbox** →
  必须显式 `position:absolute;left:-box.x;top:-box.y;width:CW;height:CH`，
  否则 CSS 的 `.sl-layer img{width:100%;height:100%}` 会把整幅压进 bbox（图变形）。
  内联样式优先级高于样式表，能盖掉那条 100%。
- 🚨 **列表缩略图仍用 `T` 徽章**，不换成真图：全画布透明 PNG 缩到 40px 只剩一点淡痕，
  不如徽章一眼认出「这是文字层」；「在哪」由 `sl-spot` 定位框负责。
- 文字编辑栏：像素态把文案/字号/颜色/加粗/对齐**全部 disable** + 提示
  「像素态：与原图逐像素一致，不可改字」；切编辑态后启用 + 提示
  「编辑态：系统字体重画，与原图会有差异」（`.warn` 变色）。切换按钮标签随态变化
  （`转为可编辑` / `还原像素`），切态要重排列表 + 画板。
- 🚨 **`splitLayersSetBusy(false)` 会把文字控件一律解禁** → 末尾要重跑一次
  `splitLayersRenderTextTools()`，否则任务跑完像素态的禁用被抹掉（等于白禁）。
- 状态栏：`splitLayersFidelityText(result.reconstruction)` 显示还原度；
  🚨 原先这里连写两遍 `SetStatus`，第二遍把层数统计覆盖掉了，现在合成一条 hint。
- 进度阶段同步：**删掉 `erase`，新增 `background`**（比例 analyze .05 / refine .10–.25 / extract .25–.92 / background .92）。

### AH.5 实测证据（2026-10-09）

- 端到端（3011 开发服务，`mode=auto`，输入 1200×1500）：
  `stats={elements:3, texts:1, base:1, redraw:false, model:0, local:3}`，
  `reconstruction={mean:0.0, max:0, bad_ratio:0.0, ok:true}`，
  **26.5 秒**（改造前 auto 模式要 35 分钟 —— 因为不再调生图模型）。
- **独立复核**：把 5 层 PNG 下载下来自己 `alpha_composite` 一遍再与原图求差 →
  **平均 0.0000 / 最大 0 / 坏点 0**，与后端自报一致。
  证据图 `output/spike/proof_fidelity_pixel.png`（原图 | 叠加结果 | 差异 ×20 放大 = **全黑**）。
- 验证资产（全绿）：`check_split_backend.py` 11 节 / `check_split_static.py` 14 节 /
  `verify_split_pixel.py`（新增，含 bbox 偏移不变性 + 退化输入）/
  `verify_split_board.js` 68-0 / `verify_split_pea.js` 33-33 / `verify_split_models.js` 21-0 /
  `verify_split_background.py` / `verify_split_bg_fidelity.py` / `validate-i18n.js` 1274 keys。

### AH.6 踩到的坑（都已修）

- 🚨 **`verify_split_pea.js` 的两个 harness 缺口**（写它时代码还没演进到那一步）：
  ① 假 DOM 元素缺 `querySelector` → `splitLayersSelectLayer` 直接抛 harness error；
  ② `splitLayersToggleVisible` 只在 `peaMode` 为真时才推给 Photopea，测试没设 → 断言假失败。
- 🚨 **`buildDocument` 会 `app.documents.add` 出新文档**，测试里缓存下来的 `doc` 还指着上一份 →
  必须重新从 `app.activeDocument` 取。
- 🚨 **抽函数不要用 `\n\n\n(?=def)` 当终止符**：`image_has_alpha` 之后紧跟模块级赋值
  `STORAGE_IMAGE_EXTS = {...}`，会被一路吞到几百行后把 `app = FastAPI()` 也抽进来
  （报错长这样：`NameError: name 'app' is not defined`）。改按「缩进回到第 0 列」判断结束。
- ⚠️ `split_local_cutout` 对**被抠掉**的像素写 `(0,0,0,0)`（RGB 清零）→ 断言「像素保持」时
  **只比 alpha>0 的像素**，别把全透明像素的 RGB 也算成偏差。
- ⚠️ 测试造图时裁切**必须外扩**：贴边的框没有背景可吃，`floodfill` 会把整块（含要保留的元素）吃掉。
- 🚨 **差点误杀老板的服务**：`netstat` 看到残留 PID 15404 → 反查 exe 发现是
  **工作区 `python\python.exe` 且正在 `0.0.0.0:3000` LISTENING**，就是老板的线上服务。
  **杀进程前一定先按 PID 反查 exe 路径**（`tasklist` 不给路径，用 ctypes `QueryFullProcessImageNameW`）。
- ⚠️ 本机 PowerShell `Get-CimInstance` 在这套沙箱里**静默无输出**，查进程还是走 ctypes。


## AI. 2026-10-09 下沉（第五批：全局红线详表 〇–八，为 `MEMORY.md` 回到 8KB 以内）

> 内容 = 原 `MEMORY.md` 第〇～八节的完整条目。`MEMORY.md` 现只留「必背一句 + 指到本节」。
> 引用字母沿用原节（A–AH 为 `REFERENCE.md` 内节号）。

### 〇 启动器红线（T/AB）
- 🚨 后台线程推 WebView2 消息**禁用 `webView.BeginInvoke`** → `PostJsonToWebView`（否则进度恒 0% + 日志空白）。
- 🚨 复用 3000 前先验 `root_fingerprint`；**开发服务别占 3000**，测试用 3010+。

### 一 画布数据安全（最优先，I）
- `data/canvases/<32hex>.json` **无回收站/无历史版本/未纳入 git**；删节点 = 硬删，撤销栈只在内存。
- 写画布前：停服务 + 确认无画布页开着 → 备份 + `md5sum`；测试用一次性画布（`POST /api/canvases` → 收尾 `DELETE .../purge`）。收尾：删 `static/__*.html`、purge、`md5sum -c`。⚠️ 哈希不符先排除「老板开着页」。
- `PUT /api/canvases/{id}` **全量替换** + **必须传 `base_updated_at`**；只改标题走 `POST .../meta`。

### 二 前端（J、U.1）
- 只有一份 `static/smart-canvas.html/js/css`；节点根 `.image-node[data-id]`；`canvas.html` 不带 `?id=` 跳选画布页。
- 🚨 改前端必查四条：① **新增非图片节点类型必须显式重显**（`.node-*` 被全局隐藏）；② **自吃鼠标事件的区域须加进 `beginNodeDrag` 排除选择器**；③ **改 i18n 必跑 `static/js/i18n/validate-i18n.js`**；④ **增删创建菜单卡片必须同步改栅格列数**（3 列 @400px）。
- 🚨 **lucide 两坑**：定尺寸**必须同时写 `i` 和 `svg`**；`lucide.js` 是 UMD，**导出名 PascalCase**（`scissors`→`Scissors`）→ 静态核查要转名，否则全假阴性。
- ⚠️ **`transform` 会给 `position:fixed` 当包含块** → 浮层搬 `document.body`；弹层挂 `#shell` 之外。⚠️ **文本框别用 `outline` 做焦点环** → `label:focus-within{border-color}`。
- ✅ **遮罩局部重绘**（AC）：`bbox → 扩比例 → 裁 crop+crop_mask → 出图 → 羽化贴回 → 落新一张`。🚨 参考图顺序 `[crop, crop_mask, ...]`；🚨 遮罩**不进 `node.images`**；🚨 与基准图同尺寸 + RGBA；🚨 `node.inpaint` 须 index + base_key 双匹配；🚨 排除列表须带 `.node-mask-badge`。

### 三 模型下拉与 Grsai（先读 F + 技能 `gateway-model-probe`）
- 下拉唯一数据源 `chatApiProviders()`，**只认 `chat_models`**；3D 用 `chatModelOptions()`。
- 🚨 **建议须与任务相关**：`isCanvasOpRequest()` 判画布操作 → 不给画风选项。
- 🚨 **画布下拉与启动器清单是两套、必须一致**（启动器读 C# 硬编码 `GrsaiCuratedModels()`）；**别因一次 400 就剔模型**。
- ✅ **启动器每次运行联网更新 Grsai 清单**：Grsai **无 `/models` 接口** → 唯一来源 = 文档页内嵌 chunk；缓存放 LOCALAPPDATA + **只增不减**；🚨 **扫 chunk 必须并行**、**分类表须与前端 `Qe()` 逐字一致**；诊断 `--probe-grsai-models`。
- 🚨 **上游 `404 page not found` = chat 路径拼错** → `base_url` 必须裸域名。⚠️ **「测试连接」对 Grsai 恒失败**。⚠️ **安装目录与工作区的平台配置是两份**。

### 四 3D 预览节点（`smart-3d`，先读 K）
- 🚨 上下游**只接「上传」**（`smart-image`；`canAutoConnectDraggedNode()` + `connectInputNode()` **两处都要改**）；**折叠阈值按实测文案宽度** / **失败态加 `.is-error`** / **取色随挂载面**。
- 🔄 **迭代流程已回退（2026-10-08 16:05）**：现为**原版一次成型**，回退前那套完整实现**备份在 `output/backup-3d-rework-20261008-1605/`**。
- 🚨 **`coder` 通道不稳**：实测 22 次里 524×6 + 502×2 全在 `coder`，同期 `grsai` 零失败。
- 🚨 **徽章语义**：未评 = 灰底 `circle`；进行中 = 蓝底 `loader-2`；已评 = 直接显示分数。**`triangle-alert` 只允许出现在真错误态**。

### 五 本地服务与启动器
- 启动 `./python/python.exe main.py --port 3010`（**后台 Bash**，日志 `output/server-3010.log`；**无 `curl`** → `urllib`）。🚨 **静态资源在 `/static/` 前缀**。🚨 **改 `main.py` 必须重启服务**（**别擅自杀**）。
- 🚨 **杀进程前先按 PID 反查 exe 路径**（`tasklist` 看不到路径；用 ctypes `QueryFullProcessImageNameW`）：实测老板的 3000 服务 exe = **工作区** `python\python.exe`，差点误杀 PID 15404。
- ✅ **只改前端不必重启**：`.html/.js/.css` 都是 `no-cache, must-revalidate` → 刷新即回源校验。⚠️ 但 `?v=` 只在启动时同步 → 跑 `output/spike/resync_static_v.py` 离线补（`i18n.js` 的 `?v=` 取自自身 mtime，**改词条不变 URL**）。🚨 **打包前必须重启服务**，打包后别再重启。
- **启动器 UI**：**exe 不内嵌网页资源** → 只改前端无需重编；🚨 **重编 UI 后跑 `sync_verify.py sync`**；**只改 C# 用最小 publish**。T.2。
- 🚨 **绝不在老板的安装目录（`Infinite-Canvas-Full-*`）里跑服务**（会锁 `python\Lib\site-packages\*.pyd`）；一律**工作区**、**3010+**；用完立即杀。⚠️ delta `from_version` 不匹配就走完整包，是设计不是 bug。
- 🚨 **「更新后功能没变」两类根因**：① 增量基线被污染；② 更新时文件被占用 → 解压中途崩（孤儿 `python.exe` 占 `PIL/_avif.pyd`，或残留启动器占自己的 exe）。**先看 `%LOCALAPPDATA%\InfiniteCanvasLauncher\update.log`**（`已写入 N 个文件` + `[异常] IOException`）与 `data/update_backups/` 时间线。⚠️ **`release-manifest.json` 的 `files` 是全量清单（3139），不是变更数**。
- ✅ **枚举「某目录内的进程」用 ctypes**（本机 PowerShell `Get-CimInstance`/`Get-Process` **静默无输出**）。🚨 **窗口圆角**只能**逐像素透明**（与 `WS_EX_LAYERED` 互斥）+ `#root{border-radius}`；**绝不可加 `CS_DROPSHADOW`**；内缩 = `2/devicePixelRatio`；⚠️ **无头截不到启动器窗口**。

### 六 磁盘与 git 硬红线
- ⚠️ 本机「删除即入回收站」→ **真正释放 = 清空回收站**。🚨 **`rm -rf` 被钩子拦**（阈值 50 文件）→ 走技能 `safe-recycle-cleanup`（幂等，被打断**重跑即可**）。
- ⚠️ 删已跟踪文件用 **`git add -u`**；**绝不裸 `git rm`**（父目录会连磁盘文件一起消失）→ Python `os.remove` + `git add -A <目录>/`。✅ 只「取消跟踪留文件」→ **`git rm --cached`**（先快照）。
- 🚨 **`git status` 干净 ≠ 意图达成** → 必须**反查 `git ls-files`**；**`.gitignore` 对已跟踪文件无效**。⚠️ 维护前先 `git bundle create ../repo-<日期>.bundle --all`。
- 🚨 **工具会话内 `git push` 挂起** → **推送/发 Release 必须老板本人做**（会话内无 `gh`）。

### 七 发布 / 版本 / 验证 / 安全（N/O/D/U.2/S.4）
- ✅ **打包 = `tools/release.py`**（`build` 后**自动跑 `scan_release.py`，不过即中止**）。技能 `infinite-canvas-release`。🚨 发布说明**两处须同步改**：`static/update-notes.json` + `--notes-file` md。
- 🚨 **发布包必须从工作区构建**；**改 `launcher/*.cs` 必须重编 exe**。🚨 **发版前核对「包内 exe sha256 == 当前 exe」**。
- 🚨 **四条排除铁律**：`assets/` 整目录；`data/` 只留 `inspire_prompt_zh.json`；`dist/InfiniteCanvasLauncher.*`/`Microsoft.Web.WebView2.*`；`static/__*.html`。
- 🚨 **更新源 = `HanaJhon/Infinite-Canvas`**；`update.json` **必须作 Release 资产上传**；**发布老板本人做**。⚠️ `releases/latest` 不切新版 → 恒显「已是最新」。
- 🚨 **启动器判更新只比版本号、不比文件哈希** → **同版本号覆盖发布 = 已装该版本的人永远收不到更新提示**；必须升版本号。
- 🚨 **增量基线 = `output/release/<上一版>/file-hashes.json`** → **为已发布过的版本号重新 build 会污染基线**（1.1.8 事故）。**要重打先把它移出 `output/release/`**；每次发版必须核对「关键文件真的在 delta 里」。
- 🚨 **不要手改 `VERSION`** → `tools/bump_version.py`；**权威 = `tools/versioning.py` + `launcher/VersionUtil.cs`** → **改规则两边同改**；⚠️ **跨日期制↔三段式绝不能比数值**。
- 🚨 **回退 = 恢复点 `data/update_backups/<ts>/`**：**`static_snapshot.complete==true` 才准整目录替换**、**回退白名单比更新宽**、**`TrimBackups` 按 `created_at` 排序**。
- 🚨 **密钥泄露清不掉，只能轮换**；钩子禁非 ASCII。🚨 **无头验证走技能 `infinite-canvas-verify`**；**证明「常量从 exe 消失」** → 解 bundle 取内嵌 dll 再搜 + 兄弟常量对照。⚠️ 单文件 bundle 压缩，明文 grep 假阴性。
- 🚨 **Codex 权限** 4 档（`data/codex_permissions.json`）；`#codexCliPanel` **只在 `protocol=codex` 时显示**；⚠️ **不改全局 `~/.codex/config.toml`**（含**明文 token**）。

### 八 Agent 两套 + Skill 市场（Q/R/W/X）
- 🚨 **分类**（W/X）：命中按**整词**（中文裸子串 / `词*` 前缀 / 英文词边界）；**技术栈不当分类**、**裸品牌词必限语境**；大分类 = **累加子分类权重**（最高单标签会**单票否决**），`design`/`image-video` = 软标签；**标签现算**。
- 🚨 **市场两坑**（X.1/X.2）：star/fork/热度是**仓库级** → 同仓并列占满首屏 → `spreadByRepo()` 同仓错峰；列 flex 里的横向滚动容器 `min-height:auto`=0 被压扁 → `flex-wrap:wrap`。
- 🚨 **两套 agent**：`gpt-chat.html` → `/api/chat/agent`；`smart-canvas.html` `#agentPanel` → `/api/agent-llm-task`。**改 agent 能力两套都改**。
- ✅ 本机工具 `run_shell`/`read_file`/`write_file`/`list_dir`；开关 `GET|POST /api/agent/tools`（默认关/8 轮/上限 20）。🚨 **上游不支持 tools 要优雅回退**；**工具循环与流式不能混用**。
- ✅ **Skill 市场 = SkillsMP**（`skills-catalog.json` + 缓存 `skills_market_cache.json`，**缓存优先**）。🚨 **`refreshed_at` ×1000**；**刷新失败删污染缓存**；**搜索走服务端全站，按相关性排**。

---

## AJ. 2026-10-09 下沉（第六批：拆分图层详表 —— 流程改造 + 还原度代价）

> 来源：`MEMORY.md` 第九节原文 + 同日第五轮（`2026-10-09.md` §8）。`MEMORY.md` 第九节只留「必背 + 指针」。

### AJ.1 入口与交互（AG 详述）

- 入口：上传节点顶部菜单 `splitLayers`；弹层 `#splitLayersModal`；后端 `POST|GET /api/split-layers-tasks`。
- 右侧默认**自研轻量画板**（`.sl-board` 按 z 叠放 + 棋盘格），Photopea 降级为按需「精细编辑」。
- 失败给 `error_detail{phase,phase_label,message,advice,tried}` + 失败卡片 +「换模型重试」。
  🚨 笼统「拆分失败」基本就是**前端超时**（`SPLIT_LAYERS_TIMEOUT_MS = 20min`）。
- 模型选择 = 与 AI Agent 面板同构的「通道 + 模型」两级联动，**分析 / 生图两个角色分开选**（4 个下拉）。

### AJ.2 像素优先（AH 详述）

- 模型只回答「哪里有什么、框在哪」，**每层像素一律从原图裁**（`split_pixel_layer`）+ 本地 alpha
  （`split_local_cutout` **只改 alpha 不动 RGB**；`floodfill` 从四边吃连通背景，**裁切必须外扩**）。
- **每层像素取自原图同一坐标 ⇒ 叠加恒等于原图，与 bbox 准不准无关**（实测偏 17px 还原度仍 0）。
- 🚨 `split_pixel_layer` 返回**四元组** `(full, method, detail, cut_ok)`；`cut_ok = split_alpha_ok(cut)` 必须
  在**抠图现场**给出。**别另写「统计 bbox 内 alpha 占比」的判据** —— 实心矩形元素 bbox 内天然全不透明，
  会被误判成「抠图失败」→ 白花一次模型钱还引入漂移（真踩过）。
- `split_alpha_ok(img, min_ratio=0.02, max_ratio=0.98)`：只看整幅，判「真的带有效透明通道」。

### AJ.3 文字层 / 背景层（AG/AH 详述）

- 🚨 **文字层默认「像素态」**（`textMode:'pixel'`）→ 前端 **url 优先**：`splitLayersIsPixelText` 判定
  排在 `kind==='text'` **之前**，**画板 / canvas 合成 / 注入 Photopea 三路径都要**；只有切「编辑态」才 `fillText`。
  **旧代码用系统字体重画 = 漂移唯一来源。**
- 🚨 像素文字层 url 是**全画布尺寸** PNG，而盒子是 OCR bbox → **必须显式按画布尺寸 + 负偏移定位**。
- 🚨 **背景层 = 原图挖洞 + 本地补**（`split_background_plate`），**不再调生图模型**；
  洞 = 各层 alpha 并集（**必须二值化** `v>0 → 255`）、**不羽化**；背景**强制不透明**（`base.putalpha(255)`）。
- 🚨 `splitLayersApplyLiveTransform` 必须**同时写 `transform` 与 `opacity`**；`.sl-text-bar[hidden]` 必须显式 `display:none`。
- 旧 `split_erase_*` 已不在流程里；`payload.erase_text` 保留字段但**已不参与流程**（前端传 false）。

### AJ.4 参数与注入红线

- ✅ `target_layers` 2–12；**文字不占层数**（N = 背景 1 + 前景 N-1）；背景层必须**后端兜底**；**绝不写死通道 id**。
- 🚨 Photopea 必须 **data URI** + **按 z 升序**注入；喂图缩到 1024 **只缩不放**（bbox/font_size 要还原）；
  模型 bbox 偏 ~41px；**本机无头 Edge 已废** → Node 抽函数断言；被拒类错误才换通道，**524/502 故意不换**。

### AJ.5 第五轮：流程改造（内置提示词 / GPT 门禁 / LLM 主导 / Photopea `#STRING`）

- 后端三个**内置提示词常量**：`SPLIT_LAYERS_SPLIT_RULES`（拆图六条，中文，**并进** `SPLIT_LAYERS_USER_PROMPT`）、
  `SPLIT_LAYERS_CUTOUT_RULES`（抠图品质规则，**英文祈使句**，写给图像模型）、`SPLIT_LAYERS_COMPOSE_RULES`（PS 合成四条）。
  ⚠️ 旧的 `SPLIT_LAYERS_EXTRACT_PROMPT` **保留但已标注被 CUTOUT_RULES 取代**。
- **层数 → 提示词重新优化**：`SPLIT_LAYERS_GRANULARITY_BANDS` 三档（2–3 / 4–6 / 7–12）
  + `split_granularity_prompt(target)`（旧的 `SPLIT_LAYERS_GRANULARITY_PROMPT` 常量已删）。
- JSON schema 新增 `need_model`（bool）+ `cutout_prompt`（英文单层描述）；
  `split_element_cutout_prompt(element)` = 内置品质规则 + LLM 单层描述；
  `split_extract_element(..., force_model=False)`；`want_redraw = (mode == 'model')`。
- **GPT 门禁两道闸**：① 入口整条**不显示**（不是灰掉）= `splitLayersGptGateOpen()`；
  ② 弹层分析侧只列 GPT = `splitLayersGptProviders()` / `splitLayersGptModels()`。
  判定链 = **弹层记忆 → Agent 面板 → 配置里第一个 GPT**（最后一步**防死锁**：从没进过弹层、没开过 Agent 面板时
  前两步都取不到，直接判 false 会让入口永远不出现）。只认名字带 `gpt`（含 `chatgpt-*`）；**o1/o3/o4 不算**。
- **Photopea `#<config>`**：`SPLIT_LAYERS_PEA_CONFIG = JSON.stringify({environment:{lang:'zh',intro:false,vmode:0}})`
  → iframe 地址 `https://www.photopea.com/#<encodeURI(config)>`；**config 被判非法时自动退回裸地址重试一次**
  （否则一个配置问题会把编辑器整个拖死）。
- **导出分层 PSD**：`splitLayersExportPsd()` → 先 `splitLayersBuildDocument()`（建文档 + 按 z 升序注入）→
  `pea.runScript('app.activeDocument.saveToOE("psd:true");')` → 🚨 **返回值在 `out[0]`，是 ArrayBuffer 不是 Blob** → 包一层下载。
- ✅ **Photopea 广告关不掉**：官方 `environment` 文档里连 `showbranding` 都是**注释掉的**（未开放），
  嵌入方没有任何去广告开关 → 默认仍用自研画板，Photopea 只在「精细编辑 / 导出 PSD」按需打开。

### AJ.6 🚨 还原度代价与已验证的修法（第五轮实测）

- 真实 e2e（3011，`mode=auto`，4 层，`ep_1791516939807/gpt-6-astra` + `gpt-image-2.5`）：
  **5/5 层可用、382.6s**（< 前端 20 分钟上限）；粒度提示词生效（目标 4 层 → 元素 3 + 文字 1）；
  LLM 判定需模型抠图 → 自动调模型成功 2 层、1 层遇 **502 → 本地去背兜底**（降级路径按设计工作）。
- **但** `reconstruction = {mean:3.915, max:251, bad_ratio:0.1326, ok:false}`（上一轮是 `{mean:0,max:0}`）。
  原因：**LLM 把 3/3 个元素都判成 `need_model=true`**，而当前实现是「**整层替换成模型重绘的像素**」
  → 那两层不再取自原图 → 叠加 ≠ 原图。**同时这也意味着 `mode=auto` 实际退化成「每次全量调模型」**（成本回归）。
- 离线对照实验 `output/spike/exp_split_alpha_only.py`（拿真实产物，不改生产代码）：

  | 方案 | mean | max | bad_ratio | ok |
  |---|---|---|---|---|
  | A 现状（模型自己的 RGB + 自己的 alpha） | 3.915 | 251 | 0.1326 | ❌ |
  | B 只取模型 alpha，RGB 换回原图同坐标 | 0.125 | 162 | 0.00446 | ❌ |
  | C 只取模型 alpha + **与「洞」同口径二值化**（`v>0→255`） | **0.0** | **0** | **0.0** | ✅ |

- **可复用性质**：「每层像素永远取自原图」+「alpha 与背景洞同口径」⇒ **叠加恒等于原图，与模型轮廓准不准无关**。
  B 不为 0 是因为洞是二值的、而模型 alpha 是软边 → 半透明像素被压平（`layer_rgb*a + plate_rgb*(1-a)`，plate 在洞里已被本地补全）。
  代价：模型轮廓若与原物错位，会**切掉/多留原图像素**（但**不会整幅漂移**）。
- ✅ **老板拍板 + 已落地（同日）**：选 **C（只取轮廓）**；`need_model` **保持**让 LLM 自行判断（不收紧）。
  新增 `split_model_outline_layer(src_rgba, model_full)` = `split_layer_hole(model_full.getchannel("A"))`
  + `src_rgba.convert("RGB")` 的 RGB；`extract_one` 里 `full = split_model_outline_layer(src_rgba, m_full)`。
  ⚠️ `mode='model'`（前端目前恒传 `auto`）仍用模型自己的像素 —— 那种模式下叠加**不**等于原图，刻意如此。
- ✅ **决定性 e2e 复跑**：`reconstruction = {"mean":0.0,"max":0,"bad_ratio":0.0,"ok":true}`（改前 `mean 3.915 / ok false`）；
  177.8s、5/5 层、`model:1 / local:2`（2 层模型失败 → 本地兜底）；层名变成「主体：充电盒 / 主要陪衬：左右无线耳机 /
  装饰：充电盒细节」，证明 4–6 档粒度策略生效。
- ✅ 验证资产：`check_split_backend.py` **97 项**（第 10 节新增 5 条轮廓断言）、`verify_split_pixel.py` **9 节**
  （第 9 节含「整层替换会坏掉」反向对照 + 「轮廓整体错位 12px 还原度仍为 0」）。

### AJ.7 环境坑（第五轮踩到，下次直接用）

- 🚨 **沙箱设了 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:1588`** → 服务/脚本里所有对外 API 请求都会
  `upstream connect failed: 由于目标计算机积极拒绝 (os error 10061)`。
  **起服务与跑 e2e 都要 `env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy`**
  （本机走 TUN，直连正常：`grsai.dakka.com.cn` 等解析到 198.18.x.x）。
- 🚨 开发服务必须用 **`run_in_background`** 起；`(cmd &)` 会在**工具调用结束时被回收**
  （日志里「Uvicorn running」了，但下一个工具调用就没了）。
- ⚠️ `netstat` 输出是 **GBK**，Python 读要 `.decode('gbk','replace')`，否则 `UnicodeDecodeError` 直接吞掉结果。
- ⚠️ `rtk ls / grep / wc` 会被拦（`os error 231`）→ 用 Python `glob` / `io.open` / `re`。
- ⚠️ `coder` 通道当时连不上（上游拒绝）；`ep_1791516939807` 可用。

## AK. 2026-10-09 下沉（第七批：文字层两态翻转 + 字体白名单 + 倾角实测）

> 触发：老板「文字图层不是可以直接编辑的状态，转为编辑状态后字体的样式和旋转角度以及倾斜的斜体角度都没有保持不变，分层的图片抠图不够完整」。
> 涉及：`main.py`（5 处）、`static/js/smart-canvas.js`（8 处）、`static/js/i18n/smart-canvas.js`（1 处）、`static/smart-canvas.html`（注释）。**未升版本号（仍 1.1.8）、未提交。**

### AK.1 文字层默认「编辑态」（2026-10-09 口径翻转）

- 旧口径：文字层默认**像素态**（为了「叠加恒等于原图」）。
- 新口径（老板要求「可以直接编辑」）：**默认编辑态**，像素态降级成「还原像素」按钮。
- 后端：文字层 entry **不再写** `textMode` 字段（删掉原来的 `"textMode": "pixel"`）。
- 前端判定唯一入口 `splitLayersIsPixelText(layer)` → `layer.kind === 'text' && layer.textMode === 'pixel' && !!layer.url`。
  - ⚠️ 只认 `'pixel'` 一个值：`undefined` / `'edit'` / 老数据缺字段 一律走编辑态。
  - `splitLayersSetTextMode(mode)` 写 `mode === 'pixel' ? 'pixel' : 'edit'`（同口径；别写成 `mode === 'edit' ? 'edit' : 'pixel'`）。
- 取舍：编辑态用估出来的字体重画 → 能改字，但字体/字距/描边与原图仍可能有细微差异。**这是取舍不是 bug**，别去「修」它。

### AK.2 🚨 像素态盒子必须 = 整幅画布（`splitLayersBoxFor`）

- 像素态文字层本身就是一张**全画布尺寸**的 PNG（后端按整图裁）。
- 旧实现：盒子 = OCR bbox，再用内联 `left:-box.x; top:-box.y; width:cw; height:ch` 把全画布图挪回原点 → **一旋转就把整幅画布绕着文字转**（支点落在 bbox 中心）。
- 现实现：`splitLayersBoxFor(layer)` 统一出盒子 —— 编辑态文字层 → `bbox`；图片层 / 像素态文字层 → `{x:0,y:0,w:canvas.width,h:canvas.height}`；内联负偏移 hack 已删。
- 🚨 **切态必须重算 box**：`splitLayersSetTextMode` 里 `layer.box = splitLayersBoxFor(layer)`，否则 span 被撑满整幅画布 / 全画布 PNG 被压进 bbox。
- 🚨 **定位框（spot）用 `layer.bbox` 而不是 `layer.box`**：像素态下 `box` 是整幅画布，拿它画框 = 「整幅都是这一层」，定位作用直接没了。

### AK.3 字体 / 斜体 / 字距（后端估 → 前端消费）

- 提示词 JSON schema 新增三个字段（仅 `kind=text`）：`italic`(bool) / `font_family`(串) / `letter_spacing`(px)。
- 🚨 **`font_family` 必须白名单**：它会原样进前端 `style="font-family:..."`，不白名单 = 敞开 CSS 注入口子。`SPLIT_LAYERS_FONT_STACKS`（17 串）+ `SPLIT_LAYERS_FONT_LOOKUP`（整串 + 首个族名小写）+ `split_norm_font_family()`，认不出回落 `Arial, sans-serif`。
- 前端消费三处：① span 的 `font-family` / `font-style`（`italic ? 'italic' : 'normal'`）/ `letter-spacing`；② canvas 的 `ctx.font = ${italic} ${weight} ${size}px ${stack}` + `ctx.letterSpacing`（⚠️ 只有 Chromium 99+ 支持，包 `try`）；③ Photopea（见 AK.7）。
- `splitLayersLetterSpacing(layer, size)` 把字距夹在 `[-size*0.3, size*2]`（与后端同口径），防老数据/手改数据把排版撑爆。
- 🚨 旋转**不在 span 里做** —— 由外层 `.sl-layer` 的 `transform` 承担。
- 🚨 `.text` 类只给「真的在渲染 `<span>` 文字」的层（编辑态）；像素态渲染的是整幅画布 `<img>`，走普通图片层那条路（套上 flex/overflow 会让 img 的 100% 高宽解析不稳）。

### AK.4 🚨 `split_measure_rotation`：从像素量真实倾斜角

签名：`split_measure_rotation(rgba, max_angle=45.0)` → 度（**顺时针为正，与 CSS `rotate()` 同号**），量不出返回 `None`。
做法：粗到细三段扫角，取「旋转后外接矩形面积最小」的那个角（最小面积矩形）。段 = `(45, 3.0) / (3.0, 0.5) / (0.6, 0.1)`。

**三个坑（拿老板真实产物踩出来的，别再犯）：**

1. 🚨 **内层循环基准角必须冻结**：`base = best` 写在每轮外层循环开头，内层用 `angle = base + i * step`。直接写 `best + i * step` → 网格跟着 `best` 漂移，实测 25° 一路漂到边界 -45°、`+12 → -12`（**符号反了**）。
2. 🚨 **旋转不变形的形状不量**：判据 = 扫描区间 `max(area_at(±45, ±22.5, 0))` 与 `best_area` 的比值 **≤ 1.15 就返回 None**。实测：圆/环 ≈ 1.04，实心方块 1.34，横条 3.68，真文字 ≥ 1.6。
   - ⚠️ **不能用「±10° 邻域」**：稀疏字形邻域比值只有 1.077 → 误杀真文字。
   - ⚠️ **不能用 bbox 长宽比**：横条倾到 44° 时 bbox 也是方的 → 会否掉真角度。
3. 🚨 **不能用「bbox 填充率高 = 实心块」**：老板 6 个文字层里 3 个带徽章底（填充率 0.85+），而那块圆角矩形的**朝向就是文字的朝向** —— 量它反而正合适。（曾实现成闸①，实测后删除，只在 docstring 留警告。）
- 两条早退：`alpha.getbbox()` 为空 → None；`min(w,h) < 6` 或 `w*h < 64` → None。

### AK.5 🚨 倾角接线：只补「模型给 0」的洞

```python
if full is not None and cut_ok:
    try: model_rot = float(item.get("rotation") or 0)
    except (TypeError, ValueError): model_rot = 0.0
    measured = split_measure_rotation(full)
    if measured is not None and abs(model_rot) < 1.0 and abs(measured) >= 1.0:
        item["rotation"] = measured
```

- **只补「模型给 0」**，**不覆盖模型已给出的非零角度**。理由：像素实测在**碎片化 alpha** 上会退化 —— 实测「整图转 12°」后那个徽章字母的 alpha 混进了徽章边缘，最小面积矩形被斜边带偏，量出 0；模型一旦给出角度通常是真读到了。
- 只在**本地真抠出了透明区（`cut_ok`）**时才量：抠失败时 alpha 是一整块矩形，量出来恒为 0，是假信号。
- `try/except` 兜底：这一步已跑完所有模型调用，为一行取值把整个任务炸掉不值得。

### AK.6 ⚠️【已被 AL 推翻，仅存历史】元素层抠图曾用「模型轮廓 + 本地并集」

- 症状（老板 2026-10-09 截图）：元素层「卷发女子与手持茶具」被切掉头顶 / 身体。
- 根因：模型会把主体**整体挪几像素** → 它的 alpha 相对原图是**错位的**；单用模型 alpha 当轮廓，一边切掉头顶/手臂，另一边多出背景。
- 实测（老板 16:59 产物）：本地抠图不透明占比 **60.4%**，模型轮廓 **30.7%**，并集 **62.3%**。
- 当时的修复：`split_model_outline_layer(src_rgba, model_full, base_full=None)` —— `base_full` 存在时用 `ImageChops.lighter` 取并集。
- 🚨 **2026-10-10 实测证伪：取并集是有害的。** 那次能过是因为本地抠图恰好在**纯色背景**上抠得准；换成**纹理背景**（花园/天空）时 `split_local_cutout(thresh=42)` 几乎无效，并集把没抠掉的背景全带进来（模型掩码 15.00% → 并集 **20.53%**，多出的 5.65% 全是背景），元素层从「一个人」撑成「**整张卡片**」。**主流程已不再传 `base_full`**，详见 **AL.3**。
- `split_local_cutout` 本身的语义没变：从四边 flood-fill 吃掉连通近背景色区（标记色 `(255,0,255)`），**只改 alpha 不动 RGB**，像素对齐。它现在只在「本地兜底」那条路上用（且**退回 bbox+6% 小块**，见 AL.3）。

### AK.7 Photopea 文字注入（font / fauxItalic / tracking）

- `SPLIT_LAYERS_PS_FONTS`：CSS 字体栈 → Photopea 认的字体名（17 条全覆盖，与 `SPLIT_LAYERS_FONT_STACKS` 一一对应）。
- `splitLayersPsFont(layer)`：查表；认不出回落 `raw.split(',')[0].trim()`。
- 🚨 **每条注入都包 `try {}`**：Photopea 认不出字体名会抛异常，不包会把整段脚本炸掉。
- 🚨 **tracking 单位是 1/1000 em** → `Math.round(letter_spacing / fontSize * 1000)`。
- 注入三项：`__t.font = "<psFont>"` / `__t.fauxItalic = true`（仅 `layer.italic`）/ `__t.tracking = <n>`。

### AK.8 本轮验证资产

| 脚本 | 结果 |
|---|---|
| `output/spike/check_split_backend.py` | **119 项 ok**（第 9 节逐字段核字体；新增 9b 节 7 条倾角；第 10 节新增并集 2 条；`"textMode": "pixel"` 断言**反转**） |
| `output/spike/check_split_static.py` | **120 项 ok**（第 12 节重写「文字层两态」；新增 12b 8 条编辑态样式；12c 6 条 Photopea 注入） |
| `output/spike/verify_split_pixel.py` | **71 项 ok**（新增 9b 5 条并集 + 第 10 节 15 条倾角：6 个角度误差 ≤1°、圆/环/全透明/过小→None、倾斜 17° 徽章底→+17°） |
| `output/spike/verify_split_board.js` | **85-0 全绿**（新增 12b 切回编辑态盒子回 bbox、12c 字体/斜体/字距 + 老数据回落 + 越界夹取） |
| `output/spike/verify_split_pea.js` | **54-54 全绿**（新增 `tl.textItem.font === 'Georgia'` / `fauxItalic === true` / `tracking === 100`） |
| `output/spike/test_split_api.py` | 文字层打印补 `font`/`italic`/`letter_spacing`/`textMode`/`url`；DONE 后打印叠加还原度 |
| `output/spike/make_preview_split_board.py` | 重跑 → `preview_split_board.html`（4 屏，326 KB） |
| `static/js/i18n/validate-i18n.js` | 1278 keys ok |

**真实 e2e（3010，`mode=auto`，5 层，117.5s）**：`reconstruction = {mean:0.0, max:0, bad_ratio:0.0, ok:true}`；`stats={elements:4, texts:1, base:1, redraw:false, model:3, local:1}`，6/6 层可用；3 层 detail 全含「已自动调用图像模型取轮廓（像素仍取自原图，并与本地抠图取并集）」；文字层新字段齐、`textMode` 缺省 = 编辑态。

**倾角在老板真实产物上验证**：6 个文字层 → `0.0 / 0.0 / -2.0 / 0.0 / 0.0 / 0.0`（与目视一致）；真倾斜样本 `5385825e80` 肉眼约 -8° → **实测 -8.1**。

### AK.9 本轮踩到的脚本坑（写验证脚本时直接避）

- `f"{got:+.1f}"` 在 `got is None` 时 → `TypeError: unsupported format string passed to NoneType.__format__`。
- `pill.putalpha(rot)` → `ValueError: images do not match`（`rot` 是 expand 后更大的图）→ 改 `alpha_composite(Image.merge("RGBA", (rot,rot,rot,rot)), (offset))`。
- JS 新增变量撞名 → `SyntaxError: Identifier 'spot' has already been declared`（改名 `spotPx` / `fFontCall`）。
- 🚨 **别用 heredoc 追加 memory**（bash 会展开反引号）→ `splitLayersIsPixelText: command not found`；用编辑工具直接写。


## AL. 2026-10-10 下沉（第八批：整图生图路线 + 去并集 + 软边阈值 128 + 合理性闸）

> 触发：老板「能否更换抠图方式，目前该抠图方式仍旧存在残缺不完整」→ 追问「执行抠图进行分层的工作是LLM做的决策吗？原提示词中并没有提到使用抠图来获得所有的元素，可能是通过原图生图呢」→ 拍板「元素层的像素用**模型生成的像素**（你截图的原方法）」。
> 涉及：`main.py`（8 处）、`static/js/smart-canvas.js`（3 处）、`static/js/i18n/smart-canvas.js`（1 处）。**未升版本号（仍 1.1.8）、未提交。**

### AL.1 老板的两个质疑，核实结果

1. **「分层」是 LLM 决策吗？** 是。`split_analyze()` 用对话模型（多模态）出 `layers[]`，每层 `kind/name/bbox/z/need_model`。
2. **「抠图 vs 生图」是 LLM 决策吗？** **不是**。LLM 只答「哪里有什么、框在哪」；**像素从哪来**由后端按 `payload.mode` 选，而前端此前**恒传 `'auto'`**（像素优先）。
3. **老板说得对**：原始提示词里**没有「抠图」概念** —— 是助手在提示词里加了 `note: 用于把这个元素单独抠成透明PNG` + `need_model: 必须交给图像模型抠图`，把它实现成了「裁块 → 抠轮廓」。老板截图里的原方法 = **整图 → 每个元素单独生成一张全画幅透明 PNG**。

### AL.2 🚨 根因①：抠图被硬裁在「LLM bbox + 6% 外扩」那个矩形里

- 旧实现把 `crop = base.crop((x0,y0,x1,y1))` 喂给图像模型，**裁剪矩形之外的像素任何算法都拿不到**。
- LLM 的 bbox 一旦比主体小（老板那次只盖到腰），裙摆 / 左臂 / 茶壶就被矩形边**硬切平**（直线边）。
- 铁证：模型返回的掩码与产物 bbox **都恰好等于**裁剪矩形 `(256,347,818,1069)`，内容触满上下边。
- 修复：`split_extract_element(..., whole_image=True)` —— `x0=y0=0`、`crop = base_rgba`、`inner=(width,height)`，把**整幅原图**交给模型。
- 提示词配套：`split_element_cutout_prompt(element, whole_image=True)` 额外声明
  「The reference image is the WHOLE picture and it also contains other objects, scenery and text that are NOT part of this task.」（不提醒的话模型会把整块区域都留下）。
- `SPLIT_LAYERS_CUTOUT_RULES` 同时补了「贴紧轮廓、不留矩形/卡片状底、排除其它物体与文字」。

### AL.3 🚨 根因②：与本地抠图取并集**有害**（推翻 AK.6）

- 实测（老板 09:14 产物）：模型掩码本身是**干净人形剪影 15.00%**；与本地 flood-fill 并集后变 **20.53%**，多出的 **5.65% 全是没抠掉的花园背景** → 元素层从「一个人」变成「**整张卡片**」。
- 原因：`split_local_cutout(thresh=42)` 在**纹理背景**上几乎无效（它假设背景连通且近纯色）。
- 修复：主流程改 `split_model_outline_layer(src_rgba, m_full)`，**不传 `base_full`**。`base_full` 参数**保留**（兼容/回放），只是不再用。
- 本地兜底**退回「bbox + 6%」小块**：整图 flood-fill 是从画布四边往外吃背景的，在截图这类图上会把整张 UI 都留下当元素层，比裁块更离谱。

### AL.4 🚨 根因③：软边掩码用 `v>0` 二值化 → 边界发毛

- 图像模型返回的 alpha 是**抗锯齿软边**：老板产物里 `alpha=0` 占 56.32%、`1..254` 占 **43.61%**、`=255` 仅 **0.07%**（实心内部值 ≈250）。
- `v>0` 会把整圈过渡带 + 零散噪点全算成实心。
- 修复：`split_layer_hole(alpha, thresh=128)` → `255 if v >= 128 else 0`（软边掩码的标准二值化）。两层（元素层 / 背景挖洞）用**同一个函数**，所以「叠加恒等于原图」这条性质不受影响。

### AL.5 🚨 新增合理性闸 `split_mask_covers_bbox(mask, bbox, min_ratio=0.15)`

- 整图模式下模型看的是整幅画面，万一**答成了别的物体**（或返回全透明图），这一层就是错的。
- 而这种错 **`split_alpha_ok` 拦不住** —— 它只看「有没有透明通道」，全透明 100% 也能过。
- 判据：模型掩码在 LLM 指的那块 bbox 内的不透明像素占比 ≥ `min_ratio`（0.15，不是 1.0：允许模型掩码比 bbox 紧一点/松一点）。
- 不通过 → 放弃模型结果、**回落本地像素**，`detail` 写「模型整图结果没盖住该元素（疑似答成了别的物体）」。

### AL.6 `mode` 语义（前端现在恒传 `'model'`）

| mode | 行为 | 像素来源 | 叠加还原度 |
|---|---|---|---|
| `'model'`（**当前默认**） | 整图交模型 → 每元素单独**生成**一张全画幅透明 PNG | **模型生成** | **≠0，属预期** |
| `'auto'`（旧，保留以便回退） | 模型只出轮廓，像素从原图裁 | 原图 | 恒为 0 |
| `'local'` | 完全不调模型 | 原图 | 恒为 0 |

- 实测 `mode=model`：`reconstruction = {mean: 3.915, max: …, bad_ratio: 0.1326}` —— **刻意取舍**（要「元素完整干净」而不是「叠加等于原图」）。
- 🚨 **前端按 `result.stats.redraw` 分措辞**：`splitLayersFidelityText(rec, redraw)`，生图模式显示 `smart.splitLayersFidelityExpected` =「生图模式，属预期」。**别把预期内的偏差渲染成报错。**

### AL.7 提示词 schema 字段回到「生成」语义

- `note`：`<给图像模型的一句话描述：这个元素是什么（用来让它单独生成这张透明 PNG）>`。
- `cutout_prompt` / `need_model` 的措辞同 AL.1 第 3 点（不再叫「抠成透明PNG」）。

### AL.8 本轮验证资产

| 脚本 | 结果 |
|---|---|
| `output/spike/check_split_backend.py` | ALL CHECKS PASSED（并集断言**反转** + 新增 10 条整图路线断言） |
| `output/spike/check_split_static.py` | ALL CHECKS PASSED（新增「生图模式下不说逐像素一致」+「前端请求 mode 是 'model'」） |
| `output/spike/verify_split_pixel.py` | ALL CHECKS PASSED（新增第 11 节 8 条闸判据） |
| `output/spike/verify_split_whole_image.py` | **新建**，ALL CHECKS PASSED（真跑 `split_extract_element`、只桩掉网络；5 节） |
| `output/spike/verify_split_board.js` | 85-0 |
| `output/spike/verify_split_pea.js` | 54-54 |
| `output/spike/verify_split_models.js` | 35-0 |
| `static/js/i18n/validate-i18n.js` | 1279 keys |

### AL.9 本轮踩到的环境坑

- 🚨 **Git Bash 会把 `/assets/...` 参数转成 Windows 路径**（`E:/WorkBuddy/.../PortableGit/assets/...`）→ 服务报「找不到要拆分的图片」。跑 e2e 必须 `MSYS_NO_PATHCONV=1`。
- 🚨 **分析阶段只对「被拒」类错误换通道**（`SPLIT_REJECT_HINTS`：credits/quota/unauthorized/not found/permission…），**5xx/超时不换**（防重复扣费）。实测 Aizzz `gpt-5.5` 返回 503 `Service temporarily unavailable` → 直接整条失败，**不会**自动换到别的通道。
- 源图找回路径：老板那张 1248×1248 的源图在画布 `data/canvases/2c794fa46a1f4224a1cfe288b2777a97.json` 的「上传」节点里 → `/assets/input/ai_ref_986fa7a0681e.png`（`截屏_2026-09-17_13-50-51.png`）。

### AL.10 真实 e2e 结果（3010，`mode=model`，`target_layers=3`，186.3s，9/9 层可用）

**✅ 修复生效的硬证据**：喂给图像模型的 `split_in_*.png` = **1248×1248**（整幅原图，768293 bytes，两个元素同一张）；**修复前是 722×722**（= crop 长边，裁块）。

```
canvas 1248×1248   erased_text=False
stats = {elements:2, texts:6, base:1, redraw:True, model:1, local:1}
叠加还原度 = {mean:31.785, max:236, bad_ratio:0.29453, ok:False}   ← 生图模式，属预期
  背景  method=base   bbox=[0,0,1248,1248]      alpha 透明 0.000
  元素① method=model  bbox=[246,241,669,786]    alpha 透明 0.452
  元素② method=local  bbox=[0,80,1248,762]      alpha 透明 0.761（detail 含「已用本地去背兜底」）
  6 个文字层 textMode=None（= 编辑态 ✓）
```

- ✅ `stats.redraw = True` → 前端走「生图模式，属预期」措辞；**1/2 元素真的用了模型生成的像素**。
- ⚠️ `mean 31.785` 偏高，主因是元素② 回落本地（bbox 就是整幅宽 `0..1248`，本地 flood-fill 在**截图**上会留下大片 UI，预计中的行为）。**生图模式下还原度不再是质量信号**。
- 🚨 **通道现状（2026-10-10）**：`ep_1791516939807`（Grsai）`gpt-image-2.5` = `apikey credits not enough`；`ep_1791536133987`（Aizzz）`image_models: []`；**唯一能用的是 `grsai` 通道的 `gpt-image-2`**（靠 `split_candidate_channels` 的回落自动救回）。

### AL.11 🚨 模型不可信于几何 → `split_anchor_to_bbox`（2026-10-10 第二轮）

> 触发：老板在 UI 跑完新版本后反馈「**元素位置没有贴合，文字层没有对齐，背景层的图片是否是通过LLM模型的决策生成的**」。

**取证对象**：老板 09:53 那次运行的真实产物（本次模型真的出图了 —— `online_447b09b888.png` 1024×1024）。

**根因（实测数据）**：

| 量 | 值 |
|---|---|
| 原图卡片（降采样 4× + BFS 最大亮块） | `(264,244,912,1032)` = 648×788 |
| LLM 给的 bbox | `(246,241,915,1027)` = 669×786 ← **LLM 是准的**（差 ≤18px） |
| 模型产物 alpha 外接框 | `(178,60,1072,1182)` = 894×1122 ← **放大 1.34~1.43 倍 + 左上偏 (86,184)** |

图像模型（这次实际用的是回落通道 `grsai/gpt-image-2`）**重新构图**了 —— 提示词里写了「do NOT enlarge, shrink, re-frame or re-compose」也没用。

**修法**：新增 `split_anchor_to_bbox(full, bbox, min_scale=0.25, max_scale=4.0)`：
裁出模型元素的 alpha 外接框 → **等比缩放**到能放进 bbox → 在 bbox 里居中。
- **口径**：模型只负责「元素长什么样」，**位置与尺寸一律由 LLM 的 bbox 决定**。
- 等比（不是拉伸铺满）是为了不把元素拉变形；代价是比例不一致时留一点边距。
- `min_scale/max_scale` 是保险：bbox 与模型产物差一个数量级时**原样返回**（更可能是 LLM 的 bbox 离谱）。
- 接线：`split_extract_element` 尾部，**只在 `method == "model"` 时**锚定（本地像素本来就在正确位置）。
- 实测效果：锚定前 894×1122 / 中心偏 (44,13) → 锚定后 626×786 / 中心偏 **(0,0)**。

**🚨「文字层没有对齐」是同一个根因的下游症状，不是文字坐标错**：
实测 6 个文字层的 alpha bbox，**5/6 精确框住原图对应文字**（把 bbox 画回原图目视核对全中）。
真因是元素层被放大+左上偏 → **盖不住背景层挖的洞** → 洞里被 `split_local_fill` 低频补全糊过的**原文字透出来**，与单独的文字层**重影**。
`split_local_fill` 是「降采样再放大」的模糊填充（不是真删除）：`mode='auto'` 下洞被元素层盖住看不见，**元素一错位就露馅**。
⚠️ 另有一个**独立的 LLM 质量问题**（遗留未修）：`9:16` 被拆进两个文字层（一层 text=`9:16 Nano Banana`、一层 text=`9:16`）→ 重影。

**✅「背景层是否 LLM 决策生成」→ 不是，完全不调模型**：
```python
# run_split_layers_task
if payload.pure_background:
    bg_source, hole = split_background_plate(src_rgba, width, height, list(plate_by_id.values()))
else:
    bg_source = src_rgba.convert("RGBA").copy(); bg_source.putalpha(255)
```
`split_background_plate` = 「所有其它层 alpha 的并集」当洞 → `split_local_fill`（纯 PIL）填。
**零模型、零费用、零等待。** LLM 只决定「有哪些层」，图像模型只负责元素层。

**验证资产**：**新建** `output/spike/verify_split_anchor.py`（合成用例 + 老板真实产物双路径，VERIFY_RESULT=OK）；`check_split_backend.py` 补 4 条锚定断言；`verify_split_whole_image.py` 抽取列表补 `split_anchor_to_bbox`。目视件 `output/spike/diag_anchor_1010_compare.png`。

### AL.12 背景层三段路由：LLM 决策 + 可调模型（2026-10-10 第三轮）

> 触发：老板纠正上一轮汇报的「背景层 = 原图挖洞 + 本地低频补（**完全不调模型**）」——
> 「**背景层允许 LLM 决策生成的，可调用模型**」。

**三段路由**（`run_split_layers_task` 的 `phase = "background"` 段）：

| 条件 | 走法 | `method` |
|---|---|---|
| `pure_background=False` | 整幅原图 | `base` |
| **LLM `background.need_model=True`** | **调图像模型**做 object removal（局部重绘 + 遮罩贴回） | `model` |
| 其余（LLM 说不用 / 模型失败） | 本地 `split_background_plate`（挖洞 + `split_local_fill`） | `local` |

**LLM 决策点**：`SPLIT_LAYERS_USER_PROMPT` 的 JSON schema 新增顶层
```json
"background": {"need_model": <bool>, "prompt": "<仅 true：交给模型的背景描述>"}
```
判定口径写进 schema：纯色/渐变/天空/墙面/地面/虚化 → `false`（本地补更快更准）；
前景背后压着复杂纹理（花园/人群/货架/密排文字/重复图案）或大片被遮挡 → `true`；**拿不准填 false**。
`split_analyze` 解析后随 `{"canvas","layers","background"}` 返回；任务里取 `background_spec` 执行。

**关键细节**：
- 模型路线传 **`mask=hole`** —— 就是 `split_background_plate` 顺手算出的**各层 alpha 精确并集**，
  比 `split_element_mask` 按 bbox 画矩形准得多。
- LLM 的 `prompt` **追加**在内置英文规则之后（`"... no transparent areas. What the background should look like: <LLM>"`），
  与元素层 `cutout_prompt` 同一套路：**内置规则不可覆盖**。
- 失败向上抛，调用方 catch 后回落本地补洞，`bg_detail` 注明「已回落本地补洞」。
- 🚨 `split_erase_elements` **重新接回主流程**（2026-10-09 曾被下线），新增 `mask=` / `extra_prompt=`
  两个可选参数；不传时仍走旧的 bbox 近似（兼容 `verify_split_bg_fidelity.py`）。

**真实 e2e（3010，`mode=model`，`target_layers=3`，107.8s，5/5 层可用）**：
```
[running] background 0/1 正在用图像模型生成纯背景…       ← 模型路线真的跑了
stats = {elements:1, texts:3, base:1, redraw:True, model:2, local:0}   ← model=2（元素 + 背景）
背景 method=model  detail=图像模型移除各层内容后重绘补全（最底层）
元素 method=model  bbox=[247,244,666,790]（日志：锚定 (169,59,1088,1195) -> (260,244,899,1034)）
叠加还原度 = {mean:8.033, max:218, bad_ratio:0.22692}   ← 上一轮 31.785，锚定后明显变好
```
- ✅ **LLM 真的判了 `need_model=true`**（日志 `LLM 判定背景层需模型重绘补全`）→ 决策链路通。
- ⚠️ **背景填充质量一般**：模型把被移除的照片区域填成**近黑色块**，没延续卡片纹理。
  这是 `gpt-image-2`（唯一可用通道）的能力问题，不是接线问题；换更强模型应会改善。
  目视件 `output/spike/diag_1010_bg_model.png`。

**验证资产**：**新建** `output/spike/verify_split_background_model.py`（6 节 31 项，VERIFY_RESULT=OK）；
`check_split_backend.py` 旧断言「`split_erase_elements` 已不在默认流程里」**反转**成「重新接回主流程」
+ 新增 5 条背景路由断言。



## AL.13 文字层「被画两遍」的三个来源与修法（2026-10-10 第四轮）

> 触发：老板「这次元素层和背景层方向对了，但**文字层又不对了**」。
> 症状 = 画面上同一块文字出现**两行错位的字**。

**诊断口径（可复算）**：只取文字行 `y=198..232, x=340..620`（避开工具条 y<185 / 卡片顶边 y>243）。
度量「洞内笔画残留 = 背景层亮度 / 原图亮度」：修前 **82%**，修后 **0.0%**。

| 来源 | 证据 | 修法 |
|---|---|---|
| 背景层（模型路线） | 洞内笔画残留 82% —— 模型不是抹掉而是**把文字重画了一遍**（位置还偏） | 模型产出后 `split_fill_text_holes(made, text_hole)` |
| 元素层 | LLM 兜底元素 bbox 覆盖整个界面，把工具条标签一起框进去 | 把 `text_hole` 从每个 element 层 alpha 里 `ImageChops.subtract` 挖掉（跳过 `id='bg'`），重存 PNG |
| 文字层自己 | LLM 一次回 5 条 kind=text，3 条坏（合并层 / 截断层 / 重复层） | `split_prune_text_layers(texts)`（**跑两次**：定义后 + 精修后）+ 提示词规则 5/6 |

**新增函数（main.py）**：
- `split_clamp_alpha(img, box)` —— alpha 夹进 box。**文字层必须夹**：`split_pixel_layer` 的 15% 外扩
  会把工具条下沿/卡片上沿当文字留下（实测 alpha 多出 y=170~179 / 243~251 两条横线），
  这些假像素会污染背景的洞 + 元素层。
- `split_fill_text_holes(img, hole, rounds=3)` —— 文字洞**迭代**低频补。一次降采样会把笔画自身亮度
  摊进均值（实测单次仍留淡影），迭代几轮文字能量按几何级数衰减。洞外像素不动。
- `split_text_key(value)` —— 归一化（去空白 + 小写）。
- `split_prune_text_layers(items)` —— ①**合并层**：框内装 ≥2 条别的文字且自己 ≥2 行 → 删；
  ②**截断层**：短框在长框内（`inside` 带 **6px 容差**，LLM 两次给同一块文字框差几像素）+ 归一化后
  短串是长串前缀**或前 60% 字符相同** → 删短的（实测 `9:16 Nanc` 末字被读错，严格前缀判不出）；
  ③**完全重复**：同内容 → 删框更松的。
- 文字层 bbox 之后**贴到实测范围** `split_layer_hole(alpha).getbbox()`：前端编辑态按 bbox 用系统字体
  重画，bbox 差 10px 就与背景原文字错开成两行。

**🚨 关键认识**：删掉一条文字层是**安全**的 —— 后端不为它挖洞，那块文字以原图像素留在元素/背景里，
画面上仍只出现一次（只是不再可编辑）。所以修剪判据可以保守：**宁可漏删不可错删**。

**🚨 修剪必须跑两次**：`texts` 定义后（用 LLM 原始框，省掉精修白花的钱）+ **精修后**（`split_refine_text`
会改 bbox —— 实测「比例标签 `9:16`」原始框没被「模型名称」包含，精修后才包含 → 只跑第一次会漏）。

**提示词**：`SPLIT_LAYERS_USER_PROMPT` 规则加 5/6 —— 禁止合并/重复文字、要求元素框不要圈文字。
实测有效：下一次运行的兜底元素 note 自动写了「**不包含可读文字**」。

**真实 e2e（3010，`mode=model`，`target_layers=3`）**：背景 `method=model`，残留 0.0%；
文字层 `Woman portrait` / `9:16` / `Nano Banana` / `Anya` / `Mahmud` 各画一次无重影。
目视件 `output/spike/diag_1010d_text_cmp.png`（原图 / 背景层 / 前端合成 三格）。

**验证**：新建 `output/spike/verify_split_text_fix.py`（4 节 ~35 项，VERIFY_RESULT=OK）。
诊断脚本 `output/spike/diag_1010b_*.py`（像素测量）、`diag_1010c_front.py`（按前端口径复现合成）。

**⚠️ 遗留**：`split_anchor_to_bbox` 的 `min_scale=0.25` 会拒绝「模型把元素画得太大」的锚定
（实测模型把小茶壶画成满画幅 → alpha 外接框≈整图 → scale=0.14 → 拒绝 → 茶壶盖住整卡）。
守卫是防「alpha 里有远端噪点把 bbox 撑大」的，不能简单放开。

## AL.14 界面覆盖物（鼠标指针）识别 + 锚定实测数字（2026-10-10 第九轮）

### AL.14.1 🚨 提示词规则 7 被「粒度段」压掉 —— 定位手法可复用

上一轮加了规则 7「界面覆盖物必须单独成层」，**没生效**。定位手法值得记住：
**把日志 `[canvas-llm] text_len=N` 与源码里提示词的实际长度对账**。
- 上次运行 `text_len=3186`；`SPLIT_LAYERS_USER_PROMPT`(2961) + `split_granularity_prompt(3)`(225) = **3186** ⇒ 规则确实发出去了，是模型没照做。
- 真因：粒度段自己写「前景只输出 2 层：**只保留最关键的视觉主体，其余全部并进背景或并进同一层；宁少勿多，绝不细碎**」，
  模型那次**正好只回 2 个 element**，把工具条/图标/加号全并进一条 → 规则 7 被「其余全部并进同一层」吞掉。

**修法**（`split_granularity_prompt`）：给界面覆盖物开豁免口，与既有「文字不占这 N 层」同套路：
```
用户要的是 {n} 层 = 背景 1 层 + 前景 {fore} 层。背景层由程序自动补，你只负责前景、文字与界面覆盖物：
…
- 界面覆盖物（鼠标指针 / 光标 / 箭头这类小图形）也不占这 {n} 层：它们必须按规则 7 单独成层，
  不要被上面那句「其余全部并进背景或并进同一层」吞掉，也不要当成照片或背景的一部分。
- 层数宁少勿多：合并优于拆碎（但上面两条例外项不算在内）。
```
规则 7 补强失效点（模型把指针当成照片内容）+ 检查范围扩到「工具条附近、任何标签或文字旁边」：
```
⚠️ 即使这个指针压在照片、人物或风景上，也**必须**单独成层 —— 它属于界面覆盖物，
不要因为「它叠在照片上」就把它当成照片内容的一部分而漏掉。
```
**实测**：新提示词 = 3056 + 342 = **3398**，日志 `text_len=3398` 逐字吻合；结果
`L13 绿色鼠标箭头 [112,44,34,35]`（老板没提，额外抓到）、`L14 粉色鼠标箭头 [759,946,31,35]`（老板要的）。
**副作用**：粒度豁免同时放开了「其余全部并进同一层」→ 老板选 3 层却拿到 **14 个 element**
（内容层 2 个正好=「前景 2」，其余 12 个是界面覆盖物）。已向老板说明、待定夺。

### AL.14.2 指针真值 + 判定口径（`output/spike/check_cursor_layer.py`）

- **粉色指针真值**：窗口 `(730,920)-(840,1010)` 内以 `#E97D9B` 为种子、色距 ≤22 取**最大连通块**
  → **bbox=(759,946,31,32)、面积 451、主色 (233,125,155)**。其余同色小块（面积 54/32/30…）是 `Mahmud` 药丸标签的粉边粉字。
- **绿色指针真值** ≈ `(114,46,46,44)`、色 `(133,174,112)`。
- 🚨 **判定必须用 IoU ≥ 0.3，不能用「覆盖率 = 交集/真值面积」**：`bg (0,0,1248,1248)` 与中央卡片
  `(247,245,668,781)` 都能 100% 盖住真值框 → 误报；IoU 天然惩罚「框太大」。实测 `L14 IoU = 0.914`。

### AL.14.3 锚定已忠实，剩余误差在 LLM bbox（逐行量边缘的口径）

`L1` 本轮真走模型（`method=model`）——`split_anchor_to_bbox` 重写后第一次在真实模型产物上跑：
```
模型原始 alpha bbox (182,74,1073,1196) = 891x1122（放大 1.33x/1.44x 且偏左上）
锚定后           alpha bbox (247,245,915,1026) = 668x781
LLM bbox [247,245,668,781]                       ← 逐像素完全一致
```
**逐行量边缘**（`diag_1010m_edge_quant.py`；口径：卡片旁是纯深色画布，逐行找「原图最右亮像素」vs「L1 alpha 最右不透明像素」）：
```
R 边：中位偏差 +16px  溢出(>+3px) 83.9% 行  最大 +31px
L 边：中位偏差  +8px  溢出(>+3px) 87.4% 行  最大 +14px
```
⇒ **锚定现在忠实铺满 bbox，但 LLM bbox 比真实卡片宽约 24px** → 合成图边缘外一条浅色带。
**要根治需「bbox 按源图真实边缘吸附」**（同 `split_refine_text` 套路：背景环带均匀才吸、纹理背景跳过），未开工。

### AL.14.4 环境与工具

- **验证用独立实例 3013**（不动老板 3000/3010）：`env -u HTTP_PROXY … ./python/python.exe main.py --port 3013`；
  `run_split_once.py` 新增 `SPLIT_BASE` 环境变量。**用完 taskkill（先 ctypes 反查 exe 确认是工作区 python）**。
- ⚠️ **`output/spike/resync_static_v.py` 不是一次幂等**：第 1 遍重写全部 html → html 自身 mtime 变 →
  第 2 遍还会再改引用它们的 `index.html`，**第 3 遍才 `(无变化)`**。跑完不用重启服务。
- ⚠️ **PIL 不在受管 python 3.13.12 里**：跑 split 相关脚本用
  `C:\Users\Administrator\.workbuddy-ai\binaries\python\envs\default\Scripts\python.exe`（3.13.14 + PIL 12.3.0）
  或项目自带 `python/python.exe`（3.10.11 + PIL）。
- 🚨 **图像通道额度用尽**：`ep_1791516939807/gpt-image-2` 与 `gpt-image-2.5` 全
  `502 … {"error":{"message":"apikey credits not enough"}}` → 元素层回落 `method=local`。
  **本地去背在纹理背景上必带残渣**：粉色指针压在玫瑰上 → 箭头形状对但四周粘花瓣碎片；
  绿色指针压在纯色深底上 → 抠得极干净。⇒ 指针像素质量**取决于图像模型通道**。
- **本轮修正 4 条陈旧断言**（`check_split_backend.py`，上一轮重写时漏同步、上轮回归清单里**没跑这个脚本**）：
  ①等比居中→非等比铺满；②护栏改 `min(sx,sy)/max(sx,sy)`；③`split_measure_rotation(plate)` + `piece["rotation"]`；
  ④`if plate is not None and cut_ok:`。另新增 3 条断言（粒度豁免 ×2、规则 7 补强 ×1）。



## AM. 文字倾角换主口径 + 元素层「组 bbox 抄邻居」闸（2026-10-10 第十轮）

老板：「就剩下一些字体倾斜角度以及元素层边缘对齐问题了」。当时 3010 被老板停掉且要求不重启 ⇒ **全程无 e2e，只用真实产物离线取证**。

### AM.1 🚨 文字倾角换主口径：`split_measure_text_angle(src_rgba, bbox)`

- **旧口径为何错**：`split_measure_rotation` 量的是**文字层自己的 alpha**，而它已被
  ① `split_clamp_alpha` 夹回 LLM bbox（+4px）、② 本地抠图把**底板亮边框**一起抠了进来
  ⇒ 最小面积矩形量到的是「残缺形状」的朝向。实测 Anya alpha bbox 仅 56x24，量出 **+6.0°**（真值 +1.26°）。
- **新口径**：**只看原图那一小块，完全不碰 alpha** —— 逐列取墨迹**上缘与下缘**各做 Theil-Sen 稳健回归，两角取中位。
- **三条经验（都踩过坑）**：
  1. 极性（亮字暗底/暗字亮底）靠**残差更小**选，**不能看「哪一极像素多」**
     （`Woman portrait` 暗极有效列 197 > 亮极 166，但暗极拟的是背景）。
  2. **残差 IQR 只能用来挑极性，不能当准不准的闸**：真文字 IQR 就有 5~9px，
     `IQR > 2.5` 会把五块**全拒掉**。准不准靠「墨迹占框宽比例 0.30~0.92」（真文字 0.64~0.71）。
  3. `pad = max(4, int(h*0.25))` —— **按高度取**；按 `max(w,h)` 会让宽文字塞进大片背景 → 闸门拒收。
- **调用位置**：文字层循环里 **优先用它**，`measured is None` 才退回 `split_measure_rotation(plate)`；
  因为不依赖 alpha，**不再需要 `cut_ok` 前提**（旧代码的 `abs(model_rot) < 1.0` 也去掉了）。
- **效果**：平均绝对误差 **1.85° → 0.36°**（Anya 4.74→0.36、Nano Banana 1.74→0.06）。

### AM.2 🚨 元素层「组 bbox 抄邻居」闸（双边缘元凶）

- **病灶**：LLM 会把一**组**东西当一个元素，给出横跨整幅的 bbox（实测「侧边参考图片卡片组」= `[0,82,1248,767]`）；
  模型路失败后回落**本地抠图**，而本地抠图只会「把这块矩形里不像背景的都留下」——
  它没法知道哪些像素是「我的」⇒ 把中央卡片原样抄一份（与源图**逐像素相同**）、
  还带更高 z 盖在真卡片层上 ⇒ 画面上两层错开的卡片边缘。
- **判据（实测数据定的，两条同时满足才丢）**：`method == "local"` **且** bbox 面积 ≥ 画布 **40%**
  **且** ≥ **80%** 的 alpha 落在别的元素层 alpha 里。
  （该层实测：面积 61.5%、被覆盖 93.8%；其余元素最大 33.5%、工具条 3.2%、图标 0.0~0.1% ⇒ 分得很开）
- **⚠️ 只丢 `out_layers`、不删 `plate_by_id`**：背景层挖洞还要用它，少挖一块会让背景残留卡片。
  代码里整段包 `try/except`（这时候已经跑完所有模型调用，不值得为一个后处理把任务炸掉）。
- 去重后剩余：L1 自身 alpha 忠实铺满 **LLM bbox**，而 LLM bbox 不准 ⇒ 元素层比真卡片宽 ~3%（见 AM.3）。

### AM.3 测量口径：拿自写测量当基准前，先跟源图亮度剖面对一次数

- 「从中心向外走、遇连续 ≥15px 暗像素即止」量边缘时，**左向行走返回值偏左 28px**：
  `return x - run + 1` 在左向时算错了起点（run=15 时正确起点就是 `x`）；右向行走那条恰好对（= 最左暗像素）。
- **金标准是「三条长边互相印证」**：卡片上缘 +1.27° / 下缘 +1.26° / 工具栏上缘 +1.25° ⇒ 全局 UI 倾角 **+1.26°**。
- **直接看像素剖面最快**：`y=450` 一行打出 `x=270..360 step 6` 的亮度，就能看到卡片左缘在 331（x=330 是 19、x=336 是 160）。
- **真卡片 bbox 参考值**（那张图）：y=450 左缘 x≈331、右缘 x≈888（宽 557）；
  L1 alpha 同排 (325, 899)（宽 574）⇒ **左外 6px、右外 11px、整体宽 3%**；
  右溢出随 y 递增（y=300 +1 → y=580 +16，**全为正**），LLM bbox 668 宽 vs 真值约 704。

### AM.4 背景文字洞补全：`rounds` 3 → 6

量「洞内 vs 洞外环带」亮度差（当前 bg 是 `method=model`）：

| rounds | Anya | Woman portrait | 9:16 | Nano Banana | Mahmud |
|---|---|---|---|---|---|
| 3 | 1.2 | 0.7 | **8.7** | 1.1 | 2.7 |
| 6 | 1.2 | 0.3 | **4.9** | 0.3 | 2.7 |
| 10 | 1.2 | 0.3 | 2.4 | 0.3 | 2.7 |

只有 `9:16`（洞内是胶囊底）还有 8.7 ⇒ 6 轮。⚠️ **元素洞不能这么糊**（没东西盖回来，糊过头会露补丁）。

### AM.5 回归脚本要跟着改的三处（本轮踩到，下次改这两个函数必看）

1. `check_split_backend.py`：`rot_src` 的结束锚点从 `def split_local_cutout(` 改成 `def split_measure_text_angle(`
   （新函数插在中间，否则块里混进两个函数）；删掉两条旧口径断言（「只补模型给 0」、
   「只在 cut_ok 时才量」），换成新口径 + 7 条新函数断言 + 兜底层闸 2 条 + rounds=6 一条。
2. `verify_split_board.js`：**`makeCtx()` 必须补 `measureText`**（新拟合要量 `actualBoundingBox*`），
   否则 `splitLayersDrawText` 直接 ReferenceError；新增 `extractLet('SPLIT_LAYERS_INK_CTX')`
   （`if(!VAR)` 在 try 外，不抽出来会抛）；给 sandbox 传 `document` 桩。
3. `verify_split_board.js` 3 条断言按新渲染方式改：`textAlign=center`→**固定 left**、
   「锚点在 box 中心 x」→「translate 里有 (box.x,box.y)」、「save/restore 各 3 次」→「相等且 ≥ 层数」。

### AM.6 本轮验证结果

- `py_compile main.py` OK；**Python 8/8 全绿**（check_split_backend / verify_split_align_1010 / verify_split_anchor /
  verify_split_background / verify_split_bg_fidelity / verify_split_pixel / verify_split_text_fix / verify_split_whole_image）。
- **JS 3/3 全绿**：verify_split_board **91-0**、verify_split_pea **54/54**、verify_split_models **35-0**。
- `?v=` resync 到不动点（3 遍：12 → 1 → 0）；未提交、未升版本号（留在 **1.1.8**）。
- 离线合成对照资产：`output/spike/diag_1010AA_guard_ab.png`、`diag_1010AA_corner.png`、`diag_1010y_local_clean.png`、`diag_1010z_text_sheet.png`。


## AN. 文字逐处拆层 + 元素几何「矩形化」（2026-10-10 晚）

### AN.1 多行文字层 ⇒ 逐处拆层（老板「文字层更不对了」）
- **症状**：画面上一个「四行左对齐的斜体大字块」，不在原位、字号也被撑大。
- **根因**：前端 `splitLayersDrawText` / `splitLayersTextNodeHtml` 把 `text` 里的 `\n` 当**一个段落**，
  按 `字号*1.15` 行距从盒子左上角左对齐排，再按墨迹盒拟合撑满 bbox；
  而 LLM 把「Anya 胶囊 + 工具条上的 9:16 / Nano Banana + 下面的 Woman portrait」并成了一条多行文字。
- **证据**：截图里四行**左缘 x 全等**（源图里是 156/372/689/774）；`split_text_*.png` 尺寸反推 bbox ≈ 497x158。
- **修法**：
  ① `SPLIT_LAYERS_TEXT_PROMPT` 增加 `lines: [{text, bbox}]`，要求「几处互不相邻的文字逐处标」；
  ② `split_refine_text` 把 lines 换算回原图坐标 → `item["lines"]`；
  ③ 新增 `split_text_by_lines(full, item)` 按 lines 拆层（各自贴自己的实测 bbox、各自反推 font_size、
     id 加 `L1/L2…`、name 加 ` · 文案`）；出图层前 `pop("lines")`。
- 🚨 **不许改成纯像素分段**：`Anya` 的胶囊比它自己的字还宽 ⇒ 按宽度配对会和 `9:16` **换位**；
  LLM 的行序又不是阅读序 ⇒ 位置约束也救不回来。**没有 `lines` 就原样返回。**
- 两道自检：① lines 条数 == 文案行数；② 每处框在本层 alpha 里真有墨迹，且各框重叠 ≤ 40%。

### AN.2 元素层几何「矩形化」（老板「元素层图片的变形状态没有对齐」）
- **症状**：元素层右缘越往下越出卡片（y=303 外溢 4px、y=943 外溢 15px）⇒ 一条**渐宽的缝**。
- **根因**：旧口径 `split_anchor_to_bbox` = 「按 bbox 长宽比反解一个角 + **非等比铺满**」。
  非等比缩放是仿射变换，**旋转过的矩形被一拉就变平行四边形**（剪切），不再是矩形。
- **判据（关键）**：取 alpha 四个极值像素 = 旋转矩形四角，算竖边/横边倾角；
  **矩形**满足 `竖边倾角 + 横边倾角 ≈ 0`，剪切破坏的正是**垂直度**。
  ⚠️ 别用「左右边是否平行」判剪切 —— 平行四边形照样左右平行。
- **实测**：老板真实产物 竖边 -10.02° / 横边 +6.49°（和 -3.5°）；源图真值 **8.84°**。
- **修法**：新增 `split_measure_shape_angle(img, bbox)`（左右各 18% 带宽找最强梯度 + Theil-Sen；
  两边倾角差 > 1.5° 判不准；**残差 IQR > 4px 判「不是直线」**，防花草/人像被硬转）；
  `split_anchor_to_bbox` 加 `src_rgba` 参数，优先走
  **① 按模型产物自己的实测倾角转正 → ② 缩放到「转回真值倾角后外接框正好 = bbox」的矩形
  （解 `[ct st; st ct][w h]^T = [bw bh]^T`）→ ③ 按源图实测倾角转回去**。结果恒是矩形。
  量不准 ⇒ 退回旧口径。
- ⚠️ 符号标定：`Image.rotate` 角度 = `-atan(dx/dy)`（实测 `alpha.rotate(+8.84)` 把卡片转正）。
- 调用点：`split_extract_element` 里 `split_anchor_to_bbox(full, [bx,by,bw,bh], src_rgba=base_rgba)`。
- 🚨 **本节口径已被 AO 取代**（同日发现源图那张卡片本身就是平行四边形，不是矩形）——
  这里保留作历史；`split_measure_shape_angle`（竖边）仍在用，**结果恒为矩形**这条已作废。

### AN.3 本轮新增/改动的验证资产
- 新增 `output/spike/verify_split_shape_1010.py`（几何矩形化，含「真实产物复现剪切」「圆形元素返回 None」）。
- 新增 `output/spike/verify_split_textlines_1010.py`（逐处拆层，含六类「原样返回」兜底）。
- 4 个老脚本的**源码字符串断言**已同步（`piece`→`sub`、锚定调用多了 `src_rgba=base_rgba`、
  `verify_split_whole_image` 抽取清单补 `split_measure_shape_angle`）。改 `main.py` 的签名/调用点后**必须一起改**。
- 诊断图：`diag_1010AF_anchor_ab.png`（三连对照）、`diag_1010AG_rightedge_ab.png`（右缘放大，最有说服力）、
  `diag_1010AH_textfix_ab.png`（文字层：一条合并 bbox 红框 vs 逐处绿框，由 `diag_1010AH_textfix_ab.py` 生成，只画框不渲染字）。

## AO. 元素几何「仿射映射到源图那块平行四边形」（2026-10-10 深夜）

### AO.1 老板反馈与结论
- **反馈**：「文字层还是很怪、跟原图差距更大了；元素层的图片**左下角和右上角**还没有对齐」。
- **反馈一（文字层）⇒ 无法复现、判定已修好**：老板这次跑的是新代码（`main.py` mtime 14:01:43 <
  产物 mtime 14:29:50~14:32:21）。`recon_1010B_diff.py` 把 13 层按 z 序叠回源图，**像素差 >40 只 5.60%**，
  `diag_1010B_recon_text.png` 里文字区**两行几乎一致**。⇒ 不再改文字层（改了反而引入新偏差）。
- **反馈二 ⇒ 真根因**：**源图那张卡片本身就是「被剪切过的平行四边形」**。

### AO.2 🚨 源图是平行四边形（推翻 AN.2 的前提）
逐列/逐行首像素 + 最小二乘 + 离群剔除（`measure_1010B_srcquad.py`、`verify_1010B_topedge.py`）：
| 边 | 倾角 | rms | n |
|---|---|---|---|
| 上边 | **+1.30°** | 0.21 | 216 |
| 下边 | +1.15° | 0.24 | 216 |
| 左/右边 | **−8.8°** | 0.29 | 178 |

⇒ 「横边倾角 + 竖边倾角 ≈ 0」这条**矩形判据在源图上根本不成立**（源图自己 −8.8+1.3 = −7.5）。
旧口径产物横边落在 **+4.67°** ⇒ 差 **3.37° × 666px ≈ 22px** = 右上角/左下角**各差一截**。
⚠️ **AN.2 的「矩形化」救不了**：它把源图倾角当旋转角，产出横边落在 +4.4°，源图要 +1.3°。

### AO.3 修法：`Image.transform(Image.AFFINE)` 仿射映射
把模型那块转正（竖边竖直、横边残留斜率 s），再**仿射映射**到「由源图实测 ta（竖边）+ tb（横边）
+ 外接框 (bw,bh) 反解出的平行四边形」。仿射把平行四边形映成平行四边形 ⇒ 结果**必然**同形同位。

关键式（`split_anchor_to_bbox` ① 路径，**整段替换**了 AN.2 的「旋转-缩放-反旋转」）：
```
ta = tan(-deg_src)      tb = tan(hgt_src)
den = 1 + ta*|tb|       hq = (bh - bw*|tb|)/den      wq = bw + hq*ta
hp  = fh - fw*|s|                       # 模型那块转正后的侧边长度
模型侧: P0=(0, max(0,-fw*s))  a_v=(fw, fw*s)   b_v=(0, hp)
目标侧: Q0=(0, max(0,-wq*tb)) qa=(wq, wq*tb)  qb=(hq*ta, hq)
M·a_v = qa、M·b_v = qb  ⇒ m01=qb[0]/hp、m11=qb[1]/hp、
                          m00=(qa[0]-(fw*s)*m01)/fw、m10=(qa[1]-(fw*s)*m11)/fw
T = (Q0+off) - M·P0     off = (bx-qminx, by-qminy)
逆变换喂 transform: i00=m11/det、i01=-m01/det、i10=-m10/det、i11=m00/det
                    cx = i00*(bx-tx) + i01*(by-ty)      ← 🚨 别加负号
                    cy = i10*(bx-tx) + i11*(by-ty)
```
尺度闸 `min_scale <= min(sx2,sy2) and max(sx2,sy2) <= max_scale`（`sx2=wq/fw`、`sy2=hq/hp`）。
两个量测任一为 None ⇒ 退回旧口径。

### AO.4 🚨 路上挖出的三个真 Bug（全修）
1. **bbox 单位坑**：`split_measure_shape_angle(alpha, list(box))` —— `box` 是 `getbbox()` 的 `(l,t,r,b)`，
   函数要 `(x,y,w,h)` ⇒ 在**偏到右下的空区域**上量、**恒 None** ⇒ 仿射整段**静默跳过**、永远退回旧口径。
   正确：`[box[0], box[1], box[2]-box[0], box[3]-box[1]]`。
   ⚠️ 上一轮的回归脚本把这行 `list(box)` 当**正确写法锁住**了，所以一直没暴露 ——
   **别让回归脚本去锁"实现细节字符串"，要锁行为**。
2. **仿射逆变换符号写反**：`cx = -(i00*(bx-tx)+i01*(by-ty))` ⇒ 产物横边 **+36.25°**、覆盖度 **51.59%**。
   正解见 AO.3（`p = Minv·(q−T)`、`q=(bx+X, by+Y)` ⇒ 常量项是 `+Minv·((bx,by)−T)`）。
3. 🚨 **`split_measure_shape_angle_h` 的「上下取均值」是错的**（详见 AO.5）。

### AO.5 🚨 横边量测：上边优先、下边兜底（不取均值）
- LLM 的 bbox 常把卡片边切掉几像素：**同一张卡片 bbox 差 1~5px，横边量测就从 0.51° 变成 None**。
- 逐道闸装仪表（`probe_1010B_h_debug.py`）+ 参数扫描（`probe_1010B_band.py`、`probe_1010B_edgewise.py`）：
  **上边那串干净**（恒 1.23~1.25°）；**下边那串被卡片内部人像纹理带偏**（−0.44 / 0.0 / −0.15 乱跳）
  ⇒ 取均值把 1.24 拉成 0.55。**外扩 bbox 反而更糟**（下带混入卡片下方玫瑰枝，IQR=5.0 全被拒）。
- **修法**：① 上/下边**各自独立过 IQR 闸**（≤4px），**先上边、后下边**，**不取均值**；
  ② 带从 **18% 收到 12%**（18% 时连整幅图都会被误量出 0.0°）。
- 修后 7 组 bbox 全部量到 **1.08~1.26°**（真值 1.30），整幅图正确返回 None。

### AO.6 验证（权威口径）
🚨 **别用 `edge_angles` 的「四角极值点」量不规则 alpha** —— 极值点不落在真正的角上，
实测给 +3.74°，而权威 +1.03°。**权威量测 = `verify_1010B_topedge.py`**（逐列首像素 + 最小二乘）。

| | 上边倾角 | 与源图(+1.30°)差 | 覆盖度漏 |
|---|---|---|---|
| 旧口径 | +4.67° | +3.37° ≈ 22px | 5.00% |
| **新口径** | **+1.03°** | **0.27° ≈ 2px** | **2.51%** |

- 回归：Python **12/12**、JS **3/3**（board 91-0、models 35-0、pea 54/54）。
- 同步的失效老脚本：`check_split_backend`（两条几何断言换仿射口径）、
  `verify_split_whole_image` / `verify_split_shape_1010`（抽取清单补 `split_measure_shape_angle_h`）、
  `check_split_static`（3 条前端断言过时：像素态渲染已抽成 **`splitLayersImageHtml` 共用函数**、
  合成改成 `drawImage(img, -box.x, -box.y, cw, ch)`、`系统字体重画` 只剩注释里）。

### AO.7 未做 / 待定
- **e2e 目视确认**：本轮**没重启任何服务**（老板的 3000 在跑，红线不许擅杀）。`main.py` 改动
  **必须重启才生效**。
- 提交 / 升版本号：仍未做（长期约束：留在 **1.1.8**）。
- 遗留：`9:16` 文字倾角闸拒收（1.26°）、粉色指针像素质量、`min_scale=0.25` 拒绝「模型把元素画得太大」。

## AP. Photopea 对用户完全不可见（2026-10-10）

老板口径：「页面中的精细编辑功能可以隐藏掉」+「导出分层 PSD 时不显示 Photopea 的页面给用户」。

- 🚨 **关键机制**：`.sl-pea { display: none }` + `.split-layers-stage.pea .sl-pea { display: block }`
  ⇒ **只要不加 `.pea` class，Photopea iframe 就不可见**。`splitLayersEnsurePea` 只做
  `host.innerHTML = ''` + `createEmbed`，**不改可见性** ⇒ 后台建文档 + 注入全程用户只看到进度遮罩。
- 改动：① `split-layers.css` 加 `.sl-stage-bar #splitLayersPeaBtn { display: none; }`
  （**id 特异性压得住 `.sl-stage-bar .sl-btn`**；404 行的 `margin-left: auto` 就是它靠右的原因）；
  ② `splitLayersExportPsd` **删掉「导出前切视图」那 5 行**（`peaMode = true` / `classList.add('pea')` /
  `btnLabel.textContent`）。
- **DOM 与 `splitLayersTogglePea` 都保留**（导出链路仍要用 Photopea），只是不给入口 —— 想恢复删 CSS 那一条即可。
- 同步了 2 条**与需求冲突**的旧断言：`check_split_static.py`「PSD 导出会切到 Photopea 视图」
  → 断言 `classList.add('pea')` **不出现**；`verify_split_pea.js` 的 `peaMode === true` → **`false`**。

### AP.1 「没使用图像生成次数较多 + 分层数作用不大」（老板认可结果，未改代码）
- **模型次数少是省，不是漏**：`need_model` 由 **LLM 逐层决策** —— 只有需要「重绘/补全」的层才调图像模型，
  纯色块、边缘干净的图标走**本地抠图**。
- **「分层数作用不大」的真因**：图层列表里大量是「工具栏图标 / 鼠标指针」这类**界面覆盖物**，
  被**规则 7** 强制单独成层、且**不占用户选的层数**（粒度段豁免，见 **AL.14**）。
  已知副作用：选 3 层实际会拿到 14+ 个 element。老板说「效果非常好」⇒ 保持现状；
  若要「选的层数更贴近实际层数」，可把同类 UI 覆盖物合并成一层（**需老板点头**）。

## AQ. 拆分图层：图层列表拖拽排序 + 圆点选择（2026-10-10）

### AQ.1 结论：列表拖拽**不要用原生 HTML5 拖放**
第一版用 `draggable="true"` + `dragstart/dragover/drop`，源码看着全对、静态断言全绿，
但老板两次反馈「拖拽不支持」。原因有两层：
- 桌面壳（WebView2）里从普通 `div` 发起原生拖放经常**整个不触发**；
- 行上留着 `draggable="true"` 时，浏览器一旦进入原生拖拽就会**吞掉 `pointermove`** ——
  想再补一条 pointer 路径会被它直接打架。
⇒ 现在行上**不写 `draggable`**，只用 `pointerdown/pointermove/pointerup` 手写（4px 死区 + `setPointerCapture`）。
排除拖拽起点的选择器：`button, input, label, a, [data-split-canvas-pick]`（眼睛 / 圆点 / 复选框）。

### AQ.2 🚨 图层列表有两套方向相反的坐标系
| | 顺序 | 谁在用 |
|---|---|---|
| **显示**（`splitLayersRenderList`） | z **降序**（最上面 = 最高 z） | 图层列表 |
| **内部数组** | z **升序**（最下面 = 最低 z） | 合成 / PSD 注入 / 导出 / 画板 |

⇒ 换算只在 `splitLayersMoveLayerToIndex(draggedId, displayIndex)` 里做一次：
拿显示序数组、`splice` 到 `displayIndex`、**倒过来**写 z（`shown.slice().reverse()`）。
同一天在这里踩了两次（先错一位、后把 +1 方向写反），所以落点必须由真实 DOM 测试锁住。

### AQ.3 🚨 落点不能用「指针落在目标行上半还是下半」
行高实测 **44px**，而拖拽死区只有 4px ⇒ 指针**还压在自己那一行里**、只挪 6px，
就会被判成「插到下一行上面」→ 整行直接甩到列表头部。
正确算法（`dropInsertIndexAt`）：**跳过被拖的那一行**，数有几行的中线落在指针上方，
那个计数就是插入下标；指针没离开自己那行时计数恒等于原位。

### AQ.4 拖拽后的尾巴
- 松手后浏览器还会补一个 `click` → 会把「刚拖过的那层」又切换一次选中。
  用 `suppressClickUntil = Date.now() + 350` 挡掉。
  🚨 **别用一次性 boolean 标志**：浏览器没补 click 时标志会一直留着，反而吃掉用户下一次正常点击。
- 键盘等价入口：行上 **Alt+↑/↓**（`keydown` 委托在列表容器上，入参是「去掉被拖行之后」的下标，
  所以上移 = `from-1`、下移 = `from+1`）。**必须有** —— 去掉上下移按钮后，纯键盘用户否则无法排序。

### AQ.5 「铺到画布」按钮的可发现性
老板反馈「选完圆点找不到导出到画布的按钮」。标题栏那个（`#splitLayersToCanvasBtn`）在窗口最右边，
容易被整块忽略；且 `.split-layers-head-actions` 没写 `flex:0 0 auto` 时会被
`.split-layers-window` 的 `overflow:hidden` **裁掉最右边那个按钮**（看起来就像「按钮不存在」）。
⇒ ① `head-actions` 加 `flex:0 0 auto`、标题让位；② 图层栏底部再放一个主按钮
`#splitLayersToCanvasSideBtn`，按钮上直接写「已选几个」（`#splitLayersToCanvasCount`，内容形如 `· 2`）。
两个按钮的 disabled 与角标统一由 `splitLayersSyncCanvasAction()` 维护（`splitLayersRenderList` 末尾也会调）。

### AQ.6 真实 DOM 验证资产：`output/spike/verify_split_layers_dom.py`
**静态断言在这个功能上完全不够**（原生拖放那版就是「全绿但用户用不了」）。这个脚本：
- 把 `static/smart-canvas.html` 复制成 `static/__probe_sl.html`，在 `</body>` 前注入采集脚本；
- 探针走**应用自己的代码路径**（`splitLayersBindOnce()` + `splitLayersApplyResult(伪造后端结果)`），
  不手搓 DOM、不手动加类；
- 派发**真实 PointerEvent / KeyboardEvent**，量**真实 getBoundingClientRect**；
- 无头 Edge `--dump-dom` 取回 49 项断言；收尾删探针页。
- ✅ **探针页不带 `?id=` ⇒ 完全不碰 `data/canvases/`**（`smart-canvas.js:1` 只读 `params.get('id')`，
  没有 id 不跳转也不加载画布）。

🚨 写这类探针时踩过的坑：
- **别「先手改 `checked` 再 dispatch click」**：`click` 在 checkbox 上还会跑一次激活行为 →
  等于翻转两次 → 探针自己假报「没选上」。要用 `el.click()` / 点 `label` 里的圆点。
- **内层函数里的 `var text` 会遮蔽外层同名辅助函数** → `TypeError: text is not a function`。
  探针里辅助函数别用 `text` / `data` / `name` 这类通用名。

## AR. 拆分图层：「在线 PS」新标签页打开（2026-10-10）

### AR.1 目标与做法
老板要「跳转到新的网页 Photopea 网页并打开此次拆分项目的所有图层」。
做法：把本次分层结果合成 PSD → 上传换一个 http 地址 → 新标签页打开
`https://www.photopea.com/#<encodeURIComponent(JSON.stringify({files:[psdUrl]}))>`。
入口：**只有标题栏一个** `#splitLayersOnlinePsBtn`（紧邻「导出分层 PSD」）。
⚠️ 2026-10-10 老板反馈「左侧栏重复了一个在线 PS」→ 图层栏底部那个（`#splitLayersOnlinePsSideBtn`）
已删除，`split-layers-side-foot` 只剩「铺到画布」一个按钮。别再把它加回来（静态守卫 + DOM 探针都有反向断言）。

### AR.1b 🚨 `#` 后面绝对不能加斜杠（2026-10-10 实测推翻）
老板曾要求把链接改成 `#/<配置>`。**实测会坏**，已改回 `#<配置>`。
判据（`output/spike/probe_photopea_fetch.py`）：本地起一个带 CORS 的静态服务器，
看 Photopea **有没有真的来 fetch 这个 PSD** —— 它解析不出 hash 就绝不会发这个请求。
| 形式 | 服务器收到的请求 |
|---|---|
| `#<配置>`（官方写法） | 1 个，`origin=https://www.photopea.com` ✅ |
| `#/<配置>` | **0 个** 🚨 一个图层都载不进来 |

同一台机器、同一个 PSD、只差一个斜杠 → Photopea 把 `#` 之后整段当 JSON parse，
多一个 `/` 就失败，`files` 与 `script` 全部不生效（页面看着正常，但是空的）。
⚠️ 前两次探测（看 `document.title`）**判不出来**：`script` 的官方语义是「每个文件加载后执行」，
无头环境里从不执行，两种形式 title 一模一样。**要测 Photopea 就得看网络请求，别看页面内脚本。**

### AR.1c 「带 hash 就无广告」是误解（2026-10-10 查证）
老板说「`https://www.photopea.com` 有广告，`https://www.photopea.com/#STRING` 无广告」。**不成立**：
- **官方文档**（`photopea.com/api/`）：想「hide advertisement ... whitelabel mode」要买
  **Distributor account**；`/api/accounts` 另说登录 **Premium account** 可「without advertisement」。
  `environment` 的**全部**可选项里**没有任何广告开关**
  （只有 theme / lang / vmode / intro / eparams / customIO / localsave / autosave / showtools /
  menus / panels / phrases / topt / tmnu / icons / plugins）。self-hosted 要 $500–2000/月。
- **实测**（`output/spike/probe_photopea_ads.py`，看 DOM 引用的外部域名）：
  - 裸 `/` → 返回的是 **16.8KB 的营销落地页**（67 个 `hreflang`、文案「Unlock your creativity…」），
    0 个 iframe、**0 个广告域名**。注意：带 Chrome UA 用 urllib 取也是这个（不是按 UA 伪装）；无 UA 直接 403。
  - `#<config>` → 真的**启动了编辑器**（有 toolbar / canvas），同时拉进 **40 个 iframe、33 个外链脚本**，
    含 `securepubads.g.doubleclick.net/tag/js/gpt.js?network-code=8095840`、prebid、pubmatic、
    criteo、360yield、4dex、id5、hadronid、confiant、Google Funding Choices。
- 结论：**hash 不是去广告开关，它是「进编辑器」的入口**。老板感觉「带 hash 更干净」的真实原因，
  多半是带 files 打开会**跳过落地/介绍页**（那页才是满屏彩色按钮和品牌推广的地方）。
  ⚠️ 无头环境对第三方广告脚本不友好，落地页那 0 个广告域名**不能**当作「落地页本来就没广告」的证据。

### AR.1d 🚨 裸 `photopea.com/` 是落地页，不是编辑器（2026-10-10 实测）
老板要求「把所有 `https://www.photopea.com` 换成 `https://www.photopea.com/#STRING`」。查完发现
**这个方向本身是对的，但理由不是去广告，而是裸地址压根不是编辑器**：

| 地址 | DOM | iframe | 结论 |
|---|---|---|---|
| `https://www.photopea.com/` | 16.7 KB | 0 | 🟡 营销落地页（`Unlock your creativity…`、67 个 hreflang） |
| `https://www.photopea.com/#`（空 hash） | 240 KB | 39 | ✅ 编辑器启动 |
| `https://www.photopea.com/#{}` | 243 KB | 40 | ✅ 编辑器启动 |
| `https://www.photopea.com/#<files>` | 245 KB | 40 | ✅ 编辑器启动 |

⚠️ `/` 与 `/#` 发给服务器的是同一个请求（hash 不发给服务器），差别只在客户端 JS ——
**但两次独立实测都复现了 `/` = 落地页、`/#` = 编辑器**，所以「有没有 `#`」确实是个真开关。
实测脚本 `output/spike/probe_photopea_boot.py`（⚠️ 判据别只看 `toolbar` 字样：没有文档打开时
工具栏不渲染，会误判成落地页；要看 DOM 体积 + iframe 数 + 落地页文案）。

**已落地的改动**：`static/js/smart-canvas.js` 里两处 `Photopea.createEmbed` **都带 config** ——
新增 `SPLIT_LAYERS_PEA_FALLBACK_CONFIG = {"environment":{"intro":false}}`，
兜底不再退到「不带 config」（那等于把编辑器退成落地页）。
⚠️ `static/vendor/js/photopea.min.js` 是 jsDelivr 上游镜像，**不要就地改**；要换默认地址从调用侧传 config。
静态守卫已加：`"Photopea.createEmbed(host)" not in js`（防漏网）。

### AR.1e 新标签页的 STRING 与内嵌编辑器共用一份 environment（2026-10-10）
老板：「点击在线 PS 后，后台应该先启动 `#STRING`，再将图层导入进 `#STRING`，
最后给到用户的才是带 `#STRING` 的版本」。
- **事实**：那三步本来就已经成立（内嵌编辑器用 `SPLIT_LAYERS_PEA_CONFIG` 启动 = `#STRING`；
  图层在它里面建文档导出 PSD；新标签页地址也是 `#STRING`）。老板看到的
  `https://www.photopea.com/#%7B%22files%22%3A...%7D` **就是** `#STRING` 形式 ——
  `#` 之前永远是域名（改不了），STRING 在 `#` 之后，浏览器把 hash 显示得很淡所以容易被忽略。
- **仍然做了的对齐**：新标签页原来只带 `{files:[...]}`，等于让 Photopea 用**默认**环境
  （语言靠自动探测、介绍面板开着）；现在改成同时带 `environment`，且 environment
  **复用后台那一份** —— 抽出唯一来源 `const SPLIT_LAYERS_PEA_ENV = {lang:'zh', intro:false, vmode:0}`，
  `SPLIT_LAYERS_PEA_CONFIG = JSON.stringify({environment: SPLIT_LAYERS_PEA_ENV})`，
  `splitLayersPhotopeaUrl()` 用 `{environment: SPLIT_LAYERS_PEA_ENV, files:[fileUrl]}`。
- ✅ **实测加 `environment` 不会让 `files` 失效**（`output/spike/probe_photopea_fetch_env.py`：
  旧形式 `{files}` 与新形式 `{environment,files}` 都让 Photopea 来 fetch 了那个 PSD）。
  ⚠️ 以后动这个 hash 配置，**必须**用这个探针复核一次，别再靠「看着像对的」。
- 静态守卫：新标签页 URL 必须同时含 `environment: SPLIT_LAYERS_PEA_ENV` 与 `files: [fileUrl]`，
  且 `SPLIT_LAYERS_PEA_ENV` 出现 ≥3 次（防两份配置各写一份飘掉）。
- DOM 探针断言 +3：`peaUrlEnvLang='zh'` / `peaUrlEnvIntro=false` / `peaUrlEnvVmode=0`（共 **95 项**）。

### AR.1f 🚨🚨 `#STRING`（无效 hash）= 零广告的可用编辑器 —— 老板是对的（2026-10-10 实测）
**这一条推翻了 AR.1c 的结论，必须优先读。**
老板两轮前说的「`photopea.com/#STRING` 这版是无广告的」**完全正确**，之前我按官方文档
（"去广告要买 Premium/Distributor"）否掉了他，是错的。

实测（`output/spike/probe_photopea_ads_forms.py`，统计 DOM 里的外部广告域名）：
| hash | DOM | iframe | 广告域名 |
|---|---|---|---|
| `#STRING`（JSON 非法） | 57–83 KB | **0** | **0** ✅ |
| `#`（空） | 241 KB | 40 | 39 |
| `#{}` | 240 KB | 39 | 38 |
| `#{"environment":{…}}` | 241 KB | 39 | 39 |
| `#{"environment":{…},"files":[…]}`（当时的线上形式） | 245 KB | 41 | 40 |

`probe_photopea_string_state.py` 进一步确认 `#STRING` 那版**是真编辑器**：加载了
`code/pp/pp*.js` + `code/dbs/DBS*.js` + `code/ext/ext*.js`（Photopea 主程序），
有 toolbar / canvas，而广告脚本**一个都没注入**。
⚠️ 别被「落地页文案」误导：`Unlock your creativity…` 那段是**嵌在 app 页面里的**，
两种状态下 DOM 里都有，不能当「没启动完」的证据。

**推测机制**：Photopea 解析 hash 时对非法 JSON 抛异常，中断了同一个脚本里后续的广告初始化；
app 主程序在别的入口仍会加载，所以编辑器照常可用。（这也解释了为什么空 hash `#` 有广告 —— 空串是合法输入，不抛。）

### AR.1g ✅ 无效 hash 下 Live Messaging API 依然可用（2026-10-10 实测）
`output/spike/probe_photopea_api_on_string.py`：临时探针页分别用
`createEmbed(host, '{"environment":{"intro":false}}')`（对照）和 `createEmbed(host, 'STRING')`（实验），
再 `runScript('app.echoToOE("PONG")')`。两组都返回 `["PONG","done"]`。
→ **可以拿一个无广告的 Photopea 实例，再用 runScript 把图层灌进去**（正是老板描述的流程）。

协议（读 `static/vendor/js/photopea.min.js` 得到，全文只有 2KB）：
`contentWindow.postMessage(script, "*")`；监听 `message`，`ev.source === contentWindow` 就收，
收到 `"done"` 结束。**只认 contentWindow，不要求是 parent** —— 所以 `window.open()` 返回的
窗口引用理论上也能当 contentWindow 用（见 AR.1h）。

### AR.1h 🚨 新标签页**不能**远程灌图层（Photopea 只认父窗口）（2026-10-10 实测）
想「新标签页开 `#STRING`，再从我们页面 postMessage 把图层推进去」——**走不通**。
- `output/spike/probe_photopea_tab_api.py`：`window.open('…/#STRING')` 拿到窗口引用，
  按 photopea.min.js 的协议反复 `win.postMessage('app.echoToOE("PONG");','*')` 14 次，
  **一条回包都没有**（`replies=0`）。
- ⚠️ 先排除了「无头不跑弹窗」这个干扰项：`output/spike/probe_popup_in_headless.py`
  开同源弹窗、子页写 `document.title='CHILD_OK'`、父页 4s 后读回 —— **读到了**，
  说明无头环境弹窗能跑，所以上面那个失败是**真的**。
- 结论：Photopea 的消息处理只接受 `window.parent` 发来的消息；`window.open` 出来的
  顶层标签页里 `window.parent === window`，opener 不在其列 → 消息被忽略。
- 推论：**「地址栏是 photopea.com」+「无广告」+「带全部图层」三者不可能同时满足**。
  要无广告又带图层，只能让用户停留在**我们自己托管的页面**里（内嵌 `createEmbed(host,'STRING')`，
  见 AR.1g —— 那条路已验证可用）。
- 还试过一条「两全」的路：hash 里直接放**裸 URL**（对 JSON.parse 非法 → 应同样跳过广告，
  而很多在线编辑器支持 `#<url>`）→ `output/spike/probe_photopea_raw_hash.py`：
  `#http://127.0.0.1:P/x.psd`（编码与不编码都试了）**0 广告、但也不会去拉那个文件**
  （日志服务器 0 命中）；对照组 `#{"files":[…]}` 拉了 1 次、带 39 个广告域名。
  → Photopea **只认 JSON 里的 `files`**，裸 URL 不会被当成待打开文件。此路不通。

### AR.2 🚨 为什么必须先把 PSD 落到服务端
Photopea 只吃「**它自己按 URL fetch 到的**文件」（官方 API 的 `files` 参数）：
- `blob:` 地址绑在当前页面的源上 → 新开的 photopea.com 取不到；
- `data:` 地址受浏览器 URL 长度限制（Chrome 约 2MB）→ 分层 PSD 轻松超；
- 所以只能给一个 http 地址。本机 `/assets` 实测返回 `Access-Control-Allow-Origin: *`
  （`main.py` 的 `CORSMiddleware(allow_origins=["*"])`），正是 photopea.com/api 文档点名要求的头。

### AR.3 🚨 走 multipart `/api/ai/upload`，不要走 `/api/ai/upload-base64`
`main.py` 的 `_local_upload_kind_ext()` 对 `.psd` 返回 `(None, ".psd")`，而
`upload_ai_base64` 在 `kind is None` 时**强制**回落成 `("image", ".png")`
→ PSD 字节顶着 `.png` 的名字，有被 Photopea 按 PNG 解析的风险。
multipart 那条对 `application/octet-stream` + `.psd` 会原样保留扩展名（落成 `ai_ref_*.psd`）。
实测：上传 → 取回，`Content-Type` 与魔数 `8BPS` 都完好。

### AR.4 🚨 必须先同步开窗、再 await
生成 PSD + 上传要好几秒；等 await 回来再 `window.open` 已经出了用户手势窗口，
会被浏览器当弹窗拦掉。所以顺序是：
`window.open('', '_blank')` **同步**开 → 往新窗口写一个「正在准备 Photopea…」占位页 →
全部准备好后 `win.location.href = target`。失败时 `win?.close()`，别把 about:blank 留在用户面前。
⚠️ 别加 `'noopener'`：加了 `window.open` 直接返回 null，就判断不出「被拦截」了。

### AR.5 ⚠️ 混合内容这条前提
Photopea 是 https，取 `http://127.0.0.1/...` 靠的是 Chromium 把 localhost / 127.0.0.1
当可信来源（potentially trustworthy origin），因此不算混合内容。
**画布如果用局域网 IP 打开，这个地址会被混合内容策略挡掉** ——
那里表现为 Photopea 自己报「打不开」，不是静默失败。

### AR.6 验证现状
`output/spike/verify_split_layers_dom.py` 覆盖到：入口的存在/可见/enabled/布局（全局只出现一次）、
busy 期间一起禁用、URL 构造与解码往返、`#` 不残留裸井号、**`#` 后不许有斜杠**，
以及**真跑一次 `/api/ai/upload`** 确认落盘扩展名是 `.psd`、取回魔数是 `8BPS`。
✅ **「Photopea 会不会真的加载文件」已实测**（`output/spike/probe_photopea_fetch.py`，见 AR.1b），
用的是「它有没有来 fetch PSD」这个观测点，不依赖页面内脚本。
⚠️ 仍**没有**自动化验证「真实会话里图层树长对了」——那需要联网 + 真实第三方会话。

## AS. 拆分图层：记录留存（误关弹窗后重开回到上次结果）—— 2026-10-10

### AS.1 需求
老板：「新增记录留存功能，防止出现手误跳出分层窗口再次打开只能重新分层的问题」。
auto 模式一次要打几十次上游模型，重拆是实打实的钱，不能逼用户重来一次。

### AS.2 🚨 为什么存 localStorage 而不是节点字段
画布 JSON 是**全量替换 + 无回收站 + 无历史版本**的高危数据（见 REFERENCE I），
一个纯前端的「上次结果缓存」没有理由长在它上面。
- key = `slRecords`，按 `节点id::图片下标` 索引，最多留 12 条（超出按 `at` 淘汰最旧）。
- 代价：换浏览器 / 清缓存就没了 —— 但本功能要解决的场景（手误关窗后重开）本来就在本机。

### AS.3 🚨 三条不能省的规则
1. **只有 `ready && layers.length` 才写**（`splitLayersSaveRecord` 开头就 return）。
   否则「重拆进行中 / 重拆失败」的中间态会覆盖掉上一次的好结果 —— 而那正好是最需要它的时刻。
2. **`source` 校验**：`rec.source !== 当前图 url` 就作废。节点上换了图时下标可能指到另一张，
   光比下标会把别的图的结果贴过来。
3. **存两处**：`splitLayersApplyResult` 末尾（拆完立刻存，防刷新）+ `closeSplitLayersEditor` 开头
   （存用户关窗那一刻的最终样子，含关窗前的排序 / 显隐 / 变换 / 文字改动）。
   ⚠️ close 里这一句**必须排在清空 state 之前** —— 下面几行就把 `layers` / `ready` 全清了。

### AS.4 打开入口的行为变了
`openSplitLayersEditor`：先 `splitLayersReadRecord(nodeId, index, item.url)`，
**有记录就直接 `splitLayersRestoreRecord(record)` 并 return** —— 不再弹预检面板。
没有记录才走原来的 `splitLayersOpenPrep()`。想重拆点标题栏「重新拆分」，那条路径一点没动。
恢复时会顺手 `splitLayersWriteTarget(rec.targetLayers)`，让预检面板的下拉显示这次记录用的层数。

### AS.5 「在线 PS」入口去重
老板当天另反馈「左侧栏重复了一个在线 PS」→ 图层栏底部那个 `#splitLayersOnlinePsSideBtn` 已删，
只留标题栏 `#splitLayersOnlinePsBtn`（紧邻「导出分层 PSD」）。
`.split-layers-side-foot` 保留列向 flex（只有一个按钮时等价单行），底部位置留给「铺到画布」独占。

### AS.6 验证
`output/spike/verify_split_layers_dom.py` 第 10 节（真实 DOM）覆盖：
存 → 读 → 源图变了作废 → 失败态不覆盖好结果 → 恢复后列表 / 画板 / 选择 / 状态栏一致 →
**集成**：`closeSplitLayersEditor()` 后再 `openSplitLayersEditor()` 直接恢复且 overlay 没有 `.prep`；
无记录的节点仍走预检面板。
第 9 节改为断言「在线 PS 全局只出现一次、底部那个不存在、foot 里只剩 1 个按钮」。

### AR.1i ✅ 落地：自托管查看器 `static/photopea-viewer.html`（2026-10-10 老板拍板「去掉广告」）
AR.1h 证明三者不可兼得，老板选定「**去掉广告**」。实现：
- 新文件 `static/photopea-viewer.html`（约 150 行，无外部依赖，只引 `vendor/js/photopea.min.js`）。
  内嵌 `Photopea.createEmbed(stage, 'STRING')` 拿**无广告**实例，再用 `runScript('app.open(...)')`
  灌 PSD；`app.open` 是异步的 → 轮询 `app.echoToOE(app.documents.length)` 直到 >0 才隐藏 `#boot`。
- 🚨 **`createEmbed` 的第二个参数只能传 `'STRING'`**（字面量）。传任何**合法 JSON**（含 `{"environment":…}`
  或 `{"files":…}`）广告都会回来。守卫：`check_split_static.py` 用
  `re.findall(r"createEmbed\(stage,([^)]*)\)", viewer)` 逐处要求 `== "'STRING'"`。
  ⚠️ 别写 `[^'"]` 那种字符类 —— 前面的 `\s*` 会回溯把空格让给它，永远匹配不上（踩过）。
- 参数：`?file=<encodeURIComponent(PSD 绝对地址)>`（必填）、`?direct=<photopea.com 兜底直链>`。
  载入失败（无 file / 无 Photopea / 超时 / 0 文档）→ 在 `#boot` 里给一条 `direct` 链接（有广告但一定能用）。
- `smart-canvas.js`：新增 `splitLayersViewerUrl(fileUrl)` → `/static/photopea-viewer.html?file=…&direct=…`；
  `splitLayersPhotopeaUrl` **降级为兜底直链**（别删，`direct` 的 URL 构造唯一来源就在它）；
  `splitLayersOpenOnlinePs` 末尾改成 `win.location.href = splitLayersViewerUrl(url)`。
- ⚠️ **代价**：地址栏变成我们服务的地址（不再是 photopea.com）。这是老板知情后选的。
- 验证：`output/spike/verify_photopea_viewer.py` → `VERIFY_RESULT=OK`（iframe src=`…/#STRING`、
  `#boot` 已 `display:none`、无兜底链接）；`verify_split_layers_dom.py` 新增 `viewerUrlIsViewer` /
  `viewerUrlFileRoundTrip` / `viewerUrlDirectIsPea`（**98 项**全过）。
  ⚠️ 该探针在无头环境**偶发抖动**：2026-10-12 一次 FAIL(2)（`#boot` 仍 flex、出兜底链接），
  同参数复跑即回 OK。**失败先复跑再下结论**，别当成回归去改 viewer。

### AR.1j 🚨🚨 文字层**绝不**在 Photopea 里建成 TEXT 层（2026-10-12，三次报「位置不对」后根治）

老板连报 4 次（`在线PS中的文字层位置发生了变化` → `位置仍然没有对齐，文字都在画布外了` →
`在线PS运行时会卡在这一步` → 附截图 `文字层在Photopea中的问题还是很明显的`），
按 TEXT 层思路修过三轮（bounds 读取时机 / `.n` / `textItem.position`）全不达标，
最后用探针定位到**两个硬根因**，彻底放弃 TEXT 层：

① **只要读文字层的 `layer.bounds`，Photopea 主线程直接卡死**（连 `ping` 都不回）。
   取证 `output/spike/probe_pea_text_pos3.py`：复现线上属性顺序后第一个动作探 bounds
   → `A_shape = __TIMEOUT__`、后续全超时。线上症状正是「正在重建图层 3/19」永远停住。
   逐属性二分 `output/spike/probe_pea_attr_bisect.py`（S0..S9：contents / size / font /
   justification / name / position / tracking / color / 完整顺序）**逐一插 ping 全通**
   → 十个属性赋值都没问题，**唯一毒药就是读 bounds**。
② `textItem.position` 只是「**第一行基线起点**」，与画板「墨迹盒左上角贴盒」口径差一截；
   且编辑态 `rotate/scale/sx/sy` 压根没搬进 Photopea。

**根治**：`splitLayersBuildDocument()` 里文字层（像素态 / 编辑态）**一律走
`splitLayersInjectImage(pea, layer)`** —— 复用 `splitLayersLayerDataUri()` →
`splitLayersCompositeTo()` 的同一套口径（墨迹盒拟合 + 编辑态变换），把该层合成一张
**整幅画布**的透明 PNG 灌进去。**画板上什么样，Photopea 里就什么样**。
代价：Photopea 里不能改字（要改回画板）。

**已删除整条旧路径**：`SPLIT_LAYERS_PS_FONTS`（CSS 字体栈→PS 字体名映射表）、
`splitLayersPsFont()`、`splitLayersPeaRun()`、`splitLayersInjectText()`（原约 70 行），
`static/js/smart-canvas.js` 留了面包屑注释说明为什么删、**别加回来**。

**验收（真 Photopea，非 mock）**：`output/spike/probe_pea_pixel_text.py` —— 单文档多图层
（与 `splitLayersBuildDocument` 同构：2 文字层 + 1 图片层），逐层 isolate 后导出量**墨迹包围盒**，
与页面侧同一张 canvas 的墨迹对比 → **`VERIFY_RESULT=OK`，maxDiff = 0**：
- `L_text_b`（旋转 15° + 等比 1.2）：pea `[188,82,448,198]` == self `[188,82,448,198]`
- `L_text_d`（两行文字）：pea `[60,257,379,350]` == self `[60,257,379,350]`
- 无变换对照：`A_ink == A_selfInk == [117,80,312,130]`，`dx = dy = 0`

**回归**：`check_split_static.py` **170 项** ALL PASSED（第 12c 段重写为 5 条**永久性负向守卫**：
不许再有字体映射表 / `splitLayersInjectText` / 给 Photopea 脚本设 `textItem` / 读 `artLayers[0].bounds`；
⚠️ 负向断言必须看**剥注释后的代码视图** `js_code`，否则被面包屑注释误伤 —— 踩过两次）；
`verify_split_pea.js`（Node harness）**46/46**；`verify_split_layers_dom.py` **98 项**；
`verify_photopea_viewer.py` **OK**。
**量文字落点必须用导出像素的墨迹包围盒**，不能信 `document.title` 或页面内脚本自报。

### AR.1k 🚨 identity 直通必须排除编辑态文字层（2026-10-12 老板「PS 中文字层颜色/位置/字体粗细没还原」）

**根因**：`splitLayersLayerDataUri()` 有个省重编码的「优化」——
`splitLayersIsIdentity(layer) && layer.url` 时**直接返回原图 url**，跳过合成。
对普通图片层没问题（原图就是画板上的样子），但**编辑态文字层的 `layer.url` 是后端从原图
裁的旧像素**（只给「还原像素」按钮用），而画板上渲染的 `<span>` 是拿后端估出的
字体/斜体/字距/颜色**重画**的 —— **两者根本不是同一张图**。
判 identity（未拖动过）就直通 ⇒ Photopea 里永远是原图那版字 ⇒ 老板看到的全错。

**修复**：直通只认「**渲染源就是该 url**」的两类：
```js
const rendersOwnUrl = layer.kind !== 'text' || splitLayersIsPixelText(layer);
if(rendersOwnUrl && splitLayersIsIdentity(layer) && layer.url){ /* 直通 */ }
```
编辑态文字层（默认态）一律走 `splitLayersCompositeTo` 合成。

**三套守卫（都做过反证：退回修复后全部 FAIL，证明不是空断言）**：
| 检查 | 新增项 | 退回时会报 |
|---|---|---|
| `verify_split_layers_dom.py`（真无头 Edge） | `uriEditIsNotOldPixel` / `uriEditIsComposite` / `uriPixelIsOwnUrl` / `uriImageIsOwnUrl` / `uriPixelMovedIsComposite` | 1 项 FAIL |
| `check_split_static.py`（负向守卫） | 2 条（`rendersOwnUrl` 必须带 `layer.kind !== 'text' \|\| splitLayersIsPixelText(layer)`） | 2 项 FAIL |
| `verify_split_pea.js`（Node harness） | 「编辑态文字层（identity + 有 url）不直通原图」+「不许出现原图旧像素」+ 普通图片层仍直通对照 | 2 项 FAIL |

⚠️ `splitLayersIsIdentity` 在 `splitLayersLayerDataUri` 里**早于** `splitLayersEnsureEditable`
执行 ⇒ 探针里造层必须**显式写 `edit` + `editInit` + `box`**，不能指望 `EnsureEditable` 补
（它只在 `!layer.edit` 时才补 `box`，预置了 edit 就跳过，`CompositeTo` 读 `box.x` 直接崩）。

### AR.1l 文字层「参数摘要」上列表（2026-10-12 老板：「拆分图层中的参数，颜色、位置、字体粗细…」）

老板要在**图层列表**就能看到文字层的排版参数，不必每选一层去右侧工具栏核对。
实现：`splitLayersTextParamsHtml(layer)`（只读，不改任何 layer 字段）渲染在 `.sl-kind` 之后，
**只在 `kind === 'text'` 时输出**。

- 🚨 **必须分两行**。实测侧栏 226px 里 grip/eye/thumb/dot 占掉约 100px，meta 只剩 ~120px，
  一行塞 7 个参数必被省略号吃掉 = 等于没做。现为：
  - 第 1 行：`■ #FF00AA · 32px · B · 斜`（色块 + 字号 + 粗细 + 斜体）
  - 第 2 行：`+4 · -12° · (120,60)`（字距 / 旋转 / 位置；**默认值不输出**，免每行拖一串 0）
- 侧栏同时 **226 → 268px**（`.split-layers-sidebar`）。
- 完整文案（含字体名、bbox 宽高）挂 `title` tooltip，见 `splitLayersTextParamsTip()`。
- ⚠️ **行高是内容撑的**，拖拽落点用 `getBoundingClientRect` **实测行高**、不依赖硬编码常量
  ⇒ 加行不会破坏拖拽手感（这条别再改成硬编码行高）。
- i18n：`smart.splitLayersParam{Bold,Regular,Italic,Color,Size,Track,Rot,Pos}`（中英各 8 条）。
- 验证：`verify_split_layers_dom.py` 新增 16 项（**119 项**全过），含
  `paramsTwoLines` / `paramsNotClipped`（`scrollWidth <= clientWidth + 2`）/ `paramsHasTip` /
  `paramsNotOnImage`；`paramsChipColor` 实测 `rgb(255,0,170)`。


## AT. 3D 预览节点 = 双引擎（`hf` 真模型 / `llm` 白模）

> 来源：2026-10-12 会话。日志细节见 `.workbuddy-ai/memory/2026-10-12.md` §8–§15。

### AT.1 引擎分派
- `engine3d: 'hf' | 'llm'`，默认 `'hf'`；`smart3DEngineOf(node)` 读节点、缺省回落 `'hf'`。
- `hf` 产物 → `model3dUrl` / `model3dStlUrl` / `model3dVideoUrl` / `model3dMeta`；
  `llm` 产物 → `scene3d`（原白模 JSON）。**两套并存，切引擎不丢**。
- 🚨 `dispose3DViewer` 只回收 viewer，**必须保留 `smart3DModelState`**（Map: nodeId → {status,url,error,group,frame}），
  否则每次重挂都会重新下载 GLB。
- `sync3DViewers` 判「该不该建 viewer」用 `smart3DHasContent(node)`（`model3dUrl` 或 `scene3d` 任一有）。

### AT.2 GLB 归一化（实测值，探针取证）
- `load3DModelIntoViewer(viewer, node, url)`：GLTFLoader → `Box3` → 居中 XZ → 缩放到 **2.4** 单位 → 底面贴 `y=0`。
- 探针 `verify_3d_hf.py` 取证：`boxSize=[2.4,2.4,2.4]`、`boxMinY=0`、`boxCenterXZ=[0,0]`、`scaleIsOneTwo`、`sitsOnGround`、`centered`、`meshCastShadow`。
- 光照抽出到 `build3DStudioLights(viewer, group)`，**`viewer.lights` 去重防叠加**：
  `lightsAfterFirst=3`、`lightsAfterRepeat=3`（重复挂载不涨）。
- vendor 本地化：`static/vendor/js/three-gltf-loader.module.js`（import 已改写为相对路径）
  + `three-buffer-geometry-utils.module.js`（GLTFLoader 的传递依赖）。

### AT.3 HF Space 客户端（`hf_3dai_client.py`）
- host `https://broyang-3dai.hf.space`；Gradio **6.27.0**。
- 🚨 `/gradio_api/call/<api_name>` 的 body **必须** `json.dumps({"data": [...]})`；裸数组 → **422**。
- 上传：`POST /gradio_api/upload`（multipart，字段名 `files`）→ 回 `["/tmp/gradio/<hash>/<name>"]`。
- Gallery 元素格式：`{"image": {"path": "<server path>", "meta": {"_type": "gradio.FileData"}}, "caption": null}`。
- 🚨 **`texture`（dropdown id=9）必须是 `int`**：发 `'1024'` 被拒
  `Value: 1024 is not in the list of choices: [512, 1024, 1536, 2048, 4096]`；发 `1024` 通过。
  ⇒ 用 `texture_size_int(value)`，**别用** `normalize_texture_size()` 的字符串结果直接发。
- 调用链 `_2`：`generate_and_extract_2` → `enable_model_exports_2` → `extract_model`
  → `materialize_export_payload` → `finish_glb_export`（+ `generate_stl_download`）。
- 🚨🚨 **参数/返回个数一律以 `/gradio_api/info` 的 `named_endpoints` 为准**
  （`gr.State` 参数被 Gradio 自动剔除，`parameters` 的长度就是该传的个数）。
  实测（2026-10-12）：`generate_and_extract_2` 7参/1返、`enable_model_exports_2` **0参**/2返、
  `extract_model` **2参**(`mesh_simplify`,`texture_size`)/1返、
  `materialize_export_payload` **0参**/1返、`finish_glb_export` **1参**(`status_text`)/2返、
  `generate_stl_download` 0参/1返。**不要凭 UI 组件编号猜。**
- 🚨🚨 **GLB 下载地址的形态**（事故根因，「上游没有返回 GLB 下载地址」的来源）：
  `DownloadButton.postprocess()` 源码只返回 `FileData(path=..., orig_name=...)`，**没有 `url`**。
  前端自己拼 `url: ${host}${api_prefix}/file=${path.split('/').map(encodeURIComponent).join('/')}`。
  ⇒ 解析必须同时认 `FileData.path`，并用 **`_find_file_url()`** 拼
  `{host}/gradio_api/file=<分段 encoded path>`。**只搜 `http…glb` 字面量必然落空。**
  路由依据：`@router.get("/file={path_or_url:path}")`，非 http 走 `file_fetch`；
  不存在的路径回 403 `File not allowed`（白名单校验，属正常）。
  单测：`output/spike/verify_hf3d_url.py`（10 项，含反向验证）。
- 参数实测：seed=52、`ss_guidance_strength`=7.5、`ss_sampling_steps`=12、
  `slat_guidance_strength`=3.0、`slat_sampling_steps`=12、`texture`=int。
- **额度用尽特征**：1.4~1.5s 内返回 `{"error": "Generation is temporarily unavailable. Please try again later."}`
  → `_is_allowance_error()` → 抛 `HF3DAIQuotaExhausted`（`code="hf_quota_exhausted"`）。
- `parse_token(raw)` 会清洗 `export HF_TOKEN=xxx` / 引号 / 空白等粘贴形态。
- 下载器：模块级 `download_to_file(url, dest_path, timeout)`，流式落盘（GLB / STL / MP4）。

### AT.4 后端端点（`main.py`）
- 🚨 **随包嵌入式 Python 的 `sys.path` 不含脚本目录**（只有 `python310.zip` / `python` / `lib/site-packages`）
  ⇒ 顶部必须：
  ```python
  _HERE = os.path.dirname(os.path.abspath(__file__))
  if _HERE not in sys.path: sys.path.insert(0, _HERE)
  ```
  否则 `import hf_3dai_client` 直接 `ModuleNotFoundError`（`run.bat` 拉起同样中招）。
- `POST /api/3d-tasks` → 建任务（`HF3D_TASK_PREFIX = "hf3d_"`）；`GET /api/3d-tasks/{task_id}` → 轮询。
  `HF3DTaskRequest`：`image_url / provider_id / model / texture_size / hf_token / image_provider_id / image_model`。
- 三视图生成复用 `split_call_image_model`，**单张失败跳过不整单失败**；
  `HF3D_VIEW_PROMPTS = {front, side, back}` + `HF3D_VIEW_SYSTEM_PROMPT`（单物体 / 纯白底 / 正交 / 同相机高度）。
- 阶段文案 `HF3D_PHASE_LABELS`：prepare / views / upload / generate / export / extract / materialize / finish / download / done；
  `hf3d_advice(phase, detail)` 给分阶段建议。
- 产物落 `assets/output/3d/`（`hf3d_asset_path()` / `hf3d_asset_url()`）。
- 任务结果 `payload_out`：`source / canvas / model_url / stl_url / video_url / texture_size / size / views / view_count / provider="hf-3dai" / engine="trellis"`。
- 错误 `error_detail`：`phase / phase_label / message / advice / code / quota_exhausted`。
- **Token 端点**：
  - `GET /api/3d-token` → **只回** `{has_token, hint}`（掩码 `hf_T…xxxx`），**绝不回明文**。
  - `POST /api/3d-token` → `HF3DTokenRequest(token, remember)`；校验 `hf_` 前缀；`remember=true` 才落盘。
  - 落盘位置 `.secretsignore.hf3d.json`（已进 `.gitignore` 与 `.secretsignore`，且
    `tools/release.py` 的 `DENY_EXACT` 排除，**不入发布包**）。

### AT.5 前端要点（`static/js/smart-canvas.js`）
- 引擎常量：`SMART_3D_ENGINE_HF='hf'` / `SMART_3D_ENGINE_LLM='llm'`；
  纹理 `SMART_3D_TEXTURE_SIZES=['512','1024','1536','2048','4096']`，默认 `'1024'`，
  localStorage key `smart3d.textureSize`（`SMART_3D_TEXTURE_KEY`）。
- `smart3DModelControlsHtml(node)` 按引擎**分派**：hf → `smart3DImageControlsHtml`（图像通道 / 模型 / 纹理）；
  llm → 原对话通道下拉。`smart3DEngineSwitchHtml(node)` 出两枚胶囊（`data-3d-engine`）。
- `run3DNode` 分派 → `run3DNodeHf` / `run3DNodeLlm`。
- 轮询：`pollHf3DTask` / `waitFor3DModel(nodeId, timeout)` / `update3DPhaseHint` / `readErrorDetail(response)`。
- **额度弹窗**：`open3DQuotaModal(nodeId)` / `close3DQuotaModal()` /
  `submit3DQuotaToken()`（校验 `hf_` 前缀 → POST → 重跑）/ `fallback3DToLlm()`（切 `engine3d='llm'` → 重跑）。
  `smart3DQuotaBindOnce()` 绑定：遮罩关闭、两按钮、回车提交。
- 🚨 **哨兵**：`load3DSavedToken()` 在后端已存 token 时设 `smart3DSessionToken = '__stored__'`，
  但 `smart3DToken()` **必须**把 `'__stored__'` 转成 `''`（发空串让后端用自己那份），否则哨兵被当 token 发出去。
- 🚨 刷新图标函数是 **`refreshIcons()`**（`smart-canvas.js:727`），**没有** `renderLucideIcons()`。
- HF Token 创建页链接：`https://huggingface.co/settings/tokens/new?tokenType=read`。

### AT.6 i18n / 样式 / 验证
- i18n 新增 32 条 `smart.3d*`（`static/js/i18n/smart-canvas.js`）：`3dEngineHf/Llm`、`3dImageProvider/Model`、
  `3dTexture`、`3dDownloadGlb/Stl`、`3dWatchVideo`、`3dVideo`、`3dModelLoadFailed`、`3dTimeout`、
  `3dQuota*`（Title/Lead/OptionToken/TagBetter/TokenNote/GetToken/UseToken/Remember/OptionFallback/TagFast/
  FallbackNote/UseFallback）、`3dToken*`（Required/Invalid/Checking/Saved/Ready）、`3dFallbackOn`。
  总数 **1299 → 1331**。
- CSS（`static/css/smart-canvas.css`）：`.smart3d-engineswitch/-engine/.is-active`（窄节点只留图标）、
  `.smart3d-filebar/-file`、`.smart3d-texture`、`.smart3d-placeholder.is-loading`、
  `.smart3d-quota-modal/-window/-head/-x/-body/-lead/-card/-cardhead/-tag/-note/-link/-row/-input/-remember/-status`。
- HTML：`static/smart-canvas.html` 新增 `#smart3DQuotaModal`（在 `#splitLayersModal` 之后）。
- 验证脚本 `output/spike/verify_3d_hf.py`：复用 `verify_split_layers_dom.py` 四步骨架
  （复制 html → 注入 module 探针 → 无头 Edge `--dump-dom` → 删探针），
  探针**手写最小合法 GLB 立方体**（8 顶点 + 36 index，自拼 JSON/BIN chunk 头）验证归一化 → **43/43 全过**。
- ⚠️ 探针里 `agentGenProviders()` 若在配置加载前调用会返回 0，`smart3DImageControlsHtml` 会
  **正确地**渲染「请先配置生图模型」告警 ⇒ 断言要写成「与 provider 数量一致（`controlsMatchProviders`）」，
  不能硬断言「三个下拉一定存在」。
- `tools/release.py`：`ROOT_FILES` 加 `"hf_3dai_client.py"`；`DENY_EXACT` 加 `".secretsignore.hf3d.json"`。

### AT.7 外部限制（非代码问题）
- 本机出口 IP 在 HF ZeroGPU **匿名额度已耗尽**（连真实浏览器点按钮也报同样错）
  ⇒ 真机端到端会停在「额度用尽」，**这正是弹窗要覆盖的场景**：填 Token 或点回退即可继续。
- ⚠️ 换自建服务（如本地跑 TRELLIS）性能门槛待评估 —— 老板已要求先测普通笔记本（H3C Megabook）能否承受，
  扛不住就取消该方向；本方案（HF Space + 额度弹窗）不引入本地算力负担。


## AU. Space(broyang/3dai) 源码级调用契约 —— 2026-10-12 拿到 app.py 后确立
> 依据：`output/spike/space_src/app.py`（96KB，`https://huggingface.co/spaces/broyang/3dai/resolve/main/app.py`）
> + `output/spike/space_src/api_info.json`（`/gradio_api/info` 全量快照）。**改 3D 客户端前必读本节。**

### AU.1 🚨🚨 头号坑：`gr.State` 输入被 info 整体剔除，但调用必须传
`named_endpoints[*].parameters` **不列 `gr.State`**。只看 info 必定传错个数 —— 这是「上游报错」
反复出现的根因。权威对照表：

| api_name | info 参数 | 源码签名（权威） | **实际 data 数组** | info 返回 | 实际返回 |
|---|---|---|---|---|---|
| `generate_and_extract_2` | 7 | `(image, seed, ss_g, ss_s, slat_g, slat_s, texture_size, req, progress)` | 7（gallery 占 image 位） | 1 | **2** = `[video_path, state]` |
| `enable_model_exports_2` | 0 | `(state)` | **1** = `[state]` | 2 | 2 = `[stl_btn, texture_size_int]` |
| `extract_model` | 2 | `(state, mesh_simplify, texture_size, progress)` | **3** = `[state, 0.95, int]` | 1 | **2** = `[status_text, payload_dict]` |
| `materialize_export_payload` | 0 | `(payload, req)` | **1** = `[payload]` | 1 | **2** = `[gr.update, glb_path_abs]` |
| `finish_glb_export` | 1 | `(glb_path, state, status_text)` | **3** | 2 | 2 = `[gr.update(btn), gr.update(dl)]` |
| `generate_stl_download` | 0 | `(state, cached_stl_path=None)` | **2** | 1 | **2** = `[gr.update, stl_path]` |

行号：`materialize_export_payload` **621**、`generate_stl_download` **646**、
`enable_model_exports` **685**、`finish_glb_export` **698**、`extract_model` **1509**、
UI 接线 **2166–2277**、`generate_and_extract` **1372**。

### AU.2 GLB 路径的真实来源
- `materialize_export_payload` 内：`glb_path_abs = abspath(EXPORT_DIR/<uuid4hex>/DOWNLOAD_STEM.glb)`
  （**app.py:631**），返回 `(gr.update(value=glb_path_abs, visible=True), glb_path_abs)`。
- `finish_glb_export(glb_path, state, status_text)` **只做展示/兜底**：
  `failed = glb_path is None`，把 `glb_path` 塞进 Downloadbutton 的 `value`。
- ⇒ 取地址**首选 materialize 第 2 个返回**；finish 只是二次机会。

### AU.3 `extract_model` 第 2 个返回是 **payload dict**（不是句柄/数字）
`payload = {"glb_name": ..., "glb_b64": base64...}`（`build_export_payload` **592**）。
必须**原样**喂给 `materialize_export_payload`；塞 int 会在 `str(payload["glb_b64"])`（**632**）崩。

### AU.4 多视图通道（本需求的技术依据）
- `generate_and_extract_2` 的 `image` 位接受 **Gallery 列表**；`_prepare_generation_input`（**1166**）
  见 `list/tuple` ⇒ 走 `normalize_gallery_images` + `preprocess_images` + `_run_original_pipeline_multi`（**948**）。
- 硬约束：`MULTI_IMAGE_MIN_VIEWS = 2`、`MULTI_IMAGE_MAX_VIEWS = 6`（**228/229**），
  少于 2 张直接 `gr.Error`；且**要求 `TRELLIS_RUNTIME == "original"`**。
- ⇒ **这正是「连 ≥2 个上传节点就跳过三视图」的可行性依据**：把已连图当 gallery 直接发即可。

### AU.5 实现落点
- 客户端：`hf_3dai_client.py` `generate()`（按 AU.1 表逐项传参）。
- 后端：`main.py` `HF3DTaskRequest.view_urls` + `run_hf3d_task` 的 views 分支。
- 前端：`static/js/smart-canvas.js` 的 `smart3DConnectedViews()` / `run3DNodeHf()` /
  `smart3DImageControlsHtml()` / `smart3DBodyHtml()`。
- 验证：`output/spike/verify_hf3d_chain.py`（22 项参数形状）、
  `verify_hf3d_url.py`（10 项 URL）、`verify_3d_hf.py`（52 项 DOM）。

### AU.6 ⚠️ 探针造连线的必备前提
无头探针页**不带 `?id=`** ⇒ 模块级 `canvas` 是 **null**，而 `canvasUsesConnections` 初值仍为 `true`
⇒ `upstreamNodesForKinds` 会走 `node.inputNodeIds` 分支、读不到你 push 的 connection。
探针里必须**自己造** `canvas = {connections:[], nodes:nodes}` 再 push。

### AU.7 🚨 多视图收集必须**按图**、不能按节点取第一张（2026-10-12 §18 修正）
- 场景：**多图并组连接** = 多个上传节点并成一个 `smart-group`，**group 再连到 3D 节点**。
- 🚨 `inputNodesFor(3d)` 此时只回 **1 个 group 节点**；group 由 `outputImagesForNode`
  的 `smart-group` 分支（`smart-canvas.js:18857`）展平成多张图。
  老实现对每个 input 只取 `imageRefsOnly(...)[0]` ⇒ **`length===1`** ⇒ 误判单图 ⇒
  **退回三视图** ⇒ 报「上游没有返回 GLB 下载地址」（用户报的正是这条）。
- ✅ 正确写法：`inputNodesFor(node).forEach(input => imageRefsOnly(outputImagesForNode(input,...)).forEach(...))`
  —— 逐个上游节点**展平它全部图片**，去重后 `slice(0,6)`。
- `imageRefsOnly` 内部上限 `SMART_REFERENCE_IMAGE_MAX=20 > 6`，不截断。
- 徽标/空态/隐藏下拉全复用 `smart3DConnectedViews` ⇒ 改一处即全好。
- 🚨 探针造组 API 是 **`createSmartGroupNode(x,y,{})`**（不存在 `createGroupNode`）；
  成员存 `node.items:[id...]`，由 `smartGroupMembers()` 解析。
- `verify_3d_hf.py` 第 8 段 8 项断言（**59/59**）覆盖：group 展平 = 2、组内剩 1 回落三视图。

### AU.8 🚨 3D 上游类型白名单**必须含 `smart-group`**（2026-10-12 §19 修正）
- 症状：把「N 图片」分组（`smart-group`）拖线到 3D 节点，**松手就被拒、无提示**，
  3D 空态仍是「连接上传节点后点生成」⇒ 用户表述为「连接不上」。
- 根因（**两处，必须同时改**）：
  - `canAutoConnectDraggedNode()` ~14604：`smart-group` 分支原先只允许 `smart-image`/`smart-loop`。
  - `connectInputNode()` ~18655：`isSmart3DNode(to) && !isSmartImageNode(from)` → false。
- 🚨 **为什么像「能连但连不上」**：`port` 拖拽 hover（~22873）**只看方向 out→in、不看类型**
  ⇒ `port-in` 会高亮，松手时 `handlePortDrop` 才校验类型并**静默 discard**（无 toast）。
- 修法：
  ```js
  if(isSmart3DNode(to) && !isSmartImageNode(from) && !isSmartGroupNode(from)) return false;
  // 以及 smart-group 分支追加 `|| isSmart3DNode(targetNode)`
  ```
- **下游方向不动**：3D 只向下游接 `smart-image`（把实时截图喂给上传）。
- 分组图来源：`imagesForNode(group)` → `smartGroupImageRefs(group)`（~2024），
  **同时覆盖 `group.images`（直接拖入）与组内 smart-image 成员的图**，按位置排序。
- 识别技巧：「**N 图片**」这个摘要文案 = `smart-group`（`smart-canvas.js:8943`），
  不是上传节点的标题（多图上传节点标题是 `Group`/`smart.attachNodeMany`）。
- `verify_3d_hf.py` 第 8 段「4 图分组 → 3D」含 `groupConnectOk`（真实调用 `connectInputNode`
  断言返回 true）等 11 项，**62/62**。

### AU.9 🚨🚨 ZeroGPU 配额机制 —— 「生成失败」/「填了 Token 也没用」的真相（2026-10-12 §20）
> 依据：`output/spike/space_src/quota_fallback.py`（15.7KB，2026-10-12 从 Space 仓库下载）
> + 本机**真实调用实测**（`output/spike/diag_hf3d_live.py`）。

#### 错误文案的真正含义
- `quota_fallback.py` 常量：
  - `ALLOWANCE_ERROR = "Generation is temporarily unavailable. Please try again later."`
    ← **就是 ZeroGPU 配额被拒**（不是网络故障、不是 Space 崩了）
  - `CAPACITY_ERROR = "Too many generations are currently running..."`
  - `WAITING_STATUS = "Requesting generation capacity..."`
- `QUOTA_PATTERN = ^You have exceeded your (Pro |free )?ZeroGPU (quota|runs limit)`
  —— HF 平台的原始文案；`safe_message()` 会把含 `HF`/`Hugging Face`/`ZeroGPU` 的消息
  **替换成 `ALLOWANCE_ERROR`** ⇒ 所以看不到「quota」字样，别被误导。

#### 为什么网页端能成功、API 失败？—— **不是「API vs 网页」的差别**
- `defer_or_fail()` → `defer_pending_fallback()` → `is_eligible_embed(req)`：
  **只有 referer 来自 `EMBED_PARENTS` 白名单**（`app.skyebrowse.com` 等）**且**
  Space 配了 `LABS_FALLBACK_SIGNING_KEY` 时，才会进 `FallbackCoordinator` 排队；
  **否则一律 `raise gr.Error(ALLOWANCE_ERROR)`**。
  ⇒ 普通网页访问和 API 调用走的是**同一条失败路径**。
- 网页端能成功 = **登录了 HF**（走账号额度）。匿名额度**按出口 IP 限免**。
- 🚨 **实测**：本机匿名调用 **6 秒被拒**（`HF3DAIQuotaExhausted`）；
  换一个**明显无效的 token** 仍是**同一个额度错误、没有 401**
  ⇒ **配额检查发生在鉴权之前**，因此**无法用无效 token 区分** token 好坏。
- 🚨 结论：**换浏览器自动化也救不了** —— 不带登录态一样被拒；要的是**有效 Token**。

#### 客户端/前端的配合（已实现）
- 后端 `run_hf3d_task` 已正确透传：`error_detail = {phase, phase_label, message,
  advice, code:"hf_quota_exhausted", quota_exhausted:true}`（实测确认）。
- 前端 `pollHf3DTask` → `error.quotaExhausted` → `open3DQuotaModal()` 弹双选窗
  （填 Token / 回退 three.js）。`close3DQuotaModal()` **不改** `scene3dError`。
- ✅ 新增 `verifyHfToken(token)`：前端直连 `https://huggingface.co/api/whoami-v2` 校验
  （**CORS 实测允许**：HF 回显 Origin，`access-control-allow-headers: authorization`）。
  401/403 ⇒ 判为无效并**中止**，不再白跑一次生成。`null`（断网）不阻断。
  —— 起因：后端 `/api/3d-token` **只查 `hf_` 前缀**，过期 Token 也「接受」。
- ✅ 「记住这个 Token」改为**默认勾选**（`readSmart3DRememberPref`/`writeSmart3DRememberPref`，
  localStorage `smart3d.rememberToken`）；不勾则刷新即丢，用户会反复「我明明填过」。
- ✅ `create3DViewer` 失败时不再只写「生成失败」，改为 `生成失败：<真实原因>`
  （`load3DThree()` 的 import 失败也走这条）；`run3DNodeHf` 的兜底也带上 `error.phase`。
- ✅ 修 `smart3DImageControlsHtml` 的 `tr(...)` → **`trf(...)`**：
  `tr()` **不接受参数**，导致多视图徽标显示成 `多视图 · {n} 张已连接图`。

#### 诊断脚本
- `output/spike/diag_hf3d_live.py [token]` —— 真实跑一次 Space，打印 phase 与完整异常。
  不带参数即匿名。**必须清代理**（`env -u HTTP_PROXY ...`）。

### AU.10 浏览器自动化（CDP + 系统 Edge）—— 页面选择器表与实测结论（2026-10-12 §21）
> 动机：ZeroGPU 免费额度**按出口 IP / 登录账号**判定，且**配额检查先于鉴权**（见 AU.9）
> ⇒ 匿名 API 必被拒。改为**用浏览器直接操作页面**，复用浏览器登录态，
> 用户**不必填 Token、项目也不落盘 Token**。
> 🚨 **零新依赖**：`websockets` 项目自带；Edge 用系统已装
> `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`。

#### 启动方式
```
msedge.exe --headless=new --remote-debugging-port=<PORT>
            --user-data-dir=<持久 profile> --no-first-run --no-default-browser-check
            --disable-gpu --hide-scrollbars about:blank
```
- CDP 就绪判据：`GET http://127.0.0.1:<PORT>/json/version` 返回 200。
- 页面 ws：`GET /json/list` → `type=="page"` 的 `webSocketDebuggerUrl`。
- 🚨 **profile 必须持久化**（登录 cookie 在里面）→ 存 `data/hf-browser-profile/`。
- 🚨 结束要发 `Browser.close`（连 `/json/version` 的 **browser-level** ws），
  否则 headless Edge 残留、下次端口被占。
- ⚠️ 清理残留进程**只按命令行匹配 `*_edge_profile*`**，**绝不要按镜像名批量结束 msedge**
  （会杀掉用户自己开的 Edge）。在 Bash 里调 powershell.exe 会被安全策略拦 → 用 PowerShell 工具。

#### 页面结构（实测，Space = SkyeBrowse "Pocket 3D AI"）
| 元素 | 选择器 | 说明 |
|---|---|---|
| 两个 Tab | `button[role="tab"]` → `[0]`=Single Image、`[1]`=Multiple Images | 文案随浏览器语言变（实测出现过中文），**别用文案定位** |
| **单图上传** | `.gr-image-container input[type=file]` | `multiple=false`；对应源码 `elem_classes="gr-image-container"` |
| **多图上传** | `input[type=file][multiple]` | 切到 Multiple Images Tab 后**才渲染**（Gradio 懒渲染）；实测 `input[type=file]` 共 2 个，`multiple` 依次 `[false, true]` |
| 单图生成 | 按钮文案 `Regenerate` | |
| 多图生成 | 按钮文案 `Generate from Multiple Images` | |
| **主生成（GLB）** | 按钮文案 `Generate 3D Model` | 🚨 初始 `disabled=true`，**出预览后才启用**（≈ API 的 `enable_model_exports`） |
| GLB 下载 | `#glb-download-btn` | `gr.DownloadButton`，**初始不渲染**（`visible=False`），就绪后才出现 |
| GLB 状态 | `#glb-export-status` | `gr.Textbox` |
| STL 下载 | `#stl-download-btn` | |
| 额度/访问提示 | `#labs-access-notice` | `gr.HTML` |
| fallback 状态 | `#labs-fallback-status` | |
| 预览视频 | `video`（`.video-container` 内） | |

#### 🚨 上传的正确姿势（实测踩坑）
- 用 CDP `DOM.setFileInputFiles`（先 `DOM.enable` + `DOM.getDocument` + `DOM.querySelector` 取 nodeId）。
- ✅ **实测有效**：会真的 POST 到 `/gradio_api/upload?upload_id=...`（约 7s），
  缩略图随即出现，**Gradio 会立刻重建 DOM**（原 input 节点消失）。
- ⚠️ 判断上传成功**不能看原 input**（已被替换），要看：
  ① `performance.getEntriesByType('resource')` 里有没有 `/gradio_api/upload`；
  ② `.gr-image-container img` 数量。注意 `performance` 条目有延迟，检查前要留足时间。
- ⚠️ 上传后**必须重新 query** 元素（DOM 已重建）。

#### 待办（§21 只做到可行性验证）
- 尚未实现：点生成 → 等预览 → 点 `Generate 3D Model` → 等 `#glb-download-btn` → 取 GLB URL/下载。
- 尚未实现：限免耗尽时（页面出现 ALLOWANCE_ERROR 文案 / `#labs-access-notice`）
  → 用**同一个 profile 起可见窗口**打开 HF 登录页 → 用户登录 → 关窗 → 重试。
- 验证脚本：`output/spike/verify_space_browser.py`（**不点生成 ⇒ 不消耗额度**）。


## AV 混元 3D（3d.hunyuan.tencent.com）多视图上传 → 生成 → 资产 → 分享 全链路实测表（2026-10-12 §25）
> 探测脚本 `output/spike/probe_hunyuan3d_*.py`；结果 JSON 同目录。**已真实生成过一次**
> （消耗 1 次额度 ×2 计量）+ 拿到真实分享链接。目标页 `https://3d.hunyuan.tencent.com/creation`。

### AV.1 登录态（headless Edge + 持久 profile）
- profile：`output/spike/_hy3d_profile`；🚨 cookie 在 **`Default/Network/Cookies`**（新版 Edge 路径）。
- 必须 `Browser.close` 正常关窗才落盘；**提前杀进程 = 丢登录态**（实测丢过一次）。
- 起服务/跑探测必须清代理（`env -u HTTP_PROXY -u HTTPS_PROXY ...`），否则外网全 10061。

### AV.2 多图上传（8 视图卡片，每卡独立 file input）
| 步骤 | 选择器 / 判据 |
|---|---|
| 切多图 | radio 文案「多张图片」→ `.t-radio-button`；或直接点 `.hy-multiple-views-upload-v2` |
| 上传 | `.hy-upload-card--{top,left,left-front,front,right,right-front,back,bottom} input[type=file]`（`DOM.setFileInputFiles`） |
| 成功判据 | 卡片 class 含 **`isSuccess`** |
| 生成 | `.sideBarLeft-generateBtn`（立即生成）；模型 `model-version-select`；面数 `generation-type-select` |
| 🚨 front 必填 | Min2 Max8；「正图」带 `*` |

### AV.3 资产 / 状态 API（均需登录 cookie）
| 用途 | 方法与 body |
|---|---|
| 资产列表 | `POST /api/3d/creations/list` `{"limit":20,"offset":N,"sceneTypeList":[]}` — 🚨 **limit ≤20**（50 回空） |
| 进行中计数 | `POST /api/3d/creations/count` `{"statusList":["wait","processing"]}` |
| 额度 | `POST /api/3d/quotainfo` `{"sceneType":"3dCreations"}` → `remainQuota/consumeQuota/totalQuota` |
| 用户 | `GET /api/3d/getuserinfo` |

资产字段：`id / status(success|...) / sceneType / businessType / modelUrl3d / mesh / faceCount / imageList / isMultiView / imageTagList / createdAt`。

### AV.4 UI 打开资产的正确路径（顺序不能乱）
1. 点 `.worldMessage`（右上完成通知，打开 model-dialog）
2. 点弹层头 `.assets-v2-header`（「资产」）→ 展开 `mini-assets-dialog`
3. 点目标卡片的 `.task-list__item__asset__model-button`（查看模型）
   （同卡片还有 `__repeat-button` 同参重生成 / `__delete-button` 删除）
- 🚨 别点全屏遮罩（会把面板关掉）；模型加载判据 = `.loading-box` opacity==0 且
  `.t-progress__inner` 宽度 100%（「加载中 0%」文本是隐藏僵尸元素）。

### AV.5 查看器操作栏（模型加载后出现）
| 功能 | 选择器 |
|---|---|
| 视角/显示切换 | `.native-edit__viewport-actionBar-btn` ×10（自动旋转/白模/线框+白模/纹理/反照率/法线/bounding-box/light/zoom-to-fit，`.is-active` 当前态） |
| 下载 | `.native-edit__viewport-actionBar-download` |
| 点赞/点踩 | `.feedback-buttons__btn` |
| **分享** | **`.share-button__btn`**（右下角） |

### AV.6 🚨 分享链接（集成用这个）
```
POST /api/3d/share
{"contentType":"asset","contentId":"<资产id>","platform":"3dPlayground"}
→ {"shareId":"<uuid>"}          # 每次调用新建，非幂等
分享链接 = https://3d.hunyuan.tencent.com/share?shareId=<shareId>
```
- `extra`（可选）携带相机视角：`{"angle":270,"spotLightIntensity":0,...}`。
- UI 弹层：`.share-box`（「分享给朋友来围观您创作的3D模型吧！分享链接 <url>」）+
  `.share-btn`（复制链接，分享给好友）+ 二维码 canvas。
- 我们的多视图资产 contentId = **`53c361db-aa80-44dc-8965-460977d84f36`**。


### AV.7 混元3D 节点正式实现（2026-10-13 §1，产品代码，不只是探测）
- 客户端 `hunyuan3d_client.py`（660 行，CDP+Edge 浏览器通道）；端点 `/api/hy3d-tasks`（POST/GET）、`/{id}/login`、`/{id}/share`；前端节点类型 **`smart-hy3d`**（创建菜单 `data-create-type="hy3d"`）。
- 🚨 **模型地址不在 `modelUrl3d`/`mesh`（恒 `{}` 废字段）**，在 `result[*].urlResult.glb`；**分享 contentId = `result[*].assetId`**（不是 creation id）。
- 🚨 **「多张图片」控件宽网选择器** `.t-radio-button, label, div, span, button`（不是 `.t-radio-button`）；radio 切完卡片可能**直接渲染**、入口按钮消失 ⇒ 就绪判据 = `.hy-upload-card--front input` 出现。
- 🚨 列表外层 key 是 `creations`；`limit ≤20`；status=success 后 `urlResult.glb` 可能还要再等（客户端给了 180s 宽限）。
- 已知限制：GLB 77-81MB（1.5m 面 PBR）；面数档位（`generation-type-select`）未做选择；登录 profile = `data/hunyuan3d-profile`（`data/*` gitignore）。
- 验证：e2e 真实生成 succeeded（270s/150 万面/81MB）+ DOM 13/13 + 下载分享复验。脚本 `output/spike/verify_hy3d_{e2e,dom,dl_share}.py`。


## AW. 混元 3D 节点：细节全表（2026-10-13 §2–§14，从 MEMORY.md 下沉）

### AW.1 节点样式（§2）
- 🚨 hy3d 节点**必须同时带 `smart3d-node` 类**：框架/头部/body 的 CSS 全以它为作用域；否则节点「裸」在黑底上**且拖不动**（可见区恰在 `beginNodeDrag` 排除名单里）。
- 白底 = `scene.background` + `build3DStudioLights(viewer, null)`；接触阴影地面**必须在算完取景后加**。
- 显示样式工具行 9 键 + 下载 `<a download>`（**不能 preventDefault**）。

### AW.2 实时截图当参考图（§3）
- `queue3DSnapshot` 里**按类型分派**给 `queueHy3dSnapshot`（hy3d 复用 `attach3DOrbit` ⇒ 一处即覆盖拖拽/滚轮/双击）。
- `outputImagesForNode` 加 hy3d 分支；**连线规则两处都放行**（`canAutoConnectDraggedNode` + `connectInputNode`）。

### AW.3 分享 = 直跳资产页（§4/§5）
- 后端生成时**在同一会话**顺手拿 `result.share_url`（省一次开浏览器）；前端有链接渲染 `<a target=_blank>`，没有则退回按钮（**先同步开窗再 await**）。
- GLB 文件名 = `{task_id}.glb`（**task_id 自带 `hy3d_` 前缀，别拼两次**）。
- 🚨 **分享兜底必须按资产 ID**（`POST /api/hy3d-share {asset_id}`）：任务记录只在内存，**服务一重启老节点 `/api/hy3d-tasks/{id}/share` 必 404**（老板「点了不跳」的真因）。assetId 持久化在 `node.hy3dAsset.id`。

### AW.4 剩余次数（§5）
- 🚨 **必须实时读**（`POST /api/3d/quotainfo`）：生成任务开始时顺手读（零成本）+ `GET /api/hy3d-quota?refresh=1`（60s 缓存）。
- 🚨 **任何额度数值都不许写死**（各账号不同）。未读到显示 `--` + `is-unknown`，点击刷新。

### AW.5 发布清单（§7）
- 🚨 **加了新的根目录 .py 模块必须同步 `tools/release.py:ROOT_FILES`**（`hunyuan3d_client.py` 曾漏登记 → 用户装完**服务起不来**）。
- 发布前跑 `output/spike/verify_release_exposure.py`（41 项：敏感路径不在包内 + 反向证明文件确实在磁盘 + 新文件在包内）。

### AW.6 单张图自动走「单张图片」方案（§8）
- `upload_views` 按数量分派：1 张 → `.uploadBox input[type=file]`（判据 `.uploadBox` 带 `isSuccess`）；≥2 张 → 8 视图卡片。tab 用文案切（`_switch_mode`，宽网）。前后端门禁都从「≥2」放宽到「≥1」。
- 🚨 **探针取画布 ID**：`POST /api/canvases` 返回 **`{"canvas":{...}}`**，只取顶层 `id` 会得 None ⇒ 页面 `?id=None`、purge 静默失败 ⇒ 遗留垃圾画布。写法：`canvas.get("id") or canvas["canvas"]["id"]`。
- ⚠️ **Git Bash 会把 env 里的 `/assets/...` 当路径转换** ⇒ 跑探针传路径类 env 必须加 `MSYS_NO_PATHCONV=1`。

### AW.7 覆盖重发同版本号（§9）
- **不 bump**；先把 `output/release/<ver>/` 移出到 `output/release-archive/`，再重打。
- **tag 已存在 ⇒ `gh release create` 必失败，改 `gh release upload ... --clobber`**（`release-summary.txt` 每次重打都被覆盖，`--clobber` 说明要重补）。
- 代价必须讲清：**已装该版本的人不会再收到更新提示**（只比版本号不比 sha256）。
- ⚠️ **读远端单文件别用 `git fetch --depth=1`**（会把仓库变浅克隆）⇒ 用 `git show origin/main:VERSION`。

### AW.8 登录（§10）
- 🚨 **登录判据 = 能读到 `remainQuota`**（不是看 URL！）：扫码后若还需绑定手机号，URL 已回创作页但账号未就绪 ⇒ 旧实现提前收工。`GET /api/3d/getuserinfo` 只用于讲清「差哪一步」（未登录 401 / `registered` / `phoneNumber`）。
- 登录页只有一个「登录」按钮、二维码点它才出、**可能开新窗口**（本页 URL 不变）⇒ cookie 判据才对。
- 🚨 **登录端点不挂任务**（`POST /api/hy3d-login`）：剩余次数 chip 常驻生成栏，用户可能在第一次生成前就要登录。
- 🚨 **`?v=` 同步一轮可能不收敛**（按 `os.listdir` 顺序重写 ⇒ 排前面的 html 会记下后面文件改写前的 mtime）⇒ **再重启一次服务**即可。

### AW.9 节点状态说明（§11）
- 🚨 只出一处：底部 `.hy3d-phase` 仅在 **`hasModel`**（舞台被模型占着）时渲染；无模型时统一由中间占位承担。
- 按钮要区分「登录中 / 生成中」（共用 `running` 标志，别一律写「生成中」）。

### AW.10 在线生图上传 + 画布拖拽（§12/§13）
- 🚨 **在线生图上传 = 三个固定单图格子**（`#file1/2/3` → Main/Aux A/Aux B，`handleFile(file, id)`，`/api/ai/upload` 返回 `{files:[{url}]}`）：拖拽/粘贴多张必须**全部**上传并依次填格（`handleFilesToSlots` + `slotOrder` 循环）。
- ⚠️ **`online.*` 的 i18n 键在 `static/js/i18n/studio.js`**（没有 online.js）。该页 1.1.8→1.1.9 只动过 `?v=`，功能代码逐字节相同。
- ⚠️ **画布侧粘贴/拖拽多张图本来就正常**（`handleFiles` 收全部 files）——别再怀疑它。
- 🚨 **画布拖拽建节点**：空白处 drop 走全局 `window` 处理器，**引用 `pendingInspireDrag`**；该变量曾被误粘进 `initAgentPanel()` 局部（缩进 0 vs 周围 4 空格）⇒ 每次拖拽抛 `ReferenceError`，**async 监听器的 rejection 被静默吞掉** ⇒ 「拖到空白处毫无反应」。已提升为全局声明。空白处 drop 现按**上传节点**建（`forceNew:true, createGroup:false`）。
- 🚨 **排查「点了没反应」必先装 `unhandledrejection` 收集器** —— async 事件监听器里的异常既不冒泡也不打印。配合 `Page.addScriptToEvaluateOnNewDocument` 在页面脚本前装收集器可区分「没执行到」vs「不在作用域」。

### AW.11 发版前先查线上版本（§14）
- 🚨 拉 `https://github.com/HanaJhon/Infinite-Canvas/releases/latest/download/update.json`（公开端点，**不需要 gh 认证**）拿 delta/full 的 sha256，与 `output/release-archive/*/update.json` 指纹比对 ⇒ 精确定位线上构建。
- 🚨 **增量基线取「最保守」的那版**（不含本次改动的旧构建）：基线越旧 ⇒ `changed` 越大 ⇒ delta 是**超集**，绝不会漏文件。
- ⚠️ **VERSION 变了 ⇒ `?v=` 要全量重同步**（重启服务，通常**两轮**才收敛）。⚠️ **delta 只有几百 KB 是正常的**（exe 未改时）。

## AX. 拆分图层 V2（2026-10-15/16，老板方案二/三：双轨图层 + 抠图与可复用背景）
### AX.1 V2 相对 V1 的反转与新增
- 🚨 **文字默认改「可编辑」**（`textMode='edit'`）——推翻 V1「默认像素态」。原字像素降级为 `raster_backup_url` 隐藏备份。
- 🚨 **PSD 文字必须是原生 Type Layer**（`kind=2`，含 `TySh`）——探针 `output/spike/probe_pea_native_text.py` 已证实可行（读 `bounds` 会卡死，**绝不能读 bounds**）。
- 🚨 文字拟合从**非等比** `scale(kx,ky)` 改为**等比** `scale(k)`（根因：字形被两倍率压扁 ⇒「Anya 等字变形」）。仍**按签名缓存**（进出编辑态不重算）。
- 🚨 **AI 局部修复的贴回 bug**：`split_ai_repair` 把裁剪尺寸 patch 贴到全画布 (0,0) ⇒ 黑块/整图污染。修法：贴回 `(x0,y0)`，且只在授权区用模型像素。
- 🚨 **小目标 mask 判据按 ROI**（不是占全图比例）——否则 26×26 的指针（占全图 0.06%）被判无效 → 退化成矩形黑块。禁止「无条件矩形兜底」。
- 🚨 **清字要扩边**（把描边/阴影/抗锯齿一起挖掉）；背景加 `bg_status`（clean/local_filled/pending/ai_completed）+「待修补」徽章（不许拿模糊占位冒充完成）。
- 🚨 **GPT 门禁放宽**：入口不再按「模型名含 gpt」整项隐藏，改为「配置里存在 GPT/Codex 模型即显示」。
- 探针：`verify_split_v2_core.py`(43) / `verify_split_v2_fixes.py` / `verify_split_v2_pipeline.py`(36) / `verify_split_v2_dom.py`(62) / 旧 `verify_split_layers_dom.py`(119) / 端到端 `verify_split_psd_native.py`(11，CDP 真实时序)。**测试端口用 9000 或 8123**（3000-3080 被系统保留 ⇒ WinError 10013）。
- 🚨 **无头 CDP 探针三个坑**：① CDP 消息 id 必须**全程单调递增**（放函数内每条都从 1 开始 ⇒ 响应错位、`Runtime.evaluate` 恒 None）；② `Runtime.evaluate` 取值要进两层 `msg["result"]["result"]["value"]`；③ `--virtual-time-budget` 会让 60s 守卫瞬间触发 ⇒ 用 CDP 真实时序 + `--remote-debugging-port`。
- 🚨 **探针里的宿主元素必须可见**：`#splitLayersModal` 不加 `open` 类则 `display:none`，Photopea 起不来。
- ⚠️ 纯 PIL 环境（**无 numpy/cv2/scipy**）⇒ 形态学只能用 `ImageFilter.MaxFilter/MinFilter`；边界伪影靠「先零填充再运算、最后裁回」。


## AY. 抠图与可复用背景素材（2026-10-16，方案《抠图与可复用背景素材优化方案-20261016》）→ 日志 2026-10-16 §1

### AY.0 🚨 查前端前先看 HTML 的 `<script src>` 清单
拆分图层前端**已抽成独立模块** `static/js/split-layers.js`（167KB / 3278 行），
`static/js/smart-canvas.js` 里只剩 11 处 `splitLayers` 引用。
本次一开始只 grep `smart-canvas.js`，得出「商品模式前端完全没接」的**错误**结论，白花了一轮。

### AY.1 现状核实（本轮开工前的真实缺口）
- 已有：`backend/split_product.py`（`candidate_alpha` / `foreground_plate` / `mask_contract` /
  `validate_mask` / `paint_constraints` / `product_quality`）、`build_product_split_result`、
  `/product-quality` 端点、前端 `splitLayersTaskMode` / `splitLayersPreviewProduct` /
  `splitLayersConfirmProduct`（三背景独显是**客户端**渲染，不是服务端预览图）。
- 真缺：① 背景资产（完整素材 + 状态机 + 素材库复用）**完全不存在**；
  ② 三背景验收在 main.py 里是**硬编码** `product_checks = {"white": False, ...}` ⇒ 恒不通过；
  ③ trimap / matting / 去色边 **完全不存在**。

### AY.2 `backend/split_background.py`（新，纯 PIL 零模型调用）
- `detect_background_kind` → solid / gradient / radial / textured / complex。
  可信采样点必须**离洞至少 band(2% 边长)**，否则主体的抗锯齿/阴影会被吸进底板。
- `build_background(..., solid_scope=)`：**full**（§5.1 商品图整幅确定性底板）/
  **region**（海报只刷主体区域 ⇒ 遮罩外逐像素等于原图，叠加才 ≈ 原图）。
- 规则背景：`_fit_plane` / `_fit_radial` 自己解 3×3 正规方程（无 numpy），采样降到 ~2 万点；
  整幅图用 `Image.frombytes` 按行拼 bytes，不要逐像素 `putpixel`。
- `mirror_extend`（对称镜像）+ `neighborhood_inpaint`（邻域扩散）。
  🚨 扩散必须**自适应降采样**（洞长边 ≤72px 再放大贴回）：朴素全画布扩散 1200×900 要十几分钟。
- 🚨 **`mirror_seam_error` 是硬需求**：`structure` 只说明「有高频结构」，噪声/照片细节也会命中，
  于是镜像补出的背景被标 `deterministic` —— 而 deterministic 是**默认直接进素材库**的状态。
  接缝误差（洞外真实像素 vs 镜像像素的通道差）超 `texture_seam_tol(42)` ⇒ 退回 complex/speculative。
- `background_provenance` / `background_status_of`：四件套 + 状态机。

### AY.3 抠图质量（`backend/split_product.py` 扩展）
- `build_trimap`（0/128/255）、`alpha_boundary`（环带/核心/软边）、`edge_contamination`。
- `refine_alpha`：只在**未知带**做 matting。
  `a = ((C-B)·(F-B)) / |F-B|²`（F 取最近确定前景像素，半径内螺旋搜）；
  再 `F' = (C - B(1-a)) / a` **反解前景色**（去色边）。
  🚨 反例就是「原 RGB 直接乘 alpha」——白边/灰边/黑边全来自它。
  ⚠️ `a < 0.15` 区**不反解**（除以小数放大噪声成彩色噪点），保留原像素 + 连续 alpha；
  确定前景/确定背景像素一律不动。
- `three_background_check`：白/深灰/棋盘客观验收。
  `halo(B) = |环带对背景对比度 − 核心对背景对比度|`（背景相关，物理上正确）。
  🚨 **矩形残留 = 填充率 ≥0.985 **且** 边缘 ≥50% 是旧背景色** —— 只看填充率会把正方形主体误判成兜底。
  🚨 **内部孔洞**不能用「闭运算多出来的像素」（会把凹形/环形轮廓算成孔），
  要用「从四边 flood-fill 标记外部透明区，剩下的才是孔」。
- `product_quality(mask, size, contract, checks, objective)`：**客观 + 用户确认都过**才 `quality_passed`。
- `preview_composites` 生成三背景预览图（服务端也用得上）。

### AY.4 main.py 接线
- 分析阶段背景改走 `build_background(..., solid_scope='region')`；
  新增 `split_removed_hole(width, height, entries, plates)`（所有非背景层覆盖范围并集）。
- 端点：`POST /api/split-layers-tasks/{id}/background`、`GET /api/assets/{id}`、
  `GET /api/assets/{id}/download?kind=`、`POST /api/assets/{id}/save-to-library`。
- 资产目录 `output/backgrounds/<assetId>/` + `index.json`（`BACKGROUND_ASSET_LOCK` 保护，临时文件 + `os.replace`）。
- 🚨 **`_bg_asset_key` 绝不能「滤掉非 hex 字符再截断」**：`bg<32hex>` 的 `g` 会被滤掉、
  再截到 32 位 ⇒ **写入与查询算出两个不同 key，全部 404**。改成白名单 `[0-9A-Za-z_-]{1,64}` + 原样保留。
- speculative 不许进素材库（422）；前景变了而背景是 AI 补的 ⇒ 标 `stale`。
- 商品模式：`build_product_split_result` 里先 `refine_alpha` 去色边 → `three_background_check` 出客观结论 →
  `product_quality(..., {}, objective)`；`confirm_product_quality` **确认时重算客观检查**（用户可能刚刷过笔刷）。

### AY.5 前端（`static/js/split-layers.js`）
- 新增 `#splitLayersObjectiveRow`（客观结论：三项色边 + 结构 + 旧底色占比，ok/bad 徽章）+
  `#splitLayersBackgroundRow`（状态徽章 + 尺寸/算法 + 下载 + 存素材库）。
- 🚨 **客观未过 ⇒ 勾选框与确认按钮必须禁用**：否则用户勾满也会被后端 422 拒掉，只看到一句「未通过」。
- `splitLayersApplyResult` / `ShowReview` / `SaveRecord` / `RestoreRecord` 都带
  `backgroundAsset` / `objective` / `objectiveMetrics`。
- ⚠️ `StudioI18n.entries()` 返回 `{zh:{...}, en:{...}}`，**不是** key→{zh,en} 的扁平表。
- ⚠️ `splitLayersLang()` = `window.StudioI18n?.lang ? StudioI18n.lang() : 'zh'`。

### AY.6 验证资产
| 文件 | 项数 | 覆盖 |
|---|---|---|
| `tests/test_split_background.py` | 12 | 背景类型判定 / 确定性底板像素级 / 遮罩外不变 / 状态机 / provenance |
| `tests/test_split_background_api.py` | 6 | 四件套落盘 / 下载 / 存素材库 / speculative 阻断 / stale / region 语义 |
| `tests/test_split_product.py` | 14 | trimap / 去色边 / 三背景 / 退化 mask 阻断 / 客观+确认双门 |
| `output/spike/verify_bg_acceptance.py` | 32 | 方案 §10 验收矩阵 + 六格对照图 `bg_acceptance_sheet.png` |
| `output/spike/verify_split_bg_dom.py` | 31 | 客观结论行 / 勾选禁用 / 背景资产行 / 记录往返 / 旧数据兼容 |
| `output/spike/verify_split_bg_visual.py` | — | 截图 `split_bg_product.png` / `split_bg_review.png` |

### AY.7 过时探针断言（本轮修掉，别再改回去）
- `verify_split_layers_dom.py:uploadPsdIsPsd` → 上传接口现在返回**能力令牌 URL**
  `/api/photopea/file/<capability>`（`main.py:15744` 的 `item["photopea_url"]`），不再暴露 `.psd`；
  「确实是 PSD 字节」由 `uploadPsdMagic == "8BPS"` 证明。已改名 `uploadPsdIsCapabilityUrl`。
- `verify_split_v2_pipeline.py` 的「整幅 mean > 0 属预期」→ 确定性背景后 mean 变成 0（更好），
  改成「整幅叠加也 ≈ 原图（确定性背景不引入漂移）」。
- `verify_split_v2_fixes.py` 的 `fake_call` 桩补 `budget` / `operation` 参数。
- `main.SPLIT_BUDGET_MAX` 未从 `backend.split_budget` 再导出 → 已补（`SPLIT_BUDGET_DEFAULT/MAX`）。
- ⚠️ `tools/release.py` 的 `PROGRAM_DIRS` 已含 `backend` 与 `static` ⇒ 新模块**自动随包**，无需改清单。

---

## AZ. 分区清洁底板 clean plate（2026-10-16 §2，方案《非纯色背景重建与可复用背景资产方案-20261016》）

### AZ.1 为什么不能只挑一个整幅算法
`clean plate + 前景层 + 可选阴影层 ≈ 原图`。画面里可以**同时**存在多个表面
（浅色桌面 + 深色面板 + 网格底 + 纹理），整幅判一个 kind 必然把面板色铺到底色上。
所以必须 **分区 → 每区判表面 → 每区按表面挑最小算法 → 只从同表面取样**。

### AZ.2 代码位置
| 文件 | 内容 |
|---|---|
| `backend/split_surfaces.py`（新，~700 行） | `build_clean_plate` / `segment_surfaces` / `classify_surface` / `_merge_surfaces` / `_edge_barriers` / `_surface_thickness` / `_profile_period` / `_periodic_source` / `surface_summary` |
| `backend/split_background.py` | 六态状态机 + `LEGACY_STATUS` 旧名升级 |
| `main.py` | 八件套落盘 `split_background_asset_write`、`POST /api/split-layers-tasks/{id}/background/region` |
| `static/js/split-layers.js` | `splitLayersRenderBgRegions` / `splitLayersRebuildRegion` / `splitLayersResetBgRegions` |
| `tests/test_split_surfaces.py`（新，11 项） | 跨表面不混色 / 遮罩外逐像素不变 / 渐变拟合 / 点阵相位 / protectMask / unknown 不写入 / region_masks 一致性 / 空白洞 / 分类 / 量化条带合并 |

### AZ.3 判据口径（改代码前先对齐，否则一定误判）
- **表面类型**：`flat / gradient / grid / texture / panel / line / shadow / text / unknown`。
- **区域来源**：`original / copied / fitted / inpainted / unknown`，只有 `TRUSTED_SOURCES` 参与采样。
- **算法分级** `_SURFACE_ALGO`：`median_fill`(flat/shadow/panel) / `plane_fit`(gradient) /
  `phase_tile`(grid) / `same_surface_copy`(texture) / `axis_extend`(line)。
- 🚨 **像素数 = 采样点数 × step²**（`nTrue`）。用 `n` 当像素数会把 1200×900 面板判成窄条（`thinRatio=25`）。
- 🚨 **`reach` 尺度用水力半径** `2·面积/周长`，**不能用 bbox 短边**。
- 🚨 **证据面积硬闸**：`region_px > 4 × nTrue ⇒ conf = 0 ⇒ unknown`。
  只靠软性距离扣分不够（1.0→0.33 仍越过 0.30 门槛）。
- 🚨 **距离惩罚只作用于复制类算法**（`same_surface_copy / phase_tile / axis_extend`）；
  参数化算法（`median_fill / plane_fit`）不受距离影响 —— 否则大面板会被判 unknown。
- 🚨 **周期估计必须用投影轮廓自相关**（`_profile_period`）。
  用「相邻样本差峰间距」在点阵上会拿到**点宽 4px** 而不是**点距 16px**，整片纹理直接丢成 0。
- 🚨 **颜色合并只能发生在有接触的标签之间**（`_label_contact`），否则色差 24 但空间不相连的
  「面板 + 顶部条」会被误并；稀疏纹理另按 `thinRatio ≥ 3.0` 且接触量大合并。
- 🚨 **屏障线配对按「与洞边界垂直」**（`_boundary_tangent` 点积最小），不是「两点距离最远」
  （后者把矩形洞的四端点连成对角线）。屏障做标签检测前要先把标签铺到 band 上。
- 🚨 区域像素账目：`region-original = w*h - written - unknown_px`（不是 `w*h - hole_px`）。
- ⚠️ 大洞（> `work_limit = 400000`）把 BFS 放到降采样图上，放大取值用 **`NEAREST`**（`BICUBIC` 糊纹理）。

### AZ.4 资产与端点
- 八件套：`background.png / -preview.jpg / -mask.png / background-write-mask.png /
  background-protect-mask.png / background-diff.png / background-regions.json / -provenance.json`。
- 六态：`original_plus_deterministic / reviewed_inpaint / candidate / needs_manual_repair / stale / failed`；
  **只有前两态默认进素材库**。旧名由 `LEGACY_STATUS` 升级（`deterministic→original_plus_deterministic`、
  `reviewed_repair→reviewed_inpaint`、`speculative→candidate`）。
- `POST /api/split-layers-tasks/{id}/background/region` = `{region_id, action: rebuild|restore}`。
  `rebuild` 只对**该区域遮罩**重跑 `build_clean_plate`；`restore` 贴回原图像素。
- 🚨 前端 `source === 'unknown'` 的区域行必须 **禁用「只重做这块」**（P0 禁止生成假背景）。
- 🚨 没有背景资产时 `splitLayersRenderBackgroundRow` 要调 `splitLayersResetBgRegions()`
  （折叠 + 清空 + 隐藏入口），否则上一轮的按钮/区域行会**残留**。

### AZ.5 探针（本轮实测）
| 探针 | 项 | 覆盖 |
|---|---|---|
| `output/spike/verify_split_bg_dom.py` | **48** | 客观结论行 + 背景资产行 + **分区树（折叠/来源徽章/unknown 禁用/端点 action）** + 记录往返 + 旧数据兼容 |
| `output/spike/verify_split_bg_visual.py` | — | 截图 `split_bg_review.png` / `split_bg_product.png` / **`split_bg_regions.png`** |
| `output/spike/verify_bg_acceptance.py` | 32 | 方案 §10 验收矩阵 |
| `tests/` | **86** | unittest discover（**本机没有 pytest**，用 `python -m unittest discover -s tests -p "test_*.py"`） |

### AZ.6 探针环境红线（本轮踩到）
- 🚨 **服务不能用 `&` 丢后台**（Bash 工具调用结束 shell 退出会带走服务）⇒ 必须 `run_in_background: true`。
- 🚨 三个 DOM 探针默认端口不同（`verify_split_layers_dom` 默认 **3000**，另两个 **8123**），
  但**都读 `SL_VERIFY_PORT`** ⇒ 统一 `SL_VERIFY_PORT=9100`（9000 本轮被占用）。
- 🚨 `parse_dump` 拿不到探针容器时必须返回**可读错误**，否则报 `NoneType.get` 掩盖「服务没起」。
- 🚨 有 `busy` 门禁的异步动作（如区域重做）在探针里要 `waitIdle()` + 轮询，别赌单次时序。

---

## BA. 背景区域修补闭环 + 覆盖账本 + 前端四组状态（2026-10-16，老板方案《背景AI修补仍未生效-原因与最优调整方案-20261016》）

> 起因：截图显示「AI 调了 3 次、背景仍有 44 万像素缺失」。根因是工程把两类操作都叫「修复」，
> 却没按 `unknown region mask` 连起来 —— 调模型 ≠ 覆盖那个区域。方案要求把闭环补上：
> `unknown → 从交付背景中隔离原主体 → 用户遮罩 → AI 区域候选 → 写入范围校验 → 用户采纳 → 未知像素重新统计`。

### BA.1 后端账本（`backend/split_bg_regions.py`，新建 ~560 行）
- 区域状态机**八态**：`unknown / generating / candidate_ready / approved / rejected / superseded / failed / stale`。
  派生集合：`OPEN_STATES=(unknown, generating, failed)`、`PENDING_STATES=(candidate_ready,)`、`ISOLATE_STATES`。
- 🚨 **`background_coverage()` 是界面唯一可信的数字来源**：`repairs.length` 不是区域总数，
  `budget.used` 不是已采纳区域数。字段：`totalPixels / originalPixels / deterministicPixels /
  candidatePixels / confirmedPixels / uncoveredPixels / outsideChanged / aiCalls / budgetLimit /
  budgetRemaining / openRegions / pendingRegions / openRegionIds / maskBased / complete`。
- 🚨 **未覆盖 / 候选像素按 mask 并集统计**（`mask_union` 用 `ImageChops.lighter` 累积）——
  相交不重复计数、空隙不漏计。**没有 mask 的旧资产**才退回「按区域像素求和」，并在
  `maskBased=False` 里如实标注（前端据此显示「账本口径：按区域像素求和」的提示，不许拿偏大的数字冒充精确值）。
- 🚨 `maskBased` 的语义是「**未覆盖/待确认的区域是否都有 mask**」，不是「有没有 mask」：
  初始 `True`，任何 OPEN/PENDING 区域缺 mask 才置 `False`。
- 🚨 `complete = (uncoveredPixels == 0 and candidatePixels == 0)`；只有 `complete` 才能升 `reviewed_inpaint`。
- 稳定 region id：`region-{label}-{sha256(rmask)[:8]}` —— **同一输入必须产出同一 id**，不许依赖数组序号。
- `effective_write_mask(region_mask, user_write, protect, expected_revision=?, revision=?, min_pixels=1)`
  → `(mask, info)`，`info` 含 `effectivePixels/writePixels/regionPixels/protectPixels/writeHash/protectHash/effectiveHash`。
  `WriteScopeError.code` 集合：`region_empty / revision_stale / mask_empty / mask_full_canvas /
  mask_outside_region / mask_effective_empty / mask_dimensions`。前端要按 `code` 给可操作提示，不能只说「失败」。
- `candidate_quality(base_rgb, merged_rgb, write_mask, protect_mask, seam_tol=26, tone_tol=30,
  structure_min=0.30, outside_tol=0)` → `{ok, metrics, reasons}`，六项：`outsideChanged / protectedChanged /
  seam / tone / structure / newContent`。
- 🚨 **结构检查的空样本陷阱**：两侧都无可测边缘（纯平面 / 纯渐变）时相关度恒 0，
  必须豁免（`if (inner_hist is not None or outer_hist is not None) and structure < structure_min`），
  否则所有纯色修补都会被判「新增内容」而拒掉。
- `candidate_id = bg_candidate_id(task_id, region_id, revision, writeHash, nonce)`；
  记录字段见 `bg_candidate_record(...)`（`candidateId/taskId/regionId/operationId/provider/model/
  maskRevision/documentRevision/writeMaskHash/protectMaskHash/effectiveMaskHash/sourceHash/
  outputHash/status/decision/quality/url/diffUrl/appliedPixels/createdAt`）。

### BA.2 后端端点（`main.py`，8 条 background 路由）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/split-layers-tasks/{tid}/background` | 一次读数：`asset/regions/coverage/ledger/status/candidates/regionMasks` |
| POST | `.../background/regions/{rid}/mask` | **纯本地**保存写入范围（`SplitLayersBgMaskRequest{region_id,hints,expected_revision,reset}`）。`reset=true` 退回整块区域 |
| POST | `.../background/regions/{rid}/candidates` | 生成 AI 候选（`SplitLayersBgCandidateRequest{region_id,mask_revision,write_mask,protect_mask,prompt_hint,provider_id,model,operation_id}`），**主背景完全不变** |
| GET | `.../background/candidates/{cid}` | 单条候选 |
| POST | `.../background/candidates/{cid}/accept` | 采纳：`plate.paste(merged, (0,0), effective)` |
| POST | `.../background/candidates/{cid}/reject` | 拒绝：主背景**一个像素都不变** |
| POST | `.../background/regions/{rid}/restore` | 委托旧端点 `action='restore'` |
| POST | `.../background/region` | 旧端点（`rebuild` / `restore`），保留 |

- 🚨 provider mask 能力三档（`split_mask_edit_mode(provider_id, model)`）：
  `native_mask / local_edit / global_only`。登记表 `SPLIT_NATIVE_MASK_CHANNELS` /
  `SPLIT_GLOBAL_ONLY_CHANNELS`（**当前都是空集**，默认 `local_edit`）。
  `global_only` 的通道**直接 400**，不许伪称「遮罩修补」（方案 §5.2）。
- 🚨 **遮罩外保护由服务端回贴保证**（`merged.paste(base_rgb, (0,0), ImageChops.invert(effective))`），
  不依赖提示词 —— 模型不守规矩也不影响结果。
- 🚨 预算用尽 → **429**，且**根本不调模型**。视觉分析（LLM）不计入图像模型预算。
- 🚨 中间态（候选图 `bg_candidate_images`、`bg_region_write/protect/revision`、`bg_candidates`）
  **只在内存**（`SPLIT_TASK_STATE`，≤6 任务）⇒ **服务重启后 `/accept`、`/candidates` 拿不到候选图**。
  前端 `splitLayersRefreshBackgroundState()` 必须对 409 **静默降级**，继续用资产自带的那份账本。
- 🚨 `save_background_asset_to_library` 加了三道账本自证闸门：
  `uncoveredPixels > 0` / `candidatePixels > 0` / `outsideChanged > 0` **一律 422**。
- 🚨 新 mask revision 出现后，该区域旧候选自动 `superseded`，`/accept` 返回 **409**。

### BA.3 前端（`static/js/split-layers.js`）
- **四组状态**（方案 §4，`splitLayersCoverageGroups()` → `#splitLayersStatusGroups`）：
  `前景质量问题 x/y 项已处理` / `背景 AI N 次调用，M 个候选待确认` /
  `背景覆盖 已重建 X/Y 像素` / `背景待处理 Z 像素（区域 …）`。
  🚨 四组是**四个不同指标**，绝不能合并回一句「已修复 x/y（AI n 次）」。
  🚨 「背景覆盖 / 背景待处理」**只在非商品模式**出现（商品模式背景是纯色底板）。
  🚨 渲染节点用 `[data-split-status-groups]` 统一渲染 **两处**（审核面板 + 结果面板）——
  用 `:not([hidden])` 做选择器会一次命中两份，断言/数字都翻倍。探针要按 id 作用域。
  🚨 **底部状态栏不再重复这四组数字**（同一屏出现两次会让人怀疑哪个是对的）。
- **写入范围编辑与图层修正遮罩共用**同一块 overlay canvas 与同一套笔刷手势，
  靠 `splitLayersMaskTarget()` 分流：`{kind:'layer'}` 要过图层变换，`{kind:'bgRegion'}` 就是**画布坐标**（identity）。
  🚨 新增非图片目标时**必须同时改** `addPoint`（坐标映射）与 `splitLayersDrawMask`（渲染映射）两处。
- **区域行动作按状态给**，不是按 `source` 猜：
  `unknown/failed` → 编辑写入范围 / 生成候选 / 恢复原图（🚨 **不渲染**「只重做这块」，比「禁用」更严）；
  `candidate_ready` → 查看候选 / 恢复原图；`approved` 且非 original → 只重做这块 / 恢复原图。
- **候选对比**（`splitLayersRenderBgCandidateCompare()` → `#splitLayersBgCandidate`）：
  当前背景 / 候选 / 差异三格 + `100% 边界` 开关（`image-rendering: pixelated` + `object-fit: cover`）。
- **clean plate 预览**（`splitLayersRenderBgPlatePreview()` → `#splitLayersBgPlate`）：
  用资产自带的 `maskUrl`（未知区遮罩）把不属于背景的像素画成**棋盘格**（`rgba(255,255,255,.55)` /
  `rgba(110,110,110,.55)`，格子 12px），再按 `regions[].bbox` 描边界
  （unknown/failed 红、candidate_ready 橙、approved 绿、选中白加粗）。
  🚨 只在**展开分区树**时显示（`#splitLayersBgRegions` 不 hidden），不是常驻装饰。
  🚨 `Image.crossOrigin='anonymous'` + `try/catch` 包住 `getImageData`：data URI / 跨域图失败要能降级。
- 🚨 **`st.bgRegions` 与 `backgroundAsset.regions` 必须是两个数组**：
  统一走 `splitLayersSetBgRegions(regions, asset)`（拷贝 + 同步回资产），
  `splitLayersAbsorbBgRegion` 全程**不可变更新**（`map` 出新数组）。
  以前 `st.bgRegions[i] = {...}` 会连带改掉资产里的 `regions`，两套数字开始分叉。
  `splitLayersRenderBgRegions()` **以 `st.bgRegions` 为准**（它才是活数据），不要反向优先 `asset.regions`。
- `splitLayersResetBgExtras()`：没有背景资产时，除分区树外还要清掉**状态组 / 候选对比 / 底板预览**三块。
- 记录往返（localStorage `slRecords`）新增 `bgCoverage` + `bgCandidates` 两个字段，
  否则重开弹窗后四组状态凭空归零，用户会以为「上次修好的又坏了」。

### BA.4 探针（本轮实测）
| 探针 | 项 | 覆盖 |
|---|---|---|
| `output/spike/verify_split_bg_dom.py` | **90** | 客观结论 + 背景资产行 + 分区树（八态徽章 / 写入范围 / bbox / unknown 闭环动作 / 已确认区域无「生成候选」）+ 写入范围端点 + 候选生命周期（生成/对比/采纳/拒绝）+ **账本四组四态** + 棋盘格底板可见性 + 三背景验收 + 记录往返 + 旧数据兼容 |
| `output/spike/verify_split_bg_visual.py` | — | 截图 `split_bg_review.png` / `split_bg_product.png` / `split_bg_regions.png` / **`split_bg_candidate.png`** |
| `tests/` | **124** | 新增 `test_split_bg_regions.py`(28) + `test_split_bg_reg_api.py`(10) |

### BA.5 探针踩坑（本轮）
- 🚨 **探针里 stub `window.fetch` 必须放行非目标 URL**：页面自身还有别的后台拉取
  （`/api/prompt-libraries`、`/api/smart-*`），一起计数会让 `calls.length === N` 假失败。
  ⇒ stub 首行 `if(String(url).indexOf('/split-layers-tasks/') < 0) return realFetch.apply(window, arguments);`
- 🚨 探针 fixture 的 `REGIONS` 数组会被页面直接引用当 `st.bgRegions` ⇒ 应用侧若就地写就会**反向改掉 fixture**，
  同一个探针里第二次 `openWith` 拿到的是被污染的数组。断言要能暴露出这类「case 之间串味」。
- ⚠️ 视觉探针里做棋盘格预览时，资产尺寸要小（480×360）——`splitLayersRenderBgPlatePreview` 是
  **纯 JS 逐像素**循环，1200×900 会在无头里拖到十几秒。

## BB. 拆分图层「图层文档」契约 + 检查抽屉 + 通道能力声明（2026-10-16 §4，方案《参考豆包图层编辑器的拆分图层重构方案-20261016》）

> 一句话：把拆分图层从「自动输出一批图片」升级为**一份可审查、可编辑、可复现的图层文档**。
> 第一性原则：**不把「调用过 AI」当成「修复完成」** —— 只有 `accepted` 才更新文档当前引用。

### BB.1 模块与端点
- 新建 `backend/split_document.py`（~530 行）= 文档契约唯一真源。
- 新建 `backend/split_providers.py`（~180 行）= 通道能力声明唯一真源。
- 端点：`GET /api/split-layers-tasks/{id}/document` **与** `GET /api/split-layers/{id}/document`
  （同一函数挂两个装饰器）；`GET /api/split-layers/providers/capabilities`；
  `get_split_layers_task()` 返回值末尾附 `task["document"] = split_document_of(task_id, task.get("result"))`。
- `main.py` 旧常量 `SPLIT_NATIVE_MASK_CHANNELS` / `SPLIT_GLOBAL_ONLY_CHANNELS` **已删除**，
  `split_mask_edit_mode(provider_id, model)` 改为 `return provider_mask_edit_mode(provider_id, model)`。

### BB.2 operation 状态机（`split_document.py`）
```python
OPERATION_STATES = ("created","validated","budget_reserved","submitted","candidate_ready",
                    "accepted","rejected","superseded","failed","cancelled","unknown")
OPERATION_TERMINAL = ("accepted","rejected","superseded","failed","cancelled")   # 终态不可再变
```
- 🚨 **终态锁定**：`rejected` 之后**不能**再 `accepted`（测试 `test_terminal_state_is_locked`）。
- 🚨 `operation_new(state, operation_id=...)` 按 **operationId 幂等**：同 ID 再调返回已有那条，不新建。
- 🚨 `operation_path(current, target)` 用 **BFS 求最短合法路径**；`operation_advance()` 只补中间步骤，
  **不跳校验** —— `accepted` 仍只能从 `candidate_ready` 到达（`test_advance_cannot_skip_validation`）。
- 🚨 进程重启后未完成的 operation 恢复为 `unknown`，**不得自动重放**（`unknown` 只允许去 `candidate_ready` / `failed`）。
- 接线侧 `main.py:split_track_operation(state, op_id, target, **fields)`：旧任务无 operation 日志时**静默跳过**，
  非法跃迁**只打日志不阻断**（界面不能因为一条记录烂掉而卡死）。

### BB.3 通道能力声明（`split_providers.py`）
- `REGISTRY = {}` **故意为空** —— 一个通道都没实测过原生 mask 入参 ⇒ 全部走保守默认。
- 🚨 精确 `provider` → `provider/*` 通配 → 保守默认，三档匹配，**不按模型名猜能力**。
- 🚨 `mask_edit_mode` 三态：`native_mask`（`supports_masked_edit`）/ `local_edit`（默认）/
  `global_only`（本地适配也救不回来）。**默认必须是 `local_edit`**（与旧口径一致，见 BB.6 坑）。
- 🚨 **`local_edit_ok` 与 `returns_aligned_crop` 必须分离**：
  - `local_edit_ok` = 服务端自己能不能做「crop → 生成 → unpad → 回贴」的局部候选（与通道守不守规矩无关）；
  - `returns_aligned_crop` = 通道返回结果能不能跟输入对齐。
- 🚨 **`can_auto_accept = supports_masked_edit AND returns_aligned_crop`** —— 当前所有通道都不满足，
  即**当前一律不允许自动采纳**，必须人工点采纳。
- ⚠️ 提示词里写「不要修改遮罩外」**不属于安全边界**；真正的边界是服务端 `effective_write_mask` 逐像素拷回。

### BB.4 旧数据兼容（`split_document.py`）
- `normalize_background_status(value)`：`LEGACY_STATUS` 升级 → 合法名 → **否则一律 `needs_manual_repair`**。
  🚨 **绝不允许映射成「已完成」**（`normalize_background_status("completed"/"done"/"看不太懂") == "needs_manual_repair"`）。
- 🚨 **`is_legacy_unverifiable` 必须查 5 个区域映射落脚点**，只查前两个会把**所有现代记录**误判成「无法追溯」：
  `result["regions"]` / `asset["regions"]` / `state["bg_regions"]` / `asset["regionCount"]` / bg 图层 `regions`
  ⇒ 统一走 `region_mapping_count(result, state)`。**这个缺陷是被单测抓出来的**（`test_current_result_is_not_flagged`）。
- `adapt_legacy_result(result, state)` **不原地修改输入**，返回新 dict。

### BB.5 前端检查抽屉（方案 §4.1 / §4.3）
- HTML：标题栏 `#splitLayersInspectBtn`（带 `#splitLayersInspectBadge` 计数徽章）+ `<aside id="splitLayersInspector" hidden>`。
- JS（`static/js/split-layers.js`）：
  - `splitLayersTextStats()` → `{total, editable, raster}`（`textMode === 'pixel'` 算栅格轨）；
  - `splitLayersDeliverChecks()` → 四项 `{key:'bg'|'fg'|'text'|'clean', ok}`；
  - `splitLayersInspectorRows()` → **6 行** `fg/bg/ai/text/deliver/doc`，每行 `{key,icon,label,value,tone}`；
  - `splitLayersToggleInspector(on)`（同步 `aria-pressed`）/ `splitLayersRenderInspector()`。
- 🚨 **前景那行只报「还没处理的」**：`!(i.fixed || i.resolved)`。把已修好的也算进风险 = 报假警。
  （先例：`test_split_bg_regions` 的 `is-1` 已 `fixed:true`，初版实现会把它算进去。）
- 🚨 **数据源只有 `st.bgCoverage` + `st.issues`/`st.audit`**，绝不前端另算一套「还剩多少」。
- 🚨 `badge.hidden = warn === 0`；面板 `hidden` 时不渲染内容（省一次重排）。
- 🚨 **`#splitLayersInspector` 无 result 时强制收起**：`if(!st.ready || !st.layers?.length)`。
- 键位：`B` 前景保留/删除笔刷（`bgRegionSel` 非空时 return）/ `M` 背景修补遮罩（无区域 → toast
  `smart.splitLayersMaskNoRegion`）/ `1/2/3` 切预览 / `Esc` 依次关**抽屉 → 遮罩 → 编辑器**；输入框内不劫持。
- CSS（`static/css/split-layers.css`，+114 行）：`.sl-inspector { flex:0 0 286px }`、
  `@media (max-width:1120px){ flex-basis:232px }`；`.sl-inspect-row` + `.sl-inspect-ok/-warn/-bad`；
  `#splitLayersInspectBtn[aria-pressed="true"]`。
- i18n：`smart-canvas.js` 1472 → **1492**（+21，`Inspect*` 系列 + `splitLayersMaskNoRegion`）。

### BB.6 坑（务必别踩回去）
- 🚨 **`.sl-inspector[hidden]` 必须显式 `display:none`** —— flex 子项会忽略 `hidden` 属性
  （`.sl-mask-bar[hidden]` 踩过同一个坑）。
- 🚨 **改 `mask_edit_mode` 默认值会改现有行为**：未登记通道旧口径就是 `local_edit`
  （服务端自己做的 crop/unpad/回贴，与通道是否守规矩无关）⇒ 新增 `local_edit_ok=True` 字段承载它，
  **不要**为了「保守」直接返回 `global_only`。
- 🚨 **`replace_all` 批量替换 `state["bg_doc_revision"] = int(...) + 1` 会留下旧缩进 + 同行粘连**
  （出现 `bump_document_revision(state)    coverage, status = ...`）⇒ 必须逐一手工修正。
  另：`bump_document_revision()` **已同时写 `document_revision` 与 `bg_doc_revision` 两个 key**，别再赋值。
- 🚨 **单测必须用项目内置 `./python/python.exe`**（只有它装了 PIL 12.3.0）。
  系统 python / 受管 python 都 `ModuleNotFoundError: No module named 'PIL'`（本次 16 项报错）。
- ⚠️ `split_document_of(task_id, result)` = `adapt_legacy_result(...) if result else result` → `build_document(...)`；
  `build_document` 是**纯读接口**，不得在里面改 state。

### BB.7 探针与验证（本轮实测）
| 项 | 数量 | 说明 |
|---|---|---|
| `tests/` | **203** | 124 → 203（+79）：`test_split_document.py`(54) / `test_split_providers.py`(16) / `test_split_document_api.py`(12) |
| `verify_split_bg_dom.py` | **109** | 90 → 109，新增 ④g 段 19 条检查抽屉断言（`inspectRowKeys: "fg,bg,ai,text,deliver,doc"`） |
| `verify_split_v2_core` / `_fixes` / `_pipeline` | 43 / 22 / 36 | 后端契约回归 |
| `verify_bg_acceptance` | 32 | 三背景验收矩阵 |
| `verify_split_psd_native` | 11 | CDP 真实时序 |
| i18n | **1492** | 1472 → 1492 |
| 截图 | 5 张 | 新增 **`split_bg_inspector.png`**（六行 + 徽章 5 + 三色分明） |

- `test_split_providers.py` 用 `RegistryResetMixin` 每个测试 save/clear/restore `REGISTRY`，
  且 `test_registry_ships_empty` 断言 `REGISTRY == {}` —— 空登记表是**设计**，不是遗漏。

## BC. 元素级拆分重构 P0：冻结旧写入口 + 只读兼容（2026-10-16）

> 方案 `Infinite-Canvas-豆包式元素级拆分图层完全重构方案-V2-20261016.md`（485 行）§2.1 / §2.2 / §14 P0 / §15。
> 本轮**只做 P0**：下线旧入口。新系统（P1 起）尚未建成 —— **不许宣称功能已恢复**（方案 §16）。

### BC.1 两步走的分工（别混）
- **P0（已做）**：旧写入口冻结 + 只读兼容。旧实现代码**保留**（P5 才删）。
- **P1–P5（未做）**：`element_document.py` / `element_ownership.py` / `element_extract.py` / `background_cleanplate.py` /
  `element_edit.py` / `element_export.py` + 新前端编辑器 + 新 API `/api/element-documents/…`。
- ⚠️ 盘出的**现况**（`output/element-refactor-inventory.md`）：旧「整图模糊冒充背景」**已无残留可删**（前几轮就没了），
  P0 删除面比方案原文设想的小；真正的重头在 **P1 ownership** ——
  **同一元素出现在多层的问题仍存在**（`split_element_mask` 只给 bbox 加 pad，各元素 mask 独立生成、无全局冲突解决）。
  §1 硬约束「每个有效像素只属于一个元素层 / clean plate / unknown 三者之一」**当前根本没实现**。

### BC.2 两个总开关（回滚用）
| 开关 | 位置 | 默认 |
|---|---|---|
| `LEGACY_SPLIT_WRITES_FROZEN` | `main.py`（`split_state_get` 之后） | `True` |
| `SPLIT_LAYERS_WRITES_FROZEN` | `static/js/split-layers.js`（`splitLayersEl` 之后） | `true` |
- 置 False/true→false 可整体放行旧链路，**仅用于排查**；新旧状态混用正是本方案要消除的问题。

### BC.3 后端守卫模式（🚨 别写成 `if blocked:`）
```python
def legacy_split_write_blocked():
    if not LEGACY_SPLIT_WRITES_FROZEN: return None
    return JSONResponse(status_code=410, content={
        "ok": False, "deprecated": True, "frozen": True, "legacy": True,
        "isElementDocument": False, "migration": "element-documents",
        "newApi": "/api/element-documents", "detail": LEGACY_SPLIT_FREEZE_HINT})
# 调用侧：
blocked = legacy_split_write_blocked()
if blocked is not None:      # 🚨 必须 is not None —— JSONResponse 的布尔值不可依赖
    return blocked
```
- **11 个写路由**全部加了守卫（`grep -c "legacy_split_write_blocked()" main.py` == **12** = 1 定义 + 11 调用）：
  `create_split_layers_task` / `repair_split_layers_task` / `update_split_layers_mask` / `confirm_product_quality` /
  `rebuild_split_background` / `rebuild_background_region` / `update_background_region_mask` /
  `create_background_candidate` / `accept_background_candidate` / `reject_background_candidate` / `restore_background_region`。
- **5 个读接口保留**只读兼容；`get_split_layers_task` / `get_split_layers_document` 加三标记
  `legacy=True / isElementDocument=False / writesFrozen=<flag>` —— **旧任务不得伪装成元素级文档**。

### BC.4 前端体验闸门（前端只是体验层，硬边界在后端 410）
- `splitLayersLegacyFrozen()` → toast + 返回 true；**10 个写函数**首行 `if(splitLayersLegacyFrozen()) return;`：
  `splitLayersApplyBgRegionMask` / `splitLayersResetBgRegionMask` / `splitLayersGenerateBgCandidate` /
  `splitLayersCandidateAction` / `splitLayersRebuildRegion` / `splitLayersConfirmProduct` / `splitLayersStartSplit` /
  `splitLayersRepair` / `splitLayersCreateTask` / `splitLayersApplyMask`。
- `splitLayersOpenPrep()` 首行拦；`openSplitLayersEditor` 两分支：有记录 → **追加**只读提示（`· ${tip}`，
  带 `includes(tip)` 去重，**不许覆盖「已恢复…」前缀**）；无记录 → `splitLayersShowFrozenNotice()` 后 return。
- 冻结公告视图 `.split-layers-overlay.frozen`（第五态）：**必须把 prep/progress/fail/review 四态全压住**
  （漏一个就留一条旧写入口），且 `#splitLayersFrozen` 里**不给任何「开始拆分」按钮**。
- `closeSplitLayersEditor` / `splitLayersShowPrepOverlay` / `splitLayersFail` 三处都要 `classList.remove('frozen')`。

### BC.5 🚨 本轮真实踩坑（会重犯的那种）
- 🚨 **冻结公告文字色必须走主题变量**：`#splitLayersModal .split-layers-overlay` 用 `--sl-base/--sl-text` 覆盖了
  旧写死的深色 ⇒ 浅色主题下写死 `#e2e8f0` = 白字白底**看不见**。改在文件尾部 `#splitLayersModal` 段落加
  `.sl-frozen-msg`（`--sl-text`）/ `.sl-frozen-hint`（`--sl-muted`）。实测对比度：浅 16.96 / 6.04，深 15.15 / 8.59。
- 🚨 **`getComputedStyle(el).display` 判不出「祖先 display:none」**：子元素自己的 computed display 仍是原值。
  判「有没有被画出来」要用 `getBoundingClientRect()` 宽高为 0 或 `offsetParent === null`。
  （探针初版拿它判 `#splitLayersStartBtn` 隐藏 → 假失败。）
- 🚨 **三个 `test_split_*_api.py` 验证的是旧实现本身**（P5 才删），P0 冻结后会失效/挂起
  （`test_concurrent_mask_requests_only_commit_one_revision` 用 `asyncio.Event` 等 release，
  冻结后提前 return 不 set ⇒ 挂死）。⇒ 各自 `import main` 后显式 `main.LEGACY_SPLIT_WRITES_FROZEN = False`。
  **「冻结行为」是另一件事，由 `tests/test_element_freeze.py` 专测**。
- 🚨 **「默认冻结」必须查源码文本**（`assertRegex(src, r"(?m)^LEGACY_SPLIT_WRITES_FROZEN\s*=\s*True\s*$")`）——
  同进程里测试文件会把开关置 False，模块属性查不到默认值。
- 🚨 **探针端口一律读 `SL_VERIFY_PORT`**（`verify_preview_split_entry.py` 原先写死 3010，服务在 9100 ⇒ 假失败）。
- 🚨 **门禁类探针必须显式 stub 两分支**，不能拿本机当前对话模型当输入（随 `data/api_providers.json` 漂移 = 假失败）。
- 🚨 **`update-notes.json` 的 `items` 是「旧→新」追加顺序，但 `static/index.html:renderProjectUpdateNotes` 只
  `items.slice(0, 8)`** ⇒ 启动器只显示**最旧** 8 条，新条目根本看不到。本轮 P0 条目**前置插入**到 index 0 才可见。
  （渲染器未动；此为准缺陷，待老板定夺。）

### BC.6 本轮验证（全绿）
| 项 | 结果 |
|---|---|
| `tests/` | **225**（203 → 225：+22 `test_element_freeze.py`） |
| `verify_element_freeze_dom.py` | **22**（新建，P0 专项：冻结态 + 零请求 + 双主题对比度） |
| `verify_split_layers_dom.py` | **121**（119 → 121：freshOpensPrepPanel 拆成 3 条冻结断言） |
| `verify_split_bg_dom.py` | **100**（109 → 100：写链路断言翻转为「一个请求都发不出 + 状态零变化」） |
| `verify_preview_split_entry.py` | 13（`btnText` → 元素拆分；门禁两分支显式 stub） |
| `verify_split_v2_dom.py` | 62 |
| `verify_split_v2_core` / `_fixes` / `_pipeline` / `verify_bg_acceptance` | 43 / 22 / 36 / 32 |
| `verify_split_psd_native.py` | 11 |
| i18n | **1498** keys（+6：`splitLayersFrozenTitle/Msg/Hint/Btn/Toast/LegacyTip`） |
| 截图 | 新增 `split_frozen_notice.png`（共 6 张） |

## BD. 元素级拆分重构 P1：文档契约 + 所有权内核（2026-10-16）

> 接 **BC**（P0 冻结）。方案 §14 P1 / §15.4–§15.5。**新系统尚未对用户可见**（§16）。
> 台账 `output/element-refactor-inventory.md` §9 是本次交付的完整记录。

### BD.1 四个新模块（纯 PIL / 纯逻辑，零模型、零磁盘写）
| 模块 | 关键 API | 出处 |
|---|---|---|
| `backend/element_understanding.py` | `parse_analysis(payload,size)` → `{elements,textCandidates,backgroundRegions,analysisVersion,issues}`；`analysis_to_elements()`；`candidates_to_entries(analysis, mask_provider)`；`analysis_summary()`；`KNOWN_RELATIONS=("in_front_of","occludes","behind_of")` | §B / §8 / §15.5 |
| `backend/element_ownership.py` | `resolve_ownership(entries,size,margin)` → `{ownership,unknown,masks,labels,order,stats}`；`check_ownership()`；`tier_for/tier_level/binary_mask` | §C / §12 / P1 |
| `backend/element_extract.py` | `extract_element(source,mask,defringe,background)` → `{rgba,bounds,alphaPixels,defringe}`；`extract_all()`；`crop_to_bounds()`；`verify_element_layer()` | §E / §12 |
| `backend/element_document.py` | `register_asset/get_asset/asset_kind`；`create_document/add_elements/attach_element_assets/set_element_transform`；`set_ownership/set_background`；`accept_element/reject_element`；`record_operation/_drive_operation`；`validate_document/document_summary` | §7 / §9 / P1 |

**复用**：`split_document.operation_new/operation_transition/operation_advance`、`normalize_background_status`；
`split_product.refine_alpha`（去色边）。**不另造第二套词汇**。

### BD.2 所有权内核（本重构的正题）
```
ownershipMask = "L" 标签图：值 = 元素序号(1..254)，0 = 无主（0 保留）
order = sorted(entries, key=(tier, confidence, depth, label), reverse=True)   # 🚨 降序
逐条：fresh = mask & ~claimed  → 先涂者占位（= 最高优先级）
      their_second = mask & claimed & ~taken2  → 记录第二顺位
unknown = contested & same_tier & |Δconf| < margin(0.08)   # 判不清
ownership.paste(0, mask=unknown)；各层 mask = (ownership==label) - unknown
```
- 🚨 **必须降序涂抹**。升序会让最低优先级拿到有主像素 ⇒「最弱的证据反而赢」= 旧链路的老毛病。
- 🚨 `unknown` 必须 `.point(lambda v: 255 if v else 0)` 归一 —— 不干净时 `subtract` 会留残差（255−3=252≠0）。
- 恒等式（`stats`）：`claimedPixels == ownedPixels + unknownPixels` 且 `unassignedPixels == 0`；
  各层 mask 之和 == `ownedPixels`。`check_ownership()` 把 §12 前两条再验一遍。
- 优先级 `TIER_LEVELS`：`user 60 / text_vector 50 / high_confidence 40 / depth 30 / edge_color 20 / unknown 0`。
  `HIGH_CONFIDENCE=0.70`、`CONTEST_MARGIN=0.08`、`DEFAULT_CONFIDENCE=0.5`（**不是 1.0**）、`MAX_ELEMENTS=254`。
- `tier_for()` 只认**声明过的证据**：`userEdited`/`source=="user"` → user；`type∈(text,vector)` → text_vector；
  `confidence>=0.70` → high_confidence；有 `in_front_of`/`occludes` 关系 → depth；否则 edge_color。
  ⚠️ 高置信**优先于**深度关系（照 §C 链），所以「有遮挡声明」也**不会**越档。

### BD.3 文档契约要点（§7）
- `ELEMENT_DOCUMENT_SCHEMA_VERSION = 1`（与旧 `split_document` 的 schemaVersion 3 是**两条线**，别比大小）。
- 资产**载荷只留在 `ASSET_STORE`**，文档只持 `assetId`；`register_asset` 返回的引用里没有 image/data
  ⇒ LAN 接口不会顺手泄漏像素/base64。
- `ownershipAssetId` **只有 `set_ownership()` 能写**；`unknownMaskAssetId` 必须 kind=`unknown_mask`。
- **`baseElementRevision` 语义**：元素级写入比该元素 `ownershipRevision`，文档级写入比 `documentRevision`；
  `base=None` 表示不校验（只用于首次构建）。不一致 → `RevisionConflict(expected, actual)`（调用方回 **409**）。
- `bump_element_revision()` **同时**推元素版本与文档版本（只推一个会让另一个失效）。
- `normalize_element`：`editable = bool(entry.editable) and type=="text"` —— **文字默认不可编辑**（§5.1）。
- `set_background` 把 `quality.plateStatus` 过 `normalize_background_status()`，不认识的状态 →
  `needs_manual_repair`（**绝不当成功**）。文档级 `background.status` 另有一套
  `BACKGROUND_DOC_STATUS = (empty,candidate,accepted,needs_review,failed)`。
- store 上限 `DOCUMENT_STORE_MAX=6` / `ASSET_STORE_MAX=512`，FIFO 淘汰（与 `SPLIT_TASK_STATE` 同策略）。
  **没有持久化** —— 半个持久化比没有更危险，完整持久化属 P5。

### BD.4 🚨 本轮真实踩坑
- 🚨 **随包 PIL 12.3.0 没有 `Image.nbytes`**（`hasattr(img,'nbytes')` → False）⇒ 资产体积用
  `len(img.tobytes())`（一次缓冲拷贝，登记是低频动作，口径准确更重要）。
- 🚨 **不能拿「有没有返回 plate」判去色边生效**：`split_product.refine_alpha` 在
  「没有软边带」或「没给 background」时会**原样返回 alpha + plate**（`reason` 字段说明原因）。
  判据必须是 `detail["refined"] > 0`。硬边元素（α 只有 0/255）**没有软边带** ⇒ 无事可做，
  这是正确行为（`test_hard_edge_element_has_nothing_to_defringe` 固化）。
- 🚨 **`element_extract` 里 mask 是最终权威**：`alpha = multiply(alpha_after_defringe, gate)`，
  上游 alpha 细化乱改也出不了层 ⇒ §E「层外必须透明」由构造成立。
- 🚨 **`getComputedStyle` 式的假信号再犯一次**：`accept_element` 早期版本
  `try: operation_transition(...) except OperationTransitionError: operation_advance(...)` ——
  单步 `operation_transition("created"→"accepted")` 必然非法，于是永远走 fallback，
  真正的非法跃迁也被吞掉 = 账本造假。改为 `_drive_operation()`：存在且未到目标才推进，非法照实抛。
- ⚠️ **测试共用 fixture 装载器**：放 `tests/_element_scene.py`（`_` 前缀 ⇒ `discover -p "test_*.py"` 不收集它），
  并在测试里 `sys.path.insert(0, 测试目录)`。`tests/` **没有 `__init__.py`** ⇒
  `python -m unittest tests.xxx` 会 `ModuleNotFoundError`，只能用 `discover -s tests`。
- ⚠️ 返回错误的**类型契约**：`element_extract` 在调 `binary_mask` 时把 `OwnershipError`
  包成 `ExtractError`，让每个模块都有自己的异常类型而不是把邻居的类型漏出去。

### BD.5 静态 fixture 与验证
- `tests/fixtures/element_scene.json`：表壳（环 rect+hole）/ 表盘 0.78 / 指针 0.96+in_front_of /
  秒针 0.86 / 标签文字 0.85(text) / 反光对 0.72+0.71（同矩形）。矩形**刻意重叠**。
  头号断言 = 指针层像素**恰好** 640 px；另有「其它层 ∩ 指针 == 0」「claimed==owned+unknown」
  「owned == Σ各层」「反光对两块全归 unknown」。
- `_element_scene.analysis_payload(scene)` → §B 形状候选 JSON；`scene_mask_provider(scene)`。
  用它跑 B→C→E 并断言与直接给 mask 的**逐字节一致**（防契约层偷改证据）。
- `tests/` **384**（225 → 384）：`test_element_ownership` 41 / `test_element_extract` 22 /
  `test_element_document` 61 / `test_element_understanding` 34。

### BD.6 已知限制 / 下一步
- **未接 HTTP 接口**（§9 的 `/api/element-documents/…` 未建）：P1 没有能创建文档的真实调用方，
  端点会是死代码。**别把「模块在但没接口」当成没做完** —— 那是刻意的顺序。
- **P2（下一步）** `background_cleanplate.py`：`removeMask` 合并 → 可控膨胀 → `backgroundHole` →
  纯色证据才允许常量填充 → 纹理/渐变走局部修补（**不得整图重生成**）→ 候选只改 `writeMask` →
  打分（边界连续性 / 结构相似度 / 重复纹理 / 空位测试）→ 未过检显示「待修复洞」。
- 新增文件都在 `backend/`、`tests/`（均在 `tools/release.py:PROGRAM_DIRS`）⇒ **无需改 `ROOT_FILES`**。

---

## BE. 元素级拆分重构 P2：背景 clean plate（2026-10-16）

> 方案 = `Infinite-Canvas-豆包式元素级拆分图层完全重构方案-V2-20261016.md` §4 阶段 D / §12 / §14 P2。
> 🚨 §16 仍生效：**内核已落地，未接 provider、未接前端、无真实图回归 ⇒ 不许宣称功能已恢复**。

### BE.1 文件
- `backend/background_cleanplate.py`（~1310 行，纯 PIL：零模型调用、零磁盘写、零网络）。
- `tests/test_background_cleanplate.py`（80 项）。
- `output/spike/verify_cleanplate.py`（320×240 合成商品图 4 组移除的端到端验收）。
- `output/element-refactor-inventory.md` §10（交付记录）、§3.4（已落地标注）。

### BE.2 接口
| 函数 | 关键约定 |
|---|---|
| `remove_mask(ownership, element_ids, include_unknown, extra, size)` | `element_ids=None` ⇒ 全清 **且 unknown 一并清**；给了 id ⇒ unknown **默认不清**（留下的元素可能正是它的归属者）。未知 id **报错不静默跳过** |
| `expand_remove(mask, radius, protect, gate, size)` | `MAX_DILATE=24` 上限、`MaxFilter` 圆盘核；**protect ∩ removeMask ≠ ∅ ⇒ 抛 `CleanPlateError`**（静默裁剪=主体留在背景里）；gate 只限扩张、永不吃掉原 mask |
| `background_hole(source, remove, protect, colors, region_masks)` | 复用 `split_surfaces.build_clean_plate` 的分区能力；**语义不沿用**（它的 plate 降级成 `local_repair` 候选）。返回 hole/regions/localRepair/protect/stats |
| `flat_evidence(source, region, hole, radius=4)` | 返回 `{ok, color, spread, drift, majority, pixels, ringPixels, reason}`；reason ∈ `ring_too_small` / `mixed_context` / `not_flat` / `color_drift` |
| `repeat_texture_check(source, plate, region, radius=4)` | reason ∈ `stamped_repeat` / `texture_broken` / `period_missing_{x,y}` / `period_mismatch_{x,y}`；**两边都没有周期 = 一致平坦 = 通过** |
| `empty_slot_test(source, plate, core, radius=4)` | 返回 `{ok, metrics, reasons, requiredChange}`；metrics = `residuePixels / ghostCorr / regionContrast / alphaHoles / mustChangePixels / ringColor` |
| `generate_candidates(source, hole_result, protect, algorithms, ring_radius)` | 只有两个确定性候选 `flat_fill` / `local_repair`；**没有**「把原图交上去」这个候选 |
| `score_candidate(source, candidate, hole_result, protect, weights)` | 逐区域喂 `candidate_quality`；`regions[].state` = `repaired`/`pending`，判据是**检查过没过** |
| `compose_plate(source, candidate, region_states)` | **只拼 `state == "repaired"`** 的区域 |
| `verify_cleanplate(plate, source, required_change, write_mask, remove, protect, tolerance)` | issues code ∈ `subject_residue` / `pending_holes` / `outside_written` / `protected_written` |
| `build_cleanplate(...)` | 全链路；返回 `plate`（**只含过检区域**）/`writeMask`/`requiredChange`/`checks`/`status`/`pendingHoles`/`candidates`/`candidateRaw`/`stats` |
| `select_candidate(result, candidate_id, source)` | 🚨 **`source` 必须显式传原图**，不能从 plate 反推（plate 已含修补像素 ⇒ 空位测试会失效，一个「什么都没改」的候选被判全绿） |
| `summarize(result)` | JSON 安全，**不含 image/base64** |
| `attach_to_document(doc, result, base_document_revision, accept)` | §D.8 硬门禁：`status ≠ original_plus_deterministic` 且 `accept=True` ⇒ **抛异常** |

常量：`DEFAULT_DILATE=3` / `MAX_DILATE=24` / `FLAT_TOLERANCE=8.0` /
`FLAT_COLOR_DRIFT_TOLERANCE=10.0` / `MAJORITY_RATIO=0.60` / `MIN_RING_PIXELS=32` /
`RESIDUE_CHANGE_TOL=6` / `GHOST_CORR_MAX=0.50` / `GHOST_CONTRAST_TOL=26.0` /
`ALPHA_EDGE_LOW=8` / `ALPHA_EDGE_HIGH=247` / `RESIDUE_RATIO_FAIL=0.02` /
`PERIOD_TOLERANCE=0.35` / `MAX_PERIOD_LAG=64` /
`QUALITY_TOLERANCES={seam_tol:26, tone_tol:30, structure_min:0.30}` /
`SCORE_WEIGHTS={continuity:.25, tone:.10, structure:.20, emptySlot:.30, texture:.15}` /
`MIN_CANDIDATE_SCORE=0.70` / `CLEANPLATE_SCHEMA_VERSION=1`。

### BE.3 判据为什么长这样（每条都付过代价）
1. **纯色证据取环带「多数簇」**：按整环色散判，指针旁混进秒针红 ⇒ spread 0→26.3，
   纯色填充在「一层压一层」的真实图里**永远**拿不到证据。种子 = 环带中位色，
   `|像素−种子| ≤ flat_tolerance` 的像素占比 ≥ 0.60 才认；再对这个簇自己算色散。
2. **边界连续性比「外圈中位色」**，不是比「围着 mean 的那一簇」：外圈换成完全不同颜色时
   那个色不在簇里 ⇒ drift 恒为 0，「近处是底色、远处是深色背景板」这种最该拦的反而不报。
3. **上下文只排除洞，不排除保护区**：指针压在表盘上时环带几乎全在保护区（要保留的表盘层），
   排除掉环带就空了，指针位置永远修不了。真正不能用的是「洞内待修区域的原始像素」。
4. **碎块必须有归属**：`build_clean_plate` 用「标签非 0」判区域，屏障线穿过的洞像素标签为 0
   ⇒ 被算进「原图保留区」⇒ 以**原主体像素**身份留在 plate 里，且**没有任何计数会露出来**。
   `_claim_strays()` 把无主洞像素并入最近区域；`stats.unlabeledPixels` **恒应为 0**
   （它是可执行断言，不是参考数字）；一个区域都没有时整块当成 `source="stray"` 的 unknown 区域。
5. **空位测试要两条证据**：`ghostCorr`（模糊/淡化复制保留轮廓，系数被推高）+ `regionContrast`
   （补完后区域**主色**与周边背景色的亮度差）。50% 淡化没有 alpha、核心区方差为 0 ⇒
   相关系数必然算成 0，整类「半透明指针」漏检（§3.3 明禁）。容差取 `seam_tol=26.0` 同值，
   避免与接缝判据打架。低对比元素（`subjectPixels == 0`）不参与 ghost 判定。
   `ghostCorr` 只在**该改的像素**上算 —— 整区域一起算会让「白反光贴白表盘」因「没被动过」
   得到完美相关 1.0 被冤枉。
6. 🚨 **「写了」≠「修好了」**：`score_candidate` 曾只要区域被写过就标 `repaired`，
   而 `compose_plate` 只拼 `repaired` ⇒ **没过检的区域被拼进 plate**。state 必须由
   「区域自己的检查（`candidate_quality` + `empty_slot_test` + `repeat_texture_check`）过没过」
   决定；候选分数只对**过检区域**取平均（「修好 1 块、修坏 5 块」不该分高）。
7. 🚨 **验收口径必须由原图定义**：曾用候选自己的 `report["requiredChange"]`（只覆盖它写过的
   区域）验收 ⇒ 没写过的区域被静默漏掉 ⇒「修了一半」报成 `original_plus_deterministic`。
   改为 `empty_slot_test(source, source, removeCore)["requiredChange"]` —— 与空位测试**同源同容差**，
   不可能出现两套口径。
8. **区域「零写入」有两种情形**：① 该改的像素为 0 ⇒ 原样保留就是正确结果（低对比元素）
   ⇒ 标 `repaired` 且计满分、不算缺陷；② 有该改的像素却没写 ⇒ 真待修复洞。
9. **候选只能改 `writeMask`**：`outsideChanged` / `protectedChanged` / `write ∈ hole` 三条各自计数，
   任一非零即不合格。逐区域单独喂 `candidate_quality`（整板一次喂会把别的区域算成越界）。
10. **不修就报待修复，不许编**：`_derive_status` 只看 `checks["ok"]`，**不看**
    `unrepairedPixels`（膨胀边角里值已正确的像素「没被写」是对的）。`unrepairedPixels`
    只作 `stats` 信息项，不进 `issues`。

### BE.4 fixture 探针实测（`output/spike/verify_cleanplate.py`，320×240）
场景 = 纯色平板 + 右侧条纹带（深 5 行/浅 5 行）+ 4 元素：机身 0.80 / 标签 0.90（在条纹带上）/
反光 0.72 / 指示灯 0.95（压在机身上，置信度差 0.15 > `CONTEST_MARGIN` 0.08 才抢得到归属）。

| 场景 | 状态 | 候选 | remove | hole | write | 区域 | 残留 |
|---|---|---|---|---|---|---|---|
| 只移除指示灯 | `original_plus_deterministic` | 2/2 | 256 | 256 | 256 | 1 | 0 |
| 只移除反光 | `original_plus_deterministic` | 1/2 | 800 | 1196 | 1196 | 1 | 0 |
| 指示灯 + 条纹带上的标签 | `needs_manual_repair` | 0/2 | 3256 | 3982 | 256 | 6(+5 待修) | 3000 |
| 移除全部元素 | `needs_manual_repair` | 0/2 | 23400 | 26238 | 22512 | 7(+5 待修) | 3000 |

- 指示灯原位：原图 `(250,96,88)` → clean plate `(58,64,78)`（**机身色**）⇒ §3.3 空位测试通过。
- 条纹带上的标签修不了 ⇒ 明确报 5 个待修复洞（残留恰为标签的 3000 px），**没有**谎报成功。
- 探针 7 条不变量：洞像素全有归属 / `writeMask ⊆ hole` / 洞外零改写 / 保护区零改写 /
  状态与证据一致（确定性⇒`checks.ok` 且 residue=0 且无待修洞；待修⇒**必有**待修洞）/
  待修区域不得标 `repaired` / 保留元素零改写 / §D.8 `accept=True` 门禁。

### BE.5 本机坑
- ⚠️ `split_surfaces._profile_period` 只在 `lag ≤ n/2` 里找峰（n = 掩码覆盖的行/列数），
  且 `num/var` 的归一化使可得分上限 ≈ `(n−lag)/n`（阈值 0.45）⇒ **20×20 的区域量不出周期 16**。
  写「检测周期」的用例，窗口必须 ≥ 2×周期（`RepeatTextureTests` 统一用 60×60 区域）。
- ⚠️ `striped(period=k)` 的**完整周期是 2k**（深 k 行 + 浅 k 行），不是 k。
- ⚠️ `element_ownership.CONTEST_MARGIN=0.08`：同档 + 置信度差 < 0.08 ⇒ 判 unknown。
  构造「A 压在 B 上」的场景，两者置信度差必须**明确跨过** 0.08，否则 A 的 mask 直接为空
  （探针第一版 `removePixels = 0` 就是这么来的）。
- ⚠️ 「纯色证据拿不到」**不能用条纹测**：条纹在局部（只覆盖浅色行的区域）确实是一种颜色，
  那里拿到证据、做常量填充是对的。用**噪声**图测（`noisy()` 助手）。
- ✅ `tests/` 无 `__init__.py` ⇒ 只能 `python -m unittest discover -s tests -p "test_*.py"`。

### BE.6 验证与状态
- `tests/` 全量 **464**（384 → 464，P2 新增 +80）；`test_background_cleanplate.py` **80**；
  `output/spike/verify_cleanplate.py` **ALL PASSED**。
- **P2 完成；P3（前端新编辑器）/ P4（单元素编辑与文字）/ P5（导出 + 删旧实现）未开始**。
- 未打包、未提交 git；`backend/` **仍未入 git**（非本轮引入，见 BC/§6 记录）。

---

## BF. 元素级拆分重构 P3：前端新编辑器（2026-10-16）

> 方案 = 同上 §10（前端信息架构）/ §14 P3。台账 = `output/element-refactor-inventory.md` §11。
> P3 要求原话：新图层栏、单层查看、选中元素属性；拖动/旋转/缩放**不复制像素**；浅色与深色主题同时验收。
> 🚨 §16 仍生效：**未接真实模型 ⇒ 不许宣称功能已恢复**。当前口径只能说「前端新编辑器已落地」。

### BF.1 文件
| 文件 | 行数 | 性质 |
|---|---|---|
| `backend/element_edit.py` | 662 | **新**：单元素变换 / 渲染清单 / 摘要取证 / 空位检查 |
| `backend/element_demo.py` | 261 | **新**：示例文档装配（P3 唯一数据源，零模型/零网络/零磁盘写） |
| `backend/element_document.py` | 758（+92） | **改**：`visible`/`locked`、`set_element_flags`、`reorder_elements`、`DocumentNotFound` |
| `main.py` | 29743（+324） | **改**：9 个新端点 + 4 请求模型 + 4 助手 |
| `static/js/element-editor.js` | 1174 | **新**：`ee-` 前端新编辑器（IIFE，`window.ElementEditor`） |
| `static/css/element-editor.css` | 327 | **新**：`ee-` 命名空间 + 浅/深双主题变量 |
| `static/smart-canvas.html` | 1102（+93） | **改**：CSS/JS 挂载 + 全屏壳 DOM + 入口按钮 |
| `static/css/smart-canvas.css` | +6 | **改**：`.element-split-toggle` 并入既有浮动按钮组与 zoom 列表 |
| `static/js/i18n/smart-canvas.js` | 864（+86 条） | **改**：`smart.ee*` 中英词条 |
| `tests/test_element_edit.py` / `_demo.py` / `_documents_api.py` | 64 / 16 / 34 | **新** |
| `output/spike/verify_element_editor_dom.py` | 860（147 断言） | **新**：端到端 DOM 探针（CDP 真实时序） |

### BF.2 🚨 `ee-` 与 `sl-` 是两套完全分离的东西
- **命名空间 / 数据源 / 写接口 全分离**：`ee-*`（新编辑器 + `/api/element-documents/*`）vs
  `sl-*`（旧拆分图层，**已冻结**，410）。改前端时**先确认在改哪一套**。
- 新增端点：`POST /api/element-documents`（`mode=demo` 装配示例；`mode=analyze` → **501** + `plannedIn=P5`）、
  `GET /{id}`、`GET /{id}/verify`（只读，现算 digests/bounds/structure/emptySlot）、
  `GET /{id}/preview?only=&background=`（PNG + `X-Element-Layers`/`X-Element-Size` 头）、
  `GET /api/element-assets/{id}`（PNG + `X-Element-Asset-Kind`，`no-store`）、
  `POST /{id}/elements/{eid}/transform`、`POST /{id}/elements/{eid}/flags`、
  `POST /{id}/elements/reorder`、`POST /{id}/operations/{op}/undo`。
  §9 里属 **P4/P5 的端点刻意不建**（同 P1 的「没调用方就别建死代码」）。
- 🚨 `POST /{id}/preview?only=<eid>` 是**服务端预言机**：前端「单层查看」必须与它**逐像素一致**（探针核心断言）。

### BF.3 三条工程设计（写死在 `element-editor.js` 头部）
1. **服务端是几何唯一真相**。前端只在拖动过程中用同一套公式镜像 `placedBounds`（`{x,y,scale,rotation}`：
   绕**资产画布中心**顺时针旋转 → 同点等比 scale → 平移）；提交后立刻用服务端返回的数。
   ⚠️ CSS `rotate()` 与 canvas `ctx.rotate()` 正角在屏幕上都是**顺时针**，与 `element_edit.rotate_point` 一致；
   ⚠️ PIL `Image.rotate` 正角是**逆时针** ⇒ 传 `-rotation`。
2. **写接口一律带版本号，409 不吞**。`commitTransform` **无条件**带 `base_element_revision`
   （缺省取刚 GET 到的 `ownershipRevision`）；冲突 → 提示「别处已改过」+ 自动重拉文档，**绝不静默覆盖**。
3. **列表拖拽用 4px 死区的手写 pointer 手势**，不用原生 HTML5 拖放（桌面壳不触发，项目既有红线）。

### BF.4 探针抓到的 4 个真 bug
| # | 症状 | 根因 | 处置 |
|---|---|---|---|
| 1 | 「重做」拉回撤销**之前一步之前** | `doUndo` 存 `{from: item.to, to: item.from}`，方向反了 | 改存 `{elementId, to: item.to}`（端点注释本就写「把 `to` 再交一次 = 重做」） |
| 2 | 棋盘格按钮 `active` 语义与五个视图按钮相反 | `classList.toggle('active', !state.checker)` | 改为 `state.checker` |
| 3 | 拖动路径**没带**版本号 | 拖动走 `commitTransform` 的无 options 分支 | 缺省即取当前 `ownershipRevision` |
| 4 | `textured` 示例报错信号太弱 | 文档级 `status=needs_review` 没显示 | `renderStatus` 把非 `ready/draft` 的文档状态加进 banner |

同时**我的判据错了 4 处**（探针先失败、再发现是我错）：
- 「源图必须不同于合成」→ **反了**：整套系统的目的就是还原原图。改「元素内部逐像素 == 源图」。
- 「对比视图左半是干净底板」→ **反了**：左半是**合成**，只有右半被原图覆盖。
- 变换账本拿**元素版本**比**文档版本** → 两者是独立计数器。改比 `documentRevision`，
  并补查 `operations[].documentRevision == inputRevision`。
- 单点像素比较在「该处本来就没像素」时两边都是 `[0,0,0,0]` ⇒ 恒真假断言 → 改**区域指纹** `regionStat`。

### BF.5 关键硬证据（探针 147/147 ALL PASSED）
| 断言 | 实测 |
|---|---|
| `singleViewMatchesServerOracle` / `singleAfterMoveMatchesOracle` | 前端单层查看 == 服务端 `?only=<eid>` PNG **逐像素一致**（拖动后仍一致） |
| `compositeReproducesSourceAtElements` | 元素内部点：合成 == 源图（重建保真） |
| `dragKeptPixels`/`rotateKeptPixels`/`scaleKeptPixels`/`resetKeptPixels` | 逐元素资产 id + 双 sha256 **全不变** ⇒ **变换不复制像素**的可执行证据 |
| `apiTransformNoAssets` / `apiTransformOpValidatedOnly` | `assetsCreated == 0`；operation 只到 `validated`（**不补齐**没发生过的「预留预算/提交生成」） |
| `analyzeIs501` / `analyzeSaysPlannedP5` | `mode=analyze` 诚实 501 + `plannedIn=P5` |
| `staleWriteConflictShown` / `afterConflictReloadedToLatest` | 陈旧版本写 → 409 → 提示 → 刷最新（**不静默覆盖**） |
| `lightTheme` / `darkTheme` | 面板文字对比 **16.18 / 13.16**；画布亮度 **1.0 / 0.0272**（深灰非纯黑）；选中框 **4.53 / 5.15** |
| `texturedDocStatusNeedsReview` / `texturedEmptySlotNotGreen` | `needs_review` / `needs_manual_repair` / `pendingHoles=4` / `emptySlot.status=="fail"`（**不报绿**） |
| `pageErrors` | `[]`（页面侧零未捕获异常/未处理拒绝） |

`tests/` 全量 **595**（P2 时 464，本轮 +131）；`node static/js/i18n/validate-i18n.js` → `i18n ok: 1584 keys`。

### BF.6 本机坑（P3 新增）
- 🚨 **CDP 驱动的 `Runtime.evaluate` 消息 id 必须全程单调递增**：把计数器放 `cmd()` 内部 ⇒ 每条命令都用 id=1，
  响应错配、恒返回 `None`。计数器必须在 `cmd()` 外部。
- 🚨 **`--dump-dom --virtual-time-budget` 对异步链路不可用**：虚拟时钟让定时器瞬间跑完、dump 早于异步结束
  ⇒ DOM 探针一律 **CDP + 真实时间轮询**（本项目统一用 `document.title === 'PROBE_DONE'` 轮询）。
- 🚨 **探针脚本内联在 `</body>` 之前 = 解析期就执行**：此时 `element-editor.js` 的
  `DOMContentLoaded → bindOnce()` 还没跑 ⇒ 点入口按钮**没有任何监听器**（首跑全崩就是这个）。
  必须先 `while (document.readyState !== 'complete') await sleep(50)`，再断言 `#elementEditor.dataset.bound === '1'`。
- 🚨 **`#elementEditor` 必须挂在 `#shell` 之外**（`#shell` 有 transform，会毁掉全屏 fixed 定位）。
- ⚠️ **`StudioTheme.set()` / `StudioI18n.set()` 会写同源 `localStorage`**（`studio_theme` / `canvas_theme` / `studio_lang`）
  ⇒ 探针切换主题/语言后**必须还原**，否则污染后续会话。
- ⚠️ 元素文档与资产**全在内存**（`element_demo` 零磁盘写）⇒ 探针不污染 `data/canvases/`，但也要记得收尾删 `static/__*.html`。
- ⚠️ **跨测试文件全局污染**：`tests/test_split_bg_reg_api.py` 等在**模块导入时**把
  `main.LEGACY_SPLIT_WRITES_FROZEN` 改成 False 且**不还原** ⇒ 断言该全局的用例必炸。
  本轮新增的 API 测试文件**只查「新 API 挂到 app 上」**，不重复断言冻结开关。
- ✅ 新增文件都在 `backend/`、`tests/`（均在 `tools/release.py:PROGRAM_DIRS`）⇒ **无需改 `ROOT_FILES`**。
  （但 `tools/` 下若加新根目录 .py 模块就要登记。）

### BF.7 已知限制（P3 刻意不做）
- **没接真实图像模型**：`mode=analyze` 返 501。编辑器数据源是 `element_demo.py` 的示例文档，
  界面自报「示例文档：未调用任何模型」。入口按钮**按住 Shift** 打开「有瑕疵」的那份（`needs_review`）。
- **mask 修正 / 提示词生成 / 背景候选 / 导出**：底栏与属性栏**占位并标注 P4/P5**，`disabled` + `title` 写明阶段
  （§16：点不动、也不假装能用）。
- **命中测试按包围盒**，不做 alpha 精确命中（示例场景全是实心块，两者结果一致；
  等 P4 的 mask 修正让元素可能带洞再上）。
- **合成只有 `transform` 四个数**：文字属性（字体/字号/颜色）与 `kind=text` 原生层属 **P4**。

### BF.8 下一步 P4
单元素局部擦除 `POST /{id}/elements/{eid}/mask-correct`、提示词生成与候选
（`POST /{id}/elements/{eid}/generate`、`.../accept`）、文字属性可编辑往返。
`element_edit.py` 里 `EDIT_KINDS` 已预留 `translate`，但 P4 重心是 mask 与生成。

---

## BG. 元素级拆分重构 · P4 交付（2026-10-17，方案 §5/§6/§12/§14 P4）

> 前情 **BC/BD/BE/BF**（P0–P3）。台账细则 `output/element-refactor-inventory.md` §12。

### BG.1 新增模块（三个，纯 PIL / 纯逻辑，零模型调用）

| 模块 | 行 | 对应方案 |
|---|---|---|
| `backend/element_mask.py` | 621 | §14 P4「局部 mask 修正」/ §6「局部擦除和恢复」 |
| `backend/element_generate.py` | 781 | §6 提示词生成 + 候选对比/采纳/拒绝 / §12 生成隔离 |
| `backend/element_text.py` | 1403 | §5.1 拟合与可编辑回退 / §5.2 文案重排 |

端点：`POST .../elements/{eid}/mask-correct`、`.../generate`、`.../accept`、`.../reject`、
`.../text`、`.../text/restyle`；`GET .../candidates`（**不含像素**）、`.../appearance`（只读回验）。
请求模型：`ElementStrokeRequest` / `ElementMaskCorrectRequest` / `ElementGenerateRequest` /
`ElementCandidateRequest` / `ElementTextRequest` / `ElementTextRestyleRequest`。

### BG.2 🚨 P4 与 P3 的红线**不一样**（最容易搞错）

P3 几何操作**一个资产都不建**（红线 = 资产 id + 双 sha256 全不变 + `assetsCreated==0`）。
P4 的涂抹与采纳**必须产生新像素** ⇒ 同一条纪律在这里的正确表述是：

> **没被笔画 / 候选触及的元素不许换资产。**

把 P3 的「谁都不许换」搬过来，会推出「涂抹必须无效」这种自相矛盾的结论。
探针三条落点：`maskIsolationOthersUnchanged` / `generateLeavesOthersUntouched` /
`acceptIsolationOthersUnchanged`。

### BG.3 🚨 四个内核判据（都是踩过坑写死的）

1. **笔画补在全局所有权标签图**，不是单元素 mask。只改单层 ⇒ 原 owner 不让出 ⇒
   两元素共有像素 ⇒ 违反 §12。`erase` 归 **label 0（背景）**而非 unknown（「这块不要」
   = 属于背景最自然，且 clean plate 在原位保留了原图像素）；`add` 必须**从 unknown 摘掉**；
   同批 `erase` 优先于 `add`；笔画按顺序生效。
2. **受保护背景上下文的基准必须是「元素现在的 bbox」**，不是候选自己的 bbox ——
   后者恒成立 ⇒ 检查永远通过 = 等于没检查。这个 bug 真出现过。
3. **`provider_available()` 查 `REGISTRY` 的 key（含 `provider/*` 通配），
   不查「能不能构造出 capability 对象」**：`provider_capability()` 对任何非空 id 都返回对象，
   拿对象存在当通道可用 ⇒ `engine=auto` 永远以为有 provider。`REGISTRY` 当前**故意为空**。
4. **`engine` 诚实的两种分界**：`auto` 默认走 provider → 取不到就记一条 `failed` operation
   并返回 `{ok:false, code:"provider_unavailable", plannedIn:"P5"}`，**元素零改动**；
   `local` 是**显式**确定性候选，标 `engine="local_deterministic"` / `isModelGenerated=false`，
   界面必须写「本地确定性候选（未调用模型）」，**不许叫 AI 生成**（§16）。

### BG.4 🚨 写操作只推进到 `validated`

`split_document.OPERATION_TRANSITIONS` 里 `accepted` 只能从 `candidate_ready` 到达，
而 `validated → budget_reserved → submitted → candidate_ready` 是给**真实模型链**设计的。
本地几何/涂抹/本地候选**没预留预算、没提交过生成** ⇒ 一律只到 `validated`
（`APPLIED_STATE = "validated"`）。用 `operation_advance(op,"accepted")` 会把中间几步
**自动补齐** = 在账本里写下没发生过的事实。候选「就绪/被采纳」记在 **record 自己的字段**上
（`candidateId`/`engine`/`candidateReady`/`accepts`）。

### BG.5 🚨 前端两条硬纪律（探针抓到的真 bug）

- **`api()` 里 200 ≠ 成功**：服务端**有意**用 `200 + {ok:false}` 交回「可预期的业务失败」
  （候选没过闸、文案为空）。只看 HTTP 状态会把它当成功并宣称「候选已就绪」——**假话**。
  正确判据：`response.ok && data.ok !== false`。
- **候选记录的 `color` 是 `{color:[r,g,b], source:'hex'|'named'}` 对象**，不是裸数组 ——
  直接 `.map()` 会当场抛异常（探针 `candidateCardHtml` 抓到）。
- 另：画笔**绑在开启时的元素**上（`state.brush.owner`），切元素必须连笔画一起弃掉，
  否则会把上一层涂到这一层；`Esc` **先退画笔、不关编辑器**；`.ee-brush[hidden]{display:none}`
  **必须显式写**（同 `.ee-banner` 的坑）；底栏两个 P4 按钮在**选中元素被锁**时禁用。

### BG.6 🚨 文字链的诚实分界（§5.1 / §16）

- `editable=True` **只在**「拟合误差 ≤ `FIT_ERROR_MAX`（0.12）**且** OCR 置信度达标**且**
  元素 type 是 `text`」时给出；否则 `fallback="image_layer"` + **逐条 reasons**
  （`no_fit` / `fit_error_too_high` / `low_ocr_confidence` / `not_text_element`）。
- `source="user"`（界面手填文案）**跳过置信度闸**（§4 优先级链首位是「用户修正」），
  但**拟合误差闸不跳**。
- analyze **只写元数据**，两个资产 id 一字不改；响应的
  `appearance.assetsUnchanged` 是这一点的**当场核对**，`appearance.renderBack` 是重排回验。
- 透视**做不到就如实标** `perspective_unsupported`（不默默按 0 处理）。
- **不要**用「OCR 说字体是 Arial」当结论 —— 仍要拟合验证（OCR 的 fontFamily 只作候选首位）。
- 拟合渲染**必须按 128 二值化再比**：`_ink_patch` 若按亚阈值边缘裁剪，墨迹整体偏 1px，
  细笔画 1px 错位能吃掉一半 IoU（表现为误差 0.496 而非 0）。
- 重着色反解前景色时，**解出负值 ⇒ 退回直接用 C**（源图自带 alpha、没混过 B），
  否则 factor 被压到下限、整块变暗。`a < 0.15` 一律原样不动。

### BG.7 验证基线（P4 收尾时）

| 命令 | 结果 |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py"` | **810 全绿**（P3 基线 595 + 44 mask + 59 generate + 78 text + 34 api） |
| `env -u … SL_VERIFY_PORT=9100 python output/spike/verify_element_p4_dom.py` | **70/70** |
| `… verify_element_editor_dom.py`（P3 回归） | **148/148**（原 147，+1「P4 入口不再是占位」） |
| `node static/js/i18n/validate-i18n.js` | `i18n ok: 1648 keys` |

⚠️ 老测试两处随 P4 有意变更：`plannedIn` 不再含 `maskCorrect`/`generate`
（改成断言「**不在**清单里」）；undo 找不存在的 operation 由 **400 改 404**
（`find_operation` 先查再分发，因为涂抹/文字/几何三类撤销语义不同）。

### BG.8 P4 刻意不做 / 属 P5

真实图像生成 provider（`split_providers.REGISTRY` 仍为空）、OCR 通道、背景候选、
PSD 导出、场景理解（`mode=analyze` 仍 501）。
⚠️ 示例文档 `el_text` 是**实心矩形**，`/text/restyle` 会诚实失败
（`writes_protected_context`，真字形排版必然超出 bbox+12px ring）—— **设计如此**，
它就是「不把不达标的东西硬塞进去」的验收点。
⚠️ §16：**不在真实模型和 PSD 回归完成前宣称功能已恢复**。**未打包、未提交 git**；
`backend/` 至今未入 git（`git ls-files backend/` = 0，非本轮引入）。

## BA. Grsai 视频链路：参数域 + 模型清单来源（2026-10-19，从 MEMORY.md 下沉）

### 视频参数域（Apifox 核对：`514679297e0`=minimax-h3，`523334530e0`=agnes-video）
- 端点：`POST /v1/api/generate`（`replyType=async`）+ 轮询 `GET /v1/api/result?id=`。
  🚨 **没有 `/v1/videos`** —— 早期 `minimax-h3` 走通用 `/v1/videos/generations`、
  `agnes-video-2.5` 被 `is_agnes_provider`（只看模型名）抢走打 `/v1/videos`，**两者都 404**。
  ⇒ 拦截必须在 `if is_agnes:` **之前**。
- 公共参数：`aspectRatio / resolution / duration / replyType / images / audios / seed`。

| | `agnes-video-2.5` | `minimax-h3` |
|---|---|---|
| aspectRatio | `16:9 9:16 21:9 4:3 1:1 3:4` | **只认 `portrait` / `landscape`** |
| resolution | `720p / 1080p / 2k` | `480p / 768p / 1080p` |
| duration | 4~12 | 1~15，**1080p 最多 10 秒** |
| images | ≤5 | ≤9 |
| audios | ≤3 | ≤3 |
| 特有 | — | `promptSkill: boolean`（默认 true） |

- 🚨 **条件收窄**：`duration` 上限随 `resolution` 变 ⇒ 写进 spec 的
  `duration_by_resolution: {"1080p": 10}`，按**解析后的分辨率**再收一次。
  只抄「1~15 秒」会把 1080p + 15 秒发出去 → 上游 400。
- 前端同步：`renderVideoDurationControl` 里 minimax-h3 + 1080p → dMax=10；
  `videoModel` / `videoResolution` 切换时都把超长时长收回 10 秒。
- 验证：`tests/test_grsai_video_specs.py`（12 项断言，含比例映射与条件收窄）。

### 模型清单来源（🚨 官网拿不到视频模型）
- `grsai.ai/zh/dashboard/documents/chat` 的 chunk（`1526dcbd4a16e246.js`）「支持模型」
  **只有 32 个 chat+image**（`gpt-image-*` / `nano-banana-*` / `gemini-*`），**零视频**。
- `/documents/video`、`/image`、`/documents` → **Cloudflare 直接断连**
  （`urlopen` 报 `[Errno 2] No such file or directory`，不是 404）。
- ⇒ 启动器**两来源并行**：
  1. 官网 chat chunk（chat+image）
  2. `https://qmy27nhsd9.apifox.cn/llms.txt` → 按行标签 `Grsai图片/视频生成接口` 筛页
     → 各页取 `model:` 参数 `description: |-` 下缩进 ≥17 空格的裸词。
- 🚨 Apifox `.md` 是 **CRLF** ⇒ 正则必须 `\r?\n`（只写 `\n` 时 `blocks=0`，静默空手而归）。
- 🚨 必须过滤哨兵值：`auto / none / default / all / custom`（见 `GrsaiModelListNoise`）；
  否则 `auto` 会被当成模型写进配置。
- 🚨 预算 **50 秒**（该站单请求 TTFB 就 15~16s；llms.txt + 4 页并行实测 ~16s）。
- 🚨 **两来源必须各自 catch**：单文件 exe 首次运行会抛瞬时
  `The SSL connection could not be established`（~300ms 就失败）；共用 `Task.WhenAll` 一个 try
  会把官网清单一起带走（实测 `ok:false / remote_count:0`）。
- 🚨 静态方法不能调实例 `SendLog`（CS0120）⇒ 用 `Action<string>? lastError` 回调。
- 🚨 **单文件 exe 里搜不到字符串是正常的**（程序集被压缩）；验证只能跑
  `--probe-grsai-models`，别用 `utf-16-le` 搜索判断。

### 实测（dist 单文件 exe，2026-10-19 11:24）
```
ok True | remote 32 | apifox 19 | merged 35
agnes-video-2.5: True | minimax-h3: True
```

### 已替换到根目录（2026-10-19 11:38，详见日志 §8）
- 旧版备份 `output/rollback-backup/launcher-exe-20261019/Lochou启动器.exe.20261014-bak`
- 根目录 `Lochou启动器.exe` = dist 版，md5 `ca506eed5030ab10eac7d1c047031368`
- 🚨 **诊断用法**：`Lochou启动器.exe --probe-grsai-models <api_providers.json 副本路径>`
  —— 副本路径是**位置参数**，不是 `--providers-json` 开关；传副本即只读试算合并。
- 回归结论：原样拉取 `merge_added=0`（零覆盖）；人为删两个模型再拉取 `merge_added=2`（自动补回）。

---

## BH. Grsai 参数/清单细节 + 巨石盘点 + 拆分图层调研 —— 从 MEMORY.md 下沉（2026-10-19）

### BH.1 Grsai 生图参数（2026-10-19 核对 Apifox）
- `/v1/api/generate` 用 **`aspectRatio` + `imageSize`(1K/2K/4K，**无 auto**) + `replyType`(json/stream/async)**，不是通用通道的 `size`。
- 比例支持 `auto` + 10 种；**nano-banana-2 系列额外** `1:4/4:1/1:8/8:1`；
- 🚨 **文档没有 `9:21`**（前端 ultratall 会静默失效）⇒ 后端白名单回退到按尺寸反推。
- 🚨 **模型判定必须用「前缀匹配 + 排除斜杠」**：`nano-banana` / `nano-banana-*` 走 Grsai，
  但 RunningHub 的 `nano-banana/text-to-image-official-stable` 含斜杠、走完全不同通道。
- 🚨 **不要硬编码型号集合** —— Grsai 会持续加新模型（`nano-banana-2-lite` 就不在文档里）。
- ⚠️ 曾经两处都硬判断 `== "nano-banana-pro"`，导致 2.1/2/fast 全走错分支 ⇒「4K 无效、auto 无效」。

### BH.2 Grsai 模型清单「自动同步」的真相
- 启动器 `Program.cs:RefreshGrsaiModelsAsync()` **每次启动**就联网抓官方清单并「只增不减」写回
  `data/api_providers.json` ⇒ **已保存通道本来就是自动同步的**。
- 缺的只是 `api-settings.js:RECOMMENDED_APIS` 里那份**新建通道的静态预设**。
- 已补：后端 `GET /api/providers/grsai-models`（读已保存 Grsai 通道）+ 前端
  `syncGrsaiPresetFromSaved()`（在 `loadProviders()` 里覆盖预设）⇒ 上新模型后**不用再改代码**。
- 🚨 web 侧 `/api/providers/{id}/fetch-models` 对 Grsai **无效**（无 `/models` 接口，全 404），只有启动器能拿到清单。
- 🚨 改 `launcher/Program.cs` 要重编 exe；但**不编也不影响**（启动器联网兜底）。
- 🚨 `build-launcher.ps1` 会从 `E:\claude\skill\canvas-launcher\dist` 同步外部资产 ⇒ **别擅自编译**。

### BH.3 「预设」≠「已保存配置」
- `api-settings.js` 的 `RECOMMENDED_APIS` 只影响**新建通道**；**启动器的模型列表页读的是
  `data/api_providers.json` 的已保存通道**。老板说「没变化」时，先确认他看的是哪个界面、读的是哪份数据。
- 启动器联网同步抓的是 **chat 文档页**（只有 chat+image，**不含视频模型**）⇒ 视频模型只能靠**内置清单**，
  而内置清单改了**必须重编 exe** 才生效。
- 重编：`dotnet publish launcher/InfiniteCanvasLauncher.csproj -c Release -r win-x64 --self-contained true
  -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o dist`，
  **跳过 `build-launcher.ps1` 的外部资产同步**（csproj 的 `Content Include="dist\**\*"` 相对 `launcher/`，
  打包 `launcher/dist/`，不需要从 `E:\claude\skill\canvas-launcher\dist` 覆盖）。
- 🚨 验证新 exe：.NET 程序集里字符串是 **UTF-16LE**，用 UTF-8 搜会误判 MISSING；
  查 `launcher/bin/.../InfiniteCanvasLauncher.dll` 更快。
- 🚨 启动器运行中无法覆盖根目录 exe（文件锁）→ 必须先关。
- 🚨 **「只增不减」必须覆盖所有写入路径**：`RefreshGrsaiModelsAsync`（启动时）是只增不减，但
  **「拉取并自动归类模型」返回的是「远端 ∪ 内置」全量列表，前端保存时全量覆盖** ⇒
  联网/内置都没有的模型（视频模型）一拉取就消失。
  已修：`MergeGrsaiModelList(remote, saved)` 增加第三来源**已保存通道的模型**
  （`LoadSavedGrsaiModels()` 读 `api_providers.json` 的 image+chat+video）。
  ⇒ **合并逻辑必须包含「已保存的数据本身」**。

### BH.4 `main.py` 巨石盘点（2026-10-17；2026-10-18 已全回退）
- 盘点对象是**工作区那版**（30144 行 / 228 路由 / 1151 函数 / 100 BaseModel，是 `backend/` 10195 行的 3 倍）：
  `except Exception` 367 处、裸 `except:` 8 处、`raise HTTPException` 645 处 vs `JSONResponse` 7 处（两套风格）；
  7 个全局内存 store；最大函数 `canvas_video` 487 / `run_split_layers_task` 468 / `rollback_update` 416 行。
  ⇒ 方案见 `output/后端代码整理与优化方案-20261017.md`。
- 🚨 **2026-10-18 全部回退**：老板要求「**完全以发布包 1.2.0 为准**」
  （`D:\工作\无限画布\Infinite-Canvas-Full-1.1.4\Infinite-Canvas`），
  当天做的 **6 个 router 拆分（47 路由）** 与 **`read_text_attachment` 重名修复** 已**全部撤销**。
  备份：`output/rollback-backup/full-1.2.0-rollback-20261018/`（main.py 29349 行 + backend 20 + routers 7）。
  ⚠️ **那些经验仍然有效、但代码已不在**：重名缺陷（两版扩展名差 32 种）、`Optional` 类型不能手写、
  `patch.object(main,…)` 对延迟导入仍生效、openapi 逐条核对套路 —— 以后重做直接照用，不必重新踩。
- ⚠️ 发布包**自身不自洽**：`tests/test_canvas_log_cleanup.py` 调 `main.delete_canvas_log`，
  但发布包与备份的 main.py **都没这个函数** ⇒ 该测试本身跑不过。**测试失败 ≠ 运行有问题**。

### BH.5 拆分图层调研成果（代码已回退，结论仍可复用）
- 📚 文档：`output/豆包图像编辑器界面规格-20261017.md` + `output/doubao-reference/`（6 张实测截图）；
  `output/see-through接入方案-20261017.md`；`output/see-through原理对照与拆分元素优化方向-20261017.md`。
- 🚨 **重做时必须带上的一条（See-through 校准，SIGGRAPH 2026）**：
  **「像素归属」做不出可用的层，「层生成」才行** —— 归属观下被遮挡处没像素可分、层天然不完整
  （当年的 `element_extract` = `sourceRGBA × ownershipMask`，零补全 ⇒ 移开露洞）。
  ⇒ 验收 = **每层完整 + 顺序正确 + 移开不露洞**，不是「能拆出 N 层」。
- ⚠️ See-through **只支持动漫角色**（23 个固定部位）⇒ 不能作通用默认通道；本机 16GB 显存刚够、
  模型 13.5GB、**未装 ComfyUI**。
- 🚨 **豆包界面实测结论**：**三层态**（首页 / 图像编辑 / 拆分进度）；
  **元素是"摆出来的"不是列表**（无左侧图层栏，靠彩色名字标签 + 树状连接线 + 圆形 `+` 节点）；
  **无右侧属性面板**（功能在顶部通栏，单元素操作在元素旁浮出胶囊工具条）；
  拆分是**真模型 2–3 分钟 + 百分比 + 可后台退出**。
- 🚨 **抓豆包界面的唯一可行路径**：**用现有已登录 Edge 实例**打开 URL（复制 profile 被
  `Network\Cookies` 排他锁堵死，非管理员也没 VSS）；**先 `keybd_event(0x12)` 按 Alt 再 `SetForegroundWindow`**
  （单调必失败）；`ShowWindow(h,3)` 最大化；截图是**原始像素**、看图会缩放 ⇒ **换算点击坐标必须乘缩放比**；
  `Add-Type` 被安全策略拦 ⇒ 一律用 Python + ctypes。
- ✅ **浅色主题修法**：`split-layers.css` 里舞台区整体是按深色写的（`.split-layers-stage`/`.sl-board-wrap` `#3a3d44`、
  `.sl-stage-bar` `#2f333a`、`.sl-text-bar` `#262a31`、`.sl-mini` `#3b414b`、`.sl-select` `#2b2f38`），
  而窗口/图层栏是浅色 ⇒ 割裂。全部改成「**浅色默认 + `html.studio-theme-dark` 覆盖**」。
  🚨 **最容易漏的一条**：`.sl-sel-name` 是 `#e2e8f0`、`.sl-op` 是 `#94a3b8` —— **配深色底写的浅色字**，
  只改背景不改字色，工具条变浅后文字直接看不见。
  ✅ 两套主题类**同时加**（`smart-canvas.js:1775-1778` 同时 toggle `theme-dark` + `studio-theme-dark`）。
  验证法：提取 `#splitLayersModal` 整块造**静态预览页** + 无头 Edge 截图，浅/深两版对比
  （证据 `output/split-layers-light-fixed.png` / `split-layers-dark-ok.png`）；预览临时页用完必须删。

### BH.6 Agent「掌握全部画布能力」+ 输入框内联胶囊（2026-10-20 下沉自 MEMORY.md）

#### ① 输入框：`<textarea>` → `contenteditable`（为了把附件内嵌成胶囊）
- 垫片 `installAgentInputShims()`（`smart-canvas.js:97`）：`Object.defineProperty(agentInput,'value',{get:agentInputPlainText,set:agentInputSetText})`
  + 同名 `disabled` 垫片。**全项目 20+ 处 `agentInput.value = x` 一处都不用改**。
- 文本 ↔ DOM：`agentNodesToText(root)`（chip → `[节点:标题]`，`<br>/<div>` → `\n`）。
- 光标（contenteditable 没有 `selectionStart`）：`agentCaretRange()` / `agentTextBeforeCaret()` /
  `agentDeleteCharsBeforeCaret(n)` / `agentInsertTextAtCursor()` / `agentPlaceCaretAfter(node)`。
- 状态 ↔ DOM 对账：`syncAgentInlineChips()`（在 `renderAgentAttachments()` 末尾调）；
  `agentRemoveChipByKey(key)`；`agentSyncStateOrderFromChips()` 按**句子顺序**回写状态数组
  （渲染顺序 = 上游基准图顺序，错序 = 改错图）。
- placeholder：contenteditable 不吃原生 placeholder → `data-empty` + `::before`（`agentSyncInputEmpty()` 维护）。
- 🚨 `agentInsertChipAtCaret` **不许无条件 `focus()`**（页面加载补齐胶囊时会抢画布焦点）。
- 🚨 `insertAgentMention` 必须先删用户打的 `@过滤词`（`lastIndexOf('@')` → `agentDeleteCharsBeforeCaret`）。

#### ② 悬停预览：CSS `:hover` 方案在这结构下**天生不可行**
`.agent-input-rich` 是 `overflow-y:auto` ⇒ 绝对定位子元素被裁，z-index 再高也没用
（实测 DOM 量到 158×167、`hasImg:true`，屏幕上完全看不见）。
- 修法：`showAgentChipPop(chip)` 把 `.agent-attach-pop` **克隆进 body 下的 `#agentChipPopLayer`**
  （`position:fixed; pointer-events:none`，防止鼠标移进卡里抖掉）；先量尺寸再定位，
  上方放不下翻到下方，左右不出屏；`hideAgentChipPop()` 清空。
- 绑定用 **document 事件委托**（`bindAgentChipHover()`），因为这段代码在 `smart-canvas.js` 靠后位置。
- 实测：164×184 可见、`naturalWidth>0`、移开后 `childElementCount===0`。

#### ③ canvas_ops 从 5 个扩到 9 个（`applyAgentCanvasOps`，`smart-canvas.js:23406` 附近）
`create_node` / `create_file_node` / `connect` / `update_node` / `remove_node`
+ 新增 `focus_node`（选中 + 视口居中）/ `group_nodes`（建智能分组并收进去）/
`ungroup_node` / `arrange_nodes`（按连线关系排开）。

#### ④ 🚨 核心教训：**提示词治不了「漏给字段」**
实测原样：模型返回 `intent:"canvas"` + `plan:["按连线关系整理画布节点"]` +
`reply:"我会按连线关系把画布节点整理开"`，但 `canvas_ops: []`。它听懂了，字段漏了。
模型对自己漏字段是盲的 ⇒ 必须代码兜底 `deriveCanvasOpsFromIntent(text, reply, intent, plan)`：
- 只在 `intent ∈ {canvas, mixed}`（或 plan 里明确提到整理/归组/对焦）时派生；
- 只派生 **安全、可撤销、无歧义**的三类：`group_nodes`（要求能解析出 ≥2 个真实节点标题）、
  `arrange_nodes`、`focus_node`；
- **建节点 / 改标题这种要具体参数的一律不猜**（猜错比不做更烦）。
派生成功把 reply 的「我会…」改「已…」；派生不出来才把话收回（加「这一步我没能真正执行」）。

#### ⑤ 🚨 `arrange_nodes` 不选节点 ≠ 什么都不做
原实现只看 `selectedNodeIds()`。用户说「有点乱」时**通常什么都没选** ⇒ 静默空转但文案说「已整理」。
改成三级回退：`op.nodes` → 当前选中 → **整张画布**。实测 movedNodes 从 0 变 3。

#### ⑥ 🚨 时态 / 谎称 / 反问，三个确定性兜底（都在 `processAgentLlmResult` 开头）
- **时态**：`canvas_ops.length` 非空时，reply 句首「我会/这就/马上/来/将」→ 「已」。
- **谎称**：`_doneClaim` 正则要覆盖宾语夹在中间的写法
  `已(将|把).{0,12}(动词)`（「已**将两个节点**归为一组」原来抓不到）。
- **反问**：`_asksWhich = /哪一?[张个]|哪个节点|指哪|请选择.{0,12}(图片|节点)/`
  - 有图节点**去重后只有 1 个** → 指代无歧义，直接把追问变 `edit` + `use_last_outputs`（实测通过）；
  - 真有多张但 `options:[]` → 把真实节点标题补成选项（「请选择」却没有按钮比反问更糟）。

#### ⑦ 能力总览与提示词（`agentOrchestrationContext()` / `agentSystemPrompt()`）
- 【画布能力总览】按**意图 → 能力**映射，🖐 标「只能引导不能假装做了」（拆分图层 / 宫格切分 / 图片编辑器 / 超分 / 下载）。
- 「编排四步」三条硬约束：不要等用户说功能名；说了就必须给 op；整理/归组/对焦不许反问。
- 【指代消解】按顺序自己找：当前选中 → 唯一有图的节点 → 最近生成 → 内联 token。
- ✅ 放宽 `_canvasOpTask` 闸门：`_modelAnswered` 为真时**以模型为准**（老逻辑会用关键词冲掉正确结果）。

#### ⑧ 测试方法（下次直接照做）
- 无头 Edge 三要素：独立 `--user-data-dir`；`sessionStorage.setItem('smart_agent_profile_skip','1')`；同源 iframe。
- 🚨 **`agentSystemPrompt()` 必须在造完场景之后取**，否则【画布现状】是空的，
  模型会回「画布目前是空的，找不到节点」（第一次跑就踩了这个）。
- 🚨 **不要驱动完整 `sendAgentMessage()`**（流式 + WebSocket 在无头里卡死）。
  改为：直连 `/api/agent-llm-task` 拿真实输出 → 页面里调 `processAgentLlmResult()`（拦截 `runAgentGenerations` 防花钱）。
- 最硬的一招：**把模型的原样输出字符串直接灌进 `processAgentLlmResult`** ——
  这样测的是「代码兜底」，不依赖网关心情（Grsai 偶发 `completion_tokens:1` 空文本）。
- ⚠️ 测胶囊必须 `page.click('#agentInput')` + `page.keyboard.type()` 造真光标，
  否则走 appendChild 分支，句子顺序会乱。
- ⚠️ 10px lucide 图标在 1x 截图里像小方块，**必须 `deviceScaleFactor:4` 放大**才能判是否渲染。

### BH.7 生图比例「说 3:2 却永远 1:1」的两层根因（2026-10-20）
#### 层一 · 前端：模型不照做
用户原话里的显式比例必须**确定性覆盖**，不能指望模型自觉：
- `parseExplicitRatio(text)`：先抓 `(\d{1,2})\s*[:：]\s*(\d{1,2})`，按 `|log(目标/候选)|` 就近匹配
  `SIZE_MAP` 的 9 个 key，**偏差 >15% 不硬塞**（那是用户在说别的数字）；再匹配中文口语
  （方形/正方形/方图→square，竖版/竖图/竖屏→portrait，横版/横图/横屏→landscape）。
- `applyExplicitRatio()` 在 `parseAgentResponse()` 里对 `prompts` 和 `generations` 统一覆盖。
- 提示词也必须列出 9 个 ratio key（原来完全没提，模型只能瞎猜）。

#### 层二 · 后端（真凶）：精确约分出白名单外的比例
`runninghub_aspect_from_size("3520x2352")` 做**精确约分** → `220:147`，不在 Grsai 白名单里。
上游**不报错、静默按 1:1 出图** —— 前端算对尺寸也没用。
- 修法 `snap_aspect_ratio(value, allowed, tolerance=0.15)`：按 `|log(目标/候选)|` 找最近的白名单值；
  超出 tolerance 返回空。
- `grsai_aspect_ratio()` 里依次尝试 `value` → `derived`（从 size 反推），都不中再以
  `tolerance=1.0` 放宽到「最接近」——**至少保住横竖方向**。退成 1:1 是最差结果：
  用户要竖图，给他方图等于没照做。
- 实测映射：`3520x2352→3:2`｜`2352x3520→2:3`｜`3264x2448→4:3`｜`2160x3840→9:16`｜
  `3840x1648→21:9`｜`1648x3840→9:16`（原全为 1:1）。真实生图验证：请求 3:2 → 出图 **5056×3392**（1.4906）。

#### 🚨 「张数」≠「prompt 条数」
`count` 是**每个方向几张**，条数 = **方向数**。把这两件事混成一句「prompts 只返回 1 条」，
会把用户画像里「先给 2-3 个方向」彻底压死（实测过）。

### BH.8 「出图与上传文件毫无关系」+ 遮罩仍整图重画（2026-10-20，两个独立根因）
#### 根因 A：`[节点:xxx]` 的图从来没进 `reference_images`
用户写 `[节点:上传] …用局部重绘的方式…` 时，节点引用只进了两处**文本**：
prompt 里的 token + `agentNodeRefsContextBlock()` 的说明。
而 `runAgentGenerations` 组装参考图只看三条路：
`gen.direct_refs` / `use_last_outputs` / `use_attachments` —— **画布节点的图一张都没带**。
⇒ 上游完全凭文字自由发挥（座椅照变人物照、车换成别的车）。
- 修法 `agentNodeRefImages(userMsg)`：
  - 从 `userMsg.nodeRefs` 拿节点，但**优先读当前画布 `nodes` 里的最新图**
    （快照是发送那一刻存的，图片可能刚重绘完 / 刚被替换）；
  - 多图节点取第一张（用户说「这个节点」通常指主图），按 url 去重；
  - 在 `runAgentGenerations` 里**插到 refs 最前面**（上游把第一张当基准图）；
  - **`gen.inpaint` 时不加** —— 那时基准图是遮罩裁切图，塞整图会让上游分不清谁是谁。

#### 根因 B：思维模式 `generations → prompts` 转换漏搬 `inpaint` / `target_node`
`processAgentLlmResult` 的思维模式分支要把 generations 转成待确认的 prompts（正常设计），
但只搬了 `ratio / resolution / quality / provider / model`，
**`inpaint` 和 `target_node` 没搬** ⇒ 用户确认后按整图生成。
🚨 只在「思维模式 + 待确认」这条路发作，直连 `/api/agent-llm-task` 完全测不出来。
- 修法：转换时一并透传。**以后新增任何生成参数，都要检查这条转换**（同样问题在重试路径已有先例）。

#### 新增守卫：要局部重绘但画布上没有遮罩 → 不许出图
实测原样：模型 reply 写着「请先涂抹遮罩」，**下面照样冒出一张整图重画**，画面面目全非。
- 在 `processAgentLlmResult` 里命中 `遮罩|涂抹|局部重绘|局部修改|只改这|只修这|这块改…`
  且 `(nodes).filter(validNodeInpaint).length === 0` ⇒
  清空 `prompts / generations / options`，reply 说明**是哪个节点**、点哪里涂、为什么不能整图重画。
- 理由：整图重画冒充局部重绘的代价（原图被覆盖且面目全非）远大于「这轮什么都不做」。
- 顺序有讲究：先跑「有遮罩 → 打 inpaint 标记」，再跑这条拦截，两者互不误伤。

#### 验证方法（真实链路，可直接复用）
1. **遮罩要先造**：用随包 Python 画一张与原图同尺寸的黑底白块 PNG（`./python/python.exe` 有 PIL，系统 Python 没有）。
2. 上传：页面里 `uploadCroppedBlob(new File([bytes], 'mask.png', {type:'image/png'}))` → 拿 url。
3. 真实准备：`POST /api/image-mask-prepare`，入参 **`image_url` + `mask_url`**
   （⚠️ 不是 `/api/inpaint/prepare`，那个不存在）。
   返回 `crop_url / crop_mask_url / bbox / aspect_ratio / size / feather`。
4. 造节点：`node.inpaint = {...返回, base_key: base_url, index: 0}`，用 `validNodeInpaint(node)` 确认有效。
5. 拦截 `window.fetch` 抓 `/api/canvas-image-tasks` 的 body，断言：
   `operation === 'inpaint'`、refs 第一张是 `crop_*`、第二张是 `mask_*` 且 `role === 'mask'`、
   `size` 跟裁切走（不是界面默认）。
6. 拦截 `pollSmartCanvasTask` 返回空 → 不回贴、不花钱。

### BH.9 局部重绘回贴的三条转换链 + 回贴静默降级（2026-10-20，从 MEMORY.md 下沉）
详细过程见 `2026-10-20.md §12 / §13`。这里只留**代码位置与判定法**。

**① `inpaint` / `target_node` 的三条转换链（少补任一条 = 白改）**
| # | 位置 | 作用 | 症状 |
|---|---|---|---|
| 1 | `generations.map`（`smart-canvas.js` L28083 附近） | 模型 JSON → 内部结构的**主通道** | 所有路径都丢 |
| 2 | 思维模式 `generations → prompts`（L28420 附近） | 思维模式待确认 | 只在思维模式发作 |
| 3 | **`_triggerGenerationsIfAllDone`（L29241 附近）** | **「点确认」的唯一出口** | **老板截图踩的就是这条** |
统一要求：`inpaint` 为真时**强制 `count=1`、不带 ratio**（尺寸跟遮罩裁切走）。

**② `agentPickInpaintTarget(userMsg)` 四级优先级**（必须放**顶层**，写进 `processAgentLlmResult`
体内会让 `agentResolveInpaintTarget` 调不到 —— 那个函数从 L28193 到 L28653）：
① 本轮 `nodeRefs` 的遮罩节点 → ② 当前选中 → ③ 画布唯一遮罩 → ④ 原话唯一点名；多遮罩无指向 → `null`。

**③ 回贴被静默跳过的判定与修法**
- 判据链：`save_ai_image_to_output` 下载上游图失败 → **原样返回远程 URL** →
  `output_file_from_url()` **只认 `/assets/` 与 `/output/`** → 返回 `None` → `compose_inpaint_result`
  判「素材缺失」直接跳过 → 用户拿到未回贴的局部图（尺寸不等于原图）。
- 日志特征：`保存上游图片失败: ; url=https://...`（**消息为空**）+ `[inpaint] 回贴素材缺失 ... gen=False`。
- 修法：`_ensure_local_asset(url)` 在 `compose_inpaint_result` 入口先落盘远程 URL；
  回贴真失败打 `⚠️ 回贴失败，已退化为未合并的局部结果`。

**④ 验收基准（别用肉眼看）**
- 输出尺寸 **== 原图尺寸**；
- `ImageChops.difference(base, merged).getbbox()` 必须**落在遮罩 bbox 内**；
- 把遮罩区涂黑后 `difference(...).getbbox() is None`（遮罩外像素完全没动）。

**⑤ 两个容易误判的坑**
- `inpaint_composite` 有羽化（`inpaint_feather_for_bbox`）+ LANCZOS 重采样 ⇒ **alpha=255 处也未必纯色**
  （实测 (217,67,216) 而非 (255,0,255)），别按纯色断言。
- 老板常涂**描边式**遮罩（实测只有 18.6% 不透明、中间 81.4% 透明），
  采样点必须落在**不透明像素**上，否则会误判「回贴没生效」。
- `canvas-image-tasks` 的状态是 `succeeded` / `failed`，**不是 `done`**。

### BH.10 自动遮罩：没涂遮罩时由理解模型出框（2026-10-20，从 MEMORY.md 下沉）

**结论先行**：后端**一行没改**。局部重绘的入口本来就是「一张 mask PNG」，
自动遮罩的全部工作量 = 在 `POST /api/image-mask-prepare` 之前把那张 PNG 造出来。

```
mask.png（人手涂 / 模型自动造，两者完全等价）
  → /api/image-mask-prepare  算 bbox / 扩标准比例 / 裁 crop + crop_mask / 出 overlay
  → node.inpaint
  → runAgentGenerations（operation:'inpaint'）
  → build_online_image_result 回贴
```

#### 必须先补的前提：理解模型看不见 @引用节点的图
- `agentNodeRefsContextBlock()`（约 L26968）只给模型**文字**：
  `[节点1]「上传」type=image 位置(x,y)` + `该节点有 1 张图：/assets/xxx.png`（一串 URL 文本）。
- 图本身只经 `agentNodeRefImages()`（约 L29526）进了**生图接口**的 `reference_images`。
- `contextImages`（约 L28904 / L29123 两处）只拼 `attachments + agentLastResults + agentLastUserAttachments`，
  **不含 nodeRefs**。⇒ 模型没见过那张图，就判断不了「这只猫在哪」，给不出 bbox。
- 修：`agentAppendNodeRefImagesToContext(contextImages)`，两处都调用。

#### 数据流：mask_hint（0~1 归一化 bbox）
模型输出在 `generations[]` 的每一项上：
```json
{"prompt":"把这只猫换成柴犬","mask_hint":{"target_node":"上传","bbox":[0.05,0.45,0.4,0.5]}}
```
- `bbox` = `[x, y, w, h]`，相对**原图**左上角，全部 0~1。
- **不要求**模型同时写 `inpaint:true` —— `agentApplyMaskHintInto()` 会自动置上。
  （教训：多一个必填字段就多一处漏搬，BH.9 里的三条转换链就是这么漏掉的。）

#### 四条转换链都要搬 `mask_hint`（跟 BH.9 同构）
| # | 位置 | 说明 |
|---|---|---|
| 1 | `generations.map`（约 L28089） | 模型 JSON → 内部结构主通道 |
| 2 | `normalizePrompts`（约 L25152） | prompts 侧归一化 |
| 3 | 思维模式 `generations → prompts`（约 L28517） | 确认轮次 |
| 4 | `_triggerGenerationsIfAllDone`（约 L29307） | **点确认的唯一出口** |

#### 校验：宁可不出框，不要瞎框
`agentNormalizeMaskHint(raw)` 只做**严格**校验，其余一律 `null`：
- 必须 4 个有限数；`w/h > 0.002`；
- 0~100 百分比容错 → **判据是四个值全都 ≥1**。
  🚨 只判「有值 >1」会把 `[1.5,0.2,0.3,0.3]`（越界的归一化值）当百分比，`1.5/100=0.015` 反而合法 ⇒ 凭空造错框。
- 越界直接 `null`；略微溢出时裁进画面。

#### 造 mask 的语义（别搞反）
`inpaint_mask_bbox()` 取的是 **`>=128`（白）** 像素的包围盒。
所以自动 mask = **黑底 + 白色矩形**（硬边，不羽化）。
🚨 在 mask 里就糊会让白像素外溢、bbox 被撑大，回贴范围跟着变大 —— 那不是「只改这块」了。
柔化交给后端 `feather`（`inpaint_feather_for_bbox`）。

#### 目标节点选择（只认唯一匹配）
`agentPickAutoMaskNode()`：`mask_hint.target_node` → 引用节点 → 当前选中 → **画布上只有一个图片节点**。
多图且指名不清 → 返回 `null`（不乱猜），走失败路径。

成功后**必须回写 `gen.target_node = node.id`** —— `agentResolveInpaintTarget()` 靠它唯一命中，
否则画布上若有别的节点也带遮罩，会挑错那张。

#### 调用时机
`agentAutoMaskGenerations(gens, userMsg)` 必须插在 `runAgentGenerations` **建占位节点之前**：
那一步就要靠 `agentResolveInpaintTarget(gen)` 判定「走 inpaint 原地改」还是「新建节点」。
晚了就变成「标了 inpaint 却找不到目标」直接报错。

#### 失败路径 = 硬规矩
造不出来（没图 / 定位不到 / 上传失败 / prepare 非 200）→ 该条 `status='error'` +
**撤掉 `gen.inpaint` 与 `gen.mask_hint`**，文案引导手动涂抹。
🚨 **绝不静默退回整图重画** —— 那正是 BH.9 修掉的老毛病。

#### 守卫要开口，但只认「校验过的」
`processAgentLlmResult` 里「没遮罩就不出图」的守卫：
```js
const _autoMaskReady = (parsed.generations || []).some(g => agentNormalizeMaskHint(g?.mask_hint));
if(!_maskedNow.length && !_autoMaskReady){ ...拦住... }
```
🚨 判据必须是**校验过**的 hint，不能是「模型说它有」：瞎填越界 bbox 时放行 + 后面造不出遮罩 = 又整图重画。

#### 顺手修掉的老遗留
`applyExplicitRatio(list, ratioKey)` 在 `generations.map` **之后**跑，会给**每一条**设 `ratio`，
把刚 `delete` 掉的 inpaint ratio 又加回来。现在 `if(item.inpaint) return;`。

#### 验收基准（2026-10-20 实测 33/33，pageErrors 0）
- 测试图 1600×1000，目标物归一化 `[0.05,0.45,0.25,0.35]`
- mask：尺寸 == 原图；框内 255、框外 0
- `node.inpaint`：`bbox=[62,450,437,350]`（扩到 5:4 后覆盖目标 400×350）、`size=1520x1216`
- 请求体：`operation:'inpaint'`、`reference_images=[crop, mask]`、`size=1520x1216`（**不是 1024×1024**）、
  `inpaint.base_w=1600 / base_h=1000`

#### 已知局限（要跟老板讲）
视觉模型给的是**矩形**，不是物体轮廓 ⇒ 框内背景也会被重绘。
精确到轮廓需要分割模型（SAM），本地没装，且 HuggingFace 通道已按老板要求彻底移除，不建议为它加回来。

### BH.11 给 Agent 加字段的「三处必改」+ 失败不删老板节点（2026-10-20）

**背景**：老板报「似乎仍然没能自动调用遮罩」，截图错误 = 「找不到要局部重绘的节点（遮罩可能已失效或对不上）」。
根因不是自动遮罩代码坏了，而是**模型根本没拿到 `mask_hint` 这个字段的说明**。

#### 一、Agent 的两套输出契约（改任何字段都必须同时对齐）
| 契约 | 位置 | 谁在用 |
|---|---|---|
| 思维模式（内联在 `agentSystemPrompt()`） | L27779 `【输出格式 / Output Format】` | `thinkingMode` 开 —— **老板默认走这套** |
| 直接模式 `AGENT_FORMAT_INSTRUCTION` | L25060 | `thinkingMode` 关 |
| 直接模式 `AGENT_OFF_MODE_INSTRUCTION` | L25120 | 同上（补充说明段） |

🚨 **铁律**：新增字段 = ①思维模式内联 schema ②`AGENT_FORMAT_INSTRUCTION` schema ③解析后的**顶层兜底**。
只改直接模式 ⇒ 老板走思维模式时模型严格按 schema 输出，字段永远不会出现（本轮就是这么翻车的）。

**顶层兜底写法**（模型常把该写在每条 prompt 上的字段放到顶层）：
```js
if(data.mask_hint){
    [...generations, ...prompts].forEach(item => {
        if(item && typeof item === 'object' && !item.mask_hint) agentApplyMaskHintInto(item, data.mask_hint);
    });
}
```

#### 二、`mask_hint` 的完整链路（局部重绘自动遮罩）
```
模型 prompts[{inpaint,mask_hint:{target_node,bbox}}]
  → parseAgentResponse（L28279 每条 gen / L25304 normalizePrompts / L28830 思维模式互转 / L29634 确认出口）
  → runAgentGenerations L29942 agentAutoMaskGenerations
      → agentApplyAutoMask：agentBuildMaskBlob（黑底+白矩形）→ uploadCroppedBlob
        → POST /api/image-mask-prepare → node.inpaint{auto:true}
      → 🚨 必须回写 gen.target_node = node.id（agentResolveInpaintTarget 靠它唯一命中）
  → payload = agentInpaintPayload(...) ⇒ operation:'inpaint'
```
- 造不出来就 `gen.status='error'` + 撤掉 inpaint/mask_hint，**绝不退回整图重画**。
- `agentNormalizeMaskHint` 的百分比容错判据：`nums.every(v => v >= 1 && v <= 100)`
  —— 只判「有值 >1」会把 `[1.5,0.2,0.3,0.3]` 误当百分比（除以 100 反而合法）⇒ 凭空造错框。

#### 三、🚨 失败时绝不能删老板的节点
`runAgentGenerations` catch 原来无脑 `nodes = nodes.filter(n => n.id !== placeholderId)`。
局部重绘时 `placeholderId` 就是**用户自己那个节点**（`ipTarget.node.id`）⇒ 上游一报错，原图节点直接消失。
`recoverAgentGenerations`（刷新后恢复）的 catch 同病。统一改成：
```js
if(gen._inpaintNodeId){ liveNode.pending = 0; liveNode.runTimerHidden = true; }
else { undoSuppressed = true; nodes = nodes.filter(n => n.id !== placeholderId); undoSuppressed = false; }
```

#### 四、验证手法（可复用）
- **真实模型探针**：`agentSystemPrompt()` 断言含字段 → POST `/api/agent-llm-task`（`thinkingMode:true`）
  → 轮询 ≥300s → 原始返回 → `parseAgentResponse()` 走真实管线 → 断言 `prompts[0].mask_hint`。
- **确认链路 e2e**：直接构造 `agentState.messages=[user, assistant{prompts:[{status:'confirmed',inpaint,mask_hint}]}]`
  → `_triggerGenerationsIfAllDone(msg)`。
- 🚨 拦 `/api/canvas-image-tasks` 必须 **reject**（`Promise.reject(new Error('__stub__'))`）；
  用 `new Promise(()=>{})` 会让 `Promise.all` 永挂，页面 evaluate 超时。
- Grsai chat 慢：简单「OK」19s，9KB system prompt + 图 2~4 分钟，偶发 `Server disconnected`。
  puppeteer `protocolTimeout` 要放到 300000。

### BH.12 输入框胶囊 ↔ 对话记录胶囊 + 浮层幽灵卡（2026-10-20）

#### 一、🍥 「克隆到 body 的浮层」必须跟着源元素一起清
`#agentChipPopLayer`（`position:fixed; pointer-events:none`）用来放悬停预览卡，
**因为 `.agent-input-rich` 是 `overflow-y:auto`，绝对定位子元素会被裁掉**。
坑：源胶囊被 `remove()` 后**不会触发 mouseout**（元素已不在文档树）⇒ 克隆卡永久留在层里，
用户还点不到它（`pointer-events:none`）⇒ 只能刷新页面。

必清的三处 + 一处兜底：
| 位置 | 为什么 |
|---|---|
| `agentRemoveChipByKey` | 点 × 删附件（老板截图就是这条） |
| `syncAgentInlineChips` | 状态变了，所有已克隆的卡都过期 |
| `renderAgentMessages` | 整表 `innerHTML` 重建 |
| `document pointermove` | 兜底：`agentChipPopOwner && !agentChipPopOwner.isConnected` → 清 |

> 通用规律：**凡是 `appendChild` 到 body 做浮层的，都要有 owner 引用 + isConnected 兜底。**

#### 二、对话记录 = 输入框（靠 token 还原，不靠数组顺序）
- 发送时 `msg.text` 里已带 `[图:名]`/`[文件:名]`/`[节点:标题]`：
  `agentNodesToText()` 读 `chip.dataset.chipToken`；`agentInput.value` 是 contenteditable 垫片
  （`installAgentInputShims`），取到就是这段带 token 的纯文本。
- `agentMsgTextHtml(msg)`：`AGENT_MSG_TOKEN_RE` 扫描 → 命中就用 `agentChipInnerHtml`
  造同样的胶囊（`{removable:false, skill:false}`），**位置/顺序/样式与输入框天然一致**。
- 🚨 **不要按 `msg.images/documets/nodeRefs` 的数组顺序重拼** —— 那是添加顺序，
  用户可能把胶囊插在句子中间，重拼会丢语义位置（「把 [图:A] 换成 [图:B] 的风格」直接读不出来）。
- 兜底：无 token（老消息）或条目已被裁掉 → 剩余 chips 补在 `.agent-msg-chips`；
  匹配不到的 token 渲染成 `.is-detached`（虚线 + .65 透明），只显示名字。
- 🚨 `msg.nodeRefs` 以前**历史里完全不渲染**，现在补上了（"无法完整回溯"的大头）。
- 历史胶囊可点：doc → `openAttachmentItem`；ref → `selectedId` + `focusNodeInViewport()`。
- 悬停委托范围：`#agentInput, #agentMessages`；两个容器都要挂 `scroll → hideAgentChipPop`。

#### 三、验证
- 一次性画布 + puppeteer，**15/15 PASS / pageErrors 0**：顺序 `['att','ref','doc']`、
  无 ×、有 pop、气泡无 token 字面量、老消息补齐、删附件后浮层立刻空、重渲染后浮层空。
- 目视：`output/attach-history-preview.png`（白胶囊 + 深色气泡，ref 虚线、doc 图标高亮）。
- ⚠️ 测试写法：`agentInsertTextAtCursor()` 内 `focus()` 会把 caret 拉回开头
  ⇒ 插胶囊前必须自己 `range.selectNodeContents(agentInput); collapse(false)`。

---

### BH.13 Agent「执行记录」——回答「你是怎么做的」只能靠记录，不能靠画布现状

**症状**：老板问「是不是用遮罩局部重绘的」，Agent 答「当前画布中无法确认是哪一种处理方式」。

**根因**：`agentHistoryMessages()` 给模型的 assistant 历史只有 `[generated N image(s) with prompt: ...]`，
**做法/目标节点/遮罩/尺寸/成败一个字都没有**。模型只能看画布现状（节点上现在有没有遮罩），
而遮罩会迁移到新图、被清掉、被用户重涂 ⇒ 现状 ≠ 当时做法。

**四件套（缺一不可）**
| 位置 | 内容 |
|---|---|
| `runAgentGenerations`（`_ipMeta` 就绪、`throw` 之后） | 落 `gen.exec = {mode:'inpaint'\|'full', target, target_id, mask_bbox(像素), size, refs, model, ts}` |
| `agentExecRecordLine(gen, idx)` | 渲染 `[执行记录 #N] 遮罩局部重绘 · 目标节点「X」 · 遮罩框 … · 输出尺寸 … · 模型 … · 成功出图 N 张`；老记录无 `exec` → 从 `target_node`/`_inpaintNodeId` 反查标题 |
| `agentHistoryMessages()` | 把该行拼进每条 assistant 历史（`g.exec \|\| g.inpaint \|\| status==='error'`） |
| `agentSystemPrompt()` | 注入【执行记录 / Execution Log】：照记录直答、🚨 禁止拿画布现状反推、🚨 禁止答「无法确认」 |

**同一类问题的另一半：画布动作**。`agentRecordCanvasOps(msg, ops, applied)` → `msg.ops` / `msg.opsApplied`，
历史里渲成 `[画布动作] add_node(x)、connect(y)（生效 N 条）`。
🚨 **4 处 `applyAgentCanvasOps` 调用点必须全接**：思维模式主路径 / `canvas_op` 分支 / `text_only` 分支 /
**生图意图分支**（最容易漏：看着「反正要出图了」，但 `canvas_ops` 是独立执行的）。

**通用规律**：凡「用户会追问『你刚才怎么做的』」的自动行为，都要**在执行时留结构化记录**，
并同时 ①进历史 ②进系统提示词 ③在 UI 上标出来。靠事后反查现状一定翻车。

---

### BH.14 同名节点 → 局部重绘必然失败（2026-10-20）

**症状**：`将女人换成小女孩` → 红字「找不到要局部重绘的节点（遮罩可能已失效或对不上）」，
而 Agent 自己上一句还写着「请先在「上传」节点上涂遮罩」。

**真模型复现**：7 个节点都叫「上传」时，模型其实**给了** bbox，但
`target_node:"上传"` 在 7 个同名节点上无法唯一命中 ⇒ `agentPickAutoMaskNode` 按
「只认唯一」的规矩返回 null ⇒ 报错。

**根因（两条）**
1. `agentOrchestrationContext()` 的画布现状**只给标题不给 id**（引用块同样）⇒
   模型没有可写的唯一标识，只能写标题；标题重复就死。
2. 模型有时只标 `"inpaint":true` 不给 `mask_hint`（按提示词「拿不准就让用户涂」），
   而代码按局部重绘去找目标 ⇒ **提示词与代码自相矛盾**。

**修法**
| 位置 | 改动 |
|---|---|
| 画布现状 / 引用块 | 每行加 `id=<node.id>`；提示词改成「target_node **写 id**，标题只在唯一时可用」 |
| `agentCleanNodeRef()` | 剥 `#` / `id=` / `节点=` / 引号 |
| `agentPickAutoMaskNode` | 标题命中多个时，用 `userMsg.nodeRefs` 消歧（原来是直接放弃） |
| `agentExplainInpaintMiss()` | 失败文案点明「画布上有 N 个都叫「X」」+ 两条出路；唯一候选时**自动选中并聚焦** |
| `agentAutoMaskGenerations` | 失败**不再 `delete gen.inpaint`**（删了重试就变整图重画） |

**验证**：改后真模型返回 `target_node:"up_2"`（id）；`__samename_test.js` 17/17 PASS。

> 通用规律：**凡是让模型「指定某个节点」的地方，都必须给它唯一 id**。
> 只给标题在单人测试画布上看不出问题，一进真实画布（大量同名「上传」「Image」）就必炸。

---

### BH.15 复制节点 → 粘贴 = 「发送至 Agent」（2026-10-20 老板要求）

**变更**：以前 Ctrl+C 复制画布节点、粘到 Agent 输入框会变成 `[节点:标题]` 引用胶囊；现在**取消**，
改成**等同于点节点工具栏的「发送至 Agent」**——图片/视频进参考图附件，文档类进文档附件。

| 位置 | 改动 |
|---|---|
| `agentSendNodeToAgent(node, index)` | 新增，唯一实现；内部自己 render + save，返回**给用户看的提示语**（空串=不提示） |
| 节点工具栏 `sendToAgent` 分支 | 改成一行调用它（原来内联 40 行） |
| `agentInput` 的 `paste` 分支 ② | `agentAddNodeRefs()` → 循环 `agentSendNodeToAgent()`；多节点去重提示 |
| `paste` 新增 ②' | 剪贴板带 `【画布节点】` 标记但 `nodeClipboard` 已空（刷新过页面）→ 拦下并提示重新复制 |

**顺手修的坑**：`mediaKindForItem()` 只认 `item.kind`，**没有 kind 字段的附件条目会被当成图片**
塞进参考图（PDF 当参考图必报错）。在 `agentSendNodeToAgent` 里按扩展名兜底，
只对 pdf/docx/xlsx/pptx/zip/rar/7z/txt/md/csv/json/srt/vtt 降级成 `file`；
🚨 **不动无扩展名的 URL**（可能是图片，误判更糟）。

**保留**：`agentAddNodeRefs()` / `agentNodeRefFromNode()` 无调用点但**没删**（`agentState.nodeRefs`
在老消息 / 引用块 / 历史胶囊里仍在用，将来做显式引用入口可直接复用）。

**验证**：8/8 PASS（粘贴→参考图 1 条、`nodeRefs` 仍为 0、输入框是 `att` 胶囊、无 `[节点:` 残留、
重复粘贴去重、工具栏仍生效、非图片进文档附件）。

---

### BH.16 上游报错要翻成人话（2026-10-20 老板截图）

**症状**：卡片红字直接显示上游原始 JSON：
`GPT-Image-2 编辑接口 /images/edits 调用失败: {"error":{"message":"非常抱歉，该提示可能违反了我们的内容政策…","code":"content_policy_violation"}}`

**根因**：`main.py` 的 GPT-Image-2 edits 失败分支（约 L15659 / L15675）**没走**
`friendly_image_error_detail()`，把原始 body 直接拼进 detail。项目里早就有这个翻译函数。

**改法**
1. 两处 raise 先过 `friendly_image_error_detail(edit_failed_text, size, model)`，翻不出来才回落原文。
2. 🚨 **传未截断的原文**：`code:"content_policy_violation"` 在 300 字之后，先 `[:300]` 再判断
   ⇒ 永远识别不出来（这是「明明有翻译函数却没生效」的隐藏原因）。
3. `friendly_image_error_detail()` 内容审核分支加中文关键词（`内容政策`/`违反了我们的`/`该提示可能违反`）
   与 `moderation_blocked`；文案要说明「**不是画布或遮罩的问题**，原图和遮罩都还在」+ 常见触发 + 建议。
4. 前端 `.agent-gen-error-text`：`white-space:pre-line` + 红色（浅/深主题各一套），error 截断 160 → 400。

> 通用规律：**任何 `raise HTTPException(detail=f"...{raw}")` 都要先过一次翻译函数**；
> 且**先判断后截断**，反过来会把判据截掉。

### BH.17 重编辑历史对话：回退记忆 / 修改记忆（2026-10-20）

**两个动作，两个按钮，别合并**：
- `保存并重新生成` = 回退 → `agentResendMessage(msg, newText)`
- `仅保存` = 改记忆 → 只更新 `msg.text / images / documents / nodeRefs`，后面消息不动

**函数位置**：`agentTokenNamesIn` / `agentEntriesAfterEdit` / `agentBeginEditMessage` /
`agentCancelEditMessage` / `agentReadEditArea` / `agentResendMessage` 全部紧挨在
`agentRetryMessage`（~L27833）前面；事件绑定在 `renderAgentMessages()` 内 `[data-agent-retry]` 之后。

**`agentEntriesAfterEdit` 的规则**（附件与正文 token 绑定）：
- 老正文里有 `[图:x]` → 新正文里还有才保留
- 老正文里**没有** token（胶囊挂在气泡下那种老数据）→ **一律保留**，绝不吞

**两条硬坑**：
1. 🚨 `renderAgentAttachments()` 内部会调 `syncAgentInlineChips()`，**按 agentState 把附件胶囊补回
   输入框**（还带尾随空格）。所以写输入框正文必须在它**之后**。顺序反了 → `[图:xxx]` 又被插回来，
   看着像 token 没清掉。（`agentInsertChipAtCaret` 无光标时就是 append 到末尾 + 一个空格。）
2. 🚨 重发必须绕开输入框（`agentResendCtx` + `if(!_rs) agentSyncStateOrderFromChips()`）：
   `agentSyncStateOrderFromChips()` 按「输入框里现有胶囊」**重建**三组附件数组，重发时输入框是空的 ⇒ 附件全丢。

**`agentRetryMessage` 已复用同一条链路**，所以「重试」也不会再丢参考图了（老 bug）。

**验证**：`__editmsg_test.js` 28/28 PASS（脚本归档在 `output/_tmp-cleanup-20261020e/`）。

**CSS 权重坑（BH.17）**：`.agent-msg.is-editing{max-width:100%;align-items:stretch}` 会被后面的
`.agent-msg.user{align-items:flex-end}`（同权重 0,2,0、位置更后）盖掉 ⇒ 编辑框只剩内容宽（387px）。
必须写 `.agent-msg.user.is-editing`，并给 `.agent-msg-edit` 补 `width:100%;box-sizing:border-box`。

### BH.18 「思考模式还是直接失败」= 缺事实 + 失败没有出口（2026-10-21）

**现象**：参考图 4096×4096 → agent 照 4K 出 → gpt-image-2 报「不支持当前尺寸」，卡片只留一行红字。

**根因三层**：
1. `genResolution` 默认 `4k`，`SIZE_MAP.square['4k']='4096x4096'` = 1677 万像素 > gpt-image-2 的 829 万上限。
2. `normalize_gpt_image_2_size()` 早就有（4096²→2880²），但**只被在线生图的默认值用过**，
   `create_canvas_image_task` 没调 ⇒ 必然失败的请求被照发。
3. `gen.error` 只是红字，**模型不参与善后**（下一轮它根本不知道失败过）⇒ 谈不上应变。

**四道修法（缺一不可）**：
| 层 | 位置 | 作用 |
|---|---|---|
| 前端护栏 | `agentGuardGenSize()` + `runAgentGenerations` 出图前 | 超限等比压到 ≤3840/≤829万（16 对齐），写 `gen.sizeNote` |
| 后端护栏 | `guard_size_for_model()` + `create_canvas_image_task` | 同一算法兜底，task 回 `size_requested/size_used/size_note` |
| 事实注入 | `agentOrchestrationContext()` 的【可用生图能力】 | 逐个模型标上限，模型才可能自己选 2k |
| 行为规则 | `agentSystemPrompt` 的「第二步 · 定能力」 | 出图前**自检三件事**；改不了就**开口问**（options 给 2-3 个方案） |

**失败出口**：`agentGenCardHtml` 的 `[data-agent-ask-fix]`「让 Agent 想办法」→ 把 error + 原 prompt
带回输入框（**只填不发**）→ 用户点发送后模型出方案。
🚨 **别做「失败自动重规划」**：多一轮 LLM（Grsai 2-4 分钟）+ 花钱；也**别对确定性错误弹窗问用户**，直接修。

**两条一致性红线**：前后端压缩算法必须同结果（2880×2880）；护栏**只对已知上限的模型**生效
（nano-banana 真能吃 4K，压了就是降质）。

**验证**：后端单测 8 例 + 接口实测 3 例；前端 `__sizeguard_test.js` 23/23；回归 `__editmsg_test.js` 28/28。

**官方尺寸表（2026-10-21 老板提供文档）—— 覆盖 gpt-image-2 / -vip / -2.5 / -2.5-flare / -2.5-sunburst**：
这家族的「4K」**不是 4096**，1:1 的 4K 就是 **2880×2880**（≈829 万像素封顶）。
前端 `GPT_IMAGE_FAMILY_SIZES` + `gptImageFamilySize(ratioKey, resolution)`，`runAgentGenerations` **先查表**再回落 `apiImageSize`。
🚨 套通用 `SIZE_MAP` 会算出**非官方值**：3:2 的 4K→3520×2352（官 3504×2336）、4:3 的 2K→2048×1536（官 2304×1728）。
🚨 `1:3`/`3:1` 官方只有两档 → index clamp。
🚨 文案必须写**真实模型名**（`gpt_image_2_size_error_message(size, model)`），写死 "GPT-Image-2" 会让老板以为认错模型。
🚨 编排上下文口径：「4K 档 1:1=2880×2880，**直接填 4k**，别自己换算成 4096」——
   写「4096 会被拒」反而让模型不敢填 4k。

## BH.19　纯提问 ≠ 生图需求（2026-10-21）
🚨 现象：问「…还是整张图的图生图？」→ 助手答对了，却多一张「生成失败·整图重绘」红卡，prompt = 这句问话。
根因两层：① `looksLikeGenRequest()` 关键词含 **`张图`** ⇒「整**张图**的」命中；② 思维模式兜底
`else if(looksLikeGenRequest(text) && !isModifyRequest)` → `prompt: text` **原样造待确认提示词** → 确认后真发出去。
- ✅ 新增 `isQuestionOnly(text)`（在 `looksLikeGenRequest` 上方）：
  `AGENT_ASK_VERB_RE`（帮我|给我|请你|来一张|把…改|用这张图重绘）**命中 ⇒ 是需求**；
  否则 `AGENT_ASK_MARK_RE`（结尾 ？|还是|是否|为什么|怎么|如何|哪一张|区别|是什么）⇒ 是提问。
- 🚨 **别收窄 `张图`**：「这张图改成浅色」「整张图重绘成浅色」还要靠它命中，收了真需求就漏（实测）。
- 🚨 `AGENT_ASK_VERB_RE` 里「用」**必须跟图**：写 `用.{0,12}(重绘…)` 会命中「采**用了遮罩局部重绘**」⇒ 问句又漏。
- 三层落地：① `looksLikeGenRequest` 开头 return false；② 非思维兜底 `hasAnyIntent && !isQuestionOnly`；
  ③ `const assistantMsg` 之前过滤 **prompt ≈ 用户原话** 的 prompts/generations（只丢回声，模型改写过的保留）。
- ⚠️ 连带副作用：问句被判成需求后，`_wantsInpaint`（含「局部重绘」）会让「没遮罩不许出图」那道闸也跳，
  把正确 reply 覆盖成「「目标」节点上还没有遮罩」—— 所以修的是判定入口，不是那句文案。
- 验证 `__askguard_test.js` 9/9（5 问句全拦 / 6 真需求全放 / 端到端 0 请求）。

## BH.20　Agent 底部 dock：收起态只剩胶囊 + 输入框高度（2026-10-21）
需求：收起态**连输入框一起隐藏**，只剩一颗胶囊；胶囊文案两态不同（收起=小抽AI / 展开=收起对话）。
- CSS 三条一组（缺一不可）：
  `.agent-panel:not(.chat-open){padding:0;gap:0;background:transparent;border:0;box-shadow:none;backdrop-filter:none;pointer-events:none}`
  `.agent-panel:not(.chat-open) > *:not(.agent-chat-toggle){display:none}`
  `.agent-panel:not(.chat-open) .agent-chat-toggle{pointer-events:auto}`
- 🚨 **`pointer-events:none` 是安全阀**：面板仍占 `--agent-dock-w`(760px)，不加会把画布那片区域点击全吃掉。
  验证方式：收起态 `document.elementFromPoint(面板中心)` 必须落到画布（`world`），不能 `panel.contains(hit)`。
- 🚨 **`border:0` 不是 `border-color:transparent`**：后者宽度还在 ⇒ 面板残留 ~2px 高度。
- 🚨 文案：改 `label.textContent` 的同时**必须改 `label.dataset.i18n`**，否则切语言时 `StudioI18n.apply()` 会把文案改回旧键的值。
  键：`smart.agentPanel`（小抽AI/Xiaochou AI）、`smart.agentCollapseChat`（收起对话/Collapse chat）。
- 🚨 **`#agentInput` 是 contenteditable，不是 textarea**：`agentAutoResizeInput()` 原来直接
  `Math.min(scrollHeight,260)+'px'`，面板隐藏/空内容时 `scrollHeight=0` ⇒ 内联 `height:0px`，
  又因 `box-sizing:border-box`+padding14 ⇒ 内容高 0，**占位文案只剩半行**。
  ⇒ 必须 `Math.max(scrollHeight, AGENT_INPUT_MIN_H=32)` 兜底（32 = padding14 + line-height17 + 余量）。
  同类坑：任何 `scrollHeight` 当高度用的地方，都要先问「这个元素此刻可见吗 / 它是不是 contenteditable」。
- 验证脚本 `output/_tmp-cleanup-20261021/__dock_test.js`（15 断言，含 EN 切换）。

## BH.21　空回复 ≠ 正常回复（2026-10-21）
现象：用户发「xlsx + 主图，生成附图1-5，5张图同时生成」→ 助手回「接口返回了空回复。」后
**接着真的出了 5 张图**，prompt 是用户原话（含 `[文件:]`/`[图:]`）+「变体2…5」。
- 🚨 链路：后端把空正文填成 `"接口返回了空回复。"` 且 **status=succeeded** → 前端当正常 reply →
  不是 JSON → `looksLikeGenRequest` 命中 → 思维模式兜底 `prompt:text` → `requestedCount=5` 补齐成 5 条。
- ✅ 后端：`EMPTY_LLM_REPLY` + `describe_empty_llm_output(finish_reason, saw_reasoning)`（四档病因）
  + `friendly_empty_llm_error()`；`run_agent_llm_task` 见空就 **raise → failed**，`result` 不写。
  `canvas_llm_stream` 要逐块记 `finish_reason` 和 `delta.reasoning_content`（流式原来只看 `delta.content`）。
- ✅ 前端：`processAgentLlmResult` 开头对空回复早退（只出一条 `intent:'error'` 说明，0 任务）；
  兜底 prompt 一律过 `agentPromptFromUserText()` 洗掉 `[图:|文件:|节点:]`，洗空就别造。
- 🚨 **别再让占位文案走正常分支**：任何「后端填空字符串再返回 200」的做法都会在 agent 里变成一次真实生成。
- 🚨 「用户说 5 张」的补齐逻辑会**放大**任何一条坏 prompt；坏 prompt 的来源必须在入口拦住，不能靠下游兜。
- 验证：`__emptyreply_test.js` 11/11、`__empty_backend_test.py` 12/12。

## BH.22　同通道不许换型号（2026-10-21）
现象：下拉里选的是 `gpt-image-2.5-sunburst`，卡片、尺寸说明、报错文案全写 `gpt-image-2.5-flare`。
- 🚨 链路：模型在【可用生图能力】里随手挑一个**同族型号**写进 `prompt.model` →
  `normalizePrompts()` 里 `prov.image_models.includes(wantModel)` 校验**通得过**（列表里真有）→
  `normalized.model = wantModel` → `runAgentGenerations` 的 `genModel` 再用它 → 用户的选择被静默顶掉。
  `sizeNote` 里那句「xxx 的 4K 规格就是 2880×2880」也跟着写错型号 ⇒ 老板无法核对。
- ✅ 规则：**只有换到另一个通道**（能力驱动，比如要 nano-banana 的 4K）才认 `gen.model`；
  **同通道一律回落界面选中**。
  - `normalizePrompts()`：`prov.id !== _uiProv` 时才 `normalized.model = wantModel`。
  - `runAgentGenerations()`：`genModel = (genProviderId !== providerId && …) ? gen.model : 界面选中`。
  - `agentOrchestrationContext()`：明写「界面当前选中 provider/model」+「默认不要写 model，
    同通道写别的型号会被忽略」+「只有当前模型确实做不到时才换通道，并在 plan 里说明原因」。
- ✅ 卡片新增 `gen.exec.model` 小字（`agentGenCardHtml` 的 `agent-gen-model`）：只显示**真正发给上游**的值，
  `status==='pending'`（还没执行）不显示。`gen.exec` 在发请求前就赋值，所以 running 也有。
- ✅ `main.py` `/images/edits`：网络异常时 `str(e)` 常是空串（老板截图里只剩一个 `-1`）→
  改成 `f"{type(e).__name__}: {e}"`（`ConnectTimeout` / `ReadTimeout` / `ConnectError` 处理方向完全不同）。
- 🚨 **改这条契约要同步改测试**：`__famsize_test.js` 原来的端到端用例靠 `gen.model` 同通道指定型号，
  属于旧契约，已改为「同通道设 `agentState.genModel` / 跨通道给 `gen.provider + gen.model`」。
- 验证：`__modelstick_test.js` 18/18（含实发 payload 断言 + 卡片渲染），`__famsize_test.js` 32/32。

## BH.23　纯理解任务不许弹「提示词确认」（2026-10-21）
现象：拖一张图 + 「描述这张图」→ 助手把图描述得完全正确，**下面还是多出一个
「📝 提示词确认 · #1 描述这张图」** + 确认/修改/重新生成/全部取消。
- 🚨 病因与 BH.19 同源：`looksLikeGenRequest` 的关键词含 `张图` ⇒「描述这**张图**」直接命中；
  模型又「顺手续一句」给了个 `prompt = 用户原话` ⇒ `msg.prompts.length > 0` ⇒ 渲染层出卡。
  渲染层条件就是 `msg.prompts.length > 0`（`agentMessageHtml`），所以**唯一解法是根本不产 prompts**。
- ✅ 新增 `isUnderstandOnly(t)`（紧跟 `isQuestionOnly`）：**有理解动词 + 没有任何生图/编辑动作**才成立。
  - 理解动词 `AGENT_UNDERSTAND_RE`：描述/解读/解释/说明/分析/识别/判断/概括/总结/评价/点评/
    说说/讲讲/看一下/看看/这是什么/是什么/什么意思/有什么。
  - 生图动作 `AGENT_GEN_ACT_RE`：生成/画成/画一/画个/画张/绘制/作图/出图/做一张/来一张/
    改成/换成/重绘/重画/修图/抠图/合成/做成/把它画/照着画/把…改…。
  - 🚨 **`反推` 一律不算纯理解**：它是产品内置的「反推提示词」流程（`data-agent-quick="describe"`
    发的是「分析这张图，反推提示词」），那条路**就是需要 prompts** 的。
- ✅ 三层落地：
  ① `looksLikeGenRequest()` 早退（挡住两处兜底）；
  ② 非思维兜底 `hasAnyIntent` 加 `!isUnderstandOnly(userText)`；
  ③ `parseAgentLlmResult` 之后**强拦**：纯理解任务里 `parsed.prompts = []`、`parsed.generations = []`
     （**连改写过的 prompt 也丢** —— 用户要的是「告诉我这是什么」，不是「画点什么」）。
- 🚨 判定一定要「理解动词 **且** 无生图动作」：
  「描述这张图，再按这个描述生成一张」「分析这张图然后画成插画」必须放行，否则会**吞掉真需求**。
- 验证：`__nogencard_test.js` **17/17**（7 例理解全拦 / 7 例生图全放 / 组合与反推放行 /
  端到端 0 prompt 且回答保留 / 渲染层无卡 + 有卡对照）。
- 回归：askguard 9/9、dock 15/15、emptyreply 11/11、modelstick 18/18、sizeguard 23/23、
  editmsg 28/28、famsize 32/32。

## BH.24　附件表格：压空列 + 行数不能截（2026-10-21）
现象：老板「结果与图需排版和风格有蛮多不太一致」——给的是一份 A+ 模块 Brief（模块｜文案｜画面建议｜不建议出现），
拿到的 5 张却是**无文字、构图各异的纯产品图**。
- 🚨 追查路径：对话在浏览器 localStorage（读不到），但**附件文件在磁盘**：
  `assets/input/ai_ref_<hex>.xlsx`。⚠️ **上传后按中文名重命名过，用中文名 find 找不到，要按扩展名找。**
- 🚨 根因 1：`extract_xlsx_text` 把 26 列宽表原样 `A |  |  |  | B` 输出 → 模型**错列**，
  「文案」和「画面建议」对不上。
- 🚨 根因 2：`if index >= 80` 硬上限，Brief 有 102 行 → **副图4/副图5 被截掉**。
- ✅ `extract_xlsx_text`：`AGENT_SHEET_SCAN_ROWS = 400`；**先扫一遍统计哪些列真有值**再输出
  （实测 26→11 列）；单元格内 `\n` → ` / `；连续分隔符压成一个；
  `=DISPIMG("ID_...",1)`（WPS 浮动图片）→ `[参考图]`。
- ✅ `agentSystemPrompt` 新增【需求文档 / Brief 执行】：需求表是**逐条执行清单**，
  **一条 prompt = 一个模块**、条数 = 模块数（压过「条数 = 方向数」）、每条 count = 1、
  主/副标题**原样写进 prompt**、「不建议出现」写成反向约束、
  🚨 不许把多个模块合并成一张「综合产品图」。
- 🚨 **生图模型不会自己编文案**：prompt 里没写主标题 → 成品一个字都没有。这是「排版对不上」的最常见原因。
- ⚠️ 遗留风险：模型偶发返回**不完整 JSON** 时，`parseAgentResponse` 会静默丢光 prompts，
  但 reply 已经说「已按 Brief 拆解…」→ 用户看到「说了要做但什么都没有」。
  这条属于 BH.21「不许静默」的同类问题，**下次再犯就在这里补**。
- ⚠️ 能力边界（要跟老板讲清）：生图模型渲染 5 组长英文主/副标题，拼写/漏字/断行都会翻车；
  要印刷级准确得「生图出画面 + 后期排版加字」，纯生图做不到。
- 验证：`__brief_test.js` 8/8（真实调一次对话模型，生图拦住）、`__xlsx_extract_test.py` 16/16。

## BH.25　Agent 读不了 Excel：工具结果回灌只有 4000 字符（2026-10-21）
现象：Agent 说「我目前无法读取上一轮的 Excel 原文件」，伴随「执行命令 exit=1」。
- 🚨 **真凶**：`agent_tool_event_from_result` 里 `agent_truncate(result.get("output"), 4000)`。
  这份 xlsx 解析出 **4444** 字符，砍到 4000 正好断在「模块五」中间 ⇒ 模型**如实**说「模块五被截断」。
  ⚠️ **模型说「内容被截断」时先查回灌额度，别先怪模型**（我连跑三次都以为它在推脱）。
  已统一成 `AGENT_TOOL_OUTPUT_LIMIT`（12000）。
- 其余三层（都要修，缺一层仍然读不到）：
  ① `read_file` 只做字节 decode → xlsx 是二进制，必须走 `extract_attachment_text`；
     并支持直接传 `/assets/...` `/output/...` `/api/storage-files/...`（模型从历史里看到的是 url）；
  ② `run_shell` 的 `python` 不是随包解释器 → 系统 PATH 里的没 openpyxl ⇒ `exit=1`。
     已在 subprocess env 里把**随包 python 目录前置** + `PYTHONIOENCODING=utf-8`；
  ③ `agentHistoryMessages()` 只传文字 → 跨轮时模型不知道文件在哪（落盘名是 `ai_ref_<hex>.xlsx`，
     跟原名对不上）。已追加 `[附件:原名 → /assets/input/ai_ref_xxx.xlsx]`。
- ✅ 完整性提示写在**正文开头**：`[✅ 完整读取：共 N 行 / M 字符，没有任何截断]`；
  截断时写 `[⚠️ 已截断：原文 N 字符…]`。末尾那句模型会忽略。
- ✅ `_OFFICE_SKILL_TRIGGER_RE` 补 `图需|brief|需求表|需求文档|读表|读取表格|读取文件|解析文件`
  —— 老板说的是「图需」，一个 office 关键词都没有，办公 Skill 根本没注入。
- ✅ `skills/office-xlsx/SKILL.md` 原来**只教生成**，新增「读取现有 Excel」整节。
- 验证：`__excel_read_test.py` 14/14、`__excel_agent_test.js` 5/5（本轮不带附件、只在历史提过）。

## BH.26　顶部/底部工具条布局四处调整（2026-10-21）
1. `#smartSendAgentBtn` 原来钉在 `left:50%; bottom:22px`（画布底部正中）→ 压住底部「小抽AI」胶囊。
   改 `left:22px; bottom:196px; transform:none`，跟「整理选中」(`bottom:158`, 高 32) 同列、贴上方 6px。
2. 顶部「小抽AI」开关移除 → `.agent-toggle{display:none!important}`。
   🚨 **只隐藏不删元素**：删了 `getElementById('agentToggle')` 变 null，几处 `addEventListener` 报错，整脚本挂。
   空出的 `right:454px` 由「灵感库」补上（原 574，工作流占 346~442）。
3. 灵感库改右侧展开：`.inspire-panel` 四处同翻 —— `left→right`、`border-right→border-left`、
   `box-shadow:18px→-18px`、`translateX(-102%)→102%`。
   🚨 **`top:0` 会铺满右半边、把顶部那排按钮全压在底下**（看不见也点不到）⇒ 改 `top:74px`
   （工具栏 `top:22`+高 40 = 到 62，留 12 间隙）+ `border-radius:16px 0 0 0`。
   ⚠️ 不是 `top:22px` —— 那只对齐按钮顶边，照样盖住。
4. 输入栏三按钮移到右下：`.composer-prompt-tools` `top:8px→bottom:8px`；
   `.prompt-input` padding `10px 96px 10px 12px` → `10px 12px 36px 12px`（右 96 原是给右上角按钮让位的）。
- 🚨 **CSS 同优先级下后定义的赢**：在 1528 行另写一条 `.inspire-toggle{right:454px}` 被 1620 行主规则的
  `right:574px` 覆盖，改动完全不生效 ⇒ **改 right 直接改主规则那一行**。
- 🚨 **别用 `window.innerWidth - el.right` 反算 right**：按钮相对定位容器不是视口（算出 412 而非 454），
  直接读 `getComputedStyle().right`。
- 🚨 **断言别拿 CSS 值比屏幕像素**：这些元素在 `data-studio-scale` 的 **zoom 列表**里，
  `top:74px` 实测渲染成 `~67px`（74 × 0.905）。用矩形比较（面板顶边 ≥ 工具栏底边 + 6）才稳。
- 验证：`__ui4_test.js` 14/14、`__inspire_clear_test.js` 7/7（含 `elementFromPoint` 可点性）。

## BH.27　小抽AI 面板默认展开（2026-10-21）
现象：老板「小抽AI 似乎被默认关闭了，没有被默认打开」，画布上既没面板也没胶囊。
- 🚨 **先分清「关」和「收起」**：实测 `#agentPanel` 一直是 `opacity:1; visibility:visible; display:flex`
  且带 `open` 类 —— 真正的问题在 `chatDrawerOpen`。`loadAgentState()` 原逻辑是
  **「有历史消息才展开、一条都没有就收起」** ⇒ 新画布 / 刚清上下文时 `h=0`，只剩一颗胶囊。
- ✅ 改成默认展开，**并且必须做一次性迁移**：
  ```js
  if(typeof agentState.chatDrawerOpen !== 'boolean' || !agentState._dockDefaultExpanded){
      agentState.chatDrawerOpen = true;
      agentState._dockDefaultExpanded = true;
  }
  ```
- 🚨 **只改默认值救不了老 localStorage**：用户那边早存着 `chatDrawerOpen:false`，
  `typeof` 已是 `boolean`，走不进 `!== 'boolean'` 分支。必须靠一个标记字段（`_dockDefaultExpanded`）
  强开一次 —— 之后用户手动收起仍然记得住，不会每次刷新都对着干。
  **这个模式适用于所有「改默认态」的需求**：默认值 + 一次性迁移标记，缺一不可。
- 验证：`__agent_default_open_test.js` 13/13（三个独立画布分别预置「无状态 / false 无标记 / false 有标记」）。
- ✅ **有正在运行的对话时自动展开**（同日追加）：收起态只剩胶囊，跑起来用户看不到进度。
  实现只改**一处** —— `renderAgentMessages()` 开头（渲染是所有运行入口的公共必经之路，
  不必去 5 个 `agentSending = true` 各写一遍）。
  🚨 判定不能只看 `agentSending`：刷新恢复的图生任务、快捷操作触发的变体，
  `agentSending` 可能是 false，但 `generations` 里仍有 `status === 'running'`。
  ⚠️ **只在跑起来时展开、跑完不自动收起**（结果还在，收起由用户决定）。
  `applyAgentDockSize()` 不回调 `renderAgentMessages`，不会递归。
- 验证：`__agent_autorun_test.js` 9/9。

## BH.28　小抽AI 窗口拖拽移动 + 四角缩放（2026-10-21）
- HTML：`.agent-panel` 末尾加 4 个 `[data-agent-resize]` 把手。
- CSS：默认「底部居中」；拖过加 `.dragged` → `left:0;top:0;bottom:auto`，
  且必须 `.agent-panel.dragged.open{transform:none}`（清掉 `.open` 的 `translate(-50%,0)`，否则再左推半个宽度）。
- JS：`bindAgentDockDrag()`（拖 `.agent-head`）、`bindAgentResizeHandles()`（四角）；
  宽度走 `--agent-dock-w`、高度走 `--agent-chat-h`，**不写死 height**（会压扁输入区）；
  位置尺寸存 `dockPos/dockW/chatDrawerHeight`。
- 🚨 **HTML 多一个 `</div>` 会让新元素被甩到 `<body>` 下**：`.agent-panel` 内部 div depth 算到 0 后又多关一个，
  浏览器容错吞掉、不报错，但把手 `parentElement` 变成 BODY ⇒ absolute 相对页面定位、`:not(.chat-open)` 隐藏规则失效。
  **新元素没按预期定位时先查 `parentElement`**；数 depth 出现负数即多关。
- 🚨 **坐标要除 zoom**（`studio-scale` ≈ 0.907）：指针给屏幕坐标、`style.left` 要 CSS 坐标。
  **第一次拖动**尤其要注意：默认 `left:50% + translate(-50%)`，`offsetLeft` 是 transform **之前**的值，
  直接拿来当起点会横跳半个宽度。正确换算 `dockPos.x = offsetLeft - offsetWidth/2`，
  **别用 `rect.left/zoom` 反推**（取整误差留 5px 跳动）。
- 验证：`__agent_drag_test.js` 20/20（含「按下不跳」这条）。

## BH.29　附件图也能局部重绘（2026-10-21）
现象：用户贴图 + 「把女人换成男人」→ 助手说「这是消息附件而非画布节点，无法绑定局部遮罩」→ 整图重绘，
脸/构图/光线全变。
- 🚨 不是链路坏，是**模型自己放弃了**：附件不在【画布现状】里 ⇒ 它判定绑不了遮罩 ⇒ 不给 `mask_hint`
  ⇒ `agentApplyAutoMask` 根本没跑。而 `agentPickAutoMaskNode()` 也确实只从**已有节点**里挑。
- ✅ 新增 `agentEnsureAttachmentNodeForMask(userMsg)`：`agentApplyAutoMask` 挑不到节点时，
  把 `userMsg.images[0]` 落成画布节点（同 url 已有则复用）。**只在 `gen.inpaint===true` 时生效**。
- ✅ 提示词补两处：`AGENT_OFF_MODE_INSTRUCTION` 的【mask_hint 什么时候填】+ `agentOrchestrationContext()`
  的【画布能力总览】。🚨 `AGENT_OFF_MODE_INSTRUCTION` 与 `AGENT_FORMAT_INSTRUCTION` 是**两个常量**，别只改一个。
- ⚠️ 测试素材必须用 `/output/` 或 `/assets/` 的图：后端 `output_file_from_url` 只认这两类，
  `/static/` 前端能 fetch、后端读不到，会误判「造不出遮罩」。
- 验证：`__attach_mask_test.js` 9/9（自动补节点 / 写入 inpaint / 回写 target_node / 没图时明确 error）。
- ✅ **实测确认模型会给 mask_hint**（`__mask_llm_test.js`）：附件图 +「只把中间头枕换成红色」→
  `mask_hint.bbox=[0.45,0.13,0.12,0.12]`，框得准。不写 `inpaint:true` 是设计如此（前端自动补）。
- ✅ **完整链路 6/6**（`__mask_e2e_test.js`）：附件图 → 自动补节点 → 写 `node.inpaint` →
  实发 `{operation:'inpaint', inpaint:{crop_url…}}`。
  - 🚨 断言别找平铺 `crop_url`，`agentInpaintPayload` 产出的是 `{operation:'inpaint', inpaint:{...}}`。
  - 🚨 思维模式产物是**待确认 prompts**，必须调 `confirmAgentPrompt(msg)` 才进 `runAgentGenerations`。
- ✅ **没让 agent 自己 create_node**：模型只给 mask_hint、系统自动落地，agent 一步搞定；
  `agentEnsureAttachmentNodeForMask` 有同 url 去重。改成显式建节点时**必须保留这条兜底**。

## BH.30　dock 三处收尾：报错文案 / 拖高条 / 收起回底部（2026-10-21）
1. **「请求上游接口失败：」后面空** → `str(httpx.ConnectTimeout())` 常是空串。
   新增 `friendly_upstream_http_error(exc)`：异常类名 + host + 按类型给排查方向，
   并 `print("[upstream-error] ...")` 进服务日志。8 处调用点（含 SSE `yield sse_event`）全部替换。
2. **移除顶部拖高条** `#agentDockResize`（拖它会把对话框往下推）；调高度交给四角缩放。
3. **收起对话后胶囊跑到顶部** → `applyAgentDockSize()` **只在展开态应用 `dockPos`/`dockW`**，
   收起态清掉 `dragged` 与 left/top，回 CSS 默认「底部居中」；`dockPos` 留着，再展开回原位。
- 🚨 **`transition` 会让 `getBoundingClientRect()` 读到过渡起点**：`.agent-panel` 的 transform 有 .16s 过渡，
  apply 之后立刻量拿到的是 `matrix(...,-379.996,0)` 而不是 `none` ⇒ 校准算反、面板被推到屏幕外、
  拖动一跳就是半个宽度（344px）。
  修法：`.agent-panel.dragged{transition:none}` + 测量前临时 `style.transition='none'`。
  **任何「设样式→立刻量位置」的代码都要先确认有没有 transition。**
- 验证：`__collapse_bottom_test.js` 8/8、`__agent_drag_test.js` 20/20。

## BH.31　局部重绘结果落新节点（2026-10-21）
老板：「结果是对的，但生产的结果不应该直接替换掉原图，而是以一个新图片节点展示」。
- ✅ `runAgentGenerations` 的 inpaint 分支不再拿用户节点当占位：`agentFindEmptyPosition(1)` 建新节点
  （标题「局部重绘」）；原节点只提供遮罩/裁切基准（`gen._inpaintNodeId` 仍记着它，payload 要用）。
- ✅ **不再迁遮罩**：删掉 `keepInpaintAfterRun` 调用 —— 原图连遮罩一起留着，
  可继续改同一块、也能对比「改前/改后」（函数本身保留，现无调用点）。
- ✅ **失败时删占位**：以前怕删掉老板的图所以只清 pending；现在占位是自己建的、原图没被碰过 ⇒ 直接删。
- ✅ `recoverAgentGenerations` 同步：标题 `gen._inpaintNodeId ? '局部重绘' : 'Group'/'Image'`。
- 🚨 **别和 BH.8 ④ 的「必须回贴」搞混**：后端仍然把裁切结果合成回**整图尺寸**（差异只在 bbox 内），
  这层没变；变的是**前端不再把它塞回原节点**，而是放进新节点。
- 验证：`__inpaint_newnode_test.js` 10/10（拦 fetch 假成功，不花钱）。

## BH.32　Agent 输入框两个模型 pill + 修鼠标抓手（2026-10-22）
1. **两个 pill 分别显示理解模型 / 生图模型**（以前只显示通道名 `Aizzz-image`，看不出跑哪个模型）：
   `#agentModelBtn`(cpu) + 新增 `#agentGenModelBtn`(image)，label 分别取
   `agentState.chatModel` / `agentState.genModel`；两个 pill 开**同一个** `#agentModelPanel`。
   CSS：`.agent-topbar .agent-toolbar-dropdown-wrap{display:flex;gap:4px}`，pill 的 `span max-width` 收到 96px。
   🚨 **`agentChatModel` 的 change 原来不调 `agentUpdateToolbarLabels()`** ——
   换理解模型 pill 不动（`agentGenModel` 那条有调，别以为都一样）。
2. 🚨 **鼠标抓手是继承来的**：`.shell{cursor:grab}`（画布可平移），`.agent-panel` 是它子元素 ⇒ 整个 Agent 区
   都是张开的手。修：`.agent-panel{cursor:default}` + `.agent-panel .agent-head{cursor:move}`
   （标题栏保留四向箭头提示可拖）。
   顺带 `.asset-mini-btn` **从没声明 cursor:pointer**，会继承父级 —— 已补。
   **凡是浮在 `.shell` 里的面板，都要自己声明 cursor**，否则都是 grab。
3. 验证：`__model_pills_test.js` 12/12、`__cursor_probe.js`（修前 grab → 修后 default）。

## BH.33　对话标题可重命名（2026-10-22）
- 🚨 **根因是标题优先级反了**：`renderAgentChatList` 原来写
  `firstMsg ? 首条消息 : (conv.title || '对话')` —— `conv.title` 只在**没有消息**时才生效，
  等于存了也白存、改完刷新就回去了。改成 `customTitle || autoTitle`。
- 🚨 **`agentNewChat` 写死 `title:'新对话'`**：配合新优先级会让新对话永远显示「新对话」。
  改成 `title:''`；老数据里的 `'新对话'` 在渲染时过滤（当「没起过名」），不用改盘。
- 🚨 **`.agent-chat-item` 原来是 `<button>`**：里面要嵌 `<input>` / 删除按钮，非法 HTML 会被浏览器改写 DOM
  ⇒ 改 `<div role="button" tabindex="0">`，CSS 补 `width:100%; box-sizing:border-box`。
- 交互：~~双击标题~~ → **改成铅笔按钮**（`[data-chat-rename-btn]`，时间右边、删除左边）。
  🚨 **「单击即跳转」的列表项上不要挂双击**：`item.onclick` 会立刻 `agentSwitchChat` + `panel.hidden=true`，
  双击的第二下落在空气里，根本够不着。老板实测「没办法双击到标题」。
  - `item.onclick` 的排除列表要加 `[data-chat-rename-btn]`；⚠️ 别和输入框的 `[data-chat-rename]` 混了（两个属性）。
  - 铅笔 `onclick` 里 `stopPropagation + preventDefault`。
  - 输入框仍：Enter 保存 / Esc 取消 / 清空恢复自动标题；`commit()` 用 `done` 防重入。
- 验证：`__chat_rename_test.js` 11/11（含「点铅笔不切换对话 / 不关闭列表」「刷新后仍是自定义标题」）。

## BH.34　思考强度（reasoning_effort）档位（2026-10-22）
- **先分清**：`thinkingMode` 是**布尔开关**（被 `enforceAgentAlwaysOn()` 强制 true），控制的是
  「先出提示词确认卡 vs 直接出图」+ 换系统提示词，**不是模型推理深度**。原 `main.py` 没有任何
  `reasoning_effort` 发送代码，模型一直用它自己的默认值。
- **UI**：第三个 pill `#agentReasoningBtn` + `#agentReasoningPanel`，5 档
  自动/最低 minimal/低 low/中 medium/高 high；复用 `showDropdown()` 定位。
- **状态**：`agentState.reasoningEffort`（默认 `'auto'`，存 localStorage）。
  `agentReasoningEffortForLlm()`：`auto` → **空串**，其余原样。
  三处 `llmPayload`（普通 / 流式 / 重新生成）统一加 `reasoning_effort`。
- **后端**：`CanvasLLMRequest.reasoning_effort` + `apply_reasoning_effort(body, effort)`，
  只注入 `canvas_llm` / `canvas_llm_stream` 的**两处** `req_body`。
- 🚨 **auto 一律不传参**：不少 OpenAI 兼容网关不认这个字段，无条件塞会 400，把能跑通的请求搞挂。
  只有用户明确选了档位才透传；空串/非法值一律不加字段。
- ⚠️ **覆盖范围**：✅ OpenAI 兼容 `chat/completions`；❌ codex CLI（走 `run_codex_cli`，不经 HTTP body）；
  ❌ gemini-cli（同上）；❌ Gemini `thinkingBudget` / Anthropic `thinking.budget_tokens`（另一套参数，未做）。
- 验证：`__reasoning_effort_test.js` 16/16；**真发一次**（`__effort_live_test.js`，`ep_1792553056895 /
  codex-auto-review`）`low` 与 `""` 均成功 ⇒ 上游不 400。⚠️「接受」≠「一定生效」，网关可能静默忽略。

## BH.35　纯提问不许触发生图（2026-10-22）
老板：**「不要一味用提示词做限制，而是让 agent 通过思考判断真实需求」**。
现象：「这张图能看出来吗」→ 模型答对了，但下面弹出「正在生成图片 + 提示词确认 #1 这张图能看出来吗」。
- 🚨 **根因是词表漏口语，不是提示词不够**：
  `AGENT_ASK_MARK_RE` 只有 `[？?]\s*$`（用户没打问号，句尾是「吗」）；
  `AGENT_UNDERSTAND_RE` 没有「看出来 / 看得出 / 认得」⇒ 两个判定都 false ⇒ 含「图」被判成生图。
- ✅ **扩词表**（第一道）：ASK_MARK 加 `[吗呢]\s*$`；UNDERSTAND 加
  `看出来|看得出|看出|认得|认得出|分辨|确认一下|能确认`。
- ✅ **硬规则（主力机制）**：**不判断意图**，只看 ① 用户话里无生图/编辑动作词（`agentUserHasGenAction()`）
  且 ② 模型给的 prompt 是用户原话（或原话一部分、≥8 字）⇒ 一定是「把问话当提示词」⇒ 直接丢。
  **不依赖意图分类准不准**，词表覆盖不到的口语也能拦。⚠️ 有动作词时不动（「画一只猫」的 prompt 就是原话，但那是真需求）。
- ✅ 提示词辅助（第三层）：`AGENT_FORMAT_INSTRUCTION` 核心规则 2 后加「只在提问/看图时 prompts 与 generations 留空」。
- 🚨 `agentUserHasGenAction()` 必须定义在**顶层**（`looksLikeGenRequest` 之前）——
  放函数内部外部测不到（第一版踩了）。
- 验证：`__ask_no_gen_test.js` 15/15（8 条判定 + 4 条端到端 + 2 条反例）。

## BH.36　生图分辨率/质量以用户原话为准（2026-10-22）
现象：老板要「默认 4K 高质量」，实际出 1024×1024。
- 🚨 **默认值本身是对的**（`agentState` 就是 square/4k/high，sunburst+4k → 2880²）。
  根因是 `_genRes = gen.resolution || ...` —— **模型爱在 generation 里写 `resolution:'1k'`**
  （它把 1K 当「安全默认」），把老板的 4K 顶掉；质量同理（`gen.quality:'medium'`）。
  而界面 10-19 就移除了参数选择器，他连改都改不了。
- ✅ 修：新增 `agentExplicitResolution()` / `agentExplicitQuality()`，**只认用户原话**：
  `4K/2K/1K/8K`（带 `(^|[^0-9])` 前置，别把「24K」误判）、`超高清/最高画质 → 4k+high`、
  `高质量/高清/精细 → high`、`普通画质 → medium`、`草稿/快速出图 → low`。
  ```js
  const _genRes = agentExplicitResolution(_userText) || agentState.genResolution || '4k';
  const genQuality = agentExplicitQuality(_userText) || agentState.genQuality || 'high';
  ```
  **`gen.resolution` / `gen.quality` 不再参与**（同 BH.7 比例覆盖的思路：用户没说，别让模型替他决定）。
  `gen.ratio` 保持原样（模型给比例通常有画面依据）。
- 验证：`__res_priority_test.js` 14/14 —— 模型硬塞 `1k+medium` → 实际 2880²/high；用户明说 1K → 1024。

## BH.37　出图参数 pill（比例/分辨率/质量/张数）（2026-10-22）
老板要求把尺寸信息显示在 agent 输入框底部（附件按钮右边）。
- 🚨 **代码全在，只有 HTML 在 10-19 被删了**：`agentSyncParamsPanel()`、四组点击绑定
  （`agentRatioGrid`/`agentResGrid`/`agentQualitySeg`/`agentCountGrid`）、全套 CSS
  （`.agent-params-panel`/`.agent-params-section`/`.agent-ratio-grid`/`.agent-res-grid`/
  `.agent-quality-seg`/`.agent-count-grid` 含 `.active`）都还活着；
  唯一被置空的是 `initAgentPanel` 里的 `const paramsBtn = null; const paramsPanel = null;`。
- ✅ 补回：`#agentParamsBtn` + `#agentParamsLabel`（放 `agent-toolbar`、附件按钮右边）+
  `#agentParamsPanel`（`data-ratio` 七个 key：square/landscape/portrait/landscape43/portrait43/wide/story）；
  JS 两行改回 `getElementById` ⇒ 点击/关闭/同步自动生效。
- **优先级**：面板改的是 `agentState` 默认值；**用户原话明确说了档位时仍以原话为准**
  （`agentExplicitResolution/Quality` 优先）—— 一次性要求和长期默认各归各位。
- 验证：`__params_pill_test.js` 12/12。⚠️ 别猜具体尺寸：gpt-image-2 家族 3:2 2K = `2048x1360`，
  不是通用的 `1792x1195`；按「比例≈1.5 且短边≥1300」判更稳。
- ✅ **比例列表与节点面板同一套规则**（2026-10-22 老板要求）：`agentRatioOptions(model)` 复刻
  `buildSmartSettings`（约 4237 行）的判断 —— 8 个基础比例 + `ultratall 9:21`（nano 自动比例系隐藏）
  + nano-banana-2 的 `1:4/4:1/1:8/8:1` + `auto 自动适配`（仅 nano 自动比例系）。
  `agentSyncParamsPanel()` 里**动态渲染**比例按钮，用 `dataset.opts` 签名控制重建时机。
  分辨率/质量映射本来就用 `apiImageSize` / `gptImageFamilySize`，与节点同源。
- 🚨 **遗留隐患**：`agentRatioOptions()` 与 `buildSmartSettings` 的比例表是**两份复制**
  （后者耦合 engine/prefix/includeSource，抽取成本高）。**改一边必须同步另一边**。
- 验证：`__ratio_rules_test.js` 11/11（gpt 9 项 / nano-banana-2.1 13 项 / 换模型动态变 / 21:9 实发 2912×1248）。
- 🚨 **两处「看着还是旧的」的坑**（同日返工）：
  ① pill 的质量段写成 `quality ? ' · …' : ''`，`genQuality=''`（自动）时整段被吞 ⇒ 显示成 `1:1 · 4K · 1张`，
     跟改之前一模一样。**永远输出质量段**（空 → 「自动」）。
  ② 比例图标 CSS 有 `width:20px; max-height:24px`，竖图的 `aspect-ratio` 被 `max-height` 压回 24 ⇒
     所有图标看着一样大。改成 **JS 按「长边 20px」算死宽高**写 inline style，CSS 只留 `display:block; border`。
     🚨 **比例字符串在 label（`3:2`）里，不在 key（`landscape`）里** —— 拿 key 去匹配 `/^(\d+):(\d+)$/` 永远不中。
- ⚠️ 量图标尺寸前必须先 `panel.hidden=false`：`display:none` 下 `getBoundingClientRect()` 全是 0，会**假通过**。
- 🚨 **换生图模型必须重建比例列表**（2026-10-22 老板：「缺少 nano-banana 独有的自动比例」）：
  `agentGenModel` 的 `change` 原来只调 `agentUpdateToolbarLabels()`，**没调 `agentSyncParamsPanel()`** ⇒
  切到 nano-banana 后面板还是上一个模型的项，「自动」不出现。已补。
  （切**通道**没问题 —— `renderAgentModelSelectors()` 末尾本来就调了。）
  ⚠️ 「自动比例」只有 nano 系有（`isNanoBananaAutoRatioModel`），gpt-image 系没有，节点也一样 ——
  用 gpt-image 的通道看不到是**正确行为**。

## BH.39　上下文指代：「基于描述文案」≠「按参考图」（2026-10-22）
现象：先「描述这张图的背景」（模型答了一段文字），再说「基于描述文案生成图片」→
模型回「**按参考图的**卖点图制作…」，把「用上一轮那段文字」理解成「用附件图」。
- 🚨 **信息没丢，是指代没关联**：`agentHistoryMessages()` 里 assistant 的 `content = m.text`，
  那段描述就在历史里，模型看得到。
- ✅ **提示词**：`agentOrchestrationContext()` 新增第 5 节【上下文指代】——
  「描述文案 / 上面的描述 / 刚才那段文字 / 就按这个描述」→ 指**上一条 assistant 正文**；
  「按参考图 / 照这个风格」→ 才是附件图；两者同时出现以文字为主。
  （放 ctx 是因为**两套模式都注入**，OFF 模式也生效。）
- ✅ **代码兜底**：`agentReferencedAssistantText()` 仅在明确指代时取上一条 assistant 正文（≥20 字），
  判据 `AGENT_REFER_TEXT_RE`。~~`prompt = 那段文字 + '\n\n' + 原prompt`~~ ← **已废弃**（见下）。
- 🚨 **方向修正（同日）**：老板「**不是完全贴合该输入文案才执行，而是需要加入 agent 的理解和判断**」。
  机械拼接只是复述（上一轮那段是「看图说话」产物，缺主体/构图/镜头/风格），照搬反而更差。
  ⇒ 改为 `agentSystemPromptWithReference(base, userText)`：**发请求时**把那段文字作为上下文块注入
  `system_prompt`，并要求「改写成生图提示词（主体/构图/镜头/光线/质感由你补）、不复述、
  不写成按参考图、不适合画面的部分直接舍弃」。三处 `llmPayload` 全包一层；**不指代时零注入**。
- 验证：`__context_ref_test.js` 9/9 + **真发一次**（`__ref_live_test.js`）4/4 ——
  模型输出的 prompt 把描述转成了完整生图指令（补了「横向构图/中景镜头/浅景深/真实摄影质感」）。

## BH.40　agent 并发对话（2026-10-22）
老板：「允许 agent 并发，A 对话跑着时允许新建对话去 B 说话」。
- 🚨 **按钮本来就没禁用**（`agentNewChat()` 里没有 `agentThinking` 拦截）。
  **真正的问题是结果归属**：`processAgentLlmResult` push 到 `agentState.messages`，
  用户切对话后该指针已指向 B ⇒ **A 的回答会串进 B**。
- ✅ `agentSendMessage` 发请求前记 `userMsg._convId` + `agentState._runningConvId`。
- ✅ 新增 `agentPushAssistant(msg)` 取代原来 10 处 `agentState.messages.push(assistantMsg) + slice`：
  目标 = `msg._convId || _runningConvId || activeConversationId`；目标 ≠ 当前对话 ⇒
  写进那个对话、`saveAgentState()`、轻提示「另一个对话有新回复」、**不刷新当前 UI**。
- ✅ `assistantMsg` 加 `_convId`（主路径 2 处）双保险。
- ✅ 生图阶段不用改：改的是**画布节点**（全局共享）+ `assistantMsg` 对象引用（已在正确对话数组里）。
- ⚠️ **已知限制**：A 跑着 → 切 B → **又在 B 发一条** ⇒ `_runningConvId` 被 B 覆盖，
  A 的结果若晚到可能落 B。彻底解决要把 convId 一路传到每个 push 点。
- 验证：`__concurrent_conv_test.js` 8/8。
- 🚨 **光改归属不够，按钮本来就被锁着**（老板截图「思考时 + 是灰的」）。
  真凶是 `agentSending`（不是 `agentThinking` —— 后者只管 spinner）：
  `renderAgentMessages` 里 `newChatBtn/chatListBtn/agentInput/agentSendBtn.disabled = agentSending`。
  修：
  ```js
  const _curConvRunning = agentSending
      && String(agentState?._runningConvId || '') === String(agentState?.activeConversationId || '');
  agentSendBtn.disabled = _curConvRunning;
  agentInput.disabled = _curConvRunning;
  newChatBtn.disabled = false;      // 永远可用（并发前提）
  chatListBtn.disabled = false;     // 切对话要能点
  moreBtn.disabled = agentSending;  // 「更多」有清空等危险操作，仍锁
  ```
  ⇒ A 在跑、切到 B 时 `_runningConvId=A ≠ active=B`，B 的输入框**立刻可用**。
  ⚠️ `agentSending` 是模块内 `let`，自动化测不到「sending=true 且同对话时被锁」，只能靠代码审查。
- 验证：`__lock_btn_test.js` 9/9。

## BH.41　节点尺寸面板的比例改圆角卡片（2026-10-22）
老板：「把画布节点输入栏处的尺寸比例**文字**改成 agent 尺寸那种**圆角矩形**」——改的是**节点**不是 agent。
- `renderSizePickerControl()`（约 4226 行）左列比例：`<span>1:1</span><small>正方形</small>`
  → `<span class="size-picker-ratio-icon" style="…"></span><span class="size-picker-ratio-label">1:1</span>`，
  「正方形/竖图/横图」退到 `title`。图标长边 18px、短边 = 18×min/max（与 agent 面板同一算法）。
- CSS：`.size-picker-preset{grid-template-columns:168px minmax(0,1fr)}`、
  `.size-picker-list.size-picker-ratios{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}`、
  `.size-picker-ratios .size-picker-option{flex-direction:column;min-height:52px}`。
- 🚨 **特异性坑**：已有 `.size-picker-option span`（0,2,1）会压住 `.size-picker-ratio-label`（0,1,0），
  必须写 `.size-picker-ratios .size-picker-option > .size-picker-ratio-label`（0,3,0）。
- ⚠️ 截图弹层：默认 hover 才显 + 带 transform，要先强制 `opacity/visibility/transform/position`，
  否则截到空白页。
- 验证：`__size_picker_cards_test.js` 9/9。

## BH.42　1.2.2 构建记录（2026-10-22）
- 产物：full **125.85 MB**（3169 文件 / 185.88 MB）、delta **1.11 MB**（基线 1.2.1：变更 23 / 删除 1）。
  delta 小是**对的** —— 没改 `launcher/*.cs`、exe 未变（纯前端+后端）。
  🚨 技能里「delta 小 = 基线污染」要看**变更条目里有没有关键文件**，不是看体积。
- 基线 `output/release/1.2.1/` 是 **10-19 12:51** 打的，今天没重建 ⇒ 未污染 ✓
- `?v=` 核对：`js/i18n.js` 是 `1.2.2.1792550183` —— **正常**，它取 `i18n/` 子包最新 mtime
  （10-21 10:36，今天没改子包），别拿 `VERSION.<该文件 mtime>` 去卡它。
- 全过：delta 24 条目含 main.py/VERSION/smart-canvas.js/css/html/update-notes/i18n；
  exe 包内==仓库根；full `prune_roots` 无 data·assets·output·API；delta `deleted=['static/gpt-chat.html']`；
  两个包 verify 均「通过」；`read_notes_file()` 13 条（≤24）。
- 🚨 **远端 main 落后两个提交**：`git ls-remote origin main` = `b9cfd20`(1.2.0)，
  **1.2.1 的提交当年没 push**（tag 有、main 没动）。本地 HEAD `f6c228e`，待推 2 个。
  这也解释了网页端读 `raw/main/VERSION` 一直看到 1.2.0 —— 但启动器走 Release 的 `update.json`，
  1.2.1 用户照样收到了更新。
- 已本地提交 `f6c228e`，**未 push**；服务已停且**打包后不要重启**（否则 `?v=` 变、包与工作区脱钩）。

## BH.43　取消图片数量强规则，改由理解模型判断（2026-10-26）
老板：「取消 agent 中图片数量强规则，改为理解模型判断」。
- 强规则原有**四处**：① `genCount` 默认 1；② `resolveFinalGenCount` 永远回落 1；
  ③ **3c** `else if(requestedCount===0 && !agentWantsMultiDirection()) prompts=slice(0,1)`；
  ④ 提示词 `_finalCount` 里 `Number('auto')`→NaN→`||1`。
- ✅ 改法：`genCount` 默认 **`'auto'`**；面板「张数」加「自动」（放最前，5 列）；
  `resolveFinalGenCount` 在 auto 时返回 `{count:0, source:'model'}`；**3c 删掉硬截那档**
  （只保留「用户原话说了数字」和「面板显式选了 N（含 1）」）；提示词 auto 时写「**由你判断**」。
- ✅ **老 localStorage 迁移**：`genCount:1` 是旧默认不是用户选择 ⇒ `_genCountMigrated` 一次性标记，
  首次加载把 `1/空/null` 改成 `'auto'`；标记在就不再改（用户显式选 1 要保留）。BH.27 同一个坑。
- ✅ `resolveFinalGenCount` 对**显式 1** 也返回 `{count:1, source:'toolbar'}`（语义准确），
  同时 30648 的「阶段二继承」加 `source !== 'toolbar'` 条件 —— 否则面板选 1 会被上一轮的 3 张继承走。
- ⚠️ 测试文本坑：`chatRequestedImageCount('画一张座库图')` 返回 **1**（「一张」命中中文数字表），
  会被当成「用户明确要 1 张」。测 auto 要用**不带数字**的文本。
- 验证：`__count_logic_test.js` 16/16 + `__count_3c_test.js` 6/6（抽 3c 真代码块跑：auto+3条→全保留）。
- 🚨 **Edge 环境已坏**（`Code: 0` 空 stderr，命令行也零输出；44 个 msedge 进程是老板的，不能杀）
  ⇒ **UI 自动化暂时不可用**，改用 Node 抽真函数跑。
  另：`~/.workbuddy-ai/tmp/edge-*` 堆了 468 个，以后测试**复用同一 profile 目录**别再新建。
- 🚨🚨 **追加查证（同日）：Edge 安装本身损坏，不是沙箱问题**。PowerShell 视角：
  根 `Application\msedge.exe` **不存在**；`Application\155.0.4283.62\` 与 `156.0.4314.42\`
  两个版本目录**里一个 .exe 都没有**（只剩骨架）⇒ 后台更新中断，旧文件清了、新的没铺完。
  44 个 msedge 进程是内存旧实例，**重启电脑后 Edge 会打不开**。
  **修复**：设置 → 应用 → Microsoft Edge → 修改 → 修复，或重下安装包覆盖。
  ⚠️ **判断文件在不在要用 PowerShell 工具，别用 Bash 的 `ls`** —— 沙箱是另一层视图，
  `ls` 能看到 `156.0.4314.42/msedge.exe` 但宿主机上根本没有，会被误导。
- 补充静态验证：Python 读 HTML/CSS/JS 断言 **10/10**（5 个张数按钮、auto 排第一、CSS 5 列、
  默认值、`source:'model'`、3c 无硬截、迁移标记、pill「自动」、`_fcAuto`）。

## BH.44　1.2.3 构建（2026-10-26）
- ⚠️ **先更正一个误判**：当时跑 `gh release view Official.1.2.x` 全部 not found、`gh release list` 为空，
  就断定「从 1.2.0 起没有 Release、用户收不到更新」——**错的**。
  真因是 `gh` 默认仓库指向 upstream `hero8152`（见 BH.45）。1.2.1/1.2.2 的 Release 一直存在、资产齐全。
  🚨 **查发布状态必须带 `-R HanaJhon/Infinite-Canvas`**，否则看到的是 upstream 的空结果，结论会完全反过来。
- 产物：full **125.85 MB** / delta **0.74 MB**（基线 1.2.2：变更 17 个）/ notes 14 条。
  核对：`?v=` 全 1.2.3、delta 18 条目含 VERSION/js/css/html/update-notes（**`main.py` 不在是正常的**，
  当天纯前端）、exe 一致、两个包 verify 通过。
- 提交：`d641405` → `1058438` → `109425b`（13 个 html 的 `?v=` 同步）。

## BH.45　🚨「从来没有 Release」的根因 + 发布链路已打通（2026-10-26）
- 🚨🚨 **`gh` 的默认仓库是 `upstream`（`hero8152/Infinite-Canvas` 原作者仓库），不是 `origin`（`HanaJhon`）**。
  `gh repo view --json nameWithOwner` 实测返回 `hero8152/Infinite-Canvas`。
  ⇒ 以前**每次** `gh release create` 都往原作者仓库发 → 无权限 → `HTTP 404: Not Found`
  ⇒ 1.2.0/1.2.1/1.2.2 只有 tag、没有 Release ⇒ `releases/latest/download/update.json` 一直 404
  ⇒ **所有用户从 1.2.0 后没收到过更新**。
- ✅ **修复**：`gh repo set-default HanaJhon/Infinite-Canvas`；发版命令**一律加 `-R HanaJhon/Infinite-Canvas`**。
- ✅ **旧经验被推翻**：技能里「工具会话内 `git push`/`gh` 会挂起，必须老板执行」**现在不成立**——
  `git push origin main` 90 秒内成功，`gh release create` 上传 126 MB 39 秒完成。以后可直接做。
- ⚠️ **别用 pipe 判成败**：`gh ... | tail` 会把退出码变成 `tail` 的 0，**404 也显示 EXIT=0**。
- ✅ 1.2.3 发布结果：tag `Official.1.2.3` → `109425b`（正确）；三个资产齐全（Full 125.85MB /
  Update 0.74MB / update.json）；`releases/latest/download/update.json` 实测 HTTP OK、version 1.2.3。

## BH.46　UI 验证改用 ego-browser（2026-10-26）
老板：「不再使用 edge 了而是 ego-browser」（技能 `~/.workbuddy-ai/skills/ego-browser`）。
- ✅ **ego lite 已装**：`C:\Program Files\Citro Labs\ego lite\Application\ego.exe`（Chromium 内核）；
  用户数据 `%LOCALAPPDATA%\Citro Labs\ego lite\User Data`；另有 `%LOCALAPPDATA%\Citro Labs\EgoUpdater`。
- ❌ **`ego-browser` CLI 没注册**：PATH / `~/.local/bin` / `%APPDATA%\npm` 全都没有；
  **npm 上也没有 `ego-browser` 包（404）** ⇒ CLI 只能由 ego lite app 的 **onboarding** 生成。
  `ego.exe --version` 是 GUI 启动器（输出 GBK 乱码），**不能当 CLI 用**。
  技能 `references/install.md` 的安装脚本**只支持 macOS**。
- 📄 已备好 `output/_tmp-cleanup-20261021/__ego_verify.js`（14 条断言，语法已过）。
  用法：`ego-browser nodejs <该文件>`；脚本自己建一次性画布、跑完 purge、`task.finish({keep:[]})`。
- 🚨 **ego-browser 不是 Playwright**：只有 TaskSpace / Page / mouse / keyboard 这几组 API，
  别用 `locator()` / `getByRole()` / `context()` / `route()`；没有的方法走 `page.evaluate()` 或 `page.cdp()`。
  `page.evaluate()` 回调**跑在页面里**，读不到 Node 变量（要传参）。
- 等老板跑完 onboarding（`command -v ego-browser` 有输出）后再执行验证。

## BH.47　🚨 启动器 0x800736B1「并行配置不正确」（2026-10-26）
现象：双击启动器弹框「应用程序无法启动，因为应用程序的并行配置不正确 (0x800736B1)」。
- 已排除：exe 损坏（sha256 与工作区/包内完全一致）、VC++ 运行时（齐全）、WebView2（存在）、
  update.log（最后一次 10-22 1.2.2 delta 成功）。
- 🚨 **根因：`.NET 单文件 exe 的解压缓存与 exe 版本不匹配**。
  `%TEMP%\.net\Lochou启动器\` 时间戳是 **10-19**，exe 是 **10-22** 更新的 ⇒ 生成激活上下文失败。
- ✅ **解法**：把 `%TEMP%\.net\Lochou启动器` **改名备份**（别直接删），结束正在报错的实例，
  再启动 → exe 自动重建缓存。
  顺手可清 `%TEMP%\.net\_apply_update_*`（本次清出 **48 个 / 437.9 MB**，每次更新留 8.3 MB）。
- 验证：重建后启动器能起（113.9 MB 内存 = WebView2 已加载）⇒ SxS 错误消失。
  ⚠️ 重建的缓存先只有 **8.3 MB bootstrap**，完整 app（~198 MB）要用户双击时才解压。
- ⚠️ **工具会话里 `Start-Process` 起的 GUI 进程会被沙箱清理** ——
  「10 秒后还在、5 分钟后没了」不是崩溃。**最终验证必须老板双击**。
- 🚨 **用户侧同款问题的解法就是这个**：删 `%TEMP%\.net\Lochou启动器\`。
  **下个版本应在 `Program.cs` 启动时自动清理不匹配的解压缓存**，否则只能人工指导。
- 🚨 **更正：清缓存没解决**。真根因在 **Windows 事件日志 Application/SideBySide**：
  `msedgewebview2.exe` 找不到从属程序集 `155.0.4283.62,type="win32"`
  ⇒ `EdgeWebView\Application\155.x\` 下**缺自名子目录**（那才是 SideBySide assembly）⇒ **WebView2 运行时损坏**。
  `winget --force` 只更新注册表；手动 installer `/repair` 未生效。
- ✅ **最终方案：启动器改为不依赖 WebView2**（老板拍板，`launcher/` 重构，见 BH.48）。

## BH.48　启动器去 WebView2 化（2026-10-26）
老板：「不用安装 edge 了，改用 ego-lite」→ 追问后选「**把启动器改成不依赖 WebView2**」。
- 新增 `launcher/LauncherPanelView.cs`（~330 行）：WinForms 原生界面
  （标题/版本/状态/URL/进度条/日志/5 按钮），`ActionRequested(type, payloadJson)` 事件
  + `HandleMessage(json)` 收 C# 消息。
- `Program.cs`：`webView`→`view`；**`InitializeLauncherAsync` 309 行→~35 行**；
  **删掉 `OnWebMessageReceived`（18 种 type 的 switch）**；新增 `OnViewActionRequested`；
  `PostJsonToWebView`→`view.HandleMessage`。
- `csproj`：删 `Microsoft.Web.WebView2` 包。
- 🚨 **关键洞察**：① 7 个 `WINDOW_*` 消息原生窗口自带，直接不要；
  ② C#→UI 只有 `LOG`/`UPDATE_PROGRESS`/`ROLLBACK_PROGRESS` 三种，界面处理极简单；
  ③ `LauncherForm` 的圆角/逐像素透明是**纯 Win32(DWM)**，与 WebView2 无关，**完整保留**；
  ④ `GET_CONFIG`/`TEST_PING`/`ROLLBACK_*` 的 `HandleXxx` 仍留在类里，等设置面板做回来再接。
- 🚨 **publish 不要用 `build-launcher.ps1`**（它输出到根 `dist/` 会混进重复 exe）。
  正确命令：`dotnet publish launcher/InfiniteCanvasLauncher.csproj -c Release -r win-x64
  --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true
  -p:EnableCompressionInSingleFile=true -o output/_launcher-publish` → **68.6 MB**。
- 替换（先备份 `.bak-webview2-20261026`）：仓库根 `Lochou启动器.exe` + 安装目录同名文件。
- 验证：进程存活 149.6 MB、窗口标题正常、**3000 自动起来**、**0x800736B1 消失**。
- ⚠️ `Add-Type` 被安全策略拦（"compiles and loads .NET code at runtime"）⇒ 不能动态编译 P/Invoke 辅助类截图。
- **待办**：exe 变了 ⇒ 要升版本发版（建议 1.2.4）；`dist/launcher/index.html` 虽已不用，
  但 `release.py` 的 `REQUIRED` 仍要它，**别删**。

## BH.49　🚨 原生界面「看不到窗口」= 逐像素透明把整窗吃掉（2026-10-26）
- 现象：老板双击启动器，进程正常起来（12 秒稳定、`MainWindowHandle != 0`、`IsWindowVisible=True`、
  `rect` 正常、无崩溃日志、未触发更新），但**屏幕上什么都看不到**。
- 🚨 **真因**：`LauncherForm.EnablePerPixelCorners()` 把**整个客户区当玻璃**
  （`DwmExtendFrameIntoClientArea(-1)`）。那套是给 WebView2 的（网页画 CSS 圆角 + alpha）；
  **换成 WinForms 原生控件后，玻璃区域里的控件内容被 DWM 合成掉 → 整窗透明**。
- ✅ **修法**：① 注释 `EnablePerPixelCorners()` 调用；② `BackColor` 黑→`FromArgb(9,10,15)`；
  ③ `Opacity` 0.0→**1.0**（原生控件同步渲染，不需要淡入；淡入期透明会被当成「打不开」）；
  ④ 圆角交给 Win11 原生 `DWMWA_WINDOW_CORNER_PREFERENCE`（本来就有）。
- 验证：全屏截图里窗口完整显示（标题/版本/状态/5 按钮/日志区）✓。
- ⚠️ **排查要点**：`Add-Type` 被安全策略拦时用 **Python + ctypes**（`EnumWindows` + `GetWindowRect`
  + `PIL.ImageGrab`）；同名窗口**取面积最大**的；窗口被遮挡时**先截全屏再裁**。
- 遗留：日志刷 `GET /api/... 404` 但状态「服务已停止」⇒ 起服务链路有问题，待查；
  `preferences.json` 的 `keepRunningInBackground:false` ⇒ 点关闭直接退出并停服务。

## BH.50　✅ 启动器最终形态：本地 HTTP + 浏览器打开原界面（2026-10-26）
老板：「启动器跟原来的版本完全不一样了」→ 选「**保留原界面，用浏览器打开**」。
- 新增 `launcher/LauncherHttpHost.cs`：`HttpListener` 起在 **`http://127.0.0.1:5199/`**，
  提供 `dist/launcher/` 静态文件 + `POST /api/bridge`（请求-响应）+ `GET /api/poll?since=N`（长轮询推送）。
- 🚨 **核心技巧：注入 shim，压缩 JS 一行不改**。原界面是 Vite 打包产物
  （`index-D6P_OsbB.js`），通信封装为 `window.chrome?.webview?.postMessage` +
  `addEventListener('message')`。在 `index.html` 的 `<script type="module">` **之前**注入一段
  shim 把 `chrome.webview` 模拟成 fetch 转发即可。
- `Program.cs`：`InitializeLauncherAsync` 起 HTTP + `OpenInDefaultBrowser` + 自动起服务；
  **`Main` 改成 `host.StartLauncher()` + `Application.Run(new ApplicationContext())`**（纯托盘无主窗口）；
  `SendToWebView`/`SendLog` → `http?.Push`；**`HandleBridgeAsync`** 从
  `Program.cs.bak-webview2-20261026` 把原 18 分支 switch 整段捞回来只改签名与返回。
- 验证：`GET /` 200（含 shim）、`POST /api/bridge GET_VERSION` → `{"success":true,"result":{"version":"1.2.2"}}`、
  浏览器标题 `CANVAS · LOCHOU LAUNCHER - ego`、界面完全恢复原样（截图 `output/launcher-browser-ui.png`）。
- ⚠️ **部署要连 `dist/launcher/` 一起复制到安装目录**（界面文件含 shim），只换 exe 界面还是旧的。
- 待办：① 发版（exe + index.html 都变了，升 1.2.4）；② `LauncherPanelView.cs` 已不显示但保留作备选；
  ③ 托盘菜单「打开启动器面板」应改成「在浏览器打开界面」。

## BH.51　❌ 浏览器打开被否决 → CefSharp 也否决 → 最终回退 WebView2（2026-10-26）
老板：「不对 这样是网页页面打开的」⇒ **要独立窗口，不要浏览器标签页**。
- ❌ `ego.exe --app=URL`：ego-lite **不支持 `--app`**（不产生无地址栏窗口）。
- ❌ **CefSharp**：`CefSharp.WinForms` 不支持 net8（NU1701 + NU1903 高危漏洞）→ 必须用
  **`CefSharp.WinForms.NETCore` 154.0.340**（restore 3.5 分钟）。但 **`libcef.dll` 276 MB**，
  publish 目录 **567 MB** ⇒ 发布包从 125 MB 涨到近 700 MB，**不可接受**。
  ⚠️ `PublishSingleFile` 对 CefSharp 无意义（native dll 压不进去）。
- ✅ **最终**：`Program.cs` 回退到 `Program.cs.bak-webview2-20261026`（纯 WebView2），
  csproj 换回 `Microsoft.Web.WebView2 1.0.2903.40`，重新 publish **68.9 MB**。
- 🚨 **修 WebView2 的正确姿势**（`scripts/fix-webview2.ps1`，需管理员）：
  **`winget --force` 单独跑没用** —— 同版本已注册，安装器只更新注册表**不重铺文件**。
  必须**先把「缺自名子目录」的版本目录改名移走**，再 `winget install --id Microsoft.EdgeWebView2Runtime --force`。
  ⚠️ `C:\Program Files (x86)` 下改名需管理员，工具会话里会被拒（访问被拒绝）。
- ⚠️ `dist/launcher/index.html` 里注入的 shim **留着无害**：WebView2 环境下第一行判断直接 return。
- `LauncherHttpHost.cs` / `LauncherPanelView.cs` 现为**死代码**（不引用），留着备选。

### 🚨 `scripts/fix-webview2.ps1` 必须存成 **UTF-8 with BOM**
老板第一次跑报：
```
At ...fix-webview2.ps1:61 char:1  + } else {  Unexpected token '}' ...
The string is missing the terminator: '
```
根因：**PowerShell 5.1 默认按 ANSI/GBK 读无 BOM 的 .ps1**，中文全变乱码 →
`Write-Host '❌ ...'` 的引号被吃掉 → 解析崩。
**修法：文件存成 `utf-8-sig`（带 BOM）**，`[Parser]::ParseFile` 验证 379 tokens 无错。
⚠️ 配套：`修复WebView2.bat` 里 `chcp 65001`（bat 本身用纯 ASCII，避免同类问题）。

### 🚨 改名还会撞「文件被占用」
第二次报：
```
Rename-Item : The process cannot access the file because it is being used by another process
```
实测当时有 **7 个 `msedgewebview2.exe` + 1 个 `Lochou启动器.exe`** 在跑。
⇒ **脚本里加了 Step 0：先 `Kill()` 掉 `msedgewebview2` 和 `Lochou启动器`，`Start-Sleep 3`，再改名**。
（`msedgewebview2` 是运行时进程，杀掉会自动重启，不影响正常应用。）
⚠️ **`Stop-Process` 杀同用户进程不需要管理员**，可以先手动清一遍再让老板跑提权脚本，成功率更高。
⚠️ 该 ps1 后来被改成了**英文输出**（老板或工具改的），改脚本前先 Read 当前内容，别按记忆里的中文版匹配。

### 🚨 第三次撞墙：`GameViewer` 占用 + 改名永远 Access denied
即使提权、即使杀光 `msedgewebview2`，`Rename-Item` 仍报
`System.IO.IOException: 对路径 ... 的访问被拒绝`。
排查结论：
- ACL 正常：`BUILTIN\Administrators:(I)(F)`（继承的完全控制），Owner = `BUILTIN\Administrators`（**不是** TrustedInstaller）。
- **真正的占用者是 `GameViewer`（PID 36188）** —— 通过 `Get-Process | Where-Object { $_.Modules.FileName -like "*EdgeWebView*" }` 抓到。
  ⇒ 这类第三方应用（游戏加速器/远程工具）会常驻加载 WebView2，**改名永远失败**。
- ✅ **结论：不要依赖「改名移走目录」这条路**。改成 **`winget uninstall` + `winget install`** —— 卸载会正常处理占用与权限。
- ⚠️ 如果卸载也失败，先让老板关掉 `GameViewer`（或重启电脑）再跑。
- 抓占用者的正确写法：
  `Get-Process | Where-Object { $_.Modules.FileName -like "*EdgeWebView*" } | Select Id, ProcessName`
  （`Modules` 对部分进程会抛异常，加 `-ErrorAction SilentlyContinue`）

### 🚨 第四次：`winget uninstall` 也救不了（未注册为包）
脚本跑到：`winget uninstall` → **「找不到与输入条件匹配的已安装程序包」**；
`winget install` 成功下载 204 MB、安装成功，**但验证仍是 `exe=True subfolder=False`**。
⇒ **同版本还在，安装器永远跳过文件**。**唯一出路是真正删掉那个损坏目录。**

**最终脚本逻辑（650 tokens 语法 OK）**：
1. **Step 0** 杀 `msedgewebview2` + `Lochou启动器` + **所有 `Modules` 里含 `EdgeWebView` 的进程**
   （实测是 **`GameViewer` PID 36188**，这类游戏加速器/远程工具会常驻加载 WebView2）
2. **Step 1** 先试 `Rename-Item`，失败则**降级为 `Remove-Item -Recurse -Force`**
   （目录已损坏、缺 SideBySide 子目录，删掉不损失任何东西）
3. 都失败就明确提示「关掉 GameViewer 或重启后再跑」
4. **Step 2** `winget uninstall` + `winget install --force`
5. **Step 3** 验证 `msedgewebview2.exe` + 自名子目录是否都在

⚠️ 杀掉 `GameViewer` 会短暂影响老板正在用的那个工具（会自动重启/需手动开），跑之前先告知。

### ✅ 第五次终于定位到真正卡点：**注册表**
杀掉 `GameViewer` 后**改名成功了**（`Moved broken folder: 155.0.4283.62 -> .broken-20261026115108`），
但 `winget install` 装完**验证仍 `exe=True subfolder=False`**。
⇒ 🚨 **WebView2 安装器判断「是否已安装」看的是注册表，不是目录**：
```
HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}
  pv = 155.0.4283.62        ← 只要它还在，安装器就认为已装、跳过所有文件
```
（`HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{...}` 那个 64 位键通常不存在。）

**最终修法（脚本已实现，720 tokens 语法 OK）**：
1. 杀占用进程（含 `Modules` 含 `EdgeWebView` 的，如 `GameViewer`）
2. 改名/删除缺子目录的版本目录
3. **删除上面那个注册表键**（`Remove-Item -Recurse -Force`）
4. `winget uninstall`（未注册会报「找不到」，忽略）
5. `winget install --force` → 此时才是**真正铺全部文件**
6. 验证 `msedgewebview2.exe` + 自名子目录

🚨 **通用教训**：Windows 组件安装器普遍用**注册表**判「已装」，光删目录/`--force` 都没用，
**必须先把注册表项删掉**。

### 🚨🚨 最终真相：**我的验证标准从一开始就是错的**（折腾了 5 轮）
**WebView2 根本没有「自名子目录」！** 那是 **Edge 浏览器**的结构。
WebView2 的 SideBySide assembly 由**同级文件 `<版本>.manifest`** 描述：
```xml
<assembly><assemblyIdentity name='155.0.4283.62' version='155.0.4283.62' type='win32'/>
          <file name='msedge_elf.dll'/></assembly>
```
⇒ **正确的健康判据 = `msedgewebview2.exe` + `<版本>.manifest` + `msedge_elf.dll` 三者同目录**
（`msedgewebview2.exe` 内嵌的 manifest 依赖 `name="155.0.4283.62"`，由这个 `.manifest` 满足）。

**实测最终状态**：`155.0.4283.62  exe=True manifest=True msedge_elf=True  => OK`
- `msedgewebview2.exe --version` / `--headless --dump-dom` 均 **rc=0 无报错**
- **启动器窗口正常**（`CANVAS · LOCHOU LAUNCHER` 1097×617），截图里原界面完整渲染
  （「想象无边界，开启你的无限画布」+ 左侧图标栏 + 版本号），中心像素 `(10,12,18)` = 深色背景 ✓

**真正起作用的修复（按顺序）**：
1. 杀 `GameViewer` 等加载了 `EdgeWebView` 模块的进程（否则目录锁死）
2. 改名/删除缺文件的版本目录
3. **删除注册表键** `HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}`
4. `winget install --force` → 这次才真正铺文件（并补上了 `.manifest`）

⚠️ 脚本的 Verify 段已改成检查 `exe + manifest + msedge_elf`（776 tokens 语法 OK），不再看子目录。

## BH.52　删掉 Release 后重建 1.2.3（2026-10-26）
老板删了 1.2.3 的 Release（连带 tag 一起没了），要求重发。
- 🚨 **`--target` 只认完整 SHA**：`--target 109425b` → `HTTP 422 Release.target_commitish is invalid`；
  必须写全 `109425b4f268eeec972a53f8b76a65f247e7c5ed`。
- 🚨 **上传 126 MB 时容易 EOF 断线**（本次 5 分钟超时）。**但资产其实已全部传完，只是 publish 那步失败**
  → 留下一个 **draft**。此时**不要重传**，直接：
  `gh release edit Official.1.2.3 -R HanaJhon/Infinite-Canvas --draft=false --latest`
- 查 draft 的正确方式：`gh api "repos/<owner>/<repo>/releases?per_page=5" --jq '.[] | "\(.id) draft=\(.draft) tag=\(.tag_name) assets=\(.assets|length)"'`
- ✅ 最终验证：`Official.1.2.3 Latest`；tag sha = `109425b`；
  线上 `releases/latest/download/update.json` → version **1.2.3** / delta(1.2.2, 0.74MB) / full(125.85MB) / notes 14。
- ⚠️ 当时工作区 HEAD 已到 `1317f34`（多了 `Program.cs.bak-webview2-20261026`、`LauncherHttpHost.cs`、
  `LauncherPanelView.cs`、`AGENTS.md`、重编译的 exe），**和发布包不一致**，所以 tag 必须钉在 `109425b`。
- ⚠️ `git ls-remote --tags | grep 1.2.3` 可能因 RTK 过滤/超时返回空，**别据此判断 tag 不存在**，
  用 `gh api repos/.../git/ref/tags/Official.1.2.3` 确认。
