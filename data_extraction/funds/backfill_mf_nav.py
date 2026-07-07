#!/usr/bin/env python3
"""backfill_mf_nav.py — Bulk MF NAV history from AMFI (all schemes, one request
per date-window). Far faster than per-scheme mftool. Fills mf_nav_history.

AMFI history goes back to ~2006. Default window keeps the table useful without
exploding (all ~17k schemes daily => ~2-3M rows/year). Extend with --from.

Run:  py -3.14 funds/backfill_mf_nav.py             # default from 2023
      py -3.14 funds/backfill_mf_nav.py --from 2018
"""
import sqlite3, sys, time
from pathlib import Path
from datetime import date, timedelta

import requests

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?frmdt={f}&todt={t}"


def ensure(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS mf_nav_history (
        scheme_code TEXT, scheme_name TEXT, date TEXT, nav REAL,
        PRIMARY KEY(scheme_code, date))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mfnav_date ON mf_nav_history(date)")
    conn.commit()


def parse(txt):
    rows = []
    from datetime import datetime
    for line in txt.split("\n"):
        p = line.strip().split(";")
        if len(p) < 8 or not p[0].strip().isdigit():
            continue
        try:
            nav = float(p[4])
        except Exception:
            continue
        try:
            d = datetime.strptime(p[7].strip(), "%d-%b-%Y").strftime("%Y-%m-%d")
        except Exception:
            continue
        rows.append((p[0].strip(), p[1].strip(), d, nav))
    return rows


def main():
    year_from = 2023
    if "--from" in sys.argv:
        year_from = int(sys.argv[sys.argv.index("--from") + 1])

    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    ensure(conn)

    cur, end = date(year_from, 1, 1), date.today()
    total = 0
    while cur <= end:
        # one calendar month per request
        if cur.month == 12:
            nxt = date(cur.year, 12, 31)
        else:
            nxt = date(cur.year, cur.month + 1, 1) - timedelta(days=1)
        nxt = min(nxt, end)
        url = URL.format(f=cur.strftime("%d-%b-%Y"), t=nxt.strftime("%d-%b-%Y"))
        try:
            txt = s.get(url, timeout=90).text
            rows = parse(txt)
            if rows:
                conn.executemany(
                    "INSERT OR REPLACE INTO mf_nav_history (scheme_code,scheme_name,date,nav) "
                    "VALUES (?,?,?,?)", rows)
                conn.commit()
                total += len(rows)
            print(f"  {cur.strftime('%Y-%m')}: {len(rows):,} rows ({total:,} total)", flush=True)
        except Exception as e:
            print(f"  {cur.strftime('%Y-%m')}: error {str(e)[:60]}", flush=True)
        time.sleep(0.4)
        cur = nxt + timedelta(days=1)

    n, nd, mn, mx = conn.execute(
        "SELECT COUNT(*),COUNT(DISTINCT scheme_code),MIN(date),MAX(date) FROM mf_nav_history").fetchone()
    conn.close()
    print(f"DONE: mf_nav_history {n:,} rows, {nd:,} schemes, {mn} -> {mx}", flush=True)


if __name__ == "__main__":
    main()
