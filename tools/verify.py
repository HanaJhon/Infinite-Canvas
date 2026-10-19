"""Run the local regression and source checks without calling paid models."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    node = shutil.which("node")
    if not node:
        print("Node.js is required for frontend checks; add node to PATH.")
        return 1
    commands = [
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        [sys.executable, "-B", "tools/check_quality.py"],
    ]
    commands.extend([node, "--check", str(path.relative_to(ROOT))]
                    for path in sorted((ROOT / "static/js").glob("*.js")))
    commands.extend([
        [node, "tests/test_frontend.js"],
        [node, "static/js/i18n/validate-i18n.js"],
    ])
    for command in commands:
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            print("Failed:", " ".join(command))
            return result.returncode
    print("verify ok: Python regression, quality checks, JavaScript syntax/behaviour, i18n")
    return 0


if __name__ == "__main__":
    sys.exit(main())