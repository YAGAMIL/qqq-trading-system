"""Pure strategy logic for the QQQ 0DTE trading system.

This module intentionally has no Longbridge dependency. It can be unit-tested
offline and reused by live trading, web display, and backtesting code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from math import floor
from statistics import mean
from typing import Iterable
from zoneinfo import ZoneInfo

from trading_config import CONFIG


TZ_ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Signal:
    kind: str
    direction: str
    entry_price: float
    reference_price: float
    filters: dict[str, bool]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PositionState:
    option_symbol: str
    direction: str
    quantity: int
    entry_opt_price: float
    entry_stock_price: float
    opened_bar_index: int
    remaining_quantity: int | None = None
    partial_taken: bool = False
    max_profit_pct: float = 0.0

    def __post_init__(self) -> None:
        if self.remaining_quantity is None:
            self.remaining_quantity = self.quantity

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExitDecision:
    action: str
    reason: str
    quantity: int = 0
    profit_pct: float = 0.0
    filters: dict[str, bool] = field(default_factory=dict)


def _as_float(value: object) -> float:
    return float(value)


def normalize_bar(raw: dict) -> dict:
    return {
        "timestamp": raw.get("timestamp"),
        "open": _as_float(raw["open"]),
        "high": _as_float(raw["high"]),
        "low": _as_float(raw["low"]),
        "close": _as_float(raw["close"]),
        "volume": _as_float(raw.get("volume", 0)),
    }


def normalize_bars(candles: Iterable[dict]) -> list[dict]:
    return [normalize_bar(candle) for candle in candles]


def get_option_symbol(
    stock_price: float,
    direction: str,
    offset: float = 2.0,
    now: datetime | None = None,
) -> str:
    if direction not in {"call", "put"}:
        raise ValueError("direction must be 'call' or 'put'")

    now_et = now.astimezone(TZ_ET) if now else datetime.now(TZ_ET)
    if direction == "call":
        strike = round(stock_price + offset)
        option_type = "C"
    else:
        strike = round(stock_price - offset)
        option_type = "P"

    expiry = now_et.strftime("%y%m%d")
    return f"QQQ{expiry}{option_type}{strike * 1000:06d}.US"


def _body_ratio(bar: dict) -> float:
    base = max(abs(bar["open"]), 0.01)
    return abs(bar["close"] - bar["open"]) / base


def _average(values: list[float], default: float = 0.0) -> float:
    return mean(values) if values else default


def _previous_volume_average(candles: list[dict], count: int = 20) -> float:
    previous = candles[:-1][-count:]
    return _average([bar["volume"] for bar in previous], default=candles[-1]["volume"])


def _sma(candles: list[dict], count: int = 20) -> float:
    window = candles[-count:]
    return _average([bar["close"] for bar in window], default=candles[-1]["close"])


def evaluate_breakout_signal(candles: Iterable[dict], config: dict | None = None) -> Signal | None:
    cfg = config or CONFIG
    bars = normalize_bars(candles)
    lookback = int(cfg["lookback"])
    if len(bars) < lookback + 1:
        return None

    current = bars[-1]
    previous_window = bars[-lookback - 1 : -1]
    upper = max(bar["high"] for bar in previous_window)
    lower = min(bar["low"] for bar in previous_window)
    sma20 = _sma(bars)
    avg_volume = _previous_volume_average(bars)
    body_ok = _body_ratio(current) >= float(cfg["min_body"])
    volume_ok = current["volume"] >= avg_volume * float(cfg["vol_mult"])

    call_filters = {
        "breakout": current["close"] > upper,
        "sma20": current["close"] > sma20,
        "volume": volume_ok,
        "momentum": current["close"] > current["open"],
        "body": body_ok,
        "gap": ((current["close"] - upper) / upper) <= float(cfg["max_gap"]),
    }
    if all(call_filters.values()):
        return Signal(
            kind="breakout",
            direction="call",
            entry_price=current["close"],
            reference_price=upper,
            filters=call_filters,
            reason="breakout_continuation",
        )

    put_filters = {
        "breakout": current["close"] < lower,
        "sma20": current["close"] < sma20,
        "volume": volume_ok,
        "momentum": current["close"] < current["open"],
        "body": body_ok,
        "gap": ((lower - current["close"]) / lower) <= float(cfg["max_gap"]),
    }
    if all(put_filters.values()):
        return Signal(
            kind="breakout",
            direction="put",
            entry_price=current["close"],
            reference_price=lower,
            filters=put_filters,
            reason="breakout_continuation",
        )

    return None


def evaluate_reversal_signal(
    candles: Iterable[dict],
    config: dict | None = None,
    reversal_used: bool = False,
) -> Signal | None:
    cfg = config or CONFIG
    if reversal_used:
        return None
    bars = normalize_bars(candles)
    if len(bars) < 2:
        return None

    current = bars[-1]
    intraday_high = max(bar["high"] for bar in bars[:-1])
    intraday_low = min(bar["low"] for bar in bars[:-1])
    drop_from_high = (intraday_high - current["close"]) / intraday_high
    rise_from_low = (current["close"] - intraday_low) / intraday_low
    body = _body_ratio(current)

    call_filters = {
        "exhaustion": drop_from_high >= float(cfg["reversal_drop"]),
        "bounce": current["close"] > current["open"],
        "body": body >= float(cfg["reversal_bounce"]),
    }
    if all(call_filters.values()):
        return Signal(
            kind="reversal",
            direction="call",
            entry_price=current["close"],
            reference_price=intraday_high,
            filters=call_filters,
            reason="exhaustion_reversal",
        )

    put_filters = {
        "exhaustion": rise_from_low >= float(cfg["reversal_drop"]),
        "bounce": current["close"] < current["open"],
        "body": body >= float(cfg["reversal_bounce"]),
    }
    if all(put_filters.values()):
        return Signal(
            kind="reversal",
            direction="put",
            entry_price=current["close"],
            reference_price=intraday_low,
            filters=put_filters,
            reason="exhaustion_reversal",
        )

    return None


def select_signal(
    candles: Iterable[dict],
    config: dict | None = None,
    reversal_used: bool = False,
) -> Signal | None:
    breakout = evaluate_breakout_signal(candles, config)
    if breakout:
        return breakout
    return evaluate_reversal_signal(candles, config, reversal_used=reversal_used)


def contracts_for_capital(
    option_price: float,
    capital: float,
    pos_pct: float,
    min_contracts: int,
    contract_multiplier: int = 100,
    max_contracts: int | None = None,
) -> int:
    if option_price <= 0:
        return 0
    budget = capital * (pos_pct / 100.0)
    affordable = floor(budget / (option_price * contract_multiplier))
    if affordable < min_contracts:
        return 0
    if max_contracts is None:
        return affordable
    if max_contracts <= 0:
        return 0
    return min(affordable, max_contracts)


def evaluate_exit(
    position: PositionState,
    option_price: float,
    bar_index: int,
    config: dict | None = None,
) -> ExitDecision:
    cfg = config or CONFIG
    if position.entry_opt_price <= 0 or position.remaining_quantity <= 0:
        return ExitDecision(action="hold", reason="invalid_position")

    profit_pct = (option_price - position.entry_opt_price) / position.entry_opt_price
    position.max_profit_pct = max(position.max_profit_pct, profit_pct)

    if profit_pct <= -float(cfg["sl"]):
        quantity = int(position.remaining_quantity)
        position.remaining_quantity = 0
        return ExitDecision("full", "stop_loss", quantity, profit_pct)

    bars_held = bar_index - position.opened_bar_index
    if bars_held >= int(cfg.get("max_hold_bars", 15)):
        quantity = int(position.remaining_quantity)
        position.remaining_quantity = 0
        return ExitDecision("full", "timeout", quantity, profit_pct)

    if not position.partial_taken and profit_pct >= float(cfg["tp_partial_pct"]):
        quantity = max(1, int(position.remaining_quantity // 2))
        position.remaining_quantity -= quantity
        position.partial_taken = True
        return ExitDecision("partial", "partial_take_profit", quantity, profit_pct)

    drawdown = position.max_profit_pct - profit_pct
    if position.partial_taken and drawdown >= float(cfg["tp_trail_drop"]):
        quantity = int(position.remaining_quantity)
        position.remaining_quantity = 0
        return ExitDecision("full", "trailing_take_profit", quantity, profit_pct)

    return ExitDecision("hold", "no_exit", 0, profit_pct)
