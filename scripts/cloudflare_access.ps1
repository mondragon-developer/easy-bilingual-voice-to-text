<#
.SYNOPSIS
  Put a Cloudflare Access gate in front of the phone front end's hostname.

.DESCRIPTION
  Creates a self-hosted Access application for the hostname with one policy:
  allow the given email, verified by a one-time code sent to it. After this,
  a visitor must pass Cloudflare's login page before a single byte reaches
  the tunnel, and then the app's own sign-in still applies. Two locks.

  Needs an API token in CLOUDFLARE_API_TOKEN (environment, or the project's
  .env) with these permissions:
    Account | Access: Apps and Policies                        | Edit
    Account | Access: Organizations, Identity Providers, Groups | Edit
    Account | Account Settings                                  | Read
  Make it at https://dash.cloudflare.com/profile/api-tokens, "Create Token",
  "Create Custom Token". The token is only used from this script, and can
  be deleted afterwards.

  Safe to run again: an application that already covers the hostname is
  left alone.

.PARAMETER Hostname
  The public hostname to protect.
.PARAMETER Email
  The one address allowed through.
#>
param(
    [Parameter(Mandatory)] [string]$Hostname,
    [Parameter(Mandatory)] [string]$Email
)

$ErrorActionPreference = "Stop"

$token = $env:CLOUDFLARE_API_TOKEN
if (-not $token) {
    $envFile = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
    if (Test-Path $envFile) {
        $line = Get-Content $envFile | Where-Object { $_ -match '^\s*CLOUDFLARE_API_TOKEN\s*=' } | Select-Object -First 1
        if ($line) { $token = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'") }
    }
}
if (-not $token) { throw "CLOUDFLARE_API_TOKEN is not set (environment or .env)." }

$api = "https://api.cloudflare.com/client/v4"
$headers = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }

function Call($method, $path, $body) {
    $args = @{ Method = $method; Uri = "$api$path"; Headers = $headers; UseBasicParsing = $true }
    if ($body) { $args.Body = ($body | ConvertTo-Json -Depth 8) }
    $res = Invoke-RestMethod @args
    if (-not $res.success) { throw ("Cloudflare API error: " + ($res.errors | ConvertTo-Json -Compress)) }
    return $res.result
}

Write-Host "== Checking the token"
Call GET "/user/tokens/verify" | Out-Null

Write-Host "== Finding the account"
$accounts = Call GET "/accounts?per_page=50"
if ($accounts.Count -gt 1) { Write-Host "Several accounts; using the first: $($accounts[0].name)" }
$account = $accounts[0].id

Write-Host "== One-time code login method"
$idps = Call GET "/accounts/$account/access/identity_providers"
if (-not ($idps | Where-Object { $_.type -eq "onetimepin" })) {
    Call POST "/accounts/$account/access/identity_providers" @{
        name = "One-time PIN"; type = "onetimepin"; config = @{}
    } | Out-Null
    Write-Host "Enabled."
} else {
    Write-Host "Already enabled."
}

Write-Host "== Access application for $Hostname"
$apps = Call GET "/accounts/$account/access/apps?per_page=100"
$existing = $apps | Where-Object { $_.domain -eq $Hostname }
if ($existing) {
    Write-Host "Already exists (id $($existing.id)); nothing changed."
} else {
    $app = Call POST "/accounts/$account/access/apps" @{
        name = "Speech to Text ($Hostname)"
        domain = $Hostname
        type = "self_hosted"
        session_duration = "720h"
        auto_redirect_to_identity = $false
        policies = @(@{
            name = "Only $Email"
            decision = "allow"
            include = @(@{ email = @{ email = $Email } })
        })
    }
    Write-Host "Created (id $($app.id))."
}

Write-Host ""
Write-Host "Done. Open https://$Hostname in a private window: Cloudflare should ask for"
Write-Host "a code sent to $Email before the app's own sign-in appears."
