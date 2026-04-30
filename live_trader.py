"""QQQ 0DTE live-trading entrypoint.

By default this program runs in dry-run mode and never submits real orders.
Real trading requires both `--live` and `QQQ_LIVE_TRADING=1`.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, time as dt_time
import json
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
from trading_config import CONFIG, WEB_CONFIG_KEYS, get_config


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
        position = PositionState(
            option_symbol=option_symbol,
            direction=signal.direction,
            quantity=quantity,
            entry_opt_price=option_quote.price,
            entry_stock_price=signal.entry_price,
            opened_bar_index=bar_index,
        )
        self.state["position"] = position.to_dict()
        self.state["trades_today"] = int(self.state.get("trades_today", 0)) + 1
        self.state["last_signal"] = signal.to_dict()
        self.state["filters"] = signal.filters
        if signal.kind == "reversal":
            self.reversal_used = True
        trade = {
            "timestamp": now_et_iso(),
            "symbol": option_symbol,
            "side": "Buy",
            "quantity": quantity,
            "price": option_quote.price,
            "notional": option_quote.price * quantity * int(self.config["contract_multiplier"]),
            "order": order,
            "signal": signal.to_dict(),
            "mode": self.state["mode"],
        }
        record_trade(trade, self.records_dir)
        self._notify_trade(trade)

    def _process_exit(self, bar_index: int) -> None:
        position = PositionState(**self.state["position"])
        quote = self.broker.quote_option(position.option_symbol)
        decision = evaluate_exit(position, quote.price, bar_index, self.config)
        self.state["position"] = None if position.remaining_quantity == 0 else position.to_dict()
        if decision.action in {"partial", "full"}:
            order = self.broker.submit_option_order(
                position.option_symbol,
                side="Sell",
                quantity=decision.quantity,
                limit_price=None if self.live and not self.dry_submit else quote.price,
            )
            pnl = (
                (quote.price - position.entry_opt_price)
                * decision.quantity
                * int(self.config["contract_multiplier"])
            )
            self.state["daily_pnl"] = float(self.state.get("daily_pnl", 0.0)) + pnl
            if decision.action == "full":
                if pnl >= 0:
                    self.state["wins_today"] = int(self.state.get("wins_today", 0)) + 1
                else:
                    self.state["losses_today"] = int(self.state.get("losses_today", 0)) + 1
            trade = {
                "timestamp": now_et_iso(),
                "symbol": position.option_symbol,
                "side": "Sell",
                "quantity": decision.quantity,
                "price": quote.price,
                "entry_price": position.entry_opt_price,
                "pnl": pnl,
                "pnl_pct": decision.profit_pct,
                "reason": decision.reason,
                "order": order,
                "mode": self.state["mode"],
            }
            record_trade(trade, self.records_dir)
            self._notify_trade(trade)

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
