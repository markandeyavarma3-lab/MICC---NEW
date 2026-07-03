#!/usr/bin/env python3
"""backtest_value_quality.py — Part 3 Module D(b) final step: the value/quality
re-backtest on the extended PIT fundamentals history. This is the ONLY path to
lifting the A3 value/quality confidence cap (<=70).

SURVIVORSHIP WARNING (printed with every run): the screener history covers the
CURRENT top-500 — companies that shrank/died since 2012 are absent, and only
~40% of historical top-500 rows have as-of fundamentals. Therefore:
  * a FAIL here is a STRONG negative (the signal failed even with a survivor
    tailwind), and the cap stays;
  * a PASS is an UPPER BOUND, never sufficient on its own — the cap lift stays a
    human decision (`--approve-cap-lift`), recorded in rule_change_log with the
    caveat attached.

Signals (pre-registered in signal_preregistration, prior sign +):
  value_ep         EPS(as-of, screener split-adjusted) / adjusted close at rebal
  quality_margin   OPM %% (Financing Margin %% for financials), as-of
  quality_growth   3-FY Net Profit growth, as-of

PIT: as-of join on pit_date <= rebal_date (FY-end + 60d convention), staleness
cap 400 days. Gate (same as every signal): monthly rank-IC vs fwd_ret_1m with
prior sign, |t| >= 3.0, second-half same sign, on months with >= 100 names.

Run:  py -3.14 common/backtest_value_quality.py [--approve-cap-lift]
"""
import sqlite3
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from backtest_momentum import DB_PATH

MIN_NAMES = 100
STALE_DAYS = 400
CANDS = ["value_ep", "quality_margin", "quality_growth"]


