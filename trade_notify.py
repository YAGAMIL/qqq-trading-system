"""Optional Hermes notification adapter for trade events."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any


SIDE_LABELS = {
    "Buy": "买入",
    "Sell": "卖出",
}

REASON_LABELS = {
    "stop_loss": "止损",
    "timeout": "持仓超时",
    "partial_take_profit": "分批止盈",
    "trailing_take_profit": "回撤止盈",
}

MODE_LABELS = {
    "dry-run": "离线模拟",
    "live-dry-submit": "真实行情 + 模拟下单",
    "live": "真实下单",
}


def format_money(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    sign = "+" if number > 0 else ""
    return f"{sign}${number:.2f}"


def format_pct(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    sign = "+" if number > 0 else ""
    return f"{sign}{number * 100:.2f}%"


def _signal_label(signal: dict[str, Any] | None) -> str:
    if not signal:
        return "-"
    kind = {"breakout": "突破", "reversal": "反转"}.get(str(signal.get("kind")), signal.get("kind", "-"))
    direction = {"call": "看涨 Call", "put": "看跌 Put"}.get(
        str(signal.get("direction")), signal.get("direction", "-")
    )
    return f"{kind} {direction}"


def format_trade_message(trade: dict[str, Any]) -> str:
    side = SIDE_LABELS.get(str(trade.get("side")), str(trade.get("side", "-")))
    mode = MODE_LABELS.get(str(trade.get("mode")), str(trade.get("mode", "-")))
    order = trade.get("order", {}) if isinstance(trade.get("order"), dict) else {}
    order_kind = "模拟成交" if order.get("dry_submit") or order.get("dry_run") else "真实成交"
    title = f"【QQQ交易系统】{order_kind}：{side}"

    lines = [
        title,
        f"合约：{trade.get('symbol', '-')}",
        f"数量：{trade.get('quantity', '-')}",
        f"价格：${float(trade.get('price', 0)):.2f}" if trade.get("price") is not None else "价格：-",
        f"模式：{mode}",
        f"时间：{trade.get('timestamp', '-')}",
    ]

    if trade.get("pnl") is not None:
        lines.append(f"盈亏：{format_money(trade.get('pnl'))}")
    if trade.get("pnl_pct") is not None:
        lines.append(f"收益率：{format_pct(trade.get('pnl_pct'))}")
    if trade.get("reason"):
        lines.append(f"原因：{REASON_LABELS.get(str(trade.get('reason')), trade.get('reason'))}")
    if isinstance(trade.get("signal"), dict):
        lines.append(f"信号：{_signal_label(trade.get('signal'))}")

    return "\n".join(lines)


def send_hermes_message(target: str, message: str, timeout: int = 30) -> dict[str, Any]:
    payload = {
        "target": target,
        "message": message,
    }
    command = [
        "wsl",
        "-e",
        "bash",
        "-lc",
        (
            "cd /root/.hermes/hermes-agent && "
            "set -a; [ -f /root/.hermes/.env ] && . /root/.hermes/.env; set +a; "
            "venv/bin/python -c 'import json,sys; "
            "from tools.send_message_tool import send_message_tool; "
            "print(send_message_tool(json.load(sys.stdin)))'"
        ),
    ]
    result = subprocess.run(
        command,
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        return {
            "ok": False,
            "target": target,
            "error": (result.stderr or result.stdout).strip(),
        }
    text = result.stdout.strip()
    try:
        response = json.loads(text)
    except json.JSONDecodeError:
        response = {"raw": text}
    if isinstance(response, dict) and response.get("error"):
        return {"ok": False, "target": target, "error": response["error"]}
    return {"ok": True, "target": target, "response": response}


def notify_trade_if_configured(
    trade: dict[str, Any],
    env: dict | os._Environ = os.environ,
) -> dict[str, Any] | None:
    target = (env.get("QQQ_NOTIFY_TARGET") or env.get("TRADE_NOTIFY_TARGET") or "").strip()
    if not target:
        return None
    try:
        timeout = int(env.get("QQQ_NOTIFY_TIMEOUT", "30"))
    except ValueError:
        timeout = 30
    message = format_trade_message(trade)
    return send_hermes_message(target, message, timeout=timeout)
