# -*- coding: utf-8 -*-
"""
MICC v2 — F&O Bhavcopy Backfill (FIXED v2)
============================================
Fixes vs v1:
  1. Probes existing fo_data schema first — uses ALTER TABLE to add
     any missing columns (option_typ etc.) rather than assuming schema
  2. Builds INSERT SQL dynamically from actual table columns
  3. Handles both standard UDiFF and older NSE CSV column names
  4. --probe flag to inspect existing fo_data schema

Run:
  py backfill_fo_data.py              → full backfill 2024-07-08 to today
  py backfill_fo_data.py --probe      → show existing fo_data schema
  py backfill_fo_data.py --today      → only today
  py backfill_fo_data.py --from 2025-01-01
  py backfill_fo_data.py --local      → load already-downloaded zips
"""

import io
import os
import sys
import time
import zipfile
import sqlite3
import warnings
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

# ── SSL cert fix ──────────────────────────────────────────────────────────────
try:
    import certifi
    _cert = certifi.where()
    os.environ["REQUESTS_CA_BUNDLE"] = _cert
    os.environ["SSL_CERT_FILE"]      = _cert
    os.environ["CURL_CA_BUNDLE"]     = _cert
except ImportError:
    pass

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH       = Path("D:/MICC/marketDB/db/market.db")
FO_DIR        = Path("D:/MICC/marketDB/NSE_FO")
BACKFILL_FROM = date(2024, 7, 8)

NSE_FO_URL = (
    "https://nsearchives.nseindia.com/content/fo/"
    "BhavCopy_NSE_FO_0_0_0_{date_str}_F_0000.csv.zip"
)
# Legacy F&O bhavcopy (pre-2024-07), e.g. .../2020/JAN/fo01JAN2020bhav.csv.zip
OLD_FO_URL = (
    "https://nsearchives.nseindia.com/content/historical/DERIVATIVES/"
    "{year}/{mon}/fo{dmy}bhav.csv.zip"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com/",
}

# ─────────────────────────────────────────────────────────────────────────────
# DESIRED SCHEMA — columns we want in fo_data
# ─────────────────────────────────────────────────────────────────────────────
DESIRED_COLS = {
    "date":        "TEXT NOT NULL",
    "instrument":  "TEXT",
    "symbol":      "TEXT",
    "expiry":      "TEXT",
    "strike":      "REAL",
    "option_typ": "TEXT",
    "open":        "REAL",
    "high":        "REAL",
    "low":         "REAL",
    "close":       "REAL",
    "settle_pr":   "REAL",
    "contracts":   "INTEGER",
    "val_inlakh":    "REAL",
    "open_int":    "INTEGER",
    "chg_in_oi":   "INTEGER",
}

# ─────────────────────────────────────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-65536")
    return conn


def get_fo_columns(conn: sqlite3.Connection) -> list:
    """Return current column names in fo_data, or [] if table doesn't exist."""
    try:
        rows = conn.execute("PRAGMA table_info(fo_data)").fetchall()
        return [r[1] for r in rows]
    except Exception:
        return []


def show_fo_schema(conn: sqlite3.Connection):
    cols = conn.execute("PRAGMA table_info(fo_data)").fetchall()
    print("\n  fo_data columns:")
    for c in cols:
        print(f"    {c[1]:25s}  {c[2]}")
    cnt = conn.execute("SELECT COUNT(*) FROM fo_data").fetchone()[0]
    try:
        dates = conn.execute(
            "SELECT MIN(date), MAX(date), COUNT(DISTINCT date) FROM fo_data"
        ).fetchone()
        print(f"\n  Rows: {cnt:,}")
        print(f"  Date range: {dates[0]} → {dates[1]} ({dates[2]} distinct dates)")
    except Exception:
        print(f"\n  Rows: {cnt:,}")
    row = conn.execute("SELECT * FROM fo_data LIMIT 1").fetchone()
    if row:
        col_names = [c[1] for c in cols]
        print("\n  Sample row:")
        for k, v in zip(col_names, row):
            print(f"    {k}: {repr(v)}")


# ─────────────────────────────────────────────────────────────────────────────
# TABLE SETUP — non-destructive, adds missing columns only
# ─────────────────────────────────────────────────────────────────────────────

