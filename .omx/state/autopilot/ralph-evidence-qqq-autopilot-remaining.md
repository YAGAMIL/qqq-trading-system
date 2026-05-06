# Ralph Evidence: QQQ autopilot remaining work

## Implementation completed
- Cleared incompatible stale OMX `team` mode via `omx state clear --input '{"mode":"team","all_sessions":true}' --json`; active modes are now empty.
- Created Autopilot context snapshot and PRD/test-spec handoff artifacts.
- Added weekend-safe option smoke selection in `skill_check.py`.
- Added explicit no-quote handling in `longbridge_client.py`.
- Added live `--once` read-only stock quote probe in `live_trader.py`.
- Added stale lock PID/process diagnostics in `skill_check.py`.
- Added regression coverage for the above.
- Updated README/SKILL operational docs.
- Added `logs/` to `.gitignore`.
- Cleaned local stale runtime artifacts after process/port proof:
  - no matching `live_trader.py`/`trader_web.py` process
  - no port 8080 listener
  - backed up state/lock to `logs/`
  - removed `.live_trader.lock`
  - set `state.json.running=false` and `state.json.connected=false`

## Verification evidence
- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` -> Ran 43 tests, OK.
- `.\.venv\Scripts\python.exe -m py_compile ... skill_check.py` -> OK.
- `git diff --check` -> OK.
- `.\.venv\Scripts\python.exe skill_check.py` -> `ok=true`; `likely_stale_lock=false`; Longbridge SDK/CLI read-only checks OK.
- `.\.venv\Scripts\python.exe longbridge_cli_check.py --symbol QQQ.US --timeout 30` -> token valid, global/cn true, QQQ quote OK.
- `QQQ_LIVE_TRADING=1 .\.venv\Scripts\python.exe live_trader.py --live --once ...` -> `mode=live-dry-submit`, `connected=true`, `last_error=null`; no `--submit-live-orders`.
- `.\.venv\Scripts\python.exe watchdog.py --max-restarts 1 --interval 0 -- --once ...` -> wrote dry-run state successfully.
- Flask dashboard temp smoke -> `/health=true`, `/api/state` symbol `QQQ.US`, `/api/trades` empty, root HTTP 200.
- `.\.venv\Scripts\python.exe backtest_v6.py today.csv --output backtest-output.json` -> `bars=2097`, `trade_events=8`, `pnl=109.26000000000326`.
- `.\.venv\Scripts\python.exe update_gist.py --records records` -> dry-run only, `2 files ready`, no upload.

## Explicitly not run
- Real Longbridge order submission (`--submit-live-orders`) was not run.
- Gist upload (`--confirm-upload`) was not run.
- Hermes/Weixin send was not run.
