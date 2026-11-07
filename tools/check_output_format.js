// 自检：提示词要动图 + gpt-image-2.6 系列 + 输出格式「自动」时，必须真的向上游要 gif。
// 从源码里抽出真实函数求值（不复制一份，避免测试自说自话）。
// 用法：node tools/check_output_format.js  →  OUTPUT_FORMAT_CHECK=OK
const fs = require('fs');
const src = fs.readFileSync(require('path').join(__dirname, '..', 'static', 'js', 'smart-canvas.js'), 'utf8');

const start = src.indexOf('const GIF_CAPABLE_MODEL');
const end = src.indexOf('\n}', src.indexOf('function outputFormatPayload')) + 2;
if (start < 0 || end < 2) throw new Error('源码里找不到 outputFormatPayload，检查是否被改名');

const OUTPUT_FORMAT_VALUES = ['auto', 'png', 'jpeg', 'webp', 'gif'];
const normalizeOutputFormat = value => {
  const clean = String(value || '').toLowerCase();
  if (clean === 'jpg') return 'jpeg';
  return OUTPUT_FORMAT_VALUES.includes(clean) ? clean : 'auto';
};
const outputFormatPayload = new Function(
  'normalizeOutputFormat',
  `${src.slice(start, end)}\nreturn outputFormatPayload;`,
)(normalizeOutputFormat);

const cases = [
  ['自动 + 2.6 + 提示词要 gif', { outputFormat: 'auto', model: 'gpt-image-2.6-sunburst' }, '生成gif图美女端起手中茶喝了一口', 'gif'],
  ['自动 + 2.6 + 普通提示词', { outputFormat: 'auto', model: 'gpt-image-2.6-sunburst' }, '一只猫在窗台上', ''],
  ['自动 + 非 2.6 模型 + 要 gif', { outputFormat: 'auto', model: 'nano-banana' }, '生成gif图', ''],
  ['手动选 gif', { outputFormat: 'gif', model: 'gpt-image-2.6-sunburst' }, '随便', 'gif'],
  ['手动选 png 压过提示词', { outputFormat: 'png', model: 'gpt-image-2.6-sunburst' }, '生成gif图', 'png'],
  ['未设置 = 自动', {}, '生成gif图', ''],
];
let failed = 0;
for (const [label, settings, prompt, expect] of cases) {
  const got = outputFormatPayload(settings, prompt);
  const ok = got === expect;
  if (!ok) failed++;
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}: 期望 ${JSON.stringify(expect)} 实得 ${JSON.stringify(got)}`);
}
if (failed) {
  console.log(`OUTPUT_FORMAT_CHECK=FAIL ${failed}/${cases.length}`);
  process.exit(1);
}
console.log(`OUTPUT_FORMAT_CHECK=OK ${cases.length}/${cases.length}`);
