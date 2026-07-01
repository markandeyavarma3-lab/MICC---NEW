#!/usr/bin/env python3
"""build_feature_store.py — PHASE 2.

Builds `features_monthly`: an as-of, point-in-time cross-sectional feature panel
sampled at each monthly rebalance date, the input every signal/backtest consumes.

Design rules (anti-lookahead):
  * Prices come from `stock_data_adj` (corporate-action adjusted) -- no split cliffs.
  * Every feature is strictly backward-looking (trailing windows only).
  * Rows are filtered through `pit_universe` -> survivorship-free membership.
  * Forward returns are stored ONLY as `fwd_*` LABEL columns (the y), never as features.

Features (all as-of the rebalance close):
  momentum : ret_1m/3m/6m/12m, mom_12_1, mom_6_1
  vol      : vol_3m, vol_6m (annualized realized)
  trend    : dist_sma50, dist_sma200, above_200, prox_52w_high
  liquidity: amihud (illiquidity), adv_rank, med_turnover, top500, liquid
  delivery : deliv_1m, deliv_3m, deliv_trend
Labels: fwd_ret_1m, fwd_ret_3m

Idempotent. Run:  py -3.14 common/build_feature_store.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\marketDB\db\market.db")
ROOT252 = np.sqrt(252.0)


def grp_roll(df, col, w, func):
    """C-accelerated rolling within symbol, realigned to df's index."""
    return df.groupby("symbol")[col].rolling(w).agg(func).reset_index(level=0, drop=True)


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=MEMORY")

    print("Loading stock_data_adj + stock_delivery + pit_universe ...", flush=True)
    adj = pd.read_sql("SELECT symbol,date,close,volume FROM stock_data_adj", conn)
    deliv = pd.read_sql("SELECT symbol,date,delivery_percent FROM stock_delivery", conn)
    pu = pd.read_sql("SELECT rebal_date,symbol,adv_rank,med_turnover,top500,liquid "
                     "FROM pit_universe", conn)
    print(f"  adj {len(adj):,} | delivery {len(deliv):,} | universe {len(pu):,}", flush=True)

    adj = adj.merge(deliv, on=["symbol", "date"], how="left")
    adj = adj.sort_values(["symbol", "date"]).reset_index(drop=True)

    gc = adj.groupby("symbol")["close"]
    close = adj["close"]
    adj["ret_d"] = close / gc.shift(1) - 1.0
    adj["turnover"] = close * adj["volume"]
    adj["illiq_d"] = adj["ret_d"].abs() / adj["turnover"].replace(0, np.nan)

    print("Computing momentum ...", flush=True)
    c21, c63, c126, c252 = gc.shift(21), gc.shift(63), gc.shift(126), gc.shift(252)
    adj["ret_1m"] = close / c21 - 1
    adj["ret_3m"] = close / c63 - 1
    adj["ret_6m"] = close / c126 - 1
    adj["ret_12m"] = close / c252 - 1
    adj["mom_12_1"] = c21 / c252 - 1            # 12m return skipping last month
    adj["mom_6_1"] = c21 / c126 - 1

    print("Computing vol / trend / liquidity / delivery ...", flush=True)
    adj["vol_3m"] = grp_roll(adj, "ret_d", 63, "std") * ROOT252
    adj["vol_6m"] = grp_roll(adj, "ret_d", 126, "std") * ROOT252
    sma50 = grp_roll(adj, "close", 50, "mean")
    sma200 = grp_roll(adj, "close", 200, "mean")
    adj["dist_sma50"] = close / sma50 - 1
    adj["dist_sma200"] = close / sma200 - 1
    adj["above_200"] = (close > sma200).astype("Int64")
    adj["prox_52w_high"] = close / grp_roll(adj, "close", 252, "max")
    adj["amihud"] = grp_roll(adj, "illiq_d", 21, "mean") * 1e7
    adj["deliv_1m"] = grp_roll(adj, "delivery_percent", 21, "mean")
    adj["deliv_3m"] = grp_roll(adj, "delivery_percent", 63, "mean")
    adj["deliv_trend"] = adj["deliv_1m"] - adj["deliv_3m"]

    print("Computing forward-return LABELS ...", flush=True)
    adj["fwd_ret_1m"] = gc.shift(-21) / close - 1
    adj["fwd_ret_3m"] = gc.shift(-63) / close - 1

    feat_cols = ["ret_1m", "ret_3m", "ret_6m", "ret_12m", "mom_12_1", "mom_6_1",
                 "vol_3m", "vol_6m", "dist_sma50", "dist_sma200", "above_200",
                 "prox_52w_high", "amihud", "deliv_1m", "deliv_3m", "deliv_trend",
                 "fwd_ret_1m", "fwd_ret_3m"]

    print("Sampling at monthly rebalance dates + universe join ...", flush=True)
    feat = adj[["symbol", "date"] + feat_cols].merge(
        pu, left_on=["date", "symbol"], right_on=["rebal_date", "symbol"], how="inner")
    feat = feat.drop(columns=["date"])
    out_cols = ["rebal_date", "symbol", "adv_rank", "med_turnover", "top500", "liquid"] + feat_cols
    feat = feat[out_cols]
    print(f"  {len(feat):,} feature rows", flush=True)

    print("Writing features_monthly ...", flush=True)
    conn.execute("DROP TABLE IF EXISTS features_monthly")
    feat.to_sql("features_monthly", conn, if_exists="replace", index=False, chunksize=50000)
    conn.execute("CREATE INDEX idx_fm_date ON features_monthly(rebal_date)")
    conn.execute("CREATE INDEX idx_fm_sym ON features_monthly(symbol)")
    conn.commit()

    validate(feat)
    conn.close()


def rank_ic(df, feat, label):
    """Mean cross-sectional Spearman rank-IC of feat vs label, by rebalance date."""
    ics = []
    for _, g in df.groupby("rebal_date"):
        s = g[[feat, label]].dropna()
        if len(s) >= 20:
            ics.append(s[feat].rank().corr(s[label].rank()))
    ics = pd.Series(ics).dropna()
    return ics.mean(), (ics > 0).mean(), len(ics)


def validate(feat):
    print("\n=== VALIDATION ===", flush=True)
    print(f"rows={len(feat):,}  months={feat['rebal_date'].nunique()}  "
          f"symbols={feat['symbol'].nunique():,}", flush=True)
    print(f"date range: {feat['rebal_date'].min()} -> {feat['rebal_date'].max()}", flush=True)

    # restrict IC test to the liquid, tradable universe (top500) -- where it matters
    liq = feat[feat["top500"] == 1]
    print("\nMean cross-sectional rank-IC vs forward return (top500 universe):", flush=True)
    print(f"  {'feature':14} {'IC vs 1m':>10} {'%+months':>10} {'IC vs 3m':>10}", flush=True)
    for f in ["mom_12_1", "mom_6_1", "ret_12m", "ret_3m", "vol_3m", "dist_sma200",
              "prox_52w_high", "amihud", "deliv_1m"]:
        ic1, pos1, n1 = rank_ic(liq, f, "fwd_ret_1m")
        ic3, _, _ = rank_ic(liq, f, "fwd_ret_3m")
        print(f"  {f:14} {ic1:>+10.4f} {pos1*100:>9.0f}% {ic3:>+10.4f}", flush=True)
    print("\n(positive IC for momentum / negative for vol & amihud = data supports the premise)",
          flush=True)


if __name__ == "__main__":
    main()
