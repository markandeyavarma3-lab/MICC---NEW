#!/usr/bin/env python3
"""status.py — quick automation health view: last heartbeats + freshness.

Run:  py -3.14 D:\\MICC\\automation\\status.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")


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
    rt = c.execute(
        "SELECT check_name, detail FROM monitoring_log "
        "WHERE check_name LIKE 'phase_runtime:%'").fetchall()
    worst = {}
    for name, detail in rt:
        try:
            obs, cap = detail.replace("s", "").split(" / cap ")
            obs, cap = float(obs), float(cap)
        except (ValueError, AttributeError):
            continue
        phase = name.split(":", 1)[1]
        if phase not in worst or obs > worst[phase][0]:
            worst[phase] = (obs, cap)
    if not worst:
        print("  (no runtimes logged yet — populates from the next pipeline run)")
    tight = {p: (o, cp) for p, (o, cp) in worst.items() if o > cp / 3}
    for p, (o, cp) in sorted(tight.items(), key=lambda kv: -kv[1][0] / kv[1][1]):
        print(f"  [TIGHT] {p:16} max {o:.0f}s vs cap {cp:.0f}s -> raise cap to ~{3*o:.0f}s")
    if worst and not tight:
        print(f"  all {len(worst)} phases have >=3x headroom")

    print("\n=== data freshness ===")
    for tbl, col in [("stock_data", "date"), ("fo_data", "date"),
                     ("current_signals", "rebal_date"), ("idea_card", "card_date")]:
        try:
            latest = c.execute(f"SELECT MAX({col}) FROM {tbl}").fetchone()[0]
            print(f"  {tbl:16} latest {latest}")
        except Exception as e:
            print(f"  {tbl:16} ? ({str(e)[:40]})")
    c.close()


if __name__ == "__main__":
    main()
