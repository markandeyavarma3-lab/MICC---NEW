#!/usr/bin/env python3
"""schema.py — Idea Engine data model (MICC Part 1, Stage 2 + 4).

Central, idempotent DDL for the idea/scoring layer. Additive only: creates new
tables in market.db and never touches the verified data tables. Imported by the
backfill, band, scoring and card builders so the schema lives in exactly one place.

Tables
  thesis        one row per conviction (durable unit the learning loop scores)
  trade         many rows per thesis (entries/exits/tranches)
  idea_card     materialised presentation view (rebuilt each refresh)
  score_weights versioned linear-composite weights (Stage 4)
  score_audit   per-pillar contribution for every scored thesis (Stage 4)

Run:  py -3.14 ideas/schema.py     # creates/verifies all tables
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")

DDL = [
    """CREATE TABLE IF NOT EXISTS thesis (
        thesis_id     INTEGER PRIMARY KEY,
        created_at    TEXT,
        symbol        TEXT,
        thesis_type   TEXT,      -- momentum|value|quality|event|macro_overlay
        source_signal TEXT,      -- strategy/factor that fired
        timeframe_class TEXT,    -- swing (1-4wk) | positional (1-3mo)
        regime_at_creation TEXT, -- snapshot of the 4-vote gate, e.g. 'RISK-ON 3/4'
        confidence_score REAL,   -- 0..100 (Stage 4 scorer)
        weight_version   TEXT,   -- score_weights.version used
        narrative     TEXT,
        status        TEXT,      -- active|closed|invalidated
        invalidation_condition TEXT,
        closed_at     TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS trade (
        trade_id     INTEGER PRIMARY KEY,
        thesis_id    INTEGER,    -- FK -> thesis.thesis_id
        entry_date   TEXT,
        entry_price  REAL,
        stop         REAL,
        target       REAL,
        size_shares  INTEGER,    -- integer shares (matches paper_trader)
        atr_k        REAL,       -- ATR multiplier used for the stop (A4)
        exit_date    TEXT,
        exit_price   REAL,
        exit_reason  TEXT,       -- target|stop|regime_liquidation|thesis_invalidated|expired
        realized_return REAL
    )""",
    """CREATE TABLE IF NOT EXISTS idea_card (
        card_date    TEXT,
        thesis_id    INTEGER,
        symbol       TEXT, company TEXT, sector TEXT,
        thesis_type  TEXT, timeframe_class TEXT,
        entry REAL, stop REAL, target REAL, rr_ratio REAL, size_shares INTEGER,
        confidence_score REAL,
        notional REAL,          -- size_shares * entry (rupees deployed)
        in_book INTEGER,        -- 1 if selected within the portfolio capital cap
        pillar_json  TEXT,       -- per-pillar breakdown for "why this score"
        status TEXT,
        PRIMARY KEY (card_date, thesis_id)
    )""",
    # ---- Stage 4 scoring framework (created now, populated in Stage 4) ----
    """CREATE TABLE IF NOT EXISTS score_weights (
        version        TEXT,
        pillar         TEXT,     -- signal_strength|trend_align|regime_align|
                                 -- liquidity_capacity|confirmation|risk_penalty
        weight         REAL,     -- Sum over pillars per version = 1.0
        effective_date TEXT,
        rationale      TEXT,
        PRIMARY KEY (version, pillar)
    )""",
    """CREATE TABLE IF NOT EXISTS score_audit (
        thesis_id      INTEGER,
        card_date      TEXT,
        pillar         TEXT,
        subscore       REAL,     -- 0..100
        weight         REAL,
        contribution   REAL,     -- subscore * weight
        weight_version TEXT,
        PRIMARY KEY (thesis_id, card_date, pillar)
    )""",
]

# The scoring pillars, canonical order. risk_penalty is negative-weighted.
# event_score added in v2.0 (Part 2 Module 7) after insider clusters passed their
# pre-registered event study (t=3.67).
PILLARS = ["signal_strength", "trend_align", "regime_align",
           "liquidity_capacity", "confirmation", "event_score", "risk_penalty"]


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=180)
    conn.execute("PRAGMA busy_timeout=180000")
    return conn


def ensure_tables(conn):
    for stmt in DDL:
        conn.execute(stmt)
    # additive migrations for tables that predate a column (SQLite ADD COLUMN is safe)
    have = {r[1] for r in conn.execute("PRAGMA table_info(idea_card)")}
    for col, decl in (("notional", "REAL"), ("in_book", "INTEGER"),
                      ("context_json", "TEXT")):
        if col not in have:
            conn.execute(f"ALTER TABLE idea_card ADD COLUMN {col} {decl}")
    conn.commit()


def main():
    conn = connect()
    ensure_tables(conn)
    got = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("thesis", "trade", "idea_card", "score_weights", "score_audit"):
        print(f"  {t:14} {'OK' if t in got else 'MISSING'}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
