"""Flask dashboard for the QQQ trading engine."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from state_store import load_env_file, read_state
from trading_config import web_config


API_TOKEN = os.environ.get("WEB_TOKEN") or os.environ.get("API_TOKEN") or "changeme"


def _load_records(records_dir: str | Path = "records") -> list[dict]:
    directory = Path(records_dir)
    if not directory.exists():
        return []
    records: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            records.extend(payload)
    return records


def create_app(
    state_path: str | Path = "state.json",
    records_dir: str | Path = "records",
    api_token: str | None = None,
):
    try:
        from flask import Flask, jsonify, request
    except ImportError as exc:
        raise RuntimeError("Flask is required. Install with: pip install flask") from exc

    load_env_file(".env")
    token = api_token or os.environ.get("WEB_TOKEN") or os.environ.get("API_TOKEN") or API_TOKEN
    app = Flask(__name__)

    def authorized() -> bool:
        return request.args.get("token") == token or request.headers.get("X-API-Token") == token

    @app.get("/")
    def index():
        return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QQQ Trading</title>
  <style>
    :root { color-scheme: light dark; font-family: Arial, sans-serif; }
    body { margin: 0; background: #101418; color: #eef2f5; }
    main { max-width: 1100px; margin: 0 auto; padding: 24px; }
    header { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
    h1 { font-size: 24px; margin: 0; letter-spacing: 0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 20px; }
    .card { border: 1px solid #2c3640; border-radius: 8px; padding: 14px; background: #151b21; }
    .label { color: #9fb0bd; font-size: 12px; text-transform: uppercase; }
    .value { font-size: 24px; margin-top: 6px; overflow-wrap: anywhere; }
    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    th, td { border-bottom: 1px solid #2c3640; padding: 10px; text-align: left; }
    input, button { height: 36px; border-radius: 6px; border: 1px solid #394650; padding: 0 10px; }
    button { background: #2a6df4; color: white; border: 0; }
    .bad { color: #ff8f8f; } .ok { color: #85e89d; }
  </style>
</head>
<body>
<main>
  <header>
    <h1>QQQ Trading</h1>
    <form id="auth"><input id="token" placeholder="token"><button>Load</button></form>
  </header>
  <section class="grid" id="cards"></section>
  <table><thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>PnL</th></tr></thead><tbody id="trades"></tbody></table>
</main>
<script>
const cards = document.getElementById('cards');
const trades = document.getElementById('trades');
async function load(token) {
  const s = await fetch('/api/state?token=' + encodeURIComponent(token));
  if (!s.ok) throw new Error('unauthorized');
  const state = await s.json();
  const r = await fetch('/api/trades?token=' + encodeURIComponent(token));
  const data = await r.json();
  cards.innerHTML = [
    ['Mode', state.mode],
    ['Connected', state.connected ? 'yes' : 'no'],
    ['Running', state.running ? 'yes' : 'no'],
    ['Candles', state.candle_count],
    ['Trades', state.trades_today],
    ['Daily PnL', Number(state.daily_pnl || 0).toFixed(2)],
    ['Position', state.position ? state.position.option_symbol : '-'],
    ['Updated', state.updated || '-']
  ].map(([k,v]) => `<div class="card"><div class="label">${k}</div><div class="value">${v}</div></div>`).join('');
  trades.innerHTML = data.slice(-50).reverse().map(t => `<tr><td>${t.timestamp || ''}</td><td>${t.symbol || ''}</td><td>${t.side || ''}</td><td>${t.quantity || ''}</td><td>${t.price || ''}</td><td>${t.pnl || ''}</td></tr>`).join('');
}
document.getElementById('auth').addEventListener('submit', e => {
  e.preventDefault();
  load(document.getElementById('token').value).catch(err => alert(err.message));
});
</script>
</body>
</html>
"""

    @app.get("/api/state")
    def api_state():
        if not authorized():
            return jsonify({"error": "unauthorized"}), 401
        return jsonify(read_state(state_path))

    @app.get("/api/trades")
    def api_trades():
        if not authorized():
            return jsonify({"error": "unauthorized"}), 401
        return jsonify(_load_records(records_dir))

    @app.get("/api/config")
    def api_config():
        if not authorized():
            return jsonify({"error": "unauthorized"}), 401
        return jsonify(web_config())

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QQQ trading dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--state", default="state.json")
    parser.add_argument("--records", default="records")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = create_app(args.state, args.records)
    app.run(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
