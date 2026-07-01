# MICC — Complete System Report
### What it has · what it does · how · what it produces · how it delivers · how it verifies

*A single-operator Indian-equity quantitative research & paper-trading platform.*
*SQLite warehouse at `D:\marketDB\db\market.db` · run everything with `py -3.14` from `data_extraction/`.*

---

## 0. What MICC is, in one paragraph

MICC ingests ~21 years of Indian (and global) market data into a 130-million-row warehouse, cleans it
into a trustworthy point-in-time research layer (corporate-action-adjusted prices, survivorship-free
universe, no-lookahead features and fundamentals), runs a library of **8 systematic strategies** through a
generic backtest engine with realistic costs and a macro **regime gate**, validates them with
institutional rigor (walk-forward, deflated Sharpe), forward-tests them in a **paper-trading engine**,
turns the top picks into **trackable recommendations** (entry/target/stop + duration) with a
self-scoring **feedback loop**, and delivers all of it through an authenticated **dashboard + REST API**,
with a **monitoring** health-check and an **order-management/risk engine** (live trading gated behind a
disabled broker stub). Every claim is backed by an executable verification test.

---

## 1. THE DATA — what it has

**Warehouse:** 57 tables · ~130.4 M rows · 16.6 GB · SQLite (WAL) · raw archive (bhavcopy/CSV/parquet) on disk.
All survivorship-free from 2005 where the source allows. Headline: `fo_data` (68.9M) + `mf_nav_history`
(36.9M) are 81% of rows.

### 1.1 Equity prices, volume, delivery
| Table | Rows | Coverage | Notes |
|---|---|---|---|
| `stock_data` | 7.65M | 4,200 sym, 2005→2026 | raw daily OHLCV, **survivorship-free** (delisted kept) |
| `stock_delivery` | 7.66M | 4,984 sym | delivery qty + % (rare 21-yr depth) |
| `market_breadth` | 5,304 | 2005→2026 | adv/dec, 52w H/L, %>50/200-DMA |

### 1.2 Indices & cross-asset
`indices_data` (88.6k, 35 indices, 1997→), `index_valuation` (PE/PB/DivYield, 21 indices),
`global_indices_daily` (212.7k, 35 assets — **IndiaVIX, NIFTY50, SPX, USDINR, Brent, US10Y, Gold, BTC**…),
`index_constituents` (current snapshot, sector/industry).

### 1.3 Derivatives (F&O)
`fo_data` (68.9M, 520 underlyings, both legacy+udiff formats — futures `STF`/`FUTSTK`, options `STO`/`OPTSTK`),
`option_greeks_raw` + `gamma_exposure_daily` (NIFTY/BANKNIFTY, computed), `options_pcr_daily` (418 sym),
`options_max_pain`, `participant_oi` (FII/DII/Pro/Client, 2014→).

### 1.4 Flows, deals, events
`bulk_deals` (222.8k, 2006→), `block_deals`, `short_deals` (2018→), `insider_trading` (279.7k, 2016→ SEBI),
`corporate_actions` (40.5k div/bonus/split/rights), `corporate_announcements`, `financial_results`,
`board_meetings`. (`fii_dii_data` is thin — a known weak table.)

### 1.5 Fundamentals & ownership
`quarterly_/annual_ income/balance/cashflow` (JSON blobs — **shallow: annual 2021+, quarterly 2024+**),
`shareholding_history` (174 sym — thin), `screener_fundamentals`.

### 1.6 Mutual funds & macro
`mf_nav_history` (36.9M, 37,977 schemes, 2006→), `mf_industry_monthly`, `mf_scheme_master`;
`us_macro_data` (1919→), `india_macro_fred`, `rbi_monetary_data`, `world_bank_macro`, `india_bond_yields`.

