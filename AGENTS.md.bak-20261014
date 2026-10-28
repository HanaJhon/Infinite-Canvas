# AGENTS.md — Infinite-Canvas 项目记忆（供 Codex 读取）

> 本文件由 WorkBuddy 于 2026-10-14 从「空间中的 agent 对话记忆」蒸馏生成。
> 包含：项目概况、当前状态、待继续的任务、铁律速查、本机环境坑、技能索引。
> 更完整的历史记忆见 `output/agent-memory-export-20261014.md`（同目录）。
> 本文件默认不入库、不进发布包（release.py 用 allow-list，AGENTS.md 不在其中）。

---

## 1. 项目概况

- **是什么**：AI 无限画布（二次开发自 hero8152/Infinite-Canvas，独立维护）。聊天驱动生图 / 图片编辑 / 视频生成 / 灵感库；支持 OpenAI 协议、ComfyUI、火山方舟、ModelScope、RunningHub、即梦、Grsai 等通道。
- **技术栈**：后端 `main.py`（FastAPI + uvicorn，单进程，端口 **3000**，无 reload）；前端 `static/` 原生 JS（无构建）；启动器 `launcher/`（.NET 8，产物 = 仓库根 `Lochou启动器.exe`，单文件压缩包）。
- **自带 Python**：`./python/python.exe`（3.10），不要用系统 Python。
- **运行**：`./python/python.exe main.py` → http://127.0.0.1:3000/
- **两份代码树（重要）**：
  | | 开发仓库（本目录） | 安装目录（老板日常在用） |
  |---|---|---|
  | root | `D:\工作\无限画布\Infinite-Canvas` | `D:\工作\无限画布\Infinite-Canvas-Full-1.1.4\Infinite-Canvas` |
  | 配置 | `data/api_providers.json` 通常为空 | 真实通道 + `API/.env` 密钥 |
  - 🚨 启动服务前先 `GET /api/app-info` 确认 3000 上跑的是哪个 root。**开发仓库绝不要长期占 3000**（老板启动器用 3000，被占时老板端读到空配置）。调试用 `--port 3010` 之类，用完即停。
- **当前版本**：`VERSION` = **1.2.0**。版本号规则：三段式 `X.Y.Z`，每多进一级少一段（`1.1.9`→`1.2.0`、`9.9`→`10`），由 `tools/versioning.py` + `launcher/VersionUtil.cs` 共用 `tools/version_vectors.json` 维护；**不要手改 VERSION**，用 `./python/python.exe tools/bump_version.py`。

## 2. 当前状态（截至 2026-10-14 导出时）

- git：本地 `main` = `origin/main` = `b9cfd20`（chore(release): 1.2.0 —— 把粘贴/拖拽两个修复放进新版本号）。**已 push。**
- tag `Official.1.2.0` **已推到远端**；但 **GitHub Release 尚未创建**（`gh release view Official.1.2.0` → release not found）。
- 构建产物已就绪（10-13 18:02 构建，`output/release/1.2.0/`）：
  - 完整包 `Infinite-Canvas-Full-1.2.0.zip`（125.67 MB，sha256 `f8c4dbc2edf0b2b9…`）
  - 增量包 `Infinite-Canvas-Update-1.2.0.zip`（**0.65 MB，正常**——本次未换启动器 exe；delta 20 条目已逐字节核对）
  - `update.json`（必须作为 Release 资产上传，启动器从 `releases/latest/download/update.json` 取）
- 线上实况：远端 `update.json` 的 1.1.9 实为 17:23 构建（**已含「在线生图多图上传」修复**，只缺「画布拖拽」修复）。

## 3. 待继续的任务（按优先级）

1. **[P0] 创建 GitHub Release `Official.1.2.0`**（tag 已有、release 未建，用 `create` 不用 `--clobber`）：
   ```bash
   gh release create Official.1.2.0 \
     "D:\工作\无限画布\Infinite-Canvas\output\release\1.2.0\Infinite-Canvas-Update-1.2.0.zip" \
     "D:\工作\无限画布\Infinite-Canvas\output\release\1.2.0\Infinite-Canvas-Full-1.2.0.zip" \
     "D:\工作\无限画布\Infinite-Canvas\output\release\1.2.0\update.json" \
     --title "Official.1.2.0" --notes-file "D:\工作\无限画布\Infinite-Canvas\output\RELEASE_NOTES-1.2.0.md"
   ```
   完整命令与注意事项见 `output/release/1.2.0/release-summary.txt`。
   ⚠️ 演进化约定：发布由**老板在自己终端执行**（工具会话内 `git push` 会因凭据助手挂起；`gh release create` 不涉及 push，可尝试，失败/挂起则转交老板）。
