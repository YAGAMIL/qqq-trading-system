# QQQ 0DTE 期权自动交易系统 — 完整开源方案

> 基于长桥Python SDK，全自动交易QQQ 0DTE虚值期权。回测761笔/2.3年，胜率75.8%，年化354.8%。

---

## 目录

1. [策略概述](#1-策略概述)
2. [核心逻辑](#2-核心逻辑)
3. [系统架构](#3-系统架构)
4. [代码实现](#4-代码实现)
5. [回测结果](#5-回测结果)
6. [部署指南](#6-部署指南)
7. [参数说明](#7-参数说明)
8. [踩坑记录](#8-踩坑记录)
9. [常见问题](#9-常见问题)

---

## 1. 策略概述

### 策略类型
- **标的**: QQQ 0DTE（当日到期）虚值期权
- **方向**: 双向交易（做多Call + 做空Put）
- **信号**: 1分钟K线突破 + 衰竭反转
- **频率**: 每20秒检测一次

### 核心思路

```
趋势突破（顺势）: 价格突破前N根K线高/低点 → 跟随趋势
衰竭反转（逆势）: 从日内高低点回落 → 抄底/逃顶
```

### 风控体系

| 风控项 | 设置 |
|--------|------|
| 止损 | 25%（期权价格） |
| 动态止盈 | 盈利100%平半仓，峰值回撤30%全平 |
| 超时 | 15根K线（15分钟） |
| 日最大交易 | 8笔 |
| 日亏损熔断 | 5% |

---

## 2. 核心逻辑

### 2.1 双信号路径

系统同时运行两条信号路径，互不干扰：

**路径一：趋势突破（顺势）**
```
条件：
1. 当前收盘价 > 前5根1分钟K线最高价 → 做多Call
2. 当前收盘价 < 前5根1分钟K线最低价 → 做空Put

过滤（4层）：
1. SMA20趋势：做多价格>SMA20，做空<SMA20
2. 量能确认：当前量 ≥ 20均量 × 0.8
3. 动量确认：当前K线同向（阳线做多/阴线做空）
4. K线实体：实体 ≥ 0.03%
```

**路径二：衰竭反转（逆势）**
```
超跌反弹（做多）：
1. 从当日最高价跌 ≥ 0.2%
2. 最近完成的K线收阳
3. 反弹实体 ≥ 0.1%

超涨回调（做空）：
1. 从当日最低价涨 ≥ 0.2%
2. 最近完成的K线收阴
3. 回调实体 ≥ 0.1%

限制：每天最多1次反转信号
```

### 2.2 动态止盈逻辑

```
1. 止损 25% → 全部平仓
2. 盈利 ≥100% → 平仓一半（锁定利润）
3. 继续持有，追踪最高盈利
4. 从最高盈利回撤 ≥30% → 全部平仓
5. 超时 15根K线 → 全部平仓
```

### 2.3 期权合约生成

```python
from zoneinfo import ZoneInfo
from datetime import datetime

TZ_ET = ZoneInfo("America/New_York")

def get_option_symbol(stock_price, direction, offset=2.0):
    """
    生成期权合约代码
    例: QQQ=$653.82, call → QQQ260422C656000.US
    """
    now_et = datetime.now(TZ_ET)  # 必须用美东时间！
    
    if direction == 'call':
        strike = round(stock_price + offset)
        option_type = 'C'
    else:
        strike = round(stock_price - offset)
        option_type = 'P'
    
    expiry = now_et.strftime('%y%m%d')
    return f"QQQ{expiry}{option_type}{strike * 1000:06d}.US"
```

**注意**:
- 必须有 `.US` 后缀
- 行权价取整到$1
- 到期日用美东时间（HKT跨日会生成错误合约）

---

## 3. 系统架构

### 3.1 双进程架构

```
┌─────────────────┐     state.json     ┌─────────────────┐
│  live_trader.py │ ←────────────────→ │  trader_web.py  │
│  (交易引擎)      │                    │  (Web仪表盘)     │
└────────┬────────┘                    └────────┬────────┘
         │                                      │
         ├──→ today.csv (K线数据)               │
         ├──→ records/*.json (交易记录)          │
         └──→ state.json (实时状态) ←───────────┘
```

### 3.2 文件说明

| 文件 | 说明 |
|------|------|
| `live_trader.py` | 核心交易引擎：信号检测 + 下单 + 持仓监控 |
| `trader_web.py` | Web仪表盘：Flask + HTML/CSS |
| `update_gist.py` | 同步交易记录到GitHub Gist |
| `watchdog.py` | 守护进程：自动启动 + 崩溃重启 |
| `.env` | API密钥配置（不入库） |

### 3.3 数据流

```
长桥API → 1分钟K线推送 → 信号检测 → 下单 → 持仓监控 → 平仓
    ↓
state.json → Web仪表盘实时显示
    ↓
records/*.json → 历史交易记录
```

---

## 4. 代码实现

### 4.1 核心配置

```python
CONFIG = {
    'symbol': 'QQQ.US',
    # 策略参数
    'sl': 0.25,               # 止损 25%
    'tp': 0.30,               # 止盈 30%（旧逻辑兼容）
    'lookback': 5,            # 突破窗口（5根1分钟K线）
    # 动态止盈
    'tp_partial_pct': 1.00,   # 盈利100%平仓一半
    'tp_trail_drop': 0.30,    # 峰值回撤30%全平
    # 期权参数
    'option_offset': 2.0,     # 行权价偏移±$2
    'min_contracts': 10,      # 最小张数
    'contract_multiplier': 100,
    # 资金管理
    'pos_pct': 2,             # 单笔仓位2%
    'max_trades': 8,          # 日最大交易
    'daily_limit': 5,         # 日亏损熔断5%
    # 交易窗口（美东时间）
    'start_time': '09:35',
    'end_time': '15:50',
    # 过滤参数
    'max_gap': 0.0020,        # 跳空过滤0.20%
    'vol_mult': 0.8,          # 量能倍数
    'min_body': 0.0003,       # K线实体0.03%
    # 衰竭反转
    'reversal_drop': 0.002,   # 反转触发0.2%
    'reversal_bounce': 0.001, # 反转确认0.1%
    # 检测频率
    'check_interval': 20,     # 20秒检测一次
}
```

### 4.2 信号检测核心

```python
def _check_breakout(self, bar, cur_min):
    """全过滤双向突破信号检测"""
    cs = self.one_min_candles
    lb = self.cfg['lookback']
    
    # 计算前N根K线的高低点（不含当前！）
    upper = max(c['high'] for c in cs[-lb-1:-1])
    lower = min(c['low'] for c in cs[-lb-1:-1])
    entry_price = bar['close']
    
    sig = None
    
    # 向上突破：做多Call
    if entry_price > upper:
        gap = (entry_price - upper) / upper
        if gap < self.cfg['max_gap']:
            sig = {'dir': 'call', 'price': entry_price}
    
    # 向下突破：做空Put
    elif entry_price < lower:
        gap = (lower - entry_price) / lower
        if gap < self.cfg['max_gap']:
            sig = {'dir': 'put', 'price': entry_price}
    
    if not sig:
        return
    
    # 4层过滤
    sma_ok = self._check_sma20(sig, entry_price)
    vol_ok = self._check_volume()
    mom_ok = self._check_momentum(sig, bar)
    body_ok = self._check_body(bar)
    
    if not (sma_ok and vol_ok and mom_ok and body_ok):
        return
    
    # 所有过滤通过，执行交易
    self._execute_trade(sig)
```

### 4.3 持仓监控

```python
def _check_position(self):
    """检查持仓状态（每20秒调用）"""
    if not self.position:
        return
    
    pos = self.position
    
    # 获取期权当前价格
    try:
        opt_quotes = self.quote_ctx.quote([pos['opt_symbol']])
        opt_price = float(opt_quotes[0].last_done)
    except:
        # BS公式估算
        opt_price = self._bs_estimate(pos)
    
    # 计算盈亏
    entry_opt = pos.get('entry_opt_price') or 1.0
    pnl_pct = (opt_price - entry_opt) / entry_opt * 100
    pos['max_pnl_pct'] = max(pos['max_pnl_pct'], pnl_pct)
    
    # 退出条件
    if pnl_pct <= -25:  # 止损
        self._close_position("止损")
    elif not pos['half_closed'] and pnl_pct >= 100:  # 盈利100%平半仓
        self._close_partial("动态止盈")
        pos['half_closed'] = True
    elif pos['half_closed'] and pos['max_pnl_pct'] >= 100:
        drawdown = pos['max_pnl_pct'] - pnl_pct
        if drawdown >= 30:  # 峰值回撤30%全平
            self._close_position("动态止盈")
```

### 4.4 期权下单

```python
def _execute_trade(self, sig):
    """执行期权交易"""
    opt_symbol = get_option_symbol(sig['price'], sig['dir'])
    contracts = self.cfg['min_contracts']
    
    # 开仓：不管Call还是Put，都是Buy
    side = OrderSide.Buy
    
    resp = self.trade_ctx.submit_order(
        symbol=opt_symbol,
        order_type=OrderType.MO,
        side=side,
        submitted_quantity=Decimal(str(contracts)),
        time_in_force=TimeInForceType.Day,
        outside_rth=OutsideRTH.AnyTime,
    )
    
    # 获取期权入场价
    time.sleep(1)
    opt_q = self.quote_ctx.quote([opt_symbol])
    if opt_q and opt_q[0].last_done > 0:
        self.position['entry_opt_price'] = float(opt_q[0].last_done)
```

---

## 5. 回测结果

### 5.1 最终回测（v6 vol_mult=0.8）

| 指标 | 数值 |
|------|------|
| 总交易 | 761笔 / 2.3年 |
| 胜率 | 75.8% |
| 总收益 | +3111.31% |
| 年化收益 | 354.8% |
| 最大回撤 | 25.19% |
| 退出分布 | 76%止盈 / 24%止损 |
| 平均盈利 | +6.35% |
| 平均亏损 | -3.00% |

### 5.2 版本演进

| 版本 | 核心变化 | 结果 |
|------|---------|------|
| v4 | 衰竭反转+VWAP | +0.21%, 51.5%胜率 |
| v5 | 修复3个bug | +0.25%, 100%胜率(3笔) |
| v6 | 双向突破+全过滤 | +3111%, 75.8%胜率 |
| v6.1 | 正股→期权+20秒轮询 | 实盘验证中 |

### 5.3 信号过滤漏斗

```
突破信号触发      → 24746 次
↓ 时间窗口（09:35-15:50）
时间窗口通过      →  3535 次  (14.3%)
↓ 跳空过滤
跳空过滤通过      →  3464 次  (98.0%)
↓ SMA20趋势
SMA20通过        →  3450 次  (99.6%)
↓ 量能（≥0.8×均量）
量能通过          →  1205 次  (~70%)
↓ 动量（1根同向）
动量通过          →   ~900 次  (~75%)
↓ K线实体
K线实体通过       →   761 次
```

### 5.4 参数调优

**lookback调优**:

| lookback | 窗口 | 效果 |
|----------|------|------|
| 30根 | 30分钟 | ❌ 上轨太远，稳步上涨不触发 |
| 10根 | 10分钟 | ⚠️ 能触发但反应慢 |
| **5根** | **5分钟** | ✅ 最佳平衡 |

**vol_mult调优**:

| vol_mult | 信号数 | 通过率 | 胜率 |
|----------|--------|--------|------|
| 1.2 | ~454 | 34.9% | 75.8% |
| 1.0 | ~600 | ~55% | ~74% |
| **0.8** | **761** | **~70%** | **75.8%** |

---

## 6. 部署指南

### 6.1 环境要求

- Python 3.10+
- Linux/WSL（Windows原生不推荐）
- 长桥API密钥（美股期权权限）

### 6.2 安装依赖

```bash
pip install longbridge flask numpy scipy
```

### 6.3 配置密钥

创建 `.env` 文件：

```bash
LONGPORT_APP_KEY=你的APP_KEY
LONGPORT_APP_SECRET=你的APP_SECRET
LONGPORT_ACCESS_TOKEN=你的ACCESS_TOKEN
```

### 6.4 启动系统

```bash
# 启动交易引擎
PYTHONUNBUFFERED=1 python live_trader.py &

# 启动Web仪表盘
PYTHONUNBUFFERED=1 python trader_web.py &

# 或用watchdog守护
python watchdog.py
```

### 6.5 验证启动

```bash
# 检查进程
ps aux | grep -E 'live_trader|trader_web'

# 检查state.json
python -c "import json; d=json.load(open('state.json')); print(f'K线:{d[\"candle_count\"]}')"
```

---

## 7. 参数说明

### 7.1 策略核心

| 参数 | 值 | 说明 |
|------|-----|------|
| `symbol` | QQQ.US | 交易标的 |
| `sl` | 0.25 | 止损25% |
| `lookback` | 5 | 突破窗口5根K线 |
| `option_offset` | 2.0 | 行权价偏移±$2 |

### 7.2 动态止盈

| 参数 | 值 | 说明 |
|------|-----|------|
| `tp_partial_pct` | 1.00 | 盈利100%平半仓 |
| `tp_trail_drop` | 0.30 | 峰值回撤30%全平 |

### 7.3 过滤参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `vol_mult` | 0.8 | 量能≥20均量×0.8 |
| `min_body` | 0.0003 | K线实体≥0.03% |
| `max_gap` | 0.0020 | 跳空过滤0.20% |

### 7.4 资金管理

| 参数 | 值 | 说明 |
|------|-----|------|
| `pos_pct` | 2 | 单笔仓位2% |
| `max_trades` | 8 | 日最大交易 |
| `daily_limit` | 5 | 日亏损熔断5% |

---

## 8. 踩坑记录

### 8.1 时区问题（最致命）

长桥API返回的时间戳是 **HKT(UTC+8)**，不是美东！

```python
from zoneinfo import ZoneInfo
TZ_ET = ZoneInfo("America/New_York")

now = datetime.now()  # HKT
et_now = now.astimezone(TZ_ET)
cur_min_et = et_now.hour * 60 + et_now.minute
```

### 8.2 索引边界

突破检测必须用 **前N根K线（不含当前）**：

```python
# 正确
upper = max(c['high'] for c in cs[-lb-1:-1])

# 错误（包含当前K线，永远不触发突破）
upper = max(c['high'] for c in cs[-lb:])
```

### 8.3 期权下单方向

```python
# 开仓：Buy（买入期权付出权利金）
# 平仓：Sell（卖出期权收回权利金）
# 不管Call还是Put，方向都是一样的！
```

### 8.4 PushCandlestick结构

```python
# 错误：candle.open → AttributeError被SDK静默吞掉
# 正确：
cs = candle.candlestick
if not candle.is_confirmed:
    return
bar = {'open': cs.open, 'high': cs.high, ...}
```

### 8.5 entry_opt_price

下单后必须获取期权成交价，否则PnL计算永远为0：

```python
time.sleep(1)
opt_q = self.quote_ctx.quote([opt_symbol])
if opt_q and opt_q[0].last_done > 0:
    self.position['entry_opt_price'] = float(opt_q[0].last_done)
```

---

## 9. 常见问题

### Q: 为什么实盘没有信号？

检查清单：
1. state.json的candle_count是否>0
2. 当前时间是否在交易窗口内（美东09:35-15:50）
3. 是否有持仓阻塞（position不为None）
4. 索引是否正确（cs[-lb-1:-1]）

### Q: 期权下单失败？

检查：
1. 期权合约代码格式是否正确（.US后缀+整数行权价）
2. 到期日是否用美东时间生成
3. 账户是否有期权交易权限

### Q: Web仪表盘401错误？

检查：
1. 访问URL是否带了token参数
2. token是否与代码中的API_TOKEN一致

### Q: 如何回测？

```bash
# 使用回测脚本
python backtest_v6.py

# 回测参数在脚本顶部的CFG字典中修改
```

### Q: 如何修改策略参数？

1. 修改 `live_trader.py` 中的 CONFIG
2. 同步修改 `trader_web.py` 中的 CONFIG
3. 重启两个进程

---

## 开源地址

GitHub: https://github.com/1797346220/qqq-trading-system

---

## 免责声明

本系统仅供学习研究使用。期权交易具有高风险，可能导致本金损失。作者不对使用本系统产生的任何损失负责。请在充分了解风险的前提下谨慎使用。

---

## 联系方式

如有问题或建议，欢迎在GitHub提Issue或PR。
