#!/usr/bin/env python3
"""build_adjusted_prices_tr.py — PHASE 4a: total-return (dividend-adjusted) price series.

Extends the split/bonus-adjusted `stock_data_adj.close` into a TOTAL-RETURN series
(`stock_data_tr.close_tr`) by back-adjusting for cash dividends: on each dividend
ex-date the prior prices are scaled by (1 - dividend_yield), so a buy-and-hold series
captures dividend income. Enables dividend-yield / total-return strategies.

dividend yield at ex-date d = amount / raw_close(d-1).  tr_factor(date) = product of
(1 - yield) over all dividend ex-dates AFTER that date (back-adjustment, same convention
as splits). close_tr = adj_close * tr_factor.

Writes `stock_data_tr(symbol, date, close_tr, tr_factor)`. Idempotent.
Run:  py -3.14 common/build_adjusted_prices_tr.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
MAX_YIELD = 0.5          # guard against bad dividend/price data


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=MEMORY")

    print("Loading adjusted + raw prices + dividends ...", flush=True)
    adj = pd.read_sql("SELECT symbol,date,close FROM stock_data_adj", conn)
    raw = pd.read_sql("SELECT symbol,date,close AS rawclose FROM stock_data", conn)
    div = pd.read_sql("SELECT symbol,date,amount FROM corporate_actions "
                      "WHERE action_type='DIVIDEND' AND amount>0", conn)
    adj = adj.merge(raw, on=["symbol", "date"], how="left").sort_values(["symbol", "date"]).reset_index(drop=True)
    print(f"  {len(adj):,} rows; {len(div):,} dividend events", flush=True)

    div_by_sym = {s: g for s, g in div.groupby("symbol")}
    all_dates = adj["date"].to_numpy()
    all_raw = adj["rawclose"].to_numpy()
    tr_factor = np.ones(len(adj))
    applied = 0

    for sym, idx in adj.groupby("symbol").indices.items():
        ev = div_by_sym.get(sym)
        if ev is None:
            continue
        dates = all_dates[idx]
        rawc = all_raw[idx]
        ex_dates, factors = [], []
        for d, amt in zip(ev["date"].to_numpy(), ev["amount"].to_numpy()):
            pos = np.searchsorted(dates, d, side="left")   # first row with date >= ex
            if pos == 0 or pos > len(dates):
                continue
            p_prev = rawc[pos - 1]
            if not (p_prev > 0):
                continue
            y = min(amt / p_prev, MAX_YIELD)
            if y <= 0:
                continue
            ex_dates.append(d); factors.append(1.0 - y); applied += 1
        if not ex_dates:
            continue
        order = np.argsort(ex_dates)
        ed = np.array(ex_dates)[order]
        fac = np.array(factors)[order]
        suffix = np.ones(len(fac) + 1)
        for i in range(len(fac) - 1, -1, -1):
            suffix[i] = suffix[i + 1] * fac[i]
        j = np.searchsorted(ed, dates, side="right")       # divs strictly after each date
        tr_factor[idx] = suffix[j]

    adj["tr_factor"] = tr_factor
    adj["close_tr"] = adj["close"] * adj["tr_factor"]

    print(f"  {applied:,} dividend adjustments applied; writing stock_data_tr ...", flush=True)
    conn.execute("DROP TABLE IF EXISTS stock_data_tr")
    conn.execute("CREATE TABLE stock_data_tr (symbol TEXT, date TEXT, close_tr REAL, tr_factor REAL)")
    conn.executemany("INSERT INTO stock_data_tr VALUES (?,?,?,?)",
                     adj[["symbol", "date", "close_tr", "tr_factor"]].itertuples(index=False, name=None))
    conn.execute("CREATE INDEX idx_tr_symdate ON stock_data_tr(symbol,date)")
    conn.commit()

    # ---- validation: TR CAGR should exceed price CAGR by ~the dividend yield ----
    print("\n=== VALIDATION (TR vs price-only CAGR, long-history dividend payers) ===", flush=True)
    for sym in ("ITC", "HINDUNILVR", "COALINDIA", "INFY", "NTPC"):
        r = conn.execute(
            "SELECT a.date, a.close, t.close_tr FROM stock_data_adj a "
            "JOIN stock_data_tr t ON a.symbol=t.symbol AND a.date=t.date "
            "WHERE a.symbol=? ORDER BY a.date", (sym,)).fetchall()
        if len(r) < 500:
            continue
        yrs = len(r) / 252
        p_cagr = (r[-1][1] / r[0][1]) ** (1 / yrs) - 1
        t_cagr = (r[-1][2] / r[0][2]) ** (1 / yrs) - 1
        print(f"  {sym:12} price {p_cagr*100:5.1f}%  total-return {t_cagr*100:5.1f}%  "
              f"(+{(t_cagr-p_cagr)*100:.1f}% div/yr)", flush=True)
    conn.close()
    print("\n  Saved -> stock_data_tr (close_tr = total-return series).", flush=True)


if __name__ == "__main__":
    main()