### 1.7 Built clean/derived layer (the trustworthy part)
| Table | What | Built by |
|---|---|---|
| `stock_data_adj` | split+bonus **adjusted** OHLCV (cliff-guarded) | `common/build_adjusted_prices.py` |
| `stock_data_tr` | **total-return** (dividend-adjusted) series | `common/build_adjusted_prices_tr.py` |
| `pit_universe` | survivorship-free monthly **equity-only** liquid universe (ETFs excluded) | `registry/build_pit_universe.py` |
| `isin_master` / `isin_renames` | ISIN↔symbol, 276 ticker renames tracked | `registry/build_isin_master.py` |
| `features_monthly` | **as-of** cross-sectional feature store (358k rows) | `common/build_feature_store.py` |
| `fundamentals_pit` | every fundamental tagged with point-in-time `pit_date` (71k) | `events/build_fundamentals_pit.py` |
| `fundamentals_features` | clean EPS/NI/revenue/ROE, PIT-dated (11k) | `events/build_fundamental_features.py` |
| `dim_sector` | sector map, 1,409 symbols (NSE + yfinance, 63% of universe) | `registry/build_sector_map.py` |

---

## 2. WHAT IT DOES WITH THE DATA — and HOW

### 2.1 Clean the data (turn raw → trustworthy)
- **Adjust prices** for splits/bonuses with a per-event **cliff-verification guard** (only applies a factor
  when the raw price actually shows the drop — skips names already adjusted at source, e.g. DBEIL).
- **Total-return** series adds dividend reinvestment (validated: COALINDIA +7.6%/yr).
- **Point-in-time universe**: monthly membership by trailing-63-day median turnover, **ETFs excluded**
  (ISIN `INF` vs `INE`), so backtests only ever see liquid equities knowable at that date.
- **ISIN master** keeps renamed companies as one continuous entity.
- **PIT fundamentals**: attaches `pit_date` (real filing date where available, else period-end + SEBI lag)
  so backtests filter `pit_date <= as_of` — **no lookahead**.

### 2.2 Engineer features (`features_monthly`, as-of, no leakage)
Momentum (`mom_12_1`, 6-1, 1/3/6/12m), volatility (`vol_3m/6m`), trend (`dist_sma50/200`, `prox_52w_high`),
liquidity (`amihud`, `med_turnover`, `adv_rank`), delivery (`deliv_1m/3m/trend`); fundamentals
(earnings-yield, ROE — as-of `pit_date`); dividend yield; sector. Forward returns stored **only** as
`fwd_*` labels, never features.

### 2.3 Build & run strategies (`common/strategy_engine.py`)
A strategy = `function(panel) → [date, symbol, weight]`. The generic engine applies the regime gate +
costs and writes standard tables. **8 strategies** in the registry; each is long top-decile, inverse-vol
weighted, regime-gated. Method for the flagship: composite = mean cross-sectional percentile-rank of
{12-1 momentum, 52w-high proximity, delivery%, low-vol}.

### 2.4 Time the market (macro regime engine)
A 4-vote risk-on classifier (breadth %>200DMA≥50 + NIFTY50>200DMA + S&P>200DMA + IndiaVIX<1yr-median).
Gate the book to cash when risk-off. **Walk-forward-validated**: regime gate OOS Sharpe ~1.55 vs
breadth-only 1.34.

### 2.5 Validate honestly (`common/backtest_hardening.py`, `backtest_best.py`)
Purged + embargoed walk-forward CV · sub-period stability (every era) · parameter-sensitivity plateau ·
block-bootstrap Sharpe CI · **Deflated Sharpe** (multiple-testing) · square-root **capacity** model.

### 2.6 Forward-test (paper-trading, `execution/paper_trader.py`)
Stateful virtual portfolio: **integer shares**, real cash, Indian delivery cost model (~0.12%/side),
**regime-gated liquidation to cash**, daily mark-to-market, and a **live-vs-backtest drift** check.

### 2.7 Recommend & learn (`common/recommendations.py`) — the feedback loop
Top-15 conviction picks → **entry / target / stop price band** (volatility-scaled) + **1-month duration** →
logged → after duration, **evaluated against the real high/low path** (TARGET/STOP/EXPIRED, first-touch) →
**scorecard** (hit rate, avg return) → tells you what to fix. (Already revealed: tight stops whipsaw momentum.)

### 2.8 Supporting analytics
MF risk-adjusted **scorecard** (847 funds), **deals intel** (insider clusters + bulk accumulation),
**F&O positioning** (futures buildup quadrant + PCR extremes).

