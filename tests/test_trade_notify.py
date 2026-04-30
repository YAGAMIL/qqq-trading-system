import unittest
from unittest.mock import patch

from trade_notify import format_trade_message, send_hermes_message


class TradeNotifyTests(unittest.TestCase):
    def test_formats_buy_message_as_dry_submit(self):
        message = format_trade_message(
            {
                "timestamp": "2026-04-28T12:47:03-04:00",
                "symbol": "QQQ260428C657000.US",
                "side": "Buy",
                "quantity": 1,
                "price": 0.40,
                "mode": "live-dry-submit",
                "order": {"dry_submit": True},
                "signal": {"kind": "breakout", "direction": "call"},
            }
        )

        self.assertIn("模拟成交：买入", message)
        self.assertIn("真实行情 + 模拟下单", message)
        self.assertIn("信号：突破 看涨 Call", message)

    def test_formats_sell_message_with_profit_percent(self):
        message = format_trade_message(
            {
                "timestamp": "2026-04-28T13:02:09-04:00",
                "symbol": "QQQ260428C657000.US",
                "side": "Sell",
                "quantity": 1,
                "price": 0.55,
                "pnl": 15.0,
                "pnl_pct": 0.375,
                "reason": "timeout",
                "mode": "live-dry-submit",
                "order": {"dry_submit": True},
            }
        )

        self.assertIn("模拟成交：卖出", message)
        self.assertIn("盈亏：+$15.00", message)
        self.assertIn("收益率：+37.50%", message)
        self.assertIn("原因：持仓超时", message)

    def test_send_hermes_uses_venv_python_and_minimal_payload(self):
        class Result:
            returncode = 0
            stdout = '{"ok": true}'
            stderr = ""

        with patch("trade_notify.subprocess.run", return_value=Result()) as run:
            result = send_hermes_message("weixin", "hello", timeout=3)

        self.assertTrue(result["ok"])
        command = run.call_args.kwargs["args"] if "args" in run.call_args.kwargs else run.call_args.args[0]
        self.assertIn("venv/bin/python", command[-1])
        self.assertIn("/root/.hermes/.env", command[-1])
        self.assertEqual(run.call_args.kwargs["timeout"], 3)
        self.assertIn('"target": "weixin"', run.call_args.kwargs["input"])
        self.assertNotIn('"action"', run.call_args.kwargs["input"])


if __name__ == "__main__":
    unittest.main()
