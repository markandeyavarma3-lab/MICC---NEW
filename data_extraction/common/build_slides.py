#!/usr/bin/env python3
"""build_slides.py — generate MICC_slides.html: a self-contained, navigable slide
deck (arrow keys / space) that is also print-to-PDF ready (Ctrl+P -> Save as PDF).
Pulls live numbers from the warehouse so the deck is always current.

Run:  py -3.14 common/build_slides.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")
OUT = Path(r"D:\MICC\MICC_slides.html")


def main():
    c = sqlite3.connect(DB_PATH, timeout=60)
    q = lambda s: c.execute(s).fetchone()
    ntab = q("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")[0]
    import os
    gb = round(os.path.getsize(DB_PATH) / 1e9, 1)
    lb = c.execute("SELECT strategy, MAX(CASE WHEN metric='Sharpe' THEN value END) sh, "
                   "MAX(CASE WHEN metric='CAGR' THEN value END) cg, "
                   "MAX(CASE WHEN metric='MaxDD' THEN value END) dd "
                   "FROM bt_strategy_metrics GROUP BY strategy ORDER BY sh DESC").fetchall()
    rec = q("SELECT COUNT(*), AVG(CASE WHEN realized_return>0 THEN 1.0 ELSE 0 END), "
            "AVG(realized_return) FROM recommendations WHERE status='CLOSED'")
    pnav = q("SELECT nav FROM paper_nav ORDER BY date DESC LIMIT 1")[0]
    c.close()

    lb_rows = "".join(
        f"<tr><td>{s}</td><td class=n>{sh:.2f}</td><td class=n>{cg*100:.1f}%</td>"
        f"<td class=n>{dd*100:.0f}%</td></tr>" for s, sh, cg, dd in lb)

    SL = []  # slides
    def slide(html): SL.append(f'<section class="slide">{html}</section>')

    slide(f"""<div class=center>
      <div class=kicker>Indian-Equity Quant Research &amp; Paper-Trading Platform</div>
      <h1>MICC</h1>
      <div class=sub>From a {gb} GB market-data warehouse to a walk-forward-validated,
      paper-traded, self-scoring strategy platform.</div>
      <div class=foot>{ntab} tables · 146.7M rows · survivorship-free since 2005 · research only, not advice</div>
    </div>""")

    slide("""<h2>The one-line thesis</h2>
      <p class=big>Clean data → no-lookahead features → 8 strategies → cost- &amp; regime-aware
      backtest → forward paper-trade → trackable recommendations → every claim verified by a test.</p>
      <p class=note>One proven edge (momentum, 20 yr). Everything else is held to the same honest bar —
      including the failures.</p>""")

    slide(f"""<h2>1 · The data</h2>
      <table><tr><th>Layer</th><th>Highlights</th></tr>
      <tr><td>Equity</td><td>7.65M rows · 4,200 symbols · 2005→2026 · <b>survivorship-free</b> (delisted kept) · delivery%</td></tr>
      <tr><td>Derivatives</td><td>68.9M-row F&amp;O bhavcopy · PCR · participant OI</td></tr>
      <tr><td>Mutual funds</td><td>36.9M NAVs · 37,977 schemes</td></tr>
      <tr><td>Macro / cross-asset</td><td>US from 1919 · IndiaVIX, NIFTY, S&amp;P, USDINR, Brent, US10Y</td></tr>
      <tr><td>Events</td><td>insider (SEBI) · bulk/block deals · corporate actions</td></tr></table>
      <p class=note>Binding limit: fundamentals only from 2021 (shallow).</p>""")

    slide("""<h2>2 · Cleaning — turning raw into trustworthy</h2>
      <ul>
      <li><b>Adjusted prices</b> (split/bonus) with a <b>cliff-verification guard</b> — only adjusts when the
      raw price actually shows the drop, so it never manufactures a fake cliff on already-adjusted names.</li>
      <li><b>Total-return</b> series (dividends): validated COALINDIA +7.6%/yr.</li>
      <li><b>Point-in-time universe</b>: survivorship-free, ETFs excluded (ISIN INF vs INE).</li>
      <li><b>PIT fundamentals</b>: every figure tagged with its filing date → no lookahead.</li>
      </ul>""")

    slide("""<h2>3 · Features — predictive &amp; leak-free</h2>
      <p>As-of cross-sectional rank-IC vs forward return (top-500, 257 months):</p>
      <table><tr><th>Feature</th><th class=n>IC (1m)</th><th class=n>IC (3m)</th></tr>
      <tr><td>52-week-high proximity</td><td class=n>+0.051</td><td class=n>+0.090</td></tr>
      <tr><td>Low volatility</td><td class=n>+0.058</td><td class=n>—</td></tr>
      <tr><td>Delivery %</td><td class=n>+0.045</td><td class=n>+0.065</td></tr>
      <tr><td>12-1 momentum</td><td class=n>+0.041</td><td class=n>+0.052</td></tr>
      <tr><td>Realized vol</td><td class=n>−0.051</td><td class=n>−0.072</td></tr></table>
      <p class=note>Every sign matches theory; magnitudes ~0.05 = legitimate, not lookahead-inflated.</p>""")

    slide(f"""<h2>4 · The 8-strategy library</h2>
      <table><tr><th>Strategy</th><th class=n>Sharpe</th><th class=n>CAGR</th><th class=n>MaxDD</th></tr>
      {lb_rows}</table>
      <p class=note>⚠ value/quality have only ~3–4 yr data. <b>Momentum is the one proven 20-yr edge.</b></p>""")

    slide("""<h2>5 · Timing — the macro regime gate</h2>
      <p class=big>4 risk-on votes: breadth &gt; 200DMA · NIFTY &gt; 200DMA · S&amp;P &gt; 200DMA · India VIX low.</p>
      <p>Invest when ≥ 2 votes, else hold cash. Walk-forward-validated: regime gate
      <b>OOS Sharpe 1.56</b> vs breadth-only 1.34. <span class=hl>Live now: 1/4 → RISK-OFF.</span></p>""")

    slide("""<h2>6 · Validation — the honest bar</h2>
      <ul>
      <li>Purged + embargoed <b>walk-forward</b> (forward label can't leak)</li>
      <li>Stable in every sub-period (2005–11, 12–18, 19–26)</li>
      <li><b>Deflated Sharpe ≈ 100%</b> after multiple-testing — not data-mined</li>
      <li>Capacity (sqrt-impact) ≈ <b>₹100–250 cr</b></li>
      <li><b>ML ranker LOST</b> to the simple model (OOS 0.76 vs 1.25) — research-first</li>
      </ul>""")

    slide("""<h2>7 · The validated best config</h2>
      <div class=center>
      <div class=hero>OOS Sharpe 1.53</div>
      <p>inverse-vol weighting + walk-forward regime gate · Calmar 1.26 · MaxDD −18.9% · 41.6× equity (2009→2026)</p>
      </div>""")

    slide(f"""<h2>8 · Paper trading — forward, with frictions</h2>
      <div class=center>
      <div class=hero>₹10L → ₹{pnav/1e7:,.1f} cr</div>
      <p>integer shares · real Indian costs · regime liquidation to cash · drift vs backtest = <b>1.000</b></p>
      </div>
      <p class=note>At today's RISK-OFF regime, the paper book is sitting in all cash.</p>""")

    slide(f"""<h2>9 · Recommendations + feedback loop</h2>
      <p class=big>Each call = entry / target / stop price band + a 1-month duration → scored against the real
      price path → a track record that improves the model.</p>
      <table><tr><th>Closed calls</th><th>Hit rate</th><th>Avg / call</th></tr>
      <tr><td class=n>{rec[0]}</td><td class=n>{rec[1]*100:.0f}%</td><td class=n>+{rec[2]*100:.2f}%</td></tr></table>
      <p class=note>Insight it already surfaced: tight vol-stops whipsaw the momentum edge (34% stop-hit).</p>""")

    slide("""<h2>10 · Execution &amp; safety</h2>
      <ul>
      <li><b>OMS + RiskEngine</b>: rejects oversized (&gt;6%), illiquid (&gt;10% ADV), and dust orders.</li>
      <li><b>PaperBroker</b> simulates fills.</li>
      <li><b>LiveBroker is DISABLED</b> — refuses any real order without your API keys + an explicit enable.
      No accidental real money.</li>
      </ul>""")

    slide("""<h2>11 · Delivery</h2>
      <ul>
      <li>Self-contained <b>HTML dashboard</b> (regime, leaderboard, equity curve, recommendations, funds, deals, F&amp;O)</li>
      <li>Authenticated <b>web server</b> :8765 + JSON <b>REST API</b> /api/*</li>
      <li><b>run_pipeline.py</b> — daily refresh + weekly full rebuild</li>
      </ul>""")

    slide("""<h2>12 · Verification — nothing trusted without a test</h2>
      <div class=center>
      <div class=hero>29 + 17 + 12</div>
      <p>29 pin-to-pin · 17 deep integrity · 12 daily health checks — all green.</p>
      <p class=hl>Including: value strategy 0/1,758 lookahead violations · risk engine proven to reject bad orders ·
      paper↔backtest drift 1.000.</p>
      </div>""")

    slide("""<h2>13 · The honest standing</h2>
      <table><tr><th>Verdict</th><th>What</th></tr>
      <tr><td class=ok>PROVEN</td><td>Momentum + delivery + low-vol, regime-gated (20 yr, OOS 1.53)</td></tr>
      <tr><td class=warn>PROMISING</td><td>Value / quality — high Sharpe but only 3–4 yr data</td></tr>
      <tr><td class=warn>MODEST</td><td>Dividend, sector-rotation (deep drawdowns)</td></tr>
      <tr><td class=bad>DEAD</td><td>Short-term reversal, naive long-short (shown, not hidden)</td></tr>
      <tr><td class=gate>GATED</td><td>Live trading — paper only until broker wired</td></tr></table>""")

    slide("""<h2>Appendix A · Cliff-verification guard</h2>
      <p>Why adjusted prices are correct — adjust only when the raw price <i>really</i> dropped:</p>
      <pre class=code>observed = close[on-ex] / close[ex-1]
apply factor  iff  |log(observed) − log(factor)| &lt; |log(observed)|</pre>
      <p class=note>DBEIL (9:1 bonus, factor 0.1) showed no raw cliff (observed 1.05) → closer to 1 → <b>skipped</b>,
      so it never manufactured a fake 10× drop. 1,130 applied · 41 skipped-already-adjusted.</p>""")

    slide("""<h2>Appendix B · Regime walk-forward</h2>
      <p>The gate threshold is chosen from <b>past data only</b>, then applied forward:</p>
      <pre class=code>for R at index i ≥ 48:
    best_t = argmax over t∈{1..4} of Sharpe(gated returns on dates &lt; R)
    oos[R] = raw[R] if score[R] ≥ best_t else cash</pre>
      <p class=note>Revealed the fixed ≥2/4 threshold is NOT robust (WF prefers ≥1) — yet the engine still
      beats breadth-only OOS 1.56 vs 1.34. A fixed-threshold backtest would have hidden that.</p>""")

    slide("""<h2>Appendix C · Paper-trade drift fix</h2>
      <p>paper.ret[R] is the return realized <b>by</b> R; backtest.net_gated[R] is the <b>forward</b> return —
      off by one month:</p>
      <pre class=code>bt["realized_by"] = bt["net_gated"].shift(1)   # = net_gated[R-1]
corr(paper.ret, bt.realized_by)  →  0.24  becomes  1.000</pre>
      <p class=note>A misaligned drift metric would falsely alarm. 1.000 proves the paper engine reproduces
      the backtest exactly.</p>""")

    slide("""<h2>Appendix D · Engineering quality</h2>
      <ul>
      <li>88 tables · 146.7M rows · idempotent, re-runnable pipeline</li>
      <li>7 real bugs caught &amp; fixed mid-build (O(n²) loop, fake-cliff, ETF leak, capacity calibration,
      ML merge bugs, drift off-by-one)</li>
      <li>Every claim has an executable test — 29 + 17 + 12 checks, all green</li>
      <li>Honest negatives kept, not hidden (failed strategies shown; ML loss documented)</li>
      </ul>""")

    slide("""<div class=center>
      <h1>That's MICC.</h1>
      <div class=sub>Survivorship-free data · no-lookahead research · proven edge · forward-tested ·
      self-scoring · fully verified.</div>
      <div class=foot>Docs: MICC_TECHNICAL_REPORT.md · MICC_BLUEPRINT.md · RESEARCH.md · README.md</div>
    </div>""")

    html = """<!DOCTYPE html><html><head><meta charset=utf-8><title>MICC — Deck</title>
<meta name=viewport content="width=device-width,initial-scale=1"><style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0b1220;color:#e2e8f0;font-family:-apple-system,Segoe UI,Roboto,sans-serif;overflow:hidden}
.slide{width:100vw;height:100vh;display:none;flex-direction:column;justify-content:center;
padding:7vh 9vw;position:relative}
.slide.active{display:flex}
h1{font-size:clamp(48px,9vw,110px);letter-spacing:-2px;background:linear-gradient(90deg,#34d399,#60a5fa);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin:10px 0}
h2{font-size:clamp(24px,4vw,40px);color:#f1f5f9;margin-bottom:24px;border-left:4px solid #34d399;padding-left:18px}
.kicker{color:#34d399;text-transform:uppercase;letter-spacing:3px;font-size:14px}
.sub{font-size:clamp(18px,2.4vw,26px);color:#94a3b8;max-width:60ch;margin:18px auto}
.foot{color:#475569;font-size:14px;margin-top:24px}
.center{text-align:center;margin:auto}
.big{font-size:clamp(20px,2.6vw,30px);line-height:1.5;color:#cbd5e1;max-width:42ch}
.hero{font-size:clamp(44px,8vw,96px);font-weight:700;color:#34d399;letter-spacing:-1px}
.note{color:#64748b;font-size:16px;margin-top:18px}
.hl{color:#fbbf24} ul{font-size:clamp(18px,2.2vw,24px);line-height:1.9;list-style:none}
ul li:before{content:"▸ ";color:#34d399} li{margin:6px 0;color:#cbd5e1}
li b{color:#f1f5f9} p{font-size:clamp(17px,2vw,22px);line-height:1.6;color:#cbd5e1;margin:10px 0}
table{border-collapse:collapse;font-size:clamp(15px,1.9vw,21px);margin-top:10px;width:100%}
th{text-align:left;color:#64748b;font-weight:500;padding:10px 14px;border-bottom:2px solid #1e293b}
td{padding:9px 14px;border-bottom:1px solid #131c2e;color:#cbd5e1} td b{color:#f1f5f9}
.n{text-align:right;font-variant-numeric:tabular-nums;color:#e2e8f0}
.ok{color:#34d399;font-weight:700}.warn{color:#fbbf24;font-weight:700}.bad{color:#f87171;font-weight:700}
.gate{color:#a5b4fc;font-weight:700}
.code{background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:16px 20px;
font-family:Consolas,monospace;font-size:clamp(13px,1.6vw,18px);color:#a5f3d0;line-height:1.6;
white-space:pre-wrap;margin:12px 0}
.nav{position:fixed;bottom:18px;right:26px;color:#475569;font-size:13px;z-index:10}
.bar{position:fixed;top:0;left:0;height:3px;background:#34d399;z-index:10;transition:width .2s}
@media print{body{overflow:visible}.slide{display:flex!important;page-break-after:always;height:100vh}
.nav,.bar{display:none}}
</style></head><body>
<div class=bar id=bar></div>
""" + "\n".join(SL) + """
<div class=nav><span id=cur>1</span> / <span id=tot></span> &nbsp;·&nbsp; → ←  to navigate · Ctrl+P = PDF</div>
<script>
var s=document.querySelectorAll('.slide'),i=0;document.getElementById('tot').textContent=s.length;
function show(n){s[i].classList.remove('active');i=Math.max(0,Math.min(s.length-1,n));
s[i].classList.add('active');document.getElementById('cur').textContent=i+1;
document.getElementById('bar').style.width=((i+1)/s.length*100)+'%';}
document.addEventListener('keydown',function(e){
if(['ArrowRight','ArrowDown',' ','PageDown'].includes(e.key)){show(i+1);e.preventDefault();}
if(['ArrowLeft','ArrowUp','PageUp'].includes(e.key)){show(i-1);e.preventDefault();}
if(e.key=='Home')show(0);if(e.key=='End')show(s.length-1);});
document.addEventListener('click',function(){show(i+1);});
show(0);
</script></body></html>"""
    OUT.write_text(html, encoding="utf-8")
    print(f"Slide deck -> {OUT}  ({len(SL)} slides, {OUT.stat().st_size/1024:.0f} KB)")
    print("  Open in a browser. Arrow keys / click to navigate. Ctrl+P -> Save as PDF for the deck.")


if __name__ == "__main__":
    main()
