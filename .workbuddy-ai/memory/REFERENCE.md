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
- **git 历史**（`API/.env` 已于 `18b4dcd` 取消跟踪，但 `9bdb54c` 有 Grsai key、`74b5c8c`/`3041576` 有 ModelScope key；已推 GitHub → 只能轮换）

- `CleanOrphanedEnvKeys()`（`Program.cs:1351`）删通道时**只置空孤立 key 的值、不删整行**，且只处理 `API_PROVIDER_` 前缀 → **内置通道 key 不会被清**。
- 清 WebView2 残留前确认进程归属：`Get-CimInstance Win32_Process` 看 `--user-data-dir`（`wmic` 被安全策略拉黑）；在跑的 `msedgewebview2.exe` 往往属于别的程序。

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

## L. 本地服务与 git 红线补充（从 MEMORY.md 下沉）

- ⚠️ **启动时 `sync_static_html_versions()`（`main.py:1743`）把 `static/*.html` 的 `?v=` 重写为 `<VERSION>.<资源mtime>` 并写回磁盘** → 每次重启让十几个 html 变 modified。**这是缓存破坏参数，必须保持最新，不要为 git 干净去 `git checkout` 还原** —— 踩过：还原后浏览器继续用缓存旧 JS，而新 CSS 已隐藏 iframe 内原胶囊 → 两个胶囊都不显示，表现为「项目功能整个消失」。
- ⚠️ **本机「删除即入回收站」→ 清理不释放磁盘空间**（`shutil.rmtree`、`SHFileOperationW`、`git gc` 删旧 pack 都只是搬进回收站）。**真正释放 = 清空回收站**，汇报成果必须同时给回收站占用。
- ⚠️ **绝不要用 `git rm <文件>`** —— 实测让**整个父目录消失**（`packages/` 41 文件、`tests/` 两次复现）。恢复用 `git checkout HEAD -- <目录>/`；**正确做法**是 Python `os.remove` / ctypes `DeleteFileW` 删文件再 `git add -A <目录>/`。
- **裸 `git` 不可用**（RTK hook 改写成 `rtk git`，rtk 解析不到）。真身：`C:/Users/Administrator/.workbuddy-ai/binaries/PortableGit/versions/1.2.0/mingw64/bin/git.exe`。`git status --cached` 非法，看暂存用 `git diff --cached --name-status`。
- ⚠️ **工具会话内 `git push` 会无限挂起**：系统级 `credential.helper=helper-selector`（GUI 助手）无界面时静默挂起；`git credential fill` → `could not read Username ... terminal prompts disabled`。**`ls-remote` 成功是假信号**（公开仓库匿名可读）。已排除直连出口、代理、HTTP/1.1、postBuffer、数据量（仅 138 对象）。结论：**推送必须由老板本人终端执行**。