2. **[P1] 待老板决策**：1.2.0 更新说明第一条「在线生图多图上传」对 1.1.9 用户是已拥有的修复——是否改成只写「画布拖拽」那条（`static/update-notes.json` 与 `output/RELEASE_NOTES-1.2.0.md`；改了要重新构建 + 重建 release）。不改也无功能危害。
3. **[P2] 已知历史积压**（未验证是否仍在计划内，做前先问老板）：画布 Agent 输入 `/` 后唤出 skill 选择浮窗（2026-09-23 记「加入下一个版本」）。

## 4. 项目专用技能（已安装到 Codex 技能目录 `~/.codex/skills/`）

| 技能 | 用途 |
|---|---|
| `infinite-canvas-release` | 干净打包与发布（allow-list、泄漏校验、增量包/更新链路、`tools/release.py` 全量陷阱） |
| `infinite-canvas-verify` | 无头 Edge 验证 UI/JS 改动 + 画布数据安全协议 + i18n 校验 + 假上游 e2e |
| `infinite-canvas-skill-market` | 维护应用内 Skill 市场（清单/两级分类/中文简介，数据源 SkillsMP） |

「改 static/ 要证据」「要打包发版」「要动画布数据」三类任务，先读对应技能再动手。

## 5. 铁律速查（都是踩过坑凝练的，详细版在三个技能 SKILL.md）

### 画布数据安全（`data/canvases/*.json`）
- 无回收站、无历史版本、**未纳入 git**，已发生过「陈旧页面抹掉 45 个节点」事故。
- 测试一律用**一次性画布**（`POST /api/canvases` 建 `__test__` → `DELETE /api/canvases/<id>/purge` 收尾），不碰老板真实画布。
- 改盘上前 `md5sum` + `cp` 备份；收尾 `md5sum -c`。无头打开画布页会触发 `POST .../touch`（只刷 `updated_at`，md5 必然变，别当事故）。

### 发布/版本
- **不要把工作目录整包压缩**。只走 `./python/python.exe tools/release.py build`（allow-list 主防线）。历史事故：798 MB 包含 `.git/` 528 MB（泄露过 Grsai 密钥 blob）+ 作者私人图片 + 画布 JSON。
- 改 `static/` 后、打包前**必须先跑一次服务**（`main.py:sync_static_html_versions()` 只在启动时把 `static/*.html` 的 `?v=<VERSION>.<mtime>` 重写）——不重启就打包，用户浏览器继续用缓存旧 JS，「功能不生效但版本号变了」。
- `static/*.html` 被 `?v=` 重写后别 `git checkout --` 还原（会造成新旧 CSS/JS 混搭 bug）。
- **增量基线被污染 = 增量包静默漏发主程序**：不要为已发布版本号重新 build；要重打先把 `output/release/<ver>/` 移出去。发版前逐项核对 delta zip 里包含 `main.py` / `smart-canvas.js` / i18n / css。
- 覆盖同版本号发布 ⇒**已装该版本用户永远收不到提示**（启动器只比版本号不比 hash）。要让所有人拿到改动只能升版本号。
- `git push` 必须老板本人（工具会话挂起）。本地提交即可，交付 `gh release create` 命令。
- **提交信息含反引号/`$`/`!` 会被 bash 吞字**——先 Write 成文件再 `git commit -F <file>`。

### 服务/验证
- 起服务**必须后台任务**且**输出重定向到文件**（绝不能 `| head -N`，SIGPIPE 会炸服务）；本机 `curl` 不可信（RTK 代理返回假 502），用 Python `socket`。
- i18n 校验：`node static/js/i18n/validate-i18n.js`（中英双语，任何折叠/隐藏阈值必须按**最宽语言**验证）。
- 语法自查：`./python/python.exe -c "import ast; ast.parse(open('main.py',encoding='utf-8').read())"` / `node --check static/js/<file>.js`。
- **项目里有两套 agent**（`static/gpt-chat.html` → `/api/chat/agent`；画布页 `#agentPanel` → `/api/agent-llm-task`），任何 agent 能力改动**两边都要改、都要测**。
- `PUT /api/canvases/{id}` 是**全量替换**，不传 `logs`/`settings` 会清空它们；必须同时传 `base_updated_at`。
- **不要在本机对任何有历史的仓库跑 `git gc`/`repack`**（2026-09-17 出过 `.git` 被整目录搬进回收站的事故，已还原；要瘦身在项目外副本上做）。

