#!/usr/bin/env python3
"""
phase2_greeks_calculator.py – Compute Greeks & Gamma Exposure for index options.
Run daily after `daily_update.py` completes.
"""

import sqlite3
import logging
import math
from pathlib import Path
from datetime import datetime, timedelta
from scipy.stats import norm
import pandas as pd
import numpy as np

DB_PATH = Path(r"D:\marketDB\db\market.db")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\greeks_gex.log")
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("greeks")

# Constants (adjustable)
RISK_FREE_RATE = 0.065     # 6.5% – approx Indian risk‑free rate
DIVIDEND_YIELD = 0.012     # 1.2% – Nifty dividend yield

def black_scholes_greeks(S, K, T, r, q, sigma, option_type):
    """Return dict of delta, gamma, theta, vega, rho for European option."""
    if T <= 0:
        return {'delta':0, 'gamma':0, 'theta':0, 'vega':0, 'rho':0}
    d1 = (math.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
    d2 = d1 - sigma*math.sqrt(T)
    if option_type.upper() == 'CE':
        delta = math.exp(-q*T) * norm.cdf(d1)
        theta = (-math.exp(-q*T)*S*norm.pdf(d1)*sigma/(2*math.sqrt(T))
                 - r*K*math.exp(-r*T)*norm.cdf(d2)
                 + q*S*math.exp(-q*T)*norm.cdf(d1)) / 365
        rho = K*T*math.exp(-r*T)*norm.cdf(d2) / 100
    else:  # PE
        delta = -math.exp(-q*T)*norm.cdf(-d1)
        theta = (-math.exp(-q*T)*S*norm.pdf(d1)*sigma/(2*math.sqrt(T))
                 + r*K*math.exp(-r*T)*norm.cdf(-d2)
                 - q*S*math.exp(-q*T)*norm.cdf(-d1)) / 365
        rho = -K*T*math.exp(-r*T)*norm.cdf(-d2) / 100
    gamma = math.exp(-q*T) * norm.pdf(d1) / (S*sigma*math.sqrt(T))
    vega = S*math.exp(-q*T)*norm.pdf(d1)*math.sqrt(T) / 100
    return {'delta':delta, 'gamma':gamma, 'theta':theta, 'vega':vega, 'rho':rho}

def create_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS option_greeks_raw (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            expiry TEXT NOT NULL,
            strike REAL,
            option_type TEXT,
            underlying_price REAL,
            iv REAL,
            delta REAL,
            gamma REAL,
            theta REAL,
            vega REAL,
            rho REAL,
            UNIQUE(date, symbol, expiry, strike, option_type)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gamma_exposure_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            expiry TEXT NOT NULL,
            strike REAL,
            option_type TEXT,
            gamma_exposure REAL,
            open_interest INTEGER,
            UNIQUE(date, symbol, expiry, strike, option_type)
        )
    """)
    conn.commit()
    log.info("Greeks tables ready")

def get_underlying_close(conn, date_str, symbol):
    """Map symbol NIFTY/BANKNIFTY to indices_data name."""
    idx_name = 'NIFTY 50' if symbol.upper() == 'NIFTY' else 'NIFTY BANK'
    row = conn.execute(
        "SELECT close FROM indices_data WHERE name=? AND date=?",
        (idx_name, date_str)
    ).fetchone()
    return row[0] if row else None

def get_days_to_expiry(expiry_str, date_str):
    if not expiry_str or not str(expiry_str).strip():
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        exp = datetime.strptime(str(expiry_str).strip(), "%Y-%m-%d")
    except ValueError:
        return None
    return max((exp - dt).days / 365.0, 0.0001)

def fetch_options_for_date(conn, date_str):
    """Get all index option contracts for a given date."""
    sql = """
        SELECT symbol, expiry, strike, option_typ, close, open_int
        FROM fo_data
        WHERE date=? AND instrument IN ('OPTIDX','IDO') AND symbol IN ('NIFTY','BANKNIFTY')
          AND close IS NOT NULL
    """
    df = pd.read_sql(sql, conn, params=[date_str])
    if df.empty:
        return df
    df.rename(columns={'open_int': 'open_interest'}, inplace=True)
    return df

def compute_greeks_for_date(conn, date_str):
    df = fetch_options_for_date(conn, date_str)
    if df.empty:
        log.info(f"No option data for {date_str}")
        return 0

    rows = []
    gex_rows = []
    for _, row in df.iterrows():
        sym = row['symbol']
        expiry = row['expiry']
        strike = row['strike']
        opt_type = row['option_typ']
        oi = row['open_interest']
        underlying = get_underlying_close(conn, date_str, sym)
        if underlying is None:
            continue
        T = get_days_to_expiry(expiry, date_str)
        if T is None:   # skip contracts with missing/invalid expiry
            continue
        iv = 0.20  # placeholder – later compute real IV
        greeks = black_scholes_greeks(underlying, strike, T, RISK_FREE_RATE, DIVIDEND_YIELD, iv, opt_type)
        rows.append((
            date_str, sym, expiry, strike, opt_type,
            underlying, iv,
            greeks['delta'], greeks['gamma'], greeks['theta'],
            greeks['vega'], greeks['rho']
        ))
        gex = greeks['gamma'] * underlying * oi
        gex_rows.append((date_str, sym, expiry, strike, opt_type, gex, oi))

    if rows:
        conn.executemany("""
            INSERT OR REPLACE INTO option_greeks_raw
            (date, symbol, expiry, strike, option_type, underlying_price, iv,
             delta, gamma, theta, vega, rho)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        conn.executemany("""
            INSERT OR REPLACE INTO gamma_exposure_daily
            (date, symbol, expiry, strike, option_type, gamma_exposure, open_interest)
            VALUES (?,?,?,?,?,?,?)
        """, gex_rows)
        conn.commit()
        log.info(f"Computed Greeks for {date_str}: {len(rows)} contracts")
        return len(rows)
    return 0

def get_dates_with_options(conn, start_date=None, end_date=None):
    """Return distinct dates in fo_data that have index options."""
    sql = """
        SELECT DISTINCT date FROM fo_data
        WHERE instrument IN ('OPTIDX','IDO') AND symbol IN ('NIFTY','BANKNIFTY')
    """
    params = []
    if start_date:
        sql += " AND date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND date <= ?"
        params.append(end_date)
    df = pd.read_sql(sql, conn, params=params)
    return sorted(df['date'].tolist())

def backfill_greeks(conn, start_date="2024-01-01"):
    dates = get_dates_with_options(conn, start_date=start_date)
    if not dates:
        log.info("No dates with options data found.")
        return
    log.info(f"Found {len(dates)} dates with options data from {dates[0]} to {dates[-1]}")
    total = 0
    for dt in dates:
        cnt = conn.execute("SELECT COUNT(*) FROM option_greeks_raw WHERE date=?", (dt,)).fetchone()[0]
        if cnt == 0:
            total += compute_greeks_for_date(conn, dt)
    log.info(f"Backfill complete. Processed {total} contract-days.")

def incremental_greeks(conn, days=7):
    end = datetime.now() - timedelta(days=1)
    start = end - timedelta(days=days)
    dates = get_dates_with_options(conn, start_date=start.strftime("%Y-%m-%d"), end_date=end.strftime("%Y-%m-%d"))
    total = 0
    for dt in dates:
        cnt = conn.execute("SELECT COUNT(*) FROM option_greeks_raw WHERE date=?", (dt,)).fetchone()[0]
        if cnt == 0:
            total += compute_greeks_for_date(conn, dt)
    log.info(f"Incremental update complete. Processed {total} contract-days.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true", help="Backfill all historical dates")
    parser.add_argument("--start", default="2024-01-01", help="Start date for backfill (YYYY-MM-DD)")
    parser.add_argument("--daily", action="store_true", help="Run incremental (last 7 days)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout=60000")
    create_tables(conn)

    if args.backfill:
        log.info("Starting full backfill of Greeks...")
        backfill_greeks(conn, args.start)
    else:
        log.info("Running incremental Greeks update (last 7 days)...")
        incremental_greeks(conn)

    conn.close()
    log.info("Done.")