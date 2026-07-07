#!/usr/bin/env python3
"""fetch_index_constituents.py — NSE index membership + sector (Industry) per
NIFTY index. Fills index_constituents (which stocks are in each index, plus the
official NSE Industry/sector for each). nifty500 alone gives sector for 500 names.
Run periodically (membership changes on rebalances). Idempotent.

Run:  py -3.14 registry/fetch_index_constituents.py
"""
import sqlite3, csv, io
from pathlib import Path
from datetime import date

import requests

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
INDICES = {
    "nifty50": "NIFTY 50", "niftynext50": "NIFTY NEXT 50", "nifty100": "NIFTY 100",
    "nifty200": "NIFTY 200", "nifty500": "NIFTY 500", "niftymidcap100": "NIFTY MIDCAP 100",
    "niftysmallcap100": "NIFTY SMALLCAP 100", "niftybank": "NIFTY BANK", "niftyit": "NIFTY IT",
    "niftyauto": "NIFTY AUTO", "niftyfmcg": "NIFTY FMCG", "niftypharma": "NIFTY PHARMA",
    "niftymetal": "NIFTY METAL", "niftyenergy": "NIFTY ENERGY", "niftyrealty": "NIFTY REALTY",
    "niftyinfra": "NIFTY INFRA", "niftymedia": "NIFTY MEDIA", "niftypsubank": "NIFTY PSU BANK",
    "niftyhealthcare": "NIFTY HEALTHCARE", "niftyconsumerdurables": "NIFTY CONSUMER DURABLES",
    "niftyoilgas": "NIFTY OIL GAS", "niftyprivatebank": "NIFTY PRIVATE BANK",
    "niftyfinservice": "NIFTY FINANCIAL SERVICES",
}


def main():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"})
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("""CREATE TABLE IF NOT EXISTS index_constituents (
        index_name TEXT, symbol TEXT, company TEXT, industry TEXT, isin TEXT, updated TEXT,
        PRIMARY KEY(index_name, symbol))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ic_symbol ON index_constituents(symbol)")
    conn.commit()

    today = date.today().strftime("%Y-%m-%d")
    tot = 0
    for fn, disp in INDICES.items():
        try:
            r = s.get(f"https://nsearchives.nseindia.com/content/indices/ind_{fn}list.csv", timeout=15)
            if r.status_code != 200 or "Symbol" not in r.text:
                print(f"  {disp}: HTTP {r.status_code}")
                continue
            rows = []
            for row in csv.DictReader(io.StringIO(r.text)):
                sym = (row.get("Symbol") or "").strip()
                if not sym:
                    continue
                rows.append((disp, sym, (row.get("Company Name") or "").strip(),
                             (row.get("Industry") or "").strip(), (row.get("ISIN Code") or "").strip(), today))
            if rows:
                conn.executemany("INSERT OR REPLACE INTO index_constituents VALUES (?,?,?,?,?,?)", rows)
                conn.commit()
                tot += len(rows)
            print(f"  {disp}: {len(rows)} stocks")
        except Exception as e:
            print(f"  {disp}: ERR {str(e)[:40]}")

    n = conn.execute("SELECT COUNT(*),COUNT(DISTINCT index_name),COUNT(DISTINCT symbol) FROM index_constituents").fetchone()
    conn.close()
    print(f"DONE: index_constituents {n[0]:,} rows, {n[1]} indices, {n[2]} unique symbols", flush=True)


if __name__ == "__main__":
    main()
