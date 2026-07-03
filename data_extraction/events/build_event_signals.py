#!/usr/bin/env python3
"""build_event_signals.py — Part 2 Module 2: evidence-graded event layer.

Populates `event_signals` from tables already in the warehouse. Every event type
carries an `evidence_tier` that says how it may be consumed:
  scored   -> may feed the event_score pillar (only after its own walk-forward
              event study passes; see common/backtest_insider.py)
  context  -> display tag on idea cards, ZERO scoring weight
  risk     -> feeds the risk_penalty pillar as a flag

Builders and their honest data-reality grades:
  insider_cluster_buy  >=2 distinct promoters/directors/KMP buying >= MIN_VALUE
                       within a 20-trading-day window (SEBI filings 2016->now).
                       Tier decided by the event study (starts 'context').
  pledge_risk          Pledge Invoke / large new Pledge -> risk flag (volatility/
                       credit evidence; never positive alpha).
  pead_proxy           YoY net-income growth, cross-sectionally standardised at
                       the PIT filing date. Only ~5 quarters of local depth ->
                       'context' until >=12 quarters accumulate (true SUE needs
                       EPS_q-4 + 8-quarter std; the doc's 'scored' assumed depth
                       we do not have). Auto-upgradeable later.
  buyback_announce     corporate_announcements only spans ~1 month locally ->
                       'context'.
  index_inclusion      new NIFTY 50 membership intervals from the niftyindices
                       history (monthly granularity, announcement date unknown)
                       -> 'context'.

Idempotent: full rebuild per event_type. PIT: events dated by FILING/public date.
Run:  py -3.14 events/build_event_signals.py
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

DB_PATH = Path(r"D:\marketDB\db\market.db")

MIN_VALUE = 2_500_000        # INR 25L per insider buy to count toward a cluster
CLUSTER_WINDOW_D = 28        # calendar days (~20 trading days)
MIN_PERSONS = 2              # distinct buyers to call it a cluster
PLEDGE_MIN_VALUE = 10_000_000  # INR 1cr invoke/new pledge to flag

DDL = """CREATE TABLE IF NOT EXISTS event_signals (
    event_id INTEGER PRIMARY KEY,
    symbol TEXT, event_date TEXT,
    event_type TEXT,          -- insider_cluster_buy|pledge_risk|pead_proxy|buyback_announce|index_inclusion
    direction TEXT,           -- bullish|bearish|risk
    magnitude REAL,           -- type-specific (cluster value cr, z-score, ...)
    surprise_score REAL,      -- normalised 0..100 within type (NULL if n/a)
    decay_horizon_days INTEGER,
    evidence_tier TEXT,       -- scored|context|risk
    source_table TEXT, computed_at TEXT
)"""


def rebuild(conn, event_type, rows):
    conn.execute("DELETE FROM event_signals WHERE event_type=?", (event_type,))
    conn.executemany(
        "INSERT INTO event_signals (symbol,event_date,event_type,direction,magnitude,"
        "surprise_score,decay_horizon_days,evidence_tier,source_table,computed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    print(f"  {event_type:20} {len(rows):>6,} events", flush=True)


def insider_clusters(conn, now):
    df = pd.read_sql(
        "SELECT symbol, filing_date, name, value FROM insider_trading "
        "WHERE transaction_type='Buy' AND value>=? AND filing_date>='2016-01-01' "
        "AND category IN ('Promoters','Promoter Group','Director','Key Managerial Personnel') "
        "ORDER BY symbol, filing_date", conn, params=(MIN_VALUE,))
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    rows = []
    for sym, g in df.groupby("symbol"):
        g = g.sort_values("filing_date")
        last_event = None
        for i in range(len(g)):
            t0 = g["filing_date"].iloc[i]
            win = g[(g["filing_date"] >= t0 - pd.Timedelta(days=CLUSTER_WINDOW_D))
                    & (g["filing_date"] <= t0)]
            if win["name"].nunique() >= MIN_PERSONS:
                d = t0.strftime("%Y-%m-%d")
                # one event per symbol per window (don't refire daily inside a cluster)
                if last_event and (t0 - last_event).days <= CLUSTER_WINDOW_D:
                    continue
                last_event = t0
                val_cr = win["value"].sum() / 1e7
                rows.append((sym, d, "insider_cluster_buy", "bullish", round(val_cr, 2),
                             None, 63, "context", "insider_trading", now))
    return rows


def pledge_risk(conn, now):
    df = pd.read_sql(
        "SELECT symbol, filing_date, transaction_type, value FROM insider_trading "
        "WHERE transaction_type IN ('Pledge','Pledge Invoke') AND value>=? "
        "AND filing_date>='2016-01-01'", conn, params=(PLEDGE_MIN_VALUE,))
    rows = [(r.symbol, r.filing_date, "pledge_risk", "risk",
             round(r.value / 1e7, 2), None, 126, "risk", "insider_trading", now)
            for r in df.itertuples()]
    return rows


def pead_proxy(conn, now):
    qi = pd.read_sql("SELECT symbol, report_date, data_json FROM quarterly_income", conn)
    pit = pd.read_sql("SELECT symbol, report_date, pit_date FROM fundamentals_pit "
                      "WHERE statement='quarterly_income' AND pit_date IS NOT NULL", conn)

    def net_income(js):
        try:
            d = json.loads(js)
            return d.get("Net Income From Continuing Operation Net Minority Interest") \
                or d.get("Net Income")
        except Exception:
            return None
    qi["ni"] = qi["data_json"].map(net_income)
    qi = qi.dropna(subset=["ni"])
    qi["rd"] = pd.to_datetime(qi["report_date"])
    rows = []
    ev = []
    for sym, g in qi.groupby("symbol"):
        g = g.sort_values("rd")
        for i in range(len(g)):
            prev = g[g["rd"] <= g["rd"].iloc[i] - pd.Timedelta(days=350)]
            if not len(prev):
                continue
            base = prev["ni"].iloc[-1]
            if base is None or abs(base) < 1e6:
                continue
            growth = (g["ni"].iloc[i] - base) / abs(base)
            ev.append((sym, g["report_date"].iloc[i], growth))
    if ev:
        e = pd.DataFrame(ev, columns=["symbol", "report_date", "growth"])
        e = e.merge(pit, on=["symbol", "report_date"], how="inner")   # PIT date required
        # cross-sectional z within each fiscal quarter, winsorised
        e["z"] = e.groupby("report_date")["growth"].transform(
            lambda s: ((s - s.median()) / (s.std() or 1)).clip(-3, 3))
        e["pct"] = e.groupby("report_date")["z"].rank(pct=True) * 100
        rows = [(r.symbol, r.pit_date, "pead_proxy",
                 "bullish" if r.z > 0 else "bearish", round(float(r.z), 2),
                 round(float(r.pct), 1), 60, "context", "quarterly_income+fundamentals_pit", now)
                for r in e.itertuples()]
    return rows


def buyback_announce(conn, now):
    df = pd.read_sql("SELECT symbol, announcement_date FROM corporate_announcements "
                     "WHERE subject LIKE '%uyback%'", conn)
    return [(r.symbol, r.announcement_date, "buyback_announce", "bullish",
             None, None, 21, "context", "corporate_announcements", now)
            for r in df.itertuples()]


def index_inclusion(conn, now):
    df = pd.read_sql("SELECT symbol, effective_from FROM index_membership "
                     "WHERE index_name='NIFTY 50' AND method='niftyindices_official' "
                     "AND effective_from > '2008-01-31'", conn)
    return [(r.symbol, r.effective_from, "index_inclusion", "bullish",
             None, None, 60, "context", "index_membership", now)
            for r in df.itertuples()]


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    conn.execute(DDL)
    now = datetime.now().isoformat()

    rebuild(conn, "insider_cluster_buy", insider_clusters(conn, now))
    rebuild(conn, "pledge_risk", pledge_risk(conn, now))
    rebuild(conn, "pead_proxy", pead_proxy(conn, now))
    rebuild(conn, "buyback_announce", buyback_announce(conn, now))
    rebuild(conn, "index_inclusion", index_inclusion(conn, now))

    tot = conn.execute("SELECT COUNT(*) FROM event_signals").fetchone()[0]
    print(f"  TOTAL: {tot:,} events", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
