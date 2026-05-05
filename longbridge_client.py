"""Longbridge SDK adapter.

The adapter is imported only when live trading is explicitly enabled. This
keeps tests and dry-run diagnostics usable without the SDK installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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

    def _quote_one(self, symbol: str) -> Any:
        quotes = self.quote_ctx.quote([symbol])
        if not quotes:
            raise LookupError(f"Longbridge returned no quote for {symbol}")
        return quotes[0]

    def quote_stock(self, symbol: str) -> QuoteSnapshot:
        quote = self._quote_one(symbol)
        return QuoteSnapshot(
            symbol=symbol,
            price=float(quote.last_done),
            volume=float(getattr(quote, "volume", 0) or 0),
        )

    def quote_option(self, symbol: str) -> QuoteSnapshot:
        quote = self._quote_one(symbol)
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
        order_id = str(response.order_id)
        return {
            "order_id": order_id,
            "longbridge_order_id": order_id,
            "source": "longbridge",
            "dry_run": False,
            "longbridge_order": self._order_detail_snapshot(order_id),
        }

    def _order_detail_snapshot(self, order_id: str) -> dict[str, Any]:
        try:
            detail = self.trade_ctx.order_detail(order_id)
        except Exception as exc:  # pragma: no cover - depends on live broker timing/network.
            return {
                "order_id": order_id,
                "detail_error": str(exc),
            }
        snapshot = _serialize_order(detail)
        snapshot.setdefault("order_id", order_id)
        return snapshot


ORDER_DETAIL_FIELDS = (
    "order_id",
    "symbol",
    "order_type",
    "side",
    "status",
    "submitted_quantity",
    "submitted_price",
    "executed_qty",
    "executed_price",
    "submitted_at",
    "updated_at",
    "tag",
    "time_in_force",
    "expire_date",
    "outside_rth",
    "remark",
)


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, (str, int, float, bool)):
        return enum_value
    enum_name = getattr(value, "name", None)
    if isinstance(enum_name, str):
        return enum_name
    return str(value)


def _serialize_order(order: Any) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for field in ORDER_DETAIL_FIELDS:
        if hasattr(order, field):
            snapshot[field] = _serialize_value(getattr(order, field))
    return snapshot
