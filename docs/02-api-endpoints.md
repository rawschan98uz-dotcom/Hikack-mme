# ModMe API Endpoints (Captured + Documented)

Base URL: `https://api.modme.uz`

## Authentication

| Method | Endpoint | Notes |
|--------|----------|-------|
| POST | `/v1/auth/login` | Phone + password login |
| POST | `/v1/auth/me` | Current user after login |
| GET | `/v2/token/me` | Validate personal access token |
| POST | `/v1/broadcasting/auth` | WebSocket channel auth (Laravel) |

## Company / Tenant

| Method | Endpoint | Notes |
|--------|----------|-------|
| GET | `/v1/company/subdomain/{subdomain}` | Resolve tenant by subdomain |
| GET | `/v1/company/{id}` | Company details |
| POST | `/v1/company/openDemoCompany` | Create demo tenant (public) |

## Dashboard

| Method | Endpoint | Notes |
|--------|----------|-------|
| GET | `/v1/dashboard` | Main dashboard metrics |
| GET | `/v1/branch` | List branches |
| GET | `/v1/schedule` | Schedule data |
| GET | `/v1/replenishments/debit_char` | Finance chart data |
| GET | `/v1/blog/` | News/updates |
| POST | `/v2/reminder/index` | Reminders list |

## Documented in `references/docs.modme.uz`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v2/branches` | Branch list |
| GET | `/v2/groups` | Groups with course (`branch_id`, `page`, `per_page`) |
| GET | `/v2/attendances` | Attendance (`branch_id`, `group_id`, `from`, `to`) |
| — | Leads API | Columns, sections, save lead (see content/1.methods/0.leads/) |

## Response Format (typical)

```json
{
  "status": 200,
  "success": true,
  "data": [],
  "pagination": {
    "count": 1,
    "total": 340,
    "perPage": 1,
    "currentPage": 1,
    "totalPages": 340
  }
}
```

## Group Model Fields (from API docs)

- `days`: 1=Mon/Wed/Fri, 2=Tue/Thu/Sat, 3=Sat/Sun, 4=Every day, 5=Custom (`exact_days`)
- `status`: 2=Active, 3=Archive
- `course`: nested object with `price`, `lesson_duration`, `course_duration`, `lessons_per_module`

## Auth Header

```
Authorization: Bearer {token}
```

Personal access tokens are created in ModMe settings.
