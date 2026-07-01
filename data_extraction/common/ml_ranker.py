#!/usr/bin/env python3
"""ml_ranker.py — PHASE 9: ML cross-sectional ranker (research-first, leakage-controlled).

Trains a LightGBM learning-to-rank model to rank stocks each month by forward return,
using the full as-of feature store, and tests it OUT-OF-SAMPLE with purged + embargoed
expanding walk-forward CV. Honestly compared against the linear equal-weight composite
on the identical OOS window. ML is only "better" if it beats the simple model net of costs.

Anti-leakage:
  * expanding walk-forward: fold k trains only on rebalances strictly before the test block
  * 1-month EMBARGO (drop the month adjacent to the test block) so the 21-day forward
    label of the last train month cannot overlap the first test month's features
  * features are as-of; label is the realized R->R+1 return; no fwd_* columns as features

Run:  py -3.14 common/ml_ranker.py
"""
import sqlite3
import warnings

import numpy as np
import pandas as pd
import lightgbm as lgb

from backtest_momentum import DB_PATH, N_DECILES, COST_PER_SIDE, load_panel, metrics
from backtest_hardening import book_returns, gate

warnings.filterwarnings("ignore")

FEATURES = ["ret_1m", "ret_3m", "ret_6m", "ret_12m", "mom_12_1", "mom_6_1",
            "vol_3m", "vol_6m", "dist_sma50", "dist_sma200", "above_200",
            "prox_52w_high", "amihud", "deliv_1m", "deliv_3m", "deliv_trend",
            "med_turnover", "adv_rank", "liquid"]
MIN_TRAIN = 60      # months before first OOS prediction
STEP = 12           # OOS block size (months)
EMBARGO = 1         # months dropped between train and test


