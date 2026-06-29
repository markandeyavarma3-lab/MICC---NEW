#!/usr/bin/env python3
"""fetch_index_valuation.py — Backfill index PE / PB / Dividend-Yield from
niftyindices.com (the official NSE index site). Fills index_valuation, 2005->now.
Idempotent (INSERT OR REPLACE), chunked per year.

Run:  py -3.14 market/fetch_index_valuation.py
"""
import sqlite3, json, time
from pathlib import Path
from datetime import datetime

import requests

DB_PATH = Path(r"D:\marketDB\db\market.db")
PEPB_URL = "https://www.niftyindices.com/Backpage.aspx/getpepbHistoricaldataDBtoString"

INDICES = [
    "NIFTY 50", "NIFTY NEXT 50", "NIFTY 100", "NIFTY 200", "NIFTY 500",
    "NIFTY MIDCAP 100", "NIFTY SMALLCAP 100", "NIFTY BANK", "NIFTY IT",
    "NIFTY AUTO", "NIFTY FMCG", "NIFTY PHARMA", "NIFTY METAL", "NIFTY ENERGY",
    "NIFTY REALTY", "NIFTY INFRASTRUCTURE", "NIFTY MEDIA", "NIFTY PSU BANK",
    "NIFTY PRIVATE BANK", "NIFTY FINANCIAL SERVICES", "NIFTY HEALTHCARE INDEX",
]


def sess():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json; charset=UTF-8",
        "Referer": "https://www.niftyindices.com/reports/historical-data",
        "Origin": "https://www.niftyindices.com",
        "X-Requested-With": "XMLHttpRequest",
    })
    try:
        s.get("https://www.niftyindices.com", timeout=15)
    except Exception:
        pass
    return s


def fetch(s, name, start, end):
    payload = {"cinfo": "{'name':'%s','startDate':'%s','endDate':'%s','indexName':'%s'}"
               % (name, start, end, name)}
    r = s.post(PEPB_URL, data=json.dumps(payload), timeout=40)
    if r.status_code != 200:
        return []
    try:
        data = json.loads(r.json()["d"])
    except Exception:
        return []
    out = []
    for x in data:
        try:
            d = datetime.strptime(x["DATE"].strip(), "%d %b %Y").strftime("%Y-%m-%d")
        except Exception:
            continue
        def f(v):
            try:
                return float(v)
            except Exception:
                return None
        out.append((name, d, f(x.get("pe")), f(x.get("pb")), f(x.get("divYield"))))
    return out


def main():
    s = sess()
    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA busy_timeout=180000")
    conn.execute("""CREATE TABLE IF NOT EXISTS index_valuation (
        index_name TEXT, date TEXT, pe REAL, pb REAL, div_yield REAL,
        PRIMARY KEY(index_name, date))""")
    conn.commit()

    today = datetime.now()
    grand = 0
    for name in INDICES:
        got = 0
        for yr in range(2005, today.year + 1):
            start = f"01-Jan-{yr}"
            end = f"31-Dec-{yr}" if yr < today.year else today.strftime("%d-%b-%Y")
            try:
                rows = fetch(s, name, start, end)
                if rows:
                    conn.executemany(
                        "INSERT OR REPLACE INTO index_valuation "
                        "(index_name,date,pe,pb,div_yield) VALUES (?,?,?,?,?)", rows)
                    conn.commit()
                    got += len(rows)
            except Exception:
                pass
            time.sleep(0.25)
        grand += got
        print(f"  {name:30} {got:,} rows", flush=True)

    mn, mx, n = conn.execute("SELECT MIN(date),MAX(date),COUNT(*) FROM index_valuation").fetchone()
    conn.close()
    print(f"DONE: index_valuation {n:,} rows, {mn} -> {mx} ({grand:,} processed)", flush=True)


if __name__ == "__main__":
    main()
