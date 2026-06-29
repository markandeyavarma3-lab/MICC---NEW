#!/usr/bin/env python3
"""compute_options_analytics.py — Daily Put-Call Ratio + OI/volume summary per
symbol, computed from fo_data (no scraping). PCR is a core sentiment indicator.
Fills options_pcr_daily for the full F&O history. Idempotent.

Run:  py -3.14 market/compute_options_analytics.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")


def main():
    conn = sqlite3.connect(DB_PATH, timeout=600)
    conn.execute("PRAGMA busy_timeout=600000")
    conn.execute("PRAGMA cache_size=-262144")
    conn.execute("""CREATE TABLE IF NOT EXISTS options_pcr_daily (
        date TEXT, symbol TEXT, call_oi REAL, put_oi REAL, pcr_oi REAL,
        call_vol REAL, put_vol REAL, pcr_vol REAL, total_oi REAL,
        PRIMARY KEY(date, symbol))""")
    conn.commit()

    print("Aggregating PCR from fo_data (full options history) ...", flush=True)
    conn.execute("""
        INSERT OR REPLACE INTO options_pcr_daily
        SELECT date, symbol, call_oi, put_oi,
               CASE WHEN call_oi > 0 THEN CAST(put_oi AS REAL)/call_oi END,
               call_vol, put_vol,
               CASE WHEN call_vol > 0 THEN CAST(put_vol AS REAL)/call_vol END,
               call_oi + put_oi
        FROM (
            SELECT date, symbol,
                   SUM(CASE WHEN option_typ='CE' THEN open_int  ELSE 0 END) AS call_oi,
                   SUM(CASE WHEN option_typ='PE' THEN open_int  ELSE 0 END) AS put_oi,
                   SUM(CASE WHEN option_typ='CE' THEN contracts ELSE 0 END) AS call_vol,
                   SUM(CASE WHEN option_typ='PE' THEN contracts ELSE 0 END) AS put_vol
            FROM fo_data
            WHERE option_typ IN ('CE','PE')
            GROUP BY date, symbol
        )
    """)
    conn.commit()

    n, nd, ns, mn, mx = conn.execute(
        "SELECT COUNT(*),COUNT(DISTINCT date),COUNT(DISTINCT symbol),MIN(date),MAX(date) "
        "FROM options_pcr_daily").fetchone()
    print(f"DONE: options_pcr_daily {n:,} rows, {nd:,} dates, {ns:,} symbols, {mn} -> {mx}", flush=True)
    # quick sanity
    for sym in ("NIFTY", "BANKNIFTY"):
        r = conn.execute("SELECT date,pcr_oi FROM options_pcr_daily WHERE symbol=? ORDER BY date DESC LIMIT 1",
                         (sym,)).fetchone()
        print(f"  latest {sym} PCR(OI):", r, flush=True)
    conn.close()


if __name__ == "__main__":
    main()
