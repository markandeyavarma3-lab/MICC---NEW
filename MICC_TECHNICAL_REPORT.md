# MICC — Technical Deep-Dive Report (engineering grade)

> Exact mechanics, formulas, algorithms, and numbers. Reproducible-from-this-document.
> State as of 2026-06-30: **88 tables · 146,682,989 rows · 19.19 GB** SQLite at
> `D:\marketDB\db\market.db`. Interpreter: `py -3.14` (has nselib/fredapi/lightgbm).

---

# PART I — THE DATA WAREHOUSE (every table, exact)

## I.1 Raw market data (ingested)

| Table | Rows | Range | Schema (key cols) | Source / how |
|---|---|---|---|---|
| `stock_data` | 7,654,136 | 2005-01-03→2026-06-25 | symbol,date,open,high,low,close,volume | NSE bhavcopy (legacy zip + secfull CSV), parsed → raw OHLCV. **Survivorship-free** (4,200 symbols incl. delisted, kept to last trade date). |
| `stock_delivery` | 7,659,152 | 2005→2026-06-26 | symbol,date,total_traded_qty,delivery_qty,delivery_percent | NSE MTO `.DAT` (pre-2020) + secfull (2020+). |
| `market_breadth` | 5,304 | 2005→2026 | date,advances,declines,ad_ratio,new_highs_52w,new_lows_52w,pct_above_50dma,pct_above_200dma,total_traded | **computed** from `stock_data` (not fetched). |
| `fo_data` | 68,928,656 | 2005→2026 | date,instrument,symbol,expiry,strike,option_typ,open,high,low,close,settle_pr,contracts,val_inlakh,open_int,chg_in_oi | NSE F&O bhavcopy. instruments: FUTIDX/FUTSTK (legacy), STF/STO (udiff 2020+), OPTIDX/OPTSTK. 520 underlyings. |
| `option_greeks_raw`, `gamma_exposure_daily` | 3,212,734 each | 2007→2026 | date,symbol,expiry,strike,iv,delta,gamma,theta,vega,rho | **computed** greeks (Black-Scholes w/ computed IV) — **NIFTY+BANKNIFTY only**. |
| `options_pcr_daily` | 262,450 | 2005→2026 | date,symbol,call_oi,put_oi,pcr_oi,call_vol,put_vol,pcr_vol,total_oi | aggregated from `fo_data` OI (418 symbols). |
| `participant_oi` | 15,359 | 2014→2026 | FII/DII/Pro/Client/TOTAL net OI | NSE fao_participant CSVs (2014 = disclosure floor). |
| `indices_data` | 88,636 | 1997→2026 | 35 NSE/BSE indices OHLC | yfinance NSE_INDEX_MASTER. |
| `index_valuation` | 92,889 | 2005→2026 | PE/PB/DivYield, 21 indices | niftyindices.com POST API. |
| `global_indices_daily` | 212,723 | 2000→2026 | date,symbol,close — 35 assets | yfinance: **IndiaVIX, NIFTY50, SPX, NDX, DJIA, USDINR, DXY, Brent, WTI, Gold, US2/10/30Y, BTC…** |
| `bulk_deals` | 222,801 | 2006→2026 | date,symbol,client,buy_sell,qty,price | NSE historicalOR `&csv=true` (uncapped). |
| `block_deals` / `short_deals` | 12,421 / 37,246 | 2006→ / 2018→ | same shape | NSE. |
| `insider_trading` | 279,720 | 2016→2026 | filing_date,symbol,name,category,transaction_type,quantity,value,post_holding,report_date | NSE corporates-pit (2016 = SEBI electronic floor). **Has both filing_date + report_date** → PIT-capable. |
| `corporate_actions` | 40,528 | 2005→2026 | symbol,date(ex),action_type,ratio,amount,subject | NSE CA bulk API; classified DIVIDEND/BONUS/SPLIT/RIGHTS/BUYBACK. |
| `mf_nav_history` | 36,915,520 | 2006→2026 | scheme_code,scheme_name,date,nav | bulk AMFI NAVHistory (37,977 schemes). **NAV-only, no holdings.** |
| `us_macro_data` | 58,010 | **1919**→2026 | FRED series | fredapi. |
| `india_macro_fred`,`rbi_monetary_data`,`world_bank_macro`,`india_bond_yields` | — | 2010/2000/1960/2011→ | macro | FRED/RBI/WB. |

