"""QQQ 0DTE live-trading entrypoint.

By default this program runs in dry-run mode and never submits real orders.
Real trading requires both `--live` and `QQQ_LIVE_TRADING=1`.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, time as dt_time
import json
from math import isfinite
import os
from pathlib import Path
import time
from typing import Callable, Protocol

from qqq_strategy import (
    PositionState,
    TZ_ET,
    contracts_for_capital,
    evaluate_exit,
    get_option_symbol,
    select_signal,
)
from state_store import (
    append_today_bar,
    default_state,
    load_env_file,
    load_today_bars,
    now_et_iso,
    read_state,
    record_trade,
    write_state,
)
from trade_notify import notify_trade_if_configured
from trading_config import WEB_CONFIG_KEYS, get_config


def live_trading_allowed(live_flag: bool, env: dict | os._Environ = os.environ) -> bool:
    return bool(live_flag and env.get("QQQ_LIVE_TRADING") == "1")


def public_config(config: dict) -> dict:
    return {key: config.get(key) for key in WEB_CONFIG_KEYS}


def is_current_trading_day(state: dict) -> bool:
    updated = state.get("updated")
    if not isinstance(updated, str) or not updated:
        return False
    try:
        parsed = datetime.fromisoformat(updated)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ_ET)
    return parsed.astimezone(TZ_ET).date() == datetime.now(TZ_ET).date()


def parse_hhmm(value: str) -> dt_time:
    hour, minute = value.split(":", 1)
    return dt_time(int(hour), int(minute))


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    price: float
    volume: float = 0.0


class Broker(Protocol):
    def quote_stock(self, symbol: str) -> QuoteSnapshot: ...

    def quote_option(self, symbol: str) -> QuoteSnapshot: ...

    def submit_option_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: float | None = None,
    ) -> dict: ...


class DryRunBroker:
    def quote_stock(self, symbol: str) -> QuoteSnapshot:
        raise RuntimeError("No quote source is configured in dry-run mode")

    def quote_option(self, symbol: str) -> QuoteSnapshot:
        return QuoteSnapshot(symbol=symbol, price=1.0, volume=0)

    def submit_option_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: float | None = None,
    ) -> dict:
        return {
            "order_id": f"dry-{int(time.time())}",
            "dry_run": True,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "limit_price": limit_price,
        }


class DrySubmitBroker:
    """Use a real quote broker but record orders without submitting them."""

    def __init__(self, quote_broker: Broker) -> None:
        self.quote_broker = quote_broker

    def quote_stock(self, symbol: str) -> QuoteSnapshot:
        return self.quote_broker.quote_stock(symbol)

    def quote_option(self, symbol: str) -> QuoteSnapshot:
        return self.quote_broker.quote_option(symbol)

    def submit_option_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: float | None = None,
    ) -> dict:
        return {
            "order_id": f"dry-submit-{int(time.time())}",
            "dry_run": True,
            "dry_submit": True,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "limit_price": limit_price,
        }


def _is_longbridge_order(order: dict) -> bool:
    return bool(
        isinstance(order, dict)
        and not order.get("dry_run")
        and (
            order.get("source") == "longbridge"
            or order.get("longbridge_order_id")
            or isinstance(order.get("longbridge_order"), dict)
        )
    )


def _order_detail(order: dict) -> dict:
    detail = order.get("longbridge_order")
    return detail if isinstance(detail, dict) else {}


def _order_field(order: dict, key: str):
    detail = _order_detail(order)
    value = detail.get(key)
    if value not in (None, ""):
        return value
    value = order.get(key)
    if value not in (None, ""):
        return value
    return None


def _order_id(order: dict) -> str | None:
    for key in ("longbridge_order_id", "order_id"):
        value = order.get(key)
        if value not in (None, ""):
            return str(value)
    detail_value = _order_detail(order).get("order_id")
    if detail_value not in (None, ""):
        return str(detail_value)
    return None


def _float_or_none(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number):
        return None
    return number


def _quantity_or_none(value) -> int | float | None:
    number = _float_or_none(value)
    if number is None or number <= 0:
        return None
    return int(number) if number.is_integer() else number


def _effective_order_quantity(
    order: dict,
    fallback_quantity: int | float | None,
) -> tuple[int | float | None, str]:
    for key, source in (
        ("executed_qty", "longbridge_executed_qty"),
        ("executed_quantity", "longbridge_executed_quantity"),
        ("submitted_quantity", "longbridge_submitted_quantity"),
        ("quantity", "order_quantity"),
    ):
        quantity = _quantity_or_none(_order_field(order, key))
        if quantity is not None:
            return quantity, source
    if fallback_quantity is not None:
        source = "local_strategy_fallback" if _is_longbridge_order(order) else "local_strategy"
        return fallback_quantity, source
    return None, "unavailable"


def _effective_order_price(
    order: dict,
    fallback_price: float | None,
) -> tuple[float | None, str]:
    for key, source in (
        ("executed_price", "longbridge_executed_price"),
        ("submitted_price", "longbridge_submitted_price"),
        ("price", "order_price"),
        ("limit_price", "order_limit_price"),
    ):
        price = _float_or_none(_order_field(order, key))
        if price is not None and price > 0:
            return price, source
    if fallback_price is not None:
        source = "local_quote_fallback" if _is_longbridge_order(order) else "local_quote"
        return fallback_price, source
    return None, "unavailable"


def _order_source(order: dict) -> str:
    if _is_longbridge_order(order):
        return "longbridge"
    if order.get("dry_submit"):
        return "dry-submit"
    if order.get("dry_run"):
        return "dry-run"
    return str(order.get("source") or "unknown")


def _enrich_trade_from_order(
    trade: dict,
    order: dict,
    *,
    fallback_quantity: int | float | None,
    fallback_price: float | None,
) -> None:
    order_id = _order_id(order)
    if order_id:
        trade["order_id"] = order_id
    trade["order_source"] = _order_source(order)

    status = _order_field(order, "status")
    if status is not None:
        trade["order_status"] = str(status)
    for key in ("submitted_at", "updated_at"):
        value = _order_field(order, key)
        if value is not None:
            trade[f"order_{key}"] = value

    if _is_longbridge_order(order) and order_id:
        trade["longbridge_order_id"] = order_id

    quantity, quantity_source = _effective_order_quantity(order, fallback_quantity)
    if quantity is not None:
        trade["quantity"] = quantity
    trade["quantity_source"] = quantity_source

    price, price_source = _effective_order_price(order, fallback_price)
    if price is not None:
        trade["price"] = price
    trade["price_source"] = price_source


def _order_summary(order: dict) -> dict:
    summary = {
        "order_id": _order_id(order),
        "source": _order_source(order),
    }
    status = _order_field(order, "status")
    if status is not None:
        summary["status"] = str(status)
    detail_error = _order_detail(order).get("detail_error")
    if detail_error:
        summary["detail_error"] = detail_error
    return {key: value for key, value in summary.items() if value not in (None, "")}


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(
            process_query_limited_information,
            False,
            wintypes.DWORD(pid),
        )
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class SingleInstanceLock:
    """Exclusive lock file used to prevent duplicate trading engines."""

    def __init__(
        self,
        path: str | Path,
        *,
        pid: int | None = None,
        process_checker: Callable[[int], bool] = is_process_running,
    ) -> None:
        self.path = Path(path)
        self.pid = pid or os.getpid()
        self.process_checker = process_checker
        self._acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                fd = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                existing_pid = self._read_existing_pid()
                if existing_pid and self.process_checker(existing_pid):
                    raise RuntimeError(
                        f"another live_trader instance is already running "
                        f"(pid={existing_pid}, lock={self.path})"
                    )
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "pid": self.pid,
                        "created": now_et_iso(),
                    },
                    handle,
                    ensure_ascii=False,
                )
                handle.write("\n")
            self._acquired = True
            return

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            if self._read_existing_pid() == self.pid:
                self.path.unlink(missing_ok=True)
        finally:
            self._acquired = False

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def _read_existing_pid(self) -> int | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        try:
            return int(data.get("pid"))
        except (TypeError, ValueError):
            return None


class BarBuilder:
    def __init__(self) -> None:
        self._minute: datetime | None = None
        self._bar: dict | None = None

    def update(self, price: float, volume: float, now: datetime) -> dict | None:
        minute = now.replace(second=0, microsecond=0)
        if self._bar is None:
            self._start_bar(price, volume, minute)
            return None
        if minute != self._minute:
            closed = dict(self._bar)
            self._start_bar(price, volume, minute)
            return closed
        self._bar["high"] = max(self._bar["high"], price)
        self._bar["low"] = min(self._bar["low"], price)
        self._bar["close"] = price
        self._bar["volume"] = volume
        return None

    def close_current(self) -> dict | None:
        if self._bar is None:
            return None
        closed = dict(self._bar)
        self._bar = None
        self._minute = None
        return closed

    def _start_bar(self, price: float, volume: float, minute: datetime) -> None:
        self._minute = minute
        self._bar = {
            "timestamp": minute.isoformat(),
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": volume,
        }


class LiveTrader:
    def __init__(
        self,
        broker: Broker | None = None,
        config: dict | None = None,
        state_path: str | Path = "state.json",
        today_path: str | Path = "today.csv",
        records_dir: str | Path = "records",
        live: bool = False,
        dry_submit: bool = False,
    ) -> None:
        self.config = config or get_config()
        self.broker = broker or DryRunBroker()
        self.state_path = Path(state_path)
        self.today_path = Path(today_path)
        self.records_dir = Path(records_dir)
        self.live = live
        self.dry_submit = dry_submit
        self.builder = BarBuilder()
        self.state = read_state(self.state_path)
        self.candles = load_today_bars(self.today_path)
        self.reversal_used = False

    def initialize_state(self, running: bool = True) -> None:
        previous = self.state if isinstance(self.state, dict) else {}
        same_trading_day = is_current_trading_day(previous)
        mode = "dry-run"
        if self.live:
            mode = "live-dry-submit" if self.dry_submit else "live"
        state = default_state()
        state.update(
            {
                "connected": False,
                "running": running,
                "mode": mode,
                "symbol": self.config["symbol"],
                "candle_count": len(self.candles),
                "updated": now_et_iso(),
                "config": public_config(self.config),
            }
        )
        if same_trading_day:
            for key in (
                "daily_pnl",
                "trades_today",
                "wins_today",
                "losses_today",
                "last_signal",
                "filters",
                "last_order",
            ):
                state[key] = previous.get(key)
            if previous.get("position"):
                state["position"] = previous.get("position")
        self.state = state
        write_state(self.state, self.state_path)

    def process_bar(self, bar: dict) -> dict:
        append_today_bar(bar, self.today_path)
        self.candles.append(bar)
        self.state["candle_count"] = len(self.candles)
        self.state["updated"] = now_et_iso()

        if self.state.get("position"):
            self._process_exit(len(self.candles) - 1)
        elif self._can_open_new_trade():
            signal = select_signal(
                self.candles,
                self.config,
                reversal_used=self.reversal_used,
            )
            if signal:
                self._open_position(signal, len(self.candles) - 1)
            else:
                self.state["last_signal"] = None
        write_state(self.state, self.state_path)
        return self.state

    def run_once(self) -> dict:
        self.initialize_state(running=False)
        if self.live:
            try:
                self.broker.quote_stock(self.config["symbol"])
                self.state["connected"] = True
                self.state["last_error"] = None
            except Exception as exc:
                self.state["connected"] = False
                self.state["last_error"] = str(exc)
            self.state["updated"] = now_et_iso()
            write_state(self.state, self.state_path)
        return self.state

    def run_forever(self) -> None:
        self.initialize_state(running=True)
        interval = int(self.config["check_interval"])
        while True:
            try:
                quote = self.broker.quote_stock(self.config["symbol"])
                self.state["connected"] = True
                bar = self.builder.update(quote.price, quote.volume, datetime.now(TZ_ET))
                if bar:
                    self.process_bar(bar)
                else:
                    self.state["updated"] = now_et_iso()
                    write_state(self.state, self.state_path)
            except KeyboardInterrupt:
                self.state["running"] = False
                write_state(self.state, self.state_path)
                raise
            except Exception as exc:
                self.state["connected"] = False
                self.state["last_error"] = str(exc)
                self.state["updated"] = now_et_iso()
                write_state(self.state, self.state_path)
            time.sleep(interval)

    def _can_open_new_trade(self) -> bool:
        if self.state.get("position"):
            return False
        if not self._in_entry_window():
            return False
        if int(self.state.get("trades_today", 0)) >= int(self.config["max_trades"]):
            return False
        limit = float(self.config["capital"]) * (float(self.config["daily_limit"]) / 100.0)
        if float(self.state.get("daily_pnl", 0.0)) <= -limit:
            return False
        return True

    def _in_entry_window(self) -> bool:
        start = parse_hhmm(str(self.config["start_time"]))
        end = parse_hhmm(str(self.config["end_time"]))
        now = self._current_bar_time()
        return start <= now <= end

    def _current_bar_time(self) -> dt_time:
        if self.candles:
            timestamp = self.candles[-1].get("timestamp")
            if isinstance(timestamp, str):
                try:
                    parsed = datetime.fromisoformat(timestamp)
                except ValueError:
                    parsed = None
                if parsed:
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=TZ_ET)
                    return parsed.astimezone(TZ_ET).time()
        return datetime.now(TZ_ET).time()

    def _open_position(self, signal, bar_index: int) -> None:
        option_symbol = get_option_symbol(
            signal.entry_price,
            signal.direction,
            offset=float(self.config["option_offset"]),
        )
        option_quote = self.broker.quote_option(option_symbol)
        max_option_price = self.config.get("max_option_price")
        if max_option_price is not None and option_quote.price > float(max_option_price):
            self.state["last_error"] = (
                f"Option price {option_quote.price:.2f} exceeds max_option_price {float(max_option_price):.2f}"
            )
            return
        quantity = contracts_for_capital(
            option_quote.price,
            float(self.config["capital"]),
            float(self.config["pos_pct"]),
            int(self.config["min_contracts"]),
            int(self.config["contract_multiplier"]),
            max_contracts=self.config.get("max_contracts"),
        )
        if quantity <= 0:
            self.state["last_error"] = "Position budget is too small for one contract"
            return

        order = self.broker.submit_option_order(
            option_symbol,
            side="Buy",
            quantity=quantity,
            limit_price=None if self.live and not self.dry_submit else option_quote.price,
        )
        entry_quantity, _quantity_source = _effective_order_quantity(order, quantity)
        entry_price, price_source = _effective_order_price(order, option_quote.price)
        position_quantity = int(entry_quantity) if entry_quantity is not None else quantity
        position_price = float(entry_price) if entry_price is not None else option_quote.price
        position = PositionState(
            option_symbol=option_symbol,
            direction=signal.direction,
            quantity=position_quantity,
            entry_opt_price=position_price,
            entry_stock_price=signal.entry_price,
            opened_bar_index=bar_index,
            entry_order_id=_order_id(order),
            entry_order_status=str(_order_field(order, "status")) if _order_field(order, "status") else None,
            entry_price_source=price_source,
        )
        self.state["position"] = position.to_dict()
        self.state["trades_today"] = int(self.state.get("trades_today", 0)) + 1
        self.state["last_signal"] = signal.to_dict()
        self.state["filters"] = signal.filters
        self.state["last_order"] = _order_summary(order)
        if signal.kind == "reversal":
            self.reversal_used = True
        trade = {
            "timestamp": now_et_iso(),
            "symbol": option_symbol,
            "side": "Buy",
            "quantity": quantity,
            "price": option_quote.price,
            "strategy_quote_price": option_quote.price,
            "strategy_quantity": quantity,
            "notional": option_quote.price * quantity * int(self.config["contract_multiplier"]),
            "order": order,
            "signal": signal.to_dict(),
            "mode": self.state["mode"],
        }
        _enrich_trade_from_order(
            trade,
            order,
            fallback_quantity=quantity,
            fallback_price=option_quote.price,
        )
        record_trade(trade, self.records_dir)
        self._notify_trade(trade)

    def _process_exit(self, bar_index: int) -> None:
        position = PositionState(**self.state["position"])
        previous_position = deepcopy(position)
        quote = self.broker.quote_option(position.option_symbol)
        decision = evaluate_exit(position, quote.price, bar_index, self.config)
        if decision.action in {"partial", "full"}:
            try:
                order = self.broker.submit_option_order(
                    position.option_symbol,
                    side="Sell",
                    quantity=decision.quantity,
                    limit_price=None if self.live and not self.dry_submit else quote.price,
                )
            except Exception as exc:
                self.state["position"] = previous_position.to_dict()
                self.state["last_error"] = f"Exit order failed; position preserved: {exc}"
                return
            exit_price, exit_price_source = _effective_order_price(order, quote.price)
            exit_quantity, _quantity_source = _effective_order_quantity(order, decision.quantity)
            realized_quantity = int(exit_quantity) if exit_quantity is not None else decision.quantity
            realized_price = float(exit_price) if exit_price is not None else quote.price
            pnl = (
                (realized_price - position.entry_opt_price)
                * realized_quantity
                * int(self.config["contract_multiplier"])
            )
            self.state["position"] = None if position.remaining_quantity == 0 else position.to_dict()
            self.state["daily_pnl"] = float(self.state.get("daily_pnl", 0.0)) + pnl
            if decision.action == "full":
                if pnl >= 0:
                    self.state["wins_today"] = int(self.state.get("wins_today", 0)) + 1
                else:
                    self.state["losses_today"] = int(self.state.get("losses_today", 0)) + 1
            self.state["last_order"] = _order_summary(order)
            trade = {
                "timestamp": now_et_iso(),
                "symbol": position.option_symbol,
                "side": "Sell",
                "quantity": decision.quantity,
                "price": quote.price,
                "strategy_quote_price": quote.price,
                "strategy_quantity": decision.quantity,
                "entry_price": position.entry_opt_price,
                "pnl": pnl,
                "pnl_pct": decision.profit_pct,
                "pnl_source": f"{exit_price_source}_minus_{position.entry_price_source}",
                "reason": decision.reason,
                "order": order,
                "mode": self.state["mode"],
            }
            _enrich_trade_from_order(
                trade,
                order,
                fallback_quantity=decision.quantity,
                fallback_price=quote.price,
            )
            record_trade(trade, self.records_dir)
            self._notify_trade(trade)
        else:
            self.state["position"] = position.to_dict()

    def _notify_trade(self, trade: dict) -> None:
        try:
            result = notify_trade_if_configured(trade)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        if result is not None:
            self.state["last_notification"] = result


def build_broker(live: bool, dry_submit: bool = False) -> Broker:
    if not live:
        return DryRunBroker()
    from longbridge_client import LongbridgeBroker

    broker = LongbridgeBroker()
    if dry_submit:
        return DrySubmitBroker(broker)
    return broker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QQQ 0DTE trading engine")
    parser.add_argument("--live", action="store_true", help="Enable live broker adapter")
    parser.add_argument(
        "--submit-live-orders",
        action="store_true",
        help="Actually call Longbridge submit_order. Without this, --live uses real quotes but dry-submits orders.",
    )
    parser.add_argument("--once", action="store_true", help="Write state and exit")
    parser.add_argument("--state", default="state.json")
    parser.add_argument("--today", default="today.csv")
    parser.add_argument("--records", default="records")
    parser.add_argument("--capital", type=float, help="Override configured account capital")
    parser.add_argument("--option-offset", type=float, help="Override option strike offset")
    parser.add_argument("--max-option-price", type=float, help="Skip entries above this option price")
    parser.add_argument("--pos-pct", type=float, help="Override configured position percentage")
    parser.add_argument("--min-contracts", type=int, help="Override configured minimum contracts")
    parser.add_argument("--max-contracts", type=int, help="Cap contracts per order")
    parser.add_argument("--max-trades", type=int, help="Override configured maximum trades per day")
    parser.add_argument(
        "--lock-file",
        default=".live_trader.lock",
        help="Exclusive lock path used to prevent duplicate long-running engines",
    )
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help="Disable the duplicate-engine lock; use only for isolated diagnostics",
    )
    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> dict:
    config = get_config()
    overrides = {
        "capital": args.capital,
        "option_offset": args.option_offset,
        "max_option_price": args.max_option_price,
        "pos_pct": args.pos_pct,
        "min_contracts": args.min_contracts,
        "max_contracts": args.max_contracts,
        "max_trades": args.max_trades,
    }
    for key, value in overrides.items():
        if value is not None:
            config[key] = value
    return config


def main() -> int:
    args = parse_args()
    load_env_file(".env")
    live = live_trading_allowed(args.live)
    dry_submit = bool(live and not args.submit_live_orders)
    broker = build_broker(live, dry_submit=dry_submit)
    trader = LiveTrader(
        broker=broker,
        config=config_from_args(args),
        state_path=args.state,
        today_path=args.today,
        records_dir=args.records,
        live=live,
        dry_submit=dry_submit,
    )
    if args.once:
        trader.run_once()
        mode = "live-dry-submit" if dry_submit else "live" if live else "dry-run"
        print(f"state written to {args.state} ({mode})")
        return 0
    if args.no_lock:
        trader.run_forever()
    else:
        with SingleInstanceLock(args.lock_file):
            trader.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
