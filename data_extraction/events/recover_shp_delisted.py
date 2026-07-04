#!/usr/bin/env python3
"""recover_shp_delisted.py — Part 4 Stage 3: best-effort SHP recovery for
delisted/suspended names, via the OFFICIAL BSE API only.

Stage-3 probe (2026-07-05) proved recovery is not an archive hunt: BSE's
SHPQNewFormat serves a delisted scrip's full filing history (verified on
DHFL/511072 — 19 PIT-timestamped filings up to its Jun-2021 delisting), and
ListofScripData exposes the Delisted (4,612) + Suspended (1,226) lists. So
"recovery" = extending Stage-1 enumeration to those lists, through the exact
same idempotent, throttled, PIT-lag-gated machinery in fetch_shp.py.

Targets: scrips in bse_scrip_master with listing_status != 'Active' whose ISIN
appears in shp_pit_universe with a missing SHP status (i.e., names in OUR
survivorship-free spine, not all 5,838 dead scrips — bounded by design; a name
that died pre-2016 is auto-excluded by the PIT lag gate after 1 cheap call).

Legitimacy gate: official JSON endpoints only. PIT gate: identical
--max-filing-lag-days discipline; a filing without a trustworthy timestamp is
never PIT-usable. Outcomes land in shp_recovery_log (one row per scrip) so
re-runs skip known-dead cells — recovery is auditable and idempotent.

DO NOT run concurrently with the main fetch_shp backfill (one fetcher per host).

Run:  py -3.14 events/recover_shp_delisted.py [--budget-min 240] [--retry-dead]
      then rebuild:  py -3.14 registry/build_shp_pit_universe.py
"""
import argparse
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_shp import (Client, enumerate_scrip, process_filing,   # noqa: E402
                       keep_system_awake, log)
from shp_schema import ensure_schema                              # noqa: E402

DB_PATH = Path(r"D:\marketDB\db\market.db")
LOG_DDL = """CREATE TABLE IF NOT EXISTS shp_recovery_log (
    scrip_code    TEXT PRIMARY KEY,
    listing_status TEXT,   -- Delisted | Suspended (at attempt time)
    route         TEXT,    -- 'bse_shpq_newformat'
    outcome       TEXT,    -- recovered | nothing_pit_usable | enum_failed
    filings_found INTEGER, -- lag-gated filings enumerated for this scrip
    attempted_at  TEXT
)"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-min", type=int, default=240)
    ap.add_argument("--max-filing-lag-days", type=int, default=400)
    ap.add_argument("--limit", type=int, default=0, help="first N targets (testing)")
    ap.add_argument("--retry-dead", action="store_true",
                    help="re-attempt scrips already logged as nothing_pit_usable/enum_failed")
    a = ap.parse_args()

    keep_system_awake()
    t0 = time.time()
    deadline = t0 + a.budget_min * 60 if a.budget_min else None

    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    ensure_schema(conn)
    conn.execute(LOG_DDL)

    # targets: dead-listed scrips whose ISIN is in our spine with SHP missing
    targets = conn.execute("""
        SELECT DISTINCT m.scrip_code, m.isin, m.company_name, m.listing_status,
               m.segment_guess
        FROM bse_scrip_master m
        JOIN shp_pit_universe u ON u.isin = m.isin
        WHERE m.listing_status != 'Active'
          AND u.shp_status IN ('missing_delisted', 'missing_active')
        ORDER BY m.scrip_code""").fetchall()
    done = {s for s, in conn.execute("SELECT scrip_code FROM shp_recovery_log"
                                     + ("" if a.retry_dead else ""))}
    if not a.retry_dead:
        targets = [t for t in targets if t[0] not in done]
    if a.limit:
        targets = targets[:a.limit]
    log.info(f"RECOVERY: {len(targets)} dead-listed scrips to attempt "
             f"(skip-already-logged={not a.retry_dead})")

    cli = Client()
    stats = dict(enum_ok=0, enum_fail=0, new_filings=0, revisions=0, parsed=0,
                 parse_fail=0, raw_fail=0, inst_parsed=0, inst_fail=0, calls=0)
    now = lambda: datetime.now().isoformat(timespec="seconds")

    for i, (scrip, isin, name, lstatus, seg) in enumerate(targets, 1):
        if deadline and time.time() > deadline:
            log.warning(f"recovery budget reached at {i}/{len(targets)} — resumes next run")
            break
        before = stats["new_filings"]
        enum_failed_before = stats["enum_fail"]
        enumerate_scrip(cli, conn, {"scrip": scrip, "isin": isin or "",
                                    "name": name, "segment": seg}, stats)
        if stats["enum_fail"] > enum_failed_before:
            outcome, found = "enum_failed", 0
        else:
            found = conn.execute(
                "SELECT COUNT(*) FROM shp_filing WHERE scrip_code=? "
                "AND is_current_version=1 AND pit_date IS NOT NULL "
                "AND julianday(pit_date)-julianday(quarter_end_date) <= ?",
                (scrip, a.max_filing_lag_days)).fetchone()[0]
            outcome = "recovered" if found else "nothing_pit_usable"
            # fetch+parse this scrip's lag-gated filings right away (small per-scrip)
            todo = conn.execute("""
                SELECT f.filing_id, f.scrip_code, f.qtrid, f.source_url, f.file_hash,
                       f.raw_blob_path, f.parse_status,
                       EXISTS(SELECT 1 FROM shp_institutional_summary s
                              WHERE s.filing_id=f.filing_id)
                FROM shp_filing f
                WHERE f.scrip_code=? AND f.is_current_version=1
                  AND julianday(f.pit_date)-julianday(f.quarter_end_date) <= ?
                  AND (f.parse_status IN ('unparsed','parse_failed')
                       OR NOT EXISTS(SELECT 1 FROM shp_institutional_summary s
                                     WHERE s.filing_id=f.filing_id))
                ORDER BY f.qtrid DESC""", (scrip, a.max_filing_lag_days)).fetchall()
            for f in todo:
                if deadline and time.time() > deadline:
                    break
                process_filing(cli, conn, f, stats)
        conn.execute("INSERT OR REPLACE INTO shp_recovery_log VALUES (?,?,?,?,?,?)",
                     (scrip, lstatus, "bse_shpq_newformat", outcome, found, now()))
        conn.commit()
        if i % 25 == 0:
            log.info(f"  recovery {i}/{len(targets)} (+{stats['new_filings']} filings, "
                     f"parsed {stats['parsed']}, inst {stats['inst_parsed']})")

    outcomes = conn.execute("SELECT outcome, COUNT(*), COALESCE(SUM(filings_found),0) "
                            "FROM shp_recovery_log GROUP BY outcome").fetchall()
    log.info(f"RECOVERY done in {(time.time()-t0)/60:.1f} min | {stats} | "
             f"log outcomes: {outcomes}")
    log.info("NEXT: py -3.14 registry/build_shp_pit_universe.py  (re-join the universe)")
    conn.close()


if __name__ == "__main__":
    main()
