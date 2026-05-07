from datetime import date
from pathlib import Path
import tempfile
import unittest

from state_store import (
    append_bar_db,
    append_today_bar,
    default_state,
    load_bars_db,
    load_today_bars,
    load_trade_records_db,
    read_state,
    read_state_db,
    record_trade,
    record_trade_db,
    upsert_broker_orders_db,
    write_state,
    write_state_db,
)


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

    def test_append_today_bar_rotates_to_new_trading_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "today.csv"
            append_today_bar(
                {
                    "timestamp": "2026-05-01T15:59:00-04:00",
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
                    "timestamp": "2026-05-04T09:35:00-04:00",
                    "open": 102,
                    "high": 103,
                    "low": 101,
                    "close": 102.5,
                    "volume": 200,
                },
                path,
            )

            rows = load_today_bars(path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timestamp"], "2026-05-04T09:35:00-04:00")

    def test_load_today_bars_filters_trading_day_and_regular_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "today.csv"
            path.write_text(
                "\n".join(
                    [
                        "timestamp,open,high,low,close,volume",
                        "2026-05-01T15:59:00-04:00,100,101,99,100.5,1000",
                        "2026-05-04T08:07:00-04:00,101,101,100,100.5,100",
                        "2026-05-04T09:35:00-04:00,102,103,101,102.5,200",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            rows = load_today_bars(
                path,
                trading_date=date(2026, 5, 4),
                regular_session_only=True,
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["timestamp"], "2026-05-04T09:35:00-04:00")

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

    def test_sqlite_persists_state_bars_trades_and_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "trading_state.db"
            state = default_state()
            state["running"] = True
            state["candle_count"] = 1

            write_state_db(state, db_path)
            append_bar_db(
                {
                    "timestamp": "2026-05-04T09:35:00-04:00",
                    "open": 102,
                    "high": 103,
                    "low": 101,
                    "close": 102.5,
                    "volume": 200,
                },
                db_path,
            )
            trade_id = record_trade_db(
                {
                    "timestamp": "2026-05-04T09:36:00-04:00",
                    "symbol": "QQQ260504C104000.US",
                    "side": "Buy",
                    "quantity": 1,
                    "longbridge_order_id": "order-1",
                },
                db_path,
            )
            upsert_broker_orders_db(
                [
                    {
                        "order_id": "order-1",
                        "symbol": "QQQ260504C104000.US",
                        "side": "Buy",
                        "status": "Filled",
                    }
                ],
                db_path,
            )

            loaded_state = read_state_db(db_path)
            bars = load_bars_db(db_path)
            trades = load_trade_records_db(db_path)

        self.assertEqual(loaded_state["candle_count"], 1)
        self.assertTrue(loaded_state["running"])
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]["close"], 102.5)
        self.assertGreater(trade_id, 0)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["longbridge_order_id"], "order-1")


if __name__ == "__main__":
    unittest.main()
