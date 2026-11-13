"""Argo 搜索的入口垫片。

为什么需要它：随包分发的嵌入式 Python 带 `python310._pth`，sys.path 完全由该文件决定，
所以 `PYTHONPATH` 和"脚本所在目录"都不生效 —— 直接 `python tools/argo/scripts/search.py`
会在 `from engine_env import env_flag` 上炸。这里先手动把 scripts/ 塞进 sys.path，
再用 runpy 以 __main__ 身份执行 argo 自己的 CLI，参数原样透传。

用法（main.py 内部调用）：
    python tools/argo_runner.py "<query>" --json --max-results 6 --no-timing --timeout 8
"""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARGO_SCRIPTS = os.path.join(HERE, "argo", "scripts")

sys.path.insert(0, ARGO_SCRIPTS)
sys.argv[0] = os.path.join(ARGO_SCRIPTS, "search.py")
runpy.run_path(sys.argv[0], run_name="__main__")
