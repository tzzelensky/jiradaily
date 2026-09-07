# Регистрация фоновых заданий Windows.
# 1) Демон при входе в Windows (всегда крутится в фоне)
# 2) Запасной триггер Пн–Пт 11:30 (если демон не запущен)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Daemon = Join-Path $Root "daemon.py"
$Report = Join-Path $Root "report.py"
$DaemonTask = "JiraTgReportDaemon"
$DailyTask = "JiraTgDailyReport"

if (-not (Test-Path $Python)) {
    Write-Error "Сначала создай venv и поставь зависимости (см. README)."
}

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# --- демон при логине ---
$DaemonAction = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "`"$Daemon`"" `
    -WorkingDirectory $Root
$LogonTrigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask `
    -TaskName $DaemonTask `
    -Action $DaemonAction `
    -Trigger $LogonTrigger `
    -Settings $Settings `
    -Force | Out-Null

# --- запасной ежедневный запуск ---
$DailyAction = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "`"$Report`"" `
    -WorkingDirectory $Root
$DailyTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "11:30AM"
Register-ScheduledTask `
    -TaskName $DailyTask `
    -Action $DailyAction `
    -Trigger $DailyTrigger `
    -Settings $Settings `
    -Force | Out-Null

# Стартуем демон сразу
Start-ScheduledTask -TaskName $DaemonTask

Write-Host "OK:"
Write-Host "  $DaemonTask  — крутится в фоне с входа в Windows (сейчас запущен)"
Write-Host "  $DailyTask   — запасной запуск Пн–Пт 11:30"
Write-Host "Проверка: Get-ScheduledTask -TaskName $DaemonTask,$DailyTask"
