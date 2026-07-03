"""
run_pipeline.py
================
MICC Data Extraction - Daily Orchestrator

Runs the data-extraction scripts (grouped into market/ macro/ funds/ events/
registry/ trends/ common/) in dependency order, with per-phase resume state.

Usage:
  py -3.14 run_pipeline.py            -> full daily update
  py -3.14 run_pipeline.py --check    -> DB health check only
  py -3.14 run_pipeline.py --weekly   -> also fundamentals + corporate actions + registries

NOTE: use the Python interpreter that has nselib + fredapi installed (py -3.14).
"""

import subprocess
import sys
import time
import os
import json
from datetime import datetime
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent.resolve()
STATE_FILE   = PIPELINE_DIR / "pipeline_state.json"


def log(msg, level="INFO"):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  {msg}", flush=True)


def clean_env():
    env = os.environ.copy()
    try:
        import certifi
        b = certifi.where()
        env["REQUESTS_CA_BUNDLE"] = b
        env["SSL_CERT_FILE"]      = b
        env["CURL_CA_BUNDLE"]     = b
    except ImportError:
        pass
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run(script_rel, desc, args=None, timeout=1800):
    script_path = PIPELINE_DIR / script_rel
    if not script_path.exists():
        log(f"{desc}: script not found ({script_rel})", "FAIL")
        return False
    cmd = [sys.executable, str(script_path)] + (args or [])
    log(f"-> {desc}")
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=str(script_path.parent), env=clean_env(),
        )
        elapsed = time.time() - t0
        if result.returncode == 0:
            log(f"{desc} ({elapsed:.0f}s)", "OK")
            return True
        log(f"{desc}  exit {result.returncode}  ({elapsed:.0f}s)", "FAIL")
        if result.stderr:
            for line in result.stderr.strip().splitlines()[-5:]:
                log(f"   {line}", "FAIL")
        return False
    except subprocess.TimeoutExpired:
        log(f"{desc} timed out after {timeout}s", "FAIL")
        return False
    except Exception as e:
        log(f"{desc} exception: {e}", "FAIL")
        return False


def load_state():
    today = datetime.now().strftime("%Y-%m-%d")
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            if state.get("date") == today:
                return state
        except Exception:
            pass
    return {"date": today, "completed": [], "failed": []}


def save_state(state):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


def run_phase(name, script_rel, desc, state, args=None, timeout=1800):
    if name in state["completed"]:
        log(f"SKIP (already done today): {desc}", "WARN")
        return True
    ok = run(script_rel, desc, args=args, timeout=timeout)
    if ok:
        state["completed"].append(name)
        if name in state["failed"]:
            state["failed"].remove(name)
    elif name not in state["failed"]:
        state["failed"].append(name)
    save_state(state)
    return ok


# (phase_key, script_relative_path, description, args, timeout)
DAILY_PHASES = [
    ("core",        "market/daily_update.py",                  "Core: Stocks + Indices + F&O + Global", None, 1200),
    ("parquet",     "common/export_parquet.py",                "Export stock_data -> per-symbol parquet", None, 600),
    ("delivery",    "market/update_delivery.py",               "Delivery % (nselib)",                   None, 300),
    ("fii_dii",     "market/fetch_nse_data.py",                "FII/DII activity (direct NSE API)",     ["--fii"], 300),
    ("global_idx",  "market/phase9a_fetch_global_indices.py",  "Global indices (yfinance)",             None, 600),
    ("deals",       "market/fetch_deals.py",                   "Bulk/Block/Short deals (snapshot)",     None, 180),
    ("fo_ban",      "market/fetch_fo_ban.py",                  "F&O ban list",                          None, 120),
    ("us_macro",    "macro/update_macro_us.py",                "US Macro (FRED)",                       ["--daily"], 600),
    ("india_macro", "macro/update_macro_india_fred.py",        "FRED India Macro",                      ["--daily"], 300),
    ("world_bank",  "macro/update_world_bank_india.py",        "World Bank India Macro",                None, 180),
    ("phase1",      "macro/fetch_phase1_data.py",              "RBI + G-Sec",                           ["--rbi", "--gsec"], 300),
    ("mf_nav",      "funds/update_mf_nav.py",                  "MF NAVs",                               None, 600),
    ("announce",    "events/phase4_corporate_announcements.py","Corporate Announcements",               None, 180),
    ("insider",     "events/insider_trading_fetch.py",         "Insider Trading (SEBI)",                None, 180),
    ("regime_spine","macro/build_regime_spine.py",             "Multi-axis regime spine (context)",     None, 300),
    ("events_layer","events/build_event_signals.py",           "Event layer (insider clusters/pledge/PEAD)", None, 600),
    ("sector_eng",  "common/build_sector_engine.py",           "Sector RRG + macro betas (context)",    None, 600),
    ("news",        "events/fetch_news.py",                    "Market news headlines (RSS)",           None, 120),
    ("ipo",         "events/fetch_ipo.py",                     "IPO GMP / subscription / listing",      None, 120),
    ("earnings",    "events/fetch_earnings_calendar.py",       "Board meetings + results calendar",     None, 120),
    ("greeks",      "market/phase2_greeks_calculator.py",      "Greeks + GEX (incremental)",            ["--daily"], 600),
    ("trends",      "trends/fetch_trends.py",                  "Google Trends",                         ["--quiet"], 300),
    # --- analytics products (refresh the dashboard from the research layer) ---
    ("signals",     "common/generate_signals.py",              "Live top-decile book + 4-vote regime",  None, 300),
    ("recos",       "common/recommendations.py",               "Stock recos (entry/target/stop) + score", None, 600),
    ("rec_sync",    "ideas/backfill_recommendations.py",       "Sync legacy recs -> thesis/trade mirror", None, 300),
    ("idea_cards",  "ideas/build_idea_cards.py",               "Idea Engine: ATR bands + 6-pillar scoring + cards", None, 600),
    ("intel",       "common/build_market_intel.py",            "Deals + F&O positioning intel",         None, 300),
    ("dashboard",   "common/build_dashboard.py",               "Build self-contained HTML dashboard",   None, 300),
    ("monitor",     "common/monitor.py",                       "Health-check (freshness/quality/regime)", None, 180),
]

