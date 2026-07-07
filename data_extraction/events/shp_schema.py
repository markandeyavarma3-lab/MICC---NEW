#!/usr/bin/env python3
"""shp_schema.py — Part 4 Stage 1: shareholding-pattern tables (additive only).

Data-acquisition layer ONLY. Nothing here feeds scoring/idea_card — SHP data is
inert storage until a future pre-registered walk-forward test (t>=3.0) earns it
weight (house rule #1).

PIT rule (the one that matters): pit_date = date of the exchange broadcast of the
version we store — NEVER quarter_end_date, and for a revised filing NEVER the
original filing date (the revised numbers weren't knowable then). Downstream joins
must use pit_date <= as_of, ideally strict <.

Revision rule: filings are never mutated in place. A revised filing is a NEW row
whose is_revision_of points at the superseded filing_id; the old row keeps its data
and gets is_current_version=0. A partial unique index enforces one current version
per (scrip_code, qtrid) at the DB level.

Run:  py -3.14 events/shp_schema.py     (creates tables if missing; idempotent)
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")

SHP_TABLES = [
    """CREATE TABLE IF NOT EXISTS shp_filing (
        filing_id           TEXT PRIMARY KEY,  -- 'bse:{scrip}:{qtrid}:{sha1(XbrlFile)[:10]}'
        scrip_code          TEXT,              -- BSE scrip code
        isin                TEXT,
        cin                 TEXT,              -- nullable; backfilled later where available
        company_name        TEXT,
        exchange_segment    TEXT,              -- 'mainboard' | 'sme' (BSE group M/MT/MS)
        source_exchange     TEXT,              -- 'bse' (Stage 1); 'nse' reserved
        quarter_end_date    TEXT,              -- ISO date, reporting period end
        qtrid               REAL,              -- BSE quarter id (129.0 = Mar 2026)
        filing_status       TEXT,              -- 'new' | 'revised' (BSE status field)
        first_filed_datetime TEXT,             -- original filing_date_time (info only)
        broadcast_datetime  TEXT,              -- timestamp of THE VERSION STORED — PIT anchor
        pit_date            TEXT,              -- date(broadcast_datetime); joins: pit_date <= as_of
        source_route        TEXT,              -- 'bse_shpq_newformat'
        source_url          TEXT,              -- raw XBRL URL
        raw_format          TEXT,              -- 'xbrl_xml'
        raw_blob_path       TEXT,              -- file on disk (data_storage/raw/shp), not a DB blob
        file_hash           TEXT,              -- sha256 of raw XBRL (revision detection)
        is_revision_of      TEXT,              -- filing_id superseded by this row (NULL if first seen)
        is_current_version  INTEGER DEFAULT 1, -- 0/1
        fetched_at          TEXT,
        parse_status        TEXT               -- 'unparsed' | 'parsed' | 'parse_failed'
    )""",
    """CREATE TABLE IF NOT EXISTS shp_category_summary (  -- SEBI Table I equivalent
        filing_id     TEXT,     -- FK -> shp_filing.filing_id
        seq           INTEGER,  -- row order in source table
        category_code TEXT,     -- Fld_Code: A1/A2/STA1A2/B1../C../grand total
        category      TEXT,     -- promoter & promoter group / public / non-promoter-non-public
        sub_category  TEXT,
        level         TEXT,     -- FLD_LEVEL e.g. 'A=A1+A2'
        num_holders   INTEGER,
        num_shares    INTEGER,  -- total shares (SQLite INTEGER = 64-bit)
        pct_holding   REAL,     -- % of A+B+C2
        pct_pledged   REAL,     -- promoter rows, where disclosed
        PRIMARY KEY (filing_id, seq)
    )""",
    """CREATE TABLE IF NOT EXISTS shp_institutional_summary (  -- Table III institutional
        filing_id     TEXT,     -- FK -> shp_filing.filing_id  -- breakdown (FPI/DII split)
        seq           INTEGER,  -- row order in source table
        category      TEXT,     -- Fld_ShortCatg, e.g. 'Public shareholder'
        sub_category  TEXT,     -- Fld_SubCategory: 'Institutions' (detail rows) or
                                 -- 'Institutions (Domestic)'/'Institutions (Foreign)' (subtotal rows)
        level         TEXT,     -- Fld_Level: institution type (e.g. 'Foreign Portfolio Investors
                                 -- Category I', 'Mutual Funds/') or 'Sub Total B1'/'Sub Total B2'
        holder_name   TEXT,     -- Fld_ShareHolderName. NULL = the category AGGREGATE row;
                                 -- non-NULL = a named >=1% holder NESTED inside that aggregate.
                                 -- ** FPI/DII signal aggregation MUST filter holder_name IS NULL **
                                 -- or it double-counts named holders against their own subtotal.
        is_aggregate  INTEGER,  -- 1 if holder_name IS NULL (the usable aggregate), else 0
        num_holders   INTEGER,
        num_shares    INTEGER,
        pct_holding   REAL,
        PRIMARY KEY (filing_id, seq)
    )""",
    """CREATE TABLE IF NOT EXISTS shp_promoter_group (   -- Table II: Promoter & Promoter Group
        filing_id     TEXT,     -- FK -> shp_filing.filing_id
        seq           INTEGER,  -- row order in source table
        category      TEXT,     -- Fld_ShortCatg, e.g. 'Promoter and Promoter Group' (agg/subtotal
                                 -- rows only; NULL on named rows -- join back via sub_category/level)
        sub_category  TEXT,     -- Fld_SubCategory: 'Indian' / 'Foreign'
        level         TEXT,     -- Fld_Level: holder type (e.g. 'Central Government/State
                                 -- Government(s)') or 'Sub Total A1'/'Sub Total A2' etc
        holder_name   TEXT,     -- Fld_ShareHolderName. NULL = the category AGGREGATE row;
                                 -- non-NULL = a named promoter NESTED inside that aggregate
                                 -- (same shares/pct as its parent -- do not sum both).
        is_aggregate  INTEGER,  -- 1 if holder_name IS NULL (the usable aggregate), else 0
        num_holders   INTEGER,
        num_shares    INTEGER,
        pct_holding   REAL,
        pledge_shares INTEGER,  -- Fld_PledgeEncumberedNoOfShares
        pledge_pct    REAL,     -- Fld_PledgeEncumberedPercentage
        lockedin_shares   INTEGER,
        lockedin_pct      REAL,
        encumbered_shares INTEGER,  -- Fld_TotalencumberedNoOfShares (pledge + other encumbrances)
        encumbered_pct    REAL,
        PRIMARY KEY (filing_id, seq)
    )""",
    """CREATE TABLE IF NOT EXISTS shp_named_holder (      -- Tables III-IV (Stage 1b fill; III/IV
                                                            -- named holders already covered inline
                                                            -- above -- reserved for Table IV detail)
        filing_id     TEXT,     -- FK -> shp_filing.filing_id
        table_no      TEXT,     -- 'II' | 'III' | 'IV'
        seq           INTEGER,
        holder_name   TEXT,
        holder_category TEXT,   -- promoter / MF / FPI / insurance / individual / custodian ...
        num_shares    INTEGER,
        pct_holding   REAL,
        is_pac        INTEGER,  -- person-acting-in-concert flag where disclosed (0/1/NULL)
        PRIMARY KEY (filing_id, table_no, seq)
    )""",
]

SHP_INDEXES = [
    # THE invariant: one current version per scrip per quarter
    """CREATE UNIQUE INDEX IF NOT EXISTS ux_shp_current
       ON shp_filing(scrip_code, qtrid) WHERE is_current_version=1""",
    "CREATE INDEX IF NOT EXISTS idx_shp_filing_scrip ON shp_filing(scrip_code)",
    "CREATE INDEX IF NOT EXISTS idx_shp_filing_pit   ON shp_filing(pit_date)",
    "CREATE INDEX IF NOT EXISTS idx_shp_filing_qtr   ON shp_filing(quarter_end_date)",
    "CREATE INDEX IF NOT EXISTS idx_shp_filing_isin  ON shp_filing(isin)",
    "CREATE INDEX IF NOT EXISTS idx_shp_inst_level   ON shp_institutional_summary(level)",
    "CREATE INDEX IF NOT EXISTS idx_shp_prom_level   ON shp_promoter_group(level)",
]


def ensure_schema(conn):
    for ddl in SHP_TABLES + SHP_INDEXES:
        conn.execute(ddl)
    conn.commit()


if __name__ == "__main__":
    c = sqlite3.connect(DB_PATH, timeout=120)
    c.execute("PRAGMA busy_timeout=120000")
    ensure_schema(c)
    tabs = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'shp_%' ORDER BY name")]
    print(f"shp schema ensured: {tabs}")
    c.close()
