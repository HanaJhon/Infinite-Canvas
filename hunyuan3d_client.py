"""混元 3D（3d.hunyuan.tencent.com）浏览器通道客户端 —— 多视图上传 → 生成 → 拿模型。

为什么走浏览器而不是纯 HTTP API
------------------------------
上传/生成只能通过页面交互完成（file input + 按钮点击，站点未开放上传 API）；
而资产查询 / 分享是站点自己的 JSON API（带登录 cookie 即可调，REFERENCE AV.3/AV.6
2026-10-12 实测）。所以分工：
  * 上传 + 生成：CDP 驱动系统 Edge 操作页面（复用浏览器登录态）；
  * 查询 / 分享 /（兜底）下载：页面内 fetch（同一登录态）。
用户不必填任何 Token，项目也不落盘 Token。

🚨 零新依赖：`websockets`（随包 python 已带，探针实测可用）+ 系统 Edge。
🚨 选择器 / API / 判据全部来自 REFERENCE **AV**（2026-10-12 实测），改页面前先看那一节。

设计：平时 headless 跑；未登录时用**同一个持久 profile** 起可见窗口让用户手动
      登录，登录后关窗、重开 headless 继续 —— 登录态留在 profile 里。
🚨 一个 profile 同时只能开一个 Edge：调用方必须自行串行化（main.py 用锁）。
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import time
import urllib.request
from typing import Any, Callable, List, Optional

try:
    import websockets
except Exception:  # pragma: no cover —— 随包 python 正常都带；缺了就明确报错
    websockets = None  # type: ignore

# --------------------------------------------------------------------------- 常量

SITE_URL = "https://3d.hunyuan.tencent.com/creation"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0")

# 选择器（REFERENCE AV.2 / AV.4 / AV.5 / AV.8 实测）
SEL_SINGLE_RADIO = "单张图片"                      # 单图模式 tab 文案（页面默认选中）
SEL_MULTI_RADIO = "多张图片"                       # 多图模式 tab 文案
MULTI_TEXT_SEL = ".t-radio-button, label, div, span, button"   # 找文案的宽网（探针同款）
SEL_SINGLE_BOX = ".uploadBox"                      # 单图模式的上传盒（isSuccess 判成）
SEL_ADD_MULTI = ".hy-multiple-views-upload-v2"     # 「添加多视图」入口按钮
SEL_GENERATE = ".sideBarLeft-generateBtn"          # 「立即生成」
# 视图卡片优先级：正图必填（站点带 *），其余按连接顺序依次落位
VIEW_ORDER = ["front", "left", "right", "back", "top", "bottom", "left-front", "right-front"]

CARD_WAIT = 150.0        # 等单张视图上传成功（isSuccess）的上限
GENERATE_WAIT = 1800.0   # 等生成完成的上限（30 分钟；实测约 3 分钟）
URL_GRACE = 180.0        # status=success 后继续等 result.urlResult.glb 的宽限
LOGIN_WAIT = 300.0       # 等用户手动登录的上限（5 分钟）
POLL = 8.0               # 轮询资产列表的间隔

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
]

# 起浏览器时剥掉代理环境变量：探测证明了「清代理」才能直连混元，
# 而 Edge 自己会走系统代理设置，不受影响。
_PROXY_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")


class Hunyuan3DError(Exception):
    """浏览器通道的普通失败。"""


class Hunyuan3DNeedLogin(Exception):
    """profile 里没有混元3D 登录态 —— 调用方引导用户登录后重试。"""

    code = "hy3d_need_login"


def find_edge() -> str:
    for path in EDGE_CANDIDATES:
        if path and os.path.exists(path):
            return path
    raise Hunyuan3DError("找不到 Microsoft Edge，无法使用浏览器通道")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _now() -> float:
    return time.time()


def _norm_ts(value: Any) -> float:
    """资产记录里的 createdAt 可能是秒或毫秒，统一成秒。"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0.0
    if num > 1e12:
        num /= 1000.0
    return num


