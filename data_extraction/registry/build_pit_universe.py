#!/usr/bin/env python3
"""build_pit_universe.py — PHASE 1 enabler (survivorship guardrail #2).

Builds `pit_universe`: a point-in-time, monthly liquid-universe membership table
so cross-sectional studies pick names using ONLY information available at each
rebalance date -- no survivorship, no lookahead.

For each month-end trading date R, looks back 63 trading days and computes each
symbol's median daily turnover (raw close x volume). Symbols trading on >= 30 of
those days are eligible and ranked by median turnover; tier flags mark the top
100 / 250 / 500 and a >= Rs 1cr median-turnover "liquid" cut.

Because it is rebuilt from raw bhavcopy (which keeps delisted names), a symbol
appears in the universe only for the months it was actually liquid and listed --
e.g. a 2012 mid-cap that later delisted is IN the 2011 universe and ABSENT from
2020, exactly as a backtest must see it.

Output `pit_universe`:
  rebal_date, symbol, n_days, med_turnover, adv_rank, top100, top250, top500, liquid

Idempotent (rebuilds the table). Run:  py -3.14 registry/build_pit_universe.py
"""
import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

# ETFs/funds (NAV-creep games momentum/52w-high/delivery). Excluded from the
# equity tradable universe. Primary signal: ISIN prefix INF (funds) vs INE
# (equities); pattern fallback for symbols not yet in isin_master.
ETF_RE = re.compile(
    r"(BEES|ETF|LIQUID|SILVER|CPSE|BHARATBOND|GSEC|GOLDBEES|GOLDCASE|GOLDIETF|"
    r"GOLDSHARE|MAFANG|HNGSNG|NIFTYBEES|EBBETF|SDLBOND|MON100|MOM100|NETF)", re.I)

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
WINDOW_TD = 63          # trailing trading days (~3 months)
MIN_DAYS = 30           # must trade at least this many of the window
LIQUID_FLOOR = 1e7      # Rs 1 crore median daily turnover


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=MEMORY")

    print("Loading stock_data (close, volume) ...", flush=True)
    df = pd.read_sql("SELECT symbol, date, close, volume FROM stock_data", conn)
    df["turnover"] = df["close"].astype(float) * df["volume"].astype(float)
    df = df[["symbol", "date", "turnover"]].dropna(subset=["turnover"])

    # exclude ETFs / funds (not equities)
    inf = pd.read_sql("SELECT DISTINCT symbol FROM isin_master WHERE isin LIKE 'INF%'",
                      conn)["symbol"].tolist()
    pat = [s for s in df["symbol"].unique() if ETF_RE.search(s)]
    exclude = set(inf) | set(pat)
    before = df["symbol"].nunique()
    df = df[~df["symbol"].isin(exclude)]
    print(f"  excluded {len(exclude)} ETF/fund symbols "
          f"({len(inf)} INF-ISIN + {len(pat)} pattern); "
          f"{before}->{df['symbol'].nunique()} equity symbols", flush=True)

    df = df.sort_values("date").reset_index(drop=True)
    print(f"  {len(df):,} rows, {df['symbol'].nunique():,} symbols", flush=True)

    all_dates = np.sort(df["date"].unique())
    # last trading date of each calendar month = rebalance points
    months = pd.Series(all_dates).str.slice(0, 7)
    rebal_dates = pd.Series(all_dates).groupby(months.values).max().tolist()
    print(f"  {len(rebal_dates)} monthly rebalance dates "
          f"({rebal_dates[0]} -> {rebal_dates[-1]})", flush=True)

    date_arr = df["date"].to_numpy()
    sym_arr = df["symbol"].to_numpy()
    turn_arr = df["turnover"].to_numpy()

    out = []
    for R in rebal_dates:
        # window = the WINDOW_TD trading days ending at R (inclusive)
        end_i = np.searchsorted(all_dates, R, side="right")     # dates[:end_i] <= R
        start_i = max(0, end_i - WINDOW_TD)
        win_start = all_dates[start_i]
        mask = (date_arr >= win_start) & (date_arr <= R)
        if not mask.any():
            continue
        w = pd.DataFrame({"symbol": sym_arr[mask], "turnover": turn_arr[mask]})
        g = w.groupby("symbol")["turnover"].agg(["median", "count"])
        g = g[g["count"] >= MIN_DAYS].copy()
        if g.empty:
            continue
        g = g.sort_values("median", ascending=False).reset_index()
        g["adv_rank"] = np.arange(1, len(g) + 1)
        for _, r in g.iterrows():
            rank = int(r["adv_rank"])
            out.append((
                R, r["symbol"], int(r["count"]), float(r["median"]), rank,
                int(rank <= 100), int(rank <= 250), int(rank <= 500),
                int(r["median"] >= LIQUID_FLOOR),
            ))

    print(f"Writing pit_universe ({len(out):,} rows) ...", flush=True)
    conn.execute("DROP TABLE IF EXISTS pit_universe")
    conn.execute("""CREATE TABLE pit_universe (
        rebal_date TEXT, symbol TEXT, n_days INTEGER, med_turnover REAL,
        adv_rank INTEGER, top100 INTEGER, top250 INTEGER, top500 INTEGER,
        liquid INTEGER, PRIMARY KEY(rebal_date, symbol))""")
    conn.executemany("INSERT OR REPLACE INTO pit_universe VALUES (?,?,?,?,?,?,?,?,?)", out)
    conn.execute("CREATE INDEX idx_pu_date ON pit_universe(rebal_date)")
    conn.commit()

    # ---- validation ----
    print("\n=== VALIDATION ===", flush=True)
    n, nd = conn.execute("SELECT COUNT(*), COUNT(DISTINCT rebal_date) FROM pit_universe").fetchone()
    print(f"pit_universe: {n:,} rows across {nd} months", flush=True)
    print("\nUniverse size over time (eligible / top500 / liquid):", flush=True)
    for yr in ("2006-12", "2010-12", "2015-12", "2020-12", "2025-12", "2026-06"):
        row = conn.execute(
            "SELECT rebal_date, COUNT(*), SUM(top500), SUM(liquid) FROM pit_universe "
            "WHERE rebal_date LIKE ?||'%' GROUP BY rebal_date ORDER BY rebal_date DESC LIMIT 1",
            (yr,)).fetchone()
        if row:
            print(f"  {row[0]}: eligible={row[1]:>5,}  top500={row[2]:>4}  liquid={row[3]:>5}", flush=True)
    print("\nTop 8 by turnover at latest rebalance (sanity = large caps):", flush=True)
    last = conn.execute("SELECT MAX(rebal_date) FROM pit_universe").fetchone()[0]
    for r in conn.execute(
        "SELECT symbol, med_turnover FROM pit_universe WHERE rebal_date=? "
        "ORDER BY adv_rank LIMIT 8", (last,)).fetchall():
        print(f"  {r[0]:14} Rs {r[1]/1e7:,.1f} cr/day", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
