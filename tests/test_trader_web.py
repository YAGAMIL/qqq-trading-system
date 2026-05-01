import json
from pathlib import Path
import tempfile
import unittest

from state_store import default_state, write_state
from trader_web import create_app


class TraderWebTests(unittest.TestCase):
    def test_dashboard_exposes_empty_trade_and_error_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = default_state()
            state["last_error"] = "Option price 0.41 exceeds max_option_price 0.15"
            write_state(state, root / "state.json")
            app = create_app(
                state_path=root / "state.json",
                records_dir=root / "records",
            )

            client = app.test_client()
            html = client.get("/").get_data(as_text=True)
            state_response = client.get("/api/state")
            trades_response = client.get("/api/trades")

        self.assertIn("最新错误", html)
        self.assertIn("暂无交易记录", html)
        self.assertIn("无需 token", html)
        self.assertEqual(state_response.status_code, 200)
        self.assertEqual(
            json.loads(state_response.get_data(as_text=True))["last_error"],
            "Option price 0.41 exceeds max_option_price 0.15",
        )
        self.assertEqual(trades_response.status_code, 200)
        self.assertEqual(json.loads(trades_response.get_data(as_text=True)), [])


if __name__ == "__main__":
    unittest.main()
