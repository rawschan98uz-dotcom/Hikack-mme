# Phase 8 Verification Checklist — Rating

**Phase:** Rating  
**Date:** 2026-06-10

## Files changed

| File | What changed |
|------|----------------|
| `app/backend/api/v1/views_misc.py` | Scores POST, detail PATCH/DELETE, filters, rank recalc |
| `app/backend/api/v1/urls.py` | `/scores/:id` |
| `app/frontend/src/views/RatingView.vue` | Table + graph, filters, CRUD drawer |

---

## Before testing

Restart backend. Open http://localhost:5173/rating  
Seed has **4 ratings** (grades 90, 85, 80, 75) for English-1 students.

---

## 1. Table tab

| Check | Expected |
|-------|----------|
| Rows | 4 students sorted by grade desc |
| #1 | Sardor — grade 90 |
| Columns | №, Name, Group, Branch, Grade |
| Top 3 numbers | Gold/silver/bronze tint on rank |

---

## 2. Graph tab

| Step | Expected |
|------|----------|
| Click **Graph** | Horizontal bars per student |
| Bar lengths | Match grades (90 longest) |
| Click student name | Opens detail drawer |

---

## 3. Filters

| Action | Expected |
|--------|----------|
| Group → English-1 | 4 rows |
| Branch → Main branch | Same 4 rows |
| Search `Sardor` → Apply | 1 row |

---

## 4. Add grade

| Step | Expected |
|------|----------|
| **+ Add grade** | Drawer |
| Select group, student, grade → **Create** | New row, ranks recalculated |

Use student without score (e.g. Timur) if available.

---

## 5. Detail / Edit

| Step | Expected |
|------|----------|
| Click row | Drawer readonly |
| **Edit** → change grade → **Save** | Table + graph update, order may change |
| Links **Students →** / **Groups →** | Navigate |

---

## 6. Delete

| Step | Expected |
|------|----------|
| Open test grade → **Delete** → confirm | Row removed, ranks shift |

---

## API (DevTools)

| Request | When |
|---------|------|
| GET `/v1/scores/branch` | List + filters |
| POST `/v1/scores/branch` | Create / upsert |
| GET `/v1/scores/:id` | Detail |
| PATCH `/v1/scores/:id` | Edit grade |
| DELETE `/v1/scores/:id` | Delete |

---

## Pass criteria

Table, graph, filters, add/edit/delete grades — all work.
