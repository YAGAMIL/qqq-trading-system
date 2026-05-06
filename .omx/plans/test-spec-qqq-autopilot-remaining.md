# Test Spec: QQQ autopilot remaining work

## Unit/regression tests
- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
  - Covers no-quote error handling.
  - Covers weekend option smoke date selection.
  - Covers stale lock diagnosis.
  - Covers live `run_once()` read-only quote probe.

## Static checks
- `.\.venv\Scripts\python.exe -m py_compile trading_config.py qqq_strategy.py state_store.py longbridge_client.py live_trader.py trader_web.py watchdog.py update_gist.py backtest_v6.py longbridge_cli_check.py trade_notify.py skill_check.py`
- `git diff --check`

## Safe capability checks
- `.\.venv\Scripts\python.exe skill_check.py`
  - Must return `"ok": true`.
  - Must keep `safety_contract.real_order_submission=false`.
  - Must keep `safety_contract.gist_upload=false`.
  - Must show Longbridge SDK/CLI read-only checks succeed when credentials are present.

## Runtime cleanup proof
Before touching runtime artifacts:
- Verify no `live_trader.py` or `trader_web.py` process for this repo.
- Verify no `127.0.0.1:8080` listener.

After cleanup:
- `.live_trader.lock` should be absent if the PID was stale.
- `state.json.running=false` and `state.json.connected=false` if no service is running.
- `skill_check.py` should no longer report `likely_stale_lock=true`.

## Additional smoke checks
- `.\.venv\Scripts\python.exe longbridge_cli_check.py --symbol QQQ.US --timeout 30`
- live dry-submit once using a temp state directory with `QQQ_LIVE_TRADING=1` and without `--submit-live-orders`.
- watchdog passthrough once using temp paths.
- Flask dashboard test against temp state/records.
- `.\.venv\Scripts\python.exe backtest_v6.py today.csv --output backtest-output.json`

## Review gate
- Code review final recommendation: `APPROVE`.
- Architectural status: `CLEAR`.
- No unresolved CRITICAL/HIGH/MEDIUM findings.
