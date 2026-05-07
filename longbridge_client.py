"""Longbridge SDK adapter.

The adapter is imported only when live trading is explicitly enabled. This
keeps tests and dry-run diagnostics usable without the SDK installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import time
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
        wait_for_execution: bool = True,
        wait_timeout: float = 8.0,
        poll_interval: float = 0.5,
    ) -> dict[str, Any]:
        OrderSide, OrderType, TimeInForceType = _order_constants()
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
        detail = (
            self.wait_order_execution(order_id, timeout=wait_timeout, interval=poll_interval)
            if wait_for_execution
            else self._order_detail_snapshot(order_id)
        )
        return {
            "order_id": order_id,
            "longbridge_order_id": order_id,
            "source": "longbridge",
            "dry_run": False,
            "longbridge_order": detail,
        }

    def wait_order_execution(
        self,
        order_id: str,
        *,
        timeout: float = 8.0,
        interval: float = 0.5,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.0, timeout)
        last_snapshot = self._order_detail_snapshot(order_id)
        while True:
            if _is_terminal_order_snapshot(last_snapshot):
                return last_snapshot
            if time.monotonic() >= deadline:
                last_snapshot["execution_wait_timeout"] = True
                return last_snapshot
            time.sleep(max(0.05, interval))
            last_snapshot = self._order_detail_snapshot(order_id)

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

    def today_orders(
        self,
        symbol: str | None = None,
        status: Any | None = None,
        side: Any | None = None,
        market: Any | None = None,
        order_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            _serialize_object(item, ORDER_DETAIL_FIELDS)
            for item in self.trade_ctx.today_orders(
                symbol=symbol,
                status=status,
                side=side,
                market=market,
                order_id=order_id,
            )
        ]

    def today_executions(
        self,
        symbol: str | None = None,
        order_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            _serialize_object(item, EXECUTION_FIELDS)
            for item in self.trade_ctx.today_executions(symbol=symbol, order_id=order_id)
        ]

    def stock_positions(self, symbols: list[str] | None = None) -> list[dict[str, Any]]:
        return [
            _serialize_object(item, POSITION_FIELDS)
            for item in self.trade_ctx.stock_positions(symbols=symbols)
        ]


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


EXECUTION_FIELDS = (
    "order_id",
    "trade_id",
    "symbol",
    "side",
    "price",
    "quantity",
    "executed_quantity",
    "executed_price",
    "submitted_quantity",
    "submitted_price",
    "executed_at",
    "trade_done_at",
    "created_at",
    "updated_at",
)


POSITION_FIELDS = (
    "symbol",
    "symbol_name",
    "quantity",
    "available_quantity",
    "cost_price",
    "market_price",
    "market_value",
    "currency",
    "market",
    "init_quantity",
    "today_buy_quantity",
    "today_sell_quantity",
)


FILLED_ORDER_STATUSES = {
    "filled",
    "partialfilled",
    "partialfilledstatus",
    "partial_filled",
}
TERMINAL_ORDER_STATUSES = FILLED_ORDER_STATUSES | {
    "rejected",
    "cancelled",
    "canceled",
    "expired",
    "failed",
}


def normalize_order_status(status: Any) -> str:
    return str(status or "").replace("_", "").replace("-", "").replace(" ", "").lower()


def _order_constants():
    try:
        from longbridge.openapi import OrderSide, OrderType, TimeInForceType

        return OrderSide, OrderType, TimeInForceType
    except ModuleNotFoundError:
        class OrderSide:
            Buy = "Buy"
            Sell = "Sell"

        class OrderType:
            MO = "MO"
            LO = "LO"

        class TimeInForceType:
            Day = "Day"

        return OrderSide, OrderType, TimeInForceType


def _order_executed_qty(snapshot: dict[str, Any]) -> float:
    for key in ("executed_qty", "executed_quantity"):
        value = snapshot.get(key)
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        return number
    return 0.0


def _is_terminal_order_snapshot(snapshot: dict[str, Any]) -> bool:
    if snapshot.get("detail_error"):
        return True
    if _order_executed_qty(snapshot) > 0:
        return True
    status = normalize_order_status(snapshot.get("status"))
    return status in TERMINAL_ORDER_STATUSES


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
    return _serialize_object(order, ORDER_DETAIL_FIELDS)


def _serialize_object(item: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for field in fields:
        if hasattr(item, field):
            snapshot[field] = _serialize_value(getattr(item, field))
    if not snapshot and isinstance(item, dict):
        return {str(key): _serialize_value(value) for key, value in item.items()}
    raw = getattr(item, "__dict__", None)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key.startswith("_"):
                continue
            snapshot.setdefault(key, _serialize_value(value))
    return snapshot
