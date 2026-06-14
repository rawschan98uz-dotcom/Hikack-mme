# Phase 3 Verification Checklist — Leads

**Phase:** Leads  
**Date:** 2026-06-10

## Files changed

| File | What changed |
|------|----------------|
| `app/backend/api/v1/views.py` | GET filters, POST create, GET/PATCH detail, POST archive |
| `app/backend/api/v1/urls.py` | `/leads/:id`, `/leads/:id/archive` |
| `app/frontend/src/views/LeadsView.vue` | Filters, table, add/edit drawer, archive/restore |

---

## Before testing

Restart backend if it was running. Open http://localhost:5173/leads (logged in).

Seed has **5 active leads** in different stages.

---

## 1. List

| Check | Expected |
|-------|----------|
| Open Leads | Table with 5 rows |
| Columns | Name, Phone, Stage, Status |
| All show **Active** green badge | yes |

---

## 2. Filters

| Action | Expected |
|--------|----------|
| Click **Incoming** stage pill | Only incoming leads (1 row: Aziza) |
| Click **Paid** | Only Rustam Erkinov |
| Click **All stages** | All 5 again |
| Search `Aziza` | 1 row |
| Clear search | All active leads |
| View → **Archived** | Empty (until you archive one) |
| View → **All** | Active + archived |
| **Hide filters** / **Show filters** | Panel toggles |

URL should update with `?stage=` and `?q=` when filtering.

---

## 3. Add lead

| Step | Expected |
|------|----------|
| Click **+ Add lead** | Right drawer opens |
| Empty name → Create | Error "Enter lead name" |
| Fill name, phone, stage → **Create lead** | Drawer closes, new row in table |
| Quick add (header **+** → Lead) | Navigates to `/leads` — click Add lead there |

Example:
- Name: `Test Lead`
- Phone: `901234567`
- Stage: Waiting

---

## 4. Edit lead (click row)

| Step | Expected |
|------|----------|
| Click any row | Drawer opens with **Lead details** |
| Change stage → **Save changes** | Table updates |
| Created date shown | yes |

---

## 5. Archive & restore

| Step | Expected |
|------|----------|
| Open lead → **Archive** | Drawer closes, lead gone from Active view |
| View → **Archived** | Lead appears with grey Archived badge |
| Click archived lead → **Restore** | Back in Active view |

---

## 6. Navigation from dashboard

| From | Expected |
|------|----------|
| Dashboard card **Active leads** | `/leads` with 5 leads |

---

## API (DevTools → Network)

| Request | When |
|---------|------|
| GET `/v1/leads` | List load |
| GET `/v1/leads?stage=paid` | Stage filter |
| POST `/v1/leads` | Create |
| PATCH `/v1/leads/:id` | Edit / restore |
| POST `/v1/leads/:id/archive` | Archive |

---

## Not in Phase 3 (expected)

- Separate full-page lead profile URL
- Lead sources / sections (ModMe extras)
- Convert lead → student

---

## Pass criteria

Create, filter, edit, archive, and restore all work without console errors.
