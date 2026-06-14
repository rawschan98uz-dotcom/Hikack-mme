# Phase 2 Verification Checklist — Dashboard

**Phase:** Dashboard  
**Date:** 2026-06-10

## Files changed

| File | What changed |
|------|----------------|
| `app/backend/api/v1/views.py` | Dashboard API: finance chart, schedule, reminders |
| `app/backend/api/v1/views_misc.py` | POST create reminder, POST complete reminder |
| `app/backend/api/v1/urls.py` | Route `POST /reminders/:id/complete` |
| `app/frontend/src/views/DashboardView.vue` | Full dashboard UI |
| `app/backend/accounts/management/commands/seed_demo.py` | Second group English-2 (even days) |

---

## Before testing

1. Restart backend (if it was running before API changes).
2. Run: `python manage.py seed_demo`
3. Open http://localhost:5173/dashboard/default (logged in).

---

## 1. Metric cards (8 cards)

Each card is **clickable** and opens the correct list.

| Card | Click → URL | Expected count (seed) |
|------|-------------|------------------------|
| Active leads | `/leads` | 5 |
| Active students | `/students?statuses=5` | 1 |
| Groups | `/groups` | 2 |
| Debtors | `/students/debtors` | 1 |
| In a trial lesson | `/students?statuses=1` | 1 |
| Paid during the month | `/students?finance=paid_during_the_month` | 1 |
| Left active group | `/students?statuses=8` | 1 |
| Left after trial period | `/students?statuses=7` | 1 |

**Check:** hover shows border highlight; numbers are not zero for most cards.

---

## 2. Top action buttons

| Button | Expected |
|--------|----------|
| **Pay** | → `/finance/payments` |
| **Create reminder** | Opens modal form |

---

## 3. Finance chart (left block)

| Check | Expected |
|-------|----------|
| Block title | "Finance" |
| Bars | 1–2 orange bars (seed has 2 payments) |
| Amount labels | e.g. 500 000, 250 000 UZS scale |
| **All payments →** | → `/finance/payments` |

---

## 4. Schedule (right block)

| Tab | Expected |
|-----|----------|
| **Odd days** | Group **English-1**, time 14:00 – 15:30 |
| **Even days** | Group **English-2**, time 16:00 – 17:30 |
| **Other** | Empty state "No groups for this schedule type" |
| Click a group row | → `/groups` |

---

## 5. Reminders block

| Check | Expected |
|-------|----------|
| List | At least 2 items (overdue + today from seed) |
| Click item | Orange border — selected |
| **Task done** | Selected reminder disappears after click, list reloads |
| **More →** | → `/reminders` |
| **More** (bottom button) | → `/reminders` |

---

## 6. Create reminder modal

| Step | Expected |
|------|----------|
| Click **Create reminder** | Modal opens |
| Empty title + Create | Error "Enter a title" |
| Fill title, click **Create** | Modal closes, new item in reminders list |
| Click **Cancel** | Modal closes without saving |
| Click **Reset** | Form fields cleared |
| Click backdrop | Modal closes |

---

## 7. Task result panel

| Check | Expected |
|-------|----------|
| No selection | "Select a reminder to mark it done." |
| Select reminder | Shows "Selected: [title]" |

---

## 8. API (optional DevTools → Network)

| Request | When | Status |
|---------|------|--------|
| GET `/v1/dashboard` | Page load | 200, body includes `finance_chart`, `schedule`, `reminders` |
| POST `/v1/reminders` | Create reminder | 201 |
| POST `/v1/reminders/:id/complete` | Task done | 200 |

---

## Not in Phase 2 (expected)

- Full reminders CRUD on `/reminders` page (ADD NEW still unwired — Phase 7)
- Real-time websocket updates
- Blog widget on dashboard

---

## Pass criteria

Dashboard loads without errors; all 8 cards navigate correctly; schedule tabs filter groups; finance chart shows data; create + complete reminder work.
