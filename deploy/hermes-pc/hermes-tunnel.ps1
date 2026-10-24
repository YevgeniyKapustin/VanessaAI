# Reverse SSH tunnel from the owner's PC (native Windows Hermes) to the
# Vanessa server. The server side listens on BindAddress:RemotePort (the
# Docker bridge IP), never on 0.0.0.0, so only server containers reach it.
#
# Run once by hand to test:
#   powershell -ExecutionPolicy Bypass -File hermes-tunnel.ps1 -SshHost vanessa.example -SshUser deploy
# Install as a self-healing scheduled task (copies this file to InstallDir):
#   powershell -ExecutionPolicy Bypass -File hermes-tunnel.ps1 -SshHost ... -SshUser ... -Install
param(
    [Parameter(Mandatory = $true)] [string] $SshHost,
    [Parameter(Mandatory = $true)] [string] $SshUser,
    [int] $SshPort = 22,
    [string] $KeyFile = "$env:USERPROFILE\.ssh\vanessa_hermes_ed25519",
    [int] $HermesPort = 8642,
    [string] $BindAddress = "172.17.0.1",
    [int] $RemotePort = 8642,
    [int] $RetrySeconds = 5,
    [int] $MaxRetrySeconds = 60,
    [int] $StableSeconds = 120,
    [string] $LogDir = "$env:LOCALAPPDATA\hermes-tunnel",
    [string] $InstallDir = "$env:LOCALAPPDATA\hermes-tunnel",
    [string] $TaskName = "VanessaHermesTunnel",
    [int] $RepeatMinutes = 5,
    [switch] $Install
)

$ssh = "$env:SystemRoot\System32\OpenSSH\ssh.exe"
$logFile = Join-Path $LogDir "tunnel.log"

function New-EventTrigger([string] $query) {
    $cls = Get-CimClass -ClassName MSFT_TaskEventTrigger `
        -Namespace Root/Microsoft/Windows/TaskScheduler
    $trigger = New-CimInstance -CimClass $cls -ClientOnly
    $trigger.Subscription = "<QueryList><Query Id='0'>$query</Query></QueryList>"
    $trigger.Enabled = $true
    return $trigger
}

function Stop-OldTunnel {
    # A stopped task can leave its ssh.exe alive; it would keep the remote port.
    $forward = "-R ${BindAddress}:${RemotePort}:"
    Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
        Where-Object { $_.CommandLine -like "*$forward*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
}

function Install-TunnelTask {
    New-Item -ItemType Directory -Force $InstallDir | Out-Null
    $script = Join-Path $InstallDir "hermes-tunnel.ps1"
    if ($PSCommandPath -ne $script) { Copy-Item $PSCommandPath $script -Force }
    # conhost --headless: no console window, so nothing can close it.
    $argsLine = "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass" +
        " -File `"$script`" -SshHost $SshHost -SshUser $SshUser -SshPort $SshPort" +
        " -KeyFile `"$KeyFile`" -HermesPort $HermesPort -BindAddress $BindAddress" +
        " -RemotePort $RemotePort -LogDir `"$LogDir`""
    $action = New-ScheduledTaskAction -Execute "conhost.exe" -Argument $argsLine
    $resume = "<Select Path='System'>*[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter']" +
        " and EventID=1]] or *[System[Provider[@Name='Microsoft-Windows-Kernel-Power'] and EventID=507]]</Select>"
    $network = "<Select Path='Microsoft-Windows-NetworkProfile/Operational'>*[System[EventID=10000]]</Select>"
    $triggers = @(
        (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME),
        (New-ScheduledTaskTrigger -Once -At (Get-Date) `
            -RepetitionInterval (New-TimeSpan -Minutes $RepeatMinutes)),
        (New-EventTrigger $resume),
        (New-EventTrigger $network)
    )
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -MultipleInstances IgnoreNew -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -DontStopOnIdleEnd
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers `
        -Settings $settings -Force | Out-Null
    Stop-ScheduledTask -TaskName $TaskName
    Stop-OldTunnel
    Start-ScheduledTask -TaskName $TaskName
    Write-Output "Installed and started task $TaskName ($script)"
}

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

function Invoke-Tunnel {
    & $ssh -N -T `
        -o BatchMode=yes `
        -o ConnectTimeout=15 `
        -o ServerAliveInterval=15 `
        -o ServerAliveCountMax=3 `
        -o TCPKeepAlive=yes `
        -o ExitOnForwardFailure=yes `
        -o StrictHostKeyChecking=yes `
        -E (Join-Path $LogDir "ssh.log") `
        -i $KeyFile `
        -p $SshPort `
        -R "${BindAddress}:${RemotePort}:127.0.0.1:${HermesPort}" `
        "$SshUser@$SshHost"
    return $LASTEXITCODE
}

if ($Install) {
    $ErrorActionPreference = "Stop"
    Install-TunnelTask
    exit 0
}

New-Item -ItemType Directory -Force $LogDir | Out-Null
Write-Log "start pid $PID, -R ${BindAddress}:${RemotePort} -> 127.0.0.1:${HermesPort}"
$delay = $RetrySeconds
while ($true) {
    $started = Get-Date
    try {
        $code = Invoke-Tunnel
    } catch {
        $code = "error: $($_.Exception.Message)"
    }
    $uptime = [int]((Get-Date) - $started).TotalSeconds
    if ($uptime -ge $StableSeconds) { $delay = $RetrySeconds }
    Write-Log "ssh exited ($code) after $uptime s, retry in $delay s"
    Start-Sleep -Seconds $delay
    $delay = [Math]::Min($delay * 2, $MaxRetrySeconds)
}
