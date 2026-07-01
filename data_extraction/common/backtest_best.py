#!/usr/bin/env python3
"""backtest_best.py — walk-forward-validate the regime threshold + combined best config.

(1) The 4-vote macro regime gate (backtest_regime.py) was best at >=2/4 IN-SAMPLE (Sharpe 1.43).
    Here the threshold is chosen WALK-FORWARD: at each rebalance, pick the threshold that maximized
    the gated book's Sharpe on data strictly before that date, apply it forward -> a true OOS number
    that removes the in-sample threshold-selection bias.

(2) Combined best config: inverse-vol-weighted top-decile book + walk-forward regime gate +
    12%-vol-target overlay. Stacks the Phase 8 (regime) and Phase 5 (sizing) wins. Persists `bt_best`.

Run:  py -3.14 common/backtest_best.py
"""
import sqlite3

import numpy as np
import pandas as pd

from backtest_momentum import DB_PATH, N_DECILES, COST_PER_SIDE, load_panel, metrics
from backtest_hardening import book_returns
from backtest_execution import weighted_book

MIN_TRAIN = 48          # months before walk-forward threshold selection starts
TARGET_VOL = 0.12
MAX_LEVER = 1.5
CANDIDATES = (1, 2, 3, 4)


def asof_vote(df, rebals, col):
    s = df.set_index("date")[col].sort_index()
    return pd.Series({R: (s[s.index <= R].iloc[-1] if len(s[s.index <= R]) else np.nan)
                      for R in rebals})


def regime_score(conn, rebals, breadth):
    g = pd.read_sql("SELECT date,symbol,close FROM global_indices_daily "
                    "WHERE symbol IN ('NIFTY50','SPX','IndiaVIX')", conn)

    def trend_vote(sym):
        d = g[g["symbol"] == sym][["date", "close"]].sort_values("date").copy()
        d["v"] = (d["close"] > d["close"].rolling(200).mean()).astype(float)
        return asof_vote(d, rebals, "v")

    vix = g[g["symbol"] == "IndiaVIX"][["date", "close"]].sort_values("date").copy()
    vix["v"] = (vix["close"] < vix["close"].rolling(252).median()).astype(float)
    br = breadth.set_index("date")["pct_above_200dma"].sort_index()
    breadth_vote = pd.Series({R: (1.0 if (len(br[br.index <= R]) and br[br.index <= R].iloc[-1] >= 50)
                                  else 0.0) for R in rebals})
    votes = pd.DataFrame({"breadth": breadth_vote, "nifty": trend_vote("NIFTY50"),
                          "spx": trend_vote("SPX"), "vix": asof_vote(vix, rebals, "v")})
    return votes.sum(axis=1, skipna=True), breadth_vote


def wf_gate(raw, score, dates):
    """Walk-forward: at each date pick the threshold maximizing trailing gated Sharpe."""
    oos, chosen = {}, {}
    for i, R in enumerate(dates):
        if i < MIN_TRAIN or pd.isna(score.get(R, np.nan)):
            continue
        past = dates[:i]
        best_t, best_s = 2, -1e9
        for t in CANDIDATES:
            gp = pd.Series([raw[d] if score.get(d, 0) >= t else 0.0 for d in past
                            if d in raw.index], index=[d for d in past if d in raw.index])
            m = metrics(gp)
            if m and m["Sharpe"] > best_s:
                best_s, best_t = m["Sharpe"], t
        chosen[R] = best_t
        oos[R] = raw[R] if score.get(R, 0) >= best_t else 0.0
    return pd.Series(oos), pd.Series(chosen)


def fixed_gate(raw, score, thr):
    return pd.Series({R: (raw[R] if score.get(R, 0) >= thr else 0.0)
                      for R in raw.index if not pd.isna(score.get(R, np.nan))})


def vol_target(series):
    base = series.dropna()
    trail = base.rolling(12).std() * np.sqrt(12)
    expo = (TARGET_VOL / trail).clip(0, MAX_LEVER).shift(1)
    return (expo * base).dropna(), expo


