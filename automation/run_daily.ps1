# run_daily.ps1 - MICC daily pipeline wrapper (Task Scheduler entry point).
# Runs run_pipeline.py --daily, tees a timestamped log, then records a heartbeat
# and fires a failure alert (via heartbeat.py). Designed to run unattended.

$ErrorActionPreference = 'Continue'
$repoRoot = 'D:\MICC'
$pipeDir  = Join-Path $repoRoot 'data_extraction'
$logDir   = Join-Path $pipeDir  'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$log   = Join-Path $logDir "daily_$stamp.log"

$env:PYTHONIOENCODING = 'utf-8'   # keep Unicode logs clean on Windows
Set-Location $pipeDir

py -3.14 run_pipeline.py | Tee-Object -FilePath $log
$code = $LASTEXITCODE

py -3.14 (Join-Path $repoRoot 'automation\heartbeat.py') --job daily --exit $code --log $log
exit $code
