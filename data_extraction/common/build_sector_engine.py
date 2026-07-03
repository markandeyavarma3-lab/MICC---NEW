#!/usr/bin/env python3
"""build_sector_engine.py — Part 2 Module 5: sector rotation + macro sensitivity.

CONTEXT TIER ONLY. The stock-level rs_sector_6m candidate failed its IC gate
(t=1.37 < 3), so per the pre-registered benchmark rule the sector engine carries
ZERO scoring weight — it exists for idea-card context tags and the dashboard.

Tables:
  sector_regime_daily   per (date, sector): equal-weight sector index, 63d RS vs
                        NIFTY, RS momentum, RRG quadrant (leading/improving/
                        weakening/lagging), sector breadth %>200DMA, sector_score
                        (cross-sector RS percentile). All trailing/PIT-correct.
  macro_sensitivity     monthly as-of rolling 252d OLS betas of sector returns on
                        market/FX/crude/rates/dollar factors, with t-stats.
                        DISPLAY ONLY: insignificant betas are shown, never scored.

Idempotent full rebuild. Run:  py -3.14 common/build_sector_engine.py
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\marketDB\db\market.db")
MIN_MEMBERS = 5
RS_WIN, MOM_WIN, BETA_WIN = 63, 21, 252

DDL = ["""CREATE TABLE IF NOT EXISTS sector_regime_daily (
    date TEXT, sector TEXT,
    rs_vs_nifty REAL, rs_mom REAL, rs_rank INTEGER, rrg_quadrant TEXT,
    sector_breadth REAL, sector_score REAL, n_members INTEGER,
    PRIMARY KEY (date, sector))""",
       """CREATE TABLE IF NOT EXISTS macro_sensitivity (
    as_of TEXT, sector TEXT, axis TEXT, beta REAL, t_stat REAL, window INTEGER,
    PRIMARY KEY (as_of, sector, axis))"""]


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    for d in DDL:
        conn.execute(d)

    sec = pd.read_sql("SELECT symbol, sector FROM dim_sector WHERE sector IS NOT NULL "
                      "AND sector NOT IN ('ETF','Unknown')", conn)
    counts = sec["sector"].value_counts()
    sec = sec[sec["sector"].isin(counts[counts >= MIN_MEMBERS].index)]
    syms = tuple(sec["symbol"])
    print(f"  {sec['sector'].nunique()} sectors, {len(syms)} symbols", flush=True)

    px = pd.read_sql(f"SELECT date, symbol, close FROM stock_data_adj "
                     f"WHERE symbol IN ({','.join('?'*len(syms))}) AND date>='2006-06-01'",
                     conn, params=syms)
    wide = px.pivot_table(index="date", columns="symbol", values="close").sort_index()
    rets = wide.pct_change(fill_method=None)
    sym2sec = sec.set_index("symbol")["sector"]

    # equal-weight daily sector returns -> cumulative sector indices
    sec_ret = rets.T.groupby(sym2sec).mean().T
    n_mem = rets.notna().T.groupby(sym2sec).sum().T
    sec_idx = (1 + sec_ret.fillna(0)).cumprod()

    nifty = pd.read_sql("SELECT date, close FROM global_indices_daily WHERE symbol='NIFTY50' "
                        "ORDER BY date", conn).set_index("date")["close"]
    nifty = nifty.reindex(sec_idx.index).ffill()

    rs = sec_idx.pct_change(RS_WIN) \
        .sub(nifty.pct_change(RS_WIN), axis=0)               # 63d RS vs NIFTY
    rs_mom = rs - rs.shift(MOM_WIN)
    above200 = wide.gt(wide.rolling(200).mean())
    breadth = (above200.T.groupby(sym2sec).mean().T * 100).where(n_mem >= MIN_MEMBERS)
    score = rs.rank(axis=1, pct=True) * 100
    rank = rs.rank(axis=1, ascending=False)

    def quadrant(r, m):
        if pd.isna(r) or pd.isna(m):
            return None
        return ("leading" if r > 0 else "improving") if m > 0 else \
               ("weakening" if r > 0 else "lagging")

    rows = []
    start = "2008-01-01"
    for d in rs.index[rs.index >= start]:
        for s in rs.columns:
            r, m = rs.at[d, s], rs_mom.at[d, s]
            if pd.isna(r):
                continue
            rows.append((d, s, round(float(r), 5),
                         None if pd.isna(m) else round(float(m), 5),
                         None if pd.isna(rank.at[d, s]) else int(rank.at[d, s]),
                         quadrant(r, m),
                         None if pd.isna(breadth.at[d, s]) else round(float(breadth.at[d, s]), 1),
                         None if pd.isna(score.at[d, s]) else round(float(score.at[d, s]), 1),
                         int(n_mem.at[d, s])))
    conn.execute("DELETE FROM sector_regime_daily")
    conn.executemany("INSERT OR REPLACE INTO sector_regime_daily VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    print(f"  sector_regime_daily: {len(rows):,} rows", flush=True)

    # ---- macro_sensitivity: monthly as-of rolling multivariate OLS ----
    fac = {}
    for sym, name in [("NIFTY50", "market"), ("USDINR", "usdinr"), ("BrentCrude", "brent"),
                      ("US10Y", "us10y"), ("DXY", "dxy")]:
        s = pd.read_sql("SELECT date, close FROM global_indices_daily WHERE symbol=? ORDER BY date",
                        conn, params=(sym,)).set_index("date")["close"]
        s = s.reindex(sec_ret.index).ffill()
        fac[name] = s.diff() if name == "us10y" else s.pct_change(fill_method=None)
    F = pd.DataFrame(fac)

    month_ends = [g.index[-1] for _, g in
                  pd.Series(1, index=rs.index[rs.index >= "2010-01-01"])
                    .groupby(pd.to_datetime(rs.index[rs.index >= "2010-01-01"]).to_period("M"))]
    ms_rows = []
    axes = list(F.columns)
    for d in month_ends:
        i = sec_ret.index.get_loc(d)
        if i < BETA_WIN:
            continue
        win = slice(i - BETA_WIN + 1, i + 1)
        Xw = F.iloc[win]
        for s in sec_ret.columns:
            y = sec_ret[s].iloc[win]
            ok = y.notna() & Xw.notna().all(axis=1)
            if ok.sum() < 150:
                continue
            X = np.column_stack([np.ones(ok.sum()), Xw[ok].to_numpy()])
            yv = y[ok].to_numpy()
            beta, res, *_ = np.linalg.lstsq(X, yv, rcond=None)
            dof = len(yv) - X.shape[1]
            sigma2 = (res[0] / dof) if len(res) else np.var(yv - X @ beta) * len(yv) / dof
            se = np.sqrt(np.diag(sigma2 * np.linalg.inv(X.T @ X)))
            for k, ax in enumerate(axes, start=1):
                ms_rows.append((d, s, ax, round(float(beta[k]), 4),
                                round(float(beta[k] / se[k]), 2) if se[k] > 0 else None,
                                BETA_WIN))
    conn.execute("DELETE FROM macro_sensitivity")
    conn.executemany("INSERT OR REPLACE INTO macro_sensitivity VALUES (?,?,?,?,?,?)", ms_rows)
    conn.commit()

    latest = conn.execute("SELECT MAX(as_of) FROM macro_sensitivity").fetchone()[0]
    print(f"  macro_sensitivity: {len(ms_rows):,} rows (monthly as-of, latest {latest})", flush=True)
    print("  latest RRG snapshot:", flush=True)
    for r in conn.execute("SELECT sector, rrg_quadrant, ROUND(rs_vs_nifty*100,1), sector_breadth "
                          "FROM sector_regime_daily WHERE date=(SELECT MAX(date) FROM "
                          "sector_regime_daily) ORDER BY rs_vs_nifty DESC LIMIT 6"):
        print(f"    {r[0]:28} {r[1]:10} rs63 {r[2]:+.1f}%  breadth {r[3]}%", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
