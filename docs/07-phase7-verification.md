# Phase 7 Verification Checklist — Reminders

**Phase:** Reminders  
**Date:** 2026-06-10

## Files changed

| File | What changed |
|------|----------------|
| `app/backend/api/v1/views_misc.py` | Detail GET/PATCH/DELETE, timezone fix, assignee |
| `app/backend/api/v1/urls.py` | `/reminders/:id` |
| `app/frontend/src/views/RemindersView.vue` | Tabs, CRUD drawer, Task done |
| `app/backend/accounts/management/commands/seed_demo.py` | Future reminder for demo |

---

## Before testing

Restart backend. Optional: `python manage.py seed_demo` (adds future reminder).  
Open http://localhost:5173/reminders

Seed tabs: **Overdue (1)**, **Today (1)**, **Future (1)** after re-seed.

---

## 1. Tabs

| Tab | Expected |
|-----|----------|
| Overdue | "Send payment reminder" |
| Today | "Call new lead Aziza" |
| Future | "Prepare monthly report" (after re-seed) |
| Counts in tab labels | Match row counts |

---

## 2. ADD NEW

| Step | Expected |
|------|----------|
| **ADD NEW** | Drawer opens |
| Title empty → Create | Error |
| Fill title, date, assignee → **Create** | Appears in correct tab (today/future/overdue) |

---

## 3. Detail drawer

| Step | Expected |
|------|----------|
| Click any row | Drawer with title, details, date, assignee, status badge |
| Fields readonly initially | Yes |

---

## 4. Edit

| Step | Expected |
|------|----------|
| **Edit** | Fields editable |
| Change title or due date → **Save** | Table updates, tab may change if date moved |

---

## 5. Task done

| Step | Expected |
|------|----------|
| Open reminder → **Task done** | Reminder disappears from all tabs |
| Dashboard reminders block | Also updated after refresh |

---

## 6. Delete

| Step | Expected |
|------|----------|
| Open reminder → **Delete** → confirm | Row removed |

---

## 7. Dashboard integration

| Step | Expected |
|------|----------|
| Dashboard → **Create reminder** | Still works (POST `/reminders`) |
| Dashboard → **Task done** | Completes selected reminder |
| Dashboard → **More →** | `/reminders` |

---

## API (DevTools)

| Request | When |
|---------|------|
| GET `/v1/reminders` | List + buckets |
| POST `/v1/reminders` | Create |
| GET `/v1/reminders/:id` | Detail |
| PATCH `/v1/reminders/:id` | Edit |
| DELETE `/v1/reminders/:id` | Delete |
| POST `/v1/reminders/:id/complete` | Task done |

---

## Pass criteria

Tabs, create, edit, complete, delete, assignee — all work. No timezone error on create.
