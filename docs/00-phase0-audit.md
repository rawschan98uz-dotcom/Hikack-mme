# Phase 0 Audit — Hijack-mme

**Date:** 2026-06-10  
**Status:** ✅ Complete — ready for Phase 1

---

## 0.1 Local run check

| Service | URL | Status |
|---------|-----|--------|
| Backend (Django) | http://127.0.0.1:8000/v1/ | ✅ Running |
| Frontend (Vite) | http://localhost:5173/ | ✅ Running |
| Proxy `/v1` → backend | `vite.config.ts` | ✅ Configured |
| Login flow | POST `/v1/auth/login` | ✅ 200 (seen in server logs) |
| Migrations | all apps | ✅ Up to date |

### Start commands

```powershell
# Backend
cd D:\projects\Hijack-mme\app\backend
.\.venv\Scripts\Activate.ps1
python manage.py runserver 8000

# Frontend
cd D:\projects\Hijack-mme\app\frontend
npm run dev
```

---

## 0.2 Demo / seed data

**Command:** `python manage.py seed_demo`

| Entity | Count (after seed) | Notes |
|--------|-------------------|-------|
| Company | 1 | `ravvatech` / RavvaTech |
| Branches | 2 | Main branch, Branch 2 |
| Admin user | 1 | phone `903708242` |
| Staff users | 2 | Kamola, Sherzod |
| Teachers | 2 | Nilufar, Jamshid *(fixed in phase 0)* |
| Courses | 1 | English A1 (code `a1`) |
| Groups | 1 | English-1 → course + teacher |
| Students | 5 | mixed statuses incl. debtor |
| Leads | 5 | all pipeline stages |
| Rooms | 2 | Room 101, 202 |
| Holidays | 1 | Navruz |
| Reminders | 2 | today + overdue |
| Finance | payments, withdraw, expense, salary | sample rows |
| Logs | SMS, call, activity | sample rows |
| Tags, forms, archive | yes | sample rows |

**Demo login:** phone `903708242`, password `50608991Zz!` (see `app/README.md`).

---

## 0.3 Screen → API → status map

Legend: **✅** ready · **🟡** partial (read or limited write) · **🔴** placeholder · **⬜** UI only (no API wired)

### Auth & shell

| Route | View | API | Status | Gap |
|-------|------|-----|--------|-----|
| `/login` | LoginView | POST `/auth/login`, `/auth/me` | ✅ | — |
| Layout sidebar | AppLayout | — | ✅ | Header buttons (search, +) ⬜ |

### Primary nav (order = implementation order)

| # | Route | View | GET API | Write API | Status | Gap |
|---|-------|------|---------|-----------|--------|-----|
| 1 | `/dashboard/default` | DashboardView | `/dashboard` | — | 🟡 | Widget buttons unwired |
| 2 | `/leads` | LeadsView | `/leads` | — | 🟡 | ADD NEW unwired |
| 3 | `/teachers` | TeachersView | `/user?type=teacher`, `/branch` | POST/DELETE `/user/teacher` | 🟡 | Edit blocked |
| 4 | `/groups` | GroupsView | `/groups` | — | 🟡 | ADD NEW unwired, no detail |
| 5 | `/students` | StudentsView | `/students` | — | 🟡 | ADD NEW unwired, debtors filter ✅ |
| 6 | `/reminders` | RemindersView | `/reminders` | — | 🟡 | ADD NEW unwired |
| 7 | `/rating` | RatingView | `/scores/branch` | — | 🟡 | Graph tab shell only |
| 8 | `/attendance-reports` | ReportsAttendanceView | `/reports/attendance` | — | 🟡 | Same as reports attendance |
| 9 | `/teacher-attendance-reports` | PlaceholderView | — | — | 🔴 | Full implementation deferred → Phase 10 |

### Finance flyout

| Route | View | GET API | Write | Status |
|-------|------|---------|-------|--------|
| `/finance/payments` | FinancePaymentsView | `/replenishments` | — | 🟡 read-only |
| `/finance/withdraw` | FinanceWithdrawView | `/withdraws` | — | 🟡 |
| `/finance/cost` | FinanceExpensesView | `/expense` | — | 🟡 |
| `/finance/new-salaries` | FinanceSalariesView | `/salary-settings` | — | 🟡 |
| `/students/debtors` | StudentsView | `/students?debtors=1` | — | 🟡 |

### Reports flyout

