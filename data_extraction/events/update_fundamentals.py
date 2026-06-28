#!/usr/bin/env python3
"""
update_fundamentals.py – Quarterly financials ONLY for symbols in stocks/all/.
"""
import sqlite3, logging, json, time, os, certifi
from pathlib import Path
from datetime import datetime
import yfinance as yf

os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

DB_PATH = Path(r"D:\marketDB\db\market.db")
STOCKS_DIR = Path("stocks/all")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\fundamentals.log")
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("fundamentals")

def create_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_fundamentals (
            symbol TEXT PRIMARY KEY, last_updated TEXT,
            sector TEXT, industry TEXT, marketCap REAL, trailingPE REAL, forwardPE REAL,
            priceToBook REAL, dividendYield REAL, payoutRatio REAL, beta REAL
        )
    """)
    for tbl in ["quarterly_income", "quarterly_balance", "quarterly_cashflow"]:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {tbl} (
                symbol TEXT, report_date TEXT, data_json TEXT, last_updated TEXT,
                PRIMARY KEY (symbol, report_date)
            )
        """)
    conn.commit()

def fetch_quarterly_financials(symbol, yahoo_symbol):
    ticker = yf.Ticker(yahoo_symbol)
    records = {"income": [], "balance": [], "cashflow": []}
    try:
        inc = ticker.quarterly_income_stmt
        if inc is not None and not inc.empty:
            for col in inc.columns:
                date_str = col.strftime("%Y-%m-%d")
                records["income"].append((date_str, inc[col].to_dict()))
    except Exception as e:
        log.debug(f"{symbol}: quarterly income error – {e}")
    try:
        bal = ticker.quarterly_balance_sheet
        if bal is not None and not bal.empty:
            for col in bal.columns:
                date_str = col.strftime("%Y-%m-%d")
                records["balance"].append((date_str, bal[col].to_dict()))
    except Exception as e:
        log.debug(f"{symbol}: quarterly balance error – {e}")
    try:
        cf = ticker.quarterly_cashflow
        if cf is not None and not cf.empty:
            for col in cf.columns:
                date_str = col.strftime("%Y-%m-%d")
                records["cashflow"].append((date_str, cf[col].to_dict()))
    except Exception as e:
        log.debug(f"{symbol}: quarterly cashflow error – {e}")
    return records

def store_quarterly(conn, symbol, records):
    now = datetime.now().isoformat()
    for qtype, data_list in records.items():
        table_name = {"income": "quarterly_income", "balance": "quarterly_balance", "cashflow": "quarterly_cashflow"}[qtype]
        for date_str, data in data_list:
            for attempt in range(3):
                try:
                    conn.execute(f"""
                        INSERT OR REPLACE INTO {table_name} (symbol, report_date, data_json, last_updated)
                        VALUES (?, ?, ?, ?)
                    """, (symbol, date_str, json.dumps(data, default=str), now))
                    break
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) and attempt < 2:
                        log.warning(f"Database locked for {symbol} {table_name}, retrying...")
                        time.sleep(2)
                    else:
                        raise
    conn.commit()

def main():
    log.info("Starting quarterly fundamentals update (2675 symbols only)")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    create_tables(conn)

    # Only symbols that have Parquet data
    if not STOCKS_DIR.exists():
        log.error("stocks/all/ directory not found.")
        return

    symbols = sorted([
        d.name for d in STOCKS_DIR.iterdir()
        if d.is_dir() and any(d.glob("*.parquet"))
    ])

    total = len(symbols)
    log.info(f"Processing {total} symbols")

    for idx, sym in enumerate(symbols, 1):
        yahoo_sym = f"{sym}.NS"
        log.info(f"({idx}/{total}) {sym}")
        try:
            records = fetch_quarterly_financials(sym, yahoo_sym)
            store_quarterly(conn, sym, records)
        except Exception as e:
            log.error(f"{sym}: {e}")
        time.sleep(0.5)

    log.info("Quarterly fundamentals update complete.")
    conn.close()

if __name__ == "__main__":
    main()