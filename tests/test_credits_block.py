"""积分「余额不足将拦截」的回归测试（老板 2026-11-13）。

规则：
  - 余额 < 本次费用 → spend() 返回 blocked=True 且不扣款（调用方回 402）；
  - 费用为 0 / 没配价 → 照常放行（"费用为0则依旧可以继续使用"）；
  - 显式关掉 enforce_balance → 退回旧的「记账不拦截」。
另外静态检查 main.py 里两处拦截落点还在。
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import credits as C  # noqa: E402


class StubAuth:
    def __init__(self):
        self.users = {"u1": {"id": "u1", "name": "tester", "credits": 0.0}}

    def find_by_id(self, uid):
        u = self.users.get(uid)
        return dict(u) if u else None

    def update_user(self, uid, patch):
        self.users[uid].update(patch)
        return dict(self.users[uid])


def make_store(tmp, balance, models, enforce=None):
    auth = StubAuth()
    auth.users["u1"]["credits"] = balance
    os.makedirs(os.path.join(tmp, "users", "u1"), exist_ok=True)
    settings = {"models": models}
    if enforce is not None:
        settings["enforce_balance"] = enforce
    with open(os.path.join(tmp, "credits_settings.json"), "w", encoding="utf-8") as fh:
        json.dump(settings, fh)
    return C.CreditsStore(tmp, auth), auth


def main():
    models = {"p::img": {"kind": "image", "per_image": 0.18}}
    tmp = tempfile.mkdtemp(prefix="credits-")
    try:
        # 1) 余额充足：正常扣
        store, auth = make_store(os.path.join(tmp, "a"), 10, models)
        os.makedirs(os.path.join(tmp, "a", "users", "u1"), exist_ok=True)
        r = store.spend("u1", {"model": "img", "provider": "p", "kind": "image", "count": 1})
        assert r["charged"] and r["credits"] == 0.18 and not r.get("blocked"), r
        assert abs(auth.users["u1"]["credits"] - 9.82) < 1e-9, auth.users["u1"]["credits"]

        # 2) 余额不足：拦截、不扣款、余额不变
        store, auth = make_store(os.path.join(tmp, "b"), 0.05, models)
        r = store.spend("u1", {"model": "img", "provider": "p", "kind": "image", "count": 1})
        assert r.get("blocked") and not r["charged"], r
        assert abs(auth.users["u1"]["credits"] - 0.05) < 1e-9, auth.users["u1"]["credits"]

        # 3) 费用为 0：余额 0 也放行
        free = {"p::free": {"kind": "image", "per_image": 0}}
        store, auth = make_store(os.path.join(tmp, "c"), 0, free)
        r = store.spend("u1", {"model": "free", "provider": "p", "kind": "image", "count": 1})
        assert not r["charged"] and r["reason"] == "zero" and not r.get("blocked"), r

        # 4) 没配价：照常放行
        store, auth = make_store(os.path.join(tmp, "d"), 0, {})
        r = store.spend("u1", {"model": "nope", "provider": "p", "kind": "image", "count": 1})
        assert r["reason"] == "no_pricing" and not r.get("blocked"), r

        # 5) 老配置文件里写死 enforce_balance=false（1.3.8 之前保存过设置的用户）：
        #    一次性迁移成 True —— 否则「更新后还是余额不足不拦截」（老板 2026-11-14 实测）。
        d5 = os.path.join(tmp, "e")
        store, auth = make_store(d5, 0.05, models, enforce=False)
        os.makedirs(os.path.join(d5, "users", "u1"), exist_ok=True)
        r = store.spend("u1", {"model": "img", "provider": "p", "kind": "image", "count": 1})
        assert r.get("blocked") and not r["charged"], r
        saved = json.load(open(os.path.join(d5, "credits_settings.json"), encoding="utf-8"))
        assert saved["enforce_balance"] is True and saved["enforce_balance_migrated"] is True, saved

        # 5b) 迁移之后管理员再手动关掉：按手动值走（不再被迁移翻回来）
        store.save_settings({"enforce_balance": False})
        r = store.spend("u1", {"model": "img", "provider": "p", "kind": "image", "count": 1})
        assert r["reason"] == "insufficient" and not r.get("blocked"), r
        assert store.settings()["enforce_balance"] is False

        # 6) 默认值就是拦截（老配置文件没有这个键）
        assert C.default_settings()["enforce_balance"] is True
        assert C.normalize_settings({})["enforce_balance"] is True

        main_py = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
        assert 'if _charge.get("blocked"):' in main_py
        assert 'status_code=402' in main_py
        assert "if _image_estimate.get(\"configured\"):" in main_py
        # 小抽AI 查余额/扣费必须用账号 id（session），不能用 IP 兜底的伪 id
        # —— 否则余额永远读成 0，富余额用户被误拦（老板 2026-11-13 实测）。
        assert "def credits_uid_for(request: Request" in main_py
        assert "_pre_balance = _credits_store.balance(_credit_uid)" in main_py
        assert "_credits_store.spend(_credit_uid, charge_payload)" in main_py
        assert "_credits_store.balance(user_id)" not in main_py

        print("OK credits-block")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
