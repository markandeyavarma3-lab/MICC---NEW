#!/usr/bin/env python3
"""api.py — PHASE 6: JSON REST API over the MICC warehouse + strategy outputs.

Stdlib only (no FastAPI). Imported by serve_dashboard.py, which dispatches /api/*
paths here and returns JSON. Endpoints expose the live research/product layer so the
dashboard (or any client) can query it programmatically.

Endpoints:
  /api                      list endpoints
  /api/regime               live 4-vote macro regime
  /api/strategies           strategy leaderboard (metrics)
  /api/signals              today's top-decile portfolio
  /api/paper                paper-trading NAV series + summary
  /api/funds                top equity funds (MF scorecard)
  /api/deals                insider/bulk smart-money intel
  /api/fno                  F&O positioning intel
  /api/ideas                live Idea-Engine cards (entry/stop/target + confidence)
  /api/thesis/{id}          one thesis: card, trades, per-pillar score audit
  /api/asset/{symbol}       single-asset profile (features, sector, signal)
"""
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")


def _rows(c, sql, params=()):
    return [dict(r) for r in c.execute(sql, params).fetchall()]


def handle(path):
    """Return (status_code, json-serializable object)."""
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        if path in ("/api", "/api/"):
            return 200, {"service": "MICC API", "endpoints": [
                "/api/regime", "/api/strategies", "/api/signals", "/api/recommendations",
                "/api/paper", "/api/funds", "/api/deals", "/api/fno", "/api/ideas",
                "/api/thesis/{id}", "/api/asset/{symbol}"]}

        if path == "/api/regime":
            br = c.execute("SELECT date,pct_above_200dma,pct_above_50dma FROM market_breadth "
                           "ORDER BY date DESC LIMIT 1").fetchone()
            return 200, {"date": br["date"], "pct_above_200dma": br["pct_above_200dma"],
                         "pct_above_50dma": br["pct_above_50dma"]}

        if path == "/api/strategies":
            d = {}
            for r in _rows(c, "SELECT strategy,metric,value FROM bt_strategy_metrics"):
                d.setdefault(r["strategy"], {})[r["metric"]] = r["value"]
            out = [{"strategy": k, **v} for k, v in d.items()]
            return 200, sorted(out, key=lambda x: -x.get("Sharpe", -9))

        if path == "/api/signals":
            return 200, _rows(c, "SELECT rank,symbol,company,score,mom_12_1,deliv_1m,med_turnover "
                                 "FROM current_signals WHERE in_portfolio=1 ORDER BY rank")

        if path == "/api/paper":
            nav = _rows(c, "SELECT date,nav FROM paper_nav ORDER BY date")
            return 200, {"final_nav": nav[-1]["nav"] if nav else None,
                         "start": nav[0]["date"] if nav else None, "n": len(nav), "series": nav}

        if path == "/api/funds":
            return 200, _rows(c, "SELECT scheme_name,amc,cat_short,cagr_3y,sharpe_3y,max_dd "
                                 "FROM mf_scorecard WHERE plan='Direct' AND cagr_3y IS NOT NULL "
                                 "ORDER BY sharpe_3y DESC LIMIT 25")

        if path == "/api/recommendations":
            op = _rows(c, "SELECT rec_date,symbol,company,entry,target,stop,horizon_days FROM "
                          "recommendations WHERE status='OPEN' AND rec_date=(SELECT MAX(rec_date) "
                          "FROM recommendations) ORDER BY score DESC")
            cl = c.execute("SELECT COUNT(*), AVG(CASE WHEN realized_return>0 THEN 1.0 ELSE 0 END), "
                           "AVG(realized_return) FROM recommendations WHERE status='CLOSED'").fetchone()
            return 200, {"open_calls": op, "track_record": {
                "closed": cl[0], "hit_rate": cl[1], "avg_return": cl[2]}}

        if path == "/api/deals":
            return 200, _rows(c, "SELECT category,symbol,detail,value FROM deals_intel")
        if path == "/api/fno":
            return 200, _rows(c, "SELECT category,symbol,detail,value FROM fno_intel")

        if path == "/api/ideas":
            cd = c.execute("SELECT MAX(card_date) FROM idea_card").fetchone()[0]
            cards = _rows(c, "SELECT thesis_id,symbol,company,sector,thesis_type,timeframe_class,"
                             "entry,stop,target,rr_ratio,size_shares,confidence_score,"
                             "notional,in_book,pillar_json,context_json "
                             "FROM idea_card WHERE card_date=? ORDER BY confidence_score DESC", (cd,))
            import json as _json
            for row in cards:
                row["pillars"] = _json.loads(row.pop("pillar_json") or "{}")
                row["context"] = _json.loads(row.pop("context_json") or "{}")
            return 200, {"card_date": cd, "n": len(cards), "cards": cards}

        if path == "/api/best":
            eq = _rows(c, "SELECT date, ret, equity FROM bt_best ORDER BY date")
            peak = 0.0
            for r in eq:
                peak = max(peak, r["equity"])
                r["drawdown"] = round(r["equity"] / peak - 1, 4) if peak else 0
            return 200, {"n": len(eq), "series": eq}

        if path == "/api/risk":
            hist = _rows(c, "SELECT * FROM risk_state_daily ORDER BY as_of_date DESC LIMIT 90")
            return 200, {"current": hist[0] if hist else None, "history": hist}

        if path == "/api/review":
            rev = _rows(c, "SELECT * FROM weekly_review ORDER BY review_id DESC LIMIT 1")
            props = _rows(c, "SELECT * FROM weight_proposal ORDER BY proposal_id DESC LIMIT 20")
            wts = _rows(c, "SELECT version, pillar, weight, rationale FROM score_weights "
                           "WHERE pillar NOT LIKE '\\_%' ESCAPE '\\' ORDER BY version, pillar")
            return 200, {"latest": rev[0] if rev else None, "proposals": props, "weights": wts}

        if path == "/api/verdicts":
            prereg = _rows(c, "SELECT * FROM signal_preregistration ORDER BY signal")
            cand = _rows(c, "SELECT * FROM signal_candidate_validation ORDER BY candidate")
            ev = _rows(c, "SELECT * FROM event_validation")
            spine = _rows(c, "SELECT * FROM spine_validation")
            ml = _rows(c, "SELECT exp_id, created_at, model_family, status, "
                          "pre_registered_criteria_json FROM ml_experiment")
            mlr = _rows(c, "SELECT exp_id, model, sharpe, deflated_sharpe, kendall_w "
                           "FROM ml_result ORDER BY exp_id, path_id")
            exitc = _rows(c, "SELECT * FROM exit_calibration ORDER BY variant")
            return 200, {"preregistration": prereg, "candidates": cand, "events": ev,
                         "spine": spine, "ml_experiments": ml, "ml_paths": mlr,
                         "exit_calibration": exitc}

        if path == "/api/events":
            recent = _rows(c, "SELECT symbol, event_date, event_type, direction, magnitude, "
                              "evidence_tier FROM event_signals "
                              "ORDER BY event_date DESC LIMIT 60")
            shadow = _rows(c, "SELECT event_type, COUNT(*) n, SUM(filled_63) filled63, "
                              "AVG(CASE WHEN filled_63=1 AND fwd_63>0 THEN 1.0 "
                              "WHEN filled_63=1 THEN 0 END) hit63, "
                              "AVG(CASE WHEN filled_63=1 THEN fwd_63 END) avg63 "
                              "FROM event_shadow_thesis GROUP BY event_type")
            tags = _rows(c, "SELECT tag, COUNT(*) n FROM announcement_tags "
                            "GROUP BY tag ORDER BY n DESC")
            return 200, {"recent": recent, "shadow": shadow, "tags": tags}

        if path == "/api/health":
            hb = _rows(c, "SELECT ts, check_name, status, detail FROM monitoring_log "
                          "WHERE check_name LIKE 'heartbeat:%' ORDER BY ts DESC LIMIT 12")
            streak = 0
            for r in hb:
                if r["status"] == "OK":
                    streak += 1
                else:
                    break
            fresh = {}
            for tbl, col in [("stock_data", "date"), ("current_signals", "rebal_date"),
                             ("idea_card", "card_date"), ("regime_daily", "date")]:
                try:
                    fresh[tbl] = c.execute(f"SELECT MAX({col}) FROM {tbl}").fetchone()[0]
                except Exception:
                    fresh[tbl] = None
            bak = _rows(c, "SELECT ts, detail FROM monitoring_log "
                           "WHERE check_name='backup:weekly' ORDER BY ts DESC LIMIT 1")
            return 200, {"heartbeats": hb, "streak": streak, "target": 10,
                         "freshness": fresh, "last_backup": bak[0] if bak else None}

        if path == "/api/sectors":
            return 200, _rows(c, "SELECT sector, rs_vs_nifty, rs_mom, rrg_quadrant, "
                                 "sector_breadth, sector_score, n_members "
                                 "FROM sector_regime_daily WHERE date="
                                 "(SELECT MAX(date) FROM sector_regime_daily) "
                                 "ORDER BY rs_vs_nifty DESC")

        m = re.match(r"/api/thesis/(\d+)$", path)
        if m:
            tid = int(m.group(1))
            th = _rows(c, "SELECT * FROM thesis WHERE thesis_id=?", (tid,))
            if not th:
                return 404, {"error": f"no thesis {tid}"}
            trades = _rows(c, "SELECT entry_date,entry_price,stop,target,size_shares,atr_k,"
                              "exit_date,exit_price,exit_reason,realized_return FROM trade "
                              "WHERE thesis_id=? ORDER BY trade_id", (tid,))
            audit = _rows(c, "SELECT pillar,subscore,weight,contribution,weight_version "
                             "FROM score_audit WHERE thesis_id=? ORDER BY contribution DESC", (tid,))
            return 200, {"thesis": th[0], "trades": trades, "score_audit": audit}

        m = re.match(r"/api/asset/([A-Za-z0-9&._\-]+)$", path)
        if m:
            sym = m.group(1).upper()
            feat = _rows(c, "SELECT * FROM features_monthly WHERE symbol=? ORDER BY rebal_date DESC LIMIT 1", (sym,))
            sec = _rows(c, "SELECT sector FROM dim_sector WHERE symbol=?", (sym,))
            sig = _rows(c, "SELECT rank,score FROM current_signals WHERE symbol=?", (sym,))
            ff = _rows(c, "SELECT report_date,eps,roe FROM fundamentals_features WHERE symbol=? "
                          "ORDER BY report_date DESC LIMIT 1", (sym,))
            if not (feat or sec or sig):
                return 404, {"error": f"no data for {sym}"}
            return 200, {"symbol": sym, "sector": sec[0]["sector"] if sec else None,
                         "latest_features": feat[0] if feat else None,
                         "fundamentals": ff[0] if ff else None,
                         "signal": sig[0] if sig else None}

        return 404, {"error": "unknown endpoint", "see": "/api"}
    except Exception as e:
        return 500, {"error": str(e)[:200]}
    finally:
        c.close()
