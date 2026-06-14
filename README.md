# Hijack-mme

Research archive for building a ModMe CRM clone. Contains public references, captured UI/API intelligence, and documentation.

**This is not the official ModMe source code.**

## Structure

```
Hijack-mme/
├── captured/          # Screenshots, HTML, JS bundles, network logs
├── docs/              # Research notes (start here)
├── references/        # Cloned public repos
│   ├── modme_clone/   # Unofficial Django API clone (MIT)
│   └── docs.modme.uz/ # Official API documentation site source
└── scripts/           # Exploration utilities
```

## Runnable Clone (MVP)

The working localhost app lives in **`app/`**:

```powershell
cd D:\projects\Hijack-mme\app
.\start.ps1
```

Then open http://localhost:5173 — login `903708242` / `50608991Zz!`

See `app/README.md` for details.

## Research Quick Start

1. Read `docs/01-overview.md`
2. Review `docs/02-api-endpoints.md` and `docs/03-ui-routes.md`
3. Use `docs/05-features-checklist.md` as build roadmap
4. Study `references/modme_clone` for Django data models

## Re-run Dashboard Capture

```powershell
# Copy .env.example to .env.local and add your credentials
$env:MODME_PHONE="..."
$env:MODME_PASSWORD="..."
$env:MODME_BASE_URL="https://your-tenant.modme.uz"
node scripts/explore-dashboard.mjs
```

## Key Findings

| Item | Value |
|------|-------|
| API base | `https://api.modme.uz` |
| CRM frontend | Vue.js SPA |
| Marketing site | Next.js at modme.uz |
| Tenant URL | `{subdomain}.modme.uz` |
| Official API docs | `references/docs.modme.uz/content/` |

## Sources

- https://modme.uz/ru
- https://modme.uz/ru/demo
- https://ravvatech188.modme.uz/dashboard/default
- https://modme-crm.gitbook.io/modme-crm
- https://github.com/modme-uz/docs.modme.uz
- https://github.com/akhroruz/modme_clone

## Security

- Never commit `.env` or `.env.local`
- Credentials are for your own tenant only
- `captured/network/` stores endpoint URLs only, not response bodies
