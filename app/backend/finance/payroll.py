"""
Salaries (owner's rules, 2026-09-28).

Teacher — only a percent, and only from money the students have really paid (owner, 2026-10-05):
  * every month line of a student (finance/charges.py) is worth its sum; one lesson = sum ÷ lessons
    planned in that month of the student;
  * the teacher earns their percent for each lesson they HELD ("Я пришёл" or the administrator's mark)
    while the student was in the group and not frozen — a missed lesson earns nothing;
  * it is PAYABLE in the share of the line that is paid: 10 students, 7 paid -> paid for 7 now, for the
    other 3 when they pay (whenever that is — the lesson stays on its own month's sheet);
  * a lesson keeps the percent of the day it was marked: changing the percent later recounts nothing.
  Example: a line of 500 000, 13 lessons planned, 12 held, 20% → 92 307 when the line is paid.
  Percent: the group's own percent → the course's percent → the teacher's general percent.

Office staff (administrator, director…) — a fixed amount a month.

A payout is recorded as expenses split by branch: a teacher's by the branches of the groups the money was
earned in, a staff member's to their branch (or the one the CEO picks).
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from django.db.models import F, Q, Sum
from django.utils import timezone

from finance.models import Expense, Payment, PayrollPayment, SalarySetting

HELD_STATUSES = (1, 2)  # TeacherAttendanceRecord: present, late


# ---------------------------------------------------------------------------
# Month
# ---------------------------------------------------------------------------

def parse_month(raw) -> tuple[str, date, date] | None:
    """'2026-09' (also '2026-9') -> ('2026-09', 1 Sep, 30 Sep); anything else -> None."""
    text = str(raw or '').strip()
    parts = text.split('-')
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    year, month = int(parts[0]), int(parts[1])
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        return None
    last = calendar.monthrange(year, month)[1]
    return f'{year:04d}-{month:02d}', date(year, month, 1), date(year, month, last)


# ---------------------------------------------------------------------------
# Lessons of a group
# ---------------------------------------------------------------------------

def lesson_days(group, start: date, end: date) -> list[date]:
    """Days in [start, end] when the group could have a lesson."""
    from crm.services import group_weekdays
    from operations.models import Holiday

    weekdays = set(group_weekdays(group.days, group.weekdays))
    first = max(start, group.group_start_date) if group.group_start_date else start
    # The planned end date does not stop lessons (owner, 2026-10-05): a group lives until it is closed
    last = end
    if group.archived_at:
        last = min(last, timezone.localtime(group.archived_at).date())
    if first > last or not weekdays:
        return []
    holidays = set(Holiday.objects.filter(
        company_id=group.company_id, branch_id=group.branch_id, holiday_date__gte=first, holiday_date__lte=last,
    ).values_list('holiday_date', flat=True))
    days = []
    day = first
    while day <= last:
        if day.weekday() in weekdays and day not in holidays:
            days.append(day)
        day += timedelta(days=1)
    return days


# ---------------------------------------------------------------------------
# Rates
# ---------------------------------------------------------------------------

def _period_q(start: date, end: date) -> Q:
    return (
        (Q(effective_from__isnull=True) | Q(effective_from__lte=end))
        & (Q(effective_to__isnull=True) | Q(effective_to__gte=start))
    )


def _newest(qs):
    return qs.order_by(F('effective_from').desc(nulls_last=True), '-id').first()


def teacher_percent(company, teacher, group, start: date, end: date) -> SalarySetting | None:
    """The group's own percent → the course's percent → the teacher's general percent."""
    base = SalarySetting.objects.filter(
        company=company, teacher=teacher, salary_type=SalarySetting.SalaryType.PERCENT,
    ).filter(_period_q(start, end))
    return (
        _newest(base.filter(group=group))
        or (_newest(base.filter(group__isnull=True, course_id=group.course_id)) if group.course_id else None)
        or _newest(base.filter(group__isnull=True, course__isnull=True))
    )


