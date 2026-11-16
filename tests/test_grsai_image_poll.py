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
        # 失败/超时也要能「查询结果」把图捞回来
        assert getattr(exc, "upstream_task_id", "") == "grsai_task_1", exc.__dict__
    else:
        raise AssertionError("失败状态必须抛 HTTPException")


def test_query_url_for_grsai():
    provider = {"id": "grsai", "name": "Grsai", "base_url": "https://grsai.example.com"}
    url = main.image_task_url_for_provider(provider, "abc123")
    assert url == "https://grsai.example.com/v1/api/result?id=abc123", url


def test_gpt_image_goes_to_generate_api():
    """gpt-image 系（老板的 gpt-image-2.6-sunburst）必须走 /v1/api/generate 异步提交。

    之前它落到 /v1/images/edits 同步 multipart：上游 164s 出图、中途网关掐连接
    ⇒ 前端 RemoteProtocolError，扣了 2400 积分却拿不到图。
    """
    got = {}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass
        def do_POST(self):
            n = int(self.headers.get('content-length') or 0)
            got['path'] = self.path
            got['body'] = json.loads(self.rfile.read(n) or b'{}')
            payload = json.dumps({"id": "gpt_task_1"}).encode()
            self.send_response(200)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def do_GET(self):
            got.setdefault('gets', []).append(self.path)
            payload = json.dumps({
                "status": "succeeded",
                "results": [{"url": "https://fake.example/gpt.png"}],
            }).encode()
            self.send_response(200)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = HTTPServer(('127.0.0.1', 0), H)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    provider = {"id": "grsai", "name": "Grsai",
                "base_url": "http://127.0.0.1:%d" % port,
                "api_key": "k"}
    saved_provider = main.get_api_provider
    saved_headers = main.api_headers
    main.get_api_provider = lambda pid: provider
    main.api_headers = lambda *a, **kw: {"Authorization": "Bearer k"}
    try:
        url, _raw = asyncio.run(main.generate_ai_image(
            "把地板换成木地板", "3504x2352", "high",
            "gpt-image-2.6-sunburst", reference_images=None, provider_id="grsai"))
    finally:
        main.get_api_provider = saved_provider
        main.api_headers = saved_headers
        server.shutdown()

    # extract_image 可能给 url 字符串，也可能给 {"type":"url","value":...}
    got_url = url if isinstance(url, str) else (url.get('value') or url.get('url') or '')
    assert got_url == "https://fake.example/gpt.png", url
    assert got['path'].endswith('/v1/api/generate'), got['path']
    assert got['body'].get('replyType') == 'async', got['body']
    assert 'imageSize' not in got['body'], got['body']
    assert '/' not in got['path'] or 'images/edits' not in got['path'], got['path']


if __name__ == '__main__':
    test_polls_until_succeeded()
    test_failed_status_raises()
    test_query_url_for_grsai()
    test_gpt_image_goes_to_generate_api()
    print('OK grsai-image-poll')
