#!/usr/bin/env python3
"""mf_scorecard.py — PHASE 10/11 product: equity mutual-fund risk-adjusted scorecard.

Ranks equity Growth-plan funds by risk-adjusted return from mf_nav_history. A factual,
SEBI-compliant analytics product (no advice). Metrics per fund:
  1y/3y/5y CAGR, annualized vol, 3y Sharpe (rf=6%), max drawdown, rolling-1y consistency.
Ranked within category. Writes `mf_scorecard`.

NOTE: NAV != holdings. This ranks performance/risk, not portfolio composition.

Run:  py -3.14 funds/mf_scorecard.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
RF = 0.06
YEAR = np.timedelta64(365, "D")


def fund_metrics(d):
    d = d.sort_values("date")
    dates = d["date"].to_numpy()
    nav = d["nav"].to_numpy(dtype=float)
    if len(d) < 252 or nav[-1] <= 0:
        return None
    last, last_dt = nav[-1], dates[-1]

    def cagr(yrs):
        idx = np.searchsorted(dates, last_dt - int(yrs) * YEAR, side="right") - 1
        if idx < 0 or nav[idx] <= 0:
            return np.nan
        r = last / nav[idx]
        return r ** (1.0 / yrs) - 1 if yrs >= 1 else r - 1

    ret = pd.Series(nav).pct_change()
    ann_vol = ret.std() * np.sqrt(252)
    cummax = pd.Series(nav).cummax()
    max_dd = float((pd.Series(nav) / cummax - 1).min())
    c3 = cagr(3)
    sharpe3 = (c3 - RF) / ann_vol if ann_vol > 0 and not np.isnan(c3) else np.nan
    roll1y = pd.Series(nav) / pd.Series(nav).shift(252) - 1
    consistency = float((roll1y > 0).mean())
    yrs_hist = float((last_dt - dates[0]) / YEAR)
    return pd.Series({
        "last_date": str(pd.Timestamp(last_dt).date()), "last_nav": round(last, 2),
        "years": round(yrs_hist, 1), "cagr_1y": cagr(1), "cagr_3y": c3, "cagr_5y": cagr(5),
        "ann_vol": float(ann_vol), "max_dd": max_dd, "sharpe_3y": sharpe3,
        "consistency": consistency})


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    print("Selecting equity Growth schemes ...", flush=True)
    mst = pd.read_sql(
        "SELECT scheme_code,scheme_name,amc,category FROM mf_scheme_master "
        "WHERE category LIKE '%Equity%' AND scheme_name LIKE '%Growth%' "
        "AND scheme_name NOT LIKE '%IDCW%'", conn)
    codes = mst["scheme_code"].tolist()
    print(f"  {len(codes)} schemes; loading NAVs ...", flush=True)
    ph = ",".join("?" * len(codes))
    nav = pd.read_sql(f"SELECT scheme_code,date,nav FROM mf_nav_history "
                      f"WHERE scheme_code IN ({ph})", conn, params=codes)
    nav["date"] = pd.to_datetime(nav["date"], errors="coerce")
    nav = nav.dropna(subset=["date", "nav"])
    print(f"  {len(nav):,} NAV rows; computing metrics ...", flush=True)

    res = nav.groupby("scheme_code", group_keys=True).apply(fund_metrics).dropna(how="all")
    res = res.reset_index()
    sc = mst.merge(res, on="scheme_code", how="inner")
    sc["plan"] = np.where(sc["scheme_name"].str.contains("DIRECT", case=False), "Direct", "Regular")
    sc["cat_short"] = sc["category"].str.replace("Equity Scheme - ", "", regex=False)
    sc = sc[sc["years"] >= 3].copy()
    sc["rank_in_cat"] = sc.groupby("category")["sharpe_3y"].rank(ascending=False, method="min")
    sc = sc.sort_values("sharpe_3y", ascending=False)

    cols = ["scheme_code", "scheme_name", "amc", "cat_short", "plan", "last_date", "last_nav",
            "years", "cagr_1y", "cagr_3y", "cagr_5y", "ann_vol", "max_dd", "sharpe_3y",
            "consistency", "rank_in_cat"]
    conn.execute("DROP TABLE IF EXISTS mf_scorecard")
    sc[cols].to_sql("mf_scorecard", conn, if_exists="replace", index=False)
    conn.commit(); conn.close()

    print(f"\n=== TOP 15 EQUITY FUNDS by 3y Sharpe (Direct Growth, >=3y) ===", flush=True)
    top = sc[(sc["plan"] == "Direct") & sc["cagr_3y"].notna()].head(15)
    print(f"  {'fund':52} {'cat':14} {'3yCAGR':>7} {'Sharpe':>7} {'MaxDD':>7} {'cons':>5}", flush=True)
    for _, r in top.iterrows():
        nm = r["scheme_name"][:50]
        print(f"  {nm:52} {r['cat_short'][:14]:14} {r['cagr_3y']*100:>6.1f}% "
              f"{r['sharpe_3y']:>7.2f} {r['max_dd']*100:>6.0f}% {r['consistency']*100:>4.0f}%", flush=True)
    print(f"\n  Saved {len(sc):,} funds -> mf_scorecard "
          f"(rank_in_cat = 3y-Sharpe rank within category).", flush=True)


if __name__ == "__main__":
    main()
