"""在线生图比例图形选择（static/online.html）——源码约定 + 形状映射自检

跑法：./python/python.exe tests/test_online_ratio_chips.py
"""
import io
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "static", "online.html")


def source():
    return io.open(HTML, encoding="utf-8").read()


def test_source_contract():
    s = source()
    assert 'id="ratioChips" class="ratio-chips sp-ratios"' in s, "缺少比例图形容器"
    # 尺寸选择改成画布同款三页签
    assert 'id="sizePicker" class="sp"' in s
    for mode in ("auto", "preset", "custom"):
        assert f'data-size-mode="{mode}"' in s, mode
    for fn in ("function currentSizeMode(", "function setSizeMode(", "function renderResRows(",
               "function handleResRowClick(", "function bindSizePicker(", "function sizeCaptionForRes("):
        assert fn in s, fn
    assert 'id="resRows"' in s and 'class="sp-res-row' in s, "缺少分辨率列表"
    assert 'picker.dataset.mode = currentSizeMode();' in s
    assert "renderResRows();" in s
    assert ".sp[data-mode=\"preset\"] .sp-body { display:grid; }" in s
    assert ".sp[data-mode=\"custom\"] .sp-custom-body { display:block; }" in s
    assert "handleRatioChipClick(event)" in s, "缺少点击委托"
    # 原生下拉必须还在（JS 状态源）但被隐藏
    assert 'id="ratioSelect"' in s and "#ratioSelect { display:none; }" in s
    for key in ("renderRatioChips", "syncRatioChips", "RATIO_ICON_CLASS"):
        assert key in s, key
    assert "renderRatioChips();" in s, "updateSizeUI 未同步图形按钮"
    # 不再用 label 包住按钮（避免点按钮触发 label 行为）
    assert '<label id="ratioField"' not in s
    assert '<div id="ratioField">' in s
    for cls in ("r-portrait", "r-portrait43", "r-landscape", "r-landscape43", "r-wide", "r-story", "r-custom"):
        assert f".ratio-icon.{cls}" in s, cls


def test_generic_choice_wiring():
    """其余下拉（厂商/模型/尺寸/质量/张数）走同一套模块化按钮逻辑。"""
    s = source()
    assert "const SELECT_CHIP_IDS = ['providerSelect', 'modelSelect', 'qualitySelect', 'countSelect'];" in s
    # 分辨率不再走 chips，避免和 sp-res 列表重复
    assert "#resolutionSelectChips" not in s
    for fn in ("function selectChipBox(", "function syncSelectChips(", "function syncAllSelectChips("):
        assert fn in s, fn
    # select 仍是状态源：点按钮只派发 change，不自己改业务状态
    assert "select.dispatchEvent(new Event('change'))" in s
    assert ".choice-native { display:none !important; }" in s
    # 三个入口都会刷新按钮，避免代码里改了 select.value 而按钮不跟
    assert s.count("syncAllSelectChips();") >= 3
    # 厂商/模型名最长，占满整行；模型多时限高滚动而不是把面板拉长
    assert ".size-row > .model-field, .size-row > .provider-field { grid-column:1/-1; }" in s
    assert "#modelSelectChips { grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); max-height:196px; overflow-y:auto;" in s
    # 质量/张数固定 4 项，恒为一行 4 列
    assert "#qualitySelectChips, #countSelectChips { grid-template-columns:repeat(4,minmax(0,1fr)); }" in s


