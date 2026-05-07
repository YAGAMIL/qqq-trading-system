import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from longbridge_client import LongbridgeBroker


class FakeQuoteContext:
    def __init__(self, quotes):
        self.quotes = quotes

    def quote(self, symbols):
        return self.quotes.get(symbols[0], [])


class LongbridgeBrokerQuoteTests(unittest.TestCase):
    def test_quote_option_reports_missing_symbol_clearly(self):
        broker = object.__new__(LongbridgeBroker)
        broker.quote_ctx = FakeQuoteContext({})

        with self.assertRaisesRegex(LookupError, "Longbridge returned no quote for QQQ260503C676000.US"):
            broker.quote_option("QQQ260503C676000.US")

    def test_quote_stock_returns_snapshot(self):
        broker = object.__new__(LongbridgeBroker)
        broker.quote_ctx = FakeQuoteContext(
            {
                "QQQ.US": [
                    SimpleNamespace(
                        last_done="674.15",
                        volume="39172607",
                    )
                ]
            }
        )

        quote = broker.quote_stock("QQQ.US")

        self.assertEqual(quote.symbol, "QQQ.US")
        self.assertEqual(quote.price, 674.15)
        self.assertEqual(quote.volume, 39172607.0)


class FakeTradeContext:
    def __init__(self):
        self.submitted = None
        self.detail_calls = 0

    def submit_order(self, **kwargs):
        self.submitted = kwargs
        return SimpleNamespace(order_id="709043056541253632")

    def order_detail(self, order_id):
        self.detail_calls += 1
        return SimpleNamespace(
            order_id=order_id,
            symbol="QQQ260503C676000.US",
            order_type="MO",
            side="Buy",
            status="Filled",
            submitted_quantity=Decimal("1"),
            submitted_price=None,
            executed_qty=Decimal("1"),
            executed_price=Decimal("1.23"),
            submitted_at=datetime(2026, 5, 5, 9, 35),
            updated_at=datetime(2026, 5, 5, 9, 35, 1),
            remark="qqq-trading-system",
        )

    def today_orders(self, **kwargs):
        return [
            SimpleNamespace(
                order_id="709043056541253632",
                symbol="QQQ260503C676000.US",
                side="Buy",
                status="Filled",
                executed_qty=Decimal("1"),
                executed_price=Decimal("1.23"),
            )
        ]

    def today_executions(self, **kwargs):
        return [
            SimpleNamespace(
                order_id="709043056541253632",
                symbol="QQQ260503C676000.US",
                side="Buy",
                quantity=Decimal("1"),
                price=Decimal("1.23"),
            )
        ]

    def stock_positions(self, symbols=None):
        return [
            SimpleNamespace(
                symbol="QQQ260503C676000.US",
                quantity=Decimal("1"),
                available_quantity=Decimal("1"),
                cost_price=Decimal("1.23"),
            )
        ]


class LongbridgeBrokerOrderTests(unittest.TestCase):
    def test_submit_order_returns_longbridge_id_and_order_detail_snapshot(self):
        broker = object.__new__(LongbridgeBroker)
        broker.trade_ctx = FakeTradeContext()

        order = broker.submit_option_order("QQQ260503C676000.US", "Buy", 1)

        self.assertFalse(order["dry_run"])
        self.assertEqual(order["source"], "longbridge")
        self.assertEqual(order["order_id"], "709043056541253632")
        self.assertEqual(order["longbridge_order_id"], "709043056541253632")
        self.assertEqual(order["longbridge_order"]["status"], "Filled")
        self.assertEqual(order["longbridge_order"]["executed_qty"], "1")
        self.assertEqual(order["longbridge_order"]["executed_price"], "1.23")
        self.assertEqual(order["longbridge_order"]["updated_at"], "2026-05-05T09:35:01")

    def test_submit_order_can_skip_waiting_for_execution(self):
        broker = object.__new__(LongbridgeBroker)
        broker.trade_ctx = FakeTradeContext()

        order = broker.submit_option_order("QQQ260503C676000.US", "Buy", 1, wait_for_execution=False)

        self.assertEqual(order["longbridge_order"]["status"], "Filled")
        self.assertEqual(broker.trade_ctx.detail_calls, 1)

    def test_submit_order_waits_until_execution_snapshot(self):
        class DelayedTradeContext(FakeTradeContext):
            def order_detail(self, order_id):
                self.detail_calls += 1
                if self.detail_calls == 1:
                    return SimpleNamespace(
                        order_id=order_id,
                        symbol="QQQ260503C676000.US",
                        status="New",
                        submitted_quantity=Decimal("1"),
                        executed_qty=Decimal("0"),
                        executed_price=Decimal("0"),
                    )
                return SimpleNamespace(
                    order_id=order_id,
                    symbol="QQQ260503C676000.US",
                    status="Filled",
                    submitted_quantity=Decimal("1"),
                    executed_qty=Decimal("1"),
                    executed_price=Decimal("1.23"),
                )

        broker = object.__new__(LongbridgeBroker)
        broker.trade_ctx = DelayedTradeContext()

        order = broker.submit_option_order(
            "QQQ260503C676000.US",
            "Buy",
            1,
            wait_timeout=1,
            poll_interval=0.01,
        )

        self.assertEqual(order["longbridge_order"]["status"], "Filled")
        self.assertEqual(order["longbridge_order"]["executed_qty"], "1")
        self.assertEqual(broker.trade_ctx.detail_calls, 2)

    def test_reconciliation_methods_serialize_orders_executions_and_positions(self):
        broker = object.__new__(LongbridgeBroker)
        broker.trade_ctx = FakeTradeContext()

        orders = broker.today_orders()
        executions = broker.today_executions()
        positions = broker.stock_positions()

        self.assertEqual(orders[0]["order_id"], "709043056541253632")
        self.assertEqual(orders[0]["executed_price"], "1.23")
        self.assertEqual(executions[0]["quantity"], "1")
        self.assertEqual(executions[0]["price"], "1.23")
        self.assertEqual(positions[0]["symbol"], "QQQ260503C676000.US")
        self.assertEqual(positions[0]["cost_price"], "1.23")


if __name__ == "__main__":
    unittest.main()
