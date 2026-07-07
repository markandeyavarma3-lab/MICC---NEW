# -*- coding: utf-8 -*-
"""
fetch_nse_session_data.py  —  NSE data requiring session cookies
=================================================================
Fixes the 404 errors from fetch_phase1_data.py for:
  - NSE participant-wise F&O OI (FII vs retail positioning)
  - NSE shareholding history per symbol

NSE blocks direct API calls. This script properly:
  1. Opens NSE homepage to get session cookies
  2. Waits for JS to load
  3. Then calls the data APIs with valid session

Run:
  py D:\MICC\data_extraction\fetch_nse_session_data.py --poi
  py D:\MICC\data_extraction\fetch_nse_session_data.py --sh
  py D:\MICC\data_extraction\fetch_nse_session_data.py  (both)

Requires: pip install requests --break-system-packages  (already installed)
"""

import os, sys, sqlite3, time, json, argparse
import certifi
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import requests
import pandas as pd
from datetime import datetime
from pathlib import Path

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
NOW     = datetime.now().isoformat()
TODAY   = datetime.now().strftime("%Y-%m-%d")

def conn():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c

def log(msg, level="INFO"):
    icon = {"OK":"✅","FAIL":"❌","WARN":"⚠️","INFO":"ℹ️"}.get(level,"ℹ️")
    print(f"  {icon}  {msg}", flush=True)

