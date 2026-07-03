#!/usr/bin/env python3
"""backtest_insider.py — Part 2 Module 2 ship-gate: insider cluster-buy event study.

Pre-registered rule (doc discipline: t>=3.0 for anything joining the factor zoo):
  insider_cluster_buy earns evidence_tier='scored' IFF
    (1) full-sample mean 21d abnormal return > 0 with |t| >= 3.0, AND
    (2) second-half-of-sample mean AR > 0 (temporal robustness).
  Otherwise it stays 'context'.

Method (EOD-honest): entry at the FIRST CLOSE AFTER the filing date (no same-day
fill); abnormal return = stock 21-trading-day forward return minus NIFTY 50 over
the same window. Uses corp-action-adjusted closes. Verdict persisted to
`event_validation`; the event_signals tier is updated in place.

Run:  py -3.14 common/backtest_insider.py
"""
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd

from backtest_momentum import DB_PATH

HORIZON = 21   # trading days

DDL = """CREATE TABLE IF NOT EXISTS event_validation (
    run_at TEXT, event_type TEXT, n_events INTEGER,
    mean_ar REAL, t_stat REAL, hit_rate REAL,
    mean_ar_h1 REAL, mean_ar_h2 REAL,
    horizon_days INTEGER, verdict TEXT,
    PRIMARY KEY (run_at, event_type)
)"""


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    conn.execute(DDL)

    ev = pd.read_sql("SELECT symbol, event_date FROM event_signals "
                     "WHERE event_type='insider_cluster_buy' ORDER BY event_date", conn)
    syms = tuple(ev["symbol"].unique())
    print(f"  events: {len(ev):,} across {len(syms)} symbols", flush=True)

    px = pd.read_sql(f"SELECT symbol, date, close FROM stock_data_adj "
                     f"WHERE symbol IN ({','.join('?'*len(syms))}) ORDER BY symbol, date",
                     conn, params=syms)
    nifty = pd.read_sql("SELECT date, close FROM global_indices_daily "
                        "WHERE symbol='NIFTY50' ORDER BY date", conn)
    nd = nifty["date"].to_numpy()
    nc = nifty["close"].to_numpy(dtype=float)

    series = {s: (g["date"].to_numpy(), g["close"].to_numpy(dtype=float))
              for s, g in px.groupby("symbol")}

    ars, dates = [], []
    for r in ev.itertuples():
        if r.symbol not in series:
            continue
        d, c = series[r.symbol]
        i = np.searchsorted(d, r.event_date, side="right")     # first close AFTER filing
        if i + HORIZON >= len(d) or c[i] <= 0:
            continue
        stock_ret = c[i + HORIZON] / c[i] - 1
        j = np.searchsorted(nd, d[i], side="left")
        if j + HORIZON >= len(nd) or nc[j] <= 0:
            continue
        bench_ret = nc[j + HORIZON] / nc[j] - 1
        ars.append(stock_ret - bench_ret)
        dates.append(r.event_date)

    ar = pd.Series(ars, index=pd.to_datetime(dates)).sort_index()
    n = len(ar)
    mean, sd = ar.mean(), ar.std()
    t = mean / (sd / np.sqrt(n)) if n > 1 and sd > 0 else 0.0
    hit = (ar > 0).mean()
    mid = ar.index[n // 2]
    h1, h2 = ar[ar.index < mid].mean(), ar[ar.index >= mid].mean()

    verdict = "scored" if (mean > 0 and t >= 3.0 and h2 > 0) else "context"
    print(f"  n={n:,}  mean 21d AR={mean*100:+.2f}%  t={t:.2f}  hit={hit*100:.0f}%", flush=True)
    print(f"  half-split: H1 {h1*100:+.2f}%  H2 {h2*100:+.2f}%", flush=True)
    print(f"  pre-registered rule (mean>0, t>=3, H2>0) -> VERDICT: {verdict.upper()}", flush=True)

    run_at = datetime.now().isoformat()
    conn.execute("DELETE FROM event_validation WHERE event_type='insider_cluster_buy'")
    conn.execute("INSERT OR REPLACE INTO event_validation VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (run_at, "insider_cluster_buy", n, float(mean), float(t), float(hit),
                  float(h1), float(h2), HORIZON, verdict))
    conn.execute("UPDATE event_signals SET evidence_tier=? WHERE event_type='insider_cluster_buy'",
                 (verdict,))
    conn.commit(); conn.close()
    print(f"  event_signals tier updated -> {verdict}", flush=True)


if __name__ == "__main__":
    main()