Known-weak raw tables: `fii_dii_data` (30 rows — effectively empty), `fo_ban` (0), `shareholding_history`
(9,913 rows / 174 symbols), `news_headlines`/`google_trends`/`ipo_data` (tiny/recent), `stock_fundamentals` (0).

## I.2 Fundamentals (shallow — the binding data limit)
`annual_income/balance/cashflow` (11,084/11,099/11,099 rows, **2021-06-30→2026-03-31**),
`quarterly_income/balance` (12,747/8,601, **2024-09-30→** — very shallow), `quarterly_cashflow` (16,806, 2002→).
Stored as JSON blobs: `(symbol, report_date, data_json, last_updated)`. `data_json` keys include
`Diluted EPS`, `Net Income`, `Total Revenue`, `Stockholders Equity`, etc. (yfinance/screener).

---

# PART II — THE CLEANING LAYER (exact algorithms)

## II.1 Corporate-action adjustment → `stock_data_adj` (7,654,136 rows)
**Factor math** (parsed from `corporate_actions.ratio` string `"a:b"`):
- SPLIT (face value a→b): `factor = b/a`  (e.g. `10:1` → 0.1).
- BONUS (X new per Y held): `factor = Y/(X+Y)`  (e.g. `1:1` → 0.5, `10:1` → 1/11).

**Back-adjustment (suffix-product algorithm):** for each symbol, sort ex-dates ascending with factors
`f_i`. `adj_factor(date) = Π f_i for all ex-dates strictly after date`, computed as a suffix product +
`np.searchsorted(ex_dates, date, side='right')`. Most-recent prices get `adj_factor=1`; older prices scaled
down. `adj_close = raw_close × adj_factor`; `adj_volume = raw_volume / adj_factor`.

**Cliff-verification guard (the key correctness piece):** a factor is applied **only if the raw price
actually shows the drop**. For each ex-date, observed jump `= close[on-ex]/close[ex-1]`; apply iff
`|log(observed) − log(factor)| < |log(observed) − log(1)|` (i.e. the jump is closer to the action factor
than to "no change"). This **skips names already adjusted at source** (e.g. DBEIL: raw showed no cliff, so
the guard refused to manufacture a fake 10× drop). Last run: **1,130 applied / 41 skipped-already-adjusted /
128 unverifiable; 1,306,299 rows adjusted.**

## II.2 Total-return → `stock_data_tr` (7,654,136 rows)
Dividend yield at ex-date `d`: `y = amount / raw_close(d-1)`, capped at 0.5. `tr_factor(date) = Π (1−y_i)
for div ex-dates after date` (same suffix-product). `close_tr = adj_close × tr_factor`. 13,314 dividend
adjustments applied. **Validated:** COALINDIA price +1.6%/yr → TR +9.2%/yr (+7.6% dividends), ITC +2.2%,
INFY +2.5%, NTPC +2.6% — matches known yields.

## II.3 Point-in-time universe → `pit_universe` (359,047 rows, 257 months)
For each month-end R: trailing **63 trading days** ending at R, per symbol `med_turnover = median(close×volume)`;
require ≥30 of 63 days traded; rank by med_turnover; flags `top100/250/500` + `liquid` (≥₹1cr/day).
**ETF/fund exclusion:** drop symbols whose ISIN starts `INF` (funds) vs `INE` (equity), + a regex fallback
(`BEES|ETF|LIQUID|GOLDBEES|…`) for names not in `isin_master`. 4,200 → **3,929 equity symbols**. Universe
grows 935 (2006) → 2,510 (2026) — the signature of a survivorship-free, backward-honest universe.

## II.4 ISIN master → `isin_master` (3,733) / `isin_renames` (276)
Parsed from ISIN-bearing legacy bhavcopy (2011–2019, monthly-sampled) + current `EQUITY_L.csv`. A rename =
one ISIN under >1 symbol over time, e.g. `INE200A01026` → AREVAT&D→ALSTOMT&D→GET&D→GVT&D. Lets price series
key on the stable ISIN.

## II.5 PIT fundamentals → `fundamentals_pit` (71,436) / `fundamentals_features` (11,084)
`pit_date` = real filing date from `financial_results` (1,988 rows where a broadcast date exists within
[period_end, +120d]) **else** `period_end + statutory lag` (45d quarterly / 60d annual, SEBI norms).
`fundamentals_features` parses `annual_income`/`annual_balance` JSON → `eps` (Diluted/Basic), `net_income`,
`revenue`, `total_equity`, `roe = net_income/total_equity`, each carrying `pit_date`. **Invariant: every
`pit_date > report_date`** (verified 0 violations).

