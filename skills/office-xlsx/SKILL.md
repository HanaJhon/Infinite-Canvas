# Skill: Excel 表格（xlsx）—— 读取与生成

本机已离线预装 `openpyxl` / `XlsxWriter`（便携 Python，无需联网安装）。
生成表格请用 `run_shell` 调 python 脚本，不要手写二进制。

## 读取现有 Excel（第一步永远是这个）

🚨 **用 `read_file` 直接读，不要自己解二进制、也不要先拼 python。**

```
read_file {"path": "/assets/input/ai_ref_xxx.xlsx"}     ← 传附件 url 也行
read_file {"path": "D:\\...\\图需-后排.xlsx"}            ← 传本机绝对路径也行
```

- `read_file` 对 `.xlsx/.xlsm/.docx/.pptx/.pdf` 会自动解析成文本，返回形如：
  ```
  [工作表] 视觉需求Brief
  模块 | 参考图 | 页面目标 | 核心卖点 | 文案 | 画面建议表达方式 | 不建议出现
  主图 | [参考图] | 提升点击率… | 漏出红色的安全带扣 / 侧面角度拍摄… | …
  副图1｜尺寸选择 | [参考图] | … | 主标题：Choose the right size / 副标题…
  ```
  表格按「工作表 → 行」展开，单元格内的换行已压成 ` / `，空列已剔除。
- **找不到文件时先 `list_dir`**：用户拖进来的附件落在 `assets/input/`，
  ⚠️ 上传时会被重命名成 `ai_ref_<随机hex>.xlsx`，**跟原文件名对不上**。
  历史消息里会给 `[附件:原名 → /assets/input/ai_ref_xxx.xlsx]`，照着那个 url 读最省事。
- **`.xls` / `.doc` / `.ppt`（Office 97-2003）解析不了** → 直接告诉用户「请另存为 .xlsx/.docx/.pptx」，
  不要反复试、也不要假装读到了。

### 表格内容怎么用

- 读到的是**逐行数据**，不是一段散文。要按「列名 → 值」对齐理解，别把相邻列串味。
- 表里常见 `[参考图]` 标记 —— 那是原表里的浮动图片占位，**不是文字需求**。
- 需求类表格（列名像 `模块 | 页面目标 | 文案 | 画面建议表达方式 | 不建议出现`）是**逐条执行清单**：
  一条任务对应一行，行里的「文案」要原样保留，「不建议出现」要当禁止项。
- 大表被截断时（输出里有「已截断」字样），用 `run_shell` 分段读，别硬猜剩下的内容。

### 需要更精细地读（公式 / 合并单元格 / 隐藏行）时才上 python

```bash
python -c "import openpyxl; wb=openpyxl.load_workbook(r'路径.xlsx', data_only=True); \
ws=wb.worksheets[0]; print(ws.title, ws.max_row, ws.max_column)"
```

`run_shell` 里的 `python` 已经指向随包解释器（自带 openpyxl），直接写 `python` 就行。
⚠️ 读值用 `data_only=True`（否则拿到的是 `=SUM(...)` 公式字符串）；要读公式本身才用 `False`。

## 统一约定（所有办公产物共用）

1. 产物一律写入项目根目录的 `output/agent/` 子目录，文件名要带正确扩展名。
2. 写完后在返回 JSON 的 `canvas_ops` 里追加一条 `create_file_node`：
   ```json
   {"op":"create_file_node","url":"/output/agent/文件名.xlsx","name":"文件名.xlsx","title":"节点标题"}
   ```
3. 用户要多个产物 → 多条 `create_file_node`，不要合并成一个文件糊弄。

## 生成 xlsx 的最小可用脚本

用 `write_file` 把下面的脚本写成 `output/agent/_make_xlsx.py`，再用 `run_shell` 执行 `python\python.exe output\agent\_make_xlsx.py`：

```python
# -*- coding: utf-8 -*-
import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent", "报表.xlsx")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

wb = Workbook()
ws = wb.active
ws.title = "数据"
headers = ["项目", "数量", "金额"]
rows = [["A", 10, 1200], ["B", 5, 800]]

ws.append(headers)
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF")
    c.fill = PatternFill("solid", fgColor="4472C4")
    c.alignment = Alignment(horizontal="center")
for r in rows:
    ws.append(r)

for col, width in zip("ABC", (22, 12, 14)):
    ws.column_dimensions[col].width = width
ws.freeze_panes = "A2"

wb.save(OUT)
print("OK", OUT, os.path.getsize(OUT))
```

## 要点

- 中文字符串直接写即可，openpyxl 输出的是 UTF-8 XML，不涉及字体问题。
- 数值务必用 `int` / `float`，不要写成字符串，否则 Excel 里无法求和。
- 需要多个工作表：`wb.create_sheet("第二页")`。
- 需要公式：`ws["D2"] = "=SUM(C2:C10)"`。
- 用户给了 CSV / 表格文本时，先解析成二维列表再写。
- 不要生成 `.xls`（旧格式），统一用 `.xlsx`。
