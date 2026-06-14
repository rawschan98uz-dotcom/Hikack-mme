# Phase 14 Verification Checklist — Cross-links

**Phase:** Student ↔ Group ↔ Teacher navigation  
**Prerequisite:** Backend + frontend running, login `903708242`

Shared helpers: `app/frontend/src/utils/crossLinks.ts`  
Query param `?open=<id>` opens detail drawer on target page.

---

## 1. Students → Group

| Step | Expected |
|------|----------|
| `/students` → click **English-1** in Group column | `/groups?open=<id>`, group drawer opens |
| Student detail → **Open groups →** | Same group drawer |

---

## 2. Groups → Students / Teacher

| Step | Expected |
|------|----------|
| Group **English-1** detail → click student name | `/students?open=<id>`, student drawer |
| **All students →** | `/students?group_id=<id>`, filtered list |
| **Open teacher →** (Nilufar) | `/teachers?open=<id>`, teacher profile |
| Table → click teacher name | Teacher profile opens |

---

## 3. Teachers → Groups

| Step | Expected |
|------|----------|
| Nilufar profile → click **English-1** | `/groups?open=<id>` |
| **All groups →** | `/groups?teacher_id=<id>`, filtered to teacher's groups |

---

## 4. Dashboard schedule

| Step | Expected |
|------|----------|
| Dashboard → Schedule row click | Opens matching group detail |

---

## 5. Reports cross-links

| Page | Link | Expected |
|------|------|----------|
| Rating detail | Students → / Groups → | Opens student / group by id |
| Attendance detail | Students → / Groups → | Opens student / group by id |
| Teacher attendance detail | Teachers → / Groups → | Opens teacher / group by id |
| Left students | Row click | Student drawer |
| Left students | Group column | Group drawer |

---

## 6. Deep link bookmark

| URL | Expected |
|-----|----------|
| `/students?open=1` | Student drawer auto-opens |
| `/groups?open=1` | Group drawer auto-opens |
| `/teachers?open=1` | Teacher profile auto-opens |
| Close drawer | `open` removed from URL |

---

## API

| Request | When |
|---------|------|
| GET `/v1/groups?teacher_id=` | Teacher filter on Groups page |

---

## Next

**Phase 15** — Final QA across all modules.
