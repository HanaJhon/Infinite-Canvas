"""工作流资源打包自检：本地 /assets 文件 + 远程 CDN 链接都要进 zip，死链跳过。

跑法：./python/python.exe tools/check_workflow_resources.py
"""
import io, os, sys, json, zipfile, threading, functools, socketserver
from http.server import SimpleHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy'):
    os.environ.pop(_p, None)

# 1) 本地静态服务，模拟"上游 CDN"
ROOT = os.path.join(os.getcwd(), "output", "_check_cdn")
os.makedirs(ROOT, exist_ok=True)
probe = os.path.join(ROOT, "probe_remote_only.png")
with open(probe, "wb") as f:
    f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

handler = functools.partial(SimpleHTTPRequestHandler, directory=ROOT)
httpd = socketserver.TCPServer(("127.0.0.1", 3099), handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()

import main

# 2) 本地已有文件 + 远程 CDN 链接 + 一个死链
local_dir = os.path.join(os.getcwd(), "assets", "input")
local_name = sorted(n for n in os.listdir(local_dir) if n.lower().endswith(".png"))[0]
nodes = [{
    "id": "n1",
    "images": [{"url": f"/assets/input/{local_name}"}],
    "remote": [{"url": "http://127.0.0.1:3099/probe_remote_only.png"}],
    "dead": [{"url": "http://127.0.0.1:3099/_nope_missing.png"}],
}]
refs = main.canvas_workflow_collect_resource_refs(nodes)
print("collected:", refs)
assert f"/assets/input/{local_name}" in refs
assert "http://127.0.0.1:3099/probe_remote_only.png" in refs

# 3) 打包：远程那张必须真的被下载进 zip
class P:
    nodes = nodes
    connections = []
    include_resources = True
    filename = "t.zip"

archive, meta = main.build_canvas_workflow_archive(P())
URL = meta_urls = [r["url"] for r in meta["resources"]]
print("resources:", [(r["name"], r["size"]) for r in meta["resources"]])
assert "http://127.0.0.1:3099/probe_remote_only.png" in URL
assert "http://127.0.0.1:3099/_nope_missing.png" not in URL
with zipfile.ZipFile(io.BytesIO(archive)) as zf:
    names = zf.namelist()
    print("zip:", names)
    assert any(s.startswith("resources/") for s in names)
    for r in meta["resources"]:
        assert r["archive"] in names and zf.getinfo(r["archive"]).file_size == r["size"]

# 4) 导入：绝对 url 归一（本地存在才改写）
norm = main.canvas_workflow_normalize_media_urls({
    "a": f"http://127.0.0.1:3000/assets/input/{local_name}",
    "b": "http://127.0.0.1:3000/assets/input/_not_here.png",
    "c": "https://file1.aitohumanize.com/file/x.png",
})
print("normalized:", norm)
assert norm["a"] == f"/assets/input/{local_name}"
assert norm["b"] == "http://127.0.0.1:3000/assets/input/_not_here.png"
assert norm["c"] == "https://file1.aitohumanize.com/file/x.png"

os.remove(probe)
import shutil; shutil.rmtree(ROOT, ignore_errors=True)
httpd.shutdown()
print("SELF-CHECK OK")
