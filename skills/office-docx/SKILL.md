# Skill: 生成 Word 文档（docx）

本机已离线预装 `python-docx`（便携 Python，无需联网安装）。生成文档请用 `run_shell` 调 python 脚本，不要手写二进制。

## 统一约定（所有办公产物共用）

1. 产物一律写入项目根目录的 `output/agent/` 子目录，文件名要带正确扩展名。
2. 写完后在返回 JSON 的 `canvas_ops` 里追加一条 `create_file_node`：
   ```json
   {"op":"create_file_node","url":"/output/agent/文件名.docx","name":"文件名.docx","title":"节点标题"}
   ```
3. 用户要多个产物 → 多条 `create_file_node`，不要合并成一个文件糊弄。

## 生成 docx 的最小可用脚本

用 `write_file` 把下面的脚本写成 `output/agent/_make_docx.py`，再用 `run_shell` 执行 `python\python.exe output\agent\_make_docx.py`：

```python
# -*- coding: utf-8 -*-
import os
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent", "报告.docx")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

doc = Document()
# 中文字体：必须同时设 ascii / eastasia，否则中文会退回默认字体
style = doc.styles["Normal"]
style.font.name = "微软雅黑"
style.font.size = Pt(10.5)
style.element.rPr.rFonts.set(__import__("docx").oxml.ns.qn("w:eastAsia"), "微软雅黑")

h = doc.add_heading("报告标题", level=1)
h.alignment = WD_ALIGN_PARAGRAPH.CENTER

doc.add_paragraph("这是一段正文，支持**加粗**这类结构请用 run 分别设置。")
p = doc.add_paragraph()
p.add_run("加粗片段").bold = True
p.add_run(" 与普通片段。")

doc.add_paragraph("要点一", style="List Bullet")
doc.add_paragraph("要点二", style="List Bullet")

table = doc.add_table(rows=1, cols=3)
table.style = "Table Grid"
for i, name in enumerate(["列1", "列2", "列3"]):
    table.rows[0].cells[i].text = name
for row in [("a", "b", "c"), ("d", "e", "f")]:
    cells = table.add_row().cells
    for i, v in enumerate(row):
        cells[i].text = v

doc.save(OUT)
print("OK", OUT, os.path.getsize(OUT))
```

## 要点

- **中文必须显式设 eastAsia 字体**，否则 Word 打开会显示成宋体/乱码观感。上面的写法是已验证可用的最小形式。
- 标题层级用 `add_heading(text, level=1..4)`，不要用加大字号的普通段落冒充标题。
- 表格必须设 `table.style = "Table Grid"`，否则 Word 里没有边框。
- 不要生成 `.doc`（旧格式），统一用 `.docx`。
