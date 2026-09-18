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

## H. 3D 预览：恢复白模工作室渲染（2026-09-18）

按老板最新要求恢复为：**纯白 `#ffffff` 视口 + 灰白白模 + 工作室环境光**。查看器固定 `SMART_3D_STUDIO` 视觉，不再让旧场景或模型输出的颜色、灯光、地面字段覆盖当前观感。

### H.1 当前实现

- 环境：每个 WebGL 查看器独立创建 PMREM 摄影棚环境贴图，并绑定 `scene.environment`；销毁查看器时释放环境目标，避免跨 WebGL 上下文复用。
- 灯光：`HemisphereLight(0.34)` + 主/辅/轮廓三盏 `DirectionalLight`（`1.35 / 0.46 / 0.60`），主光开启阴影。
- 地面：`ShadowMaterial({opacity:0.2})` 平面，只接收柔和接触阴影；背景固定纯白。
- 对象材质：所有图元统一灰白石膏材质 `#d9dce1`、roughness `0.62`，plane 使用双面材质克隆。
- `normalize3DScene()` 对旧场景做几何字段兼容，返回值只保留相机和图元；FOV 滑块与相机姿态持久化继续保留。

### H.2 历史场景驱动方案（已撤回）

此前的 `SMART_3D_STUDIO`、PMREM、半球光、三点方向光与接触阴影方案已从运行代码移除；详情保留在提交 `86b30ce` 与当日工作日志中。

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