def load_asof_fundamentals(conn):
    f = pd.read_sql("SELECT symbol, report_date, pit_date, metric, value "
                    "FROM fundamentals_annual_pit WHERE metric IN "
                    "('EPS in Rs','Net Profit','OPM %','Financing Margin %')", conn)
    w = f.pivot_table(index=["symbol", "report_date", "pit_date"],
                      columns="metric", values="value").reset_index()
    w["margin"] = w.get("OPM %").fillna(w.get("Financing Margin %")) \
        if "Financing Margin %" in w else w.get("OPM %")
    w = w.sort_values(["symbol", "pit_date"])
    # 3-FY Net Profit growth (as-of the same filing)
    w["np_3ago"] = w.groupby("symbol")["Net Profit"].shift(3)
    w["growth3"] = (w["Net Profit"] - w["np_3ago"]) / w["np_3ago"].abs()
    return w


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")

    if "--approve-cap-lift" in sys.argv:
        v = conn.execute("SELECT verdict FROM signal_candidate_validation "
                         "WHERE candidate IN ('value_ep','quality_margin','quality_growth') "
                         "AND verdict='scored'").fetchall()
        if not v:
            print("  REFUSED: no value/quality candidate holds a 'scored' verdict — "
                  "nothing to approve.", flush=True)
            sys.exit(1)
        now = datetime.now().isoformat()
        conn.execute("INSERT OR REPLACE INTO score_weights VALUES "
                     "('v2.0','_cap_lift_enabled',1.0,?, "
                     "'owner-approved after value re-backtest; SURVIVORSHIP CAVEAT applies')",
                     (now[:10],))
        conn.execute("INSERT INTO rule_change_log (change_date,component,description,"
                     "evidence_ref,approved_by) VALUES (?,?,?,?,?)",
                     (now, "weights", "cap_lift enabled per-symbol (>=8yr validated depth); "
                      "survivorship-caveated pass", "signal_candidate_validation", "owner"))
        conn.commit()
        print("  cap-lift ENABLED (rule_change_log written).", flush=True)
        return

    print("  SURVIVORSHIP WARNING: current-survivor universe; ~40% historical "
          "coverage. FAIL=strong negative, PASS=upper bound only.", flush=True)

    fm = pd.read_sql("SELECT rebal_date, symbol, fwd_ret_1m FROM features_monthly "
                     "WHERE top500=1 AND liquid=1 AND fwd_ret_1m IS NOT NULL "
                     "AND rebal_date>='2012-01-01'", conn)
    fund = load_asof_fundamentals(conn)
    syms = tuple(fund["symbol"].unique())
    px = pd.read_sql(f"SELECT symbol, date, close FROM stock_data_adj WHERE symbol IN "
                     f"({','.join('?'*len(syms))}) AND date>='2011-06-01'",
                     conn, params=syms)
    px = px.rename(columns={"date": "rebal_date"})
    fm = fm.merge(px, on=["rebal_date", "symbol"], how="left")

    # as-of join: latest filing with pit_date <= rebal_date (merge_asof per symbol)
    fm["rd_ts"] = pd.to_datetime(fm["rebal_date"])
    fund["pit_ts"] = pd.to_datetime(fund["pit_date"])
    fm = fm.sort_values("rd_ts")
    fund = fund.sort_values("pit_ts")
    merged = pd.merge_asof(
        fm, fund[["symbol", "pit_ts", "EPS in Rs", "margin", "growth3"]],
        left_on="rd_ts", right_on="pit_ts", by="symbol")
    fresh = (merged["rd_ts"] - merged["pit_ts"]).dt.days <= STALE_DAYS
    merged.loc[~fresh.fillna(False), ["EPS in Rs", "margin", "growth3"]] = np.nan

    merged["value_ep"] = np.where(merged["close"] > 0,
                                  merged["EPS in Rs"] / merged["close"], np.nan)
    merged["quality_margin"] = merged["margin"]
    merged["quality_growth"] = merged["growth3"].clip(-3, 3)

    run_at = datetime.now().isoformat()
    print(f"  panel: {len(merged):,} rows, months with >= {MIN_NAMES} named: ", end="", flush=True)
    ok_months = (merged.dropna(subset=["value_ep"]).groupby("rebal_date")["symbol"]
                 .count() >= MIN_NAMES).sum()
    print(f"{ok_months}", flush=True)

    results = {}
    for cand in CANDS:
        d = merged.dropna(subset=[cand, "fwd_ret_1m"])
        ics = (d.groupby("rebal_date")
                .apply(lambda g: g[cand].rank().corr(g["fwd_ret_1m"].rank())
                       if len(g) >= MIN_NAMES else np.nan)).dropna()
        n = len(ics)
        mean, sd = ics.mean(), ics.std()
        t = mean / (sd / np.sqrt(n)) if n > 1 and sd > 0 else 0.0
        h1, h2 = ics.iloc[: n // 2].mean(), ics.iloc[n // 2:].mean()
        # decile texture: top-decile minus universe monthly spread
        def dec_spread(g):
            if len(g) < MIN_NAMES:
                return np.nan
            top = g[g[cand] >= g[cand].quantile(0.9)]
            return top["fwd_ret_1m"].mean() - g["fwd_ret_1m"].mean()
        spread = d.groupby("rebal_date").apply(dec_spread).dropna()
        verdict = "scored" if (mean > 0 and t >= 3.0 and h2 > 0) else "context"
        results[cand] = (n, mean, t, h1, h2, verdict)
        conn.execute("INSERT OR REPLACE INTO signal_candidate_validation "
                     "VALUES (?,?,?,?,?,?,?,?,?)",
                     (run_at, cand, n, float(mean), float(t), float(h1), float(h2),
                      "+", verdict))
        print(f"  {cand:15} months={n:<4} IC={mean:+.4f} t={t:+.2f} "
              f"H1={h1:+.4f} H2={h2:+.4f} spread={spread.mean()*100:+.2f}%/mo "
              f"-> {verdict.upper()}", flush=True)
    conn.commit()

    passed = [c for c, r in results.items() if r[5] == "scored"]
    print(f"\n  PRE-REGISTERED VERDICT: "
          f"{'PASS (survivorship-caveated): ' + ', '.join(passed) + ' — cap lift requires human --approve-cap-lift' if passed else 'FAIL — cap stays (failed even with survivor tailwind)'}",
          flush=True)
    conn.close()


if __name__ == "__main__":
    main()
