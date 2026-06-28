# -*- coding: utf-8 -*-
"""
phase9b_build_window_stats.py  (v2 — ADVANCED ENGINE)
=======================================================
Builds the complete multi-window statistical warehouse for all
NSE stocks (2675), NSE indices (147), and global indices (29).

WHAT THIS COMPUTES (per symbol):

  LAYER 1 — Core window stats (17 horizons):
    Windows: 1, 2, 3, 5, 7, 10, 15, 20, 30, 45, 60, 90, 120, 180, 252, 504, 756d
    - mean, median, std, min, max
    - percentiles: p1, p5, p10, p25, p50, p75, p90, p95, p99
    - P(>0%), P(>2%), P(>5%), P(>10%), P(>20%), P(>50%)
    - P(<-2%), P(<-5%), P(<-10%), P(<-20%), P(<-50%)
    - annualised return equivalent
    - Sharpe-like ratio (mean/std)
    - Calmar-like ratio (mean/abs(worst_window))
    - top-10 best + top-10 worst episodes (start date, end date, return %)

  LAYER 2 — Full-history series stats (one row per symbol):
    - Total trading days, date range
    - Annualised return (CAGR), total return %
    - Annualised volatility
    - Max drawdown % with start/trough/recovery dates + duration in days
    - Sharpe ratio, Sortino ratio, Calmar ratio
    - Skewness and kurtosis of daily returns
    - % of positive days
    - 52-week high/low + % distance from each

  LAYER 3 — Regime-sliced window stats (Bull / Bear / Sideways / All):
    - Same window distribution split by Nifty 50 regime
    - Selected windows: 5, 10, 20, 30, 60, 90, 180, 252d

  LAYER 4 — Seasonality (month, quarter, weekday):
    - Average monthly return (Jan-Dec) across all years
    - Average quarterly return (Q1-Q4) across all years
    - Average weekday return (Mon-Fri)

  LAYER 5 — Correlations to 7 benchmarks:
    - Nifty 50, Nifty Bank, S&P 500, Gold, DXY, VIX, USD/INR
    - Rolling 1y, 3y, 5y, all-time Pearson correlation
    - Beta vs Nifty 50 (1y rolling)

  LAYER 6 — Technical indicators (current snapshot):
    - RSI(14), RSI(21)
    - MACD line, signal, histogram (12/26/9)
    - Bollinger Band position (0=lower, 1=upper) + bandwidth %
    - ATR(14) as % of price
    - ADX(14)
    - % above SMA20, SMA50, SMA200
    - SMA20>SMA50 and SMA50>SMA200 flags (golden/death cross)
    - 52-week high/low + % from each
    - Volume surge: last-20d avg vs last-252d avg

NEW DB TABLES WRITTEN:
  window_stats        (upgraded with new columns)
  window_extremes     (TOP_N expanded to 10)
  symbol_series_stats (NEW)
  window_regime_stats (NEW)
  symbol_seasonality  (NEW)
  symbol_correlations (NEW)
  symbol_technicals   (NEW)

RUN MODES:
  py phase9b_build_window_stats.py                  FULL (all layers, all symbols)
  py phase9b_build_window_stats.py --stocks-only    stocks only
  py phase9b_build_window_stats.py --indices-only   NSE + global indices only
  py phase9b_build_window_stats.py --sym RELIANCE   single symbol debug/refresh
  py phase9b_build_window_stats.py --resume         skip already-computed symbols
  py phase9b_build_window_stats.py --layer window   recompute one layer only
    (layers: window | series | regime | seasonality | correlations | technicals)

EXPECTED RUNTIME (Intel Ultra 5 125H):
  Indices (147 NSE + 29 global): ~10 min
  Stocks all 6 layers (2675):    ~3-5 hours

Location: D:/MICC/data_extraction/phase9b_build_window_stats.py
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

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

DB_PATH      = Path(r"D:\marketDB\db\market.db")
PARQUET_ROOT = Path(r"D:\marketDB\stocks\all")

WINDOWS = [1, 2, 3, 5, 7, 10, 15, 20, 30, 45, 60, 90, 120, 180, 252, 504, 756]
REGIME_WINDOWS = [5, 10, 20, 30, 60, 90, 180, 252]

TOP_N          = 10
MIN_ABSOLUTE   = 60
MIN_WIN_FACTOR = 3

TODAY_STR = datetime.today().strftime("%Y-%m-%d")

ETF_PATTERNS = (
    "ETF", "LIQUID", "GOLD", "SILVER", "GILT", "BEES", "MOM30",
    "SETF", "BSLGOLD", "ABSLPAY", "ICICIB22", "NIFTYBEES",
)

GLOBAL_BENCHMARKS = {
    "SPX":    "S&P 500",
    "Gold":   "Gold",
    "DXY":    "USD Index",
    "VIX":    "VIX",
    "USDINR": "USD/INR",
}
NSE_BENCHMARKS = {
    "Nifty 50":   "Nifty50",
    "Nifty Bank": "NiftyBank",
}


# ═══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

def log(msg, level="INFO"):
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag = {"OK": " OK ", "FAIL": "FAIL", "WARN": "WARN"}.get(level, "INFO")
    print(f"[{ts}] [{tag}]  {msg}", flush=True)


def is_etf(s):
    return any(p in s.upper() for p in ETF_PATTERNS)


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE / SCHEMA SETUP
# ═══════════════════════════════════════════════════════════════════════════════

def ensure_tables(conn):
    cur = conn.cursor()

    # Upgrade window_stats with new columns if coming from v1
    existing_ws = {r[1].lower() for r in cur.execute("PRAGMA table_info(window_stats)").fetchall()}
    new_ws_cols = [
        ("p1", "REAL"), ("p10", "REAL"), ("p90", "REAL"), ("p99", "REAL"),
        ("prob_gt2", "REAL"), ("prob_gt50", "REAL"),
        ("prob_lt_neg2", "REAL"), ("prob_lt_neg50", "REAL"),
        ("sharpe_ratio", "REAL"), ("calmar_ratio", "REAL"),
    ]
    for col, ct in new_ws_cols:
        if col not in existing_ws:
            cur.execute(f"ALTER TABLE window_stats ADD COLUMN {col} {ct}")
            log(f"window_stats: added column {col}")

    # symbol_series_stats
    cur.execute("""
        CREATE TABLE IF NOT EXISTS symbol_series_stats (
            symbol TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'stock',
            first_date TEXT, last_date TEXT, n_trading_days INTEGER,
            cagr_pct REAL, total_return_pct REAL, ann_volatility_pct REAL,
            max_drawdown_pct REAL, mdd_start_date TEXT, mdd_trough_date TEXT,
            mdd_recovery_date TEXT, mdd_duration_days INTEGER, mdd_recovery_days INTEGER,
            sharpe_ratio REAL, calmar_ratio REAL, sortino_ratio REAL,
            skewness REAL, kurtosis REAL, pct_positive_days REAL,
            last_close REAL, high_52w REAL, low_52w REAL,
            pct_from_52w_high REAL, pct_from_52w_low REAL,
            computed_date TEXT,
            PRIMARY KEY (symbol, asset_type)
        )
    """)

    # window_regime_stats
    cur.execute("""
        CREATE TABLE IF NOT EXISTS window_regime_stats (
            symbol TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'stock',
            window_days INTEGER NOT NULL, regime TEXT NOT NULL,
            n_windows INTEGER, mean_return REAL, median_return REAL, std_return REAL,
            p5 REAL, p25 REAL, p75 REAL, p95 REAL,
            prob_positive REAL, prob_gt10 REAL, prob_lt_neg10 REAL,
            min_return REAL, max_return REAL, computed_date TEXT,
            PRIMARY KEY (symbol, asset_type, window_days, regime)
        )
    """)

    # symbol_seasonality
    cur.execute("""
        CREATE TABLE IF NOT EXISTS symbol_seasonality (
            symbol TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'stock',
            period_type TEXT NOT NULL, period_value INTEGER NOT NULL,
            n_obs INTEGER, mean_return_pct REAL, median_return_pct REAL,
            std_return_pct REAL, p25 REAL, p75 REAL, prob_positive REAL,
            computed_date TEXT,
            PRIMARY KEY (symbol, asset_type, period_type, period_value)
        )
    """)

    # symbol_correlations
    cur.execute("""
        CREATE TABLE IF NOT EXISTS symbol_correlations (
            symbol TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'stock',
            benchmark TEXT NOT NULL,
            corr_1y REAL, corr_3y REAL, corr_5y REAL, corr_alltime REAL, beta_1y REAL,
            computed_date TEXT,
            PRIMARY KEY (symbol, asset_type, benchmark)
        )
    """)

    # symbol_technicals
    cur.execute("""
        CREATE TABLE IF NOT EXISTS symbol_technicals (
            symbol TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'stock',
            as_of_date TEXT NOT NULL,
            rsi_14 REAL, rsi_21 REAL,
            macd_line REAL, macd_signal REAL, macd_histogram REAL,
            bb_position REAL, bb_width_pct REAL,
            atr_14_pct REAL, adx_14 REAL,
            pct_above_sma20 REAL, pct_above_sma50 REAL, pct_above_sma200 REAL,
            sma20_above_sma50 INTEGER, sma50_above_sma200 INTEGER,
            high_52w REAL, low_52w REAL, pct_from_52w_high REAL, pct_from_52w_low REAL,
            vol_surge_20d REAL, computed_date TEXT,
            PRIMARY KEY (symbol, asset_type)
        )
    """)

    # Indices
    index_sqls = [
        "CREATE INDEX IF NOT EXISTS idx_sss_sym    ON symbol_series_stats  (symbol)",
        "CREATE INDEX IF NOT EXISTS idx_sss_at     ON symbol_series_stats  (asset_type)",
        "CREATE INDEX IF NOT EXISTS idx_wrs_sw     ON window_regime_stats  (symbol, window_days)",
        "CREATE INDEX IF NOT EXISTS idx_wrs_reg    ON window_regime_stats  (regime, window_days)",
        "CREATE INDEX IF NOT EXISTS idx_sseas_sym  ON symbol_seasonality   (symbol)",
        "CREATE INDEX IF NOT EXISTS idx_scorr_sym  ON symbol_correlations  (symbol, benchmark)",
        "CREATE INDEX IF NOT EXISTS idx_stech_sym  ON symbol_technicals    (symbol)",
    ]
    for sql in index_sqls:
        cur.execute(sql)

    conn.commit()
    log("Schema ready", "OK")


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


def load_parquet_full(symbol):
    sym_dir = PARQUET_ROOT / symbol
    if not sym_dir.exists():
        return pd.DataFrame()
    dfs = []
    for pf in sorted(sym_dir.glob("*.parquet")):
        try:
            df = pd.read_parquet(pf)
            df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
            if "close" not in df.columns or "date" not in df.columns:
                continue
            dfs.append(df)
        except Exception:
            continue
    if not dfs:
        return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    df["date"] = df["date"].apply(_parse_date)
    df = df.dropna(subset=["date"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df.get(col, pd.Series(dtype=float)), errors="coerce")
    df = df[df["close"] > 1.0].sort_values("date").drop_duplicates("date").reset_index(drop=True)
    return df[["date", "open", "high", "low", "close", "volume"]]


def load_index_full(conn, index_name):
    try:
        rows = conn.execute(
            "SELECT date, closing_index_value FROM market_snapshot "
            "WHERE index_name=? AND closing_index_value>0 ORDER BY date", (index_name,)
        ).fetchall()
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "close"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"]).reset_index(drop=True)
    df["open"] = df["high"] = df["low"] = df["close"]
    df["volume"] = 0.0
    return df[["date", "open", "high", "low", "close", "volume"]]


def load_global_full(conn, symbol):
    try:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM global_indices_daily "
            "WHERE symbol=? AND close IS NOT NULL ORDER BY date", (symbol,)
        ).fetchall()
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)


def load_regime_map(conn):
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

    closes = np.array(closes_list)
    sma50  = pd.Series(closes).rolling(50, min_periods=50).mean().values
    sma200 = pd.Series(closes).rolling(200, min_periods=200).mean().values
    result = {}
    for i, d in enumerate(dates):
        if np.isnan(sma200[i]):
            result[d] = "sideways"
        elif closes[i] > sma50[i] > sma200[i]:
            result[d] = "bull"
        elif closes[i] < sma50[i] < sma200[i]:
            result[d] = "bear"
        else:
            result[d] = "sideways"
    return result


def load_benchmarks(conn):
    """Returns {display_name: pd.Series(close indexed by date)}"""
    bm = {}
    for sym, name in GLOBAL_BENCHMARKS.items():
        try:
            rows = conn.execute(
                "SELECT date, close FROM global_indices_daily "
                "WHERE symbol=? AND close IS NOT NULL ORDER BY date", (sym,)
            ).fetchall()
            if rows:
                bm[name] = pd.Series({r[0]: float(r[1]) for r in rows})
        except Exception:
            pass
    for idx_name, name in NSE_BENCHMARKS.items():
        try:
            rows = conn.execute(
                "SELECT date, closing_index_value FROM market_snapshot "
                "WHERE index_name=? AND closing_index_value>0 ORDER BY date",
                (idx_name,)
            ).fetchall()
            if rows:
                bm[name] = pd.Series({r[0]: float(r[1]) for r in rows})
        except Exception:
            pass
    return bm


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — WINDOW STATS + EXTREMES
# ═══════════════════════════════════════════════════════════════════════════════

def compute_windows(symbol, asset_type, df):
    closes = df.set_index("date")["close"]
    closes = closes[closes > 0]
    c_arr  = closes.values.astype(np.float64)
    dates  = closes.index.tolist()

    stats_rows = []
    ext_rows   = []

    for w in WINDOWS:
        min_n = max(w * MIN_WIN_FACTOR, MIN_ABSOLUTE) + w
        if len(c_arr) < min_n:
            continue
        buy  = c_arr[:-w]
        sell = c_arr[w:]
        rets = (sell - buy) / buy * 100.0
        rets = rets[np.isfinite(rets)]
        if len(rets) < MIN_ABSOLUTE:
            continue

        n      = len(rets)
        mean_r = float(np.mean(rets))
        std_r  = float(np.std(rets, ddof=1)) if n > 1 else 0.0
        worst  = float(np.min(rets))
        pcts   = np.percentile(rets, [1, 5, 10, 25, 50, 75, 90, 95, 99])

        stats_rows.append({
            "symbol": symbol, "asset_type": asset_type, "window_days": w,
            "first_date": dates[0], "last_date": dates[-1], "n_windows": n,
            "mean_return":   round(mean_r, 4),
            "median_return": round(float(pcts[3]), 4),
            "std_return":    round(std_r, 4),
            "min_return":    round(worst, 4),
            "max_return":    round(float(np.max(rets)), 4),
            "p1":   round(float(pcts[0]), 4), "p5":  round(float(pcts[1]), 4),
            "p10":  round(float(pcts[2]), 4), "p25": round(float(pcts[3]), 4),
            "p75":  round(float(pcts[5]), 4), "p90": round(float(pcts[6]), 4),
            "p95":  round(float(pcts[7]), 4), "p99": round(float(pcts[8]), 4),
            "prob_positive": round(float(np.mean(rets > 0)), 4),
            "prob_gt2":      round(float(np.mean(rets > 2)), 4),
            "prob_gt5":      round(float(np.mean(rets > 5)), 4),
            "prob_gt10":     round(float(np.mean(rets > 10)), 4),
            "prob_gt20":     round(float(np.mean(rets > 20)), 4),
            "prob_gt50":     round(float(np.mean(rets > 50)), 4),
            "prob_lt_neg2":  round(float(np.mean(rets < -2)), 4),
            "prob_lt_neg5":  round(float(np.mean(rets < -5)), 4),
            "prob_lt_neg10": round(float(np.mean(rets < -10)), 4),
            "prob_lt_neg20": round(float(np.mean(rets < -20)), 4),
            "prob_lt_neg50": round(float(np.mean(rets < -50)), 4),
            "ann_return_equiv": round(mean_r * 252.0 / w, 4),
            "sharpe_ratio":  round(mean_r / std_r, 4) if std_r > 0 else None,
            "calmar_ratio":  round(mean_r / abs(worst), 4) if worst < 0 else None,
            "computed_date": TODAY_STR,
        })

        # Extremes — vectorised argsort
        top_up = np.argsort(rets)[-TOP_N:][::-1]
        top_dn = np.argsort(rets)[:TOP_N]
        for rank, i in enumerate(top_up, 1):
            ext_rows.append({
                "symbol": symbol, "asset_type": asset_type, "window_days": w,
                "direction": "up", "rank_n": rank,
                "start_date": dates[i],
                "end_date": dates[min(i + w, len(dates)-1)],
                "return_pct": round(float(rets[i]), 4),
                "computed_date": TODAY_STR,
            })
        for rank, i in enumerate(top_dn, 1):
            ext_rows.append({
                "symbol": symbol, "asset_type": asset_type, "window_days": w,
                "direction": "down", "rank_n": rank,
                "start_date": dates[i],
                "end_date": dates[min(i + w, len(dates)-1)],
                "return_pct": round(float(rets[i]), 4),
                "computed_date": TODAY_STR,
            })

    return stats_rows, ext_rows


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — SERIES STATS (full history metrics)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_series_stats(symbol, asset_type, df):
    if df.empty or len(df) < MIN_ABSOLUTE:
        return None
    c    = df["close"].values.astype(np.float64)
    dates = df["date"].tolist()
    dr   = np.diff(c) / c[:-1]
    dr   = dr[np.isfinite(dr)]
    if len(dr) < 20:
        return None

    n_years  = len(c) / 252.0
    tot_ret  = (c[-1] / c[0] - 1) * 100 if c[0] > 0 else None
    cagr     = ((c[-1] / c[0]) ** (1 / n_years) - 1) * 100 if c[0] > 0 and n_years > 0 else None
    ann_vol  = float(np.std(dr, ddof=1) * np.sqrt(252) * 100)

    # Max drawdown
    peak = c[0]; mdd = 0.0; mdd_pi = mdd_ti = cur_pi = 0
    for i, v in enumerate(c):
        if v > peak:
            peak = v; cur_pi = i
        dd = (v - peak) / peak * 100
        if dd < mdd:
            mdd = dd; mdd_pi = cur_pi; mdd_ti = i
    mdd_ri = None
    for i in range(mdd_ti + 1, len(c)):
        if c[i] >= c[mdd_pi]:
            mdd_ri = i; break

    def ddays(d1, d2):
        try:
            return (datetime.strptime(d2, "%Y-%m-%d") - datetime.strptime(d1, "%Y-%m-%d")).days
        except Exception:
            return None

    mdd_dur  = ddays(dates[mdd_pi], dates[mdd_ti])
    mdd_rdays = ddays(dates[mdd_ti], dates[mdd_ri]) if mdd_ri else None

    mean_d = float(np.mean(dr)); std_d = float(np.std(dr, ddof=1))
    sharpe = (mean_d / std_d * np.sqrt(252)) if std_d > 0 else None
    calmar = (cagr / abs(mdd)) if cagr and mdd < 0 else None
    dn     = dr[dr < 0]
    dn_std = float(np.std(dn, ddof=1)) if len(dn) > 1 else None
    sortino = (mean_d / dn_std * np.sqrt(252)) if dn_std and dn_std > 0 else None

    try:
        from scipy.stats import skew as _sk, kurtosis as _ku
        skew = float(_sk(dr)); kurt = float(_ku(dr))
    except Exception:
        skew = kurt = None

    last252 = c[-252:] if len(c) >= 252 else c
    h52 = float(np.max(last252)); l52 = float(np.min(last252)); lc = float(c[-1])

    def r4(x):
        return round(float(x), 4) if x is not None and np.isfinite(float(x) if x is not None else float("nan")) else None

    return {
        "symbol": symbol, "asset_type": asset_type,
        "first_date": dates[0], "last_date": dates[-1], "n_trading_days": len(c),
        "cagr_pct": r4(cagr), "total_return_pct": r4(tot_ret),
        "ann_volatility_pct": r4(ann_vol),
        "max_drawdown_pct": r4(mdd),
        "mdd_start_date": dates[mdd_pi], "mdd_trough_date": dates[mdd_ti],
        "mdd_recovery_date": dates[mdd_ri] if mdd_ri else None,
        "mdd_duration_days": mdd_dur, "mdd_recovery_days": mdd_rdays,
        "sharpe_ratio": r4(sharpe), "calmar_ratio": r4(calmar), "sortino_ratio": r4(sortino),
        "skewness": r4(skew), "kurtosis": r4(kurt),
        "pct_positive_days": r4(float(np.mean(dr > 0) * 100)),
        "last_close": r4(lc), "high_52w": r4(h52), "low_52w": r4(l52),
        "pct_from_52w_high": r4((lc - h52) / h52 * 100) if h52 > 0 else None,
        "pct_from_52w_low":  r4((lc - l52) / l52 * 100) if l52 > 0 else None,
        "computed_date": TODAY_STR,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — REGIME-SLICED WINDOW STATS
# ═══════════════════════════════════════════════════════════════════════════════

def compute_regime_stats(symbol, asset_type, df, regime_map):
    if not regime_map or df.empty:
        return []
    closes = df.set_index("date")["close"]
    c_arr  = closes.values.astype(np.float64)
    dates  = closes.index.tolist()
    rows   = []

    for w in REGIME_WINDOWS:
        if len(c_arr) < w + MIN_ABSOLUTE:
            continue
        buy  = c_arr[:-w]; sell = c_arr[w:]
        rets = (sell - buy) / buy * 100.0
        finite = np.isfinite(rets)

        groups = defaultdict(list)
        for i, (r, ok) in enumerate(zip(rets, finite)):
            if not ok: continue
            reg = regime_map.get(dates[i], "sideways") if i < len(dates) else "sideways"
            groups[reg].append(r)
            groups["all"].append(r)

        for reg, rv_list in groups.items():
            rv = np.array(rv_list)
            if len(rv) < 5: continue
            rows.append({
                "symbol": symbol, "asset_type": asset_type,
                "window_days": w, "regime": reg,
                "n_windows":     len(rv),
                "mean_return":   round(float(np.mean(rv)), 4),
                "median_return": round(float(np.median(rv)), 4),
                "std_return":    round(float(np.std(rv, ddof=1)), 4) if len(rv) > 1 else 0.0,
                "p5":            round(float(np.percentile(rv, 5)), 4),
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


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — SEASONALITY
# ═══════════════════════════════════════════════════════════════════════════════

def compute_seasonality(symbol, asset_type, df):
    if df.empty or len(df) < 60:
        return []
    rows = []
    df2  = df.copy()
    df2["dt"]      = pd.to_datetime(df2["date"])
    df2["year"]    = df2["dt"].dt.year
    df2["month"]   = df2["dt"].dt.month
    df2["quarter"] = df2["dt"].dt.quarter
    df2["weekday"] = df2["dt"].dt.weekday

    def add_rows(period_type, groups_dict, min_obs=3):
        for pv, rv_list in groups_dict.items():
            rv = np.array([v for v in rv_list if np.isfinite(v)])
            if len(rv) < min_obs: continue
            rows.append({
                "symbol": symbol, "asset_type": asset_type,
                "period_type": period_type, "period_value": int(pv),
                "n_obs": len(rv),
                "mean_return_pct":   round(float(np.mean(rv)), 4),
                "median_return_pct": round(float(np.median(rv)), 4),
                "std_return_pct":    round(float(np.std(rv, ddof=1)), 4) if len(rv) > 1 else 0.0,
                "p25":               round(float(np.percentile(rv, 25)), 4),
                "p75":               round(float(np.percentile(rv, 75)), 4),
                "prob_positive":     round(float(np.mean(rv > 0)), 4),
                "computed_date":     TODAY_STR,
            })

    # Monthly
    mo_rets = defaultdict(list)
    for (yr, mo), grp in df2.groupby(["year", "month"]):
        grp = grp.sort_values("date")
        if len(grp) < 2: continue
        r = (grp["close"].iloc[-1] / grp["close"].iloc[0] - 1) * 100
        mo_rets[mo].append(r)
    add_rows("month", mo_rets)

    # Quarterly
    qt_rets = defaultdict(list)
    for (yr, qt), grp in df2.groupby(["year", "quarter"]):
        grp = grp.sort_values("date")
        if len(grp) < 5: continue
        r = (grp["close"].iloc[-1] / grp["close"].iloc[0] - 1) * 100
        qt_rets[qt].append(r)
    add_rows("quarter", qt_rets)

    # Weekday (daily return)
    df2["daily_ret"] = df2["close"].pct_change() * 100
    wd_rets = defaultdict(list)
    for _, row2 in df2.iterrows():
        r = row2["daily_ret"]
        if np.isfinite(r):
            wd_rets[int(row2["weekday"])].append(r)
    add_rows("weekday", wd_rets, min_obs=20)

    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 5 — CORRELATIONS + BETA
# ═══════════════════════════════════════════════════════════════════════════════

def compute_correlations(symbol, asset_type, df, benchmarks):
    if df.empty or len(df) < 30 or not benchmarks:
        return []
    rows  = []
    sym_s = df.set_index("date")["close"].pct_change().dropna()

    for bname, bseries in benchmarks.items():
        try:
            b_r   = bseries.pct_change().dropna()
            common = sym_s.index.intersection(b_r.index)
            if len(common) < 30: continue
            sr = sym_s.loc[common].values.astype(np.float64)
            br = b_r.loc[common].values.astype(np.float64)

            def rc(n):
                if len(sr) < n: return None
                sw = sr[-n:]; bw = br[-n:]
                if np.std(sw) == 0 or np.std(bw) == 0: return None
                v = np.corrcoef(sw, bw)[0, 1]
                return round(float(v), 4) if np.isfinite(v) else None

            def beta():
                n = min(252, len(sr))
                sw = sr[-n:]; bw = br[-n:]
                vb = np.var(bw)
                if vb == 0: return None
                v = np.cov(sw, bw)[0, 1] / vb
                return round(float(v), 4) if np.isfinite(v) else None

            ca = float(np.corrcoef(sr, br)[0, 1]) if len(sr) > 2 else None
            rows.append({
                "symbol": symbol, "asset_type": asset_type, "benchmark": bname,
                "corr_1y": rc(252), "corr_3y": rc(756), "corr_5y": rc(1260),
                "corr_alltime": round(ca, 4) if ca and np.isfinite(ca) else None,
                "beta_1y": beta() if asset_type == "stock" else None,
                "computed_date": TODAY_STR,
            })
        except Exception:
            continue
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 6 — TECHNICAL INDICATORS
# ═══════════════════════════════════════════════════════════════════════════════

def _ema(arr, p):
    k = 2.0 / (p + 1); out = np.full(len(arr), np.nan)
    if len(arr) < p: return out
    out[p-1] = np.mean(arr[:p])
    for i in range(p, len(arr)):
        out[i] = arr[i] * k + out[i-1] * (1 - k)
    return out

def _rsi(c, p=14):
    if len(c) < p + 1: return None
    d = np.diff(c[-(p*4):]); g = np.where(d>0, d, 0.); l = np.where(d<0, -d, 0.)
    ag = np.mean(g[-p:]); al = np.mean(l[-p:])
    if al == 0: return 100.
    return float(100 - 100 / (1 + ag/al))

def _atr(h, l, c, p=14):
    if len(c) < p+1: return None
    h2=h[-(p+1):]; l2=l[-(p+1):]; c2=c[-(p+1):]
    tr = np.maximum(h2[1:]-l2[1:], np.maximum(abs(h2[1:]-c2[:-1]), abs(l2[1:]-c2[:-1])))
    return float(np.mean(tr))

def _adx(h, l, c, p=14):
    n = p*3
    if len(c) < n+1: return None
    h2=h[-(n+1):].astype(float); l2=l[-(n+1):].astype(float); c2=c[-(n+1):].astype(float)
    trs=[]; pds=[]; nds=[]
    for i in range(1, len(h2)):
        trs.append(max(h2[i]-l2[i], abs(h2[i]-c2[i-1]), abs(l2[i]-c2[i-1])))
        pds.append(max(h2[i]-h2[i-1], 0) if (h2[i]-h2[i-1]) > (l2[i-1]-l2[i]) else 0)
        nds.append(max(l2[i-1]-l2[i], 0) if (l2[i-1]-l2[i]) > (h2[i]-h2[i-1]) else 0)
    atr = np.mean(trs[-p:])
    if atr == 0: return None
    pdi = 100*np.mean(pds[-p:])/atr; ndi = 100*np.mean(nds[-p:])/atr
    return float(100*abs(pdi-ndi)/(pdi+ndi)) if (pdi+ndi) > 0 else 0.

def compute_technicals(symbol, asset_type, df):
    if df.empty or len(df) < 21: return None
    df2 = df.tail(756).reset_index(drop=True)
    c  = df2["close"].values.astype(np.float64)
    h  = df2["high"].values.astype(np.float64)  if "high"   in df2.columns else c.copy()
    l  = df2["low"].values.astype(np.float64)   if "low"    in df2.columns else c.copy()
    v  = df2["volume"].values.astype(np.float64) if "volume" in df2.columns else np.zeros(len(c))
    lc = float(c[-1]); as_of = df2["date"].iloc[-1]

    r14 = _rsi(c, 14); r21 = _rsi(c, 21)

    e12 = _ema(c, 12); e26 = _ema(c, 26)
    if not np.isnan(e12[-1]) and not np.isnan(e26[-1]):
        ml_arr = e12 - e26; ms_arr = _ema(ml_arr, 9)
        ml = float(ml_arr[-1]) if np.isfinite(ml_arr[-1]) else None
        ms = float(ms_arr[-1]) if np.isfinite(ms_arr[-1]) else None
        mh = (ml - ms) if ml and ms else None
    else:
        ml = ms = mh = None

    bb_pos = bb_w = None
    if len(c) >= 20:
        s20 = float(np.mean(c[-20:])); std20 = float(np.std(c[-20:], ddof=1))
        bup = s20 + 2*std20; blo = s20 - 2*std20
        rng = bup - blo
        bb_pos = (lc - blo)/rng if rng > 0 else 0.5
        bb_w   = (rng/s20*100) if s20 > 0 else None

    atr14  = _atr(h, l, c, 14)
    atr_p  = (atr14/lc*100) if atr14 and lc > 0 else None
    adx14  = _adx(h, l, c, 14)

    def sma(n): return float(np.mean(c[-n:])) if len(c) >= n else None
    s20v=sma(20); s50v=sma(50); s200v=sma(200)

    last252 = c[-252:] if len(c) >= 252 else c
    h52 = float(np.max(last252)); l52 = float(np.min(last252))

    vol_surge = None
    if len(v) >= 252:
        a252 = float(np.mean(v[-252:])); a20 = float(np.mean(v[-20:]))
        vol_surge = (a20/a252) if a252 > 0 else None

    def r4(x):
        if x is None: return None
        try:
            f = float(x)
            return round(f, 4) if np.isfinite(f) else None
        except Exception:
            return None

    return {
        "symbol": symbol, "asset_type": asset_type, "as_of_date": as_of,
        "rsi_14": r4(r14), "rsi_21": r4(r21),
        "macd_line": r4(ml), "macd_signal": r4(ms), "macd_histogram": r4(mh),
        "bb_position": r4(bb_pos), "bb_width_pct": r4(bb_w),
        "atr_14_pct": r4(atr_p), "adx_14": r4(adx14),
        "pct_above_sma20":  r4((lc-s20v)/s20v*100)  if s20v  else None,
        "pct_above_sma50":  r4((lc-s50v)/s50v*100)  if s50v  else None,
        "pct_above_sma200": r4((lc-s200v)/s200v*100) if s200v else None,
        "sma20_above_sma50":   int(s20v > s50v)   if s20v and s50v   else None,
        "sma50_above_sma200":  int(s50v > s200v)  if s50v and s200v  else None,
        "high_52w": r4(h52), "low_52w": r4(l52),
        "pct_from_52w_high": r4((lc-h52)/h52*100) if h52 > 0 else None,
        "pct_from_52w_low":  r4((lc-l52)/l52*100) if l52 > 0 else None,
        "vol_surge_20d": r4(vol_surge),
        "computed_date": TODAY_STR,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DB WRITERS (bulk upserts)
# ═══════════════════════════════════════════════════════════════════════════════

def write_all(conn, symbol, asset_type, df, regime_map, benchmarks, layers):
    if df.empty or len(df) < MIN_ABSOLUTE:
        return False
    try:
        if "window" in layers:
            ws, we = compute_windows(symbol, asset_type, df)
            if ws:
                conn.executemany("""
                    INSERT OR REPLACE INTO window_stats
                    (symbol,asset_type,window_days,first_date,last_date,n_windows,
                     mean_return,median_return,std_return,min_return,max_return,
                     p1,p5,p10,p25,p75,p90,p95,p99,
                     prob_positive,prob_gt2,prob_gt5,prob_gt10,prob_gt20,prob_gt50,
                     prob_lt_neg2,prob_lt_neg5,prob_lt_neg10,prob_lt_neg20,prob_lt_neg50,
                     ann_return_equiv,sharpe_ratio,calmar_ratio,computed_date)
                    VALUES
                    (:symbol,:asset_type,:window_days,:first_date,:last_date,:n_windows,
                     :mean_return,:median_return,:std_return,:min_return,:max_return,
                     :p1,:p5,:p10,:p25,:p75,:p90,:p95,:p99,
                     :prob_positive,:prob_gt2,:prob_gt5,:prob_gt10,:prob_gt20,:prob_gt50,
                     :prob_lt_neg2,:prob_lt_neg5,:prob_lt_neg10,:prob_lt_neg20,:prob_lt_neg50,
                     :ann_return_equiv,:sharpe_ratio,:calmar_ratio,:computed_date)
                """, ws)
            if we:
                conn.executemany("""
                    INSERT OR REPLACE INTO window_extremes
                    (symbol,asset_type,window_days,direction,rank_n,
                     start_date,end_date,return_pct,computed_date)
                    VALUES (:symbol,:asset_type,:window_days,:direction,:rank_n,
                            :start_date,:end_date,:return_pct,:computed_date)
                """, we)

        if "series" in layers:
            ss = compute_series_stats(symbol, asset_type, df)
            if ss:
                conn.execute("""
                    INSERT OR REPLACE INTO symbol_series_stats
                    (symbol,asset_type,first_date,last_date,n_trading_days,
                     cagr_pct,total_return_pct,ann_volatility_pct,
                     max_drawdown_pct,mdd_start_date,mdd_trough_date,
                     mdd_recovery_date,mdd_duration_days,mdd_recovery_days,
                     sharpe_ratio,calmar_ratio,sortino_ratio,
                     skewness,kurtosis,pct_positive_days,
                     last_close,high_52w,low_52w,pct_from_52w_high,pct_from_52w_low,
                     computed_date)
                    VALUES
                    (:symbol,:asset_type,:first_date,:last_date,:n_trading_days,
                     :cagr_pct,:total_return_pct,:ann_volatility_pct,
                     :max_drawdown_pct,:mdd_start_date,:mdd_trough_date,
                     :mdd_recovery_date,:mdd_duration_days,:mdd_recovery_days,
                     :sharpe_ratio,:calmar_ratio,:sortino_ratio,
                     :skewness,:kurtosis,:pct_positive_days,
                     :last_close,:high_52w,:low_52w,:pct_from_52w_high,:pct_from_52w_low,
                     :computed_date)
                """, ss)

        if "regime" in layers:
            rs = compute_regime_stats(symbol, asset_type, df, regime_map)
            if rs:
                conn.executemany("""
                    INSERT OR REPLACE INTO window_regime_stats
                    (symbol,asset_type,window_days,regime,n_windows,
                     mean_return,median_return,std_return,p5,p25,p75,p95,
                     prob_positive,prob_gt10,prob_lt_neg10,min_return,max_return,computed_date)
                    VALUES (:symbol,:asset_type,:window_days,:regime,:n_windows,
                            :mean_return,:median_return,:std_return,:p5,:p25,:p75,:p95,
                            :prob_positive,:prob_gt10,:prob_lt_neg10,:min_return,:max_return,
                            :computed_date)
                """, rs)

        if "seasonality" in layers:
            seas = compute_seasonality(symbol, asset_type, df)
            if seas:
                conn.executemany("""
                    INSERT OR REPLACE INTO symbol_seasonality
                    (symbol,asset_type,period_type,period_value,n_obs,
                     mean_return_pct,median_return_pct,std_return_pct,p25,p75,
                     prob_positive,computed_date)
                    VALUES (:symbol,:asset_type,:period_type,:period_value,:n_obs,
                            :mean_return_pct,:median_return_pct,:std_return_pct,
                            :p25,:p75,:prob_positive,:computed_date)
                """, seas)

        if "correlations" in layers:
            corrs = compute_correlations(symbol, asset_type, df, benchmarks)
            if corrs:
                conn.executemany("""
                    INSERT OR REPLACE INTO symbol_correlations
                    (symbol,asset_type,benchmark,corr_1y,corr_3y,corr_5y,
                     corr_alltime,beta_1y,computed_date)
                    VALUES (:symbol,:asset_type,:benchmark,:corr_1y,:corr_3y,:corr_5y,
                            :corr_alltime,:beta_1y,:computed_date)
                """, corrs)

        if "technicals" in layers:
            tech = compute_technicals(symbol, asset_type, df)
            if tech:
                conn.execute("""
                    INSERT OR REPLACE INTO symbol_technicals
                    (symbol,asset_type,as_of_date,
                     rsi_14,rsi_21,macd_line,macd_signal,macd_histogram,
                     bb_position,bb_width_pct,atr_14_pct,adx_14,
                     pct_above_sma20,pct_above_sma50,pct_above_sma200,
                     sma20_above_sma50,sma50_above_sma200,
                     high_52w,low_52w,pct_from_52w_high,pct_from_52w_low,
                     vol_surge_20d,computed_date)
                    VALUES
                    (:symbol,:asset_type,:as_of_date,
                     :rsi_14,:rsi_21,:macd_line,:macd_signal,:macd_histogram,
                     :bb_position,:bb_width_pct,:atr_14_pct,:adx_14,
                     :pct_above_sma20,:pct_above_sma50,:pct_above_sma200,
                     :sma20_above_sma50,:sma50_above_sma200,
                     :high_52w,:low_52w,:pct_from_52w_high,:pct_from_52w_low,
                     :vol_surge_20d,:computed_date)
                """, tech)

        conn.commit()
        return True
    except Exception as e:
        try: conn.rollback()
        except Exception: pass
        return False


def already_done(conn, symbol, asset_type, layers):
    checks = {
        "window":       ("window_stats",       "window_days=252"),
        "series":       ("symbol_series_stats", "1=1"),
        "regime":       ("window_regime_stats", "window_days=252"),
        "seasonality":  ("symbol_seasonality",  "period_type='month'"),
        "correlations": ("symbol_correlations", "1=1"),
        "technicals":   ("symbol_technicals",   "1=1"),
    }
    for layer in layers:
        if layer not in checks: continue
        t, cond = checks[layer]
        try:
            row = conn.execute(
                f"SELECT 1 FROM {t} WHERE symbol=? AND asset_type=? AND {cond} LIMIT 1",
                (symbol, asset_type)
            ).fetchone()
            # Don't block --resume if regime table is empty (first run without regime)
            if layer == "regime":
                total = conn.execute(
                    "SELECT COUNT(*) FROM window_regime_stats"
                ).fetchone()[0]
                if total == 0:
                    continue
            if not row: return False
        except Exception:
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# BATCH RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

def run_batch(conn, symbols, asset_type, loader_fn, regime_map, benchmarks, layers, resume):
    t0 = time.time()
    done = skip = fail = 0
    for i, sym in enumerate(symbols, 1):
        if resume and already_done(conn, sym, asset_type, layers):
            skip += 1
            continue
        df = loader_fn(sym)
        ok = write_all(conn, sym, asset_type, df, regime_map, benchmarks, layers)
        if ok: done += 1
        else:  fail += 1
        if i % 100 == 0:
            el  = time.time() - t0
            eta = (el / i) * (len(symbols) - i) / 60
            log(f"[{i:4d}/{len(symbols)}] {i/len(symbols)*100:.0f}%  "
                f"done={done} skip={skip} fail={fail}  ETA={eta:.1f}m")
    log(f"DONE: {done} ok | {skip} skip | {fail} fail | "
        f"{(time.time()-t0)/60:.1f} min", "OK")


def print_summary(conn):
    print()
    print("=" * 65)
    print("  DATABASE SUMMARY — Phase 9B v2")
    print("=" * 65)
    for table, label in [
        ("window_stats",        "Window stats   "),
        ("window_extremes",     "Window extremes"),
        ("symbol_series_stats", "Series stats   "),
        ("window_regime_stats", "Regime stats   "),
        ("symbol_seasonality",  "Seasonality    "),
        ("symbol_correlations", "Correlations   "),
        ("symbol_technicals",   "Technicals     "),
    ]:
        try:
            rows = conn.execute(
                f"SELECT asset_type, COUNT(DISTINCT symbol), COUNT(*) "
                f"FROM {table} GROUP BY asset_type ORDER BY asset_type"
            ).fetchall()
            for at, nsym, nrow in rows:
                print(f"  {label}  {at:<10}  {nsym:>5} symbols  {nrow:>9} rows")
        except Exception:
            pass
    print()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    stocks_only  = "--stocks-only"  in sys.argv
    indices_only = "--indices-only" in sys.argv
    resume       = "--resume"       in sys.argv

    single_sym = None
    if "--sym" in sys.argv:
        idx = sys.argv.index("--sym")
        if idx + 1 < len(sys.argv):
            single_sym = sys.argv[idx + 1].upper()

    all_layers = {"window", "series", "regime", "seasonality", "correlations", "technicals"}
    layers = all_layers.copy()
    if "--layer" in sys.argv:
        idx = sys.argv.index("--layer")
        if idx + 1 < len(sys.argv):
            picked = sys.argv[idx + 1].lower()
            if picked in all_layers:
                layers = {picked}

    print()
    print("=" * 65)
    print("  MICC Phase 9B v2 — Advanced Window Stats Warehouse")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Windows (17): {WINDOWS}")
    print(f"  Top-N per window: {TOP_N} best + {TOP_N} worst")
    print(f"  Layers active: {sorted(layers)}")
    if resume:
        print("  Mode: RESUME (skip already-computed symbols)")
    print("=" * 65)
    print()

    if not DB_PATH.exists():
        log(f"DB not found: {DB_PATH}", "FAIL"); sys.exit(1)

    try:
        from scipy.stats import skew as _s, kurtosis as _k
    except ImportError:
        log("scipy missing — install: pip install scipy --break-system-packages", "FAIL")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-262144")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=4294967296")

    try:
        log("Ensuring schema...")
        ensure_tables(conn)

        log("Loading Nifty 50 regime map...")
        regime_map = load_regime_map(conn)
        log(f"  {len(regime_map)} dates labelled (bull/bear/sideways)")

        log("Loading benchmark series...")
        benchmarks = load_benchmarks(conn)
        log(f"  {len(benchmarks)} benchmarks: {list(benchmarks.keys())}")

        if single_sym:
            df = load_parquet_full(single_sym); at = "stock"
            if df.empty: df = load_index_full(conn, single_sym); at = "index"
            if df.empty: df = load_global_full(conn, single_sym); at = "global"
            if df.empty:
                log(f"No data for {single_sym}", "FAIL")
            else:
                log(f"{single_sym}: {len(df)} rows  ({df['date'].iloc[0]} .. {df['date'].iloc[-1]})")
                ok = write_all(conn, single_sym, at, df, regime_map, benchmarks, layers)
                log(f"{single_sym}: {'OK' if ok else 'FAILED'}", "OK" if ok else "FAIL")

        elif indices_only:
            log("=== NSE Indices ===")
            nse_idx = [r[0] for r in conn.execute(
                "SELECT DISTINCT index_name FROM market_snapshot ORDER BY index_name").fetchall()]
            run_batch(conn, nse_idx, "index",
                      lambda s: load_index_full(conn, s),
                      regime_map, benchmarks, layers, resume)

            log("=== Global Indices ===")
            glob = [r[0] for r in conn.execute(
                "SELECT DISTINCT symbol FROM global_indices_daily ORDER BY symbol").fetchall()]
            run_batch(conn, glob, "global",
                      lambda s: load_global_full(conn, s),
                      regime_map, benchmarks, layers, resume)

        elif stocks_only:
            log("=== NSE Stocks ===")
            syms = sorted([d.name for d in PARQUET_ROOT.iterdir()
                           if d.is_dir() and not is_etf(d.name)])
            log(f"  {len(syms)} stocks")
            run_batch(conn, syms, "stock",
                      lambda s: load_parquet_full(s),
                      regime_map, benchmarks, layers, resume)

        else:
            log("=== STEP 1/3: NSE Indices ===")
            nse_idx = [r[0] for r in conn.execute(
                "SELECT DISTINCT index_name FROM market_snapshot ORDER BY index_name").fetchall()]
            run_batch(conn, nse_idx, "index",
                      lambda s: load_index_full(conn, s),
                      regime_map, benchmarks, layers, resume)

            log("=== STEP 2/3: Global Indices ===")
            glob = [r[0] for r in conn.execute(
                "SELECT DISTINCT symbol FROM global_indices_daily ORDER BY symbol").fetchall()]
            run_batch(conn, glob, "global",
                      lambda s: load_global_full(conn, s),
                      regime_map, benchmarks, layers, resume)

            log("=== STEP 3/3: NSE Stocks (long run ~3-5h) ===")
            syms = sorted([d.name for d in PARQUET_ROOT.iterdir()
                           if d.is_dir() and not is_etf(d.name)])
            log(f"  {len(syms)} stocks × 6 layers")
            run_batch(conn, syms, "stock",
                      lambda s: load_parquet_full(s),
                      regime_map, benchmarks, layers, resume)

        print_summary(conn)
        log("Phase 9B v2 COMPLETE", "OK")

    except KeyboardInterrupt:
        log("Interrupted — partial results saved", "WARN")
        print_summary(conn)
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
