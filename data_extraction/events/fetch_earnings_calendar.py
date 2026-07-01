#!/usr/bin/env python3
"""fetch_earnings_calendar.py — Corporate board meetings + financial-results
filings from NSE. board_meetings = upcoming results/dividend dates (forward,
accumulates); financial_results = filed results metadata. Idempotent.

Run:  py -3.14 events/fetch_earnings_calendar.py
"""
import re
import sqlite3
from pathlib import Path
from datetime import datetime

import requests

DB_PATH = Path(r"D:\marketDB\db\market.db")


def sess():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                      "Accept": "application/json, text/plain, */*", "Referer": "https://www.nseindia.com/"})
    try:
        s.get("https://www.nseindia.com", timeout=12)
    except Exception:
        pass
    return s


def _iso(d):
    """Parse a date that may carry a trailing time component (NSE sends
    '25-Jun-2026 16:39:17'). Never returns a truncated partial date."""
    if not d:
        return None
    s = str(d).strip()
    candidates = [s, s.split()[0] if s.split() else s]   # full, then date token
    fmts = ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d/%m/%Y")
    for cand in candidates:
        for fmt in fmts:
            try:
                return datetime.strptime(cand, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    m = re.search(r"\d{1,2}-[A-Za-z]{3}-\d{4}", s) or re.search(r"\d{4}-\d{2}-\d{2}", s)
    if m:
        for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(m.group(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return None   # unparseable -> NULL, never a half date


def main():
    s = sess()
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("""CREATE TABLE IF NOT EXISTS board_meetings (
        symbol TEXT, meeting_date TEXT, purpose TEXT, description TEXT, industry TEXT,
        company TEXT, fetched_at TEXT, PRIMARY KEY(symbol, meeting_date, purpose))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS financial_results (
        symbol TEXT, period TEXT, broadcast_date TEXT, audited TEXT, consolidated TEXT,
        company TEXT, fetched_at TEXT, PRIMARY KEY(symbol, period, broadcast_date))""")
    conn.commit()
    now = datetime.now().isoformat()

    # 1) Board meetings (upcoming results / dividend / buyback dates)
    try:
        d = s.get("https://www.nseindia.com/api/corporate-board-meetings?index=equities", timeout=25).json()
        recs = d if isinstance(d, list) else d.get("data", [])
        rows = [(r.get("bm_symbol"), _iso(r.get("bm_date")), (r.get("bm_purpose") or "").strip(),
                 (r.get("bm_desc") or "").strip()[:300], r.get("sm_indusrty"), r.get("sm_name"), now)
                for r in recs if r.get("bm_symbol")]
        if rows:
            conn.executemany("INSERT OR REPLACE INTO board_meetings VALUES (?,?,?,?,?,?,?)", rows)
            conn.commit()
        print(f"  board_meetings: {len(rows)}", flush=True)
    except Exception as e:
        print(f"  board_meetings ERR {str(e)[:50]}", flush=True)

    # 2) Financial results filings
    try:
        d = s.get("https://www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly",
                  timeout=30).json()
        recs = d if isinstance(d, list) else d.get("data", [])
        rows = []
        for r in recs:
            sym = r.get("symbol") or r.get("Symbol")
            if not sym:
                continue
            rows.append((sym, "Quarterly", _iso(r.get("broadCastDate")),
                         str(r.get("audited")), str(r.get("consolidated")), r.get("companyName"), now))
        if rows:
            conn.executemany("INSERT OR REPLACE INTO financial_results VALUES (?,?,?,?,?,?,?)", rows)
            conn.commit()
        print(f"  financial_results: {len(rows)}", flush=True)
    except Exception as e:
        print(f"  financial_results ERR {str(e)[:50]}", flush=True)

    bm = conn.execute("SELECT COUNT(*) FROM board_meetings").fetchone()[0]
    fr = conn.execute("SELECT COUNT(*) FROM financial_results").fetchone()[0]
    conn.close()
    print(f"DONE: board_meetings {bm:,} | financial_results {fr:,}", flush=True)


if __name__ == "__main__":
    main()
