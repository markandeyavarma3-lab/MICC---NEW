#!/usr/bin/env python3
"""build_adjusted_prices.py — PHASE 1 enabler.

Materializes `stock_data_adj`: corporate-action back-adjusted OHLCV so that
momentum / breakout / event signals are not poisoned by split/bonus price cliffs.

Adjustment convention (back-adjustment): prices ON or AFTER the most recent
ex-date are left unchanged; every earlier price is multiplied by the cumulative
product of the factors of all ex-dates strictly after it. On the ex-date itself
the NSE bhavcopy close already reflects the action, so that event's own factor
is NOT applied to the ex-date row (only to rows before it).

Factors:
  SPLIT  'a:b'  (face value a -> b)            factor = b / a
  BONUS  'X:Y'  (X new shares for every Y held) factor = Y / (X + Y)

Dividends (price-only momentum does not need them) and RIGHTS (need the
subscription price, not stored) are intentionally NOT adjusted in v1 -- see
README "Phase 1" for the documented limitation.

Output table `stock_data_adj`:
  symbol, date, open, high, low, close, volume   <- all back-adjusted
  adj_factor                                     <- multiplier applied to prices
  (raw price = adjusted / adj_factor ; raw volume = adjusted * adj_factor)

Idempotent: rebuilds the table from scratch each run.

Run:  py -3.14 common/build_adjusted_prices.py
      py -3.14 common/build_adjusted_prices.py --validate   (only re-run checks)
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\marketDB\db\market.db")


def parse_factor(action_type, ratio):
    """Return the price multiplier for an ex-date, or None if not adjustable."""
    if not ratio or ":" not in str(ratio):
        return None
    try:
        a_str, b_str = str(ratio).split(":")[:2]
        a, b = float(a_str), float(b_str)
    except (ValueError, TypeError):
        return None
    if a <= 0 or b <= 0:
        return None
    if action_type == "SPLIT":
        return b / a                # face value a -> b ; price scales by b/a
    if action_type == "BONUS":
        return b / (a + b)          # a new per b held ; price scales by b/(a+b)
    return None


def load_events(conn):
    df = conn.execute(
        "SELECT symbol, date, action_type, ratio FROM corporate_actions "
        "WHERE action_type IN ('SPLIT','BONUS')"
    ).fetchall()
    rows = []
    for sym, dt, at, ratio in df:
        f = parse_factor(at, ratio)
        if f is not None and abs(f - 1.0) > 1e-9:
            rows.append((sym, dt, f))
    ev = pd.DataFrame(rows, columns=["symbol", "date", "factor"])
    # If multiple events share an ex-date for a symbol, combine multiplicatively
    ev = ev.groupby(["symbol", "date"], as_index=False)["factor"].prod()
    return ev


def back_adjust_symbol(dates, closes, events, stats):
    """dates/closes: this symbol's ascending trade dates + raw closes.
    events: DataFrame(date, factor). Returns adj_factor per trade date =
    product of *verified* factors with ex_date > trade_date.

    A factor is applied only if the raw close actually shows the cliff at the
    ex-date (jump closer to `factor` than to 1.0 in log space). This skips names
    whose source data is already corporate-action adjusted -- applying the factor
    there would manufacture a fake cliff (see DBEIL)."""
    n = len(dates)
    if events.empty:
        return np.ones(n)
    kept_dates, kept_fac = [], []
    for d, f in zip(events["date"].to_numpy(), events["factor"].to_numpy()):
        pos = np.searchsorted(dates, d, side="left")   # first row with date >= ex-date
        if pos == 0 or pos >= n:
            stats["unverifiable"] += 1
            continue
        p_before, p_after = closes[pos - 1], closes[pos]
        if not (p_before > 0 and p_after > 0):
            stats["unverifiable"] += 1
            continue
        observed = p_after / p_before
        if abs(np.log(observed) - np.log(f)) < abs(np.log(observed)):  # vs log(1)=0
            kept_dates.append(d); kept_fac.append(f)
            stats["applied"] += 1
        else:
            stats["skipped_already_adj"] += 1
    if not kept_dates:
        return np.ones(n)
    order = np.argsort(kept_dates)
    ev_dates = np.array(kept_dates)[order]
    ev_fac = np.array(kept_fac)[order]
    suffix = np.ones(len(ev_fac) + 1)
    for i in range(len(ev_fac) - 1, -1, -1):
        suffix[i] = suffix[i + 1] * ev_fac[i]
    j = np.searchsorted(ev_dates, dates, side="right")  # events strictly after each date
    return suffix[j]


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")

    if "--validate" not in sys.argv:
        print("Loading corporate actions (SPLIT/BONUS) ...", flush=True)
        events = load_events(conn)
        print(f"  {len(events):,} adjustable ex-dates across "
              f"{events['symbol'].nunique():,} symbols", flush=True)

        print("Loading stock_data ...", flush=True)
        df = pd.read_sql(
            "SELECT symbol, date, open, high, low, close, volume FROM stock_data",
            conn)
        print(f"  {len(df):,} rows, {df['symbol'].nunique():,} symbols", flush=True)

        ev_by_sym = {s: g[["date", "factor"]] for s, g in events.groupby("symbol")}

        print("Computing back-adjustment factors ...", flush=True)
        df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
        all_dates = df["date"].to_numpy()           # hoist once (not per-symbol)
        all_close = df["close"].to_numpy()
        factors = np.ones(len(df))
        stats = {"applied": 0, "skipped_already_adj": 0, "unverifiable": 0}
        for sym, idx in df.groupby("symbol").indices.items():
            ev = ev_by_sym.get(sym)
            if ev is None or ev.empty:
                continue
            factors[idx] = back_adjust_symbol(all_dates[idx], all_close[idx], ev, stats)
        print(f"  events applied={stats['applied']:,}  "
              f"skipped(already-adjusted)={stats['skipped_already_adj']:,}  "
              f"unverifiable={stats['unverifiable']:,}", flush=True)

        df["adj_factor"] = factors
        for col in ("open", "high", "low", "close"):
            df[col] = df[col] * df["adj_factor"]
        # keep traded value comparable: shares scale by 1/factor
        df["volume"] = df["volume"] / df["adj_factor"]

        print(f"Writing stock_data_adj ({len(df):,} rows) ...", flush=True)
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA journal_mode=MEMORY")
        conn.execute("DROP TABLE IF EXISTS stock_data_adj")
        conn.execute("""CREATE TABLE stock_data_adj (
            symbol TEXT, date TEXT, open REAL, high REAL, low REAL,
            close REAL, volume REAL, adj_factor REAL)""")
        cols = ["symbol", "date", "open", "high", "low", "close", "volume", "adj_factor"]
        conn.executemany(
            "INSERT INTO stock_data_adj VALUES (?,?,?,?,?,?,?,?)",
            df[cols].itertuples(index=False, name=None))
        conn.execute(
            "CREATE INDEX idx_sda_symdate ON stock_data_adj(symbol,date)")
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM stock_data_adj").fetchone()[0]
        nadj = conn.execute(
            "SELECT COUNT(*) FROM stock_data_adj WHERE ABS(adj_factor-1)>1e-9").fetchone()[0]
        print(f"DONE: stock_data_adj {n:,} rows ({nadj:,} actually adjusted)", flush=True)

    validate(conn)
    conn.close()


def validate(conn):
    """Confirm the raw price cliff exists and the adjusted series removes it."""
    print("\n=== VALIDATION (raw cliff vs adjusted continuity) ===", flush=True)
    checks = conn.execute(
        "SELECT symbol, date, action_type, ratio FROM corporate_actions "
        "WHERE action_type IN ('SPLIT','BONUS') AND date < date('now') "
        "ORDER BY date DESC LIMIT 200").fetchall()
    shown = 0
    for sym, exdate, at, ratio in checks:
        f = parse_factor(at, ratio)
        if f is None:
            continue
        raw = conn.execute(
            "SELECT date, close FROM stock_data WHERE symbol=? AND date<? "
            "ORDER BY date DESC LIMIT 1", (sym, exdate)).fetchone()
        rawon = conn.execute(
            "SELECT date, close FROM stock_data WHERE symbol=? AND date>=? "
            "ORDER BY date ASC LIMIT 1", (sym, exdate)).fetchone()
        adjb = conn.execute(
            "SELECT date, close FROM stock_data_adj WHERE symbol=? AND date<? "
            "ORDER BY date DESC LIMIT 1", (sym, exdate)).fetchone()
        adjon = conn.execute(
            "SELECT date, close FROM stock_data_adj WHERE symbol=? AND date>=? "
            "ORDER BY date ASC LIMIT 1", (sym, exdate)).fetchone()
        if not (raw and rawon and adjb and adjon):
            continue
        raw_jump = rawon[1] / raw[1] if raw[1] else 0
        adj_jump = adjon[1] / adjb[1] if adjb[1] else 0
        print(f"  {sym:12} {at:6} {ratio:6} ex={exdate}  "
              f"raw {raw[1]:>9.2f}->{rawon[1]:<9.2f} (x{raw_jump:.3f})  "
              f"adj {adjb[1]:>9.2f}->{adjon[1]:<9.2f} (x{adj_jump:.3f})  "
              f"[expect raw~x{f:.3f}, adj~x1]", flush=True)
        shown += 1
        if shown >= 12:
            break


if __name__ == "__main__":
    main()
