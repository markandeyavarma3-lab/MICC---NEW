#!/usr/bin/env python3
"""build_dashboard.py — PHASE 3/10: self-contained interactive HTML dashboard.

Generates MICC_dashboard.html (repo root) from the live tables: the 4-vote macro
regime, the best-strategy equity curve vs benchmark, headline metrics, today's
top-decile portfolio, and the top equity mutual funds. One file, opens in any
browser, no server. Research output only — not investment advice.

Run:  py -3.14 common/build_dashboard.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
OUT = Path(r"D:\MICC\MICC_dashboard.html")
PERIODS_YR = 12


def metrics(r):
    r = pd.Series(r).dropna()
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (PERIODS_YR / len(r)) - 1
    vol = r.std() * np.sqrt(PERIODS_YR)
    sharpe = r.mean() * PERIODS_YR / vol
    dd = (eq / eq.cummax() - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sharpe, maxdd=dd,
                calmar=cagr / abs(dd), final=eq.iloc[-1])


def regime(conn):
    bd, p200, p50 = conn.execute(
        "SELECT date,pct_above_200dma,pct_above_50dma FROM market_breadth "
        "ORDER BY date DESC LIMIT 1").fetchone()
    gi = pd.read_sql("SELECT date,symbol,close FROM global_indices_daily "
                     "WHERE symbol IN ('NIFTY50','SPX','IndiaVIX')", conn)

    def trend(sym):
        d = gi[gi["symbol"] == sym].sort_values("date")
        return None if len(d) < 200 else float(d["close"].iloc[-1]) > float(d["close"].tail(200).mean())

    d = gi[gi["symbol"] == "IndiaVIX"].sort_values("date")
    vix = None if len(d) < 252 else float(d["close"].iloc[-1]) < float(d["close"].tail(252).median())
    votes = {"Breadth &gt;50%": p200 >= 50, "NIFTY &gt; 200DMA": trend("NIFTY50"),
             "S&amp;P &gt; 200DMA": trend("SPX"), "India VIX low": vix}
    score = sum(1 for v in votes.values() if v)
    return bd, votes, score


def card(label, value, sub=""):
    return (f'<div class="card"><div class="cv">{value}</div>'
            f'<div class="cl">{label}</div><div class="cs">{sub}</div></div>')


def table(df, fmts):
    head = "".join(f"<th>{c}</th>" for c in df.columns)
    rows = ""
    for _, r in df.iterrows():
        rows += "<tr>" + "".join(f"<td>{fmts.get(c, str)(r[c])}</td>" for c in df.columns) + "</tr>"
    return f'<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")

    best = pd.read_sql("SELECT date,ret,equity FROM bt_best ORDER BY date", conn)
    bench = pd.read_sql("SELECT date,ret FROM bt_equity WHERE strategy='Bench (EW top500)' "
                        "ORDER BY date", conn)
    m = metrics(best["ret"])

    # align benchmark to best window, rebased
    bench = bench[bench["date"].isin(best["date"])].copy()
    bench["eq"] = (1 + bench["ret"]).cumprod()

    sig = pd.read_sql("SELECT * FROM current_signals WHERE in_portfolio=1 ORDER BY rank", conn)
    asof = sig["rebal_date"].iloc[0] if len(sig) else "—"
    try:
        funds = pd.read_sql("SELECT scheme_name,amc,cat_short,plan,cagr_3y,sharpe_3y,max_dd "
                            "FROM mf_scorecard WHERE plan='Direct' AND cagr_3y IS NOT NULL "
                            "ORDER BY sharpe_3y DESC LIMIT 12", conn)
    except Exception:
        funds = pd.DataFrame()
    try:
        deals = pd.read_sql("SELECT category,symbol,detail,value FROM deals_intel", conn)
        fno = pd.read_sql("SELECT category,symbol,detail,value FROM fno_intel", conn)
    except Exception:
        deals = fno = pd.DataFrame()
    try:
        sm = pd.read_sql("SELECT strategy,metric,value FROM bt_strategy_metrics", conn)
        lb = sm.pivot(index="strategy", columns="metric", values="value").reset_index()
        lb = lb.sort_values("Sharpe", ascending=False)
    except Exception:
        lb = pd.DataFrame()
    try:
        recs = pd.read_sql("SELECT symbol,company,entry,target,stop FROM recommendations "
                           "WHERE status='OPEN' AND rec_date=(SELECT MAX(rec_date) FROM "
                           "recommendations) ORDER BY score DESC LIMIT 12", conn)
        rtr = conn.execute("SELECT COUNT(*), AVG(CASE WHEN realized_return>0 THEN 1.0 ELSE 0 END), "
                           "AVG(realized_return) FROM recommendations WHERE status='CLOSED'").fetchone()
    except Exception:
        recs, rtr = pd.DataFrame(), (0, 0, 0)
    try:
        ideas = pd.read_sql("SELECT symbol,company,sector,timeframe_class,entry,stop,target,"
                            "rr_ratio,size_shares,confidence_score,pillar_json,context_json,"
                            "in_book FROM idea_card "
                            "WHERE card_date=(SELECT MAX(card_date) FROM idea_card) "
                            "ORDER BY confidence_score DESC LIMIT 15", conn)
    except Exception:
        ideas = pd.DataFrame()
    try:
        riskrow = conn.execute(
            "SELECT as_of_date, equity, drawdown_pct, consec_losses, risk_budget_mult, "
            "halt_new_cards, avg_pairwise_corr, regime_votes, sector_concentration_json "
            "FROM risk_state_daily ORDER BY as_of_date DESC LIMIT 1").fetchone()
    except Exception:
        riskrow = None
    try:
        wr = conn.execute("SELECT narrative_md FROM weekly_review "
                          "ORDER BY review_id DESC LIMIT 1").fetchone()
        weights_hist = pd.read_sql(
            "SELECT version, pillar, weight FROM score_weights "
            "WHERE pillar NOT LIKE '\\_%' ESCAPE '\\' ORDER BY version, pillar", conn)
    except Exception:
        wr, weights_hist = None, pd.DataFrame()
    bdate, votes, score = regime(conn)
    conn.close()

    # equity curve figure
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=best["date"], y=best["equity"], name="Best strategy",
                             line=dict(color="#34d399", width=2)))
    fig.add_trace(go.Scatter(x=bench["date"], y=bench["eq"], name="Benchmark (EW top500)",
                             line=dict(color="#94a3b8", width=1.5, dash="dot")))
    fig.update_layout(template="plotly_dark", height=380, yaxis_type="log",
                      margin=dict(l=40, r=20, t=30, b=30),
                      paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
                      legend=dict(orientation="h", y=1.1),
                      yaxis_title="Growth of 1 (log)")
    chart = fig.to_html(full_html=False, include_plotlyjs=True, config={"displayModeBar": False})

    risk_on = score >= 2
    regime_html = "".join(
        f'<span class="vote {"on" if v else ("off" if v is not None else "na")}">{k}</span>'
        for k, v in votes.items())

    sig_disp = sig[["rank", "symbol", "company", "score", "mom_12_1", "deliv_1m", "med_turnover"]].head(20)
    sig_disp.columns = ["#", "Symbol", "Company", "Score", "12-1 Mom", "Deliv%", "Turnover"]
    sig_tbl = table(sig_disp, {
        "Company": lambda x: str(x)[:30] if pd.notna(x) else "",
        "Score": lambda x: f"{x:.0f}", "12-1 Mom": lambda x: f"{x*100:+.0f}%",
        "Deliv%": lambda x: f"{x:.0f}", "Turnover": lambda x: f"₹{x/1e7:,.0f}cr"})

    if len(lb):
        for col in ["CAGR", "Sharpe", "Sortino", "MaxDD", "Calmar", "Months"]:
            if col not in lb.columns:
                lb[col] = float("nan")
        lbd = lb[["strategy", "CAGR", "Sharpe", "Sortino", "MaxDD", "Calmar", "Months"]].copy()
        lbd.columns = ["Strategy", "CAGR", "Sharpe", "Sortino", "Max DD", "Calmar", "Months"]
        lb_tbl = table(lbd, {
            "CAGR": lambda x: f"{x*100:.1f}%", "Sharpe": lambda x: f"{x:.2f}",
            "Sortino": lambda x: f"{x:.2f}", "Max DD": lambda x: f"{x*100:.0f}%",
            "Calmar": lambda x: f"{x:.2f}", "Months": lambda x: f"{x:.0f}"})
    else:
        lb_tbl = "<p>Run <code>common/strategy_engine.py</code> to populate.</p>"

    if len(funds):
        funds.columns = ["Fund", "AMC", "Category", "Plan", "3y CAGR", "3y Sharpe", "Max DD"]
        fund_tbl = table(funds, {
            "Fund": lambda x: str(x)[:46], "AMC": lambda x: str(x).replace(" Mutual Fund", "")[:20],
            "3y CAGR": lambda x: f"{x*100:.1f}%", "3y Sharpe": lambda x: f"{x:.2f}",
            "Max DD": lambda x: f"{x*100:.0f}%"})
    else:
        fund_tbl = "<p>Run <code>funds/mf_scorecard.py</code> to populate.</p>"

    def intel_tbl(df, valfmt):
        if not len(df):
            return "<p style='color:#64748b'>No recent signals (run build_market_intel.py).</p>"
        rows = "".join(
            f'<tr><td><span class="tag">{r["category"]}</span></td>'
            f'<td><b>{r["symbol"]}</b></td><td>{r["detail"]}</td><td>{valfmt(r)}</td></tr>'
            for _, r in df.iterrows())
        return ('<table><thead><tr><th>Signal</th><th>Symbol</th><th>Detail</th><th></th>'
                f'</tr></thead><tbody>{rows}</tbody></table>')

    deals_tbl = intel_tbl(deals, lambda r: f"₹{r['value']/1e7:,.0f}cr" if r["value"] > 0 else "")
    fno_tbl = intel_tbl(fno, lambda r: f"{r['value']:+.1f}%" if "buildup" in r["category"] else "")

    if len(recs):
        recs["co"] = recs["company"].fillna("").str.slice(0, 26)
        recs["t%"] = (recs["target"] / recs["entry"] - 1) * 100
        recs["s%"] = (recs["stop"] / recs["entry"] - 1) * 100
        rd = recs[["symbol", "co", "entry", "target", "t%", "stop", "s%"]]
        rd.columns = ["Symbol", "Company", "Entry", "Target", "T%", "Stop", "S%"]
        rec_tbl = table(rd, {
            "Entry": lambda x: f"₹{x:,.0f}", "Target": lambda x: f"₹{x:,.0f}",
            "T%": lambda x: f"+{x:.0f}%", "Stop": lambda x: f"₹{x:,.0f}",
            "S%": lambda x: f"{x:.0f}%"})
    else:
        rec_tbl = "<p>Run <code>common/recommendations.py</code> to populate.</p>"
    rec_card = (f'{card("Track record", f"{rtr[1]*100:.0f}%", f"hit rate · {rtr[0]} closed")}'
                f'{card("Avg / call", f"{rtr[2]*100:+.2f}%", "1-month horizon")}') if rtr and rtr[0] else ""

    if len(ideas):
        import json as _json

        def _why(pj):
            try:
                d = _json.loads(pj)
                top = sorted(d.items(), key=lambda kv: -kv[1]["contribution"])[:2]
                return ", ".join(f'{k.split("_")[0]} {v["contribution"]:+.0f}' for k, v in top)
            except Exception:
                return ""

        def _ctx(cj):
            try:
                d = _json.loads(cj or "{}")
                bits = []
                if "sector_rrg" in d:
                    bits.append(d["sector_rrg"].split(" (")[0])
                bits += [k.replace("_", " ") for k in d if k not in
                         ("regime_spine", "sector_rrg")]
                return ", ".join(bits[:3])
            except Exception:
                return ""
        ideas["why"] = ideas["pillar_json"].map(_why)
        ideas["ctx"] = ideas["context_json"].map(_ctx)
        ideas["bk"] = ideas["in_book"].map(lambda x: "✓" if x else "wait")
        idd = ideas[["symbol", "timeframe_class", "entry", "stop", "target", "rr_ratio",
                     "size_shares", "confidence_score", "why", "ctx", "bk"]].copy()
        idd.columns = ["Symbol", "Frame", "Entry", "Stop", "Target", "R:R", "Size",
                       "Conf", "Why (top pillars)", "Context", "Book"]
        idea_tbl = table(idd, {
            "Entry": lambda x: f"₹{x:,.0f}", "Stop": lambda x: f"₹{x:,.0f}",
            "Target": lambda x: f"₹{x:,.0f}", "R:R": lambda x: f"{x:.1f}",
            "Size": lambda x: f"{int(x)}", "Conf": lambda x: f"{x:.0f}"})
    else:
        idea_tbl = "<p>Run <code>ideas/build_idea_cards.py</code> to populate.</p>"

    # --- risk meta-engine panel ---
    if riskrow:
        _, req, rdd, rcl, rmult, rhalt, rcorr, rvotes, rconc = riskrow
        import json as _json2
        conc = _json2.loads(rconc or "{}")
        top_conc = ", ".join(f"{k} {v*100:.0f}%" for k, v in list(conc.items())[:4])
        risk_cards = (
            card("Desk R-PnL", f"₹{req/1e5:.1f}L", "cumulative, R-based") +
            card("Drawdown", f"{rdd*100:.1f}%", "brake at 10/15/22%") +
            card("Risk budget", f"×{rmult}", "HALTED" if rhalt else "normal") +
            card("Loss streak", f"{rcl}", "brake at 3") +
            card("Holdings corr", "n/a" if rcorr is None else f"{rcorr:.2f}", "throttle >0.6"))
        risk_html = (f'<div class="cards">{risk_cards}</div>'
                     f'<div style="color:#64748b;font-size:11px;margin-top:6px">'
                     f'Sector exposure: {top_conc or "n/a"} · governance only, not alpha</div>')
    else:
        risk_html = "<p>Run <code>common/build_risk_state.py</code> to populate.</p>"

    # --- weekly review + weight evolution ---
    review_html = ""
    if wr and wr[0]:
        body = wr[0].replace("# ", "").replace("*", "").replace("\n", "<br>")
        review_html = f'<div style="font-size:13px;color:#cbd5e1;line-height:1.6">{body}</div>'
    if len(weights_hist):
        wp = weights_hist.pivot(index="pillar", columns="version", values="weight").reset_index()
        wp.columns.name = None
        review_html += "<h3 style='font-size:13px;color:#94a3b8;margin-top:14px'>Weight evolution (versioned)</h3>"
        review_html += table(wp, {c: (lambda x: "" if pd.isna(x) else f"{x:+.2f}")
                                  for c in wp.columns if c != "pillar"})

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>MICC Dashboard</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#0b1220;color:#e2e8f0;
font-family:-apple-system,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:1100px;margin:0 auto;padding:24px}}
h1{{font-size:24px;margin:0}} .sub{{color:#64748b;font-size:13px;margin:4px 0 20px}}
h2{{font-size:15px;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;
margin:28px 0 12px;border-bottom:1px solid #1e293b;padding-bottom:8px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap}}
.card{{background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:14px 18px;flex:1;min-width:120px}}
.cv{{font-size:24px;font-weight:600;color:#f1f5f9}} .cl{{font-size:12px;color:#94a3b8;margin-top:4px}}
.cs{{font-size:11px;color:#64748b}}
.regime{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:#0f172a;
border:1px solid #1e293b;border-radius:10px;padding:16px}}
.badge{{font-size:18px;font-weight:700;padding:6px 16px;border-radius:8px}}
.badge.on{{background:#064e3b;color:#34d399}} .badge.off{{background:#3f1d1d;color:#f87171}}
.vote{{font-size:12px;padding:5px 10px;border-radius:6px;border:1px solid #1e293b}}
.vote.on{{color:#34d399;border-color:#065f46}} .vote.off{{color:#f87171;border-color:#7f1d1d}}
.vote.na{{color:#64748b}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;color:#64748b;font-weight:500;padding:8px;border-bottom:1px solid #1e293b}}
td{{padding:8px;border-bottom:1px solid #131c2e}} tr:hover td{{background:#0f172a}}
.foot{{color:#475569;font-size:11px;margin-top:30px;text-align:center}}
code{{background:#1e293b;padding:2px 6px;border-radius:4px}}
.tag{{font-size:11px;color:#a5b4fc;background:#1e1b4b;padding:2px 8px;border-radius:5px;white-space:nowrap}}
.banner{{background:#2a1e05;border:1px solid #78350f;color:#fbbf24;font-size:12px;
padding:10px 14px;border-radius:8px;margin:0 0 18px}}
</style></head><body><div class="wrap">
<h1>MICC — Indian Equity Quant Dashboard</h1>
<div class="sub">Survivorship-free · corp-action-adjusted · point-in-time · {asof} · research only, not advice</div>
<div class="banner">⚠ Dashboard polish ≠ validated edge. Only the momentum strategy is out-of-sample proven (Sharpe {m['sharpe']:.2f}). Idea-card <b>confidence is a transparent heuristic composite</b> (see per-pillar breakdown), not a return forecast; value/quality ideas are capped until fundamentals depth improves.</div>

<h2>Market Regime</h2>
<div class="regime">
  <span class="badge {'on' if risk_on else 'off'}">{'RISK-ON' if risk_on else 'RISK-OFF'} · {score}/4</span>
  {regime_html}
  <span style="color:#64748b;font-size:12px;margin-left:auto">as of {bdate}</span>
</div>

<h2>Best Strategy — inverse-vol + walk-forward regime gate (OOS 2009→2026)</h2>
<div class="cards">
  {card("Sharpe", f"{m['sharpe']:.2f}", "out-of-sample")}
  {card("CAGR", f"{m['cagr']*100:.1f}%", "net of costs")}
  {card("Max DD", f"{m['maxdd']*100:.0f}%", "")}
  {card("Calmar", f"{m['calmar']:.2f}", "")}
  {card("Growth of 1", f"{m['final']:.0f}x", "since 2009")}
</div>
<div style="margin-top:16px">{chart}</div>

<h2>Strategy Library — Leaderboard (net, regime-gated)</h2>
{lb_tbl}
<div style="color:#64748b;font-size:11px;margin-top:6px">⚠ value/quality have short (~3–4yr) history — fundamentals start 2021. Momentum is the proven 20-yr edge.</div>

<h2>Stock Recommendations — entry / target / stop (1-month) + track record</h2>
<div class="cards">{rec_card}</div>
<div style="margin-top:12px">{rec_tbl}</div>
<div style="color:#64748b;font-size:11px;margin-top:6px">Calls are logged, then scored after their duration vs the real price path → the feedback loop that improves the model. Research only, not advice.</div>

<h2>Risk Meta-Engine — drawdown/streak brakes · concentration</h2>
{risk_html}

<h2>Idea Cards — ATR bands · auto timeframe · 7-pillar confidence</h2>
{idea_tbl}
<div style="color:#64748b;font-size:11px;margin-top:6px">Entry/stop/target from ATR-14 (swing 1.75× · positional 2.75×), equal rupee-risk sizing. Confidence = transparent linear composite of 6 pillars; "Why" shows the two largest contributions. Full audit via <code>/api/thesis/&lt;id&gt;</code>.</div>

<h2>Today's Top-Decile Portfolio {'(held as CASH — regime risk-off)' if not risk_on else ''}</h2>
{sig_tbl}

<h2>Top Equity Funds (Direct Growth, by 3y Sharpe)</h2>
{fund_tbl}

<h2>Friday Learning Loop — latest review &amp; weight evolution</h2>
{review_html or '<p>Runs Fridays (weekly pipeline).</p>'}

<h2>Smart Money — Insider Cluster-Buys &amp; Bulk-Deal Accumulation</h2>
{deals_tbl}

<h2>F&amp;O Positioning — Futures Buildup &amp; PCR Extremes</h2>
{fno_tbl}

<div class="foot">MICC research pipeline · momentum + delivery + low-vol composite · breadth/regime gated ·
generated from live SQLite warehouse · not investment advice</div>
</div></body></html>"""

    OUT.write_text(html, encoding="utf-8")
    print(f"Dashboard written -> {OUT}  ({OUT.stat().st_size/1024:.0f} KB)", flush=True)
    print(f"  regime {score}/4 ({'RISK-ON' if risk_on else 'RISK-OFF'}), "
          f"best Sharpe {m['sharpe']:.2f}, {len(sig)} holdings, {len(funds)} funds", flush=True)


if __name__ == "__main__":
    main()
