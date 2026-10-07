<#
.SYNOPSIS
  Make the phone front end reachable from your own devices, through Tailscale.

.DESCRIPTION
  The three manual steps from the README's "Use it from your phone", in one
  run: install Tailscale if it is missing, sign this computer in (a browser
  window opens for that once), and publish the local server inside your
  private Tailscale network with HTTPS. Prints the address to open on the
  phone at the end.

  Needs a network that lets Tailscale through: some institutional networks
  block its hosts entirely, in which case this fails at the first step and
  says so. Run it from home or a phone hotspot; once signed in, Tailscale
  keeps working on those networks too.

  Safe to run again: each step is skipped when already done.

.PARAMETER Port
  Where the web server listens. Default 8765, matching python -m webapp.
#>
param([int]$Port = 8765)

$ErrorActionPreference = "Stop"
$exe = "C:\Program Files\Tailscale\tailscale.exe"

function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }

Step "Checking the server"
try {
    $status = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/status" |
        ConvertFrom-Json
    Write-Host "Running: Whisper $($status.model) on $($status.device)"
} catch {
    Write-Host "The web server is not running on port $Port." -ForegroundColor Yellow
    Write-Host "Start it with scripts\web_server.bat (or python -m webapp) and run this again."
    exit 1
}

Step "Checking that this network lets Tailscale through"
try {
    Invoke-WebRequest -UseBasicParsing -Method Head "https://login.tailscale.com/" -TimeoutSec 15 | Out-Null
} catch {
    Write-Host "Cannot reach login.tailscale.com from here." -ForegroundColor Yellow
    Write-Host "This network blocks Tailscale. Run this script from home or a phone hotspot."
    exit 1
}

Step "Installing Tailscale"
if (Test-Path $exe) {
    Write-Host "Already installed."
} else {
    winget install --id Tailscale.Tailscale --exact --silent `
        --accept-package-agreements --accept-source-agreements
    if (-not (Test-Path $exe)) { throw "Tailscale did not install; see the winget output above." }
}

Step "Signing this computer in"
$state = (& $exe status --json 2>$null | ConvertFrom-Json)
if ($state -and $state.BackendState -eq "Running") {
    Write-Host "Already signed in as $($state.Self.DNSName.TrimEnd('.'))"
} else {
    Write-Host "A browser window opens: sign in with the same account you will use on the phone."
    & $exe up
}

Step "Publishing the server to your devices, with HTTPS"
& $exe serve --bg --https=443 "http://127.0.0.1:$Port"

$self = (& $exe status --json | ConvertFrom-Json).Self.DNSName.TrimEnd('.')
Step "Done"
Write-Host "On the phone: install Tailscale, sign in with the same account, then open"
Write-Host ""
Write-Host "    https://$self" -ForegroundColor Green
Write-Host ""
Write-Host "Allow the microphone when asked, and use the browser's 'Add to Home Screen'."
Write-Host "Only devices signed in to your Tailscale account can reach this address."