## II.6 Sector map → `dim_sector` (1,409 symbols)
NSE `index_constituents.industry` (507, authoritative) + yfinance `.info['sector']` for the rest of the
liquid universe (902 fetched, 838 yfinance-404 = delisted/renamed). Both normalized to ~12 common buckets
(`NORM` dict: NSE "Information Technology" and yfinance "Technology" → "Information Technology", etc.).
Coverage: **1,405/2,243 (63%)** of the liquid universe.

---

# PART III — FEATURE STORE → `features_monthly` (343,963 rows, 257 months, as-of)

Computed per (symbol, month-end), **all trailing-window only** (no future data). C-accelerated via
`groupby(symbol).rolling(...)`. Built on `stock_data_adj` (adjusted), filtered to `pit_universe`.

| Feature | Formula |
|---|---|
| `ret_1m/3m/6m/12m` | `close/close.shift(21/63/126/252) − 1` |
| `mom_12_1` | `close.shift(21)/close.shift(252) − 1` (12m return skip last month — the classic) |
| `mom_6_1` | `close.shift(21)/close.shift(126) − 1` |
| `vol_3m/6m` | `daily_ret.rolling(63/126).std() × √252` |
| `dist_sma50/200` | `close / rolling(50/200).mean() − 1` |
| `above_200` | `close > sma200` |
| `prox_52w_high` | `close / rolling(252).max()` (∈ (0,1]) |
| `amihud` | `(|ret|/turnover).rolling(21).mean() × 1e7` (illiquidity) |
| `deliv_1m/3m` | `delivery_percent.rolling(21/63).mean()` |
| `deliv_trend` | `deliv_1m − deliv_3m` |
| `fwd_ret_1m/3m` | `close.shift(−21/−63)/close − 1` — **LABELS only, never features** |

**Predictive power (mean cross-sectional Spearman rank-IC vs forward return, top500, 257 months):**
prox_52w_high +0.051 (3m +0.090) · low-vol +0.058 · deliv_1m +0.045 · mom_12_1 +0.041 · dist_sma200 +0.037 ·
vol_3m −0.051 · amihud −0.023. Every sign matches theory; magnitudes ~0.04–0.06 = legitimate-institutional,
not lookahead-inflated.

---

# PART IV — STRATEGY ENGINE → `common/strategy_engine.py`

## IV.1 The generic engine
A strategy is `function(panel) → DataFrame[rebal_date, symbol, weight]`. `run_engine(signal_df, panel, gate,
cost)`:
1. merge target weights with realized R→R+1 return (from `panel.realized`).
2. per rebalance R: renormalize weights `w = w/Σw`; `gross = Σ(w·realized)`.
3. turnover `= Σ|w_t − w_{t-1}|`; `net = gross − turnover·cost`.
4. apply regime gate: `net_gated = net × (1 if score(R)≥2 else 0)`.
5. emit per-name trades (Δweight → BUY/SELL) and holdings.
Writes `bt_portfolio_daily` (1,544 rows), `bt_trades` (95,177), `bt_holdings` (67,828), `bt_strategy_metrics`
(64 = 8 strategies × 8 metrics). Cost = 0.30%/side default.

## IV.2 The 8 strategies (exact selection + weighting)
All: long **top decile** (`pd.qcut` on rank, guard if <10 names), **inverse-vol weighted**
`w ∝ 1/clip(vol_3m, 0.05)`, regime-gated.

1. **momentum_delivery_lowvol** — composite = mean percentile-rank of {mom_12_1, prox_52w_high, deliv_1m,
   low_vol(=−vol_3m)}; top decile.
2. **low_volatility** — decile 1 (lowest vol_3m).
3. **short_term_reversal** — bottom decile ret_1m (equal-weight).
4. **high52_breakout** — top decile prox_52w_high among above_200=1.
5. **value_earnings_yield** — top decile `earnings_yield = eps/close`, eps attached via `merge_asof(pit_date
   ≤ rebal_date)` (no lookahead), positive earners only.
