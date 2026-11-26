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
    assert 'id="ratioChips" class="ratio-chips"' in s, "缺少比例图形容器"
    assert "handleRatioChipClick(event)" in s, "缺少点击委托"
    # 原生下拉必须还在（JS 状态源）但被隐藏
    assert 'id="ratioSelect"' in s and "#ratioSelect { display:none; }" in s
    for key in ("renderRatioChips", "syncRatioChips", "RATIO_ICON_CLASS"):
        assert key in s, key
    assert "renderRatioChips();" in s, "updateSizeUI 未同步图形按钮"
    # 不再用 label 包住按钮（避免点按钮触发 label 行为）
    assert '<label id="ratioField"' not in s
    assert '<div id="ratioField" class="size-field">' in s
    for cls in ("r-portrait", "r-portrait43", "r-landscape", "r-landscape43", "r-wide", "r-story", "r-custom"):
        assert f".ratio-icon.{cls}" in s, cls


def test_generic_choice_wiring():
    """其余下拉（厂商/模型/尺寸/质量/张数）走同一套模块化按钮逻辑。"""
    s = source()
    assert "const SELECT_CHIP_IDS = ['providerSelect', 'modelSelect', 'resolutionSelect', 'qualitySelect', 'countSelect'];" in s
    for fn in ("function selectChipBox(", "function syncSelectChips(", "function syncAllSelectChips("):
        assert fn in s, fn
    # select 仍是状态源：点按钮只派发 change，不自己改业务状态
    assert "select.dispatchEvent(new Event('change'))" in s
    assert ".choice-native { display:none !important; }" in s
    # 三个入口都会刷新按钮，避免代码里改了 select.value 而按钮不跟
    assert s.count("syncAllSelectChips();") >= 3


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
eval(block);
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
        assert data["ratios"] == ["", "auto", "square", "portrait", "landscape",
                                  "portrait43", "landscape43", "story", "wide", "custom"], data
        assert data["icons"] == data["expect"][1:], data


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


if __name__ == "__main__":
    test_source_contract()
    test_generic_choice_wiring()
    test_shape_mapping_runtime()
    test_generic_chips_runtime()
    print("OK online-ratio-chips")
