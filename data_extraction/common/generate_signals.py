#!/usr/bin/env python3
"""generate_signals.py — PHASE 3 operationalization.

Turns the validated flagship strategy into TODAY's actionable output: the current
month-end top-decile portfolio (the names you'd hold now), each with its signal
components and liquidity, plus the live breadth regime gate that says whether to
be invested or in cash.

Uses the SAME composite as the backtest (mean percentile-rank of mom_12_1 +
prox_52w_high + deliv_1m) on the latest top500 PIT universe. Writes `current_signals`.

This is research output, NOT investment advice.

Run:  py -3.14 common/generate_signals.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(r"D:\marketDB\db\market.db")
SIGNALS = ["mom_12_1", "prox_52w_high", "deliv_1m"]
N_DECILES = 10
GATE_THRESHOLD = 50.0     # invest only when %>200DMA >= 50


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")

    asof = conn.execute("SELECT MAX(rebal_date) FROM features_monthly").fetchone()[0]
    df = pd.read_sql(
        "SELECT rebal_date,symbol,adv_rank,med_turnover," + ",".join(SIGNALS) +
        " FROM features_monthly WHERE rebal_date=? AND top500=1", conn, params=(asof,))
    df = df.dropna(subset=SIGNALS).copy()

    # company names for readability
    reg = pd.read_sql("SELECT symbol,company_name FROM stock_registry", conn)
    df = df.merge(reg, on="symbol", how="left")

    # composite = mean percentile-rank (identical to backtest)
    for s in SIGNALS:
        df[s + "_r"] = df[s].rank(pct=True)
    df["composite"] = df[[s + "_r" for s in SIGNALS]].mean(axis=1)
    df["decile"] = pd.qcut(df["composite"].rank(method="first"), N_DECILES,
                           labels=False) + 1
    df["score"] = (df["composite"] * 100).round(1)
    df = df.sort_values("composite", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    df["in_portfolio"] = (df["decile"] == N_DECILES).astype(int)

    # live regime gate — 4-signal vote (validated OOS in backtest_best.py: the
    # multi-signal regime beats the single breadth gate, Sharpe 1.34 -> ~1.55)
    br = conn.execute(
        "SELECT date,pct_above_200dma,pct_above_50dma FROM market_breadth "
        "ORDER BY date DESC LIMIT 1").fetchone()
    breadth_date, pct200, pct50 = br
    gi = pd.read_sql("SELECT date,symbol,close FROM global_indices_daily "
                     "WHERE symbol IN ('NIFTY50','SPX','IndiaVIX')", conn)

    def _trend_on(sym):
        d = gi[gi["symbol"] == sym].sort_values("date")
        return None if len(d) < 200 else \
            float(d["close"].iloc[-1]) > float(d["close"].tail(200).mean())

    def _vix_calm():
        d = gi[gi["symbol"] == "IndiaVIX"].sort_values("date")
        return None if len(d) < 252 else \
            float(d["close"].iloc[-1]) < float(d["close"].tail(252).median())

    votes = {"breadth>50": pct200 >= GATE_THRESHOLD, "NIFTY>200DMA": _trend_on("NIFTY50"),
             "SPX>200DMA": _trend_on("SPX"), "VIX<1y-med": _vix_calm()}
    score = sum(1 for v in votes.values() if v)
    n_avail = sum(1 for v in votes.values() if v is not None)
    risk_on = score >= 2
    verdict = (f"RISK-ON ({score}/{n_avail} votes) -> hold top-decile book" if risk_on
               else f"RISK-OFF ({score}/{n_avail} votes) -> gate to CASH")

    # persist
    conn.execute("DROP TABLE IF EXISTS current_signals")
    conn.execute("""CREATE TABLE current_signals (
        rebal_date TEXT, rank INTEGER, symbol TEXT, company TEXT, decile INTEGER,
        score REAL, mom_12_1 REAL, prox_52w_high REAL, deliv_1m REAL,
        med_turnover REAL, in_portfolio INTEGER)""")
    conn.executemany(
        "INSERT INTO current_signals VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        df[["rebal_date", "rank", "symbol", "company_name", "decile", "score",
            "mom_12_1", "prox_52w_high", "deliv_1m", "med_turnover",
            "in_portfolio"]].itertuples(index=False, name=None))
    conn.commit()
    conn.close()

    # ---- report ----
    port = df[df["in_portfolio"] == 1]
    print("=" * 78)
    print(f"  MICC SIGNAL — as of {asof}   (top500 PIT universe, {len(df)} names)")
    print("=" * 78)
    print(f"  REGIME ({breadth_date}):  " +
          "  ".join(f"{k}={'Y' if v else ('N' if v is not None else '-')}" for k, v in votes.items())
          + f"   [%>200DMA={pct200:.0f}]")
    print(f"  GATE: {verdict}")
    print(f"  Top-decile book: {len(port)} names, equal-weight"
          + ("" if risk_on else "  [HELD AS CASH under regime gate]"))
    print("-" * 78)
    print(f"  {'#':>3} {'SYMBOL':12} {'score':>5} {'12-1mom':>8} {'52wH':>6} "
          f"{'deliv%':>6} {'Rs cr/d':>8}  company")
    print("-" * 78)
    for _, r in port.head(25).iterrows():
        comp = (str(r["company_name"])[:26] if pd.notna(r["company_name"]) else "")
        print(f"  {int(r['rank']):>3} {r['symbol']:12} {r['score']:>5.1f} "
              f"{r['mom_12_1']*100:>+7.1f}% {r['prox_52w_high']:>6.2f} "
              f"{r['deliv_1m']:>6.1f} {r['med_turnover']/1e7:>8.1f}  {comp}")
    if len(port) > 25:
        print(f"  ... +{len(port)-25} more (see current_signals table)")
    print("-" * 78)
    print(f"  Saved {len(df)} ranked names -> current_signals "
          f"(in_portfolio=1 marks the {len(port)} holdings).")
    print("  Research output only — not investment advice.")


if __name__ == "__main__":
    main()
