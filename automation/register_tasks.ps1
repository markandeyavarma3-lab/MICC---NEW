# register_tasks.ps1 - one-time registration of the MICC scheduled tasks.
# Self-elevates to admin (required to create a "run whether logged on or not"
# task with RunLevel Highest - the fix for the earlier scheduled-task issue).
#
# Creates:
#   MICC-Daily   : daily  18:30 local (post-close EOD refresh)
#   MICC-Weekly  : Friday 19:30 local (fundamentals/registry/backtest rebuild)
#
# 2026-07-05 incident fixes baked in:
#   - ExecutionTimeLimit was 4h for BOTH tasks; Task Scheduler killed the
#     2026-07-03 weekly mid-run (Last Result 267014) after ~5.4h — the weekly
#     legitimately needs 6-10h (fundamentals ~1.6h + annual_fin up to 6h +
#     backtest rebuild). Now: daily 6h, weekly 14h.
#   - Weekly moved 19:00 -> 19:30: the scheduled daily finishes ~19:00:20-45,
#     so the Friday weekly used to start INSIDE the daily's final writes —
#     that overlap produced a "database is locked" failure on 2026-07-03.
#
# Run once:  powershell -ExecutionPolicy Bypass -File automation\register_tasks.ps1
# Verify:    schtasks /query /tn MICC-Daily ; schtasks /query /tn MICC-Weekly

$ErrorActionPreference = 'Stop'

# --- self-elevate if not already admin ---
$admin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host 'Elevating to administrator...'
    Start-Process powershell -Verb RunAs -ArgumentList (
        '-NoProfile','-ExecutionPolicy','Bypass','-File',"`"$PSCommandPath`"")
    exit
}

$repoRoot = 'D:\MICC'
$daily  = Join-Path $repoRoot 'automation\run_daily.ps1'
$weekly = Join-Path $repoRoot 'automation\run_weekly.ps1'

# run whether logged on or not, with highest privileges, as the current user
$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType S4U -RunLevel Highest

function New-MiccSettings($hours) {
    New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -DontStopOnIdleEnd -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours $hours)
}

function Register-Micc($name, $script, $trigger, $settings) {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force | Out-Null
    Write-Host "registered $name"
}

Register-Micc 'MICC-Daily'  $daily  (New-ScheduledTaskTrigger -Daily -At 6:30PM) (New-MiccSettings 6)
Register-Micc 'MICC-Weekly' $weekly (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At 7:30PM) (New-MiccSettings 14)

Write-Host ''
Write-Host 'Done. Verify with:  schtasks /query /tn MICC-Daily'
