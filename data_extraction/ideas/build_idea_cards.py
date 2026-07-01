#!/usr/bin/env python3
"""build_idea_cards.py — Part 1 Stage 6 daily orchestrator for the Idea Engine.

Chains the three Idea-Engine steps and materialises the presentation view:
    1. build_bands  -> live theses + ATR entry/stop/target + integer sizing
    2. scoring      -> 6-pillar confidence + per-pillar score_audit
    3. materialise idea_card (thesis + latest trade + sector + "why this score")

idea_card is rebuilt from scratch for the current card_date every run (it is a
derived view, never hand-edited). Idempotent.

Run:  py -3.14 ideas/build_idea_cards.py
"""
import json

import build_bands
import scoring
from schema import connect, ensure_tables


def materialise(conn, card_date):
    cur = conn.cursor()
    cur.execute("DELETE FROM idea_card WHERE card_date=?", (card_date,))
    live = cur.execute(
        "SELECT h.thesis_id,h.symbol,h.thesis_type,h.timeframe_class,h.confidence_score,"
        "h.status FROM thesis h WHERE h.narrative='live:momentum_bands' AND h.created_at=?",
        (card_date,)).fetchall()

    made = 0
    for tid, sym, ttype, tf, conf, status in live:
        tr = cur.execute(
            "SELECT entry_price,stop,target,size_shares FROM trade WHERE thesis_id=? "
            "ORDER BY trade_id DESC LIMIT 1", (tid,)).fetchone()
        if not tr:
            continue
        entry, stop, target, size = tr
        rr = round((target - entry) / (entry - stop), 2) if entry and entry != stop else None
        company = cur.execute("SELECT company FROM current_signals WHERE symbol=? "
                              "AND rebal_date=? LIMIT 1", (sym, card_date)).fetchone()
        company = company[0] if company else sym
        sector = cur.execute("SELECT sector FROM dim_sector WHERE symbol=?", (sym,)).fetchone()
        sector = sector[0] if sector else None
        pillars = {p: {"subscore": round(s, 1), "weight": w, "contribution": round(c, 2)}
                   for p, s, w, c in cur.execute(
                       "SELECT pillar,subscore,weight,contribution FROM score_audit "
                       "WHERE thesis_id=? AND card_date=?", (tid, card_date))}
        cur.execute(
            "INSERT INTO idea_card (card_date,thesis_id,symbol,company,sector,thesis_type,"
            "timeframe_class,entry,stop,target,rr_ratio,size_shares,confidence_score,"
            "pillar_json,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (card_date, tid, sym, company, sector, ttype, tf, entry, stop, target, rr,
             size, conf, json.dumps(pillars), status))
        made += 1
    conn.commit()
    return made


def main():
    build_bands.main()
    scoring.main()
    conn = connect()
    ensure_tables(conn)
    card_date = conn.execute("SELECT MAX(rebal_date) FROM current_signals").fetchone()[0]
    n = materialise(conn, card_date)
    top = conn.execute("SELECT symbol,timeframe_class,confidence_score,rr_ratio "
                       "FROM idea_card WHERE card_date=? ORDER BY confidence_score DESC LIMIT 5",
                       (card_date,)).fetchall()
    print(f"\n  idea_card materialised: {n} cards for {card_date}", flush=True)
    for s, tf, c, rr in top:
        print(f"    {s:12} {tf:10} conf {c:5.1f}  rr {rr}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
