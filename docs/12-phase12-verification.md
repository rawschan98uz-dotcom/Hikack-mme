# Phase 12 Verification Checklist — Reports

**Phase:** Reports (conversion, leads, left students, workly)  
**Date:** 2026-06-10

## Files changed

| File | What changed |
|------|----------------|
| `app/backend/operations/models.py` | `WorklyRecord` model |
| `app/backend/operations/migrations/0003_*.py` | Migration |
| `app/backend/api/v1/views_extended.py` | Enhanced conversion/leads; left-students + workly APIs |
| `app/backend/api/v1/urls.py` | New report routes |
| `app/frontend/src/views/ReportsConversionView.vue` | Filters + pipeline checkmarks |
| `app/frontend/src/views/ReportsLeadsView.vue` | Filters + leads table |
| `app/frontend/src/views/ReportsLeftStudentsView.vue` | New page (replaces placeholder) |
| `app/frontend/src/views/ReportsWorklyView.vue` | New page (replaces placeholder) |
| `app/frontend/src/router/index.ts` | Wired routes |
| `app/backend/accounts/management/commands/seed_demo.py` | 3 workly records |

---

## Before testing

Restart backend. Run: `python manage.py migrate`  
Optional: `python manage.py seed_demo`

Seed:
- **Left students:** Malika (left active), Timur (left trial)
- **Workly:** 3 records (Kamola at work, Sherzod late, director)
- **Conversion/Leads:** 5 demo leads across all stages

---

## 1. Conversion — `/reports/conversion`

| Check | Expected |
|-------|----------|
| Pipeline cards | 5 stages with counts (1 each in seed) |
| Table | Leads with ✓ through current stage |
| Filters (dates, search) + **Apply** | Rows filtered |

---

## 2. Leads reports — `/reports/leads`

| Check | Expected |
|-------|----------|
| Summary cards | Total 5, Active 5 |
| By stage breakdown | 1 per stage |
| Table | 5 leads with stage + date |
| Stage filter + **Apply** | Filtered rows |
| **All leads →** | Navigates to `/leads` |

---

## 3. Attendance reports — `/reports/attendance`

| Check | Expected |
|-------|----------|
| Still works | Phase 9 CRUD unchanged |

---

## 4. Left students — `/reports/left-students`

| Check | Expected |
|-------|----------|
| Not placeholder | Real page |
| Summary | Total 2, Left active 1, Left trial 1 |
| Table | Malika + Timur |
| Status filter → Left active group | Malika only |
| Status filter → Left after trial | Timur only |
| Dashboard **Left active group** card | `/students?statuses=8` (StudentsView) |

Note: `/left-students` in Settings flyout stays placeholder until Phase 13.

---

## 5. Workly Report — `/reports/workly`

| Check | Expected |
|-------|----------|
| Not placeholder | Real page |
| Summary | 3 total, 2 at work, 1 late |
| Tabs All / At work / Late in | Filter table |
| **+ Add record** | Drawer → Create |
| Click row → Edit / Delete | CRUD works |

---

## API (DevTools)

| Endpoint | Methods |
|----------|---------|
| `/v1/reports/conversion` | GET |
| `/v1/reports/leads` | GET |
| `/v1/reports/left-students` | GET |
| `/v1/reports/workly` | GET, POST |
| `/v1/reports/workly/:id` | GET, PATCH, DELETE |

---

## Pass criteria

No placeholders in Reports flyout; conversion/leads enhanced; left-students + workly functional.
