# TECHNICAL AUDIT & ACTION PLAN
## Teachers + Groups, Django + Vue 3 CRM/LMS

**Basis:** `00_TEACHERS_AND_GROUPS_ALL_IN_ONE.txt` plus attached backend files.  
**Goal:** implementation plan for another AI/developer.  
**Priority:** P0 = security/data integrity, P1 = high business risk, P2 = hardening.

## 0. Executive summary

The modules have a useful tenant boundary through `company` and teacher-scoping helpers for the main Groups/Students endpoints, but object-level authorization is not consistently applied to Attendance. Schedule conflict validation is not authoritative on the backend. Payroll formulas are simple, but their inputs are historically unstable because teacher/group identity is often stored or inferred by mutable names/current relationships.

### Highest-priority findings

1. **P0: Student Attendance is not teacher-scoped.** Teachers have `attendance.view/write`, but `report_attendance()` and `_attendance_queryset()` operate on any group/student inside the same company.
2. **P0: `attendance_detail()` can create invalid student/group combinations.** It changes `student` and `group` independently and calls `save()` without rechecking membership. `Model.clean()` is not automatically called by Django `save()`.
3. **P0/P1: Teacher Attendance ownership is incomplete.** Controller logic supports a teacher marking themselves, but RBAC does not grant teachers `teacher_attendance.write`. If write is later granted without additional checks, arbitrary teacher/group combinations are possible.
4. **P1: No backend schedule collision check** for teacher, room, weekday/time/date overlap on group create/edit.
5. **P1: Group DELETE is a hard delete.** Students survive through `SET_NULL`, but attendance history cascades away.
6. **P1: SalarySetting identifies teachers by `teacher_name`, not FK.** Rename/duplicate-name problems can break payroll.
7. **P1: Percentage payroll attributes payments through the student's current group**, so moving a student can change historical payroll.
8. **P1: Refunds, discounts, freeze periods and effective salary-setting periods are not modeled robustly.**
9. **P1: Student Attendance lacks a DB uniqueness constraint** for one student/group/date.
10. **P0 security issue discovered outside the requested modules:** login contains hard-coded fallback passwords/credential behavior. Remove immediately.

---

# 1. Architecture and data integrity

Current core graph:

```text
Company
├─ Branch
│  ├─ Room
│  └─ Group
│     ├─ course -> Course (SET_NULL)
│     ├─ room -> Room (SET_NULL)
│     ├─ teacher -> User/TEACHER (SET_NULL)
│     ├─ students -> Student.group (SET_NULL)
│     ├─ AttendanceRecord.group (CASCADE)
│     └─ TeacherAttendanceRecord.group (CASCADE)
├─ User/TEACHER -> TeacherBranch
├─ Payment -> Student (SET_NULL)
└─ SalarySetting -> teacher_name STRING
```

### Good foundations

- Group teacher/course/room use `SET_NULL`.
- Student group uses `SET_NULL`, so group deletion does not delete students.
- Main group/student endpoints are company-scoped.
- Teacher helpers exist: `filter_groups_queryset`, `filter_students_queryset`, `teacher_can_access_group`, `teacher_can_access_student`.
- `AttendanceRecord.clean()` describes the correct membership invariant.

### P1: Room can belong to a different branch

`_apply_group_fields()` checks only `room.branch.company == company`. It does not require `room.branch_id == group.branch_id`.

**Fix:** resolve the final group branch first, then load room with `Room.objects.get(pk=..., branch=final_branch)`. Add model/service validation and create/PATCH tests.

### P1: Teacher branch membership is not enforced when assigning a group

Teacher assignment checks company and `user_type=TEACHER`, but not `TeacherBranch`.

**Fix:** require a `TeacherBranch` link for the group's branch, unless cross-branch teaching without such a link is an explicit business rule.

### P1: Student branch and group branch can drift

Make this invariant explicit:

```python
if student.group_id:
    assert student.branch_id == student.group.branch_id
```

Prefer deriving branch from group when group is selected.

---

# 2. Archive/delete behavior

## Group

Current `DELETE /groups/<id>` calls `group.delete()`.

