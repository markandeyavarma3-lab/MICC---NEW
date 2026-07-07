# -*- coding: utf-8 -*-
"""
phase9b_fix_regime.py  (v2 — correct table)
=============================================
Fixes the regime map failure. Root cause: market_snapshot only stores
~33 recent rows. The correct source for long Nifty 50 history is the
`indices_data` table (column: name='NIFTY 50', col: close) which has
full history going back years.

Also uses `global_indices_daily` (our new table, SPX from 2000) as a
verified fallback.

What this does:
  1. Probes indices_data and global_indices_daily to find the best
     Nifty 50 source (auto-detects column names)
  2. Builds bull/bear/sideways regime map with SMA50/SMA200
  3. Fills window_regime_stats for all 2008 stocks + 147 NSE indices
     + 29 global indices
  4. Patches phase9b_build_window_stats.py so future runs use the
     correct source automatically

Run once:
  cd D:/MICC/data_extraction
  py phase9b_fix_regime.py

Expected: ~10-15 min
Location: D:/MICC/data_extraction/phase9b_fix_regime.py
"""

import sqlite3
import sys
import time
import os
import warnings
from datetime import datetime
from pathlib import Path
from collections import defaultdict

warnings.filterwarnings("ignore")
try:
    import certifi
    os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
    os.environ["SSL_CERT_FILE"]      = certifi.where()
except ImportError:
    pass

import numpy as np
import pandas as pd

DB_PATH      = Path(r"D:\MICC\marketDB\db\market.db")
PARQUET_ROOT = Path(r"D:\MICC\marketDB\stocks\all")

REGIME_WINDOWS = [5, 10, 20, 30, 60, 90, 180, 252]
TODAY_STR      = datetime.today().strftime("%Y-%m-%d")
MIN_ABSOLUTE   = 60


def log(msg, level="INFO"):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: PROBE DB AND BUILD REGIME MAP
# ═══════════════════════════════════════════════════════════════════════════════

def probe_nifty_sources(conn):
    """
    Try every known table/column combination that might hold Nifty 50 history.
    Returns the best (dates_list, closes_list) tuple found.
    Priority: indices_data > global_data > global_indices_daily (SPX proxy skip)
    """
    results = []

    # ── Source 1: indices_data (name='NIFTY 50', col=close) ─────────────────
    # This is the primary NSE index history table
    try:
        cols = [r[1].lower() for r in conn.execute(
            "PRAGMA table_info(indices_data)").fetchall()]
        log(f"indices_data columns: {cols}")

        # Detect close column name
        close_col = None
        for c in ("close", "closing_value", "last", "closing_index_value"):
            if c in cols:
                close_col = c
                break

        # Detect name/index column
        name_col = None
        for c in ("name", "index_name", "index", "symbol"):
            if c in cols:
                name_col = c
                break

        if close_col and name_col:
            # Try multiple Nifty 50 name variants
            for n50 in ("NIFTY 50", "Nifty 50", "NIFTY50", "nifty 50", "NSE:NIFTY50"):
                rows = conn.execute(
                    f"SELECT date, {close_col} FROM indices_data "
                    f"WHERE {name_col}=? AND {close_col}>0 "
                    f"ORDER BY date",
                    (n50,)
                ).fetchall()
                if rows:
                    log(f"indices_data '{n50}' ({close_col}): {len(rows)} rows "
                        f"({rows[0][0]} .. {rows[-1][0]})", "OK")
                    results.append((len(rows), [r[0] for r in rows],
                                    [float(r[1]) for r in rows],
                                    f"indices_data/{n50}"))
                    break

            # If exact match failed, show what names ARE in the table
            if not results:
                sample = conn.execute(
                    f"SELECT DISTINCT {name_col} FROM indices_data "
                    f"ORDER BY {name_col} LIMIT 20"
                ).fetchall()
                log(f"indices_data sample names: {[r[0] for r in sample]}", "WARN")

                # Try LIKE match
                rows = conn.execute(
                    f"SELECT date, {close_col} FROM indices_data "
                    f"WHERE {name_col} LIKE '%NIFTY%50%' AND {close_col}>0 "
                    f"ORDER BY date"
                ).fetchall()
                if rows:
                    log(f"indices_data LIKE NIFTY%50: {len(rows)} rows", "OK")
                    results.append((len(rows), [r[0] for r in rows],
                                    [float(r[1]) for r in rows],
                                    "indices_data/LIKE-NIFTY50"))

    except Exception as e:
        log(f"indices_data probe failed: {e}", "WARN")

    # ── Source 2: global_data (ticker='S&P 500' etc.) ────────────────────────
    # global_data has India VIX and sometimes Nifty
    try:
        tickers = [r[0] for r in conn.execute(
            "SELECT DISTINCT ticker FROM global_data ORDER BY ticker"
        ).fetchall()]
        log(f"global_data tickers: {tickers}")

        for t in ("NIFTY 50", "Nifty 50", "NIFTY", "NSE NIFTY"):
            if t in tickers:
                rows = conn.execute(
                    "SELECT date, close FROM global_data "
                    "WHERE ticker=? AND close>0 ORDER BY date", (t,)
                ).fetchall()
                if rows:
                    log(f"global_data '{t}': {len(rows)} rows", "OK")
                    results.append((len(rows), [r[0] for r in rows],
                                    [float(r[1]) for r in rows],
                                    f"global_data/{t}"))
    except Exception as e:
        log(f"global_data probe failed: {e}", "WARN")

    # ── Source 3: global_indices_daily — use SPX as proxy for regime ─────────
    # If no Nifty source found with 200+ days, use SPX-based regime
    # (SPX and Nifty are highly correlated — ~0.80 long-term)
    try:
        rows = conn.execute(
            "SELECT date, close FROM global_indices_daily "
            "WHERE symbol='SPX' AND close>0 ORDER BY date"
        ).fetchall()
        if rows:
            log(f"global_indices_daily SPX (proxy): {len(rows)} rows", "WARN")
            results.append((len(rows) - 10000,  # lower priority than real Nifty
                             [r[0] for r in rows],
                             [float(r[1]) for r in rows],
                             "global_indices_daily/SPX-proxy"))
    except Exception as e:
        log(f"global_indices_daily probe failed: {e}", "WARN")

    if not results:
        return [], [], "none"

    # Return the source with most rows (excluding proxy penalty)
    results.sort(key=lambda x: x[0], reverse=True)
    best = results[0]
    return best[1], best[2], best[3]


