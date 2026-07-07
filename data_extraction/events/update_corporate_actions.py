#!/usr/bin/env python3
"""
update_corporate_actions.py – ONLY symbols present in stocks/all/ (parallel, progress).

Yahoo's rate limiter is burst-sensitive: a 20-thread hammering (the old design)
trips it almost instantly and stays tripped for a cooldown window regardless of
how gently you retry inside that window. Kept to a small thread count with a
per-call retry/backoff so a rate-limit hit is retried, not silently recorded as
"no corporate action" for that symbol.
"""
import sqlite3, time, logging, os, certifi, random
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

DB_PATH = Path(r"D:\marketDB\db\market.db")
STOCKS_DIR = Path(r"D:\marketDB\stocks\all")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\corporate_actions.log")
LOG_FILE.parent.mkdir(exist_ok=True)

MAX_WORKERS = 4
MAX_RETRIES = 3          # per symbol, on rate-limit only
BACKOFF_BASE = 20         # seconds; doubles each retry + jitter
CIRCUIT_BREAK_AFTER = 15  # consecutive rate-limit exhaustions -> stop the whole run

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE)]
)
log = logging.getLogger("corp_actions")

def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS corporate_actions (
            symbol TEXT, date TEXT, action_type TEXT,
            ratio REAL, amount REAL,
            PRIMARY KEY (symbol, date, action_type)
        )
    """)
    conn.commit()

class RateLimited(Exception):
    """Raised when a symbol exhausts its retries against an active rate limit --
    distinct from a clean 'no corporate actions for this symbol' result."""

def fetch_one(symbol):
    """Use symbol + .NS as Yahoo ticker. Retries on rate-limit; any other failure
    (missing ticker, no history, etc.) is treated as a genuine empty result."""
    yahoo = f"{symbol}.NS"
    for attempt in range(MAX_RETRIES):
        try:
            ticker = yf.Ticker(yahoo)
            if ticker.history(period="5d").empty:
                return []
            splits = ticker.splits
            dividends = ticker.dividends
            rows = []
            for dt, ratio in splits.items():
                rows.append((symbol, dt.strftime("%Y-%m-%d"), "SPLIT", float(ratio), None))
            for dt, amount in dividends.items():
                rows.append((symbol, dt.strftime("%Y-%m-%d"), "DIVIDEND", None, float(amount)))
            return rows
        except YFRateLimitError:
            if attempt == MAX_RETRIES - 1:
                raise RateLimited(symbol)
            time.sleep(BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 5))
        except Exception:
            return []

def main():
    print("=" * 60)
    print("Corporate Actions – stocks with Parquet data only")

    if not STOCKS_DIR.exists():
        print("stocks/all/ directory not found.")
        return

    # Only directories that contain at least one .parquet file
    symbols = sorted([
        d.name for d in STOCKS_DIR.iterdir()
        if d.is_dir() and any(d.glob("*.parquet"))
    ])

    print(f"Found {len(symbols)} symbols with price data.")
    if not symbols:
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout=60000")
    create_table(conn)

    total = len(symbols)
    print(f"Processing {total} symbols with {MAX_WORKERS} threads...")

    rate_limited_syms = []
    consecutive_rate_limits = 0
    circuit_broken = False

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_one, sym): sym for sym in symbols}
        for future in tqdm(as_completed(futures), total=total, desc="Fetching", unit="sym"):
            sym = futures[future]
            try:
                data = future.result()
                consecutive_rate_limits = 0
                if data:
                    conn.executemany("""
                        INSERT OR REPLACE INTO corporate_actions (symbol, date, action_type, ratio, amount)
                        VALUES (?, ?, ?, ?, ?)
                    """, data)
                    conn.commit()
            except RateLimited:
                rate_limited_syms.append(sym)
                consecutive_rate_limits += 1
                log.warning(f"{sym}: rate-limited past {MAX_RETRIES} retries")
                if consecutive_rate_limits >= CIRCUIT_BREAK_AFTER:
                    log.warning(f"CIRCUIT BREAKER: {consecutive_rate_limits} consecutive "
                                f"rate-limit exhaustions -- stopping run, {sym} onward untried")
                    circuit_broken = True
                    for f in futures:
                        f.cancel()
                    break
            except Exception as e:
                log.error(f"{sym}: {e}")

    conn.close()
    if rate_limited_syms:
        print(f"! {len(rate_limited_syms)} symbols still rate-limited after "
              f"{MAX_RETRIES} retries each: {rate_limited_syms[:10]}"
              f"{'...' if len(rate_limited_syms) > 10 else ''}")
    if circuit_broken:
        print("✗ Circuit breaker tripped -- run stopped early, rerun to resume "
              "(idempotent; symbols already stored this run are kept).")
    else:
        print("✓ Corporate actions update complete.")
    print("=" * 60)

if __name__ == "__main__":
    main()