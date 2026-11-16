"""画布调色（滤镜 / 曝光 / 饱和 / 曲线）的像素数学与接线。

像素数学写在 `static/js/smart-canvas.js` 的 `/* COLOR-GRADE:START */ ... END */`
之间（纯函数、不碰 DOM），所以这里直接把那段抠出来丢给 node 跑断言，
不需要浏览器、也不需要起服务。
"""
import io
import os
import re
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = 'static/js/smart-canvas.js'
HTML = 'static/smart-canvas.html'

NODE_CHECK = r"""
const assert = require('assert');

// 1) 程度 0 = 原图（滤镜再猛也不能漏出来）
let cfg = colorGradeConfig({filter:'nh', strength:0, exposure:80, saturation:100});
assert.deepStrictEqual(colorGradePixel(20, 120, 200, cfg), [20, 120, 200]);

// 2) 曝光 +100（+2EV）变亮，-100 变暗
const base = [60, 90, 120];
assert.ok(colorGradePixel(...base, colorGradeConfig({exposure:100}))[0] > base[0]);
assert.ok(colorGradePixel(...base, colorGradeConfig({exposure:-100}))[0] < base[0]);

// 3) 饱和 -100 = 灰度（三通道相等）；+100 = 更饱和
const gray = colorGradePixel(200, 60, 30, colorGradeConfig({saturation:-100}));
assert.ok(Math.abs(gray[0] - gray[1]) < 1 && Math.abs(gray[1] - gray[2]) < 1, 'sat -100 应为灰');
const vivid = colorGradePixel(200, 60, 30, colorGradeConfig({saturation:100}));
assert.ok(vivid[0] > 200 && vivid[2] < 30, 'sat +100 应更分离');

// 4) 曲线：抬阴影只影响暗部，高光基本不动
const darkBefore = colorGradePixel(20, 20, 20, colorGradeConfig({}))[0];
const darkAfter = colorGradePixel(20, 20, 20, colorGradeConfig({shadow:0.25}))[0];
const lightBefore = colorGradePixel(250, 250, 250, colorGradeConfig({}))[0];
const lightAfter = colorGradePixel(250, 250, 250, colorGradeConfig({shadow:0.25}))[0];
assert.ok(darkAfter - darkBefore > 10, '抬阴影应提亮暗部');
assert.ok(Math.abs(lightAfter - lightBefore) < 12, '抬阴影不该大幅改动高光');

// 5) 滤镜预设各不相同，且 none 保持原样
const px = [140, 110, 90];
const none = colorGradePixel(...px, colorGradeConfig({filter:'none'}));
assert.deepStrictEqual(none.map(v => Math.round(v)), px);
const seen = new Set();
for (const key of ['800t', 'cc', 'nc', 'nh']) {
  const out = colorGradePixel(...px, colorGradeConfig({filter:key})).map(v => Math.round(v));
  assert.notDeepStrictEqual(out, px, key + ' 应有变化');
  seen.add(out.join(','));
}
assert.strictEqual(seen.size, 4, '四种胶片预设效果不能撞车');

// 6) 吸管「仅调该色」：相近色被改，远处颜色不动
const pick = [200, 40, 40];
const near = colorGradePixel(205, 45, 45, colorGradeConfig({saturation:-100, picked:pick, pickedOnly:true}));
const far = colorGradePixel(40, 40, 200, colorGradeConfig({saturation:-100, picked:pick, pickedOnly:true}));
assert.ok(Math.max(...near) - Math.min(...near) < 40, '相近色应被明显去饱和');
assert.deepStrictEqual(far.map(v => Math.round(v)), [40, 40, 200], '远处颜色不该被改');

console.log('OK color-grade-math');
"""


def read(rel):
    with io.open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _pure_block():
    src = read(JS)
    start = src.index('/* COLOR-GRADE:START')
    end = src.index('/* COLOR-GRADE:END */')
    return src[start:end]


def test_pixel_math():
    node = shutil.which('node')
    assert node, '需要 node 才能跑这段纯函数测试'
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'color_grade.js')
        with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(_pure_block() + '\n' + NODE_CHECK)
        proc = subprocess.run([node, path], capture_output=True, text=True, encoding='utf-8')
    assert proc.returncode == 0, proc.stderr
    assert 'OK color-grade-math' in proc.stdout


def test_mode_wired():
    js = read(JS)
    html = read(HTML)
    # 模式按钮、工具条、画布三者都在页面上
    assert 'data-image-edit-mode="color"' in html
    assert 'id="imageColorTools"' in html
    assert 'id="colorCanvas"' in html
    assert 'id="colorCurve"' in html
    # 四个胶片预设与需求名字对应
    for name in ['800T胶片', 'CC胶片', 'NC胶片', 'NH胶片']:
        assert name in html, name
    # 模式被接受、会切画布、会打开预览
    assert "'color'].includes(mode)" in js
    assert "classList.toggle('color-mode'" in js
    assert 'requestAnimationFrame(() => openColorGrade())' in js
    # 应用按钮走本地调色而不是裁剪
    assert "if(imageEditMode === 'color') return applyImageColor();" in js
    body = js[js.index('async function applyImageColor('):]
    assert 'uploadCroppedBlob(' in body and 'replaceEditedImage(' in body


if __name__ == '__main__':
    test_pixel_math()
    test_mode_wired()
    print('OK canvas-color-grade')
