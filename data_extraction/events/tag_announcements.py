#!/usr/bin/env python3
"""tag_announcements.py — Part 3 Module E (optional item): classify corporate
announcements into a fixed event taxonomy.

Deterministic keyword rules FIRST (reproducible, free, auditable) — the doc's
own guidance for delivery components. An LLM pass can be layered later for the
'other' residual; tags are INPUTS to event research, never trade triggers.

Idempotent full rebuild -> announcement_tags. Run:  py -3.14 events/tag_announcements.py
"""
import re
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(r"D:\MICC\marketDB\db\market.db")

# tag -> regex over the announcement subject (checked in order; first hit wins)
TAXONOMY = [
    ("buyback",           r"buy.?back"),
    ("results",           r"financial result|outcome of board meeting|result"),
    ("dividend",          r"dividend"),
    ("fund_raise",        r"fund rais|qip|preferential|rights issue|fpo|allotment"),
    ("pledge",            r"pledge"),
    ("order_win",         r"order|contract|award|bagging|loi\b|letter of intent"),
    ("merger_acquisition",r"merger|amalgamation|acquisition|acquir|scheme of arrangement|demerger|stake"),
    ("mgmt_change",       r"resignation|appointment|change in management|cessation|kmp|smp"),
    ("rating",            r"credit rating|rating action|icra|crisil|care rating"),
    ("capacity_capex",    r"capacity|expansion|capex|new plant|commissioning|commercial production"),
    ("regulatory",        r"sebi|penalty|show cause|litigation|tax demand|gst|income tax|inspection"),
    ("meeting_admin",     r"trading window|newspaper publication|shareholders meeting|agm|egm|book closure|record date|analyst|investor meet|con\.? call|press release"),
    ("takeover_disclosure", r"takeover regulation|sast"),
]

DDL = """CREATE TABLE IF NOT EXISTS announcement_tags (
    ann_id INTEGER PRIMARY KEY,      -- corporate_announcements.id
    symbol TEXT, announcement_date TEXT,
    tag TEXT, matched TEXT, tagged_at TEXT)"""


def classify(subject):
    s = (subject or "").lower()
    for tag, pat in TAXONOMY:
        m = re.search(pat, s)
        if m:
            return tag, m.group(0)
    return "other", None


def main():
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute(DDL)
    conn.execute("DELETE FROM announcement_tags")
    now = datetime.now().isoformat()
    rows = []
    for aid, sym, d, subj in conn.execute(
            "SELECT id, symbol, announcement_date, subject FROM corporate_announcements"):
        tag, matched = classify(subj)
        rows.append((aid, sym, d, tag, matched, now))
    conn.executemany("INSERT OR REPLACE INTO announcement_tags VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    print(f"  tagged {len(rows):,} announcements:", flush=True)
    for tag, n in conn.execute("SELECT tag, COUNT(*) FROM announcement_tags "
                               "GROUP BY tag ORDER BY 2 DESC"):
        print(f"    {tag:22} {n:>6,}", flush=True)
    other = conn.execute("SELECT COUNT(*) FROM announcement_tags WHERE tag='other'").fetchone()[0]
    print(f"  residual 'other': {other/len(rows)*100:.0f}% (LLM layer candidate later)", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
