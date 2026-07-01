#!/usr/bin/env python3
"""backtest_regime.py — PHASE 8: multi-signal macro regime engine.

Replaces the single breadth gate with a vote-based risk-on/off classifier and tests
whether better timing improves the strategy's risk-adjusted return.

Four trailing (as-of, no-lookahead) risk-on votes at each month-end:
  1. market breadth  %>200DMA >= 50
  2. NIFTY 50  >  its own 200-DMA
  3. S&P 500   >  its own 200-DMA           (global risk proxy)
  4. India VIX < its trailing 1-yr median   (calm vol)

Regime score = count of votes (0-4). Gate the book when score >= threshold.
Compared against ungated and the current breadth-only gate.

Run:  py -3.14 common/backtest_regime.py
"""
import sqlite3

import numpy as np
import pandas as pd

from backtest_momentum import DB_PATH, N_DECILES, COST_PER_SIDE, load_panel, metrics
from backtest_hardening import book_returns


def asof(series_df, rebals, col="val"):
    """Last value on/before each rebalance date."""
    s = series_df.set_index("date")[col].sort_index()
    out = {}
    for R in rebals:
        sub = s[s.index <= R]
        out[R] = sub.iloc[-1] if len(sub) else np.nan
    return pd.Series(out)


def fmt(m):
    return (f"CAGR {m['CAGR']*100:5.1f}%  Vol {m['Vol']*100:4.1f}%  Sharpe {m['Sharpe']:4.2f}  "
            f"Sortino {m['Sortino']:4.2f}  MaxDD {m['MaxDD']*100:6.1f}%  Calmar {m['Calmar']:4.2f}  "
            f"invested {m.get('inv',0)*100:.0f}%") if m else "n/a"


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    print("Loading panel + macro series ...", flush=True)
    panel, rebals, breadth = load_panel(conn)

    g = pd.read_sql("SELECT date,symbol,close FROM global_indices_daily "
                    "WHERE symbol IN ('NIFTY50','SPX','IndiaVIX')", conn)
    conn.close()

    def trend_votes(sym):
        d = g[g["symbol"] == sym][["date", "close"]].sort_values("date").copy()
        d["ma200"] = d["close"].rolling(200).mean()
        d["val"] = (d["close"] > d["ma200"]).astype(float)
        return asof(d, rebals)

    nifty_vote = trend_votes("NIFTY50")
    spx_vote = trend_votes("SPX")
    vix = g[g["symbol"] == "IndiaVIX"][["date", "close"]].sort_values("date").copy()
    vix["med"] = vix["close"].rolling(252).median()
    vix["val"] = (vix["close"] < vix["med"]).astype(float)
    vix_vote = asof(vix, rebals)
    br = breadth.set_index("date")["pct_above_200dma"]
    breadth_vote = pd.Series({R: (br[br.index <= R].iloc[-1] >= 50)
                              if len(br[br.index <= R]) else np.nan for R in rebals}).astype(float)

    votes = pd.DataFrame({"breadth": breadth_vote, "nifty": nifty_vote,
                          "spx": spx_vote, "vix": vix_vote})
    votes["score"] = votes.sum(axis=1, skipna=True)
    print(f"  regime score available for {votes['score'].notna().sum()} months", flush=True)
    print(f"  mean votes: " + ", ".join(f"{c}={votes[c].mean():.2f}" for c in
                                         ["breadth", "nifty", "spx", "vix"]) + "\n", flush=True)

    # ungated book (inverse... use equal-weight composite decile book)
    book = book_returns(panel, rebals, {N_DECILES}, set(), COST_PER_SIDE, "decile")
    raw = book["long_net"]

    def gated(thresh):
        sc = votes["score"].reindex(raw.index)
        r = pd.Series(np.where(sc >= thresh, raw.values, 0.0), index=raw.index)
        m = metrics(r)
        if m:
            m["inv"] = (sc >= thresh).mean()
        return m

    def breadth_only():
        b = breadth_vote.reindex(raw.index)
        r = pd.Series(np.where(b >= 1, raw.values, 0.0), index=raw.index)
        m = metrics(r)
        if m:
            m["inv"] = (b >= 1).mean()
        return m

    print("=== REGIME GATE COMPARISON (LongOnly D10, net 30bps) ===", flush=True)
    mu = metrics(raw); mu["inv"] = 1.0
    print(f"  Ungated (always in)         : {fmt(mu)}", flush=True)
    print(f"  Breadth-only gate (current) : {fmt(breadth_only())}", flush=True)
    for t in (2, 3, 4):
        print(f"  Regime gate (>= {t}/4 votes)  : {fmt(gated(t))}", flush=True)
    print("\n  (More votes = more selective = fewer invested months; pick the best\n"
          "   Sharpe/Calmar vs time-in-market trade-off.)", flush=True)


if __name__ == "__main__":
    main()
