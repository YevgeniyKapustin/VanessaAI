# Reverse SSH tunnel from the owner's PC (native Windows Hermes) to the
# Vanessa server. The server side listens on BindAddress:RemotePort (the
# Docker bridge IP), never on 0.0.0.0, so only server containers reach it.
#
# Run once by hand to test:
#   powershell -ExecutionPolicy Bypass -File hermes-tunnel.ps1 -SshHost vanessa.example -SshUser deploy
# Start at logon (Task Scheduler):
#   powershell -ExecutionPolicy Bypass -File hermes-tunnel.ps1 -SshHost ... -SshUser ... -Install
param(
    [Parameter(Mandatory = $true)] [string] $SshHost,
    [Parameter(Mandatory = $true)] [string] $SshUser,
    [int] $SshPort = 22,
    [string] $KeyFile = "$env:USERPROFILE\.ssh\vanessa_hermes_ed25519",
    [int] $HermesPort = 8642,
    [string] $BindAddress = "172.17.0.1",
    [int] $RemotePort = 8642,
    [int] $RetrySeconds = 15,
    [switch] $Install
)

$ErrorActionPreference = "Stop"
$ssh = "$env:SystemRoot\System32\OpenSSH\ssh.exe"

if ($Install) {
    $argsLine = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`"" +
        " -SshHost $SshHost -SshUser $SshUser -SshPort $SshPort -KeyFile `"$KeyFile`"" +
        " -HermesPort $HermesPort -BindAddress $BindAddress -RemotePort $RemotePort"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argsLine
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName "VanessaHermesTunnel" -Action $action `
        -Trigger $trigger -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName "VanessaHermesTunnel"
    Write-Output "Installed and started task VanessaHermesTunnel"
    exit 0
}

while ($true) {
    & $ssh -N -T `
        -o BatchMode=yes `
        -o ServerAliveInterval=30 `
        -o ServerAliveCountMax=3 `
        -o ExitOnForwardFailure=yes `
        -o StrictHostKeyChecking=yes `
        -i $KeyFile `
        -p $SshPort `
        -R "${BindAddress}:${RemotePort}:127.0.0.1:${HermesPort}" `
        "$SshUser@$SshHost"
    Write-Output "$(Get-Date -Format s) tunnel exited ($LASTEXITCODE), retry in $RetrySeconds s"
    Start-Sleep -Seconds $RetrySeconds
}
