# ModMe CRM — Research Overview

Research archive for building a ModMe-like educational center CRM clone.

## What ModMe Is

- **Product**: Cloud SaaS CRM + LMS for private educational centers (Uzbekistan, expanding internationally)
- **Company**: OOO «MODME», Tashkent
- **Website**: https://modme.uz
- **API**: https://api.modme.uz
- **Tenant model**: `{subdomain}.modme.uz` (e.g. `ravvatech188.modme.uz`)
- **Mobile apps**: ModMe Students App, ModMe Teachers App

## Official Source Code Availability

| Asset | Public? | Location |
|-------|---------|----------|
| Main CRM backend/frontend | No | Proprietary |
| API developer docs (partial) | Yes | `references/docs.modme.uz` |
| User documentation | Yes | GitBook + `references/docs.modme.uz` |
| Community Django clone | Yes | `references/modme_clone` |

## Tech Stack (Observed)

### CRM App (`*.modme.uz`)
- **Frontend**: Vue.js SPA (webpack chunks: `index.*.js`, `chunk-vendors.*.js`)
- **Icons**: simple-line-icons, iconsminds
- **Analytics**: Yandex Metrika, Cloudflare
- **Realtime**: Laravel broadcasting (`/v1/broadcasting/auth`) — likely Laravel Echo + Pusher/WebSockets

### Marketing Site (`modme.uz`)
- **Framework**: Next.js (App Router, React Server Components)
- **Styling**: Tailwind CSS
- **Brand color**: `#ff8000` (orange)

### API
- REST API at `https://api.modme.uz`
- Versions: `v1` (main), `v2` (newer endpoints)
- Auth: Bearer token (session after login) + Personal Access Tokens for integrations

## Payment Modes (`balance_mode`)

From demo form and GitBook documentation:

| Value | RU Name | Description |
|-------|---------|-------------|
| 1 | Ежедневный (By day) | Charge per lesson |
| 2 | Ежемесячный (Calendar) | Full month price on 1st of month |
| 3 | Дата начала группы | Billing on group start date each month |
| 4 | Весь курс | One-time full course payment |
| 5 | Модуль | Charge every N lessons (module) |
| 6 | Индивидуальный | Monthly on student's activation date |

## Demo Registration API

```
POST https://api.modme.uz/v1/company/openDemoCompany
```

Form fields: `first_name`, `name` (center), `phone` (9 digits), `balance_mode`, `password`

## Key Links

- User docs: https://modme-crm.gitbook.io/modme-crm
- API docs repo: https://github.com/modme-uz/docs.modme.uz
- Support Telegram: https://t.me/modme_support
- Student app: `uz.modme.student` (Google Play)
- Teacher app: App Store id6467503409

## Team (from modme.uz/about, useful for understanding scope)

- Backend: Umаров Шохрух, Муроджонов Самандар
- Frontend: Саидакбаров Файзулло
- Product: Бехруз Бердиев
