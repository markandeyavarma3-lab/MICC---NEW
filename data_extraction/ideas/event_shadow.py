#!/usr/bin/env python3
"""event_shadow.py — Part 3 Module D(a): shadow log for event-born theses.

Every scored/context bullish event is logged as a WOULD-BE standalone idea
(entry = first close after the event, EOD-honest) and its forward returns are
filled in at 21/63/126 trading days as data arrives. NO live cards originate
from events yet.

Pre-registered promotion criteria (doc D(a)): an event type may originate live
cards only after >=12 months of shadow history AND >=30 filled instances AND
hit-rate/expectancy beating the momentum baseline (49% hit) by a pre-set margin
— evaluated with the same walk-forward discipline as any signal, and sized 0.5x
if ever promoted. Expected per the India evidence: PEAD and insider clusters
promotable someday; buybacks likely fail (edge is pre-announcement).

Idempotent: inserts new events once; refreshes unfilled forward returns each run.
Run:  py -3.14 ideas/event_shadow.py
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
HORIZONS = (21, 63, 126)
SHADOW_TYPES = ("insider_cluster_buy", "pead_proxy", "buyback_announce", "index_inclusion")
START = "2024-01-01"          # shadow window start (recent regime, forward-looking log)

DDL = """CREATE TABLE IF NOT EXISTS event_shadow_thesis (
    shadow_id INTEGER PRIMARY KEY,
    symbol TEXT, event_date TEXT, event_type TEXT, direction TEXT,
    entry_date TEXT, entry_price REAL,
    fwd_21 REAL, fwd_63 REAL, fwd_126 REAL,
    filled_21 INTEGER DEFAULT 0, filled_63 INTEGER DEFAULT 0, filled_126 INTEGER DEFAULT 0,
    created_at TEXT,
    UNIQUE (symbol, event_date, event_type)
)"""


def main():
    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA busy_timeout=180000")
    conn.execute(DDL)
    now = datetime.now().isoformat()

    # 1) register new shadow instances (bullish events only)
    ins = conn.execute(
        "INSERT OR IGNORE INTO event_shadow_thesis (symbol,event_date,event_type,"
        "direction,created_at) "
        "SELECT symbol, event_date, event_type, direction, ? FROM event_signals "
        "WHERE event_type IN ({}) AND direction='bullish' AND event_date>=?"
        .format(",".join("?" * len(SHADOW_TYPES))), (now, *SHADOW_TYPES, START)).rowcount
    conn.commit()

    # 2) fill entries + forward returns where price history allows
    todo = pd.read_sql("SELECT shadow_id, symbol, event_date, entry_price, "
                       "filled_21, filled_63, filled_126 FROM event_shadow_thesis "
                       "WHERE filled_126=0", conn)
    if len(todo):
        syms = tuple(todo["symbol"].unique())
        px = pd.read_sql("SELECT symbol, date, close FROM stock_data_adj WHERE symbol IN "
                         f"({','.join('?'*len(syms))}) AND date>=date(?, '-5 day') "
                         "ORDER BY symbol, date", conn, params=(*syms, START))
        series = {s: (g["date"].to_numpy(), g["close"].to_numpy(dtype=float))
                  for s, g in px.groupby("symbol")}
        filled = 0
        for r in todo.itertuples():
            sv = series.get(r.symbol)
            if sv is None:
                continue
            d, c = sv
            i = np.searchsorted(d, r.event_date, side="right")   # first close AFTER event
            if i >= len(d) or c[i] <= 0:
                continue
            entry_price, entry_date = float(c[i]), str(d[i])
            upd = {"entry_price": entry_price, "entry_date": entry_date}
            for h in HORIZONS:
                if getattr(r, f"filled_{h}") == 0 and i + h < len(d):
                    upd[f"fwd_{h}"] = round(float(c[i + h] / c[i] - 1), 5)
                    upd[f"filled_{h}"] = 1
            sets = ",".join(f"{k}=?" for k in upd)
            conn.execute(f"UPDATE event_shadow_thesis SET {sets} WHERE shadow_id=?",
                         (*upd.values(), r.shadow_id))
            filled += 1
        conn.commit()

    # 3) promotion scoreboard (report-only; promotion needs the pre-registered gate)
    print(f"  new shadow instances: {ins}", flush=True)
    for et, n, n63, hit, avg in conn.execute(
            "SELECT event_type, COUNT(*), SUM(filled_63), "
            "AVG(CASE WHEN filled_63=1 AND fwd_63>0 THEN 1.0 WHEN filled_63=1 THEN 0 END), "
            "AVG(CASE WHEN filled_63=1 THEN fwd_63 END) FROM event_shadow_thesis "
            "GROUP BY event_type"):
        hit_s = "n/a" if hit is None else f"{hit*100:.0f}%"
        avg_s = "n/a" if avg is None else f"{avg*100:+.1f}%"
        gate = "" if (n63 or 0) >= 30 else f"  [needs >=30 filled, has {n63 or 0}]"
        print(f"  {et:20} n={n:<4} filled63={n63 or 0:<4} hit {hit_s:>4}  "
              f"avg63 {avg_s}{gate}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
