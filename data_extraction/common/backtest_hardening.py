#!/usr/bin/env python3
"""backtest_hardening.py — PHASE 5 rigor layer.

Turns the in-sample flagship (backtest_momentum.py) into a defensible result by
adding the four tests an institutional reviewer asks for:

  1. SUB-PERIOD STABILITY  -- does it work in each era, or one lucky decade?
  2. WALK-FORWARD (OOS)     -- IC-weighted composite using ONLY past data at each
                              rebalance, vs the static equal-weight, on the same
                              out-of-sample window. Proves it isn't curve-fit.
  3. PARAMETER SENSITIVITY  -- grid over top-cut x regime threshold; is the edge a
                              knife-edge or a plateau?
  4. SIGNIFICANCE           -- block-bootstrap Sharpe CI, Probabilistic Sharpe
                              Ratio (PSR>0), and Deflated Sharpe (PSR vs the best
                              Sharpe expected from N trials of pure luck).

Reuses the exact panel/book logic from backtest_momentum (no drift).
Run:  py -3.14 common/backtest_hardening.py
"""
import math
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_momentum import (DB_PATH, SIGNALS, N_DECILES, COST_PER_SIDE,
                               load_panel, metrics)

GAMMA = 0.5772156649015329     # Euler-Mascheroni
MIN_HIST = 36                  # months of history before walk-forward starts


# ---------- normal helpers (no scipy) ----------
def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_ppf(p):
    a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2,
         1.383577518672690e2, -3.066479806614716e1, 2.506628277459239e0]
    b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2,
         6.680131188771972e1, -1.328068155288572e1]
    c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838e0,
         -2.549732539343734e0, 4.374664141464968e0, 2.938163982698783e0]
    d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996e0,
         3.754408661907416e0]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= phigh:
        q = p - 0.5; r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


# ---------- flexible book (long/short decile SETS) ----------
def book_returns(panel, rebals, long_set, short_set, cost, decile_col="decile"):
    long_prev, short_prev = set(), set()
    rows = []
    for R in rebals:
        g = panel[panel["rebal_date"] == R]
        if g[decile_col].notna().sum() < N_DECILES * 5:
            continue
        L = g[g[decile_col].isin(long_set)]
        S = g[g[decile_col].isin(short_set)] if short_set else g.iloc[0:0]
        if len(L) == 0:
            continue
        lnow, snow = set(L["symbol"]), set(S["symbol"])
        lret = L["realized"].mean()
        sret = S["realized"].mean() if len(S) else np.nan
        to_l = len(lnow - long_prev) / len(lnow) if lnow else 0
        to_s = len(snow - short_prev) / len(snow) if snow else 0
        rows.append({"rebal_date": R,
                     "long_net": lret - 2*to_l*cost,
                     "ls_net": (lret - sret) - 2*to_l*cost - 2*to_s*cost
                     if not np.isnan(sret) else np.nan,
                     "turnover": to_l})
        long_prev, short_prev = lnow, snow
    return pd.DataFrame(rows).set_index("rebal_date")


def gate(series, breadth, thr=50):
    bm = breadth.set_index("date")["pct_above_200dma"].reindex(series.index)
    return pd.Series(np.where(bm.fillna(100) >= thr, series.values, 0.0), index=series.index)


# ---------- significance ----------
def psr(r, sr_star_per=0.0):
    r = np.asarray(pd.Series(r).dropna()); n = len(r)
    sd = r.std(ddof=1)
    if sd == 0:
        return np.nan
    sr = r.mean() / sd
    g3 = pd.Series(r).skew()
    g4 = pd.Series(r).kurt() + 3            # pandas kurt = excess
    denom = math.sqrt(max(1e-9, 1 - g3*sr + ((g4-1)/4)*sr**2))
    return norm_cdf((sr - sr_star_per) * math.sqrt(n - 1) / denom)


def deflated_sharpe(r, trial_sharpes_ann, N):
    r = np.asarray(pd.Series(r).dropna())
    V = np.var(np.array(trial_sharpes_ann) / np.sqrt(12), ddof=1)   # per-period trial var
    sr0 = math.sqrt(V) * ((1 - GAMMA) * norm_ppf(1 - 1.0/N)
                          + GAMMA * norm_ppf(1 - 1.0/(N * math.e)))
    return psr(r, sr0), sr0 * math.sqrt(12)


def block_bootstrap(r, nboot=3000, block=6, seed=7):
    rng = np.random.default_rng(seed)
    r = np.asarray(pd.Series(r).dropna()); n = len(r)
    out = []
    for _ in range(nboot):
        idx = []
        while len(idx) < n:
            s = rng.integers(0, n - block + 1)
            idx.extend(range(s, s + block))
        rr = r[np.array(idx[:n])]
        sd = rr.std()
        out.append(rr.mean() * 12 / (sd * np.sqrt(12)) if sd > 0 else 0.0)
    out = np.array(out)
    return np.percentile(out, [5, 50, 95]), (out > 0).mean()


