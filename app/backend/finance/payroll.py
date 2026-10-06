"""
Salaries (owner's rules, 2026-09-28).

Teacher — only a percent, counted per group and per lesson:
  * a lesson of the group is worth, for every student, (course price − the student's monthly discount)
    ÷ the number of lessons the group COULD have in the month (its weekday schedule, inside the group's
    start / end / archive dates, without holidays of its branch);
  * the teacher gets their percent of the lessons they HELD ("Я пришёл" or the administrator's mark,
    present or late), only on lesson days of the schedule;
  * a lesson counts only the students who were in the group that day (group history) and were not frozen
    that day (freeze journal); students who left after the trial lesson are not counted; debtors are counted
    (the base is the course price, not the money that came).
  Example: 10 students × 500 000, 12 possible lessons, 3 held, 30% → 5 000 000 ÷ 12 × 3 × 30% = 375 000.
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
    return _newest(SalarySetting.objects.filter(
        company=company, teacher=person, salary_type=SalarySetting.SalaryType.FIXED,
    ).filter(_period_q(start, end)))


# ---------------------------------------------------------------------------
# Teacher accrual
# ---------------------------------------------------------------------------

def monthly_discount(student, price: int, month_end: date) -> int:
    """
    The student's discount for a month: the discount of their latest payment made by the end of the month,
    spread over the months that payment closed (a payment for 3 months with 300 000 off = 100 000 a month).
    """
    payment = Payment.objects.filter(
        student=student, transaction_type=Payment.TransactionType.PAYMENT,
    ).filter(Q(payment_date__lte=month_end) | Q(payment_date__isnull=True, created_at__date__lte=month_end)).order_by(
        F('payment_date').desc(nulls_last=True), '-created_at', '-id',
    ).first()
    if payment is None or not payment.discount_amount:
        return 0
    months = max(1, payment.months_covered or 1)
    return min(price, payment.discount_amount // months)


def _group_accrual(company, teacher, group, held_dates: set, start: date, end: date) -> dict:
    from crm.models import GroupEnrollment, Student, StudentFreeze

    possible_days = lesson_days(group, start, end)
    possible = len(possible_days)
    held_days = sorted(set(possible_days) & held_dates)
    setting = teacher_percent(company, teacher, group, start, end)
    percent = setting.amount if setting else 0
    price = (group.course.price or 0) if group.course_id else 0

    enrollments = list(
        GroupEnrollment.objects.filter(group=group, joined_date__lte=end)
        .filter(Q(left_date__isnull=True) | Q(left_date__gt=start))
        .exclude(student__status=Student.Status.LEFT_TRIAL)  # the trial lesson is free: never a paying student
        .select_related('student')
    )
    student_ids = {e.student_id for e in enrollments}
    freezes = {}
    for f in StudentFreeze.objects.filter(student_id__in=student_ids, start_date__lte=end).filter(
        Q(end_date__isnull=True) | Q(end_date__gt=start),
    ):
        freezes.setdefault(f.student_id, []).append((f.start_date, f.end_date))
    base = {
        e.student_id: max(0, price - monthly_discount(e.student, price, end)) for e in enrollments
    } if price else {}

    money_lessons = 0      # Σ over held lessons of the students' monthly bases
    student_lessons = 0    # how many student-lessons were counted
    for day in held_days:
        present = set()
        for e in enrollments:
            if e.student_id in present:
                continue
            if e.joined_date > day or (e.left_date is not None and e.left_date <= day):
                continue
            if any(s <= day and (f_end is None or day < f_end) for s, f_end in freezes.get(e.student_id, ())):
                continue
            present.add(e.student_id)
            money_lessons += base.get(e.student_id, 0)
        student_lessons += len(present)

    # One exact integer division at the end: no sum is lost on rounding
    accrued = money_lessons * percent // (possible * 100) if possible else 0
    return {
        'group_id': group.id,
        'group': group.name,
        'branch_id': group.branch_id,
        'branch': group.branch.name if group.branch_id else '',
        'course_price': price,
        'possible_lessons': possible,
        'held_lessons': len(held_days),
        'student_lessons': student_lessons,
        'percent': percent,
        'percent_scope': (
            'группа' if setting and setting.group_id else 'курс' if setting and setting.course_id
            else 'общий' if setting else 'не задан'
        ),
        'accrued': accrued,
    }


def teacher_accrual(company, teacher, start: date, end: date) -> dict:
    """Accrual of a teacher for [start, end] by the groups they held lessons in (substitutions included)."""
    from crm.models import Group
    from operations.models import TeacherAttendanceRecord

    held = {}
    for group_id, day in TeacherAttendanceRecord.objects.filter(
        company=company, teacher=teacher, attend_date__gte=start, attend_date__lte=end,
        status__in=HELD_STATUSES,
    ).values_list('group_id', 'attend_date'):
        held.setdefault(group_id, set()).add(day)
    # Groups the teacher leads now are listed too (with 0 lessons), so a missing mark is visible
    group_ids = set(held) | set(
        Group.objects.filter(company=company, teacher=teacher, status=Group.Status.ACTIVE).values_list('id', flat=True)
    )
    groups = Group.objects.filter(pk__in=group_ids).select_related('course', 'branch').order_by('name')
    rows = [_group_accrual(company, teacher, g, held.get(g.id, set()), start, end) for g in groups]
    return {'groups': rows, 'accrued': sum(r['accrued'] for r in rows)}


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
        return accrual['accrued'], {'groups': accrual['groups'], 'fixed_amount': None}
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
    if closed is not None:
        # Closed month: the salary saved at closing time, whatever changed since
        snapshot = PayrollSnapshot.objects.filter(closed_month=closed, person=person).first()
        base = snapshot.accrued if snapshot else 0
        details = snapshot.details if snapshot else {}
    else:
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
