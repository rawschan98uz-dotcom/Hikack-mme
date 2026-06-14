# Phase 11 Verification Checklist — Finance

**Phase:** Finance (payments, withdrawals, expenses, salaries)  
**Date:** 2026-06-10

## Files changed

| File | What changed |
|------|----------------|
| `app/backend/api/v1/views_extended.py` | Full CRUD for payments, withdrawals, expenses, salary settings |
| `app/backend/api/v1/urls.py` | Detail routes for finance endpoints |
| `app/frontend/src/views/FinancePaymentsView.vue` | Filters, table, create/edit/delete drawer |
| `app/frontend/src/views/FinanceWithdrawView.vue` | Filters, table, create/edit/delete drawer |
| `app/frontend/src/views/FinanceExpensesView.vue` | Categories, filters, CRUD drawer |
| `app/frontend/src/views/FinanceSalariesView.vue` | Search, CRUD drawer |
| `app/backend/accounts/management/commands/seed_demo.py` | Salary seed: Nilufar Karimova / English-1 |

---

## Before testing

Restart backend.  
Optional: `python manage.py seed_demo`  
Login: phone `903708242` — see `app/README.md`

Seed data:
- **Payments:** 2 rows
- **Withdrawals:** 1 row
- **Expenses:** 1 row
- **Salary settings:** 1 row (Nilufar Karimova)

---

## 1. Payments — `/finance/payments`

| Check | Expected |
|-------|----------|
| Page loads | Table with demo payments |
| Filters (dates, method, search) + **Apply** | Rows filtered |
| **+ Add payment** | Drawer opens |
| Fill student, amount, method → **Create** | New row in table |
| Click row | Detail drawer (read-only) |
| **Edit** → change amount/comment → **Save** | Updated |
| **Delete** → confirm | Row removed |

---

## 2. Withdrawals — `/finance/withdraw`

| Check | Expected |
|-------|----------|
| Page loads | 1 demo withdrawal |
| Filters + **Apply** | Works |
| **+ Add withdrawal** | Drawer |
| Create / Edit / Delete | Same pattern as payments |

---

## 3. Expenses — `/finance/cost`

| Check | Expected |
|-------|----------|
| Page loads | 1 demo expense |
| Category filter | Uses `/expense_types` categories |
| **New expense** | Drawer with category, description, payee, method, amount |
| Create / Edit / Delete | Full CRUD |

---

## 4. Salaries — `/finance/new-salaries`

| Check | Expected |
|-------|----------|
| Page loads | Nilufar Karimova row |
| Search + **Apply** | Filters by teacher/course/group |
| **+ Add setting** | Drawer |
| Fields: teacher, salary type (fixed/percent/per student), amount, course, group | |
| Create / Edit / Delete | Full CRUD |

---

## 5. Dashboard link

| Action | Expected |
|--------|----------|
| Dashboard **Pay** button | Opens `/finance/payments` (student payments, not billing) |

---

## API (DevTools)

| Endpoint | Methods |
|----------|---------|
| `/v1/replenishments` | GET, POST |
| `/v1/replenishments/:id` | GET, PATCH, DELETE |
| `/v1/withdraws` | GET, POST |
| `/v1/withdraws/:id` | GET, PATCH, DELETE |
| `/v1/expense` | GET, POST |
| `/v1/expense/:id` | GET, PATCH, DELETE |
| `/v1/expense_types` | GET |
| `/v1/salary-settings` | GET, POST |
| `/v1/salary-settings/:id` | GET, PATCH, DELETE |

List filters: `date_from`, `date_to`, `q`; also `method` (payments), `category_id` (expenses).

---

## Pass criteria

All four finance pages have working CRUD drawers, filters, and no unwired primary buttons.
