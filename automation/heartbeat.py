#!/usr/bin/env python3
"""heartbeat.py — Part 1 Stage 5: record every scheduled pipeline run and shout on
failure. Task Scheduler gives NO failure alerts by default; this closes that gap.

Writes one row to monitoring_log per run (check_name='heartbeat:<job>'), and on a
non-zero exit posts to MICC_ALERT_WEBHOOK (Slack/Discord-style JSON) if that env
var is set. Stdlib only; never raises (a broken alert must not fail the job).

Usage:  py -3.14 automation/heartbeat.py --job daily --exit 0 --log <path>
"""
import argparse
import json
import os
import sqlite3
import urllib.request
from datetime import datetime
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")


def tail(path, n=25):
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except Exception:
        return ""


def notify(job, code, log):
    url = os.environ.get("MICC_ALERT_WEBHOOK")
    if not url:
        return "no-webhook"
    text = (f":rotating_light: MICC pipeline *{job}* FAILED (exit {code})\n"
            f"```\n{tail(log, 20)}\n```")
    try:
        req = urllib.request.Request(
            url, data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15)
        return "sent"
    except Exception as e:
        return f"alert-failed:{str(e)[:60]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--exit", type=int, required=True)
    ap.add_argument("--log", default="")
    a = ap.parse_args()

    status = "OK" if a.exit == 0 else "FAIL"
    detail = f"exit={a.exit}"
    if a.exit != 0:
        detail += f" | alert={notify(a.job, a.exit, a.log)}"

    try:
        c = sqlite3.connect(DB_PATH, timeout=60)
        c.execute("INSERT INTO monitoring_log VALUES (?,?,?,?)",
                  (datetime.now().isoformat(), f"heartbeat:{a.job}", status, detail))
        c.commit(); c.close()
    except Exception as e:
        print(f"heartbeat: DB write failed: {e}", flush=True)

    print(f"heartbeat[{a.job}] {status} ({detail})", flush=True)


if __name__ == "__main__":
    main()