def _extract_items(payload: Any) -> List[dict]:
    """从 creations/list 响应里递归找出「资产字典列表」。

    实测响应的外层形状可能包在 data / list 下（探针两种都见过），
    所以按「列表元素是带 id+status 的字典」递归找第一个命中，不猜结构。
    """
    if isinstance(payload, list):
        if payload and all(isinstance(x, dict) for x in payload) and any(
                "id" in x and "status" in x for x in payload if isinstance(x, dict)):
            return [x for x in payload if isinstance(x, dict)]
        for item in payload:
            found = _extract_items(item)
            if found:
                return found
        return []
    if isinstance(payload, dict):
        for key in ("list", "data", "creations", "items", "records"):
            if key in payload:
                found = _extract_items(payload[key])
                if found:
                    return found
        for value in payload.values():
            found = _extract_items(value)
            if found:
                return found
    return []


def _extract_glb(item: dict):
    """从资产记录里拿 (glb_url, asset_id)。

    🚨 实测（2026-10-13）：`modelUrl3d` / `mesh` 恒为 `{}`（废字段），真正的下载地址在
    `result[*].urlResult.glb`（带 COS 签名的完整 URL）；分享用的 contentId 是
    `result[*].assetId`（**不是** create 记录的 id —— 昨天实测分享 53c361db 就是它）。
    """
    results = item.get("result")
    if isinstance(results, list):
        for entry in results:
            if not isinstance(entry, dict):
                continue
            url_result = entry.get("urlResult")
            if isinstance(url_result, dict):
                for key in ("glb", "GLB", "model", "url"):
                    value = url_result.get(key)
                    if isinstance(value, str) and value.startswith("http"):
                        return value, str(entry.get("assetId") or "")
    value = item.get("modelUrl3d")  # 兜底：万一日后改成字符串
    if isinstance(value, str) and value.startswith("http"):
        return value, ""
    return "", ""


class _CDP:
    """极简 CDP 客户端：发命令 + 收响应/事件。"""

    def __init__(self, ws):
        self.ws = ws
        self._id = 0
        self.events: List[dict] = []

    async def send(self, method: str, params: Optional[dict] = None, timeout: float = 60.0):
        self._id += 1
        mid = self._id
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = _now() + timeout
        while _now() < deadline:
            msg = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=max(1.0, deadline - _now())))
            if msg.get("id") == mid:
                if "error" in msg:
                    raise Hunyuan3DError(f"CDP {method} 失败：{msg['error']}")
                return msg.get("result")
            if "method" in msg:
                self.events.append(msg)
                self.events = self.events[-200:]
        raise Hunyuan3DError(f"CDP {method} 超时")

    async def eval(self, expression: str, timeout: float = 60.0):
        res = await self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            timeout=timeout,
        )
        return (res or {}).get("result", {}).get("value")

# --------------------------------------------------------------------------- 主类