Effects:
- students become `group=None`;
- `AttendanceRecord` rows cascade-delete;
- `TeacherAttendanceRecord` rows cascade-delete;
- historical schedule/audit context disappears.

### Required change

Make normal DELETE a soft archive:

```python
group.status = Group.Status.ARCHIVE
group.archived_at = timezone.now()
group.archived_by = request.user
group.save(...)
```

Do not physically delete operational groups with attendance/history. If a hard-delete endpoint is retained, make it CEO-only and refuse deletion when historical records exist.

## Teacher

Teacher DELETE clears group.teacher and deletes the user. Teacher attendance has a cascading teacher FK, so history may disappear.

**Recommended:** deactivate/archive teachers instead of deleting them. Use `PROTECT` or immutable snapshots for financial/audit relations.

---

# 3. Schedule

## Finding

Group create/PATCH accepts branch, teacher, room, `days`, start/end time and date range but does not reject collisions.

It also does not reliably reject:
- start >= end;
- only one of start/end being present;
- room overlap;
- teacher overlap;
- overlapping active date periods;
- teacher not assigned to branch;
- room from another branch.

Frontend schedule components must not be the source of truth because direct API requests bypass them.

## Required backend service

Create:

```python
validate_group_schedule(
    company,
    branch,
    teacher,
    room,
    days,
    start_time,
    end_time,
    start_date,
    end_date,
    exclude_group_id=None,
)
```

Time overlap:

```python
existing_start < candidate_end and candidate_start < existing_end
```

Date ranges must also intersect. Ignore archived groups.

Return HTTP 409 with structured conflicts:

```json
{
  "code": "schedule_conflict",
  "conflicts": [
    {"type": "room", "group_id": 12},
    {"type": "teacher", "group_id": 15}
  ]
}
```

### Schema recommendation

Current `Group.Days` is an enum (`ODD`, `EVEN`, `WEEKEND`, `EVERY_DAY`, `CUSTOM`), which is weaker than normalized weekdays. Introduce:

```text
GroupScheduleSlot
- group_id
- weekday 0..6
- start_time
- end_time
- room_id
```

This makes conflict detection deterministic, especially for `CUSTOM`.

### Tests

Cover exact/partial/contained overlap, touching boundaries, different days, different rooms, different teachers, archived groups, non-overlapping date ranges, PATCH excluding itself, and concurrent creates.

---

# 4. Student Attendance

## P0: Teacher can target another teacher's group through API

Teacher RBAC includes `attendance.view` and `attendance.write`, but `_attendance_queryset()` only scopes by company. POST also loads `Group` by company, not by current teacher.

### Fix all Attendance paths

For teacher users:

```python
qs = qs.filter(group__teacher=request.user)
```

For create/update/delete:

```python
group = Group.objects.get(
    pk=group_id,
    company=company,
    teacher=request.user,
)
```

Load detail records from a scoped queryset and return 404 for foreign records.

## P0: PATCH can violate membership

`attendance_detail()` may change group/student independently and then save.

Before save require:

```python
record.student.company_id == company.id
record.group.company_id == company.id
record.student.group_id == record.group_id
```

Move this to one shared attendance service used by bulk, single create and PATCH.

## P1: Backdating/future attendance is unrestricted

Define policy explicitly:

- Teacher: own groups only, today or a small correction window.
- Admin/branch director: configurable correction window.
- CEO: broader correction, but require audit reason.
- Future dates: reject.
- Historical edits: audit old/new values and actor.

Also verify the date is a scheduled lesson date and inside the group's active period.

## P1: Missing DB uniqueness

Add:

```python
UniqueConstraint(
    fields=["company", "student", "group", "attend_date"],
    name="uniq_student_attendance_per_group_day",
)
```

Deduplicate before migration.

## P2: Bulk attendance silently skips invalid rows

Current bulk behavior can return success with fewer rows saved.

Prefer atomic validation: if any item is invalid, reject the batch with per-row errors. Otherwise return explicit `saved/rejected/errors`.

---

# 5. Teacher Attendance

## RBAC/controller mismatch

Teacher role has `teacher_attendance.view` but not `teacher_attendance.write`, while the controller contains self-marking logic.

Choose one rule:

### Recommended

Create a dedicated self-check-in endpoint/permission:

