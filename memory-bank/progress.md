# Progress

## Completed

### Phase 0 — Foundation ✅
- [x] 0.1 Backend + frontend run locally
- [x] 0.2 Seed data (incl. fix: 2 demo teachers + group assignment)
- [x] 0.3 Screen → API → status map (`docs/00-phase0-audit.md`)
- [x] 0.4 Placeholder routes classified (implement vs defer)

### Phase 1 — Auth & shell ✅
- [x] 1.1 Login redirect + logged-in guard
- [x] 1.2 Logout
- [x] 1.3–1.5 Sidebar + flyout + highlight (verified via checklist)
- [x] 1.6 Header: search, quick add, locale, help, reminders, fullscreen
- [x] 1.7 Footer: Support + Video tutorials links
- [x] 401 expired token handling
- [x] Unknown route → dashboard

### Phase 2 — Dashboard ✅
- [x] 2.1 GET `/dashboard` — stats + finance chart + schedule + reminders
- [x] 2.2 Buttons: Pay, Create reminder, Task done, More, Cancel, Reset, Create
- [x] 2.3 Schedule tabs + reminders block
- [x] Clickable metric cards → filtered routes

### Phase 3 — Leads ✅
- [x] 3.1 List GET + filters
- [x] 3.2 ADD NEW POST
- [x] 3.3 Edit PATCH + archive

### Phase 4 — Teachers ✅
- [x] 4.1 List GET
- [x] 4.2 ADD NEW POST
- [x] 4.3 Delete
- [x] 4.4 Edit PATCH
- [x] 4.5 Profile drawer + groups

### Phase 5 — Groups ✅
- [x] 5.1 List GET + filters
- [x] 5.2 ADD NEW POST
- [x] 5.3 Detail GET + students
- [x] 5.4 Edit PATCH
- [x] 5.5 Delete
- [x] License banner + Billing removed (one-time purchase)

### Phase 6 — Students ✅
- [x] 6.1 List GET + filters (status, branch, group, q, finance)
- [x] 6.2 ADD NEW POST
- [x] 6.3 Detail GET
- [x] 6.4 Edit PATCH
- [x] 6.5 Delete
- [x] 6.6 Dashboard deep links + debtors route

### Phase 7 — Reminders ✅
- [x] 7.1 Tabs overdue/today/future
- [x] 7.2 ADD NEW POST
- [x] 7.3 Detail GET + edit PATCH
- [x] 7.4 Task done (complete)
- [x] 7.5 Delete
- [x] 7.6 Assignee select

### Phase 8 — Rating ✅
- [x] 8.1 Table GET + filters
- [x] 8.2 Graph tab (bar chart)
- [x] 8.3 Add grade POST
- [x] 8.4 Edit PATCH
- [x] 8.5 Delete + rank recalc

### Phase 9 — Attendance reports ✅
- [x] 9.1 Summary cards (present/absent/late)
- [x] 9.2 Filters (branch, group, status, dates, search)
- [x] 9.3 Mark attendance POST
- [x] 9.4 Edit PATCH / Delete
- [x] 9.5 Both `/attendance-reports` and `/reports/attendance`

### Phase 10 — Teacher attendance ✅
- [x] 10.1 TeacherAttendanceRecord model
- [x] 10.2 GET summary + filters
- [x] 10.3 Mark attendance POST
- [x] 10.4 Edit PATCH / Delete
- [x] 10.5 Replaced PlaceholderView

### Phase 11 — Finance ✅
- [x] 11.1 Payments CRUD + filters
- [x] 11.2 Withdrawals CRUD + filters
- [x] 11.3 Expenses CRUD + category filter
- [x] 11.4 Salary settings CRUD + search
- [x] 11.5 Dashboard Pay → `/finance/payments`

### Phase 12 — Reports ✅
- [x] 12.1 Conversion — filters + pipeline table
- [x] 12.2 Leads reports — filters + table
- [x] 12.3 Left students report (replaced placeholder)
- [x] 12.4 Workly report + CRUD (replaced placeholder)
- [x] 12.5 Attendance reports unchanged (Phase 9)

### Phase 13 — Settings ✅ (revised)
- [x] 13.A VoIP settings page + save
- [x] 13.B Grade settings page + save
- [x] 13.C Auto-SMS save, Staff CRUD
- [x] 13.D Courses edit/delete, Rooms/Holidays/Forms/Tags CRUD
- [x] 13.E `/left-students` wired (same as reports)
- [x] 13.F Logs read-only (SMS, Call, Activity)
- [x] 13.G Archive — ModMe-like filters + bulk actions + reasons
- [x] 13.H Roadmap — milestone page (not placeholder)
- [x] 13.I Courses seed dedupe by code

### Phase 14 — Cross-links ✅
- [x] 14.1 `crossLinks.ts` + `?open=` deep links
- [x] 14.2 Students ↔ Groups ↔ Teachers navigation
- [x] 14.3 Dashboard schedule → group
- [x] 14.4 Reports entity links (rating, attendance, left students)
- [x] 14.5 GET `/groups?teacher_id=`

### Phase 15 — Final QA ✅
- [x] 15.1 Full verification checklist (`docs/15-phase15-verification.md`)
- [x] 15.2 Quick add → create drawer (`?create=1`)
- [x] 15.3 What's new page (`/blog/news`)
- [x] 15.4 Django check + frontend build pass
- [x] 15.5 Audit doc updated — zero PlaceholderView routes

## Project status

**Phases 0–15 complete.** See `docs/15-phase15-verification.md` for regression checklist.

## Known limitations (accepted)

- No `/courses/:id` page (drawer only)
- Teacher Import, header layout/notifications — disabled UI
- Locale switcher is local-only
- Pixel-perfect ModMe parity — out of scope
