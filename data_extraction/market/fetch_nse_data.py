# -*- coding: utf-8 -*-
"""
fetch_nse_data.py  —  NSE Participant OI + Shareholding via nsefin
===================================================================
nsefin is ALREADY installed and handles NSE cookies internally.
No 403 errors. Uses the same client as insider_trading_fetch.py.

From your dir() output, nsefin has:
  get_fii_dii_activity       — FII/DII cash + derivatives
  get_most_active_contracts_by_oi — top OI contracts
  get_most_active_futures_by_volume
  get_most_active_index_calls / puts
  get_most_active_stock_calls / puts
  get_option_chain           — full chain for any symbol

Place at: D:\MICC\data_extraction\fetch_nse_data.py
Run:
  py D:\MICC\data_extraction\fetch_nse_data.py --fii     # FII/DII activity
  py D:\MICC\data_extraction\fetch_nse_data.py --oi      # top OI contracts
  py D:\MICC\data_extraction\fetch_nse_data.py --chain   # option chains
  py D:\MICC\data_extraction\fetch_nse_data.py           # all
"""
import os, sys, sqlite3, time, json, argparse
import certifi
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import nsefin
import pandas as pd
from datetime import datetime
from pathlib import Path

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
NOW     = datetime.now().isoformat()
TODAY   = datetime.now().strftime("%Y-%m-%d")

def get_conn():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c

def log(msg, ok=True):
    icon = "✅" if ok else "❌"
    print(f"  {icon}  {msg}", flush=True)

def warn(msg):
    print(f"  ⚠️  {msg}", flush=True)

def info(msg):
    print(f"  ℹ️  {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════
# 1. FII / DII ACTIVITY (cash + derivatives breakdown)
# ═══════════════════════════════════════════════════════════════════

def setup_fii_detailed(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS fii_dii_detailed (
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            segment TEXT,
            buy_value REAL,
            sell_value REAL,
            net_value REAL,
            last_updated TEXT,
            PRIMARY KEY (date, category, segment)
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_fdd_date ON fii_dii_detailed(date)")
    c.commit()

def _fii_dii_direct():
    """Direct NSE API fetch for FII/DII (bypasses nsefin's malformed-URL bug).
    Primes session cookies on the NSE homepage, then hits the public JSON API."""
    import requests
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/",
    })
    s.get("https://www.nseindia.com", timeout=10)  # prime cookies
    r = s.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=15)
    r.raise_for_status()
    return pd.DataFrame(r.json())


def fetch_fii_dii(nse):
    info("Fetching FII/DII activity (direct NSE API, nsefin fallback)...")
    c = get_conn()
    setup_fii_detailed(c)

    try:
        try:
            df = _fii_dii_direct()
        except Exception as direct_err:
            warn(f"Direct NSE API failed ({direct_err}); trying nsefin...")
            df = nse.get_fii_dii_activity()
        if df is None or df.empty:
            warn("No FII/DII data returned")
            c.close()
            return False

        info(f"Columns: {list(df.columns)}")
        info(f"Rows: {len(df)}")
        print(df.head(10).to_string())

        inserted = 0
        for _, row in df.iterrows():
            # Try to extract date
            date_val = None
            for dcol in ["date","Date","DATE","trading_date"]:
                if dcol in row.index:
                    try:
                        date_val = pd.to_datetime(row[dcol]).strftime("%Y-%m-%d")
                        break
                    except Exception:
                        pass
            if not date_val:
                date_val = TODAY

            # Try to extract category (FII/DII)
            cat = None
            for ccol in ["category","Category","type","Type","participant"]:
                if ccol in row.index:
                    cat = str(row[ccol]).strip()
                    break
            if not cat:
                cat = "UNKNOWN"

            # Try numeric values
            def gf(keys):
                for k in keys:
                    if k in row.index:
                        try: return float(str(row[k]).replace(",",""))
                        except: pass
                return None

            buy  = gf(["buyValue","buy_value","Buy Value","buyVal","gross_purchase"])
            sell = gf(["sellValue","sell_value","Sell Value","sellVal","gross_sales"])
            net  = gf(["netValue","net_value","Net Value","netVal","net_investment"])
            if net is None and buy is not None and sell is not None:
                net = buy - sell

            seg = None
            for scol in ["segment","Segment","market_type"]:
                if scol in row.index:
                    seg = str(row[scol]).strip()
                    break

            c.execute("""
                INSERT OR REPLACE INTO fii_dii_detailed
                (date,category,segment,buy_value,sell_value,net_value,last_updated)
                VALUES (?,?,?,?,?,?,?)
            """, (date_val, cat, seg, buy, sell, net, NOW))
            inserted += 1

        c.commit()
        log(f"FII/DII detailed: {inserted} rows stored for {TODAY}")
        c.close()
        return True

    except Exception as e:
        warn(f"FII/DII error: {e}")
        c.close()
        return False