| Route | View | GET API | Status |
|-------|------|---------|--------|
| `/reports/conversion` | ReportsConversionView | `/reports/conversion` | 🟡 read-only |
| `/reports/attendance` | ReportsAttendanceView | `/reports/attendance` | 🟡 |
| `/reports/leads` | ReportsLeadsView | `/reports/leads` | 🟡 |
| `/reports/left-students` | PlaceholderView | — | 🔴 → Phase 12 |
| `/reports/workly` | PlaceholderView | — | 🔴 → Phase 12 |

### Settings flyout (implementation order within Phase 13)

| Route | View | GET API | Write | Status |
|-------|------|---------|-------|--------|
| `/auto-sms` | AutoSmsView | `/company/settings` | — | 🟡 Save button unwired |
| `/admin/voip` | PlaceholderView | — | — | 🔴 → Phase 13.A |
| `/settings-grade` | PlaceholderView | — | — | 🔴 → Phase 13.B |
| `/settings` | SettingsView | `/company/settings` | POST settings | 🟡 General tab only |
| `/staff/list` | StaffView | `/user?type=staff` | — | 🟡 ADD unwired |
| `/billing` | BillingView | `/company/:id/payments` | — | 🟡 |
| `/roadmap` | PlaceholderView | — | — | 🔴 defer / external link |
| `/courses` | CoursesView | `/courses` | POST `/courses` | 🟡 no detail route |
| `/rooms` | RoomsView | `/room` | — | 🟡 ADD unwired |
| `/holiday` | HolidaysView | `/holidayRecalculation` | — | 🟡 ADD unwired |
| `/archive/list` | ArchiveView | `/archive/list` | — | 🟡 |
| `/left-students` | PlaceholderView | — | — | 🔴 → Phase 13.D |
| `/form` | FormsView | `/leadForm` | — | 🟡 ADD unwired |
| `/tags` | TagsView | `/tags` | — | 🟡 ADD unwired |
| `/blog/news` | PlaceholderView | — | — | 🔴 defer |
| `/sms` | SmsLogView | `/sms/report` | — | 🟡 read-only |
| `/call` | CallLogView | `/call/logs` | — | 🟡 read-only |
| `/history/logs` | ActivityLogsView | `/history/logs` | — | 🟡 read-only |

### Backend endpoints without matching UI action

| Endpoint | Methods | Used by |
|----------|---------|---------|
| `/courses` | GET, POST | CoursesView |
| `/courses/:id` | — | **Missing** |
| `/groups` | GET only | GroupsView |
| `/leads` | GET only | LeadsView |
| `/students` | GET only | StudentsView |
| `/room` | GET only | RoomsView |
| `/user/teacher` | POST | TeachersView |
| `/user/teacher/:id` | DELETE | TeachersView |
| `/company/settings` | GET, POST | SettingsView, AutoSmsView |

---

## 0.4 Placeholder routes — decision

| Route | Title | Decision |
|-------|-------|----------|
| `/teacher-attendance-reports` | Teacher attendance reports | **Implement** — Phase 10 |
| `/reports/left-students` | Students left the group | **Implement** — Phase 12 (may share with `/left-students`) |
| `/reports/workly` | Workly Report | **Implement** — Phase 12 (needs ModMe API capture) |
| `/settings-grade` | Grade | **Implement** — Phase 13.B |
| `/admin/voip` | VoIP settings | **Implement** — Phase 13.A |
| `/roadmap` | Roadmap | **Defer** — external link or static page |
| `/left-students` | Students left the group | **Implement** — Phase 13.D (merge with reports variant) |
| `/blog/news` | What's new | **Defer** — optional GET `/blog/` later |

---

## Phase 0 fixes applied

1. **Seed teachers** — `seed_demo.py` now creates 2 teachers and assigns one to English-1 group.
2. **This audit document** — single source of truth for Phase 1+.

---

## Final status (Phase 15 — 2026-06-10)

All primary routes implemented. **Zero `PlaceholderView` routes** in the app router.

| Category | Status |
|----------|--------|
| Core CRM (Leads, Teachers, Groups, Students, Reminders) | ✅ Full CRUD |
| Rating, Attendance, Teacher attendance | ✅ |
| Finance (payments, withdraw, expenses, salaries, debtors) | ✅ |
| Reports (conversion, leads, attendance, left-students, workly) | ✅ |
| Settings (VoIP, grade, SMS, staff, courses, rooms, holidays, archive, forms, tags, roadmap, left-students, what's new) | ✅ |
| Cross-links (student ↔ group ↔ teacher) | ✅ Phase 14 |
| Quick add header → create forms | ✅ Phase 15 |

Regression checklist: `docs/15-phase15-verification.md`

---

## Next step

**Maintenance / handoff** — use Phase 15 checklist before demos. No further planned phases in the 0–15 roadmap.