def get_nse_session():
    """
    Build a valid NSE session with cookies.
    NSE requires hitting the homepage first, then waiting.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.nseindia.com/",
    })

    # Step 1: hit homepage
    try:
        resp = session.get("https://www.nseindia.com", timeout=15)
        log(f"NSE homepage: {resp.status_code}", "INFO")
        time.sleep(2)
    except Exception as e:
        log(f"NSE homepage failed: {e}", "WARN")

    # Step 2: hit a data page to confirm session
    try:
        resp2 = session.get(
            "https://www.nseindia.com/get-quotes/equity?symbol=RELIANCE",
            timeout=10
        )
        time.sleep(1)
    except Exception:
        pass

    return session


def create_participant_oi_table(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS participant_oi (
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            index_fut_long REAL,  index_fut_short REAL,  index_fut_net REAL,
            index_call_long REAL, index_call_short REAL,
            index_put_long REAL,  index_put_short REAL,
            stock_fut_long REAL,  stock_fut_short REAL,  stock_fut_net REAL,
            stock_call_long REAL, stock_put_long REAL,
            last_updated TEXT,
            PRIMARY KEY (date, category)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_poi_date ON participant_oi(date)")
    c.commit()


def fetch_participant_oi():
    """Fetch NSE participant-wise F&O OI with proper session."""
    log("Fetching NSE participant OI...")

    c = conn()
    create_participant_oi_table(c)
    session = get_nse_session()

    # Try multiple NSE endpoints (they change occasionally)
    ENDPOINTS = [
        "https://www.nseindia.com/api/participant-stats-equity",
        "https://www.nseindia.com/api/participant-stats",
        "https://www.nseindia.com/api/fii-stats",
    ]

    data = None
    for url in ENDPOINTS:
        try:
            resp = session.get(url, timeout=15)
            log(f"  {url.split('/')[-1]}: HTTP {resp.status_code}", "INFO")
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    log(f"  Got data from: {url}", "OK")
                    break
            time.sleep(1)
        except Exception as e:
            log(f"  {url}: {e}", "WARN")
            time.sleep(1)

    if not data:
        # Fallback: try the archives CSV
        log("  Trying NSE archives CSV fallback...", "WARN")
        try:
            # NSE publishes participant OI as CSV in FO section
            csv_urls = [
                "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi.csv",
                "https://nsearchives.nseindia.com/content/nsccl/fo_participant_oi.csv",
            ]
            for csv_url in csv_urls:
                resp = session.get(csv_url, timeout=15)
                if resp.status_code == 200 and len(resp.text) > 100:
                    from io import StringIO
                    df = pd.read_csv(StringIO(resp.text))
                    log(f"  CSV columns: {list(df.columns)}", "INFO")
                    log(f"  CSV rows: {len(df)}", "INFO")

                    # Store what we can
                    for _, row in df.iterrows():
                        # Try to identify category column
                        cat_cols = [col for col in df.columns
                                    if any(k in col.lower()
                                           for k in ["client","type","participant","category"])]
                        if not cat_cols:
                            continue
                        category = str(row[cat_cols[0]]).strip()

                        def safe_float(val):
                            try: return float(str(val).replace(",",""))
                            except: return None

                        # Get all numeric columns
                        num_data = {col: safe_float(row[col])
                                    for col in df.columns if col not in cat_cols}

                        # Map to our schema based on common NSE column names
                        ifl  = num_data.get("Index Future Long",
                               num_data.get("futureIndexLong", None))
                        ifs  = num_data.get("Index Future Short",
                               num_data.get("futureIndexShort", None))
                        sfl  = num_data.get("Stock Future Long",
                               num_data.get("futureStockLong", None))
                        sfs  = num_data.get("Stock Future Short",
                               num_data.get("futureStockShort", None))

                        c.execute("""
                            INSERT OR REPLACE INTO participant_oi
                            (date, category, index_fut_long, index_fut_short,
                             index_fut_net, stock_fut_long, stock_fut_short,
                             stock_fut_net, last_updated)
                            VALUES (?,?,?,?,?,?,?,?,?)
                        """, (TODAY, category, ifl, ifs,
                              (ifl or 0) - (ifs or 0),
                              sfl, sfs,
                              (sfl or 0) - (sfs or 0), NOW))

                    c.commit()
                    log(f"  Stored from CSV", "OK")
                    c.close()
                    return True

        except Exception as e:
            log(f"  CSV fallback error: {e}", "FAIL")

        log("NSE participant OI: all endpoints failed — NSE may require browser auth", "WARN")
        log("  Alternative: download manually from nseindia.com/market-data/live-market", "WARN")
        c.close()
        return False

    # Parse successful JSON response
    rows_parsed = 0
    if isinstance(data, dict):
        records = data.get("data", data.get("resultList", [data]))
    else:
        records = data if isinstance(data, list) else []

    for record in records:
        def g(keys, default=0.0):
            for k in keys:
                v = record.get(k)
                if v is not None:
                    try: return float(str(v).replace(",",""))
                    except: pass
            return default

        category = (record.get("clientType") or record.get("participant_type") or
                    record.get("participantType") or record.get("Category") or "")
        if not category:
            continue
        category = str(category).strip()

        ifl = g(["futureIndexLong","Index Future Long","IF_Long"])
        ifs = g(["futureIndexShort","Index Future Short","IF_Short"])
        sfl = g(["futureStockLong","Stock Future Long","SF_Long"])
        sfs = g(["futureStockShort","Stock Future Short","SF_Short"])
        icl = g(["optionIndexCallLong","Index Call Long"])
        ics = g(["optionIndexCallShort","Index Call Short"])
        ipl = g(["optionIndexPutLong","Index Put Long"])
        ips = g(["optionIndexPutShort","Index Put Short"])
        scl = g(["optionStockCallLong","Stock Call Long"])
        spl = g(["optionStockPutLong","Stock Put Long"])

        c.execute("""
            INSERT OR REPLACE INTO participant_oi
            (date, category, index_fut_long, index_fut_short, index_fut_net,
             index_call_long, index_call_short, index_put_long, index_put_short,
             stock_fut_long, stock_fut_short, stock_fut_net,
             stock_call_long, stock_put_long, last_updated)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (TODAY, category, ifl, ifs, ifl-ifs,
              icl, ics, ipl, ips,
              sfl, sfs, sfl-sfs, scl, spl, NOW))
        rows_parsed += 1

    c.commit()

    # Print FII summary
    fii_row = c.execute(
        "SELECT index_fut_long, index_fut_short, index_fut_net "
        "FROM participant_oi WHERE date=? AND category LIKE '%FII%'",
        (TODAY,)
    ).fetchone()
    if fii_row:
        log(f"  FII index futures: Long={fii_row[0]:,.0f}  Short={fii_row[1]:,.0f}  "
            f"Net={fii_row[2]:+,.0f}", "OK")

    c.close()
    log(f"Participant OI: {rows_parsed} categories for {TODAY}", "OK")
    return True


