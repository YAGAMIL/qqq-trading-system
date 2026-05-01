from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from qqq_strategy import (
    PositionState,
    contracts_for_capital,
    evaluate_breakout_signal,
    evaluate_exit,
    get_option_symbol,
)
from trading_config import CONFIG


def bar(open_, high, low, close, volume=1000, minute=0):
    return {
        "timestamp": f"2026-04-23T09:{minute:02d}:00-04:00",
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


class OptionSymbolTests(unittest.TestCase):
    def test_uses_eastern_date_and_integer_strike(self):
        now = datetime(2026, 4, 23, 15, 45, tzinfo=ZoneInfo("America/New_York"))

        self.assertEqual(
            get_option_symbol(430.20, "call", offset=2.0, now=now),
            "QQQ260423C432000.US",
        )
        self.assertEqual(
            get_option_symbol(430.20, "put", offset=2.0, now=now),
            "QQQ260423P428000.US",
        )


class BreakoutSignalTests(unittest.TestCase):
    def test_breakout_uses_previous_lookback_window_not_current_bar(self):
        cfg = dict(CONFIG, lookback=5, vol_mult=0.8, min_body=0.0003, max_gap=0.002)
        candles = [
            bar(99.0, 100.0, 98.8, 99.5, minute=0),
            bar(99.4, 100.1, 99.1, 99.8, minute=1),
            bar(99.7, 100.2, 99.5, 100.0, minute=2),
            bar(100.0, 100.3, 99.8, 100.1, minute=3),
            bar(100.1, 100.4, 99.9, 100.2, minute=4),
            bar(100.3, 100.8, 100.2, 100.55, volume=900, minute=5),
        ]

        signal = evaluate_breakout_signal(candles, cfg)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "call")
        self.assertAlmostEqual(signal.reference_price, 100.4)
        self.assertTrue(all(signal.filters.values()))

    def test_current_bar_high_alone_does_not_create_breakout(self):
        cfg = dict(CONFIG, lookback=5, vol_mult=0.8, min_body=0.0003, max_gap=0.002)
        candles = [
            bar(99.0, 100.0, 98.8, 99.5, minute=0),
            bar(99.4, 100.1, 99.1, 99.8, minute=1),
            bar(99.7, 100.2, 99.5, 100.0, minute=2),
            bar(100.0, 100.3, 99.8, 100.1, minute=3),
            bar(100.1, 100.4, 99.9, 100.2, minute=4),
            bar(100.2, 100.8, 100.0, 100.35, volume=900, minute=5),
        ]

        signal = evaluate_breakout_signal(candles, cfg)

        self.assertIsNone(signal)


class ExitDecisionTests(unittest.TestCase):
    def test_stop_loss_closes_full_position(self):
        position = PositionState(
            option_symbol="QQQ260423C432000.US",
            direction="call",
            quantity=10,
            entry_opt_price=1.00,
            entry_stock_price=430.0,
            opened_bar_index=3,
        )

        decision = evaluate_exit(position, option_price=0.74, bar_index=4, config=CONFIG)

        self.assertEqual(decision.action, "full")
        self.assertEqual(decision.reason, "stop_loss")

    def test_partial_profit_then_trailing_exit(self):
        position = PositionState(
            option_symbol="QQQ260423C432000.US",
            direction="call",
            quantity=10,
            entry_opt_price=1.00,
            entry_stock_price=430.0,
            opened_bar_index=3,
        )

        first = evaluate_exit(position, option_price=2.05, bar_index=5, config=CONFIG)
        self.assertEqual(first.action, "partial")
        self.assertEqual(position.remaining_quantity, 5)
        self.assertTrue(position.partial_taken)

        hold = evaluate_exit(position, option_price=2.30, bar_index=6, config=CONFIG)
        self.assertEqual(hold.action, "hold")

        trail = evaluate_exit(position, option_price=1.95, bar_index=7, config=CONFIG)
        self.assertEqual(trail.action, "full")
        self.assertEqual(trail.reason, "trailing_take_profit")


class PositionSizingTests(unittest.TestCase):
    def test_does_not_force_min_contracts_when_budget_is_too_small(self):
        contracts = contracts_for_capital(
            option_price=1.0,
            capital=10000,
            pos_pct=2,
            min_contracts=10,
            contract_multiplier=100,
        )

        self.assertEqual(contracts, 0)

    def test_caps_contracts_for_small_live_smoke_orders(self):
        contracts = contracts_for_capital(
            option_price=0.50,
            capital=100000,
            pos_pct=2,
            min_contracts=1,
            contract_multiplier=100,
            max_contracts=1,
        )

        self.assertEqual(contracts, 1)


if __name__ == "__main__":
    unittest.main()
