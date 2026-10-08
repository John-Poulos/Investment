# Registers the two Windows scheduled tasks for the nightly SEC refresh (D-SEC-15).
# Run once from the repo folder in PowerShell:   .\scripts\register_tasks.ps1
# Remove them with:                               .\scripts\register_tasks.ps1 -Remove
#
#  1. "Investment engine - nightly SEC refresh": every day at 02:00 local time; wakes the
#     PC from sleep to run. Runs only while you are logged on (locked screen is fine).
#  2. "Investment engine - missed refresh check": a few minutes after you log on; if the
#     02:00 run was missed (PC off or logged off), asks before catching up (owner choice).
# Both use the project's pythonw.exe, so no console window opens. Reports go to logs\.

param([switch]$Remove)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Pythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"
$Script = Join-Path $Root "scripts\run_refresh.py"
$Nightly = "Investment engine - nightly SEC refresh"
$Missed = "Investment engine - missed refresh check"

if ($Remove) {
    foreach ($name in @($Nightly, $Missed)) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Write-Host "Removed: $name"
        }
    }
    return
}

if (-not (Test-Path $Pythonw)) { throw "Not found: $Pythonw (run 'uv sync' in $Root first)" }

$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

# 1. Nightly at 02:00. StartWhenAvailable is off on purpose: a missed run is handled by
#    task 2, which asks first.
$nightlyAction = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Script`" --scheduled" `
    -WorkingDirectory $Root
$nightlyTrigger = New-ScheduledTaskTrigger -Daily -At "02:00"
$nightlySettings = New-ScheduledTaskSettingsSet -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $Nightly -Action $nightlyAction -Trigger $nightlyTrigger `
    -Settings $nightlySettings -Principal $principal -Force | Out-Null
Write-Host "Registered: $Nightly (daily 02:00, wakes from sleep)"

# 2. At logon (2-minute delay): ask before catching up if the last 02:00 run was missed.
$missedAction = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Script`" --if-missed --ask" `
    -WorkingDirectory $Root
$missedTrigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$missedTrigger.Delay = "PT2M"
$missedSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $Missed -Action $missedAction -Trigger $missedTrigger `
    -Settings $missedSettings -Principal $principal -Force | Out-Null
Write-Host "Registered: $Missed (at logon, asks before catching up)"
