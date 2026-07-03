#!/usr/bin/env python3
"""calibrate_exits.py — Part 3 Module C: MFE/MAE exit calibration from MICC's own
540+ closed trades.

Diagnoses the placeholder bands (34% stop-hit rate is the classic tight-volatility-
stop-whipsaws-momentum symptom) and tests exit variants on the ACTUAL historical
price paths of our own trades:

  current        stop/target as originally set, 21td time expiry (baseline)
  wide_1.25x     stop distance x1.25, target = 2x new stop distance
  wide_1.5x      stop distance x1.5,  target = 2x new stop distance
  wide_2x        stop distance x2.0,  target = 2x new stop distance
  trail_atr3     no fixed target; trailing stop = highest close - 3*ATR14(entry)
  time_only      no stop/target; exit at horizon close (control)

Pre-registered acceptance gate (doc Module C): a variant replaces the current
bands ONLY if it beats the current expectancy (in R) on BOTH the train window
(first 70% by entry date) AND the held-out last 30%, with MFE capture >= 0.60.
Otherwise the current bands stay and the verdict is recorded. Whipsaw diagnostic:
% of stopped trades that then hit the ORIGINAL target within the horizon.

All simulation is EOD-honest: stop fires if day-low <= level, target if day-high
>= level; if both hit the same day the STOP is assumed first (conservative).
Results -> `exit_calibration`; adopted changes -> `rule_change_log`.

Run:  py -3.14 common/calibrate_exits.py
"""
import json
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd

from backtest_momentum import DB_PATH

HORIZON_TD = 21
TRAIN_FRAC = 0.70
R_MULT = 2.0
VARIANTS = ["current", "wide_1.25x", "wide_1.5x", "wide_2x", "trail_atr3", "time_only"]

DDL = ["""CREATE TABLE IF NOT EXISTS exit_calibration (
    run_at TEXT, variant TEXT, segment TEXT,
    n_train INTEGER, n_test INTEGER,
    exp_r_train REAL, exp_r_test REAL,
    hit_rate_test REAL, stop_rate_test REAL,
    mfe_capture_test REAL, verdict TEXT,
    PRIMARY KEY (run_at, variant, segment))""",
       """CREATE TABLE IF NOT EXISTS rule_change_log (
    change_id INTEGER PRIMARY KEY,
    change_date TEXT, component TEXT,
    description TEXT, evidence_ref TEXT, approved_by TEXT)"""]


def load_trades(conn):
    t = pd.read_sql(
        "SELECT t.thesis_id, h.symbol, t.entry_date, t.entry_price, t.stop, t.target "
        "FROM trade t JOIN thesis h ON t.thesis_id=h.thesis_id "
        "WHERE h.narrative='backfill:recommendations' AND t.exit_price IS NOT NULL "
        "AND t.entry_price>0 AND t.stop>0 AND t.target>0 ORDER BY t.entry_date", conn)
    return t


def load_paths(conn, symbols):
    qm = ",".join("?" * len(symbols))
    px = pd.read_sql(f"SELECT symbol, date, open, high, low, close FROM stock_data_adj "
                     f"WHERE symbol IN ({qm}) ORDER BY symbol, date", conn,
                     params=tuple(symbols))
    return {s: g.reset_index(drop=True) for s, g in px.groupby("symbol")}


def atr14_at(g, i):
    """ATR-14 ending at bar i (trailing only)."""
    if i < 15:
        return None
    h, l, c = (g["high"].to_numpy(), g["low"].to_numpy(), g["close"].to_numpy())
    trs = [max(h[j] - l[j], abs(h[j] - c[j-1]), abs(l[j] - c[j-1]))
           for j in range(i - 13, i + 1)]
    return float(np.mean(trs))


def simulate(g, i0, entry, stop, target, variant, atr):
    """Walk the path from bar i0+... to horizon under a variant. Returns
    (ret, outcome, mfe, mae) with mfe/mae as fractional moves from entry."""
    n = len(g)
    hi, lo, cl = g["high"].to_numpy(), g["low"].to_numpy(), g["close"].to_numpy()
    end = min(i0 + HORIZON_TD, n - 1)
    mfe = mae = 0.0
    trail_peak = entry
    s, t = stop, target
    for i in range(i0, end + 1):
        mfe = max(mfe, hi[i] / entry - 1)
        mae = min(mae, lo[i] / entry - 1)
        if variant == "time_only":
            continue
        if variant == "trail_atr3":
            trail_peak = max(trail_peak, cl[i])
            s = max(s, trail_peak - 3 * (atr or (entry - stop)))
            if lo[i] <= s:
                return s / entry - 1, "stop", mfe, mae
            continue
        if lo[i] <= s:                       # conservative: stop before target
            return s / entry - 1, "stop", mfe, mae
        if hi[i] >= t:
            return t / entry - 1, "target", mfe, mae
    ret = cl[end] / entry - 1
    return ret, "expired", mfe, mae


def variant_levels(entry, stop, variant):
    d = entry - stop
    if variant == "wide_1.25x":
        d *= 1.25
    elif variant == "wide_1.5x":
        d *= 1.5
    elif variant == "wide_2x":
        d *= 2.0
    return entry - d, entry + R_MULT * d, d


