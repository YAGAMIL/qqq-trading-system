import unittest

from trade_notify import format_trade_message


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


if __name__ == "__main__":
    unittest.main()
