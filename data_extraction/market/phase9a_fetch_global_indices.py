# -*- coding: utf-8 -*-
"""
phase9a_fetch_global_indices.py
================================
Phase 9A — Step 2: Fetch global indices from yfinance and populate
global_indices_daily table.

Global universe fetched:
  Equity Indices:   SPX, NDX100, Nikkei225, DAX, HangSeng, FTSE100,
                    CAC40, Shanghai, Kospi, SGX Nifty (approx via SGD)
  Macro/Commodity:  VIX, DXY, Gold, CrudeWTI, BrentCrude
  Rates:            US10Y, US2Y, US10Y-2Y spread (computed)
  FX:               USDINR, EURUSD, USDJPY

First run: fetches full history (max available from yfinance).
Subsequent runs: fetches only missing dates (incremental).

Location: D:/MICC/data_extraction/phase9a_fetch_global_indices.py
Usage:
  py phase9a_fetch_global_indices.py           -- incremental (default)
  py phase9a_fetch_global_indices.py --full    -- full history refetch
  py phase9a_fetch_global_indices.py --verify  -- check row counts only
"""

import sqlite3
import sys
import time
import os
import warnings
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")

# SSL fix — same pattern as rest of MICC
try:
    import certifi
    os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
    os.environ["SSL_CERT_FILE"]      = certifi.where()
    os.environ["CURL_CA_BUNDLE"]     = certifi.where()
except ImportError:
    pass

import pandas as pd
import yfinance as yf

DB_PATH = Path(r"D:\marketDB\db\market.db")

# ── Global ticker universe ────────────────────────────────────────────────────
# Format: "MICC_SYMBOL": ("yfinance_ticker", "display_name", "category")
GLOBAL_TICKERS = {
    # ── Major Equity Indices ──────────────────────────────────────────────
    "SPX":          ("^GSPC",    "S&P 500",          "equity_index"),
    "NDX":          ("^NDX",     "Nasdaq 100",        "equity_index"),
    "DJIA":         ("^DJI",     "Dow Jones",         "equity_index"),
    "Nikkei225":    ("^N225",    "Nikkei 225",        "equity_index"),
    "DAX":          ("^GDAXI",   "DAX (Germany)",     "equity_index"),
    "HangSeng":     ("^HSI",     "Hang Seng",         "equity_index"),
    "FTSE100":      ("^FTSE",    "FTSE 100",          "equity_index"),
    "CAC40":        ("^FCHI",    "CAC 40 (France)",   "equity_index"),
    "Shanghai":     ("000001.SS","Shanghai Comp",     "equity_index"),
    "Kospi":        ("^KS11",    "KOSPI (Korea)",     "equity_index"),
    "ASX200":       ("^AXJO",    "ASX 200",           "equity_index"),
    "Taiwan":       ("^TWII",    "Taiwan Weighted",   "equity_index"),

    # ── Volatility ────────────────────────────────────────────────────────
    "VIX":          ("^VIX",     "CBOE VIX",          "volatility"),
    "IndiaVIX":     ("^INDIAVIX","India VIX",          "volatility"),

    # ── Commodities ───────────────────────────────────────────────────────
    "Gold":         ("GC=F",     "Gold Futures",      "commodity"),
    "Silver":       ("SI=F",     "Silver Futures",    "commodity"),
    "CrudeWTI":     ("CL=F",     "Crude Oil WTI",     "commodity"),
    "BrentCrude":   ("BZ=F",     "Brent Crude",       "commodity"),
    "NatGas":       ("NG=F",     "Natural Gas",       "commodity"),
    "Copper":       ("HG=F",     "Copper",            "commodity"),

    # ── Currencies / FX ──────────────────────────────────────────────────
    "DXY":          ("DX-Y.NYB", "USD Index (DXY)",   "fx"),
    "USDINR":       ("USDINR=X", "USD/INR",           "fx"),
    "EURUSD":       ("EURUSD=X", "EUR/USD",           "fx"),
    "USDJPY":       ("USDJPY=X", "USD/JPY",           "fx"),
    "GBPUSD":       ("GBPUSD=X", "GBP/USD",           "fx"),

    # ── US Treasuries / Rates ─────────────────────────────────────────────
    "US10Y":        ("^TNX",     "US 10Y Yield",      "rates"),
    "US2Y":         ("^IRX",     "US 2Y Yield (proxy)","rates"),
    "US30Y":        ("^TYX",     "US 30Y Yield",      "rates"),

    # ── Bitcoin (global risk-on barometer) ────────────────────────────────
    "Bitcoin":      ("BTC-USD",  "Bitcoin",           "crypto"),

    # ── Indian Indices (Tier A.A and A.B per spec) ────────────────────────
    # These give India-specific seasonality in global_indices_daily
    "NIFTY50":      ("^NSEI",      "Nifty 50",             "equity_index"),
    "NIFTYBANK":    ("^NSEBANK",   "Nifty Bank",           "equity_index"),
    "SENSEX":       ("^BSESN",     "Sensex (BSE)",         "equity_index"),
    "NIFTYIT":      ("^CNXIT",     "Nifty IT",             "equity_index"),
    "NIFTYMID100":  ("^NSEMDCP50", "Nifty Midcap 50",      "equity_index"),
    "EUROSTOXX50":  ("^STOXX50E",  "Euro Stoxx 50",        "equity_index"),
}


