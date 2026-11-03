# Runs the Vanessa deploy bridge (bridge.py) on the owner's PC and keeps it
# alive. The server reaches it through the same reverse SSH tunnel as
# Hermes: 172.17.0.1:8643 -> 127.0.0.1:8643.
#
# Install once (writes the bearer token, copies the files, registers a task):
#   powershell -ExecutionPolicy Bypass -File run-bridge.ps1 -Install -Token <long-secret>
# Test by hand:
#   powershell -ExecutionPolicy Bypass -File run-bridge.ps1 -Token <long-secret>
param(
    [string] $Python = "python",
    [string] $Glab = "glab",
    [int] $Port = 8643,
    [string] $Token = "",
    [string] $TokenFile = "$env:LOCALAPPDATA\vanessa-bridge\token",
    [string] $LogDir = "$env:LOCALAPPDATA\vanessa-bridge",
    [string] $InstallDir = "$env:LOCALAPPDATA\vanessa-bridge",
    [string] $TaskName = "VanessaDeployBridge",
    [int] $RetrySeconds = 5,
    [int] $MaxRetrySeconds = 60,
    [int] $RepeatMinutes = 5,
    [switch] $Install
)

$logFile = Join-Path $LogDir "bridge.log"

function Write-Log([string] $text) {
    try {
        if ((Test-Path $logFile) -and (Get-Item $logFile).Length -gt 1MB) {
            Move-Item $logFile "$logFile.old" -Force
        }
        Add-Content -Path $logFile -Value "$(Get-Date -Format s) $text"
    } catch {
        Write-Output "$(Get-Date -Format s) $text"
    }
}

function Resolve-Command([string] $name) {
    $found = Get-Command $name -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    return $name
}

function Stop-OldBridge {
    $script = [Regex]::Escape((Join-Path $InstallDir "run-bridge.ps1"))
    $loopPattern = '-File\s+"?' + $script + '"?(\s|$)'
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='pwsh.exe'" |
        Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match $loopPattern } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*bridge.py*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
}

function Install-BridgeTask {
    New-Item -ItemType Directory -Force $InstallDir | Out-Null
    New-Item -ItemType Directory -Force $LogDir | Out-Null
    if ($Token) {
        Set-Content -Path $TokenFile -Value $Token -NoNewline -Encoding ascii
        Write-Output "Token written to $TokenFile"
    }
    if (-not (Test-Path $TokenFile)) {
        throw "No token: run again with -Install -Token <long-secret>"
    }
    $script = Join-Path $InstallDir "run-bridge.ps1"
    $code = Join-Path $InstallDir "bridge.py"
    Copy-Item $PSCommandPath $script -Force
    Copy-Item (Join-Path $PSScriptRoot "bridge.py") $code -Force
    $powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $argsLine = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass" +
        " -File `"$script`" -Python `"$(Resolve-Command $Python)`"" +
        " -Glab `"$(Resolve-Command $Glab)`" -Port $Port" +
        " -TokenFile `"$TokenFile`" -LogDir `"$LogDir`""
    $action = New-ScheduledTaskAction -Execute $powershell -Argument $argsLine
    $triggers = @(
        (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME),
        (New-ScheduledTaskTrigger -Once -At (Get-Date) `
            -RepetitionInterval (New-TimeSpan -Minutes $RepeatMinutes))
    )
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -MultipleInstances IgnoreNew -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -DontStopOnIdleEnd
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers `
        -Settings $settings -Force | Out-Null
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Stop-OldBridge
    Start-ScheduledTask -TaskName $TaskName
    Write-Output "Installed and started task $TaskName ($script)"
}

if ($Install) {
    $ErrorActionPreference = "Stop"
    Install-BridgeTask
    exit 0
}

if (-not $Token) {
    if (-not (Test-Path $TokenFile)) { throw "No token: pass -Token or install it first" }
}
New-Item -ItemType Directory -Force $LogDir | Out-Null
$bridge = Join-Path $PSScriptRoot "bridge.py"
$delay = $RetrySeconds
while ($true) {
    $started = Get-Date
    # The stored interpreter may vanish with a Hermes update; fall back to PATH.
    $pythonExe = if (Test-Path $Python) { $Python } else { Resolve-Command "python" }
    $cliArgs = @($bridge, "--port", "$Port", "--glab", (Resolve-Command $Glab),
        "--token-file", $TokenFile, "--log-file", $logFile)
    Write-Log "start bridge pid $PID"
    try {
        & $pythonExe @cliArgs 2>&1 | ForEach-Object { Write-Log "out: $_" }
        $code = $LASTEXITCODE
    } catch {
        $code = "error: $($_.Exception.Message)"
    }
    $uptime = [int]((Get-Date) - $started).TotalSeconds
    if ($uptime -ge 120) { $delay = $RetrySeconds }
    Write-Log "bridge exited ($code) after $uptime s, retry in $delay s"
    Start-Sleep -Seconds $delay
    $delay = [Math]::Min($delay * 2, $MaxRetrySeconds)
}