def setup_table(conn: sqlite3.Connection):
    existing = get_fo_columns(conn)

    if not existing:
        # Create fresh
        col_defs = ",\n    ".join(
            f"{col} {dtype}" for col, dtype in DESIRED_COLS.items()
        )
        conn.execute(f"""
            CREATE TABLE fo_data (
                {col_defs},
                PRIMARY KEY (date, instrument, symbol, expiry, strike, option_typ)
            )
        """)
        print("[Setup] Created fo_data table fresh")
    else:
        # Add any missing columns (won't touch existing ones)
        added = []
        for col, dtype in DESIRED_COLS.items():
            if col not in existing:
                try:
                    conn.execute(f"ALTER TABLE fo_data ADD COLUMN {col} {dtype}")
                    added.append(col)
                except Exception as e:
                    print(f"[Setup] Could not add {col}: {e}")
        if added:
            print(f"[Setup] Added missing columns: {added}")
        else:
            print(f"[Setup] Schema OK — {len(existing)} columns, no changes needed")

    # Indices (safe — IF NOT EXISTS)
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_fo_date   ON fo_data(date)",
        "CREATE INDEX IF NOT EXISTS idx_fo_symbol ON fo_data(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_fo_inst   ON fo_data(instrument)",
    ]:
        try:
            conn.execute(idx_sql)
        except Exception:
            pass

    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# EXISTING DATE CACHE
# ─────────────────────────────────────────────────────────────────────────────

def get_existing_dates(conn: sqlite3.Connection) -> set:
    rows = conn.execute("SELECT DISTINCT date FROM fo_data").fetchall()
    return {r[0] for r in rows}


# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD
# ─────────────────────────────────────────────────────────────────────────────

def nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=10, verify=True)
        time.sleep(0.5)
    except Exception:
        pass
    return s


