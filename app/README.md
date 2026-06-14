# Hijack MME — Runnable Clone (MVP)

Local ModMe-like CRM clone with Django API + Vue 3 frontend.

## Quick start

### 1. Backend

```powershell
cd D:\projects\Hijack-mme\app\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py makemigrations accounts org crm
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

API: http://127.0.0.1:8000/v1/

### 2. Frontend

```powershell
cd D:\projects\Hijack-mme\app\frontend
npm install
npm run dev
```

App: http://localhost:5173

### Demo login

| Field | Value |
|-------|-------|
| Phone | `903708242` |
| Password | `50608991Zz!` |

## What's included

- Login (JWT, ModMe-style API envelope)
- Dashboard with 8 metric cards
- **Leads, Teachers, Groups, Students, Courses** — tables with data
- **Finance** — payments, withdraw, expenses, salaries
- **Reports** — conversion pipeline, attendance, leads stats
- **Settings** — general tab with save
- SQLite database (no PostgreSQL required)
- Seed data for all sections above

After pulling updates, re-run:
```powershell
python manage.py migrate
python manage.py seed_demo
```
Restart backend + refresh frontend.

## Phases complete

Implementation phases **0–15** are done. Regression checklist: `../docs/15-phase15-verification.md`.
