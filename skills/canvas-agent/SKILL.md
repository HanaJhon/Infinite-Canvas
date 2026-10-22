# Skill: 画布全功能手册（节点 / 参数 / 操作协议）

> 这是**当前这块画布**的能力地图。用户让你操作画布或生成内容时，先对照本手册确认：
> 有哪些节点类型、每个参数的真实取值范围、以及怎么把动作写成 `canvas_ops`。
> **不要凭想象编造不存在的节点类型或参数名。**

## 一、节点类型（`create_node` 的 `type`）

`type` 按子串匹配，以下写法都认：`image` / `prompt` / `loop` / `minimax` / `3d` / `hy3d` / `group`。

| type | 节点 | 用途 |
| --- | --- | --- |
| `image` | 上传/图片节点 | 载入参考图、承接生成结果；没有 type 时的默认值 |
| `prompt` | 提示词节点 | 存提示词文本，可带 LLM 扩写；连到图片节点作为指令来源 |
| `loop` | 循环节点 | 同一提示词按轮次反复生成，做变体探索 |
| `minimax` | 视频节点 | 视频生成（MiniMax / Grsai 视频通道） |
| `3d` | 3D 预览节点 | 用对话模型看图 → 生成 JSON 图元 → three.js 白模渲染 |
| `hy3d` | 混元 3D 节点 | 多视图生成 GLB 模型（需登录，有额度限制） |
| `group` | 智能分组 | 把多个节点收进一个可折叠分组 |

**附件没有独立 type**：产物落文件用 `create_file_node`，用户自己传文件就建 `image` 节点。

## 二、连线（`connect`）

```json
{"op":"connect","from":"来源节点 id 或标题","to":"目标节点 id 或标题","kind":"input"}
```

- 数据流向：`from` 的输出喂给 `to`。
- 常见链：`prompt → image`（提示词驱动出图）、`image → loop`（拿图做变体）、`image → minimax`（图生视频）。
- 节点既可用 `id` 也可用**标题**引用，标题支持模糊匹配（小写包含）。

## 三、生成参数（界面上已无选择器，由你判断）

每条 generation 可带自己的参数：

```json
{"prompt":"...","count":1,"ratio":"square","resolution":"4k","quality":"high"}
```

### `ratio` 白名单（**只能用这 9 个键，写错会被丢弃**）

| 键 | 比例 | 典型用途 |
| --- | --- | --- |
| `square` | 1:1 | 头像、商品主图、默认值 |
| `portrait` | 2:3 | 竖版海报 |
| `portrait43` | 3:4 | 竖版配图 |
| `landscape43` | 4:3 | 横版配图 |
| `landscape` | 3:2 | 横版摄影 |
| `story` | 9:16 | 手机竖屏、短视频封面 |
| `wide` | 16:9 | 视频封面、横屏 |
| `ultrawide` | 21:9 | 超宽银幕 |
| `ultratall` | 9:21 | 超长竖图 |

### `resolution`
`1k` / `2k` / `4k`。**默认 4k**；用户要草稿、要速度才降到 `2k` 或 `1k`。

### `quality`
`high` / `medium` / `low`。**默认 high**。

### `count`
1~8。**默认 1**；用户明确要多版才增加。

### 无法判断时
一律 `高质量 · 4K · 1:1 · 1 张`（`{"ratio":"square","resolution":"4k","quality":"high","count":1}`）。
**不要为了确认参数而追问用户。**

## 四、视频参数（`minimax` 节点相关）

| 模型 | 比例 | 分辨率 | 时长 |
| --- | --- | --- | --- |
| `minimax-h3` | **只认横/竖**（`16:9` 或 `9:16`） | `480p` / `768p` / `1080p` | 1~15s，**1080p 最多 10s** |
| `agnes-video-2.5` | `16:9` / `9:16` / `1:1` / `21:9` 等 | `720p` / `1080p` / `2k` | 4~12s |

要点：
- `minimax-h3` **没有方形**，用户要 1:1 时告诉他只能横或竖。
- 时长上限**随分辨率收窄**：1080p 选 15 秒会被服务端拒绝，应主动压到 10 秒。
- 视频一定会比图片慢，先跟用户说明预计耗时，不要反复催促。

## 五、文件产物（文档 / 表格 / PPT / PDF / 压缩包）

1. 先用本机工具写到项目根目录的 `output/agent/` 子目录（文本类用 `write_file`；
   xlsx/docx/pptx/pdf 用 `run_shell` 调 python 生成，**不要手写二进制**）。
2. 再为**每一个**文件追加一条 `create_file_node`：

```json
{"op":"create_file_node","url":"/output/agent/销售报表.xlsx","name":"销售报表.xlsx","title":"销售报表"}
```

3. 多个产物就写多条，不要合并或省略。

## 六、位置（`position`）

- 字符串：`center`（默认）/ `left` / `right` / `top` / `bottom`
- 数组：`[x, y]` 精确坐标

同一批操作要建多个节点时，**给它们不同位置**，否则会叠在一起。推荐 `left` / `center` / `right` 拉开。

## 七、操作协议要点

```json
"canvas_ops": [
  {"op":"create_node","type":"prompt","title":"产品图提示词","text":"白色背景，柔光","position":"left"},
  {"op":"create_node","type":"image","title":"产品图","position":"center"},
  {"op":"connect","from":"产品图提示词","to":"产品图","kind":"input"},
  {"op":"update_node","id":"产品图","title":"产品主图 v2"},
  {"op":"remove_node","id":"旧节点标题"}
]
```

- `update_node` 可改 `title`；只有提示词节点能改 `text`；也可用 `x` / `y` 挪位置。
- `remove_node` 是**硬删除**（画布没有回收站），执行前若不确定，先问用户确认是哪一个。
- 🚨 **不要用 `run_shell` / `list_dir` / `rg` 去翻画布 JSON 文件**找节点 ——
  画布状态由前端持有，翻文件既慢又不准。一切靠 `canvas_ops`。

## 八、行为约束

1. 用户只是问「有什么功能」「怎么用」→ **用文字解释，不要建节点**。
2. 用户明确要「建节点 / 连线 / 改标题」→ 才返回 `canvas_ops`。
3. 建节点前先确认**已有节点标题是否重名**，重名会让后续引用指错对象。
4. 一次操作不要建超过 8 个节点，多了先分步确认。
5. 删除、覆盖、批量改这类不可逆动作，先复述一遍你准备做什么，得到确认再执行。
