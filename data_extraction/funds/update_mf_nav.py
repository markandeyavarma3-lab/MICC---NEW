# update_mf_nav.py – robust version
import sqlite3
import logging
import requests
import time
from pathlib import Path
from datetime import datetime

# --- SSL fix ---
import os, certifi
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

DB_PATH = Path(r"D:\marketDB\db\market.db")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\mf_nav.log")
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("mf_nav")

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mf_nav_history (
            scheme_code TEXT,
            scheme_name TEXT,
            date TEXT,
            nav REAL,
            PRIMARY KEY (scheme_code, date)
        )
    """)
    conn.commit()
    conn.close()

def fetch_all_schemes():
    url = "https://api.mfapi.in/mf"
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=60)
            if response.status_code == 200:
                return response.json()
            else:
                time.sleep(5)
        except Exception as e:
            log.warning(f"MFAPI attempt {attempt+1} failed: {e}")
            time.sleep(5)
    return []

def get_nav_for_scheme(scheme_code, scheme_name):
    """Fetch latest NAV for a single scheme. Returns (scheme_code, scheme_name, date, nav) or None."""
    try:
        resp = requests.get(f"https://api.mfapi.in/mf/{scheme_code}", timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if 'data' not in data or not data['data']:
            return None
        latest = data['data'][0]
        nav_str = latest.get('nav', '')
        if nav_str in ('', '-', 'null', None):
            return None
        nav = float(nav_str)
        date_str = latest.get('date', '')
        if not date_str:
            return None
        # Convert dd-mm-yyyy to yyyy-mm-dd
        try:
            date_obj = datetime.strptime(date_str, "%d-%m-%Y")
            date_fmt = date_obj.strftime("%Y-%m-%d")
        except:
            return None
        return (scheme_code, scheme_name, date_fmt, nav)
    except Exception as e:
        log.debug(f"Error for {scheme_code} ({scheme_name[:50]}): {e}")
        return None

def main():
    log.info("=" * 55)
    log.info("Mutual Fund NAV Tracker (robust)")
    setup_db()
    conn = sqlite3.connect(DB_PATH)

    schemes = fetch_all_schemes()
    if not schemes:
        log.error("Could not fetch scheme list. Check internet connection.")
        return

    log.info(f"Found {len(schemes)} schemes. Fetching NAVs for first 100...")
    inserted = 0
    for idx, scheme in enumerate(schemes[:100], 1):
        code = scheme.get('schemeCode')
        name = scheme.get('schemeName')
        if not code or not name:
            log.warning(f"Skipping scheme {idx}: missing code or name")
            continue
        log.info(f"({idx}/100) {name[:60]}...")
        nav_data = get_nav_for_scheme(code, name)
        if nav_data:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO mf_nav_history (scheme_code, scheme_name, date, nav)
                    VALUES (?, ?, ?, ?)
                """, nav_data)
                inserted += 1
            except Exception as e:
                log.error(f"DB insert error for {code}: {e}")
        time.sleep(0.2)  # be gentle to the API

    conn.commit()
    conn.close()
    log.info(f"Done. Inserted/updated {inserted} NAV records.")
    log.info("=" * 55)

if __name__ == "__main__":
    main()