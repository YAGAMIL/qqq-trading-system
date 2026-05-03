import unittest
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


if __name__ == "__main__":
    unittest.main()
