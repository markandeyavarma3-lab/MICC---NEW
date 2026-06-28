#!/usr/bin/env python3
"""export_parquet.py — Export stock_data (SQLite) to per-symbol yearly parquet.

Writes D:/marketDB/stocks/all/<SYMBOL>/<YEAR>.parquet so the parquet-based
consumers work (update_corporate_actions, update_fundamentals, phase9b stocks
mode, marketdb.get_stock). Idempotent: merges with existing files, dedup by date.

Run after daily_update.py:  py -3.14 common/export_parquet.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH      = Path(r"D:\marketDB\db\market.db")
PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")

COLS = ["date", "open", "high", "low", "close", "volume"]


def main():
    conn = sqlite3.connect(DB_PATH)
    if not conn.execute("SELECT name FROM sqlite_master WHERE name='stock_data'").fetchone():
        print("stock_data table not found; run market/daily_update.py first.")
        conn.close()
        return
    df = pd.read_sql("SELECT symbol,date,open,high,low,close,volume FROM stock_data", conn)
    conn.close()

    if df.empty:
        print("stock_data is empty; nothing to export.")
        return

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["_year"] = df["date"].dt.year

    PARQUET_ROOT.mkdir(parents=True, exist_ok=True)
    symbols_written = files_written = 0

    for symbol, g in df.groupby("symbol"):
        sym_dir = PARQUET_ROOT / str(symbol)
        sym_dir.mkdir(parents=True, exist_ok=True)
        for year, gy in g.groupby("_year"):
            path = sym_dir / f"{int(year)}.parquet"
            out = gy[COLS].copy()
            out["date"] = out["date"].dt.strftime("%Y-%m-%d")
            if path.exists():
                try:
                    out = pd.concat([pd.read_parquet(path), out], ignore_index=True)
                    out = out.drop_duplicates(subset=["date"], keep="last")
                except Exception:
                    pass
            out = out.sort_values("date").reset_index(drop=True)
            out.to_parquet(path, index=False, compression="snappy")
            files_written += 1
        symbols_written += 1

    print(f"Exported {symbols_written} symbols, {files_written} parquet files -> {PARQUET_ROOT}")


if __name__ == "__main__":
    main()