```text
POST /v1/teacher-attendance/self-checkin
teacher_attendance.self_checkin
```

The server derives `teacher=request.user`; do not accept arbitrary `teacher_id`.

Require:

```python
group.teacher_id == request.user.id
attend_date == timezone.localdate()
```

Optionally allow check-in only around the scheduled lesson time.

Do **not** simply grant generic `teacher_attendance.write` to teachers.

### Detail PATCH

If administrators can edit teacher attendance, enforce:

```python
record.group.teacher_id == record.teacher_id
```

If substitutes are legitimate, model substitute assignment explicitly rather than weakening the invariant.

---

# 6. Payroll & SalarySettings

Current arithmetic:

```text
FIXED       = amount
PERCENT     = group_payments * amount / 100
PER_STUDENT = amount * active_students
```

The formulas themselves are simple. The dangerous part is the source data.

## P1: SalarySetting uses teacher name instead of teacher FK

Add:

```python
teacher = ForeignKey(User, on_delete=PROTECT)
```

Also replace `course_name` and `group_name` with nullable FKs if they are intended to scope a rate. Keep name snapshots only for display/history.

## P1: No effective dates for salary settings

Add:

```text
effective_from
effective_to
```

Historical payroll must use the setting effective during the payroll period.

## P1: Percentage payroll is historically unstable

Current calculation filters payments using:

```python
student__group__in=teacher_groups
```

That is the student's **current** group at payroll calculation time.

Failure:
1. student pays in Teacher A's group;
2. student moves to Teacher B;
3. old payroll is recalculated;
4. old payment can move to Teacher B.

### Required fix

Snapshot allocation at payment time:

```text
Payment / PaymentAllocation
- student_id
- group_id
- course_id
- teacher_id
- service_period
- gross_amount
- discount_amount
- net_amount
```

Payroll percentage must use immutable payment allocation, not current student membership.

## Refunds

Do not delete financial records to represent refunds. Add ledger semantics:

```text
transaction_type = PAYMENT | REFUND | ADJUSTMENT
status = POSTED | VOID
reverses_payment_id
```

Define whether teacher percentage is calculated on gross, collected cash, net after discount, or net after refunds.

## Discounts

Current code effectively pays percentage on recorded cash collected in the month. That is not necessarily the same as earned revenue.

Document and implement the intended policy.

## Frozen students

PER_STUDENT currently counts students whose current status is `STUDYING`, so frozen students are excluded now. But historical payroll can change when status changes later.

Introduce `GroupEnrollment` / membership history with join/leave/freeze periods and calculate active students for the payroll period.

## Fixed salary

Current fixed salary is full amount even for partial month. Decide whether this is intentional. If proration is needed, implement it explicitly using employment/effective dates.

## Salary payments are identified by name

Payroll considers salary paid by matching `Expense.payee == teacher.display_name()` and category name containing `Зарплата`.

Replace this with a first-class model:

```text
PayrollPayment
- company
- teacher FK
- payroll_period
- amount
- method
- paid_at
- created_by
- expense FK optional
```

Prevent overpayment unless explicitly overridden with elevated permission.

---

# 7. Security and RBAC

## Existing positive behavior

Teacher scope helpers correctly restrict the main Groups and Students list/detail endpoints to `group.teacher == user`.

## P0: Attendance bypasses those helpers

Apply object-level teacher scoping to every attendance/report endpoint, not only Groups/Students.

## Salary access

Teacher role currently has no `finance.view/write`, so generic RBAC should block salary settings/payroll. Keep this and add explicit tests that teachers receive 403 for:

```text
GET/POST /salary-settings
GET/PATCH/DELETE /salary-settings/<id>
GET /finance/payroll
POST /finance/payroll/pay
```

## P0: hard-coded login fallback credentials

The login code contains special password strings and fallback password behavior.

**Action:**
- remove immediately;
- rotate affected passwords/tokens;
- inspect logs;
- add test proving only `authenticate()`/normal password verification is accepted;
- search repository/history for the credential strings;
- treat this as a security incident if deployed.

## RBAC middleware test

`RbacPermission.has_permission()` returns `True` for unauthenticated requests and relies on endpoint `IsAuthenticated`. This is defensible only if every private endpoint declares authentication correctly.