WEEKLY_PHASES = [
    ("stock_registry", "registry/refresh_stock_registry.py",   "Stock registry refresh",                ["--headless"], 600),
    ("universe",       "registry/build_tradable_universe.py",  "Tradable universe",                     None, 300),
    ("fundamentals",   "events/update_fundamentals.py",        "Fundamentals TTM",                      None, 7200),
    ("corp_actions",   "events/update_corporate_actions.py",   "Corporate Actions",                     None, 1800),
    ("amfi_flows",     "funds/backfill_amfi_industry.py",      "AMFI MF industry monthly flows",        None, 600),
    ("index_members",  "registry/fetch_index_constituents.py", "Index constituents + sector",           None, 300),
    ("nifty50_hist",   "registry/fetch_niftyindices_nifty50.py","NIFTY 50 survivorship-free history (niftyindices)", None, 120),
    ("index_membership","registry/build_index_membership.py",   "Named PIT index membership (hybrid)",    None, 600),
    ("top500_sectors", "registry/backfill_top500_sectors.py",   "Top-500 sector coverage (ETF tag)",      None, 120),
    ("pcr",            "market/compute_options_analytics.py",  "Options PCR / OI analytics (from fo_data)", None, 900),
    ("max_pain",       "market/compute_max_pain.py",           "Index options max-pain (from fo_data)", None, 600),
    ("mf_master",      "funds/fetch_mf_scheme_master.py",      "MF scheme master (AMC/category)",       None, 180),
    ("annual_fin",     "events/fetch_annual_financials.py",    "Annual financials (yfinance)",          None, 7200),
    ("alphavantage",   "events/fetch_alphavantage.py",         "AlphaVantage US earnings/holdings/insider", None, 300),
    # --- research/strategy layer rebuild (order matters: isin -> adj -> universe -> features -> backtests) ---
    ("isin",        "registry/build_isin_master.py",      "ISIN master + renames",                  None, 600),
    ("adj_prices",  "common/build_adjusted_prices.py",    "Corp-action adjusted prices",            None, 1200),
    ("pit_univ",    "registry/build_pit_universe.py",     "Point-in-time equity universe",          None, 900),
    ("features",    "common/build_feature_store.py",      "As-of feature store + IC report",        None, 900),
    ("backtest",    "common/backtest_momentum.py",        "Flagship backtest (bt_equity/metrics)",  None, 600),
    ("best_config", "common/backtest_best.py",            "Regime-validated best config (bt_best)", None, 600),
    # --- Part 2 ship-gate revalidations (pre-registered rules; verdicts drive tiers) ---
    ("spine_gate",  "common/backtest_regime_spine.py",    "Regime-spine vs 4-vote WF ship-gate",    None, 900),
    ("insider_gate","common/backtest_insider.py",         "Insider cluster event-study ship-gate",  None, 600),
    ("cand_gate",   "common/backtest_signal_candidates.py","Signal-candidate IC ship-gate",         None, 300),
    ("mf_score",    "funds/mf_scorecard.py",              "Equity MF risk-adjusted scorecard",      None, 900),
]


def main():
    if "--check" in sys.argv:
        run("common/check_db_health.py", "DB Health Check", timeout=60)
        return

    weekly = "--weekly" in sys.argv
    state = load_state()

    print()
    print("=" * 65)
    print("  MICC DATA EXTRACTION - DAILY UPDATE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if state["completed"]:
        print(f"  Resuming: already done: {', '.join(state['completed'])}")
    print("=" * 65)
    print()

    r = {}
    phases = DAILY_PHASES + (WEEKLY_PHASES if weekly else [])
    for name, script_rel, desc, args, timeout in phases:
        r[name] = run_phase(name, script_rel, desc, state, args=args, timeout=timeout)

    run("common/check_db_health.py", "Health Check", timeout=60)

    passed = sum(1 for v in r.values() if v)
    failed = sum(1 for v in r.values() if not v)
    print()
    print("=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    for name, ok in r.items():
        print(f"  [{'OK  ' if ok else 'FAIL'}]  {name}")
    print()
    log(f"Passed: {passed}  |  Failed: {failed}")
    print("=" * 65)
    print()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
