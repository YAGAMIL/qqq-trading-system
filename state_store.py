"""State, CSV, and trade-record persistence helpers."""

from __future__ import annotations

import csv
from contextlib import contextmanager
from datetime import date, datetime, time as dt_time
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any
from zoneinfo import ZoneInfo

from trading_config import CONFIG, web_config


TZ_ET = ZoneInfo("America/New_York")
CSV_FIELDS = ("timestamp", "open", "high", "low", "close", "volume")
REGULAR_MARKET_START = dt_time(9, 30)
REGULAR_MARKET_END = dt_time(16, 0)
DEFAULT_DB_PATH = "trading_state.db"
DB_SCHEMA_VERSION = 1


@contextmanager
def sqlite_connection(path: str | Path):
    conn = sqlite3.connect(path, timeout=0.2)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


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


def parse_et_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ_ET)
    return parsed.astimezone(TZ_ET)


def bar_trading_date(bar: dict) -> date | None:
    parsed = parse_et_timestamp(bar.get("timestamp"))
    return parsed.date() if parsed else None


def is_regular_market_bar(bar: dict) -> bool:
    parsed = parse_et_timestamp(bar.get("timestamp"))
    if parsed is None:
        return True
    current = parsed.time()
    return REGULAR_MARKET_START <= current <= REGULAR_MARKET_END


