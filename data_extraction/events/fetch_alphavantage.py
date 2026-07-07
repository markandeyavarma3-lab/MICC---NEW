#!/usr/bin/env python3
"""fetch_alphavantage.py — AlphaVantage US-equity fundamentals into market.db.

Pulls three datasets and upserts them into namespaced av_* tables (kept
separate from the India NSE tables so US data never contaminates them):
  * av_earnings_calendar    — full forward calendar (no symbol => all names)
  * av_institutional_holdings — per-symbol 13F holder list
  * av_insider_transactions — per-symbol insider buys/sells

AlphaVantage covers US-listed equities only. Free tier = 25 requests/day.
Idempotent: INSERT OR REPLACE on stable primary keys. Raw earnings CSV is
also dumped to data_storage/raw/alphavantage/ for provenance.

Run:  set ALPHAVANTAGE_KEY=... && py -3.14 events/fetch_alphavantage.py
Env:  ALPHAVANTAGE_KEY (required; get a free key at alphavantage.co/support)
"""
import csv
import io
import os
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

import requests

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
RAW_DIR = Path(__file__).resolve().parents[1].parent / "data_storage" / "raw" / "alphavantage"
API_KEY = os.environ.get("ALPHAVANTAGE_KEY", "")
BASE = "https://www.alphavantage.co/query"

# US symbols to pull holder/insider detail for. Extend as the daily quota allows.
SYMBOLS = ["IBM"]


def _get(params):
    params = {**params, "apikey": API_KEY}
    r = requests.get(BASE, params=params, timeout=60)
    r.raise_for_status()
    return r


def _check_note(payload):
    """AlphaVantage returns a JSON note (not an error) on rate-limit/invalid key."""
    if isinstance(payload, dict):
        for k in ("Note", "Information", "Error Message"):
            if k in payload:
                raise RuntimeError(f"{k}: {payload[k]}")


def ensure_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS av_earnings_calendar (
        symbol TEXT, name TEXT, report_date TEXT, fiscal_date_ending TEXT,
        estimate REAL, currency TEXT, time_of_day TEXT, fetched_at TEXT,
        PRIMARY KEY(symbol, report_date, fiscal_date_ending))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS av_institutional_holdings (
        symbol TEXT, holder_name TEXT, last_reported TEXT, shares_held INTEGER,
        shares_changed INTEGER, shares_changed_pct TEXT, change_type TEXT,
        fetched_at TEXT, PRIMARY KEY(symbol, holder_name, last_reported))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS av_insider_transactions (
        symbol TEXT, transaction_date TEXT, executive TEXT, executive_title TEXT,
        security_type TEXT, acquisition_or_disposal TEXT, shares REAL,
        share_price REAL, fetched_at TEXT,
        PRIMARY KEY(symbol, transaction_date, executive, security_type,
                    acquisition_or_disposal, shares, share_price))""")
    conn.commit()


def _num(v, cast=float):
    try:
        s = str(v).replace(",", "").strip()
        return cast(s) if s not in ("", "n/a", "None") else None
    except (ValueError, TypeError):
        return None


def fetch_earnings_calendar(conn, now):
    r = _get({"function": "EARNINGS_CALENDAR", "horizon": "12month"})
    text = r.content.decode("utf-8")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    (RAW_DIR / f"earnings_calendar_12m_{stamp}.csv").write_text(text, encoding="utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or rows[0][0] != "symbol":
        raise RuntimeError(f"unexpected CSV head: {rows[:1]}")
    out = []
    for row in rows[1:]:
        if len(row) < 7 or not row[0]:
            continue
        out.append((row[0], row[1], row[2] or None, row[3] or None,
                    _num(row[4]), row[5] or None, row[6] or None, now))
    conn.executemany("INSERT OR REPLACE INTO av_earnings_calendar VALUES (?,?,?,?,?,?,?,?)", out)
    conn.commit()
    print(f"  av_earnings_calendar: {len(out)}", flush=True)


def fetch_institutional_holdings(conn, now, symbol):
    d = _get({"function": "INSTITUTIONAL_HOLDINGS", "symbol": symbol}).json()
    _check_note(d)
    holdings = d.get("holdings", []) if isinstance(d, dict) else []
    out = [(symbol, h.get("holder_name"), h.get("last_reported"),
            _num(h.get("shares_held"), int), _num(h.get("shares_changed"), int),
            h.get("shares_changed_percentage"), h.get("change_type"), now)
           for h in holdings if h.get("holder_name")]
    conn.executemany("INSERT OR REPLACE INTO av_institutional_holdings VALUES (?,?,?,?,?,?,?,?)", out)
    conn.commit()
    print(f"  av_institutional_holdings [{symbol}]: {len(out)}", flush=True)


def fetch_insider_transactions(conn, now, symbol):
    d = _get({"function": "INSIDER_TRANSACTIONS", "symbol": symbol}).json()
    _check_note(d)
    recs = d.get("data", []) if isinstance(d, dict) else []
    out = [(rec.get("ticker") or symbol, rec.get("transaction_date"), rec.get("executive"),
            rec.get("executive_title"), rec.get("security_type"),
            rec.get("acquisition_or_disposal"), _num(rec.get("shares")),
            _num(rec.get("share_price")), now)
           for rec in recs if rec.get("transaction_date")]
    conn.executemany("INSERT OR REPLACE INTO av_insider_transactions VALUES (?,?,?,?,?,?,?,?,?)", out)
    conn.commit()
    print(f"  av_insider_transactions [{symbol}]: {len(out)}", flush=True)


def main():
    if not API_KEY:
        print("ERROR: set ALPHAVANTAGE_KEY env var (free key at alphavantage.co/support)", flush=True)
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA busy_timeout=180000")
    ensure_tables(conn)
    now = datetime.now().isoformat()

    steps = [("earnings_calendar", lambda: fetch_earnings_calendar(conn, now))]
    for sym in SYMBOLS:
        steps.append((f"holdings/{sym}", lambda s=sym: fetch_institutional_holdings(conn, now, s)))
        steps.append((f"insider/{sym}", lambda s=sym: fetch_insider_transactions(conn, now, s)))
    for name, fn in steps:
        try:
            fn()
        except Exception as e:
            print(f"  {name} ERR {str(e)[:80]}", flush=True)

    for t in ("av_earnings_calendar", "av_institutional_holdings", "av_insider_transactions"):
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"DONE: {t} {n:,}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
