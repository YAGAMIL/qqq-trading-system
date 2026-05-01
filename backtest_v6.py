"""Lightweight signal backtest for CSV OHLCV data.

This is a reproducible harness for the strategy rules, not a substitute for a
real option-chain fill simulator.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import json
from pathlib import Path

from qqq_strategy import PositionState, evaluate_exit, select_signal
from trading_config import CONFIG, get_config


def load_bars(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def option_proxy_price(position: PositionState, stock_price: float) -> float:
    direction_mult = 1 if position.direction == "call" else -1
    move = direction_mult * ((stock_price - position.entry_stock_price) / position.entry_stock_price)
    return max(0.01, position.entry_opt_price * (1 + move * 12))


def run_backtest(bars: list[dict], config: dict | None = None) -> dict:
    cfg = config or get_config()
    candles: list[dict] = []
    position: PositionState | None = None
    trades: list[dict] = []
    reversal_used = False
    pnl = 0.0

    for index, raw_bar in enumerate(bars):
        bar = {
            "timestamp": raw_bar.get("timestamp") or raw_bar.get("time") or str(index),
            "open": float(raw_bar["open"]),
            "high": float(raw_bar["high"]),
            "low": float(raw_bar["low"]),
            "close": float(raw_bar["close"]),
            "volume": float(raw_bar.get("volume", 0)),
        }
        candles.append(bar)
        if position:
            proxy_price = option_proxy_price(position, bar["close"])
            decision = evaluate_exit(position, proxy_price, index, cfg)
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

        if len(trades) >= int(cfg["max_trades"]):
            continue
        signal = select_signal(candles, cfg, reversal_used=reversal_used)
        if not signal:
            continue
        entry_opt_price = max(0.25, bar["close"] * 0.003)
        quantity = int(cfg["min_contracts"])
        position = PositionState(
            option_symbol=f"BACKTEST-{signal.direction.upper()}",
            direction=signal.direction,
            quantity=quantity,
            entry_opt_price=entry_opt_price,
            entry_stock_price=bar["close"],
            opened_bar_index=index,
        )
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
