# Phase 5 Verification Checklist — Groups

**Phase:** Groups  
**Date:** 2026-06-10

## Also in this release

- Removed platform license banner (Teachers page)
- Removed **Billing** from sidebar and routes (one-time purchase model)

## Files changed

| File | What changed |
|------|----------------|
| `app/backend/api/v1/views.py` | Groups POST, GET/PATCH/DELETE detail, filters |
| `app/backend/api/v1/urls.py` | `/groups/:id` |
| `app/frontend/src/views/GroupsView.vue` | List, filters, create/edit drawer, students in detail |
| `app/frontend/src/views/TeachersView.vue` | License banner removed |
| `app/frontend/src/config/navigation.ts` | Billing link removed |
| `app/frontend/src/router/index.ts` | `/billing` routes removed |

---

## Before testing

Restart backend. Open http://localhost:5173/groups  
Seed has **2 groups**: English-1, English-2.

---

## 1. License / billing removed

| Check | Expected |
|-------|----------|
| `/teachers` | No orange license banner |
| Settings sidebar | No **Billing** item |
| `/billing` | Redirects to dashboard (404 handler) |

---

## 2. List

| Check | Expected |
|-------|----------|
| Table loads | English-1, English-2 |
| Columns | Group, course, branch, teacher, schedule, time, students, status |
| English-1 | Nilufar, Mon/Wed/Fri, ~5 students |
| English-2 | Jamshid or —, Tue/Thu/Sat |

---

## 3. Filters

| Action | Expected |
|--------|----------|
| Branch → Main branch | Only main-branch groups |
| Status → Active | Active groups only |
| Search `English` | Both groups |
| **Apply** | Table updates |

---

## 4. Create group

| Step | Expected |
|------|----------|
| **+ New group** | Drawer opens |
| Fill name, branch, course, teacher, times → **Create** | New row in table |

Example: `English-3`, Main branch, English A1, Jamshid

---

## 5. Group detail

| Step | Expected |
|------|----------|
| Click row **English-1** | Drawer with readonly fields |
| Students block | Lists students from seed |
| **All students →** | `/students` |

---

## 6. Edit group

| Step | Expected |
|------|----------|
| Open group → **Edit** | Fields editable |
| Change teacher or time → **Save** | Table updates |

---

## 7. Delete group

| Step | Expected |
|------|----------|
| Open empty group → **Delete** → confirm | Row removed |

Use a group you created (not English-1 if it has students you need).

---

## API (DevTools)

| Request | When |
|---------|------|
| GET `/v1/groups` | List + filters |
| POST `/v1/groups` | Create |
| GET `/v1/groups/:id` | Detail + students |
| PATCH `/v1/groups/:id` | Edit |
| DELETE `/v1/groups/:id` | Delete |

---

## Pass criteria

No license banner, no billing nav, groups CRUD and detail with students list work.
