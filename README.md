# HiJack LMS

**HiJack LMS** is a modern, full-featured Learning Management System (LMS) and CRM platform designed for educational centers, language academies, tutoring centers, and private schools.

It offers a complete suite of tools to manage the entire educational workflow: from incoming leads and student enrollments to course scheduling, attendance tracking, teacher payroll, and financial analytics.

---

## 🌟 Key Features

### 👨‍🎓 Students & Leads CRM
* **Leads Funnel:** Kanban board and list view to manage prospective students across pipeline stages.
* **Student Directory:** Comprehensive profiles with contact information, enrolled groups, attendance history, and individual balance.
* **Parent & Contact Info:** Secondary contacts, notes, tags, and status tracking.

### 📚 Groups, Courses & Timetables
* **Course Catalog:** Configurable course types, lesson durations, and pricing.
* **Groups & Scheduling:** Room assignment, day-of-week recurrence, and teacher allocation.
* **Attendance & Grading:** Quick-mark daily attendance with automatic debiting and statistics.

### 💰 Finance, Billing & Payroll
* **Multi-Mode Balance Engine:** Supports flexible billing models (daily, monthly, full-course, modular, individual).
* **Tuition Payments:** Multi-method payments (cash, card, bank transfer) with automated receipts.
* **Expenses & Salary:** Operational expense tracking and calculated teacher salaries based on hours/students.
* **Debtor Alerts:** Real-time visibility into students with negative balance.

### 📥 Smart Data Import & Export
* **Intelligent File Parser:** Supports both **CSV** and **Excel (.xlsx, .xls)** formats.
* **Smart Column Detection:** Automatic fuzzy matching for column headers in Russian, Uzbek, and English (e.g., `ФИО`, `Студент`, `Ism`, `Тел`, `Telefon`, `Школа`, `Группа`).
* **Messy Data Tolerant:** Automatically detects header rows even if title banners exist on rows 1–3, cleans up composite names, and extracts 9-digit telephone numbers from noisy cells.
* **1-Click Excel Template:** Built-in template download with UTF-8 BOM to open cleanly in Microsoft Excel on Windows without character encoding glitches.

### 🤖 Telegram Bot Integration
* Automated notifications to students and parents about class schedules, payments, and balance reminders.
* Configurable bot tokens via system settings.

### 💻 Desktop & Portable Distribution
* **Windows Setup Installer:** Single-file installer (`HiJack-LMS-Setup.exe`) with desktop and Start Menu shortcuts, background server lifecycle management, and clean uninstall.
* **Zero-Install Portable Archive:** Self-contained portable edition (`HiJack-LMS-Portable.zip`) with bundled Python runtime and SQLite database — runs on any Windows PC without installation or admin rights.

---

## 🚀 Getting Started

### Option 1: Desktop Application (Windows)
1. Download or locate `HiJack-LMS-Setup.exe`.
2. Run the installer and follow the prompt.
3. Launch **HiJack LMS** from the desktop shortcut. The local server starts automatically in background and opens your default browser.

### Option 2: Portable Edition (No Installation)
1. Unpack `HiJack-LMS-Portable.zip` into any folder or USB drive.
2. Double-click `launcher.pyw` (or `start.bat`) to start.
3. When finished, double-click `stop.pyw` (or `stop.bat`) to shut down the server.

### Option 3: Running from Source (Development)

#### Backend (Django REST Framework)
```powershell
cd app\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```
The REST API will be available at `http://127.0.0.1:8000/v1/`.

#### Frontend (Vue 3 + Vite)
```powershell
cd app\frontend
npm install
npm run dev
```
The application will open at `http://localhost:5173`.

---

## 🔑 Default CEO Credentials

To log in to a newly deployed or cleaned system:

| Parameter | Value |
|---|---|
| **Phone / Login** | `946263200` |
| **Password** | `HiJack2024!` |
| **Role** | CEO / Administrator |

---

## 📁 Project Architecture

```
Hijack-mme/
├── app/
│   ├── backend/        # Django REST Framework backend
│   │   ├── accounts/   # User authentication, roles & RBAC
│   │   ├── api/        # REST API endpoints & smart import parser
│   │   ├── crm/        # Students, Leads, Groups, Courses
│   │   ├── finance/    # Payments, Expenses, Salaries, Debts
│   │   └── operations/ # Attendance, Scores, Schedules
│   ├── frontend/       # Vue 3 SPA with Tailwind CSS & Pinia
│   └── desktop/        # Windows desktop runtime & system-tray assets
├── installer/          # Inno Setup compiler script (HiJack-LMS.iss)
├── portable/           # Portable bundle staging directory
├── HiJack-LMS-Setup.exe     # Compiled Windows installer
├── HiJack-LMS-Portable.zip  # Compiled portable archive
└── Dockerfile          # Production container configuration
```

---

## 📜 License

Private and proprietary. All rights reserved.
