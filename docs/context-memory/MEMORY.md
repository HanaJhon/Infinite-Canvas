# 项目长期记忆 · Infinite-Canvas
> 索引:只留「做什么 + 去哪看」。细节 `REFERENCE.md`（A–BH）,过程 `YYYY-MM-DD.md`（§N）。⚠️ **上限 8K,加内容前先下沉 REFERENCE**。

## 〇 启动器红线 → REFERENCE AI
- 🚨 后台线程推 WebView2 用 `PostJsonToWebView`，**禁 `webView.BeginInvoke`**（否则进度恒 0%）。🚨 复用 3000 前先验 `root_fingerprint`，**别占 3000**（保留⇒10013）
## 一 画布数据安全（最优先）→ REFERENCE AI / I
- `data/canvases/<32hex>.json` **无回收站/无历史版本/未入 git**,删节点 = 硬删。
- 写画布前:停服务 + 确认无画布页开着 → 备份 + `md5sum`;测试用一次性画布（`POST /api/canvases` → `DELETE .../purge`）。
- `PUT /api/canvases/{id}` **全量替换 + 必传 `base_updated_at`**;只改标题走 `POST .../meta`。

## 二 前端（J、U.1）→ REFERENCE AI / AQ
- 🚨 改前端必查四条:① 新增非图片节点类型**必须显式重显**;② 自吃鼠标事件的区域加进 `beginNodeDrag` 排除选择器;③ 改 i18n 后自己用 node 正则查重/缺;④ 增删创建菜单卡片**同步改栅格列数**。🚨 lucide:定尺寸**同时写 `i` 和 `svg`**;UMD **导出名 PascalCase**；**列表拖拽排序别用原生 HTML5 拖放** → 手写 pointer 手势。⚠️ 图层列表**显示序 z 降序 / 数组 z 升序**。🚨 改顶部条 `right` 改主规则那行（后者赢），隐藏按钮要补位。🚨 浮层要自己声明 `cursor`（`.shell{grab}` 会继承）。**AQ / BH.26 / BH.32**
- 🚨 **`render()` L13721 就 `return;`，后面 300+ 行死代码**。
- ✅ **新增节点自动对焦**：`focusNodeInViewport()`+`maybeFocusNewNode()` 用**节点 id 差集**判新增。
- 🚨 **偏好设置多选：字段仍是单个字符串、多值用「、」连接**；`agentProfileValues()` **绝不能把 `/` 当分隔符**（选项自带斜杠）。
- 🚨 **改默认态救不了老 localStorage** → 默认值 + **一次性迁移标记**。**BH.27**
- 🚨 **`transition` 下 `getBoundingClientRect()` 读到过渡起点**（设样式后立刻量=旧值）。**BH.30**

## 三 模型下拉与 Grsai → REFERENCE **AI / BA / BH.1–BH.3** + 技能 `gateway-model-probe`
- 下拉唯一数据源 `chatApiProviders()`,**只认 `chat_models`**;3D 用 `chatModelOptions()`。🚨 **画布下拉与启动器清单须一致**;**别因一次 400 剔模型**。🚨 **同通道不许换型号**：仅跨通道才认 `gen.model`，同通道回落界面选中；卡片显示 `gen.exec.model`。**BH.22**
- ✅ 启动器每次联网更新 Grsai 清单：**无 `/models`** → 取文档页内嵌 chunk；缓存 LOCALAPPDATA + **只增不减**。🚨 `404`=chat 路径拼错 → `base_url` 必须裸域名
- 🚨 **生图比例两处必查** → **BH.7**：① 前端 `parseExplicitRatio()` 按原话**确定性覆盖**；
  ② 后端 `runninghub_aspect_from_size()` **精确约分**（`220:147` 不在白名单）⇒ 上游**静默按 1:1**，必须过 `snap_aspect_ratio()`。
  🚨 **「张数 count」≠「prompt 条数」**（条数=方向数）。