def staff_fixed(company, person, start: date, end: date) -> SalarySetting | None:
    """
    The monthly sum of an office worker. A sum set without a start date counts from the day it was entered:
    months before that are not owed (it used to show a debt for every past month ever).
    """
    return _newest(SalarySetting.objects.filter(
        company=company, teacher=person, salary_type=SalarySetting.SalaryType.FIXED,
    ).filter(_period_q(start, end)).filter(
        Q(effective_from__isnull=False) | Q(created_at__date__lte=end),
    ))


# ---------------------------------------------------------------------------
# Teacher accrual
# ---------------------------------------------------------------------------

def percent_on(company, teacher, group, day: date) -> int | None:
    """The teacher's percent for a lesson of `group` on `day`; None when no percent is set at all."""
    setting = teacher_percent(company, teacher, group, day, day)
    return int(setting.amount) if setting else None


def _record_percent(company, teacher, group, record) -> int:
    """
    The percent of one held lesson. A lesson keeps the percent of the day it was marked (stored in the
    record), so a later change of the teacher's percent never recounts lessons already given. A lesson
    marked before any percent was set gets the one valid for its day now.
    """
    if record.percent is not None:
        return int(record.percent)
    return percent_on(company, teacher, group, record.attend_date) or 0


def _group_accrual(company, teacher, group, records: list, start: date, end: date) -> dict:
    """
    Owner (2026-10-05): the teacher is paid only from what the students have really paid, and only for
    the lessons the teacher really held.

    Every month line of a student (finance/charges.py) is worth its sum; one lesson of it is worth
    sum ÷ lessons planned in that month of the student. For each lesson held, the teacher earns their
    percent of that — "earned" if the line were paid in full, "payable" in the share that IS paid.
    When the student pays later (a September debt paid in December), the rest becomes payable then.
        Example: Азиз's line 500 000, 13 lessons planned, Том held 12, percent 20.
        Paid in full -> 500 000 × 12 ÷ 13 × 20% = 92 307. Paid 250 000 so far -> 46 153 now, 46 154 waiting.
    """
    from crm.models import GroupEnrollment, Student, StudentFreeze
    from finance.models import StudentCharge
    from operations.models import TeacherAttendanceRecord

    held = {r.attend_date: _record_percent(company, teacher, group, r) for r in records}
    setting = teacher_percent(company, teacher, group, start, end)
    row = {
        'group_id': group.id,
        'group': group.name,
        'branch_id': group.branch_id,
        'branch': group.branch.name if group.branch_id else '',
        'held_lessons': len(held),
        'student_lessons': 0,
        'percent': max(held.values()) if held else (int(setting.amount) if setting else 0),
        'percent_scope': (
            'группа' if setting and setting.group_id else 'курс' if setting and setting.course_id
            else 'общий' if setting else 'не задан'
        ),
        'earned': 0,    # if every student pays in full
        'accrued': 0,   # payable now: from the money already paid
        'waiting': 0,   # will become payable when the students pay
        'students_unpaid': 0,
    }
    if not held:
        return row

    # Who could be at these lessons: students whose history of groups has this group in the month, and
    # students whose month line was written for this group (a card created later than the start date:
    # the history of groups begins on the day of creation, the line says the student already studied)
    overlap = Q(period_start__lte=end, period_end__gt=start)
    student_ids = set(GroupEnrollment.objects.filter(group=group, joined_date__lte=end).filter(
        Q(left_date__isnull=True) | Q(left_date__gt=start),
    ).values_list('student_id', flat=True)) | set(
        StudentCharge.objects.filter(overlap, group=group).values_list('student_id', flat=True)
    )
    # The trial lesson is free: who left after it was never a paying student
    student_ids -= set(Student.objects.filter(pk__in=student_ids, status=Student.Status.LEFT_TRIAL).values_list('pk', flat=True))
    if not student_ids:
        return row
    stays: dict[int, list] = {}
    for e in GroupEnrollment.objects.filter(student_id__in=student_ids):
        stays.setdefault(e.student_id, []).append((e.group_id, e.joined_date, e.left_date))
    freezes: dict[int, list] = {}
    for f in StudentFreeze.objects.filter(student_id__in=student_ids, start_date__lte=end).filter(
        Q(end_date__isnull=True) | Q(end_date__gt=start),
    ):
        freezes.setdefault(f.student_id, []).append((f.start_date, f.end_date))
    lines = list(StudentCharge.objects.filter(overlap, student_id__in=student_ids).order_by('student_id', 'seq'))
    if not lines:
        return row

    # Every lesson held in this group (by anybody) inside the months of these lines: a month never pays
    # for more lessons than it has
    span = (min(line.period_start for line in lines), max(line.period_end for line in lines))
    all_held = sorted(set(TeacherAttendanceRecord.objects.filter(
        company=company, group=group, status__in=HELD_STATUSES,
        attend_date__gte=span[0], attend_date__lt=span[1],
    ).values_list('attend_date', flat=True)))

    def attended(line, day: date) -> bool:
        """Was the student of this line a member of this group on `day` and not frozen?"""
        history = stays.get(line.student_id, ())
        here = None
        for group_id, joined, left in history:
            if joined <= day and (left is None or day < left):
                here = group_id == group.id
                break
        if here is None:
            # Before the history of groups began: the group the line was written for
            began = min((joined for _g, joined, _l in history), default=None)
            here = (began is None or day < began) and line.group_id == group.id
        if not here:
            return False
        return not any(s <= day and (e is None or day < e) for s, e in freezes.get(line.student_id, ()))

    unpaid_students = set()
    for line in lines:
        weight = 0   # Σ percent over the lessons of this line the teacher held in the month
        for day, percent in held.items():
            if line.period_start <= day < line.period_end and attended(line, day):
                weight += percent
                row['student_lessons'] += 1
        if not weight:
            continue
        planned = line.lessons_planned or len(lesson_days(group, line.period_start, line.period_end - timedelta(days=1)))
        given = sum(1 for day in all_held if line.period_start <= day < line.period_end and attended(line, day))
        planned = max(planned, given, 1)
        # A written-off month will never be paid further: only its money counts
        worth = line.amount if line.status == StudentCharge.Status.OPEN else line.paid_amount
        earned = worth * weight // (planned * 100)
        payable = min(earned, line.paid_amount * weight // (planned * 100))
        row['earned'] += earned
        row['accrued'] += payable
        if payable < earned:
            unpaid_students.add(line.student_id)
    row['waiting'] = row['earned'] - row['accrued']
    row['students_unpaid'] = len(unpaid_students)
    return row


def teacher_accrual(company, teacher, start: date, end: date) -> dict:
    """Accrual of a teacher for [start, end] by the groups they held lessons in (substitutions included)."""
    from crm.models import Group
    from operations.models import TeacherAttendanceRecord

    held: dict[int, list] = {}
    for record in TeacherAttendanceRecord.objects.filter(
        company=company, teacher=teacher, attend_date__gte=start, attend_date__lte=end,
        status__in=HELD_STATUSES,
    ):
        held.setdefault(record.group_id, []).append(record)
    # Groups the teacher leads now are listed too (with 0 lessons), so a missing mark is visible
    group_ids = set(held) | set(
        Group.objects.filter(company=company, teacher=teacher, status=Group.Status.ACTIVE).values_list('id', flat=True)
    )
    groups = Group.objects.filter(pk__in=group_ids).select_related('course', 'branch').order_by('name')
    rows = [_group_accrual(company, teacher, g, held.get(g.id, []), start, end) for g in groups]
    return {
        'groups': rows,
        'accrued': sum(r['accrued'] for r in rows),
        'earned': sum(r['earned'] for r in rows),
        'waiting': sum(r['waiting'] for r in rows),
    }


def stamp_percents(company, start: date, end: date) -> int:
    """
    A month is being closed: every lesson of it that has no percent of its own yet gets the percent valid
    for its day now — after that the percents of the closed month never move.
    """
    from operations.models import TeacherAttendanceRecord

    stamped = 0
    for record in TeacherAttendanceRecord.objects.filter(
        company=company, attend_date__gte=start, attend_date__lte=end, percent__isnull=True,
        status__in=HELD_STATUSES,
    ).select_related('teacher', 'group'):
        percent = percent_on(company, record.teacher, record.group, record.attend_date) if record.group_id else None
        if percent is not None:
            TeacherAttendanceRecord.objects.filter(pk=record.pk).update(percent=percent)
            stamped += 1
    return stamped


# ---------------------------------------------------------------------------
# One person for one month
# ---------------------------------------------------------------------------

def paid_in_month(company, person, month_key: str, start: date, end: date) -> tuple[int, list[dict]]:
    payouts = list(PayrollPayment.objects.filter(company=company, teacher=person, payroll_period=month_key).order_by('created_at'))
    paid = sum(p.amount for p in payouts)
    # Old salaries typed in as plain expenses before payouts existed
    legacy = Expense.objects.filter(
        company=company,
        payee=person.display_name(),
        category__name__icontains='Зарплата',
        expense_date__gte=start,
        expense_date__lte=end,
        payroll_payments__isnull=True,
        payroll_payment__isnull=True,
    ).aggregate(total=Sum('amount'))['total'] or 0
    return paid + legacy, [
        {
            'id': p.id,
            'amount': p.amount,
            'method': p.method,
            'comment': p.comment,
            'date': timezone.localtime(p.created_at).date().isoformat(),
        }
        for p in payouts
    ] + ([{'id': None, 'amount': legacy, 'method': '', 'comment': 'Старая запись в расходах', 'date': ''}] if legacy else [])


def _is_teacher(person) -> bool:
    from accounts.models import User

    return person.user_type == User.UserType.TEACHER


def live_accrual(company, person, start: date, end: date) -> tuple[int, dict]:
    """The salary counted from today's data: (accrued, details for "Как посчитано")."""
    if _is_teacher(person):
        accrual = teacher_accrual(company, person, start, end)
        return accrual['accrued'], {
            'groups': accrual['groups'], 'fixed_amount': None,
            'earned': accrual['earned'], 'waiting': accrual['waiting'],
        }
    setting = staff_fixed(company, person, start, end)
    amount = setting.amount if setting else 0
    return amount, {'groups': [], 'fixed_amount': amount if setting else None}


_LOOKUP = object()


def closed_month_of(company, month_key: str):
    from finance.models import ClosedMonth

    return ClosedMonth.objects.filter(company=company, month=month_key).select_related('closed_by').first()


def payroll_people(company, month_key: str, teachers=None, staff=None, closed=_LOOKUP) -> list:
    """
    Who is on the salary list of a month: every teacher, and office staff with a monthly amount, a payout,
    a frozen salary or a correction in that month. `teachers` / `staff` narrow the list (a director's branch).
    """
    from accounts.models import User
    from finance.models import PayrollAdjustment, PayrollSnapshot

    if closed is _LOOKUP:
        closed = closed_month_of(company, month_key)
    if teachers is None:
        teachers = User.objects.filter(company=company, user_type=User.UserType.TEACHER)
    if staff is None:
        staff = User.objects.filter(company=company, user_type=User.UserType.STAFF)
    ids = set(SalarySetting.objects.filter(
        company=company, salary_type=SalarySetting.SalaryType.FIXED,
    ).values_list('teacher_id', flat=True))
    ids |= set(PayrollPayment.objects.filter(company=company, payroll_period=month_key).values_list('teacher_id', flat=True))
    ids |= set(PayrollAdjustment.objects.filter(company=company, payroll_period=month_key).values_list('person_id', flat=True))
    if closed is not None:
        ids |= set(PayrollSnapshot.objects.filter(closed_month=closed).values_list('person_id', flat=True))
    people, seen = [], set()
    for person in list(teachers.order_by('first_name', 'last_name')) + list(
        staff.filter(pk__in=ids).order_by('first_name', 'last_name')
    ):
        if person.pk not in seen:
            seen.add(person.pk)
            people.append(person)
    return people


def person_payroll(company, person, month_key: str, start: date, end: date, closed=_LOOKUP) -> dict:
    from finance.models import PayrollAdjustment, PayrollSnapshot

    if closed is _LOOKUP:
        closed = closed_month_of(company, month_key)
    is_teacher = _is_teacher(person)
    if closed is not None and not is_teacher:
        # Closed month, office staff: the monthly sum saved at closing time, whatever changed since
        snapshot = PayrollSnapshot.objects.filter(closed_month=closed, person=person).first()
        base = snapshot.accrued if snapshot else 0
        details = snapshot.details if snapshot else {}
    else:
        # A teacher's month is counted from facts that no longer change (lessons with their percents, the
        # students' month lines) — closed or not. Only a late payment of a student adds to it: that is
        # exactly "the rest is paid when the students pay".
        base, details = live_accrual(company, person, start, end)
    groups = details.get('groups') or []
    fixed_amount = details.get('fixed_amount')
    kind_label = 'Учитель · процент' if is_teacher else 'Сотрудник · фикс в месяц'

    adjustments = list(
        PayrollAdjustment.objects.filter(company=company, person=person, payroll_period=month_key)
        .select_related('created_by').order_by('created_at', 'id')
    )
    accrued = base + sum(a.amount for a in adjustments)
    paid, payouts = paid_in_month(company, person, month_key, start, end)
    balance = accrued - paid
    if accrued <= 0 and paid <= 0:
        status = 'none'
    elif balance <= 0:
        status = 'paid'
    elif paid > 0:
        status = 'partial'
    else:
        status = 'unpaid'
    return {
        'teacher_id': person.id,
        'person_id': person.id,
        'teacher_name': person.display_name(),
        'phone': person.phone,
        'kind': 'teacher' if is_teacher else 'staff',
        'kind_label': kind_label,
        'is_active': person.is_active,
        'branch_id': getattr(person, 'branch_id', None),
        'groups': groups,
        'fixed_amount': fixed_amount,
        'month_closed': closed is not None,
        # Counted (or frozen) salary before the CEO's corrections
        'accrued_base': base,
        'adjustments': [
            {
                'id': a.id,
                'amount': a.amount,
                'reason': a.reason,
                'date': timezone.localtime(a.created_at).date().isoformat(),
                'by': a.created_by.display_name() if a.created_by_id else '',
            }
            for a in adjustments
        ],
        'accrued': accrued,
        # Teacher: earned if every student pays in full, and the part still waiting for the students' money
        'earned': (details.get('earned') or 0) if is_teacher else accrued,
        'waiting': (details.get('waiting') or 0) if is_teacher else 0,
        'paid': paid,
        # Owed to THIS person (never offset by an overpayment to somebody else)
        'balance': max(0, balance),
        'overpaid': max(0, -balance),
        'status': status,
        'payouts': payouts,
    }


# ---------------------------------------------------------------------------
# Payout split by branch
# ---------------------------------------------------------------------------

def split_by_weights(amount: int, weights: dict) -> dict:
    """Split a whole sum by weights without losing any (largest remainder goes to the biggest parts)."""
    weights = {k: w for k, w in weights.items() if w > 0}
    if not weights:
        return {}
    total = sum(weights.values())
    parts = {k: amount * w // total for k, w in weights.items()}
    left = amount - sum(parts.values())
    for k in sorted(weights, key=lambda key: (amount * weights[key]) % total, reverse=True)[:left]:
        parts[k] += 1
    return {k: v for k, v in parts.items() if v > 0}
