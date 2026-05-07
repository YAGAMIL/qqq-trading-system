"""Lightweight signal backtest for CSV OHLCV data.

This is a reproducible harness for the strategy rules, not a substitute for a
real option-chain fill simulator.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from qqq_strategy import PositionState, StrategyState, evaluate_exit
from state_store import is_regular_market_bar, parse_et_timestamp
from trading_config import CONFIG, get_config


def load_bars(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def option_proxy_price(position: PositionState, stock_price: float) -> float:
    direction_mult = 1 if position.direction == "call" else -1
    move = direction_mult * ((stock_price - position.entry_stock_price) / position.entry_stock_price)
    return max(0.01, position.entry_opt_price * (1 + move * 12))


def _parse_hhmm(value: str):
    hour, minute = value.split(":", 1)
    return int(hour), int(minute)


def _bar_time(bar: dict):
    parsed = parse_et_timestamp(bar.get("timestamp"))
    if parsed is None:
        return None
    return parsed.time()


def _in_entry_window(bar: dict, cfg: dict) -> bool:
    current = _bar_time(bar)
    if current is None:
        return True
    start_h, start_m = _parse_hhmm(str(cfg["start_time"]))
    end_h, end_m = _parse_hhmm(str(cfg["end_time"]))
    start = current.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = current.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    return start <= current <= end


def _bar_index(candles: list[dict]) -> int:
    return max(0, len(candles) - 1)


def run_backtest(bars: list[dict], config: dict | None = None) -> dict:
    cfg = config or get_config()
    candles: list[dict] = []
    strategy_state = StrategyState()
    position: PositionState | None = None
    trades: list[dict] = []
    reversal_used = False
    pnl = 0.0

    trades_opened = 0
    for index, raw_bar in enumerate(bars):
        bar = {
            "timestamp": raw_bar.get("timestamp") or raw_bar.get("time") or str(index),
            "open": float(raw_bar["open"]),
            "high": float(raw_bar["high"]),
            "low": float(raw_bar["low"]),
            "close": float(raw_bar["close"]),
            "volume": float(raw_bar.get("volume", 0)),
        }
        if not is_regular_market_bar(bar):
            continue
        candles.append(bar)
        strategy_state.append(bar)
        if position:
            proxy_price = option_proxy_price(position, bar["close"])
            decision = evaluate_exit(position, proxy_price, _bar_index(candles), cfg)
            if decision.action in {"partial", "full"}:
                trade_pnl = (
                    (proxy_price - position.entry_opt_price)
                    * decision.quantity
                    * int(cfg["contract_multiplier"])
                )
                pnl += trade_pnl
                trades.append(
                    {
                        "timestamp": bar["timestamp"],
                        "side": "Sell",
                        "quantity": decision.quantity,
                        "price": proxy_price,
                        "pnl": trade_pnl,
                        "reason": decision.reason,
                    }
                )
            if position.remaining_quantity == 0:
                position = None
            continue

        if not _in_entry_window(bar, cfg):
            continue
        if trades_opened >= int(cfg["max_trades"]):
            continue
        daily_limit = float(cfg["capital"]) * (float(cfg["daily_limit"]) / 100.0)
        if pnl <= -daily_limit:
            continue
        signal = strategy_state.select_signal(cfg, reversal_used=reversal_used)
        if not signal:
            continue
        entry_opt_price = max(0.25, bar["close"] * 0.003)
        max_option_price = cfg.get("max_option_price")
        if max_option_price is not None and entry_opt_price > float(max_option_price):
            continue
        quantity = int(cfg["min_contracts"])
        max_contracts = cfg.get("max_contracts")
        if max_contracts is not None:
            quantity = min(quantity, int(max_contracts))
        if quantity <= 0:
            continue
        position = PositionState(
            option_symbol=f"BACKTEST-{signal.direction.upper()}",
            direction=signal.direction,
            quantity=quantity,
            entry_opt_price=entry_opt_price,
            entry_stock_price=bar["close"],
            opened_bar_index=_bar_index(candles),
        )
        trades_opened += 1
        reversal_used = reversal_used or signal.kind == "reversal"
        trades.append(
            {
                "timestamp": bar["timestamp"],
                "side": "Buy",
                "quantity": quantity,
                "price": entry_opt_price,
                "signal": signal.to_dict(),
            }
        )

    if position and candles:
        final_bar = candles[-1]
        proxy_price = option_proxy_price(position, final_bar["close"])
        quantity = int(position.remaining_quantity or 0)
        if quantity > 0:
            trade_pnl = (
                (proxy_price - position.entry_opt_price)
                * quantity
                * int(cfg["contract_multiplier"])
            )
            pnl += trade_pnl
            trades.append(
                {
                    "timestamp": final_bar["timestamp"],
                    "side": "Sell",
                    "quantity": quantity,
                    "price": proxy_price,
                    "pnl": trade_pnl,
                    "reason": "end_of_data",
                }
            )

    return {
        "bars": len(bars),
        "trade_events": len(trades),
        "round_trips_estimate": sum(1 for trade in trades if trade["side"] == "Buy"),
        "pnl": pnl,
        "config": {key: cfg[key] for key in sorted(CONFIG)},
        "trades": trades,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run signal backtest from OHLCV CSV")
    parser.add_argument("csv")
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_backtest(load_bars(args.csv))
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
