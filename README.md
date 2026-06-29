# MICC — Market Data Extraction

A clean NSE/BSE + macro **data-extraction** project. Two top-level folders:

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

### Tier 2 — official / free, planned

- **AMFI monthly flows** — AUM, SIP inflows, folio counts (amfiindia.com); the domestic counterweight to FII/DII.
- **MF portfolio holdings** (monthly disclosure) — institutional positioning per stock.
- **India high-frequency macro** — GST collections, PMI (mfg/services), FADA auto sales, e-way bills, power demand (Grid-India), RBI weekly (forex reserves, credit/deposit), monthly trade.
- **IPO data** — GMP, subscription, listing gains (mainboard + SME), IPO calendar.
- **News headlines (RSS)** — Pulse/ET/Moneycontrol/NSE feeds for per-stock NLP sentiment.

### Tier 3 — aggregator-dependent (⚠️ ToS-sensitive)

- Analyst estimates / consensus target prices / rating changes (Trendlyne, Tickertape)
- Brokerage research reports, credit-rating actions (CRISIL/ICRA/CARE)
- Concall transcripts / investor presentations (NLP), NSDL/CDSL fortnightly FPI sector flows, index reconstitution events.

### Cross-asset add-ons (trivial via yfinance/FRED)

DXY, MOVE index, Baltic Dry Index, BTC/ETH, MCX commodities (gold/silver/crude/copper/natgas).

## Notes

- `run_pipeline.py` keeps daily resume state in `data_extraction\pipeline_state.json`.
- **FRED key:** the macro scripts read `os.getenv("FRED_API_KEY")`. Set it before running:
  `setx FRED_API_KEY <your_key>` (open a new terminal afterward). The previously
  hardcoded key was removed from the code and should be rotated.
- Dropped during cleanup (dead/broken): the old `pipeline/` file-watcher framework
  (depended on a missing `agents.shared` package), `backfill_indices.py` (same),
  `fill_parquet_from_delivery.py` (incompatible delivery schema), and the orphaned
  `config.py`.
