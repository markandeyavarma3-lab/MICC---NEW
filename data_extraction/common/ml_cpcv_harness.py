#!/usr/bin/env python3
"""ml_cpcv_harness.py — Part 3 Module E: probationary ML challenger harness
(Combinatorial Purged Cross-Validation + deflated Sharpe + importance stability).

Champion: the frozen linear composite (mean pct-rank of the proven signals) —
it already beat LightGBM OOS (1.25 vs 0.76). Challengers: ridge linear and
LightGBM, trained per CPCV path.

CPCV(6 groups, 2 test) -> 15 chronology-respecting paths. Labels are 1-month
forward returns, so train months within EMBARGO_M months of any test month are
purged/embargoed. Per path and model: rank the test cross-sections, take the
top decile equal-weight, monthly mean fwd return -> annualised Sharpe.

Pre-registered promotion criteria (ALL must hold; stored with the experiment):
  1. median challenger path Sharpe > median champion path Sharpe (same paths)
  2. Deflated Sharpe Ratio of the pooled challenger OOS series > 0
     (corrected for n_paths trials, skew, kurtosis)
  3. LightGBM feature-importance rank stability across paths: Kendall's W >= 0.7
If any fails, the challenger stays a shadow experiment. It would only ever
RE-RANK within the linear top-N — never override gates or caps.

Run:  py -3.14 common/ml_cpcv_harness.py
"""
import itertools
import json
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd

from backtest_momentum import DB_PATH

N_GROUPS, N_TEST = 6, 2
EMBARGO_M = 1
FEATURES = ["mom_12_1", "mom_6_1", "ret_1m", "ret_3m", "ret_6m", "vol_3m", "vol_6m",
            "dist_sma50", "dist_sma200", "prox_52w_high", "amihud",
            "deliv_1m", "deliv_3m", "deliv_trend"]
CHAMPION_SIGNALS = ["mom_12_1", "prox_52w_high", "deliv_1m"]   # generate_signals composite

DDL = ["""CREATE TABLE IF NOT EXISTS ml_experiment (
    exp_id INTEGER PRIMARY KEY, created_at TEXT, model_family TEXT,
    feature_set_ref TEXT, label_def TEXT, cpcv_config_json TEXT,
    pre_registered_criteria_json TEXT, status TEXT)""",
       """CREATE TABLE IF NOT EXISTS ml_result (
    result_id INTEGER PRIMARY KEY, exp_id INTEGER, path_id INTEGER,
    model TEXT, sharpe REAL, mean_ret REAL,
    deflated_sharpe REAL, kendall_w REAL, shap_top_json TEXT, created_at TEXT)"""]


def sharpe(m):
    m = pd.Series(m).dropna()
    return float(m.mean() / m.std() * np.sqrt(12)) if len(m) > 3 and m.std() > 0 else np.nan


def deflated_sharpe(series, n_trials):
    """Bailey & Lopez de Prado DSR of a monthly series given n_trials."""
    r = pd.Series(series).dropna()
    T = len(r)
    if T < 12 or r.std() == 0:
        return np.nan
    sr = r.mean() / r.std()                          # per-period SR
    g1 = float(r.skew())
    g2 = float(r.kurtosis()) + 3
    emc = 0.5772156649
    from scipy.stats import norm                     # scipy ships with pandas stacks
    var_sr = 1.0 / T
    sr0 = np.sqrt(var_sr) * ((1 - emc) * norm.ppf(1 - 1 / n_trials)
                             + emc * norm.ppf(1 - 1 / (n_trials * np.e)))
    denom = np.sqrt(max(1 - g1 * sr + (g2 - 1) / 4 * sr ** 2, 1e-9))
    return float(norm.cdf(((sr - sr0) * np.sqrt(T - 1)) / denom))


def kendalls_w(rank_matrix):
    """rank_matrix: paths x features ranks. W = 12S / m^2 (k^3 - k)."""
    m, k = rank_matrix.shape
    rank_sums = rank_matrix.sum(axis=0)
    S = ((rank_sums - rank_sums.mean()) ** 2).sum()
    return float(12 * S / (m ** 2 * (k ** 3 - k)))


def top_decile_series(df_test, score_col):
    out = {}
    for m, g in df_test.groupby("rebal_date"):
        g = g.dropna(subset=[score_col, "fwd_ret_1m"])
        if len(g) < 50:
            continue
        top = g[g[score_col] >= g[score_col].quantile(0.9)]
        out[m] = top["fwd_ret_1m"].mean()
    return pd.Series(out).sort_index()