### 密钥/隐私
- `data/api_providers.json`、`API/.env` 是老板真实配置/密钥——只追加不改写，测完 md5 还原，绝不回显。
- 发布包 deny-list：`.git/ .workbuddy-ai/ .claude/ API/ assets/ output/ data/`；`data/asset_library.json` 绝不能随包分发。

## 6. 本机环境坑（与 Codex 会话直接相关）

- **PowerShell 工具常吞 stdout**：判断某物是否存在时，写文件再用 Read 读，别信空输出。
- **裸 `git` 被 RTK hook 改写后不可用**（`rtk: Failed to resolve 'git'`）；需要时用全路径 `C:/Users/Administrator/.workbuddy-ai/binaries/PortableGit/versions/1.2.0/mingw64/bin/git.exe`。
- **node 的 child_process 用管道捕获输出（stdio pipe/execSync）一律 EBUSY**（宿主沙箱限制），`inherit`/`ignore` 正常。
- **工具会话内 dotnet 报 `Value cannot be null. (Parameter 'path1')`**：缺 17 个标准 Windows 环境变量。用 `~/.workbuddy-ai/skills/launcher-web-sync/scripts/dotnet_env.py` 补齐后再 exec。
- 涉外部服务（生图/LLM）优先走技能 `grsai-image-gen`（默认 nano-banana-2.1 / 4K）；Grsai 网关模型名是 OpenAI 官方 ID（`gpt-6-astra` 等），**禁止按通用命名猜**、禁止并发扫模型名。
- Cloudflare 前置网关要显式带 `User-Agent`，否则 403。

## 7. 关键文件地图

| 路径 | 职责 |
|---|---|
| `main.py` | 全部后端：路由 / 画布 CRUD / LLM 任务 / Skill 市场 / i18n 版本 / 更新检测 / 打包调用 |
| `static/js/smart-canvas.js` | 画布前端主逻辑（约 1 万行，节点渲染/交互/agent 面板） |
| `static/smart-canvas.html` / `canvas.html` | 画布页 / 经典编辑器页 |
| `static/js/i18n/` | 中英文案（`common.js` `canvas.js` `api-settings.js` `smart-canvas.js` …） |
| `tools/release.py` | 发布打包（allow-list / verify / manifest） |
| `tools/bump_version.py` `tools/versioning.py` | 版本号升降（唯一权威规则） |
| `launcher/Program.cs` `launcher/UpdateApplier.cs` | 启动器与更新执行器 |
| `data/inspire_prompt_zh.json` | 唯一随包分发的 data 文件（灵感库提示词） |
| `CLI/windows/openai/` | Codex / Gemini / 即梦 CLI 安装启动脚本（`2-start_openai_codex_cli.bat` = cd 项目根跑 `codex`） |

## 8. 对话记忆原始索引（Codex 可按需深挖）

WorkBuddy 会话记录（jsonl，`type=message, role=user/assistant, content=[{type:input_text|output_text}]`）：

| 文件 | 时间 | 主题 |
|---|---|---|
| `C:\Users\Administrator\.workbuddy-ai\projects\d-工作-无限画布-Infinite-Canvas\713f75a5-….jsonl` | 2026-09-17 → 10-13 | **主会话**（1109 条用户消息：启动器改版、项目胶囊、回收站、模型测速、3D 预览节点、拆分图层+在线PS、混元3D节点、1.1.x→1.2.0 全部发版） |
| `…\d-工作-无限画布-Infinite-Canvas\167416ee-….jsonl` | 2026-09-16 | 启动器打包形式研究（WebView 壳 vs 原生） |
| `…\d-工作-无限画布-Infinite-Canvas-agent\1e3e07dc-….jsonl` | 2026-09-03 | 正式版制作：清除用户残留与密钥 |
| `…\d-工作-无限画布-Infinite-Canvas-agent-Infinite-Canvas-agent-main\8f12f913-….jsonl` | 2026-09-03 | Grsai API 地址修正（`api.grsai.com` → `grsai.dakka.com.cn`） |

蒸馏后的项目长期记忆（全局，含大量本机环境规则）：
`C:\Users\Administrator\.workbuddy-ai\user-90173419-63cb-43e2-8931-0e8c9407dc58-personal\MEMORY.md`。

> 注意：jsonl 是**逐字对话流水**（主会话 477 MB / 5.8 万行），不要整体读入；用上面的索引定位时间段，或优先读三个技能的 SKILL.md（已是凝练版）。
