"""小抽AI 的内置浏览器 —— 用 CDP 驱动无头 Edge，画面实时回传给页面显示。

它是「可视化内置浏览器」：浏览器进程在服务端跑（默认无头），小抽AI 页面
右侧面板按帧显示它的画面，用户能直接看到 Agent 正在点哪里、填了什么；
同一个面板也能自己动手（点、滚动、打字都由页面把坐标转给 CDP）。

为什么是 CDP 而不是扩展 / Playwright
-----------------------------------
项目里已经有一条 CDP 通道（`hunyuan3d_client.py`，混元 3D 用它点页面），
`websockets` 随包 python 就带，Edge 是 Windows 自带 ⇒ 零新依赖、零安装步骤。

🚨 「控制当前打开的那个浏览器窗口」有个硬前提：那个进程必须带
   `--remote-debugging-port` 启动，否则浏览器不对外暴露 CDP，谁也连不上
   （这是浏览器的安全边界，不是我们没做）。所以本模块自己起一个浏览器：
     1. 已经有我们开的浏览器 → 直接复用；
     2. 环境变量 `BROWSER_CDP_URL` 指到某个调试端口 → 接上去；
     3. 都没有 → 起一个无头 Edge（独立 profile，登录一次就记住）。
   想要一个真的窗口盯着看，设 `BROWSER_VISIBLE=1` 就带窗口启动。

设计约束：
  * 一个进程一个 profile，同一时刻只有一个标签页被驱动（串行锁）；
  * 所有动作走 `send()`，超时统一 30s，避免把对话卡死；
  * 页面上取不到的元素直接报错，不猜坐标。
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import subprocess
import time
import urllib.request
from typing import Any, Dict, Optional

try:
    import websockets
except Exception:  # pragma: no cover
    websockets = None  # type: ignore

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    # Edge 被卸载时退到 Chrome（同样支持 CDP）
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

ACTION_TIMEOUT = 30.0        # 单个动作上限
LAUNCH_TIMEOUT = 25.0        # 等调试端口就绪
PAGE_TEXT_LIMIT = 6000       # 回灌给模型的正文字符数

_PROXY_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")


class BrowserControlError(Exception):
    """浏览器通道的普通失败（会原样告诉模型）。"""


def find_edge() -> str:
    for path in EDGE_CANDIDATES:
        if path and os.path.exists(path):
            return path
    raise BrowserControlError("找不到 Microsoft Edge，无法使用浏览器通道")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_json(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


class _CDP:
    """极简 CDP 客户端：发命令、等响应，事件丢进队列。"""

    def __init__(self, ws):
        self.ws = ws
        self._id = 0
        # 收帧（SSE）和 Agent 的动作会同时打进来，一条连接只能一问一答 ⇒ 排队
        self._lock = asyncio.Lock()

    async def send(self, method: str, params: Optional[dict] = None, timeout: float = ACTION_TIMEOUT):
        async with self._lock:
            self._id += 1
            mid = self._id
            await self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            deadline = time.time() + timeout
            while time.time() < deadline:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=max(1.0, deadline - time.time()))
                msg = json.loads(raw)
                if msg.get("id") == mid:
                    if "error" in msg:
                        raise BrowserControlError(f"浏览器执行 {method} 失败：{msg['error']}")
                    return msg.get("result")
        raise BrowserControlError(f"浏览器执行 {method} 超时")

    async def eval(self, expression: str, timeout: float = ACTION_TIMEOUT):
        res = await self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            timeout=timeout,
        )
        return ((res or {}).get("result") or {}).get("value")


class BrowserSession:
    """一个受控 Edge 窗口 + 当前标签页。进程级单例（由 main.py 用锁串行化调用）。"""

    def __init__(self, profile_dir: str):
        self.profile_dir = profile_dir
        self.port: Optional[int] = None
        self.proc: Optional[subprocess.Popen] = None
        self.cdp: Optional[_CDP] = None
        self.ws = None
        self.target_id: Optional[str] = None

    # ---------------------------------------------------------------- 启动 / 连接

    async def ensure(self) -> None:
        """确保有一个可驱动的标签页。"""
        if websockets is None:
            raise BrowserControlError("服务端缺少 websockets 组件，无法控制浏览器")
        if self.cdp is not None:
            try:
                await self.cdp.eval("1")
                return
            except Exception:
                await self.close()
        env_port = str(os.getenv("BROWSER_CDP_URL") or "").strip()
        if env_port:
            self.port = int(env_port.rsplit(":", 1)[-1].strip("/"))
        else:
            await self._launch()
        await self._attach()

    async def _launch(self) -> None:
        self.port = _free_port()
        os.makedirs(self.profile_dir, exist_ok=True)
        args = [
            find_edge(),
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1280,860",
            # 默认无头：画面回传给小抽AI 页面显示，不在桌面上另开窗口
            "--hide-scrollbars",
        ]
        if not os.getenv("BROWSER_VISIBLE"):
            args.append("--headless=new")
        args.append("about:blank")
        # 剥掉代理环境变量（本机代理会让浏览器访问外网变慢）；Edge 自己读系统代理，不受影响
        env = dict(os.environ)
        for key in _PROXY_ENV_KEYS:
            env.pop(key, None)
        self.proc = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + LAUNCH_TIMEOUT
        while time.time() < deadline:
            try:
                _http_json(f"http://127.0.0.1:{self.port}/json/version", timeout=1.5)
                return
            except Exception:
                await asyncio.sleep(0.3)
        raise BrowserControlError("浏览器没有启动成功（调试端口没响应）")

    async def _attach(self) -> None:
        targets = _http_json(f"http://127.0.0.1:{self.port}/json/list")
        pages = [t for t in targets if t.get("type") == "page"]
        if not pages:
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/new?about:blank", method="PUT")
            with urllib.request.urlopen(req, timeout=8) as resp:
                pages = [json.loads(resp.read().decode("utf-8", "ignore"))]
        page = pages[0]
        self.target_id = page.get("id")
        self.ws = await websockets.connect(page["webSocketDebuggerUrl"], max_size=32 * 1024 * 1024)
        self.cdp = _CDP(self.ws)
        await self.cdp.send("Page.enable")
        await self.cdp.send("Runtime.enable")

    async def close(self) -> None:
        try:
            if self.ws is not None:
                await self.ws.close()
        except Exception:
            pass
        self.ws = None
        self.cdp = None

    async def shutdown(self) -> None:
        """关掉受控窗口（用户取消授权时调用）。"""
        await self.close()
        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None

    # ---------------------------------------------------------------- 动作

    async def _wait_ready(self, timeout: float = 15.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if await self.cdp.eval("document.readyState", timeout=5) == "complete":
                    return
            except Exception:
                pass
            await asyncio.sleep(0.4)

    async def goto(self, url: str) -> Dict[str, Any]:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        await self.cdp.send("Page.navigate", {"url": url})
        await self._wait_ready()
        return await self.read()

    async def current_url(self) -> str:
        return await self.cdp.eval("location.href") or ""

    async def read(self) -> Dict[str, Any]:
        text = await self.cdp.eval("document.body ? document.body.innerText : ''") or ""
        title = await self.cdp.eval("document.title") or ""
        url = await self.current_url()
        body = text.strip()
        clipped = len(body) > PAGE_TEXT_LIMIT
        return {
            "ok": True,
            "summary": f"{title or url}",
            "output": body[:PAGE_TEXT_LIMIT],
            "url": url,
            "title": title,
            "truncated": clipped,
        }

    def _find_element_js(self, selector: str = "", text: str = "") -> str:
        """返回一个能在页面里执行的 JS 片段，结果存到 window.__xvTarget。"""
        if selector:
            sel_literal = json.dumps(selector)
            return (
                "(() => {"
                f" const el = document.querySelector({sel_literal});"
                " if (!el) return false;"
                " el.scrollIntoView({block:'center'}); window.__xvTarget = el; return true;"
                "})()"
            )
        text_literal = json.dumps(text)
        return (
            "(() => {"
            f" const want = {text_literal}.trim();"
            " const nodes = Array.from(document.querySelectorAll('a,button,input,textarea,select,li,label,div,span'));"
            " const norm = s => (s || '').replace(/\\s+/g, ' ').trim();"
            " const exact = nodes.filter(n => norm(n.innerText || n.value || '') === want);"
            " const fuzzy = nodes.filter(n => norm(n.innerText || n.value || '').includes(want));"
            " const el = (exact.length ? exact : fuzzy).sort((a, b) =>"
            "   (a.innerText || '').length - (b.innerText || '').length)[0];"
            " if (!el) return false;"
            " el.scrollIntoView({block:'center'}); window.__xvTarget = el; return true;"
            "})()"
        )

    async def click(self, selector: str = "", text: str = "") -> Dict[str, Any]:
        if not selector and not text:
            raise BrowserControlError("click 需要 selector 或 text 参数")
        found = await self.cdp.eval(self._find_element_js(selector, text))
        if not found:
            raise BrowserControlError(f"页面上没找到要点的元素（{selector or text}）")
        # 先在页面内点一次（兼容 SPA 的事件绑定），失败再用真实鼠标事件补
        clicked = await self.cdp.eval(
            "(() => { const el = window.__xvTarget; if (!el) return 'gone';"
            " el.click(); return 'ok'; })()"
        )
        if clicked != "ok":
            raise BrowserControlError("元素已消失，无法点击")
        box = await self.cdp.eval(
            "(() => { const r = window.__xvTarget.getBoundingClientRect();"
            " return [r.x + r.width / 2, r.y + r.height / 2]; })()"
        )
        if box:
            x, y = box
            for kind in ("mousePressed", "mouseReleased"):
                await self.cdp.send("Input.dispatchMouseEvent", {
                    "type": kind, "x": x, "y": y, "button": "left", "clickCount": 1,
                })
        await asyncio.sleep(0.4)
        return await self.read()

    async def type_text(self, text: str, selector: str = "", Enter: bool = False) -> Dict[str, Any]:
        if selector:
            focused = await self.cdp.eval(
                "(() => { const el = document.querySelector(" + json.dumps(selector) + ");"
                " if (!el) return false; el.focus(); return true; })()"
            )
            if not focused:
                raise BrowserControlError(f"页面上没找到输入框（{selector}）")
        await self.cdp.send("Input.insertText", {"text": text})
        if Enter:
            await self.key("Enter")
        await asyncio.sleep(0.3)
        return await self.read()

    async def key(self, name: str) -> Dict[str, Any]:
        key_map = {
            "Enter": ("Enter", 13), "Tab": ("Tab", 9), "Escape": ("Escape", 27),
            "Backspace": ("Backspace", 8), "ArrowDown": ("ArrowDown", 40),
            "ArrowUp": ("ArrowUp", 38), "PageDown": ("PageDown", 34),
        }
        code, kc = key_map.get(name, (name, 0))
        for kind in ("keyDown", "keyUp"):
            await self.cdp.send("Input.dispatchKeyEvent", {
                "type": kind, "key": code, "windowsVirtualKeyCode": kc, "nativeVirtualKeyCode": kc,
            })
        await asyncio.sleep(0.3)
        return await self.read()

    async def scroll(self, delta_y: int = 600) -> Dict[str, Any]:
        await self.cdp.eval(f"window.scrollBy(0, {int(delta_y)})")
        await asyncio.sleep(0.2)
        return await self.read()

    # ---------------------------------------------------------------- 画面与真人操作

    async def capture(self, quality: int = 50) -> Dict[str, Any]:
        """取一帧 JPEG（base64），顺带把地址和视口尺寸带回去给页面换算坐标。"""
        res = await self.cdp.send("Page.captureScreenshot", {
            "format": "jpeg", "quality": int(quality), "captureBeyondViewport": False,
        }, timeout=15)
        vp = await self.cdp.eval(
            "(() => ({ w: window.innerWidth, h: window.innerHeight,"
            " url: location.href, title: document.title }))()"
        ) or {}
        return {
            "image": (res or {}).get("data") or "",
            "width": int(vp.get("w") or 0),
            "height": int(vp.get("h") or 0),
            "url": vp.get("url") or "",
            "title": vp.get("title") or "",
        }

    async def click_at(self, x: float, y: float) -> None:
        for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
            await self.cdp.send("Input.dispatchMouseEvent", {
                "type": kind, "x": float(x), "y": float(y), "button": "left", "clickCount": 1,
            })

    async def wheel(self, x: float, y: float, delta: int) -> None:
        await self.cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseWheel", "x": float(x), "y": float(y),
            "deltaX": 0, "deltaY": int(delta), "button": "none",
        })

    async def reload_page(self) -> None:
        await self.cdp.send("Page.reload", {})
        await self._wait_ready()

    async def go_back(self) -> None:
        await self.cdp.eval("history.back()")
        await self._wait_ready(timeout=8)

    async def go_forward(self) -> None:
        await self.cdp.eval("history.forward()")
        await self._wait_ready(timeout=8)

    async def screenshot(self, path: str) -> Dict[str, Any]:
        res = await self.cdp.send("Page.captureScreenshot", {"format": "png"})
        data = base64.b64decode((res or {}).get("data") or "")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return {"ok": True, "summary": "已截图", "output": "", "path": path, "bytes": len(data)}


_SESSION: Optional[BrowserSession] = None


def get_session(profile_dir: str) -> BrowserSession:
    global _SESSION
    if _SESSION is None or _SESSION.profile_dir != profile_dir:
        _SESSION = BrowserSession(profile_dir)
    return _SESSION


async def shutdown_session() -> None:
    global _SESSION
    if _SESSION is not None:
        await _SESSION.shutdown()
        _SESSION = None