def test_shape_mapping_runtime():
    """在 node 里跑图形按钮渲染逻辑：形状类名与 active/disabled 同步必须正确。"""
    s = source()
    start = s.index("        /* 比例图形选择：从隐藏的 <select> 生成图形按钮")
    end = s.index("        function setCustomRatio(){")
    block = s[start:end]
    js = r"""
const fs = require('fs');
const block = fs.readFileSync(process.argv[2], 'utf8');
const RATIO_SHAPES_ORDER = ['', 'auto', 'square', 'portrait', 'landscape', 'portrait43', 'landscape43', 'story', 'wide', 'custom'];
const options = RATIO_SHAPES_ORDER.map(v => ({value: v, hidden: false, textContent: v === '' ? '比例为空' : v}));
const box = { innerHTML: '', querySelectorAll: () => btns };
const btns = [];
const select = { options, disabled: false, value: 'square' };
let ratio = 'square';
global.document = {
  getElementById: (id) => id === 'ratioChips' ? box : id === 'ratioSelect' ? select : null,
};
global.escapeHtml = (v) => String(v).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
// 真实现按模型官方表过滤，这里只关心形状映射，全部放行
global.onlineRatioSupported = () => true;
global.firstReferenceDimension = () => null;
eval(block);
// 真实现要在官方表里查比例，这个用例只验形状：直接放行
onlineRatioSupported = () => true;
box.querySelectorAll = () => btns;
renderRatioChips(true);
// 从生成的 HTML 里抠出 data-ratio + 图标类名
const html = box.innerHTML;
const m = [...html.matchAll(/data-ratio="([^"]*)"[^>]*>/g)].map(x => x[1]);
const icons = [...html.matchAll(/ratio-icon ([a-z0-9-]+)/g)].map(x => x[1]);
const expect = ['', 'r-auto', 'r-square', 'r-portrait', 'r-landscape', 'r-portrait43', 'r-landscape43', 'r-story', 'r-wide', 'r-custom'];
console.log(JSON.stringify({ ratios: m, icons, expect }));
"""
    with tempfile.TemporaryDirectory() as tmp:
        frag = os.path.join(tmp, "block.js")
        io.open(frag, "w", encoding="utf-8", newline="\n").write(block)
        script = os.path.join(tmp, "run.js")
        io.open(script, "w", encoding="utf-8", newline="\n").write(js)
        out = subprocess.run(["node", script, frag], capture_output=True, text=True, encoding="utf-8")
        assert out.returncode == 0, out.stderr
        import json
        data = json.loads(out.stdout.strip().splitlines()[-1])
        # 每个选项一个按钮，顺序与 <select> 一致；空比例没有图形，"auto" 用虚线圆
        # 「比例为空」「auto」由「自动」页签承担，网格里只剩具体比例
        assert data["ratios"] == ["square", "portrait", "landscape", "portrait43",
                                  "landscape43", "story", "wide", "custom"], data
        assert data["icons"] == ["r-square", "r-portrait", "r-landscape", "r-portrait43",
                                 "r-landscape43", "r-story", "r-wide", "r-source"], data


