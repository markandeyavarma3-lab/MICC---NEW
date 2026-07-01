#!/usr/bin/env python3
"""backtest_multifactor.py — PHASE 6.

Extends the flagship into a multi-factor book and tests two upgrades:
  B) add the LOW-VOLATILITY factor (low_vol = -vol_3m) to the 3-factor composite
     -> 4-factor equal-weight. Fully supported (vol_3m exists for every name).
  C) SECTOR-NEUTRALIZE the 4-factor composite (demean each factor's rank within
     NSE sector at each date). APPROXIMATE: sector = current index_constituents
     snapshot, which covers ~49% of historical top500 rows -> uncovered names go
     to an 'Unknown' bucket. Reported honestly, not oversold.

All books: gated LongOnly D10 (the proven config), 30 bps/side, top500 equity
universe, same realized returns + regime gate as the flagship.

Run:  py -3.14 common/backtest_multifactor.py
"""
import sqlite3

import numpy as np
import pandas as pd

from backtest_momentum import DB_PATH, SIGNALS, N_DECILES, COST_PER_SIDE, load_panel, metrics
from backtest_hardening import book_returns, gate

FACTORS4 = SIGNALS + ["low_vol"]


def decile(panel, comp_col):
    return panel.groupby("rebal_date")[comp_col].transform(
        lambda x: pd.qcut(x.rank(method="first"), N_DECILES, labels=False) + 1)


def plain_composite(panel, factors):
    parts = []
    for f in factors:
        parts.append(panel.groupby("rebal_date")[f].rank(pct=True))
    return pd.concat(parts, axis=1).mean(axis=1)


def secneutral_composite(panel, factors):
    parts = []
    for f in factors:
        r = panel.groupby("rebal_date")[f].rank(pct=True)
        tmp = pd.DataFrame({"rebal_date": panel["rebal_date"], "sector": panel["sector"], "r": r})
        sec_mean = tmp.groupby(["rebal_date", "sector"])["r"].transform("mean")
        parts.append(r - sec_mean)              # demean within sector at each date
    return pd.concat(parts, axis=1).mean(axis=1)


def run(panel, rebals, breadth, comp_col):
    panel = panel.copy()
    panel["dec"] = decile(panel, comp_col)
    bk = book_returns(panel, rebals, {N_DECILES}, set(), COST_PER_SIDE, "dec")
    return metrics(gate(bk["long_net"], breadth))


def fmt(m):
    return (f"CAGR {m['CAGR']*100:5.1f}%  Vol {m['Vol']*100:4.1f}%  Sharpe {m['Sharpe']:4.2f}  "
            f"Sortino {m['Sortino']:4.2f}  MaxDD {m['MaxDD']*100:6.1f}%  Calmar {m['Calmar']:4.2f}")


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    print("Loading panel + vol_3m + sector ...", flush=True)
    panel, rebals, breadth = load_panel(conn)
    vol = pd.read_sql("SELECT rebal_date,symbol,vol_3m FROM features_monthly", conn)
    sec = pd.read_sql("SELECT DISTINCT symbol,industry AS sector FROM index_constituents "
                      "WHERE industry IS NOT NULL", conn).drop_duplicates("symbol")
    conn.close()

    panel = panel.merge(vol, on=["rebal_date", "symbol"], how="left")
    panel = panel.merge(sec, on="symbol", how="left")
    panel["sector"] = panel["sector"].fillna("Unknown")
    panel = panel.dropna(subset=["vol_3m"]).copy()
    panel["low_vol"] = -panel["vol_3m"]
    cov = (panel["sector"] != "Unknown").mean()
    print(f"  {len(panel):,} rows; sector coverage {cov*100:.0f}% "
          f"(rest -> Unknown bucket)\n", flush=True)

    # low_vol IC justification
    liq = panel[panel["top500"] == 1]
    ic = liq.groupby("rebal_date").apply(
        lambda g: g["low_vol"].rank().corr(g["fwd_ret_1m"].rank())
        if "fwd_ret_1m" in g else np.nan)
    # fwd not in panel (load_panel drops it); recompute IC from realized
    ic = liq.groupby("rebal_date").apply(
        lambda g: g["low_vol"].rank().corr(g["realized"].rank()))
    print(f"low_vol rank-IC vs realized (top500): {ic.mean():+.4f} "
          f"({(ic>0).mean()*100:.0f}% +months)\n", flush=True)

    print("=== MULTI-FACTOR COMPARISON (gated LongOnly D10, net 30bps) ===", flush=True)
    # A) flagship 3-factor
    panel["comp_3f"] = plain_composite(panel, SIGNALS)
    print(f"  A 3-factor (flagship)           : {fmt(run(panel, rebals, breadth, 'comp_3f'))}", flush=True)
    # B) 4-factor + low_vol
    panel["comp_4f"] = plain_composite(panel, FACTORS4)
    print(f"  B 4-factor (+low_vol)           : {fmt(run(panel, rebals, breadth, 'comp_4f'))}", flush=True)
    # C) 4-factor sector-neutral (approximate)
    panel["comp_sn"] = secneutral_composite(panel, FACTORS4)
    print(f"  C 4-factor sector-neutral (~)   : {fmt(run(panel, rebals, breadth, 'comp_sn'))}", flush=True)
    print("\n  (C is sector-limited: only ~49% of historical rows have a real sector;\n"
          "   treat as indicative. B is the supported upgrade.)", flush=True)

    # persist the winning multi-factor equity curve
    panel["dec"] = decile(panel, "comp_4f")
    bk = book_returns(panel, rebals, {N_DECILES}, set(), COST_PER_SIDE, "dec")
    g = gate(bk["long_net"], breadth).dropna()
    eq = (1 + g).cumprod()
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("DROP TABLE IF EXISTS bt_multifactor")
    conn.execute("CREATE TABLE bt_multifactor (date TEXT, ret REAL, equity REAL)")
    conn.executemany("INSERT INTO bt_multifactor VALUES (?,?,?)",
                     [(d, float(r), float(e)) for d, r, e in zip(g.index, g.values, eq.values)])
    conn.commit(); conn.close()
    print(f"\n  Saved 4-factor gated equity ({eq.iloc[-1]:.1f}x) -> bt_multifactor.", flush=True)


if __name__ == "__main__":
    main()
