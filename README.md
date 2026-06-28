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

| Table | Rows | Range | Status |
|-------|------|-------|--------|
| `stock_data` (OHLCV)        | ~7.65M | 2005-01-03 → 2026 | ✅ complete (4,200 symbols) |
| `stock_delivery`            | ~7.66M | 2005-01-03 → 2026 | ✅ complete (4,984 symbols) |
| `indices_data` (NSE/BSE)    | ~88.6k | 1997-07 → 2026     | ✅ complete (20 indices; 4 CNX tickers unavailable on Yahoo) |
| `global_indices_daily`      | ~212k  | 2000-01 → 2026     | ✅ complete (35 symbols) |
| per-symbol parquet          | 37,667 files | 2005 → 2026 | ✅ complete (`D:\marketDB\stocks\all`) |
| macro (FRED/WorldBank/RBI)  | —      | full history       | ✅ complete |
| `fo_data` (F&O)             | ~10.1M | 2005 → **~2008**, + recent | 🟡 PARTIAL — stopped; gap ~2008→2026 |
| quarterly fundamentals      | partial | —                 | 🟡 PARTIAL — stopped ~1,356/4,200 symbols |
| `option_greeks_raw` / `gamma_exposure_daily` | recent only | 2026 | ⏸ pending (run after F&O) |

### Backfill tooling (in `data_extraction/`)

- `market/backfill_stocks.py`  — local bhavcopy (legacy+secfull) → `stock_data`
- `market/backfill_delivery.py` — local mto+secfull → `stock_delivery`
- `market/backfill_indices_hist.py` — yfinance → `indices_data`
- `market/backfill_fo_data.py`  — NSE archive (udiff + legacy) → `fo_data` (resumable: skips existing dates)
- `market/phase9a_fetch_global_indices.py --full` — global history
- `common/export_parquet.py`    — `stock_data` → per-symbol parquet

### Resume the backfill (tomorrow)

```powershell
cd data_extraction
# 1) Finish F&O (resumes automatically — skips dates already in fo_data)
py -3.14 market\backfill_fo_data.py --from 2005-01-01
# 2) Finish quarterly fundamentals (re-run; processes all parquet symbols)
py -3.14 events\update_fundamentals.py
# 3) Once fo_data is complete, backfill Greeks/GEX from it
py -3.14 market\phase2_greeks_calculator.py --backfill
# 4) Refresh per-symbol parquet after any stock_data change
py -3.14 common\export_parquet.py
```

> All backfills are idempotent (`INSERT OR REPLACE`); re-running is safe. The F&O job
> is the long pole (~5,600 trading days off the NSE archive, ~2-3 hrs end to end).

## Notes

- `run_pipeline.py` keeps daily resume state in `data_extraction\pipeline_state.json`.
- **FRED key:** the macro scripts read `os.getenv("FRED_API_KEY")`. Set it before running:
  `setx FRED_API_KEY <your_key>` (open a new terminal afterward). The previously
  hardcoded key was removed from the code and should be rotated.
- Dropped during cleanup (dead/broken): the old `pipeline/` file-watcher framework
  (depended on a missing `agents.shared` package), `backfill_indices.py` (same),
  `fill_parquet_from_delivery.py` (incompatible delivery schema), and the orphaned
  `config.py`.