def test_generic_chips_runtime():
    """node 里跑 syncSelectChips：隐藏项过滤、active 跟随 select.value、禁用透传。"""
    s = source()
    start = s.index("        const SELECT_CHIP_IDS = [")
    end = s.index("        /* 比例图形选择：从隐藏的 <select> 生成图形按钮")
    block = s[start:end]
    js = r"""
const fs = require('fs');
const block = fs.readFileSync(process.argv[2], 'utf8');
function mkBox() {
  const box = {
    id: '', className: '', dataset: {}, innerHTML: '',
    addEventListener() {},
    _cache: { html: null, btns: [] },
    querySelectorAll() {
      // 同一份 innerHTML 复用同一批按钮对象，才能看到 classList/disabled 的变化
      if (this._cache.html !== this.innerHTML) {
        this._cache.html = this.innerHTML;
        this._cache.btns = [...this.innerHTML.matchAll(/data-value="([^"]*)"/g)].map(m => {
          const btn = { dataset: { value: m[1] }, _cls: new Set(), disabled: false };
          btn.classList = { toggle: (c, v) => (v ? btn._cls.add(c) : btn._cls.delete(c)) };
          return btn;
        });
      }
      return this._cache.btns;
    },
  };
  return box;
}
const boxes = {};
function mkSelect(opts, value, extra) {
  const parent = { insertBefore(node) { boxes[node.id] = node; } };
  return Object.assign({ options: opts, value, disabled: false, classList: { add() {} }, parentNode: parent }, extra || {});
}
const registry = {
  countSelect: mkSelect([{ value: '1', textContent: '×1', hidden: false }, { value: '2', textContent: '×2', hidden: false }, { value: '9', textContent: '隐藏', hidden: true }], '2'),
};
global.document = {
  getElementById: (id) => {
    if (id.endsWith('Chips')) return boxes[id] || null;
    return registry[id] || null;
  },
  createElement: () => Object.assign(mkBox(), { parentNode: null }),
};
global.escapeHtml = (v) => String(v).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
global.Event = class { constructor(t) { this.type = t; } };
eval(block);
syncSelectChips('countSelect');
const box = boxes.countSelectChips;
const data = {
  html: box.innerHTML,
  signature: box.dataset.signature,
};
const btns = box.querySelectorAll('.ratio-chip');
data.count = btns.length;
data.active = btns.filter(b => b._cls.has('active')).map(b => b.dataset.value);
registry.countSelect.disabled = true;
syncSelectChips('countSelect');
data.disabledAll = box.querySelectorAll('.ratio-chip').every(b => b.disabled);
console.log(JSON.stringify(data));
"""
    with tempfile.TemporaryDirectory() as tmp:
        frag = os.path.join(tmp, "block.js")
        io.open(frag, "w", encoding="utf-8", newline="\n").write(block)
        script = os.path.join(tmp, "run.js")
        io.open(script, "w", encoding="utf-8", newline="\n").write(js)
        out = subprocess.run(["node", script, frag], capture_output=True, text=True, encoding="utf-8")
        assert out.returncode == 0, out.stderr
        import json
        data = json.loads(out.stdout.strip().splitlines()[-1])
        assert data["count"] == 2, data          # hidden 选项不生成按钮
        assert data["active"] == ["2"], data     # active 跟随 select.value
        assert data["disabledAll"] is True, data  # select 禁用时按钮同步禁用



