"""邮箱验证码：SMTP 发信 + 验证码存储。

只做两件事：
1. `send_mail()` —— 按管理员的 SMTP 配置发一封纯文本邮件（stdlib smtplib，无第三方依赖）。
2. `EmailCodeStore` —— 生成 / 限频 / 校验 6 位验证码，落盘到 `data/email_codes.json`（重启不丢）。

注册流程（main.py `/api/auth/register`）在 `signup.require_email_verify` 打开时调用
`EmailCodeStore.consume()`，校验通过才允许建号。
"""

import json
import os
import random
import re
import smtplib
import threading
import time
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Dict, Optional

#: 验证码有效期（秒）
CODE_TTL = 600
#: 同一邮箱重发间隔（秒）
RESEND_INTERVAL = 60
#: 同一邮箱一小时内最多发几次
HOURLY_LIMIT = 10
#: 单个验证码最多尝试几次
MAX_ATTEMPTS = 6
CODE_LENGTH = 6

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def mask_email(email: str) -> str:
    """`abcdef@qq.com` → `ab***@qq.com`，用于接口回显与日志。"""
    addr = str(email or "").strip()
    if "@" not in addr:
        return addr
    name, _, domain = addr.partition("@")
    if len(name) <= 2:
        shown = name[:1] + "*"
    else:
        shown = name[:2] + "***"
    return f"{shown}@{domain}"


def mail_ready(mail: Dict[str, Any]) -> bool:
    cfg = mail if isinstance(mail, dict) else {}
    return bool(cfg.get("enabled") and str(cfg.get("host") or "").strip())


def send_mail(mail: Dict[str, Any], to_addr: str, subject: str, body: str) -> None:
    """同步发一封纯文本邮件；失败抛异常（调用方转成 400/500）。"""
    cfg = mail if isinstance(mail, dict) else {}
    if not mail_ready(cfg):
        raise RuntimeError("未配置发信服务器")
    host = str(cfg.get("host") or "").strip()
    port = int(cfg.get("port") or 465)
    security = str(cfg.get("security") or "ssl").strip().lower()
    user = str(cfg.get("user") or "").strip()
    password = str(cfg.get("password") or "")
    sender = str(cfg.get("sender") or "").strip() or user
    sender_name = str(cfg.get("sender_name") or "").strip()
    if not sender:
        raise RuntimeError("未配置发件人地址")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((sender_name, sender)) if sender_name else sender
    msg["To"] = to_addr
    msg.set_content(body, charset="utf-8")

    timeout = 20
    if security == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=timeout)
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
        if security == "starttls":
            server.starttls()
    try:
        server.ehlo()
        if user:
            server.login(user, password)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


class EmailCodeStore:
    """验证码的生成与校验。线程安全；落盘保证重启后仍可用（10 分钟内）。"""

    def __init__(self, data_dir: str):
        self._lock = threading.RLock()
        self.path = os.path.join(data_dir, "email_codes.json")
        self._codes: Dict[str, Dict[str, Any]] = self._load()

    # ------------------------------------------------------------ 存储
    def _load(self) -> Dict[str, Dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                now = time.time()
                return {k: v for k, v in data.items()
                        if isinstance(v, dict) and float(v.get("exp") or 0) > now}
        except Exception:
            pass
        return {}

    def _write(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._codes, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            pass   # 落盘失败不影响内存校验

    def _prune(self) -> None:
        now = time.time()
        for key in [k for k, v in self._codes.items() if float(v.get("exp") or 0) <= now]:
            self._codes.pop(key, None)

    # ------------------------------------------------------------ 生成
    def issue(self, email: str, ttl: int = CODE_TTL) -> Dict[str, Any]:
        """生成验证码。限频时抛 ValueError（带中文提示）。"""
        addr = str(email or "").strip().lower()
        if not EMAIL_RE.match(addr):
            raise ValueError("邮箱格式不正确")
        now = time.time()
        with self._lock:
            self._prune()
            item = self._codes.get(addr) or {}
            sent_at = float(item.get("sent_at") or 0)
            if sent_at and now - sent_at < RESEND_INTERVAL:
                wait = int(RESEND_INTERVAL - (now - sent_at)) + 1
                raise ValueError(f"发送太频繁，请 {wait} 秒后再试")
            history = [t for t in (item.get("history") or []) if now - float(t) < 3600]
            if len(history) >= HOURLY_LIMIT:
                raise ValueError("该邮箱一小时内验证码次数过多，请稍后再试")
            code = "".join(random.choice("0123456789") for _ in range(CODE_LENGTH))
            item.update({
                "code": code,
                "exp": now + max(60, int(ttl)),
                "sent_at": now,
                "tries": 0,
                "history": history + [now],
            })
            self._codes[addr] = item
            self._write()
            return {"code": code, "expires_in": max(60, int(ttl)),
                    "retry_after": RESEND_INTERVAL}

    # ------------------------------------------------------------ 校验
    def check(self, email: str, code: str) -> str:
        """返回空串表示通过；否则返回中文原因（不消耗验证码）。"""
        addr = str(email or "").strip().lower()
        given = str(code or "").strip()
        if not given:
            return "请填写邮箱验证码"
        with self._lock:
            self._prune()
            item = self._codes.get(addr)
            if not isinstance(item, dict):
                return "请先获取邮箱验证码"
            if float(item.get("exp") or 0) <= time.time():
                self._codes.pop(addr, None)
                self._write()
                return "验证码已过期，请重新获取"
            if int(item.get("tries") or 0) >= MAX_ATTEMPTS:
                return "验证码错误次数过多，请重新获取"
            if str(item.get("code") or "") != given:
                item["tries"] = int(item.get("tries") or 0) + 1
                self._write()
                return "验证码不正确"
            return ""

    def consume(self, email: str) -> None:
        """校验通过后调用，作废该验证码。"""
        addr = str(email or "").strip().lower()
        with self._lock:
            if addr in self._codes:
                self._codes.pop(addr, None)
                self._write()


_code_store: Optional[EmailCodeStore] = None
_code_lock = threading.Lock()


def code_store(data_dir: str) -> EmailCodeStore:
    """进程内单例（data_dir 固定，无需多实例）。"""
    global _code_store
    with _code_lock:
        if _code_store is None:
            _code_store = EmailCodeStore(data_dir)
        return _code_store
