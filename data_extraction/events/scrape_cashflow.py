#!/usr/bin/env python3
"""scrape_cashflow.py — Annual cash-flow statements from screener.in into
quarterly_cashflow. yfinance lacks cash-flow for most Indian tickers, so this
fills the gap. Idempotent per (symbol, report_date). Universe = tradable_eq_stocks.

Run:  py -3.14 events/scrape_cashflow.py
"""
import sqlite3, time, json, io
from pathlib import Path
from datetime import datetime

import requests
import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")


def ensure(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS quarterly_cashflow (
        symbol TEXT, report_date TEXT, data_json TEXT, last_updated TEXT,
        PRIMARY KEY(symbol, report_date))""")
    conn.commit()


def fetch_cashflow(s, symbol):
    for path in ("consolidated/", ""):
        try:
            r = s.get(f"https://www.screener.in/company/{symbol}/{path}", timeout=20)
            if r.status_code != 200:
                continue
            for t in pd.read_html(io.StringIO(r.text)):
                if t.shape[1] < 2:
                    continue
                first = t.iloc[:, 0].astype(str)
                if first.str.contains("Operating Activity", case=False, na=False).any():
                    return t
        except Exception:
            continue
    return None


def parse_year(col):
    try:
        return datetime.strptime(str(col).strip(), "%b %Y").replace(day=1).strftime("%Y-%m-%d")
    except Exception:
        return None


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    ensure(conn)
    syms = [r[0] for r in conn.execute("SELECT symbol FROM tradable_eq_stocks ORDER BY symbol")]

    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    now = datetime.now().isoformat()
    tot = nsym = 0

    for i, sym in enumerate(syms):
        t = fetch_cashflow(s, sym)
        if t is not None:
            t = t.set_index(t.columns[0])
            rows = []
            for col in t.columns:
                rd = parse_year(col)
                if not rd:
                    continue
                d = {str(idx): (None if pd.isna(v) else str(v)) for idx, v in t[col].items()}
                rows.append((sym, rd, json.dumps(d), now))
            if rows:
                conn.executemany(
                    "INSERT OR REPLACE INTO quarterly_cashflow "
                    "(symbol,report_date,data_json,last_updated) VALUES (?,?,?,?)", rows)
                conn.commit()
                tot += len(rows)
                nsym += 1
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(syms)} | {nsym} symbols, {tot} cashflow-years | last {sym}", flush=True)
        time.sleep(0.5)

    n = conn.execute("SELECT COUNT(*),COUNT(DISTINCT symbol) FROM quarterly_cashflow").fetchone()
    conn.close()
    print(f"DONE: quarterly_cashflow {n[0]:,} rows, {n[1]:,} symbols", flush=True)


if __name__ == "__main__":
    main()
