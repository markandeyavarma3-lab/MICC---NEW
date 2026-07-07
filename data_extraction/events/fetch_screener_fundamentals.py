#!/usr/bin/env python3
"""fetch_screener_fundamentals.py — Part 2 Module 6a (FETCHER ONLY).

Collects deep annual fundamentals history (~10-12 years) from screener.in for the
current top-500 universe, so depth accumulates in the background NOW. INTEGRATION
IS DEFERRED: screener shows RESTATED numbers, so nothing here may touch
fundamentals_pit / value scoring until a dedicated Part-3 verification pass
(overlap-check vs fundamentals_pit, PIT caveats documented). Raw storage only.

Tables:
  screener_raw    (symbol PK) raw parsed tables as JSON + fetch metadata
  screener_annual (symbol, fiscal_year, field, value) parsed annual P&L rows

Polite scraping: personal use, ~3s + jitter between requests, browser UA,
resumable (skips symbols fetched < REFRESH_DAYS ago), --limit N for testing.
Full top-500 run ~30 min; wired as a weekly background phase.

Run:  py -3.14 events/fetch_screener_fundamentals.py [--limit N]
"""
import io
import json
import random
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
REFRESH_DAYS = 30
SLEEP_S = 3.0
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

DDL = ["""CREATE TABLE IF NOT EXISTS screener_raw (
    symbol TEXT PRIMARY KEY, url TEXT, is_consolidated INTEGER,
    n_tables INTEGER, payload_json TEXT, fetched_at TEXT)""",
       """CREATE TABLE IF NOT EXISTS screener_annual (
    symbol TEXT, fiscal_year TEXT, field TEXT, value REAL,
    is_consolidated INTEGER, fetched_at TEXT,
    PRIMARY KEY (symbol, fiscal_year, field))"""]


def fetch_page(symbol):
    """Try consolidated first, fall back to standalone. Returns (html, url, is_cons)."""
    for url, cons in [(f"https://www.screener.in/company/{symbol}/consolidated/", 1),
                      (f"https://www.screener.in/company/{symbol}/", 0)]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
            if "profit-loss" in html:
                return html, url, cons
        except Exception:
            continue
    return None, None, None


def parse_annual_pl(html):
    """Extract the annual P&L table: rows = fields, columns = fiscal years (Mar YYYY)."""
    tables = pd.read_html(io.StringIO(html))
    best = None
    for t in tables:
        cols = [str(c) for c in t.columns]
        period_cols = [c for c in cols if c[:4] in ("Mar ", "Dec ", "Jun ", "Sep ")]
        mar_cols = [c for c in period_cols if c.startswith("Mar ")]
        # ANNUAL P&L: >=5 period columns, (nearly) all fiscal-year-end "Mar YYYY".
        # The quarterly table has mixed Jun/Sep/Dec months -> rejected here.
        first_col = t.iloc[:, 0].astype(str).str.cat(sep="|") if len(t) else ""
        if (len(period_cols) >= 5 and len(mar_cols) / len(period_cols) >= 0.8
                and ("Sales" in first_col or "Revenue" in first_col)):
            if best is None or len(mar_cols) > best[1]:
                best = (t, len(mar_cols))
    if best is None:
        return []
    t = best[0]
    rows = []
    for _, r in t.iterrows():
        field = str(r.iloc[0]).replace("+", "").strip()
        if not field or field == "nan":
            continue
        for c in t.columns[1:]:
            cs = str(c)
            if not cs[:3] in ("Mar", "Dec", "Jun", "Sep"):
                continue
            raw = str(r[c]).replace(",", "").replace("%", "").strip()
            try:
                val = float(raw)
            except ValueError:
                continue
            rows.append((field, cs, val))
    return rows


def universe(conn):
    return [s for s, in conn.execute(
        "SELECT p.symbol FROM pit_universe p LEFT JOIN dim_sector d ON p.symbol=d.symbol "
        "WHERE p.rebal_date=(SELECT MAX(rebal_date) FROM pit_universe) AND p.top500=1 "
        "AND COALESCE(d.sector,'') != 'ETF' ORDER BY p.adv_rank")]


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    conn = sqlite3.connect(DB_PATH, timeout=120)
    for d in DDL:
        conn.execute(d)
    conn.commit()

    cutoff = (datetime.now() - timedelta(days=REFRESH_DAYS)).isoformat()
    done = {r[0] for r in conn.execute(
        "SELECT symbol FROM screener_raw WHERE fetched_at > ?", (cutoff,))}
    todo = [s for s in universe(conn) if s not in done]
    if limit:
        todo = todo[:limit]
    print(f"  universe top-500 (ex-ETF): {len(done)} fresh, {len(todo)} to fetch", flush=True)

    ok = fail = 0
    for i, sym in enumerate(todo):
        html, url, cons = fetch_page(sym)
        now = datetime.now().isoformat()
        if html is None:
            fail += 1
            conn.execute("INSERT OR REPLACE INTO screener_raw VALUES (?,?,?,?,?,?)",
                         (sym, None, None, 0, None, now))
        else:
            try:
                rows = parse_annual_pl(html)
            except Exception:
                rows = []
            conn.execute("INSERT OR REPLACE INTO screener_raw VALUES (?,?,?,?,?,?)",
                         (sym, url, cons, len(rows), json.dumps(rows[:2000]), now))
            conn.execute("DELETE FROM screener_annual WHERE symbol=?", (sym,))
            conn.executemany("INSERT OR REPLACE INTO screener_annual VALUES (?,?,?,?,?,?)",
                             [(sym, fy, f, v, cons, now) for f, fy, v in rows])
            ok += 1
        conn.commit()
        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{len(todo)} done ({ok} ok, {fail} fail)", flush=True)
        time.sleep(SLEEP_S + random.uniform(0, 1.5))

    yrs = conn.execute("SELECT COUNT(DISTINCT symbol), COUNT(DISTINCT fiscal_year) "
                       "FROM screener_annual").fetchone()
    print(f"  DONE: {ok} fetched, {fail} failed | screener_annual: "
          f"{yrs[0]} symbols x up to {yrs[1]} fiscal years", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
