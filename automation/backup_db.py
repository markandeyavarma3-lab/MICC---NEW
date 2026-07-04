#!/usr/bin/env python3
"""backup_db.py — Part 3 Module F(c): integrity-checked SQLite backups + restore drill.

Weekly:  VACUUM INTO a dated backup (safe on a live DB, defragments), then
         PRAGMA integrity_check on the BACKUP (a backup you never checked is not
         a backup), then WAL checkpoint on the source, then retention pruning.
Drill:   --drill opens the newest backup read-only, runs integrity_check and
         compares row counts of key tables vs live (restore confidence).

Retention: newest KEEP_WEEKLY weekly backups + first-backup-of-month archives
(KEEP_MONTHLY). Heartbeat row written to monitoring_log either way.

Run:  py -3.14 automation/backup_db.py [--drill]
"""
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(r"D:\marketDB\db\market.db")
BACKUP_DIR = Path(r"D:\marketDB\backups")
# 2026-07-04: moved off C: (house rule -- all MICC data lives under D:\MICC or
# D:\marketDB only). This is now a SAME-DRIVE secondary copy: it protects against
# accidental deletion / bad pruning of the primary backups dir, but NOT against a
# D: drive failure -- that DR guarantee is gone until this points at a genuinely
# separate physical location (external drive / NAS / cloud). Exactly ONE
# secondary copy is kept (newest).
SECONDARY_DIR = Path(os.environ.get("MICC_BACKUP_SECONDARY", r"D:\marketDB\backups_secondary"))
KEEP_WEEKLY = 2
KEEP_MONTHLY = 2
KEY_TABLES = ["stock_data", "stock_data_adj", "recommendations", "thesis",
              "trade", "score_audit", "event_signals", "index_membership"]


def log_monitor(status, detail):
    try:
        c = sqlite3.connect(DB_PATH, timeout=60)
        c.execute("INSERT INTO monitoring_log VALUES (?,?,?,?)",
                  (datetime.now().isoformat(), "backup:weekly", status, detail[:300]))
        c.commit(); c.close()
    except Exception:
        pass


def newest_backup():
    baks = sorted(BACKUP_DIR.glob("market_*.db"))
    return baks[-1] if baks else None


def drill():
    bak = newest_backup()
    if not bak:
        print("  DRILL FAIL: no backup found", flush=True)
        return 1
    print(f"  drill target: {bak.name} ({bak.stat().st_size/1e9:.1f} GB)", flush=True)
    bc = sqlite3.connect(f"file:{bak}?mode=ro", uri=True, timeout=120)
    ic = bc.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"  integrity_check: {ic}", flush=True)
    live = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=120)
    ok = ic == "ok"
    for t in KEY_TABLES:
        try:
            nb = bc.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            nl = live.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            drift = (nl - nb) / max(nl, 1)
            flag = "OK" if drift < 0.10 else "DRIFT"
            if flag != "OK":
                ok = False
            print(f"    {t:18} backup={nb:,} live={nl:,} [{flag}]", flush=True)
        except Exception as e:
            ok = False
            print(f"    {t}: ERR {str(e)[:60]}", flush=True)
    bc.close(); live.close()
    print(f"  DRILL {'PASS' if ok else 'FAIL'}", flush=True)
    return 0 if ok else 1


def backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    dest = BACKUP_DIR / f"market_{stamp}.db"
    if dest.exists():
        dest.unlink()
    t0 = datetime.now()
    conn = sqlite3.connect(DB_PATH, timeout=300)
    conn.execute("PRAGMA busy_timeout=300000")
    print(f"  VACUUM INTO {dest.name} ...", flush=True)
    conn.execute("VACUUM INTO ?", (str(dest),))
    # keep the source WAL from ballooning after a big vacuum read
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass
    conn.close()
    mins = (datetime.now() - t0).total_seconds() / 60
    size = dest.stat().st_size / 1e9
    print(f"  backup written: {size:.1f} GB in {mins:.1f} min", flush=True)

    bc = sqlite3.connect(f"file:{dest}?mode=ro", uri=True, timeout=120)
    ic = bc.execute("PRAGMA integrity_check").fetchone()[0]
    bc.close()
    print(f"  integrity_check(backup): {ic}", flush=True)
    if ic != "ok":
        dest.rename(dest.with_suffix(".db.CORRUPT"))
        log_monitor("FAIL", f"integrity_check={ic}")
        return 1

    # retention: newest weeklies + first-of-month archives
    baks = sorted(BACKUP_DIR.glob("market_*.db"))
    monthly_keep = {}
    for b in baks:                                   # first backup of each month
        month = b.stem.split("_")[1][:6]
        monthly_keep.setdefault(month, b)
    keep = set(baks[-KEEP_WEEKLY:]) | set(list(monthly_keep.values())[-KEEP_MONTHLY:])
    for b in baks:
        if b not in keep:
            b.unlink()
            print(f"  pruned {b.name}", flush=True)

    # secondary copy on the other drive (newest only; skip if space is short)
    sec = "skipped"
    try:
        import shutil
        free = shutil.disk_usage(SECONDARY_DIR.anchor).free
        if free > dest.stat().st_size * 1.1:
            SECONDARY_DIR.mkdir(parents=True, exist_ok=True)
            for old in SECONDARY_DIR.glob("market_*.db"):
                old.unlink()
            shutil.copy2(dest, SECONDARY_DIR / dest.name)
            sc = sqlite3.connect(f"file:{SECONDARY_DIR / dest.name}?mode=ro", uri=True)
            sec_ic = sc.execute("PRAGMA quick_check").fetchone()[0]
            sc.close()
            sec = f"copied ic={sec_ic}"
        else:
            sec = f"no-space ({free/1e9:.0f}GB free)"
    except Exception as e:
        sec = f"failed:{str(e)[:50]}"
    print(f"  secondary copy ({SECONDARY_DIR}): {sec}", flush=True)
    log_monitor("OK", f"{dest.name} {size:.1f}GB ic=ok kept={len(keep)} secondary={sec}")
    return 0


def main():
    sys.exit(drill() if "--drill" in sys.argv else backup())


if __name__ == "__main__":
    main()
