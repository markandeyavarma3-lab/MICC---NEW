# -*- coding: utf-8 -*-
"""
fetch_trends.py  —  MICC Google Trends
=======================================
Auto-installs pytrends using the CORRECT Python (py/Python314).
No manual pip needed.

Place at: D:\MICC\data_extraction\fetch_trends.py
Run:      py D:\MICC\data_extraction\fetch_trends.py
"""
import sys, os, sqlite3, time, subprocess
import certifi
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
from datetime import datetime
from pathlib import Path

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
NOW     = datetime.now().isoformat()

# ── Auto-install pytrends using THIS Python (not pip) ─────────────────────────
def ensure_pytrends():
    try:
        import pytrends
        return True
    except ImportError:
        print("  Installing pytrends with correct Python...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pytrends", "--quiet"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("  ✅ pytrends installed")
            return True
        else:
            print(f"  ❌ Install failed: {result.stderr[-200:]}")
            return False

def get_conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    return c

def setup(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS google_trends (
            query TEXT NOT NULL,
            symbol TEXT,
            date TEXT NOT NULL,
            interest_score INTEGER,
            category TEXT,
            geo TEXT,
            last_updated TEXT,
            PRIMARY KEY (query, date)
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_gt_sym ON google_trends(symbol,date)")
    c.commit()

# Queries: (search term, symbol tag, category)
QUERIES = [
    # Stocks
    ("RELIANCE share price",   "RELIANCE",   "stock"),
    ("TCS share price",        "TCS",        "stock"),
    ("HDFC Bank share",        "HDFCBANK",   "stock"),
    ("Infosys share",          "INFY",       "stock"),
    ("Zomato share",           "ZOMATO",     "stock"),
    # Market sentiment
    ("Nifty 50 today",         "NIFTY",      "index"),
    ("NSE stock market",       None,         "market"),
    ("best stocks buy India",  None,         "sentiment"),
    ("stock market crash",     None,         "fear"),
    # Sectors
    ("pharma stocks India",    None,         "sector"),
    ("banking stocks India",   None,         "sector"),
    ("IT stocks India",        None,         "sector"),
    ("IPO India",              None,         "ipo"),
    ("SIP mutual fund India",  None,         "mf"),
]

import sys as _sys
TIMEFRAME = "all" if "--full" in _sys.argv else "today 12-m"  # --full => 2004-present


def fetch_batch(pytrends_obj, batch, c):
    """Fetch one batch of up to 5 queries, with retry/backoff (Google 429s hard
    on long-range queries)."""
    terms = [q[0] for q in batch]
    inserted = 0
    for attempt in range(4):
        try:
            pytrends_obj.build_payload(terms, cat=0, timeframe=TIMEFRAME, geo="IN")
            df = pytrends_obj.interest_over_time()
            if df.empty:
                time.sleep(20 * (attempt + 1))
                continue
            for term, symbol, category in batch:
                if term not in df.columns:
                    continue
                for dt, val in df[term].items():
                    c.execute("""
                        INSERT OR REPLACE INTO google_trends
                        (query,symbol,date,interest_score,category,geo,last_updated)
                        VALUES (?,?,?,?,?,?,?)
                    """, (term, symbol, dt.strftime("%Y-%m-%d"),
                          int(val), category, "IN", NOW))
                    inserted += 1
            c.commit()
            return inserted
        except Exception as e:
            print(f"    batch error (attempt {attempt+1}): {str(e)[:80]}")
            time.sleep(20 * (attempt + 1))
    return inserted

def main():
    print(f"\n{'='*55}")
    print("  MICC Google Trends")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}\n")

    if not ensure_pytrends():
        sys.exit(1)

    from pytrends.request import TrendReq
    c = get_conn()
    setup(c)

    pt = TrendReq(hl="en-US", tz=330, timeout=(10, 25))
    total = 0

    # Process in batches of 5 (pytrends limit)
    for i in range(0, len(QUERIES), 5):
        batch = QUERIES[i:i+5]
        labels = ", ".join(q[0][:20] for q in batch)
        print(f"  Fetching: {labels}...")
        n = fetch_batch(pt, batch, c)
        total += n
        print(f"    → {n} data points")
        time.sleep(15)  # pytrends rate limit (long-range needs more)

    # Show latest scores
    rows = c.execute("""
        SELECT symbol, query, interest_score
        FROM google_trends
        WHERE date = (SELECT MAX(date) FROM google_trends)
        AND symbol IS NOT NULL
        ORDER BY interest_score DESC LIMIT 10
    """).fetchall()

    if rows:
        print("\n  Latest interest scores (India):")
        for sym, qry, score in rows:
            bar = "█" * (score // 10)
            print(f"    {sym:<15} {score:>3}  {bar}")

    c.close()
    print(f"\n  Total: {total} data points stored")
    print(f"{'='*55}\n")

if __name__ == "__main__":
    main()
