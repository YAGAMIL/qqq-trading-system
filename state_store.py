"""State, CSV, and trade-record persistence helpers."""

from __future__ import annotations

import csv
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

from trading_config import CONFIG, web_config


TZ_ET = ZoneInfo("America/New_York")
CSV_FIELDS = ("timestamp", "open", "high", "low", "close", "volume")


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)
        legacy_aliases = {
            "LONGPORT_APP_KEY": "LONGBRIDGE_APP_KEY",
            "LONGPORT_APP_SECRET": "LONGBRIDGE_APP_SECRET",
            "LONGPORT_ACCESS_TOKEN": "LONGBRIDGE_ACCESS_TOKEN",
        }
        if key in legacy_aliases:
            os.environ.setdefault(legacy_aliases[key], value)


def now_et_iso() -> str:
    return datetime.now(TZ_ET).isoformat(timespec="seconds")


def default_state() -> dict:
    return {
        "connected": False,
        "running": False,
        "mode": "dry-run",
        "symbol": CONFIG["symbol"],
        "updated": now_et_iso(),
        "candle_count": 0,
        "position": None,
        "daily_pnl": 0.0,
        "trades_today": 0,
        "wins_today": 0,
        "losses_today": 0,
        "last_signal": None,
        "last_error": None,
        "filters": {
            "breakout": None,
            "sma20": None,
            "volume": None,
            "momentum": None,
            "body": None,
            "gap": None,
        },
        "config": web_config(),
    }


def atomic_write_json(payload: dict | list, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(target.parent),
        delete=False,
        newline="\n",
    ) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        temp_name = tmp.name
    Path(temp_name).replace(target)


def read_state(path: str | Path = "state.json") -> dict:
    state_path = Path(path)
    if not state_path.exists():
        return default_state()
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        state = default_state()
        state["last_error"] = f"Invalid JSON in {state_path}"
        return state
    merged = default_state()
    merged.update(state)
    merged.setdefault("filters", default_state()["filters"])
    merged.setdefault("config", web_config())
    return merged


def write_state(state: dict, path: str | Path = "state.json") -> None:
    state = dict(state)
    state["updated"] = state.get("updated") or now_et_iso()
    atomic_write_json(state, path)


def append_today_bar(bar: dict, path: str | Path = "today.csv") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    exists = target.exists() and target.stat().st_size > 0
    with target.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: bar.get(field, "") for field in CSV_FIELDS})


def load_today_bars(path: str | Path = "today.csv") -> list[dict]:
    target = Path(path)
    if not target.exists():
        return []
    with target.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _record_date(trade: dict) -> str:
    timestamp = trade.get("timestamp")
    if isinstance(timestamp, str) and len(timestamp) >= 10:
        return timestamp[:10]
    return datetime.now(TZ_ET).date().isoformat()


def record_trade(trade: dict, records_dir: str | Path = "records") -> Path:
    directory = Path(records_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_record_date(trade)}.json"
    records = []
    if path.exists():
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            records = []
    records.append(trade)
    atomic_write_json(records, path)
    return path
