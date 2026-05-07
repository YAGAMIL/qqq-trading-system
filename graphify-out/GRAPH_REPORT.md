# Graph Report - .  (2026-05-07)

## Corpus Check
- Corpus is ~16,020 words - fits in a single context window. You may not need a graph.

## Summary
- 319 nodes · 684 edges · 16 communities (15 shown, 1 thin omitted)
- Extraction: 63% EXTRACTED · 31% INFERRED · 0% AMBIGUOUS · INFERRED: 212 edges (avg confidence: 0.68)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 15|Community 15]]

## God Nodes (most connected - your core abstractions)
1. `LiveTrader` - 36 edges
2. `PositionState` - 31 edges
3. `DrySubmitBroker` - 29 edges
4. `SingleInstanceLock` - 24 edges
5. `FakeQuoteBroker` - 22 edges
6. `BarBuilder` - 21 edges
7. `LongbridgeBroker` - 20 edges
8. `write_state()` - 15 edges
9. `QuoteSnapshot` - 15 edges
10. `main()` - 14 edges

## Surprising Connections (you probably didn't know these)
- `create_app()` --calls--> `load_env_file()`  [INFERRED]
  trader_web.py → state_store.py
- `notification_check()` --calls--> `format_trade_message()`  [INFERRED]
  skill_check.py → trade_notify.py
- `notification_check()` --calls--> `notify_trade_if_configured()`  [INFERRED]
  skill_check.py → trade_notify.py
- `run_check()` --calls--> `load_env_file()`  [INFERRED]
  longbridge_cli_check.py → state_store.py
- `main()` --calls--> `load_env_file()`  [INFERRED]
  live_trader.py → state_store.py

## Hyperedges (group relationships)
- **hyperedge:live_safety_contract** — module:live_trader_py, safety:triple_live_order_gate, safety:longbridge_order_authority, safety:read_only_longbridge_checks, safety:gist_upload_gate, safety:dashboard_local_binding [INFERRED]
- **hyperedge:p0_signal_correctness_findings** — review:today_csv_cross_day_pollution, review:barbuilder_cumulative_volume, review:pre_market_bars_affect_strategy, review:barbuilder_skips_empty_minutes, strategy:dual_signal_v61, artifact:today_csv [INFERRED]
- **hyperedge:order_state_integrity_findings** — review:position_written_before_fill, review:order_detail_single_fetch, review:running_state_not_cleared_on_crash, review:stale_state_lock, safety:longbridge_order_authority, artifact:state_json, artifact:live_trader_lock [INFERRED]
- **hyperedge:documentation_drift_cluster** — stale_doc:skill_path_placeholder, stale_doc:skill_pushcandlestick_polling_mismatch, stale_doc:skill_config_sync_mismatch, stale_doc:deployment_token_auth_mismatch, stale_doc:deployment_nohup_syntax, stale_doc:dependency_numpy_scipy_unused, stale_doc:config_missing_safety_params, stale_doc:readme_windows_set, stale_doc:dead_config [INFERRED]

## Communities (16 total, 1 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.1
Nodes (20): BarBuilder, DrySubmitBroker, LiveTrader, parse_hhmm(), QuoteSnapshot, Use a real quote broker but record orders without submitting them., Exclusive lock file used to prevent duplicate trading engines., SingleInstanceLock (+12 more)

