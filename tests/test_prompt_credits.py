"""提示词节点的积分预估只按 LLM 单价算（老板 2026-11-13：一直显示 0.1803）。

从 smart-canvas.js 里把几个纯函数抠出来，用 node 跑一遍真实价格表：
  - 换理解模型，预估要跟着变；
  - 而且不能再把画布记住的生图模型（nano-banana-pro 0.18/张）算进去。
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
const node = {type: 'smart-prompt', llmProvider: 'ep_1792553056895',
  llmSystemPrompt: 'You are a helpful prompt assistant.',
  text: '描述一下这张图的纯光效背景'};
const out = {};
for(const model of ['gpt-6.1-sol', 'gpt-6-astra']){
    const cost = creditsNodeCost(Object.assign({}, node, {llmModel: model}));
    out[model] = cost ? {credits: cost.credits, kind: cost.kind, text: creditsFormat(cost.credits)} : null;
}
const unpriced = creditsNodeCost(Object.assign({}, node, {llmModel: 'no-such-model', llmProvider: 'ep_x'}));
console.log(JSON.stringify({out, unpriced}));
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
    sol = data["out"]["gpt-6.1-sol"]
    astra = data["out"]["gpt-6-astra"]
    assert sol and astra, data
    assert sol["kind"] == "llm" and astra["kind"] == "llm", data
    assert sol["credits"] < 0.001 and astra["credits"] < 0.001, data
    assert astra["credits"] > sol["credits"] * 2, data
    assert sol["text"] != astra["text"], data
    assert data["unpriced"] is None, data
    print("OK", json.dumps(data, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
