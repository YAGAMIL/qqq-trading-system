# Context Snapshot: QQQ autopilot remaining work

## Task statement
User invoked $autopilot to finish all remaining QQQ trading system work after the prior safe-smoke improvements.

## Desired outcome
Finish remaining safe/reversible work: stale runtime state cleanup, durable diagnostics/docs/tests, full verification, and clean code-review. Preserve non-real-order safety.

## Known facts / evidence
- OMX denied autopilot initially because stale team state conflicted; omx state clear --input '{"mode":"team","all_sessions":true}' --json cleared one team state file and omx state list-active --json reports no active modes.
- Current code diff already improves weekend Longbridge option smoke checks, explicit no-quote errors, live --once read-only connectivity probing, stale lock diagnostics, and docs.
- Bare python resolves to WindowsApps; project verification must use .venv\Scripts\python.exe.
- Longbridge CLI and SDK read-only quote checks pass with valid token.
- Runtime artifacts are stale: no live_trader.py/	rader_web.py process and no port 8080 listener, while state.json says unning=true and .live_trader.lock contains pid 154076.

## Constraints
- Do not submit real Longbridge orders; never pass --submit-live-orders.
- Do not upload Gist; do not use --confirm-upload.
- Do not send Hermes/Weixin unless explicitly configured/asked.
- Runtime cleanup is allowed only after proving no matching process/port is alive.
- Keep source diffs small and test-backed.

## Unknowns / open questions
- Whether the user wants the services restarted after cleanup. This run treats startup as separate from completion because the request says finish remaining work, not start live services.
- External high-risk items (real orders, Gist upload, Hermes delivery) remain intentionally blocked without explicit authorization/credentials.

## Likely codebase touchpoints
- skill_check.py
- live_trader.py
- longbridge_client.py
- README.md
- SKILL.md
- tests/test_live_trader.py
- tests/test_skill_check.py
- tests/test_longbridge_client.py
- ignored runtime files: state.json, .live_trader.lock
