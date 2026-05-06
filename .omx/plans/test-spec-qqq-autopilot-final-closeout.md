# Test Spec: QQQ autopilot final closeout

## Verification commands
- .\.venv\Scripts\python.exe -m unittest discover -s tests -q
- .\.venv\Scripts\python.exe skill_check.py
- .\.venv\Scripts\python.exe longbridge_cli_check.py --symbol QQQ.US --timeout 30
- git push origin main then git status --short --branch
- Safe startup: 	rader_web.py --host 127.0.0.1 --port 8080 and live_trader.py --live --min-contracts 1 --max-contracts 1 --max-trades 1 --max-option-price 1.00, with QQQ_LIVE_TRADING=1 but without --submit-live-orders.
- Runtime proof: process list, port 8080 listener, /api/state, /api/trades, .live_trader.lock.

## Real-order gate
Real-order verification is not pass/fail for Autopilot because it requires a precise user-approved order ticket and financial risk acceptance.