# ═══════════════════════════════════════════════════════════════════
# 2. TOP OI CONTRACTS — who's building positions
# ═══════════════════════════════════════════════════════════════════

def setup_top_oi(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS top_oi_contracts (
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            expiry TEXT,
            instrument TEXT,
            strike REAL,
            option_type TEXT,
            open_interest REAL,
            chg_in_oi REAL,
            last_price REAL,
            volume REAL,
            last_updated TEXT,
            PRIMARY KEY (date, symbol, expiry, instrument, strike, option_type)
        )""")
    c.commit()

def fetch_top_oi(nse):
    info("Fetching top OI contracts...")
    c = get_conn()
    setup_top_oi(c)
    inserted = 0

    for fn_name, label in [
        ("get_most_active_contracts_by_oi", "top OI contracts"),
        ("get_most_active_index_calls",     "index calls"),
        ("get_most_active_index_puts",      "index puts"),
        ("get_most_active_stock_calls",     "stock calls"),
        ("get_most_active_stock_puts",      "stock puts"),
    ]:
        try:
            fn = getattr(nse, fn_name)
            df = fn()
            if df is None or df.empty:
                warn(f"  {label}: no data")
                continue

            for _, row in df.iterrows():
                def g(keys, default=None):
                    for k in keys:
                        if k in row.index:
                            try: return float(str(row[k]).replace(",","").replace("-","0"))
                            except: pass
                    return default

                def gs(keys, default=""):
                    for k in keys:
                        if k in row.index and row[k]:
                            return str(row[k]).strip()
                    return default

                symbol = gs(["symbol","Symbol","underlying"])
                expiry = gs(["expiryDate","expiry","Expiry","expiry_date"])
                try:
                    expiry = pd.to_datetime(expiry).strftime("%Y-%m-%d")
                except Exception:
                    pass
                instr  = gs(["instrumentType","instrument","Instrument"], label)
                strike = g(["strikePrice","strike","Strike"])
                opttyp = gs(["optionType","option_type","CE/PE","type"])
                oi     = g(["openInterest","open_interest","OI","oi"])
                chgoi  = g(["changeinOpenInterest","chg_in_oi","change_oi"])
                ltp    = g(["lastPrice","ltp","LTP","last_price","close"])
                vol    = g(["totalTradedVolume","volume","Volume","vol"])

                if not symbol:
                    continue

                c.execute("""
                    INSERT OR REPLACE INTO top_oi_contracts
                    (date,symbol,expiry,instrument,strike,option_type,
                     open_interest,chg_in_oi,last_price,volume,last_updated)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (TODAY,symbol,expiry,instr,strike,opttyp,oi,chgoi,ltp,vol,NOW))
                inserted += 1

            log(f"  {label}: {len(df)} rows")
            time.sleep(0.5)

        except Exception as e:
            warn(f"  {label}: {e}")

    c.commit()
    c.close()
    log(f"Top OI contracts: {inserted} rows total")
    return inserted > 0


# ═══════════════════════════════════════════════════════════════════
# 3. OPTION CHAINS for key symbols — store IV snapshots
# ═══════════════════════════════════════════════════════════════════

