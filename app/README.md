# HiJack LMS — Core Application

Modern Learning Management System & CRM for educational centers, language schools, and tutoring academies.

Built with **Django REST Framework** + **Vue 3 / Vite**.

## Quick start

### 1. Backend

```powershell
cd app\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

API: http://127.0.0.1:8000/v1/

### 2. Frontend

```powershell
cd app\frontend
npm install
npm run dev
```

App: http://localhost:5173

### Default CEO Login

| Field | Value |
|---|---|
| Phone | `946263200` |
| Password | `946263200` |

## Key Features

- **Dashboard**: Real-time business metrics, active student counts, financial status.
- **Students & Leads**: Kanban and table views, funnel status, smart search, and quick actions.
- **Groups & Schedule**: Class management, course allocations, lesson timetables, and teacher assignments.
- **Finance**: Multi-mode student balance calculations, tuition payments, expenses, teacher salaries.
- **Reports**: Conversion pipeline, student attendance, left-students analytics, revenue summaries.
- **Data Import**: Smart import from CSV and Excel (.xlsx, .xls) with fuzzy column matching.
- **Telegram Bot Integration**: Automated debt alerts and student notifications.
- **Cross-platform**: Web SPA, zero-install Portable, and Windows Setup installer.
