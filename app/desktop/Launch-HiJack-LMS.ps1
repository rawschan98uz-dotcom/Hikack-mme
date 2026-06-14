#Requires -Version 5.1
<#
.SYNOPSIS
  Start Hi Jack LMS (Django + built frontend) and open in app window.

.PARAMETER Network
  Listen on all network interfaces (0.0.0.0) so other computers on LAN can connect.
#>
param(
  [int]$Port = 8000,
  [string]$HostName = '127.0.0.1',
  [switch]$Network
)

$ErrorActionPreference = 'Stop'
$AppRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $AppRoot 'backend'
$FrontendRoot = Join-Path $AppRoot 'frontend'
$DistIndex = Join-Path $FrontendRoot 'dist\index.html'

if ($Network) {
  $BindHost = '0.0.0.0'
  $LocalUrl = "http://127.0.0.1:$Port/"
} else {
  $BindHost = $HostName
  $LocalUrl = "http://${HostName}:$Port/"
}

function Test-ServerReady {
  param([string]$CheckUrl = $LocalUrl)
  try {
    $response = Invoke-WebRequest -Uri $CheckUrl -UseBasicParsing -TimeoutSec 2
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Ensure-FirewallRule {
  param([int]$RulePort)
  $ruleName = 'Hi Jack LMS'
  $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
  if ($existing) {
    return
  }

  try {
    New-NetFirewallRule `
      -DisplayName $ruleName `
      -Direction Inbound `
      -Protocol TCP `
      -LocalPort $RulePort `
      -Action Allow `
      -Profile Private, Domain `
      -ErrorAction Stop | Out-Null
    Write-Host "Firewall rule added for port $RulePort (Private/Domain networks)."
  } catch {
    Write-Warning "Could not add firewall rule (run as Administrator or allow port $RulePort manually)."
  }
}

function Get-LanAddresses {
  Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
      $_.IPAddress -notlike '127.*' -and
      $_.IPAddress -notlike '169.254.*' -and
      $_.PrefixOrigin -ne 'WellKnown'
    } |
    Select-Object -ExpandProperty IPAddress -Unique
}

function Show-NetworkInfo {
  param([int]$InfoPort)
  $addresses = @(Get-LanAddresses)
  Write-Host ''
  Write-Host '=== Network access ==='
  if ($addresses.Count -eq 0) {
    Write-Host "Other computers: http://<this-pc-ip>:$InfoPort/"
    Write-Host 'Run "ipconfig" to find your IPv4 address.'
  } else {
    Write-Host 'Other computers can open:'
    foreach ($ip in $addresses) {
      Write-Host "  http://${ip}:$InfoPort/"
    }
  }
  Write-Host 'All PCs must be on the same Wi-Fi / LAN.'
  Write-Host ''
}

function Test-PortInUse {
  param([int]$CheckPort)
  return [bool](Get-NetTCPConnection -LocalPort $CheckPort -State Listen -ErrorAction SilentlyContinue)
}

function Ensure-BackendReady {
  if (-not (Test-Path (Join-Path $BackendRoot '.venv\Scripts\python.exe'))) {
    Write-Host 'Creating Python virtual environment...'
    Push-Location $BackendRoot
    python -m venv .venv
    Pop-Location
  }

  $python = Join-Path $BackendRoot '.venv\Scripts\python.exe'
  $pip = Join-Path $BackendRoot '.venv\Scripts\pip.exe'

  Write-Host 'Installing backend dependencies...'
  & $pip install -q -r (Join-Path $BackendRoot 'requirements.txt')

  Push-Location $BackendRoot
  if (-not (Test-Path (Join-Path $BackendRoot 'db.sqlite3'))) {
    Write-Host 'Initializing database...'
    & $python manage.py migrate --noinput
    & $python manage.py seed_demo
  } else {
    & $python manage.py migrate --noinput | Out-Null
  }
  Pop-Location
}

function Ensure-FrontendBuilt {
  if (Test-Path $DistIndex) {
    return
  }

  Write-Host 'Building frontend (first run)...'
  Push-Location $FrontendRoot
  if (-not (Test-Path 'node_modules')) {
    npm install
  }
  npm run build
  Pop-Location

  if (-not (Test-Path $DistIndex)) {
    throw 'Frontend build failed. dist/index.html not found.'
  }
}

function Start-BackendServer {
  $python = Join-Path $BackendRoot '.venv\Scripts\python.exe'
  $logDir = Join-Path $AppRoot 'desktop'
  $logFile = Join-Path $logDir 'server.log'
  $pidFile = Join-Path $logDir 'server.pid'

  New-Item -ItemType Directory -Force -Path $logDir | Out-Null

    $proc = Start-Process -FilePath $python `
    -ArgumentList @('manage.py', 'runserver', "${BindHost}:$Port", '--noreload') `
    -WorkingDirectory $BackendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError (Join-Path $logDir 'server.err') `
    -PassThru

  Set-Content -Path $pidFile -Value $proc.Id -Encoding ascii
  return $proc
}

function Open-AppWindow {
  param([string]$TargetUrl)

  $chrome = "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe"
  if (-not (Test-Path $chrome)) {
    $chrome = "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
  }

  $edge = "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe"
  if (-not (Test-Path $edge)) {
    $edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
  }

  if (Test-Path $chrome) {
    Start-Process $chrome -ArgumentList @("--app=$TargetUrl", '--new-window')
    return
  }

  if (Test-Path $edge) {
    Start-Process $edge -ArgumentList @("--app=$TargetUrl", '--new-window')
    return
  }

  Start-Process $TargetUrl
}

Write-Host 'Hi Jack LMS — starting...'

if ($Network) {
  Write-Host 'Network mode: server accepts connections from other computers.'
  Ensure-FirewallRule -RulePort $Port
}

Ensure-FrontendBuilt
Ensure-BackendReady

if (-not (Test-PortInUse -CheckPort $Port)) {
  Write-Host "Starting server on ${BindHost}:$Port"
  Start-BackendServer | Out-Null
} else {
  Write-Host "Server already listening on port $Port"
}

$attempts = 0
while (-not (Test-ServerReady) -and $attempts -lt 30) {
  Start-Sleep -Seconds 1
  $attempts++
}

if (-not (Test-ServerReady)) {
  Write-Error "Server did not respond at $LocalUrl. Check app\desktop\server.log"
}

if ($Network) {
  Show-NetworkInfo -InfoPort $Port
}

Write-Host "Opening $LocalUrl"
Open-AppWindow -TargetUrl $LocalUrl
