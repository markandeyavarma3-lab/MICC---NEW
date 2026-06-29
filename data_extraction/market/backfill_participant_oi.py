#!/usr/bin/env python3
"""backfill_participant_oi.py — Participant-wise F&O Open Interest
(Client / DII / FII / Pro / TOTAL) from NSE archive dated CSVs
(fao_participant_oi_<DDMMYYYY>.csv), ~2014 -> now. Idempotent; skips
dates already present. Run:  py -3.14 market/backfill_participant_oi.py
"""
import sqlite3, time
from pathlib import Path
from datetime import date, timedelta

import requests

DB_PATH = Path(r"D:\marketDB\db\market.db")
URLS = [
    "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{d}.csv",
    "https://archives.nseindia.com/content/nsccl/fao_participant_oi_{d}.csv",
]


def sess():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                      "Referer": "https://www.nseindia.com/"})
    try:
        s.get("https://www.nseindia.com", timeout=12)
    except Exception:
        pass
    return s


def ensure(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS participant_oi (
        date TEXT, category TEXT, index_fut_long REAL, index_fut_short REAL, index_fut_net REAL,
        index_call_long REAL, index_call_short REAL, index_put_long REAL, index_put_short REAL,
        stock_fut_long REAL, stock_fut_short REAL, stock_fut_net REAL,
        stock_call_long REAL, stock_put_long REAL, last_updated TEXT,
        PRIMARY KEY(date, category))""")
    conn.commit()


def fetch(s, d):
    for tmpl in URLS:
        try:
            r = s.get(tmpl.format(d=d.strftime("%d%m%Y")), timeout=20)
            if r.status_code == 200 and "Participant" in r.text:
                return r.text
        except Exception:
            pass
    return None


def parse(txt, iso):
    rows = []
    for line in txt.strip().split("\n")[2:]:        # skip title + header
        p = [x.strip() for x in line.split(",")]
        if len(p) < 13 or not p[0]:
            continue
        def n(i):
            try:
                return float(p[i])
            except Exception:
                return None
        ifl, ifs = n(1), n(2)
        sfl, sfs = n(3), n(4)
        net = lambda a, b: (a - b) if (a is not None and b is not None) else None
        rows.append((iso, p[0], ifl, ifs, net(ifl, ifs),
                     n(5), n(7), n(6), n(8),            # idx call long/short, put long/short
                     sfl, sfs, net(sfl, sfs),
                     n(9), n(10), None))                # stock call long, put long
    return rows


def main():
    s = sess()
    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA busy_timeout=180000")
    ensure(conn)
    have = {r[0] for r in conn.execute("SELECT DISTINCT date FROM participant_oi")}

    d, end = date(2014, 1, 1), date.today()
    tot = done = 0
    while d <= end:
        if d.weekday() < 5:
            iso = d.strftime("%Y-%m-%d")
            if iso not in have:
                txt = fetch(s, d)
                if txt:
                    rows = parse(txt, iso)
                    if rows:
                        conn.executemany(
                            "INSERT OR REPLACE INTO participant_oi VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                        tot += len(rows)
                time.sleep(0.25)
                done += 1
                if done % 200 == 0:
                    conn.commit()
                    print(f"  {iso}: {tot:,} rows so far", flush=True)
        d += timedelta(days=1)
    conn.commit()
    n = conn.execute("SELECT COUNT(*),COUNT(DISTINCT date),MIN(date),MAX(date) FROM participant_oi").fetchone()
    conn.close()
    print(f"DONE: participant_oi {n[0]:,} rows, {n[1]} dates, {n[2]} -> {n[3]}", flush=True)


if __name__ == "__main__":
    main()
