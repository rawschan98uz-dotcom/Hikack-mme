# Phase 9 Verification Checklist — Attendance reports

**Phase:** Attendance reports  
**Date:** 2026-06-10

## Files changed

| File | What changed |
|------|----------------|
| `app/backend/api/v1/views_extended.py` | Attendance GET summary+filters, POST, PATCH/DELETE detail |
| `app/backend/api/v1/urls.py` | `/reports/attendance/:id` |
| `app/frontend/src/views/ReportsAttendanceView.vue` | Summary cards, filters, CRUD drawer |
| `app/backend/accounts/management/commands/seed_demo.py` | Present/Absent/Late demo rows |

Works on both routes: `/attendance-reports` and `/reports/attendance`.

---

## Before testing

Restart backend. Optional: `python manage.py seed_demo`  
Open http://localhost:5173/attendance-reports

Seed: **3 records** — Present, Absent, Late (last 3 days).

---

## 1. Summary cards

| Card | Expected (seed) |
|------|-----------------|
| Total | 3 |
| Present | 1 |
| Absent | 1 |
| Late | 1 |

---

## 2. Table

| Check | Expected |
|-------|----------|
| Rows | 3 students, English-1 |
| Status badges | Green Present, red Absent, amber Late |
| Click row | Detail drawer |

---

## 3. Filters

| Action | Expected |
|--------|----------|
| Status → Absent | 1 row |
| Group → English-1 | 3 rows |
| Date from = today | Today’s record only |
| Search student name → Apply | Filtered rows |
| Summary cards | Update with filters |

---

## 4. Mark attendance

| Step | Expected |
|------|----------|
| **+ Mark attendance** | Drawer |
| Select group, student, date, status → **Create** | New row + summary updates |
| Same student+group+date again | Updates existing (upsert) |

---

## 5. Edit / Delete

| Step | Expected |
|------|----------|
| Open row → **Edit** → change status → **Save** | Table + summary update |
| **Delete** → confirm | Row removed |

---

## 6. Reports route

| URL | Expected |
|-----|----------|
| `/reports/attendance` | Same page, title "Attendance report" |

---

## API (DevTools)

| Request | When |
|---------|------|
| GET `/v1/reports/attendance` | List + summary + filters |
| POST `/v1/reports/attendance` | Create / upsert |
| GET `/v1/reports/attendance/:id` | Detail |
| PATCH `/v1/reports/attendance/:id` | Edit |
| DELETE `/v1/reports/attendance/:id` | Delete |

---

## Pass criteria

Summary, filters, create, edit, delete work on both attendance routes.
