# -*- coding: utf-8 -*-
"""
phase9a_create_tables.py
========================
Phase 9A — Step 1: Create the three new DB tables for Deep Analysis Room.

Tables created:
  1. window_stats        — per-symbol, per-window statistical warehouse
  2. window_extremes     — top-N best/worst episodes per symbol+window
  3. global_indices_daily — daily OHLCV for global indices (SPX, Nikkei, etc.)

Run ONCE (or re-run safely — uses CREATE TABLE IF NOT EXISTS + index checks).

Location: D:/MICC/data_extraction/phase9a_create_tables.py
Usage:    py phase9a_create_tables.py
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")


def log(msg: str, level: str = "INFO"):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  {msg}", flush=True)


def create_tables(conn: sqlite3.Connection):
    cur = conn.cursor()

    # ── 1. window_stats ──────────────────────────────────────────────────────
    # One row per (symbol, asset_type, window_days).
    # asset_type: 'stock' | 'index' | 'global'
    # Stores the full distribution summary for that holding period.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS window_stats (
            symbol          TEXT    NOT NULL,
            asset_type      TEXT    NOT NULL DEFAULT 'stock',
            window_days     INTEGER NOT NULL,

            -- coverage
            first_date      TEXT,
            last_date       TEXT,
            n_windows       INTEGER,

            -- central tendency
            mean_return     REAL,
            median_return   REAL,
            std_return      REAL,

            -- extremes
            min_return      REAL,
            max_return      REAL,

            -- percentiles
            p5              REAL,
            p25             REAL,
            p75             REAL,
            p95             REAL,

            -- probability metrics
            prob_positive   REAL,    -- P(return > 0)
            prob_gt5        REAL,    -- P(return > +5%)
            prob_gt10       REAL,    -- P(return > +10%)
            prob_gt20       REAL,    -- P(return > +20%)
            prob_lt_neg5    REAL,    -- P(return < -5%)
            prob_lt_neg10   REAL,    -- P(return < -10%)
            prob_lt_neg20   REAL,    -- P(return < -20%)

            -- annualised (for longer windows, optional)
            ann_return_equiv REAL,   -- annualised equivalent of mean_return

            -- metadata
            computed_date   TEXT,    -- YYYY-MM-DD when this row was last computed

            PRIMARY KEY (symbol, asset_type, window_days)
        )
    """)
    log("Table window_stats: ready", "OK")

    # ── 2. window_extremes ───────────────────────────────────────────────────
    # Top-5 best and top-5 worst episodes per (symbol, window_days).
    # direction: 'up' (best rally) | 'down' (worst crash)
    # rank: 1=best/worst, 2=second best/worst, ...
    cur.execute("""
        CREATE TABLE IF NOT EXISTS window_extremes (
            symbol          TEXT    NOT NULL,
            asset_type      TEXT    NOT NULL DEFAULT 'stock',
            window_days     INTEGER NOT NULL,
            direction       TEXT    NOT NULL,   -- 'up' or 'down'
            rank_n          INTEGER NOT NULL,   -- 1..5

            start_date      TEXT    NOT NULL,
            end_date        TEXT    NOT NULL,
            return_pct      REAL    NOT NULL,

            computed_date   TEXT,

            PRIMARY KEY (symbol, asset_type, window_days, direction, rank_n)
        )
    """)
    log("Table window_extremes: ready", "OK")

    # ── 3. global_indices_daily ──────────────────────────────────────────────
    # Daily OHLCV for global indices fetched from yfinance.
    # symbol examples: SPX, NDX, Nikkei225, DAX, HangSeng, FTSE100,
    #                  DXY, Gold, CrudeWTI, VIX, US10Y
    cur.execute("""
        CREATE TABLE IF NOT EXISTS global_indices_daily (
            symbol          TEXT    NOT NULL,
            date            TEXT    NOT NULL,   -- YYYY-MM-DD
            open            REAL,
            high            REAL,
            low             REAL,
            close           REAL    NOT NULL,
            volume          REAL,
            pct_change      REAL,               -- daily % change, computed on insert

            PRIMARY KEY (symbol, date)
        )
    """)
    log("Table global_indices_daily: ready", "OK")

    conn.commit()


def create_indices(conn: sqlite3.Connection):
    """Create covering indices for fast lookups by all 4 agents."""
    cur = conn.cursor()

    # Existing indices check helper
    def idx_exists(name: str) -> bool:
        row = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,)
        ).fetchone()
        return row is not None

    indices = [
        # window_stats — Agent Kappa needs fast single-symbol lookup
        ("idx_ws_symbol",      "window_stats",         "symbol"),
        ("idx_ws_sym_win",     "window_stats",         "symbol, window_days"),
        ("idx_ws_atype",       "window_stats",         "asset_type, window_days"),

        # window_extremes — Agent Kappa pulls top episodes per symbol+window
        ("idx_we_sym_win",     "window_extremes",      "symbol, window_days"),
        ("idx_we_sym_dir",     "window_extremes",      "symbol, window_days, direction"),

        # global_indices_daily — Agent Mu needs fast time-range queries
        ("idx_gid_sym",        "global_indices_daily", "symbol"),
        ("idx_gid_date",       "global_indices_daily", "date"),
        ("idx_gid_sym_date",   "global_indices_daily", "symbol, date"),
    ]

    created = 0
    for idx_name, table, cols in indices:
        if idx_exists(idx_name):
            log(f"Index {idx_name}: already exists", "WARN")
        else:
            cur.execute(f"CREATE INDEX {idx_name} ON {table} ({cols})")
            log(f"Index {idx_name}: created", "OK")
            created += 1

    conn.commit()
    log(f"Indices: {created} created (others already existed)")


def verify(conn: sqlite3.Connection):
    """Quick verification that all 3 tables are present and accessible."""
    cur = conn.cursor()
    tables = ["window_stats", "window_extremes", "global_indices_daily"]
    all_ok = True
    for t in tables:
        try:
            row = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
            log(f"Verified {t}: {row[0]} rows", "OK")
        except Exception as e:
            log(f"FAILED to verify {t}: {e}", "FAIL")
            all_ok = False
    return all_ok


def main():
    print()
    print("=" * 60)
    print("  MICC Phase 9A — Create Deep Analysis Tables")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    if not DB_PATH.exists():
        log(f"DB not found: {DB_PATH}", "FAIL")
        sys.exit(1)

    log(f"Connecting to {DB_PATH}")

    # Use WAL mode — consistent with the rest of MICC
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    try:
        log("Creating tables...")
        create_tables(conn)

        log("Creating indices...")
        create_indices(conn)

        log("Verifying...")
        ok = verify(conn)

        print()
        if ok:
            log("Phase 9A Step 1 COMPLETE — all tables and indices ready", "OK")
        else:
            log("Phase 9A Step 1 had errors — check above", "FAIL")
            sys.exit(1)

    except Exception as e:
        log(f"Fatal error: {e}", "FAIL")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()

    print()
    print("  Next step: py phase9a_fetch_global_indices.py")
    print()


if __name__ == "__main__":
    main()