class Hunyuan3DBrowserClient:
    """一个浏览器会话（可跨多次生成复用，用完记得 aclose()）。

    🚨 同一 profile 不能并发开两个 Edge —— main.py 用 HY3D_BROWSER_LOCK 串行化。
    """

    def __init__(self, profile_dir: str, headless: bool = True, edge_path: Optional[str] = None):
        self.profile_dir = profile_dir
        self.headless = headless
        self.edge_path = edge_path or find_edge()
        self.port = free_port()
        self._proc: Optional[subprocess.Popen] = None
        self._ws = None
        self._cdp: Optional[_CDP] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *_exc):
        await self.aclose()

    # ------------------------------------------------------------ 生命周期

    def _child_env(self) -> dict:
        env = dict(os.environ)
        for key in _PROXY_ENV_KEYS:
            env.pop(key, None)
        return env

    def _spawn(self, headless: bool) -> subprocess.Popen:
        args = [
            self.edge_path,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--hide-scrollbars",
            "--disable-features=Translate,OptimizationHints,MediaRouter",
            "--window-size=1440,1100",
        ]
        if headless:
            args.append("--headless=new")
        args.append("about:blank")
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        return subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=self._child_env(), creationflags=creation,
        )

    async def start(self, headless: Optional[bool] = None):
        if headless is not None:
            self.headless = headless
        if websockets is None:
            raise Hunyuan3DError("缺少 websockets 依赖，浏览器通道不可用")
        os.makedirs(self.profile_dir, exist_ok=True)
        await self._close_browser_process()
        self.port = free_port()
        self._proc = self._spawn(self.headless)
        await self._wait_cdp()
        await self._connect()
        return self

    async def _wait_cdp(self, timeout: float = 45.0):
        deadline = _now() + timeout
        while _now() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=2) as r:
                    if r.status == 200:
                        return
            except Exception:
                pass
            await asyncio.sleep(0.4)
        raise Hunyuan3DError("浏览器调试端口没起来（CDP 不可用）")

    async def _connect(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=5) as r:
            tabs = json.loads(r.read())
        ws_url = ""
        for tab in tabs:
            if tab.get("type") == "page" and tab.get("webSocketDebuggerUrl"):
                ws_url = tab["webSocketDebuggerUrl"]
                break
        if not ws_url:
            raise Hunyuan3DError("没有可用的页面标签")
        # CDP 是本机回环 ws，不走代理
        self._ws = await websockets.connect(ws_url, max_size=64 * 1024 * 1024)
        self._cdp = _CDP(self._ws)
        for method in ("Page.enable", "Runtime.enable", "DOM.enable"):
            await self._cdp.send(method)
        return self._cdp

    @property
    def cdp(self) -> _CDP:
        if self._cdp is None:
            raise Hunyuan3DError("浏览器还没启动")
        return self._cdp

    async def _close_browser_process(self, wait: float = 6.0):
        """发 Browser.close（让 cookie 正常落盘！），再兜底结束进程。"""
        if self._ws is not None:
            try:
                await self._cdp.send("Browser.close", timeout=5.0)  # type: ignore[union-attr]
            except Exception:
                pass
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
            self._cdp = None
        if self._proc is not None:
            deadline = _now() + wait
            while _now() < deadline and self._proc.poll() is None:
                await asyncio.sleep(0.3)
            if self._proc.poll() is None:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
            self._proc = None

    async def aclose(self):
        await self._close_browser_process()

    # ------------------------------------------------------------ 页面操作原语

    async def goto(self, url: str, timeout: float = 90.0):
        await self.cdp.send("Page.navigate", {"url": url})
        deadline = _now() + timeout
        while _now() < deadline:
            await asyncio.sleep(0.8)
            try:
                if await self.cdp.eval("document.readyState") == "complete":
                    return
            except Exception:
                pass
        raise Hunyuan3DError(f"打开页面超时：{url}")

    async def wait_for(self, expression: str, timeout: float = 60.0, poll: float = 0.7) -> Any:
        deadline = _now() + timeout
        last: Any = None
        while _now() < deadline:
            try:
                last = await self.cdp.eval(expression)
            except Exception as exc:  # noqa: BLE001 —— 导航期间求值会失败，重试即可
                last = f"<eval failed: {exc}>"
            if last:
                return last
            await asyncio.sleep(poll)
        raise Hunyuan3DError(f"等待超时（{timeout:.0f}s）：{expression[:110]}（最后一次：{last}）")

    async def wait_quiet(self, expression: str, timeout: float = 20.0, poll: float = 0.7) -> bool:
        deadline = _now() + timeout
        while _now() < deadline:
            try:
                if await self.cdp.eval(expression):
                    return True
            except Exception:
                pass
            await asyncio.sleep(poll)
        return False

    async def click_js(self, expression: str) -> bool:
        return bool(await self.cdp.eval(
            f"(() => {{ const el = ({expression}); if(!el) return false; el.click(); return true; }})()"
        ))

    async def set_files(self, selector: str, paths: List[str]) -> bool:
        doc = await self.cdp.send("DOM.getDocument", {"depth": -1})
        res = await self.cdp.send("DOM.querySelector",
                                  {"nodeId": doc["root"]["nodeId"], "selector": selector})
        node_id = (res or {}).get("nodeId")
        if not node_id:
            return False
        await self.cdp.send("DOM.setFileInputFiles", {"files": list(paths), "nodeId": node_id})
        return True

    # ------------------------------------------------------------ 页面内 API（带登录态）

    async def api_post(self, path: str, body: dict, timeout: float = 40.0):
        """在页面上下文里 POST 站点自己的 JSON API，返回解析后的 data。"""
        expr = """(async () => {
          try {
            const r = await fetch(%s, {method:'POST', credentials:'include',
              headers:{'Content-Type':'application/json'}, body: JSON.stringify(%s)});
            const t = await r.text();
            return JSON.stringify({ok:r.ok, status:r.status, body:t.slice(0, 60000)});
          } catch (e) { return JSON.stringify({ok:false, status:0, body:String(e)}); }
        })()""" % (json.dumps(path), json.dumps(body))
        raw = await self.cdp.eval(expr, timeout=timeout)
        if not raw:
            raise Hunyuan3DError(f"页面内请求 {path} 无返回")
        try:
            payload = json.loads(raw)
        except Exception:
            raise Hunyuan3DError(f"页面内请求 {path} 返回无法解析：{str(raw)[:120]}")
        if not payload.get("ok"):
            raise Hunyuan3DError(f"{path} HTTP {payload.get('status')}: {str(payload.get('body'))[:200]}")
        try:
            return json.loads(payload.get("body") or "null")
        except Exception:
            raise Hunyuan3DError(f"{path} 返回的不是 JSON：{str(payload.get('body'))[:160]}")

    # ------------------------------------------------------------ 业务：登录 / 上传 / 生成

    async def ensure_ready(self):
        """打开创作页；未登录抛 Hunyuan3DNeedLogin；并就绪控件等待。"""
        await self.goto(SITE_URL)
        await asyncio.sleep(4.0)
        href = str(await self.cdp.eval("location.href") or "")
        if "/login" in href:
            raise Hunyuan3DNeedLogin("混元3D 站点未登录（浏览器 profile 里没有登录态）")
        ok = await self.wait_quiet(
            f"!!document.querySelector('{SEL_ADD_MULTI}') || !!document.querySelector('{SEL_GENERATE}')",
            timeout=30.0,
        )
        if not ok:
            raise Hunyuan3DError("创作页控件没出来（页面结构可能变了，见 REFERENCE AV）")

    async def login_interactive(self, timeout: float = LOGIN_WAIT, on_poll: Optional[Callable[[int], None]] = None):
        """用同一个 profile 起**可见窗口**，等用户手动登录。

        登录成功后正常关窗（cookie 落盘），调用方再 start(headless) 重试。
        """
        await self._close_browser_process()
        os.makedirs(self.profile_dir, exist_ok=True)
        self.port = free_port()
        self._proc = self._spawn(headless=False)
        await self._wait_cdp()
        await self._connect()
        await self.goto(SITE_URL)
        deadline = _now() + timeout
        stable = 0
        last_href = ""
        while _now() < deadline:
            await asyncio.sleep(2.0)
            try:
                href = str(await self.cdp.eval("location.href") or "")
            except Exception:
                continue
            if "/login" not in href and "3d.hunyuan.tencent.com" in href:
                # 连续两次稳定在创作页才算登录完成（避开登录跳转中的中间页）
                stable = stable + 1 if href == last_href else 1
                last_href = href
                if stable >= 2:
                    await asyncio.sleep(2.0)  # 等 cookie 落盘
                    await self._close_browser_process()
                    return True
            else:
                stable = 0
            if on_poll:
                try:
                    on_poll(int(_now() - (deadline - timeout)))
                except Exception:
                    pass
        await self._close_browser_process()
        raise Hunyuan3DNeedLogin(f"登录等待超时（{int(timeout)} 秒）")

    async def _switch_mode(self, label: str):
        """按文案切「单张图片 / 多张图片」。🚨 选择器必须用宽网（与探针逐字一致）——
        实测该控件不一定是 .t-radio-button，可能是 div/span；窄选择器会漏。"""
        expr = """(() => {
          const els = Array.from(document.querySelectorAll(%s));
          const el = els.find(n => (n.textContent||'').trim() === %s);
          if (!el) return 'missing';
          const group = el.closest('.t-radio-button') || el;
          const input = group.querySelector('input[type=radio], input');
          if (String(group.className).includes('t-is-checked') || (input && input.checked)) return 'checked';
          group.click();
          return 'clicked';
        })()""" % (json.dumps(MULTI_TEXT_SEL), json.dumps(label))
        state = await self.wait_for(expr, timeout=15.0)
        if state == "missing":
            raise Hunyuan3DError(f"找不到「{label}」控件（页面结构可能变了，见 REFERENCE AV.2）")
        if state == "clicked":
            await self.wait_quiet(
                """(() => {
                  const els = Array.from(document.querySelectorAll(%s));
                  const el = els.find(n => (n.textContent||'').trim() === %s);
                  if (!el) return false;
                  const group = el.closest('.t-radio-button') || el;
                  const input = group.querySelector('input[type=radio], input');
                  return String(group.className).includes('t-is-checked') || (input && input.checked);
                })()""" % (json.dumps(MULTI_TEXT_SEL), json.dumps(label)),
                timeout=10.0,
            )

    async def _switch_to_single(self):
        await self._switch_mode(SEL_SINGLE_RADIO)

    async def _switch_to_multi(self):
        await self._switch_mode(SEL_MULTI_RADIO)

    async def upload_single(self, path: str):
        """单图模式：切「单张图片」→ 塞 1 张进 .uploadBox → 等 isSuccess。"""
        if not os.path.isfile(path):
            raise Hunyuan3DError(f"图片不存在：{path}")
        await self._switch_to_single()
        sel = f"{SEL_SINGLE_BOX} input[type=file]"
        await self.wait_for(f"!!document.querySelector('{sel}')", timeout=30.0)
        if not await self.set_files(sel, [path]):
            raise Hunyuan3DError("单图模式的上传控件没找到（页面结构可能变了，见 REFERENCE AV.8）")
        ok = await self.wait_quiet(
            """(() => { const b = document.querySelector(%s);
                return !!b && String(b.className).includes('isSuccess'); })()""" % json.dumps(SEL_SINGLE_BOX),
            timeout=CARD_WAIT, poll=1.5,
        )
        if not ok:
            raise Hunyuan3DError("单张图片上传后长时间未确认成功（isSuccess 没出现）")

    async def upload_views(self, paths: List[str]):
        """按图片数量自动选方案：1 张 → 单图模式；≥2 张 → 多视图模式。

        🚨 多视图只支持 ≥2 张（站点入口 Min2）；正图必填，所以第 1 张落 front。
        🚨 「添加多视图」入口按钮在 radio 切完后**可能直接消失**（卡片就地渲染）——
          所以真正的就绪判据是 front 卡片 input 出现；入口只在卡片没出来时才点。
        """
        if not paths:
            raise Hunyuan3DError("没有可上传的图片")
        if len(paths) == 1:
            return await self.upload_single(paths[0])
        if len(paths) > len(VIEW_ORDER):
            paths = paths[:len(VIEW_ORDER)]

        await self._switch_to_multi()

        # 卡片没出来才找入口按钮点一次（探针实测路径）；已在就不用点，避免把卡片收起来
        cards_up = await self.wait_quiet(
            "!!document.querySelector('.hy-upload-card--front input[type=file]')", timeout=8.0)
        if not cards_up:
            if await self.wait_quiet(f"!!document.querySelector('{SEL_ADD_MULTI}')", timeout=10.0):
                if not await self.click_js(f"document.querySelector('{SEL_ADD_MULTI}')"):
                    raise Hunyuan3DError("点不动「添加多视图」按钮（见 REFERENCE AV.2）")
                await asyncio.sleep(2.0)
        await self.wait_for(
            "!!document.querySelector('.hy-upload-card--front input[type=file]')", timeout=30.0)

        # 3. 逐张上传，每张等卡片 isSuccess
        for path, view in zip(paths, VIEW_ORDER):
            if not os.path.isfile(path):
                raise Hunyuan3DError(f"视图图片不存在：{path}")
            if not await self.set_files(f".hy-upload-card--{view} input[type=file]", [path]):
                raise Hunyuan3DError(f"视图 {view} 的上传控件没找到（页面结构可能变了）")
            ok = await self.wait_quiet(
                """(() => { const c = document.querySelector(%s);
                    return !!c && String(c.className).includes('isSuccess'); })()"""
                % json.dumps(f".hy-upload-card--{view}"),
                timeout=CARD_WAIT, poll=1.5,
            )
            if not ok:
                raise Hunyuan3DError(f"视图 {view} 上传后长时间未确认成功（isSuccess 没出现）")
            await asyncio.sleep(1.0)  # 让上一张的 DOM 重建稳定一下

    async def click_generate(self):
        """点「立即生成」（前置条件：视图已上传、按钮非禁用）。"""
        ok = await self.wait_quiet(
            """(() => { const b = document.querySelector(%s);
                return !!b && !b.disabled; })()""" % json.dumps(SEL_GENERATE),
            timeout=30.0,
        )
        if not ok:
            raise Hunyuan3DError("「立即生成」按钮不可用（视图可能没上传够，正图必填）")
        if not await self.click_js(f"document.querySelector('{SEL_GENERATE}')"):
            raise Hunyuan3DError("点不动「立即生成」按钮")
        await asyncio.sleep(1.5)

    # ------------------------------------------------------------ 业务：资产 / 分享 / 下载

    async def _fetch_creations(self) -> List[dict]:
        data = await self.api_post("/api/3d/creations/list",
                                   {"limit": 20, "offset": 0, "sceneTypeList": []})
        return _extract_items(data)

    async def _max_created_at(self) -> float:
        """上传前记录当前最新资产时间戳（基线）——用站点自己的值，避免本机时钟偏差。"""
        try:
            items = await self._fetch_creations()
        except Exception:
            return 0.0
        stamps = [_norm_ts(it.get("createdAt")) for it in items]
        return max(stamps) if stamps else 0.0

    async def wait_asset(self, baseline_ts: float, timeout: float = GENERATE_WAIT,
                         on_progress: Optional[Callable[[str], None]] = None) -> dict:
        """轮询资产列表，等新资产（createdAt > 基线）生成完成并拿到 GLB 地址。

        🚨 status=success 后 `result[].urlResult.glb` 可能还要再等一会儿才填，
           所以「成功但没 URL」时继续轮询（最多再等 URL_GRACE 秒），不是失败。
        """
        deadline = _now() + timeout
        url_deadline = None
        newest = None
        last_status = ""
        while _now() < deadline:
            await asyncio.sleep(POLL)
            try:
                items = await self._fetch_creations()
            except Hunyuan3DError:
                continue  # 导航/刷新瞬间的求值失败，下一轮再看
            fresh = [it for it in items if _norm_ts(it.get("createdAt")) > baseline_ts + 1]
            if fresh:
                newest = max(fresh, key=lambda it: _norm_ts(it.get("createdAt")))
                status = str(newest.get("status") or "").lower()
                last_status = status
                if status in ("success", "succeeded", "successed", "done", "finished"):
                    glb_url, asset_id = _extract_glb(newest)
                    if glb_url:
                        return {
                            "asset_id": asset_id or str(newest.get("id") or ""),
                            "status": status,
                            "face_count": newest.get("faceCount"),
                            "model_url": glb_url,
                        }
                    # 成功但 URL 没填：给一段宽限继续等
                    if url_deadline is None:
                        url_deadline = _now() + URL_GRACE
                        last_status = "success(等模型地址)"
                elif any(k in status for k in ("fail", "error", "cancel")):
                    raise Hunyuan3DError(f"混元3D 生成失败（status={status}）")
            if url_deadline is not None and _now() > url_deadline and newest is not None:
                raise Hunyuan3DError("资产已生成但长时间拿不到模型地址（result.urlResult.glb 为空）")
            if on_progress:
                try:
                    on_progress(last_status or "processing")
                except Exception:
                    pass
        raise Hunyuan3DError(f"等待生成完成超时（{int(timeout // 60)} 分钟，最后状态：{last_status or '未出现新资产'}）")

    async def share_asset(self, content_id: str) -> str:
        """POST /api/3d/share → shareId → 拼出分享链接（每次调用新建）。"""
        if not content_id:
            raise Hunyuan3DError("没有资产 ID，无法分享")
        data = await self.api_post("/api/3d/share", {
            "contentType": "asset",
            "contentId": content_id,
            "platform": "3dPlayground",
        })
        share_id = str((data or {}).get("shareId") or "")
        if not share_id:
            raise Hunyuan3DError(f"分享接口没返回 shareId：{str(data)[:160]}")
        return f"https://3d.hunyuan.tencent.com/share?shareId={share_id}"

    async def fetch_quota(self) -> dict:
        """读当前登录账号的混元3D 额度（积分/次数）。

        🚨 必须实时读 —— 每个账号的总额度/已用量都不一样，**绝不能写死**。
        返回 {remain, total, consume, date}；字段缺失时给 None。
        """
        data = await self.api_post("/api/3d/quotainfo", {"sceneType": "3dCreations"})

        def pick(*keys):
            for key in keys:
                value = (data or {}).get(key)
                if isinstance(value, (int, float)):
                    return int(value)
            return None

        return {
            "remain": pick("remainQuota", "remain", "leftQuota"),
            "total": pick("totalQuota", "total"),
            "consume": pick("consumeQuota", "consume", "usedQuota"),
            "date": str((data or {}).get("date") or ""),
        }

    def _download_direct(self, url: str) -> Optional[bytes]:
        # ① 直连（绕环境代理——探测证明清代理才能到混元）
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=180) as r:
                return r.read()
        except Exception:
            pass
        # ② 走环境代理（老板机器若必须代理上网）
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=180) as r:
                return r.read()
        except Exception:
            return None

    async def _download_via_page(self, url: str) -> bytes:
        expr = """(async () => {
          try {
            const r = await fetch(%s, {credentials:'include'});
            const buf = await r.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let bin = '';
            const CH = 0x8000;
            for (let i = 0; i < bytes.length; i += CH) {
              bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
            }
            return JSON.stringify({ok:r.ok, status:r.status, b64:btoa(bin)});
          } catch (e) { return JSON.stringify({ok:false, status:0, b64:String(e)}); }
        })()""" % json.dumps(url)
        raw = await self.cdp.eval(expr, timeout=300.0)
        payload = json.loads(raw or "{}")
        if not payload.get("ok"):
            raise Hunyuan3DError(f"页面内下载失败 HTTP {payload.get('status')}")
        import base64 as _b64
        return _b64.b64decode(payload.get("b64") or "")

    async def download_model(self, url: str, dest_path: str) -> int:
        """下载 GLB 到 dest_path，返回字节数。三级兜底：直连 → 环境代理 → 页面内 fetch。"""
        data = self._download_direct(url)
        if data is None:
            data = await self._download_via_page(url)
        if not data or len(data) < 16:
            raise Hunyuan3DError("下载到的模型文件异常（太小或为空）")
        if data[:4] != b"glTF":
            raise Hunyuan3DError("下载到的不是 GLB 文件（头部魔校验失败）")
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(data)
        return len(data)

    # ------------------------------------------------------------ 主流程

    async def generate(self, view_paths: List[str], glb_path: str,
                       on_progress: Optional[Callable[[str, str], None]] = None) -> dict:
        """完整跑一遍：登录检查 → 上传 → 生成 → 等资产 → 下载 GLB。

        返回 {asset_id, face_count, model_url, glb_bytes}。on_progress(phase, message)。
        """

        def note(phase: str, message: str):
            if on_progress:
                try:
                    on_progress(phase, message)
                except Exception:
                    pass

        await self.ensure_ready()
        baseline = await self._max_created_at()

        mode = "单张图片" if len(view_paths) == 1 else f"多张图片（{len(view_paths)} 视图）"
        note("upload", f"上传到混元3D（{mode}）")
        await self.upload_views(view_paths)

        note("generate", "点击「立即生成」")
        await self.click_generate()

        note("process", "混元3D 生成中（约 2~5 分钟）")
        asset = await self.wait_asset(
            baseline,
            on_progress=lambda st: note("process", f"混元3D 生成中（{st or 'processing'}）"),
        )

        note("download", "下载 GLB 模型")
        size = await self.download_model(asset["model_url"], glb_path)
        asset["glb_bytes"] = size
        note("done", "模型就绪")
        return asset
