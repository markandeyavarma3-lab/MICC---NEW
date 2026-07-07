#!/usr/bin/env python3
"""backtest_momentum.py — PHASE 4/5 flagship.

Survivorship-free, cost- and capacity-aware monthly backtest of a composite
momentum + delivery signal, built entirely on the Phase 1/2 clean layer:
  features_monthly (as-of signals) x stock_data_adj (realized returns)
  x pit_universe (top500 tradable) x market_breadth (regime gate).

Signal = equal-weight average of cross-sectional percentile ranks of
  [mom_12_1, prox_52w_high, deliv_1m]   (all "higher = better").

Books (monthly rebalance, equal-weight, hold to next month-end):
  LS        long top decile  / short bottom decile
  LongOnly  long top decile
  LO+Regime long top decile only when %>200DMA >= 50 (else cash)
  Bench     equal-weight top500 (costless reference)

Costs: turnover-based, default 30 bps/side, applied to both legs; cost-sensitivity
sweep reported. No parameter optimization -- this is a factor test, not a fit.

Anti-lookahead: signal as-of month-end R, realized return R->R+1 from adjusted
close, universe + regime as-of R. Execution assumed at rebalance close (slippage
in the cost rate covers that optimism).

Run:  py -3.14 common/backtest_momentum.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
SIGNALS = ["mom_12_1", "prox_52w_high", "deliv_1m"]
COST_PER_SIDE = 0.0030          # 30 bps default
N_DECILES = 10
PERIODS_YR = 12


def metrics(r):
    """r: monthly return Series. Returns dict of performance stats."""
    r = r.dropna()
    if len(r) < 12:
        return {}
    eq = (1 + r).cumprod()
    n = len(r)
    cagr = eq.iloc[-1] ** (PERIODS_YR / n) - 1
    vol = r.std() * np.sqrt(PERIODS_YR)
    sharpe = (r.mean() * PERIODS_YR) / vol if vol > 0 else np.nan
    downside = r[r < 0].std() * np.sqrt(PERIODS_YR)
    sortino = (r.mean() * PERIODS_YR) / downside if downside > 0 else np.nan
    dd = eq / eq.cummax() - 1
    maxdd = dd.min()
    calmar = cagr / abs(maxdd) if maxdd < 0 else np.nan
    return {"CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino,
            "MaxDD": maxdd, "Calmar": calmar, "HitRate": (r > 0).mean(), "Months": n}


def build_book(panel, rebals, decile_col, long_dec, short_dec, cost):
    """Return per-month gross/net returns + turnover for a decile book."""
    long_prev, short_prev = set(), set()
    rows = []
    for R in rebals:
        g = panel[panel["rebal_date"] == R]
        if g[decile_col].notna().sum() < N_DECILES * 5:
            continue
        L = g[g[decile_col] == long_dec]
        S = g[g[decile_col] == short_dec]
        if len(L) == 0:
            continue
        long_now, short_now = set(L["symbol"]), set(S["symbol"])
        long_ret = L["realized"].mean()
        short_ret = S["realized"].mean() if len(S) else np.nan
        # one-way turnover = fraction of book newly entered
        to_long = len(long_now - long_prev) / len(long_now) if long_now else 0
        to_short = len(short_now - short_prev) / len(short_now) if short_now else 0
        cost_long = 2 * to_long * cost          # entries + exits
        cost_short = 2 * to_short * cost
        rows.append({
            "rebal_date": R,
            "long_gross": long_ret, "short_gross": short_ret,
            "long_net": long_ret - cost_long,
            "ls_gross": long_ret - short_ret if not np.isnan(short_ret) else np.nan,
            "ls_net": (long_ret - short_ret) - cost_long - cost_short
            if not np.isnan(short_ret) else np.nan,
            "turnover": to_long,
        })
        long_prev, short_prev = long_now, short_now
    return pd.DataFrame(rows)


def load_panel(conn):
    """Build the as-of backtest panel (shared by the flagship + hardening script).
    Returns (panel, rebals, breadth). panel has per-(date,symbol): SIGNALS, realized
    R->R+1 return, percentile ranks, equal-weight composite, and decile."""
    feat = pd.read_sql(
        "SELECT rebal_date,symbol,top500," + ",".join(SIGNALS) +
        " FROM features_monthly WHERE top500=1", conn)
    rebals = sorted(feat["rebal_date"].unique())
    ph = ",".join("?" * len(rebals))
    close = pd.read_sql(
        f"SELECT date AS rebal_date, symbol, close FROM stock_data_adj WHERE date IN ({ph})",
        conn, params=rebals)
    breadth = pd.read_sql("SELECT date, pct_above_200dma FROM market_breadth", conn)

    nxt = {rebals[i]: rebals[i + 1] for i in range(len(rebals) - 1)}
    feat = feat.merge(close, on=["rebal_date", "symbol"], how="left")
    feat["next_date"] = feat["rebal_date"].map(nxt)
    close_n = close.rename(columns={"rebal_date": "next_date", "close": "close_next"})
    feat = feat.merge(close_n, on=["next_date", "symbol"], how="left")
    feat["realized"] = feat["close_next"] / feat["close"] - 1
    panel = feat.dropna(subset=["realized"] + SIGNALS).copy()

    for s in SIGNALS:
        panel[s + "_r"] = panel.groupby("rebal_date")[s].rank(pct=True)
    panel["composite"] = panel[[s + "_r" for s in SIGNALS]].mean(axis=1)
    panel["decile"] = panel.groupby("rebal_date")["composite"].transform(
        lambda x: pd.qcut(x.rank(method="first"), N_DECILES, labels=False) + 1)
    return panel, rebals, breadth


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    print("Loading feature store + adjusted closes + breadth ...", flush=True)
    panel, rebals, breadth = load_panel(conn)
    conn.close()
    print(f"  {len(panel):,} realized signal rows over {len(rebals)} months", flush=True)

    # ---- decile monotonicity (gross, no cost) ----
    print("\n=== DECILE MONOTONICITY (mean realized monthly return, gross) ===", flush=True)
    dec = panel.groupby("decile")["realized"].mean() * 100
    for d in range(1, N_DECILES + 1):
        bar = "#" * max(0, int(dec.get(d, 0) * 8))
        print(f"  D{d:<2} {dec.get(d, float('nan')):+6.3f}%  {bar}", flush=True)
    print(f"  spread D10-D1 = {(dec.get(10,0)-dec.get(1,0)):+.3f}% / month", flush=True)

    # ---- main books ----
    book = build_book(panel, rebals, "decile", N_DECILES, 1, COST_PER_SIDE)
    book = book.set_index("rebal_date")
    bench = panel.groupby("rebal_date")["realized"].mean().reindex(book.index)
    breadth_m = breadth.set_index("date")["pct_above_200dma"].reindex(book.index)
    lo_regime = np.where(breadth_m.fillna(100) >= 50, book["long_net"], 0.0)
    lo_regime = pd.Series(lo_regime, index=book.index)

    series = {
        "LS (D10-D1) net": book["ls_net"],
        "LongOnly D10 net": book["long_net"],
        "LO + Regime gate": lo_regime,
        "Bench (EW top500)": bench,
    }

    print("\n=== PERFORMANCE (net of 30 bps/side, 2005-2026) ===", flush=True)
    hdr = f"  {'strategy':20} {'CAGR':>7} {'Vol':>6} {'Sharpe':>7} {'Sortino':>8} {'MaxDD':>7} {'Calmar':>7} {'Hit':>5}"
    print(hdr, flush=True)
    for name, r in series.items():
        m = metrics(r)
        if not m:
            continue
        print(f"  {name:20} {m['CAGR']*100:>6.1f}% {m['Vol']*100:>5.1f}% "
              f"{m['Sharpe']:>7.2f} {m['Sortino']:>8.2f} {m['MaxDD']*100:>6.1f}% "
              f"{m['Calmar']:>7.2f} {m['HitRate']*100:>4.0f}%", flush=True)
    print(f"  avg monthly one-way turnover (long book): {book['turnover'].mean()*100:.0f}%", flush=True)

    # ---- regime split: bull vs bear by breadth ----
    print("\n=== REGIME SPLIT (LongOnly D10 net) ===", flush=True)
    bull = book["long_net"][breadth_m >= 50]
    bear = book["long_net"][breadth_m < 50]
    for nm, r in [("Bull (>=50% above 200DMA)", bull), ("Bear (<50%)", bear)]:
        if len(r) >= 6:
            print(f"  {nm:28} mean {r.mean()*100:+.2f}%/mo  hit {(r>0).mean()*100:.0f}%  "
                  f"n={len(r)}", flush=True)

    # ---- cost sensitivity (LS) ----
    print("\n=== COST SENSITIVITY (LS net Sharpe & CAGR) ===", flush=True)
    for c in (0.0, 0.0010, 0.0020, 0.0030, 0.0050):
        b = build_book(panel, rebals, "decile", N_DECILES, 1, c).set_index("rebal_date")
        m = metrics(b["ls_net"])
        if m:
            print(f"  {c*1e4:>3.0f} bps/side -> Sharpe {m['Sharpe']:>5.2f}  CAGR {m['CAGR']*100:>5.1f}%",
                  flush=True)

    # ---- persist equity curves + metrics ----
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    eq_rows, met_rows = [], []
    for name, r in series.items():
        r = r.dropna()
        eq = (1 + r).cumprod()
        for dt, ret, e in zip(r.index, r.values, eq.values):
            eq_rows.append((name, dt, float(ret), float(e)))
        m = metrics(r)
        for k, v in m.items():
            met_rows.append((name, k, float(v)))
    conn.execute("DROP TABLE IF EXISTS bt_equity")
    conn.execute("CREATE TABLE bt_equity (strategy TEXT, date TEXT, ret REAL, equity REAL)")
    conn.executemany("INSERT INTO bt_equity VALUES (?,?,?,?)", eq_rows)
    conn.execute("DROP TABLE IF EXISTS bt_metrics")
    conn.execute("CREATE TABLE bt_metrics (strategy TEXT, metric TEXT, value REAL)")
    conn.executemany("INSERT INTO bt_metrics VALUES (?,?,?)", met_rows)
    conn.commit()
    conn.close()
    print("\nSaved equity curves -> bt_equity, metrics -> bt_metrics.", flush=True)


if __name__ == "__main__":
    main()
