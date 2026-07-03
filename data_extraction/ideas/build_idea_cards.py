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
from build_bands import CAPITAL
from schema import connect, ensure_tables


def materialise(conn, card_date):
    cur = conn.cursor()
    cur.execute("DELETE FROM idea_card WHERE card_date=?", (card_date,))
    # confidence-ranked so the portfolio cap keeps the HIGHEST-conviction ideas
    live = cur.execute(
        "SELECT h.thesis_id,h.symbol,h.thesis_type,h.timeframe_class,h.confidence_score,"
        "h.status FROM thesis h WHERE h.narrative='live:momentum_bands' AND h.created_at=? "
        "ORDER BY h.confidence_score DESC", (card_date,)).fetchall()

    made = 0
    cum_notional = 0.0          # portfolio-level capital cap: total deployed <= CAPITAL
    for tid, sym, ttype, tf, conf, status in live:
        tr = cur.execute(
            "SELECT entry_price,stop,target,size_shares FROM trade WHERE thesis_id=? "
            "ORDER BY trade_id DESC LIMIT 1", (tid,)).fetchone()
        if not tr:
            continue
        entry, stop, target, size = tr
        rr = round((target - entry) / (entry - stop), 2) if entry and entry != stop else None
        notional = round((size or 0) * entry, 2)
        # include this idea only if it still fits under the capital cap (highest conf first)
        in_book = 1 if (cum_notional + notional) <= CAPITAL else 0
        if in_book:
            cum_notional += notional
        company = cur.execute("SELECT company FROM current_signals WHERE symbol=? "
                              "AND rebal_date=? LIMIT 1", (sym, card_date)).fetchone()
        company = company[0] if company else sym
        sector = cur.execute("SELECT sector FROM dim_sector WHERE symbol=?", (sym,)).fetchone()
        sector = sector[0] if sector else None
        pillars = {p: {"subscore": round(s, 1), "weight": w, "contribution": round(c, 2)}
                   for p, s, w, c in cur.execute(
                       "SELECT pillar,subscore,weight,contribution FROM score_audit "
                       "WHERE thesis_id=? AND card_date=?", (tid, card_date))}
        # context tags: zero scoring weight, display-only (Part 2 context tier)
        ctx = {}
        rg = cur.execute("SELECT regime_label,regime_score FROM regime_daily "
                         "WHERE date<=? ORDER BY date DESC LIMIT 1", (card_date,)).fetchone()
        if rg:
            ctx["regime_spine"] = f"{rg[0]} ({rg[1]:.0f})"
        if sector:
            sq = cur.execute("SELECT rrg_quadrant,sector_breadth FROM sector_regime_daily "
                             "WHERE sector=? AND date<=? ORDER BY date DESC LIMIT 1",
                             (sector, card_date)).fetchone()
            if sq and sq[0]:
                ctx["sector_rrg"] = f"{sq[0]} (breadth {sq[1]:.0f}%)"
        for et, ed in cur.execute(
                "SELECT event_type,MAX(event_date) FROM event_signals WHERE symbol=? "
                "AND event_date<=? AND evidence_tier='context' "
                "AND julianday(?)-julianday(event_date)<=decay_horizon_days "
                "GROUP BY event_type", (sym, card_date, card_date)):
            ctx[et] = ed
        cur.execute(
            "INSERT INTO idea_card (card_date,thesis_id,symbol,company,sector,thesis_type,"
            "timeframe_class,entry,stop,target,rr_ratio,size_shares,confidence_score,"
            "notional,in_book,pillar_json,context_json,status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (card_date, tid, sym, company, sector, ttype, tf, entry, stop, target, rr,
             size, conf, notional, in_book, json.dumps(pillars), json.dumps(ctx), status))
        made += 1
    conn.commit()
    return made, cum_notional


def main():
    build_bands.main()
    scoring.main()
    conn = connect()
    ensure_tables(conn)
    card_date = conn.execute("SELECT MAX(rebal_date) FROM current_signals").fetchone()[0]
    n, deployed = materialise(conn, card_date)
    in_book = conn.execute("SELECT COUNT(*),COALESCE(SUM(notional),0) FROM idea_card "
                           "WHERE card_date=? AND in_book=1", (card_date,)).fetchone()
    top = conn.execute("SELECT symbol,timeframe_class,confidence_score,rr_ratio,in_book "
                       "FROM idea_card WHERE card_date=? ORDER BY confidence_score DESC LIMIT 5",
                       (card_date,)).fetchall()
    print(f"\n  idea_card materialised: {n} cards for {card_date}", flush=True)
    print(f"  portfolio: {in_book[0]}/{n} in book, deployed Rs {in_book[1]:,.0f} "
          f"/ Rs {CAPITAL:,.0f} ({in_book[1]/CAPITAL:.0%})", flush=True)
    for s, tf, c, rr, ib in top:
        print(f"    {s:12} {tf:10} conf {c:5.1f}  rr {rr}  {'[book]' if ib else '[waitlist]'}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
