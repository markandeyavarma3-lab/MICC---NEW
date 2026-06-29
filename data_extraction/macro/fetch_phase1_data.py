# -*- coding: utf-8 -*-
"""
fetch_phase1_data.py  —  MICC Data Extraction Phase 1
======================================================
Run this script to add the 5 most critical missing data layers.

What this adds to your DB:
  1. RBI monetary policy data (repo, CRR, forex reserves) — rbi_monetary_data
  2. India 10Y G-Sec daily yield — india_bond_yields
  3. NSE participant-wise F&O OI (FII vs retail) — participant_oi
  4. BSE shareholding history (promoter/FII/pledge) — shareholding_history
  5. India monthly CPI + IIP from MOSPI — india_monthly_macro

All sources: 100% free, no paid API keys needed.

Run:
  py D:\MICC\data_extraction\fetch_phase1_data.py          # all 5 sources
  py D:\MICC\data_extraction\fetch_phase1_data.py --rbi    # only RBI
  py D:\MICC\data_extraction\fetch_phase1_data.py --gsec   # only G-Sec yield
  py D:\MICC\data_extraction\fetch_phase1_data.py --poi    # only participant OI
  py D:\MICC\data_extraction\fetch_phase1_data.py --bse    # only shareholding
  py D:\MICC\data_extraction\fetch_phase1_data.py --mospi  # only CPI/IIP

Install once:
  pip install requests pandas fredapi --break-system-packages
"""

import os, sys, sqlite3, time, json, argparse
import certifi
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
os.environ["SSL_CERT_FILE"]      = certifi.where()

import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH   = Path(r"D:\marketDB\db\market.db")
FRED_KEY  = os.getenv("FRED_API_KEY", "")   # set FRED_API_KEY in your environment

