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

# index_name -> top-N by turnover rank for historical reconstruction.
# Confidence is NOT guessed -- it is MEASURED per index as the current turnover-topN
# agreement with the official list, then stamped on that index's historical rows.
RECON_TOPN = {"NIFTY 50": 50, "NIFTY 100": 100, "NIFTY 200": 200, "NIFTY 500": 500}
# all size indices whose current membership we lift straight from the snapshot
OFFICIAL_INDICES = ["NIFTY 50", "NIFTY 100", "NIFTY 200", "NIFTY 500",
                    "NIFTY NEXT 50", "NIFTY MIDCAP 100", "NIFTY SMALLCAP 100"]

# Reviewer fix: a low-confidence membership table must not be silently consumed.
# Anything below this is QUARANTINED out of the `index_membership_consumable` view,
# which is the ONLY thing Part 2's index-relative signals are allowed to join.
# (turnover proxy: NIFTY 50/100 history ~58-63% -> excluded; 200/500 ~78-80% -> kept;
#  all official current rows are 1.0 -> always kept.)
CONSUMABLE_CONFIDENCE_MIN = 0.75

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

    # 2) HISTORICAL reconstruction. Confidence per index = MEASURED current
    #    turnover-topN agreement with the official list (data-driven, not guessed).
    pu = pd.read_sql("SELECT rebal_date,symbol,adv_rank FROM pit_universe "
                     "WHERE adv_rank<=500", conn)
    latest_pu = pu["rebal_date"].max()
    hist_n = 0
    measured = {}
    for idx, topn in RECON_TOPN.items():
        recon_now = {r for r, in conn.execute(
            "SELECT symbol FROM pit_universe WHERE rebal_date=? AND adv_rank<=?",
            (latest_pu, topn))}
        off_now = {r for r, in conn.execute(
            "SELECT symbol FROM index_constituents WHERE index_name=?", (idx,))}
        conf = round(len(recon_now & off_now) / len(off_now), 2) if off_now else 0.0
        measured[idx] = conf
        rows = reconstruct_intervals(pu, idx, topn, conf, cutoff, now)
        rows = [r for r in rows if r[2] != cutoff]     # no PK clash with official row
        conn.executemany("INSERT OR REPLACE INTO index_membership VALUES (?,?,?,?,?,?,?)", rows)
        hist_n += len(rows)

    # 3) CONSUMABLE view -- the ONLY membership Part 2 signals may join. Quarantines
    #    any row below the confidence floor (weak narrow-index history stays out).
    conn.execute("DROP VIEW IF EXISTS index_membership_consumable")
    conn.execute(f"CREATE VIEW index_membership_consumable AS "
                 f"SELECT * FROM index_membership WHERE confidence >= {CONSUMABLE_CONFIDENCE_MIN}")
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
    consumable = conn.execute("SELECT COUNT(*) FROM index_membership_consumable").fetchone()[0]
    quarantined = tot - consumable
    print(f"  index_membership rows: {tot:,}  (official={len(off_rows):,} historical={hist_n:,})", flush=True)
    print(f"  cutoff (snapshot date): {cutoff}", flush=True)
    print(f"  measured historical confidence (=current agreement): "
          + ", ".join(f"{k.split()[-1]}={v:.0%}" for k, v in measured.items()), flush=True)
    print(f"  {'PASS' if match >= 0.99 else 'FAIL'}: NIFTY 50 current == official ({match:.0%})", flush=True)
    print(f"  {'PASS' if overlaps == 0 else 'FAIL'}: no overlapping intervals ({overlaps})", flush=True)
    print(f"  consumable view (conf>={CONSUMABLE_CONFIDENCE_MIN}): {consumable:,} rows kept, "
          f"{quarantined:,} quarantined (weak narrow-index history)", flush=True)
    print("  NOTE: turnover proxy -- Part 2 index-relative signals MUST use "
          "index_membership_consumable, never the raw table.", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