- 🚨 **生图参数**：`aspectRatio` + `imageSize`(1K/2K/4K，**无 auto**) + `replyType`，**不是 `size`**；
  **模型判定用「前缀匹配 + 排除斜杠」**；**不许硬编码型号集合**。**BH.1**。
- 🚨 **Grsai 视频** → **REFERENCE BA**：① 只能从 **Apifox 文档站**抓（官网 chunk 零视频）；
  ② `minimax-h3` 比例只认 `portrait/landscape` 且 **1080p 最多 10 秒**；③ 两来源必须**各自 catch**。
  走 `POST /v1/api/generate` + 轮询 `GET /v1/api/result?id=`；**没有 `/v1/videos`**；
  🚨 `canvas_video` 里 Grsai 分支**必须放在 `if is_agnes` 之前**（否则被抢走打错端点）。
- 🚨 **「预设」≠「已保存配置」**：`RECOMMENDED_APIS` 只影响新建通道，列表页读 `data/api_providers.json`。
  🚨 **「只增不减」必须覆盖所有写入路径** → `MergeGrsaiModelList` 第三来源是**已保存通道本身**。**BH.2/BH.3**。
- 🚨 **提示词预设 `minimaxH3`** → 日志 `2026-10-19.md §9`。先判 **T2VA/I2VA/FL2VA/L2VA** 再定有无指令行；
  `S.SS` 两位小数；三字段名不许改；`[Shot 1]` 不写时间戳；`non_diegetic_music` 禁情绪词。
  🚨 **`canvas-llm` 不接收音频** ⇒ 音频只能以文件名进文本，别加 `audios` 字段。
- 🚨 **尺寸出图前必压**；🚨 **gpt-image-2 家族 4K≠4096**（1:1=2880²）⇒ 走 `GPT_IMAGE_FAMILY_SIZES` 表，套 `SIZE_MAP` 算错 3:2/4:3。**BH.18**

## 四 3D 节点（本地 three.js 白模）→ REFERENCE **K/AT**
- 上游只接**「上传」/「分组」**;`canAutoConnectDraggedNode()` + `connectInputNode()` **两处都改**。
- 引擎**只有本地白模**：对话模型视觉识别 → JSON 图元 → `scene3d`。产物只存 `scene3d`。
- 🚨 **HuggingFace 通道已彻底移除**;备份在 `output/rollback-backup/`。**别加回来**。
- 🚨 **随包 Python `sys.path` 无脚本目录** ⇒ 同目录 import 需 `sys.path.insert(0, dirname(abspath(__file__)))`;GLB 归一化=居中+缩到 **2.4**+底面 `y=0`。

## 五 本地服务与启动器 → REFERENCE AI
- 启动 `./python/python.exe main.py --port 8123`（**无 `curl`** → `urllib`）。🚨 静态资源 `/static/` 前缀；**改 `main.py` 必须重启**。
- 🚨 **杀进程前先按 PID 反查 exe 路径**。🚨 **绝不在安装目录（`Infinite-Canvas-Full-*`）跑服务**（锁 `*.pyd`），用完即杀。
- ✅ 只改前端不必重启；🚨 **打包前必须重启**。🚨 沙箱有代理 → 外网 `os error 10061`；**必须清代理**（`env -u HTTP_PROXY`）。🚨 用 `run_in_background` 起（**TaskStop 不连带子进程**）。

## 六 磁盘与 git 硬红线 → REFERENCE AI
- 🚨 **git bash 的 `rm` 直接删、不进回收站**；只有 `Remove-Item` 才进。
  ⇒ **删任何未入 git 的文件前先 `cp` 备份**。🚨 **`rm -rf` 被钩子拦** → 技能 `safe-recycle-cleanup`。
