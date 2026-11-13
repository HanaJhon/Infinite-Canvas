"""积分与计费（2026-11-05 新增）

设计要点（老板 m15737 的需求）：
- 积分为站点级虚拟货币，1 积分默认 = $1 = ¥1（汇率可改，两套同时给）。
- 管理员在「API 设置 → 积分与计费」里配置：汇率、新用户初始积分、注册限制、
  充值套餐（标准额度）、收款方式（二维码图片或链接）、每个模型的积分单价。
- 模型计价分三类：
    * 语言模型：输入 / 输出 / 缓存读取 三个「积分 / 1M tokens」；
    * 视频模型：按分辨率 1080P / 720P / 480P 的「积分 / 秒」；
    * 图像模型：直接「积分 / 张」。
- 用户余额存在 `data/users.json` 的 `credits` 字段（和账号同一条记录，删号即清）；
  流水写到 `data/users/<uid>/credits_ledger.json`（最多保留 500 条）。
- 充值申请走 `data/credits_topups.json`：成员提交 → 管理员批准或驳回。
- **本版只记账、不拦截**：`enforce_balance` 默认 False，余额不够也允许生成，
  只是不扣（`spend()` 返回 0）。等老板确认后再打开拦截。
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

LEDGER_LIMIT = 500
TOPUP_LIMIT = 500

PAYMENT_METHODS = ("wechat", "alipay", "paypal", "bank", "other")

MODEL_KINDS = ("llm", "image", "video")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out or out in (float("inf"), float("-inf")):   # NaN / inf
        return default
    return out


def _video_price_tier(resolution) -> str:
    """单价表只有 480p / 720p / 1080p 三档，更细的模型档位按就近档计价。

    minimax-h3 的 768p 官方是与 720p 同价档（0.14/秒），若直接查表会落空、
    再退到「表里第一个值」（1080p = 0.3/秒），预估价翻倍（老板 2026-11-06 反馈）。
    """
    raw = str(resolution or "").strip().lower()
    if not raw:
        return "720p"
    if raw == "768p":
        return "720p"
    if raw in ("2k", "4k", "2160p"):
        return "1080p"
    return raw.replace("p", "") + "p"


def _round(value: float) -> float:
    return round(_num(value), 4)


#: 中日韩文字/全角符号（这些按「一字一 token」估，其它按 4 字符一 token）
_WIDE_CHAR_RE = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")


def estimate_tokens(text: Any) -> int:
    """粗略 token 数估算：中文等宽字符 ≈1 token/字，其余 ≈4 字符/token。

    前端 `static/js/credits-badge.js` 的 `estimateTokens()` 用同一套规则，
    两边算出来的积分预估才对得上（老板 m22656）。
    """
    s = str(text or "")
    if not s:
        return 0
    wide = len(_WIDE_CHAR_RE.findall(s))
    return int(round(wide + (len(s) - wide) / 4.0))


#: 「主流邮箱」白名单——勾了「不允许非主流邮箱」时，只放行这些域名（以及管理员手工加入 allow 的域名）。
FREE_EMAIL_DOMAINS = {
    "qq.com", "foxmail.com", "163.com", "126.com", "yeah.net", "sina.com", "sina.cn",
    "sohu.com", "139.com", "189.cn", "aliyun.com", "gmail.com", "googlemail.com",
    "outlook.com", "hotmail.com", "live.com", "msn.com", "icloud.com", "me.com",
    "mac.com", "yahoo.com", "ymail.com", "proton.me", "protonmail.com", "gmx.com",
    "yandex.com", "zoho.com", "aol.com", "mail.com", "fastmail.com", "hey.com",
}

def _str_list(raw: Any, limit: int = 40) -> List[str]:
    """把「多行文本 / 逗号分隔 / 数组」统一成去重后的字符串列表。"""
    items: List[str] = []
    if isinstance(raw, str):
        parts = re.split(r"[\s,，;；\n\r]+", raw)
    elif isinstance(raw, (list, tuple)):
        parts = [str(x) for x in raw]
    else:
        parts = []
    for part in parts:
        text = str(part or "").strip().lower()
        if not text:
            continue
        if text not in items:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def _email_matches(entry: str, email: str, domain: str) -> bool:
    """allow/deny 条目既可以是完整邮箱，也可以是域名（可带 @）。"""
    key = entry.strip().lower().lstrip("@")
    if not key:
        return False
    if "@" in key:
        return email == key
    return domain == key or email.endswith("@" + key)


def check_email_policy(signup: Dict[str, Any], email: str) -> str:
    """返回空串表示通过，否则返回中文拒绝原因。"""
    policy = signup.get("email") if isinstance(signup.get("email"), dict) else {}
    allow = _str_list(policy.get("allow"))
    deny = _str_list(policy.get("deny"))
    block_free = bool(policy.get("block_free"))
    addr = str(email or "").strip().lower()
    if not addr:
        return ""
    domain = addr.split("@")[-1]

    for entry in deny:
        if _email_matches(entry, addr, domain):
            return "该邮箱域名不在本站允许范围内"
    if allow:
        if not any(_email_matches(entry, addr, domain) for entry in allow):
            return "本站只允许指定邮箱域名注册"
    if block_free and domain not in FREE_EMAIL_DOMAINS:
        if not any(_email_matches(entry, addr, domain) for entry in allow):
            return "请使用主流邮箱注册（不支持临时邮箱 / 小众域名）"
    return ""


def default_settings() -> Dict[str, Any]:
    return {
        "version": 1,
        "rate": {
            "credit_per_cny": 1.0,
            "credit_per_usd": 1.0,
            "note": "1 积分 = ￥1 = $1",
        },
        "signup": {
            "initial_credits": 0.0,
            "require_email": False,
            # 邮箱验证码：开启后注册必须先收码并通过 /api/auth/verify-email 校验
            "require_email_verify": False,
            # 邮箱范围限制：allow / deny 支持「完整邮箱」或「域名」，block_free = 不允许非主流邮箱
            "email": {"allow": [], "deny": [], "block_free": False},
        },
        # 发信服务器（邮箱验证码用）。password 为 SMTP 授权码，仅存本地 data/credits_settings.json
        "mail": {
            "enabled": False,
            "host": "",
            "port": 465,
            "security": "ssl",          # ssl / starttls / none
            "user": "",
            "password": "",
            "sender": "",               # 留空则用 user
            "sender_name": "无限画布",
        },
        "topup": {
            # 标准额度：{id, label, credits, price_cny, price_usd}
            "presets": [],
            # 收款方式：{id, method, label, kind:'qr'|'link', value, note}
            "payments": [],
            "allowed_methods": ["wechat", "alipay", "paypal"],
        },
        # 模型计价：key = 模型名（或 "provider::model"），见 normalize_model_pricing()
        "models": {},
        # 余额不足拦截（老板 2026-11-13 要求：余额不足将拦截；费用为 0 的不拦）
        "enforce_balance": True,
        "auto_deduct": True,
        "updated_at": 0,
    }


def normalize_model_pricing(raw: Any) -> Dict[str, Any]:
    """把管理员提交的模型单价清洗成固定结构。非法条目直接丢弃。"""
    out: Dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for key, item in raw.items():
        name = str(key or "").strip()
        if not name or not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        if kind not in MODEL_KINDS:
            continue
        if kind == "llm":
            entry = {
                "kind": "llm",
                "input": _round(item.get("input")),      # 积分 / 1M 输入 token
                "output": _round(item.get("output")),    # 积分 / 1M 输出 token
                "cache": _round(item.get("cache")),      # 积分 / 1M 缓存读取 token
            }
        elif kind == "image":
            entry = {"kind": "image", "per_image": _round(item.get("per_image"))}
        else:
            per_second = item.get("per_second") if isinstance(item.get("per_second"), dict) else {}
            entry = {
                "kind": "video",
                "per_second": {
                    "1080p": _round(per_second.get("1080p", per_second.get("1080P", 0))),
                    "720p": _round(per_second.get("720p", per_second.get("720P", 0))),
                    "480p": _round(per_second.get("480p", per_second.get("480P", 0))),
                },
            }
        label = str(item.get("label") or "").strip()
        if label:
            entry["label"] = label
        out[name] = entry
    return out


def normalize_settings(raw: Any) -> Dict[str, Any]:
    base = default_settings()
    if not isinstance(raw, dict):
        return base

    rate = raw.get("rate") if isinstance(raw.get("rate"), dict) else {}
    base["rate"]["credit_per_cny"] = _num(rate.get("credit_per_cny"), 1.0) or 1.0
    base["rate"]["credit_per_usd"] = _num(rate.get("credit_per_usd"), 1.0) or 1.0
    base["rate"]["note"] = str(rate.get("note") or "").strip()

    signup = raw.get("signup") if isinstance(raw.get("signup"), dict) else {}
    base["signup"]["initial_credits"] = max(0.0, _round(signup.get("initial_credits")))
    base["signup"]["require_email"] = bool(signup.get("require_email"))
    base["signup"]["require_email_verify"] = bool(signup.get("require_email_verify"))

    email_policy = signup.get("email") if isinstance(signup.get("email"), dict) else {}
    base["signup"]["email"] = {
        "allow": _str_list(email_policy.get("allow")),
        "deny": _str_list(email_policy.get("deny")),
        "block_free": bool(email_policy.get("block_free")),
    }

    mail = raw.get("mail") if isinstance(raw.get("mail"), dict) else {}
    security = str(mail.get("security") or "ssl").strip().lower()
    if security not in ("ssl", "starttls", "none"):
        security = "ssl"
    port = int(_num(mail.get("port"), 465)) or 465
    base["mail"] = {
        "enabled": bool(mail.get("enabled")),
        "host": str(mail.get("host") or "").strip(),
        "port": max(1, min(65535, port)),
        "security": security,
        "user": str(mail.get("user") or "").strip(),
        "password": str(mail.get("password") or ""),
        "sender": str(mail.get("sender") or "").strip(),
        "sender_name": str(mail.get("sender_name") or "无限画布").strip() or "无限画布",
    }

    topup = raw.get("topup") if isinstance(raw.get("topup"), dict) else {}
    presets: List[Dict[str, Any]] = []
    for item in topup.get("presets") or []:
        if not isinstance(item, dict):
            continue
        credits = _round(item.get("credits"))
        if credits <= 0:
            continue
        presets.append({
            "id": str(item.get("id") or "p_" + secrets.token_hex(4)),
            "label": str(item.get("label") or f"{credits:g} 积分").strip(),
            "credits": credits,
            "price_cny": _round(item.get("price_cny")),
            "price_usd": _round(item.get("price_usd")),
        })
    base["topup"]["presets"] = presets[:24]

    payments: List[Dict[str, Any]] = []
    for item in topup.get("payments") or []:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or "").strip()
        if not value:
            continue
        method = str(item.get("method") or "other").strip().lower()
        if method not in PAYMENT_METHODS:
            method = "other"
        kind = "qr" if str(item.get("kind") or "qr").lower() == "qr" else "link"
        payments.append({
            "id": str(item.get("id") or "m_" + secrets.token_hex(4)),
            "method": method,
            "label": str(item.get("label") or method).strip(),
            "kind": kind,
            "value": value,
            "note": str(item.get("note") or "").strip(),
        })
    base["topup"]["payments"] = payments[:12]

    methods = [str(m).strip().lower() for m in (topup.get("allowed_methods") or [])]
    base["topup"]["allowed_methods"] = [m for m in methods if m in PAYMENT_METHODS][:8] or ["wechat", "alipay", "paypal"]

    base["models"] = normalize_model_pricing(raw.get("models"))
    base["enforce_balance"] = bool(raw.get("enforce_balance", True))
    base["auto_deduct"] = bool(raw.get("auto_deduct", True))
    base["updated_at"] = int(_num(raw.get("updated_at"), 0))
    return base


class CreditsStore:
    """积分设置 + 余额 + 流水 + 充值申请。线程安全（与 AuthStore 共用一把锁更简单）。"""

    def __init__(self, data_dir: str, auth_store):
        self.data_dir = data_dir
        self.auth = auth_store
        self._lock = threading.RLock()
        self.settings_file = os.path.join(data_dir, "credits_settings.json")
        self.topups_file = os.path.join(data_dir, "credits_topups.json")

    # ------------------------------------------------------------ JSON 读写
    def _read(self, path: str, default: Any) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _write(self, path: str, payload: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        last = None
        for attempt in range(4):
            try:
                os.replace(tmp, path)
                return
            except PermissionError as exc:
                last = exc
                time.sleep(0.05 * (attempt + 1))
        raise last  # type: ignore[misc]

    # ------------------------------------------------------------ 设置
    def settings(self) -> Dict[str, Any]:
        with self._lock:
            return normalize_settings(self._read(self.settings_file, {}))

    def save_settings(self, patch: Any) -> Dict[str, Any]:
        """整份覆盖保存（前端每次都提交完整表单，避免局部合并歧义）。"""
        with self._lock:
            current = self.settings()
            merged = dict(current)
            if isinstance(patch, dict):
                for key in ("rate", "signup", "topup", "models", "mail", "enforce_balance", "auto_deduct"):
                    if key in patch:
                        merged[key] = patch[key]
            merged["updated_at"] = int(time.time())
            clean = normalize_settings(merged)
            self._write(self.settings_file, clean)
            return clean

    def public_settings(self) -> Dict[str, Any]:
        """给普通成员看的：汇率、充值套餐、收款方式、是否记账扣费。"""
        s = self.settings()
        return {
            "rate": s["rate"],
            "presets": s["topup"]["presets"],
            "payments": s["topup"]["payments"],
            "allowed_methods": s["topup"]["allowed_methods"],
            "models": s["models"],
            "auto_deduct": s["auto_deduct"],
            "enforce_balance": s["enforce_balance"],
            "signup": {
                "require_email": s["signup"]["require_email"],
                "require_email_verify": s["signup"]["require_email_verify"],
                "email_verify_ready": s["signup"]["require_email_verify"] and bool(
                    s["mail"]["enabled"] and s["mail"]["host"]
                ),
            },
        }

    # ------------------------------------------------------------ 估算
    @staticmethod
    def _pricing_entry(models: Dict[str, Any], provider: str, model: str):
        """按「供应商::模型」取单价；老数据只有模型名时兼容回退（仅当该模型没配过供应商级单价）。"""
        model = str(model or "").strip()
        provider = str(provider or "").strip()
        if not model:
            return None
        if provider:
            entry = models.get(f"{provider}::{model}")
            if isinstance(entry, dict):
                return entry
            # 该模型已按供应商分别配置 ⇒ 不再共享裸模型名的单价
            if any(str(k).endswith("::" + model) for k in models):
                return None
        entry = models.get(model)
        return entry if isinstance(entry, dict) else None

    def estimate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """按模型单价估算积分。没配置该模型时 configured=False（前端不显示徽标）。"""
        settings = self.settings()
        model = str(payload.get("model") or "").strip()
        provider = str(payload.get("provider") or payload.get("provider_id") or "").strip()
        entry = self._pricing_entry(settings["models"], provider, model)
        if entry is None and not provider and "::" in model:
            # 前端把 "provider::model" 整串塞进 model 的老写法
            head, _, tail = model.partition("::")
            entry = self._pricing_entry(settings["models"], head, tail)
        if not isinstance(entry, dict):
            return {"configured": False, "credits": 0, "kind": "", "model": model, "provider": provider}

        kind = str(payload.get("kind") or entry.get("kind") or "").strip().lower()
        credits = 0.0
        detail: Dict[str, Any] = {}
        if kind == "llm":
            # 输入 / 缓存命中 / 输出 三段各自计价（老板 m22656）：给了 token 数就用真值，
            # 只给文本时按同一规则估算，绝不「照搬输入那一档」。
            input_tokens = max(0.0, _num(payload.get("input_tokens"))) or float(estimate_tokens(payload.get("input_text")))
            cache_tokens = max(0.0, _num(payload.get("cache_tokens"))) or float(estimate_tokens(payload.get("context_text")))
            output_tokens = (max(0.0, _num(payload.get("output_tokens")))
                             or max(0.0, _num(payload.get("max_tokens")))
                             or max(1.0, round(input_tokens / 2)))
            cache_price = _num(entry.get("cache")) or _num(entry.get("input"))
            credits = (input_tokens / 1_000_000.0 * _num(entry.get("input"))
                       + output_tokens / 1_000_000.0 * _num(entry.get("output"))
                       + cache_tokens / 1_000_000.0 * cache_price)
            detail = {"input_tokens": input_tokens, "output_tokens": output_tokens,
                      "cache_tokens": cache_tokens,
                      "input": entry.get("input", 0), "output": entry.get("output", 0),
                      "cache": cache_price}
        elif kind == "image":
            count = max(1.0, _num(payload.get("count"), 1.0))
            credits = entry.get("per_image", 0) * count
            detail = {"per_image": entry.get("per_image", 0), "count": count}
        elif kind == "video":
            seconds = max(0.0, _num(payload.get("seconds")))
            resolution = _video_price_tier(payload.get("resolution"))
            table = entry.get("per_second") or {}
            per_second = _num(table.get(resolution))
            if not per_second:
                per_second = _num(table.get("720p"))
            if not per_second and table:
                per_second = _num(next(iter(table.values())))
            credits = per_second * seconds
            detail = {"per_second": per_second, "seconds": seconds, "resolution": resolution}

        return {
            "configured": True,
            "kind": kind,
            "model": model,
            "provider": provider,
            "credits": _round(credits),
            "detail": detail,
        }

    # ------------------------------------------------------------ 余额与流水
    def _ledger_path(self, uid: str) -> str:
        return os.path.join(self.data_dir, "users", uid, "credits_ledger.json")

    def ledger(self, uid: str, limit: int = 100) -> List[Dict[str, Any]]:
        data = self._read(self._ledger_path(uid), {"entries": []})
        entries = data.get("entries") if isinstance(data, dict) else []
        if not isinstance(entries, list):
            return []
        return list(reversed(entries))[:max(1, int(limit))]

    def _append_ledger(self, uid: str, entry: Dict[str, Any]) -> None:
        path = self._ledger_path(uid)
        data = self._read(path, {"entries": []})
        entries = data.get("entries") if isinstance(data, dict) else []
        if not isinstance(entries, list):
            entries = []
        entries.append(entry)
        if len(entries) > LEDGER_LIMIT:
            entries = entries[-LEDGER_LIMIT:]
        self._write(path, {"entries": entries})

    def balance(self, uid: str) -> float:
        user = self.auth.find_by_id(uid)
        if not user:
            return 0.0
        return _round(user.get("credits", 0))

    def adjust(self, uid: str, delta: float, reason: str = "", actor: str = "", kind: str = "adjust") -> Dict[str, Any]:
        """加/减积分。delta 可为负；结果不小于 0（欠费不允许）。"""
        delta = _round(delta)
        with self._lock:
            user = self.auth.find_by_id(uid)
            if not user:
                raise ValueError("账号不存在")
            balance = max(0.0, _round(_num(user.get("credits")) + delta))
            self.auth.update_user(uid, {"credits": balance, "credits_updated_at": int(time.time())})
            entry = {
                "ts": int(time.time()),
                "delta": delta,
                "balance": balance,
                "reason": str(reason or ""),
                "kind": kind,
                "actor": actor or "",
            }
            self._append_ledger(uid, entry)
            return {"balance": balance, "delta": delta, "entry": entry}

    def spend(self, uid: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """按用量扣费（只有估算命中且 auto_deduct 才扣）。

        enforce_balance=True（默认）时：余额不够就拒绝，返回 blocked=True 且不扣款，
        由调用方回 402；费用为 0 或没配价的一律放行（老板 2026-11-13）。
        """
        settings = self.settings()
        if not settings.get("auto_deduct", True):
            return {"charged": False, "credits": 0, "reason": "auto_deduct_off"}
        est = self.estimate(payload)
        if not est.get("configured"):
            return {"charged": False, "credits": 0, "reason": "no_pricing"}
        amount = _round(est.get("credits"))
        if amount <= 0:
            return {"charged": False, "credits": 0, "reason": "zero"}
        balance = self.balance(uid)
        if balance < amount:
            if settings.get("enforce_balance", True):
                return {"charged": False, "blocked": True, "credits": amount,
                        "balance": balance, "reason": "insufficient"}
            return {"charged": False, "credits": amount, "balance": balance, "reason": "insufficient"}
        result = self.adjust(uid, -amount, reason=str(payload.get("reason") or "模型调用"),
                             actor=uid, kind="spend")
        return {"charged": True, "credits": amount, "balance": result["balance"], "reason": "ok"}

    def refund(self, uid: str, credits: float, reason: str = "任务失败退款") -> Dict[str, Any]:
        """把预扣的积分退回去（任务失败时用）。"""
        amount = _round(credits)
        if amount <= 0:
            return {"refunded": False, "credits": 0, "reason": "zero"}
        result = self.adjust(uid, amount, reason=reason, actor=uid, kind="refund")
        return {"refunded": True, "credits": amount, "balance": result["balance"], "reason": "ok"}

    # ------------------------------------------------------------ 充值申请
    def _topups(self) -> Dict[str, Any]:
        data = self._read(self.topups_file, {"requests": []})
        if not isinstance(data, dict):
            return {"requests": []}
        if not isinstance(data.get("requests"), list):
            data["requests"] = []
        return data

    def topup_create(self, uid: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        settings = self.settings()
        preset_id = str(payload.get("preset_id") or "").strip()
        preset = next((p for p in settings["topup"]["presets"] if p["id"] == preset_id), None)
        if not preset:
            raise ValueError("充值套餐不存在")
        method = str(payload.get("method") or "").strip().lower()
        if not method:
            raise ValueError("请选择支付方式")
        reference = str(payload.get("reference") or "").strip()[:200]
        with self._lock:
            user = self.auth.find_by_id(uid) or {}
            data = self._topups()
            req_id = "tp_" + secrets.token_hex(6)
            now = int(time.time())
            for r in data["requests"]:
                if r.get("uid") == uid and r.get("status") == "pending" and r.get("preset_id") == preset_id:
                    raise ValueError("同样的充值申请已经在等待管理员确认")
            entry = {
                "id": req_id,
                "uid": uid,
                "user_id": uid,
                "user_name": user.get("name", ""),
                "user_seq": user.get("seq"),
                "preset_id": preset_id,
                "preset_label": preset.get("label", ""),
                "credits": preset.get("credits", 0),
                "price_cny": preset.get("price_cny", 0),
                "price_usd": preset.get("price_usd", 0),
                "method": method,
                "reference": reference,
                "status": "pending",
                "created_at": now,
                "decided_at": 0,
                "decided_by": "",
                "note": "",
            }
            data["requests"].append(entry)
            if len(data["requests"]) > TOPUP_LIMIT:
                data["requests"] = data["requests"][-TOPUP_LIMIT:]
            self._write(self.topups_file, data)
            return entry

    def topup_list(self, uid: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        data = self._topups()
        items = data["requests"]
        if uid:
            items = [r for r in items if r.get("uid") == uid]
        picked = list(reversed(items))[:max(1, int(limit))]
        return [self._topup_with_user(r) for r in picked]

    def _topup_with_user(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """订单信息始终带用户 id / 名字 / 序号（老板 m16684）。

        优先取账号当前值（改名后订单跟着变）；账号已删时退回下单时的快照。
        """
        out = dict(req)
        rid = str(out.get("uid") or out.get("user_id") or "")
        out["user_id"] = rid
        user: Optional[Dict[str, Any]] = None
        if rid:
            try:
                user = self.auth.find_by_id(rid)
            except Exception:  # noqa: BLE001 - 账号库异常不该让订单列表整体失败
                user = None
        if isinstance(user, dict):
            out["user_name"] = str(user.get("name") or out.get("user_name") or "")
            out["user_seq"] = user.get("seq", out.get("user_seq"))
        else:
            out["user_name"] = str(out.get("user_name") or "")
            out["user_seq"] = out.get("user_seq")
        return out

    def topup_decide(self, request_id: str, approve: bool, actor: str = "", note: str = "") -> Dict[str, Any]:
        with self._lock:
            data = self._topups()
            hit = None
            for r in data["requests"]:
                if r.get("id") == request_id:
                    hit = r
                    break
            if not hit:
                raise ValueError("充值申请不存在")
            if hit.get("status") != "pending":
                raise ValueError("该申请已处理过")
            now = int(time.time())
            hit["decided_at"] = now
            hit["decided_by"] = actor
            hit["note"] = str(note or "")[:200]
            if approve:
                hit["status"] = "approved"
                self._write(self.topups_file, data)
                result = self.adjust(hit.get("uid", ""), _num(hit.get("credits")),
                                     reason=f"充值（{hit.get('preset_label') or hit.get('method')}）",
                                     actor=actor, kind="topup")
                return {"request": hit, "balance": result["balance"]}
            hit["status"] = "rejected"
            self._write(self.topups_file, data)
            return {"request": hit, "balance": self.balance(hit.get("uid", ""))}

    # ------------------------------------------------------------ 账号字段维护
    def ensure_user_fields(self) -> Dict[str, Any]:
        """给老账号补 seq 与 credits；顺序按 created_at 升序（首个注册者为 1 号）。"""
        users = self.auth.users()
        seqs = {u.get("seq") for u in users if isinstance(u.get("seq"), int) and u.get("seq", 0) > 0}
        next_seq = max(seqs) + 1 if seqs else 1
        settings = self.settings()
        changed = []
        ordered = sorted(users, key=lambda u: (_num(u.get("created_at")), str(u.get("id"))))
        for user in ordered:
            patch: Dict[str, Any] = {}
            seq = user.get("seq")
            if not isinstance(seq, int) or seq <= 0:
                while next_seq in seqs:
                    next_seq += 1
                patch["seq"] = next_seq
                seqs.add(next_seq)
                next_seq += 1
            if user.get("credits") is None:
                patch["credits"] = 0.0 if user.get("role") == "admin" else settings["signup"]["initial_credits"]
            if patch:
                self.auth.update_user(user.get("id", ""), patch)
                changed.append({"id": user.get("id"), **patch})
        return {"changed": changed, "count": len(changed)}

