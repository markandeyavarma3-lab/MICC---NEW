#!/usr/bin/env python3
"""build_shp_pit_universe.py — Part 4 Stage 3: survivorship-free PIT universe for SHP.

WHY: Stage 2 found SHP enumeration used today's Active list only, so names that
delisted (blowups, distress — exactly what the pledge signal must catch) are
invisible. A pledge test on that universe is structurally tilted toward "pledge
didn't hurt". This builds the survivorship-free quarterly denominator from the
price warehouse (which already contains then-listed-now-delisted names since 2005)
and joins SHP onto it, making the hole measurable instead of invisible.

MEMBERSHIP RULE (documented, principled): symbol S is a member of quarter Q iff
  (a) S traded on >= 10 days within Q            (filters blips/data noise), AND
  (b) S's last trade in Q is within 21 calendar  (SHP is a quarter-END snapshot;
      days of Q's end                             the name must be alive at the end)
Fund/ETF ISINs (INF...) are excluded per house rule (NAV-creep names, not equities).

IDENTITY: symbol -> ISIN via isin_master resolved AS-OF the quarter end (rename-safe);
ISIN -> BSE scrip via bse_scrip_master (Active+Delisted+Suspended, 10,751 scrips)
with shp_filing as fallback. delisted_today = last trade anywhere < max(date) - 90d.

STATUS per (quarter x symbol):  shp_status in
  present            a current-version, PIT-lag-gated filing exists for that quarter
  missing_active     no filing; name still trades today
  missing_delisted   no filing; name delisted today   <- THE ADVERSE-BIAS BUCKET
with status_reason in  has_filing | no_filing | no_scrip_mapping | no_isin_mapping.
(Recovery outcomes are tracked separately in shp_recovery_log; rebuilds here never
lose them because this table is derived and the log is not.)

Idempotent: full DELETE+INSERT rebuild of the derived table on every run.

Run:  py -3.14 registry/build_shp_pit_universe.py [--lag-days 400]
"""
import argparse
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
FIRST_QUARTER = "2016-03-31"        # empirical PIT floor (Stage 2)
MIN_TRADING_DAYS = 10
LAST_TRADE_WINDOW_DAYS = 21
DELISTED_STALENESS_DAYS = 90

DDL = """CREATE TABLE IF NOT EXISTS shp_pit_universe (
    quarter_end    TEXT,
    symbol         TEXT,     -- NSE symbol (spine identity)
    isin           TEXT,     -- as-of quarter end via isin_master (rename-safe)
    scrip_code     TEXT,     -- BSE scrip via bse_scrip_master/shp_filing (NULL = unmapped)
    tier           TEXT,     -- top100 | top250 | top500 | other (from pit_universe)
    trading_days   INTEGER,  -- days traded within the quarter
    delisted_today INTEGER,  -- 1 if last trade anywhere < spine max date - 90d
    shp_status     TEXT,     -- present | missing_active | missing_delisted
    status_reason  TEXT,     -- has_filing | no_filing | no_scrip_mapping | no_isin_mapping
    table1_parsed  INTEGER,  -- 1 if the filing's Table I is parsed (backfill progress)
    filing_id      TEXT,     -- the matched current-version filing (NULL if missing)
    built_at       TEXT,
    PRIMARY KEY (quarter_end, symbol)
)"""


def quarter_ends(first, last):
    out, y, m = [], int(first[:4]), int(first[5:7])
    ends = {3: "-03-31", 6: "-06-30", 9: "-09-30", 12: "-12-31"}
    while True:
        qe = f"{y}{ends[m]}"
        if qe > last:
            break
        out.append(qe)
        m += 3
        if m > 12:
            m, y = 3, y + 1
    return out


