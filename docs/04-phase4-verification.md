# Phase 4 Verification Checklist — Teachers

**Phase:** Teachers  
**Date:** 2026-06-10

## Files changed

| File | What changed |
|------|----------------|
| `app/backend/api/v1/views_extended.py` | GET/PATCH/DELETE teacher detail, groups in profile |
| `app/backend/api/v1/urls.py` | `/user/teacher/:id` → detail view |
| `app/frontend/src/views/TeachersView.vue` | Edit, profile drawer, SMS link |

---

## Before testing

Restart backend. Open http://localhost:5173/teachers  
Seed has **2 teachers**: Nilufar Karimova, Jamshid Rakhimov.

---

## 1. List

| Check | Expected |
|-------|----------|
| Quantity | 2 |
| Each card | name, phone, groups count |
| Nilufar | 1 group (English-1) |
| Jamshid | 0 groups |

---

## 2. Add teacher

| Step | Expected |
|------|----------|
| **ADD NEW** | Modal opens |
| Without password | Error |
| Fill form + password + branch → **Create** | New card appears, quantity +1 |

Example phone: `901005555` (must be unique)

---

## 3. Edit teacher

| Step | Expected |
|------|----------|
| Menu (⋮) → **Edit** | Modal with filled data |
| Change last name → **Save** | Card updates |
| No error "Edit is not available yet" | — |

Or: click card → profile → **Edit teacher**

---

## 4. Branches on edit

| Step | Expected |
|------|----------|
| Edit teacher → toggle **Branch 2** on | Save |
| Open profile | Branches shows both |

---

## 5. Profile drawer

| Step | Expected |
|------|----------|
| Click teacher card (not menu) | Profile drawer opens |
| Nilufar profile | Shows **English-1** group with course/branch/days |
| Jamshid profile | "No groups assigned" |
| **All groups →** | → `/groups` |
| **SMS log** | → `/sms` |

---

## 6. Delete

| Step | Expected |
|------|----------|
| Menu → **Delete** → confirm | Teacher removed, quantity -1 |

---

## 7. Import button

Disabled, greyed — "Import coming soon" on hover.

---

## API (DevTools)

| Request | When |
|---------|------|
| GET `/v1/user?user_type=teacher` | List |
| POST `/v1/user/teacher` | Create |
| GET `/v1/user/teacher/:id` | Profile |
| PATCH `/v1/user/teacher/:id` | Edit |
| DELETE `/v1/user/teacher/:id` | Delete |

---

## Pass criteria

Create, edit, delete, profile with groups — all work.
