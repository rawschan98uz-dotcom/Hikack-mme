# Tech Context

## Backend
- Python 3, Django, DRF, SimpleJWT
- SQLite (`app/backend/db.sqlite3`)
- API prefix: `/v1/` — see `app/backend/api/v1/urls.py`
- Envelope: `{ status, success, data, message }`

## Frontend
- Vue 3, Vue Router, Pinia, Axios, Tailwind
- Dev: `npm run dev` → :5173, proxies `/v1` to :8000
- Auth token: `localStorage.access_token`

## Commands
```powershell
cd app/backend && python manage.py migrate && python manage.py seed_demo && python manage.py runserver
cd app/frontend && npm run dev
```

## Reference assets
- Live capture: `captured/sections/sections-report.json`
- ModMe clone backend ref: `references/modme_clone/`
