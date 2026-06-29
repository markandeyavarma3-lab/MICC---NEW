#!/usr/bin/env python3
"""fetch_annual_financials.py — Annual income / balance / cashflow statements per
symbol from yfinance (complements the quarterly_* tables). JSON per fiscal year.
Universe = tradable_eq_stocks. Idempotent. Slow (per-symbol) — run in background.

Run:  py -3.14 events/fetch_annual_financials.py
"""
import sqlite3, json, time
from pathlib import Path
from datetime import datetime

import pandas as pd
import yfinance as yf

DB_PATH = Path(r"D:\marketDB\db\market.db")


def ensure(conn):
    for t in ("annual_income", "annual_balance", "annual_cashflow"):
        conn.execute(f"""CREATE TABLE IF NOT EXISTS {t} (
            symbol TEXT, report_date TEXT, data_json TEXT, last_updated TEXT,
            PRIMARY KEY(symbol, report_date))""")
    conn.commit()


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    ensure(conn)
    syms = [r[0] for r in conn.execute("SELECT symbol FROM tradable_eq_stocks ORDER BY symbol")]
    now = datetime.now().isoformat()
    done = tot = 0

    for i, sym in enumerate(syms):
        try:
            tk = yf.Ticker(sym + ".NS")
            for stmt, table in ((tk.income_stmt, "annual_income"),
                                (tk.balance_sheet, "annual_balance"),
                                (tk.cashflow, "annual_cashflow")):
                if stmt is None or stmt.empty:
                    continue
                rows = []
                for col in stmt.columns:
                    rd = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)[:10]
                    d = {str(k): (None if pd.isna(v) else float(v)) for k, v in stmt[col].items()}
                    rows.append((sym, rd, json.dumps(d), now))
                if rows:
                    conn.executemany(
                        f"INSERT OR REPLACE INTO {table} (symbol,report_date,data_json,last_updated) "
                        f"VALUES (?,?,?,?)", rows)
                    tot += len(rows)
            conn.commit()
            done += 1
        except Exception:
            pass
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(syms)} | {done} symbols, {tot} statement-years | last {sym}", flush=True)
        time.sleep(0.3)

    for t in ("annual_income", "annual_balance", "annual_cashflow"):
        n, ns = conn.execute(f"SELECT COUNT(*),COUNT(DISTINCT symbol) FROM {t}").fetchone()
        print(f"  {t}: {n:,} rows, {ns:,} symbols", flush=True)
    conn.close()
    print("DONE: annual financials", flush=True)


if __name__ == "__main__":
    main()