- ⚠️ 删已跟踪文件用 `git add -u`;**绝不裸 `git rm`**。🚨 **`git status` 干净 ≠ 意图达成** → 反查 `git ls-files`。🚨 **推送/发 Release 必须老板本人做**。
## 七 发布 / 版本 / 验证 / 安全 → REFERENCE AI
- ✅ 打包 = `tools/release.py`（含 `scan_release.py` 门禁）;技能 `infinite-canvas-release`;🚨 发布说明两处同步:`static/update-notes.json` + `--notes-file` md。🚨 必须从工作区构建;改 `launcher/*.cs` 要重编 exe;🚨 更新源 = `HanaJhon/Infinite-Canvas`，`update.json` 必须作 Release 资产上传。🚨 判更新**只比版本号** → **同版本号覆盖发布 = 存量用户收不到更新**;🚨 **增量基线 `output/release/<上一版>/file-hashes.json`（重 build 会污染）**。
- 🚨 不要手改 `VERSION` → `tools/bump_version.py`。🚨 无头验证走技能 `infinite-canvas-verify`。🚨 **新根目录 .py 必须登记 `ROOT_FILES`**。
- 🚨 **`?v=` 没变 ≠ 没同步**：`sync_static_html_versions()` 取**文件 mtime**。核对 `?v` == `<VERSION>.<mtime>`。
- 🚨 **`safe_update_notes(payload)` 传整个对象**（非 items 列表），传错返回 `items:0` 且**不报错**。
- 🚨 **构建可能被密钥审计拦在测试文件上** → 写 `.secretsignore`；先确认 `scan_release.py` 有 `load_ignore()`。🚨 `release.py` 的 `PROGRAM_DIRS` 里 **`backend` 是残留**；`git add -A` 会带进 `AGENTS.md`。

## 八 Agent 两套 + Skill 市场（Q/R/W/X）→ REFERENCE **AI / BH.6**
- 🚨 agent 入口只剩一套：`smart-canvas.html` `#agentPanel`→`/api/agent-llm-task`（`gpt-chat.html` 已删）。✅ Skill 市场 = SkillsMP（**缓存优先**）;**`refreshed_at` ×1000**。
- 🚨 **提示词治不了漏字段**：模型会回 `intent:"canvas"`+plan+「已整理」但 `canvas_ops:[]`
  ⇒ 必须代码兜底 `deriveCanvasOpsFromIntent()`（只派生整理/归组/对焦，**建节点/改标题不猜**）+ 时态校正。
- 🚨 **输入框是 contenteditable**（附件内嵌胶囊）→ `.value` 靠 defineProperty 垫片；
  🚨 **overflow 容器里的绝对定位预览必被裁** → 悬停卡克隆到 body 的 fixed 浮层。**BH.6**。
- 🚨 **`[节点:xxx]` 的图必须自己塞进 `reference_images`**（插最前，inpaint 时不加）+ **没遮罩要局部重绘必须拦住不出图**。**BH.8/BH.9**。
- ✅ **Agent 定位 = 任务编排者，不是提示词优化器**：`agentOrchestrationContext()` 每轮注入
  【可用生图能力】【画布现状】【可用画布动作】【能力边界】；输出契约含 `intent` + `plan`。
  🚨 **只给规则不给事实 = 模型只能退化成写提示词**。改 agent 行为先问「它有没有决策依据」。
- 🚨 **多方向落地要看执行层**：`processAgentLlmResult` 曾无条件 `prompts.slice(0,1)`，把「先给 2-3 个方向」废掉
  现按「用户说数字 > 记忆要多方向 > 截 1 条」三档。
- 🚨 **无头验证 agent 别驱动 `sendAgentMessage()`**（流式会卡死）；用「直连 `/api/agent-llm-task`
  → 页面里调 `processAgentLlmResult()`（拦 `runAgentGenerations` 防花钱）」。Grsai 偶发 `completion_tokens:1`，重试即好。
- ✅ **Agent 输入框引用体系**：拖入/粘贴文件 = 内联 token；**Ctrl+C 复制节点 = 直接「发送至 Agent」**
  （不再产生 `[节点:]`）。🚨 **token 写名称不写编号**（编号会漂移）。
  🚨 **复制节点必须走原生 `copy` 事件写剪贴板**，`navigator.clipboard.writeText` 在 WebView 失败。

