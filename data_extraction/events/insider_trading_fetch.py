"""
insider_trading_fetch.py – Fetch SEBI insider trading data using nsefin.
Run daily (incremental) or with --backfill for historical data.
"""

import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import logging

import time

import pandas as pd
import requests
import nsefin  # kept for import-compat; insider fetch now uses the NSE API directly

# --- SSL fix (removes broken env variable) ---
import os, certifi
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\insider_trading.log")
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("insider_trading")


def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS insider_trading (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filing_date TEXT NOT NULL,
            symbol TEXT,
            company TEXT,
            name TEXT,
            category TEXT,
            transaction_type TEXT,
            quantity INTEGER,
            price REAL,
            value REAL,
            post_holding INTEGER,
            report_date TEXT,
            last_updated TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_insider_symbol ON insider_trading(symbol)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_insider_filing_date ON insider_trading(filing_date)")
    conn.commit()
    log.info("Insider trading table ready.")


def safe_int(x):
    try:
        return int(float(x)) if x and x != '' else 0
    except:
        return 0

def safe_float(x):
    try:
        return float(x) if x and x != '' else 0.0
    except:
        return 0.0

def _pit_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading",
    })
    try:
        s.get("https://www.nseindia.com", timeout=12)
    except Exception:
        pass
    return s


# ── 2026-07-05 endpoint migration ────────────────────────────────────────────
# NSE retired /api/corporates-pit around late April 2026: the old path still
# answers HTTP 200 with a VALID EMPTY envelope ({"data":[]}), which made this
# fetcher go silently green-but-empty for ~2 months (last real row 2026-06-09,
# healthy volume last seen week of Apr-20). The live page now uses
# /api/corporates-pit-gg, which returns a FILING INDEX (symbol, broadcast time,
# XBRL links) — the transaction detail (name/category/qty/value/type) moved
# into per-filing XBRL XML files on nsearchives. So: index fetch + one small
# XML fetch per new filing, parsed by contextRef groups.

