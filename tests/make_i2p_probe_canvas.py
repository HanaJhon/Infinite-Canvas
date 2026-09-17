"""为分层编辑器验证准备一张一次性测试画布（用完必须 purge）。

用法：
    python tests/make_i2p_probe_canvas.py create   # 建画布 + 塞一个图片节点，打印 canvas id
    python tests/make_i2p_probe_canvas.py purge <cid>
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:3000"
TITLE = "__i2p_probe__"
IMAGE_URL = "/output/launcher-sidebar-verify.png"


def request(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8")
            return response.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def create():
    status, data = request("POST", "/api/canvases", {"title": TITLE, "kind": "smart", "project": "default"})
    if status not in (200, 201) or not isinstance(data, dict):
        print("创建画布失败", status, data)
        return 1
    canvas_id = data.get("id") or (data.get("canvas") or {}).get("id")
    if not canvas_id:
        print("返回里没有 id：", data)
        return 1
    node = {
        "id": "probe_node_1",
        "type": "smart-image",
        "title": "Probe Image",
        "x": 80, "y": 80, "w": 320, "h": 260, "scale": 1,
        "images": [{"url": IMAGE_URL, "name": "launcher-sidebar-verify.png", "kind": "image",
                    "mime": "image/png"}],
        "connections": [],
        "created_at": int(time.time() * 1000),
    }
    payload = {
        "title": TITLE,
        "nodes": [node],
        "connections": [],
        "logs": [],
        "settings": {},
        "viewport": {"x": 0, "y": 0, "scale": 1},
    }
    status, data = request("PUT", f"/api/canvases/{canvas_id}", payload)
    if status != 200:
        print("写入画布失败", status, data)
        request("DELETE", f"/api/canvases/{canvas_id}/purge")
        return 1
    print(canvas_id)
    return 0


def purge(canvas_id):
    status, data = request("DELETE", f"/api/canvases/{canvas_id}/purge")
    print("purge", status, data)
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    if sys.argv[1] == "create":
        return create()
    if sys.argv[1] == "purge":
        return purge(sys.argv[2])
    if sys.argv[1] == "list":
        files = os.listdir(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "canvases"))
        for name in files:
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "canvases", name)
            try:
                with open(path, encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                continue
            if data.get("title") == TITLE:
                print(name)
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