### Community 1 - "Community 1"
Cohesion: 0.1
Nodes (19): is_current_trading_day(), main(), parse_args(), public_config(), append_today_bar(), atomic_write_json(), default_state(), load_today_bars() (+11 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (37): .live_trader.lock, records/*.json, state.json, today.csv, backtest_v6.py, live_trader.py, longbridge_cli_check.py, longbridge_client.py (+29 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (13): Protocol, Broker, build_broker(), DryRunBroker, LongbridgeBroker, QuoteSnapshot, Longbridge SDK adapter.  The adapter is imported only when live trading is expli, _serialize_order() (+5 more)

### Community 4 - "Community 4"
Cohesion: 0.12
Nodes (26): live_trading_allowed(), dry_run_once(), env_readiness(), fail(), gist_config(), longbridge_cli(), longbridge_sdk_quotes(), main() (+18 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (20): _as_float(), _average(), _body_ratio(), contracts_for_capital(), evaluate_breakout_signal(), evaluate_exit(), evaluate_reversal_signal(), ExitDecision (+12 more)

### Community 6 - "Community 6"
Cohesion: 0.24
Nodes (13): _effective_order_price(), _effective_order_quantity(), _enrich_trade_from_order(), _float_or_none(), _is_longbridge_order(), is_process_running(), _order_detail(), _order_field() (+5 more)

### Community 7 - "Community 7"
Cohesion: 0.2
Nodes (11): format_money(), format_pct(), format_trade_message(), _is_filled_status(), notify_trade_if_configured(), _order_id(), _order_status(), Optional Hermes notification adapter for trade events. (+3 more)

### Community 8 - "Community 8"
Cohesion: 0.25
Nodes (9): load_bars(), main(), option_proxy_price(), parse_args(), Lightweight signal backtest for CSV OHLCV data.  This is a reproducible harness, run_backtest(), config_from_args(), get_config() (+1 more)

### Community 9 - "Community 9"
Cohesion: 0.24
Nodes (6): collect_records(), main(), parse_args(), Publish daily records to a GitHub Gist.  External upload is disabled unless --co, update_gist(), UpdateGistSafetyTests

### Community 10 - "Community 10"
Cohesion: 0.27
Nodes (8): main(), _number(), parse_args(), Read-only Longbridge CLI preflight for the QQQ trading system., run_check(), _run_json(), _summarize(), LongbridgeCliCheckTests

### Community 11 - "Community 11"
Cohesion: 0.38
Nodes (5): main(), parse_args(), Flask dashboard for the QQQ trading engine., _read_lock_pid(), _runtime_checked_state()

### Community 12 - "Community 12"
Cohesion: 0.67
Nodes (3): main(), parse_args(), Simple process watchdog for the trading engine.

### Community 13 - "Community 13"
Cohesion: 0.67
Nodes (3): trading_config.py, Dead config entries, SKILL.md CONFIG sync mismatch

## Knowledge Gaps
- **19 isolated node(s):** `Flask dashboard for the QQQ trading engine.`, `Optional Hermes notification adapter for trade events.`, `State, CSV, and trade-record persistence helpers.`, `Longbridge SDK adapter.  The adapter is imported only when live trading is expli`, `Shared configuration for the QQQ 0DTE trading system.` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `LongbridgeBroker` connect `Community 3` to `Community 0`, `Community 4`?**
  _High betweenness centrality (0.158) - this node is a cross-community bridge._
- **Why does `LiveTrader` connect `Community 0` to `Community 1`, `Community 3`, `Community 6`?**
  _High betweenness centrality (0.130) - this node is a cross-community bridge._
- **Why does `PositionState` connect `Community 0` to `Community 1`, `Community 3`, `Community 5`, `Community 6`, `Community 8`?**
  _High betweenness centrality (0.129) - this node is a cross-community bridge._
- **Are the 23 inferred relationships involving `LiveTrader` (e.g. with `PositionState` and `LongbridgeBroker`) actually correct?**
  _`LiveTrader` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Are the 28 inferred relationships involving `PositionState` (e.g. with `QuoteSnapshot` and `Broker`) actually correct?**
  _`PositionState` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Are the 22 inferred relationships involving `DrySubmitBroker` (e.g. with `PositionState` and `LongbridgeBroker`) actually correct?**
  _`DrySubmitBroker` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `SingleInstanceLock` (e.g. with `PositionState` and `LongbridgeBroker`) actually correct?**
  _`SingleInstanceLock` has 15 INFERRED edges - model-reasoned connections that need verification._