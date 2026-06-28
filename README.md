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

## Notes

- `run_pipeline.py` keeps daily resume state in `data_extraction\pipeline_state.json`.
- The FRED API key is currently hardcoded inline in the two macro scripts
  (`macro/update_macro_us.py`, `macro/update_macro_india_fred.py`). Move it to an
  environment variable if this repo will ever be shared.
- Dropped during cleanup (dead/broken): the old `pipeline/` file-watcher framework
  (depended on a missing `agents.shared` package), `backfill_indices.py` (same),
  `fill_parquet_from_delivery.py` (incompatible delivery schema), and the orphaned
  `config.py`.
