#!/usr/bin/env python3
"""backfill_delivery.py — Deep delivery-% backfill into stock_delivery from the
LOCAL archive (offline).

Sources (data_storage/raw/bhavcopy):
  - mto/<year>/MTO_<DDMMYYYY>.DAT          (2005 .. ~2019)  EQ delivery
  - secfull/<year>/sec_bhavdata_full_*.csv (2020 .. now)    DELIV_QTY / DELIV_PER

Writes EQ rows to stock_delivery (symbol,date,total_traded_qty,delivery_qty,
delivery_percent), INSERT OR REPLACE. Idempotent.

Run:  py -3.14 market/backfill_delivery.py
"""
import sqlite3, glob, time
from pathlib import Path
from datetime import datetime

import pandas as pd

DB_PATH     = Path(r"D:\MICC\marketDB\db\market.db")
ARCHIVE     = Path(r"D:\MICC\data_storage\raw\bhavcopy")
MTO_DIR     = ARCHIVE / "mto"
SECFULL_DIR = ARCHIVE / "secfull"


def ensure_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS stock_delivery (
        symbol TEXT, date TEXT, total_traded_qty REAL, delivery_qty REAL,
        delivery_percent REAL, PRIMARY KEY (symbol, date))""")
    conn.commit()


def parse_mto(path):
    """MTO_<DDMMYYYY>.DAT: data lines '20,SrNo,SYMBOL,SERIES,QtyTrd,DelivQty,DelivPct'."""
    name = Path(path).stem            # MTO_01032005
    try:
        d = datetime.strptime(name.split("_")[1], "%d%m%Y").strftime("%Y-%m-%d")
    except Exception:
        return []
    rows = []
    try:
        with open(path, "r", errors="ignore") as f:
            for line in f:
                p = line.strip().split(",")
                if len(p) >= 7 and p[0] == "20" and p[3].strip() == "EQ":
                    try:
                        rows.append((p[2].strip(), d, float(p[4]), float(p[5]), float(p[6])))
                    except ValueError:
                        pass
    except Exception:
        return []
    return rows


def _num(s):
    return pd.to_numeric(s.astype(str).str.replace(" ", "").replace({"-": "0", "": "0"}),
                         errors="coerce").fillna(0)


def parse_secfull(path):
    try:
        df = pd.read_csv(path)
    except Exception:
        return []
    df.columns = [str(c).strip().upper() for c in df.columns]
    if "DELIV_QTY" not in df.columns:
        return []
    df = df[df["SERIES"].astype(str).str.strip() == "EQ"]
    if df.empty:
        return []
    dt = pd.to_datetime(df["DATE1"].astype(str).str.strip(), format="%d-%b-%Y", errors="coerce")
    out = pd.DataFrame({
        "symbol": df["SYMBOL"].astype(str).str.strip(),
        "date":   dt.dt.strftime("%Y-%m-%d"),
        "ttq":    _num(df["TTL_TRD_QNTY"]),
        "dq":     _num(df["DELIV_QTY"]),
        "dp":     _num(df["DELIV_PER"]),
    }).dropna(subset=["date"])
    return [tuple(r) for r in out.itertuples(index=False, name=None)]


def main():
    files = []
    if MTO_DIR.exists():
        for y in sorted(p.name for p in MTO_DIR.iterdir() if p.is_dir()):
            files += [("mto", f) for f in sorted(glob.glob(str(MTO_DIR / y / "*.DAT")))]
    if SECFULL_DIR.exists():
        for y in sorted(p.name for p in SECFULL_DIR.iterdir() if p.is_dir()):
            files += [("secfull", f) for f in sorted(glob.glob(str(SECFULL_DIR / y / "*.csv")))]

    print(f"Backfilling delivery from {len(files):,} files ...", flush=True)
    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=180000")
    ensure_table(conn)

    total = done = 0
    t0 = time.time()
    for kind, f in files:
        rows = parse_mto(f) if kind == "mto" else parse_secfull(f)
        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO stock_delivery "
                "(symbol,date,total_traded_qty,delivery_qty,delivery_percent) VALUES (?,?,?,?,?)", rows)
            total += len(rows)
        done += 1
        if done % 300 == 0:
            conn.commit()
            print(f"  {done:,}/{len(files):,} files | {total:,} rows | {time.time()-t0:.0f}s", flush=True)
    conn.commit()

    mn, mx, n, ns = conn.execute(
        "SELECT MIN(date),MAX(date),COUNT(*),COUNT(DISTINCT symbol) FROM stock_delivery").fetchone()
    conn.close()
    print(f"DONE: {total:,} rows processed | stock_delivery now {n:,} rows, "
          f"{ns:,} symbols, {mn} -> {mx} ({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
