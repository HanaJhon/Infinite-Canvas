# 项目长期记忆 · Infinite-Canvas

> 索引式硬规则，细节下沉 `REFERENCE.md`（A 启动器 / B `.git` / C 胶囊 / D Key / E 磁盘 / F Grsai / G 磁盘 / H 3D 白模 / I 保存 / J 前端 / K 3D 界面 / L 服务与 git / M three.js）；过程见 `YYYY-MM-DD.md`。

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
- **验证前端改动务必用全新 `--user-data-dir`**；`render()`（`smart-canvas.js:9166`）无节流 → WebGL 查看器 DOM 必须复用。其余见 J。

## 四、模型下拉与 Grsai

- 下拉唯一数据源是 `chatApiProviders()`（`smart-canvas.js:3049`），**只认 `chat_models`**；3D 节点用 `chatModelOptions()`，不做视觉过滤。
- **Grsai 对话模型 14 个**（GPT 4 + Gemini 10），4 个 GPT 全支持读图；命名 = **OpenAI 官方模型 ID**，别自己编后缀。清单见 F。
- ⚠️ 探测三坑（F.4）：① 别按通用命名猜；② **禁止并发扫** → 串行 + 间隔 1~1.5s；③ **判「不存在」必须看到 `model not found`**。Grsai 无 `/v1/models` 只能手填。

## 五、3D 预览节点（`smart-3d`）

- 上下游都只能接「快速生图」，与 prompt/loop/group 双向拒绝（`canAutoConnectDraggedNode()` + `connectInputNode()` **两处都要改**）。视觉风格见 H。
- **three.js 本地 r160（2023-12）、官方最新 r186（2026-09）**；升级清单见 M。
- 外框 / 标题栏 / 窄节点折叠 / 四态约定全部见 K。最易踩的三条：
  ① 🚨 **折叠阈值必须按实测文案宽度算**（`smart3DBarNeedWidth`），**不能写死像素** —— 英文比中文宽 20~30px；模型名完整显示需 select ≥104px（原生箭头占 19px，DOM 量不出截断）。
  ② ⚠️ 失败态必须加 `.is-error`，否则与中性空态同色；`.smart3d-nomodel` 是阻断性告警必须读得全（`nowrap`+`overflow:hidden` 会硬切，已改允许换行）。
  ③ 🚨 **舞台深浅两主题下都是纯白，白底区域不要按主题切色**。
- **两主题取色方向相反**：挂在**节点面板**上的元素（`.smart3d-nomodel`）**必须**按主题取色；挂在**恒白舞台**上的（`.smart3d-placeholder.is-error`）**绝不能**按主题切（深色换 `#f87171` 掉到 2.76:1）。10px 小字按 AA 4.5:1。基线表见 K.9。

## 六、本地服务

- 启动：`./python/python.exe main.py`（端口 3000，**必须后台 Bash 任务方式启动**，日志 `output/server.log`；本机 `curl` 不可用，改用 Python `socket`/`urllib`）。
- ⚠️ 启动会重写 `static/*.html` 的 `?v=`，**不要为 git 干净去还原**（否则浏览器继续用旧 JS，表现为「项目功能整个消失」）。

## 七、磁盘与 git 硬红线

- ⚠️ 本机「删除即入回收站」→ 清理不释放空间；**真正释放 = 清空回收站**，汇报成果必须同时给回收站占用。
- ⚠️ **绝不要 `git rm <文件>`**（实测整个父目录消失）；用 Python `os.remove` + `git add -A <目录>/`。
- 🚨 `.git` 曾于 2026-09-17 被递归搬进回收站（已还原）。防护：维护前 `git bundle create ../repo-<日期>.bundle --all`；瘦身在项目外副本做。
- ⚠️ **工具会话内 `git push` 会无限挂起** → 推送必须由老板本人终端执行（裸 `git` 不可用，真身在 PortableGit 1.2.0）。详见 B/L。