---

## 3. WHAT IT PRODUCES — the outputs

| Output | Table(s) | Content |
|---|---|---|
| Strategy library + leaderboard | `bt_strategy_metrics`, `bt_portfolio_daily/_trades/_holdings` | 8 strategies ranked by Sharpe/Calmar; full trade & holding logs |
| Validated best config | `bt_best`, `bt_equity`, `bt_metrics` | OOS Sharpe 1.53 (inverse-vol + walk-forward regime gate) |
| Paper portfolio | `paper_nav/_positions/_trades` | forward track: ₹10L → ₹3.2cr (32×), drift corr 1.000 |
| **Stock recommendations** | `recommendations` | entry/target/stop + duration; 525 closed, 49% hit, scorecard |
| Today's signals + regime | `current_signals` | top-decile book + live 4-vote regime (invest/cash) |
| MF scorecard | `mf_scorecard` | 847 equity funds by 3y Sharpe/CAGR/maxDD/consistency |
| Smart-money + F&O intel | `deals_intel`, `fno_intel` | insider clusters, bulk deals, futures buildup, PCR extremes |
| Monitoring | `monitoring_log` | 12 health checks (freshness/quality/regime/strategy) |
| Order blotter | `oms_orders` | risk-checked paper orders |

**The honest leaderboard (net, regime-gated):**

| strategy | Sharpe | months | standing |
|---|---|---|---|
| value_earnings_yield | 1.57 | 49 ⚠ | promising, short history |
| **momentum_delivery_lowvol** | **1.46** | 245 ✅ | **the proven edge** (20yr, walk-forward) |
| quality_roe | 1.30 | 40 ⚠ | promising, short history |
| dividend_yield | 0.92 | 245 | modest, −39% DD |
| sector_rotation | 0.87 | 245 | modest, −45% DD |
| low_volatility / high52_breakout | 0.83 / 0.82 | 245 | secondary |
| short_term_reversal | −0.12 | 245 | fails (correctly) |

---

## 4. HOW IT DELIVERS

- **SQLite warehouse** — single source of truth; query directly or via DB Browser for SQLite.
- **Self-contained HTML dashboard** (`MICC_dashboard.html`, built by `common/build_dashboard.py`) — one
  file, opens in any browser, 6 sections: regime, strategy leaderboard, best-strategy equity curve,
  **stock recommendations + track record**, today's portfolio, top funds, smart-money deals, F&O.
- **Authenticated web server** (`web/serve_dashboard.py`, stdlib, no Flask) — http://localhost:8765,
  HTTP Basic Auth (`admin`/`micc`, override via `MICC_USER`/`MICC_PASS`), `/refresh` route.
- **REST API** (`web/api.py`, served at `/api/*`): `/api/regime`, `/strategies`, `/signals`,
  `/recommendations`, `/paper`, `/funds`, `/deals`, `/fno`, `/asset/{symbol}` — all JSON, behind auth.
- **CLI** — every component runnable standalone (`py -3.14 common/recommendations.py --report`, etc.).
- **Orchestration** (`run_pipeline.py`) — `--daily` refreshes data + signals + recommendations + intel +
  dashboard + monitor; `--weekly` rebuilds the whole strategy layer (adjusted prices → universe → features
  → backtests → scorecard) in dependency order.

---

## 5. HOW IT VERIFIES — nothing is trusted without a test

| Layer | Tool | Coverage |
|---|---|---|
| Phases 1/2/4/5 | `common/verify_phases.py` | **29/29** pin-to-pin: raw==adj/adj_factor exact, momentum & forward-return recomputed from source, survivorship (delisted absent post-delist), top500 cap, clean dates, genuine renames, 0 universe leak, backtest metrics reproduce |
| Phases 3/6/7/8 | deep-dive script | **17/17**: paper↔backtest drift corr 1.000, RISK-OFF→all-cash, TR back-adjust, every `pit_date` after period-end, **value strategy 0/1758 lookahead violations**, all API endpoints 200, monitoring 0-ALERT, **RiskEngine rejects oversized/illiquid/dust orders**, LiveBroker disabled |
| Ongoing health | `common/monitor.py` | data freshness, price validity, universe size, regime flip, strategy Sharpe, paper NAV, sector coverage → OK/WARN/ALERT |
| Self-accountability | `common/recommendations.py` | every recommendation scored against the real price path → live track record |

