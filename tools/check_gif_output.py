"""GIF 输出链路自检（stdlib + 已装 Pillow，无网络）。

覆盖：
1. save_ai_image_to_output 对 image/gif 的 b64 与 URL 两种来源都保留 .gif 后缀；
2. /api/media-preview 对 .gif 直接回原文件（否则 PIL 会把动画压成单帧静态图）。

用法：./python/python.exe tools/check_gif_output.py  → 打印 GIF_CHECK=OK
"""
import asyncio
import base64
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import main  # noqa: E402

from PIL import Image  # noqa: E402


def make_gif(path, frames=3):
    imgs = []
    for i in range(frames):
        img = Image.new("RGB", (16, 16), (255, i * 60 % 255, 0))
        imgs.append(img)
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=80, loop=0)
    with Image.open(path) as f:
        return getattr(f, "n_frames", 1)


async def run():
    out_dir = os.path.join(ROOT, "output")
    os.makedirs(out_dir, exist_ok=True)
    fd, gif_path = tempfile.mkstemp(prefix="__gif_check_", suffix=".gif", dir=out_dir)
    os.close(fd)
    try:
        frames = make_gif(gif_path)
        assert frames == 3, f"造出来的 GIF 不是 3 帧：{frames}"

        # 1) b64 来源保留 .gif
        with open(gif_path, "rb") as f:
            raw = f.read()
        url = await main.save_ai_image_to_output(
            {"type": "b64", "mime_type": "image/gif", "value": base64.b64encode(raw).decode()},
            prefix="__gifcheck_",
        )
        assert url.lower().endswith(".gif"), f"b64 GIF 存成了 {url}"
        saved = main.output_file_from_url(url)
        assert saved and os.path.isfile(saved), f"落盘文件不存在：{url}"
        with Image.open(saved) as img:
            assert getattr(img, "n_frames", 1) == 3, "落盘的 GIF 帧数被改"
        os.remove(saved)

        # 1b) 后缀撒谎：GIF 内容挂在 .png 链接 + octet-stream 上（Aizzz 真实行为）
        assert main.image_extension_from_bytes(raw) == ".gif", "GIF 文件头没被认出来"
        assert main.image_extension_from_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 8) == ".png"
        assert main.image_extension_from_bytes(b"\xff\xd8\xff\xe0" + b"0" * 8) == ".jpg"
        assert main.image_extension_from_hint("application/octet-stream https://x/a.PNG") == ".png"
        import http.server, threading

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            lying = await main.save_ai_image_to_output(
                {"type": "url", "value": f"http://127.0.0.1:{srv.server_port}/preview.png"},
                prefix="__gifcheck_",
            )
        finally:
            srv.shutdown()
        assert lying.lower().endswith(".gif"), f"撒谎后缀的 GIF 被存成了 {lying}"
        os.remove(main.output_file_from_url(lying))

        # 2) media_preview 对 .gif 回原文件（不压成静态图）
        rel = "/output/" + os.path.basename(gif_path)
        resp = await main.media_preview(rel, 512)
        assert resp.media_type == "image/gif", f"media_preview 返回 {resp.media_type}"
        assert os.path.abspath(resp.path) == os.path.abspath(gif_path), "media_preview 回了别的文件"
        print("frames=%d b64_url=%s preview=image/gif" % (frames, url))
        print("GIF_CHECK=OK")
    finally:
        try:
            os.remove(gif_path)
        except OSError:
            pass


asyncio.run(run())
