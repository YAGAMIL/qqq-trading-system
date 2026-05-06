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
        from flask import Flask, Response, jsonify
    except ImportError as exc:
        raise RuntimeError("Flask is required. Install with: pip install flask") from exc

    load_env_file(".env")
    app = Flask(__name__)

    @app.get("/")
    def index():
        return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QQQ 期权交易系统</title>
  <meta name="color-scheme" content="dark">
  <style>
    :root {
      color-scheme: dark;
      --bg: #020617;
      --bg-soft: #031312;
      --panel: rgba(6, 24, 30, 0.78);
      --panel-strong: rgba(5, 46, 50, 0.82);
      --card: rgba(8, 31, 42, 0.76);
      --card-hover: rgba(13, 54, 65, 0.92);
      --line: rgba(45, 212, 191, 0.22);
      --line-strong: rgba(56, 189, 248, 0.36);
      --text: #e6fffb;
      --muted: #8bb8b1;
      --muted-2: #6b8f8c;
      --teal: #14b8a6;
      --teal-strong: #2dd4bf;
      --blue: #38bdf8;
      --green: #34d399;
      --amber: #fbbf24;
      --red: #fb7185;
      --shadow: 0 24px 80px rgba(0, 0, 0, 0.42);
      --radius-xl: 28px;
      --radius-lg: 22px;
      --radius-md: 16px;
      font-family: "Josefin Sans", Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      min-height: 100vh;
      margin: 0;
      background:
        radial-gradient(circle at 18% 12%, rgba(20, 184, 166, 0.18), transparent 34rem),
        radial-gradient(circle at 84% 8%, rgba(56, 189, 248, 0.15), transparent 30rem),
        linear-gradient(135deg, #010409 0%, var(--bg) 42%, #031716 100%);
      color: var(--text);
      letter-spacing: 0.01em;
    }

    body::before {
      position: fixed;
      inset: 0;
      z-index: -1;
      pointer-events: none;
      content: "";
      background-image:
        linear-gradient(rgba(45, 212, 191, 0.055) 1px, transparent 1px),
        linear-gradient(90deg, rgba(45, 212, 191, 0.055) 1px, transparent 1px);
      background-size: 42px 42px;
      mask-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.9), transparent 78%);
    }

    a { color: inherit; }
    button, a.action-link { cursor: pointer; }
    button, .action-link {
      border: 0;
      border-radius: 999px;
      padding: 11px 16px;
      font: inherit;
      font-weight: 700;
      text-decoration: none;
      transition: transform 180ms ease-out, border-color 180ms ease-out, background 180ms ease-out, color 180ms ease-out;
    }
    button:focus-visible, a:focus-visible {
      outline: 3px solid rgba(56, 189, 248, 0.86);
      outline-offset: 4px;
    }
    button:hover, .action-link:hover { transform: translateY(-1px); }
    button:disabled {
      cursor: not-allowed;
      opacity: 0.66;
    }
    button:disabled:hover { transform: none; }

    .skip-link {
      position: fixed;
      top: 14px;
      left: 14px;
      z-index: 20;
      transform: translateY(-160%);
      border-radius: 999px;
      padding: 10px 14px;
      background: #e6fffb;
      color: #042f2e;
      font-weight: 800;
      transition: transform 160ms ease-out;
    }
    .skip-link:focus { transform: translateY(0); }

    .page {
      width: min(1440px, calc(100% - 32px));
      margin: 0 auto;
      padding: 18px 0 40px;
    }

    .topbar {
      position: sticky;
      top: 14px;
      z-index: 10;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 10px 12px 10px 18px;
      background: rgba(2, 13, 18, 0.72);
      box-shadow: 0 14px 40px rgba(0, 0, 0, 0.28);
      backdrop-filter: blur(18px);
    }
    .brand {
      display: inline-flex;
      align-items: center;
      min-width: 0;
      gap: 12px;
      font-weight: 800;
      white-space: nowrap;
    }
    .brand-mark {
      display: grid;
      width: 34px;
      height: 34px;
      place-items: center;
      border: 1px solid rgba(45, 212, 191, 0.5);
      border-radius: 12px;
      background: linear-gradient(135deg, rgba(20, 184, 166, 0.24), rgba(56, 189, 248, 0.08));
      box-shadow: inset 0 0 18px rgba(45, 212, 191, 0.2);
    }
    .brand-mark svg { width: 20px; height: 20px; }
    .topbar-meta {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid rgba(139, 184, 177, 0.24);
      border-radius: 999px;
      padding: 7px 10px;
      background: rgba(255, 255, 255, 0.035);
      color: var(--muted);
      white-space: nowrap;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--muted-2);
      box-shadow: 0 0 18px currentColor;
    }
    .dot.ok { background: var(--green); color: var(--green); }
    .dot.warn { background: var(--amber); color: var(--amber); }
    .dot.bad { background: var(--red); color: var(--red); }

    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.75fr);
      gap: 18px;
      align-items: stretch;
      margin-bottom: 18px;
    }
    .hero-main, .side-panel, .section-panel, .status-panel {
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      background: linear-gradient(145deg, rgba(7, 25, 34, 0.86), rgba(3, 19, 18, 0.74));
      box-shadow: var(--shadow);
      backdrop-filter: blur(20px);
    }
    .hero-main {
      position: relative;
      overflow: hidden;
      min-height: 360px;
      padding: clamp(24px, 4vw, 48px);
    }
    .hero-main::after {
      position: absolute;
      right: -90px;
      bottom: -120px;
      width: 360px;
      height: 360px;
      border: 1px solid rgba(45, 212, 191, 0.18);
      border-radius: 999px;
      content: "";
      background: radial-gradient(circle, rgba(20, 184, 166, 0.22), transparent 64%);
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 22px;
      border: 1px solid rgba(45, 212, 191, 0.24);
      border-radius: 999px;
      padding: 8px 12px;
      background: rgba(20, 184, 166, 0.08);
      color: var(--teal-strong);
      font-size: 13px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }
    h1 {
      max-width: 860px;
      margin: 0;
      font-family: "Microsoft YaHei UI", "Segoe UI", Inter, ui-sans-serif, system-ui, sans-serif;
      font-size: clamp(34px, 4.2vw, 60px);
      line-height: 1.08;
      letter-spacing: -0.035em;
      text-wrap: balance;
    }
    h1 span { display: block; }
    .title-code {
      color: #f2fffc;
      font-family: "Segoe UI", Inter, ui-sans-serif, system-ui, sans-serif;
      letter-spacing: -0.055em;
    }
    .hero-copy {
      max-width: 720px;
      margin: 20px 0 0;
      color: #b6d7d2;
      font-size: clamp(17px, 2vw, 22px);
      line-height: 1.55;
    }
    .actions {
      position: relative;
      z-index: 1;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 28px;
    }
    .primary-action {
      background: linear-gradient(135deg, var(--teal), var(--blue));
      color: #001312;
      box-shadow: 0 12px 34px rgba(20, 184, 166, 0.22);
    }
    .secondary-action {
      border: 1px solid rgba(139, 184, 177, 0.25);
      background: rgba(255, 255, 255, 0.045);
      color: var(--text);
    }
    .mini-strip {
      position: relative;
      z-index: 1;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 26px;
    }

    .side-panel {
      display: grid;
      gap: 14px;
      padding: 18px;
    }
    .signal-card {
      border: 1px solid rgba(56, 189, 248, 0.18);
      border-radius: var(--radius-lg);
      padding: 18px;
      background: rgba(2, 14, 20, 0.58);
    }
    .signal-card h2, .section-title h2 {
      margin: 0;
      font-size: 13px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .signal-card strong {
      display: block;
      margin-top: 10px;
      color: var(--text);
      font-size: 28px;
      line-height: 1.1;
      overflow-wrap: anywhere;
    }
    .signal-card p {
      margin: 10px 0 0;
      color: var(--muted);
      line-height: 1.45;
    }
    .sparkline {
      min-height: 158px;
      border: 1px solid rgba(45, 212, 191, 0.14);
      border-radius: var(--radius-lg);
      padding: 14px;
      background: rgba(3, 14, 18, 0.58);
    }
    .sparkline svg { display: block; width: 100%; height: 104px; }
    .sparkline .empty {
      display: grid;
      min-height: 104px;
      place-items: center;
      color: var(--muted);
      text-align: center;
    }

    .content-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(300px, 0.34fr);
      gap: 18px;
      align-items: start;
    }
    .section-panel, .status-panel { padding: 18px; }
    .section-title {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 16px;
    }
    .section-title p {
      margin: 6px 0 0;
      color: var(--muted);
      line-height: 1.45;
    }
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .metric-card {
      min-height: 128px;
      border: 1px solid rgba(139, 184, 177, 0.16);
      border-radius: var(--radius-lg);
      padding: 16px;
      background: var(--card);
      transition: transform 180ms ease-out, background 180ms ease-out, border-color 180ms ease-out;
    }
    .metric-card:hover {
      transform: translateY(-2px);
      border-color: var(--line-strong);
      background: var(--card-hover);
    }
    .metric-card.wide { grid-column: span 2; }
    .metric-card.ok { border-color: rgba(52, 211, 153, 0.3); }
    .metric-card.warn { border-color: rgba(251, 191, 36, 0.34); }
    .metric-card.bad { border-color: rgba(251, 113, 133, 0.34); }
    .metric-label {
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }
    .metric-value {
      color: var(--text);
      font-size: clamp(21px, 2.3vw, 31px);
      font-weight: 800;
      line-height: 1.05;
      overflow-wrap: anywhere;
    }
    .metric-detail {
      margin-top: 10px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
    }
    .metric-card.ok .metric-value { color: var(--green); }
    .metric-card.warn .metric-value { color: var(--amber); }
    .metric-card.bad .metric-value { color: var(--red); }

    .status-panel {
      display: grid;
      gap: 14px;
      margin-bottom: 18px;
    }
    .status-copy {
      border-radius: var(--radius-lg);
      padding: 16px;
      background: rgba(255, 255, 255, 0.045);
      color: var(--muted);
      line-height: 1.55;
    }
    .bad { color: var(--red); }
    .ok { color: var(--green); }
    .warn { color: var(--amber); }
    .muted { color: var(--muted); }
    .subline { display: block; margin-top: 4px; color: var(--muted-2); font-size: 12px; }

    .table-panel {
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      background: rgba(4, 18, 25, 0.78);
      box-shadow: var(--shadow);
    }
    .table-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid rgba(139, 184, 177, 0.14);
      padding: 16px 18px;
    }
    .table-wrap { overflow-x: auto; }
    table {
      width: 100%;
      min-width: 1120px;
      border-collapse: collapse;
    }
    th, td {
      border-bottom: 1px solid rgba(139, 184, 177, 0.12);
      padding: 14px 12px;
      text-align: left;
      vertical-align: top;
    }
    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: rgba(3, 16, 22, 0.96);
      color: #b9d8d4;
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    td { color: #e2f7f4; }
    tbody tr:hover { background: rgba(20, 184, 166, 0.055); }
    .time-cell span { display: block; white-space: nowrap; }
    .day-row td {
      border-bottom-color: rgba(45, 212, 191, 0.22);
      padding: 16px 18px;
      background: linear-gradient(90deg, rgba(20, 184, 166, 0.15), rgba(56, 189, 248, 0.035));
    }
    .day-heading {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
    }
    .day-title {
      color: var(--text);
      font-size: 18px;
      font-weight: 900;
      letter-spacing: 0.02em;
    }
    .day-meta {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
    }
    .day-meta .pill { font-size: 12px; }
    .empty-row td {
      padding: 22px;
      color: var(--muted);
      text-align: center;
    }
    .trade-side {
      display: inline-flex;
      border-radius: 999px;
      padding: 5px 9px;
      background: rgba(56, 189, 248, 0.1);
      color: var(--blue);
      font-weight: 800;
      white-space: nowrap;
    }
    .trade-side.sell {
      background: rgba(251, 191, 36, 0.1);
      color: var(--amber);
    }

    @media (max-width: 1180px) {
      .hero, .content-grid { grid-template-columns: 1fr; }
      .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    }
    @media (max-width: 760px) {
      .page { width: min(100% - 20px, 720px); padding-top: 10px; }
      .topbar {
        position: static;
        align-items: flex-start;
        border-radius: 24px;
        flex-direction: column;
      }
      .topbar-meta { justify-content: flex-start; }
      .hero-main { min-height: auto; padding: 24px; }
      .metric-grid { grid-template-columns: 1fr; }
      .metric-card.wide { grid-column: auto; }
      .section-title, .table-toolbar { align-items: flex-start; flex-direction: column; }
      .day-heading { align-items: flex-start; flex-direction: column; }
      .day-meta { justify-content: flex-start; }
      .actions { flex-direction: column; }
      button, .action-link { width: 100%; text-align: center; }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        scroll-behavior: auto !important;
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
      }
      button:hover, .action-link:hover, .metric-card:hover { transform: none; }
    }
  </style>