def setup_option_snapshots(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS option_chain_snapshots (
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            expiry TEXT NOT NULL,
            strike REAL NOT NULL,
            ce_oi REAL, ce_chg_oi REAL, ce_iv REAL, ce_ltp REAL,
            pe_oi REAL, pe_chg_oi REAL, pe_iv REAL, pe_ltp REAL,
            pcr_strike REAL,
            last_updated TEXT,
            PRIMARY KEY (date, symbol, expiry, strike)
        )""")
    c.commit()

def fetch_option_chains(nse):
    info("Fetching option chain snapshots...")
    SYMBOLS = ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK",
               "INFY", "ICICIBANK", "AXISBANK", "BAJFINANCE", "TATAMOTORS"]

    c = get_conn()
    setup_option_snapshots(c)
    inserted = 0

    for symbol in SYMBOLS:
        try:
            df = nse.get_option_chain(symbol)
            if df is None or df.empty:
                warn(f"  {symbol}: no chain data")
                continue

            info(f"  {symbol}: {len(df)} strikes, columns: {list(df.columns)[:8]}")

            for _, row in df.iterrows():
                def g(keys):
                    for k in keys:
                        if k in row.index:
                            try: return float(str(row[k]).replace(",","").replace("-","0") or 0)
                            except: pass
                    return None

                def gs(keys):
                    for k in keys:
                        if k in row.index and row[k]:
                            return str(row[k]).strip()
                    return None

                expiry = gs(["expiryDate","expiry","Expiry"])
                try:
                    expiry = pd.to_datetime(expiry).strftime("%Y-%m-%d")
                except Exception:
                    pass

                strike  = g(["strikePrice","strike","Strike"])
                ce_oi   = g(["CE.openInterest","CE_OI","ce_oi"])
                ce_chg  = g(["CE.changeinOpenInterest","CE_CHG_OI"])
                ce_iv   = g(["CE.impliedVolatility","CE_IV","ce_iv"])
                ce_ltp  = g(["CE.lastPrice","CE_LTP","ce_ltp"])
                pe_oi   = g(["PE.openInterest","PE_OI","pe_oi"])
                pe_chg  = g(["PE.changeinOpenInterest","PE_CHG_OI"])
                pe_iv   = g(["PE.impliedVolatility","PE_IV","pe_iv"])
                pe_ltp  = g(["PE.lastPrice","PE_LTP","pe_ltp"])
                pcr     = round(pe_oi/ce_oi, 3) if ce_oi and ce_oi > 0 else None

                if not strike or not expiry:
                    continue

                c.execute("""
                    INSERT OR REPLACE INTO option_chain_snapshots
                    (date,symbol,expiry,strike,
                     ce_oi,ce_chg_oi,ce_iv,ce_ltp,
                     pe_oi,pe_chg_oi,pe_iv,pe_ltp,pcr_strike,last_updated)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (TODAY,symbol,expiry,strike,
                      ce_oi,ce_chg,ce_iv,ce_ltp,
                      pe_oi,pe_chg,pe_iv,pe_ltp,pcr,NOW))
                inserted += 1

            c.commit()
            log(f"  {symbol}: {len(df)} strikes stored")
            time.sleep(0.8)

        except Exception as e:
            warn(f"  {symbol}: {e}")

    c.close()
    log(f"Option chains: {inserted} strike rows stored")
    return inserted > 0


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fii",   action="store_true", help="FII/DII detailed activity")
    parser.add_argument("--oi",    action="store_true", help="Top OI contracts")
    parser.add_argument("--chain", action="store_true", help="Option chain snapshots")
    args = parser.parse_args()
    run_all = not (args.fii or args.oi or args.chain)

    print(f"\n{'='*55}")
    print("  MICC NSE Data Fetcher (via nsefin)")
    print(f"  {TODAY}")
    print(f"{'='*55}\n")

    nse = nsefin.NSEClient()
    results = {}

    if run_all or args.fii:
        results["FII/DII activity"]    = fetch_fii_dii(nse)
    if run_all or args.oi:
        results["Top OI contracts"]    = fetch_top_oi(nse)
    if run_all or args.chain:
        results["Option chain snapshots"] = fetch_option_chains(nse)

    print(f"\n{'='*55}")
    for name, ok in results.items():
        print(f"  [{'✅' if ok else '❌'}]  {name}")
    print(f"{'='*55}\n")

if __name__ == "__main__":
    import argparse
    main()
