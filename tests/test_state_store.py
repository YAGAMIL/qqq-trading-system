from pathlib import Path
import tempfile
import unittest

from state_store import append_today_bar, default_state, read_state, record_trade, write_state


class StateStoreTests(unittest.TestCase):
    def test_write_and_read_default_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = default_state()
            state["candle_count"] = 3

            write_state(state, path)
            loaded = read_state(path)

            self.assertEqual(loaded["candle_count"], 3)
            self.assertIn("filters", loaded)
            self.assertIn("position", loaded)

    def test_append_today_bar_writes_csv_header_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "today.csv"
            append_today_bar(
                {
                    "timestamp": "2026-04-23T09:35:00-04:00",
                    "open": 100,
                    "high": 101,
                    "low": 99,
                    "close": 100.5,
                    "volume": 1000,
                },
                path,
            )
            append_today_bar(
                {
                    "timestamp": "2026-04-23T09:36:00-04:00",
                    "open": 100.5,
                    "high": 101.5,
                    "low": 100,
                    "close": 101,
                    "volume": 900,
                },
                path,
            )

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], "timestamp,open,high,low,close,volume")
            self.assertEqual(len(lines), 3)

    def test_record_trade_uses_trade_date_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            records_dir = Path(tmp) / "records"

            path = record_trade(
                {
                    "timestamp": "2026-04-23T10:00:00-04:00",
                    "symbol": "QQQ260423C432000.US",
                    "side": "Buy",
                    "quantity": 10,
                },
                records_dir,
            )

            self.assertEqual(path.name, "2026-04-23.json")
            self.assertTrue(path.exists())
            self.assertIn("QQQ260423C432000.US", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
