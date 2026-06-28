#!/usr/bin/env python3
"""backfill_stocks.py — Deep historical OHLCV backfill into stock_data from the
LOCAL bhavcopy archive (offline, survivorship-free, all symbols).

Sources (data_storage/raw/bhavcopy):
  - legacy/<year>/cm*bhav.csv.zip   (2005 .. ~2019)  EQ series
  - secfull/<year>/sec_bhavdata_full_*.csv (2020 .. now)  EQ series (+delivery)

Writes EQ-series rows to stock_data (symbol,date,open,high,low,close,volume),
INSERT OR REPLACE so the canonical bhavcopy supersedes earlier yfinance rows.
Idempotent and re-runnable.

Run:  py -3.14 market/backfill_stocks.py            # full archive
      py -3.14 market/backfill_stocks.py --from 2016
"""
import sqlite3, zipfile, sys, time, glob
from pathlib import Path

import pandas as pd

DB_PATH      = Path(r"D:\marketDB\db\market.db")
ARCHIVE      = Path(r"D:\MICC\data_storage\raw\bhavcopy")
LEGACY_DIR   = ARCHIVE / "legacy"
SECFULL_DIR  = ARCHIVE / "secfull"


def ensure_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS stock_data (
        symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
        PRIMARY KEY(symbol, date))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_data_date ON stock_data(date)")
    conn.commit()


def _rows_from_df(df, date_str=None):
    """Normalize a legacy or secfull bhavcopy DataFrame to EQ OHLCV rows."""
    df.columns = [str(c).strip().upper() for c in df.columns]
    if "OPEN_PRICE" in df.columns:          # secfull
        cmap = dict(o="OPEN_PRICE", h="HIGH_PRICE", l="LOW_PRICE", c="CLOSE_PRICE",
                    v="TTL_TRD_QNTY", d="DATE1")
    elif "OPEN" in df.columns:              # legacy cm-bhavcopy
        cmap = dict(o="OPEN", h="HIGH", l="LOW", c="CLOSE", v="TOTTRDQTY", d="TIMESTAMP")
    else:
        return []
    df = df[df["SERIES"].astype(str).str.strip() == "EQ"]
    if df.empty:
        return []
    dt = pd.to_datetime(df[cmap["d"]].astype(str).str.strip(), format="%d-%b-%Y", errors="coerce")
    out = pd.DataFrame({
        "symbol": df["SYMBOL"].astype(str).str.strip(),
        "date":   dt.dt.strftime("%Y-%m-%d"),
        "open":   pd.to_numeric(df[cmap["o"]], errors="coerce"),
        "high":   pd.to_numeric(df[cmap["h"]], errors="coerce"),
        "low":    pd.to_numeric(df[cmap["l"]], errors="coerce"),
        "close":  pd.to_numeric(df[cmap["c"]], errors="coerce"),
        "volume": pd.to_numeric(df[cmap["v"]], errors="coerce"),
    }).dropna(subset=["date", "close"])
    return [tuple(r) for r in out.itertuples(index=False, name=None)]


def read_legacy(path):
    try:
        with zipfile.ZipFile(path) as z:
            df = pd.read_csv(z.open(z.namelist()[0]))
        return _rows_from_df(df)
    except Exception:
        return []


def read_secfull(path):
    try:
        return _rows_from_df(pd.read_csv(path))
    except Exception:
        return []


def main():
    year_from = 0
    if "--from" in sys.argv:
        year_from = int(sys.argv[sys.argv.index("--from") + 1])

    files = []
    for y in sorted(p.name for p in LEGACY_DIR.iterdir() if p.is_dir()):
        if int(y) >= year_from:
            files += [("legacy", f) for f in sorted(glob.glob(str(LEGACY_DIR / y / "*.zip")))]
    for y in sorted(p.name for p in SECFULL_DIR.iterdir() if p.is_dir()):
        if int(y) >= year_from:
            files += [("secfull", f) for f in sorted(glob.glob(str(SECFULL_DIR / y / "*.csv")))]

    print(f"Backfilling {len(files):,} bhavcopy files into stock_data ...", flush=True)
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    ensure_table(conn)

    total_rows = done = 0
    t0 = time.time()
    for kind, f in files:
        rows = read_legacy(f) if kind == "legacy" else read_secfull(f)
        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO stock_data (symbol,date,open,high,low,close,volume) "
                "VALUES (?,?,?,?,?,?,?)", rows)
            total_rows += len(rows)
        done += 1
        if done % 250 == 0:
            conn.commit()
            print(f"  {done:,}/{len(files):,} files | {total_rows:,} rows | {time.time()-t0:.0f}s",
                  flush=True)
    conn.commit()

    mn, mx, n, nsym = conn.execute(
        "SELECT MIN(date), MAX(date), COUNT(*), COUNT(DISTINCT symbol) FROM stock_data").fetchone()
    conn.close()
    print(f"DONE: {total_rows:,} rows processed | stock_data now {n:,} rows, "
          f"{nsym:,} symbols, {mn} -> {mx} ({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
