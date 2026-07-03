#!/usr/bin/env python3
"""build_risk_state.py — Part 3 Module B: portfolio-level risk meta-engine.

Computes a daily risk state from the idea desk's OWN closed-trade equity curve
(R-based: each closed trade contributes realized_R x base risk budget) and the
current in-book exposure. Every rule is a hard threshold; all of it is
capital-preservation governance, explicitly NOT alpha (reducing size after
losses does not improve per-trade odds — it caps the tail).

Rules (from the Part 3 plan, practitioner-consensus defaults):
  drawdown brake   DD<10%: x1.00 | 10-15%: x0.75 | 15-22%: x0.50
                   | >22%: x0.25 + HALT new cards (protects the -30% tolerance)
  streak brake     3 consecutive closed losers -> x0.75 until the next winner
  combined mult    min(dd_mult, streak_mult); NEVER above 1.0
  regime throttle  4-vote gate risk-off -> max_new_cards halved (the gate itself
                   still owns liquidation; this only throttles new risk)
  concentration    sector shares of in-book notional + avg 60d pairwise corr of
                   holdings; corr>0.6 -> corr_throttle flag (halves max_new_cards)

Consumers: ideas/build_bands.py multiplies RISK_BUDGET by risk_budget_mult;
ideas/build_idea_cards.py enforces HALT (no in_book cards while halted).
Confidence-scaled sizing (fractional-Kelly-lite) is deliberately NOT enabled:
equal-risk stays the default until confidence calibration is proven (doc B).

Idempotent: rebuilds today's row (and backfills the full history of the curve).
Run:  py -3.14 common/build_risk_state.py [--selftest]
"""
import json
import sqlite3
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from backtest_momentum import DB_PATH

BASE_RISK = 10_000.0
DD_STEPS = [(0.10, 1.00), (0.15, 0.75), (0.22, 0.50), (9.99, 0.25)]
STREAK_N, STREAK_MULT = 3, 0.75
CORR_THRESHOLD = 0.6
BASE_MAX_NEW_CARDS = 50

DDL = """CREATE TABLE IF NOT EXISTS risk_state_daily (
    as_of_date TEXT PRIMARY KEY,
    equity REAL, high_water_mark REAL, drawdown_pct REAL,
    consec_losses INTEGER,
    dd_mult REAL, streak_mult REAL, risk_budget_mult REAL,
    halt_new_cards INTEGER,
    max_new_cards INTEGER, open_positions INTEGER,
    sector_concentration_json TEXT, avg_pairwise_corr REAL,
    regime_votes INTEGER, notes TEXT
)"""


def dd_multiplier(dd):
    for lim, m in DD_STEPS:
        if dd < lim:
            return m
    return DD_STEPS[-1][1]


def equity_curve(conn):
    """R-based desk equity from closed mirror trades, ordered by exit date."""
    t = pd.read_sql(
        "SELECT t.exit_date, t.entry_price, t.stop, t.realized_return FROM trade t "
        "WHERE t.exit_price IS NOT NULL AND t.realized_return IS NOT NULL "
        "AND t.entry_price>0 AND t.stop>0 AND t.exit_date IS NOT NULL "
        "ORDER BY t.exit_date, t.trade_id", conn)
    t["r_mult"] = t["realized_return"] / ((t["entry_price"] - t["stop"]) / t["entry_price"])
    t["pnl"] = t["r_mult"] * BASE_RISK
    return t


def streak_from(seq):
    s = 0
    for r in reversed(seq):
        if r <= 0:
            s += 1
        else:
            break
    return s


