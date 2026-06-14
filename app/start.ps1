# Start backend and frontend dev servers (run from app/)
$backend = Start-Process powershell -ArgumentList @(
  '-NoExit', '-Command',
  "cd '$PSScriptRoot\backend'; if (-not (Test-Path .venv)) { python -m venv .venv }; .\.venv\Scripts\Activate.ps1; pip install -q -r requirements.txt; if (-not (Test-Path db.sqlite3)) { python manage.py makemigrations accounts org crm; python manage.py migrate; python manage.py seed_demo }; python manage.py runserver"
) -PassThru

Start-Sleep -Seconds 3

$frontend = Start-Process powershell -ArgumentList @(
  '-NoExit', '-Command',
  "cd '$PSScriptRoot\frontend'; npm install; npm run dev"
) -PassThru

Write-Host "Backend PID: $($backend.Id)"
Write-Host "Frontend PID: $($frontend.Id)"
Write-Host "Open http://localhost:5173"