**The two proofs that matter most:** (1) value/quality strategies have **zero lookahead** — every holding's
fundamentals were filed before the holding date (0/1758 violations); (2) the **risk engine actually rejects**
bad orders and the **live broker cannot fire a real order** without explicit credentials + enable.

---

## 6. THE HONEST STANDING (what's real vs not)

- **Proven:** momentum + delivery + low-vol, regime-gated — 20 years, walk-forward-validated, **OOS Sharpe
  1.53**, deflated-Sharpe significant, capacity ≈ ₹100–250 cr. This is the core edge.
- **Promising, not proven:** value & quality — high Sharpes but only 3–4 years of data (fundamentals start
  2021) in a bull market. Machinery is correct (no lookahead); the data is shallow.
- **Modest:** dividend & sector-rotation — real but deep drawdowns.
- **Correctly dead:** short-term reversal, naive long-short (momentum crash) — the engine shows failures.
- **Feedback-loop insight live:** tight vol-stops hurt the momentum edge (34% stop-hit) → widen/remove next.

**Known data limits (not bugs):** fundamentals shallow (2021+), sector coverage 63%, no PIT index
membership, no intraday, MF data is NAV-only (no holdings), greeks index-only & computed, `fii_dii` thin.

**Deliberately gated:** live trading — `LiveBroker` refuses real orders until you provide broker API keys +
an explicit enable. Paper-trading only until then.

---

## 7. END-TO-END FLOW (one picture)

```
 SOURCES (NSE/BSE/AMFI/FRED/RBI/yfinance, raw archive)
   │  ingestion (idempotent fetchers, run_pipeline.py)
   ▼
 RAW WAREHOUSE  (stock_data, fo_data, mf_nav, corporate_actions, insider, macro …)
   │  CLEAN: adjusted prices · total-return · PIT universe (ETF-excluded) · ISIN · PIT fundamentals · sector
   ▼
 RESEARCH LAYER  (stock_data_adj/_tr, pit_universe, features_monthly, fundamentals_features, dim_sector)
   │  FEATURES (as-of, no leakage)  →  REGIME ENGINE (4-vote)
   ▼
 STRATEGY ENGINE  (8 strategies)  →  BACKTEST + HARDENING (walk-forward, deflated Sharpe, capacity)
   │
   ├─►  PAPER TRADER (integer shares, costs, regime liquidation, drift check)
   ├─►  RECOMMENDATIONS (entry/target/stop + duration → evaluate → scorecard → improve)
   ├─►  OMS + RISK ENGINE (paper-safe; live gated)
   └─►  PRODUCTS (signals, MF scorecard, deals/F&O intel)
   │
   ▼  DELIVERY: SQLite · HTML dashboard · auth web server :8765 · REST API /api/* · CLI
   ▼  GOVERNANCE: monitor.py (health) · verify_phases.py (29) · deep-dive (17) · recommendation scorecard
```

---

## 8. Quick reference — run it

```powershell
cd data_extraction
py -3.14 run_pipeline.py --daily          # refresh data + signals + recos + dashboard + monitor
py -3.14 run_pipeline.py --weekly         # + rebuild whole strategy layer
py -3.14 common\strategy_engine.py         # 8-strategy leaderboard
py -3.14 execution\paper_trader.py         # forward paper-trade the flagship
py -3.14 common\recommendations.py         # generate + score recommendations
py -3.14 common\monitor.py                 # health-check
py -3.14 common\verify_phases.py           # 29-check audit
py -3.14 web\serve_dashboard.py            # dashboard + API on :8765 (admin/micc)
```

*Full methodology & blueprint: `MICC_BLUEPRINT.md`. Flagship research write-up: `RESEARCH.md`.
Phase-by-phase build log & status: `README.md`.*