def fmt(m):
    return (f"CAGR {m['CAGR']*100:5.1f}%  Vol {m['Vol']*100:4.1f}%  Sharpe {m['Sharpe']:4.2f}  "
            f"Sortino {m['Sortino']:4.2f}  MaxDD {m['MaxDD']*100:6.1f}%  Calmar {m['Calmar']:4.2f}") if m else "n/a"


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    print("Loading panel + full feature set ...", flush=True)
    panel0, rebals, breadth = load_panel(conn)          # realized + linear composite + breadth
    full = pd.read_sql(
        "SELECT rebal_date,symbol,top500," + ",".join(FEATURES) +
        " FROM features_monthly WHERE top500=1", conn)
    conn.close()
    panel = full.merge(panel0[["rebal_date", "symbol", "realized", "composite"]],
                       on=["rebal_date", "symbol"], how="inner")
    # cross-sectional relevance label = forward-return decile per date (0..9)
    panel["relevance"] = panel.groupby("rebal_date")["realized"].transform(
        lambda x: pd.qcut(x.rank(method="first"), N_DECILES, labels=False))
    panel = panel.dropna(subset=["relevance"])
    panel["relevance"] = panel["relevance"].astype(int)
    print(f"  {len(panel):,} rows, {len(FEATURES)} features, {len(rebals)} months", flush=True)

    test_dates = rebals[MIN_TRAIN:]
    starts = list(range(MIN_TRAIN, len(rebals), STEP))
    print(f"  walk-forward: {len(starts)} folds, OOS {rebals[MIN_TRAIN]} -> {rebals[-1]} "
          f"(embargo={EMBARGO}mo)\n", flush=True)

    panel["ml_score"] = np.nan
    importances = np.zeros(len(FEATURES))
    nfold = 0
    for i in starts:
        tr_dates = set(rebals[: max(0, i - EMBARGO)])           # purge + embargo
        te_dates = set(rebals[i: i + STEP])
        tr = panel[panel["rebal_date"].isin(tr_dates)].sort_values("rebal_date")
        te = panel[panel["rebal_date"].isin(te_dates)]
        if len(tr) < 5000 or len(te) == 0:
            continue
        grp = tr.groupby("rebal_date").size().values
        model = lgb.LGBMRanker(
            objective="lambdarank", n_estimators=250, learning_rate=0.03,
            num_leaves=31, min_child_samples=50, subsample=0.8,
            colsample_bytree=0.8, random_state=42, n_jobs=-1, verbosity=-1)
        model.fit(tr[FEATURES], tr["relevance"], group=grp)
        panel.loc[te.index, "ml_score"] = model.predict(te[FEATURES])
        importances += model.feature_importances_
        nfold += 1
    importances /= max(nfold, 1)

    oos = panel[panel["ml_score"].notna()].copy()
    oos_dates = sorted(oos["rebal_date"].unique())
    print(f"OOS predictions: {len(oos):,} rows over {len(oos_dates)} months\n", flush=True)

    # ML decile book (gated long-only) vs linear composite on the SAME OOS window
    oos["ml_dec"] = oos.groupby("rebal_date")["ml_score"].transform(
        lambda x: pd.qcut(x.rank(method="first"), N_DECILES, labels=False) + 1)
    oos["lin_dec"] = oos.groupby("rebal_date")["composite"].transform(
        lambda x: pd.qcut(x.rank(method="first"), N_DECILES, labels=False) + 1)

    ml_book = book_returns(oos, oos_dates, {N_DECILES}, set(), COST_PER_SIDE, "ml_dec")
    lin_book = book_returns(oos, oos_dates, {N_DECILES}, set(), COST_PER_SIDE, "lin_dec")
    ml_g = gate(ml_book["long_net"], breadth)
    lin_g = gate(lin_book["long_net"], breadth)

    print("=== ML RANKER vs LINEAR COMPOSITE (gated LongOnly D10, net, SAME OOS) ===", flush=True)
    print(f"  Linear composite : {fmt(metrics(lin_g))}", flush=True)
    print(f"  LightGBM ranker  : {fmt(metrics(ml_g))}", flush=True)
    # ML+linear ensemble (rank-average)
    oos["ens"] = (oos.groupby("rebal_date")["ml_score"].rank(pct=True)
                  + oos.groupby("rebal_date")["composite"].rank(pct=True)) / 2
    oos["ens_dec"] = oos.groupby("rebal_date")["ens"].transform(
        lambda x: pd.qcut(x.rank(method="first"), N_DECILES, labels=False) + 1)
    ens_g = gate(book_returns(oos, oos_dates, {N_DECILES}, set(), COST_PER_SIDE, "ens_dec")["long_net"], breadth)
    print(f"  Ensemble (ML+lin): {fmt(metrics(ens_g))}", flush=True)

    # rank-IC comparison (OOS)
    def ic(col):
        v = oos.groupby("rebal_date").apply(
            lambda g: g[col].rank().corr(g["realized"].rank()))
        return v.mean()
    print(f"\n  OOS rank-IC: ML={ic('ml_score'):+.4f}  linear={ic('composite'):+.4f}", flush=True)

    print("\n=== LightGBM feature importance (avg gain across folds, top 10) ===", flush=True)
    imp = sorted(zip(FEATURES, importances), key=lambda x: -x[1])
    for f, v in imp[:10]:
        bar = "#" * int(v / max(importances) * 40)
        print(f"  {f:14} {bar}", flush=True)

    # persist ML equity
    g = ml_g.dropna(); eq = (1 + g).cumprod()
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("DROP TABLE IF EXISTS bt_ml_ranker")
    conn.execute("CREATE TABLE bt_ml_ranker (date TEXT, ret REAL, equity REAL)")
    conn.executemany("INSERT INTO bt_ml_ranker VALUES (?,?,?)",
                     [(d, float(r), float(e)) for d, r, e in zip(g.index, g.values, eq.values)])
    conn.commit(); conn.close()
    print(f"\n  Saved ML gated equity ({eq.iloc[-1]:.1f}x) -> bt_ml_ranker.", flush=True)


if __name__ == "__main__":
    main()
