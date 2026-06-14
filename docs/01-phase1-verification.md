# Phase 1 Verification Checklist

**Phase:** Auth & shell  
**Date:** 2026-06-10

## Files changed

| File | What changed |
|------|----------------|
| `app/frontend/src/api/client.ts` | 401 interceptor → logout + redirect to login |
| `app/frontend/src/stores/auth.ts` | `syncTokenFromStorage()` helper |
| `app/frontend/src/router/index.ts` | Unknown routes → redirect to dashboard |
| `app/frontend/src/layouts/AppLayout.vue` | Header/footer wiring, quick add menu |
| `app/frontend/src/views/StudentsView.vue` | Client search filter via `?q=` query |

---

## 1. Login & logout

| Step | Where | Expected |
|------|-------|----------|
| Open app logged out | http://localhost:5173/ | Redirect to `/login` |
| Wrong password | Login form | Error message, stay on login |
| Correct login | Phone `903708242`, password from README | Redirect to `/dashboard/default` |
| Already logged in | Open `/login` while logged in | Redirect to dashboard |
| Logout | Header → avatar/name (right) | Back to `/login`, token cleared |

---

## 2. Invalid / expired token

| Step | Where | Expected |
|------|-------|----------|
| Simulate bad token | DevTools → Application → Local Storage → set `access_token` to `invalid` → refresh any page | Redirect to `/login` |
| After redirect | Login again | App works normally |

---

## 3. Primary sidebar (11 icons)

Click each icon left sidebar. **Flyout should close** when leaving Finance/Reports/Settings.

| Icon | URL after click | Flyout |
|------|-----------------|--------|
| Leads | `/leads` | hidden |
| Teachers | `/teachers` | hidden |
| Groups | `/groups` | hidden |
| Students | `/students` | hidden |
| Reminders | `/reminders` | hidden |
| Rating | `/rating` | hidden |
| Attendance reports | `/attendance-reports` | hidden |
| Teacher attendance | `/teacher-attendance-reports` | hidden (placeholder page OK) |
| Finance | `/finance/payments` | **visible** — first item All payments |
| Reports | `/reports/conversion` | **visible** |
| Settings | `/auto-sms` | **visible** — first item SMS settings |

**Active state:** clicked icon = orange bar + orange ring.

---

## 4. Finance flyout (5 links)

Settings sidebar closed. Click **Finance**, then each link:

| Link | URL | Finance icon active? | Students icon NOT active? |
|------|-----|----------------------|---------------------------|
| All payments | `/finance/payments` | yes | yes |
| Withdraw | `/finance/withdraw` | yes | — |
| Total Expenses | `/finance/cost` | yes | — |
| Salaries new | `/finance/new-salaries` | yes | — |
| Debtors | `/students/debtors` | **yes** | **no** (Finance active, not Students) |

---

## 5. Reports flyout (5 links)

| Link | URL |
|------|-----|
| Conversion reports | `/reports/conversion` |
| Attendance reports | `/reports/attendance` |
| Leads reports | `/reports/leads` |
| Students left the group | `/reports/left-students` (placeholder) |
| Workly Report | `/reports/workly` (placeholder) |

Reports icon stays orange for all above.

---

## 6. Settings flyout (all links)

Click **Settings**, then every item:

| Link | URL |
|------|-----|
| SMS settings | `/auto-sms` |
| VoIP settings | `/admin/voip` |
| Grade | `/settings-grade` |
| General settings | `/settings` |
| Staff | `/staff/list` |
| Billing | `/billing` |
| Roadmap | `/roadmap` |
| Courses | `/courses` |
| Rooms | `/rooms` |
| Holidays | `/holiday` |
| Archive | `/archive/list` |
| Students left the group | `/left-students` |
| Forms | `/form` |
| Tags | `/tags` |
| What's new | `/blog/news` |
| Sent SMS log | `/sms` |
| Call log | `/call` |
| Logs | `/history/logs` |

Each flyout item highlights orange when active.

---

## 7. Header actions

| Control | Where | Expected |
|---------|-------|----------|
| **RavvaTech** (company name) | Top left | Go to `/dashboard/default`, flyout closes |
| **+** Quick add | Next to name | Dropdown: Lead, Teacher, Group, Student, Course, Reminder |
| Quick add → Lead | Dropdown | Navigate to `/leads`, menu closes |
| Quick add → Course | Dropdown | Navigate to `/courses` |
| Click outside dropdown | Anywhere | Menu closes |
| **Search** | Center | Type `Sardor` → Enter → `/students?q=Sardor`, filtered table |
| **en / ru / uz** | Header | Cycles on click, saved in localStorage (UI label only) |
| **Layout** | Header | Disabled, greyed — "coming soon" |
| **Fullscreen** | Header | Toggles browser fullscreen |
| **?** Help | Header | Opens https://modme.uz/support in new tab |
| **Reminders icon** | Header | Go to `/reminders` |
| **Notifications bell** | Header | Disabled — coming soon |

---

## 8. Footer

| Link | Expected |
|------|----------|
| Support | Opens Telegram https://t.me/modme_support |
| Video tutorials | Opens https://modme.uz/support/video-courses |
| Payment mode | Shows label from company (e.g. Daily) |

---

## 9. 404 / unknown URL

| Step | Expected |
|------|----------|
| While logged in, open http://localhost:5173/this-does-not-exist | Redirect to `/dashboard/default` |

---

## Not in Phase 1 (expected unchanged)

- ADD NEW buttons on list pages — still unwired (Phase 3+)
- Course card click — no detail page yet
- Placeholder pages content — still stub text
- Language switch — label only, no translation yet
- Notifications — disabled

---

## Pass criteria

Phase 1 complete if all sections 1–9 work without console errors.
