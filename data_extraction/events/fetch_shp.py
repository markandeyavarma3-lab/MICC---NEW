#!/usr/bin/env python3
"""fetch_shp.py — Part 4 Stage 1: BSE quarterly shareholding patterns (full universe).

Route verified 2026-07-04 (docs/shp_extraction_routes.md): the BSE JSON API behind
api.bseindia.com. Per scrip, SHPQNewFormat enumerates every SHP filing with the
exchange filing timestamp (the PIT anchor, populated from March 2016 onward);
per (scrip, quarter) the SHPSUMMARY endpoint serves parsed Table I and the raw
XBRL instance is downloadable.

What one run does (all steps idempotent — re-running is a no-op for stored data):
  1. ENUMERATE  universe from ListofScripData (mainboard + SME in one list);
                per scrip, upsert one shp_filing row per filing WITH a filing
                timestamp (2016+). Revised filings insert a NEW row
                (is_revision_of -> old id) and flip the old to non-current.
  2. RAW+PARSE  for current filings in the most recent --quarters N (default 8):
                download raw XBRL to data_storage/raw/shp/, sha256 it, fetch the
                Table I summary JSON, store rows in shp_category_summary.
  3. NOTIFY     (--notify) push a summary to ntfy (MICC_NTFY_TOPIC) — new filings,
                revisions, parse failures, coverage.

Stage discipline: data acquisition ONLY — nothing here touches scoring/idea_card.

Usage:
  py -3.14 events/fetch_shp.py                          # full sweep (long on first run)
  py -3.14 events/fetch_shp.py --limit 15               # smoke test on 15 scrips
  py -3.14 events/fetch_shp.py --scrips 500325,532540   # specific scrips
  py -3.14 events/fetch_shp.py --quarters 8 --budget-min 80 --notify   # weekly job
  py -3.14 events/fetch_shp.py --enumerate-only         # just refresh the filing index
"""
import argparse
import hashlib
import json
import logging
import os
import random
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import certifi
import requests

sys.path.insert(0, str(Path(__file__).parent))
from shp_schema import ensure_schema  # noqa: E402

os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

DB_PATH  = Path(r"D:\marketDB\db\market.db")
RAW_DIR  = Path(r"D:\MICC\data_storage\raw\shp")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\fetch_shp.log")
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("fetch_shp")

API  = "https://api.bseindia.com/BseIndiaAPI/api"
SITE = "https://www.bseindia.com"
HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.bseindia.com/",
    "Origin": "https://www.bseindia.com",
}
SME_GROUPS = {"M", "MT", "MS"}
THROTTLE = 0.35          # seconds between API calls (+ jitter)
MONTH_END = {"March": "03-31", "June": "06-30", "September": "09-30", "December": "12-31"}


# ── HTTP session ─────────────────────────────────────────────────────────────
def new_session():
    s = requests.Session()
    s.headers.update(HDRS)
    try:
        s.get(SITE + "/", timeout=20)   # prime cookies
    except Exception as e:
        log.warning(f"cookie prime failed (continuing): {e}")
    return s


class Client:
    """Throttled GET with one re-prime retry on non-JSON/HTTP failure."""
    def __init__(self):
        self.s = new_session()
        self.calls = 0

    def _sleep(self):
        time.sleep(THROTTLE + random.uniform(0, 0.15))

    def get_json(self, url):
        for attempt in (1, 2):
            self._sleep()
            self.calls += 1
            try:
                r = self.s.get(url, timeout=30)
                if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                    return r.json()
                log.warning(f"non-JSON HTTP {r.status_code} (try {attempt}): {url[:120]}")
            except Exception as e:
                log.warning(f"GET failed (try {attempt}) {type(e).__name__}: {url[:120]}")
            if attempt == 1:
                self.s = new_session()
        return None

    def get_bytes(self, url):
        for attempt in (1, 2):
            self._sleep()
            self.calls += 1
            try:
                r = self.s.get(url, timeout=60)
                if r.status_code == 200 and len(r.content) > 500:
                    return r.content
                log.warning(f"raw HTTP {r.status_code} len={len(r.content)} (try {attempt}): {url[:120]}")
            except Exception as e:
                log.warning(f"raw GET failed (try {attempt}) {type(e).__name__}: {url[:120]}")
            if attempt == 1:
                self.s = new_session()
        return None


# ── helpers ──────────────────────────────────────────────────────────────────
def quarter_end(qtr_name):
    """'March 2026' -> '2026-03-31'"""
    try:
        month, year = qtr_name.strip().split()
        return f"{year}-{MONTH_END[month]}"
    except Exception:
        return None


