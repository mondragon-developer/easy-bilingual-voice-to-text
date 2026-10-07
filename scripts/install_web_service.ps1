<#
.SYNOPSIS
  Start the phone front end at every log on, hidden, and start it now.

.DESCRIPTION
  Puts a small launcher in the current user's Startup folder that runs
  web_service.ps1 with no window. No administrator rights are needed, and
  nothing is installed system-wide. Run with -Uninstall to remove the
  launcher and stop the running server and tunnel.
#>
param([switch]$Uninstall)

$ErrorActionPreference = "Stop"
$startup = [Environment]::GetFolderPath("Startup")
$launcher = Join-Path $startup "SpeechToText web.vbs"
$service = Join-Path $PSScriptRoot "web_service.ps1"

function Stop-Service-Processes {
    # The supervisor, the server it runs, and this app's own tunnel. Not
    # this installer (whose name contains "web_service.ps1" too), and not
    # any other cloudflared tunnel on the machine.
    Get-CimInstance Win32_Process |
        Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and (
            $_.CommandLine -like "*\web_service.ps1*" -or
            $_.CommandLine -like "*-m webapp*" -or
            $_.CommandLine -like "*speech-to-text.yml*") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

if ($Uninstall) {
    Stop-Service-Processes
    if (Test-Path $launcher) { Remove-Item $launcher }
    Write-Host "Removed the log-on launcher and stopped the server and tunnel."
    exit 0
}

# VBScript doubles quotes inside a string, so the path's own quotes become
# "" and the whole command sits in one line.
$command = 'powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""' + $service + '""'
$lines = @()
$lines += "' Starts the Speech to Text phone front end at log on, hidden."
$lines += "' Logs: $env:LOCALAPPDATA\SpeechToText. Remove this file to stop it starting."
$lines += 'CreateObject("WScript.Shell").Run "' + $command + '", 0, False'
Set-Content -Path $launcher -Value ($lines -join "`r`n") -Encoding ASCII

Stop-Service-Processes
Start-Process wscript.exe -ArgumentList "`"$launcher`""
Write-Host "Installed $launcher and started the server."
Write-Host "Logs: $env:LOCALAPPDATA\SpeechToText"
