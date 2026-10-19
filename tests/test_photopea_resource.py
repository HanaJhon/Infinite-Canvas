import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, Request
import httpx
from starlette.datastructures import Headers, UploadFile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


def make_request(method="GET", origin=""):
    headers = {"host": "192.168.1.20:3010"}
    if origin:
        headers["origin"] = origin
    raw_headers = [
        (key.encode("latin-1"), value.encode("latin-1"))
        for key, value in headers.items()
    ]
    return Request({
        "type": "http",
        "method": method,
        "path": "/api/photopea/file/test",
        "query_string": b"",
        "headers": raw_headers,
        "client": ("192.168.1.20", 3010),
        "server": ("192.168.1.20", 3010),
        "scheme": "http",
    })


class PhotopeaResourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_route_returns_photopea_capability_with_exact_cors(self):
        with tempfile.TemporaryDirectory() as directory:
            old_root = main.OUTPUT_INPUT_DIR
            main.OUTPUT_INPUT_DIR = directory
            try:
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                    response = await client.post(
                        "/api/ai/upload",
                        files={"files": ("design.psd", b"8BPS synthetic", "application/octet-stream")},
                    )
                    self.assertEqual(response.status_code, 200)
                    url = response.json()["files"][0]["photopea_url"]
                    head = await client.head(url, headers={"Origin": "https://www.photopea.com"})
                    self.assertEqual(head.status_code, 200)
                    self.assertEqual(
                        head.headers.get("access-control-allow-origin"),
                        "https://www.photopea.com",
                    )
                    denied = await client.get(url, headers={"Origin": "https://evil.example"})
                    self.assertEqual(denied.status_code, 403)
            finally:
                main.OUTPUT_INPUT_DIR = old_root

    async def test_psd_upload_returns_capability_url_without_rewriting_asset_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_root = main.OUTPUT_INPUT_DIR
            main.OUTPUT_INPUT_DIR = str(root)
            upload = UploadFile(
                file=BytesIO(b"8BPS synthetic"),
                filename="design.psd",
                headers=Headers({"content-type": "application/octet-stream"}),
            )
            try:
                payload = await main.upload_ai_reference(make_request(), [upload])
                item = payload["files"][0]
                self.assertTrue(item["url"].endswith(".psd"))
                self.assertTrue(item["photopea_url"].startswith(
                    "http://192.168.1.20:3010/api/photopea/file/"
                ))
                self.assertNotIn("design.psd", item["url"])
            finally:
                for path in root.iterdir():
                    path.unlink()
                main.OUTPUT_INPUT_DIR = old_root

    async def test_capability_is_read_only_cors_scoped_and_supports_range(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "ai_ref_test.psd"
            path.write_bytes(b"8BPS" + bytes(range(32)))
            old_root = main.OUTPUT_INPUT_DIR
            main.OUTPUT_INPUT_DIR = str(root)
            token = main.issue_photopea_capability(path)
            try:
                head = await main.get_photopea_file(
                    token, make_request("HEAD", "https://www.photopea.com")
                )
                self.assertEqual(head.status_code, 200)
                self.assertEqual(head.headers["access-control-allow-origin"], "https://www.photopea.com")
                self.assertEqual(head.headers["content-length"], "36")

                ranged = await main.get_photopea_file(
                    token,
                    Request({
                        "type": "http",
                        "method": "GET",
                        "path": "/api/photopea/file/test",
                        "query_string": b"",
                        "headers": [
                            (b"host", b"192.168.1.20:3010"),
                            (b"origin", b"https://www.photopea.com"),
                            (b"range", b"bytes=4-9"),
                        ],
                        "client": ("192.168.1.20", 3010),
                        "server": ("192.168.1.20", 3010),
                        "scheme": "http",
                    }),
                )
                self.assertEqual(ranged.status_code, 206)
                self.assertEqual(ranged.headers["content-range"], "bytes 4-9/36")
                body = b"".join([chunk async for chunk in ranged.body_iterator])
                self.assertEqual(body, bytes(range(6)))

                with self.assertRaises(HTTPException) as denied:
                    await main.get_photopea_file(
                        token, make_request("GET", "https://evil.example")
                    )
                self.assertEqual(denied.exception.status_code, 403)
            finally:
                main.PHOTOPEA_CAPABILITIES.pop(token, None)
                main.OUTPUT_INPUT_DIR = old_root

    async def test_expired_capability_is_not_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "ai_ref_expired.psd"
            path.write_bytes(b"8BPS test")
            old_root = main.OUTPUT_INPUT_DIR
            main.OUTPUT_INPUT_DIR = str(root)
            token = main.issue_photopea_capability(path)
            main.PHOTOPEA_CAPABILITIES[token]["expires_at"] = 0
            try:
                with self.assertRaises(HTTPException) as expired:
                    await main.get_photopea_file(token, make_request("HEAD"))
                self.assertEqual(expired.exception.status_code, 404)
            finally:
                main.PHOTOPEA_CAPABILITIES.pop(token, None)
                main.OUTPUT_INPUT_DIR = old_root


if __name__ == "__main__":
    unittest.main()
