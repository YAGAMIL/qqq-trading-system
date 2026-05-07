"""End-to-end smoke checks for the QQQ trading system skill.

The script is intentionally read-only for broker state: it verifies imports,
dry-run state writing, Longbridge read-only quote paths, optional Gist config,
and optional Hermes notification wiring. It never submits live orders.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from live_trader import is_process_running, live_trading_allowed
from longbridge_cli_check import run_check as run_longbridge_cli_check
from qqq_strategy import TZ_ET, get_option_symbol
from state_store import load_env_file, load_bars_db, load_trade_records_db, read_runtime_state
from trade_notify import format_trade_message, notify_trade_if_configured


CORE_MODULES = (
    "trading_config.py",
    "qqq_strategy.py",
    "state_store.py",
    "longbridge_client.py",
    "live_trader.py",
    "trader_web.py",
    "watchdog.py",
    "update_gist.py",
    "backtest_v6.py",
    "longbridge_cli_check.py",
    "trade_notify.py",
)


def ok(**extra: Any) -> dict[str, Any]:
    return {"ok": True, **extra}


def fail(error: BaseException | str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": str(error), **extra}


def package_versions() -> dict[str, Any]:
    packages = {}
    for name in ("longbridge", "flask", "tzdata"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return ok(python=sys.version.split()[0], packages=packages)


def py_compile_check() -> dict[str, Any]:
    command = [sys.executable, "-m", "py_compile", *CORE_MODULES]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return fail(result.stderr or result.stdout, command=command)
    return ok(files=len(CORE_MODULES))


def safety_guards(env: dict[str, str]) -> dict[str, Any]:
    """Report local safety defaults without contacting external services."""

    return ok(
        dry_run_default=not live_trading_allowed(False, env),
        live_requires_env_opt_in=not live_trading_allowed(True, {})
        and live_trading_allowed(True, {"QQQ_LIVE_TRADING": "1"}),
        live_order_submission_requires_submit_flag=True,
        gist_upload_requires_confirm_upload=True,
        notification_disabled_without_target=not bool(env.get("QQQ_NOTIFY_TARGET")),
    )


def env_readiness(env_file: Path, env: dict[str, str]) -> dict[str, Any]:
    """Summarize credential presence without printing secrets."""

    required = (
        "LONGBRIDGE_APP_KEY",
        "LONGBRIDGE_APP_SECRET",
        "LONGBRIDGE_ACCESS_TOKEN",
    )
    return ok(
        env_file=str(env_file),
        env_file_exists=env_file.exists(),
        longbridge_credentials={name: bool(env.get(name)) for name in required},
        qqq_live_trading=env.get("QQQ_LIVE_TRADING", "0"),
        gist_configured=bool(env.get("GIST_ID") and env.get("GITHUB_TOKEN")),
        notify_target_set=bool(env.get("QQQ_NOTIFY_TARGET")),
    )


def _read_lock_pid(lock_path: Path) -> int | None:
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return int(payload.get("pid"))
    except (TypeError, ValueError):
        return None


def runtime_artifacts(
    state_path: Path,
    today_path: Path,
    records_dir: Path,
    lock_path: Path,
    db_path: Path | None = None,
    process_checker=is_process_running,
) -> dict[str, Any]:
    """Inspect local runtime artifacts without deleting or mutating them."""

    state: dict[str, Any] | None = None
    if state_path.exists() or (db_path is not None and db_path.exists()):
        state = read_runtime_state(state_path, db_path if db_path and db_path.exists() else None)
    lock_pid = _read_lock_pid(lock_path) if lock_path.exists() else None
    lock_process_running = process_checker(lock_pid) if lock_pid is not None else False
    state_running = bool(state.get("running")) if state else False
    db_exists = bool(db_path and db_path.exists())
    db_bars = len(load_bars_db(db_path)) if db_exists and db_path is not None else 0
    db_trades = len(load_trade_records_db(db_path)) if db_exists and db_path is not None else 0
    return ok(
        state_exists=state_path.exists(),
        state_updated=state.get("updated") if state else None,
        state_running=state.get("running") if state else None,
        today_csv_exists=today_path.exists(),
        records_dir_exists=records_dir.exists(),
        record_files=len(list(records_dir.glob("*.json"))) if records_dir.exists() else 0,
        db_exists=db_exists,
        db_bars=db_bars,
        db_trades=db_trades,
        lock_exists=lock_path.exists(),
        lock_pid=lock_pid,
        lock_process_running=lock_process_running,
        likely_stale_lock=lock_path.exists() and not lock_process_running,
        likely_stale_state=state_running and not lock_process_running,
    )


def dry_run_once() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="qqq_skill_check_") as tmp:
        root = Path(tmp)
        state = root / "state.json"
        today = root / "today.csv"
        records = root / "records"
        command = [
            sys.executable,
            "live_trader.py",
            "--once",
            "--state",
            str(state),
            "--today",
            str(today),
            "--records",
            str(records),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return fail(result.stderr or result.stdout, command=command)
        payload = json.loads(state.read_text(encoding="utf-8"))
        return ok(
            mode=payload.get("mode"),
            running=payload.get("running"),
            connected=payload.get("connected"),
            symbol=payload.get("symbol"),
        )


def option_smoke_datetimes(now: datetime | None = None, days: int = 7) -> list[tuple[datetime, str]]:
    """Return listed weekday option dates to probe for smoke checks.

    Live trading still uses same-day 0DTE symbols. The smoke check may run on a
    weekend or holiday, so it probes the current ET weekday first and then the
    next weekdays instead of manufacturing a non-listed Saturday/Sunday symbol.
    """

    now_et = (now or datetime.now(TZ_ET)).astimezone(TZ_ET)
    candidates: list[tuple[datetime, str]] = []
    for offset in range(days + 1):
        candidate = now_et + timedelta(days=offset)
        if candidate.weekday() >= 5:
            continue
        source = "current_et" if offset == 0 else "next_weekday_et"
        candidates.append((candidate, source))
    return candidates


def longbridge_sdk_quotes(env_file: Path) -> dict[str, Any]:
    load_env_file(env_file)
    try:
        from longbridge_client import LongbridgeBroker

        broker = LongbridgeBroker(str(env_file))
        stock = broker.quote_stock("QQQ.US")
        skipped_candidates: list[dict[str, Any]] = []
        last_error: Exception | None = None
        for option_now, source in option_smoke_datetimes():
            call_symbol = get_option_symbol(stock.price, "call", now=option_now)
            put_symbol = get_option_symbol(stock.price, "put", now=option_now)
            try:
                call_quote = broker.quote_option(call_symbol)
                put_quote = broker.quote_option(put_symbol)
                return ok(
                    stock={"symbol": stock.symbol, "price": stock.price, "volume": stock.volume},
                    option_date=option_now.date().isoformat(),
                    option_date_source=source,
                    skipped_candidates=skipped_candidates,
                    call={"symbol": call_symbol, "price": call_quote.price, "volume": call_quote.volume},
                    put={"symbol": put_symbol, "price": put_quote.price, "volume": put_quote.volume},
                )
            except Exception as exc:
                last_error = exc
                skipped_candidates.append(
                    {
                        "date": option_now.date().isoformat(),
                        "source": source,
                        "call_symbol": call_symbol,
                        "put_symbol": put_symbol,
                        "error": str(exc),
                    }
                )

        if last_error is None:
            raise RuntimeError("no weekday option quote candidates generated")
        return fail(
            last_error,
            stock={"symbol": stock.symbol, "price": stock.price, "volume": stock.volume},
            skipped_candidates=skipped_candidates,
        )
    except Exception as exc:  # pragma: no cover - live external path
        return fail(exc)


def longbridge_cli(env_file: Path, timeout: int) -> dict[str, Any]:
    try:
        return ok(summary=run_longbridge_cli_check("QQQ.US", env_file, timeout))
    except Exception as exc:
        shim = shutil.which("longbridge") or shutil.which("longbridge.exe")
        return fail(exc, shim=shim)


def gist_config(env: dict[str, str]) -> dict[str, Any]:
    return ok(
        configured=bool(env.get("GIST_ID") and env.get("GITHUB_TOKEN")),
        gist_id_set=bool(env.get("GIST_ID")),
        token_set=bool(env.get("GITHUB_TOKEN")),
    )


def safety_contract(env: dict[str, str]) -> dict[str, Any]:
    """Expose the non-real-order guarantees this smoke check is allowed to prove."""

    return ok(
        real_order_submission=False,
        gist_upload=False,
        live_order_requires=[
            "QQQ_LIVE_TRADING=1",
            "live_trader.py --live",
            "live_trader.py --submit-live-orders",
        ],
        live_order_env_opt_in=env.get("QQQ_LIVE_TRADING") == "1",
        external_writes=["none"],
        notes=[
            "skill_check.py does not pass --submit-live-orders",
            "update_gist.py is not invoked with --confirm-upload",
            "Longbridge checks are quote/account read-only when --skip-live is not used",
        ],
    )


def notification_check(send: bool) -> dict[str, Any]:
    trade = {
        "timestamp": "2026-05-01T09:35:00-04:00",
        "symbol": "QQQ260501C665000.US",
        "side": "Buy",
        "quantity": 1,
        "price": 0.98,
        "mode": "live-dry-submit",
        "order": {"dry_submit": True},
        "signal": {"kind": "breakout", "direction": "call"},
    }
    message = format_trade_message(trade)
    if not send:
        return ok(configured=bool(os.environ.get("QQQ_NOTIFY_TARGET")), dry_run=True, message=message)
    try:
        result = notify_trade_if_configured(trade)
        return ok(configured=result is not None, result=result)
    except Exception as exc:  # pragma: no cover - live external path
        return fail(exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run safe QQQ skill capability checks")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--state", default="state.json", help="Runtime state path to inspect")
    parser.add_argument("--today", default="today.csv", help="Runtime candle CSV path to inspect")
    parser.add_argument("--records", default="records", help="Runtime records directory to inspect")
    parser.add_argument("--lock-file", default=".live_trader.lock", help="Runtime lock path to inspect")
    parser.add_argument("--db", default="trading_state.db", help="SQLite runtime database path to inspect")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--skip-live", action="store_true", help="Skip Longbridge live quote checks")
    parser.add_argument(
        "--send-test-notification",
        action="store_true",
        help="Send one Hermes notification if QQQ_NOTIFY_TARGET is configured",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_file = Path(args.env_file)
    load_env_file(env_file)

    checks: dict[str, Any] = {
        "packages": package_versions(),
        "py_compile": py_compile_check(),
        "safety_guards": safety_guards(os.environ),
        "env_readiness": env_readiness(env_file, os.environ),
        "runtime_artifacts": runtime_artifacts(
            Path(args.state),
            Path(args.today),
            Path(args.records),
            Path(args.lock_file),
            Path(args.db),
        ),
        "dry_run_once": dry_run_once(),
        "gist_config": gist_config(os.environ),
        "safety_contract": safety_contract(os.environ),
        "notification": notification_check(send=args.send_test_notification),
    }
    if not args.skip_live:
        checks["longbridge_sdk_quotes"] = longbridge_sdk_quotes(env_file)
        checks["longbridge_cli"] = longbridge_cli(env_file, args.timeout)

    required = ("packages", "py_compile", "dry_run_once")
    if not args.skip_live:
        required += ("longbridge_sdk_quotes", "longbridge_cli")

    overall_ok = all(bool(checks[name].get("ok")) for name in required)
    print(json.dumps({"ok": overall_ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
