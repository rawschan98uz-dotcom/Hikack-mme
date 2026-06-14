# Phase 10 Verification Checklist — Teacher attendance reports

**Phase:** Teacher attendance reports  
**Date:** 2026-06-10

## Files changed

| File | What changed |
|------|----------------|
| `app/backend/operations/models.py` | `TeacherAttendanceRecord` model |
| `app/backend/operations/migrations/0002_*.py` | Migration |
| `app/backend/api/v1/views_extended.py` | CRUD API + summary + filters |
| `app/backend/api/v1/urls.py` | `/reports/teacher-attendance` routes |
| `app/frontend/src/views/TeacherAttendanceReportsView.vue` | Full page (replaces placeholder) |
| `app/frontend/src/router/index.ts` | Wired route |
| `app/backend/accounts/management/commands/seed_demo.py` | 2 demo teacher attendance rows |

---

## Before testing

Restart backend. Run: `python manage.py migrate` (if not applied).  
Optional: `python manage.py seed_demo`  
Open http://localhost:5173/teacher-attendance-reports

Seed: **2 records** — Nilufar Present, Jamshid Late.

---

## 1. Page loads (no placeholder)

| Check | Expected |
|-------|----------|
| Title | "Teacher attendance reports" |
| Not placeholder text | Real table + summary |

---

## 2. Summary + table

| Check | Expected |
|-------|----------|
| Total | 2 |
| Present | 1 (Nilufar) |
| Late | 1 (Jamshid) |
| Table columns | Teacher, Group, Branch, Date, Status, Note |

---

## 3. Filters

| Action | Expected |
|--------|----------|
| Teacher → Nilufar | 1 row |
| Group → English-1 | Nilufar row |
| Status → Late | Jamshid row |
| Search `Jamshid` | 1 row |

---

## 4. Mark attendance

| Step | Expected |
|------|----------|
| **+ Mark attendance** | Drawer |
| Teacher + group + date + status + note → **Create** | New row |

---

## 5. Edit / Delete

| Step | Expected |
|------|----------|
| Click row → **Edit** → change status/note → **Save** | Updated |
| **Delete** → confirm | Removed |
| Links **Teachers →** / **Groups →** | Navigate |

---

## API (DevTools)

| Request | When |
|---------|------|
| GET `/v1/reports/teacher-attendance` | List + summary |
| POST `/v1/reports/teacher-attendance` | Create / upsert |
| GET/PATCH/DELETE `/v1/reports/teacher-attendance/:id` | Detail CRUD |

---

## Pass criteria

Placeholder gone; full CRUD + filters + summary work.
