# 查询模板（Query Templates）

命名好的检索模式：一步展开并执行，可组合、可扩展。日常用 `argo template`
即可，本文件解释机制与扩展方式。

## 快速上手

```bash
argo template --list                          # 列出全部模板（按分组）
argo template ai_model_release                # 用模板搜索
argo template ai_model_release --add "GPT-5"  # 模板 + 追加词（空格即 AND）
argo template ai_zh --sort top -n 20 --json   # 转发参数给底层命令
argo template ai_model_release --dry-run      # 只看展开后的命令与查询串
```

`argo template` 只做三件事：**取模板 → 展开成查询串 → 转发给该模板的 command**。
转发参数（`-n` / `--sort` / `--json` / `--engine` / `--since` …）原样透传，
语义仍由底层命令持有——本机制不复制任何搜索开关定义。

## 随包模板

源自宝玉（[@dotey](https://x.com/dotey)）《X AI 资讯检索》方法论，全部走
`command: x-search`（X 原生搜索），查询统一带 `-is:retweet`（去转发）与
`lang:`（语言）。

| 分组 | id | 说明 |
|------|----|------|
| AI 模型 | `ai_model_release` | 前沿模型发布/正式开放 |
| AI 模型 | `ai_new_model` | 新模型 / 开放权重 / 开源模型 |
| AI 产品 | `ai_agent_product` | AI Agent / MCP / agent skills 发布 |
| AI 产品 | `ai_coding_agent` | 编码 Agent 更新（Cursor / Claude Code / Codex / Devin …） |
| AI 行业 | `ai_industry_funding` | 融资 / 并购 / 破产 |
| AI 行业 | `ai_industry_policy` | 监管 / 诉讼 / 禁令 / 行政令 |
| AI 行业 | `ai_security` | 安全 / 漏洞 / 越狱 / 泄露 |
| AI 爆料 | `ai_leak` | 爆料 / 泄露 / 即将发布 |
| AI 中文 | `ai_zh` | 中文 AI 资讯（发布 / 开源 / 上线） |
| 示例 | `ai_media_tools` | 语音/视频/媒体类 AI 工具发布（自定义方向样例） |

热度筛选：加 `--sort top` 走 X 的 Top 榜（默认 `latest` 最新）；或拿到结果后
按 `social_meta.likes/reposts` 排序。

## 加自己的模板（零代码）

把同名文件放到用户注册表即可，**不改仓库**：

```
$XDG_CONFIG_HOME/argo/query-templates.yaml   # 缺省 ~/.config/argo/query-templates.yaml
```

或用环境变量 `ARGO_TEMPLATES_FILE` 指路径。合并规则：新 id 追加，同名 id 覆盖
随包条目；`disabled: true` 停用随包条目。

```yaml
version: 1
templates:
  quantum_news:
    description: 量子计算进展
    category: 我的方向
    command: x-search
    query: '(quantum computing OR qubit) (breakthrough OR milestone) -is:retweet lang:en'
```

`command` 白名单只有两个：`x-search`（X 原生搜索）与 `search`（通用多源搜索，
走 `argo search`）。模板是数据，**不拥有执行任意命令的能力**。

## X 原生搜索语法速查（`command: x-search` 时）

| 语法 | 含义 |
|------|------|
| `-is:retweet` | 去转发 |
| `lang:en` / `lang:zh` | 语言 |
| `from:OpenAI` | 盯人（可 OR：`from:OpenAI OR from:AnthropicAI`） |
| `min_faves:100` / `min_retweets:50` | 热度门 |
| `since:2026-10-01 until:2026-10-16` | 时间窗 |
| `-filter:replies` | 排除回复 |
| `filter:media` / `filter:images` / `filter:videos` | 只要媒体 |
| 空格=AND、`OR`=或、`-词`=排除、`( )`=分组 | 布尔与分组 |

「盯一批官方号」的典型写法：`from:OpenAI OR from:AnthropicAI OR from:GoogleDeepMind -is:retweet lang:en`，
存成一条模板即可复用。

## 通道说明（为什么是 x-search 而不是 fxtwitter）

X 布尔语法只有 `x.com/search` 本体认，通用网页搜索引擎一律忽略——所以要
「盯人 / 按关键词找发布」只能走 X 原生搜索。`argo x-search` 借 ego-browser
驱动用户已登录的浏览器抓 `x.com/search`（同 `x_trending` 引擎的通道思路）。

> 注：`engines/specs/fxtwitter.yaml` 的 HTTP 免登录搜索通道，上游公开实例的
> `/2/search` 已停用（对任意查询恒返回 404 + 空结果，status/profile 端点仍正常）。
> 关键词搜索请走 `argo x-search`；单条推文按 URL 取正文仍走 `argo tweet`。

## 与其它能力的关系

- **模板 ≠ 深度研究**：模板是「一次结构化检索」，要问题分解 / 多源取证 / 达标检查走 `argo research`。
- **模板 ≠ 事实核验**：社交帖是叙事/舆情，不进事实真值（见 SKILL.md「Agent 执行纪律」）。要核到走 `argo evidence` / `--verify`。
- **交叉核对**：X 上的说法对照 Hacker News / 官方博客 / 主流媒体（宝玉方法论第 4 条）——用 `argo search` 或 `argo research` 完成，模板只负责把 X 侧取全。
