# MICC — Indian Equity Quant Research Platform

> From a **130-million-row** NSE/BSE + macro warehouse to a **walk-forward-validated** factor
> strategy and a live dashboard — survivorship-free, corporate-action-adjusted, point-in-time.

**Highlights**
- 🗄️ **130.4M-row** warehouse (57 tables, 16.6 GB): 21 yrs equity OHLCV + delivery, 69M-row F&O,
  37M-row MF NAV, macro, deals, events — survivorship-free from 2005.
- 🧱 **Clean research layer**: corp-action-adjusted prices (cliff-guarded), point-in-time
  equity-only universe, ISIN rename tracking, as-of feature store — **29/29 pin-to-pin verified**.
- 🧪 **Validated strategy**: momentum + delivery + low-vol composite, inverse-vol weighted, macro
  **regime-gated** → **out-of-sample Sharpe 1.53** (Calmar 1.26, MaxDD −19%, net of costs, 2009→2026).
- 🔬 **Honest negatives documented**: ML ranker loses to the linear model; F&O/sector-neutral add
  no edge; vol-target doesn't stack on the gate. (Research-first, not hype.)
- 📈 **Products**: live signal generator, equity-fund scorecard (847 funds), self-contained dashboard.

**Key docs:** [📄 Research paper](RESEARCH.md) · [🧭 Analysis blueprint](MICC_BLUEPRINT.md) ·
[📊 Dashboard](MICC_dashboard.html) (open in a browser) · run `py -3.14 common/verify_phases.py` to audit.

---

Built on a clean NSE/BSE + macro **data-extraction** base. Two top-level folders:

```
MICC/
├── data_extraction/     # all the fetcher/extractor scripts
│   ├── market/          # NSE prices, F&O, delivery, greeks, indices
│   ├── macro/           # FRED (US + India), World Bank, RBI, G-Sec
│   ├── funds/           # mutual-fund NAVs
│   ├── events/          # corporate announcements/actions, insider, fundamentals
│   ├── registry/        # stock/BSE registry, tradable universe
│   ├── trends/          # Google Trends
│   ├── common/          # marketdb query API, db health, optimize, debug
│   ├── logs/            # per-script log files
│   ├── run_pipeline.py  # daily orchestrator
│   └── requirements.txt
└── data_storage/        # the data itself
    ├── raw/             # bhavcopy zips, XBRL results, BSE, indices, CA (2005->)
    ├── parquet/         # daily/bse_daily parquet
    ├── duckdb/          # duckdb warehouse
    ├── market_warehouse/
    ├── fiidii/  paper/
```