def build_regime_map(conn) -> dict:
    """Build bull/bear/sideways map from best available Nifty 50 data."""
    dates, closes_list, source = probe_nifty_sources(conn)

    if len(dates) < 210:
        log(f"Best source has only {len(dates)} rows — need 210+ for SMA200", "FAIL")
        log("Available sources exhausted. Regime stats will be skipped.", "FAIL")
        return {}

    log(f"Building regime map from: {source}  ({len(dates)} days)")
    closes  = np.array(closes_list, dtype=np.float64)
    sma50   = pd.Series(closes).rolling(50,  min_periods=50).mean().values
    sma200  = pd.Series(closes).rolling(200, min_periods=200).mean().values

    result = {}
    bull = bear = sideways = 0
    for i, d in enumerate(dates):
        if np.isnan(sma200[i]):
            result[d] = "sideways"; sideways += 1
        elif closes[i] > sma50[i] > sma200[i]:
            result[d] = "bull";     bull += 1
        elif closes[i] < sma50[i] < sma200[i]:
            result[d] = "bear";     bear += 1
        else:
            result[d] = "sideways"; sideways += 1

    log(f"Regime map: {len(result)} days  bull={bull} bear={bear} sideways={sideways}", "OK")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# REGIME STATS COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════════

def compute_regime_stats(symbol, asset_type, closes_df, regime_map):
    """
    closes_df: DataFrame with 'date' and 'close' columns, sorted ascending.
    Returns list of dicts for window_regime_stats.
    """
    if closes_df.empty or len(closes_df) < MIN_ABSOLUTE or not regime_map:
        return []

    c_arr = closes_df["close"].values.astype(np.float64)
    dates = closes_df["date"].tolist()
    rows  = []

    for w in REGIME_WINDOWS:
        if len(c_arr) < w + MIN_ABSOLUTE:
            continue
        buy  = c_arr[:-w]
        sell = c_arr[w:]
        rets = (sell - buy) / buy * 100.0
        finite = np.isfinite(rets)

        groups = defaultdict(list)
        for i, (r, ok) in enumerate(zip(rets, finite)):
            if not ok:
                continue
            reg = regime_map.get(dates[i], "sideways")
            groups[reg].append(r)
            groups["all"].append(r)

        for reg, rv_list in groups.items():
            rv = np.array(rv_list)
            if len(rv) < 5:
                continue
            n   = len(rv)
            std = float(np.std(rv, ddof=1)) if n > 1 else 0.0
            rows.append({
                "symbol":        symbol,
                "asset_type":    asset_type,
                "window_days":   w,
                "regime":        reg,
                "n_windows":     n,
                "mean_return":   round(float(np.mean(rv)), 4),
                "median_return": round(float(np.median(rv)), 4),
                "std_return":    round(std, 4),
                "p5":            round(float(np.percentile(rv,  5)), 4),
                "p25":           round(float(np.percentile(rv, 25)), 4),
                "p75":           round(float(np.percentile(rv, 75)), 4),
                "p95":           round(float(np.percentile(rv, 95)), 4),
                "prob_positive": round(float(np.mean(rv > 0)), 4),
                "prob_gt10":     round(float(np.mean(rv > 10)), 4),
                "prob_lt_neg10": round(float(np.mean(rv < -10)), 4),
                "min_return":    round(float(np.min(rv)), 4),
                "max_return":    round(float(np.max(rv)), 4),
                "computed_date": TODAY_STR,
            })
    return rows


