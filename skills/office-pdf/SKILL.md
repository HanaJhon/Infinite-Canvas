# Skill: 生成 PDF 文件

本机已离线预装 `fpdf2` / `pypdf`（便携 Python，无需联网安装）。生成 PDF 请用 `run_shell` 调 python 脚本，不要手写二进制。

## 统一约定（所有办公产物共用）

1. 产物一律写入项目根目录的 `output/agent/` 子目录，文件名要带正确扩展名。
2. 写完后在返回 JSON 的 `canvas_ops` 里追加一条 `create_file_node`：
   ```json
   {"op":"create_file_node","url":"/output/agent/文件名.pdf","name":"文件名.pdf","title":"节点标题"}
   ```
3. 用户要多个产物 → 多条 `create_file_node`，不要合并成一个文件糊弄。

## 生成 PDF 的最小可用脚本

用 `write_file` 把下面的脚本写成 `output/agent/_make_pdf.py`，再用 `run_shell` 执行 `python\python.exe output\agent\_make_pdf.py`：

```python
# -*- coding: utf-8 -*-
import os
from fpdf import FPDF

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent", "文档.pdf")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

pdf = FPDF()
pdf.add_page()

# 中文必须挂一个本机字体，否则所有中文都会变成方块/报错
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]
font_path = next((p for p in FONT_CANDIDATES if os.path.isfile(p)), "")
if font_path:
    pdf.add_font("cjk", "", font_path)
    pdf.set_font("cjk", size=12)
else:
    pdf.set_font("helvetica", size=12)   # 无中文字体时只能输出英文

pdf.set_font_size(20)
pdf.multi_cell(0, 12, "文档标题", new_x="LMARGIN", new_y="NEXT")
pdf.set_font_size(12)
pdf.ln(4)
pdf.multi_cell(0, 8, "这是正文段落。multi_cell 会自动换行，cell 不会。", new_x="LMARGIN", new_y="NEXT")

pdf.output(OUT)
print("OK", OUT, os.path.getsize(OUT))
```

## 要点

- **中文必须 `add_font` 挂 `C:\Windows\Fonts` 下的字体**（优先 `msyh.ttc`）。不挂字体时 fpdf2 会直接抛异常或输出方块。
- ⚠️ `multi_cell` 默认把光标停在**右边距**，连续调用第二个 `multi_cell` 会报
  `Not enough horizontal space to render a single character`。
  必须加 `new_x="LMARGIN", new_y="NEXT"`（或用 `pdf.set_x(pdf.l_margin)` 复位）。
- 长文本一律用 `multi_cell`，`cell` 不会自动换行、会溢出页面。
- 需要读 PDF 内容时用 `pypdf`：
  ```python
  from pypdf import PdfReader
  text = "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
  ```
- 不要为了出 PDF 去调用外部在线服务或打印驱动，fpdf2 就够。
