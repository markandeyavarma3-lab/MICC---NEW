#!/usr/bin/env python3
"""compute_market_breadth.py — Daily market breadth computed from stock_data
(no scraping; full history). advances/declines, 52-week highs/lows, % above
50/200-DMA. Writes market_breadth. Idempotent.

Run:  py -3.14 market/compute_market_breadth.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")


def main():
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    print("Loading stock_data ...", flush=True)
    df = pd.read_sql("SELECT symbol,date,close FROM stock_data WHERE close>0", conn)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["symbol", "date"])
    g = df.groupby("symbol")["close"]
    print(f"Computing breadth over {len(df):,} rows ...", flush=True)
    df["prev"]  = g.shift(1)
    df["ma50"]  = g.transform(lambda x: x.rolling(50,  min_periods=20).mean())
    df["ma200"] = g.transform(lambda x: x.rolling(200, min_periods=50).mean())
    df["hi52"]  = g.transform(lambda x: x.rolling(252, min_periods=60).max())
    df["lo52"]  = g.transform(lambda x: x.rolling(252, min_periods=60).min())

    df["adv"]  = df["close"] > df["prev"]
    df["dec"]  = df["close"] < df["prev"]
    df["unch"] = df["close"] == df["prev"]
    df["nh"]   = df["close"] >= df["hi52"]
    df["nl"]   = df["close"] <= df["lo52"]
    df["a50"]  = df["close"] > df["ma50"]
    df["a200"] = df["close"] > df["ma200"]

    agg = df.groupby("date").agg(
        advances=("adv", "sum"), declines=("dec", "sum"), unchanged=("unch", "sum"),
        new_highs_52w=("nh", "sum"), new_lows_52w=("nl", "sum"),
        n50=("a50", "sum"), n200=("a200", "sum"), total=("close", "count"),
    ).reset_index()
    agg["ad_ratio"]         = agg["advances"] / agg["declines"].replace(0, 1)
    agg["pct_above_50dma"]  = 100 * agg["n50"] / agg["total"]
    agg["pct_above_200dma"] = 100 * agg["n200"] / agg["total"]
    agg["date"] = agg["date"].dt.strftime("%Y-%m-%d")

    conn.execute("""CREATE TABLE IF NOT EXISTS market_breadth (
        date TEXT PRIMARY KEY, advances INTEGER, declines INTEGER, unchanged INTEGER,
        ad_ratio REAL, new_highs_52w INTEGER, new_lows_52w INTEGER,
        pct_above_50dma REAL, pct_above_200dma REAL, total_traded INTEGER)""")
    rows = [(r.date, int(r.advances), int(r.declines), int(r.unchanged), float(r.ad_ratio),
             int(r.new_highs_52w), int(r.new_lows_52w),
             float(r.pct_above_50dma), float(r.pct_above_200dma), int(r.total))
            for r in agg.itertuples()]
    conn.executemany("INSERT OR REPLACE INTO market_breadth VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    mn, mx, n = conn.execute("SELECT MIN(date),MAX(date),COUNT(*) FROM market_breadth").fetchone()
    conn.close()
    print(f"DONE: market_breadth {n:,} days, {mn} -> {mx}", flush=True)


if __name__ == "__main__":
    main()