6. **quality_roe** — top decile ROE (as-of pit_date).
7. **dividend_yield** — top decile trailing-12m dividend yield (`Σ div in (R−365,R] / close`, via per-symbol
   `searchsorted` on cumulative dividends).
8. **sector_rotation** — long stocks in the top-3 sectors by mean `mom_12_1` (via `dim_sector`).

## IV.3 Leaderboard (net, regime-gated)
| strategy | CAGR | Sharpe | Sortino | MaxDD | Calmar | months |
|---|---|---|---|---|---|---|
| value_earnings_yield | 28.4% | 1.57 | 4.53 | −14.4% | 1.97 | 49 ⚠ |
| momentum_delivery_lowvol | 17.6% | **1.46** | 2.06 | −16.5% | 1.07 | 245 ✅ |
| quality_roe | 18.7% | 1.30 | 2.43 | −9.4% | 1.98 | 40 ⚠ |
| dividend_yield | 15.1% | 0.92 | 1.35 | −38.8% | 0.39 | 245 |
| sector_rotation | 13.0% | 0.87 | 1.17 | −44.6% | 0.29 | 245 |
| low_volatility | 8.3% | 0.83 | 1.12 | −20.8% | 0.40 | 245 |
| high52_breakout | 11.0% | 0.82 | 1.23 | −31.0% | 0.35 | 245 |
| short_term_reversal | −4.9% | −0.12 | −0.14 | −87.5% | −0.06 | 245 |

## IV.4 Macro regime engine (the timing layer)
4 binary risk-on votes, all trailing/as-of: (1) breadth %>200DMA ≥ 50; (2) NIFTY50 > its 200-DMA;
(3) S&P 500 > its 200-DMA; (4) IndiaVIX < its trailing-252d median. `score = Σvotes ∈ {0..4}`. Gate the book
when `score ≥ 2`. Source: `market_breadth` + `global_indices_daily`. Latest live read: **1/4 → RISK-OFF**.

---

# PART V — BACKTESTING & VALIDATION (exact math)

## V.1 Return + metric definitions
Realized R→R+1 = `adj_close[next month-end]/adj_close[R] − 1`. Monthly series → annualize ×12:
`CAGR = (Π(1+r))^(12/n) − 1`, `Vol = std(r)·√12`, `Sharpe = mean(r)·12 / Vol`, `Sortino` (downside std),
`MaxDD` from cumulative equity, `Calmar = CAGR/|MaxDD|`.

## V.2 Walk-forward (purged + embargoed)
Expanding window: fold k trains on rebalances `< cutoff_k − embargo`, tests `[cutoff_k, +step)`. **Embargo = 1
month** so the last train month's 21-day forward label cannot overlap the first test month's features.
MIN_TRAIN=48–60 months. Used for the ML ranker and the regime-threshold validation.

## V.3 Deflated / Probabilistic Sharpe (multiple-testing control) — `backtest_hardening.py`
PSR(SR*) = `Φ[ (ŜR − SR*)·√(n−1) / √(1 − γ3·ŜR + ((γ4−1)/4)·ŜR²) ]`, ŜR = per-period Sharpe, γ3=skew, γ4=kurtosis.
DSR = PSR(SR0) where `SR0 = √V̂ · [(1−γ)·Z⁻¹(1−1/N) + γ·Z⁻¹(1−1/(N·e))]`, V̂ = variance of trial Sharpes,
γ=0.5772, N=#trials. `Φ` via `math.erf`; `Z⁻¹` via Acklam's inverse-normal (no scipy). Result for the gated
book: bootstrap Sharpe 90% CI [0.73, 1.59], PSR≈100%, **DSR≈100% (N=21)** → not a data-mining fluke.

## V.4 Capacity (square-root market impact) — `backtest_execution.py`
`impact_i = k·√(order_i/ADV_i)`, k=0.025 (≈daily vol), ADV worked over 5 days, charged on traded fraction
only. Net Sharpe vs AUM: ₹10cr→1.04, ₹100cr→0.85, ₹250cr→0.68, ₹500cr→0.49 → **capacity ≈ ₹100–250 cr**.

