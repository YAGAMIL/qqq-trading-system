"""Flask dashboard for the QQQ trading engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from live_trader import is_process_running
from state_store import load_env_file, read_state
from trading_config import web_config


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


def _read_lock_pid(lock_path: str | Path) -> int | None:
    try:
        data = json.loads(Path(lock_path).read_text(encoding="utf-8"))
        return int(data.get("pid"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _runtime_checked_state(state: dict, lock_path: str | Path, process_checker=is_process_running) -> dict:
    checked = dict(state)
    lock = Path(lock_path)
    lock_pid = _read_lock_pid(lock) if lock.exists() else None
    lock_process_running = process_checker(lock_pid) if lock_pid is not None else False
    engine_reported_running = bool(checked.get("running"))
    stale_running_state = engine_reported_running and not lock_process_running
    checked["engine_reported_running"] = engine_reported_running
    checked["runtime_status"] = {
        "lock_exists": lock.exists(),
        "lock_pid": lock_pid,
        "lock_process_running": lock_process_running,
        "stale_running_state": stale_running_state,
    }
    if stale_running_state:
        checked["running"] = False
        checked["runtime_warning"] = (
            "state.json reports running=true, but no active live_trader lock/process was found"
        )
    else:
        checked["runtime_warning"] = None
    return checked


def create_app(
    state_path: str | Path = "state.json",
    records_dir: str | Path = "records",
    lock_path: str | Path = ".live_trader.lock",
    process_checker=is_process_running,
):
    try:
        from flask import Flask, jsonify
    except ImportError as exc:
        raise RuntimeError("Flask is required. Install with: pip install flask") from exc

    load_env_file(".env")
    app = Flask(__name__)

    @app.get("/")
    def index():
        return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QQQ 期权交易系统</title>
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
    .wide { grid-column: 1 / -1; }
    .muted { color: #9fb0bd; }
    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    th, td { border-bottom: 1px solid #2c3640; padding: 10px; text-align: left; }
    .bad { color: #ff8f8f; } .ok { color: #85e89d; }
    .warn { color: #ffd166; }
    .small { font-size: 13px; line-height: 1.5; }
    .time-cell span, .subline { display: block; }
  </style>
</head>
<body>
<main>
  <header>
    <h1>QQQ 0DTE 期权交易系统</h1>
    <div class="muted">本地仪表盘 · 无需 token · 仅建议绑定 127.0.0.1</div>
  </header>
  <section class="grid" id="cards"></section>
  <section class="card wide small" id="status">正在读取运行状态...</section>
  <table><thead><tr><th>美东时间 / 北京时间</th><th>动作</th><th>合约</th><th>数量</th><th>价格</th><th>盈亏</th><th>收益率</th><th>原因</th><th>下单类型</th><th>长桥订单号</th><th>订单状态</th></tr></thead><tbody id="trades"></tbody></table>
</main>
<script>
const cards = document.getElementById('cards');
const trades = document.getElementById('trades');
const status = document.getElementById('status');
const sideLabel = {Buy: '买入', Sell: '卖出'};
const reasonLabel = {
  stop_loss: '止损',
  timeout: '持仓超时',
  partial_take_profit: '分批止盈',
  trailing_take_profit: '回撤止盈'
};
const modeLabel = {
  'dry-run': '离线模拟',
  'live-dry-submit': '真实行情 + 模拟下单',
  live: '真实下单'
};
const signalKindLabel = {breakout: '突破', reversal: '反转'};
const directionLabel = {call: '看涨 Call', put: '看跌 Put'};
function fmtTime(date, timeZone) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false
  }).format(date);
}
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}
function dualTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return escapeHtml(value);
  return `<span>美东 ${fmtTime(date, 'America/New_York')}</span><span class="muted">北京 ${fmtTime(date, 'Asia/Shanghai')}</span>`;
}
function money(value) {
  const n = Number(value || 0);
  const sign = n > 0 ? '+' : '';
  return `${sign}$${n.toFixed(2)}`;
}
function pct(value) {
  if (value === undefined || value === null || value === '') return '-';
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  const sign = n > 0 ? '+' : '';
  return `${sign}${(n * 100).toFixed(2)}%`;
}
function price(value) {
  if (value === undefined || value === null || value === '') return '-';
  const n = Number(value);
  return Number.isFinite(n) ? `$${n.toFixed(2)}` : String(value);
}
function signalText(signal) {
  if (!signal) return '-';
  return `${signalKindLabel[signal.kind] || signal.kind || '-'} ${directionLabel[signal.direction] || signal.direction || '-'}`;
}
function positionText(position) {
  if (!position) return '无持仓';
  return `${position.option_symbol} · ${directionLabel[position.direction] || position.direction} · ${position.remaining_quantity}/${position.quantity} 张 · 成本 ${price(position.entry_opt_price)} · 最高浮盈 ${pct(position.max_profit_pct)}`;
}
function notifyText(notification) {
  if (!notification) return '未启用';
  if (notification.ok) return `已发送到 ${notification.target || '-'}`;
  return `发送失败：${notification.error || '未知错误'}`;
}
function runtimeText(state) {
  const runtime = state.runtime_status || {};
  if (state.runtime_warning) return '状态文件陈旧 · 未发现 live_trader 进程';
  if (state.running && runtime.lock_process_running) return `进程在线 · PID ${runtime.lock_pid || '-'}`;
  if (state.running) return '运行中';
  return '未运行';
}
function orderId(trade) {
  const order = trade.order || {};
  const detail = order.longbridge_order || {};
  return trade.longbridge_order_id || trade.order_id || order.longbridge_order_id || order.order_id || detail.order_id || '-';
}
function orderStatus(trade) {
  const order = trade.order || {};
  const detail = order.longbridge_order || {};
  return trade.order_status || detail.status || (order.dry_submit ? '模拟提交' : order.dry_run ? '模拟' : '-');
}
function orderPrice(trade) {
  const rendered = price(trade.price);
  if (trade.price_source === 'local_quote_fallback') {
    return `${rendered}<span class="subline muted">本地报价回退</span>`;
  }
  if ((trade.price_source || '').startsWith('longbridge_')) {
    return `${rendered}<span class="subline muted">长桥订单</span>`;
  }
  return rendered;
}
function lastOrderText(order) {
  if (!order) return '无';
  const id = order.order_id || '-';
  const source = order.source === 'longbridge' ? '长桥' : order.source || '-';
  const statusText = order.status ? ` · ${order.status}` : '';
  return `${source} · ${id}${statusText}`;
}
function enrichTrades(data) {
  const entries = {};
  return data.map(t => {
    const copy = {...t};
    const symbol = copy.symbol || '';
    if (copy.side === 'Buy') entries[symbol] = copy;
    if (copy.side === 'Sell' && copy.pnl_pct === undefined) {
      const entry = entries[symbol];
      if (entry && entry.price && copy.pnl !== undefined) {
        const cost = Number(entry.price) * Number(copy.quantity || 0) * 100;
        if (cost > 0) copy.pnl_pct = Number(copy.pnl) / cost;
      }
    }
    return copy;
  });
}
async function load() {
  const s = await fetch('/api/state');
  if (!s.ok) throw new Error('状态接口请求失败');
  const state = await s.json();
  const r = await fetch('/api/trades');
  if (!r.ok) throw new Error('交易记录接口请求失败');
  const data = enrichTrades(await r.json());
  const mode = modeLabel[state.mode] || state.mode || '-';
  const runtimeWarning = state.runtime_warning
    ? `<span class="warn">运行状态校验：${escapeHtml(state.runtime_warning)}</span><br>`
    : '';
  cards.innerHTML = [
    ['运行模式', mode],
    ['行情连接', state.connected ? '已连接' : '未连接'],
    ['引擎状态', state.running ? '运行中' : '已停止'],
    ['运行校验', runtimeText(state)],
    ['K线数量', state.candle_count],
    ['今日开仓', `${state.trades_today || 0} 次`],
    ['今日盈亏', money(state.daily_pnl)],
    ['胜 / 负', `${state.wins_today || 0} / ${state.losses_today || 0}`],
    ['当前持仓', positionText(state.position)],
    ['最新信号', signalText(state.last_signal)],
    ['最近订单', lastOrderText(state.last_order)],
    ['最新错误', state.last_error || '无'],
    ['通知状态', notifyText(state.last_notification)],
    ['更新时间', dualTime(state.updated)]
  ].map(([k,v]) => `<div class="card"><div class="label">${k}</div><div class="value">${v}</div></div>`).join('');
  if (data.length === 0) {
    status.innerHTML = state.last_error
      ? `${runtimeWarning}<span class="bad">暂无交易记录。最新候选入场被风控拦截：${state.last_error}</span>`
      : `${runtimeWarning}<span class="muted">暂无交易记录。引擎正在等待满足全部过滤条件的信号。</span>`;
    trades.innerHTML = '<tr><td colspan="11" class="muted">暂无交易记录。</td></tr>';
    return;
  }
  const dry = state.mode === 'live-dry-submit';
  status.innerHTML = `${runtimeWarning}<span class="${dry ? 'warn' : 'ok'}">已加载 ${data.length} 条交易记录。${dry ? '当前是模拟下单：真实行情会跑策略，但不会向长桥发送真实订单。' : '真实订单以长桥订单号和长桥订单详情为准；如长桥详情暂不可得，会标记本地报价回退。'}</span>`;
  trades.innerHTML = data.slice(-50).reverse().map(t => `<tr><td class="time-cell">${dualTime(t.timestamp)}</td><td>${sideLabel[t.side] || t.side || '-'}</td><td>${t.symbol || ''}</td><td>${t.quantity || ''}</td><td>${orderPrice(t)}</td><td>${t.pnl === undefined ? '-' : money(t.pnl)}</td><td>${pct(t.pnl_pct)}</td><td>${reasonLabel[t.reason] || t.reason || '-'}</td><td>${modeLabel[t.mode] || t.mode || '-'}</td><td>${orderId(t)}</td><td>${orderStatus(t)}</td></tr>`).join('');
}
load().catch(err => { status.innerHTML = `<span class="bad">${err.message}</span>`; });
setInterval(() => load().catch(err => { status.innerHTML = `<span class="bad">${err.message}</span>`; }), 20000);
</script>
</body>
</html>
"""

    @app.get("/api/state")
    def api_state():
        state = read_state(state_path)
        return jsonify(_runtime_checked_state(state, lock_path, process_checker))

    @app.get("/api/trades")
    def api_trades():
        return jsonify(_load_records(records_dir))

    @app.get("/api/config")
    def api_config():
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
    parser.add_argument("--lock-file", default=".live_trader.lock")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = create_app(args.state, args.records, lock_path=args.lock_file)
    app.run(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
