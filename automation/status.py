#!/usr/bin/env python3
"""status.py — quick automation health view: last heartbeats + freshness.

Run:  py -3.14 D:\\MICC\\automation\\status.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")


def main():
    c = sqlite3.connect(DB_PATH, timeout=30)

    print("=== last 10 heartbeats ===")
    rows = c.execute(
        "SELECT ts,check_name,status,detail FROM monitoring_log "
        "WHERE check_name LIKE 'heartbeat:%' ORDER BY ts DESC LIMIT 10").fetchall()
    if not rows:
        print("  (none yet — a scheduled run has not completed)")
    for ts, name, status, detail in rows:
        flag = "OK  " if status == "OK" else "FAIL"
        print(f"  [{flag}] {ts[:19]}  {name:16} {detail}")

    # consecutive green streak (the 10-in-a-row acceptance gate)
    streak = 0
    for _, _, status, _ in rows:
        if status == "OK":
            streak += 1
        else:
            break
    print(f"\n  green streak (newest-first): {streak}/10 "
          f"{'-> gate PASSED, safe to trust unattended' if streak >= 10 else ''}")

    print("\n=== phase timeout headroom (want cap >= 3x observed max) ===")
    # observed max across ALL runs, but cap from the LATEST run — old rows carry
    # since-raised caps and previously produced stale [TIGHT] flags for phases
    # that were already fixed (bit us on 2026-07-05).
    rt = c.execute(
        "SELECT ts, check_name, detail FROM monitoring_log "
        "WHERE check_name LIKE 'phase_runtime:%' ORDER BY ts").fetchall()
    obs_max, cur_cap = {}, {}
    for _ts, name, detail in rt:
        try:
            obs, cap = detail.replace("s", "").split(" / cap ")
            obs, cap = float(obs), float(cap)
        except (ValueError, AttributeError):
            continue
        phase = name.split(":", 1)[1]
        obs_max[phase] = max(obs_max.get(phase, 0), obs)
        cur_cap[phase] = cap            # rows are ts-ordered: last write wins
    if not obs_max:
        print("  (no runtimes logged yet — populates from the next pipeline run)")
    tight = {p: (obs_max[p], cur_cap[p]) for p in obs_max
             if obs_max[p] > cur_cap[p] / 3}
    for p, (o, cp) in sorted(tight.items(), key=lambda kv: -kv[1][0] / kv[1][1]):
        print(f"  [TIGHT] {p:16} max {o:.0f}s vs cap {cp:.0f}s -> raise cap to ~{3*o:.0f}s")
    if obs_max and not tight:
        print(f"  all {len(obs_max)} phases have >=3x headroom")

    print("\n=== data freshness (cadence-aware) ===")
    # (table, column, cadence, max age in days before it is genuinely stale)
    for tbl, col, cadence, max_age in [
            ("stock_data", "date", "daily", 5),
            ("fo_data", "date", "daily", 5),
            ("current_signals", "rebal_date", "monthly", 35),
            ("idea_card", "card_date", "monthly", 35)]:
        try:
            latest = c.execute(f"SELECT MAX({col}) FROM {tbl}").fetchone()[0]
            age = c.execute("SELECT julianday('now') - julianday(?)",
                            (latest,)).fetchone()[0]
            flag = "OK   " if age is not None and age <= max_age else "STALE"
            print(f"  [{flag}] {tbl:16} latest {latest}  ({cadence}, "
                  f"{age:.0f}d old, limit {max_age}d)")
        except Exception as e:
            print(f"  [?    ] {tbl:16} ({str(e)[:40]})")
    c.close()


if __name__ == "__main__":
    main()