## V.5 The validated best config → `bt_best` (209 rows, 2009→2026 OOS)
inverse-vol weighting + **walk-forward-adaptive** regime gate (threshold chosen from past data only).
**OOS Sharpe 1.53**, Sortino 2.30, MaxDD −18.9%, Calmar 1.26, CAGR 23.9%, 41.6× equity. Findings: regime gate
beats breadth-only OOS (1.56 vs 1.34); the fixed ≥2/4 threshold does NOT survive (WF prefers ≥1 in 72% of
months); vol-target overlay does NOT stack on the gate (1.53→1.40). ML ranker (LightGBM, purged WF CV)
**loses** to the linear composite (OOS Sharpe 0.76 vs 1.25) → research-first vindicated.

---

# PART VI — PAPER TRADING → `execution/paper_trader.py`

Stateful forward sim. State: `cash`, `positions{symbol→shares}`. Per rebalance R (from `--start`):
1. mark-to-market: drop unpriceable (delisted) names; `nav = cash + Σ shares·price[R]`.
2. targets = strategy weights, **or {} (all cash) when regime gate off**.
3. integer shares `tgt = floor(nav·w / price)`; trade `Δ = tgt − held`.
4. fill at price × (1 ± 0.0005 slippage); cost = |Δ|·price·**0.0012** (STT+exchange+stamp+GST, Zerodha-realistic);
   update cash.
Writes `paper_nav` (246), `paper_positions` (8,008), `paper_trades` (11,240).
**Result:** ₹10L → ₹32,028,886 (**32.0×**), CAGR 18.4%, Sharpe 1.53, MaxDD −16.3%. **Drift check:** paper monthly
return ↔ backtest `net_gated[R−1]` (aligned for the forward-label offset) → **corr 1.000** (engine faithful).
At 2026-06-25 (RISK-OFF) → **all cash** (last positions 2026-05-29).

---

# PART VII — RECOMMENDATIONS + FEEDBACK LOOP → `common/recommendations.py`

## VII.1 Generation
Top-15 by flagship composite per month. `entry = raw close[R]`. 1-month sigma `σ_H = vol_3m·√(21/252)`.
**Price band:** `target = entry·(1 + 1.5·σ_H)`, `stop = entry·(1 − 1.0·σ_H)`. Horizon = 21 trading days.
Logged to `recommendations` (555 rows; PK (rec_date,symbol,strategy); status OPEN).

## VII.2 Evaluation (first-touch path walk)
For OPEN recs whose horizon elapsed (rec_date + 21 TD ≤ latest data): walk daily path R→horizon_end in order;
first day with `high ≥ target` → **TARGET** (exit=target); first with `low ≤ stop` → **STOP** (exit=stop);
neither → **EXPIRED_WIN/LOSS** at horizon-end close. `realized = exit/entry − 1`. 525 closed.

## VII.3 Scorecard (the model-improvement signal)
525 closed: **hit rate 49% · avg +0.47%/call · avg win +6.54% / avg loss −5.43% · target-hit 23% · stop-hit
34% · expired 43%.** Best PRESTIGE +18.6%, HSCL +16.4%; worst ZENTEC −13.5%, RKFORGE −12.9%. **Insight
surfaced:** the underlying momentum book earns ~1.5%/mo but the stopped recommendations earn +0.47%/mo →
**tight vol-stops whipsaw momentum** (34% stop-hit) → next experiment: widen/remove stops or lengthen horizon.

---

# PART VIII — EXECUTION STACK (OMS + risk) → `execution/oms.py`

`OMS.rebalance(targets, prices, advs, positions, nav)`: integer target shares (cap at MAX_WEIGHT),
order = Δshares, each → `RiskEngine.check`:
- reject if notional < ₹5,000 (min ticket);
- reject if notional > 6%·nav·1.05 (position cap);
- reject if notional > 10%·ADV (liquidity).
Accepted → `Broker.place`. **`PaperBroker`** fills at price ± half-spread + 0.12% cost. **`LiveBroker` is a
disabled stub** — `place()` raises unless `enabled and api_key and api_secret`; no path to a real order without
explicit credentials + enable. Demo run: 46 BUY orders, 0 rejected (well-sized portfolio), 95% deployed,
₹1,137 cost → `oms_orders` (46). RiskEngine **verified** to reject oversized/illiquid/dust and pass good.

---

# PART IX — DELIVERY

- **SQLite** single source of truth (88 tables).
- **`common/build_dashboard.py` → `MICC_dashboard.html`** (4.77 MB, self-contained, plotly embedded). 6
  sections: regime · strategy leaderboard · best-strategy equity curve (log) · **recommendations + track
  record** · today's portfolio · top funds · deals · F&O.
