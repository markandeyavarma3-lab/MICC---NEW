#!/usr/bin/env python3
"""build_sector_map.py — PHASE 4b: expand sector classification to the liquid universe.

NSE's index_constituents only covers ~507 names; the tradable universe is ~2,243. This
fills the rest via yfinance, normalizes both NSE + yfinance taxonomies to a common
~12-sector scheme, and writes `dim_sector(symbol, sector_raw, sector, source, updated)`.

Resumable + incremental: skips symbols already classified, commits in batches, so it can
be re-run to finish if interrupted. yfinance is slow/flaky -> best-effort.

Run:  py -3.14 registry/build_sector_map.py
"""
import sqlite3
import time
from pathlib import Path

import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")

# normalize NSE-industry + yfinance-GICS sector strings -> common buckets
NORM = {
    # NSE industries
    "information technology": "Information Technology", "financial services": "Financial Services",
    "healthcare": "Healthcare", "fast moving consumer goods": "Consumer Staples",
    "automobile and auto components": "Automobile", "oil gas & consumable fuels": "Energy",
    "metals & mining": "Metals & Materials", "consumer durables": "Consumer Discretionary",
    "consumer services": "Consumer Discretionary", "capital goods": "Industrials",
    "construction": "Industrials", "construction materials": "Metals & Materials",
    "power": "Utilities", "telecommunication": "Telecom", "realty": "Realty",
    "chemicals": "Chemicals", "services": "Services", "media entertainment & publication": "Media",
    "textiles": "Consumer Discretionary", "diversified": "Diversified",
    # yfinance GICS
    "technology": "Information Technology", "healthcare ": "Healthcare",
    "financial services ": "Financial Services", "consumer cyclical": "Consumer Discretionary",
    "consumer defensive": "Consumer Staples", "energy": "Energy", "basic materials": "Metals & Materials",
    "industrials": "Industrials", "utilities": "Utilities", "communication services": "Telecom",
    "real estate": "Realty",
}


def norm(s):
    if not s:
        return None
    return NORM.get(str(s).strip().lower(), str(s).strip())


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("""CREATE TABLE IF NOT EXISTS dim_sector (
        symbol TEXT PRIMARY KEY, sector_raw TEXT, sector TEXT, source TEXT, updated TEXT)""")

    # 1) seed from NSE index_constituents (authoritative)
    nse = pd.read_sql("SELECT DISTINCT symbol, industry FROM index_constituents "
                      "WHERE industry IS NOT NULL", conn).drop_duplicates("symbol")
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    conn.executemany(
        "INSERT OR REPLACE INTO dim_sector VALUES (?,?,?,?,?)",
        [(r.symbol, r.industry, norm(r.industry), "nse", now) for r in nse.itertuples()])
    conn.commit()
    print(f"  seeded {len(nse)} NSE-classified symbols", flush=True)

    # 2) liquid universe needing classification
    universe = [r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM pit_universe WHERE top500=1").fetchall()]
    done = {r[0] for r in conn.execute("SELECT symbol FROM dim_sector").fetchall()}
    todo = [s for s in universe if s not in done]
    print(f"  universe {len(universe)} | classified {len(done)} | to fetch {len(todo)} via yfinance",
          flush=True)

    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance not available — NSE-only sector map written.", flush=True)
        conn.close(); return

    ok = fail = 0
    for i, sym in enumerate(todo, 1):
        sec = None
        try:
            info = yf.Ticker(f"{sym}.NS").info
            sec = info.get("sector")
        except Exception:
            sec = None
        if sec:
            conn.execute("INSERT OR REPLACE INTO dim_sector VALUES (?,?,?,?,?)",
                         (sym, sec, norm(sec), "yfinance", time.strftime("%Y-%m-%dT%H:%M:%S")))
            ok += 1
        else:
            fail += 1
        if i % 50 == 0:
            conn.commit()
            print(f"    {i}/{len(todo)}  ok={ok} fail={fail}", flush=True)
        time.sleep(0.2)
    conn.commit()

    tot = conn.execute("SELECT COUNT(*) FROM dim_sector").fetchone()[0]
    cov = conn.execute(
        "SELECT COUNT(DISTINCT p.symbol) FROM pit_universe p JOIN dim_sector d ON p.symbol=d.symbol "
        "WHERE p.top500=1").fetchone()[0]
    print(f"\nDONE: dim_sector {tot} symbols (yfinance ok={ok}, fail={fail})", flush=True)
    print(f"  liquid-universe coverage: {cov}/{len(universe)} ({cov/len(universe)*100:.0f}%)", flush=True)
    for s, n in conn.execute("SELECT sector,COUNT(*) FROM dim_sector GROUP BY sector ORDER BY 2 DESC LIMIT 8"):
        print(f"    {s:24} {n}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