def quarter_start(qe):
    y, m = int(qe[:4]), int(qe[5:7])
    return f"{y}-{m-2:02d}-01"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lag-days", type=int, default=400,
                    help="PIT trust gate, same as the fetcher (default 400)")
    a = ap.parse_args()

    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute(DDL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spu_status ON shp_pit_universe(shp_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spu_isin ON shp_pit_universe(isin)")

    max_date = conn.execute("SELECT MAX(date) FROM stock_data").fetchone()[0]
    stale_cut = (datetime.strptime(max_date, "%Y-%m-%d")
                 - timedelta(days=DELISTED_STALENESS_DAYS)).strftime("%Y-%m-%d")
    quarters = quarter_ends(FIRST_QUARTER, max_date)
    print(f"spine max date {max_date} | delisted-today cut {stale_cut} | "
          f"{len(quarters)} quarters {quarters[0]}..{quarters[-1]}", flush=True)

    # ---- identity maps (loaded once) -------------------------------------
    # symbol -> [(isin, first_date, last_date)]  (rename-safe as-of resolution)
    sym_isin = {}
    for isin, sym, fd, ld in conn.execute(
            "SELECT isin, symbol, first_date, last_date FROM isin_master"):
        sym_isin.setdefault(sym, []).append((isin, fd or "0000", ld or "9999"))

    def isin_asof(sym, qe):
        rows = sym_isin.get(sym)
        if not rows:
            return None
        for isin, fd, ld in rows:
            if fd <= qe <= ld:
                return isin
        return max(rows, key=lambda r: r[2])[0]   # fallback: latest-known ISIN

    # isin -> scrip: bse_scrip_master (incl. Delisted/Suspended), shp_filing fallback
    isin_scrip = {i: s for s, i in conn.execute(
        "SELECT scrip_code, isin FROM bse_scrip_master WHERE isin != ''")}
    for i, s in conn.execute("SELECT DISTINCT isin, scrip_code FROM shp_filing "
                             "WHERE isin IS NOT NULL AND isin != ''"):
        isin_scrip.setdefault(i, s)

    # delisted-today per symbol
    delisted = {s: (1 if md < stale_cut else 0) for s, md in conn.execute(
        "SELECT symbol, MAX(date) FROM stock_data GROUP BY symbol")}

    # PIT-lag-gated current filings: (scrip, quarter_end) -> (filing_id, parsed)
    filings = {}
    for scrip, qe, fid, ps in conn.execute(
            "SELECT scrip_code, quarter_end_date, filing_id, parse_status FROM shp_filing "
            "WHERE is_current_version=1 AND pit_date IS NOT NULL "
            "AND julianday(pit_date)-julianday(quarter_end_date) <= ?", (a.lag_days,)):
        filings[(scrip, qe)] = (fid, 1 if ps == "parsed" else 0)

    # liquidity tiers from pit_universe: last rebal on/before each quarter end
    rebals = [r for r, in conn.execute(
        "SELECT DISTINCT rebal_date FROM pit_universe ORDER BY rebal_date")]
    tier_cache = {}
    def tiers_for(qe):
        if qe in tier_cache:
            return tier_cache[qe]
        rd = max((r for r in rebals if r <= qe), default=None)
        t = {}
        if rd:
            for sym, t1, t2, t5 in conn.execute(
                    "SELECT symbol, top100, top250, top500 FROM pit_universe "
                    "WHERE rebal_date=?", (rd,)):
                t[sym] = "top100" if t1 else "top250" if t2 else "top500" if t5 else "other"
        tier_cache[qe] = t
        return t

    # ---- build ------------------------------------------------------------
    conn.execute("DELETE FROM shp_pit_universe")
    now = datetime.now().isoformat(timespec="seconds")
    n_rows = 0
    for qe in quarters:
        qs = quarter_start(qe)
        near_cut = (datetime.strptime(qe, "%Y-%m-%d")
                    - timedelta(days=LAST_TRADE_WINDOW_DAYS)).strftime("%Y-%m-%d")
        members = conn.execute(
            "SELECT symbol, COUNT(*) AS td, MAX(date) AS lt FROM stock_data "
            "WHERE date BETWEEN ? AND ? GROUP BY symbol "
            "HAVING td >= ? AND lt >= ?",
            (qs, qe, MIN_TRADING_DAYS, near_cut)).fetchall()
        tmap = tiers_for(qe)
        batch = []
        for sym, td, _lt in members:
            isin = isin_asof(sym, qe)
            if isin and isin.startswith("INF"):     # fund/ETF — house-rule exclusion
                continue
            scrip = isin_scrip.get(isin) if isin else None
            fid, parsed = filings.get((scrip, qe), (None, 0)) if scrip else (None, 0)
            dl = delisted.get(sym, 0)
            if fid:
                status, reason = "present", "has_filing"
            else:
                status = "missing_delisted" if dl else "missing_active"
                reason = ("no_isin_mapping" if not isin
                          else "no_scrip_mapping" if not scrip else "no_filing")
            batch.append((qe, sym, isin, scrip, tmap.get(sym, "other"), td, dl,
                          status, reason, parsed, fid, now))
        conn.executemany(
            "INSERT OR REPLACE INTO shp_pit_universe VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            batch)
        n_rows += len(batch)
    conn.commit()

    # ---- summary ----------------------------------------------------------
    print(f"built {n_rows:,} scrip-quarter rows", flush=True)
    print("\nstatus totals:", flush=True)
    for st, rs, n in conn.execute(
            "SELECT shp_status, status_reason, COUNT(*) AS n FROM shp_pit_universe "
            "GROUP BY shp_status, status_reason ORDER BY shp_status, n DESC"):
        print(f"  {st:>17} | {rs:<17} {n:>7,}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
