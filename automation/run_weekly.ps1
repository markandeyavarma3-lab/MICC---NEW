# run_weekly.ps1 - MICC weekly pipeline wrapper (Task Scheduler entry point).
# Runs run_pipeline.py --weekly (fundamentals, registries, index membership,
# backtest rebuild, backups etc.), tees a log, records a heartbeat + failure alert.

$ErrorActionPreference = 'Continue'
$repoRoot = 'D:\MICC'
$pipeDir  = Join-Path $repoRoot 'data_extraction'
$logDir   = Join-Path $pipeDir  'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$log   = Join-Path $logDir "weekly_$stamp.log"

$env:PYTHONIOENCODING = 'utf-8'
Set-Location $pipeDir

py -3.14 run_pipeline.py --weekly | Tee-Object -FilePath $log
$code = $LASTEXITCODE

py -3.14 (Join-Path $repoRoot 'automation\heartbeat.py') --job weekly --exit $code --log $log

# log rotation: prune pipeline logs older than 60 days
Get-ChildItem $logDir -Filter *.log | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-60) } | Remove-Item -Force -ErrorAction SilentlyContinue

exit $code
