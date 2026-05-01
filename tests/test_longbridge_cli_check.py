import unittest

from longbridge_cli_check import _summarize


class LongbridgeCliCheckTests(unittest.TestCase):
    def test_summarize_redacts_portfolio_values_and_counts_read_only_state(self):
        summary = _summarize(
            cli_path="longbridge",
            symbol="QQQ.US",
            check={
                "session": {"token": "valid"},
                "connectivity": {"global": {"ok": True}, "cn": {"ok": False}},
            },
            quote=[{"symbol": "QQQ.US", "last": "664.23", "status": "Normal"}],
            positions=[{"symbol": "MSFT.US"}, {"symbol": "QQQ.US"}],
            portfolio={
                "overview": {
                    "currency": "USD",
                    "risk_level": 0,
                    "total_asset": "100000",
                },
                "holdings": [{"symbol": "MSFT.US"}],
            },
        )

        self.assertTrue(summary["read_only"])
        self.assertTrue(summary["connectivity"]["global"])
        self.assertFalse(summary["connectivity"]["cn"])
        self.assertEqual(summary["quote"]["last"], 664.23)
        self.assertEqual(summary["account"]["positions"], 2)
        self.assertEqual(summary["account"]["portfolio_holdings"], 1)
        self.assertNotIn("total_asset", summary["account"])


if __name__ == "__main__":
    unittest.main()
