# 项目长期记忆 · Infinite-Canvas

> 索引式硬规则，细节下沉 `REFERENCE.md`（A 启动器 / B `.git` 事故 / C 胶囊 / D API Key / E 磁盘 / F Grsai 模型 / G 磁盘补充 / H 3D 白模 / I 保存接口 / J 前端 / K 3D 界面 / L 服务与 git）；过程见 `YYYY-MM-DD.md`。

## 一、画布数据安全（最高优先级）

- `data/canvases/<32hex>.json` **无回收站、无历史版本、未纳入 git**；删节点是硬删（整份覆盖 PUT），撤销栈只在内存。已发生「陈旧页面抹掉 45 个节点」事故。
- 写画布前：停服务 / 确认无画布页开着 → 备份 + 记 `md5sum` → 测试一律用一次性画布（`POST /api/canvases` → 收尾 `DELETE .../purge`）。
- 收尾三件事：删 `static/__*.html`、purge 一次性画布、`md5sum -c` 比对真实画布哈希；中途报错时 `POST` 可能已建好画布，按标题扫 `data/canvases/` 找孤儿。流程见技能 `infinite-canvas-verify`。

## 二、保存接口（`PUT /api/canvases/{id}`）

- **全量替换**：`nodes`/`connections`/`logs`/`settings` 不传等于清空；**必须传 `base_updated_at`**，两道 409 守卫（旧 base / 静默丢节点）。`GET` 返回 `{"canvas": {...}}`；只改标题走 `POST .../meta`。
- ⚠️ 清 `logs` 要全量回传其余字段（少传 `settings` 会连设置一起清）；清完**必须让用户刷新页面**，否则旧页面会把 logs 写回。详见 `REFERENCE.md` I。

## 三、前端要点

- 全项目只有一份 `static/smart-canvas.html/js/css`；`canvas.html` 不带 `?id=` 会跳选画布页。节点根元素 `.image-node[data-id]`。
- ⚠️ 非空节点的 `.node-head`/`.node-title`/`.node-hint` 被全局隐藏（CSS 574/575/702）→ **新增非图片节点类型必须显式重显**；`.image-node.selected:not(...)` 长 `:not` 链要补新型号。
- ⚠️ 节点拖拽靠 `beginNodeDrag` 的「排除选择器」判断，自吃鼠标事件的区域（如 3D 舞台）必须加进排除列表。
- 改 i18n 必跑 `node static/js/i18n/validate-i18n.js`；`t()` **不做 `{name}` 插值**；JS 动态文案要监听 `studio-lang-change` 重画。
- **验证前端改动务必用全新 `--user-data-dir`**；`render()`（`smart-canvas.js:9166`）是渲染主入口、147 处调用无节流 → WebGL 查看器 DOM 必须复用。其余（lucide PascalCase、canvas-llm 视觉管线、three.js 路径）见 `REFERENCE.md` J。

## 四、模型下拉与 Grsai

- 下拉唯一数据源是 `chatApiProviders()`（`smart-canvas.js:3049`），**只认 `chat_models`**；生图/视频模型不会出现在对话下拉里。3D 节点用 `chatModelOptions()`，不做视觉过滤。
- **Grsai 对话模型 = GPT 4 + Gemini 10 = 14 个**，4 个 GPT 全支持读图。⚠️ 命名 = **OpenAI 官方模型 ID**（`gpt-6-astra`/`gpt-5.6-terra`/`gpt-5.6-sol`/`gpt-5.5`），**别自己编后缀**。清单见 `REFERENCE.md` F。
- ⚠️ 探测三坑：① 按通用命名试 `gpt-4o`/`gpt-5` 全 400 就误判「没有 GPT」（被老板纠正两次）；② **禁止并发扫模型名**（限流会把已知可用的扫成失败）→ 串行 + 间隔 1~1.5s；③ **判「存在」看 200，判「不存在」必须看到 `model not found`**。Grsai 无 `/v1/models`（全 404）只能手填，后端不校验模型是否存在。老板另有 Aizzz 网关（`~/.codex/config.toml`，≥2000 token 门槛）**仅备选**。

## 五、3D 预览节点（`smart-3d`）

- 定位：上游只能「快速生图」、下游也只能「快速生图」，与 prompt/loop/group 双向拒绝（`canAutoConnectDraggedNode()` + `connectInputNode()` 两处都要改）。
- 视觉风格：纯白 `#ffffff` 视口 + 灰白石膏白模 `#d9dce1` + 固定工作室光，无 GridHelper；详见 `REFERENCE.md` H。
- **外框布局约定**：① `padding-top:0` 让标题栏顶到边；② **跳过 `.floating-node-actions` 浮动删除按钮**（模板加 `&& !is3D`）；③ **交互说明入标题栏**（`headSub` → `.node-head-sub`，条件 `is3D && smart3DHasScene(node)`，底部不渲染 `.node-hint`）；④ **标题栏 `padding:0; border-bottom:0`**，且 `.node-delete` 必须显式去 `box-shadow`/`backdrop-filter` 并补 `:hover`（全局 3 类规则压过 `.mini-x:hover`）。验收锚点见 `REFERENCE.md` K.1/K.2。
- **窄节点（`smart3DLayoutSize(node).width < 420`）给 `.smart3d-body` 加 `is-narrow`**，CSS 隐藏 `.smart3d-meta > span`（计数压成纯图标，文案留 `title`）—— 否则 320px 下模型下拉只剩 45px（`G..`/`g..`），折叠后 84.5px。`.smart3d-meta` 内部必须用 `<span>` 包文案作钩子。
- **四个状态要分别验**：成功 / 解析失败 / 请求失败 / 空场景。⚠️ 失败态必须加 `.is-error`，否则与中性空态**同色**（`#8b95a8`）看不出报错；🚨 **舞台在深浅两主题下都是纯白，固定白底区域不要按主题切色**（统一 `#dc2626` = 4.85:1）；`.smart3d-raw` 收起态要退化成一行小字（默认面板吃 36px 视口）。字段/查看器/坑位见 `REFERENCE.md` K。

## 六、本地服务

- 启动：`./python/python.exe main.py`（cwd = 项目根，端口 3000，单进程无 reload）。⚠️ **必须用后台 Bash 任务方式启动**。日志 `output/server.log`；本机 `curl` 不可用（假 502），改用 Python `socket`/`urllib`。
- ⚠️ 启动时 `sync_static_html_versions()` 会重写 `static/*.html` 的 `?v=`（缓存破坏参数），**不要为 git 干净去还原**，否则浏览器继续用旧 JS，表现为「项目功能整个消失」。

## 七、磁盘与 git 硬红线

- ⚠️ 本机「删除即入回收站」→ 清理不释放空间；**真正释放 = 清空回收站**，汇报成果必须同时给回收站占用。
- ⚠️ **绝不要 `git rm <文件>`**（实测整个父目录消失）；用 Python `os.remove` + `git add -A <目录>/`。
- 🚨 `.git` 曾于 2026-09-17 被递归搬进回收站（已完整还原）。防护：维护前 `git bundle create ../repo-<日期>.bundle --all`；瘦身在项目外副本做。
- ⚠️ **工具会话内 `git push` 会无限挂起**（GUI 凭据助手；`ls-remote` 成功是假信号）→ 推送必须由老板本人终端执行。裸 `git` 不可用（RTK 改写），真身在 PortableGit 1.2.0。详见 `REFERENCE.md` B/L。
