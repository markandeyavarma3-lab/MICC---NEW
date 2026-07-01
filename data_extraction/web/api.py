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
                "/api/paper", "/api/funds", "/api/deals", "/api/fno", "/api/asset/{symbol}"]}

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
