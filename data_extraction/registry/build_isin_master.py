#!/usr/bin/env python3
"""build_isin_master.py — PHASE 1 closer.

Builds `isin_master` (ISIN <-> NSE symbol mapping with date ranges) so a company
that changed ticker is tracked as ONE continuous entity. ISIN is the stable key;
the symbol is not -- a rename shows up as one ISIN mapped to >1 symbol over time.

Sources (best available, survivorship-free where possible):
  1. Legacy NSE cm-bhavcopy zips that carry ISIN (~2011-2019), monthly-sampled
     -> historical symbol<->ISIN, including renamed/delisted names.
  2. NSE EQUITY_L.csv (current active listings) -> symbol, ISIN, company, listing date.

Outputs:
  isin_master(isin, symbol, company, first_date, last_date, listing_date,
              is_active, source)
  isin_renames(isin, n_symbols, symbols)   -- ISINs seen under multiple symbols

Idempotent. Run:  py -3.14 registry/build_isin_master.py
"""
import io
import re
import sqlite3
import zipfile
from pathlib import Path

import pandas as pd
import requests

DB_PATH = Path(r"D:\marketDB\db\market.db")
LEGACY_DIR = Path(r"D:\MICC\data_storage\raw\bhavcopy\legacy")
EQUITY_L_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
FNAME_RE = re.compile(r"cm(\d{2})([A-Z]{3})(\d{4})bhav", re.I)


def fname_date(p):
    m = FNAME_RE.search(p.name)
    if not m:
        return None
    d, mon, y = m.group(1), m.group(2).upper(), m.group(3)
    if mon not in MONTHS:
        return None
    return f"{y}-{MONTHS[mon]:02d}-{int(d):02d}"


def monthly_sample(years=range(2011, 2020)):
    """One legacy zip per (year, month) -- earliest day -- for ISIN-bearing years."""
    picked = {}
    for yr in years:
        d = LEGACY_DIR / str(yr)
        if not d.exists():
            continue
        for z in d.glob("*.zip"):
            dt = fname_date(z)
            if not dt:
                continue
            key = dt[:7]                      # YYYY-MM
            if key not in picked or dt < picked[key][0]:
                picked[key] = (dt, z)
    return [v for _, v in sorted(picked.items())]


def parse_legacy(files):
    rows = []
    for dt, z in files:
        try:
            with zipfile.ZipFile(z) as zf:
                name = zf.namelist()[0]
                df = pd.read_csv(io.BytesIO(zf.read(name)))
        except Exception:
            continue
        df.columns = [c.strip().upper() for c in df.columns]
        if "ISIN" not in df.columns or "SYMBOL" not in df.columns:
            continue
        sub = df[df.get("SERIES", "EQ").astype(str).str.strip().isin(["EQ", "BE"])] \
            if "SERIES" in df.columns else df
        for sym, isin in zip(sub["SYMBOL"].astype(str).str.strip(),
                             sub["ISIN"].astype(str).str.strip()):
            if isin and isin != "nan" and isin.startswith("IN"):
                rows.append((isin, sym, dt))
    return pd.DataFrame(rows, columns=["isin", "symbol", "date"])


def fetch_equity_l():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*",
                      "Referer": "https://www.nseindia.com/"})
    try:
        s.get("https://www.nseindia.com", timeout=12)
    except Exception:
        pass
    try:
        r = s.get(EQUITY_L_URL, timeout=30)
        df = pd.read_csv(io.StringIO(r.text))
    except Exception as e:
        print(f"  EQUITY_L fetch failed ({str(e)[:50]}) -- continuing legacy-only", flush=True)
        return None
    df.columns = [c.strip().upper() for c in df.columns]
    return df


