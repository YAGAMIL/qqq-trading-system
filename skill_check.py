"""End-to-end smoke checks for the QQQ trading system skill.

The script is intentionally read-only for broker state: it verifies imports,
dry-run state writing, Longbridge read-only quote paths, optional Gist config,
and optional Hermes notification wiring. It never submits live orders.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from longbridge_cli_check import run_check as run_longbridge_cli_check
from qqq_strategy import get_option_symbol
from state_store import load_env_file
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
    for name in ("longbridge", "flask", "numpy", "scipy"):
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


def longbridge_sdk_quotes(env_file: Path) -> dict[str, Any]:
    load_env_file(env_file)
    try:
        from longbridge_client import LongbridgeBroker

        broker = LongbridgeBroker(str(env_file))
        stock = broker.quote_stock("QQQ.US")
        call_symbol = get_option_symbol(stock.price, "call")
        put_symbol = get_option_symbol(stock.price, "put")
        call_quote = broker.quote_option(call_symbol)
        put_quote = broker.quote_option(put_symbol)
        return ok(
            stock={"symbol": stock.symbol, "price": stock.price, "volume": stock.volume},
            call={"symbol": call_symbol, "price": call_quote.price, "volume": call_quote.volume},
            put={"symbol": put_symbol, "price": put_quote.price, "volume": put_quote.volume},
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
        "dry_run_once": dry_run_once(),
        "gist_config": gist_config(os.environ),
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
