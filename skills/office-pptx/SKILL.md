# Skill: 生成 PPT 演示文稿（pptx）

本机已离线预装 `python-pptx`（便携 Python，无需联网安装）。生成演示文稿请用 `run_shell` 调 python 脚本，不要手写二进制。

## 统一约定（所有办公产物共用）

1. 产物一律写入项目根目录的 `output/agent/` 子目录，文件名要带正确扩展名。
2. 写完后在返回 JSON 的 `canvas_ops` 里追加一条 `create_file_node`：
   ```json
   {"op":"create_file_node","url":"/output/agent/文件名.pptx","name":"文件名.pptx","title":"节点标题"}
   ```
3. 用户要多个产物 → 多条 `create_file_node`，不要合并成一个文件糊弄。

## 生成 pptx 的最小可用脚本

用 `write_file` 把下面的脚本写成 `output/agent/_make_pptx.py`，再用 `run_shell` 执行 `python\python.exe output\agent\_make_pptx.py`：

```python
# -*- coding: utf-8 -*-
import os
from pptx import Presentation
from pptx.util import Inches, Pt

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent", "演示.pptx")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

prs = Presentation()                      # 默认 4:3；16:9 见下
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)

# 封面（版式 0 = 标题幻灯片）
s = prs.slides.add_slide(prs.slide_layouts[0])
s.shapes.title.text = "演示标题"
s.placeholders[1].text = "副标题 / 日期"

# 内容页（版式 1 = 标题和内容）
s = prs.slides.add_slide(prs.slide_layouts[1])
s.shapes.title.text = "第一页要点"
tf = s.placeholders[1].text_frame
tf.text = "第一条要点"
for line in ("第二条要点", "第三条要点"):
    p = tf.add_paragraph()
    p.text = line
    p.font.size = Pt(18)

# 空白页 + 表格（版式 6 = 空白）
s = prs.slides.add_slide(prs.slide_layouts[6])
rows, cols = 3, 3
table = s.shapes.add_table(rows, cols, Inches(1), Inches(1.5), Inches(9), Inches(3)).table
for r in range(rows):
    for c in range(cols):
        table.cell(r, c).text = f"{r + 1}-{c + 1}"

prs.save(OUT)
print("OK", OUT, os.path.getsize(OUT))
```

## 要点

- 版式索引：`0` 标题幻灯片、`1` 标题和内容、`5` 标题和竖排内容、`6` 空白。只用这几种，其它版式在不同模板下占位符数量可能不同，会 IndexError。
- 不要用 `s.shapes.title` 之外的硬编码文本框堆内容；优先用版式占位符。
- 一页只讲一件事，每页 3~6 条要点，每条不超过 20 字。
- 表格必须设列宽或总宽度，否则会挤在一起。
- 不要生成 `.ppt`（旧格式），统一用 `.pptx`。
