# HiJack LMS - Local Sync and Auto-Deploy Script
# Run this script after making ANY change in the workspace to sync with the installed desktop app.

$ErrorActionPreference = "Stop"

$workspaceRoot = "c:\Users\user\Desktop\Hijack-lms"
$installedAppRoot = "C:\Users\user\AppData\Local\Programs\HiJack-LMS"
$pythonExe = "$installedAppRoot\runtime\python\python.exe"

Write-Host "=== 1. Building Frontend ===" -ForegroundColor Cyan
$env:PATH = "C:\Program Files\nodejs;$env:PATH"
Set-Location "$workspaceRoot\app\frontend"
& "C:\Program Files\nodejs\npm.cmd" run build
if ($LASTEXITCODE -ne 0) {
    Write-Error "Frontend build failed!"
    exit 1
}

Write-Host "=== 2. Applying Migrations in Workspace ===" -ForegroundColor Cyan
Set-Location "$workspaceRoot\app\backend"
& $pythonExe manage.py makemigrations
& $pythonExe manage.py migrate

Write-Host "=== 3. Synchronizing Files to Installed App ===" -ForegroundColor Cyan
# Copy backend code
Copy-Item "$workspaceRoot\app\backend\accounts\*" "$installedAppRoot\app\backend\accounts\" -Recurse -Force
Copy-Item "$workspaceRoot\app\backend\api\*" "$installedAppRoot\app\backend\api\" -Recurse -Force
Copy-Item "$workspaceRoot\app\backend\crm\*" "$installedAppRoot\app\backend\crm\" -Recurse -Force
Copy-Item "$workspaceRoot\app\backend\finance\*" "$installedAppRoot\app\backend\finance\" -Recurse -Force
Copy-Item "$workspaceRoot\app\backend\operations\*" "$installedAppRoot\app\backend\operations\" -Recurse -Force
Copy-Item "$workspaceRoot\app\backend\org\*" "$installedAppRoot\app\backend\org\" -Recurse -Force
Copy-Item "$workspaceRoot\app\backend\config\*" "$installedAppRoot\app\backend\config\" -Recurse -Force

# Copy frontend dist
Copy-Item "$workspaceRoot\app\frontend\dist\*" "$installedAppRoot\app\frontend\dist\" -Recurse -Force

Write-Host "=== 4. Applying Migrations in Installed App ===" -ForegroundColor Cyan
Set-Location "$installedAppRoot\app\backend"
& $pythonExe manage.py migrate

Write-Host "=== 5. Restarting Background Server (Port 8000) ===" -ForegroundColor Cyan
# Terminate old server processes
Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*HiJack-LMS*"
} | Stop-Process -Force
Start-Sleep -Seconds 1

# Start fresh server completely detached from the console / job object
$serverCmd = "`"$pythonExe`" manage.py runserver 127.0.0.1:8000 --noreload"
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = $serverCmd
    CurrentDirectory = "$installedAppRoot\app\backend"
} | Out-Null

Start-Sleep -Seconds 3

# Check health
try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/" -TimeoutSec 3
    if ($response -eq "ok") {
        Write-Host ">>> Server is UP and healthy on http://127.0.0.1:8000/ <<<" -ForegroundColor Green
        Write-Host "Remember to press Ctrl + F5 in your browser to clear cache!" -ForegroundColor Yellow
    }
} catch {
    Write-Warning "Server check returned an error. Please verify port 8000."
}