Add a route audit test that iterates private URLs and confirms unauthenticated access is rejected.

---

# 8. Database constraints and migrations

Implement after cleaning existing data:

1. Student attendance unique `(company, student, group, attend_date)`.
2. SalarySetting teacher FK.
3. SalarySetting effective period.
4. PayrollPayment with teacher FK + payroll period.
5. Payment allocation snapshots for group/course/teacher.
6. Group archive metadata.
7. Teacher archive metadata or retain `is_active` with audit fields.
8. GroupScheduleSlot normalized weekdays.
9. Optional GroupEnrollment history.
10. Validation that room/group branch and student/group branch agree at service/model level.

Use `PROTECT` for records required for accounting/audit history.

---

# 9. Test plan

## Authorization matrix

Create users for two companies and two teachers in the same company.

For every endpoint test:
- anonymous;
- Teacher A own object;
- Teacher A Teacher B object;
- cross-company ID;
- limited admin;
- administrator;
- CEO.

Critical endpoints:
- groups;
- students;
- student attendance list/create/detail;
- teacher attendance list/create/detail;
- salary settings;
- payroll;
- payroll pay.

## Schedule tests

Test room and teacher collisions, date/day/time edge cases, archived groups, PATCH self-exclusion and concurrent requests.

## Attendance tests

Test:
- foreign group read/write denied;
- student/group mismatch;
- future date rejected;
- teacher backdate policy;
- duplicate date uniqueness;
- bulk atomicity;
- PATCH cannot switch to unrelated student/group;
- teacher self-check-in cannot choose another teacher/group.

## Payroll tests

Test:
- teacher rename does not break settings/history;
- student transfer does not move historical payment allocation;
- refund reduces eligible revenue according to policy;
- discount behavior;
- frozen period;
- partial-month effective rate;
- duplicate names;
- salary payment overpayment protection;
- recomputing an old month is stable.

---

# 10. Implementation order for another AI/developer

## Phase 1, P0 security

1. Remove hard-coded login fallback credentials.
2. Add teacher object scope to all student Attendance GET/POST/detail operations.
3. Fix `attendance_detail()` membership validation.
4. Decide teacher self-check-in policy and implement dedicated safe endpoint or remove dead self-write logic.
5. Add security regression tests before further refactoring.

## Phase 2, P1 schedule and deletion

6. Implement backend schedule validation service.
7. Validate room branch and teacher branch.
8. Validate start/end times and group date range.
9. Change group DELETE to archive.
10. Change teacher deletion to deactivation/archive for records with history.

## Phase 3, P1 payroll integrity

11. Migrate SalarySetting from teacher name to teacher FK.
12. Add effective dates.
13. Add immutable payment allocation with group/teacher snapshots.
14. Add explicit refunds/adjustments.
15. Add PayrollPayment model.
16. Decide/document fixed, percentage, discount, refund and freeze business rules.

## Phase 4, P2 structural hardening

17. Normalize schedule into `GroupScheduleSlot`.
18. Add `GroupEnrollment` history.
19. Add audit log for attendance/payroll corrections.
20. Add DB constraints and cleanup migrations.
21. Expand endpoint-level RBAC/tenant regression suite.

---

# 11. Acceptance criteria

The work is complete only when:

- a teacher cannot read or mutate another teacher's group/student/attendance by guessing IDs;
- teacher self-attendance, if enabled, cannot target another teacher/group/date;
- two active groups cannot occupy the same room or teacher at overlapping times;
- deleting/archiving a group or teacher does not destroy attendance/payroll history;
- attendance cannot persist with student/group mismatch;
- one student has at most one attendance row per group/date;
- salary settings are linked to teacher IDs, not names;
- historical payroll remains unchanged after teacher rename or student group transfer;
- refund/discount/freeze behavior is explicitly tested;
- all cross-company access attempts fail;
- no hard-coded authentication bypass remains.

---

## Important discrepancy in supplied documentation

The overview document describes some structures differently from the actual code. For example, it describes schedule days/tags in a more JSON-like form, while the actual `Group` model uses an integer `Days` enum and a ManyToMany Tag relation. Treat executable models/views as the source of truth and update the overview after the refactor.
