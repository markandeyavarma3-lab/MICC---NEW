#!/usr/bin/env python3
"""fno_feature_study.py — PHASE 2b (F&O feature signal study).

Before building anything on F&O positioning, test whether it carries cross-sectional
signal. Computes, at each monthly rebalance, per-symbol F&O features and measures
their rank-IC vs forward return on the F&O-eligible top500 subset.

Features:
  pcr_oi        put/call OI ratio (options_pcr_daily) at the rebalance date
  fut_oi_chg    MoM change in total stock-future OI (fo_data FUTSTK)
  fut_oi_level  z-scored OI level (crowding proxy)

This is a STUDY (does it add edge?), not a book. F&O covers ~190 names so the
cross-section is small; treat results as indicative.

Run:  py -3.14 common/fno_feature_study.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")


def rank_ic(df, feat, label="fwd_ret_1m"):
    ics = []
    for _, g in df.groupby("rebal_date"):
        s = g[[feat, label]].dropna()
        if len(s) >= 15:
            ics.append(s[feat].rank().corr(s[label].rank()))
    ics = pd.Series(ics).dropna()
    return ics.mean(), (ics > 0).mean(), len(ics)


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")

    base = pd.read_sql(
        "SELECT rebal_date,symbol,fwd_ret_1m FROM features_monthly "
        "WHERE top500=1 AND fwd_ret_1m IS NOT NULL", conn)
    rebals = sorted(base["rebal_date"].unique())
    ph = ",".join("?" * len(rebals))

    print("Loading F&O inputs at rebalance dates ...", flush=True)
    pcr = pd.read_sql(
        f"SELECT date AS rebal_date, symbol, pcr_oi FROM options_pcr_daily "
        f"WHERE date IN ({ph})", conn, params=rebals)
    fut = pd.read_sql(
        f"SELECT date AS rebal_date, symbol, SUM(open_int) AS fut_oi "
        f"FROM fo_data WHERE instrument='FUTSTK' AND date IN ({ph}) "
        f"GROUP BY date,symbol", conn, params=rebals)
    conn.close()
    print(f"  pcr rows={len(pcr):,} ({pcr['symbol'].nunique()} syms)  "
          f"fut rows={len(fut):,} ({fut['symbol'].nunique()} syms)", flush=True)

    # MoM futures OI change
    fut = fut.sort_values(["symbol", "rebal_date"])
    fut["fut_oi_prev"] = fut.groupby("symbol")["fut_oi"].shift(1)
    fut["fut_oi_chg"] = fut["fut_oi"] / fut["fut_oi_prev"] - 1
    fut["fut_oi_level"] = fut.groupby("rebal_date")["fut_oi"].transform(
        lambda x: (x - x.mean()) / x.std(ddof=0))

    df = base.merge(pcr, on=["rebal_date", "symbol"], how="left")
    df = df.merge(fut[["rebal_date", "symbol", "fut_oi_chg", "fut_oi_level"]],
                  on=["rebal_date", "symbol"], how="left")

    print("\n=== F&O FEATURE rank-IC vs forward 1m return (F&O top500 subset) ===", flush=True)
    print(f"  {'feature':14} {'mean IC':>9} {'%+months':>9} {'n_months':>9}", flush=True)
    for f in ["pcr_oi", "fut_oi_chg", "fut_oi_level"]:
        sub = df[df[f].notna()]
        ic, pos, n = rank_ic(sub, f)
        print(f"  {f:14} {ic:>+9.4f} {pos*100:>8.0f}% {n:>9}", flush=True)
    cov = df["pcr_oi"].notna().mean()
    print(f"\n  F&O coverage of top500 rows: {cov*100:.0f}% (rest are non-F&O names)", flush=True)
    print("  Interpretation: |IC|<~0.02 = weak/noisy; treat F&O as a confirmation\n"
          "  overlay on the ~190 F&O names, not a standalone cross-sectional factor.", flush=True)


if __name__ == "__main__":
    main()