## 八·补 🚨 后端 `main.py` 是巨石 → REFERENCE **BH.4**
- 🚨 **`1.2.0` 用过两次**：发布包 26560 行无 `backend/`；工作区 29349 行 + 19 模块 ⇒ 先比行数。
- 🚨 **2026-10-18 全部回退**，router 拆分已撤销；备份在 `output/rollback-backup/`。
- ✅ 优化只做「按领域拆 `routers/`」。🚨 **不做**：DI 分层、整体重写、645 处 `HTTPException` 全换、Celery/RQ。
- 🚨 **Brief 需求表：逐模块出图 + 文案原样进 prompt；xlsx 抽取压空列、别截行**。**BH.24**
- 🚨 **工具结果回灌仅 4000 字符** ⇒ 大文件读一半、模型称「被截断」；已改 12000。**BH.25**

## 九 拆分图层（= 发布包 1.2.0 的内联旧实现）→ 日志 `2026-10-18.md §5` + REFERENCE **BH.5**
- 🚨 **当前状态**：拆分图层 = `main.py` **内联实现**（39 处 + `split-layers.css`），**无 `backend/`、无独立 `split-layers.js`**（内联在 `smart-canvas.js`）。
- 🚨 **重做必带（See-through）**：**「像素归属」做不出层，「层生成」才行** —— 被遮挡处没像素可分。验收 = **每层完整 + 顺序对 + 移开不露洞**。
- ✅ **浅色主题**：「浅色默认 + `html.studio-theme-dark` 覆盖」。🚨 最易漏 `.sl-sel-name`/`.sl-op`。
- 🚨 **遮罩下屏蔽 LLM 扩写**：`llmBlockedByInpaint()`/`promptNodeLlmActive()`。只屏蔽显示与运行、**不写坏 `llmEnabled`**。
- 🚨 **局部重绘全链路 → REFERENCE BH.8–BH.10（必读）**：① `inpaint`/`target_node`/`mask_hint` 有**四条转换链**，最易漏 **`_triggerGenerationsIfAllDone`（点确认唯一出口）**；② 目标**唯一匹配**、写 **id 不写标题**；
  ③ 挑不到目标必须 `error`+**0 请求**，绝不静默整图重画；④ **必须回贴**（后端合成整图，差异只在 bbox）；**结果落新节点**。**BH.31**
  ⑤ **没涂遮罩可自动**（bbox→白块 mask）；**附件图同理**：先落节点再造遮罩。**BH.29**
  ⑥ **遮罩默认保留**：只有手动 ×/`clear_mask` 才清；agent 原地改要 `keepInpaintAfterRun` **迁到新图**（换图后 `base_key` 失配）；圆环按**屏幕像素**算。
  ⑦ 🚨 **加字段必改三处**（schema / 格式说明 / 顶层兜底）。🚨 生图失败**绝不删节点**（BH.11）。
  ⑧⑨ 🚨 答不出做法=历史没传（记 `gen.exec`/`msg.ops`，BH.13）；同名节点引用块**必带 id**（BH.14）。
- 🚨 **重编辑历史对话**：`保存并重新生成`=回退重跑 / `仅保存`=改记忆。写输入框必须在 `renderAgentAttachments()` **之后**；重发走 `agentResendCtx` 绕开胶囊对账。**BH.17**
- 🚨 **纯提问/纯理解 ≠ 生图需求**：「整**张图**的」「描述这张图」都命中 `张图`。用 `isQuestionOnly()` / `isUnderstandOnly()` 拦兜底与私塞 prompts。**BH.19/23**

## 十 混元 3D 多视图链路 → REFERENCE **AV/AW**
- `hunyuan3d_client.py`（CDP+Edge）+ `/api/hy3d-tasks` + 前端 `smart-hy3d` 节点。
- 🚨 模型地址 `result[*].urlResult.glb`（`modelUrl3d` 恒 `{}`）；分享 contentId = `result[*].assetId`；**兜底按资产 ID**（重启 404）；**次数实时读** `/api/3d/quotainfo`。
- 🚨 **hy3d 节点必须带 `smart3d-node` 类**；**登录判据 = 能读到 `remainQuota`**。
