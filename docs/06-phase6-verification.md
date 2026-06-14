# Phase 6 Verification Checklist — Students

**Phase:** Students  
**Date:** 2026-06-10

## Files changed

| File | What changed |
|------|----------------|
| `app/backend/api/v1/views.py` | Students POST, GET/PATCH/DELETE detail, search + filters |
| `app/backend/api/v1/urls.py` | `/students/:id` |
| `app/frontend/src/views/StudentsView.vue` | CRUD drawer, filters, row click, dashboard route support |

---

## Before testing

Restart backend. Open http://localhost:5173/students  
Seed has **5 students** (mixed statuses, 1 debtor).

---

## 1. List

| Check | Expected |
|-------|----------|
| Table loads | 5 rows |
| Columns | Name, phone, status, group, branch, balance, paid this month |
| Bobur Nazarov | Status **Debtor**, negative balance |

---

## 2. Dashboard deep links

| Link from dashboard | Expected |
|---------------------|----------|
| Active students card | `/students?statuses=5` — only active |
| Debtors card | `/students/debtors` — only debtors |
| Trial card | `/students?statuses=1` |
| Paid during month | `/students?finance=paid_during_the_month` |
| Header search `?q=Sardor` | Filtered list |

---

## 3. Filters (main `/students`)

| Action | Expected |
|--------|----------|
| Branch → Main branch | Filtered rows |
| Group → English-1 | Students in that group |
| Status → Debtor | Only debtors |
| Search `Bobur` → **Apply** | One row |
| URL updates with query params | Yes |

---

## 4. Add student

| Step | Expected |
|------|----------|
| **+ Add student** | Drawer opens |
| Fill first name, phone, branch, group → **Create** | New row in table |

Example: `Test`, `901009999`, Main branch, English-2

---

## 5. Student detail

| Step | Expected |
|------|----------|
| Click **Sardor Rahimov** | Drawer with readonly fields |
| Group block | English-1 + **Open groups →** |

---

## 6. Edit student

| Step | Expected |
|------|----------|
| Open student → **Edit** | Fields editable |
| Change status to Active → **Save** | Table updates |

---

## 7. Delete student

| Step | Expected |
|------|----------|
| Open test student → **Delete** → confirm | Row removed |

---

## API (DevTools)

| Request | When |
|---------|------|
| GET `/v1/students` | List + filters |
| POST `/v1/students` | Create |
| GET `/v1/students/:id` | Detail |
| PATCH `/v1/students/:id` | Edit |
| DELETE `/v1/students/:id` | Delete |

---

## Pass criteria

Create, edit, delete, filters, dashboard links, and detail drawer all work.
