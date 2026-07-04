#!/usr/bin/env python3
"""shp_coverage_audit.py — Part 4 Stage 2: honest coverage audit of the SHP tables.

The DELIVERABLE of Stage 2. Answers, in numbers not vibes: how much PIT-correct,
low-bias shareholding-pattern data do the pre-registered signals actually have to
work with, and where are the holes / biases that would corrupt a future test.

Repeatable: re-run any time as more data lands. Read-only (never writes to the DB).

Sections:
  1. PIT floor + usable window (the real-time-filed range; retro-uploads excluded)
  2. Fill matrix: quarter x segment (enumerated / Table I parsed / Table III parsed)
  3. Table III (FPI/DII) fill rate -- S3/S4 depend on it, it is newer/less uniform
  4. Per-liquidity-tier fill (top100/250/500 via NSE pit_universe, where mappable)
  5. Survivorship verdict -- the single most important line (denominator is
     today's-active-only => biased; quantify the direction)
  6. Revision prevalence by segment
  7. Cross-source promoter-% vs NSE (shareholding_history) across years

Run:  py -3.14 analysis/shp_coverage_audit.py [--md path.md]
"""
import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")
LAG_FLOOR_DAYS = 400   # same trustworthiness gate the fetcher uses

OUT = []
def emit(s=""):
    OUT.append(s)
    print(s, flush=True)


def qtr_label(qend):
    """'2016-03-31' -> '2016-Q4' (Indian FY quarter is cosmetic here; use CY month)."""
    y, m, _ = qend.split("-")
    return {"03": f"{y}-Mar", "06": f"{y}-Jun", "09": f"{y}-Sep", "12": f"{y}-Dec"}.get(m, qend)


