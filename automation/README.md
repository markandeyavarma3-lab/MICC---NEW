# MICC automation (Task Scheduler)

Local, unattended scheduling for the pipeline. GitHub Actions is **not** usable
here — the 19 GB `market.db` lives on `D:\` and cloud runners can't reach it.

| File | Role |
|---|---|
| `run_daily.ps1` | Task entry point: `run_pipeline.py` (daily) + log + heartbeat |
| `run_weekly.ps1` | Task entry point: `run_pipeline.py --weekly` + log + heartbeat |
| `heartbeat.py` | Writes `monitoring_log` per run; alerts on failure (no silent fails) |
| `register_tasks.ps1` | One-time: registers `MICC-Daily` (18:30) + `MICC-Weekly` (Fri 19:00) |

## Setup (once, as admin)
```powershell
powershell -ExecutionPolicy Bypass -File automation\register_tasks.ps1   # self-elevates
schtasks /query /tn MICC-Daily        # verify
```
Tasks run **whether logged on or not** (`-LogonType S4U -RunLevel Highest`) and
catch up missed runs (`-StartWhenAvailable`).

## Failure alerts (optional)
Set a Slack/Discord-style webhook so failures ping you:
```powershell
[Environment]::SetEnvironmentVariable('MICC_ALERT_WEBHOOK','https://hooks...','User')
```
Without it, failures are still recorded in `monitoring_log` (`heartbeat:<job>` = FAIL).

## Acceptance gate before retiring the manual run
Watch for **10 consecutive green unattended runs** (`monitoring_log` heartbeats OK)
before trusting the schedule.

> Note: API keys (`ALPHAVANTAGE_KEY`, `FRED_API_KEY`) must exist as User env vars —
> the scheduled task inherits the user environment. They are already set.
