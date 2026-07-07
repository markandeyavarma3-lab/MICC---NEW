#!/usr/bin/env python3
"""backfill_indices_hist.py — Deep historical index OHLCV into indices_data via yfinance.

There is no local index-OHLCV archive, so this pulls full history for each NSE/BSE
index from its Yahoo Finance ticker (auto-adjusted). INSERT OR REPLACE into
indices_data (name,date,open,high,low,close,volume,adj_close).

Some legacy ^CNX* tickers are no longer served by Yahoo; those are skipped and
reported. Run:  py -3.14 market/backfill_indices_hist.py
"""
import sqlite3, time
from pathlib import Path

import pandas as pd
import yfinance as yf

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")

# name -> (yahoo_ticker, history_start)
NSE_INDEX_MASTER = {
    "NIFTY 50": ("^NSEI", "1999-11-03"),       "NIFTY BANK": ("^NSEBANK", "2000-01-01"),
    "NIFTY IT": ("^CNXIT", "1999-01-01"),       "NIFTY MIDCAP 100": ("^CNX100", "2001-01-01"),
    "NIFTY SMALLCAP 100": ("NIFTY_SMALLCAP_100.NS", "2004-01-01"),
    "NIFTY NEXT 50": ("^NSMIDCP", "1997-01-01"),"NIFTY 100": ("^CNX100", "2003-01-01"),
    "NIFTY 200": ("^CNX200", "2004-01-01"),     "NIFTY 500": ("^CNX500", "1999-01-01"),
    "NIFTY AUTO": ("^CNXAUTO", "2004-01-01"),   "NIFTY FMCG": ("^CNXFMCG", "1996-01-01"),
    "NIFTY PHARMA": ("^CNXPHARMA", "2001-01-01"),"NIFTY METAL": ("^CNXMETAL", "2004-01-01"),
    "NIFTY REALTY": ("^CNXREALTY", "2007-01-01"),"NIFTY ENERGY": ("^CNXENERGY", "2001-01-01"),
    "NIFTY INFRA": ("^CNXINFRA", "2004-01-01"), "NIFTY MEDIA": ("^CNXMEDIA", "2005-01-01"),
    "NIFTY PSU BANK": ("^CNXPSUBANK", "2004-01-01"),"NIFTY PRIVATE BANK": ("^NSPVTBNK", "2004-01-01"),
    "INDIA VIX": ("^INDIAVIX", "2008-01-01"),   "NIFTY MIDCAP 50": ("^NSEMDCP50", "2005-01-01"),
    "NIFTY FINANCIAL SERVICES": ("^CNXFINANCE", "2004-01-01"),
    "SENSEX": ("^BSESN", "1997-01-01"),         "BSE 500": ("BSE-500.BO", "1999-01-01"),
}


def ensure_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS indices_data (
        name TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, adj_close REAL,
        PRIMARY KEY(name, date))""")
    conn.commit()


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_table(conn)

    ok, empty, total_rows = [], [], 0
    for name, (ticker, start) in NSE_INDEX_MASTER.items():
        try:
            df = yf.download(ticker, start=start, auto_adjust=True, progress=False, threads=False)
            if df is None or df.empty:
                empty.append(name); print(f"  [empty] {name} ({ticker})", flush=True); continue
            df = df.reset_index()
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            rows = []
            for _, r in df.iterrows():
                d = pd.to_datetime(r["Date"]).strftime("%Y-%m-%d")
                close = r.get("Close")
                if pd.isna(close):
                    continue
                rows.append((name, d, r.get("Open"), r.get("High"), r.get("Low"),
                             close, r.get("Volume"), close))
            if rows:
                conn.executemany(
                    "INSERT OR REPLACE INTO indices_data "
                    "(name,date,open,high,low,close,volume,adj_close) VALUES (?,?,?,?,?,?,?,?)", rows)
                conn.commit()
                total_rows += len(rows)
                ok.append(name)
                print(f"  [ok]    {name:26} {len(rows):,} rows", flush=True)
            time.sleep(0.5)
        except Exception as e:
            empty.append(name); print(f"  [err]   {name} ({ticker}): {str(e)[:80]}", flush=True)

    mn, mx, n = conn.execute("SELECT MIN(date),MAX(date),COUNT(*) FROM indices_data").fetchone()
    conn.close()
    print(f"\nDONE: {len(ok)} indices loaded, {len(empty)} unavailable ({total_rows:,} rows). "
          f"indices_data now {n:,} rows, {mn} -> {mx}", flush=True)
    if empty:
        print("Unavailable on Yahoo:", ", ".join(empty))


if __name__ == "__main__":
    main()