def main():
    import sys
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    for d in DDL:
        conn.execute(d)
    # --auto (pipeline mode): quarterly cadence — self-skip if last run < 80 days ago
    if "--auto" in sys.argv:
        last = conn.execute("SELECT MAX(run_at) FROM exit_calibration").fetchone()[0]
        if last and (datetime.now() - datetime.fromisoformat(last)).days < 80:
            print(f"  quarterly gate: last run {last[:10]}, skipping (auto mode)", flush=True)
            conn.close()
            return

    trades = load_trades(conn)
    paths = load_paths(conn, trades["symbol"].unique().tolist())
    print(f"  closed trades: {len(trades)} across {trades['symbol'].nunique()} symbols", flush=True)

    rows = []
    whip_stopped = whip_reversed = 0
    for tr in trades.itertuples():
        g = paths.get(tr.symbol)
        if g is None:
            continue
        idx = g.index[g["date"] > tr.entry_date]
        if not len(idx):
            continue
        i0 = idx[0]                                   # first bar AFTER signal date
        atr = atr14_at(g, i0 - 1)
        base_d = tr.entry_price - tr.stop
        if base_d <= 0:
            continue
        rec = {"entry_date": tr.entry_date}
        for v in VARIANTS:
            s, t, d = variant_levels(tr.entry_price, tr.stop, v)
            ret, oc, mfe, mae = simulate(g, i0, tr.entry_price, s, t, v, atr)
            # (R-multiple, outcome, MFE frac, MAE frac, realized frac return)
            rec[v] = (ret / (d / tr.entry_price), oc, mfe, mae, ret)
        rows.append(rec)
        # whipsaw diagnostic on the CURRENT variant
        r, oc, mfe, _, _ = rec["current"]
        if oc == "stop":
            whip_stopped += 1
            if mfe >= (tr.target / tr.entry_price - 1):
                whip_reversed += 1

    df = pd.DataFrame(rows).sort_values("entry_date").reset_index(drop=True)
    cut = int(len(df) * TRAIN_FRAC)
    run_at = datetime.now().isoformat()
    print(f"  simulated {len(df)} trades | train {cut} / test {len(df)-cut}", flush=True)
    print(f"  whipsaw: {whip_stopped} stopped, {whip_reversed} then hit original target "
          f"({whip_reversed/max(whip_stopped,1)*100:.0f}%)", flush=True)

    stats = {}
    for v in VARIANTS:
        def agg(part):
            r = part[v].map(lambda x: x[0])
            oc = part[v].map(lambda x: x[1])
            # MFE capture: realized FRACTIONAL return / MFE frac, winners with real MFE
            caps = [x[4] / x[2] for x in part[v] if x[2] > 0.005 and x[4] > 0]
            return (r.mean(), (r > 0).mean(), (oc == "stop").mean(),
                    float(np.median(caps)) if caps else np.nan)
        tr_m = agg(df.iloc[:cut])
        te_m = agg(df.iloc[cut:])
        stats[v] = (tr_m, te_m)
        print(f"  {v:11} train ExpR {tr_m[0]:+.3f} | test ExpR {te_m[0]:+.3f}  "
              f"hit {te_m[1]*100:.0f}%  stop {te_m[2]*100:.0f}%  MFEcap {te_m[3]:.2f}", flush=True)

    base_tr, base_te = stats["current"][0][0], stats["current"][1][0]
    winner, best_gain = "current", 0.0
    for v in VARIANTS[1:]:
        tr_m, te_m = stats[v]
        if (tr_m[0] > base_tr and te_m[0] > base_te and te_m[3] >= 0.60
                and te_m[0] - base_te > best_gain):
            winner, best_gain = v, te_m[0] - base_te

    conn.execute("DELETE FROM exit_calibration")
    for v in VARIANTS:
        tr_m, te_m = stats[v]
        verdict = "ADOPT" if v == winner and winner != "current" else \
                  ("KEEP" if v == "current" and winner == "current" else "reject")
        conn.execute("INSERT OR REPLACE INTO exit_calibration VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (run_at, v, "swing_21d", cut, len(df) - cut,
                      round(float(tr_m[0]), 4), round(float(te_m[0]), 4),
                      round(float(te_m[1]), 3), round(float(te_m[2]), 3),
                      round(float(te_m[3]), 3), verdict))
    if winner != "current":
        conn.execute("INSERT INTO rule_change_log (change_date,component,description,"
                     "evidence_ref,approved_by) VALUES (?,?,?,?,?)",
                     (run_at, "atr", f"exit variant '{winner}' beats current on train+test "
                      f"(test ExpR +{best_gain:.3f}R); pending human approval before bands change",
                      "exit_calibration", "PENDING"))
    conn.commit(); conn.close()
    print(f"\n  PRE-REGISTERED VERDICT: {'ADOPT ' + winner + ' (pending approval)' if winner != 'current' else 'KEEP current bands (no variant beat train+test+MFEcap gate)'}", flush=True)


if __name__ == "__main__":
    main()