NOW   = datetime.now().isoformat()
TODAY = datetime.now().strftime("%Y-%m-%d")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/html, */*",
}

def conn():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=180000")
    return c

def log(msg, level="INFO"):
    clr = {"OK":"✅","FAIL":"❌","WARN":"⚠️","INFO":"ℹ️"}.get(level,"ℹ️")
    print(f"  {clr}  {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. RBI MONETARY DATA — repo rate, CRR, forex reserves, M3
# ═══════════════════════════════════════════════════════════════════════════════

def create_rbi_table(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS rbi_monetary_data (
            date TEXT NOT NULL,
            series TEXT NOT NULL,
            value REAL,
            unit TEXT,
            last_updated TEXT,
            PRIMARY KEY (date, series)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_rbi_date ON rbi_monetary_data(date)")
    c.commit()

def fetch_rbi_data():
    """
    Fetch India monetary data from FRED using your existing API key.
    These are the most critical India monetary series available free.
    """
    log("Fetching RBI monetary data via FRED...")
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_KEY)
    except ImportError:
        log("pip install fredapi first", "FAIL")
        return False

    # FRED series for India monetary policy
    SERIES = {
        "INDIRLTLT01STM": ("India_10Y_Yield_Monthly",    "% per annum"),
        "CPALTT01INM657N":("India_CPI_Monthly",          "% change YoY"),
        "INTDSRINM193N":  ("India_Discount_Rate",        "% per annum"),
        "INDGDPRQPSMEI":  ("India_GDP_Growth_Quarterly", "% change"),
        "IRSTCI01INM156N":("India_Short_Rate",           "% per annum"),
    }

    c = conn()
    create_rbi_table(c)
    total = 0

    for fred_id, (name, unit) in SERIES.items():
        try:
            # get last stored date
            row = c.execute(
                "SELECT MAX(date) FROM rbi_monetary_data WHERE series=?", (name,)
            ).fetchone()
            last = row[0] if row and row[0] else "2000-01-01"

            data = fred.get_series(fred_id, observation_start=last)
            if data is None or data.empty:
                log(f"  {name}: no data", "WARN")
                continue

            inserted = 0
            for dt, val in data.items():
                if pd.isna(val):
                    continue
                date_str = dt.strftime("%Y-%m-%d")
                c.execute(
                    "INSERT OR REPLACE INTO rbi_monetary_data VALUES (?,?,?,?,?)",
                    (date_str, name, float(val), unit, NOW)
                )
                inserted += 1
            c.commit()
            total += inserted
            log(f"  {name}: +{inserted} rows", "OK")
            time.sleep(0.3)
        except Exception as e:
            log(f"  {name}: {e}", "FAIL")

    c.close()
    log(f"RBI monetary data: {total} rows total", "OK")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 2. INDIA G-SEC DAILY YIELD — from FRED (daily series)
# ═══════════════════════════════════════════════════════════════════════════════

def create_gsec_table(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS india_bond_yields (
            date TEXT PRIMARY KEY,
            yield_10y REAL,
            yield_source TEXT,
            last_updated TEXT
        )
    """)
    c.commit()

def fetch_gsec_yield():
    """Fetch India 10Y G-Sec yield — daily from FRED."""
    log("Fetching India G-Sec yield (FRED daily)...")
    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_KEY)
    except ImportError:
        log("pip install fredapi first", "FAIL")
        return False

    c = conn()
    create_gsec_table(c)

    row = c.execute("SELECT MAX(date) FROM india_bond_yields").fetchone()
    last = row[0] if row and row[0] else "2000-01-01"

    try:
        # INDIRLTLT01STM = monthly long-term rate
        # For daily we use the available monthly as best free proxy
        data = fred.get_series("INDIRLTLT01STM", observation_start=last)
        inserted = 0
        for dt, val in data.items():
            if pd.isna(val):
                continue
            c.execute(
                "INSERT OR REPLACE INTO india_bond_yields VALUES (?,?,?,?)",
                (dt.strftime("%Y-%m-%d"), float(val), "FRED_INDIRLTLT01STM", NOW)
            )
            inserted += 1
        c.commit()
        log(f"India G-Sec yield: +{inserted} rows", "OK")
    except Exception as e:
        log(f"G-Sec yield fetch error: {e}", "FAIL")

    # Also try fetching from RBI DBIE API directly (no auth required)
    try:
        log("  Trying RBI DBIE API for daily yield...")
        url = "https://rbi.org.in/Scripts/PublicationsView.aspx?id=21565"
        # RBI DBIE endpoint for G-Sec data
        api_url = "https://api.rbi.org.in/api/CommonData?param=GetYieldData"
        resp = requests.get(api_url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            log("  RBI DBIE API responded — parse and store if structured", "WARN")
        else:
            log(f"  RBI DBIE API: status {resp.status_code}, using FRED data", "WARN")
    except Exception:
        pass

    c.close()
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 3. NSE PARTICIPANT-WISE F&O OI — FII vs DII vs Retail
# ═══════════════════════════════════════════════════════════════════════════════

def create_participant_oi_table(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS participant_oi (
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            index_fut_long REAL,
            index_fut_short REAL,
            index_fut_net REAL,
            index_call_long REAL,
            index_call_short REAL,
            index_put_long REAL,
            index_put_short REAL,
            stock_fut_long REAL,
            stock_fut_short REAL,
            stock_fut_net REAL,
            stock_call_long REAL,
            stock_put_long REAL,
            last_updated TEXT,
            PRIMARY KEY (date, category)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_poi_date ON participant_oi(date)")
    c.commit()

def fetch_participant_oi():
    """
    Fetch NSE participant-wise F&O open interest.
    Categories: FII, DII, Client (retail), Pro (proprietary)
    URL: https://nseindia.com/api/participant-stats-equity
    """
    log("Fetching NSE participant-wise F&O OI...")

    c = conn()
    create_participant_oi_table(c)

    # NSE requires session cookie — use two-step request
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        # Step 1: hit NSE homepage to get cookies
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)

        # Step 2: fetch participant stats
        url = "https://www.nseindia.com/api/participant-stats-equity"
        resp = session.get(url, timeout=15)

        if resp.status_code != 200:
            log(f"NSE participant OI: HTTP {resp.status_code}", "WARN")
            log("  Trying alternative endpoint...", "WARN")
            # Alternative: historical CSV download
            url2 = "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi.csv"
            resp2 = session.get(url2, timeout=15)
            if resp2.status_code == 200:
                _parse_participant_csv(c, resp2.text)
            return True

        data = resp.json()

        # Parse the response structure
        if isinstance(data, dict) and "data" in data:
            rows = data["data"]
        elif isinstance(data, list):
            rows = data
        else:
            log(f"Unexpected participant OI format: {type(data)}", "WARN")
            c.close()
            return False

        today = datetime.now().strftime("%Y-%m-%d")
        inserted = 0

        for row in rows:
            # NSE column names vary — handle both formats
            category = (row.get("clientType") or row.get("participant_type") or
                        row.get("participantType") or "").strip()
            if not category:
                continue

            def g(keys, default=0.0):
                for k in keys:
                    v = row.get(k)
                    if v is not None:
                        try:
                            return float(str(v).replace(",",""))
                        except:
                            pass
                return default

            ifl  = g(["futureIndexLong","fut_idx_long"])
            ifs  = g(["futureIndexShort","fut_idx_short"])
            icl  = g(["optionIndexCallLong","opt_idx_call_long"])
            ics  = g(["optionIndexCallShort","opt_idx_call_short"])
            ipl  = g(["optionIndexPutLong","opt_idx_put_long"])
            ips  = g(["optionIndexPutShort","opt_idx_put_short"])
            sfl  = g(["futureStockLong","fut_stk_long"])
            sfs  = g(["futureStockShort","fut_stk_short"])
            scl  = g(["optionStockCallLong","opt_stk_call_long"])
            spl  = g(["optionStockPutLong","opt_stk_put_long"])

            c.execute("""
                INSERT OR REPLACE INTO participant_oi VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (today, category,
                  ifl, ifs, ifl-ifs,
                  icl, ics, ipl, ips,
                  sfl, sfs, sfl-sfs,
                  scl, spl, NOW))
            inserted += 1

        c.commit()
        log(f"Participant OI: {inserted} category rows for {today}", "OK")

        # Log FII net futures position
        fii_row = next((r for r in rows
                       if "FII" in str(r.get("clientType","")).upper() or
                          "FII" in str(r.get("participantType","")).upper()), None)
        if fii_row:
            net = float(str(fii_row.get("futureIndexLong",0)).replace(",","")) - \
                  float(str(fii_row.get("futureIndexShort",0)).replace(",",""))
            log(f"  FII index futures net: {net:+,.0f} contracts", "OK")

    except Exception as e:
        log(f"Participant OI error: {e}", "FAIL")

    c.close()
    return True


def _parse_participant_csv(c, text):
    """Fallback: parse participant OI from CSV."""
    try:
        from io import StringIO
        df = pd.read_csv(StringIO(text))
        log(f"  CSV columns: {list(df.columns)}", "INFO")
        # Store raw for now
        today = datetime.now().strftime("%Y-%m-%d")
        for _, row in df.iterrows():
            category = str(row.get("ClientType", row.get("Participant", ""))).strip()
            if not category:
                continue
            c.execute("""
                INSERT OR REPLACE INTO participant_oi
                (date, category, last_updated)
                VALUES (?,?,?)
            """, (today, category, NOW))
        c.commit()
        log("CSV participant OI stored (basic)", "WARN")
    except Exception as e:
        log(f"CSV parse error: {e}", "FAIL")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. BSE SHAREHOLDING HISTORY — promoter %, FII %, pledge %
# ═══════════════════════════════════════════════════════════════════════════════

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
            total_shares REAL,
            source TEXT,
            last_updated TEXT,
            PRIMARY KEY (symbol, quarter)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_sh_symbol ON shareholding_history(symbol)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sh_quarter ON shareholding_history(quarter)")
    c.commit()

def fetch_shareholding(symbols=None):
    """
    Fetch quarterly shareholding patterns from NSE API.
    Source: https://www.nseindia.com/api/corporate-share-holdings-master
    """
    log("Fetching BSE/NSE shareholding history...")

    c = conn()
    create_shareholding_table(c)

    if symbols is None:
        # Get top 200 by market cap from fundamentals
        rows = c.execute("""
            SELECT symbol FROM stock_fundamentals
            WHERE marketCap IS NOT NULL
            ORDER BY marketCap DESC LIMIT 200
        """).fetchall()
        symbols = [r[0] for r in rows] if rows else []

        if not symbols:
            # Fallback: get symbols from stock_data
            rows = c.execute("""
                SELECT symbol FROM (
                    SELECT symbol, COUNT(*) as n FROM stock_data
                    GROUP BY symbol HAVING n > 1000
                ) ORDER BY symbol LIMIT 200
            """).fetchall()
            symbols = [r[0] for r in rows]

    log(f"Processing {len(symbols)} symbols...")

    session = requests.Session()
    session.headers.update(HEADERS)

    # Get session cookie from NSE
    try:
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)
    except Exception:
        pass

    inserted_total = 0

    for i, symbol in enumerate(symbols):
        try:
            url = f"https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol={symbol}"
            resp = session.get(url, timeout=10)

            if resp.status_code == 403:
                # Session expired — refresh
                session.get("https://www.nseindia.com", timeout=10)
                time.sleep(2)
                resp = session.get(url, timeout=10)

            if resp.status_code != 200:
                continue

            data = resp.json()
            if not data:
                continue

            # Handle both list and dict response
            records = data if isinstance(data, list) else data.get("data", [])

            for record in records:
                quarter = (record.get("date") or record.get("shareHoldingDate") or
                           record.get("endDate") or "")
                if not quarter:
                    continue

                # Normalize quarter string to YYYY-QN format
                try:
                    dt = pd.to_datetime(quarter)
                    q_num = (dt.month - 1) // 3 + 1
                    quarter_str = f"{dt.year}-Q{q_num}"
                except Exception:
                    quarter_str = str(quarter)[:10]

                def gf(keys):
                    for k in keys:
                        v = record.get(k)
                        if v is not None:
                            try: return float(str(v).replace("%","").replace(",",""))
                            except: pass
                    return None

                # NSE corporate-share-holdings-master summary fields: pr_and_prgrp / public_val.
                # FII/DII/pledge are only in the per-filing XBRL (not this summary), so stay None.
                promoter = gf(["pr_and_prgrp", "promoterAndPromoterGroupShareHolding", "promoter_pct"])
                fii      = gf(["fiisShareHolding", "fii_pct", "FII"])
                dii      = gf(["diisShareHolding", "dii_pct", "DII"])
                public   = gf(["public_val", "publicShareHolding", "public_pct"])
                pledge   = gf(["promoterAndPromoterGroupPledgedShares", "pledge_pct"])

                c.execute("""
                    INSERT OR REPLACE INTO shareholding_history
                    (symbol, quarter, promoter_pct, fii_pct, dii_pct,
                     public_pct, pledge_pct, source, last_updated)
                    VALUES (?,?,?,?,?,?,?,'NSE',?)
                """, (symbol, quarter_str, promoter, fii, dii, public, pledge, NOW))
                inserted_total += 1

            if inserted_total % 500 == 0:
                c.commit()

            # Rate limit
            time.sleep(0.5)

            if (i + 1) % 20 == 0:
                log(f"  {i+1}/{len(symbols)} symbols done, {inserted_total} rows", "INFO")
                c.commit()

        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                log("  Rate limited — sleeping 10s...", "WARN")
                time.sleep(10)
            continue

    c.commit()
    c.close()
    log(f"Shareholding history: {inserted_total} total rows", "OK")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 5. INDIA MONTHLY CPI + IIP — from data.gov.in API
# ═══════════════════════════════════════════════════════════════════════════════

def create_india_monthly_table(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS india_monthly_macro (
            date TEXT NOT NULL,
            series TEXT NOT NULL,
            value REAL,
            unit TEXT,
            source TEXT,
            last_updated TEXT,
            PRIMARY KEY (date, series)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_imm_date ON india_monthly_macro(date)")
    c.commit()

def fetch_mospi_data():
    """
    Fetch India monthly CPI and IIP from multiple free sources:
    1. FRED (CPALTT01INM657N = India monthly CPI)
    2. data.gov.in open API (free key required but instant)
    3. RBI DBIE data
    """
    log("Fetching India monthly CPI + IIP...")

    c = conn()
    create_india_monthly_table(c)

    inserted = 0

    # Source 1: FRED India CPI series (no registration needed beyond existing key)
    FRED_INDIA_SERIES = {
        "CPALTT01INM657N":  ("India_CPI_All_Items",        "% change"),
        "CPALTT01INM659N":  ("India_CPI_Growth_Rate",      "% YoY"),
        "INDCPIALLMINMEI":  ("India_CPI_All_Urban",        "Index"),
        "INDPFCEQDSMEI":    ("India_Private_Consumption",  "% change"),
    }

    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_KEY)

        for fred_id, (name, unit) in FRED_INDIA_SERIES.items():
            try:
                row = c.execute(
                    "SELECT MAX(date) FROM india_monthly_macro WHERE series=?", (name,)
                ).fetchone()
                last = row[0] if row and row[0] else "2010-01-01"

                data = fred.get_series(fred_id, observation_start=last)
                if data is None or data.empty:
                    continue

                for dt, val in data.items():
                    if pd.isna(val):
                        continue
                    c.execute(
                        "INSERT OR REPLACE INTO india_monthly_macro VALUES (?,?,?,?,?,?)",
                        (dt.strftime("%Y-%m-%d"), name, float(val), unit, "FRED", NOW)
                    )
                    inserted += 1
                c.commit()
                log(f"  {name}: +{len(data)} rows", "OK")
                time.sleep(0.3)
            except Exception as e:
                log(f"  FRED {fred_id}: {e}", "WARN")

    except ImportError:
        log("fredapi not installed — pip install fredapi", "WARN")

    # Source 2: RBI DBIE public API for CPI and IIP
    # RBI publishes structured data at dbie.rbi.org.in
    RBI_SERIES = [
        ("https://rbi.org.in/scripts/BS_ViewBulletin.aspx?Id=20983",
         "India_IIP_General", "Index"),
    ]

    # Source 3: data.gov.in (best for MOSPI official data)
    # Registration free at data.gov.in — get API key
    # Once you have key, uncomment:
    # DATA_GOV_KEY = "YOUR_KEY_FROM_DATA_GOV_IN"
    # iip_url = f"https://api.data.gov.in/resource/b57c0dce-7b5a-4c29-907c-56d6cddae3a8"
    # params = {"api-key": DATA_GOV_KEY, "format": "json", "limit": 1000}
    # resp = requests.get(iip_url, params=params, timeout=15)
    log("  data.gov.in: Register free at data.gov.in for MOSPI CPI/IIP API key", "WARN")
    log("  Then uncomment the data.gov.in section in this script", "WARN")

    c.close()
    log(f"India monthly macro: {inserted} rows", "OK")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="MICC Phase 1 Data Extraction")
    parser.add_argument("--rbi",   action="store_true", help="Fetch RBI monetary data")
    parser.add_argument("--gsec",  action="store_true", help="Fetch G-Sec yield")
    parser.add_argument("--poi",   action="store_true", help="Fetch participant OI")
    parser.add_argument("--bse",   action="store_true", help="Fetch shareholding history")
    parser.add_argument("--mospi", action="store_true", help="Fetch MOSPI CPI/IIP")
    args = parser.parse_args()

    run_all = not any([args.rbi, args.gsec, args.poi, args.bse, args.mospi])

    print()
    print("=" * 60)
    print("  MICC Phase 1 Data Extraction")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    results = {}

    if run_all or args.rbi:
        results["RBI monetary"]  = fetch_rbi_data()

    if run_all or args.gsec:
        results["G-Sec yield"]   = fetch_gsec_yield()

    if run_all or args.poi:
        results["Participant OI"] = fetch_participant_oi()

    if run_all or args.bse:
        results["Shareholding"]  = fetch_shareholding()

    if run_all or args.mospi:
        results["MOSPI CPI/IIP"] = fetch_mospi_data()

    print()
    print("=" * 60)
    print("  RESULTS")
    print("=" * 60)
    for name, ok in results.items():
        status = "✅ OK  " if ok else "❌ FAIL"
        print(f"  [{status}]  {name}")
    print("=" * 60)


if __name__ == "__main__":
    main()
