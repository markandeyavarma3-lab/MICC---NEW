#!/usr/bin/env python3
"""backfill_deals.py — Historical bulk / block / short deals from the NSE
historicalOR CSV download (uncapped, unlike the 70-row JSON). Idempotent.
  bulk_deals  : 2006 -> now   (date,symbol,name,client,buy/sell,qty,price,remarks)
  block_deals : 2006 -> now   (same)
  short_deals : 2018 -> now   (date,symbol,name,qty only)

Run:  py -3.14 market/backfill_deals.py
"""
import sqlite3, csv, io, time
from pathlib import Path
from datetime import datetime, date

import requests

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
BASE = ("https://www.nseindia.com/api/historicalOR/bulk-block-short-deals"
        "?optionType={ot}&from={f}&to={t}&csv=true")


def sess():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                      "Accept": "*/*",
                      "Referer": "https://www.nseindia.com/report-detail/display-bulk-and-block-deals"})
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


def _num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return None


def _iso(d):
    try:
        return datetime.strptime(d.strip(), "%d-%b-%Y").strftime("%Y-%m-%d")
    except Exception:
        return None


def fetch_csv(s, ot, frm, to):
    try:
        txt = s.get(BASE.format(ot=ot, f=frm, t=to), timeout=45).text
        return list(csv.reader(io.StringIO(txt)))
    except Exception:
        return []


def main():
    s = sess()
    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA busy_timeout=180000")
    ensure(conn)
    today = date.today()

    # (optionType, table, start_year, schema_kind)
    jobs = [("bulk_deals", "bulk_deals", 2006, "full"),
            ("block_deals", "block_deals", 2006, "full"),
            ("short_selling", "short_deals", 2018, "short")]

    for ot, table, yr0, kind in jobs:
        tot = 0
        for yr in range(yr0, today.year + 1):
            frm = f"01-01-{yr}"
            to = f"31-12-{yr}" if yr < today.year else today.strftime("%d-%m-%Y")
            rows = fetch_csv(s, ot, frm, to)
            out = []
            for r in rows[1:]:                       # skip header
                if len(r) < 4:
                    continue
                d = _iso(r[0])
                if not d:
                    continue
                if kind == "full" and len(r) >= 7:
                    out.append((d, r[1].strip(), r[2].strip(), r[3].strip(), r[4].strip(),
                                _num(r[5]), _num(r[6]), (r[7].strip() if len(r) > 7 else None)))
                elif kind == "short":
                    out.append((d, r[1].strip(), r[2].strip(), None, None, _num(r[3]), None, None))
            if out:
                conn.executemany(
                    f"INSERT OR REPLACE INTO {table} "
                    f"(date,symbol,name,client,buy_sell,qty,price,remarks) VALUES (?,?,?,?,?,?,?,?)", out)
                conn.commit()
                tot += len(out)
            print(f"  {table} {yr}: {len(out):,} ({tot:,} total)", flush=True)
            time.sleep(0.4)
        print(f"{table} DONE: {tot:,} rows", flush=True)

    for t in ("bulk_deals", "block_deals", "short_deals"):
        print(t, conn.execute(f"SELECT COUNT(*),MIN(date),MAX(date) FROM {t}").fetchone(), flush=True)
    conn.close()


if __name__ == "__main__":
    main()
