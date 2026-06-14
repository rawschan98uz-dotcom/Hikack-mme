#Requires -Version 5.1
<#
.SYNOPSIS
  Build Hi Jack LMS, create icon, and place desktop shortcut.
#>
$ErrorActionPreference = 'Stop'

$AppRoot = Split-Path -Parent $PSScriptRoot
$DesktopRoot = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $DesktopRoot 'Hi Jack LMS (Server).lnk'
$LauncherPath = Join-Path $PSScriptRoot 'Launch-HiJack-LMS-Network.ps1'
$OldShortcutPath = Join-Path $DesktopRoot 'Hi Jack LMS.lnk'
$IconPath = Join-Path $PSScriptRoot 'assets\lms.ico'
$BackendRoot = Join-Path $AppRoot 'backend'
$FrontendRoot = Join-Path $AppRoot 'frontend'

Write-Host '=== Hi Jack LMS — desktop install ==='

# Backend venv + icon dependency
if (-not (Test-Path (Join-Path $BackendRoot '.venv\Scripts\python.exe'))) {
  Push-Location $BackendRoot
  python -m venv .venv
  Pop-Location
}

$pip = Join-Path $BackendRoot '.venv\Scripts\pip.exe'
$python = Join-Path $BackendRoot '.venv\Scripts\python.exe'

Write-Host 'Installing Pillow for icon generation...'
& $pip install -q pillow

Write-Host 'Creating LMS icon...'
& $python (Join-Path $PSScriptRoot 'create_icon.py')

Write-Host 'Building frontend...'
Push-Location $FrontendRoot
if (-not (Test-Path 'node_modules')) {
  npm install
}
npm run build
Pop-Location

Write-Host 'Preparing database...'
Push-Location $BackendRoot
& $pip install -q -r requirements.txt
& $python manage.py migrate --noinput
if (-not (Test-Path 'db.sqlite3')) {
  & $python manage.py seed_demo
}
Pop-Location

Write-Host "Creating shortcut: $ShortcutPath"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = 'powershell.exe'
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$LauncherPath`""
$shortcut.WorkingDirectory = $AppRoot
$shortcut.IconLocation = "$IconPath,0"
$shortcut.Description = 'Hi Jack LMS — this computer + others on LAN'
$shortcut.Save()

if (Test-Path $OldShortcutPath) {
  Remove-Item $OldShortcutPath -Force
  Write-Host "Removed old shortcut: $OldShortcutPath"
}

Write-Host ''
Write-Host 'Done. Desktop shortcut "Hi Jack LMS (Server)" is ready.'
Write-Host 'This computer + other devices on the same Wi-Fi/LAN can connect.'
