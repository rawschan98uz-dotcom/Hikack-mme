# Phase 15 Verification Checklist — Final QA

**Phase:** Final QA across all modules  
**Prerequisite:** Backend `:8000`, frontend `:5173`, login `903708242`

---

## 0. Smoke test (automated)

```powershell
cd D:\projects\Hijack-mme\app\backend
$env:DJANGO_SETTINGS_MODULE = "config.settings"
.\.venv\Scripts\python.exe manage.py check
```

Frontend build:

```powershell
cd D:\projects\Hijack-mme\app\frontend
npm run build
```

Both must pass with no errors.

---

## 1. Auth & shell

| Check | Expected |
|-------|----------|
| Login → dashboard | JWT stored, metrics load |
| Logout | Redirect to `/login` |
| Unknown URL | Redirect to dashboard |
| Header search | `/students?q=...` |
| **Quick add (+)** → Lead / Teacher / Group / Student / Course / Reminder | Page opens **with create drawer/modal** |
| Sidebar flyouts | Finance, Reports, Settings links work |
| Footer Support / Video | External modme.uz links |

**Intentionally disabled:** Layout toggle, Notifications bell, Teachers Import.

---

## 2. Core CRM (Phases 3–7)

| Route | List | Create | Edit | Delete |
|-------|------|--------|------|--------|
| `/leads` | ✅ | ✅ | ✅ | Archive |
| `/teachers` | ✅ | ✅ | ✅ | ✅ |
| `/groups` | ✅ | ✅ | ✅ | ✅ |
| `/students` | ✅ | ✅ | ✅ | ✅ |
| `/students/debtors` | ✅ filter | — | — | — |
| `/reminders` | ✅ tabs | ✅ | ✅ | ✅ |

---

## 3. Operations (Phases 8–10)

| Route | Expected |
|-------|----------|
| `/rating` | Table + graph, CRUD |
| `/attendance-reports` | Summary + mark/edit |
| `/reports/attendance` | Same view as above |
| `/teacher-attendance-reports` | Teacher/group attendance CRUD |

---

## 4. Finance (Phase 11)

| Route | Expected |
|-------|----------|
| `/finance/payments` | CRUD + filters |
| `/finance/withdraw` | CRUD |
| `/finance/cost` | Expenses CRUD |
| `/finance/new-salaries` | Salary settings CRUD |
| `/students/debtors` | Debtor filter (Finance menu) |

---

## 5. Reports (Phase 12)

| Route | Expected |
|-------|----------|
| `/reports/conversion` | Pipeline table |
| `/reports/leads` | Stats + table |
| `/reports/attendance` | Attendance report |
| `/reports/left-students` | Summary cards + table |
| `/reports/workly` | Workly CRUD |

---

## 6. Settings (Phase 13)

| Route | Expected |
|-------|----------|
| `/auto-sms` | Save |
| `/admin/voip` | Save |
| `/settings-grade` | Save |
| `/settings` | General save |
| `/staff/list` | CRUD |
| `/courses` | Card grid + edit/delete |
| `/rooms`, `/holiday` | CRUD |
| `/archive/list` | Filters + bulk + CSV |
| `/tags`, `/form` | ModMe tables + CRUD |
| `/roadmap` | Milestones page |
| `/left-students` | Left students (no summary cards) |
| `/blog/news` | **What's new** release notes (not placeholder) |

**Not in Settings menu (by design):** SMS log, Call log, Activity logs — routes exist at `/sms`, `/call`, `/history/logs`.

---

## 7. Cross-links (Phase 14)

| Flow | Expected |
|------|----------|
| Student → group name | `/groups?open=` |
| Group → student name | `/students?open=` |
| Group → teacher | `/teachers?open=` |
| Teacher → group | `/groups?open=` |
| Dashboard schedule row | Group detail |
| Reports drawer links | Correct entity opens |

---

## 8. Seed data sanity

After `python manage.py seed_demo`:

| Entity | Min count |
|--------|-----------|
| Teachers | 2 (Nilufar, Jamshid) |
| Groups | 1+ (English-1) |
| Students | 3+ |
| Leads | 5 |
| Courses | CEFR codes without duplicates |

---

## 9. Known limitations (accepted)

| Item | Status |
|------|--------|
| `/courses/:id` dedicated page | Not implemented — card drawer only |
| Teacher Import | Disabled UI |
| Header layout / notifications | Disabled UI |
| Locale switcher | Cycles en/ru/uz locally only |
| Pixel-perfect ModMe UI | Out of scope |
| Mobile apps | Out of scope |

---

## 10. Zero placeholders

All primary nav routes must show real pages — **no** `PlaceholderView` except none remain.

Hidden log routes (`/sms`, `/call`, `/history/logs`) are read-only log pages, not placeholders.

---

## Project complete

Phases **0–15** implemented. Use this checklist for regression before demos or handoff.
