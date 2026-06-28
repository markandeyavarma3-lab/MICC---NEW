# -*- coding: utf-8 -*-
"""
fetch_phase2_data.py  —  MICC Data Extraction Phase 2
======================================================
Adds quality fundamentals, Google Trends, and historical options IV.

What this adds:
  1. Screener.in fundamentals (replaces unreliable yfinance for Indian stocks)
  2. Google Trends weekly interest per stock/sector (via pytrends)
  3. Historical options IV surface (NSE bhavcopy backfill 2018→now)

Install:
  pip install requests beautifulsoup4 pytrends --break-system-packages

Run:
  py D:\MICC\data_extraction\fetch_phase2_data.py              # all
  py D:\MICC\data_extraction\fetch_phase2_data.py --screener   # fundamentals only
  py D:\MICC\data_extraction\fetch_phase2_data.py --trends     # Google Trends only
  py D:\MICC\data_extraction\fetch_phase2_data.py --iv         # options IV backfill
  py D:\MICC\data_extraction\fetch_phase2_data.py --iv --from 2023-01-01  # partial
"""

import os, sys, sqlite3, time, json, argparse, re
import certifi
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import requests
import pandas as pd
from datetime import datetime, timedelta, date as _date
from pathlib import Path
from io import StringIO, BytesIO
import zipfile

DB_PATH = Path(r"D:\marketDB\db\market.db")
NOW     = datetime.now().isoformat()
TODAY   = datetime.now().strftime("%Y-%m-%d")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def conn():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c