def download_fo_zip(session: requests.Session, trade_date: date):
    # Try UDiFF (2024-07+) first, then the legacy historical archive (pre-2024-07).
    udiff = NSE_FO_URL.format(date_str=trade_date.strftime("%Y%m%d"))
    legacy = OLD_FO_URL.format(
        year=trade_date.strftime("%Y"),
        mon=trade_date.strftime("%b").upper(),
        dmy=trade_date.strftime("%d%b%Y").upper(),
    )
    for url in (udiff, legacy):
        try:
            resp = session.get(url, timeout=30, verify=True)
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
        except Exception as e:
            print(f"    Download error: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# PARSE
# ─────────────────────────────────────────────────────────────────────────────

def parse_fo_zip(zip_bytes: bytes, trade_date: date):
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            csv_files = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_files:
                return None
            with zf.open(csv_files[0]) as f:
                df = pd.read_csv(f, low_memory=False)
    except Exception as e:
        print(f"    Parse error: {e}")
        return None

    df.columns = [c.strip().upper() for c in df.columns]

    # Map all known UDiFF / alternate column names → our desired names
    col_map = {
        "INSTRUMENT":   "instrument",
        "SYMBOL":       "symbol",
        "EXPIRY_DT":    "expiry",
        "EXPIRY":       "expiry",
        "EXPIRYDATE":   "expiry",
        "STRIKE_PR":    "strike",
        "STRIKEPRICE":  "strike",
        "OPTION_TYP":   "option_typ",
        "OPTIONTYPE":   "option_typ",
        "OPEN":         "open",
        "HIGH":         "high",
        "LOW":          "low",
        "CLOSE":        "close",
        "SETTLE_PR":    "settle_pr",
        "SETTLPRICE":   "settle_pr",
        "CONTRACTS":    "contracts",
        "VAL_INLAKH":   "val_inlakh",
        "VALINLAKH":    "val_inlakh",
        "VALUE":        "val_inlakh",
        "OPEN_INT":     "open_int",
        "OPENINT":      "open_int",
        "OPENINTEREST": "open_int",
        "CHG_IN_OI":    "chg_in_oi",
        "CHGINOI":      "chg_in_oi",
        # UDiFF F&O format (2024-07 onward)
        "TCKRSYMB":        "symbol",
        "FININSTRMTP":     "instrument",
        "XPRYDT":          "expiry",
        "STRKPRIC":        "strike",
        "OPTNTP":          "option_typ",
        "OPNPRIC":         "open",
        "HGHPRIC":         "high",
        "LWPRIC":          "low",
        "CLSPRIC":         "close",
        "STTLMPRIC":       "settle_pr",
        "TTLTRADGVOL":     "contracts",
        "TTLTRFVAL":       "val_inlakh",
        "OPNINTRST":       "open_int",
        "CHNGINOPNINTRST": "chg_in_oi",
    }
    df.rename(
        columns={k: v for k, v in col_map.items() if k in df.columns},
        inplace=True,
    )

    # Add date
    df["date"] = trade_date.strftime("%Y-%m-%d")

    # Ensure all desired columns exist
    for col in DESIRED_COLS:
        if col not in df.columns:
            df[col] = None

    # Clean string columns
    for col in ["instrument", "symbol", "option_typ"]:
        df[col] = df[col].astype(str).str.strip().str.upper()
        df[col] = df[col].replace({"NAN": "", "NONE": ""})

    # Parse expiry date → YYYY-MM-DD string
    df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce", dayfirst=True)
    df["expiry"] = df["expiry"].dt.strftime("%Y-%m-%d")
    df["expiry"] = df["expiry"].where(df["expiry"].notna(), "")

    # Numeric
    for col in ["strike", "open", "high", "low", "close", "settle_pr", "val_inlakh"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["contracts", "open_int", "chg_in_oi"]:
        # .round() first: some F&O records carry fractional values that can't
        # safely cast straight to Int64 (raises "cannot safely cast float64 to int64")
        df[col] = pd.to_numeric(df[col], errors="coerce").round().astype("Int64")

    # Drop empty symbol rows
    df = df[df["symbol"].str.len() > 0].copy()

    # Keep only our columns
    keep = [c for c in DESIRED_COLS if c in df.columns]
    df = df[keep]

    # Replace pandas NA → Python None for sqlite3
    df = df.where(pd.notna(df), None)

    return df if not df.empty else None


# ─────────────────────────────────────────────────────────────────────────────
# INSERT — builds SQL dynamically from actual table columns
# ─────────────────────────────────────────────────────────────────────────────

def insert_fo_df(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    table_cols = get_fo_columns(conn)
    if not table_cols:
        raise RuntimeError("fo_data table missing!")

    # Only insert columns present in BOTH df and the actual table
    insert_cols = [c for c in DESIRED_COLS if c in table_cols and c in df.columns]
    if not insert_cols:
        raise RuntimeError(
            f"No matching columns!\n  DF has: {df.columns.tolist()}\n  Table has: {table_cols}"
        )

    placeholders = ", ".join(["?"] * len(insert_cols))
    col_str      = ", ".join(insert_cols)
    sql = f"INSERT OR REPLACE INTO fo_data ({col_str}) VALUES ({placeholders})"

    rows = []
    for _, r in df.iterrows():
        row = []
        for c in insert_cols:
            val = r.get(c)
            # Convert pandas Int64 NA / float NaN → None
            if val is None:
                row.append(None)
            elif hasattr(val, '__class__') and val.__class__.__name__ == 'NAType':
                row.append(None)
            elif isinstance(val, float) and pd.isna(val):
                row.append(None)
            else:
                try:
                    row.append(val.item())  # numpy scalar → Python scalar
                except AttributeError:
                    row.append(val)
        rows.append(tuple(row))

    if rows:
        conn.executemany(sql, rows)
        conn.commit()

    return len(rows)


# ─────────────────────────────────────────────────────────────────────────────
# TRADING DATE RANGE (Mon–Fri only; holidays handled by 404)
# ─────────────────────────────────────────────────────────────────────────────

def trading_date_range(start: date, end: date) -> list:
    days, cur = [], start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


# ─────────────────────────────────────────────────────────────────────────────
# MAIN BACKFILL
# ─────────────────────────────────────────────────────────────────────────────

def run_backfill(start: date, end: date, force: bool = False):
    FO_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  MICC F&O Backfill")
    print(f"  Range: {start} → {end}")
    print(f"  DB: {DB_PATH}")
    print(f"{'='*60}\n")

    conn = get_conn()

    # Show pre-existing schema
    existing_cols = get_fo_columns(conn)
    if existing_cols:
        print(f"  Existing fo_data: {len(existing_cols)} cols: {existing_cols}")

    # Setup / patch schema
    setup_table(conn)

    final_cols = get_fo_columns(conn)
    print(f"  Final cols ({len(final_cols)}): {final_cols}\n")

    existing_dates = get_existing_dates(conn) if not force else set()
    print(f"  Already loaded: {len(existing_dates)} dates")

    all_dates = trading_date_range(start, end)
    todo = [d for d in all_dates if d.strftime("%Y-%m-%d") not in existing_dates]
    print(f"  To download: {len(todo)} dates (of {len(all_dates)} trading days)\n")

    if not todo:
        print("  Nothing to do — already complete.")
        conn.close()
        return

    print("  Creating NSE session...")
    session = nse_session()
    print("  Session ready.\n")

    ok = skip = err = rows_total = 0

    for i, trade_date in enumerate(todo, 1):
        date_str = trade_date.strftime("%Y-%m-%d")
        print(f"  [{i:3d}/{len(todo)}] {date_str} ... ", end="", flush=True)

        zip_bytes = download_fo_zip(session, trade_date)
        if zip_bytes is None:
            print("⬛ skip (holiday/no data)")
            skip += 1
            time.sleep(0.3)
            continue

        df = parse_fo_zip(zip_bytes, trade_date)
        if df is None or df.empty:
            print("⚠️  parse failed")
            err += 1
            time.sleep(0.5)
            continue

        # Cache zip locally
        try:
            (FO_DIR / f"fo_{date_str.replace('-','')}.zip").write_bytes(zip_bytes)
        except Exception:
            pass

        try:
            n = insert_fo_df(conn, df)
            rows_total += n
            ok += 1
            print(f"✅ {n:,} rows")
        except Exception as e:
            print(f"❌ insert: {e}")
            err += 1

        time.sleep(0.8)

        if i % 50 == 0:
            print("  Refreshing session...")
            session = nse_session()

    conn.close()

    print(f"\n{'='*60}")
    print(f"  DONE")
    print(f"  Downloaded : {ok}")
    print(f"  Skipped    : {skip} (holidays/weekends)")
    print(f"  Errors     : {err}")
    print(f"  Rows added : {rows_total:,}")
    print(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# LOAD FROM LOCAL ZIPs
# ─────────────────────────────────────────────────────────────────────────────

def load_from_local():
    if not FO_DIR.exists():
        print(f"FO_DIR not found: {FO_DIR}")
        return

    conn = get_conn()
    setup_table(conn)
    existing = get_existing_dates(conn)

    zips = sorted(FO_DIR.glob("fo_*.zip"))
    print(f"\nFound {len(zips)} local zips. Loading missing ones...")

    ok = 0
    for zp in zips:
        try:
            ds = zp.stem.replace("fo_", "")
            trade_date = datetime.strptime(ds, "%Y%m%d").date()
            date_str = trade_date.strftime("%Y-%m-%d")
        except Exception:
            continue
        if date_str in existing:
            continue

        df = parse_fo_zip(zp.read_bytes(), trade_date)
        if df is not None and not df.empty:
            try:
                n = insert_fo_df(conn, df)
                print(f"  {date_str}: {n:,} rows")
                ok += 1
            except Exception as e:
                print(f"  {date_str}: ❌ {e}")

    conn.close()
    print(f"\nLoaded {ok} dates from local cache.")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MICC F&O Backfill")
    parser.add_argument("--probe",    action="store_true", help="Show existing fo_data schema + exit")
    parser.add_argument("--today",    action="store_true")
    parser.add_argument("--from",    dest="from_date", default=None)
    parser.add_argument("--force",   action="store_true", help="Re-download existing dates")
    parser.add_argument("--local",   action="store_true", help="Load from D:/MICC/marketDB/NSE_FO/*.zip")
    args = parser.parse_args()

    if args.probe:
        conn = get_conn()
        print("\n=== fo_data SCHEMA PROBE ===")
        show_fo_schema(conn)
        conn.close()
        sys.exit(0)

    if args.local:
        load_from_local()
        sys.exit(0)

    today = date.today()
    if args.today:
        run_backfill(today, today, force=args.force)
    elif args.from_date:
        try:
            start = datetime.strptime(args.from_date, "%Y-%m-%d").date()
        except ValueError:
            print(f"Bad date: {args.from_date} (need YYYY-MM-DD)")
            sys.exit(1)
        run_backfill(start, today, force=args.force)
    else:
        run_backfill(BACKFILL_FROM, today, force=args.force)
