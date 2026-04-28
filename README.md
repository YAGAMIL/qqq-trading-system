# QQQ Trading System

This repository contains a runnable implementation of the QQQ 0DTE system
described in `SKILL.md`.

The trading engine defaults to dry-run mode. Even with `--live`, it uses real
quotes but dry-submits orders unless all three conditions are true:

1. `QQQ_LIVE_TRADING=1` is present in the environment or `.env`.
2. `live_trader.py` is started with `--live`.
3. `live_trader.py` is also started with `--submit-live-orders`.

## Setup

```bash
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

Fill `.env` with `LONGBRIDGE_APP_KEY`, `LONGBRIDGE_APP_SECRET`,
`LONGBRIDGE_ACCESS_TOKEN`, and a private `WEB_TOKEN`.

## Dry-Run Diagnostics

```bash
python live_trader.py --once
python longbridge_cli_check.py
python trader_web.py
```

Open `http://127.0.0.1:8080` and enter the `WEB_TOKEN`.

## Longbridge CLI Verification

MCP is optional for this project. Use the official `longbridge` CLI as the
read-only external verification path:

```bash
longbridge check --format json
longbridge quote QQQ.US --format json
longbridge positions --format json
longbridge portfolio --format json
python longbridge_cli_check.py --symbol QQQ.US
```

`longbridge_cli_check.py` loads `.env`, runs only read-only CLI commands, and
prints a compact JSON summary. It does not call order submission commands.

## Live Mode

Real quotes with simulated order submission:

```bash
set QQQ_LIVE_TRADING=1
python live_trader.py --live --min-contracts 1 --max-contracts 1 --max-trades 1 --max-option-price 0.15
```

Real quotes with real order submission:

```bash
set QQQ_LIVE_TRADING=1
python live_trader.py --live --submit-live-orders --min-contracts 1 --max-contracts 1 --max-trades 1 --max-option-price 0.15
```

## Tests

```bash
python -m unittest discover -s tests
python -m py_compile trading_config.py qqq_strategy.py state_store.py longbridge_client.py live_trader.py trader_web.py watchdog.py update_gist.py backtest_v6.py longbridge_cli_check.py
```

## Files

- `qqq_strategy.py` - pure signal, option-symbol, sizing, and exit logic.
- `live_trader.py` - polling engine, state writer, dry-run/live broker routing.
- `longbridge_cli_check.py` - read-only CLI auth, quote, positions, and portfolio check.
- `trader_web.py` - Flask dashboard and JSON APIs.
- `watchdog.py` - simple restart loop for `live_trader.py`.
- `update_gist.py` - record publisher, dry-run by default.
- `backtest_v6.py` - CSV signal backtest harness.
