"""账号与会话（2026-10-27 新增）

局域网多人使用时，每个人要有独立的画布 / Agent 记录 / 个人资产库；
工作流库与团队资产库是共享的。

设计要点：
- 用户表存在 `data/users.json`，密码用 `hashlib.scrypt` 加盐哈希（标准库，不引依赖）。
- 会话用 HttpOnly Cookie `ic_session`，令牌映射存 `data/sessions.json`，
  服务重启后仍然有效（比内存会话更适合「局域网多设备」场景）。
- 首个注册的用户自动成为 admin，并**接管**现有 data/ 下的画布与 Agent 记录
  （见 `claim_legacy_data()`）——老板选的方案。
- 用 `contextvars` 传递当前用户，异步并发下安全（不能用全局变量）。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from typing import Any, Dict, Optional

# ---------------------------------------------------------------- 常量

SESSION_COOKIE = "ic_session"
SESSION_TTL = 60 * 60 * 24 * 30          # 30 天
MIN_PASSWORD_LEN = 6
USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5-]{2,24}$")

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1


# ---------------------------------------------------------------- 密码

def hash_password(password: str) -> str:
    """返回 `scrypt$N$r$p$salt_hex$hash_hex`。"""
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p), dklen=len(hash_hex) // 2)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ---------------------------------------------------------------- 存储

class AuthStore:
    """用户表 + 会话表的读写（JSON 文件 + 进程内锁）。"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.users_file = os.path.join(data_dir, "users.json")
        self.sessions_file = os.path.join(data_dir, "sessions.json")
        self._lock = threading.RLock()

    # -- 基础读写
    def _read_json(self, path: str, default: Any) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _write_json(self, path: str, payload: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        # 🚨 Windows 上 os.replace 会被「瞬时占用」打回 WinError 5（杀毒/索引/另一个进程正在读）——
        #    实测过一次登录因此 500。这里做 4 次短重试，仍失败才抛。
        last = None
        for attempt in range(4):
            try:
                os.replace(tmp, path)
                return
            except PermissionError as exc:   # WinError 5 / sharing violation
                last = exc
                time.sleep(0.05 * (attempt + 1))
        raise last  # type: ignore[misc]

    # -- 用户
    def users(self) -> list:
        with self._lock:
            return self._read_json(self.users_file, {"users": []}).get("users", [])

    def has_any_user(self) -> bool:
        return len(self.users()) > 0

    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        low = (name or "").strip().lower()
        for u in self.users():
            if str(u.get("name", "")).lower() == low:
                return u
        return None

    def find_by_id(self, uid: str) -> Optional[Dict[str, Any]]:
        for u in self.users():
            if u.get("id") == uid:
                return u
        return None

    def create_user(self, name: str, password: str, role: str = "member") -> Dict[str, Any]:
        name = (name or "").strip()
        if not USERNAME_RE.match(name):
            raise ValueError("用户名只能包含中英文、数字、下划线和短横线，长度 2-24")
        if len(password or "") < MIN_PASSWORD_LEN:
            raise ValueError(f"密码至少 {MIN_PASSWORD_LEN} 位")
        with self._lock:
            data = self._read_json(self.users_file, {"users": []})
            users = data.setdefault("users", [])
            if any(str(u.get("name", "")).lower() == name.lower() for u in users):
                raise ValueError("用户名已存在")
            user = {
                "id": "u_" + secrets.token_hex(8),
                "name": name,
                "pw": hash_password(password),
                "role": role,
                "created_at": int(time.time()),
            }
            users.append(user)
            self._write_json(self.users_file, data)
            return user

    def delete_user(self, uid: str) -> bool:
        with self._lock:
            data = self._read_json(self.users_file, {"users": []})
            before = len(data.get("users", []))
            data["users"] = [u for u in data.get("users", []) if u.get("id") != uid]
            if len(data["users"]) == before:
                return False
            self._write_json(self.users_file, data)
            return True

    def set_password(self, uid: str, password: str) -> bool:
        if len(password or "") < MIN_PASSWORD_LEN:
            raise ValueError(f"密码至少 {MIN_PASSWORD_LEN} 位")
        with self._lock:
            data = self._read_json(self.users_file, {"users": []})
            hit = None
            for u in data.get("users", []):
                if u.get("id") == uid:
                    u["pw"] = hash_password(password)
                    hit = u
                    break
            if not hit:
                return False
            self._write_json(self.users_file, data)
            return True

    # -- 会话
    def _sessions(self) -> Dict[str, Dict[str, Any]]:
        return self._read_json(self.sessions_file, {})

    def create_session(self, uid: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            s = self._sessions()
            now = int(time.time())
            # 顺手清掉过期会话，避免文件无限增长
            s = {k: v for k, v in s.items() if int(v.get("expires_at", 0)) > now}
            s[token] = {"uid": uid, "created_at": now, "expires_at": now + SESSION_TTL}
            self._write_json(self.sessions_file, s)
        return token

    def session_user(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        s = self._sessions()
        rec = s.get(token)
        if not rec:
            return None
        if int(rec.get("expires_at", 0)) <= int(time.time()):
            self.drop_session(token)
            return None
        return self.find_by_id(rec.get("uid", ""))

    def drop_session(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            s = self._sessions()
            if token in s:
                s.pop(token, None)
                self._write_json(self.sessions_file, s)

    def drop_user_sessions(self, uid: str) -> None:
        with self._lock:
            s = self._sessions()
            s = {k: v for k, v in s.items() if v.get("uid") != uid}
            self._write_json(self.sessions_file, s)


# ---------------------------------------------------------------- 用户数据目录

def user_data_dir(data_dir: str, uid: str) -> str:
    return os.path.join(data_dir, "users", uid)


def ensure_user_dirs(data_dir: str, uid: str) -> str:
    base = user_data_dir(data_dir, uid)
    for sub in ("canvases", "conversations", "media_previews"):
        os.makedirs(os.path.join(base, sub), exist_ok=True)
    return base


# ---------------------------------------------------------------- 存量数据接管

#: 首次注册时从 data/ 迁移到 data/users/<uid>/ 的条目（目录或文件）。
#: ⚠️ 只搬「属于个人」的东西：画布、会话记录、Agent 记忆、个人资产库、项目、提示词库。
#:    workflows/ 与团队资产库是共享的，**不搬**。
LEGACY_MOVE_ITEMS = (
    "canvases",
    "conversations",
    "media_previews",
    "agent_profile.json",
    "asset_library.json",
    "projects.json",
    "prompt_libraries.json",
    "agent_tools.json",
)


def claim_legacy_data(data_dir: str, uid: str) -> Dict[str, Any]:
    """把现有 data/ 下的个人数据搬到首个账号目录。

    只在「此前一个用户都没有」时调用一次。搬不动的（被占用等）记进 errors，不中断。
    """
    import shutil

    dest_root = ensure_user_dirs(data_dir, uid)
    moved, skipped, errors = [], [], []
    for item in LEGACY_MOVE_ITEMS:
        src = os.path.join(data_dir, item)
        dst = os.path.join(dest_root, item)
        if not os.path.exists(src):
            continue

        # 🚨 ensure_user_dirs() 已经建好 canvases/ conversations/ media_previews/ 空目录，
        #    所以这里不能因为「dst 存在」就跳过——要按目录逐项搬内容。
        if os.path.isdir(src):
            os.makedirs(dst, exist_ok=True)
            moved_any = False
            for name in os.listdir(src):
                s_item = os.path.join(src, name)
                d_item = os.path.join(dst, name)
                if os.path.exists(d_item):
                    skipped.append(f"{item}/{name}")
                    continue
                try:
                    shutil.move(s_item, d_item)
                    moved_any = True
                except Exception as exc:
                    errors.append(f"{item}/{name}: {exc}")
            if moved_any:
                moved.append(item)
            continue

        # 文件：目标已存在则跳过
        if os.path.exists(dst):
            skipped.append(item)
            continue
        try:
            shutil.move(src, dst)
            moved.append(item)
        except Exception as exc:                      # 被占用 / 跨盘等
            errors.append(f"{item}: {exc}")
    return {"moved": moved, "skipped": skipped, "errors": errors}
