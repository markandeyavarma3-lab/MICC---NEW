#!/usr/bin/env python3
"""backtest_regime_spine.py — Part 2 Module 1 ship-gate: does the multi-axis
regime spine beat the incumbent 4-vote gate OUT-OF-SAMPLE?

Mirrors backtest_best.py exactly: same panel, same equal-weight + inverse-vol
books, same walk-forward threshold-selection machinery (48-month min train) —
the ONLY difference is the gating score:
  incumbent : 4-vote count (breadth, NIFTY>200DMA, SPX>200DMA, VIX<median),
              thresholds {1,2,3,4}
  challenger: regime_daily.regime_score (0..100, as-of month-end),
              thresholds {40,45,50,55,60}
Both are compared on the IDENTICAL intersection of OOS months.

Ship rule (doc Module 1): the spine feeds the regime_align pillar ONLY if its
OOS Sharpe on the primary (inverse-vol) book beats the incumbent's. Otherwise
the 4-vote gate stays and the extra axes are demoted to context. Verdict is
persisted to `spine_validation` — scoring.py reads it and falls back automatically.

Run:  py -3.14 common/backtest_regime_spine.py
"""
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd

from backtest_momentum import DB_PATH, N_DECILES, COST_PER_SIDE, load_panel, metrics
from backtest_hardening import book_returns
from backtest_execution import weighted_book
from backtest_best import regime_score, fmt

MIN_TRAIN = 48
INCUMBENT_CANDS = (1, 2, 3, 4)
SPINE_CANDS = (40, 45, 50, 55, 60)

DDL = """CREATE TABLE IF NOT EXISTS spine_validation (
    run_at TEXT, book TEXT, months INTEGER,
    sharpe_incumbent REAL, sharpe_spine REAL,
    maxdd_incumbent REAL, maxdd_spine REAL,
    shipped INTEGER,            -- 1 = spine feeds regime_align, 0 = 4-vote stays
    note TEXT,
    PRIMARY KEY (run_at, book)
)"""


def wf_gate_param(raw, score, dates, candidates):
    """Walk-forward threshold selection (same machinery as backtest_best.wf_gate,
    parameterised by candidate list)."""
    oos, chosen = {}, {}
    for i, R in enumerate(dates):
        if i < MIN_TRAIN or pd.isna(score.get(R, np.nan)):
            continue
        past = [d for d in dates[:i] if d in raw.index]
        best_t, best_s = candidates[0], -1e9
        for t in candidates:
            gp = pd.Series([raw[d] if score.get(d, 0) >= t else 0.0 for d in past],
                           index=past)
            m = metrics(gp)
            if m and m["Sharpe"] > best_s:
                best_s, best_t = m["Sharpe"], t
        chosen[R] = best_t
        oos[R] = raw[R] if score.get(R, 0) >= best_t else 0.0
    return pd.Series(oos), pd.Series(chosen)


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    conn.execute(DDL)
    print("Loading panel + books + both regime scores ...", flush=True)
    panel, rebals, breadth = load_panel(conn)
    aux = pd.read_sql("SELECT rebal_date,symbol,vol_3m,med_turnover FROM features_monthly", conn)
    panel = panel.merge(aux, on=["rebal_date", "symbol"], how="left").dropna(subset=["vol_3m"])

    score4, _ = regime_score(conn, rebals, breadth)          # incumbent 4-vote count

    spine = pd.read_sql("SELECT date,regime_score FROM regime_daily ORDER BY date", conn)
    sp = spine.set_index("date")["regime_score"].sort_index()
    spine_m = pd.Series({R: (sp[sp.index <= R].iloc[-1] if len(sp[sp.index <= R]) else np.nan)
                         for R in rebals})                   # as-of month-end, trailing only

    # books (identical to backtest_best)
    ew = book_returns(panel, rebals, {N_DECILES}, set(), COST_PER_SIDE, "decile")["long_net"]
    iv = weighted_book(panel, rebals, "invvol", COST_PER_SIDE)[0]["net"]

    run_at = datetime.now().isoformat()
    results = {}
    for name, raw in [("EW", ew), ("IV", iv)]:
        inc, _ = wf_gate_param(raw, score4, rebals, INCUMBENT_CANDS)
        spn, chosen = wf_gate_param(raw, spine_m, rebals, SPINE_CANDS)
        common = inc.index.intersection(spn.index)           # identical OOS months
        mi, ms = metrics(inc.reindex(common)), metrics(spn.reindex(common))
        results[name] = (mi, ms, len(common), chosen)
        print(f"\n=== {name} book, {len(common)} identical OOS months ===", flush=True)
        print(f"  incumbent 4-vote WF gate : {fmt(mi)}", flush=True)
        print(f"  regime-spine WF gate     : {fmt(ms)}", flush=True)

    mi, ms, n, chosen = results["IV"]
    shipped = 1 if ms["Sharpe"] > mi["Sharpe"] else 0
    note = (f"spine {'BEATS' if shipped else 'does NOT beat'} incumbent on IV book "
            f"({ms['Sharpe']:.2f} vs {mi['Sharpe']:.2f}); thresholds used: "
            f"{dict(chosen.value_counts().sort_index())}")
    conn.execute("DELETE FROM spine_validation")             # keep only latest verdict
    for name, (a, b, months, _) in results.items():
        conn.execute("INSERT OR REPLACE INTO spine_validation VALUES (?,?,?,?,?,?,?,?,?)",
                     (run_at, name, months, a["Sharpe"], b["Sharpe"],
                      a["MaxDD"], b["MaxDD"], shipped, note))
    conn.commit(); conn.close()

    print(f"\n=== VERDICT ===", flush=True)
    print(f"  {note}", flush=True)
    print(f"  -> {'SHIP: regime_align will read regime_daily' if shipped else 'NO-SHIP: 4-vote gate stays; spine axes = context only'}", flush=True)


if __name__ == "__main__":
    main()