> The live SQLite DB + per-symbol parquet that scripts read/write still live at
> `D:\marketDB\` (hardcoded in the scripts). `data_storage/` holds the raw archival
> data. These can be consolidated later if you want a single self-contained tree.

## Requirements

Install into the **Python 3.14** interpreter (it has `nselib`, `fredapi`, `nsefin`):

```powershell
py -3.14 -m pip install -r data_extraction\requirements.txt
```

⚠️ **Interpreter matters.** `nselib` and `fredapi` are installed only under Python
3.14 on this machine. Running a script with plain `py` may select 3.13 and fail with
`ModuleNotFoundError`. Always launch with **`py -3.14`** (or use `run.bat`).

## Run

```powershell
cd data_extraction
py -3.14 run_pipeline.py            # full daily extraction
py -3.14 run_pipeline.py --check    # DB health check only
py -3.14 run_pipeline.py --weekly   # + fundamentals, corporate actions, registries
```

Or run any single extractor directly, e.g.:

```powershell
py -3.14 data_extraction\macro\update_macro_us.py --daily
py -3.14 data_extraction\market\update_delivery.py
py -3.14 data_extraction\market\fetch_nse_data.py --fii
```

## Data coverage & deep backfill

The live DB (`D:\marketDB\db\market.db`) has been deep-backfilled from the local
archive (`data_storage/raw/bhavcopy`, offline, survivorship-free) and online sources.

Every dataset is backfilled to **the earliest its source provides**.

**Equity price / volume**
| Table | Rows | Range | Notes |
|---|---|---|---|
| `stock_data` (OHLCV) | ~7.65M | 2005 → 2026 | 4,200 symbols (survivorship-free) |
| `stock_delivery` | ~7.66M | 2005 → 2026 | 4,984 symbols |
| `market_breadth` | 5,304 | 2005 → 2026 | adv/dec, 52w H/L, % >50/200-DMA |
| per-symbol parquet | 37,667 files | 2005 → 2026 | `D:\marketDB\stocks\all` |

**Indices**
| Table | Rows | Range | Notes |
|---|---|---|---|
| `indices_data` (OHLC) | ~88.6k | 1997 → 2026 | 20 NSE/BSE indices |
| `index_valuation` (PE/PB/DivYld) | ~92.9k | 2005 → 2026 | 21 indices (niftyindices) |
| `global_indices_daily` | ~212k | 2000 → 2026 | 35 global symbols/commodities/FX |

**Derivatives**
| Table | Rows | Range | Notes |
|---|---|---|---|
| `fo_data` (F&O) | ~69M | 2005 → 2026 | both legacy + udiff formats |
| `option_greeks_raw` / `gamma_exposure_daily` | ~3.2M | 2007 → 2026 | NIFTY + BANKNIFTY |
| `participant_oi` | ~15k | **2014** → 2026 | NSE disclosure floor |

**Fundamentals & ownership**
| Table | Rows | Range | Notes |
|---|---|---|---|
| `quarterly_income` / `quarterly_balance` | ~21k | — | ~2,340 symbols (yfinance) |
| `quarterly_cashflow` | ~16.8k | **2002** → 2026 | 1,745 symbols (screener.in scraper) |
| `shareholding_history` | ~10k | **2004** → 2026 | promoter/public % |
| `corporate_announcements` | ~13.8k | — | 2,298 symbols |
| `corporate_actions` | ~40.5k | **2005** → 2026 | div/bonus/split/rights classified |
| `insider_trading` | ~280k | **2016** → 2026 | SEBI PIT floor (direct NSE API) |

**Flows / funds / macro / sentiment**
| Table | Rows | Range | Notes |
|---|---|---|---|
| `mf_nav_history` | **~36.9M** | 2006 → 2026 | 37,977 schemes (bulk AMFI) |
| `us_macro_data` (FRED) | ~58k | 1919 → 2026 | |
| `rbi_monetary_data` / `world_bank_macro` / `india_bond_yields` | — | 1960/2000/2011 → 2026 | |
| `bulk_deals` / `block_deals` | ~150k+ | **2006** → 2026 | NSE historicalOR `&csv=true` (uncapped) |
| `short_deals` | — | **2018** → 2026 | NSE short-selling history |
| `fii_dii_data`, `fo_ban`, `google_trends` | recent | forward / blocked | see "source limits" below |

**Derived analytics** (`phase9b`): `symbol_technicals`, `symbol_seasonality`, `symbol_correlations`, `window_stats`, `window_extremes`, `window_regime_stats` — rebuilt across ~3,800 symbols.

**Source limits (cannot go deeper — the data does not exist):** `insider_trading` only from 2016 (SEBI electronic PIT), `participant_oi` only from 2014 (NSE disclosure start), `short_deals` only from 2018. Genuinely **forward-only** (no history at source): `fii_dii_data`, `fo_ban`, and `google_trends` (Google blocks long-range queries). `fetch_deals` + `fetch_fo_ban` are wired into `run_pipeline.py` so they accumulate daily.

### Backfill / scraper tooling (in `data_extraction/`)

All backfills are **idempotent** (`INSERT OR REPLACE`, skip-existing) and have a
generous `busy_timeout` so several can run in parallel (keep it to ~4-5 at once —
SQLite DDL thrashes beyond that).

| Script | → table | Source |
|---|---|---|
| `market/backfill_stocks.py` | `stock_data` | local bhavcopy (legacy+secfull) |
| `market/backfill_delivery.py` | `stock_delivery` | local mto+secfull |
| `market/backfill_indices_hist.py` | `indices_data` | yfinance |
| `market/backfill_fo_data.py --from 2005-01-01` | `fo_data` | NSE archive (udiff + legacy) |
| `market/phase2_greeks_calculator.py --backfill --start 2005-01-01` | greeks/GEX | computed from `fo_data` |
| `market/backfill_participant_oi.py` | `participant_oi` | NSE archive CSVs (2014+) |
| `market/compute_market_breadth.py` | `market_breadth` | computed from `stock_data` |
| `market/fetch_index_valuation.py` | `index_valuation` | niftyindices.com |
| `market/backfill_deals.py` | `bulk_deals`/`block_deals`/`short_deals` | NSE historicalOR `&csv=true` (2006+/2018+) |
| `market/fetch_deals.py` / `fetch_fo_ban.py` | deals / `fo_ban` | NSE daily snapshot (wired into run_pipeline) |
| `events/insider_trading_fetch.py --backfill --from-date 2016-01-01` | `insider_trading` | NSE corporates-pit API |
| `events/backfill_corporate_actions.py --from 2005` | `corporate_actions` | NSE CA bulk API |
| `events/scrape_cashflow.py` | `quarterly_cashflow` | screener.in |
| `macro/fetch_phase1_data.py --bse` | `shareholding_history` | NSE corp-share-holdings |
| `funds/backfill_mf_nav.py --from 2006` | `mf_nav_history` | bulk AMFI NAV history |
| `common/export_parquet.py` | per-symbol parquet | `stock_data` |

## Data expansion roadmap (Tier 1 → 2 → 3)

Additional datasets to extend coverage, by priority. "Backfillable" = deep history
available; "forward" = source serves current day only, so it accumulates over time.

### Tier 1 — ✅ DONE (breadth + valuation backfilled; deals/ban live daily)

| Dataset | Script → table | Source | History |
|---------|----------------|--------|---------|
| Market breadth (adv/dec, 52w H/L, % >50/200 DMA) | `market/compute_market_breadth.py` → `market_breadth` | computed from `stock_data` | ✅ backfillable (2005→) |
| Index PE / PB / Div-Yield | `market/fetch_index_valuation.py` → `index_valuation` | niftyindices.com | ✅ backfillable (2005→) |
| Bulk / Block / Short deals | `market/fetch_deals.py` → `bulk_deals` / `block_deals` / `short_deals` | NSE `snapshot-capital-market-largedeal` | ⏩ forward (run daily) |
| F&O ban list | `market/fetch_fo_ban.py` → `fo_ban` | NSE `fo_secban.csv` | ⏩ forward (run daily) |
| ETF NAV / premium-discount | — | (ETFs mixed into EQ series; needs AMC NAV) | ⏸ deferred |

```powershell
py -3.14 market\compute_market_breadth.py     # breadth (full history)
py -3.14 market\fetch_index_valuation.py       # PE/PB/DivYield (full history)
py -3.14 market\fetch_deals.py                 # bulk/block/short — run daily
py -3.14 market\fetch_fo_ban.py                # F&O ban — run daily
```

### Tier 2 — 4 of 5 done

| Dataset | Script → table | Status |
|---|---|---|
| **News headlines** | `events/fetch_news.py` → `news_headlines` | ✅ 5 RSS feeds (ET/Pulse/MC); daily |
| **IPO data** (GMP/sub/listing) | `events/fetch_ipo.py` → `ipo_data` | ✅ investorgain JSON; daily |
| **India macro** | `macro/update_macro_india_fred.py --backfill` → `india_macro_fred` | ✅ 14 FRED series, 2010→2026 (was 4) |
| **AMFI MF industry flows** | `funds/backfill_amfi_industry.py` → `mf_industry_monthly` | ✅ 87 months 2019→2026 (schemes/folios/funds-mobilized/net-flow/AUM by category) |
| **MF portfolio holdings** | — | ⏸ not done — per-AMC monthly **PDF**, 40+ houses (too fragile) |

> **India high-frequency macro** (GST/PMI/auto/e-way/power) was probed and **dropped** —
> PMI is paywalled (S&P), GST `data.gov.in` API 500s, MOSPI API down; only press-release/PDF
> remains. The clean macro path is the expanded FRED India series above.

### Tier 3 — aggregator-dependent (⚠️ ToS-sensitive)

- Analyst estimates / consensus target prices / rating changes (Trendlyne, Tickertape)
- Brokerage research reports, credit-rating actions (CRISIL/ICRA/CARE)
- Concall transcripts / investor presentations (NLP), NSDL/CDSL fortnightly FPI sector flows, index reconstitution events.

### Extras built (derived / reference data)

| Dataset | Script → table | Notes |
|---|---|---|
| Index constituents + sector | `registry/fetch_index_constituents.py` → `index_constituents` | 21 NIFTY indices, 507 stocks + NSE Industry/sector classification |
| Options PCR / OI analytics | `market/compute_options_analytics.py` → `options_pcr_daily` | daily Put-Call ratio + OI/vol per symbol, 2005→2026 (computed from `fo_data`) |
| Options max-pain | `market/compute_max_pain.py` → `options_max_pain` | NIFTY/BANKNIFTY/FINNIFTY front-expiry max-pain strike, 2005→2026 |
| Annual financials | `events/fetch_annual_financials.py` → `annual_income`/`annual_balance`/`annual_cashflow` | yfinance, complements quarterly_* |
| MF scheme master | `funds/fetch_mf_scheme_master.py` → `mf_scheme_master` | 14,208 schemes → AMC + category (AMFI NAVAll) |
| Earnings calendar | `events/fetch_earnings_calendar.py` → `board_meetings` / `financial_results` | upcoming results/dividend dates + filed results |

### Cross-asset — already covered in `global_indices_daily`

DXY, USDINR/USDJPY/EURUSD/GBPUSD, Gold/Silver/Copper, WTI/Brent/NatGas, Bitcoin,
VIX, India VIX, US 2/10/30Y, + global indices (35 symbols, 2000→2026).

## Analysis & research roadmap (phased)

The warehouse is now broad enough that the bottleneck is **trustworthiness, not coverage**.
The full institutional analysis (19 sections: bias audit, 100+ idea table, signal factory,
factor/event/derivatives/macro/ML blueprints, backtest architecture, dashboards, monetization)
lives in [`MICC_BLUEPRINT.md`](MICC_BLUEPRINT.md); the written-up flagship study (methodology +
results + honest negatives) is in [`RESEARCH.md`](RESEARCH.md). Execution is phased:

| Phase | Goal | Status |
|---|---|---|
| **0 — Audit** | Validate core tables; find lookahead/survivorship in raw + derived | ✅ findings logged + 29/29 pin-to-pin verify (see below) |
| **1 — Clean foundation** | Corporate-action **adjusted prices**, point-in-time universe, fix `financial_results` date bug, ISIN master | ✅ adj prices · PIT universe · results-date · ISIN master |
| **2 — Feature store** | As-of (lagged) momentum / vol / delivery / liquidity / F&O / breadth features | ✅ equity core; F&O studied (weak, overlay-only) |
| **3 — Analytics + first dashboards** | Regime, breadth, screener, MF scorecard | ✅ live signals + self-contained HTML dashboard |
| **4 — Signal research** | 5 ready factors (momentum, low-vol, liquidity, event, derivatives) + delivery/insider/deal overlays | 🔄 momentum+delivery flagship ✅ |
| **5 — Backtest engine** | Walk-forward, transaction costs, capacity, false-discovery control | ✅ full — +inverse-vol/vol-target sizing + capacity curve (~₹100–250cr) |
| **6 — Factor research** | Sector-neutral composite, IC / decay tests, long-short + long-only | ✅ +low-vol 4-factor (Sharpe 1.19); sector-neutral data-limited |
| **7 — Derivatives analytics** | Buildup / rollover / basis / chain / participant positioning | ⬜ |
| **8 — Macro regime** | One composite risk-on/off regime classifier (gate, not signal) | ✅ walk-forward-validated; best config **OOS Sharpe 1.53** (`bt_best`) |
| **9 — ML ranking** | LightGBM cross-sectional ranker on the feature store (purged walk-forward CV) | ✅ tested — **linear beats ML** (OOS Sharpe 1.25 vs 0.76); ML overfits the noise |
| **10 — Productization** | Auth, alerts, polish on the monetizable dashboards | 🔄 MF scorecard + dashboard built (no web/auth layer yet) |
| **11 — Monetization** | MF scorecard / screener / deals / F&O / regime (SEBI-compliant, factual) | 🔄 fund scorecard + signal/dashboard analytics (factual, no advice) |

---

## ▶ REGIME VALIDATION — DONE. PRODUCTION CONFIG LOCKED.

The macro regime gate was walk-forward-validated (`common/backtest_best.py` → `bt_best`):
- **Regime gate beats breadth-only out-of-sample** — WF-adaptive threshold OOS Sharpe **1.56**
  (Calmar 1.37) vs breadth-only **1.34** on the same 2009–2026 window. Validated.
- The specific **≥2/4 threshold did NOT survive** — chosen from past data only, the gate prefers
  **≥1 in 72% of months** (more time in market). So the *engine* is robust; the fixed threshold isn't.
- **Combined best config = inverse-vol weighted top-decile + walk-forward regime gate**:
  **OOS Sharpe 1.53**, Sortino 2.30, MaxDD −18.9%, Calmar 1.26, CAGR 23.9% (`bt_best`, 41.6× equity).
- **vol-target does NOT stack** on the regime gate (1.53→1.40) — the gate already controls risk.
- `generate_signals.py` now reports the live 4-vote regime (latest read: 1/4 → RISK-OFF/cash).

## ▶ MASTER ROADMAP (active) — "trade-it-myself" (60%) + research breadth (40%)

User direction: personal trading system (paper → maybe live later) + research breadth; paper-trading
AND backtest; moderate/pragmatic engineering (no star-schema/staging refactor — overkill for solo);
build sequentially.

| Phase | What | Status |
|---|---|---|
| **1 — Generic strategy engine** | Signal-table backtester + registry; `bt_portfolio_daily`/`bt_trades`/`bt_holdings`/`bt_strategy_metrics`; flagship ported | ✅ done |
| **2 — Strategy library** | + low-vol, short-term-reversal, 52w-breakout; leaderboard | ✅ done (4 strategies) |
| **3 — Paper-trading engine** | Forward simulator: integer shares, real cost model, regime liquidation, live-vs-backtest drift | ✅ done (corr 1.000) |
| **4 — Close data gaps** | Total-return ✅ · PIT-dated fundamentals ✅ · sector map ✅ (63%) | ✅ done |
| **5 — More strategies** | value, quality, dividend, sector-rotation added (8 total); seasonality ⬜ | ✅ 8-strategy library |
| **6 — API + dashboard suite** | stdlib JSON REST API (`/api/*`) + dashboard strategy-leaderboard | ✅ done |
| **7 — Monitoring/governance** | health-check: freshness, data-quality, regime-flip, strategy health | ✅ done (`monitor.py`) |
| **8 — Live trading** *(gated)* | OMS + risk engine + broker interface; **LiveBroker disabled** (paper-safe) | ✅ skeleton; live gated |

**Phase 1/2 — `common/strategy_engine.py`** (generic engine + registry). A strategy is a
function(panel)→`[rebal_date, symbol, weight]`; the engine applies the macro regime gate + costs and
writes standard tables. Leaderboard (net, regime-gated, full period):

| strategy | CAGR | Sharpe | Sortino | MaxDD | Calmar | months |
|---|---|---|---|---|---|---|
| value_earnings_yield* | 28.4% | 1.57 | 4.53 | −14.4% | 1.97 | **49** ⚠ |
| momentum_delivery_lowvol | 17.6% | **1.46** | 2.06 | −16.5% | 1.07 | 245 ✅ |
| quality_roe* | 18.7% | 1.30 | 2.43 | −9.4% | 1.98 | **40** ⚠ |
| dividend_yield | 15.1% | 0.92 | 1.35 | −38.8% | 0.39 | 245 |
| sector_rotation | 13.0% | 0.87 | 1.17 | −44.6% | 0.29 | 245 |
| low_volatility | 8.3% | 0.83 | 1.12 | −20.8% | 0.40 | 245 |
| high52_breakout | 11.0% | 0.82 | 1.22 | −31.0% | 0.35 | 245 |
| short_term_reversal | −4.9% | −0.12 | −0.14 | −87.5% | −0.06 | 245 (fails — correctly) |

*\*Value/quality use PIT fundamentals (`fundamentals_features`, as-of `pit_date` — no lookahead) but the
fundamental data only starts 2021, so their backtests are **short (~3–4 yr) in a strong bull market** —
promising, **not** proven. Momentum (20-yr, walk-forward-validated) remains the only proven strategy.
Deeper fundamental history is the binding data constraint.*

```powershell
py -3.14 common\strategy_engine.py            # run all strategies -> leaderboard + bt_* tables
py -3.14 common\strategy_engine.py --list      # list registered strategies
```

**Phase 3 — `execution/paper_trader.py`** (forward paper-trading simulator → `paper_nav` /
`paper_positions` / `paper_trades`). Stateful virtual portfolio: **integer shares + real cash**,
Indian delivery **cost model** (~0.12%/side: STT+exchange+stamp+GST+slippage), **regime-gated
liquidation to cash** (sells everything + pays cost when regime turns off, re-buys when on), and a
**live-vs-backtest drift** check. Flagship full-history: ₹10L → ₹3.20 cr (32×), CAGR 18.4%, Sharpe 1.53,
MaxDD −16.3%, drift corr **1.000** (engine faithful). At 2026-06-25 (regime RISK-OFF) it correctly
holds all cash.

```powershell
py -3.14 execution\paper_trader.py                                   # flagship, full history
py -3.14 execution\paper_trader.py --strategy low_volatility --start 2018-01-01 --capital 1000000
```

**Phase 4 — data gaps:**
- **4a Total-return** (`common/build_adjusted_prices_tr.py` → `stock_data_tr.close_tr`): back-adjusts
  `stock_data_adj` for cash dividends (13,314 applied). Validated: COALINDIA +7.6%/yr div, ITC +2.2%,
  INFY +2.5% — unblocks dividend / total-return strategies.
- **4c PIT fundamentals** (`events/build_fundamentals_pit.py` → `fundamentals_pit`): attaches a
  point-in-time `pit_date` to every fundamental record (real filing date from `financial_results`
  where available — 1,988 — else period-end + SEBI lag of 45d quarterly / 60d annual; 71,436 rows).
  Backtests must filter `pit_date <= as_of` to avoid lookahead → unblocks value/quality factors.
- **4b Sector map** (`registry/build_sector_map.py` → `dim_sector`): NSE industry (507) + yfinance for
  the rest of the liquid universe, normalized to ~12 common sectors. Resumable/incremental (commits in
  batches). Long-running yfinance fetch.

```powershell
py -3.14 common\build_adjusted_prices_tr.py    # total-return series -> stock_data_tr
py -3.14 events\build_fundamentals_pit.py       # PIT dates -> fundamentals_pit
py -3.14 registry\build_sector_map.py           # sector map -> dim_sector (resumable)
```

Earlier milestone — **regime validation** (`backtest_best.py` → `bt_best`): WF-adaptive regime gate
OOS Sharpe 1.56 vs breadth-only 1.34; combined best (inverse-vol + WF-regime) **OOS Sharpe 1.53**.
Verify anytime with `py -3.14 common/verify_phases.py` (expect 29/29).

---

**Phase 1 — adjusted-price layer** (`data_extraction/common/build_adjusted_prices.py` → `stock_data_adj`):
back-adjusts OHLCV for SPLIT + BONUS so momentum/breakout/event signals aren't poisoned by
price cliffs. Per-event **cliff-verification guard** only applies a factor when the raw close
actually shows the drop — names already adjusted at source (e.g. DBEIL) are skipped to avoid
manufacturing fake cliffs. Last run: 1,130 events applied, 41 skipped (already-adjusted),
128 unverifiable; **1.31 M rows adjusted** of 7.65 M. Known v1 limitations: **dividends**
(price-only momentum doesn't need them) and **RIGHTS** (need subscription price, not stored)
are not yet adjusted — documented for a future total-return series.

**Phase 1 — point-in-time universe** (`data_extraction/registry/build_pit_universe.py` → `pit_universe`):
survivorship-free monthly liquid-universe membership. For each month-end it ranks symbols by
trailing-63-day median turnover (raw close×volume) and flags `top100/250/500` + a ≥₹1cr `liquid`
cut, using **only** data up to that date. **ETFs/funds are excluded** (ISIN prefix INF vs equity
INE, + symbol-pattern fallback; 4,200→3,929 equity symbols) because NAV-creep games momentum /
52w-high / delivery. ~257 months (2005→2026); universe grows backward-to-forward — the signature
of a delisting-inclusive universe. Filter every cross-sectional study through this table.

**Phase 1 — results-date fix** (`events/fetch_earnings_calendar.py`): `broadcast_date` was being
truncated by a `[:10]` slice on NSE's `'25-Jun-2026 16:39:17'` (date+time) string, dropping the
last year digit (`25-Jun-202`). `_iso()` now strips the time component and never emits a partial
date; the garbage-keyed rows were cleared and re-fetched (clean ISO `2025-01-07 → 2026-06-25`).

**Phase 0 — audit finding (lookahead guardrail):** the derived `window_*` and `symbol_*` tables
(`window_extremes`, `window_stats`, `window_regime_stats`, `symbol_technicals`, `symbol_seasonality`,
`symbol_correlations`, `symbol_series_stats`) are **full-sample descriptive snapshots** — each row is
computed over the *entire* history under a single `computed_date`. They are fine for dashboards and
current-state screening but **must NOT be used as point-in-time features in any backtest** (they leak
the future into every historical date). Build as-of features fresh in Phase 2 instead.

**Phase 1 — ISIN master** (`registry/build_isin_master.py` → `isin_master`, `isin_renames`):
maps the stable ISIN to its NSE symbol(s) so a renamed company stays one continuous entity.
Built from ISIN-bearing legacy bhavcopy (2011–2019, monthly-sampled) + current `EQUITY_L.csv`.
3,419 ISINs / 3,382 symbols / 2,394 active, with **276 renames** caught (e.g.
`INE200A01026` → AREVAT&D→ALSTOMT&D→GET&D→GVT&D). Key price series on ISIN, not symbol, to
survive ticker changes. Known v1 gap: pre-2011 and 2020-only renames (no ISIN in those raw files).

**Phase 2 — feature store** (`common/build_feature_store.py` → `features_monthly`): as-of,
point-in-time cross-sectional panel sampled at the 257 monthly rebalance dates (358,127 rows /
4,115 symbols, 2005→2026). Built on `stock_data_adj`, filtered through `pit_universe`. Features:
momentum (`ret_1m/3m/6m/12m`, `mom_12_1`, `mom_6_1`), vol (`vol_3m/6m`), trend (`dist_sma50/200`,
`above_200`, `prox_52w_high`), liquidity (`amihud`, `adv_rank`, `med_turnover`), delivery
(`deliv_1m/3m`, `deliv_trend`). Forward returns are stored ONLY as `fwd_ret_1m`/`fwd_ret_3m`
**labels** (never features). F&O / breadth features are a Phase 2b follow-on.

Self-validation = mean cross-sectional **rank-IC vs forward return** (top500 universe). Every sign
matches theory, magnitudes are realistic (not lookahead-inflated), confirming the adjusted-price +
PIT-universe foundation is clean:

| feature | IC vs 1m | %+ months | IC vs 3m |
|---|---|---|---|
| prox_52w_high | +0.051 | 61% | **+0.090** |
| deliv_1m | +0.045 | 63% | +0.065 |
| mom_12_1 | +0.041 | 65% | +0.052 |
| dist_sma200 | +0.037 | 62% | +0.065 |
| vol_3m | **−0.051** | 40% | −0.072 |
| amihud | −0.023 | 39% | −0.022 |

**Phase 4/5 — flagship backtest** (`common/backtest_momentum.py` → `bt_equity`, `bt_metrics`):
survivorship-free, cost- and regime-aware monthly backtest of a composite signal
(mean percentile-rank of `mom_12_1` + `prox_52w_high` + `deliv_1m`) on the top500 PIT universe,
adjusted-price realized returns, 30 bps/side turnover cost, **equity-only universe (ETFs/funds
excluded)**. Decile spread is **monotonic** (+1.65%/mo gross D10−D1). Headline (net, 2005→2026):

| Strategy | CAGR | Vol | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|---|
| **LongOnly D10 + breadth-regime gate** | 15.7% | 13.9% | **1.12** | **−17.8%** | 0.88 |
| LongOnly D10 (no gate) | 19.6% | 21.9% | 0.94 | −65.9% | 0.30 |
| Bench (EW top500) | 10.1% | 29.3% | 0.48 | −72.5% | 0.14 |
| LS (D10−D1) | 9.4% | 30.8% | 0.48 | −79.8% | 0.12 |

Key finding: the **breadth regime gate** (trade only when %>200DMA ≥ 50) cuts max drawdown
−65.9% → −17.8% while holding ~16% CAGR. The naive long-short is poor (momentum-crash on the
short leg) — value is in long-only + gate. Honest caveats: ~38%/mo turnover (capacity-bound),
regime threshold not optimized. (Excluding ETFs/funds, which game momentum/52w-high/delivery via
NAV-creep, slightly *improved* every metric — the low-return funds were diluting the top decile.)

**Phase 5 — backtest hardening** (`common/backtest_hardening.py`): the four rigor tests that make
the flagship defensible (reuses the same `load_panel`). Results:
- **Sub-period stability:** gated LongOnly works in every era — 2005–11 Sharpe 0.90, 2012–18 1.17,
  2019–26 1.30 (rising, no decay). Not one lucky decade.
- **Walk-forward OOS (2008–2026):** IC-weighted composite (past-data-only weights) Sharpe 1.17;
  naive equal-weight 1.29 — edge does not depend on weight-fitting.
- **Parameter sensitivity:** Sharpe plateau across top-10/20/30% × regime 40/50/60% (no knife-edge).
- **Significance:** bootstrap Sharpe 90% CI [0.73, 1.59], P(Sharpe>0)=100%; PSR≈100%; Deflated
  Sharpe≈100% (N=21 trials, SR0=0.15) — not a multiple-testing fluke.

Remaining honest gaps: residual survivorship (~1,258 name-months dropped for mid-month delisting
slightly flatters returns), capacity bound (~38%/mo turnover → real impact > 30bps in smaller
top500 names), execution modeled at month-end close, long-only (short leg is dead — momentum crash).

**Pin-to-pin verification** (`common/verify_phases.py`): independent re-derivation of every Phase
1/2/4/5 claim from raw tables — **29/29 checks pass**. Includes manual recomputes (raw == adj/adj_factor
exact; `mom_12_1` & `fwd_ret_1m` recomputed from `stock_data_adj` 5/5; momentum IC +0.0407 reproduces),
survivorship (delisted `A2ZMES` absent from post-2018 universe), top500 cap = 500, clean ISO result
dates, genuine multi-symbol renames, 0 universe leak, and backtest metrics (Sharpe 1.094, MaxDD −18.0%,
17.5× equity) reproduced. Data-quality note: ~12 of the 60 most-recent split/bonus names (e.g. SKYGOLD,
SME/new listings) have daily-data gaps straddling the ex-date — adjustment factor is still applied
correctly (9:1 bonus → ×0.1), but price-continuity can't be price-verified for those few names.

**Phase 3 — live signal generator** (`common/generate_signals.py` → `current_signals`): operationalizes
the flagship into TODAY's actionable output — the latest month-end top-decile portfolio (the names you'd
hold now) with each name's signal components (12-1 momentum, 52w-high proximity, delivery%) and liquidity,
plus the **live breadth regime gate** (invest vs cash). Latest run (as-of 2026-06-25): regime RISK-OFF
(%>200DMA = 45.1 < 50 → gate to cash); 46-name top-decile book led by ANANDRATHI, NYKAA, FEDERALBNK,
LAURUSLABS, TORNTPHARM. Research output only — not investment advice.

**Phase 6 — multi-factor** (`common/backtest_multifactor.py` → `bt_multifactor`): adds the low-vol
factor (IC +0.058) to the composite. The **4-factor gated book improves risk-adjusted return** —
Sharpe 1.12→**1.19**, Sortino 1.13→1.26, MaxDD −17.8%→**−14.9%**, Calmar 0.88→0.91 (CAGR 13.6% vs
15.7% — the low-vol trade-off). Sector-neutralization *lowered* Sharpe to 1.02 and is **not used**:
sector data is a snapshot covering only ~49% of historical rows. **Phase 2b — F&O study**
(`common/fno_feature_study.py`): PCR / futures-OI features are weak cross-sectionally (|IC|<0.02,
8% coverage; crowding −0.056 but size-confounded) → confirmation overlay only, not a core factor.

**Advanced layer (Phases 8/9 + execution realism):**
- **Phase 9 ML** (`common/ml_ranker.py` → `bt_ml_ranker`): LightGBM learning-to-rank on all 19
  features, purged+embargoed walk-forward CV. **Linear composite beats ML** (OOS Sharpe 1.25 vs 0.76;
  OOS rank-IC +0.082 vs +0.016) — monthly cross-sectional returns are too noisy for the tree model to
  generalize; the transparent rank-composite wins. Honest, leakage-controlled proof of "research-first".
- **Phase 5 execution** (`common/backtest_execution.py` → `bt_execution`): inverse-vol weighting +
  a 12%-vol-target overlay lift **Sharpe 1.12→1.18, Sortino→1.60, Calmar→1.17, MaxDD→−14.0%**.
  Square-root market-impact capacity curve: Sharpe holds ~1.0 to ₹100cr, ~0.7 at ₹250cr → **capacity ≈ ₹100–250cr**.
- **Phase 8 macro regime** (`common/backtest_regime.py`): a 4-vote risk-on classifier (breadth + Nifty
  trend + S&P trend + India-VIX-below-median) replaces the single breadth gate and lifts **Sharpe
  1.12→1.43, Sortino→2.00, CAGR→21.9%** (invested 70% vs 46%). The ≥2/4 threshold is one of three
  tested → flagged for walk-forward validation before production.

**Build/run order (clean-layer pipeline):**
```powershell
py -3.14 common\build_adjusted_prices.py              # rebuild stock_data_adj (idempotent)
py -3.14 registry\build_isin_master.py                 # isin_master + isin_renames (needed by universe ETF filter)
py -3.14 registry\build_pit_universe.py                # pit_universe (equity-only, ETFs excluded)
py -3.14 common\build_feature_store.py                 # features_monthly + IC report
py -3.14 common\backtest_momentum.py                   # flagship backtest A + save curves
py -3.14 common\backtest_hardening.py                  # walk-forward + sub-period + DSR rigor
py -3.14 common\backtest_multifactor.py                # 4-factor (+low-vol) B + sector-neutral test
py -3.14 common\fno_feature_study.py                   # F&O cross-sectional signal study
py -3.14 common\ml_ranker.py                           # Phase 9 LightGBM ranker (vs linear, OOS)
py -3.14 common\backtest_execution.py                  # inverse-vol + vol-target + capacity curve
py -3.14 common\backtest_regime.py                     # Phase 8 macro regime gate (in-sample)
py -3.14 common\backtest_best.py                       # WF-validate regime + combined best (bt_best, OOS 1.53)
py -3.14 common\verify_phases.py                       # 29-check pin-to-pin audit of all phases
py -3.14 common\generate_signals.py                    # today's top-decile book + regime -> current_signals
py -3.14 common\recommendations.py                     # stock recos (entry/target/stop) + score elapsed -> recommendations
py -3.14 common\recommendations.py --report             # just the recommendation scorecard
py -3.14 funds\mf_scorecard.py                         # equity-fund risk-adjusted scorecard -> mf_scorecard
py -3.14 common\build_dashboard.py                     # -> MICC_dashboard.html (open in browser)
```

**Products (Phase 10/11):**
- **`common/recommendations.py` → `recommendations`**: the accountability/feedback loop — turns the
  top-conviction picks into trackable **stock recommendations** (entry / target / stop **price band**,
  volatility-scaled, + a **1-month duration**), logs them, then after the duration **evaluates against the
  real price path** (TARGET-hit / STOP-hit / EXPIRED) and keeps a **scorecard** (hit rate, avg return,
  best/worst). Backfills a historical track record so it works immediately. Track record: 525 closed calls,
  49% hit, +0.47%/call — which *already* surfaced an insight: tight vol-stops whipsaw the momentum edge
  (34% stop-hit), so they hurt. That's the model-improvement loop working. Research only, not advice.
- **`common/generate_signals.py` → `current_signals`**: today's top-decile equity book + the live
  4-vote macro regime (invest vs cash).
- **`funds/mf_scorecard.py` → `mf_scorecard`**: 847 equity Growth funds ranked by 3y Sharpe / CAGR /
  max-drawdown / rolling-1y consistency, within category (factual analytics, not advice; NAV ≠ holdings).
- **`common/build_market_intel.py` → `deals_intel`, `fno_intel`**: recent insider cluster-buys +
  bulk-deal accumulation, and futures-buildup quadrant + PCR extremes on the ~210 F&O names.
- **`common/build_dashboard.py` → `MICC_dashboard.html`**: one self-contained interactive page (regime,
  best-strategy equity curve vs benchmark, metrics, today's portfolio, top funds, smart-money, F&O). No server.
- **`web/serve_dashboard.py`**: stdlib (no-Flask) web layer — serves the dashboard behind HTTP Basic
  Auth with a `/refresh` route. `py -3.14 web/serve_dashboard.py` → http://localhost:8765 (set
  `MICC_USER`/`MICC_PASS` env before sharing; defaults admin/micc).

**Phase 6 — REST API** (`web/api.py`, served by `web/serve_dashboard.py` under the same auth):
`/api/regime`, `/api/strategies` (leaderboard), `/api/signals`, `/api/paper` (NAV series), `/api/funds`,
`/api/deals`, `/api/fno`, `/api/asset/{symbol}` (e.g. RELIANCE → sector + live features). Dashboard also
gained the 8-strategy leaderboard section.

**Phase 7 — monitoring** (`common/monitor.py` → `monitoring_log`): one health-check pass — data freshness,
price/adjustment validity, universe size, regime state + flip, flagship Sharpe, paper portfolio, strategy
count, sector coverage → OK / WARN / ALERT. Run daily.

**Phase 8 — execution stack** (`execution/oms.py` → `oms_orders`): `OMS` + `RiskEngine` (position cap 6%,
≤10% ADV liquidity, min-ticket) + `Broker` interface. `PaperBroker` simulates fills; **`LiveBroker` is a
disabled stub** that refuses to trade without API credentials + an explicit enable flag — no accidental
real orders. Paper rebalance into today's portfolio: 46 orders, risk-checked, 95% deployed.

```powershell
py -3.14 web\serve_dashboard.py     # dashboard (/) + JSON API (/api/*) on :8765, auth admin/micc
py -3.14 common\monitor.py           # daily health-check -> monitoring_log
py -3.14 execution\oms.py            # paper OMS rebalance into signal portfolio -> oms_orders
```

**Pipeline wiring:** `run_pipeline.py` now refreshes products daily (signals → intel → dashboard at the
tail of `DAILY_PHASES`) and rebuilds the whole strategy layer weekly (`--weekly`: isin → adjusted prices
→ PIT universe → feature store → backtests → MF scorecard, in dependency order).

## Notes

- `run_pipeline.py` keeps daily resume state in `data_extraction\pipeline_state.json`.
- **FRED key:** the macro scripts read `os.getenv("FRED_API_KEY")`. Set it before running:
  `setx FRED_API_KEY <your_key>` (open a new terminal afterward). The previously
  hardcoded key was removed from the code and should be rotated.
- Dropped during cleanup (dead/broken): the old `pipeline/` file-watcher framework
  (depended on a missing `agents.shared` package), `backfill_indices.py` (same),
  `fill_parquet_from_delivery.py` (incompatible delivery schema), and the orphaned
  `config.py`.