</head>
<body>
<a class="skip-link" href="#content">跳到主要内容</a>
<div class="page">
  <nav class="topbar" aria-label="Dashboard navigation">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" role="img">
          <path d="M4 15.5 8.6 11l3.2 3.2L20 6" stroke="#2dd4bf" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M4 19h16" stroke="#38bdf8" stroke-width="2.2" stroke-linecap="round"/>
        </svg>
      </span>
      <span>QQQ 0DTE Command Center</span>
    </div>
    <div class="topbar-meta" aria-label="Safety metadata">
      <span class="pill"><span class="dot ok"></span>本地仪表盘 · 无需 token</span>
      <span class="pill">仅建议绑定 127.0.0.1</span>
      <span class="pill" id="updatedStamp">等待刷新</span>
    </div>
  </nav>

  <header class="hero" id="content">
    <section class="hero-main" aria-labelledby="page-title">
      <div class="eyebrow"><span class="dot ok"></span>Risk-first options cockpit</div>
      <h1 id="page-title" aria-label="QQQ 0DTE 期权交易系统"><span class="title-code">QQQ 0DTE</span><span>期权交易系统</span></h1>
      <p class="hero-copy">
        面向实盘监控的深色高对比指挥台：优先显示运行校验、风控拦截、持仓与最近订单，
        用最少扫视成本确认系统是否安全、在线、可追溯。
      </p>
      <div class="actions" aria-label="Primary actions">
        <button class="primary-action" id="refreshButton" type="button">刷新状态</button>
        <a class="action-link secondary-action" href="/api/state">查看状态 JSON</a>
        <a class="action-link secondary-action" href="/api/trades">查看交易记录 JSON</a>
      </div>
      <div class="mini-strip" id="summaryStrip" aria-label="Runtime summary">
        <span class="pill"><span class="dot warn"></span>20 秒自动刷新</span>
        <span class="pill">真实下单需外部安全开关</span>
      </div>
    </section>

    <aside class="side-panel" aria-label="Live signal and profit trend">
      <section class="signal-card" id="heroSignal">
        <h2>当前信号</h2>
        <strong>读取中</strong>
        <p>正在读取运行状态...</p>
      </section>
      <section class="sparkline" aria-labelledby="sparkline-title">
        <div class="section-title">
          <div>
            <h2 id="sparkline-title">PNL 轨迹</h2>
            <p>最近交易的累计盈亏线。</p>
          </div>
        </div>
        <div id="pnlChart" aria-live="polite"></div>
      </section>
    </aside>
  </header>

  <main class="content-grid">
    <section class="section-panel" aria-labelledby="overview-title">
      <div class="section-title">
        <div>
          <h2 id="overview-title">运行概览</h2>
          <p>关键运行、行情、风控与通知状态。</p>
        </div>
      </div>
      <div class="metric-grid" id="cards"></div>
    </section>

    <aside class="status-panel" aria-labelledby="status-title">
      <div class="section-title">
        <div>
          <h2 id="status-title">安全状态</h2>
          <p>状态文件、进程锁与交易记录的综合提示。</p>
        </div>
      </div>
      <div class="status-copy" id="status" role="status" aria-live="polite">正在读取运行状态...</div>
    </aside>
  </main>

  <section class="table-panel" aria-labelledby="trades-title">
    <div class="table-toolbar">
      <div class="section-title">
        <div>
          <h2 id="trades-title">执行流水</h2>
          <p>按美股交易日（America/New_York）收纳展示最近记录，含每日盈亏、胜负和订单状态。</p>
        </div>
      </div>
      <span class="pill" id="tradeCount">暂无交易记录</span>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>美东时间 / 北京时间</th>
            <th>动作</th>
            <th>合约</th>
            <th>数量</th>
            <th>价格</th>
            <th>盈亏</th>
            <th>收益率</th>
            <th>原因</th>
            <th>下单类型</th>
            <th>长桥订单号</th>
            <th>订单状态</th>
          </tr>
        </thead>
        <tbody id="trades"></tbody>
      </table>
    </div>
  </section>
