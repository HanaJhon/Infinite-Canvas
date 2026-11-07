"""积分计费自检：python tools/check_credits.py（无框架、无网络、临时目录）。

覆盖：按供应商独立定价、预扣、退款、余额不足不扣。
"""
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import auth  # noqa: E402
import credits  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as tmp:
        store_dir = pathlib.Path(tmp)
        auth_store = auth.AuthStore(store_dir)
        user = auth_store.create_user("probe", "pw123456", role="member", credits=10.0)
        uid = user["id"]
        ledger = credits.CreditsStore(store_dir, auth_store)

        ledger.save_settings({"models": {
            "gpt-image": {"kind": "image", "per_image": 2},
            "pid_a::gpt-image": {"kind": "image", "per_image": 1},
            "pid_b::gpt-image": {"kind": "image", "per_image": 5},
            "pid_llm::gpt-llm": {"kind": "llm", "input": 2.0, "output": 8.0, "cache": 0.5},
            "pid_llm2::gpt-llm": {"kind": "llm", "input": 4.0, "output": 4.0},
        }})

        # 同一模型不同供应商必须各算各的
        est_a = ledger.estimate({"model": "gpt-image", "provider": "pid_a", "kind": "image", "count": 3})
        est_b = ledger.estimate({"model": "gpt-image", "provider": "pid_b", "kind": "image", "count": 1})
        assert est_a["credits"] == 3.0, est_a
        assert est_b["credits"] == 5.0, est_b

        # 预扣：先扣
        charged = ledger.spend(uid, {"model": "gpt-image", "provider": "pid_b", "kind": "image", "count": 1})
        assert charged["charged"] is True, charged
        assert charged["credits"] == 5.0, charged
        assert ledger.balance(uid) == 5.0, ledger.balance(uid)

        # 退款：失败后原路退回
        refunded = ledger.refund(uid, 5.0, "任务失败退款")
        assert refunded["refunded"] is True and refunded["credits"] == 5.0, refunded
        assert ledger.balance(uid) == 10.0, ledger.balance(uid)

        # 余额不够（enforce_balance=False）不扣
        spent = ledger.spend(uid, {"model": "gpt-image", "provider": "pid_b", "kind": "image", "count": 5})
        assert spent["charged"] is False and spent["reason"] == "insufficient", spent
        assert ledger.balance(uid) == 10.0, ledger.balance(uid)

        # LLM：输入 / 输出 / 缓存三段各按各的单价（老板 m22656）
        est_llm = ledger.estimate({"model": "gpt-llm", "provider": "pid_llm", "kind": "llm",
                                   "input_tokens": 1_000_000, "output_tokens": 1_000_000,
                                   "cache_tokens": 1_000_000})
        assert est_llm["credits"] == 10.5, est_llm          # 2 + 8 + 0.5
        assert est_llm["detail"]["cache"] == 0.5, est_llm

        # 缓存没单独配价时按输入价算，不能被当成 0
        est_nocache = ledger.estimate({"model": "gpt-llm", "provider": "pid_llm2", "kind": "llm",
                                       "input_tokens": 0, "output_tokens": 0, "cache_tokens": 1_000_000})
        assert est_nocache["credits"] == 4.0, est_nocache

        # 只给文本：按估算 token 算，中文 ≈1 token/字
        assert credits.estimate_tokens("你好世界") == 4
        assert credits.estimate_tokens("abcd") == 1
        est_text = ledger.estimate({"model": "gpt-llm", "provider": "pid_llm", "kind": "llm",
                                    "input_text": "你好世界", "context_text": "abcd" * 25})
        assert est_text["detail"]["input_tokens"] == 4, est_text
        assert est_text["detail"]["cache_tokens"] == 25, est_text
        est_long = ledger.estimate({"model": "gpt-llm", "provider": "pid_llm", "kind": "llm",
                                    "input_text": "你好世界" * 1000})
        assert est_long["detail"]["input_tokens"] == 4000, est_long
        assert est_long["credits"] > 0, est_long

        kinds = [e["kind"] for e in ledger._read(ledger._ledger_path(uid), {"entries": []})["entries"]]
        assert kinds[-1] == "refund", kinds
        # 视频：单价表只有 480p/720p/1080p，模型的 768p 必须落到 720p 档
        # （老板 2026-11-06：minimax-h3 768P × 10 秒显示 3 积分，实际应为 1.4）
        ledger.save_settings({"models": {
            "pid_v::minimax-h3": {"kind": "video",
                                  "per_second": {"1080p": 0.3, "720p": 0.14, "480p": 0.1}},
        }})
        est_768 = ledger.estimate({"model": "minimax-h3", "provider": "pid_v", "kind": "video",
                                   "seconds": 10, "resolution": "768P"})
        assert abs(est_768["credits"] - 1.4) < 1e-9, est_768
        est_1080 = ledger.estimate({"model": "minimax-h3", "provider": "pid_v", "kind": "video",
                                    "seconds": 10, "resolution": "1080p"})
        assert abs(est_1080["credits"] - 3.0) < 1e-9, est_1080
        est_2k = ledger.estimate({"model": "minimax-h3", "provider": "pid_v", "kind": "video",
                                  "seconds": 10, "resolution": "2k"})
        assert abs(est_2k["credits"] - 3.0) < 1e-9, est_2k

        print("CREDITS_CHECK=OK")


if __name__ == "__main__":
    main()