def compute_state(pnl_series, r_seq):
    equity = float(pnl_series.sum())
    curve = pnl_series.cumsum()
    hwm = float(max(curve.max(), 0.0))
    dd = (hwm - float(curve.iloc[-1])) / (abs(hwm) + BASE_RISK * 100) if len(curve) else 0.0
    # DD measured against HWM on a notional base of 100 x base risk (the rupee
    # risk the desk would deploy at full budget) so early tiny curves don't
    # trigger the brake spuriously.
    consec = streak_from(r_seq)
    dm = dd_multiplier(dd)
    sm = STREAK_MULT if consec >= STREAK_N else 1.0
    mult = min(dm, sm, 1.0)
    halt = 1 if dd >= 0.22 else 0
    return equity, hwm, dd, consec, dm, sm, mult, halt


def selftest():
    """Pin-to-pin threshold transitions on synthetic curves."""
    ok = True
    ok &= dd_multiplier(0.05) == 1.0
    ok &= dd_multiplier(0.12) == 0.75
    ok &= dd_multiplier(0.18) == 0.50
    ok &= dd_multiplier(0.30) == 0.25
    ok &= streak_from([1, -1, -1, -1]) == 3
    ok &= streak_from([-1, 1]) == 0
    ok &= streak_from([]) == 0
    # combined mult never exceeds 1 and takes the harsher brake
    _, _, _, _, dm, sm, mult, halt = compute_state(
        pd.Series([-2500.0] * 40), [-1] * 40)
    ok &= mult == min(dm, sm) <= 0.75 and halt in (0, 1)
    print(f"  selftest: {'PASS' if ok else 'FAIL'}", flush=True)
    return ok


def main():
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute(DDL)

    t = equity_curve(conn)
    today = datetime.now().strftime("%Y-%m-%d")
    if not len(t):
        print("  no closed trades; neutral state", flush=True)
        equity = hwm = dd = consec = 0
        dm = sm = mult = 1.0
        halt = 0
    else:
        equity, hwm, dd, consec, dm, sm, mult, halt = compute_state(
            t["pnl"], t["r_mult"].tolist())

    # regime votes (validated 4-vote gate) for the throttle
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "ideas"))
    from scoring import regime_votes
    votes = regime_votes(conn, today)
    max_new = BASE_MAX_NEW_CARDS if votes >= 2 else BASE_MAX_NEW_CARDS // 2

    # in-book concentration + pairwise correlation
    book = pd.read_sql("SELECT symbol, sector, notional FROM idea_card "
                       "WHERE in_book=1 AND card_date=(SELECT MAX(card_date) FROM idea_card)",
                       conn)
    conc = {}
    corr = None
    if len(book):
        tot = book["notional"].sum()
        conc = {s: round(v / tot, 3) for s, v in
                book.groupby("sector")["notional"].sum().sort_values(ascending=False).items()}
        syms = tuple(book["symbol"])
        px = pd.read_sql(f"SELECT symbol,date,close FROM stock_data_adj WHERE symbol IN "
                         f"({','.join('?'*len(syms))}) AND date>=date('now','-120 day')",
                         conn, params=syms)
        wide = px.pivot_table(index="date", columns="symbol", values="close")
        rets = wide.pct_change(fill_method=None).tail(60)
        cm = rets.corr().to_numpy()
        corr = float((cm.sum() - np.trace(cm)) / (cm.shape[0] * (cm.shape[0] - 1))) \
            if cm.shape[0] > 1 else None
        if corr is not None and corr > CORR_THRESHOLD:
            max_new = max_new // 2

    conn.execute("INSERT OR REPLACE INTO risk_state_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (today, round(equity, 2), round(hwm, 2), round(dd, 4), consec,
                  dm, sm, mult, halt, max_new, len(book),
                  json.dumps(conc), None if corr is None else round(corr, 3),
                  votes, "R-based desk curve; governance not alpha"))
    conn.commit()
    print(f"  {today}: equity Rs {equity:,.0f} (cum R-pnl) | DD {dd*100:.1f}% | "
          f"streak {consec} | mult {mult} | halt {halt} | max_new {max_new} | "
          f"corr {corr if corr is None else round(corr,2)} | votes {votes}/4", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