def filing_identity(scrip, qtrid, xbrl_file, broadcast):
    basis = xbrl_file or broadcast or "na"
    h = hashlib.sha1(basis.encode()).hexdigest()[:10]
    return f"bse:{scrip}:{qtrid:g}:{h}"


def to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def to_real(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── step 1: universe ─────────────────────────────────────────────────────────
def fetch_universe(cli):
    url = f"{API}/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active"
    data = cli.get_json(url)
    if not data:
        log.error("universe fetch failed")
        return []
    uni = []
    for x in data:
        scrip = str(x.get("SCRIP_CD", "")).strip()
        if not scrip:
            continue
        grp = str(x.get("GROUP", "") or "").strip()
        uni.append({
            "scrip": scrip,
            "name": (x.get("Issuer_Name") or x.get("Scrip_Name") or "").strip(),
            "isin": (x.get("ISIN_NUMBER") or "").strip(),
            "segment": "sme" if grp in SME_GROUPS else "mainboard",
        })
    log.info(f"universe: {len(uni)} active scrips "
             f"({sum(1 for u in uni if u['segment']=='sme')} sme)")
    return uni


# ── step 2: enumerate filings per scrip ──────────────────────────────────────
def enumerate_scrip(cli, conn, u, stats):
    data = cli.get_json(f"{API}/SHPQNewFormat/w?scripcode={u['scrip']}")
    if data is None:
        stats["enum_fail"] += 1
        return
    now = datetime.now().isoformat(timespec="seconds")
    # BSE can list MULTIPLE rows for the same quarter (original + refiled version,
    # both status 'New', newest first). Group by qtrid and process versions in
    # broadcast-time ASCENDING order so the latest version ends up current and
    # is_revision_of chains old -> new.
    per_qtr = {}
    for r in data.get("Table") or []:
        filed = r.get("filing_date_time")
        if not filed:
            continue                       # pre-2016: no PIT timestamp -> Stage 2/3
        qtrid = to_real(r.get("qtrid"))
        qend = quarter_end(r.get("qtr") or "")
        if qtrid is None or qend is None:
            continue
        status = "revised" if (r.get("status") or "").strip().lower() == "revised" else "new"
        # PIT anchor = timestamp of the version served NOW (revised data was not
        # knowable at the original filing time)
        broadcast = r.get("revised_date_time") if (status == "revised" and r.get("revised_date_time")) else filed
        per_qtr.setdefault(qtrid, []).append(
            {"qend": qend, "status": status, "filed": filed, "broadcast": broadcast,
             "xbrl": (r.get("XbrlFile") or "").strip()})
    for qtrid, versions in per_qtr.items():
        versions.sort(key=lambda v: v["broadcast"])
        for v in versions:
            qend, status, filed, broadcast, xbrl_file = (
                v["qend"], v["status"], v["filed"], v["broadcast"], v["xbrl"])
            fid = filing_identity(u["scrip"], qtrid, xbrl_file, broadcast)
            cur = conn.execute(
                "SELECT filing_id FROM shp_filing WHERE scrip_code=? AND qtrid=? "
                "AND is_current_version=1", (u["scrip"], qtrid)).fetchone()
            if cur and cur[0] == fid:
                continue                   # unchanged -> no-op
            known = conn.execute("SELECT 1 FROM shp_filing WHERE filing_id=?",
                                 (fid,)).fetchone()
            if known:
                continue                   # already stored as a superseded version
            prev_id = None
            if cur:                        # a different version exists -> revision
                prev_id = cur[0]
                conn.execute("UPDATE shp_filing SET is_current_version=0 "
                             "WHERE filing_id=?", (prev_id,))
                stats["revisions"] += 1
                log.info(f"revision: {u['scrip']} qtr {qtrid:g} {prev_id} -> {fid}")
            conn.execute(
                """INSERT OR IGNORE INTO shp_filing
                   (filing_id, scrip_code, isin, cin, company_name, exchange_segment,
                    source_exchange, quarter_end_date, qtrid, filing_status,
                    first_filed_datetime, broadcast_datetime, pit_date, source_route,
                    source_url, raw_format, raw_blob_path, file_hash, is_revision_of,
                    is_current_version, fetched_at, parse_status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,'unparsed')""",
                (fid, u["scrip"], u["isin"], None, u["name"], u["segment"], "bse",
                 qend, qtrid, status, filed, broadcast,
                 (broadcast or "")[:10] or None, "bse_shpq_newformat",
                 f"{SITE}/XBRLFILES/SHPXBRLDataXML/{xbrl_file}" if xbrl_file else None,
                 "xbrl_xml", None, None, prev_id, now))
            stats["new_filings"] += 1
    conn.commit()
    stats["enum_ok"] += 1


# ── step 3: raw XBRL + Table I parse ─────────────────────────────────────────
def parse_summary_json(payload):
    """SHPSUMMARY Table1 -> list of category rows (defensive on field names)."""
    out = []
    for i, row in enumerate(payload.get("Table1") or []):
        pledged = None
        for k, v in row.items():
            lk = k.lower()
            if "pledge" in lk and ("per" in lk or "pct" in lk):
                pledged = to_real(v)
                break
        out.append((
            i,
            (row.get("Fld_Code") or "").strip(),
            (row.get("Fld_ShortCatg") or row.get("Fld_ShortName") or "").strip(),
            (row.get("FLD_SUBCATEGORY") or row.get("Fld_SubCategory") or None),
            (row.get("FLD_LEVEL") or row.get("Fld_Level") or None),
            to_int(row.get("Fld_NoOfShareHolders")),
            to_int(row.get("Fld_TotalNoOfShares")),
            to_real(row.get("Fld_TotalPercentageOf_A_B_C2")),
            pledged,
        ))
    return out


def parse_pubshold_json(payload):
    """SHPPubShold (Table III) Table1 -> institutional sub-category rows.

    Each institution type appears as an AGGREGATE row (Fld_ShareHolderName NULL,
    e.g. 'Foreign Portfolio Investors Category I' = 17.57%) optionally followed by
    NAMED >=1% holder rows NESTED inside it (Fld_ShareHolderName set, e.g. 'Government
    Of Singapore' = 1.88%). The named rows are a SUBSET of the aggregate -- summing a
    level's rows double-counts. We store both, flagged by is_aggregate, so downstream
    FPI/DII signal code filters is_aggregate=1 and the named holders remain available
    for later SAST/holder-level work. Also stores the B1/B2/B3/B4 subtotal rows."""
    out = []
    for i, row in enumerate(payload.get("Table1") or []):
        cat = (row.get("Fld_ShortCatg") or "").strip()
        sub = row.get("Fld_SubCategory") or row.get("FLD_SUBCATEGORY")
        lvl = row.get("Fld_Level") or row.get("FLD_LEVEL")
        if not (sub or lvl):
            continue
        name = row.get("Fld_ShareHolderName")
        name = name.strip() if isinstance(name, str) and name.strip() else None
        out.append((
            i, cat, sub, lvl, name, 1 if name is None else 0,
            to_int(row.get("Fld_NoOfShareHolders")),
            to_int(row.get("Fld_TotalNoOfShares")),
            to_real(row.get("Fld_TotalPercentageOf_A_B_C2")),
        ))
    return out


def process_filing(cli, conn, f, stats):
    fid, scrip, qtrid, src_url, old_hash, blob_path, parse_status, has_inst = f
    scrip_dir = RAW_DIR / scrip
    scrip_dir.mkdir(parents=True, exist_ok=True)
    new_hash, new_path = old_hash, blob_path

    if parse_status != "parsed":
        # raw XBRL (skip if the exact file is already on disk with a stored hash)
        if src_url:
            fname = src_url.rsplit("/", 1)[-1]
            fpath = scrip_dir / fname
            if fpath.exists():
                new_hash = old_hash or hashlib.sha256(fpath.read_bytes()).hexdigest()
            else:
                raw = cli.get_bytes(src_url)
                if raw is None:
                    stats["raw_fail"] += 1
                    conn.execute("UPDATE shp_filing SET parse_status='parse_failed' "
                                 "WHERE filing_id=?", (fid,))
                    conn.commit()
                    return
                fpath.write_bytes(raw)
                new_hash = hashlib.sha256(raw).hexdigest()
            new_path = str(fpath)

        # Table I summary JSON (also snapshotted next to the XBRL for lineage)
        payload = cli.get_json(
            f"{API}/Corp_shpSec_SHPSUMMARY_ng/w?scripcode={scrip}&qtrcode={qtrid:g}")
        rows = parse_summary_json(payload) if payload else []
        if not rows:
            stats["parse_fail"] += 1
            conn.execute("UPDATE shp_filing SET raw_blob_path=?, file_hash=?, "
                         "parse_status='parse_failed' WHERE filing_id=?",
                         (new_path, new_hash, fid))
            conn.commit()
            return
        (scrip_dir / f"{qtrid:g}_summary.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        conn.execute("DELETE FROM shp_category_summary WHERE filing_id=?", (fid,))
        conn.executemany(
            "INSERT INTO shp_category_summary VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(fid,) + r for r in rows])
        conn.execute("UPDATE shp_filing SET raw_blob_path=?, file_hash=?, "
                     "parse_status='parsed' WHERE filing_id=?", (new_path, new_hash, fid))
        conn.commit()
        stats["parsed"] += 1

    if has_inst:
        return  # Table III already present -- this call was purely a Table I fetch/retry

    # Table III institutional breakdown (FPI/DII split) -- supplementary: a failure
    # here does NOT downgrade parse_status (Table I already satisfied the primary
    # parse contract); tracked separately so coverage is honestly reported.
    pub_payload = cli.get_json(
        f"{API}/Corp_shpSec_SHPPubShold_ng/w?SCRIPCODE={scrip}&QtrCode={qtrid:g}")
    inst_rows = parse_pubshold_json(pub_payload) if pub_payload else []
    if inst_rows:
        (scrip_dir / f"{qtrid:g}_pubshold.json").write_text(
            json.dumps(pub_payload, ensure_ascii=False), encoding="utf-8")
        conn.execute("DELETE FROM shp_institutional_summary WHERE filing_id=?", (fid,))
        conn.executemany(
            "INSERT INTO shp_institutional_summary VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(fid,) + r for r in inst_rows])
        conn.commit()
        stats["inst_parsed"] += 1
    else:
        stats["inst_fail"] += 1


# ── notify ───────────────────────────────────────────────────────────────────
def notify(stats, elapsed_min):
    topic = os.environ.get("MICC_NTFY_TOPIC")
    if not topic:
        return
    text = ("SHP weekly sweep done\n"
            f"new filings: {stats['new_filings']}  revisions: {stats['revisions']}\n"
            f"parsed: {stats['parsed']}  parse_fail: {stats['parse_fail']}  "
            f"raw_fail: {stats['raw_fail']}\n"
            f"institutional (Table III): {stats.get('inst_parsed',0)} ok / "
            f"{stats.get('inst_fail',0)} fail\n"
            f"enum ok/fail: {stats['enum_ok']}/{stats['enum_fail']}  "
            f"({elapsed_min:.0f} min, {stats['calls']} calls)")
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}", data=text.encode(),
            headers={"Title": "MICC SHP sweep", "Priority": "default", "Tags": "bar_chart"})
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        log.warning(f"ntfy failed: {e}")


def keep_system_awake():
    """Ask Windows to stay awake while this long backfill runs (idle-sleep is what
    killed the first deep run). Non-invasive: uses SetThreadExecutionState, which is
    auto-released when the process exits -- it does NOT change the user's power plan.
    (Does not override a manual lid-close sleep; keep the machine plugged in.)"""
    try:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        log.info("keep-awake: system sleep suppressed for the duration of this run")
    except Exception as e:
        log.warning(f"keep-awake unavailable ({e}); machine may sleep mid-run")


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only first N scrips (testing)")
    ap.add_argument("--scrips", default="", help="comma-separated scrip codes")
    ap.add_argument("--quarters", type=int, default=8,
                    help="parse raw+Table I for the N most recent quarters (default 8)")
    ap.add_argument("--full-depth", action="store_true",
                    help="parse the ENTIRE real-time-filed range (overrides --quarters); "
                         "for the one-time deep backfill, not the weekly job")
    ap.add_argument("--max-filing-lag-days", type=int, default=400,
                    help="PIT trustworthiness gate: only parse filings broadcast within N "
                         "days of quarter-end (default 400). Excludes retro-uploads (e.g. "
                         "2006 data uploaded to BSE in 2023) whose timestamp is PIT-honest "
                         "but useless for a quarter-aligned test. Empirically this floors the "
                         "usable window at Mar 2016.")
    ap.add_argument("--budget-min", type=int, default=0,
                    help="stop cleanly after N minutes (0 = unlimited); resumes next run")
    ap.add_argument("--enumerate-only", action="store_true")
    ap.add_argument("--skip-enum", action="store_true",
                    help="jump straight to Phase B (parse), skipping the ~90-min "
                         "re-enumeration -- for cheap resumes of an interrupted deep backfill")
    ap.add_argument("--notify", action="store_true")
    a = ap.parse_args()

    keep_system_awake()
    t0 = time.time()
    deadline = t0 + a.budget_min * 60 if a.budget_min else None
    out_of_time = lambda: deadline and time.time() > deadline

    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    ensure_schema(conn)
    cli = Client()
    stats = dict(enum_ok=0, enum_fail=0, new_filings=0, revisions=0,
                 parsed=0, parse_fail=0, raw_fail=0, inst_parsed=0, inst_fail=0, calls=0)

    uni = fetch_universe(cli)
    if a.scrips:
        want = {s.strip() for s in a.scrips.split(",")}
        uni = [u for u in uni if u["scrip"] in want]
    if a.limit:
        uni = uni[:a.limit]
    if not uni:
        log.error("empty universe — aborting")
        sys.exit(1)

    # Phase A: enumerate (this is also the weekly new/revised-filing detector)
    if a.skip_enum:
        log.info("Phase A: SKIPPED (--skip-enum; resuming an interrupted deep backfill)")
    else:
        log.info(f"Phase A: enumerating {len(uni)} scrips ...")
        for i, u in enumerate(uni, 1):
            if out_of_time():
                log.warning(f"budget reached during enumeration at {i}/{len(uni)}")
                break
            enumerate_scrip(cli, conn, u, stats)
            if i % 250 == 0:
                log.info(f"  enum {i}/{len(uni)}  (+{stats['new_filings']} filings, "
                         f"{stats['revisions']} revisions)")

    # Phase B: raw + Table I + Table III, newest quarters first. Picks up a row if
    # EITHER Table I still needs (re)fetching OR Table III (FPI/DII) is missing --
    # process_filing() internally skips whichever half is already done.
    if not a.enumerate_only:
        qcut = conn.execute("SELECT MAX(qtrid) FROM shp_filing").fetchone()[0]
        if qcut is not None:
            qmin = (conn.execute("SELECT MIN(qtrid) FROM shp_filing").fetchone()[0]
                    if a.full_depth else qcut - a.quarters + 1)
            # PIT trustworthiness gate: skip retro-uploads (broadcast years after
            # quarter-end). Their pit_date is honest but they can't seed a quarter-
            # aligned test; empirically this floors the usable window at Mar 2016.
            lag_clause = (" AND julianday(f.pit_date) - julianday(f.quarter_end_date) "
                          "<= ?")
            # scope Phase B to the SAME scrip subset Phase A used (--scrips/--limit) --
            # otherwise a targeted test run silently grabs the whole table's backlog
            scrip_clause, params = "", [qmin, a.max_filing_lag_days]
            if a.scrips or a.limit:
                codes = [u["scrip"] for u in uni]
                scrip_clause = f" AND f.scrip_code IN ({','.join('?' * len(codes))})"
                params += codes
            todo = conn.execute(
                f"""SELECT f.filing_id, f.scrip_code, f.qtrid, f.source_url, f.file_hash,
                           f.raw_blob_path, f.parse_status,
                           EXISTS(SELECT 1 FROM shp_institutional_summary s
                                  WHERE s.filing_id=f.filing_id) AS has_inst
                    FROM shp_filing f
                    WHERE f.is_current_version=1 AND f.qtrid>=?{lag_clause}{scrip_clause}
                      AND (f.parse_status IN ('unparsed','parse_failed')
                           OR NOT EXISTS(SELECT 1 FROM shp_institutional_summary s
                                         WHERE s.filing_id=f.filing_id))
                    ORDER BY f.qtrid DESC, f.scrip_code""", params).fetchall()
            log.info(f"Phase B: {len(todo)} filings to fetch+parse "
                     f"(qtrid {qmin:g}..{qcut:g}, full_depth={a.full_depth}, "
                     f"max_lag={a.max_filing_lag_days}d)")
            for i, f in enumerate(todo, 1):
                if out_of_time():
                    log.warning(f"budget reached during parse at {i}/{len(todo)} — resumes next run")
                    break
                process_filing(cli, conn, f, stats)
                if i % 200 == 0:
                    log.info(f"  parse {i}/{len(todo)}  (ok {stats['parsed']}, "
                             f"fail {stats['parse_fail']}+{stats['raw_fail']}, "
                             f"inst {stats['inst_parsed']}/{stats['inst_fail']})")

    stats["calls"] = cli.calls
    elapsed = (time.time() - t0) / 60
    # coverage snapshot for the log
    cov = conn.execute(
        """SELECT exchange_segment, COUNT(DISTINCT scrip_code) FROM shp_filing
           WHERE qtrid=(SELECT MAX(qtrid) FROM shp_filing) GROUP BY exchange_segment"""
    ).fetchall()
    log.info(f"done in {elapsed:.1f} min | {stats} | latest-qtr coverage {cov}")
    conn.close()
    if a.notify:
        notify(stats, elapsed)


if __name__ == "__main__":
    main()
