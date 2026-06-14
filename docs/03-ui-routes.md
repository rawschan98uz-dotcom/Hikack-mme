# ModMe CRM — UI Routes & Navigation

Captured from logged-in tenant `ravvatech188.modme.uz` on 2026-06-10.

## Architecture

- Multi-tenant: each center gets `{name}.modme.uz`
- Login at tenant root `/`, dashboard at `/dashboard/default`
- Vue Router SPA with lazy-loaded chunks

## Sidebar / Main Navigation

| Section | Route | Description |
|---------|-------|-------------|
| Leads | `/leads` | Active leads pipeline |
| Teachers | `/teachers` | Teacher management |
| Groups | `/groups` | Class groups |
| Students | `/students` | Student hub |
| Reminders | `/reminders` | Task reminders |
| Rating | `/rating` | Student ratings |
| Attendance reports | `/attendance-reports` | Student attendance |
| Teacher attendance | `/teacher-attendance-reports` | Staff attendance |

## Finance

| Route | Description |
|-------|-------------|
| `/finance/payments` | All payments |
| `/finance/withdraw` | Withdrawals |
| `/finance/cost` | Total expenses |
| `/finance/new-salaries` | Salary calculation |
| `/students/debtors` | Debtors list |
| `/billing` | Platform billing |

## Reports

| Route | Description |
|-------|-------------|
| `/reports/conversion` | Conversion reports |
| `/reports/attendance` | Attendance reports |
| `/reports/leads` | Leads reports |
| `/reports/left-students` | Students who left |
| `/reports/workly` | Workly integration report |

## Settings & Admin

| Route | Description |
|-------|-------------|
| `/settings` | General settings |
| `/settings-grade` | Grading system |
| `/staff/list` | Staff management |
| `/courses` | Courses |
| `/rooms` | Rooms |
| `/holiday` | Holidays |
| `/archive/list` | Archive |
| `/tags` | Tags |
| `/form` | Lead forms |
| `/auto-sms` | SMS automation |
| `/admin/voip` | VoIP settings |
| `/sms` | Sent SMS log |
| `/call` | Call log |
| `/history/logs` | Activity logs |
| `/roadmap` | Product roadmap |
| `/blog/news` | What's new |

## Student Filters (dashboard widgets)

| Widget | Route |
|--------|-------|
| Active students | `/students/list?statuses=5` |
| Trial lesson | `/students/list?statuses=1` |
| Paid this month | `/students/list?finance=paid_during_the_month` |
| Left active group | `/left-students?statuses=left_active_group` |
| Left after trial | `/left-students?statuses=left_after_trial` |

## Dashboard Widgets (default page)

Eight metric cards:
1. Active leads
2. Active students
3. Groups
4. Debtors
5. In trial lesson
6. Paid during the month
7. Left active group
8. Left after trial period

Plus: finance chart area, schedule section (Odd/Even/Other days tabs).

## Lazy-loaded JS Chunks (from bundle)

See `captured/frontend-routes.json` for full extracted list.

Notable chunks: `admin`, `attendance`, `dashboards`, `debtors`, `students`, `teachers`, `roomsList`, `ReportsLeadsStatistic`, `ReportsLeftStudents`, `ReportsSkipClasses`
