#!/usr/bin/env python3
"""build_fundamental_features.py — PHASE 5 prep: clean PIT fundamental factors.

Parses the JSON income/balance blobs into a tidy, point-in-time factor table the
strategy engine can join as-of. Uses ANNUAL statements (2021+) for a longer window
than the shallow quarterly (2024+). Each row carries the `pit_date` (when it became
knowable) from `fundamentals_pit`, so strategies see it only after filing.

Writes `fundamentals_features(symbol, report_date, pit_date, eps, net_income,
revenue, total_equity, roe)`.
Run:  py -3.14 events/build_fundamental_features.py
"""
import json
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")


def jget(blob, *keys):
    try:
        d = json.loads(blob)
    except Exception:
        return None
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")

    inc = pd.read_sql("SELECT symbol,report_date,data_json FROM annual_income", conn)
    bal = pd.read_sql("SELECT symbol,report_date,data_json FROM annual_balance", conn)
    pit = pd.read_sql("SELECT symbol,report_date,pit_date FROM fundamentals_pit "
                      "WHERE statement='annual_income'", conn)

    inc["eps"] = inc["data_json"].apply(lambda b: jget(b, "Diluted EPS", "Basic EPS"))
    inc["net_income"] = inc["data_json"].apply(lambda b: jget(b, "Net Income", "Net Income Common Stockholders"))
    inc["revenue"] = inc["data_json"].apply(lambda b: jget(b, "Total Revenue", "Operating Revenue"))
    bal["total_equity"] = bal["data_json"].apply(
        lambda b: jget(b, "Stockholders Equity", "Total Equity Gross Minority Interest",
                       "Common Stock Equity"))

    df = inc[["symbol", "report_date", "eps", "net_income", "revenue"]].merge(
        bal[["symbol", "report_date", "total_equity"]], on=["symbol", "report_date"], how="left")
    df = df.merge(pit, on=["symbol", "report_date"], how="left")
    df = df.dropna(subset=["pit_date"])
    df["roe"] = df["net_income"] / df["total_equity"].where(df["total_equity"] > 0)

    cols = ["symbol", "report_date", "pit_date", "eps", "net_income", "revenue", "total_equity", "roe"]
    conn.execute("DROP TABLE IF EXISTS fundamentals_features")
    df[cols].to_sql("fundamentals_features", conn, if_exists="replace", index=False)
    conn.execute("CREATE INDEX idx_ff ON fundamentals_features(symbol, pit_date)")
    conn.commit()

    n = len(df)
    neps = df["eps"].notna().sum()
    nroe = df["roe"].notna().sum()
    print(f"fundamentals_features: {n:,} rows ({df['symbol'].nunique():,} symbols, "
          f"{df['report_date'].min()} -> {df['report_date'].max()})", flush=True)
    print(f"  EPS present {neps:,} | ROE present {nroe:,}", flush=True)
    print("  sample:", df[df["eps"].notna()].head(3)[["symbol", "report_date", "pit_date", "eps", "roe"]]
          .to_dict("records"), flush=True)
    conn.close()


if __name__ == "__main__":
    main()
