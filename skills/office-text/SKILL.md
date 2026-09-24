# Skill: 生成文本类文件（txt / md / csv / json / 代码）

纯文本产物**不需要** run_shell，直接用 `write_file` 写即可（它会自动创建父目录）。只有需要批量计算或格式化时才用 python 脚本。

## 统一约定（所有办公产物共用）

1. 产物一律写入项目根目录的 `output/agent/` 子目录，文件名要带正确扩展名。
2. 写完后在返回 JSON 的 `canvas_ops` 里追加一条 `create_file_node`：
   ```json
   {"op":"create_file_node","url":"/output/agent/说明.md","name":"说明.md","title":"说明文档"}
   ```
3. 用户要多个产物 → 多条 `create_file_node`，不要合并成一个文件糊弄。

## 各格式写法

| 扩展名 | 写法 | 注意 |
| --- | --- | --- |
| `.txt` | `write_file` 直写纯文本 | 不要带 markdown 标记 |
| `.md` | `write_file` 直写 markdown | 标题 `#`、列表 `-`、表格用 `\|` |
| `.csv` | `write_file` 直写 | **UTF-8 且带 BOM**（首行开头写 `\ufeff`），否则 Excel 打开中文乱码 |
| `.json` | `write_file` 直写 | 必须是合法 JSON，缩进 2 空格；不要写注释 |
| `.py` / `.js` / `.sql` 等 | `write_file` 直写 | 内容要能直接运行 |

CSV 中文兼容的推荐写法（用 python 生成，最稳）：

```python
# -*- coding: utf-8 -*-
import csv, os
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent", "数据.csv")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8-sig", newline="") as f:   # utf-8-sig 才会带 BOM
    w = csv.writer(f)
    w.writerow(["名称", "数量"])
    w.writerow(["甲", 1])
print("OK", OUT)
```

## 要点

- 不要用 run_shell 拼 echo/重定向来写文本，`write_file` 更可靠（避免引号与编码问题）。
- 用户要"把结果整理成文件"时，默认给 `.md`（可读性最好）；明确要 Excel/Word/PPT 才用对应库。
- 多个文件时，一次回复里把所有 `create_file_node` 都列出来，不要只做第一个。
