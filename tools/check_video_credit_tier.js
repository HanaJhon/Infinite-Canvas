// 视频积分预估的分辨率档位归一化自检（node tools/check_video_credit_tier.js）
// 老板 2026-11-06：minimax-h3 768P + 10 秒被算成 3 积分（= 1080p 单价），实际应为 1.4（720p 档）。
// 直接读 static/js/smart-canvas.js 里的真实实现来跑，避免「测试自说自话」。
const fs = require('fs');
const src = fs.readFileSync(__dirname + '/../static/js/smart-canvas.js', 'utf8');
function grab(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('missing ' + name);
  let depth = 0, i = src.indexOf('{', start);
  for (let j = i; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (!depth) return src.slice(start, j + 1); }
  }
  throw new Error('unbalanced ' + name);
}
const creditsNumber = v => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
const code = grab('creditsVideoTier') + '\n' + grab('creditsVideoPerSecond') + '\nreturn {creditsVideoTier, creditsVideoPerSecond};';
const api = new Function('creditsNumber', code)(creditsNumber);
const table = { '1080p': 0.3, '720p': 0.14, '480p': 0.1 };
const cases = [
  ['768p', 0.14], ['768P', 0.14], ['720p', 0.14], ['1080p', 0.3], ['480p', 0.1],
  ['2k', 0.3], ['4k', 0.3], ['', 0.14], ['weird', 0.14],
];
let bad = 0;
for (const [res, want] of cases) {
  const got = api.creditsVideoPerSecond(table, res);
  if (got !== want) { bad++; console.log('FAIL', JSON.stringify(res), got, '!=', want); }
}
const ten = Math.round(api.creditsVideoPerSecond(table, '768p') * 10 * 1e6) / 1e6;
if (ten !== 1.4) { bad++; console.log('FAIL 768p*10 =', ten); }
console.log(bad ? 'VIDEO_TIER_CHECK=FAIL' : 'VIDEO_TIER_CHECK=OK');
process.exit(bad ? 1 : 0);
