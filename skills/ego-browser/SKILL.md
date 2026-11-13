# Skill: 浏览器操作（ego-browser）

> 内置自 ego-browser（ego lite）的 Agent 用法，按画布 / 小抽AI 的职责做了裁剪。
> 需要「真的打开网页、点按钮、填表单、抓页面内容」时用这套，**不要**用纯 HTTP 抓取去冒充浏览器操作。

## 第一步：先验环境，再问用法

```bash
ego-browser --version     # 没这条命令 = 本机没装，直接告诉用户装不了，不要硬编
ego-browser skill         # 打印当前版本的完整用法（很长，按需看，别整份复述给用户）
```

`ego-browser skill` 的输出会随版本变化，**以它为准**；本 Skill 只给这套 API 的骨架和几个必踩的坑。

## 怎么跑一段浏览器脚本

统一入口 `ego-browser nodejs`，按**执行脚本的 shell** 选写法：

- Bash / Git Bash：heredoc 最稳

  ```bash
  ego-browser nodejs <<'EOF'
  const task = await taskSpace("查一下官网价格");
  const page = task.page("p1");
  await page.goto("https://example.com");
  console.log({ spaceId: task.spaceId, snapshot: await page.snapshot() });
  EOF
  ```

- PowerShell：**不支持 heredoc**，且 5.1 会把参数里的双引号拆坏。必须把整段写成 `.mjs` 文件（UTF-8、无 BOM），再
  `ego-browser nodejs -e "await import('file:///C:/Users/<名字>/ego/round-01.mjs')"`。中文只能写在文件里，不要塞进 `-e`。
- cmd：`ego-browser nodejs < C:\Users\<名字>\ego\round-01.mjs`

## 一次任务怎么组织（照做，别自创）

1. **一个目标一个 TaskSpace**：`taskSpace("名字")` 建一次，把 `task.spaceId` 打出来；后续每轮 `taskSpace(<id>)` 续上同一个空间。
2. **每轮是一个新进程**：变量全丢，空间、标签、Page 留着。所以每轮写**新文件**（`round-01.mjs`、`round-02.mjs`…），不要改上一轮的文件——改了会把旧步骤重放一遍。
3. **Page 复用**：默认就有 `p1`，直接 `goto()` 换页；需要并排开才 `await task.newPage()`。
4. **观察要省**：`page.snapshot()` 拿语义结构（带选择器），只有 canvas / 富文本 / 地图这类没语义的界面才 `page.screenshot()`。别两样都抓。
5. **卡住不要换空间**：在原空间里排查；实在不行停下问用户。

## 常用 API（细节跑 `help("page.click")` 之类）

- 导航：`page.goto(url)`、`page.reload()`、`page.waitForURL()`、`page.waitForSelector()`、`page.waitForLoadState()`
- 观察：`page.snapshot()`、`page.screenshot()`、`page.title()`、`page.url()`、`page.info()`
- 元素：`page.click(sel)`、`fill(sel, text)`、`press(sel, key)`、`selectOption()`、`setInputFiles()`、`hover()`、`dblclick()`
- 视觉操作（缺语义时）：`page.mouse.click(x, y)`、`page.mouse.wheel(0, 600)`、`page.keyboard.type()` / `paste()`
- 页内批量：`page.evaluate(fn, arg)`，只接受一个可 JSON 序列化的参数，返回也必须是可序列化的
- 弹窗：`page.acceptDialog(text?)` / `page.dismissDialog()`

## 坑（都踩过）

- **截图路径必须绝对**，Windows 用正斜杠：`C:/Users/x/ego-shots/before.png`（反斜杠在 JS 字符串里是转义）。
- 坐标是 CSS 像素；`mouse.wheel()` 前先把鼠标移到目标滚动区域里。
- 快捷键用 `ControlOrMeta`，不要自己拼平台差异。
- 点了链接后页面导航未完成时再调其它 API 会 `EGO_PAGE_UNRESPONSIVE`，错误信息会告诉你现在显示的是哪份文档、怎么继续。
- 一个任务做完就收：`task.finish({ keep })`；要用户自己登录/验证码/付款时用 `handOff()` 把控制权交给用户，**不要替用户输密码、点付款**。
- 清理 cookie / 缓存 / storage 前先读 Skill 目录的 `references/clearing-state.md`——有些清理动的是整个浏览器配置，会影响用户自己的登录态。

## 什么时候不用它

- 只需要读一个公开网页的正文 → 用内置 `web_read`（快、省 token）。
- 只需要搜关键词 → 用内置 `web_search`。
- 只有「必须点、必须登录态、必须看渲染结果」时才上 ego-browser。
