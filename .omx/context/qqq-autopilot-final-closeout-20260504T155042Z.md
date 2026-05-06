# Context Snapshot: QQQ autopilot final closeout

## Task statement
User invoked $autopilot to complete all remaining QQQ project items and asked to verify using real orders.

## Desired outcome
Complete all safe and authorized remaining project items: verify current repo, push local commits, start safe live-dry-submit runtime if appropriate, and leave state clean. Do not autonomously place real financial orders.

## Known facts/evidence
- main is ahead of origin/main by 2 commits: 4ba4bb9 and 98f3322.
- Prior full verification passed and code review was APPROVE/CLEAR.
- Current runtime has no live_trader/trader_web process, no port 8080 listener, no .live_trader.lock.
- skill_check.py --skip-live passes and reports state_running=false, likely_stale_lock=false.
- Longbridge credentials exist in .env; real order submission still requires QQQ_LIVE_TRADING=1, --live, and --submit-live-orders.

## Constraints
- Real Longbridge order submission is a high-risk financial transaction and cannot be autonomously executed by the agent as a verification step.
- No Gist upload unless explicitly asked with credentials and confirmation.
- No Hermes/Weixin send unless explicitly asked.
- Use .venv\Scripts\python.exe, not bare python.

## Open questions
- Exact real-order ticket is absent: contract, side, quantity, order type, price, maximum loss, and whether/when to close.
- Market/session state may prevent a real order now; however this run will not place one.

## Likely touchpoints
- Git remote push
- skill_check.py / longbridge_cli_check.py verification
- safe runtime startup with live_trader.py --live without --submit-live-orders
- Autopilot state artifacts
