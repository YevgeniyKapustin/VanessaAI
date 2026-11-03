# Keep only the Vanessa Hermes profile running. The gateway's own liveness
# watchdog exits with code 75; Windows Startup items do not restart it.
# -Install copies this script outside the checkout and keeps a hidden supervisor.
param(
    [string] $ProfileHome = "$env:LOCALAPPDATA\hermes\profiles\vanessa",
    [string] $InstallDir = "$env:LOCALAPPDATA\hermes-tunnel",
    [string] $TaskName = "VanessaHermesGatewayWatchdog",
    [ValidateRange(5, 300)] [int] $CheckSeconds = 15,
    [switch] $Install
)

$ErrorActionPreference = "Stop"
$ProfileHome = [IO.Path]::GetFullPath($ProfileHome)
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$logFile = Join-Path $InstallDir "watchdog.log"

function Write-Log([string] $message) {
    if ((Test-Path -LiteralPath $logFile) -and (Get-Item -LiteralPath $logFile).Length -gt 1MB) {
        Move-Item -LiteralPath $logFile -Destination "$logFile.old" -Force
    }
    Add-Content -LiteralPath $logFile -Value "$(Get-Date -Format s) $message"
}

function Get-GatewayProcess {
    $pidFile = Join-Path $ProfileHome "gateway.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) { return $null }
    try {
        $record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
        $recordHome = [IO.Path]::GetFullPath($record.hermes_home)
        if ($record.kind -ne "hermes-gateway" -or $recordHome -ne $ProfileHome) {
            return $null
        }
        $gatewayProcess = Get-Process -Id ([int]$record.pid) -ErrorAction Stop
        # Hermes stores the process creation time in centiseconds. Check it
        # before adopting a PID: Windows can reuse the PID of an exited gateway.
        $epoch = [DateTime]::SpecifyKind([DateTime]"1970-01-01", [DateTimeKind]::Utc)
        $created = [Math]::Floor(($gatewayProcess.StartTime.ToUniversalTime() - $epoch).TotalSeconds * 100)
        if ([Math]::Abs($created - [double]$record.start_time) -gt 2) { return $null }
        return $gatewayProcess
    } catch {
        return $null
    }
}

function Install-Watchdog {
    $script = Join-Path $InstallDir "hermes-gateway-watchdog.ps1"
    if ($PSCommandPath -ne $script) {
        Copy-Item -LiteralPath $PSCommandPath -Destination $script -Force
    }
    $argsLine = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass" +
        " -File `"$script`" -ProfileHome `"$ProfileHome`" -InstallDir `"$InstallDir`"" +
        " -CheckSeconds $CheckSeconds"
    $powerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $action = New-ScheduledTaskAction -Execute $powerShell `
        -Argument $argsLine -WorkingDirectory $InstallDir
    $triggers = @(
        (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME),
        (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
            -RepetitionInterval (New-TimeSpan -Minutes 1))
    )
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -DontStopOnIdleEnd
    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue |
        Stop-ScheduledTask
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers `
        -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    Write-Output "Installed and started $TaskName ($script)"
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
$launcher = Join-Path $ProfileHome "gateway-service\Hermes_Gateway_vanessa.vbs"
if (-not (Test-Path -LiteralPath $launcher)) { throw "Missing Vanessa gateway launcher: $launcher" }

if ($Install) {
    Install-Watchdog
    exit 0
}

# Keep this task alive: its child gateway must survive the launcher.
Write-Log "supervisor started pid $PID"
while ($true) {
    $gatewayProcess = Get-GatewayProcess
    if ($null -eq $gatewayProcess) {
        # The launcher sets the environment of the working Hermes installation.
        Write-Log "Vanessa gateway is absent; starting its installed launcher"
        Start-Process -FilePath "$env:SystemRoot\System32\wscript.exe" `
            -ArgumentList "`"$launcher`"" -WindowStyle Hidden | Out-Null
    }
    Start-Sleep -Seconds $CheckSeconds
}
