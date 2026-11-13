"""提示词节点的积分预估只按 LLM 单价算（老板 2026-11-13：一直显示 0.1803）。

从 smart-canvas.js 里把几个纯函数抠出来，用 node 跑一遍真实价格表：
  - 不能再把画布记住的生图模型（nano-banana-pro 0.18/张）算进去；
  - 预估太小就不显示（老板：太低则不显示，费用照样扣除），单价够高时照常显示。
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "static", "js", "smart-canvas.js")
PRICES = os.path.join(ROOT, "data", "credits_settings.json")

FUNCS = ["creditsNumber", "creditsFormat", "creditsLlmCost", "creditsNodeCost"]


def extract_func(source, name):
    start = source.index("function " + name + "(")
    i = source.index("{", start)
    depth, j = 0, i
    quote = None
    while j < len(source):
        c = source[j]
        if quote:
            if c == "\\":
                j += 2
                continue
            if c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
        elif c == "/" and source[j + 1] == "/":
            j = source.index("\n", j)
            continue
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return source[start:j + 1]
        j += 1
    raise ValueError("unbalanced braces in " + name)


def build_script():
    src = io.open(SRC, encoding="utf-8").read()
    prices = json.load(io.open(PRICES, encoding="utf-8"))
    funcs = "\n\n".join(extract_func(src, name) for name in FUNCS)
    min_show = re.search(r"const CREDITS_MIN_SHOW = ([\d.]+);", src)
    assert min_show, "CREDITS_MIN_SHOW not found"
    funcs = "const CREDITS_MIN_SHOW = %s;\n" % min_show.group(1) + funcs
    return """
const PRICES = %s;
function creditsEntryFor(model, provider){
    const table = PRICES.models || {};
    const key = String(provider || '') + '::' + String(model || '');
    if(table[key]) return table[key];
    const suffix = '::' + String(model || '');
    for(const k of Object.keys(table)) if(k.endsWith(suffix)) return table[k];
    return null;
}
function inputPromptTextFor(){ return ''; }
function smartSettingsForNode(){ return {model: 'nano-banana-pro', provider_id: 'ep_1791961101246'}; }
function isApiLikeEngine(){ return false; }
function creditsNodeProviderId(){ return 'ep_1791961101246'; }
function creditsVideoPerSecond(){ return 0; }
%s
PRICES.models['ep_test::llm-big'] = {kind: 'llm', input: 500, output: 1000, cache: 100};
const node = {type: 'smart-prompt', llmProvider: 'ep_1792553056895',
  llmSystemPrompt: 'You are a helpful prompt assistant.',
  text: '描述一下这张图的纯光效背景'};
const out = {};
for(const model of ['gpt-6.1-sol', 'gpt-6-astra']){
    const cost = creditsNodeCost(Object.assign({}, node, {llmModel: model}));
    out[model] = cost ? {credits: cost.credits, kind: cost.kind, text: creditsFormat(cost.credits)} : null;
}
const unpriced = creditsNodeCost(Object.assign({}, node, {llmModel: 'no-such-model', llmProvider: 'ep_x'}));
const big = creditsNodeCost(Object.assign({}, node, {llmModel: 'llm-big', llmProvider: 'ep_test'}));
console.log(JSON.stringify({out, unpriced,
    big: big ? {credits: big.credits, kind: big.kind, text: creditsFormat(big.credits)} : null}));
""" % (json.dumps(prices), funcs)


def main():
    node = shutil.which("node")
    if not node:
        print("SKIP: node not found")
        return 0
    raw = subprocess.run([node, "-e", build_script()], capture_output=True, text=True, encoding="utf-8")
    if raw.returncode != 0:
        print(raw.stderr)
        return 1
    data = json.loads(raw.stdout.strip().splitlines()[-1])
    # 便宜模型：预估不到 0.001 积分 ⇒ 不显示（返回 null）
    assert data["out"]["gpt-6.1-sol"] is None, data
    assert data["out"]["gpt-6-astra"] is None, data
    # 没配单价 ⇒ 也不显示
    assert data["unpriced"] is None, data
    # 单价够高 ⇒ 正常显示，且是 llm 而不是一张图的价
    big = data["big"]
    assert big and big["kind"] == "llm", data
    assert 0.001 <= big["credits"] < 0.18, data
    assert big["text"].startswith("0.02"), data
    print("OK", json.dumps(data, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
