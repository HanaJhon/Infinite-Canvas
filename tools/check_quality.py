"""Fast, dependency-free checks for the Infinite-Canvas source tree."""

from __future__ import annotations

import ast
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIRS = (ROOT / "backend", ROOT / "tests", ROOT / "tools")
SOURCE_FILES = (ROOT / "main.py", ROOT / "hunyuan3d_client.py")


def python_files():
    files = list(SOURCE_FILES)
    for directory in PYTHON_DIRS:
        if directory.exists():
            files.extend(directory.rglob("*.py"))
    return sorted(set(path for path in files if path.is_file()))


def check_python_syntax(errors):
    for path in python_files():
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            errors.append(f"Python syntax: {path}: {exc}")


def check_duplicate_routes(errors):
    routes = {}
    main_path = ROOT / "main.py"
    tree = ast.parse(main_path.read_text(encoding="utf-8"), filename=str(main_path))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "app":
                continue
            if decorator.func.attr == "middleware":
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            route = (decorator.func.attr.upper(), str(decorator.args[0].value))
            previous = routes.get(route)
            if previous:
                errors.append(f"Duplicate route {route[0]} {route[1]}: {previous} and {node.name}")
            routes[route] = node.name


def check_token_response(errors):
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    match = re.search(
        r'@app\.get\("/api/config/token"\).*?(?=\n@app\.|\Z)',
        source,
        flags=re.S,
    )
    if not match:
        errors.append("Token endpoint /api/config/token is missing")
        return
    body = match.group(0)
    if '"token":' in body or "'token':" in body:
        errors.append("Token endpoint must not return a token field")
    if "has_token" not in body:
        errors.append("Token endpoint must expose has_token for compatibility")


def check_security_boundaries(errors):
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    if 'allow_origins=["*"]' in source or "allow_origins = [\"*\"]" in source:
        errors.append("CORS must not allow every origin")
    if "configured_cors_origins" not in source:
        errors.append("CORS must use explicit configured origins")
    if "secret_field = re.compile" not in source or "public_provider" not in source:
        errors.append("Provider responses must redact credential-shaped legacy fields")


def check_split_budget_boundary(errors):
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    call_match = re.search(
        r"async def split_call_image_model\(.*?\n(?=async def |\Z)",
        source,
        flags=re.S,
    )
    if not call_match or "budget.spend(1," not in call_match.group(0):
        errors.append("Image-model calls must atomically spend split-layer budget")
    for name in ("split_extract_element", "split_ai_repair", "split_erase_elements"):
        helper = re.search(rf"async def {name}\(.*?\n(?=async def |\Z)", source, flags=re.S)
        if not helper or "budget=budget" not in helper.group(0):
            errors.append(f"{name} must forward the split-layer budget")


def check_frontend_wiring(errors):
    class Scripts(HTMLParser):
        def __init__(self):
            super().__init__()
            self.sources = []

        def handle_starttag(self, tag, attrs):
            if tag == "script":
                self.sources.append(dict(attrs).get("src", "").split("?", 1)[0])

    parser = Scripts()
    parser.feed((ROOT / "static/smart-canvas.html").read_text(encoding="utf-8"))
    required = ["/static/js/canvas-sync.js", "/static/js/split-layers.js", "/static/js/smart-canvas.js"]
    for src in required:
        if parser.sources.count(src) != 1 or not (ROOT / src.lstrip("/")).is_file():
            errors.append(f"Missing or duplicate canvas script: {src}")
    if all(src in parser.sources for src in required):
        positions = [parser.sources.index(src) for src in required]
        if positions != sorted(positions):
            errors.append("Canvas helpers must load before smart-canvas.js")


def main():
    errors = []
    check_python_syntax(errors)
    check_duplicate_routes(errors)
    check_token_response(errors)
    check_security_boundaries(errors)
    check_split_budget_boundary(errors)
    check_frontend_wiring(errors)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"quality ok: {len(python_files())} Python files checked; routes unique; token response redacted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
