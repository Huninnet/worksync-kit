$ErrorActionPreference = "Stop"

$wd = $PSScriptRoot

# The Microsoft Store alias (WindowsApps\python.exe) is a stub: exit code 9009.
# Get-Command alone is not proof, so every candidate must actually run print(1).
$candidates = @()
$candidates += (Join-Path $env:USERPROFILE ".workbuddy\binaries\python\versions\3.13.12\python.exe")
foreach ($name in @("python", "py")) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if ($c -and $c.Source) { $candidates += $c.Source }
}
$py = $null
foreach ($c in $candidates) {
    if (-not $c -or -not (Test-Path $c)) { continue }
    try {
        $out = & $c -c "print(1)" 2>$null
        if (("$out").Trim() -eq "1") { $py = $c; break }
    } catch { }
}
if (-not $py) { throw "Python not found: no candidate passed the print(1) test. Edit this script and set `$py manually." }
Write-Host "Python:" $py

# Sync interval is user-configurable via config.json "interval_minutes" (default 30).
$interval = 30
$cfgPath = Join-Path $wd "config.json"
if (Test-Path $cfgPath) {
    try {
        # -Encoding UTF8: PS 5.1 defaults to system codepage (GBK on zh-CN), mojibake breaks ConvertFrom-Json
        $j = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($j.interval_minutes -and [int]$j.interval_minutes -ge 1) { $interval = [int]$j.interval_minutes }
    } catch { }
}
Write-Host "Sync interval:" "$interval minutes"

$act = New-ScheduledTaskAction -Execute $py `
    -Argument ('"' + (Join-Path $wd "sync.py") + '" sync --quiet') `
    -WorkingDirectory $wd
$t1 = New-ScheduledTaskTrigger -AtLogOn
$t2 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $interval) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName "WorkBuddy WorkSync" -Action $act -Trigger $t1, $t2 `
    -Settings $set -Description "WorkBuddy cross-device sync" -Force | Out-Null

Start-ScheduledTask -TaskName "WorkBuddy WorkSync"
Start-Sleep -Seconds 5
Get-ScheduledTaskInfo -TaskName "WorkBuddy WorkSync" |
    Select-Object TaskName, LastRunTime, LastTaskResult | Format-List
Write-Host "Done. Log:" (Join-Path $wd "logs\sync.log")
