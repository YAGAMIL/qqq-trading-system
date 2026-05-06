# PRD: QQQ autopilot remaining work

## Objective
Finish all remaining safe, reversible work for the QQQ trading system after the prior smoke-path improvements.

## Scope
- Preserve the non-real-order safety boundary.
- Make stale runtime state visible and safe to clean.
- Clean current stale local runtime artifacts only after proving no live project process is running.
- Verify the full local and read-only Longbridge path.
- Review the code diff and finish with a clean merge-readiness verdict.

## Non-goals
- No real Longbridge order submission.
- No Gist upload.
- No Hermes/Weixin test send.
- No service restart unless separately requested.

## Acceptance criteria
1. `omx state list-active --json` reports no incompatible active `team` state before Autopilot proceeds.
2. `skill_check.py` reports stale locks with PID/process evidence.
3. Weekend `skill_check.py` does not fail by generating non-listed weekend 0DTE option symbols.
4. `live_trader.py --live --once` performs a read-only quote probe and reports `connected=true` when Longbridge quote succeeds.
5. Local stale runtime state is corrected only when no `live_trader.py`/`trader_web.py` process and no port 8080 listener are present.
6. Unit tests, py_compile, `skill_check.py`, Longbridge CLI, live-dry-submit once, watchdog smoke, web smoke, and backtest all pass.
7. Code review verdict is `APPROVE` with architectural status `CLEAR`.

## Constraints
- Use `.venv\Scripts\python.exe`; bare `python` is the WindowsApps alias on this host.
- Do not pass `--submit-live-orders`.
- Do not pass `--confirm-upload`.
- Do not send Hermes notifications.

## Decision
Implement only durable diagnostics and safe runtime cleanup. Treat real orders, real Gist publish, and Hermes delivery as explicit external gates, not unfinished local work.

## Handoff to Ralph
Ralph should:
1. Finish any missing regression tests around stale lock detection and live-once quote probing.
2. Clean the stale local lock/state after process/port verification.
3. Run the full verification stack.
4. Produce evidence for code review.