def upsert_regime(conn, rows):
    if not rows:
        return 0
    conn.executemany("""
        INSERT OR REPLACE INTO window_regime_stats
        (symbol, asset_type, window_days, regime, n_windows,
         mean_return, median_return, std_return, p5, p25, p75, p95,
         prob_positive, prob_gt10, prob_lt_neg10, min_return, max_return,
         computed_date)
        VALUES (:symbol,:asset_type,:window_days,:regime,:n_windows,
                :mean_return,:median_return,:std_return,:p5,:p25,:p75,:p95,
                :prob_positive,:prob_gt10,:prob_lt_neg10,:min_return,:max_return,
                :computed_date)
    """, rows)
    conn.commit()
    return len(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADERS
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_date(v):
    import re
    s = str(v).strip() if v is not None else ""
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    m = re.match(r"^(\d{1,2})[-/]([A-Za-z]{3})[-/](\d{4})$", s)
    if m:
        d2, mon, y = m.groups()
        mo = {"jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06",
              "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12"
              }.get(mon.lower())
        if mo:
            return f"{y}-{mo}-{d2.zfill(2)}"
    return None


def load_stock(symbol):
    sym_dir = PARQUET_ROOT / symbol
    if not sym_dir.exists():
        return pd.DataFrame()
    dfs = []
    for pf in sorted(sym_dir.glob("*.parquet")):
        try:
            df = pd.read_parquet(pf)
            df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
            if "close" in df.columns and "date" in df.columns:
                dfs.append(df[["date", "close"]])
        except Exception:
            continue
    if not dfs:
        return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    df["date"]  = df["date"].apply(_parse_date)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date","close"])
    df = df[df["close"] > 1.0].sort_values("date").drop_duplicates("date")
    return df[["date","close"]].reset_index(drop=True)


def load_index(conn, index_name):
    try:
        rows = conn.execute(
            "SELECT date, closing_index_value FROM market_snapshot "
            "WHERE index_name=? AND closing_index_value>0 ORDER BY date",
            (index_name,)
        ).fetchall()
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date","close"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna().sort_values("date").drop_duplicates("date").reset_index(drop=True)


def load_global(conn, symbol):
    try:
        rows = conn.execute(
            "SELECT date, close FROM global_indices_daily "
            "WHERE symbol=? AND close IS NOT NULL ORDER BY date",
            (symbol,)
        ).fetchall()
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date","close"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna().sort_values("date").drop_duplicates("date").reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH phase9b_build_window_stats.py
# ═══════════════════════════════════════════════════════════════════════════════

def patch_phase9b(regime_source_info: str):
    """Patch load_regime_map to use indices_data instead of market_snapshot."""
    target = Path(__file__).parent / "phase9b_build_window_stats.py"
    if not target.exists():
        log(f"phase9b not found at {target} — skip patch", "WARN")
        return

    content = target.read_text(encoding="utf-8")
    if "indices_data" in content and "probe_nifty" in content:
        log("phase9b already patched", "WARN")
        return

    OLD = '''def load_regime_map(conn):
    """Bull/Bear/Sideways per date from Nifty 50 SMA trend."""
    try:
        rows = conn.execute(
            "SELECT date, closing_index_value FROM market_snapshot "
            "WHERE index_name='Nifty 50' AND closing_index_value>0 ORDER BY date"
        ).fetchall()
    except Exception:
        return {}
    if len(rows) < 210:
        return {}
    dates  = [r[0] for r in rows]
    closes = np.array([float(r[1]) for r in rows])'''

    NEW = '''def load_regime_map(conn):
    """
    Bull/Bear/Sideways per date from Nifty 50 SMA50/SMA200 trend.
    Source priority:
      1. indices_data table (full NSE index history)
      2. global_data table (has India VIX and sometimes Nifty)
      3. global_indices_daily SPX as correlation proxy (last resort)
    market_snapshot is NOT used — it only stores ~33 recent rows.
    """
    dates = []; closes_list = []

    # Source 1: indices_data
    try:
        cols = [r[1].lower() for r in conn.execute(
            "PRAGMA table_info(indices_data)").fetchall()]
        close_col = next((c for c in ("close","closing_value","last","closing_index_value")
                          if c in cols), None)
        name_col  = next((c for c in ("name","index_name","index","symbol")
                          if c in cols), None)
        if close_col and name_col:
            for n50 in ("NIFTY 50", "Nifty 50", "NIFTY50"):
                rows = conn.execute(
                    f"SELECT date, {close_col} FROM indices_data "
                    f"WHERE {name_col}=? AND {close_col}>0 ORDER BY date",
                    (n50,)
                ).fetchall()
                if len(rows) >= 210:
                    dates       = [r[0] for r in rows]
                    closes_list = [float(r[1]) for r in rows]
                    break
            if not dates:
                rows = conn.execute(
                    f"SELECT date, {close_col} FROM indices_data "
                    f"WHERE {name_col} LIKE '%NIFTY%50%' AND {close_col}>0 "
                    f"ORDER BY date"
                ).fetchall()
                if len(rows) >= 210:
                    dates       = [r[0] for r in rows]
                    closes_list = [float(r[1]) for r in rows]
    except Exception:
        pass

    # Source 2: global_data Nifty
    if len(dates) < 210:
        try:
            for t in ("NIFTY 50", "Nifty 50", "NIFTY"):
                rows = conn.execute(
                    "SELECT date, close FROM global_data "
                    "WHERE ticker=? AND close>0 ORDER BY date", (t,)
                ).fetchall()
                if len(rows) >= 210:
                    dates       = [r[0] for r in rows]
                    closes_list = [float(r[1]) for r in rows]
                    break
        except Exception:
            pass

    # Source 3: SPX proxy
    if len(dates) < 210:
        try:
            rows = conn.execute(
                "SELECT date, close FROM global_indices_daily "
                "WHERE symbol='SPX' AND close>0 ORDER BY date"
            ).fetchall()
            if len(rows) >= 210:
                dates       = [r[0] for r in rows]
                closes_list = [float(r[1]) for r in rows]
        except Exception:
            pass

    if len(dates) < 210:
        return {}

    closes = np.array(closes_list)'''

    if OLD not in content:
        log("load_regime_map block not found in phase9b — manual patch needed", "WARN")
        log("The function signature may have changed. Check phase9b manually.", "WARN")
        return

    # Also fix already_done to not block resume on empty regime table
    OLD2 = '''            if not row: return False
        except Exception:
            return False
    return True'''

    NEW2 = '''            # Don't block --resume if regime table is empty (first run without regime)
            if layer == "regime":
                total = conn.execute(
                    "SELECT COUNT(*) FROM window_regime_stats"
                ).fetchone()[0]
                if total == 0:
                    continue
            if not row: return False
        except Exception:
            return False
    return True'''

    backup = target.with_suffix(".py.bak2")
    backup.write_text(content, encoding="utf-8")

    patched = content.replace(OLD, NEW)
    if OLD2 in patched:
        patched = patched.replace(OLD2, NEW2)
        log("Patch 2 applied: --resume no longer blocked by empty regime table", "OK")

    target.write_text(patched, encoding="utf-8")
    log(f"phase9b patched: load_regime_map now uses indices_data (backup: {backup.name})", "OK")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print()
    print("=" * 65)
    print("  MICC Phase 9B — Regime Map Fix (v2)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)
    print()

    if not DB_PATH.exists():
        log(f"DB not found: {DB_PATH}", "FAIL"); sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-262144")
    conn.execute("PRAGMA temp_store=MEMORY")

    try:
        # ── Step 1: Find the best data source and build regime map ───────────
        log("Step 1/5: Probing DB for Nifty 50 data sources...")
        regime_map = build_regime_map(conn)

        if not regime_map:
            log("All sources failed. Printing full DB table list for diagnosis:", "FAIL")
            tables = conn.execute(
                "SELECT name, (SELECT COUNT(*) FROM sqlite_master "
                " WHERE type='table' AND name=t.name) "
                "FROM sqlite_master t WHERE type='table' ORDER BY name"
            ).fetchall()
            for t in tables:
                try:
                    cnt = conn.execute(f"SELECT COUNT(*) FROM [{t[0]}]").fetchone()[0]
                    print(f"  {t[0]:<40}  {cnt:>10} rows")
                except Exception:
                    print(f"  {t[0]:<40}  (error)")
            log("Run this manually to diagnose:", "WARN")
            log("  py -c \"import sqlite3; c=sqlite3.connect(r'D:/MICC/marketDB/db/market.db'); [print(r) for r in c.execute(\\\"SELECT name FROM sqlite_master WHERE type='table'\\\").fetchall()]\"")
            sys.exit(1)

        # ── Step 2: NSE index regime stats ───────────────────────────────────
        log("Step 2/5: NSE index regime stats (147 indices)...")
        nse_idx = [r[0] for r in conn.execute(
            "SELECT DISTINCT index_name FROM market_snapshot ORDER BY index_name"
        ).fetchall()]
        i_done = i_fail = i_rows = 0
        for name in nse_idx:
            df = load_index(conn, name)
            if df.empty: i_fail += 1; continue
            rows = compute_regime_stats(name, "index", df, regime_map)
            if rows:
                upsert_regime(conn, rows)
                i_rows += len(rows); i_done += 1
            else:
                i_fail += 1
        log(f"NSE indices: {i_done} ok, {i_fail} fail, {i_rows} rows written", "OK")

        # ── Step 3: Global index regime stats ────────────────────────────────
        log("Step 3/5: Global index regime stats (29 symbols)...")
        glob = [r[0] for r in conn.execute(
            "SELECT DISTINCT symbol FROM global_indices_daily"
        ).fetchall()]
        g_done = g_fail = g_rows = 0
        for sym in glob:
            df = load_global(conn, sym)
            if df.empty: g_fail += 1; continue
            rows = compute_regime_stats(sym, "global", df, regime_map)
            if rows:
                upsert_regime(conn, rows)
                g_rows += len(rows); g_done += 1
            else:
                g_fail += 1
        log(f"Global: {g_done} ok, {g_fail} fail, {g_rows} rows written", "OK")

        # ── Step 4: Stock regime stats ───────────────────────────────────────
        log("Step 4/5: Stock regime stats (~10-15 min for 2008 stocks)...")
        existing = [r[0] for r in conn.execute(
            "SELECT DISTINCT symbol FROM symbol_series_stats WHERE asset_type='stock'"
        ).fetchall()]
        log(f"  {len(existing)} stocks with series stats — processing all")

        t0 = time.time()
        done = fail = total_rows = 0
        for i, sym in enumerate(existing, 1):
            df = load_stock(sym)
            if df.empty: fail += 1; continue
            rows = compute_regime_stats(sym, "stock", df, regime_map)
            if rows:
                upsert_regime(conn, rows)
                total_rows += len(rows); done += 1
            else:
                fail += 1
            if i % 250 == 0:
                el  = time.time() - t0
                eta = (el / i) * (len(existing) - i) / 60
                log(f"  [{i:4d}/{len(existing)}]  done={done} fail={fail} "
                    f"rows={total_rows}  ETA={eta:.1f}m")

        elapsed = (time.time() - t0) / 60
        log(f"Stocks: {done} ok, {fail} fail, {total_rows} rows  ({elapsed:.1f} min)", "OK")

        # ── Step 5: Summary + patch ──────────────────────────────────────────
        print()
        print("=" * 65)
        print("  window_regime_stats summary")
        print("=" * 65)
        for at, reg, nsym, nrow in conn.execute("""
            SELECT asset_type, regime, COUNT(DISTINCT symbol), COUNT(*)
            FROM window_regime_stats
            GROUP BY asset_type, regime ORDER BY asset_type, regime
        """).fetchall():
            print(f"  {at:<8}  {reg:<10}  {nsym:>5} symbols  {nrow:>9} rows")
        print()

        log("Step 5/5: Patching phase9b_build_window_stats.py...")
        patch_phase9b("indices_data")

        log("Regime fix COMPLETE", "OK")

    except KeyboardInterrupt:
        log("Interrupted — partial results saved", "WARN")
    except Exception as e:
        log(f"Fatal: {e}", "FAIL")
        import traceback; traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()

    print()
    print("  Next: py agent_iota.py  (Phase 9C)")
    print()


if __name__ == "__main__":
    main()