def main():
    import lightgbm as lgb
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    for d in DDL:
        conn.execute(d)

    df = pd.read_sql("SELECT rebal_date, symbol, fwd_ret_1m, " + ",".join(FEATURES) +
                     " FROM features_monthly WHERE top500=1 AND liquid=1 "
                     "AND fwd_ret_1m IS NOT NULL", conn)
    months = sorted(df["rebal_date"].unique())
    groups = np.array_split(np.array(months), N_GROUPS)
    print(f"  panel: {len(df):,} rows, {len(months)} months, "
          f"{N_GROUPS} groups -> {len(list(itertools.combinations(range(N_GROUPS), N_TEST)))} paths",
          flush=True)

    # champion composite (no training): mean pct-rank of the proven signals
    for s in CHAMPION_SIGNALS:
        df[s + "_r"] = df.groupby("rebal_date")[s].rank(pct=True)
    df["champion"] = df[[s + "_r" for s in CHAMPION_SIGNALS]].mean(axis=1)

    month_idx = {m: i for i, m in enumerate(months)}
    results = {"champion": [], "ridge": [], "lgbm": []}
    pooled = {"ridge": {}, "lgbm": {}, "champion": {}}
    lgb_ranks = []

    for pid, test_gids in enumerate(itertools.combinations(range(N_GROUPS), N_TEST)):
        test_months = set()
        for gi in test_gids:
            test_months |= set(groups[gi])
        # purge + embargo: drop train months within EMBARGO_M of any test month
        tmi = sorted(month_idx[m] for m in test_months)
        banned = set()
        for i in tmi:
            for j in range(i - EMBARGO_M, i + EMBARGO_M + 1):
                banned.add(j)
        train_months = [m for m in months
                        if month_idx[m] not in banned and m not in test_months]
        tr = df[df["rebal_date"].isin(train_months)].dropna(subset=FEATURES)
        te = df[df["rebal_date"].isin(test_months)].copy()

        # standardise features per training set
        mu, sd = tr[FEATURES].mean(), tr[FEATURES].std().replace(0, 1)
        Xtr = ((tr[FEATURES] - mu) / sd).to_numpy()
        ytr = tr["fwd_ret_1m"].to_numpy()
        Xte_full = ((te[FEATURES] - mu) / sd)

        # ridge (lambda = 10)
        lam = 10.0
        A = Xtr.T @ Xtr + lam * np.eye(len(FEATURES))
        beta = np.linalg.solve(A, Xtr.T @ ytr)
        te["ridge"] = np.where(Xte_full.notna().all(axis=1),
                               Xte_full.fillna(0).to_numpy() @ beta, np.nan)

        # lightgbm
        model = lgb.LGBMRegressor(n_estimators=200, learning_rate=0.05, num_leaves=31,
                                  min_child_samples=50, subsample=0.8,
                                  colsample_bytree=0.8, verbose=-1)
        model.fit(tr[FEATURES], ytr)
        te["lgbm"] = model.predict(te[FEATURES])
        lgb_ranks.append(pd.Series(model.feature_importances_, index=FEATURES)
                         .rank(ascending=False).to_numpy())

        for name in ("champion", "ridge", "lgbm"):
            s = top_decile_series(te, name)
            results[name].append(sharpe(s))
            for m, v in s.items():
                pooled[name].setdefault(m, []).append(v)

    med = {k: float(np.nanmedian(v)) for k, v in results.items()}
    pooled_series = {k: pd.Series({m: np.mean(vs) for m, vs in d.items()}).sort_index()
                     for k, d in pooled.items()}
    n_paths = len(results["champion"])
    dsr = {k: deflated_sharpe(pooled_series[k], n_trials=n_paths * 2)
           for k in ("ridge", "lgbm")}
    W = kendalls_w(np.vstack(lgb_ranks))

    print(f"\n  median path Sharpe: champion {med['champion']:.2f} | "
          f"ridge {med['ridge']:.2f} | lgbm {med['lgbm']:.2f}", flush=True)
    print(f"  pooled DSR: ridge {dsr['ridge']:.3f} | lgbm {dsr['lgbm']:.3f}", flush=True)
    print(f"  LightGBM importance stability Kendall's W = {W:.3f}", flush=True)

    verdicts = {}
    for m_ in ("ridge", "lgbm"):
        passed = (med[m_] > med["champion"]) and (dsr[m_] > 0.5) and (W >= 0.7 or m_ == "ridge")
        verdicts[m_] = "passed" if passed else "killed"
    print(f"  PRE-REGISTERED VERDICTS: ridge={verdicts['ridge'].upper()} "
          f"lgbm={verdicts['lgbm'].upper()}  "
          f"(promotion needs median>champion AND DSR>0.5 AND W>=0.7)", flush=True)

    now = datetime.now().isoformat()
    conn.execute("DELETE FROM ml_experiment"); conn.execute("DELETE FROM ml_result")
    for m_ in ("ridge", "lgbm"):
        conn.execute("INSERT INTO ml_experiment (created_at,model_family,feature_set_ref,"
                     "label_def,cpcv_config_json,pre_registered_criteria_json,status) "
                     "VALUES (?,?,?,?,?,?,?)",
                     (now, m_, json.dumps(FEATURES), "fwd_ret_1m top500 liquid",
                      json.dumps({"groups": N_GROUPS, "test": N_TEST, "embargo_m": EMBARGO_M,
                                  "paths": n_paths}),
                      json.dumps({"beat_champion_median": True, "dsr_min": 0.5,
                                  "kendall_w_min": 0.7,
                                  "deploy_scope": "re-rank within linear top-N only"}),
                      verdicts[m_]))
        exp_id = conn.execute("SELECT MAX(exp_id) FROM ml_experiment").fetchone()[0]
        for pid, sh in enumerate(results[m_]):
            conn.execute("INSERT INTO ml_result (exp_id,path_id,model,sharpe,mean_ret,"
                         "deflated_sharpe,kendall_w,shap_top_json,created_at) "
                         "VALUES (?,?,?,?,?,?,?,?,?)",
                         (exp_id, pid, m_, None if np.isnan(sh) else round(sh, 3),
                          None, round(dsr[m_], 4) if not np.isnan(dsr[m_]) else None,
                          round(W, 3), None, now))
        # champion reference rows
    conn.commit(); conn.close()


if __name__ == "__main__":
    main()
