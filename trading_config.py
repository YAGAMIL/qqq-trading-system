"""Shared configuration for the QQQ 0DTE trading system."""

from __future__ import annotations

from copy import deepcopy


CONFIG = {
    "symbol": "QQQ.US",
    "sl": 0.25,
    "tp": 0.30,
    "lookback": 5,
    "tp_partial_pct": 1.00,
    "tp_trail_drop": 0.30,
    "option_offset": 2.0,
    "max_option_price": None,
    "min_contracts": 10,
    "contract_multiplier": 100,
    "pos_pct": 2,
    "max_trades": 8,
    "daily_limit": 5,
    "start_time": "09:35",
    "end_time": "15:50",
    "trail_activate": 0.10,
    "trail_drop": 0.05,
    "max_gap": 0.0020,
    "vol_mult": 0.8,
    "min_body": 0.0003,
    "reversal_drop": 0.002,
    "reversal_bounce": 0.001,
    "check_interval": 20,
    "capital": 100000,
    "max_contracts": None,
    "max_hold_bars": 15,
}


WEB_CONFIG_KEYS = (
    "sl",
    "tp",
    "lookback",
    "tp_partial_pct",
    "tp_trail_drop",
    "vol_mult",
    "min_body",
    "max_gap",
    "max_trades",
    "max_option_price",
    "daily_limit",
    "max_contracts",
    "start_time",
    "end_time",
    "reversal_drop",
    "reversal_bounce",
)


def get_config() -> dict:
    return deepcopy(CONFIG)


def web_config() -> dict:
    return {key: CONFIG[key] for key in WEB_CONFIG_KEYS}
