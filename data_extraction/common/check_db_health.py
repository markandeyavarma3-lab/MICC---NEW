# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
check_db_health.py – Full database freshness check (no false positives).
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")

# Known NSE holidays (same as daily_update)
NSE_HOLIDAYS = {
    "2026-01-15", "2026-01-26", "2026-03-03", "2026-03-26",
    "2026-03-31", "2026-04-03", "2026-04-14", "2026-05-01",
    "2026-05-28", "2026-06-26", "2026-09-14", "2026-10-02",
    "2026-10-20", "2026-11-10", "2026-11-24", "2026-12-25",
}

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def trading_days(start, end):
    d = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    dates = []
    while d <= e:
        if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in NSE_HOLIDAYS:
            dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return dates

def check_table(conn, table, date_col, name_col=None):
    """Return (count, latest_date) using the provided date column."""
    try:
        row = conn.execute(f"SELECT MAX({date_col}) FROM {table}").fetchone()
        latest = row[0] if row else None
        cnt = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return cnt, latest
    except:
        return 0, None

def main():
    conn = sqlite3.connect(DB_PATH)
    print("=" * 65)
    print("  MarketDB Health Check —", datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 65)

    # Expected last 10 trading days
    yesterday = datetime.now().date() - timedelta(days=1)
    expected_dates = trading_days(
        (yesterday - timedelta(days=21)).strftime("%Y-%m-%d"),
        yesterday.strftime("%Y-%m-%d")
    )[-10:]
    print(f"  Last 10 trading days: {', '.join(expected_dates[-3:])}...\n")

    # ── Table definitions (table_name, date_column, display_name) ──
    tables = [
        ("indices_data",            "date",                "Indices"),
        ("stock_data",              "date",                "Stocks (SQLite)"),
        ("fo_data",                 "date",                "F&O Bhavcopy"),
        ("fii_dii_data",            "date",                "FII/DII"),
        ("global_data",             "date",                "Global Macro"),
        ("us_macro_data",           "date",                "US Macro (FRED)"),
        ("world_bank_macro",        "date",                "India Macro (WB)"),
        ("india_macro_fred",        "date",                "India Macro (FRED)"),
        ("mf_nav_history",          "date",                "MF NAVs"),
        ("stock_fundamentals",      "last_updated",        "Fundamentals"),
        ("corporate_actions",       "date",                "Corporate Actions"),
        ("corporate_announcements", "announcement_date",   "Announcements"),
        ("insider_trading",         "filing_date",         "Insider Trading"),
        ("stock_delivery",          "date",                "Delivery %"),
        ("bulk_deals",              "deal_date",           "Bulk Deals"),
        ("block_deals",             "deal_date",           "Block Deals"),
        ("option_greeks_raw",       "date",                "Greeks (Raw)"),
        ("gamma_exposure_daily",    "date",                "Gamma Exposure"),
    ]

    for table, date_col, label in tables:
        cnt, latest = check_table(conn, table, date_col)
        print(f"  {label:<25} {cnt:>12,} rows   latest: {latest or 'N/A'}")

        # For tables with daily expectations (date‑based), check for missing days
        if date_col in ("date", "deal_date", "announcement_date", "filing_date"):
            if latest and latest < expected_dates[-1]:
                missing = [d for d in expected_dates if d > latest]
                print(f"    [WARN]  Missing {len(missing)} recent trading day(s): {', '.join(missing[-5:])}")
            elif latest is None and cnt == 0:
                print("    ℹ  Empty table")
            else:
                print("    [OK] Up to date")
        else:
            # For tables with last_updated – just note if they are empty or very old
            if cnt == 0:
                print("    ℹ  Empty table")
            elif latest:
                days_old = (datetime.now() - datetime.strptime(latest[:10], "%Y-%m-%d")).days
                if days_old > 7:
                    print(f"    [WARN]  Last updated {days_old} days ago")
                else:
                    print("    [OK] Recently updated")

    # ── Parquet stocks ──
    stocks_dir = Path("stocks/all")
    if stocks_dir.exists():
        n_syms = sum(1 for d in stocks_dir.iterdir() if d.is_dir() and any(d.glob("*.parquet")))
        print(f"\n  Stocks (Parquet)         {n_syms} symbols present")

    conn.close()
    print("=" * 65)

if __name__ == "__main__":
    main()