def create_shareholding_table(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS shareholding_history (
            symbol TEXT NOT NULL,
            quarter TEXT NOT NULL,
            promoter_pct REAL,
            fii_pct REAL,
            dii_pct REAL,
            public_pct REAL,
            pledge_pct REAL,
            source TEXT,
            last_updated TEXT,
            PRIMARY KEY (symbol, quarter)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_sh_sym ON shareholding_history(symbol)")
    c.commit()


def fetch_shareholding(max_symbols=100):
    """Fetch quarterly shareholding from NSE with session."""
    log(f"Fetching NSE shareholding history (top {max_symbols} symbols)...")

    c = conn()
    create_shareholding_table(c)

    # Get symbols
    rows = c.execute("""
        SELECT symbol FROM stock_fundamentals
        WHERE marketCap IS NOT NULL ORDER BY marketCap DESC LIMIT ?
    """, (max_symbols,)).fetchall()

    if not rows:
        rows = c.execute("""
            SELECT symbol FROM (
                SELECT symbol, COUNT(*) as n FROM stock_data
                GROUP BY symbol HAVING n > 1000
            ) ORDER BY symbol LIMIT ?
        """, (max_symbols,)).fetchall()

    symbols = [r[0] for r in rows]
    if not symbols:
        log("No symbols found", "WARN")
        c.close()
        return False

    log(f"  Processing {len(symbols)} symbols...")
    session = get_nse_session()
    inserted = 0
    errors = 0

    for i, symbol in enumerate(symbols):
        # Skip if recently fetched
        row = c.execute(
            "SELECT COUNT(*) FROM shareholding_history "
            "WHERE symbol=? AND last_updated > date('now','-30 days')",
            (symbol,)
        ).fetchone()
        if row and row[0] > 0:
            continue

        try:
            # NSE shareholding API
            url = (f"https://www.nseindia.com/api/corporate-share-holdings-master"
                   f"?symbol={symbol}&series=EQ&from=&to=&isEmptyData=true")
            resp = session.get(url, timeout=12)

            if resp.status_code == 401 or resp.status_code == 403:
                # Session expired — refresh
                log(f"  Session expired at {symbol} — refreshing...", "WARN")
                session = get_nse_session()
                time.sleep(3)
                resp = session.get(url, timeout=12)

            if resp.status_code != 200:
                errors += 1
                time.sleep(0.5)
                continue

            data = resp.json()
            if not data:
                continue

            records = data if isinstance(data, list) else data.get("data", [])

            for record in records:
                # Date parsing
                date_raw = (record.get("date") or record.get("shareHoldingDate") or
                            record.get("endDate") or record.get("quarter") or "")
                if not date_raw:
                    continue
                try:
                    dt = pd.to_datetime(date_raw)
                    q_num = (dt.month - 1) // 3 + 1
                    quarter_str = f"{dt.year}-Q{q_num}"
                except:
                    quarter_str = str(date_raw)[:10]

                def gf(keys):
                    for k in keys:
                        v = record.get(k)
                        if v is not None:
                            try: return float(str(v).replace("%","").replace(",",""))
                            except: pass
                    return None

                promoter = gf(["promoterAndPromoterGroupShareHolding",
                               "promoterHolding","Promoter"])
                fii      = gf(["fiisShareHolding","fiiHolding","FII"])
                dii      = gf(["diisShareHolding","diiHolding","DII"])
                public   = gf(["publicShareHolding","publicHolding","Public"])
                pledge   = gf(["promoterAndPromoterGroupPledgedShares",
                               "pledgeShares","Pledge"])

                c.execute("""
                    INSERT OR REPLACE INTO shareholding_history
                    (symbol, quarter, promoter_pct, fii_pct, dii_pct,
                     public_pct, pledge_pct, source, last_updated)
                    VALUES (?,?,?,?,?,?,?,'NSE',?)
                """, (symbol, quarter_str, promoter, fii, dii,
                      public, pledge, NOW))
                inserted += 1

            if inserted % 200 == 0 and inserted > 0:
                c.commit()

            if (i + 1) % 10 == 0:
                log(f"  {i+1}/{len(symbols)} done — {inserted} rows, {errors} errors",
                    "INFO")

            time.sleep(0.6)  # NSE rate limit

        except Exception as e:
            errors += 1
            if "429" in str(e):
                log("  Rate limited — sleeping 15s...", "WARN")
                time.sleep(15)
            continue

    c.commit()
    c.close()
    log(f"Shareholding: {inserted} rows stored, {errors} errors", "OK")
    return inserted > 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--poi", action="store_true", help="Participant OI only")
    parser.add_argument("--sh",  action="store_true", help="Shareholding only")
    parser.add_argument("--max", type=int, default=100,
                        help="Max symbols for shareholding (default 100)")
    args = parser.parse_args()
    run_all = not (args.poi or args.sh)

    print()
    print("=" * 60)
    print("  MICC NSE Session Data Fetcher")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    results = {}
    if run_all or args.poi:
        results["Participant OI"]  = fetch_participant_oi()
    if run_all or args.sh:
        results["Shareholding"]    = fetch_shareholding(args.max)

    print()
    print("=" * 60)
    for name, ok in results.items():
        print(f"  [{'✅ OK  ' if ok else '❌ FAIL'}]  {name}")
    print("=" * 60)

if __name__ == "__main__":
    main()
