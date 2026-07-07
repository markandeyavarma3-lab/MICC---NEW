#!/usr/bin/env python3
"""compute_max_pain.py — Daily max-pain strike for index options (NIFTY, BANKNIFTY,
FINNIFTY) front expiry, computed from fo_data. Max pain = strike that minimizes
total option-writer payout (where most OI expires worthless). Idempotent.

Run:  py -3.14 market/compute_max_pain.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
SYMBOLS = ("NIFTY", "BANKNIFTY", "FINNIFTY")


def max_pain(ce, pe):
    strikes = np.array(sorted(set(ce.index) | set(pe.index)), dtype=float)
    if len(strikes) < 3:
        return None
    ce_arr = np.array([ce.get(k, 0) for k in strikes], dtype=float)
    pe_arr = np.array([pe.get(k, 0) for k in strikes], dtype=float)
    S = strikes[:, None]
    K = strikes[None, :]
    call_pain = (ce_arr[None, :] * np.maximum(0.0, S - K)).sum(axis=1)
    put_pain = (pe_arr[None, :] * np.maximum(0.0, K - S)).sum(axis=1)
    total = call_pain + put_pain
    return float(strikes[int(total.argmin())])


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    conn.execute("""CREATE TABLE IF NOT EXISTS options_max_pain (
        date TEXT, symbol TEXT, expiry TEXT, max_pain_strike REAL,
        PRIMARY KEY(date, symbol))""")
    conn.commit()

    ph = ",".join("?" * len(SYMBOLS))
    print("Loading index options from fo_data ...", flush=True)
    df = pd.read_sql(
        f"SELECT date,symbol,expiry,strike,option_typ,open_int FROM fo_data "
        f"WHERE symbol IN ({ph}) AND option_typ IN ('CE','PE') AND open_int IS NOT NULL",
        conn, params=SYMBOLS)
    print(f"{len(df):,} option rows", flush=True)

    rows = []
    for (dt, sym), g in df.groupby(["date", "symbol"]):
        exps = sorted(e for e in g["expiry"].dropna().unique() if e and e >= dt)
        if not exps:
            exps = sorted(g["expiry"].dropna().unique())
        if not exps:
            continue
        chain = g[g["expiry"] == exps[0]]
        ce = chain[chain.option_typ == "CE"].groupby("strike")["open_int"].sum()
        pe = chain[chain.option_typ == "PE"].groupby("strike")["open_int"].sum()
        mp = max_pain(ce, pe)
        if mp is not None:
            rows.append((dt, sym, exps[0], mp))

    if rows:
        conn.executemany("INSERT OR REPLACE INTO options_max_pain VALUES (?,?,?,?)", rows)
        conn.commit()
    n, nd = conn.execute("SELECT COUNT(*),COUNT(DISTINCT date) FROM options_max_pain").fetchone()
    print(f"DONE: options_max_pain {n:,} rows, {nd:,} dates", flush=True)
    for sym in SYMBOLS:
        r = conn.execute("SELECT date,max_pain_strike FROM options_max_pain WHERE symbol=? ORDER BY date DESC LIMIT 1",
                         (sym,)).fetchone()
        if r:
            print(f"  latest {sym} max-pain:", r, flush=True)
    conn.close()


if __name__ == "__main__":
    main()