def fmt(m):
    return (f"CAGR {m['CAGR']*100:5.1f}%  Sharpe {m['Sharpe']:4.2f}  "
            f"MaxDD {m['MaxDD']*100:6.1f}%  Calmar {m['Calmar']:4.2f}  n={m['Months']}") if m else "n/a"


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    print("Loading shared panel ...", flush=True)
    panel, rebals, breadth = load_panel(conn)
    conn.close()
    print(f"  {len(panel):,} rows over {len(rebals)} months "
          f"({rebals[0]} -> {rebals[-1]})\n", flush=True)

    # baseline equal-weight gated long-only (the flagship headline)
    base = book_returns(panel, rebals, {10}, set(), COST_PER_SIDE)
    base_gated = gate(base["long_net"], breadth)

    # ===== 1. SUB-PERIOD STABILITY =====
    print("=== 1. SUB-PERIOD STABILITY (gated LongOnly D10, net) ===", flush=True)
    eras = [("2005-2011", "2005", "2011"), ("2012-2018", "2012", "2018"),
            ("2019-2026", "2019", "2026")]
    for name, lo, hi in eras:
        sub = base_gated[(base_gated.index >= lo) & (base_gated.index <= hi + "-12-31")]
        print(f"  {name}:  {fmt(metrics(sub))}", flush=True)
    print(f"  FULL    :  {fmt(metrics(base_gated))}", flush=True)

    # ===== 2. WALK-FORWARD (OOS, IC-weighted vs equal-weight) =====
    print("\n=== 2. WALK-FORWARD OUT-OF-SAMPLE ===", flush=True)
    # per-date, per-signal rank-IC vs realized
    ic = {}
    for s in SIGNALS:
        ic[s] = panel.groupby("rebal_date").apply(
            lambda g, s=s: g[s].rank().corr(g["realized"].rank()))
    ic_df = pd.DataFrame(ic).reindex(rebals)
    # at each R, weight_s = max(0, mean of past ICs); composite_oos = weighted ranks
    panel = panel.copy()
    panel["composite_oos"] = np.nan
    oos_dates = rebals[MIN_HIST:]
    for R in oos_dates:
        past = ic_df.loc[ic_df.index < R]
        w = past.mean().clip(lower=0)
        w = w / w.sum() if w.sum() > 0 else pd.Series(1/len(SIGNALS), index=SIGNALS)
        mask = panel["rebal_date"] == R
        panel.loc[mask, "composite_oos"] = sum(
            w[s] * panel.loc[mask, s + "_r"] for s in SIGNALS)
    oos = panel[panel["rebal_date"].isin(oos_dates)].copy()
    oos["decile_oos"] = oos.groupby("rebal_date")["composite_oos"].transform(
        lambda x: pd.qcut(x.rank(method="first"), N_DECILES, labels=False) + 1)

    icw = gate(book_returns(oos, oos_dates, {10}, set(), COST_PER_SIDE, "decile_oos")["long_net"], breadth)
    eqw = gate(book_returns(oos, oos_dates, {10}, set(), COST_PER_SIDE, "decile")["long_net"], breadth)
    print(f"  same OOS window {oos_dates[0]} -> {oos_dates[-1]} ({len(oos_dates)} months)", flush=True)
    print(f"  Equal-weight composite (static) : {fmt(metrics(eqw))}", flush=True)
    print(f"  IC-weighted composite (walk-fwd): {fmt(metrics(icw))}", flush=True)
    print("  avg walk-forward weights: " +
          ", ".join(f"{s}={ic_df.loc[ic_df.index<oos_dates[-1]].mean().clip(lower=0).pipe(lambda x:x/x.sum())[s]:.2f}"
                    for s in SIGNALS), flush=True)

    # ===== 3. PARAMETER SENSITIVITY =====
    print("\n=== 3. PARAMETER SENSITIVITY (gated LongOnly Sharpe / CAGR) ===", flush=True)
    print(f"  {'top-cut':12}" + "".join(f"  thr={t}%" for t in (40, 50, 60)), flush=True)
    trial_sharpes = []
    cuts = [("D10 (top10%)", {10}), ("D9-10 (top20%)", {9, 10}), ("D8-10 (top30%)", {8, 9, 10})]
    for cname, cset in cuts:
        bk = book_returns(panel, rebals, cset, set(), COST_PER_SIDE)
        cells = []
        for thr in (40, 50, 60):
            g = gate(bk["long_net"], breadth, thr)
            m = metrics(g)
            trial_sharpes.append(m["Sharpe"])
            cells.append(f"{m['Sharpe']:.2f}/{m['CAGR']*100:.0f}%")
        print(f"  {cname:12}" + "".join(f"  {c:>9}" for c in cells), flush=True)

    # ===== 4. SIGNIFICANCE =====
    print("\n=== 4. SIGNIFICANCE (gated LongOnly D10, net) ===", flush=True)
    ci, pgt0 = block_bootstrap(base_gated)
    print(f"  block-bootstrap Sharpe 90% CI: [{ci[0]:.2f}, {ci[2]:.2f}]  median {ci[1]:.2f}  "
          f"P(Sharpe>0)={pgt0*100:.0f}%", flush=True)
    print(f"  Probabilistic Sharpe Ratio  PSR(SR*=0) = {psr(base_gated)*100:.1f}%", flush=True)
    N = len(trial_sharpes) + 12          # explicit grid trials + a margin for the search
    dsr, sr0_ann = deflated_sharpe(base_gated, trial_sharpes, N)
    print(f"  Deflated Sharpe (N={N} trials): PSR vs luck-threshold "
          f"(ann SR0={sr0_ann:.2f}) = {dsr*100:.1f}%", flush=True)
    print("  (PSR>0 ~100% and DSR>95% => edge unlikely to be a multiple-testing fluke)", flush=True)


if __name__ == "__main__":
    main()
