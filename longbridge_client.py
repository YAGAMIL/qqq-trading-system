"""Longbridge SDK adapter.

The adapter is imported only when live trading is explicitly enabled. This
keeps tests and dry-run diagnostics usable without the SDK installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from state_store import load_env_file


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    price: float
    volume: float = 0.0


class LongbridgeBroker:
    def __init__(self, env_path: str = ".env") -> None:
        load_env_file(env_path)
        from longbridge.openapi import Config, QuoteContext, TradeContext

        config = Config.from_apikey_env()
        self.quote_ctx = QuoteContext(config)
        self.trade_ctx = TradeContext(config)

    def quote_stock(self, symbol: str) -> QuoteSnapshot:
        quote = self.quote_ctx.quote([symbol])[0]
        return QuoteSnapshot(
            symbol=symbol,
            price=float(quote.last_done),
            volume=float(getattr(quote, "volume", 0) or 0),
        )

    def quote_option(self, symbol: str) -> QuoteSnapshot:
        quote = self.quote_ctx.quote([symbol])[0]
        return QuoteSnapshot(
            symbol=symbol,
            price=float(quote.last_done),
            volume=float(getattr(quote, "volume", 0) or 0),
        )

    def submit_option_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: float | None = None,
    ) -> dict[str, Any]:
        from longbridge.openapi import OrderSide, OrderType, TimeInForceType

        order_side = OrderSide.Buy if side.lower() == "buy" else OrderSide.Sell
        kwargs: dict[str, Any] = {
            "symbol": symbol,
            "side": order_side,
            "submitted_quantity": Decimal(quantity),
            "time_in_force": TimeInForceType.Day,
            "remark": "qqq-trading-system",
        }
        if limit_price is None:
            kwargs["order_type"] = OrderType.MO
        else:
            kwargs["order_type"] = OrderType.LO
            kwargs["submitted_price"] = Decimal(str(round(limit_price, 2)))
        response = self.trade_ctx.submit_order(**kwargs)
        return {"order_id": response.order_id, "dry_run": False}