- **`web/serve_dashboard.py`** (stdlib `http.server`, HTTP Basic Auth admin/micc, `MICC_PORT`/`MICC_USER`/
  `MICC_PASS` env, `/refresh` route) on **:8765**.
- **`web/api.py`** JSON REST (same auth): `/api/regime|strategies|signals|recommendations|paper|funds|deals|
  fno|asset/{symbol}`.
- **`run_pipeline.py`**: DAILY = core data → signals → recommendations → intel → dashboard → monitor;
  WEEKLY = isin → adjusted prices → PIT universe → features → backtests → best-config → MF scorecard
  (dependency order).

---

# PART X — VERIFICATION (every check)

**`common/verify_phases.py` — 29/29** (phases 1/2/4/5): adj-table row count == raw; no non-positive prices;
adj_factor ∈ (0,1]; `raw == adj/adj_factor` recompute (maxerr 0.00000); split ex-dates de-cliffed (47
checked, 0 residual, 12 gap-skipped); pit_universe top500 ≤ 500; **delisted A2ZMES absent post-2018**
(survivorship); financial_results clean ISO dates; ISINs well-formed; renames genuinely multi-symbol;
0 universe leak; `mom_12_1` & `fwd_ret_1m` recomputed from `stock_data_adj` (5/5); momentum IC +0.0407
reproduces; backtest Sharpe 1.094 / MaxDD −18.0% / 17.5× stored.

**Deep-dive — 17/17** (phases 3/6/7/8): paper↔backtest drift **corr 1.000**; RISK-OFF→0 positions; TR hist <
price; every pit_date > report_date; **value strategy 0/1,758 lookahead violations**; value starts post-
fundamentals (2022-05); 8 strategies; all 6 API endpoints 200; monitoring 12 checks/0 ALERT; **RiskEngine
rejects oversized+illiquid+dust, passes good**; LiveBroker disabled.

**`common/monitor.py`** — 12 daily checks (freshness ≤6d, prices valid, universe 400–500, regime+flip,
flagship Sharpe>1, paper NAV, ≥8 strategies, sector>60%) → `monitoring_log`. Last: 12 OK / 0 WARN / 0 ALERT.

**Self-accountability** — `recommendations` scorecard grades every call vs the real price path.

---

# PART XI — HONEST LIMITS, BUGS FOUND & FIXED

## XI.1 What's proven vs not
- **Proven:** momentum+delivery+low-vol, regime-gated — 20yr, walk-forward, OOS Sharpe 1.53, deflated-
  significant, ~₹100–250cr capacity.
- **Promising, not proven:** value (49mo) / quality (40mo) — high Sharpe but only 3–4yr (fundamentals 2021+)
  in a bull market.
- **Modest:** dividend / sector-rotation (deep DDs). **Correctly dead:** short-term-reversal, naive L/S.

## XI.2 Data limits (not bugs)
Fundamentals shallow (annual 2021+, quarterly 2024+); sector 63%; no PIT index membership; no intraday;
MF NAV-only (no holdings); greeks index-only + computed; `fii_dii` thin; recommendations/paper forward-tracks
are *replayed* over history (true live-forward accrues only as new data arrives).

## XI.3 Bugs caught & fixed during build (all verified fixed)
1. Adjusted-price loop materialized the full date array per-symbol (O(symbols×rows)) → hoisted.
2. Blind CA adjustment manufactured a fake cliff on already-adjusted names (DBEIL) → cliff-verification guard.
3. ETFs leaked into the equity universe (LIQUIDBEES etc. gamed momentum) → ISIN-INF + regex exclusion.
4. Capacity model mis-calibrated (k=0.10, full-book each month) → k=0.025, traded-fraction only.
5. ML-ranker merge-suffix collision + non-datetime merge_asof keys + sparse-decile qcut → fixed.
6. Paper-trade drift corr looked like 0.24 → off-by-one (forward-label) alignment → corr 1.000.
7. Dashboard server torn down between sessions → restart `web/serve_dashboard.py`.

## XI.4 Gated by design
Live trading: `LiveBroker` refuses real orders until you supply broker API keys + set `enabled=True`. Until
then it is paper-only.

---

*Companion docs: `MICC_REPORT.md` (overview) · `MICC_BLUEPRINT.md` (19-section strategy blueprint) ·
`RESEARCH.md` (flagship paper) · `README.md` (phase build log).*
