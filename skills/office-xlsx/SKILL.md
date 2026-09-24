# Skill: 生成 Excel 表格（xlsx）

本机已离线预装 `openpyxl` / `XlsxWriter`（便携 Python，无需联网安装）。生成表格请用 `run_shell` 调 python 脚本，不要手写二进制。

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