def log(msg, level="INFO"):
    icon = {"OK":"✅","FAIL":"❌","WARN":"⚠️","INFO":"ℹ️"}.get(level,"ℹ️")
    print(f"  {icon}  {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SCREENER.IN FUNDAMENTALS
# ═══════════════════════════════════════════════════════════════════════════════

def create_screener_table(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS screener_fundamentals (
            symbol TEXT PRIMARY KEY,
            company_name TEXT,
            sector TEXT,
            market_cap_cr REAL,
            pe_ttm REAL,
            pb REAL,
            roce_pct REAL,
            roe_pct REAL,
            div_yield_pct REAL,
            debt_equity REAL,
            current_ratio REAL,
            sales_5yr_cagr REAL,
            profit_5yr_cagr REAL,
            promoter_holding_pct REAL,
            fii_holding_pct REAL,
            pledge_pct REAL,
            eps_ttm REAL,
            book_value REAL,
            face_value REAL,
            data_json TEXT,
            last_updated TEXT
        )
    """)
    c.commit()

def parse_screener_number(text):
    """Convert Screener text like '1,234.56' or '12.3%' to float."""
    if not text:
        return None
    text = str(text).replace(",","").replace("%","").replace("Cr","").strip()
    try:
        return float(text)
    except:
        return None

def fetch_screener_for_symbol(symbol, session):
    """
    Fetch fundamental data from screener.in for one symbol.
    URL pattern: https://www.screener.in/company/SYMBOL/consolidated/
    """
    for consolidated in ["consolidated", "standalone"]:
        url = f"https://www.screener.in/company/{symbol}/{consolidated}/"
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 404:
                continue
            if resp.status_code == 200:
                return resp.text, consolidated
        except Exception:
            pass
    return None, None

def parse_screener_html(html, symbol):
    """Parse Screener.in company page HTML."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None

    soup = BeautifulSoup(html, "html.parser")
    data = {"symbol": symbol}

    # Company name
    h1 = soup.find("h1", class_="margin-0")
    if h1:
        data["company_name"] = h1.get_text(strip=True)

    # Key ratios from the top section
    # Screener puts them in <li> items under company-ratios
    ratio_section = soup.find("ul", id="top-ratios")
    if ratio_section:
        for li in ratio_section.find_all("li"):
            name_el = li.find("span", class_="name")
            val_el  = li.find("span", class_="number") or li.find("span", class_="value")
            if name_el and val_el:
                name = name_el.get_text(strip=True).lower()
                val  = val_el.get_text(strip=True)
                num  = parse_screener_number(val)
                if "market cap" in name:
                    data["market_cap_cr"] = num
                elif name.strip() in ["p/e", "pe"]:
                    data["pe_ttm"] = num
                elif "p/b" in name or "price/book" in name:
                    data["pb"] = num
                elif "roce" in name:
                    data["roce_pct"] = num
                elif "roe" in name:
                    data["roe_pct"] = num
                elif "div yield" in name or "dividend yield" in name:
                    data["div_yield_pct"] = num
                elif "debt/equity" in name or "debt / equity" in name:
                    data["debt_equity"] = num

    # Shareholding from the shareholding section
    sh_section = soup.find("section", id="shareholding")
    if sh_section:
        # Latest promoter holding
        table = sh_section.find("table")
        if table:
            rows_data = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td","th"])]
                rows_data.append(cells)
            if rows_data:
                header = rows_data[0] if rows_data else []
                for row in rows_data[1:]:
                    if row and "promoter" in str(row[0]).lower():
                        try:
                            data["promoter_holding_pct"] = float(str(row[-1]).replace("%",""))
                        except:
                            pass
                    if row and ("fii" in str(row[0]).lower() or "foreign" in str(row[0]).lower()):
                        try:
                            data["fii_holding_pct"] = float(str(row[-1]).replace("%",""))
                        except:
                            pass

    # Store raw as JSON for future parsing
    data["data_json"] = json.dumps({k: v for k, v in data.items() if k != "symbol"})

    return data

def fetch_screener_fundamentals(max_symbols=500):
    """Fetch Screener.in data for top symbols by market cap."""
    log(f"Fetching Screener.in fundamentals (up to {max_symbols} symbols)...")

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log("pip install beautifulsoup4 lxml", "FAIL")
        return False

    c = conn()
    create_screener_table(c)

    # Get symbols sorted by market cap (or all from parquet universe)
    rows = c.execute("""
        SELECT sf.symbol FROM stock_fundamentals sf
        ORDER BY sf.marketCap DESC NULLS LAST
        LIMIT ?
    """, (max_symbols,)).fetchall()

    symbols = [r[0] for r in rows]
    if not symbols:
        rows = c.execute("""
            SELECT DISTINCT symbol FROM stock_data
            WHERE close IS NOT NULL
            ORDER BY symbol LIMIT ?
        """, (max_symbols,)).fetchall()
        symbols = [r[0] for r in rows]

    log(f"  Processing {len(symbols)} symbols...")

    session = requests.Session()
    session.headers.update(HEADERS)

    # Screener.in rate limit: ~1 req/sec is safe
    inserted = 0
    failed = 0

    for i, symbol in enumerate(symbols):
        try:
            # Check if already fetched recently (within 7 days)
            row = c.execute(
                "SELECT last_updated FROM screener_fundamentals WHERE symbol=?", (symbol,)
            ).fetchone()
            if row and row[0]:
                try:
                    last = datetime.fromisoformat(row[0])
                    if (datetime.now() - last).days < 7:
                        continue  # Skip if fresh
                except:
                    pass

            html, mode = fetch_screener_for_symbol(symbol, session)
            if not html:
                failed += 1
                time.sleep(0.5)
                continue

            data = parse_screener_html(html, symbol)
            if not data:
                failed += 1
                time.sleep(1)
                continue

            c.execute("""
                INSERT OR REPLACE INTO screener_fundamentals
                (symbol, company_name, sector, market_cap_cr, pe_ttm, pb,
                 roce_pct, roe_pct, div_yield_pct, debt_equity, current_ratio,
                 sales_5yr_cagr, profit_5yr_cagr, promoter_holding_pct,
                 fii_holding_pct, pledge_pct, eps_ttm, book_value,
                 face_value, data_json, last_updated)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                symbol,
                data.get("company_name"),
                data.get("sector"),
                data.get("market_cap_cr"),
                data.get("pe_ttm"),
                data.get("pb"),
                data.get("roce_pct"),
                data.get("roe_pct"),
                data.get("div_yield_pct"),
                data.get("debt_equity"),
                data.get("current_ratio"),
                data.get("sales_5yr_cagr"),
                data.get("profit_5yr_cagr"),
                data.get("promoter_holding_pct"),
                data.get("fii_holding_pct"),
                data.get("pledge_pct"),
                data.get("eps_ttm"),
                data.get("book_value"),
                data.get("face_value"),
                data.get("data_json"),
                NOW
            ))
            inserted += 1

            if inserted % 50 == 0:
                c.commit()
                log(f"  {i+1}/{len(symbols)} — {inserted} stored, {failed} failed", "INFO")

            time.sleep(1.2)  # Screener rate limit

        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                log("  Rate limited — sleeping 30s...", "WARN")
                time.sleep(30)
            failed += 1
            continue

    c.commit()
    c.close()
    log(f"Screener fundamentals: {inserted} symbols updated, {failed} failed", "OK")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 2. GOOGLE TRENDS — weekly interest per sector/stock
# ═══════════════════════════════════════════════════════════════════════════════

def create_trends_table(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS google_trends (
            query TEXT NOT NULL,
            symbol TEXT,
            date TEXT NOT NULL,
            interest_score INTEGER,
            yoy_change REAL,
            category TEXT,
            last_updated TEXT,
            PRIMARY KEY (query, date)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_gt_symbol ON google_trends(symbol, date)")
    c.commit()

def fetch_google_trends():
    """
    Fetch Google Trends weekly interest for key stocks and sectors.
    Uses pytrends — free, no API key.
    """
    log("Fetching Google Trends data...")

    try:
        from pytrends.request import TrendReq
    except ImportError:
        log("pip install pytrends", "FAIL")
        return False

    c = conn()
    create_trends_table(c)

    # Key queries — mix of stocks and sector themes
    STOCK_QUERIES = [
        ("RELIANCE share", "RELIANCE", "stock"),
        ("TCS share price", "TCS", "stock"),
        ("HDFC Bank share", "HDFCBANK", "stock"),
        ("Infosys share", "INFY", "stock"),
        ("Zomato share", "ZOMATO", "stock"),
        ("Adani share", "ADANIENT", "stock"),
        ("Nifty 50", "NIFTY50", "index"),
        ("NSE stock market", None, "market"),
        ("pharma stocks India", None, "sector"),
        ("banking stocks India", None, "sector"),
        ("IT stocks India", None, "sector"),
        ("stock market crash India", None, "sentiment"),
        ("best stocks to buy India", None, "sentiment"),
        ("NSE IPO", None, "ipo"),
    ]

    pytrends = TrendReq(hl="en-US", tz=330)  # IST = UTC+330min
    inserted = 0

    # Batch queries (pytrends handles 5 at a time)
    batch_size = 5
    for batch_start in range(0, len(STOCK_QUERIES), batch_size):
        batch = STOCK_QUERIES[batch_start:batch_start + batch_size]
        queries = [q[0] for q in batch]

        try:
            pytrends.build_payload(
                queries,
                cat=0,
                timeframe="today 12-m",
                geo="IN",  # India
                gprop=""
            )
            df = pytrends.interest_over_time()

            if df.empty:
                time.sleep(5)
                continue

            for i, (query, symbol, category) in enumerate(batch):
                if query not in df.columns:
                    continue
                series = df[query]

                # Compute YoY change (last week vs same week last year)
                yoy = None
                if len(series) >= 52:
                    last_val = series.iloc[-1]
                    year_ago = series.iloc[-52]
                    if year_ago > 0:
                        yoy = round((last_val / year_ago - 1) * 100, 1)

                for dt, val in series.items():
                    date_str = dt.strftime("%Y-%m-%d")
                    c.execute("""
                        INSERT OR REPLACE INTO google_trends
                        (query, symbol, date, interest_score, yoy_change, category, last_updated)
                        VALUES (?,?,?,?,?,?,?)
                    """, (query, symbol, date_str, int(val), yoy, category, NOW))
                    inserted += 1

            c.commit()
            log(f"  Batch {batch_start//batch_size + 1}: {len(queries)} queries done", "OK")
            time.sleep(3)  # pytrends rate limit

        except Exception as e:
            log(f"  Trends batch error: {e}", "WARN")
            time.sleep(10)
            continue

    c.close()
    log(f"Google Trends: {inserted} data points stored", "OK")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 4. HISTORICAL OPTIONS IV SURFACE BACKFILL
# ═══════════════════════════════════════════════════════════════════════════════

def create_iv_history_table(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS options_iv_history (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            expiry TEXT,
            atm_strike REAL,
            atm_iv_ce REAL,
            atm_iv_pe REAL,
            atm_iv_avg REAL,
            iv_rank_252d REAL,
            iv_percentile_252d REAL,
            pcr_oi REAL,
            total_ce_oi REAL,
            total_pe_oi REAL,
            last_updated TEXT,
            PRIMARY KEY (symbol, date, expiry)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_iv_sym_date ON options_iv_history(symbol, date)")
    c.commit()

def compute_iv_from_bhavcopy(df_fo, date_str, symbol):
    """
    Compute ATM IV from F&O bhavcopy data for one symbol/date.
    Uses Black-Scholes approximation.
    """
    try:
        import numpy as np
        from scipy.stats import norm
        HAS_SCIPY = True
    except ImportError:
        HAS_SCIPY = False
        import numpy as np

    # Filter for this symbol, options only, nearest expiry
    sym_df = df_fo[
        (df_fo["symbol"] == symbol) &
        (df_fo["instrument"].str.contains("OPT", na=False))
    ].copy()

    if sym_df.empty:
        return None

    # Get nearest expiry
    sym_df["expiry"] = pd.to_datetime(sym_df["expiry"], errors="coerce")
    sym_df = sym_df.dropna(subset=["expiry"])
    if sym_df.empty:
        return None

    today_dt = pd.to_datetime(date_str)
    sym_df = sym_df[sym_df["expiry"] >= today_dt]
    if sym_df.empty:
        return None

    nearest_expiry = sym_df["expiry"].min()
    exp_df = sym_df[sym_df["expiry"] == nearest_expiry].copy()

    # Get ATM strike (closest to current price using settle_pr as proxy for futures)
    fut_df = df_fo[
        (df_fo["symbol"] == symbol) &
        (df_fo["instrument"].str.contains("FUT", na=False)) &
        (pd.to_datetime(df_fo["expiry"], errors="coerce") == nearest_expiry)
    ]

    if not fut_df.empty:
        spot_proxy = float(fut_df["close"].iloc[0])
    else:
        close_vals = exp_df["close"].dropna()
        if close_vals.empty:
            return None
        spot_proxy = float(close_vals.median())

    # Find ATM strike
    strikes = exp_df["strike"].dropna().unique()
    if len(strikes) == 0:
        return None

    atm_strike = min(strikes, key=lambda s: abs(s - spot_proxy))

    # Get CE and PE at ATM
    ce = exp_df[(exp_df["strike"] == atm_strike) & (exp_df["option_typ"] == "CE")]
    pe = exp_df[(exp_df["strike"] == atm_strike) & (exp_df["option_typ"] == "PE")]

    atm_iv_ce = None
    atm_iv_pe = None

    # Simplified IV approximation: Brenner-Subrahmanyam formula
    # IV ≈ option_price / (spot × sqrt(T)) × sqrt(2π)
    try:
        T = max((nearest_expiry - today_dt).days / 365.0, 1/365)
        sqrt_T = T ** 0.5

        if not ce.empty and spot_proxy > 0 and sqrt_T > 0:
            ce_price = float(ce["close"].iloc[0])
            if ce_price > 0:
                atm_iv_ce = round((ce_price / (spot_proxy * sqrt_T)) * (2 * 3.14159) ** 0.5 * 100, 2)
                atm_iv_ce = min(atm_iv_ce, 200.0)  # cap at 200%

        if not pe.empty and spot_proxy > 0 and sqrt_T > 0:
            pe_price = float(pe["close"].iloc[0])
            if pe_price > 0:
                atm_iv_pe = round((pe_price / (spot_proxy * sqrt_T)) * (2 * 3.14159) ** 0.5 * 100, 2)
                atm_iv_pe = min(atm_iv_pe, 200.0)
    except Exception:
        pass

    # PCR
    total_ce_oi = float(exp_df[exp_df["option_typ"] == "CE"]["open_int"].sum())
    total_pe_oi = float(exp_df[exp_df["option_typ"] == "PE"]["open_int"].sum())
    pcr = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi > 0 else None

    atm_iv_avg = None
    if atm_iv_ce and atm_iv_pe:
        atm_iv_avg = round((atm_iv_ce + atm_iv_pe) / 2, 2)
    elif atm_iv_ce:
        atm_iv_avg = atm_iv_ce
    elif atm_iv_pe:
        atm_iv_avg = atm_iv_pe

    return {
        "expiry": nearest_expiry.strftime("%Y-%m-%d"),
        "atm_strike": atm_strike,
        "atm_iv_ce": atm_iv_ce,
        "atm_iv_pe": atm_iv_pe,
        "atm_iv_avg": atm_iv_avg,
        "pcr_oi": pcr,
        "total_ce_oi": total_ce_oi,
        "total_pe_oi": total_pe_oi,
    }

def fetch_iv_backfill(from_date="2020-01-01", symbols=None):
    """
    Backfill IV history from existing fo_data table.
    Uses already-stored F&O data — no new downloads needed!
    """
    log(f"Building options IV history from fo_data (from {from_date})...")

    c = conn()
    create_iv_history_table(c)

    # Default symbols: NIFTY + BANKNIFTY + top 20 by OI
    if symbols is None:
        rows = c.execute("""
            SELECT DISTINCT symbol FROM fo_data
            WHERE instrument LIKE '%OPT%'
            AND symbol IN ('NIFTY','BANKNIFTY','RELIANCE','TCS','HDFCBANK',
                           'INFY','ICICIBANK','AXISBANK','WIPRO','KOTAKBANK',
                           'TATAMOTORS','BAJFINANCE','HINDUNILVR','ITC',
                           'SBIN','ASIANPAINT','MARUTI','LT','ULTRACEMCO','TITAN')
            LIMIT 20
        """).fetchall()
        symbols = [r[0] for r in rows] if rows else ["NIFTY", "BANKNIFTY"]

    log(f"  Processing {len(symbols)} symbols...")

    # Get all unique dates in fo_data since from_date
    dates = c.execute("""
        SELECT DISTINCT date FROM fo_data
        WHERE date >= ? AND instrument LIKE '%OPT%'
        ORDER BY date
    """, (from_date,)).fetchall()
    dates = [r[0] for r in dates]

    log(f"  {len(dates)} trading dates to process")

    inserted = 0
    iv_history = {sym: [] for sym in symbols}

    for i, date_str in enumerate(dates):
        try:
            # Load F&O data for this date
            df = pd.read_sql_query(
                """SELECT symbol, instrument, expiry, strike, option_typ,
                          open, high, low, close, settle_pr, open_int,
                          chg_in_oi, contracts
                   FROM fo_data
                   WHERE date=? AND instrument LIKE '%OPT%' OR
                         (date=? AND instrument LIKE '%FUT%')""",
                sqlite3.connect(DB_PATH, timeout=30),
                params=(date_str, date_str)
            )

            if df.empty:
                continue

            df["strike"]   = pd.to_numeric(df["strike"], errors="coerce")
            df["open_int"] = pd.to_numeric(df["open_int"], errors="coerce").fillna(0)
            df["close"]    = pd.to_numeric(df["close"], errors="coerce")

            for symbol in symbols:
                result = compute_iv_from_bhavcopy(df, date_str, symbol)
                if not result:
                    continue

                iv_val = result["atm_iv_avg"]
                if iv_val:
                    iv_history[symbol].append(iv_val)

                # Compute IV rank (where is today vs last 252 values)
                iv_rank = None
                iv_pct  = None
                hist = iv_history[symbol]
                if len(hist) >= 20:
                    arr = hist[-252:]
                    iv_rank = round((iv_val - min(arr)) / (max(arr) - min(arr) + 1e-9) * 100, 1)
                    iv_pct  = round(sum(1 for x in arr if x <= iv_val) / len(arr) * 100, 1)

                c.execute("""
                    INSERT OR REPLACE INTO options_iv_history
                    (symbol, date, expiry, atm_strike, atm_iv_ce, atm_iv_pe,
                     atm_iv_avg, iv_rank_252d, iv_percentile_252d,
                     pcr_oi, total_ce_oi, total_pe_oi, last_updated)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    symbol, date_str,
                    result["expiry"], result["atm_strike"],
                    result["atm_iv_ce"], result["atm_iv_pe"],
                    result["atm_iv_avg"], iv_rank, iv_pct,
                    result["pcr_oi"],
                    result["total_ce_oi"], result["total_pe_oi"], NOW
                ))
                inserted += 1

            if inserted % 1000 == 0 and inserted > 0:
                c.commit()
                log(f"  Date {i+1}/{len(dates)} ({date_str}): {inserted} rows", "INFO")

        except Exception as e:
            continue

    c.commit()
    c.close()
    log(f"Options IV history: {inserted} rows built from fo_data", "OK")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="MICC Phase 2 Data Extraction")
    parser.add_argument("--screener", action="store_true")
    parser.add_argument("--trends",   action="store_true")
    parser.add_argument("--iv",       action="store_true")
    parser.add_argument("--from",     dest="from_date", default="2020-01-01",
                        help="Start date for IV backfill (YYYY-MM-DD)")
    parser.add_argument("--max",      dest="max_sym", type=int, default=500,
                        help="Max symbols for Screener fetch")
    args = parser.parse_args()

    run_all = not any([args.screener, args.trends, args.iv])

    print()
    print("=" * 60)
    print("  MICC Phase 2 Data Extraction")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    results = {}

    if run_all or args.screener:
        results["Screener fundamentals"] = fetch_screener_fundamentals(args.max_sym)

    if run_all or args.trends:
        results["Google Trends"]         = fetch_google_trends()

    if run_all or args.iv:
        results["Options IV history"]    = fetch_iv_backfill(args.from_date)

    print()
    print("=" * 60)
    for name, ok in results.items():
        print(f"  [{'✅ OK  ' if ok else '❌ FAIL'}]  {name}")
    print("=" * 60)


if __name__ == "__main__":
    main()
