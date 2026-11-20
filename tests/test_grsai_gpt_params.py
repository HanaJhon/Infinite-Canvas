"""Grsai GPT Image 系列参数分档（文档 2026-11-20 核对）。

三件事必须钉住：
1. 像素档（-vip / -flare / -sunburst）发像素值，基础款（gpt-image-2 / 2.5 / 2.6）发比例字符串；
2. quality 按模型分档，基础款只有 auto，只有 2.5-sunburst 吃 xhigh/max；
3. outputFormat 只认 png/gif/svg，gif 仅 2.6 系、svg 仅 gpt-image-2.6；
4. 前端尺寸表：基础款一档、像素档 1K/2K/4K，且 4K 是官方值（1:1 = 2880²，21:9 = 3840x1648）。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import main  # noqa: E402


def check(name, got, want):
    assert got == want, "%s: got %r, want %r" % (name, got, want)


def test_quality():
    check("基础款只认 auto", main.grsai_gpt_quality("gpt-image-2", "high"), "")
    check("基础款 auto", main.grsai_gpt_quality("gpt-image-2.6", "auto"), "auto")
    check("vip 四档", main.grsai_gpt_quality("gpt-image-2-vip", "high"), "high")
    check("2.5-sunburst 吃 xhigh", main.grsai_gpt_quality("gpt-image-2.5-sunburst", "xhigh"), "xhigh")
    check("2.6-sunburst 不吃 max", main.grsai_gpt_quality("gpt-image-2.6-sunburst", "max"), "")
    check("非 gpt 模型不传", main.grsai_gpt_quality("nano-banana-pro", "high"), "")


def test_output_format():
    check("png 总是允许", main.grsai_gpt_output_format("gpt-image-2", "png"), "png")
    check("jpg 归一", main.grsai_gpt_output_format("gpt-image-2", "jpg"), "")
    check("gif 仅 2.6 系", main.grsai_gpt_output_format("gpt-image-2.6", "gif"), "gif")
    check("2.5 不给 gif", main.grsai_gpt_output_format("gpt-image-2.5", "gif"), "")
    check("svg 仅 2.6", main.grsai_gpt_output_format("gpt-image-2.6", "svg"), "svg")
    check("2.6-flare 不给 svg", main.grsai_gpt_output_format("gpt-image-2.6-flare", "svg"), "")


def test_aspect_ratio():
    # 像素档：必须发像素值，且过 GPT 尺寸护栏（长边≤3840、≤8.29MP、16 对齐）
    check("像素档原样", main.grsai_gpt_aspect_ratio("21:9", "1456x624", "gpt-image-2.5-flare"), "1456x624")
    clamped = main.grsai_gpt_aspect_ratio("1:1", "4096x4096", "gpt-image-2-vip")
    w, h = [int(v) for v in clamped.split("x")]
    assert max(w, h) <= 3840 and w * h <= main.GPT_IMAGE2_MAX_PIXELS, clamped
    assert w == h and w % 16 == 0, clamped
    # 文档下限 655,360 像素：太小的自定义尺寸等比放大
    tiny = main.grsai_gpt_aspect_ratio("1:1", "256x256", "gpt-image-2-vip")
    tw, th = [int(v) for v in tiny.split("x")]
    assert tw * th >= main.GPT_IMAGE2_MIN_PIXELS, tiny
    # 基础款：仍交给比例白名单
    check("基础款走比例", main.grsai_gpt_aspect_ratio("16:9", "1672x941", "gpt-image-2"), "16:9")
    # 像素档的 auto 不能落成 illegal 像素串
    check("像素档 auto", main.grsai_gpt_aspect_ratio("auto", "auto", "gpt-image-2.6-sunburst"), "auto")


NODE_CASE = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2] || process.argv[1], 'utf8');
const from = src.indexOf('const GPT_IMAGE_FAMILY_SIZES');
const to = src.indexOf('/* 尺寸护栏');
if (from < 0 || to < 0 || to <= from) { console.log('SLICE_FAIL'); process.exit(1); }
const block = src.slice(from, to);
const stub = 'const API_RATIO_VALUES = {square:"1:1",portrait:"2:3",landscape:"3:2",portrait43:"3:4",'
    + 'landscape43:"4:3",story:"9:16",wide:"16:9",ultrawide:"21:9",ultratall:"9:21"};'
    + 'const SIZE_MAP = {square:{"1k":"1024x1024","2k":"2048x2048","4k":"4096x4096"}};'
    + 'function isGptImageAutoSizeModel(model){'
    + 'const n = String(model||"").trim().toLowerCase();'
    + 'return n === "gpt-image-2" || n.startsWith("gpt-image-2-") || n.startsWith("gpt-image-2.");'
    + '}';
const api = new Function(stub + block + ';return {gptImageFamilySize, isGptImageBaseModel};')();
const out = {
    base_1k: api.gptImageFamilySize('square', '1k', 'gpt-image-2'),
    base_4k: api.gptImageFamilySize('square', '4k', 'gpt-image-2.6'),
    base_169: api.gptImageFamilySize('wide', '2k', 'gpt-image-2.5'),
    vip_1k: api.gptImageFamilySize('ultrawide', '1k', 'gpt-image-2-vip'),
    vip_4k: api.gptImageFamilySize('ultrawide', '4k', 'gpt-image-2.5-sunburst'),
    vip_square4k: api.gptImageFamilySize('square', '4k', 'gpt-image-2.6-flare'),
    auto: api.gptImageFamilySize('square', 'auto', 'gpt-image-2'),
    unknown: api.gptImageFamilySize('square', '1k', 'nano-banana-pro'),
    base_flag: api.isGptImageBaseModel('gpt-image-2.5'),
    vip_flag: api.isGptImageBaseModel('gpt-image-2-vip')
};
console.log(JSON.stringify(out));
"""


def test_frontend_size_tables(tmpdir=None):
    js = os.path.join(ROOT, "static", "js", "smart-canvas.js")
    proc = subprocess.run(
        ["node", "-e", NODE_CASE, js],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    import json
    got = json.loads(proc.stdout.strip().splitlines()[-1])
    check("基础款 1K", got["base_1k"], "1024x1024")
    check("基础款没有 4K 档", got["base_4k"], "1024x1024")
    check("基础款 16:9", got["base_169"], "1672x941")
    check("像素档 21:9 1K", got["vip_1k"], "1456x624")
    check("像素档 21:9 4K", got["vip_4k"], "3840x1648")
    check("像素档 1:1 4K 是 2880", got["vip_square4k"], "2880x2880")
    check("auto 透传", got["auto"], "auto")
    check("非 gpt 模型查不到", got["unknown"], "")
    check("基础款识别", got["base_flag"], True)
    check("像素档不是基础款", got["vip_flag"], False)


def main_run():
    test_quality()
    test_output_format()
    test_aspect_ratio()
    test_frontend_size_tables()
    print("OK grsai-gpt-params")


if __name__ == "__main__":
    main_run()
