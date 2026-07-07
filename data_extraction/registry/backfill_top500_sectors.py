#!/usr/bin/env python3
"""backfill_top500_sectors.py — Part 1 Stage 1B: guarantee every CURRENT top-500
pit_universe member has a sector, so the Idea Engine's sector-neutral logic never
hits a NULL. The overall dim_sector coverage stays ~60% by design: the missing
~950 names are the illiquid equity tail OUTSIDE the tradable top-500, for which no
free sector source exists -- and the Idea Engine never scores them.

The residual top-500 gap is ETFs (gold/silver/index funds) that enter by turnover
but have no equity sector; they are tagged sector='ETF'. Idempotent.

Run:  py -3.14 registry/backfill_top500_sectors.py
"""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")

# ETFs that reach the top-500 by turnover but carry no equity sector.
KNOWN_ETFS = {"TATSILV", "TATAGOLD", "HDFCGOLD", "HDFCSML250", "GOLD1", "MODEFENCE"}


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120)
    now = datetime.now().isoformat()
    d = conn.execute("SELECT MAX(rebal_date) FROM pit_universe").fetchone()[0]

    gap = [r[0] for r in conn.execute(
        "SELECT p.symbol FROM pit_universe p LEFT JOIN dim_sector s ON p.symbol=s.symbol "
        "WHERE p.rebal_date=? AND p.top500=1 AND s.symbol IS NULL", (d,))]

    tagged = 0
    for sym in gap:
        if sym in KNOWN_ETFS:
            conn.execute("INSERT OR REPLACE INTO dim_sector VALUES (?,?,?,?,?)",
                         (sym, "ETF", "ETF", "manual:etf_classification", now))
            tagged += 1
    conn.commit()

    remaining = conn.execute(
        "SELECT COUNT(*) FROM pit_universe p LEFT JOIN dim_sector s ON p.symbol=s.symbol "
        "WHERE p.rebal_date=? AND p.top500=1 AND s.symbol IS NULL", (d,)).fetchone()[0]
    tot500 = conn.execute("SELECT COUNT(*) FROM pit_universe WHERE rebal_date=? AND top500=1",
                          (d,)).fetchone()[0]
    cov = conn.execute("SELECT COUNT(DISTINCT symbol) FROM dim_sector").fetchone()[0]
    trad = conn.execute("SELECT COUNT(*) FROM tradable_eq_stocks").fetchone()[0]
    print(f"  tagged {tagged} ETFs; top-500 gap now {remaining}/{tot500}", flush=True)
    print(f"  {'PASS' if remaining == 0 else 'FAIL'}: no NULL sector in current top-500", flush=True)
    print(f"  overall dim_sector coverage: {cov}/{trad} = {cov/trad:.0%} "
          f"(tail outside top-500 has no free sector source)", flush=True)
    if remaining:
        print("  still missing:", [r[0] for r in conn.execute(
            "SELECT p.symbol FROM pit_universe p LEFT JOIN dim_sector s ON p.symbol=s.symbol "
            "WHERE p.rebal_date=? AND p.top500=1 AND s.symbol IS NULL", (d,))], flush=True)
    conn.close()


if __name__ == "__main__":
    main()
