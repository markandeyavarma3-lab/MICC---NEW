#!/usr/bin/env python3
"""backfill_recommendations.py — one-shot migration of the 555 legacy
`recommendations` rows into the Idea Engine (thesis + trade), preserving the
track record so the Part-3 learning loop can score history.

Each recommendation -> one thesis (single-trade) + one trade. realized_return is
copied verbatim so backfill parity is exact (verify_phases P7). Idempotent:
wipes only the backfilled rows (source_signal tag) and rebuilds them, so re-runs
are safe and never double-count. `recommendations` is never modified.

Run:  py -3.14 ideas/backfill_recommendations.py
"""
import sqlite3

from schema import connect, ensure_tables

BACKFILL_TAG = "backfill:recommendations"

# outcome (recommendations) -> exit_reason (trade)
EXIT_REASON = {"TARGET": "target", "STOP": "stop",
               "EXPIRED_WIN": "expired", "EXPIRED_LOSS": "expired"}


def thesis_type_of(strategy: str) -> str:
    s = (strategy or "").lower()
    for key in ("momentum", "value", "quality", "event", "macro"):
        if key in s:
            return "macro_overlay" if key == "macro" else key
    return "momentum"  # the only legacy strategy is momentum_delivery_lowvol


def timeframe_of(horizon_days) -> str:
    return "swing" if (horizon_days or 0) <= 21 else "positional"


def main():
    conn = connect()
    ensure_tables(conn)
    cur = conn.cursor()

    # --- idempotent reset: drop prior backfill only (leave live theses intact) ---
    old = [r[0] for r in cur.execute(
        "SELECT thesis_id FROM thesis WHERE narrative=?", (BACKFILL_TAG,))]
    if old:
        qmarks = ",".join("?" * len(old))
        cur.execute(f"DELETE FROM trade WHERE thesis_id IN ({qmarks})", old)
        cur.execute(f"DELETE FROM thesis WHERE thesis_id IN ({qmarks})", old)
        conn.commit()
        print(f"  reset {len(old)} prior backfilled theses", flush=True)

    recs = cur.execute(
        "SELECT rec_date,symbol,company,strategy,score,horizon_days,entry,target,"
        "stop,status,close_date,exit_price,realized_return,outcome "
        "FROM recommendations ORDER BY rec_date,symbol").fetchall()

    n_th = n_tr = 0
    for (rec_date, symbol, company, strategy, score, horizon, entry, target, stop,
         status, close_date, exit_price, realized, outcome) in recs:
        st = "closed" if status == "CLOSED" else "active"
        cur.execute(
            "INSERT INTO thesis (created_at,symbol,thesis_type,source_signal,"
            "timeframe_class,regime_at_creation,confidence_score,weight_version,"
            "narrative,status,invalidation_condition,closed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rec_date, symbol, thesis_type_of(strategy), strategy,
             timeframe_of(horizon), None, score, None, BACKFILL_TAG, st, None,
             close_date))
        thesis_id = cur.lastrowid
        n_th += 1

        exit_reason = EXIT_REASON.get(outcome) if outcome else None
        cur.execute(
            "INSERT INTO trade (thesis_id,entry_date,entry_price,stop,target,"
            "size_shares,atr_k,exit_date,exit_price,exit_reason,realized_return) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (thesis_id, rec_date, entry, stop, target, None, None,
             close_date, exit_price, exit_reason, realized))
        n_tr += 1

    conn.commit()

    # --- self-check: backfill parity (mirrors verify_phases P7) ---
    rec_mean = cur.execute(
        "SELECT AVG(realized_return) FROM recommendations "
        "WHERE status='CLOSED' AND realized_return IS NOT NULL").fetchone()[0]
    trd_mean = cur.execute(
        "SELECT AVG(realized_return) FROM trade t JOIN thesis h "
        "ON t.thesis_id=h.thesis_id WHERE h.narrative=? "
        "AND t.exit_price IS NOT NULL AND t.realized_return IS NOT NULL",
        (BACKFILL_TAG,)).fetchone()[0]
    parity = abs((rec_mean or 0) - (trd_mean or 0))
    print(f"  thesis inserted : {n_th}", flush=True)
    print(f"  trade  inserted : {n_tr}", flush=True)
    print(f"  parity |rec-trade mean ret| = {parity:.2e}  "
          f"(rec={rec_mean:.6f} trade={trd_mean:.6f})", flush=True)
    print(f"  {'PASS' if parity < 1e-6 else 'FAIL'}: backfill parity", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