def filter_bars_for_trading_day(
    bars: list[dict],
    trading_date: date | None = None,
    *,
    regular_session_only: bool = False,
) -> list[dict]:
    target_date = trading_date or datetime.now(TZ_ET).date()
    filtered = [bar for bar in bars if bar_trading_date(bar) == target_date]
    if regular_session_only:
        filtered = [bar for bar in filtered if is_regular_market_bar(bar)]
    return filtered


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
        "last_order": None,
        "last_error": None,
        "last_notification": None,
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


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _json_loads_dict(payload: str | None) -> dict:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def init_database(path: str | Path = DEFAULT_DB_PATH) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite_connection(target) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runtime_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                updated TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bars (
                timestamp TEXT PRIMARY KEY,
                trading_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_bars_trading_date ON bars(trading_date, timestamp);
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                timestamp TEXT,
                symbol TEXT,
                side TEXT,
                order_id TEXT,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trades_trade_date ON trades(trade_date, id);
            CREATE TABLE IF NOT EXISTS broker_orders (
                order_id TEXT PRIMARY KEY,
                symbol TEXT,
                side TEXT,
                status TEXT,
                source TEXT,
                updated_at TEXT,
                seen_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS broker_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                seen_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            ("schema_version", str(DB_SCHEMA_VERSION)),
        )


def write_state_db(state: dict, path: str | Path = DEFAULT_DB_PATH) -> None:
    init_database(path)
    payload = dict(state)
    payload["updated"] = payload.get("updated") or now_et_iso()
    with sqlite_connection(path) as conn:
        conn.execute(
            """
            INSERT INTO runtime_state(id, updated, payload)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated=excluded.updated,
                payload=excluded.payload
            """,
            (str(payload["updated"]), _json_dumps(payload)),
        )


def read_state_db(path: str | Path = DEFAULT_DB_PATH) -> dict:
    target = Path(path)
    if not target.exists():
        return default_state()
    init_database(target)
    with sqlite_connection(target) as conn:
        row = conn.execute("SELECT payload FROM runtime_state WHERE id = 1").fetchone()
    merged = default_state()
    if row:
        merged.update(_json_loads_dict(row[0]))
    merged.setdefault("filters", default_state()["filters"])
    merged.setdefault("config", web_config())
    return merged


def read_runtime_state(
    state_path: str | Path = "state.json",
    db_path: str | Path | None = None,
) -> dict:
    if db_path is not None and Path(db_path).exists():
        return read_state_db(db_path)
    return read_state(state_path)


def write_runtime_state(
    state: dict,
    state_path: str | Path = "state.json",
    db_path: str | Path | None = None,
) -> None:
    write_state(state, state_path)
    if db_path is not None:
        write_state_db(state, db_path)


def _write_bars_csv(bars: list[dict], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in bars:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def _last_non_empty_line(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            position = handle.tell()
            buffer = bytearray()
            while position > 0:
                chunk_size = min(4096, position)
                position -= chunk_size
                handle.seek(position)
                buffer[:0] = handle.read(chunk_size)
                lines = [line for line in buffer.splitlines() if line.strip()]
                if len(lines) >= 2 or position == 0:
                    return lines[-1].decode("utf-8") if lines else None
    except OSError:
        return None
    return None


def _last_csv_bar_date(path: Path) -> date | None:
    line = _last_non_empty_line(path)
    if not line or line == ",".join(CSV_FIELDS):
        return None
    try:
        row = next(csv.DictReader([",".join(CSV_FIELDS), line]))
    except (csv.Error, StopIteration):
        return None
    return bar_trading_date(row)


def append_today_bar(bar: dict, path: str | Path = "today.csv") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target_date = bar_trading_date(bar) or datetime.now(TZ_ET).date()
    if target.exists() and target.stat().st_size > 0:
        last_date = _last_csv_bar_date(target)
        if last_date is None or last_date != target_date:
            existing = load_today_bars(target)
            same_day = filter_bars_for_trading_day(existing, target_date)
            _write_bars_csv(same_day, target)
    exists = target.exists() and target.stat().st_size > 0
    with target.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: bar.get(field, "") for field in CSV_FIELDS})


def load_today_bars(
    path: str | Path = "today.csv",
    trading_date: date | None = None,
    *,
    regular_session_only: bool = False,
) -> list[dict]:
    target = Path(path)
    if not target.exists():
        return []
    with target.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if trading_date is not None:
        rows = filter_bars_for_trading_day(
            rows,
            trading_date,
            regular_session_only=regular_session_only,
        )
    elif regular_session_only:
        rows = [bar for bar in rows if is_regular_market_bar(bar)]
    return rows


def append_bar_db(bar: dict, path: str | Path = DEFAULT_DB_PATH) -> None:
    init_database(path)
    normalized = {
        "timestamp": bar.get("timestamp") or now_et_iso(),
        "open": float(bar["open"]),
        "high": float(bar["high"]),
        "low": float(bar["low"]),
        "close": float(bar["close"]),
        "volume": float(bar.get("volume", 0)),
    }
    trading_date = bar_trading_date(normalized) or datetime.now(TZ_ET).date()
    with sqlite_connection(path) as conn:
        conn.execute(
            """
            INSERT INTO bars(timestamp, trading_date, open, high, low, close, volume, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(timestamp) DO UPDATE SET
                trading_date=excluded.trading_date,
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume,
                payload=excluded.payload
            """,
            (
                str(normalized["timestamp"]),
                trading_date.isoformat(),
                normalized["open"],
                normalized["high"],
                normalized["low"],
                normalized["close"],
                normalized["volume"],
                _json_dumps(normalized),
            ),
        )


def load_bars_db(
    path: str | Path = DEFAULT_DB_PATH,
    trading_date: date | None = None,
    *,
    regular_session_only: bool = False,
) -> list[dict]:
    target = Path(path)
    if not target.exists():
        return []
    init_database(target)
    params: tuple[Any, ...] = ()
    query = "SELECT payload FROM bars"
    if trading_date is not None:
        query += " WHERE trading_date = ?"
        params = (trading_date.isoformat(),)
    query += " ORDER BY timestamp"
    with sqlite_connection(target) as conn:
        rows = [_json_loads_dict(row[0]) for row in conn.execute(query, params)]
    if regular_session_only:
        rows = [bar for bar in rows if is_regular_market_bar(bar)]
    return rows


def append_runtime_bar(
    bar: dict,
    today_path: str | Path = "today.csv",
    db_path: str | Path | None = None,
) -> None:
    if db_path is not None:
        append_bar_db(bar, db_path)
    append_today_bar(bar, today_path)


def load_runtime_bars(
    today_path: str | Path = "today.csv",
    trading_date: date | None = None,
    *,
    regular_session_only: bool = False,
    db_path: str | Path | None = None,
) -> list[dict]:
    if db_path is not None and Path(db_path).exists():
        rows = load_bars_db(
            db_path,
            trading_date,
            regular_session_only=regular_session_only,
        )
        if rows:
            return rows
    return load_today_bars(
        today_path,
        trading_date,
        regular_session_only=regular_session_only,
    )


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


def record_trade_db(trade: dict, path: str | Path = DEFAULT_DB_PATH) -> int:
    init_database(path)
    trade_date = _record_date(trade)
    order_id = None
    for key in ("longbridge_order_id", "order_id"):
        value = trade.get(key)
        if value not in (None, ""):
            order_id = str(value)
            break
    with sqlite_connection(path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO trades(trade_date, timestamp, symbol, side, order_id, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                trade_date,
                trade.get("timestamp"),
                trade.get("symbol"),
                trade.get("side"),
                order_id,
                _json_dumps(trade),
            ),
        )
        return int(cursor.lastrowid)


def record_runtime_trade(
    trade: dict,
    records_dir: str | Path = "records",
    db_path: str | Path | None = None,
) -> Path:
    if db_path is not None:
        record_trade_db(trade, db_path)
    return record_trade(trade, records_dir)


def load_trade_records_db(path: str | Path = DEFAULT_DB_PATH) -> list[dict]:
    target = Path(path)
    if not target.exists():
        return []
    init_database(target)
    with sqlite_connection(target) as conn:
        rows = conn.execute("SELECT payload FROM trades ORDER BY trade_date, id").fetchall()
    return [_json_loads_dict(row[0]) for row in rows]


def upsert_broker_orders_db(
    orders: list[dict],
    path: str | Path = DEFAULT_DB_PATH,
    *,
    seen_at: str | None = None,
) -> None:
    if not orders:
        return
    init_database(path)
    seen = seen_at or now_et_iso()
    with sqlite_connection(path) as conn:
        for order in orders:
            order_id = order.get("order_id")
            if order_id in (None, ""):
                continue
            conn.execute(
                """
                INSERT INTO broker_orders(order_id, symbol, side, status, source, updated_at, seen_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    symbol=excluded.symbol,
                    side=excluded.side,
                    status=excluded.status,
                    source=excluded.source,
                    updated_at=excluded.updated_at,
                    seen_at=excluded.seen_at,
                    payload=excluded.payload
                """,
                (
                    str(order_id),
                    order.get("symbol"),
                    str(order.get("side")) if order.get("side") not in (None, "") else None,
                    str(order.get("status")) if order.get("status") not in (None, "") else None,
                    str(order.get("source") or "longbridge"),
                    order.get("updated_at"),
                    seen,
                    _json_dumps(order),
                ),
            )


def record_broker_snapshot_db(
    kind: str,
    payload: dict | list,
    path: str | Path = DEFAULT_DB_PATH,
    *,
    seen_at: str | None = None,
) -> None:
    init_database(path)
    with sqlite_connection(path) as conn:
        conn.execute(
            "INSERT INTO broker_snapshots(kind, seen_at, payload) VALUES (?, ?, ?)",
            (kind, seen_at or now_et_iso(), _json_dumps(payload)),
        )