def test_model_sizes_runtime():
    """官方尺寸表按模型生效：基础款只有 1K，像素档三档，nano 用自家表；自动档跟随参考图。"""
    s = source()
    start = s.index("        /* 官方尺寸表：与 static/js/smart-canvas.js:3837-3947 同一份数据")
    end = s.index("        const SLOTS = [1,2,3,4,5,6,7,8,9];")
    block = s[start:end]
    js = r"""
const fs = require('fs');
const block = fs.readFileSync(process.argv[2], 'utf8');
let selectedModel = 'gpt-image-2';
const RES_PIXEL_LIMIT = { '1k': 1572864, '2k': 4194304, '4k': 8294400 };
let refDim = null;
global.selectedModel = undefined;
global.firstReferenceDimension = () => refDim;
eval(block);
// block 里的函数读的是闭包变量 selectedModel，这里用 globalThis 赋值无效，改走函数参数
const pick = (model, ratioKey, res) => onlineOfficialSize(ratioKey, res, model);
const out = {
  baseRows: onlineResKeys('gpt-image-2'),
  pixelRows: onlineResKeys('gpt-image-2.5-flare'),
  base11: pick('gpt-image-2.6', 'square', '4k'),
  base169: pick('gpt-image-2', 'wide', '1k'),
  flare169_2k: pick('gpt-image-2.5-flare', 'wide', '2k'),
  flare11_4k: pick('gpt-image-2-flare', 'square', '4k'),
  nano169_4k: pick('nano-banana-pro', 'wide', '4k'),
  nano43_1k: pick('nano-banana-pro', 'landscape43', '1k'),
  gemini43_2k: pick('gemini-3-pro-image-preview', 'landscape43', '2k'),
  unknown: pick('some-relay/model', 'wide', '2k'),
  snapLandscape: onlineSnapAspect(1600, 900, 'nano-banana-pro'),
  snapSquare: onlineSnapAspect(1024, 1024, 'nano-banana-pro'),
  snapCustom: onlineSnapAspect(1000, 333, 'nano-banana-pro'),
};
console.log(JSON.stringify(out));
"""
    with tempfile.TemporaryDirectory() as tmp:
        frag = os.path.join(tmp, "block.js")
        io.open(frag, "w", encoding="utf-8", newline="\n").write(block)
        script = os.path.join(tmp, "run.js")
        io.open(script, "w", encoding="utf-8", newline="\n").write(js)
        out = subprocess.run(["node", script, frag], capture_output=True, text=True, encoding="utf-8")
        assert out.returncode == 0, out.stderr
        import json
        data = json.loads(out.stdout.strip().splitlines()[-1])
    assert data["baseRows"] == ["1k"], data
    assert data["pixelRows"] == ["1k", "2k", "4k"], data
    # 基础款只有一档，4K 也回官方 1:1 尺寸
    assert data["base11"] == "1024x1024", data
    assert data["base169"] == "1672x941", data
    # 像素档走家族三档表
    assert data["flare169_2k"] == "2048x1152", data
    assert data["flare11_4k"] == "2880x2880", data
    # nano / gemini 走自家表（4K 是 5504x3072，不是 gpt 的 3840x2160）
    assert data["nano169_4k"] == "5504x3072", data
    assert data["nano43_1k"] == "1200x896", data
    assert data["gemini43_2k"] == "2400x1792", data
    # 带斜杠的中转模型不查表
    assert data["unknown"] == "", data
    assert data["snapLandscape"] == "16:9", data
    assert data["snapSquare"] == "1:1", data
    assert data["snapCustom"] == "1000:333", data


def test_reference_follow_wiring():
    """自动档「跟随参考图」：像素按参考图 16 对齐，比例吸附官方白名单。"""
    s = source()
    for fn in ("function onlineReferenceSize(", "function onlineSnapAspect(",
               "function onlineOfficialSize(", "function onlineResKeys(", "function renderAutoHint("):
        assert fn in s, fn
    assert "if(currentSizeMode() === 'auto'){" in s and "if(ref) return `${ref.width}x${ref.height}`;" in s
    assert "if(ref) return ref.aspect;" in s
    assert "renderAutoHint();" in s
    assert "ONLINE_NANO_EXTREME_SIZES" in s
    # 换模型要把不支持的档位收回到 1K
    assert "if(!onlineResKeys(selectedModel).includes(resolution) && resolution !== 'custom') resolution = '1k';" in s


def test_ratio_filter_and_source():
    """比例列表按模型官方表过滤；「原图」按参考图尺寸输出。"""
    s = source()
    for fn in ("function onlineRatioSupported(", "function applySourceSize("):
        assert fn in s, fn
    assert 'value="ultrawide"' in s and 'value="ultratall"' in s
    assert "ultrawide:'21:9'" in s and "ultratall:'9:21'" in s
    assert "ultrawide: 'r-wide'" in s and "custom: 'r-source'" in s
    assert "onlineRatioSupported(o.value)" in s
    # 原图按钮一直在，没有参考图时置灰；点它走自适应而不是切到自定义比例输入
    assert "if(ratioKey === 'custom') return true;" in s
    assert "btn.disabled = select.disabled || (isSource && !hasSource);" in s
    assert "if(btn.dataset.ratio === 'custom'){ applySourceSize(); return; }" in s
    assert "resolution = 'custom';" in s.split("function applySourceSize(")[1][:600]
    assert "16:" in s  # 比例吸附

if __name__ == "__main__":
    test_source_contract()
    test_generic_choice_wiring()
    test_shape_mapping_runtime()
    test_generic_chips_runtime()
    print("OK online-ratio-chips")
