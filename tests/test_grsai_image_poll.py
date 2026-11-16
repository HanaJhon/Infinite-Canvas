"""Grsai 出图改成 async 提交 + 秒级轮询。

同参数实测 `replyType:"json"`（同步阻塞）比官方 web 的 async 慢好几倍，
所以 `generate_ai_image()` 必须交任务后自己轮询 `GET /v1/api/result?id=`。
这里用本地假上游钉住三件事：轮询能拿到成功结果、失败的 status 会抛错、间隔是秒级不是 5s。
"""
import asyncio
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import httpx  # noqa: E402

import main  # noqa: E402

# 不碰真密钥：轮询逻辑与鉴权无关，直接给个空 header
main.api_headers = lambda *a, **kw: {"Accept": "application/json"}


def make_upstream(statuses):
    """按顺序回放的假 Grsai；最后一个状态会被一直重复。"""
    calls = {"n": 0, "interval": []}
    last = {"t": 0.0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            now = time.monotonic()
            if last["t"]:
                calls["interval"].append(now - last["t"])
            last["t"] = now
            idx = min(calls["n"], len(statuses) - 1)
            status = statuses[idx]
            calls["n"] += 1
            body = {"id": "grsai_task_1", "status": status}
            if status == "succeeded":
                body["results"] = [{"url": "https://fake.example/a.png"}]
            if status == "failed":
                body["error"] = "excessive system load"
            data = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    return Handler, calls


def serve(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run_poll(statuses):
    handler, calls = make_upstream(statuses)
    server = serve(handler)
    port = server.server_address[1]
    provider = {"id": "grsai-test", "api_key": "k", "base_url": f"http://127.0.0.1:{port}"}
    t0 = time.monotonic()

    async def go():
        async with httpx.AsyncClient(timeout=10) as client:
            return await main.wait_for_grsai_image_task(
                client, provider, f"http://127.0.0.1:{port}/v1/api/generate", "grsai_task_1", "nano-banana-pro")

    try:
        result = asyncio.run(go())
    finally:
        server.shutdown()
    return result, calls, time.monotonic() - t0


def test_polls_until_succeeded():
    result, calls, elapsed = run_poll(["running", "running", "succeeded"])
    assert result.get("status") == "succeeded", result
    assert result["results"][0]["url"] == "https://fake.example/a.png"
    assert calls["n"] == 3, calls
    # 0.8 + 1.5 = 2.3s；留足余量，但必须远小于旧的 5s 档（3 次查询 >= 10s）
    assert elapsed < 6, elapsed
    assert all(gap < 2.5 for gap in calls["interval"]), calls["interval"]


def test_failed_status_raises():
    try:
        run_poll(["running", "failed"])
    except main.HTTPException as exc:
        assert "Grsai 出图失败" in str(exc.detail)
    else:
        raise AssertionError("失败状态必须抛 HTTPException")


if __name__ == '__main__':
    test_polls_until_succeeded()
    test_failed_status_raises()
    print('OK grsai-image-poll')
