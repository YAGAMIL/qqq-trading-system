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
and `LONGBRIDGE_ACCESS_TOKEN`.

## Dry-Run Diagnostics

```bash
python live_trader.py --once
python longbridge_cli_check.py
python skill_check.py
python trader_web.py
```

Open `http://127.0.0.1:8080`. The local dashboard does not require a token.
Keep it bound to `127.0.0.1` unless you put it behind your own network access
control; the JSON endpoints expose runtime state and trade records.

The dashboard is Chinese-first and shows:

- `今日盈亏`: realized P/L from recorded exits, dollars.
- `收益率`: option trade return percentage, e.g. buy at `0.40` and sell at
  `0.55` = `+37.50%`.
- `下单类型`: `真实行情 + 模拟下单` means no real Longbridge order was submitted.
- `美东时间 / 北京时间`: every runtime/trade timestamp is rendered in both
  America/New_York and Asia/Shanghai for market/session review.
- `长桥订单号` / `订单状态`: real-order rows are keyed to the Longbridge order
  id. When Longbridge order detail returns `executed_qty` / `executed_price` /
  `status`, those fields override local strategy quote fields; fallback values
  are explicitly marked as local quote fallback.
- `通知状态`: optional Hermes delivery status.

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

For a fuller safe smoke test, run:

```bash
python skill_check.py
```

It checks packages, py_compile, dry-run state writing, Longbridge read-only
stock/option quotes, Longbridge CLI health, notification formatting, and Gist
credential presence, plus local safety guards for non-real-order mode, runtime
artifact inspection (including stale lock detection), and env readiness.
Weekend runs probe the next listed weekday option date instead of generating a
non-listed weekend 0DTE symbol. It never submits live orders. Add
`--send-test-notification` only when you intentionally want one Hermes message
sent to `QQQ_NOTIFY_TARGET`.

## Live Mode

Real quotes with simulated order submission. This is the normal smoke-test
mode: it reads live Longbridge quotes, writes `state.json` / `today.csv`, and
records dry-submit orders if the strategy enters, but it does not submit real
orders. With `--once`, live mode performs a single stock-quote probe so
`state.json.connected` reflects read-only Longbridge connectivity.

```bash
set QQQ_LIVE_TRADING=1
python live_trader.py --live --min-contracts 1 --max-contracts 1 --max-trades 1 --max-option-price 1.00
```

Long-running engines create `.live_trader.lock` by default. A second engine
will fail fast instead of writing the same `state.json` or submitting duplicate
signals. Use `--no-lock` only for isolated diagnostics with separate state files.

Watchdog can forward any `live_trader.py` arguments after `--`, which makes
safe smoke tests and separate state files possible:

```bash
python watchdog.py --max-restarts 1 --interval 0 -- --once --state tmp_state.json --today tmp_today.csv --records tmp_records
```

Real quotes with real order submission:

```bash
set QQQ_LIVE_TRADING=1
python live_trader.py --live --submit-live-orders --min-contracts 1 --max-contracts 1 --max-trades 1 --max-option-price 0.15
```

Use `--submit-live-orders` only when you intentionally want Longbridge orders
to be sent. Without that flag, `--live` still uses real quotes but order records
are dry-submit simulations.

In real-order mode, local strategy state keeps signal context and fallback quote
diagnostics, but order identity and order status are treated as Longbridge-owned:
records carry `longbridge_order_id`, the latest Longbridge order detail snapshot,
and source markers such as `longbridge_executed_price` or
`local_quote_fallback`.

## Hermes / Weixin Notifications

Trade notifications are optional. Hermes is not used to decide trades; the
engine still owns signal detection, position state, and exits. Hermes is used
only as a delivery bridge after a buy/sell record is written.

Enable delivery by setting a target in `.env` or the process environment:

```bash
QQQ_NOTIFY_TARGET=weixin
QQQ_NOTIFY_TIMEOUT=30
```

Other valid targets follow Hermes `send_message` format, for example
`telegram`, `discord:#测试`, or a concrete Weixin ID. If `QQQ_NOTIFY_TARGET` is
empty, no external message is sent.

## Daily Operating Flow

1. Confirm credentials and connectivity:
   ```bash
   python longbridge_cli_check.py --symbol QQQ.US
   ```
2. Start or keep running the dashboard:
   ```bash
   python trader_web.py --host 127.0.0.1 --port 8080
   ```
3. Start the engine in safe live-data mode:
   ```bash
   set QQQ_LIVE_TRADING=1
   python live_trader.py --live --min-contracts 1 --max-contracts 1 --max-trades 1 --max-option-price 1.00
   ```
4. Watch `http://127.0.0.1:8080`:
   - `Connected=yes` means live quote reads are working.
   - `Trades=0` means no accepted entry has happened yet.
   - `Last Error` explains the latest blocked candidate, such as an option
     price cap.
   - Trade rows appear only after a signal passes filters and a dry-submit or
     live order is recorded.
   - If `QQQ_NOTIFY_TARGET=weixin` is set, each recorded buy/sell also sends a
     Hermes message to Weixin.
5. Stop the engine by terminating the `live_trader.py` process. The lock file
   prevents a second engine from running at the same time.

## Tests

```bash
python -m unittest discover -s tests
python -m py_compile trading_config.py qqq_strategy.py state_store.py longbridge_client.py live_trader.py trader_web.py watchdog.py update_gist.py backtest_v6.py longbridge_cli_check.py
python skill_check.py
```

## Safe Finalization Checklist

Use this checklist for routine operation reviews where real orders and external
uploads are out of scope:

1. `python -m unittest discover -s tests -v` passes, including safety tests for
   live-order gating and Gist dry-run behavior.
2. `python -m py_compile ...` passes for all executable modules listed above.
3. `python skill_check.py --skip-live` passes locally without broker access and
   reports `safety_contract.real_order_submission=false` plus
   `safety_contract.gist_upload=false`.
4. `python skill_check.py` may be run only when Longbridge read-only quote
   checks are intended. It still does not submit orders or upload Gist records.
5. `python update_gist.py --records records` is dry-run only. A real upload
   requires both credentials and explicit `--confirm-upload`.
6. Do not run `--submit-live-orders` during diagnostics. Treat that as a
   separate, explicit production trading action.

Known external gaps should be reported separately from code health:

- Weixin/Hermes can return upstream `ret=-2` rate limits even when local
  notification formatting and command wiring are correct.
- Gist publish remains intentionally unverified unless `GIST_ID`,
  `GITHUB_TOKEN`, and explicit upload confirmation are supplied.
- Real Longbridge order submission is intentionally unverified in safe
  finalization runs.

## Files

- `qqq_strategy.py` - pure signal, option-symbol, sizing, and exit logic.
- `live_trader.py` - polling engine, state writer, dry-run/live broker routing.
- `longbridge_cli_check.py` - read-only CLI auth, quote, positions, and portfolio check.
- `skill_check.py` - safe end-to-end skill capability smoke check.
  It also reports local safety defaults, env readiness, and runtime artifact
  status without mutating state.
- `trade_notify.py` - optional Hermes `send_message` bridge for trade events.
- `trader_web.py` - Flask dashboard and JSON APIs.
- `watchdog.py` - simple restart loop for `live_trader.py`.
- `update_gist.py` - record publisher, dry-run by default.
- `backtest_v6.py` - CSV signal backtest harness.
