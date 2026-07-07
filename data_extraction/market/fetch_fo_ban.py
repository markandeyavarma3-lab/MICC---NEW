#!/usr/bin/env python3
"""fetch_fo_ban.py — Daily F&O ban list (securities banned for trade).
Forward-only: NSE serves the current day's ban file only. Run daily.

Run:  py -3.14 market/fetch_fo_ban.py
"""
import sqlite3, re
from pathlib import Path
from datetime import datetime

import requests

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
URL = "https://nsearchives.nseindia.com/content/fo/fo_secban.csv"


def main():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"})
    txt = s.get(URL, timeout=15).text

    # Header line: "Securities in Ban For Trade Date 29-JUN-2026: NIL"  (or a numbered list)
    date = datetime.now().strftime("%Y-%m-%d")
    m = re.search(r"Trade Date\s+([0-9A-Za-z\-]+)", txt)
    if m:
        try:
            date = datetime.strptime(m.group(1), "%d-%b-%Y").strftime("%Y-%m-%d")
        except Exception:
            pass

    body = txt.split(":", 1)[1] if ":" in txt else txt
    syms = []
    for tok in re.split(r"[\n,]+", body):
        tok = tok.strip()
        if tok and tok.upper() != "NIL" and re.match(r"^[A-Z&\-]{2,}$", tok):
            syms.append(tok)

    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("CREATE TABLE IF NOT EXISTS fo_ban (date TEXT, symbol TEXT, PRIMARY KEY(date, symbol))")
    if syms:
        conn.executemany("INSERT OR REPLACE INTO fo_ban (date,symbol) VALUES (?,?)",
                         [(date, x) for x in syms])
    conn.commit()
    conn.close()
    print(f"F&O ban {date}: {len(syms)} securities {syms[:12]}", flush=True)


if __name__ == "__main__":
    main()
