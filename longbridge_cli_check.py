"""Read-only Longbridge CLI preflight for the QQQ trading system."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from state_store import load_env_file


def _run_json(command: list[str], timeout: int) -> Any:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(command)} failed with exit {result.returncode}: {result.stderr.strip()}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{' '.join(command)} did not return JSON") from exc


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _summarize(
    cli_path: str,
    symbol: str,
    check: dict[str, Any],
    quote: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    portfolio: dict[str, Any],
) -> dict[str, Any]:
    quote_item = quote[0] if quote else {}
    last = _number(quote_item.get("last") or quote_item.get("last_done"))
    overview = portfolio.get("overview", {}) if isinstance(portfolio, dict) else {}
    holdings = portfolio.get("holdings", []) if isinstance(portfolio, dict) else []
    connectivity = check.get("connectivity", {})
    return {
        "cli": cli_path,
        "read_only": True,
        "token": check.get("session", {}).get("token"),
        "connectivity": {
            "global": bool(connectivity.get("global", {}).get("ok")),
            "cn": bool(connectivity.get("cn", {}).get("ok")),
        },
        "quote": {
            "symbol": symbol,
            "ok": bool(last and last > 0),
            "last": last,
            "status": quote_item.get("status") or quote_item.get("trade_status"),
        },
        "account": {
            "positions": len(positions) if isinstance(positions, list) else 0,
            "portfolio_holdings": len(holdings) if isinstance(holdings, list) else 0,
            "currency": overview.get("currency"),
            "risk_level": overview.get("risk_level"),
        },
    }


def run_check(symbol: str, env_file: Path, timeout: int) -> dict[str, Any]:
    load_env_file(env_file)
    cli_path = shutil.which("longbridge") or shutil.which("longbridge.exe")
    if not cli_path:
        raise RuntimeError("Longbridge CLI not found on PATH")

    check = _run_json([cli_path, "check", "--format", "json"], timeout)
    quote = _run_json([cli_path, "quote", symbol, "--format", "json"], timeout)
    positions = _run_json([cli_path, "positions", "--format", "json"], timeout)
    portfolio = _run_json([cli_path, "portfolio", "--format", "json"], timeout)
    return _summarize(cli_path, symbol, check, quote, positions, portfolio)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run read-only Longbridge CLI checks for auth, quotes, positions, and portfolio."
    )
    parser.add_argument("--symbol", default="QQQ.US", help="Symbol to quote, e.g. QQQ.US")
    parser.add_argument("--env-file", default=".env", help="Env file with Longbridge credentials")
    parser.add_argument("--timeout", type=int, default=30, help="Per-command timeout in seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = run_check(args.symbol, Path(args.env_file), args.timeout)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
