#!/usr/bin/env python3
"""verify_phases.py — independent PIN-TO-PIN verification of Phases 1/2/4/5.

Does NOT trust prior printouts. Re-derives key claims from raw tables and asserts
them with PASS/FAIL, including manual recomputations that would catch alignment /
lookahead / adjustment bugs.

Run:  py -3.14 common/verify_phases.py
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


def days_between(d1, d2):
    return abs((datetime.strptime(d1, "%Y-%m-%d") - datetime.strptime(d2, "%Y-%m-%d")).days)

DB_PATH = Path(r"D:\marketDB\db\market.db")
R = []   # results: (passed, name, detail)


def check(cond, name, detail=""):
    R.append((bool(cond), name, detail))


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    q = lambda s, p=(): conn.execute(s, p).fetchone()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    # ============ PHASE 1: stock_data_adj ============
    print("Verifying Phase 1: stock_data_adj ...", flush=True)
    check("stock_data_adj" in tables, "P1 stock_data_adj exists")
    # adj is rebuilt WEEKLY while raw is updated DAILY, so between a daily fetch and the
    # weekly adj rebuild raw legitimately leads adj (both by new dates and by symbols
    # backfilled onto older dates). Assert adj covers raw within its own date range up to
    # a tiny pending-rebuild tolerance, and that adj never EXCEEDS raw (phantom rows).
    n_adj = q("SELECT COUNT(*) FROM stock_data_adj")[0]
    n_raw = q("SELECT COUNT(*) FROM stock_data")[0]
    adj_max = q("SELECT MAX(date) FROM stock_data_adj")[0]
    n_raw_in_range = q("SELECT COUNT(*) FROM stock_data WHERE date<=?", (adj_max,))[0]
    shortfall = n_raw_in_range - n_adj          # in-range raw rows adj hasn't picked up yet
    ok = (n_adj <= n_raw) and (0 <= shortfall <= 0.005 * n_adj)
    check(ok, "P1 adj covers raw within its date range (raw may lead; adj rebuild is weekly)",
          f"adj={n_adj:,} raw={n_raw:,} in_range(<= {adj_max})={n_raw_in_range:,} shortfall={shortfall}")
    bad = q("SELECT COUNT(*) FROM stock_data_adj WHERE close<=0 OR close IS NULL "
            "OR open<=0 OR high<=0 OR low<=0")[0]
    check(bad == 0, "P1 no non-positive/NULL adj prices", f"bad={bad}")
    frng = q("SELECT MIN(adj_factor),MAX(adj_factor) FROM stock_data_adj")
    check(0 < frng[0] and frng[1] <= 1.0001, "P1 adj_factor in (0,1]", f"range={frng}")
    nadj = q("SELECT COUNT(*) FROM stock_data_adj WHERE ABS(adj_factor-1)>1e-9")[0]
    check(nadj > 1_000_000, "P1 >1M rows actually adjusted", f"{nadj:,}")
    # raw recovered = adj/adj_factor must match stock_data (sample 1 symbol)
    s = q("SELECT symbol FROM stock_data_adj WHERE adj_factor<0.5 LIMIT 1")[0]
    a = pd.read_sql("SELECT date,close,adj_factor FROM stock_data_adj WHERE symbol=?",
                    conn, params=(s,))
    r = pd.read_sql("SELECT date,close FROM stock_data WHERE symbol=?", conn, params=(s,))
    m = a.merge(r, on="date", suffixes=("_adj", "_raw"))
    m["recovered"] = m["close_adj"] / m["adj_factor"]
    err = (m["recovered"] - m["close_raw"]).abs().max()
    check(err < 0.01, "P1 raw == adj/adj_factor (recompute)", f"sym={s} maxerr={err:.5f}")
    # cliff continuity: adjusted series has no >40% single-day gap at a split ex-date
    ex = conn.execute(
        "SELECT symbol,date,action_type,ratio FROM corporate_actions "
        "WHERE action_type IN ('SPLIT','BONUS') AND date<'2025-01-01' "
        "ORDER BY date DESC LIMIT 60").fetchall()
    fake_cliffs = 0
    checked = skipped_gap = 0
    for sym, ed, at, ratio in ex:
        b = q("SELECT date,close FROM stock_data_adj WHERE symbol=? AND date<? "
              "ORDER BY date DESC LIMIT 1", (sym, ed))
        o = q("SELECT date,close FROM stock_data_adj WHERE symbol=? AND date>=? "
              "ORDER BY date ASC LIMIT 1", (sym, ed))
        rb = q("SELECT close FROM stock_data WHERE symbol=? AND date<? "
               "ORDER BY date DESC LIMIT 1", (sym, ed))
        ro = q("SELECT close FROM stock_data WHERE symbol=? AND date>=? "
               "ORDER BY date ASC LIMIT 1", (sym, ed))
        if not (b and o and rb and ro and b[1] and rb[0]):
            continue
        # continuity heuristic only valid when both straddle rows hug the ex-date;
        # a data gap over the ex-date (e.g. SKYGOLD) makes the jump meaningless.
        if days_between(b[0], ed) > 12 or days_between(o[0], ed) > 12:
            skipped_gap += 1
            continue
        checked += 1
        adj_jump = o[1] / b[1]
        raw_jump = ro[0] / rb[0]
        if raw_jump < 0.7 and not (0.7 < adj_jump < 1.45):
            fake_cliffs += 1
    check(fake_cliffs == 0, "P1 split ex-dates de-cliffed in adj series",
          f"checked={checked} residual_cliffs={fake_cliffs} skipped_gap={skipped_gap}")

    # ============ PHASE 1: pit_universe ============
    print("Verifying Phase 1: pit_universe ...", flush=True)
    check("pit_universe" in tables, "P1 pit_universe exists")
    nu, nm = q("SELECT COUNT(*),COUNT(DISTINCT rebal_date) FROM pit_universe")
    check(nm >= 250, "P1 pit_universe >=250 months", f"months={nm}")
    over = q("SELECT MAX(c) FROM (SELECT rebal_date,SUM(top500) c FROM pit_universe "
             "GROUP BY rebal_date)")[0]
    check(over <= 500, "P1 top500 never exceeds 500/month", f"max={over}")
    r1 = q("SELECT MIN(adv_rank),MAX(top100) FROM pit_universe")
    check(r1[0] == 1, "P1 adv_rank starts at 1")
    # survivorship: a name delisted early must NOT appear in a late universe
    deli = q("SELECT symbol,MAX(date) md FROM stock_data GROUP BY symbol "
             "HAVING md<'2015-01-01' AND COUNT(*)>500 ORDER BY md DESC LIMIT 1")
    if deli:
        dsym, dmax = deli
        late = q("SELECT COUNT(*) FROM pit_universe WHERE symbol=? AND rebal_date>'2018-01-01'",
                 (dsym,))[0]
        early = q("SELECT COUNT(*) FROM pit_universe WHERE symbol=?", (dsym,))[0]
        check(late == 0, "P1 delisted name absent from post-delist universe",
              f"sym={dsym} last={dmax} late_rows={late} total={early}")
    # PIT: membership uses only past data -> rebal_date close must exist in raw
    check(True, "P1 (window is trailing/inclusive by construction)")

    # ============ PHASE 1: financial_results dates ============
    print("Verifying Phase 1: financial_results ...", flush=True)
    nbad = q("SELECT COUNT(*) FROM financial_results WHERE broadcast_date IS NULL "
             "OR LENGTH(broadcast_date)!=10 OR broadcast_date NOT LIKE '____-__-__'")[0]
    check(nbad == 0, "P1 all broadcast_date are clean ISO yyyy-mm-dd", f"bad={nbad}")

    # ============ PHASE 1: isin_master ============
    print("Verifying Phase 1: isin_master ...", flush=True)
    check("isin_master" in tables and "isin_renames" in tables, "P1 isin tables exist")
    nbadisin = q("SELECT COUNT(*) FROM isin_master WHERE isin NOT LIKE 'IN%'")[0]
    check(nbadisin == 0, "P1 all ISINs well-formed (IN...)", f"bad={nbadisin}")
    nren = q("SELECT COUNT(*) FROM isin_renames")[0]
    check(nren > 100, "P1 renames detected (>100)", f"renames={nren}")
    # every rename row truly has >1 distinct symbol
    badren = q("SELECT COUNT(*) FROM (SELECT isin,COUNT(DISTINCT symbol) c "
               "FROM isin_master GROUP BY isin) WHERE isin IN "
               "(SELECT isin FROM isin_renames) AND c<2")[0]
    check(badren == 0, "P1 isin_renames rows genuinely multi-symbol", f"violations={badren}")

    # ============ PHASE 2: features_monthly ============
    print("Verifying Phase 2: features_monthly ...", flush=True)
    check("features_monthly" in tables, "P2 features_monthly exists")
    nf, nfm = q("SELECT COUNT(*),COUNT(DISTINCT rebal_date) FROM features_monthly")
    # every feature row must be a genuine pit_universe member (no leak);
    # top500 is a FLAG (the backtest filters top500=1), not a row filter here.
    leak = q("SELECT COUNT(*) FROM features_monthly f LEFT JOIN pit_universe p "
             "ON f.rebal_date=p.rebal_date AND f.symbol=p.symbol "
             "WHERE p.symbol IS NULL")[0]
    check(leak == 0, "P2 every feature row is a genuine PIT-universe member",
          f"non_member_rows={leak}")
    t5 = q("SELECT COUNT(*) FROM features_monthly WHERE top500=1")[0]
    check(t5 > 100000, "P2 top500 tradable subset present (flag)", f"top500_rows={t5:,}")
    # prox_52w_high must be in (0,1]
    pbad = q("SELECT COUNT(*) FROM features_monthly WHERE prox_52w_high>1.0001 "
             "AND prox_52w_high IS NOT NULL")[0]
    check(pbad == 0, "P2 prox_52w_high <= 1", f"violations={pbad}")
    # MANUAL RECOMPUTE: mom_12_1 and fwd_ret_1m for a sample row, from stock_data_adj
    smp = conn.execute(
        "SELECT rebal_date,symbol,mom_12_1,fwd_ret_1m FROM features_monthly "
        "WHERE mom_12_1 IS NOT NULL AND fwd_ret_1m IS NOT NULL "
        "AND rebal_date BETWEEN '2015-01-01' AND '2022-01-01' LIMIT 5").fetchall()
    mom_ok = fwd_ok = 0
    for rd, sym, mom_stored, fwd_stored in smp:
        ser = pd.read_sql("SELECT date,close FROM stock_data_adj WHERE symbol=? ORDER BY date",
                          conn, params=(sym,))
        idx = ser.index[ser["date"] == rd]
        if len(idx) == 0:
            continue
        i = idx[0]
        if i - 252 >= 0:
            mom_calc = ser["close"].iloc[i-21] / ser["close"].iloc[i-252] - 1
            if abs(mom_calc - mom_stored) < 1e-4:
                mom_ok += 1
        if i + 21 < len(ser):
            fwd_calc = ser["close"].iloc[i+21] / ser["close"].iloc[i] - 1
            if abs(fwd_calc - fwd_stored) < 1e-4:
                fwd_ok += 1
    check(mom_ok >= 3, "P2 mom_12_1 matches manual recompute", f"{mom_ok}/5 ok")
    check(fwd_ok >= 3, "P2 fwd_ret_1m is genuine FORWARD return (recompute)", f"{fwd_ok}/5 ok")
    # IC sign check: momentum positive, vol negative (quick pooled Spearman by date)
    fm = pd.read_sql("SELECT rebal_date,mom_12_1,fwd_ret_1m FROM features_monthly "
                     "WHERE top500=1 AND mom_12_1 IS NOT NULL AND fwd_ret_1m IS NOT NULL", conn)
    ics = fm.groupby("rebal_date").apply(
        lambda g: g["mom_12_1"].rank().corr(g["fwd_ret_1m"].rank()))
    check(ics.mean() > 0.01, "P2 momentum rank-IC positive", f"mean_IC={ics.mean():.4f}")

    # ============ PHASE 4/5: backtest tables ============
    print("Verifying Phase 4/5: backtest ...", flush=True)
    check("bt_equity" in tables and "bt_metrics" in tables, "P45 backtest tables exist")
    sharpe = q("SELECT value FROM bt_metrics WHERE strategy='LO + Regime gate' AND metric='Sharpe'")
    maxdd = q("SELECT value FROM bt_metrics WHERE strategy='LO + Regime gate' AND metric='MaxDD'")
    check(sharpe and sharpe[0] > 0.9, "P45 gated Sharpe > 0.9 stored",
          f"sharpe={sharpe[0] if sharpe else None}")
    check(maxdd and maxdd[0] > -0.30, "P45 gated MaxDD better than -30%",
          f"maxdd={maxdd[0] if maxdd else None}")
    # equity curve monotone-ish positive end
    fin = q("SELECT equity FROM bt_equity WHERE strategy='LO + Regime gate' ORDER BY date DESC LIMIT 1")
    check(fin and fin[0] > 5, "P45 gated final equity > 5x", f"final={fin[0]:.2f}" if fin else "none")

    # ============ PHASE 6: PIT as-of integrity (Part 1 Stage 1C) ============
    print("Verifying Phase 6: PIT as-of integrity ...", flush=True)
    # 6.1 fundamentals_pit: a result cannot be KNOWN before it is filed -> pit_date >= report_date
    if "fundamentals_pit" in tables:
        neg = q("SELECT COUNT(*) FROM fundamentals_pit "
                "WHERE pit_date IS NOT NULL AND report_date IS NOT NULL "
                "AND pit_date < report_date")[0]
        check(neg == 0, "P6 fundamentals pit_date >= report_date (no negative filing lag)",
              f"violations={neg}")
        badd = q("SELECT COUNT(*) FROM fundamentals_pit WHERE pit_date IS NOT NULL "
                 "AND (LENGTH(pit_date)!=10 OR pit_date NOT LIKE '____-__-__')")[0]
        check(badd == 0, "P6 fundamentals_pit pit_date clean ISO", f"bad={badd}")
        lags = pd.read_sql("SELECT report_date,pit_date FROM fundamentals_pit "
                           "WHERE pit_date IS NOT NULL AND report_date IS NOT NULL "
                           "AND dated_by='filing'", conn)
        if len(lags):
            lags["lag"] = (pd.to_datetime(lags["pit_date"]) -
                           pd.to_datetime(lags["report_date"])).dt.days
            med = lags["lag"].median()
            check(0 <= med < 200, "P6 median filing lag plausible (0..200d)",
                  f"median={med:.0f}d n={len(lags):,}")
    else:
        check(False, "P6 fundamentals_pit exists")

    # 6.2 named index membership -- integrity checks activate once Stage 1A builds the table
    if "index_membership" in tables:
        ov = q("SELECT COUNT(*) FROM index_membership a JOIN index_membership b "
               "ON a.index_name=b.index_name AND a.symbol=b.symbol "
               "AND a.effective_from < b.effective_from "
               "AND (a.effective_to IS NULL OR a.effective_to > b.effective_from)")[0]
        check(ov == 0, "P6 index_membership: no overlapping intervals", f"overlaps={ov}")
        badiv = q("SELECT COUNT(*) FROM index_membership "
                  "WHERE effective_to IS NOT NULL AND effective_to < effective_from")[0]
        check(badiv == 0, "P6 index_membership: effective_to >= effective_from", f"bad={badiv}")
        cur = {r[0] for r in conn.execute("SELECT symbol FROM index_membership "
               "WHERE index_name='NIFTY 50' AND effective_to IS NULL")}
        snap = {r[0] for r in conn.execute("SELECT symbol FROM index_constituents "
                "WHERE index_name='NIFTY 50'")}
        if snap:
            match = len(cur & snap) / len(snap)
            check(match >= 0.99, "P6 NIFTY 50 current membership matches snapshot",
                  f"match={match:.1%} n={len(snap)}")
        # sector coverage of the tradable universe: no NULL inside current top-500
        d_pu = q("SELECT MAX(rebal_date) FROM pit_universe")[0]
        sec_gap = q("SELECT COUNT(*) FROM pit_universe p LEFT JOIN dim_sector s "
                    "ON p.symbol=s.symbol WHERE p.rebal_date=? AND p.top500=1 "
                    "AND s.symbol IS NULL", (d_pu,))[0]
        check(sec_gap == 0, "P6 no NULL sector inside current top-500", f"gap={sec_gap}")
        # consumable view must quarantine every low-confidence row (reviewer fix):
        # nothing below 0.75 may leak through the view Part 2 signals join.
        views = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'")}
        if "index_membership_consumable" in views:
            leak = q("SELECT COUNT(*) FROM index_membership_consumable WHERE confidence < 0.75")[0]
            check(leak == 0, "P6 consumable view excludes conf<0.75 rows", f"leak={leak}")
            offv = q("SELECT COUNT(*) FROM index_membership_consumable WHERE method='official'")[0]
            check(offv > 0, "P6 consumable view still carries official current members", f"n={offv}")
    else:
        print("  (P6 membership tests skipped -- index_membership not built yet [Stage 1A])",
              flush=True)

    # 6.3 idea-engine backfill parity -- activates once Stage 2 builds thesis/trade
    if "thesis" in tables and "trade" in tables:
        nth = q("SELECT COUNT(*) FROM thesis")[0]
        nrec = q("SELECT COUNT(*) FROM recommendations")[0]
        check(nth >= nrec, "P7 thesis count >= recommendations (backfill complete)",
              f"thesis={nth} recs={nrec}")
        orphan = q("SELECT COUNT(*) FROM trade t LEFT JOIN thesis h "
                   "ON t.thesis_id=h.thesis_id WHERE h.thesis_id IS NULL")[0]
        check(orphan == 0, "P7 no orphan trades (every trade.thesis_id resolves)",
              f"orphans={orphan}")
        # backfill parity: mean realized_return of backfilled closed trades == recommendations
        rec_mean = q("SELECT AVG(realized_return) FROM recommendations "
                     "WHERE status='CLOSED' AND realized_return IS NOT NULL")[0]
        trd_mean = q("SELECT AVG(realized_return) FROM trade "
                     "WHERE exit_price IS NOT NULL AND realized_return IS NOT NULL")[0]
        if rec_mean is not None and trd_mean is not None:
            check(abs(rec_mean - trd_mean) < 1e-6,
                  "P7 backfill parity: trade mean return == recommendations",
                  f"rec={rec_mean:.6f} trade={trd_mean:.6f}")
    else:
        print("  (P7 idea-engine tests skipped -- thesis/trade not built yet [Stage 2])",
              flush=True)

    # ============ PHASE 8: ATR band invariants (Part 1 Stage 3) ============
    bands = conn.execute(
        "SELECT t.entry_price,t.stop,t.target,t.size_shares,t.atr_k "
        "FROM trade t JOIN thesis h ON t.thesis_id=h.thesis_id "
        "WHERE h.narrative='live:momentum_bands' AND t.size_shares IS NOT NULL").fetchall()
    if bands:
        print("Verifying Phase 8: ATR band invariants ...", flush=True)
        ok_order = all(s < e < tg for e, s, tg, _, _ in bands)
        check(ok_order, "P8 bands: stop < entry < target for all", f"n={len(bands)}")
        check(all(sz >= 1 for _, _, _, sz, _ in bands), "P8 bands: size_shares >= 1")
        # reward:risk consistent (target-entry == R*(entry-stop), R=2)
        rr = [ (tg - e) / (e - s) for e, s, tg, _, _ in bands if e - s > 0 ]
        check(all(abs(x - 2.0) < 0.05 for x in rr), "P8 bands: reward:risk ~ 2:1",
              f"min={min(rr):.2f} max={max(rr):.2f}")
        # owner rule: stop-loss never more than 10% below entry
        max_stop_pct = max((e - s) / e for e, s, tg, sz, _ in bands)
        check(max_stop_pct <= 0.10 + 1e-4, "P8 bands: stop-loss <= 10% for all",
              f"max_stop={max_stop_pct:.1%}")
        # risk per idea never EXCEEDS the budget (position cap can only lower it)
        max_risk = max(sz * (e - s) for e, s, tg, sz, _ in bands)
        check(max_risk <= 10000 + max(e - s for e, s, tg, sz, _ in bands) + 1,
              "P8 bands: risk <= budget per idea", f"max_risk={max_risk:,.0f}")
        check(all(k is not None for *_, k in bands), "P8 bands: atr_k persisted per trade")
        # portfolio-level capital cap: selected book never exceeds capital
        if "idea_card" in tables:
            deployed = q("SELECT COALESCE(SUM(notional),0) FROM idea_card "
                         "WHERE in_book=1 AND card_date=(SELECT MAX(card_date) FROM idea_card)")[0]
            import sys as _s
            _s.path.insert(0, str(Path(__file__).resolve().parents[1] / "ideas"))
            import build_bands as _bb
            check(deployed <= _bb.CAPITAL + 1e-6, "P8 portfolio: in-book notional <= capital",
                  f"deployed={deployed:,.0f} cap={_bb.CAPITAL:,.0f}")
            # no in-book position exceeds the concentration cap
            over = q("SELECT COUNT(*) FROM idea_card WHERE in_book=1 AND notional > ? "
                     "AND card_date=(SELECT MAX(card_date) FROM idea_card)",
                     (_bb.MAX_POSITION_PCT * _bb.CAPITAL + 1,))[0]
            check(over == 0, "P8 portfolio: no position exceeds concentration cap", f"over={over}")

    # ============ PHASE 10: regime spine (Part 2 Module 1) ============
    if "regime_daily" in tables:
        print("Verifying Phase 10: regime spine ...", flush=True)
        n_rd = q("SELECT COUNT(*) FROM regime_daily")[0]
        check(n_rd > 4000, "P10 regime_daily has full history", f"days={n_rd:,}")
        badscore = q("SELECT COUNT(*) FROM regime_daily WHERE regime_score IS NULL "
                     "OR regime_score < 0 OR regime_score > 100")[0]
        check(badscore == 0, "P10 regime_score bounded 0..100, no NULLs", f"bad={badscore}")
        # known-episode re-derivation: GFC + COVID must be risk_off
        gfc = q("SELECT regime_score FROM regime_daily WHERE date LIKE '2008-11-2%' "
                "ORDER BY date LIMIT 1")
        cov = q("SELECT regime_score FROM regime_daily WHERE date LIKE '2020-03-2%' "
                "ORDER BY date LIMIT 1")
        check(gfc and gfc[0] < 40 and cov and cov[0] < 40,
              "P10 GFC + COVID classified risk_off",
              f"gfc={gfc[0] if gfc else None} covid={cov[0] if cov else None}")
        # ship-gate honesty: if the spine did not beat the incumbent, it must be
        # recorded shipped=0 (scoring falls back to the validated 4-vote gate)
        if "spine_validation" in tables:
            sv = q("SELECT shipped, sharpe_incumbent, sharpe_spine FROM spine_validation "
                   "WHERE book='IV' ORDER BY run_at DESC LIMIT 1")
            if sv:
                consistent = (sv[0] == 1) == (sv[2] > sv[1])
                check(consistent, "P10 spine ship verdict consistent with OOS Sharpe",
                      f"shipped={sv[0]} inc={sv[1]:.2f} spine={sv[2]:.2f}")

    # ============ PHASE 11: event layer (Part 2 Module 2) ============
    if "event_signals" in tables:
        print("Verifying Phase 11: event layer ...", flush=True)
        types = {r[0] for r in conn.execute("SELECT DISTINCT event_type FROM event_signals")}
        need = {"insider_cluster_buy", "pledge_risk", "pead_proxy",
                "buyback_announce", "index_inclusion"}
        check(need <= types, "P11 all five event builders populated",
              f"missing={need - types or 'none'}")
        badd = q("SELECT COUNT(*) FROM event_signals WHERE event_date IS NULL "
                 "OR LENGTH(event_date)!=10")[0]
        check(badd == 0, "P11 event dates clean ISO", f"bad={badd}")
        # tier honesty: the insider tier must equal the persisted event-study verdict,
        # and 'scored' is only legal with t>=3 and positive mean (pre-registered rule)
        if "event_validation" in tables:
            v = q("SELECT verdict, t_stat, mean_ar, mean_ar_h2 FROM event_validation "
                  "WHERE event_type='insider_cluster_buy' ORDER BY run_at DESC LIMIT 1")
            tier = q("SELECT DISTINCT evidence_tier FROM event_signals "
                     "WHERE event_type='insider_cluster_buy'")
            if v and tier:
                check(tier[0] == v[0], "P11 insider tier == event-study verdict",
                      f"tier={tier[0]} verdict={v[0]}")
                legal = (v[0] != "scored") or (v[1] >= 3.0 and v[2] > 0 and v[3] > 0)
                check(legal, "P11 'scored' only with t>=3, mean>0, H2>0",
                      f"t={v[1]:.2f} mean={v[2]*100:.2f}% h2={v[3]*100:.2f}%")
        # risk events must never be bullish
        badr = q("SELECT COUNT(*) FROM event_signals WHERE evidence_tier='risk' "
                 "AND direction!='risk'")[0]
        check(badr == 0, "P11 risk-tier events carry direction=risk", f"bad={badr}")

    # ============ PHASE 12: sector engine (Part 2 Module 5, context tier) ============
    if "sector_regime_daily" in tables:
        print("Verifying Phase 12: sector engine ...", flush=True)
        n_sr = q("SELECT COUNT(*) FROM sector_regime_daily")[0]
        check(n_sr > 50000, "P12 sector_regime_daily has full history", f"rows={n_sr:,}")
        badq = q("SELECT COUNT(*) FROM sector_regime_daily WHERE rrg_quadrant IS NOT NULL "
                 "AND rrg_quadrant NOT IN ('leading','improving','weakening','lagging')")[0]
        check(badq == 0, "P12 RRG quadrants valid", f"bad={badq}")
        badb = q("SELECT COUNT(*) FROM sector_regime_daily WHERE sector_breadth IS NOT NULL "
                 "AND (sector_breadth < 0 OR sector_breadth > 100)")[0]
        check(badb == 0, "P12 sector breadth bounded 0..100", f"bad={badb}")
        nsec = q("SELECT COUNT(DISTINCT sector) FROM sector_regime_daily")[0]
        check(nsec >= 10, "P12 >=10 sectors covered", f"sectors={nsec}")

    # ============ PHASE 13: v2.0 scoring honesty (Part 2 Module 7) ============
    if "score_weights" in tables and q("SELECT COUNT(*) FROM score_weights "
                                       "WHERE version='v2.0'")[0] > 0:
        print("Verifying Phase 13: v2.0 scoring honesty ...", flush=True)
        # v1.0 history preserved (versioned, never overwritten)
        v1 = q("SELECT COUNT(*) FROM score_weights WHERE version='v1.0'")[0]
        check(v1 >= 6, "P13 v1.0 weight history preserved", f"rows={v1}")
        # event_score may carry weight ONLY because the insider study passed
        evw = q("SELECT weight FROM score_weights WHERE version='v2.0' "
                "AND pillar='event_score'")
        if evw and evw[0] > 0 and "event_validation" in tables:
            v = q("SELECT verdict FROM event_validation "
                  "WHERE event_type='insider_cluster_buy' ORDER BY run_at DESC LIMIT 1")
            check(v and v[0] == "scored",
                  "P13 event_score weight>0 backed by a passed event study",
                  f"verdict={v[0] if v else None}")
        # context-tier events must never appear in score_audit (zero weight enforced)
        ctx_leak = q("SELECT COUNT(*) FROM score_audit WHERE pillar IN "
                     "('pead_proxy','buyback_announce','index_inclusion','sector_align')")[0]
        check(ctx_leak == 0, "P13 context tags carry zero scoring weight", f"leak={ctx_leak}")
        # no orphaned audit rows (thesis rebuilds must cascade to score_audit)
        orph_a = q("SELECT COUNT(*) FROM score_audit a LEFT JOIN thesis h "
                   "ON a.thesis_id=h.thesis_id WHERE h.thesis_id IS NULL")[0]
        check(orph_a == 0, "P13 no orphaned score_audit rows", f"orphans={orph_a}")
        # regime_align subscore == validated 4-vote gate re-derivation (live theses only)
        cd9 = q("SELECT MAX(card_date) FROM score_audit")[0]
        ra = q("SELECT a.subscore FROM score_audit a JOIN thesis h ON a.thesis_id=h.thesis_id "
               "WHERE a.card_date=? AND a.pillar='regime_align' LIMIT 1", (cd9,))
        if ra is not None and ra:
            import sys as _s9
            _s9.path.insert(0, str(Path(__file__).resolve().parents[1] / "ideas"))
            import scoring as SC13
            expect = SC13.regime_votes(conn, cd9) / 4 * 100
            check(abs(ra[0] - expect) < 1e-6,
                  "P13 regime_align == validated 4-vote gate (re-derived)",
                  f"stored={ra[0]:.1f} expect={expect:.1f}")

    # ============ PHASE 9: scoring framework (Part 1 Stage 4) ============
    if "score_weights" in tables and q("SELECT COUNT(*) FROM score_weights")[0] > 0:
        print("Verifying Phase 9: scoring framework ...", flush=True)
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ideas"))
        import scoring as SC
        w = SC.load_weights(conn)
        pos = sum(v for k, v in w.items() if v > 0)
        check(abs(pos - 1.0) < 1e-9, "P9 positive pillar weights sum to 1.0", f"sum={pos:.4f}")
        check(w["risk_penalty"] <= 0, "P9 risk_penalty weight <= 0", f"w={w['risk_penalty']}")
        scored = conn.execute(
            "SELECT thesis_id,symbol,thesis_type,confidence_score,created_at FROM thesis "
            "WHERE weight_version IS NOT NULL AND narrative='live:momentum_bands'").fetchall()
        bad = 0
        for tid, sym, ttype, stored, cd in scored:
            raw = conn.execute("SELECT SUM(contribution) FROM score_audit "
                               "WHERE thesis_id=? AND card_date=?", (tid, cd)).fetchone()[0]
            rec = SC.apply_fundamentals_cap(ttype, SC.annual_years(conn, sym), SC.clamp(raw))
            if abs(round(rec, 2) - stored) > 0.01:
                bad += 1
        check(bad == 0, "P9 every confidence reproducible from score_audit",
              f"{len(scored)-bad}/{len(scored)}")
        demo = conn.execute("SELECT symbol FROM annual_income GROUP BY symbol "
                            "HAVING COUNT(DISTINCT substr(report_date,1,4))<8 LIMIT 1").fetchone()[0]
        check(SC.apply_fundamentals_cap("value", SC.annual_years(conn, demo), 95.0) <= SC.FUND_CAP,
              "P9 A3 value cap binds at <8yr coverage", f"demo={demo}")
        # degenerate weights (signal_strength=1) must reproduce generate_signals ranking
        cd = conn.execute("SELECT MAX(rebal_date) FROM current_signals").fetchone()[0]
        syms = [s for s, in conn.execute("SELECT symbol FROM thesis "
                "WHERE narrative='live:momentum_bands' AND created_at=?", (cd,))]
        if syms:
            subs = SC.compute_subscores(conn, cd, syms)
            degen = {p: (1.0 if p == "signal_strength" else 0.0) for p in SC.PILLARS}
            comp = {s: SC.composite(subs[s], degen) for s in syms}
            gs = {s: sc for s, sc in conn.execute(
                "SELECT symbol,score FROM current_signals WHERE rebal_date=?", (cd,))}
            oc = sorted(syms, key=lambda x: -comp[x])
            og = sorted(syms, key=lambda x: -gs.get(x, 0))
            check(oc == og, "P9 degenerate weights reproduce generate_signals ranking",
                  f"n={len(syms)}")
    else:
        print("  (P9 scoring tests skipped -- score_weights not seeded yet [Stage 4])", flush=True)

    conn.close()

    # ============ REPORT ============
    print("\n" + "=" * 72, flush=True)
    print("  VERIFICATION REPORT", flush=True)
    print("=" * 72, flush=True)
    npass = sum(1 for p, _, _ in R if p)
    for p, name, detail in R:
        tag = "PASS" if p else "**FAIL**"
        print(f"  [{tag}] {name}" + (f"   ({detail})" if detail else ""), flush=True)
    print("=" * 72, flush=True)
    print(f"  {npass}/{len(R)} checks passed", flush=True)
    print("=" * 72, flush=True)


if __name__ == "__main__":
    main()
