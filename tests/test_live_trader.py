from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from live_trader import BarBuilder, DrySubmitBroker, LiveTrader, QuoteSnapshot, live_trading_allowed
from tests.test_strategy import bar


class LiveTradingGuardTests(unittest.TestCase):
    def test_live_mode_requires_flag_and_environment_opt_in(self):
        self.assertFalse(live_trading_allowed(False, {"QQQ_LIVE_TRADING": "1"}))
        self.assertFalse(live_trading_allowed(True, {}))
        self.assertFalse(live_trading_allowed(True, {"QQQ_LIVE_TRADING": "true"}))
        self.assertTrue(live_trading_allowed(True, {"QQQ_LIVE_TRADING": "1"}))


class FakeQuoteBroker:
    def __init__(self):
        self.submits = []

    def quote_stock(self, symbol):
        return QuoteSnapshot(symbol, 100.0, 1000)

    def quote_option(self, symbol):
        return QuoteSnapshot(symbol, 1.25, 10)

    def submit_option_order(self, symbol, side, quantity, limit_price=None):
        self.submits.append((symbol, side, quantity, limit_price))
        return {"order_id": "real-order"}


class DrySubmitBrokerTests(unittest.TestCase):
    def test_delegates_quotes_but_never_calls_submit(self):
        real = FakeQuoteBroker()
        broker = DrySubmitBroker(real)

        self.assertEqual(broker.quote_stock("QQQ.US").price, 100.0)
        self.assertEqual(broker.quote_option("QQQ260423C432000.US").price, 1.25)
        order = broker.submit_option_order("QQQ260423C432000.US", "Buy", 10, 1.25)

        self.assertEqual(real.submits, [])
        self.assertTrue(order["dry_run"])
        self.assertTrue(order["dry_submit"])
        self.assertEqual(order["side"], "Buy")

    def test_live_trader_records_dry_submit_order_without_real_submit(self):
        real = FakeQuoteBroker()
        broker = DrySubmitBroker(real)
        cfg = {
            "symbol": "QQQ.US",
            "sl": 0.25,
            "tp": 0.30,
            "lookback": 5,
            "tp_partial_pct": 1.00,
            "tp_trail_drop": 0.30,
            "option_offset": 2.0,
            "min_contracts": 1,
            "contract_multiplier": 100,
            "pos_pct": 2,
            "max_trades": 8,
            "daily_limit": 5,
            "start_time": "09:35",
            "end_time": "15:50",
            "trail_activate": 0.10,
            "trail_drop": 0.05,
            "max_gap": 0.0020,
            "vol_mult": 0.8,
            "min_body": 0.0003,
            "reversal_drop": 0.002,
            "reversal_bounce": 0.001,
            "check_interval": 20,
            "capital": 100000,
            "max_contracts": 1,
            "max_hold_bars": 15,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trader = LiveTrader(
                broker=broker,
                config=cfg,
                state_path=root / "state.json",
                today_path=root / "today.csv",
                records_dir=root / "records",
                live=True,
                dry_submit=True,
            )
            trader.initialize_state(running=False)
            for candle in [
                bar(99.0, 100.0, 98.8, 99.5, minute=35),
                bar(99.4, 100.1, 99.1, 99.8, minute=36),
                bar(99.7, 100.2, 99.5, 100.0, minute=37),
                bar(100.0, 100.3, 99.8, 100.1, minute=38),
                bar(100.1, 100.4, 99.9, 100.2, minute=39),
                bar(100.3, 100.8, 100.2, 100.55, volume=900, minute=40),
            ]:
                trader.process_bar(candle)

            record_files = list((root / "records").glob("*.json"))
            self.assertEqual(len(record_files), 1)
            records = json.loads(record_files[0].read_text(encoding="utf-8"))

        self.assertEqual(real.submits, [])
        self.assertEqual(trader.state["mode"], "live-dry-submit")
        self.assertEqual(trader.state["config"]["max_contracts"], 1)
        self.assertEqual(records[0]["quantity"], 1)
        self.assertTrue(records[0]["order"]["dry_submit"])

    def test_live_trader_does_not_open_before_entry_window(self):
        real = FakeQuoteBroker()
        broker = DrySubmitBroker(real)
        cfg = {
            "symbol": "QQQ.US",
            "sl": 0.25,
            "tp": 0.30,
            "lookback": 5,
            "tp_partial_pct": 1.00,
            "tp_trail_drop": 0.30,
            "option_offset": 2.0,
            "min_contracts": 1,
            "contract_multiplier": 100,
            "pos_pct": 2,
            "max_trades": 1,
            "daily_limit": 5,
            "start_time": "09:35",
            "end_time": "15:50",
            "trail_activate": 0.10,
            "trail_drop": 0.05,
            "max_gap": 0.0020,
            "vol_mult": 0.8,
            "min_body": 0.0003,
            "reversal_drop": 0.002,
            "reversal_bounce": 0.001,
            "check_interval": 20,
            "capital": 100000,
            "max_contracts": 1,
            "max_hold_bars": 15,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trader = LiveTrader(
                broker=broker,
                config=cfg,
                state_path=root / "state.json",
                today_path=root / "today.csv",
                records_dir=root / "records",
                live=True,
                dry_submit=True,
            )
            trader.initialize_state(running=False)
            for candle in [
                bar(99.0, 100.0, 98.8, 99.5, minute=0),
                bar(99.4, 100.1, 99.1, 99.8, minute=1),
                bar(99.7, 100.2, 99.5, 100.0, minute=2),
                bar(100.0, 100.3, 99.8, 100.1, minute=3),
                bar(100.1, 100.4, 99.9, 100.2, minute=4),
                bar(100.3, 100.8, 100.2, 100.55, volume=900, minute=5),
            ]:
                trader.process_bar(candle)

            self.assertFalse((root / "records").exists())

        self.assertEqual(real.submits, [])
        self.assertIsNone(trader.state["position"])

    def test_live_trader_skips_order_above_option_price_cap(self):
        real = FakeQuoteBroker()
        broker = DrySubmitBroker(real)
        cfg = {
            "symbol": "QQQ.US",
            "sl": 0.25,
            "tp": 0.30,
            "lookback": 5,
            "tp_partial_pct": 1.00,
            "tp_trail_drop": 0.30,
            "option_offset": 2.0,
            "max_option_price": 1.0,
            "min_contracts": 1,
            "contract_multiplier": 100,
            "pos_pct": 2,
            "max_trades": 1,
            "daily_limit": 5,
            "start_time": "09:35",
            "end_time": "15:50",
            "trail_activate": 0.10,
            "trail_drop": 0.05,
            "max_gap": 0.0020,
            "vol_mult": 0.8,
            "min_body": 0.0003,
            "reversal_drop": 0.002,
            "reversal_bounce": 0.001,
            "check_interval": 20,
            "capital": 100000,
            "max_contracts": 1,
            "max_hold_bars": 15,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trader = LiveTrader(
                broker=broker,
                config=cfg,
                state_path=root / "state.json",
                today_path=root / "today.csv",
                records_dir=root / "records",
                live=True,
                dry_submit=True,
            )
            trader.initialize_state(running=False)
            for candle in [
                bar(99.0, 100.0, 98.8, 99.5, minute=35),
                bar(99.4, 100.1, 99.1, 99.8, minute=36),
                bar(99.7, 100.2, 99.5, 100.0, minute=37),
                bar(100.0, 100.3, 99.8, 100.1, minute=38),
                bar(100.1, 100.4, 99.9, 100.2, minute=39),
                bar(100.3, 100.8, 100.2, 100.55, volume=900, minute=40),
            ]:
                trader.process_bar(candle)

            self.assertFalse((root / "records").exists())

        self.assertEqual(real.submits, [])
        self.assertIn("exceeds max_option_price", trader.state["last_error"])


class BarBuilderTests(unittest.TestCase):
    def test_confirms_bar_when_minute_changes(self):
        tz = ZoneInfo("America/New_York")
        builder = BarBuilder()
        self.assertIsNone(builder.update(100.0, 1000, datetime(2026, 4, 23, 9, 35, tzinfo=tz)))
        closed = builder.update(101.0, 1200, datetime(2026, 4, 23, 9, 36, tzinfo=tz))

        self.assertIsNotNone(closed)
        self.assertEqual(closed["open"], 100.0)
        self.assertEqual(closed["high"], 100.0)
        self.assertEqual(closed["low"], 100.0)
        self.assertEqual(closed["close"], 100.0)
        self.assertEqual(closed["volume"], 1000)

    def test_updates_open_bar_high_low_close(self):
        tz = ZoneInfo("America/New_York")
        builder = BarBuilder()
        builder.update(100.0, 1000, datetime(2026, 4, 23, 9, 35, tzinfo=tz))
        self.assertIsNone(builder.update(101.0, 1100, datetime(2026, 4, 23, 9, 35, 20, tzinfo=tz)))
        self.assertIsNone(builder.update(99.5, 1200, datetime(2026, 4, 23, 9, 35, 40, tzinfo=tz)))
        closed = builder.close_current()

        self.assertEqual(closed["open"], 100.0)
        self.assertEqual(closed["high"], 101.0)
        self.assertEqual(closed["low"], 99.5)
        self.assertEqual(closed["close"], 99.5)
        self.assertEqual(closed["volume"], 1200)


if __name__ == "__main__":
    unittest.main()