</div>
<script>
const cards = document.getElementById('cards');
const trades = document.getElementById('trades');
const status = document.getElementById('status');
const heroSignal = document.getElementById('heroSignal');
const pnlChart = document.getElementById('pnlChart');
const refreshButton = document.getElementById('refreshButton');
const summaryStrip = document.getElementById('summaryStrip');
const tradeCount = document.getElementById('tradeCount');
const updatedStamp = document.getElementById('updatedStamp');
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
const toneClass = {ok: 'ok', warn: 'warn', bad: 'bad', neutral: ''};
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
function marketDateKey(value) {
  if (!value) return '未知交易日';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '未知交易日';
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(date).reduce((acc, part) => {
    acc[part.type] = part.value;
    return acc;
  }, {});
  return `${parts.year}-${parts.month}-${parts.day}`;
}
function marketDayLabel(key) {
  if (key === '未知交易日') return key;
  const date = new Date(`${key}T12:00:00-04:00`);
  const weekday = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'America/New_York',
    weekday: 'short'
  }).format(date);
  return `${key} · ${weekday}`;
}
function shortTime(value, timeZone = 'Asia/Shanghai') {
  if (!value) return '-';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '-';
  return fmtTime(date, timeZone);
}
function stateAge(value) {
  if (!value) return {text: '未知', tone: 'warn'};
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return {text: '无法解析', tone: 'warn'};
  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (minutes < 2) return {text: '刚刚更新', tone: 'ok'};
  if (minutes < 60) return {text: `约 ${minutes} 分钟前`, tone: minutes > 5 ? 'warn' : 'ok'};
  const hours = Math.round(minutes / 60);
  if (hours < 48) return {text: `约 ${hours} 小时前`, tone: 'warn'};
  return {text: `约 ${Math.round(hours / 24)} 天前`, tone: 'warn'};
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
  return Number.isFinite(n) ? `$${n.toFixed(2)}` : escapeHtml(value);
}
function signalText(signal) {
  if (!signal) return '<span class="muted">等待信号</span>';
  const kind = signalKindLabel[signal.kind] || signal.kind || '-';
  const direction = directionLabel[signal.direction] || signal.direction || '-';
  return `${escapeHtml(kind)} ${escapeHtml(direction)}`;
}
function positionText(position) {
  if (!position) return '<span class="muted">无持仓</span>';
  const direction = directionLabel[position.direction] || position.direction || '-';
  return `${escapeHtml(position.option_symbol || '-')}<span class="subline">${escapeHtml(direction)} · ${escapeHtml(position.remaining_quantity ?? '-')}/${escapeHtml(position.quantity ?? '-')} 张 · 成本 ${price(position.entry_opt_price)} · 最高浮盈 ${pct(position.max_profit_pct)}</span>`;
}
function notifyText(notification) {
  if (!notification) return '<span class="muted">未启用</span>';
  if (notification.ok) return `已发送到 ${escapeHtml(notification.target || '-')}`;
  return `发送失败：${escapeHtml(notification.error || '未知错误')}`;
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
  return escapeHtml(trade.longbridge_order_id || trade.order_id || order.longbridge_order_id || order.order_id || detail.order_id || '-');
}
function orderStatus(trade) {
  const order = trade.order || {};
  const detail = order.longbridge_order || {};
  return escapeHtml(trade.order_status || detail.status || (order.dry_submit ? '模拟提交' : order.dry_run ? '模拟' : '-'));
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
  return `${escapeHtml(source)} · ${escapeHtml(id)}${escapeHtml(statusText)}`;
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
function groupTradesByMarketDate(data) {
  const grouped = new Map();
  for (const trade of data) {
    const key = marketDateKey(trade.timestamp);
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(trade);
  }
  return Array.from(grouped.entries())
    .map(([date, rows]) => ({
      date,
      rows: rows.slice().sort((a, b) => new Date(a.timestamp || 0) - new Date(b.timestamp || 0))
    }))
    .sort((a, b) => b.date.localeCompare(a.date));
}
function summarizeDay(rows) {
  const sells = rows.filter(t => t.side === 'Sell');
  const pnl = sells.reduce((sum, t) => sum + Number(t.pnl || 0), 0);
  const wins = sells.filter(t => Number(t.pnl || 0) > 0).length;
  const losses = sells.filter(t => Number(t.pnl || 0) < 0).length;
  const buys = rows.filter(t => t.side === 'Buy').length;
  const modes = Array.from(new Set(rows.map(t => modeLabel[t.mode] || t.mode).filter(Boolean)));
  return {pnl, wins, losses, buys, sells: sells.length, modes};
}
function renderTradeRow(t) {
  const side = sideLabel[t.side] || t.side || '-';
  const sideClass = t.side === 'Sell' ? 'trade-side sell' : 'trade-side';
  return `<tr><td class="time-cell">${dualTime(t.timestamp)}</td><td><span class="${sideClass}">${escapeHtml(side)}</span></td><td>${escapeHtml(t.symbol || '')}</td><td>${escapeHtml(t.quantity || '')}</td><td>${orderPrice(t)}</td><td>${t.pnl === undefined ? '-' : money(t.pnl)}</td><td>${pct(t.pnl_pct)}</td><td>${escapeHtml(reasonLabel[t.reason] || t.reason || '-')}</td><td>${escapeHtml(modeLabel[t.mode] || t.mode || '-')}</td><td>${orderId(t)}</td><td>${orderStatus(t)}</td></tr>`;
}
function renderDayGroup(group) {
  const summary = summarizeDay(group.rows);
  const tone = pnlTone(summary.pnl);
  const meta = [
    `${group.rows.length} 条流水`,
    `${summary.buys} 买 / ${summary.sells} 卖`,
    `胜负 ${summary.wins}/${summary.losses}`,
    summary.modes.join('、') || '未知模式'
  ];
  return `<tr class="day-row"><td colspan="11"><div class="day-heading"><div><div class="day-title">${escapeHtml(marketDayLabel(group.date))}</div><div class="${toneClass[tone]}">当日已实现 ${money(summary.pnl)}</div></div><div class="day-meta">${meta.map(item => `<span class="pill">${escapeHtml(item)}</span>`).join('')}</div></div></td></tr>${group.rows.slice().reverse().map(renderTradeRow).join('')}`;
}
function renderGroupedTrades(data) {
  if (data.length === 0) {
    trades.innerHTML = '<tr class="empty-row"><td colspan="11">暂无交易记录。</td></tr>';
    return [];
  }
  const groups = groupTradesByMarketDate(data);
  trades.innerHTML = groups.map(renderDayGroup).join('');
  return groups;
}
function pnlTone(value) {
  const n = Number(value || 0);
  if (n > 0) return 'ok';
  if (n < 0) return 'bad';
  return 'neutral';
}
function healthTone(state) {
  if (state.runtime_warning || state.last_error || stateAge(state.updated).tone === 'warn') return 'warn';
  if (state.running && state.connected) return 'ok';
  if (state.connected || state.running) return 'warn';
  return 'neutral';
}
function renderMetric(item) {
  const cls = ['metric-card', toneClass[item.tone || 'neutral'], item.wide ? 'wide' : ''].filter(Boolean).join(' ');
  const detail = item.detail ? `<div class="metric-detail">${item.detail}</div>` : '';
  return `<article class="${cls}"><p class="metric-label">${escapeHtml(item.label)}</p><div class="metric-value">${item.value}</div>${detail}</article>`;
}
function renderSummary(state, data) {
  const tone = healthTone(state);
  const mode = modeLabel[state.mode] || state.mode || '-';
  summaryStrip.innerHTML = [
    `<span class="pill"><span class="dot ${toneClass[tone]}"></span>${escapeHtml(mode)}</span>`,
    `<span class="pill">今日 ${escapeHtml(state.trades_today || 0)} 次开仓</span>`,
    `<span class="pill">${escapeHtml(data.length)} 条本地记录</span>`,
    '<span class="pill">20 秒自动刷新</span>'
  ].join('');
}
function renderHeroSignal(state) {
  const tone = healthTone(state);
  const signal = signalText(state.last_signal);
  const runtime = runtimeText(state);
  heroSignal.innerHTML = `<h2>当前信号</h2><strong>${signal}</strong><p><span class="dot ${toneClass[tone]}"></span> ${escapeHtml(runtime)} · 最新错误：${escapeHtml(state.last_error || '无')}</p>`;
}
function renderPnlChart(data) {
  const pnlTrades = data.filter(t => t.pnl !== undefined && Number.isFinite(Number(t.pnl))).slice(-24);
  if (pnlTrades.length === 0) {
    pnlChart.innerHTML = '<div class="empty">暂无交易记录。产生卖出记录后会显示累计盈亏曲线。</div>';
    return;
  }
  let total = 0;
  const values = pnlTrades.map(t => {
    total += Number(t.pnl || 0);
    return total;
  });
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0);
  const span = max - min || 1;
  const points = values.map((value, index) => {
    const x = pnlTrades.length === 1 ? 50 : (index / (pnlTrades.length - 1)) * 100;
    const y = 88 - ((value - min) / span) * 76;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(' ');
  const zeroY = 88 - ((0 - min) / span) * 76;
  pnlChart.innerHTML = `<svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="最近交易累计盈亏曲线"><line x1="0" y1="${zeroY.toFixed(2)}" x2="100" y2="${zeroY.toFixed(2)}" stroke="rgba(139,184,177,.28)" stroke-width="1"/><polyline points="${points}" fill="none" stroke="#2dd4bf" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><polyline points="${points} 100,100 0,100" fill="rgba(20,184,166,.11)" stroke="none"/></svg><span class="${total >= 0 ? 'ok' : 'bad'}">累计 ${money(total)}</span>`;
}
async function load() {
  refreshButton.disabled = true;
  refreshButton.textContent = '刷新中...';
  const s = await fetch('/api/state');
  if (!s.ok) throw new Error('状态接口请求失败');
  const state = await s.json();
  const r = await fetch('/api/trades');
  if (!r.ok) throw new Error('交易记录接口请求失败');
  const data = enrichTrades(await r.json());
  const mode = modeLabel[state.mode] || state.mode || '-';
  const age = stateAge(state.updated);
  const runtimeWarning = state.runtime_warning
    ? `<span class="warn">运行状态校验：${escapeHtml(state.runtime_warning)}</span><br>`
    : '';
  renderSummary(state, data);
  renderHeroSignal(state);
  renderPnlChart(data);
  updatedStamp.textContent = `更新时间 ${shortTime(state.updated)}`;
  const groups = groupTradesByMarketDate(data);
  tradeCount.textContent = data.length ? `${groups.length} 个交易日 · ${data.length} 条记录` : '暂无交易记录';
  cards.innerHTML = [
    {label: '运行模式', value: escapeHtml(mode), detail: '安全档位与下单边界', tone: state.mode === 'live' ? 'bad' : state.mode === 'live-dry-submit' ? 'warn' : 'neutral'},
    {label: '行情连接', value: state.connected ? '已连接' : '未连接', detail: 'Longbridge 行情连接状态', tone: state.connected ? 'ok' : 'warn'},
    {label: '引擎状态', value: state.running ? '运行中' : '已停止', detail: '来自状态文件与锁校验', tone: state.running ? 'ok' : 'neutral'},
    {label: '运行校验', value: escapeHtml(runtimeText(state)), detail: '检查 live_trader 锁与 PID', tone: state.runtime_warning ? 'warn' : state.running ? 'ok' : 'neutral'},
    {label: '状态新鲜度', value: escapeHtml(age.text), detail: 'state.json 快照更新时间', tone: age.tone},
    {label: 'K线数量', value: escapeHtml(state.candle_count ?? 0), detail: '本轮可用行情样本'},
    {label: '今日开仓', value: `${escapeHtml(state.trades_today || 0)} 次`, detail: '当日入场计数'},
    {label: '今日盈亏', value: money(state.daily_pnl), detail: '本地记录聚合', tone: pnlTone(state.daily_pnl)},
    {label: '胜 / 负', value: `${escapeHtml(state.wins_today || 0)} / ${escapeHtml(state.losses_today || 0)}`, detail: '日内交易结果'},
    {label: '当前持仓', value: positionText(state.position), detail: '合约、方向、数量与成本', wide: true, tone: state.position ? 'warn' : 'neutral'},
    {label: '最新信号', value: signalText(state.last_signal), detail: '突破或反转路径', wide: true},
    {label: '最近订单', value: lastOrderText(state.last_order), detail: '长桥或本地模拟订单', wide: true},
    {label: '通知状态', value: notifyText(state.last_notification), detail: 'Hermes / Weixin 通知结果', wide: true, tone: state.last_notification && !state.last_notification.ok ? 'warn' : 'neutral'},
    {label: '最新错误', value: escapeHtml(state.last_error || '无'), detail: '风控拦截或运行异常', wide: true, tone: state.last_error ? 'warn' : 'ok'},
    {label: '更新时间', value: dualTime(state.updated), detail: '同时展示美东与北京时间', wide: true}
  ].map(renderMetric).join('');
  if (data.length === 0) {
    status.innerHTML = state.last_error
      ? `${runtimeWarning}<span class="bad">暂无交易记录。最新候选入场被风控拦截：${escapeHtml(state.last_error)}</span>`
      : `${runtimeWarning}<span class="muted">暂无交易记录。引擎正在等待满足全部过滤条件的信号。</span>`;
    renderGroupedTrades(data);
    refreshButton.disabled = false;
    refreshButton.textContent = '刷新状态';
    return;
  }
  const dry = state.mode === 'live-dry-submit';
  const renderedGroups = renderGroupedTrades(data);
  status.innerHTML = `${runtimeWarning}<span class="${dry ? 'warn' : 'ok'}">已按 ${renderedGroups.length} 个美股交易日收纳 ${data.length} 条交易记录。${dry ? '当前是模拟下单：真实行情会跑策略，但不会向长桥发送真实订单。' : '真实订单以长桥订单号和长桥订单详情为准；如长桥详情暂不可得，会标记本地报价回退。'}</span>`;
  refreshButton.disabled = false;
  refreshButton.textContent = '刷新状态';
}
function handleLoadError(err) {
  status.innerHTML = `<span class="bad">${escapeHtml(err.message)}</span>`;
  refreshButton.disabled = false;
  refreshButton.textContent = '刷新状态';
}
refreshButton.addEventListener('click', () => load().catch(handleLoadError));
load().catch(handleLoadError);
setInterval(() => load().catch(handleLoadError), 20000);
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

    @app.get("/favicon.ico")
    def favicon():
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="#031312"/><path d="M14 42h36" stroke="#38bdf8" stroke-width="5" stroke-linecap="round"/><path d="M16 35l10-10 8 7 14-16" stroke="#2dd4bf" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
        return Response(svg, mimetype="image/svg+xml")

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
