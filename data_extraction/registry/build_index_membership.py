#!/usr/bin/env python3
"""build_index_membership.py — Part 1 Stage 1A: named point-in-time index
membership (NIFTY 50 / 100 / 200 / 500 + size buckets) with change-dates.

HYBRID, and honest about it:
  * CURRENT membership  -> taken verbatim from index_constituents (the official
    NSE snapshot). method='official', confidence=1.0, effective_to=NULL.
  * HISTORICAL membership -> reconstructed month-by-month from pit_universe's
    Price x Volume liquidity rank (adv_rank). method='reconstructed_turnover'.
    NOTE: turnover rank is a WEAK proxy for NIFTY 50 (measured ~58% agreement vs
    the official current list), better for broad NIFTY 500. Confidence is set
    accordingly and low on purpose so downstream code can filter it out. We do
    NOT claim the doc's optimistic 85-90% (that was market-cap ranking; we only
    have turnover). Every historical row carries its confidence so nothing is
    silently trusted.

Idempotent: rebuilds the whole table each run. Never touches source tables.
Run:  py -3.14 registry/build_index_membership.py
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

DB_PATH = Path(r"D:\marketDB\db\market.db")

# index_name -> (top-N by turnover rank for reconstruction, historical confidence)
RECON = {"NIFTY 50": (50, 0.60), "NIFTY 500": (500, 0.80)}
# all size indices whose current membership we lift straight from the snapshot
OFFICIAL_INDICES = ["NIFTY 50", "NIFTY 100", "NIFTY 200", "NIFTY 500",
                    "NIFTY NEXT 50", "NIFTY MIDCAP 100", "NIFTY SMALLCAP 100"]

DDL = """CREATE TABLE IF NOT EXISTS index_membership (
    index_name   TEXT,
    symbol       TEXT,
    effective_from TEXT,
    effective_to   TEXT,
    method       TEXT,
    confidence   REAL,
    fetched_at   TEXT,
    PRIMARY KEY (index_name, symbol, effective_from)
)"""


def reconstruct_intervals(pu, index_name, topn, conf, cutoff, now):
    """Collapse monthly membership (adv_rank<=topn) into effective_from/to islands,
    all ending at/before `cutoff` (the official snapshot takes over after that)."""
    months = sorted(pu["rebal_date"].unique())
    month_idx = {m: i for i, m in enumerate(months)}
    mem = pu[pu["adv_rank"] <= topn]
    rows = []
    for sym, g in mem.groupby("symbol"):
        ms = sorted(g["rebal_date"].unique())
        run_start = prev = ms[0]
        for m in ms[1:]:
            if month_idx[m] == month_idx[prev] + 1:      # contiguous month
                prev = m
                continue
            rows.append((index_name, sym, run_start, prev, "reconstructed_turnover", conf, now))
            run_start = prev = m
        rows.append((index_name, sym, run_start, prev, "reconstructed_turnover", conf, now))
    # close each interval at the month AFTER its last member-month (= date it left);
    # keep only history strictly before the official snapshot cutoff.
    out = []
    for idx, sym, f, t, meth, c, ts in rows:
        i = month_idx[t]
        eff_to = months[i + 1] if i + 1 < len(months) else t
        if f >= cutoff:
            continue
        out.append((idx, sym, f, min(eff_to, cutoff), meth, c, ts))
    return out


def main():
    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA busy_timeout=180000")
    conn.execute(DDL)
    conn.execute("DELETE FROM index_membership")     # full idempotent rebuild
    now = datetime.now().isoformat()

    # snapshot cutoff = when index_constituents was last refreshed
    cutoff = conn.execute("SELECT MAX(updated) FROM index_constituents").fetchone()[0]

    # 1) OFFICIAL current membership (effective_to = NULL)
    off_rows = []
    for idx in OFFICIAL_INDICES:
        for (sym,) in conn.execute(
                "SELECT symbol FROM index_constituents WHERE index_name=?", (idx,)):
            off_rows.append((idx, sym, cutoff, None, "official", 1.0, now))
    conn.executemany("INSERT OR REPLACE INTO index_membership VALUES (?,?,?,?,?,?,?)", off_rows)

    # 2) HISTORICAL reconstruction for the two indices we can proxy
    pu = pd.read_sql("SELECT rebal_date,symbol,adv_rank FROM pit_universe "
                     "WHERE adv_rank<=500", conn)
    hist_n = 0
    for idx, (topn, conf) in RECON.items():
        rows = reconstruct_intervals(pu, idx, topn, conf, cutoff, now)
        # avoid clashing PK with the official row (same effective_from=cutoff)
        rows = [r for r in rows if r[2] != cutoff]
        conn.executemany("INSERT OR REPLACE INTO index_membership VALUES (?,?,?,?,?,?,?)", rows)
        hist_n += len(rows)
    conn.commit()

    # --- self-checks ---
    tot = conn.execute("SELECT COUNT(*) FROM index_membership").fetchone()[0]
    cur50 = {r[0] for r in conn.execute("SELECT symbol FROM index_membership "
             "WHERE index_name='NIFTY 50' AND effective_to IS NULL")}
    off50 = {r[0] for r in conn.execute("SELECT symbol FROM index_constituents "
             "WHERE index_name='NIFTY 50'")}
    match = len(cur50 & off50) / len(off50) if off50 else 0
    overlaps = conn.execute(
        "SELECT COUNT(*) FROM index_membership a JOIN index_membership b "
        "ON a.index_name=b.index_name AND a.symbol=b.symbol "
        "AND a.effective_from < b.effective_from "
        "AND (a.effective_to IS NULL OR a.effective_to > b.effective_from)").fetchone()[0]
    print(f"  index_membership rows: {tot:,}  (official={len(off_rows):,} historical={hist_n:,})", flush=True)
    print(f"  cutoff (snapshot date): {cutoff}", flush=True)
    print(f"  {'PASS' if match >= 0.99 else 'FAIL'}: NIFTY 50 current == official ({match:.0%})", flush=True)
    print(f"  {'PASS' if overlaps == 0 else 'FAIL'}: no overlapping intervals ({overlaps})", flush=True)
    print("  NOTE: historical NIFTY 50 is a turnover proxy (~58% accurate) -- "
          "confidence-flagged, not for leakage-critical use.", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
