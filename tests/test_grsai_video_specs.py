"""Grsai 视频参数域端到端验证（2026-10-19，Apifox 文档核对后）。

核对来源：
  · https://qmy27nhsd9.apifox.cn/514679297e0  minimax-h3
  · https://qmy27nhsd9.apifox.cn/523334530e0  agnes-video

断言要点：
  · minimax-h3  aspectRatio 只认 portrait/landscape；resolution 480p/768p/1080p
                duration 1~15，**1080p 最多 10 秒**
  · agnes-video aspectRatio 16:9/9:16/21:9/4:3/1:1/3:4；resolution 720p/1080p/2k；duration 4~12
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.argv = ["x"]

import main as app  # noqa: E402


class Payload:
    def __init__(self):
        self.duration = None
        self.prompt = "p"
        self.aspect_ratio = "16:9"
        self.size = ""
        self.images = []
        self.audios = []
        self.seed = None


class FakeResp:
    status_code = 200
    text = ""

    def json(self):
        return {"id": "t1", "status": "succeeded", "results": [{"url": "https://x/y.mp4"}]}

    def raise_for_status(self):
        pass


class FakeClient:
    def __init__(self):
        self.sent = None

    async def post(self, url, headers=None, json=None):
        self.sent = json
        return FakeResp()

    async def get(self, *a, **k):
        return FakeResp()


async def _save(url):
    return url


app.save_remote_video_to_output = _save
app.api_headers = lambda **k: {}


async def run():
    cases = [
        # model, res_in, dur_in, 期望 res, 期望 dur
        ("minimax-h3", "1080p", 15, "1080p", 10),   # 1080p 收窄到 10
        ("minimax-h3", "1080p", 8, "1080p", 8),     # 未超限不动
        ("minimax-h3", "480p", 15, "480p", 15),     # 非 1080p 可到 15
        ("minimax-h3", "", 5, "480p", 5),           # 空分辨率回退首档
        ("agnes-video-2.5", "2k", 20, "2k", 12),    # 上限 12
        ("agnes-video-2.5", "720p", 2, "720p", 4),  # 下限 4
    ]
    ok = True
    for model, res, dur, want_res, want_dur in cases:
        client = FakeClient()
        payload = Payload()
        payload.duration = dur
        payload.resolution = res
        await app.generate_grsai_video(client, payload, {"name": "Grsai"}, "https://grsaiapi.com", model)
        body = client.sent
        got_res, got_dur = body["resolution"], body["duration"]
        flag = "OK " if (got_res, got_dur) == (want_res, want_dur) else "FAIL"
        if flag == "FAIL":
            ok = False
        print(f"{flag} {model:16s} in(res={res or '-':6s} dur={dur:2d}) -> "
              f"aspect={body['aspectRatio']:10s} res={got_res:6s} dur={got_dur:2d} "
              f"expect(res={want_res:6s} dur={want_dur:2d})")

    # 比例映射
    for model, aspect, want in [
        ("minimax-h3", "16:9", "landscape"),
        ("minimax-h3", "9:16", "portrait"),
        ("minimax-h3", "portrait", "portrait"),
        ("agnes-video-2.5", "21:9", "21:9"),
        ("agnes-video-2.5", "9:21", "9:16"),
        ("agnes-video-2.5", "16:9", "16:9"),
    ]:
        spec = app.GRSAI_VIDEO_SPECS[model]
        got = app.grsai_video_aspect(spec, aspect, "")
        flag = "OK " if got == want else "FAIL"
        if flag == "FAIL":
            ok = False
        print(f"{flag} aspect {model:16s} {aspect:10s} -> {got:10s} expect {want}")

    print("\nRESULT:", "ALL PASS" if ok else "HAS FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
