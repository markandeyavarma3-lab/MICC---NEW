#!/usr/bin/env python3
"""fetch_ipo.py — IPO data (GMP, subscription, price band, dates, listing) from
investorgain's JSON report. Mainboard + SME. Values arrive HTML-wrapped, so we
strip tags/entities. Idempotent per IPO name. Run periodically to accumulate.

Run:  py -3.14 events/fetch_ipo.py
"""
import sqlite3, re, html, time
from pathlib import Path
from datetime import datetime

import requests

DB_PATH = Path(r"D:\marketDB\db\market.db")
# 331 = "Live IPO GMP" report; FY path gives that financial year's IPOs
URLS = [
    "https://webnodejs.investorgain.com/cloud/report/data-read/331/1/5/{y}/{fy}/0/all?search=&v=09-25",
]
# (calendar_year, financial_year) windows to pull for some history
WINDOWS = [(2027, "2027-28"), (2026, "2026-27"), (2025, "2025-26"),
           (2024, "2024-25"), (2023, "2023-24"), (2022, "2022-23"), (2021, "2021-22")]

FIELDS = ["Name", "GMP", "Rating", "Sub", "Price (₹)", "IPO Size", "Lot",
          "Open", "Close", "BoA Dt", "Listing", "Updated-On"]


def clean(v):
    if v is None:
        return None
    t = re.sub(r"<[^>]+>", "", str(v))
    t = html.unescape(t).strip()
    return t or None


def ensure(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS ipo_data (
        name TEXT PRIMARY KEY, gmp TEXT, rating TEXT, subscription TEXT, price TEXT,
        ipo_size TEXT, lot TEXT, open_date TEXT, close_date TEXT, boa_date TEXT,
        listing TEXT, updated_on TEXT, fetched_at TEXT)""")
    conn.commit()


def main():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                      "Accept": "application/json, text/plain, */*",
                      "Referer": "https://www.investorgain.com/"})
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    ensure(conn)
    now = datetime.now().isoformat()
    tot = 0

    for y, fy in WINDOWS:
        for tmpl in URLS:
            try:
                j = s.get(tmpl.format(y=y, fy=fy), timeout=30).json()
                recs = j.get("reportTableData", [])
                rows = []
                for r in recs:
                    name = clean(r.get("Name"))
                    if not name:
                        continue
                    rows.append((name, clean(r.get("GMP")), clean(r.get("Rating")), clean(r.get("Sub")),
                                 clean(r.get("Price (₹)")), clean(r.get("IPO Size")), clean(r.get("Lot")),
                                 clean(r.get("Open")), clean(r.get("Close")), clean(r.get("BoA Dt")),
                                 clean(r.get("Listing")), clean(r.get("Updated-On")), now))
                if rows:
                    conn.executemany("""INSERT OR REPLACE INTO ipo_data
                        (name,gmp,rating,subscription,price,ipo_size,lot,open_date,close_date,
                         boa_date,listing,updated_on,fetched_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
                    conn.commit()
                    tot += len(rows)
                print(f"  FY {fy}: {len(rows)} IPOs", flush=True)
            except Exception as e:
                print(f"  FY {fy}: ERR {str(e)[:50]}", flush=True)
            time.sleep(0.5)

    n = conn.execute("SELECT COUNT(*) FROM ipo_data").fetchone()[0]
    conn.close()
    print(f"DONE: ipo_data +{tot} this run, {n:,} total", flush=True)


if __name__ == "__main__":
    main()
