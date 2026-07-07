#!/usr/bin/env python3
"""build_fundamentals_pit.py — PHASE 4c: point-in-time dating for fundamentals.

The fundamentals tables (quarterly_/annual_ income/balance/cashflow) are keyed by
`report_date` = PERIOD-END, with no original filing date — using them as-of period-end
is lookahead. This builds `fundamentals_pit`: for every (statement, symbol, period) it
attaches a conservative `pit_date` = period_end + statutory filing lag (SEBI: ~45 days
for quarterly results, ~60 days for annual). Backtests must filter `pit_date <= as_of`.

Where the `financial_results` table has a real broadcast/filing date for that symbol+period
(recent ~18 months), the actual date is used instead of the lag estimate.

Writes `fundamentals_pit(statement, symbol, period_type, report_date, pit_date, dated_by)`.
Run:  py -3.14 events/build_fundamentals_pit.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
LAG = {"quarterly": 45, "annual": 60}
TABLES = [("quarterly_income", "quarterly"), ("quarterly_balance", "quarterly"),
          ("quarterly_cashflow", "quarterly"), ("annual_income", "annual"),
          ("annual_balance", "annual"), ("annual_cashflow", "annual")]


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    # real filing dates from financial_results (symbol -> sorted broadcast dates)
    fr = pd.read_sql("SELECT symbol, broadcast_date FROM financial_results "
                     "WHERE broadcast_date IS NOT NULL", conn) \
        if "financial_results" in have else pd.DataFrame(columns=["symbol", "broadcast_date"])
    fr["broadcast_date"] = pd.to_datetime(fr["broadcast_date"], errors="coerce")
    fr = fr.dropna().sort_values("broadcast_date")

    rows = []
    for tbl, ptype in TABLES:
        if tbl not in have:
            continue
        d = pd.read_sql(f"SELECT DISTINCT symbol, report_date FROM {tbl} "
                        f"WHERE report_date IS NOT NULL", conn)
        d["rd"] = pd.to_datetime(d["report_date"], errors="coerce")
        d = d.dropna(subset=["rd"])
        d["pit_lag"] = d["rd"] + pd.to_timedelta(LAG[ptype], unit="D")
        for _, r in d.iterrows():
            # try a real filing date: earliest broadcast within [period_end, period_end+120d]
            real = None
            if len(fr):
                cand = fr[(fr["symbol"] == r["symbol"]) &
                          (fr["broadcast_date"] >= r["rd"]) &
                          (fr["broadcast_date"] <= r["rd"] + pd.Timedelta(days=120))]
                if len(cand):
                    real = cand["broadcast_date"].iloc[0]
            pit = real if real is not None else r["pit_lag"]
            rows.append((tbl, r["symbol"], ptype, r["report_date"],
                         str(pit.date()), "filing" if real is not None else "lag_estimate"))

    df = pd.DataFrame(rows, columns=["statement", "symbol", "period_type",
                                     "report_date", "pit_date", "dated_by"])
    conn.execute("DROP TABLE IF EXISTS fundamentals_pit")
    df.to_sql("fundamentals_pit", conn, if_exists="replace", index=False)
    conn.execute("CREATE INDEX idx_fpit ON fundamentals_pit(symbol, pit_date)")
    conn.commit()

    n_real = (df["dated_by"] == "filing").sum()
    print(f"fundamentals_pit: {len(df):,} rows "
          f"({n_real:,} real filing dates, {len(df)-n_real:,} lag estimates)", flush=True)
    print("  by statement:", flush=True)
    for s, g in df.groupby("statement"):
        print(f"    {s:20} {len(g):>6,}  ({(g['dated_by']=='filing').sum()} real-dated)", flush=True)
    print("  sample:", df.head(3).to_dict("records"), flush=True)
    conn.close()


if __name__ == "__main__":
    main()
