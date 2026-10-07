<#
.SYNOPSIS
  Keeps the phone front end up: the web server, and the Cloudflare tunnel
  that makes it reachable from outside.

.DESCRIPTION
  Meant to run hidden at log on (install_web_service.ps1 puts a launcher in
  the Startup folder). It starts cloudflared when a tunnel config for this
  app exists, then runs python -m webapp in a loop that restarts it after a
  crash, backing off up to a minute. Everything logs under
  %LOCALAPPDATA%\SpeechToText.

  Remote sign-in comes from the project's .env (STT_REMOTE_USER and
  STT_REMOTE_PASSWORD), read by the server itself; this script never sees
  the password.
#>
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $env:LOCALAPPDATA "SpeechToText"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir "web-service.log"

function Log($text) {
    Add-Content -Path $log -Value ("{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $text)
}

# --- the tunnel ---------------------------------------------------------
$cloudflared = Join-Path $env:LOCALAPPDATA "cloudflared\cloudflared.exe"
$tunnelConfig = Join-Path $env:USERPROFILE ".cloudflared\speech-to-text.yml"
$tunnel = $null
if ((Test-Path $cloudflared) -and (Test-Path $tunnelConfig)) {
    $tunnel = Start-Process -FilePath $cloudflared -WindowStyle Hidden -PassThru `
        -ArgumentList @("--config", "`"$tunnelConfig`"", "tunnel", "run") `
        -RedirectStandardOutput (Join-Path $logDir "tunnel.out.log") `
        -RedirectStandardError (Join-Path $logDir "tunnel.err.log")
    Log "tunnel started, pid $($tunnel.Id)"
} else {
    Log "no tunnel: cloudflared or $tunnelConfig missing; serving on localhost only"
}

# --- the server, restarted after a crash --------------------------------
$delay = 2
while ($true) {
    Log "server starting"
    $started = Get-Date
    $server = Start-Process -FilePath "python" -ArgumentList @("-m", "webapp") `
        -WorkingDirectory $repo -WindowStyle Hidden -PassThru -Wait `
        -RedirectStandardOutput (Join-Path $logDir "web.out.log") `
        -RedirectStandardError (Join-Path $logDir "web.err.log")
    $uptime = ((Get-Date) - $started).TotalSeconds
    Log "server exited with code $($server.ExitCode) after $([int]$uptime)s"
    # A server that ran for a while earned a quick restart; one that dies
    # at once gets a growing pause, so a broken install does not spin.
    if ($uptime -gt 60) { $delay = 2 } else { $delay = [Math]::Min($delay * 2, 60) }
    Start-Sleep -Seconds $delay
}