def log(msg: str, level: str = "INFO"):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  {msg}", flush=True)


def get_latest_date(conn: sqlite3.Connection, symbol: str) -> str | None:
    """Return latest date in global_indices_daily for this symbol."""
    row = conn.execute(
        "SELECT MAX(date) FROM global_indices_daily WHERE symbol = ?", (symbol,)
    ).fetchone()
    return row[0] if row and row[0] else None


def fetch_ticker(micc_sym: str, yf_ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    Download OHLCV from yfinance for a single ticker.
    Returns cleaned DataFrame with columns: date, open, high, low, close, volume
    Returns empty DataFrame on failure.
    """
    try:
        ticker = yf.Ticker(yf_ticker)
        df = ticker.history(start=start, end=end, auto_adjust=True)

        if df.empty:
            return pd.DataFrame()

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]

        # Date column — yfinance returns 'date' or 'datetime'
        date_col = "date" if "date" in df.columns else "datetime"
        if date_col not in df.columns:
            return pd.DataFrame()

        df["date"] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")

        # Standardise OHLCV
        for col in ["open", "high", "low", "close"]:
            if col not in df.columns:
                df[col] = None
        if "volume" not in df.columns:
            df["volume"] = 0

        # Compute daily pct_change
        df = df.sort_values("date").reset_index(drop=True)
        df["pct_change"] = (
            df["close"].pct_change() * 100
        ).round(4)

        df["symbol"] = micc_sym
        return df[["symbol", "date", "open", "high", "low", "close", "volume", "pct_change"]]

    except Exception as e:
        return pd.DataFrame()


def upsert_rows(conn: sqlite3.Connection, df: pd.DataFrame):
    """Insert-or-replace rows into global_indices_daily."""
    if df.empty:
        return 0

    rows = [
        (
            str(r["symbol"]),
            str(r["date"]),
            float(r["open"])   if r["open"]   == r["open"] else None,
            float(r["high"])   if r["high"]   == r["high"] else None,
            float(r["low"])    if r["low"]    == r["low"]  else None,
            float(r["close"])  if r["close"]  == r["close"] else None,
            float(r["volume"]) if r["volume"] == r["volume"] else 0.0,
            float(r["pct_change"]) if r["pct_change"] == r["pct_change"] else None,
        )
        for _, r in df.iterrows()
        if r["close"] == r["close"]   # skip NaN close
    ]

    conn.executemany("""
        INSERT OR REPLACE INTO global_indices_daily
            (symbol, date, open, high, low, close, volume, pct_change)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    return len(rows)


def run_full(conn: sqlite3.Connection):
    """Fetch full history for all tickers. Used on first run."""
    log("Mode: FULL HISTORY (this will take 3-5 minutes)", "WARN")
    start = "2000-01-01"
    end   = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    total = 0
    failed = []

    for i, (sym, (yf_sym, name, cat)) in enumerate(GLOBAL_TICKERS.items(), 1):
        log(f"[{i:2d}/{len(GLOBAL_TICKERS)}] {sym:15s} ({yf_sym}) ...")
        df = fetch_ticker(sym, yf_sym, start, end)
        if df.empty:
            log(f"  {sym}: no data returned", "WARN")
            failed.append(sym)
        else:
            n = upsert_rows(conn, df)
            total += n
            log(f"  {sym}: {n} rows inserted  ({df['date'].min()} .. {df['date'].max()})", "OK")

        # Small delay between yfinance calls to avoid rate limiting
        time.sleep(0.4)

    log(f"Full fetch complete: {total} total rows, {len(failed)} failed")
    if failed:
        log(f"Failed symbols: {', '.join(failed)}", "WARN")
    return total


def run_incremental(conn: sqlite3.Connection):
    """Fetch only new data since last stored date per ticker."""
    log("Mode: INCREMENTAL (default)")
    end   = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    total = 0
    up_to_date = 0
    failed = []

    for i, (sym, (yf_sym, name, cat)) in enumerate(GLOBAL_TICKERS.items(), 1):
        latest = get_latest_date(conn, sym)

        if latest:
            # Fetch from day after latest stored
            start_dt = datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)
            start    = start_dt.strftime("%Y-%m-%d")
        else:
            # First time for this symbol — get full history
            start = "2000-01-01"

        # Skip if already up to date (latest is today or yesterday)
        today_str = datetime.today().strftime("%Y-%m-%d")
        yesterday = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        if latest in (today_str, yesterday):
            up_to_date += 1
            continue

        log(f"[{i:2d}/{len(GLOBAL_TICKERS)}] {sym:15s}: fetching from {start}")
        df = fetch_ticker(sym, yf_sym, start, end)
        if df.empty:
            failed.append(sym)
        else:
            n = upsert_rows(conn, df)
            total += n
            log(f"  {sym}: +{n} rows", "OK")

        time.sleep(0.3)

    log(f"Incremental fetch: +{total} new rows | {up_to_date} symbols already current")
    if failed:
        log(f"Symbols with no new data: {', '.join(failed)}", "WARN")
    return total


