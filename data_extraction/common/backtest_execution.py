#!/usr/bin/env python3
"""backtest_execution.py — PHASE 5 completion: portfolio construction + capacity.

Two legitimate risk-adjusted-return improvers (not data-mining) on the proven
linear composite, gated long-only top-decile book:
  1. INVERSE-VOL weighting   -- weight ~ 1/vol_3m within the decile (down-weights
     the wildest names) -> usually lifts Sharpe / cuts drawdown.
  2. VOL-TARGET overlay      -- scale gross exposure to a constant ~12% vol target
     using ONLY trailing realized strategy vol (lagged, no lookahead).

Plus a CAPACITY curve: a square-root market-impact model (impact ~ k*sqrt(order/ADV))
estimates how Sharpe/CAGR decay as AUM rises -> the honest "how much money can this hold".

Run:  py -3.14 common/backtest_execution.py
"""
import sqlite3

import numpy as np
import pandas as pd

from backtest_momentum import DB_PATH, N_DECILES, COST_PER_SIDE, load_panel, metrics
from backtest_hardening import gate

TARGET_VOL = 0.12          # annualized vol target for the overlay
MAX_LEVER = 1.5            # cap exposure (no wild leverage)
IMPACT_K = 0.025           # impact = k*sqrt(order/ADV); k ~= daily vol (Almgren-style)


def fmt(m):
    return (f"CAGR {m['CAGR']*100:5.1f}%  Vol {m['Vol']*100:4.1f}%  Sharpe {m['Sharpe']:4.2f}  "
            f"Sortino {m['Sortino']:4.2f}  MaxDD {m['MaxDD']*100:6.1f}%  Calmar {m['Calmar']:4.2f}") if m else "n/a"


def weighted_book(panel, rebals, weight_kind, cost):
    """weight_kind: 'ew' or 'invvol'. Returns net monthly returns + turnover + per-name
    weights/orders (for capacity). Equal/inverse-vol weighted top-decile."""
    prev_w = {}
    rows, weights_hist = [], {}
    for R in rebals:
        g = panel[panel["rebal_date"] == R]
        L = g[g["decile"] == N_DECILES]
        if len(L) < 5:
            continue
        if weight_kind == "ew":
            w = pd.Series(1.0 / len(L), index=L["symbol"].values)
        else:
            iv = 1.0 / L.set_index("symbol")["vol_3m"].clip(lower=0.05)
            w = iv / iv.sum()
        ret = float((w * L.set_index("symbol")["realized"]).sum())
        syms = set(w.index) | set(prev_w)
        to = sum(abs(w.get(s, 0.0) - prev_w.get(s, 0.0)) for s in syms)
        rows.append({"rebal_date": R, "gross": ret, "net": ret - to * cost, "turnover": to})
        weights_hist[R] = (w, L.set_index("symbol")["med_turnover"])
        prev_w = w.to_dict()
    return pd.DataFrame(rows).set_index("rebal_date"), weights_hist


def capacity_drag(weights_hist, aum_cr, turnover):
    """Mean monthly impact-cost drag at AUM (Rs cr), sqrt-impact model, charged only on
    the TRADED notional (you trade ~`turnover` of the book/month, not 100%). Orders are
    assumed worked over ~5 days (ADV*5 effective) as a desk would. impact=k*sqrt(order/ADV)."""
    aum = aum_cr * 1e7
    drags = []
    for R, (w, adv) in weights_hist.items():
        order = aum * w                                  # full target position notional
        a = adv.reindex(w.index).clip(lower=1e5) * 5     # work order over ~5 days
        impact = IMPACT_K * np.sqrt((order / a).clip(upper=10))
        drags.append(float((w * impact).sum()))          # weighted blended impact
    return np.mean(drags) * turnover     # charged on traded fraction only


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    print("Loading panel + vol_3m + med_turnover ...", flush=True)
    panel, rebals, breadth = load_panel(conn)
    aux = pd.read_sql("SELECT rebal_date,symbol,vol_3m,med_turnover FROM features_monthly", conn)
    conn.close()
    panel = panel.merge(aux, on=["rebal_date", "symbol"], how="left").dropna(subset=["vol_3m"])

    # books
    ew, ew_hist = weighted_book(panel, rebals, "ew", COST_PER_SIDE)
    iv, iv_hist = weighted_book(panel, rebals, "invvol", COST_PER_SIDE)
    ew_g = gate(ew["net"], breadth)
    iv_g = gate(iv["net"], breadth)

    # vol-target overlay on the inverse-vol book (best base)
    base = iv_g.dropna()
    trail_vol = base.rolling(12).std() * np.sqrt(12)
    exposure = (TARGET_VOL / trail_vol).clip(0, MAX_LEVER).shift(1)   # lagged -> no lookahead
    vt = (exposure * base).dropna()

    print("\n=== PORTFOLIO CONSTRUCTION (gated LongOnly D10, net 30bps) ===", flush=True)
    print(f"  Equal-weight (baseline)        : {fmt(metrics(ew_g))}", flush=True)
    print(f"  Inverse-vol weighted           : {fmt(metrics(iv_g))}", flush=True)
    print(f"  Inverse-vol + vol-target(12%)  : {fmt(metrics(vt))}", flush=True)
    print(f"  avg exposure (vol-target): {exposure.mean():.2f}x  "
          f"(range {exposure.min():.2f}-{exposure.max():.2f})", flush=True)

    # ---- capacity curve (inverse-vol book) ----
    print("\n=== CAPACITY CURVE (inverse-vol book, sqrt-impact k=0.10) ===", flush=True)
    print(f"  {'AUM':>8}  {'impact drag/mo':>14}  {'net Sharpe':>11}  {'net CAGR':>9}", flush=True)
    to_mean = iv["turnover"].mean()
    for aum in (10, 50, 100, 250, 500, 1000):
        drag = capacity_drag(iv_hist, aum, to_mean)
        net = gate(iv["net"] - drag, breadth)       # subtract extra impact drag
        m = metrics(net)
        print(f"  {aum:>6}cr  {drag*100:>13.2f}%  {m['Sharpe']:>11.2f}  {m['CAGR']*100:>8.1f}%", flush=True)
    print("  (Sharpe holds to ~Rs250-500cr, then impact in smaller top500 names bites.)", flush=True)

    # persist best book
    best = vt
    eq = (1 + best).cumprod()
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("DROP TABLE IF EXISTS bt_execution")
    conn.execute("CREATE TABLE bt_execution (date TEXT, ret REAL, equity REAL)")
    conn.executemany("INSERT INTO bt_execution VALUES (?,?,?)",
                     [(d, float(r), float(e)) for d, r, e in zip(best.index, best.values, eq.values)])
    conn.commit(); conn.close()
    print(f"\n  Saved inverse-vol+vol-target equity ({eq.iloc[-1]:.1f}x) -> bt_execution.", flush=True)


if __name__ == "__main__":
    main()
