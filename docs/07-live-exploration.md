# Live ModMe Exploration (ravvatech188)

Captured with user credentials on 2026-06-10.

## Where files are

- Screenshots: `captured/sections/*.png`
- Structured report: `captured/sections/sections-report.json`
- Per-section API calls listed in report

## Key API endpoints discovered per section

### Leads (`/leads`)
- `GET /v1/leadSection`
- `GET /v1/leadSource`
- `GET /v1/leads/archive-reason`
- `GET /v1/tags`
- `GET /v1/user`
- `GET /v1/course`

### Teachers (`/teachers/list`)
- `GET /v1/user` (filtered teachers)

### Groups (`/groups/list`)
- Group list endpoints (see report)

### Students
- Student list with status filters

### Finance
- Payments, withdraw, expenses, salaries sections

## Clone implementation status

| Section | Clone status |
|---------|--------------|
| Dashboard | Done |
| Leads | Done (+ pipeline stage) |
| Groups | Done |
| Students | Done |
| Courses | Done |
| Teachers | Done (`/v1/user?user_type=teacher`) |
| Finance → Payments | Done (`/v1/replenishments`) |
| Finance → Withdraw | Done (`/v1/withdraws`) |
| Finance → Expenses | Done (`/v1/expense`) |
| Finance → Salaries | Done (`/v1/salary-settings`) |
| Reports → Conversion | Done |
| Reports → Attendance | Done |
| Reports → Leads | Done |
| Settings | Done (general tab + save) |
| Reminders, Rooms, SMS… | TODO (screenshots available) |

Use screenshots side-by-side with localhost when implementing remaining pages.
