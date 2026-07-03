#!/usr/bin/env python3
"""backtest_signal_candidates.py — Part 2 Module 4 ship-gate: IC study for new
signal-library candidates.

Candidates (from the India evidence):
  amihud        illiquidity premium (Aziz & Ansari: illiquid winners +2.7%/mo).
                Sign prior: + (higher illiquidity -> higher forward return).
  rs_sector_6m  6m return minus the stock's SECTOR-mean 6m return (relative
                strength; RS-vs-NIFTY is skipped because subtracting a per-month
                constant cannot change cross-sectional ranks).

Method: monthly cross-sectional Spearman rank-IC vs fwd_ret_1m over the tradable
top-500 liquid universe (the same panel the flagship uses). Pre-registered rule:
a candidate earns 'scored' IFF mean IC has the prior sign with |t| >= 3.0 across
months AND the second-half mean IC keeps that sign. Losers stay 'context'.

IMPORTANT: winners do NOT touch the proven generate_signals composite (the
flagship edge stays frozen); they feed idea-card scoring via score_weights v2.0
(Module 7). Verdicts persisted to `signal_candidate_validation`.

Run:  py -3.14 common/backtest_signal_candidates.py
"""
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd

from backtest_momentum import DB_PATH

DDL = """CREATE TABLE IF NOT EXISTS signal_candidate_validation (
    run_at TEXT, candidate TEXT, months INTEGER,
    mean_ic REAL, t_stat REAL, ic_h1 REAL, ic_h2 REAL,
    sign_prior TEXT, verdict TEXT,
    PRIMARY KEY (run_at, candidate)
)"""


def ic_study(df, col, prior_sign):
    ics = (df.dropna(subset=[col, "fwd_ret_1m"])
             .groupby("rebal_date")
             .apply(lambda g: g[col].rank().corr(g["fwd_ret_1m"].rank())
                    if len(g) >= 50 else np.nan)).dropna()
    n = len(ics)
    mean, sd = ics.mean(), ics.std()
    t = mean / (sd / np.sqrt(n)) if n > 1 and sd > 0 else 0.0
    h1, h2 = ics.iloc[: n // 2].mean(), ics.iloc[n // 2:].mean()
    want = 1 if prior_sign == "+" else -1
    verdict = "scored" if (np.sign(mean) == want and abs(t) >= 3.0
                           and np.sign(h2) == want) else "context"
    return n, mean, t, h1, h2, verdict


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    conn.execute(DDL)

    df = pd.read_sql("SELECT rebal_date, symbol, ret_6m, amihud, fwd_ret_1m "
                     "FROM features_monthly WHERE top500=1 AND liquid=1", conn)
    sec = pd.read_sql("SELECT symbol, sector FROM dim_sector", conn)
    df = df.merge(sec, on="symbol", how="left")
    df["rs_sector_6m"] = df["ret_6m"] - df.groupby(["rebal_date", "sector"])["ret_6m"] \
                                          .transform("mean")
    df.loc[df["sector"].isna(), "rs_sector_6m"] = np.nan   # no sector -> no RS claim

    run_at = datetime.now().isoformat()
    conn.execute("DELETE FROM signal_candidate_validation")
    for cand, prior in [("amihud", "+"), ("rs_sector_6m", "+")]:
        n, mean, t, h1, h2, verdict = ic_study(df, cand, prior)
        conn.execute("INSERT OR REPLACE INTO signal_candidate_validation "
                     "VALUES (?,?,?,?,?,?,?,?,?)",
                     (run_at, cand, n, float(mean), float(t), float(h1), float(h2),
                      prior, verdict))
        print(f"  {cand:14} months={n}  IC={mean:+.4f}  t={t:+.2f}  "
              f"H1={h1:+.4f} H2={h2:+.4f}  -> {verdict.upper()}", flush=True)
    conn.commit(); conn.close()


if __name__ == "__main__":
    main()