def _localname(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag.rsplit(":", 1)[-1]


def _norm_category(raw):
    """Map new-XBRL CategoryOfPerson vocab onto the legacy values the scored
    event layer filters on (category IN ('Promoters','Promoter Group',
    'Director','Key Managerial Personnel')). Normalizing at ingest keeps the
    frozen scoring layer untouched. Raw value preserved in category_raw."""
    r = (raw or "").strip()
    low = r.lower()
    if low in ("promoter", "promoters"):
        return "Promoters"
    if "promoter" in low and "group" in low:
        return "Promoter Group"
    if "promoter" in low and "director" in low:
        return "Promoters"          # promoter is the stronger class
    if low == "kmp" or "key managerial" in low:
        return "Key Managerial Personnel"
    if low == "director" or low == "directors":
        return "Director"
    return r


def _norm_txn_type(raw, mode):
    """Normalize XBRL transaction vocab onto the values the event layer filters
    on ('Buy', 'Sell', 'Pledge', 'Pledge Invoke', ...). Raw value is preserved
    separately in transaction_type_raw for audit."""
    r = (raw or "").strip().lower()
    m = (mode or "").strip().lower()
    if "pledge" in r or "pledge" in m:
        blob = r + " " + m
        if "invo" in blob:
            return "Pledge Invoke"
        if "revo" in blob or "releas" in blob:
            return "Pledge Revoke"
        return "Pledge"
    if r.startswith(("acqui", "buy", "purchas", "subscri", "allot")):
        return "Buy"
    if r.startswith(("dispos", "sell", "sale", "transfer")):
        return "Sell"
    return (raw or "").strip() or "Unknown"


def _parse_pit_xml(xml_text):
    """One PIT filing XML -> list of transaction dicts (one per contextRef that
    carries a TransactionType). Small flat files (~10KB); namespace-agnostic."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    # bucket leaf values by contextRef
    ctx = {}
    for el in root.iter():
        cref = el.attrib.get("contextRef")
        if cref is None or el.text is None:
            continue
        ctx.setdefault(cref, {})[_localname(el.tag)] = el.text.strip()
    rows = []
    for _cref, f in ctx.items():
        if "SecuritiesAcquiredOrDisposedTransactionType" not in f and \
           "NameOfThePerson" not in f:
            continue
        raw_type = f.get("SecuritiesAcquiredOrDisposedTransactionType", "")
        mode = f.get("ModeOfAcquisitionOrDisposal", "")
        if not raw_type and not f.get("NameOfThePerson"):
            continue
        rows.append({
            "name": f.get("NameOfThePerson", ""),
            "category": _norm_category(f.get("CategoryOfPerson", "")),
            "category_raw": f.get("CategoryOfPerson", ""),
            "raw_type": raw_type,
            "mode": mode,
            "transaction_type": _norm_txn_type(raw_type, mode),
            "quantity": safe_int(f.get("SecuritiesAcquiredOrDisposedNumberOfSecurity")),
            "value": safe_float(f.get("SecuritiesAcquiredOrDisposedValueOfSecurity")),
            "post_holding": safe_int(
                f.get("SecuritiesHeldPostAcquistionOrDisposalNumberOfSecurity")),
            "intim_date": f.get("DateOfIntimationToCompany", ""),
        })
    # de-dup identical contexts (XBRL often repeats the same facts in D/I contexts)
    seen, out = set(), []
    for r in rows:
        k = (r["name"], r["raw_type"], r["quantity"], r["value"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def _fetch_pit(from_date_str, to_date_str):
    """Fetch the corporates-pit-gg filing index for a window (monthly chunks,
    equities + sme). Returns (session, index_rows); per-filing XBRL fetch and
    inserts happen in fetch_and_store so work commits incrementally."""
    s = _pit_session()
    start = pd.to_datetime(from_date_str).date()
    end = pd.to_datetime(to_date_str).date()

    index_rows, cur = [], start
    while cur <= end:
        nxt = min((pd.Timestamp(cur) + pd.offsets.MonthEnd(1)).date(), end)
        for idx in ("equities", "sme"):
            u = ("https://www.nseindia.com/api/corporates-pit-gg?index=" + idx +
                 f"&from_date={cur.strftime('%d-%m-%Y')}&to_date={nxt.strftime('%d-%m-%Y')}")
            try:
                data = s.get(u, timeout=30).json().get("data", [])
                index_rows.extend(data)
                log.info(f"  PIT-GG {idx} {cur} .. {nxt}: {len(data)} filings")
            except Exception as e:
                log.warning(f"  PIT-GG {idx} {cur}..{nxt} error: {e}")
            time.sleep(0.7)
        cur = (pd.Timestamp(nxt) + pd.Timedelta(days=1)).date()

    return s, index_rows


MAX_CONSECUTIVE_XML_FAILS = 10   # circuit breaker: nsearchives hard-throttles
                                 # bursts; grinding 30s timeouts helps nobody.
                                 # Stop early, keep what we have, resume later
                                 # (known filing_refs are skipped on rerun).


def _ensure_new_columns(conn):
    """Additive schema evolution for the pit-gg migration (no-op if present)."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(insider_trading)")}
    for col, typ in (("transaction_type_raw", "TEXT"), ("mode", "TEXT"),
                     ("filing_ref", "TEXT"), ("broadcast_dt", "TEXT"),
                     ("category_raw", "TEXT")):
        if col not in have:
            conn.execute(f"ALTER TABLE insider_trading ADD COLUMN {col} {typ}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_insider_filing_ref "
                 "ON insider_trading(filing_ref)")
    conn.commit()