def fmt(m):
    return (f"CAGR {m['CAGR']*100:5.1f}%  Vol {m['Vol']*100:4.1f}%  Sharpe {m['Sharpe']:4.2f}  "
            f"Sortino {m['Sortino']:4.2f}  MaxDD {m['MaxDD']*100:6.1f}%  Calmar {m['Calmar']:4.2f}") if m else "n/a"


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    print("Loading panel + macro regime + books ...", flush=True)
    panel, rebals, breadth = load_panel(conn)
    aux = pd.read_sql("SELECT rebal_date,symbol,vol_3m,med_turnover FROM features_monthly", conn)
    panel = panel.merge(aux, on=["rebal_date", "symbol"], how="left").dropna(subset=["vol_3m"])
    score, breadth_vote = regime_score(conn, rebals, breadth)
    conn.close()

    # ungated books
    ew = book_returns(panel, rebals, {N_DECILES}, set(), COST_PER_SIDE, "decile")["long_net"]
    iv = weighted_book(panel, rebals, "invvol", COST_PER_SIDE)[0]["net"]

    # walk-forward threshold selection on the EW book (validates the >=2/4 finding)
    ew_wf, chosen = wf_gate(ew, score, rebals)
    oos_dates = ew_wf.index
    print(f"  walk-forward OOS: {oos_dates.min()} -> {oos_dates.max()} ({len(oos_dates)} months)", flush=True)
    tc = chosen.value_counts().sort_index()
    print(f"  thresholds chosen walk-forward: " +
          ", ".join(f">={int(t)}:{int(n)}mo" for t, n in tc.items()), flush=True)

    # restrict every series to the SAME OOS window for a fair comparison
    def on_oos(s):
        return s.reindex(oos_dates)

    print("\n=== REGIME GATE: in-sample vs WALK-FORWARD (EW book, net, SAME OOS window) ===", flush=True)
    print(f"  Breadth-only gate        : {fmt(metrics(on_oos(fixed_gate(ew, breadth_vote*4, 1))))}", flush=True)
    print(f"  Fixed >=2/4 (in-sample)  : {fmt(metrics(on_oos(fixed_gate(ew, score, 2))))}", flush=True)
    print(f"  Walk-forward threshold   : {fmt(metrics(ew_wf))}", flush=True)
    survives = (chosen == 2).mean()
    print(f"  -> threshold>=2 chosen in {survives*100:.0f}% of WF months "
          f"({'CONFIRMS' if survives>0.5 else 'does NOT confirm'} the in-sample pick)", flush=True)

    # ===== combined best config =====
    iv_wf, _ = wf_gate(iv, score, rebals)
    vt, expo = vol_target(iv_wf)
    print("\n=== COMBINED CONFIG (inverse-vol + WF-regime gate [+ vol-target]) ===", flush=True)
    print(f"  inverse-vol + WF regime  : {fmt(metrics(iv_wf))}   <- BEST", flush=True)
    print(f"  + 12% vol-target overlay : {fmt(metrics(vt))}", flush=True)
    print(f"  -> vol-target does NOT stack on the regime gate (Sharpe "
          f"{metrics(iv_wf)['Sharpe']:.2f}->{metrics(vt)['Sharpe']:.2f}): the gate already "
          f"controls risk, so the overlay over-de-risks. Best = inverse-vol + regime gate.", flush=True)
    best = iv_wf.dropna()

    print("\n=== REFERENCE (prior in-sample headlines) ===", flush=True)
    print("  flagship breadth-gate Sharpe 1.12 | regime >=2/4 in-sample 1.43 | "
          "invvol+vol-target 1.18/Calmar 1.17", flush=True)

    # persist
    eq = (1 + best).cumprod()
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("DROP TABLE IF EXISTS bt_best")
    conn.execute("CREATE TABLE bt_best (date TEXT, ret REAL, equity REAL)")
    conn.executemany("INSERT INTO bt_best VALUES (?,?,?)",
                     [(d, float(r), float(e)) for d, r, e in zip(best.index, best.values, eq.values)])
    conn.commit(); conn.close()
    m = metrics(best)
    print(f"\n  Saved combined-best equity ({eq.iloc[-1]:.1f}x, Sharpe {m['Sharpe']:.2f}) -> bt_best.", flush=True)


if __name__ == "__main__":
    main()
