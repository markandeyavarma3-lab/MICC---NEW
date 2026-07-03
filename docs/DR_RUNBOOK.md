# MICC Disaster-Recovery Runbook

*Written 2026-07-03. Test the restore drill monthly: `py -3.14 automation\backup_db.py --drill`*

## What exists, where
| Asset | Location | Cadence |
|---|---|---|
| Live DB (19 GB) | `D:\marketDB\db\market.db` | continuous |
| Primary backups (VACUUM INTO, integrity-checked) | `D:\marketDB\backups\market_YYYYMMDD.db` | weekly, keep 2 weekly + 2 monthly |
| Secondary copy (different drive) | `C:\MICC_backups\` (newest only) | weekly |
| Parquet lake (prices, rebuildable source) | `data_storage/parquet/` + `D:\marketDB\stocks\all` | daily |
| Code + configs | GitHub `markandeyavarma3-lab/MICC---NEW` | every change |
| Dependency lock | `requirements-lock.txt` (py -3.14) | on change |

## Scenario 1 — DB corrupted, D: alive
1. Stop scheduled tasks: `schtasks /end /tn MICC-Daily` (and Weekly); disable temporarily.
2. `PRAGMA integrity_check` on the live DB to confirm corruption.
3. Rename the corrupt DB aside; copy the newest `D:\marketDB\backups\market_*.db`
   to `D:\marketDB\db\market.db`.
4. `py -3.14 automation\backup_db.py --drill` mindset: run
   `py -3.14 data_extraction\common\verify_phases.py` — all green = restored.
5. Re-run `py -3.14 data_extraction\run_pipeline.py` to catch up the gap days
   (daily_update backfills missed dates). Re-enable tasks.

## Scenario 2 — D: drive dead
1. New disk. Restore code: `git clone https://github.com/markandeyavarma3-lab/MICC---NEW D:\MICC`.
2. Restore env: install Python 3.14, `py -3.14 -m pip install -r requirements-lock.txt`.
3. Restore DB from the secondary copy: `C:\MICC_backups\market_*.db` → `D:\marketDB\db\market.db`.
   (Loses at most 7 days of data — the daily pipeline re-fetches recent days on next run;
   older gap days: `market/daily_update.py` checks the last ~6 trading dates only, so for a
   longer outage re-run bhavcopy backfill for the missing range.)
4. Re-set user env vars: `ALPHAVANTAGE_KEY`, `MICC_NTFY_TOPIC`, optional `FRED_API_KEY`,
   `MICC_ALERT_WEBHOOK`, `MICC_CAPITAL`, `MICC_RISK_BUDGET`.
5. Re-register tasks: `powershell -ExecutionPolicy Bypass -File automation\register_tasks.ps1`.
6. `verify_phases.py` green + one green heartbeat = recovered.

## Scenario 3 — both drives dead
Code + docs survive on GitHub. Market data is re-buildable from source (bhavcopy
2005→, NSE/BSE fetchers) but slowly (~days). The derived research tables rebuild
from `PART1/2/3.md` reproduce sections. Idea-desk *track record* (thesis/trade,
score_audit, weekly_review) would be LOST — this is the argument for adding a
cloud copy (R2/Backblaze) of the weekly backup if the desk record becomes valuable.

## Alert channels
- Failures push to ntfy topic **`micc-alerts-iy1e2gza3p`** (subscribe in the ntfy
  app: https://ntfy.sh/micc-alerts-iy1e2gza3p). Optional Slack/Discord via
  `MICC_ALERT_WEBHOOK` (takes precedence).
- Heartbeats + phase runtimes: `py -3.14 automation\status.py`.