def section(title):
    emit("\n" + "=" * 78)
    emit(f"  {title}")
    emit("=" * 78)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default="", help="also write the report to this markdown file")
    a = ap.parse_args()

    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=120)
    c.execute("PRAGMA busy_timeout=120000")

    emit("SHP COVERAGE AUDIT  (Part 4 Stage 2)")
    emit(f"DB: {DB_PATH}")
    tot = c.execute("SELECT COUNT(*) FROM shp_filing").fetchone()[0]
    emit(f"shp_filing rows: {tot:,}")

    # ── 1. PIT floor / usable window ─────────────────────────────────────────
    section("1. PIT FLOOR & USABLE WINDOW")
    emit("Rule: a filing is USABLE iff broadcast within "
         f"{LAG_FLOOR_DAYS}d of quarter-end (real-time filed).")
    emit("Retro-uploads (data posted years late) are PIT-honest but cannot seed a")
    emit("quarter-aligned test -> excluded from the usable window.\n")
    retro = c.execute("SELECT COUNT(*) FROM shp_filing "
                      "WHERE julianday(pit_date)-julianday(quarter_end_date) > ?",
                      (LAG_FLOOR_DAYS,)).fetchone()[0]
    usable = c.execute("SELECT MIN(quarter_end_date), MAX(quarter_end_date), "
                       "COUNT(DISTINCT quarter_end_date) FROM shp_filing "
                       "WHERE julianday(pit_date)-julianday(quarter_end_date) <= ?",
                       (LAG_FLOOR_DAYS,)).fetchone()
    emit(f"retro-uploads excluded : {retro:,}")
    emit(f"usable window          : {usable[0]} -> {usable[1]}  ({usable[2]} distinct quarters)")
    # the cliff: filings per quarter, to show where real coverage begins
    emit("\nfilings/quarter around the ramp (shows the Mar-2016 cliff):")
    for qend, n in c.execute(
            "SELECT quarter_end_date, COUNT(*) FROM shp_filing "
            "WHERE julianday(pit_date)-julianday(quarter_end_date) <= ? "
            "AND quarter_end_date <= '2016-06-30' "
            "GROUP BY quarter_end_date ORDER BY quarter_end_date DESC LIMIT 6", (LAG_FLOOR_DAYS,)):
        emit(f"    {qtr_label(qend):>10}  {n:>6}")

    # ── 2. Fill matrix: quarter x segment ────────────────────────────────────
    section("2. FILL MATRIX  (usable window; current-version filings only)")
    emit("Per quarter: enumerated filings, Table I parsed, Table III parsed.")
    emit("'parse %' = Table I parsed / enumerated (fetcher completeness).\n")
    emit(f"  {'quarter':>10} {'seg':>4} {'enum':>6} {'tblI':>6} {'tblIII':>7} "
         f"{'parse%':>7} {'t3%':>6}")
    rows = c.execute(f"""
        SELECT f.quarter_end_date, f.exchange_segment,
               COUNT(*) AS enum,
               SUM(CASE WHEN f.parse_status='parsed' THEN 1 ELSE 0 END) AS t1,
               SUM(CASE WHEN EXISTS(SELECT 1 FROM shp_institutional_summary s
                                    WHERE s.filing_id=f.filing_id) THEN 1 ELSE 0 END) AS t3
        FROM shp_filing f
        WHERE f.is_current_version=1
          AND julianday(f.pit_date)-julianday(f.quarter_end_date) <= {LAG_FLOOR_DAYS}
        GROUP BY f.quarter_end_date, f.exchange_segment
        ORDER BY f.quarter_end_date DESC, f.exchange_segment
    """).fetchall()
    for qend, seg, enum, t1, t3 in rows:
        p1 = 100 * t1 / enum if enum else 0
        p3 = 100 * t3 / enum if enum else 0
        emit(f"  {qtr_label(qend):>10} {seg[:4]:>4} {enum:>6} {t1:>6} {t3:>7} "
             f"{p1:>6.0f}% {p3:>5.0f}%")

    # ── 3. Table III fill rate (headline) ────────────────────────────────────
    section("3. TABLE III (FPI/DII) FILL RATE  -- S3/S4 depend on this")
    t1_tot, t3_tot = c.execute(f"""
        SELECT SUM(CASE WHEN f.parse_status='parsed' THEN 1 ELSE 0 END),
               SUM(CASE WHEN EXISTS(SELECT 1 FROM shp_institutional_summary s
                                    WHERE s.filing_id=f.filing_id) THEN 1 ELSE 0 END)
        FROM shp_filing f
        WHERE f.is_current_version=1
          AND julianday(f.pit_date)-julianday(f.quarter_end_date) <= {LAG_FLOOR_DAYS}
    """).fetchone()
    emit(f"Table I parsed (usable) : {t1_tot or 0:,}")
    emit(f"Table III present       : {t3_tot or 0:,}  "
         f"({100*(t3_tot or 0)/(t1_tot or 1):.0f}% of Table-I-parsed)")
    miss = c.execute(f"""
        SELECT COUNT(*) FROM shp_filing f
        WHERE f.is_current_version=1 AND f.parse_status='parsed'
          AND julianday(f.pit_date)-julianday(f.quarter_end_date) <= {LAG_FLOOR_DAYS}
          AND NOT EXISTS(SELECT 1 FROM shp_institutional_summary s
                         WHERE s.filing_id=f.filing_id)
    """).fetchone()[0]
    emit(f"Table I parsed but Table III MISSING: {miss:,}  (backfill still in progress if >0)")

    # ── 3b. FPI/DII format break (load-bearing for S3/S4) ────────────────────
    section("3b. FPI/DII SUBTOTAL AVAILABILITY  -- BSE format break ~Sep 2022")
    emit("BSE's SHP institutional format changed. NEW format has clean B1 (domestic")
    emit("institutions) / B2 (foreign institutions) subtotals; OLD format lumps all")
    emit("institutions into B1 and leaves B2=0, so a clean foreign/domestic split at the")
    emit("subtotal level does NOT exist pre-break. The FPI *line* ('Foreign Portfolio")
    emit("Investors%') stays populated throughout, so fpi_delta (S3) is recoverable across")
    emit("the window by SUMMING is_aggregate FPI rows; but dii_delta (S4) via the clean B1")
    emit("subtotal is only reliable post-break, and old-format 'Any Other' institution")
    emit("rows are ambiguous foreign/domestic. This shrinks S4's clean depth.\n")
    emit(f"  {'quarter':>10} {'filings':>8} {'B2>0':>6} {'B2pop%':>7} {'FPIline%':>9}")
    fb = c.execute(f"""
        SELECT f.quarter_end_date, COUNT(DISTINCT f.filing_id) AS nf,
          COUNT(DISTINCT CASE WHEN EXISTS(SELECT 1 FROM shp_institutional_summary s
                WHERE s.filing_id=f.filing_id AND s.level='Sub Total B2' AND s.pct_holding>0)
              THEN f.filing_id END) AS b2pop,
          COUNT(DISTINCT CASE WHEN EXISTS(SELECT 1 FROM shp_institutional_summary s
                WHERE s.filing_id=f.filing_id AND s.is_aggregate=1
                  AND s.level LIKE 'Foreign Portfolio Investors%')
              THEN f.filing_id END) AS fpi
        FROM shp_filing f
        WHERE f.is_current_version=1 AND f.parse_status='parsed'
          AND EXISTS(SELECT 1 FROM shp_institutional_summary s WHERE s.filing_id=f.filing_id)
          AND julianday(f.pit_date)-julianday(f.quarter_end_date) <= {LAG_FLOOR_DAYS}
        GROUP BY f.quarter_end_date ORDER BY f.quarter_end_date DESC
    """).fetchall()
    for qend, nf, b2pop, fpi in fb:
        emit(f"  {qtr_label(qend):>10} {nf:>8} {b2pop:>6} "
             f"{100*b2pop/nf if nf else 0:>6.0f}% {100*fpi/nf if nf else 0:>8.0f}%")
    emit("\n=> The quarter where B2pop% jumps to ~100% is the clean-DII floor. Report it.")

    # ── 4. Per-liquidity-tier fill (NSE pit_universe via ISIN) ───────────────
    section("4. FILL BY LIQUIDITY TIER  (NSE top100/250/500 via ISIN map; partial)")
    emit("Approximate: BSE scrip -> ISIN -> NSE symbol -> latest pit_universe tier.")
    emit("Only the BSE names that map to an NSE liquid symbol are counted here.\n")
    tiers = c.execute(f"""
        WITH latest AS (SELECT symbol, top100, top250, top500 FROM pit_universe
                        WHERE rebal_date=(SELECT MAX(rebal_date) FROM pit_universe)),
             mapped AS (
               SELECT DISTINCT f.scrip_code,
                      MAX(CASE WHEN l.top100 THEN 1 ELSE 0 END) t100,
                      MAX(CASE WHEN l.top250 THEN 1 ELSE 0 END) t250,
                      MAX(CASE WHEN l.top500 THEN 1 ELSE 0 END) t500
               FROM shp_filing f
               JOIN isin_master im ON im.isin=f.isin
               JOIN latest l ON l.symbol=im.symbol
               WHERE f.is_current_version=1 AND f.parse_status='parsed'
                 AND julianday(f.pit_date)-julianday(f.quarter_end_date) <= {LAG_FLOOR_DAYS}
               GROUP BY f.scrip_code)
        SELECT SUM(t100), SUM(t250), SUM(t500), COUNT(*) FROM mapped
    """).fetchone()
    emit(f"  BSE scrips w/ parsed SHP that map to NSE top100: {tiers[0] or 0}")
    emit(f"  ... top250: {tiers[1] or 0}   ... top500: {tiers[2] or 0}   "
         f"mapped total: {tiers[3] or 0}")
    emit("  (Coverage of the liquid, capacity-realistic U1 universe -- the tier the")
    emit("   pre-registered signals' primary test uses -- is effectively complete when")
    emit("   these approach the NSE tier sizes of 100/250/500.)")

    # ── 5. Survivorship verdict (THE line) ───────────────────────────────────
    section("5. SURVIVORSHIP VERDICT  *** the most important line ***")
    active = c.execute("SELECT COUNT(*) FROM bse_stock_registry WHERE is_active=1").fetchone()[0]
    emit("Enumeration universe = BSE ListofScripData?status=Active = TODAY's listed")
    emit(f"names only ({active:,} active scrips). Delisted-before-today names are NEVER")
    emit("enumerated -> their SHP history is entirely absent.\n")
    emit("=> The historical universe is NOT survivorship-free. Both numerator and")
    emit("   denominator are survivor-conditioned.")
    # quantify the direction: survivor count per quarter vs the latest quarter
    latest_n = c.execute(f"""SELECT COUNT(DISTINCT scrip_code) FROM shp_filing
        WHERE is_current_version=1 AND parse_status='parsed'
          AND quarter_end_date=(SELECT MAX(quarter_end_date) FROM shp_filing
              WHERE julianday(pit_date)-julianday(quarter_end_date) <= {LAG_FLOOR_DAYS}
                AND quarter_end_date < date('now'))""").fetchone()[0]
    emit(f"\nsurvivor filings per quarter (distinct scrips) vs latest full quarter ({latest_n}):")
    for qend, n in c.execute(f"""
        SELECT quarter_end_date, COUNT(DISTINCT scrip_code) FROM shp_filing
        WHERE is_current_version=1
          AND julianday(pit_date)-julianday(quarter_end_date) <= {LAG_FLOOR_DAYS}
          AND quarter_end_date IN ('2016-03-31','2018-03-31','2020-03-31',
                                   '2022-03-31','2024-03-31','2025-03-31')
        GROUP BY quarter_end_date ORDER BY quarter_end_date"""):
        ratio = 100 * n / latest_n if latest_n else 0
        emit(f"    {qtr_label(qend):>10}  {n:>5}  ({ratio:>3.0f}% of latest)")
    emit("\nInterpretation: the decline going back is a MIX of (a) real listing-age")
    emit("(fewer companies existed / had IPO'd) and (b) survivorship (names that")
    emit("delisted are invisible). We cannot cleanly separate them without enumerating")
    emit("delisted scrips -- that is Stage 3. For a pledge/crash signal this bias is")
    emit("ADVERSE and directional: the worst names (which delist) are exactly the ones")
    emit("missing, so any crash-risk effect measured on survivors is UNDERSTATED.")

    # ── 6. Revision prevalence ───────────────────────────────────────────────
    section("6. REVISION PREVALENCE")
    for seg in ("mainboard", "sme"):
        r = c.execute(f"""
            SELECT COUNT(*) AS scrip_qtrs,
                   SUM(CASE WHEN nver>1 THEN 1 ELSE 0 END) AS revised
            FROM (SELECT scrip_code, qtrid, COUNT(*) nver FROM shp_filing
                  WHERE exchange_segment=?
                    AND julianday(pit_date)-julianday(quarter_end_date) <= {LAG_FLOOR_DAYS}
                  GROUP BY scrip_code, qtrid)""", (seg,)).fetchone()
        sq, rev = r[0] or 0, r[1] or 0
        emit(f"  {seg:>10}: {rev:,} / {sq:,} scrip-quarters have >1 version "
             f"({100*rev/sq if sq else 0:.2f}%)")

    # ── 7. Cross-source promoter-% vs NSE, by year ───────────────────────────
    section("7. CROSS-SOURCE PROMOTER-% vs NSE (shareholding_history), BY YEAR")
    emit("Independent exchange + independent fetcher. Agreement within 1pp; a drop in")
    emit("older years = a data-quality warning for those years.\n")
    emit(f"  {'year':>6} {'overlaps':>9} {'within1pp':>10} {'agree%':>7}")
    for yr in range(2016, 2027):
        xs = c.execute(f"""
            SELECT s.pct_holding AS bse, sh.promoter_pct AS nse
            FROM shp_filing f
            JOIN shp_category_summary s ON s.filing_id=f.filing_id AND s.category_code='STA1A2'
            JOIN isin_master im ON im.isin=f.isin
            JOIN shareholding_history sh ON sh.symbol=im.symbol
                 AND sh.quarter = substr(f.quarter_end_date,1,4) || '-Q' ||
                     ((CAST(substr(f.quarter_end_date,6,2) AS INTEGER)+2)/3)
            WHERE f.is_current_version=1 AND f.parse_status='parsed'
              AND substr(f.quarter_end_date,1,4)='{yr}'
              AND sh.promoter_pct IS NOT NULL""").fetchall()
        if not xs:
            continue
        ok = sum(1 for b, n in xs if abs(b - n) <= 1.0)
        emit(f"  {yr:>6} {len(xs):>9} {ok:>10} {100*ok/len(xs):>6.0f}%")

    # ── bottom line ──────────────────────────────────────────────────────────
    section("BOTTOM LINE (usable quarters for the pre-registered signals)")
    full_q = c.execute(f"""
        SELECT COUNT(*) FROM (
          SELECT quarter_end_date FROM shp_filing f
          WHERE f.is_current_version=1 AND f.parse_status='parsed'
            AND julianday(f.pit_date)-julianday(f.quarter_end_date) <= {LAG_FLOOR_DAYS}
            AND f.quarter_end_date < date('now')
          GROUP BY quarter_end_date
          HAVING COUNT(DISTINCT scrip_code) >= 500)""").fetchone()[0]
    emit(f"Quarters with >=500 parsed survivor scrips: {full_q}")
    emit("This is the effective N for a top-500 (U1) quarterly cross-sectional test,")
    emit("BEFORE the survivorship haircut. Power reminder from the brief: t>=3.0 at")
    emit("N~60 needs annualized net Sharpe ~0.77 -- demanding for a lag-eroded signal.")
    emit("Survivorship bias (Section 5) makes the *true* testable N effectively smaller")
    emit("for any signal correlated with delisting risk (esp. pledge).")

    c.close()
    if a.md:
        Path(a.md).write_text("```\n" + "\n".join(OUT) + "\n```\n", encoding="utf-8")
        print(f"\n[written to {a.md}]")


if __name__ == "__main__":
    main()
