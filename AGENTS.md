# AGENTS.md — Infinite-Canvas 项目上下文（DSH / DeepSeek Harness 读取）

> **导出时间**：2026-10-28 ｜ **导出范围**：完整项目记忆（26 个记忆文件，约 1.7 MB）
> **数据来源**：`D:\工作\无限画布\Infinite-Canvas\.workbuddy-ai\memory\`（原始文件已随包完整复制到 `memory/`）
> **本文件定位**：DSH 每次请求都会加载的**入口摘要**。完整细节在 `memory/` 目录，按需读取，不要整体灌入上下文。
> **前身**：本文件基于 2026-10-14 的 `AGENTS.md` 更新，补齐 10-16 → 10-27 的增量（原文件状态停留在 1.2.0）。

---

## 0. DSH 读取指引（先读这一节）

DSH 的 `dsh-agent-instructions` 插件按以下顺序加载指令链：`$DSH_HOME/AGENTS.md` → 项目根 `AGENTS.md` → 子目录 `AGENTS.md`，`CLAUDE.md` 为等价候选，`.local.md` 为追加覆盖。

**建议用法**：

| 你想做什么 | 读哪里 |
|---|---|
| 快速上手、知道红线 | 本文件 §1–§8 |
| 查某个主题的细节 | `memory/MEMORY.md`（索引，13 KB，指向 REFERENCE 章节号） |
| 查具体实现/事故取证 | `memory/REFERENCE.md`（506 个章节，A–BH 编号，551 KB，**按章节读，勿整读**） |
| 查某天做了什么 | `memory/YYYY-MM-DD.md`（24 份日报） |
| 一次性全文检索 | `CONTEXT-ALL.md`（全部记忆按序拼接的单一文件） |

⚠️ **不要**把 `REFERENCE.md` 或 `CONTEXT-ALL.md` 整体读入上下文——它们是检索用的，不是通读用的。

---

## 1. 项目概况

- **是什么**：AI 无限画布（二次开发自 hero8152/Infinite-Canvas，独立维护）。聊天驱动生图 / 图片编辑 / 视频生成 / 灵感库 / 3D 预览 / 拆分图层；支持 OpenAI 协议、ComfyUI、火山方舟、ModelScope、RunningHub、即梦、Grsai 等通道。
- **技术栈**：后端 `main.py`（FastAPI + uvicorn，单进程，端口 **3000**，无 reload，当前 **28,541 行**）；前端 `static/` 原生 JS（无构建）；启动器 `launcher/`（.NET 8，产物 = 仓库根 `Lochou启动器.exe`）。
- **自带 Python**：`./python/python.exe`（3.10），不要用系统 Python。
- **运行**：`./python/python.exe main.py` → http://127.0.0.1:3000/
- **两份代码树（重要）**：

  | | 开发仓库（本目录） | 安装目录（老板日常在用） |
  |---|---|---|
  | root | `D:\工作\无限画布\Infinite-Canvas` | `D:\工作\无限画布\Infinite-Canvas-Full-1.1.4\Infinite-Canvas` |
  | 配置 | `data/api_providers.json` 通常为空 | 真实通道 + `API/.env` 密钥 |

  🚨 启动服务前先 `GET /api/app-info` 确认 3000 上跑的是哪个 root。**开发仓库绝不要长期占 3000**（老板启动器用 3000，被占时老板端读到空配置）。调试用 `--port 3010` 之类，用完即停。
- **版本号规则**：三段式 `X.Y.Z`，每多进一级少一段（`1.1.9`→`1.2.0`、`9.9`→`10`），由 `tools/versioning.py` + `launcher/VersionUtil.cs` 共用 `tools/version_vectors.json` 维护；**不要手改 `VERSION`**，用 `./python/python.exe tools/bump_version.py`。

## 2. 当前状态（截至 2026-10-28 导出时，已核实）

- `VERSION` = **1.2.5**
- git：本地 `main` = `origin/main` = `6506bb1`（chore(release): 1.2.5 —— 多账号系统：数据隔离 / 工作流共享 / 资产库个人团队）。**已 push。**
- ⚠️ 工作区有未提交改动：`M static/index.html`
- **代码结构现状（重要，与 10-16/10-17 日报描述不同）**：
  - ❌ **无 `backend/` 目录**、❌ **无 `routers/` 目录**、❌ **无 `static/js/split-layers.js`**
  - 原因：2026-10-18 后端 router 拆分**全部回退**（备份在 `output/rollback-backup/`）
  - 拆分图层 = `main.py` **内联实现**（39 处 + `split-layers.css`），逻辑内联在 `static/js/smart-canvas.js`
  - 多账号系统靠根目录 `auth.py` 实现（1.2.5 引入）
- **版本演进（1.2.0 之后，来自 git log）**：

  | 版本 | 主题 |
  |---|---|
  | 1.2.1 | Grsai 视频、H3 提示词预设、遮罩屏蔽 LLM |
  | 1.2.2 | 窗口拖拽缩放、参数与思考强度、并发对话、纯提问拦截 |
  | 1.2.3 | 出图张数改由理解模型判断 |
  | 1.2.4 | Agent 图片预览按原比例显示 / 点击看大图 / 可拖到画布 |
  | 1.2.5 | 多账号系统（数据隔离 / 工作流共享 / 资产库个人团队） |

## 3. 项目专用技能（已安装到 `~/.codex/skills/`）

| 技能 | 用途 |
|---|---|
| `infinite-canvas-release` | 干净打包与发布（allow-list、泄漏校验、增量包/更新链路、`tools/release.py` 全量陷阱） |
| `infinite-canvas-verify` | 无头 Edge 验证 UI/JS 改动 + 画布数据安全协议 + i18n 校验 + 假上游 e2e |
| `infinite-canvas-skill-market` | 维护应用内 Skill 市场（清单/两级分类/中文简介，数据源 SkillsMP） |

「改 static/ 要证据」「要打包发版」「要动画布数据」三类任务，先读对应技能再动手。

## 4. 铁律速查（都是踩过坑凝练的，详细版在三个技能 SKILL.md + `memory/REFERENCE.md`）

### 画布数据安全（`data/canvases/*.json`）
- 无回收站、无历史版本、**未纳入 git**，已发生过「陈旧页面抹掉 45 个节点」事故。
- 测试一律用**一次性画布**（`POST /api/canvases` 建 `__test__` → `DELETE /api/canvases/<id>/purge` 收尾），不碰老板真实画布。
- 改盘上前 `md5sum` + `cp` 备份；收尾 `md5sum -c`。无头打开画布页会触发 `POST .../touch`（只刷 `updated_at`，md5 必然变，别当事故）。
- `PUT /api/canvases/{id}` 是**全量替换**，不传 `logs`/`settings` 会清空它们；必须同时传 `base_updated_at`。只改标题走 `POST .../meta`。

### 发布 / 版本
- **不要把工作目录整包压缩**。只走 `./python/python.exe tools/release.py build`（allow-list 主防线）。历史事故：798 MB 包含 `.git/` 528 MB（泄露过 Grsai 密钥 blob）+ 作者私人图片 + 画布 JSON。
- 改 `static/` 后、打包前**必须先跑一次服务**（`main.py:sync_static_html_versions()` 只在启动时把 `static/*.html` 的 `?v=<VERSION>.<mtime>` 重写）——不重启就打包，用户浏览器继续用缓存旧 JS，「功能不生效但版本号变了」。
- `static/*.html` 被 `?v=` 重写后别 `git checkout --` 还原（会造成新旧 CSS/JS 混搭 bug）。
- **增量基线被污染 = 增量包静默漏发主程序**：不要为已发布版本号重新 build；要重打先把 `output/release/<ver>/` 移出去。发版前逐项核对 delta zip 里包含 `main.py` / `smart-canvas.js` / i18n / css。
- 覆盖同版本号发布 ⇒ **已装该版本用户永远收不到提示**（启动器只比版本号不比 hash）。要让所有人拿到改动只能升版本号。
- 更新源 = `HanaJhon/Infinite-Canvas`；`update.json` 必须作为 Release 资产上传。
- `git push` 必须老板本人（工具会话挂起）。本地提交即可，交付 `gh release create` 命令。
- **提交信息含反引号/`$`/`!` 会被 bash 吞字**——先 Write 成文件再 `git commit -F <file>`。
- 🚨 `safe_update_notes(payload)` 传**整个对象**（非 items 列表），传错返回 `items:0` 且**不报错**。
- 🚨 新根目录 `.py` 必须登记 `ROOT_FILES`；构建可能被密钥审计拦在测试文件上 → 写 `.secretsignore`。

### 服务 / 验证
- 起服务**必须后台任务**且**输出重定向到文件**（绝不能 `| head -N`，SIGPIPE 会炸服务）；本机 `curl` 不可信（RTK 代理返回假 502），用 Python `socket`/`urllib`。
- i18n 校验：`node static/js/i18n/validate-i18n.js`（中英双语，任何折叠/隐藏阈值必须按**最宽语言**验证）。
- 语法自查：`./python/python.exe -c "import ast; ast.parse(open('main.py',encoding='utf-8').read())"` / `node --check static/js/<file>.js`。
- 🚨 **agent 入口只剩一套**：`smart-canvas.html` `#agentPanel` → `/api/agent-llm-task`（`gpt-chat.html` 已删除）。
- **不要在本机对任何有历史的仓库跑 `git gc`/`repack`**（2026-09-17 出过 `.git` 被整目录搬进回收站的事故）。
- 🚨 **杀进程前先按 PID 反查 exe 路径**；**绝不在安装目录（`Infinite-Canvas-Full-*`）跑服务**（锁 `*.pyd`），用完即杀。

### 密钥 / 隐私
- `data/api_providers.json`、`API/.env` 是老板真实配置/密钥——只追加不改写，测完 md5 还原，绝不回显。
- 发布包 deny-list：`.git/ .workbuddy-ai/ .claude/ API/ assets/ output/ data/`；`data/asset_library.json` 绝不能随包分发。

## 5. 前端与模型通道铁律（摘要，细节见 `memory/MEMORY.md` §二/§三）

- 🚨 改前端必查四条：① 新增非图片节点类型**必须显式重显**；② 自吃鼠标事件的区域加进 `beginNodeDrag` 排除选择器；③ 改 i18n 后自己用 node 正则查重/缺；④ 增删创建菜单卡片**同步改栅格列数**。
- 🚨 `render()` 在 `smart-canvas.js` L13721 就 `return;`，后面 300+ 行是**死代码**。
- 🚨 **偏好设置多选：字段仍是单个字符串、多值用「、」连接**；`agentProfileValues()` **绝不能把 `/` 当分隔符**。
- 🚨 **改默认态救不了老 localStorage** → 默认值 + **一次性迁移标记**。
- 🚨 **`transition` 下 `getBoundingClientRect()` 读到过渡起点**（设样式后立刻量 = 旧值）。
- 模型下拉唯一数据源 `chatApiProviders()`，**只认 `chat_models`**；3D 用 `chatModelOptions()`；🚨 画布下拉与启动器清单须一致；**别因一次 400 剔模型**。
- 🚨 **生图参数**：`aspectRatio` + `imageSize`(1K/2K/4K，**无 auto**) + `replyType`，**不是 `size`**；**模型判定用「前缀匹配 + 排除斜杠」**，不许硬编码型号集合。
- 🚨 **gpt-image-2 家族 4K ≠ 4096**（1:1 = 2880²）⇒ 走 `GPT_IMAGE_FAMILY_SIZES` 表。
- 🚨 **生图比例两处必查**：前端 `parseExplicitRatio()` 确定性覆盖；后端 `runninghub_aspect_from_size()` 精确约分，必须过 `snap_aspect_ratio()`（否则上游静默按 1:1）。
- 🚨 **「张数 count」≠「prompt 条数」**（条数 = 方向数）。
- 🚨 **Grsai**：`base_url` 必须裸域名（`404` = chat 路径拼错）；走 `POST /v1/api/generate` + 轮询 `GET /v1/api/result?id=`，**没有 `/v1/videos`**；`canvas_video` 里 Grsai 分支**必须放在 `if is_agnes` 之前**。
- 🚨 **「预设」≠「已保存配置」**：`RECOMMENDED_APIS` 只影响新建通道，列表页读 `data/api_providers.json`。

## 6. Agent 编排铁律（`memory/MEMORY.md` §八）

- ✅ **Agent 定位 = 任务编排者，不是提示词优化器**：`agentOrchestrationContext()` 每轮注入【可用生图能力】【画布现状】【可用画布动作】【能力边界】；输出契约含 `intent` + `plan`。
- 🚨 **只给规则不给事实 = 模型只能退化成写提示词**。改 agent 行为先问「它有没有决策依据」。
- 🚨 **提示词治不了漏字段**：模型会回 `intent:"canvas"` + plan + 「已整理」但 `canvas_ops:[]` ⇒ 必须代码兜底 `deriveCanvasOpsFromIntent()`。
- 🚨 **输入框是 contenteditable**（附件内嵌胶囊）→ `.value` 靠 defineProperty 垫片。
- 🚨 **`[节点:xxx]` 的图必须自己塞进 `reference_images`**（插最前，inpaint 时不加）+ **没遮罩要局部重绘必须拦住不出图**。
- 🚨 **工具结果回灌仅 4000 字符**（已改 12000）⇒ 大文件读一半、模型称「被截断」。

## 7. 本机环境坑（与工具会话直接相关）

- **PowerShell 工具常吞 stdout**：判断某物是否存在时，写文件再用 Read 读，别信空输出。
- **裸 `git` 被 RTK hook 改写后不可用**（`rtk: Failed to resolve 'git'`）；需要时用全路径 `C:/Users/Administrator/.workbuddy-ai/binaries/PortableGit/versions/1.2.0/mingw64/bin/git.exe`。
- **node 的 child_process 用管道捕获输出（stdio pipe/execSync）一律 EBUSY**（宿主沙箱限制），`inherit`/`ignore` 正常。
- **工具会话内 dotnet 报 `Value cannot be null. (Parameter 'path1')`**：缺 17 个标准 Windows 环境变量。用 `~/.workbuddy-ai/skills/launcher-web-sync/scripts/dotnet_env.py` 补齐后再 exec。
- 🚨 **沙箱有代理 → 外网 `os error 10061`**；必须清代理（`env -u HTTP_PROXY`）。
- 🚨 **git bash 的 `rm` 直接删、不进回收站**；只有 `Remove-Item` 才进。**删任何未入 git 的文件前先 `cp` 备份**。`rm -rf` 被钩子拦 → 技能 `safe-recycle-cleanup`。
- 涉外部服务（生图/LLM）优先走技能 `grsai-image-gen`（默认 nano-banana-2.1 / 4K）；Grsai 网关模型名是 OpenAI 官方 ID，**禁止按通用命名猜**、禁止并发扫模型名。
- Cloudflare 前置网关要显式带 `User-Agent`，否则 403。

## 8. 关键文件地图

| 路径 | 职责 |
|---|---|
| `main.py` | 全部后端（28,541 行）：路由 / 画布 CRUD / LLM 任务 / Skill 市场 / i18n 版本 / 更新检测 / 打包调用 |
| `auth.py` | 多账号系统（1.2.5 引入） |
| `hunyuan3d_client.py` | 混元 3D 多视图链路（CDP + Edge） |
| `static/js/smart-canvas.js` | 画布前端主逻辑（约 1 万行，节点渲染/交互/agent 面板/拆分图层内联实现） |
| `static/smart-canvas.html` / `canvas.html` | 画布页 / 经典编辑器页 |
| `static/js/i18n/` | 中英文案（`common.js` `canvas.js` `api-settings.js` `smart-canvas.js` …） |
| `tools/release.py` | 发布打包（allow-list / verify / manifest） |
| `tools/bump_version.py` `tools/versioning.py` | 版本号升降（唯一权威规则） |
| `launcher/Program.cs` `launcher/UpdateApplier.cs` | 启动器与更新执行器 |
| `data/inspire_prompt_zh.json` | 唯一随包分发的 data 文件（灵感库提示词） |
| `CLI/windows/openai/` | Codex / Gemini / 即梦 CLI 安装启动脚本 |

## 9. 2026-10-16 → 10-27 增量索引（原 AGENTS.md 未覆盖）

> 以下只是**日报章节索引**，用于定位；细节请打开对应 `memory/<日期>.md`。

| 日期 | 章节主题 |
|---|---|
| 10-16 | §1 抠图与可复用背景素材（新增背景资产模块、抠图质量、后端接线、前端、验证、踩坑、遗留） |
| 10-17 | §1 P4 收尾（元素级拆分重构）；§2 界面不像豆包 + 无法针对指定图像拆分；§3 See-through 调研 |
| 10-18 | §1 后端重构第一步：修 `read_text_attachment` 重名 + 拆出 `routers/history.py`；§2 继续拆 `routers/skills.py` / `routers/prompts.py`（⚠️ **后于同日全部回退**） |
| 10-19 | §1 修 Grsai nano-banana-2.1 参数未对齐（4K 无效 / 不支持 auto）；§2 模型清单同步 + 拉取后自动同步预设 |
| 10-20 | §1 偏好设置字段结构调整；§2「先给 2-3 个方向」被系统提示词压死；§3 出图永远 1:1 的真因（两层）；§4 新增节点自动对焦；§5 Agent 从「提示词优化器」改成「任务编排者」 |
| 10-21 | §1 思考模式直接失败：尺寸护栏 + 失败要给出路；§2 更正：2880×2880 是该家族官方 4K 档，不是压缩结果 |
| 10-22 | §一 Agent 输入框显示两个模型 pill + 修鼠标抓手（`cursor` 继承）；§二 对话标题可重命名（标题优先级反了） |
| 10-26 | §一 取消 agent 图片数量强规则，改由理解模型判断（含两个环境坑 + Edge 安装损坏排查）；§二 构建 1.2.3 并查出一个大问题 |
| 10-27 | §一 多账号系统（局域网多人使用，架构 + 10 项测试 + 坑 + 待办）；§二 首页空白——`/` 被放进免鉴权名单；§三 注册成功后页面显示 `{"detail":"Not Found"}` |

更早（09-03 → 10-14）的日报同样在 `memory/` 目录，主题已基本沉淀进 `memory/MEMORY.md` 与 `memory/REFERENCE.md`。

## 10. 原始对话索引（可按需深挖，但勿整读）

WorkBuddy 会话记录（jsonl，`type=message, role=user/assistant`）：

| 文件 | 时间 | 主题 |
|---|---|---|
| `C:\Users\Administrator\.workbuddy-ai\projects\d-工作-无限画布-Infinite-Canvas\713f75a5-….jsonl` | 2026-09-17 → 10-13 | **主会话**（1109 条用户消息：启动器改版、项目胶囊、回收站、模型测速、3D 预览节点、拆分图层+在线PS、混元3D节点、1.1.x→1.2.0 全部发版） |
| `…\d-工作-无限画布-Infinite-Canvas\167416ee-….jsonl` | 2026-09-16 | 启动器打包形式研究（WebView 壳 vs 原生） |
| `…\d-工作-无限画布-Infinite-Canvas-agent\1e3e07dc-….jsonl` | 2026-09-03 | 正式版制作：清除用户残留与密钥 |
| `…\d-工作-无限画布-Infinite-Canvas-agent-Infinite-Canvas-agent-main\8f12f913-….jsonl` | 2026-09-03 | Grsai API 地址修正（`api.grsai.com` → `grsai.dakka.com.cn`） |

> 主会话 585 MB / 1565 turns，**不要整体读入**。用上表定位时间段，或优先读三个技能 SKILL.md（已是凝练版）。

---

*本文件由 WorkBuddy 于 2026-10-28 从项目记忆完整导出生成。记忆原文见同目录 `memory/`，全文拼接版见 `CONTEXT-ALL.md`。*