def fetch_and_store(conn, from_date_str, to_date_str):
    """Fetch insider trades for a date range (corporates-pit-gg index + per-filing
    XBRL). Commits PER FILING so an interruption (kill, sleep, throttle-abort)
    never loses parsed work, and skips filings already in the DB so reruns only
    chase the gaps. Returns rows inserted."""
    try:
        log.info(f"Fetching insider trades from {from_date_str} to {to_date_str}")
        _ensure_new_columns(conn)

        known_refs = {r[0] for r in conn.execute(
            "SELECT DISTINCT filing_ref FROM insider_trading WHERE filing_ref IS NOT NULL")}

        s, index_rows = _fetch_pit(from_date_str, to_date_str)
        # de-dup index entries + drop already-stored filings BEFORE any XML fetch
        todo, seen = [], set()
        for fil in index_rows:
            xml_url = fil.get("xmlFileName") or ""
            ref = xml_url.rsplit("/", 1)[-1] if xml_url else ""
            if not ref or ref in known_refs or ref in seen:
                continue
            seen.add(ref)
            todo.append((fil, xml_url, ref))
        log.info(f"Index: {len(index_rows)} filings, {len(todo)} not yet stored.")

        cursor = conn.cursor()
        inserted, consec_fails = 0, 0
        now_iso = datetime.now().isoformat()
        for i, (fil, xml_url, ref) in enumerate(todo, 1):
            bdt = fil.get("broadcastDateTime") or ""
            try:
                fdate = pd.to_datetime(bdt, format="%d-%b-%Y %H:%M:%S").strftime("%Y-%m-%d")
            except Exception:
                fdate = None
            try:
                xr = s.get(xml_url, timeout=30)
                txns = _parse_pit_xml(xr.text) if xr.ok else []
                consec_fails = 0
            except Exception as e:
                consec_fails += 1
                log.warning(f"  XML fetch failed ({consec_fails} consec) {ref}: {e}")
                if consec_fails >= MAX_CONSECUTIVE_XML_FAILS:
                    log.warning(f"  CIRCUIT BREAKER: {consec_fails} consecutive XML "
                                f"failures at {i}/{len(todo)} — nsearchives is "
                                f"throttling. Stopping early; rerun resumes here.")
                    break
                continue
            for t in txns:
                fd = t["intim_date"] or fdate
                try:
                    fd = pd.to_datetime(fd).strftime("%Y-%m-%d")
                except Exception:
                    fd = fdate
                price = t["value"] / t["quantity"] if t["quantity"] > 0 else 0
                cursor.execute("""
                    INSERT INTO insider_trading
                    (filing_date, symbol, company, name, category, transaction_type,
                     quantity, price, value, post_holding, report_date, last_updated,
                     transaction_type_raw, mode, filing_ref, broadcast_dt, category_raw)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (fd, fil.get("symbol", ""), fil.get("companyName", ""),
                      t["name"], t["category"], t["transaction_type"], t["quantity"],
                      price, t["value"], t["post_holding"], fd, now_iso,
                      t["raw_type"], t["mode"], ref, bdt, t["category_raw"]))
                inserted += 1
            conn.commit()                       # per-filing durability
            if i % 100 == 0:
                log.info(f"  {i}/{len(todo)} filings ({inserted} rows inserted)")
            time.sleep(0.6)
        log.info(f"Inserted {inserted} rows from {len(todo)} pending filings.")
        return inserted

    except Exception as e:
        log.error(f"Fetch/store error: {e}")
        import traceback
        log.error(traceback.format_exc())
        return 0


STALE_TRIPWIRE_DAYS = 7   # exit non-zero if the feed is older than this


def incremental_update(conn):
    """Self-healing incremental: start from max(filing_date) - 3d (NOT just
    yesterday — the old yesterday-only window meant any failed day was lost
    forever, which is how a 2-month outage stayed invisible). Then a staleness
    tripwire: if the feed is still old after the fetch, exit non-zero so the
    pipeline shows a loud FAIL instead of a silent green."""
    today = datetime.now().strftime('%Y-%m-%d')
    last = conn.execute("SELECT MAX(filing_date) FROM insider_trading").fetchone()[0]
    start = (pd.to_datetime(last) - timedelta(days=3)).strftime('%Y-%m-%d') \
        if last else (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    # cap the catch-up window so a very stale table doesn't turn the daily
    # phase into an hours-long backfill (run --backfill manually for that)
    floor = (datetime.now() - timedelta(days=45)).strftime('%Y-%m-%d')
    start = max(start, floor)
    log.info(f"--- INCREMENTAL UPDATE ({start} -> {today}) ---")
    fetch_and_store(conn, start, today)

    mx = conn.execute("SELECT MAX(filing_date) FROM insider_trading").fetchone()[0]
    age = (datetime.now() - pd.to_datetime(mx)).days if mx else 999
    if age > STALE_TRIPWIRE_DAYS:
        log.error(f"STALENESS TRIPWIRE: max(filing_date)={mx} is {age}d old "
                  f"(> {STALE_TRIPWIRE_DAYS}d) — failing loudly.")
        raise SystemExit(2)


def historical_backfill(conn, from_date_str, to_date_str=None):
    if to_date_str is None:
        to_date_str = datetime.now().strftime('%Y-%m-%d')
    log.info(f"--- HISTORICAL BACKFILL from {from_date_str} to {to_date_str} ---")
    fetch_and_store(conn, from_date_str, to_date_str)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true", help="Historical backfill")
    parser.add_argument("--from-date", default="2024-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA busy_timeout=180000")
    create_table(conn)

    if args.backfill:
        historical_backfill(conn, args.from_date, args.to_date)
    else:
        incremental_update(conn)

    conn.close()
    log.info("Insider trading ETL finished.")