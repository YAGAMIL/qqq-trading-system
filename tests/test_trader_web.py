import json
from pathlib import Path
import tempfile
import unittest

from state_store import default_state, record_trade_db, write_state, write_state_db
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
        self.assertIn("运行校验", html)
        self.assertIn("美东时间 / 北京时间", html)
        self.assertIn("长桥订单号", html)
        self.assertIn("订单状态", html)
        self.assertEqual(state_response.status_code, 200)
        self.assertEqual(
            json.loads(state_response.get_data(as_text=True))["last_error"],
            "Option price 0.41 exceeds max_option_price 0.15",
        )
        self.assertEqual(trades_response.status_code, 200)
        self.assertEqual(json.loads(trades_response.get_data(as_text=True)), [])

    def test_api_state_marks_running_state_stale_when_live_lock_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = default_state()
            state["running"] = True
            write_state(state, root / "state.json")
            app = create_app(
                state_path=root / "state.json",
                records_dir=root / "records",
                lock_path=root / ".live_trader.lock",
                process_checker=lambda pid: False,
            )

            response = app.test_client().get("/api/state")
            payload = json.loads(response.get_data(as_text=True))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["engine_reported_running"])
        self.assertFalse(payload["running"])
        self.assertTrue(payload["runtime_status"]["stale_running_state"])
        self.assertIn("state.json reports running=true", payload["runtime_warning"])

    def test_api_reads_sqlite_state_and_trades_when_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "trading_state.db"
            state = default_state()
            state["last_error"] = "sqlite-state"
            write_state_db(state, db_path)
            record_trade_db(
                {
                    "timestamp": "2026-05-04T09:36:00-04:00",
                    "symbol": "QQQ260504C104000.US",
                    "side": "Buy",
                    "quantity": 1,
                },
                db_path,
            )
            app = create_app(
                state_path=root / "state.json",
                records_dir=root / "records",
                lock_path=root / ".live_trader.lock",
                db_path=db_path,
            )

            client = app.test_client()
            state_payload = json.loads(client.get("/api/state").get_data(as_text=True))
            trades_payload = json.loads(client.get("/api/trades").get_data(as_text=True))

        self.assertEqual(state_payload["last_error"], "sqlite-state")
        self.assertEqual(len(trades_payload), 1)
        self.assertEqual(trades_payload[0]["symbol"], "QQQ260504C104000.US")


if __name__ == "__main__":
    unittest.main()