def run_verify(conn: sqlite3.Connection):
    """Print row counts and date ranges per symbol."""
    print()
    print(f"{'Symbol':<18} {'Rows':>6}  {'First Date':<12}  {'Last Date':<12}  Category")
    print("-" * 70)

    rows = conn.execute("""
        SELECT g.symbol, COUNT(*) as n, MIN(g.date), MAX(g.date)
        FROM global_indices_daily g
        GROUP BY g.symbol
        ORDER BY g.symbol
    """).fetchall()

    for sym, n, first, last in rows:
        cat = GLOBAL_TICKERS.get(sym, ("", "", "unknown"))[2]
        print(f"{sym:<18} {n:>6}  {first:<12}  {last:<12}  {cat}")

    print()
    total = sum(r[1] for r in rows)
    log(f"Total: {len(rows)} symbols, {total} rows in global_indices_daily", "OK")


def main():
    full    = "--full"   in sys.argv
    verify  = "--verify" in sys.argv

    print()
    print("=" * 65)
    print("  MICC Phase 9A — Fetch Global Indices")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Tickers: {len(GLOBAL_TICKERS)}")
    print("=" * 65)
    print()

    if not DB_PATH.exists():
        log(f"DB not found: {DB_PATH}", "FAIL")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=180000")

    try:
        if verify:
            run_verify(conn)
        elif full:
            run_full(conn)
            print()
            run_verify(conn)
        else:
            run_incremental(conn)
            print()
            run_verify(conn)

        log("Phase 9A Step 2 COMPLETE", "OK")

    except KeyboardInterrupt:
        log("Interrupted by user", "WARN")
    except Exception as e:
        log(f"Fatal error: {e}", "FAIL")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()

    print()
    print("  Next step: py phase9b_build_window_stats.py")
    print()


if __name__ == "__main__":
    main()