def main():
    print("Sampling legacy ISIN-bearing bhavcopy (monthly, 2011-2019) ...", flush=True)
    files = monthly_sample()
    print(f"  {len(files)} monthly files", flush=True)
    leg = parse_legacy(files)
    print(f"  {len(leg):,} (isin,symbol,date) obs, "
          f"{leg['isin'].nunique():,} ISINs, {leg['symbol'].nunique():,} symbols", flush=True)

    agg = leg.groupby(["isin", "symbol"]).agg(
        first_date=("date", "min"), last_date=("date", "max"),
        n_obs=("date", "count")).reset_index()
    agg["company"] = None
    agg["listing_date"] = None
    agg["is_active"] = 0
    agg["source"] = "legacy"

    print("Fetching EQUITY_L.csv (current active) ...", flush=True)
    eq = fetch_equity_l()
    if eq is not None:
        col_isin = next((c for c in eq.columns if "ISIN" in c), None)
        col_name = next((c for c in eq.columns if "NAME" in c), None)
        col_list = next((c for c in eq.columns if "LISTING" in c), None)
        cur = pd.DataFrame({
            "isin": eq[col_isin].astype(str).str.strip(),
            "symbol": eq["SYMBOL"].astype(str).str.strip(),
            "company": eq[col_name].astype(str).str.strip() if col_name else None,
            "listing_date": eq[col_list].astype(str).str.strip() if col_list else None,
        })
        cur = cur[cur["isin"].str.startswith("IN")]
        print(f"  {len(cur):,} active listings", flush=True)
        # mark active rows in agg; add active rows missing from legacy
        active_map = dict(zip(cur["symbol"], cur["isin"]))
        agg.loc[agg.apply(lambda r: active_map.get(r["symbol"]) == r["isin"], axis=1),
                "is_active"] = 1
        have = set(zip(agg["isin"], agg["symbol"]))
        add = cur[~cur.apply(lambda r: (r["isin"], r["symbol"]) in have, axis=1)].copy()
        add["first_date"] = add["listing_date"]
        add["last_date"] = None
        add["n_obs"] = 0
        add["is_active"] = 1
        add["source"] = "equity_l"
        agg = pd.concat([agg, add[agg.columns]], ignore_index=True)

    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("DROP TABLE IF EXISTS isin_master")
    conn.execute("""CREATE TABLE isin_master (
        isin TEXT, symbol TEXT, company TEXT, first_date TEXT, last_date TEXT,
        listing_date TEXT, is_active INTEGER, source TEXT,
        PRIMARY KEY(isin, symbol))""")
    conn.executemany(
        "INSERT OR REPLACE INTO isin_master "
        "(isin,symbol,company,first_date,last_date,listing_date,is_active,source) "
        "VALUES (?,?,?,?,?,?,?,?)",
        agg[["isin", "symbol", "company", "first_date", "last_date",
             "listing_date", "is_active", "source"]].itertuples(index=False, name=None))
    conn.execute("CREATE INDEX idx_im_isin ON isin_master(isin)")
    conn.execute("CREATE INDEX idx_im_symbol ON isin_master(symbol)")

    # rename view: one ISIN under multiple symbols
    conn.execute("DROP TABLE IF EXISTS isin_renames")
    conn.execute("""CREATE TABLE isin_renames AS
        SELECT isin, COUNT(DISTINCT symbol) AS n_symbols,
               GROUP_CONCAT(DISTINCT symbol) AS symbols
        FROM isin_master GROUP BY isin HAVING COUNT(DISTINCT symbol) > 1""")
    conn.commit()

    # ---- validation ----
    print("\n=== VALIDATION ===", flush=True)
    ni, ns = conn.execute("SELECT COUNT(DISTINCT isin), COUNT(DISTINCT symbol) FROM isin_master").fetchone()
    na = conn.execute("SELECT COUNT(*) FROM isin_master WHERE is_active=1").fetchone()[0]
    nr = conn.execute("SELECT COUNT(*) FROM isin_renames").fetchone()[0]
    print(f"isin_master: {ni:,} ISINs, {ns:,} symbols, {na:,} active rows", flush=True)
    print(f"isin_renames: {nr:,} ISINs seen under >1 symbol (ticker changes/renames)", flush=True)
    print("\nSample renames (ISIN -> symbols):", flush=True)
    for r in conn.execute("SELECT isin, symbols FROM isin_renames ORDER BY n_symbols DESC LIMIT 12").fetchall():
        print(f"  {r[0]}  ->  {r[1]}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
