#!/usr/bin/env python3
"""fetch_deals.py — Daily bulk / block / short deals from NSE.
Forward-only: NSE's snapshot endpoint serves the latest trading day only
(historical deal APIs are blocked), so run this daily to accumulate history.

Run:  py -3.14 market/fetch_deals.py
"""
import sqlite3
from pathlib import Path
from datetime import datetime

import requests

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
URL = "https://www.nseindia.com/api/snapshot-capital-market-largedeal"


def session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    })
    try:
        s.get("https://www.nseindia.com", timeout=12)
    except Exception:
        pass
    return s


def ensure(conn):
    for t in ("bulk_deals", "block_deals", "short_deals"):
        conn.execute(f"""CREATE TABLE IF NOT EXISTS {t} (
            date TEXT, symbol TEXT, name TEXT, client TEXT, buy_sell TEXT,
            qty REAL, price REAL, remarks TEXT,
            PRIMARY KEY(date, symbol, client, buy_sell, qty))""")
    conn.commit()


def to_iso(d):
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(d).strip(), fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return str(d)


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except Exception:
        return None


def main():
    s = session()
    j = s.get(URL, timeout=25).json()
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    ensure(conn)
    tot = {}
    for key, table in [("BULK_DEALS_DATA", "bulk_deals"),
                       ("BLOCK_DEALS_DATA", "block_deals"),
                       ("SHORT_DEALS_DATA", "short_deals")]:
        rows = []
        for r in (j.get(key) or []):
            rows.append((to_iso(r.get("date", "")), r.get("symbol"), r.get("name"),
                         r.get("clientName"), r.get("buySell"),
                         _num(r.get("qty")), _num(r.get("watp")), r.get("remarks")))
        if rows:
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} "
                f"(date,symbol,name,client,buy_sell,qty,price,remarks) VALUES (?,?,?,?,?,?,?,?)", rows)
        tot[table] = len(rows)
    conn.commit()
    conn.close()
    print(f"Deals stored (as_on {j.get('as_on_date')}): {tot}", flush=True)


if __name__ == "__main__":
    main()
