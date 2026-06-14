# Phase 13 Verification Checklist — Settings

**Phase:** Settings flyout  
**Date:** 2026-06-10

## Files changed

| Area | What changed |
|------|----------------|
| `org/models.py` | VoIP, grade, SMS text fields on Company |
| `views_extended.py` | Staff CRUD; extended company settings |
| `views_misc.py` | Rooms, holidays, tags, forms CRUD |
| `views.py` | Course detail PATCH/DELETE |
| `AutoSmsView`, `VoipSettingsView`, `GradeSettingsView` | Save wired |
| `StaffView`, `RoomsView`, `HolidaysView`, `FormsView`, `TagsView` | CRUD drawers |
| `CoursesView` | Click card → edit/delete |
| Router | VoIP, Grade, `/left-students` wired |

**Still placeholder (by design):** Roadmap, What's new (blog)

---

## Before testing

Restart backend. Run `python manage.py migrate`.  
Login: phone `903708242` — see `app/README.md`

---

## 1. SMS settings — `/auto-sms`

| Check | Expected |
|-------|----------|
| Toggle SMS + edit text → **Save** | Persists after reload |

---

## 2. VoIP — `/admin/voip`

| Check | Expected |
|-------|----------|
| Enable + gateway + caller ID → **Save** | Persists |

---

## 3. Grade — `/settings-grade`

| Check | Expected |
|-------|----------|
| Pass score + max scale → **Save** | Persists |

---

## 4. General settings — `/settings`

| Check | Expected |
|-------|----------|
| Edit center name / payment mode → **Save** | Works (Phase 0+) |

---

## 5. Staff — `/staff/list`

| Check | Expected |
|-------|----------|
| Kamola + Sherzod in list | Seed |
| **ADD NEW** → Create | New row |
| Click → Edit / Delete | CRUD |

---

## 6. Courses — `/courses`

| Check | Expected |
|-------|----------|
| Click course card | Edit drawer |
| Save changes | Updated |
| Delete | Removed |

---

## 7. Rooms — `/rooms`

| Check | Expected |
|-------|----------|
| Room 101, 202 | Seed |
| ADD NEW / Edit / Delete | CRUD |

---

## 8. Holidays — `/holiday`

| Check | Expected |
|-------|----------|
| Navruz in list | Seed |
| Upcoming / Past tabs | Filter |
| ADD NEW / Edit / Delete | CRUD |

**Still placeholder (by design):** What's new (blog)

---

## 9. Archive — `/archive/list` (revised)

| Check | Expected |
|-------|----------|
| Title shows **Quantity — N** | Count matches rows |
| Filters: name/phone, role, reason, dates | Apply works |
| **Reasons for archiving** | Modal with 3 reasons |
| Checkboxes + **Delete** / **Reestablish** | Bulk actions |
| Row **Restore** / **Delete** | Single actions |
| **Export** | Downloads CSV |
| Demo row | Old Student Test |

---

## 10. Roadmap — `/roadmap` (revised)

| Check | Expected |
|-------|----------|
| Not placeholder | Milestone list with statuses |
| **modme.uz →** link | Opens official site |

---

## 11. Courses — `/courses` (note)

| Check | Expected |
|-------|----------|
| Card grid (not table) | CEFR badges |
| Click card → Edit drawer | Save / Delete |
| After `seed_demo` | One `a1` course (no duplicates) |

---

## 12. Left students — `/left-students`

| Check | Expected |
|-------|----------|
| Same as `/reports/left-students` | Malika + Timur |

---

## 11. Forms — `/form`

| Check | Expected |
|-------|----------|
| Main lead form | Seed |
| ADD NEW / Edit / Delete | CRUD |

---

## 12. Tags — `/tags` (revised)

| Check | Expected |
|-------|----------|
| Columns | id, Name, From Where, Actions |
| From Where | Orange badge (e.g. Students) |
| Actions | 🗑 Delete, ✏ Edit inline |
| **ADD NEW** | Pill button |

---

## 13. Forms — `/form`

| Check | Expected |
|-------|----------|
| Columns | id, Name, type, Actions |
| **Add new** | Pill button (not drawer on row click) |
| Edit/Delete | Inline action icons |

---

## 14. Students left the group — `/left-students` (Settings)

| Check | Expected |
|-------|----------|
| Title | Large navy «Students left the group» |
| No summary cards | Only filters + table |
| `/reports/left-students` | Keeps summary cards |

---

## 15. Settings nav — no LOGS section

| Check | Expected |
|-------|----------|
| Settings flyout ends at Blog | No Sent SMS / Call / Logs items |

---

## Logs (routes exist, hidden from Settings menu)

Routes `/sms`, `/call`, `/history/logs` still work if opened directly.

---

## Pass criteria

Archive (filters + bulk), Roadmap (milestones), Courses (cards + CRUD) match ModMe flows.
Only `/blog/news` remains placeholder. No unwired **Save** / **ADD NEW** on implemented pages.
