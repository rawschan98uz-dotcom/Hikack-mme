"""
Student month lines — "строки" (owner, 2026-10-05). The way a paper ledger works:

  * Every month of every student is a LINE: who, which month, what sum (finance.StudentCharge).
    It is written on the first day of that month, at the course price of that day, and never recounted.
  * A student's month runs from their start date: came on 17 September -> 17.09–17.10, 17.10–17.11 …
  * A payment closes lines, the oldest unpaid one first (finance.PaymentAllocation). The September debt
    paid in December closes the September line and touches nothing else.
  * Money on top of every existing line pays the next months in advance, at the price of the payment day.
  * A discount given with a payment lowers the sum of the months that payment pays (never more than half
    of a month's price); it is not money, so the teacher's percent is counted from what was really paid.
  * A debt is simply the lines that are not paid in full; its sum is exact, each month at its own price.
  * A freeze pauses the running month: what was left of it continues from the day the student comes back.

Example: Азиз came on 17.09, the course costs 500 000. Lines: 17.09–17.10 = 500 000, 17.10–17.11 = 500 000.
From 1 November the course costs 600 000 -> the line 17.11–17.12 = 600 000, the first two stay as they were.
On 20 December he brings 500 000 -> the line 17.09–17.10 is closed; 500 000 + 600 000 are still owed.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Max, Q, Sum
from django.utils import timezone

from crm.models import GroupEnrollment, Student, StudentFreeze
from crm.pricing import price_on
from finance.models import Payment, PaymentAllocation, StudentCharge

OPEN = StudentCharge.Status.OPEN
WRITTEN_OFF = StudentCharge.Status.WRITTEN_OFF

MAX_NEW_LINES = 240  # 20 years of months: a guard against an endless loop, never a real limit
# Nobody pays for more than two years ahead. Money beyond that waits in the копилка — and a sum typed with
# extra zeros (or a price typed without them) cannot write hundreds of "paid" months
MAX_MONTHS_AHEAD = 24
# Owner (2026-10-05): a discount is free, but never more than half of the month's price
MAX_DISCOUNT_PERCENT = 50
GONE = (Student.Status.LEFT, Student.Status.GRADUATED)


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def add_months(d: date, months: int) -> date:
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def months_days_between(start: date, end: date) -> tuple[int, int]:
    """(whole months, leftover days) from start to end, end >= start."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    while months > 0 and add_months(start, months) > end:
        months -= 1
    return months, (end - add_months(start, months)).days


def next_boundary(d: date, pay_day: int) -> date:
    """The student's pay day in the month after `d` (31 -> 28 February -> 31 March: the day never drifts)."""
    year = d.year + d.month // 12
    month = d.month % 12 + 1
    return date(year, month, min(pay_day, calendar.monthrange(year, month)[1]))


def anchor_of(student: Student) -> date:
    """The day the student's first month starts: the start date, else the day the card was created."""
    start = student.trial_date
    if isinstance(start, str):  # a caller holding the date as text (Student(trial_date='2026-09-01'))
        start = date.fromisoformat(start[:10])
    return start or timezone.localtime(student.created_at).date()


def freeze_day(student: Student) -> date | None:
    return timezone.localtime(student.frozen_at).date() if student.frozen_at else None


def left_day(student: Student, today: date | None = None) -> date:
    """The day a student left or finished (the journal of groups keeps it for those who finished)."""
    if student.left_at:
        return timezone.localtime(student.left_at).date()
    last = GroupEnrollment.objects.filter(student=student, left_date__isnull=False).order_by('-left_date').first()
    return last.left_date if last else (today or timezone.localdate())


def payment_day(payment: Payment) -> date:
    return payment.payment_date or timezone.localtime(payment.created_at).date()


def _limit(student: Student, today: date) -> tuple[date | None, bool]:
    """
    Until which day new months of the student start: (day, strict).
    Studying — a month's line appears on its first day. Frozen / left — only months that had already begun
    (the pause or the leaving on the very first day of a month does not start it). After a trial — never.
    """
    if student.status == Student.Status.STUDYING:
        return today, False
    if student.status == Student.Status.FROZEN:
        return freeze_day(student) or today, True
    if student.status in GONE:
        return left_day(student, today), True
    return None, True


def _may_start(start: date, limit: date | None, strict: bool) -> bool:
    if limit is None:
        return False
    return start < limit if strict else start <= limit


# ---------------------------------------------------------------------------
# Creating lines
# ---------------------------------------------------------------------------

def _group_on(student: Student, day: date):
    """The group the student was in on `day` (history of groups); else the first later one; else the current."""
    history = GroupEnrollment.objects.filter(student=student).select_related('group__course')
    then = history.filter(joined_date__lte=day).filter(
        Q(left_date__isnull=True) | Q(left_date__gt=day),
    ).order_by('-joined_date', '-id').first()
    if then is not None:
        return then.group
    later = history.filter(joined_date__gt=day).order_by('joined_date', 'id').first()
    if later is not None:
        return later.group
    return student.group if student.group_id else None


def _lessons_planned(group, start: date, end: date) -> int:
    if group is None:
        return 0
    from finance.payroll import lesson_days

    return len(lesson_days(group, start, end - timedelta(days=1)))


def _next_start(student: Student, last: StudentCharge | None) -> tuple[date, int]:
    start = last.period_end if last else anchor_of(student)
    pay_day = last.pay_day if last else start.day
    resume = student.charge_resume_date
    if resume and start < resume:
        # Came back from a freeze between two months: the next month starts on the day of return
        start, pay_day = resume, resume.day
    return start, pay_day


def _new_line(student: Student, last: StudentCharge | None, priced_on: date | None = None) -> StudentCharge | None:
    """
    The next month of the student. `priced_on` — the day of a payment made in advance: a month that has not
    begun yet is fixed at the price of that day. No group with a price -> None (the month waits for the price).
    """
    start, pay_day = _next_start(student, last)
    day = min(start, priced_on) if priced_on else start
    group = _group_on(student, day)
    course = group.course if group is not None and group.course_id else None
    price = price_on(course, day) if course is not None else 0
    if price <= 0:
        return None
    end = next_boundary(start, pay_day)
    try:
        with transaction.atomic():
            return StudentCharge.objects.create(
                company_id=student.company_id, student=student, group=group, course=course,
                seq=(last.seq + 1) if last else 0, period_start=start, period_end=end, pay_day=pay_day,
                price=price, discount=0, amount=price, lessons_planned=_lessons_planned(group, start, end),
            )
    except IntegrityError:
        return None  # somebody else has just written this month


def ensure_charges(student: Student, today: date | None = None) -> list[StudentCharge]:
    """Write the lines of every month of the student that has begun and has no line yet."""
    today = today or timezone.localdate()
    limit, strict = _limit(student, today)
    if limit is None:
        return []
    last = StudentCharge.objects.filter(student=student).order_by('-seq').first()
    created = []
    for _ in range(MAX_NEW_LINES):
        start, _pay_day = _next_start(student, last)
        if not _may_start(start, limit, strict):
            break
        line = _new_line(student, last)
        if line is None:
            break
        created.append(line)
        last = line
    return created


# ---------------------------------------------------------------------------
# Money on lines
# ---------------------------------------------------------------------------

def _allocate(student: Student, today: date) -> None:
    lines = list(StudentCharge.objects.select_for_update().filter(student=student).order_by('seq'))
    payments = sorted(
        Payment.objects.filter(student=student, transaction_type=Payment.TransactionType.PAYMENT),
        key=lambda p: (payment_day(p), p.created_at, p.id),
    )
    refunded = dict(
        Payment.objects.filter(
            reverses_payment__in=[p.id for p in payments], transaction_type=Payment.TransactionType.REFUND,
        ).values('reverses_payment').annotate(total=Sum('amount')).values_list('reverses_payment', 'total')
    )
    limit, strict = _limit(student, today)
    can_prepay = student.status in Student.CURRENT_STATUSES

    paid = {line.id: 0 for line in lines}
    # Discounts are facts of payments: every pass gives them to the lines again
    discount = {line.id: 0 if line.status == OPEN else line.discount for line in lines}
    # How much a line takes: its price (minus discounts, below); a written-off line keeps only the money
    # that was already on it — the rest of it was forgiven
    amount = {line.id: line.price if line.status == OPEN else line.paid_amount for line in lines}
    paid_at: dict[int, date] = {}
    closed_by = {p.id: 0 for p in payments}
    given_back = {}
    parts: dict[tuple[int, int], int] = {}
    waiting = 0  # money that found no line (no course price yet, or an overpayment of a student who left)
    index = 0
    ahead = sum(1 for line in lines if line.period_start > today)
    for payment in payments:
        back = min(refunded.get(payment.id) or 0, payment.amount or 0)
        given_back[payment.id] = back
        value = max(0, (payment.amount or 0) - back)
        day = payment_day(payment)
        # The discount of this payment: spread over the months it was given for, the oldest it pays first
        off_left = max(0, payment.discount_amount or 0)
        off_months = max(1, payment.discount_months or 1)
        off_each = off_left // off_months
        off_given: set[int] = set()
        while value > 0:
            while index < len(lines) and paid[lines[index].id] >= amount[lines[index].id]:
                index += 1
            if index == len(lines):
                line = None
                if can_prepay and ahead < MAX_MONTHS_AHEAD:
                    line = _new_line(student, lines[-1] if lines else None, priced_on=day)
                if line is None:
                    break
                lines.append(line)
                paid[line.id], discount[line.id], amount[line.id] = 0, 0, line.price
                if line.period_start > today:
                    ahead += 1
            line = lines[index]
            if line.status == OPEN and off_left > 0 and off_months > 0 and line.id not in off_given:
                off_given.add(line.id)
                room = line.price * MAX_DISCOUNT_PERCENT // 100 - discount[line.id]
                give = max(0, min(off_each if off_months > 1 else off_left, room, amount[line.id] - paid[line.id]))
                discount[line.id] += give
                amount[line.id] -= give
                off_left -= give
                off_months -= 1
            part = min(value, amount[line.id] - paid[line.id])
            if part > 0:
                parts[(payment.id, line.id)] = parts.get((payment.id, line.id), 0) + part
                paid[line.id] += part
                value -= part
            if line.status == OPEN and paid[line.id] >= amount[line.id]:
                paid_at[line.id] = day
                closed_by[payment.id] += 1
        waiting += value

    # A month ahead that holds no money any more (the advance payment was removed or given back) is not
    # a line yet: it will be written on its first day, at the price of that day
    while lines:
        line = lines[-1]
        if line.status == OPEN and paid[line.id] == 0 and not _may_start(line.period_start, limit, strict):
            line.delete()
            lines.pop()
        else:
            break

    kept = {line.id for line in lines}
    PaymentAllocation.objects.filter(charge__student=student).delete()
    PaymentAllocation.objects.bulk_create([
        PaymentAllocation(payment_id=payment_id, charge_id=line_id, amount=amount)
        for (payment_id, line_id), amount in parts.items() if line_id in kept and amount > 0
    ])
    for line in lines:
        if line.status != OPEN:
            if line.paid_amount != paid[line.id]:
                StudentCharge.objects.filter(pk=line.pk).update(paid_amount=paid[line.id])
            continue
        new = (paid[line.id], paid_at.get(line.id), discount[line.id], amount[line.id])
        if (line.paid_amount, line.paid_at, line.discount, line.amount) != new:
            StudentCharge.objects.filter(pk=line.pk).update(
                paid_amount=new[0], paid_at=new[1], discount=new[2], amount=new[3],
            )
    for payment in payments:
        if (
            payment.months_covered != closed_by[payment.id]
            or payment.refunded_amount != given_back[payment.id]
            or payment.refunded_months
        ):
            # Kept for the lists and receipts: how many months this payment closed
            Payment.objects.filter(pk=payment.pk).update(
                months_covered=closed_by[payment.id], refunded_amount=given_back[payment.id], refunded_months=0,
            )
    # "Копилка": money already brought towards a month that is not paid in full yet
    wallet = waiting + sum(
        paid[line.id] for line in lines if line.status == OPEN and 0 < paid[line.id] < amount[line.id]
    )
    if student.wallet_amount != wallet:
        Student.objects.filter(pk=student.pk).update(wallet_amount=wallet)
        student.wallet_amount = wallet


def reallocate(student: Student | None, today: date | None = None) -> None:
    """Bring the student's lines up to date and spread their payments over them again (oldest line first)."""
    if student is None or student.pk is None:
        return
    today = today or timezone.localdate()
    with transaction.atomic():
        ensure_charges(student, today)
        _allocate(student, today)


def refresh(student: Student, today: date | None = None) -> None:
    """Cheap check before reading: a new month has begun -> write its line and count the money waiting for it."""
    if student is None or student.pk is None:
        return
    today = today or timezone.localdate()
    if ensure_charges(student, today):
        with transaction.atomic():
            _allocate(student, today)


def rebuild(student: Student) -> None:
    """The start date was corrected: the months are written again from the new date."""
    with transaction.atomic():
        StudentCharge.objects.filter(student=student).delete()
        reallocate(student)


def shift_after_freeze(student: Student, frozen_on: date, resume_on: date) -> None:
    """
    The student came back from a freeze. The month that was running when they were frozen continues from
    the day of return with exactly what was left of it (months + days); months paid in advance follow it.
    Lines of earlier months are history and stay as they are — an unpaid one is still a debt.
    """
    with transaction.atomic():
        lines = list(StudentCharge.objects.select_for_update().filter(student=student).order_by('seq'))
        # A month that began on the day of freezing or later had not really begun (the same rule as when
        # lines are written): if nobody paid anything for it, it is not a line
        while lines and lines[-1].status == OPEN and lines[-1].paid_amount == 0 and lines[-1].period_start >= frozen_on:
            lines.pop().delete()
        running = next((i for i, line in enumerate(lines) if line.period_start <= frozen_on < line.period_end), None)
        if running is not None and resume_on > frozen_on:
            line = lines[running]
            months, days = months_days_between(frozen_on, line.period_end)
            line.period_end = add_months(resume_on, months) + timedelta(days=days)
            line.pay_day = line.period_end.day
            line.save(update_fields=['period_end', 'pay_day'])
            previous = line
            for later in lines[running + 1:]:
                later.period_start = previous.period_end
                later.pay_day = previous.pay_day
                later.period_end = next_boundary(later.period_start, later.pay_day)
                later.save(update_fields=['period_start', 'period_end', 'pay_day'])
                previous = later
        Student.objects.filter(pk=student.pk).update(charge_resume_date=resume_on)
        student.charge_resume_date = resume_on


def resume_from(student: Student, day: date) -> None:
    """
    The student is back after leaving: the months of absence are not charged — the next month starts on the
    day of return (a month that was running when they left simply goes on). Old unpaid lines stay a debt.
    """
    Student.objects.filter(pk=student.pk).update(charge_resume_date=day)
    student.charge_resume_date = day


def write_off(student: Student, before: date) -> int:
    """The CEO forgave the debt of a student who left: the unpaid lines up to that day are closed as written off."""
    lines = StudentCharge.objects.filter(student=student, status=OPEN, period_start__lt=before)
    ids = [line.id for line in lines if line.paid_amount < line.amount]
    StudentCharge.objects.filter(pk__in=ids).update(status=WRITTEN_OFF)
    return len(ids)


class _Undo(Exception):
    pass


def preview_payment(student: Student, money: int, discount: int = 0, months: int = 1, day: date | None = None) -> dict:
    """
    What a payment WOULD do, counted by the very same code that counts a real one: the payment is written,
    the lines are recounted, the result is read — and everything is rolled back. Nothing is saved.
    """
    today = timezone.localdate()
    refresh(student, today)

    def owed(lines):
        return sum(line.amount - line.paid_amount for line in lines if _unpaid(line) and line.period_start <= today)

    before = student_lines(student)
    result = {
        'debt_before': owed(before), 'debt_after': owed(before), 'closes': [], 'months_closed': 0,
        'waiting': 0, 'next_payment_date': schedule(student, before)['next_due'].isoformat(),
    }
    if money <= 0:
        return result
    had = {line.id: line.paid_amount for line in before}
    try:
        with transaction.atomic():
            payment = Payment.objects.create(
                company_id=student.company_id, student=student, student_name=student.full_name, amount=money,
                discount_amount=max(0, discount), discount_months=max(1, months), payment_date=day or today,
                transaction_type=Payment.TransactionType.PAYMENT, months_covered=0,
            )  # the post_save signal spreads it over the lines
            after = StudentCharge.objects.filter(student=student).order_by('seq')
            taken = dict(PaymentAllocation.objects.filter(payment=payment).values_list('charge_id', 'amount'))
            lines = list(after)
            for line in lines:
                if line.id not in taken:
                    continue
                result['closes'].append({
                    'period_start': line.period_start.isoformat(),
                    'period_end': line.period_end.isoformat(),
                    'price': line.price,
                    'discount': line.discount,
                    'amount': line.amount,
                    'paid_before': had.get(line.id, 0),
                    'pays': taken[line.id],
                    'left_after': max(0, line.amount - line.paid_amount),
                    'ahead': line.period_start > today,
                })
            result['months_closed'] = Payment.objects.get(pk=payment.pk).months_covered
            result['waiting'] = money - sum(taken.values())
            result['debt_after'] = owed(lines)
            result['next_payment_date'] = schedule(student, lines)['next_due'].isoformat()
            raise _Undo
    except _Undo:
        pass
    student.refresh_from_db(fields=['wallet_amount'])
    return result


def reprice_unpaid(course, old_price: int, new_price: int, valid_from: date | None, valid_until: date | None) -> tuple[int, int]:
    """
    A price record was typed wrong and the CEO fixed it ("500" instead of "500 000"): the lines written at the
    wrong price in the days of that record get the right one — but only lines nobody has paid anything for.
    A line with money on it is a fact already agreed with the parent and stays. Returns (fixed, left as is).
    """
    lines = StudentCharge.objects.filter(course=course, status=OPEN, price=old_price, discount=0)
    if valid_from is not None:
        lines = lines.filter(period_start__gte=valid_from)
    if valid_until is not None:
        lines = lines.filter(period_start__lt=valid_until)
    untouched = lines.exclude(paid_amount=0).count()
    fixed = lines.filter(paid_amount=0).update(price=new_price, amount=new_price)
    return fixed, untouched


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def student_lines(student: Student) -> list[StudentCharge]:
    return list(StudentCharge.objects.filter(student=student).order_by('seq'))


def company_lines(company_id: int) -> dict[int, list[StudentCharge]]:
    """Lines of every student of the company in one query: student id -> lines in order."""
    result: dict[int, list[StudentCharge]] = {}
    for line in StudentCharge.objects.filter(company_id=company_id).order_by('student_id', 'seq'):
        result.setdefault(line.student_id, []).append(line)
    return result


def student_freezes(student: Student) -> list[tuple[date, date]]:
    return list(StudentFreeze.objects.filter(student=student, end_date__isnull=False).values_list('start_date', 'end_date'))


def company_freezes(company_id: int) -> dict[int, list[tuple[date, date]]]:
    result: dict[int, list[tuple[date, date]]] = {}
    for student_id, start, end in StudentFreeze.objects.filter(
        company_id=company_id, end_date__isnull=False,
    ).values_list('student_id', 'start_date', 'end_date'):
        result.setdefault(student_id, []).append((start, end))
    return result


def _paused_days(freezes, start: date, end: date) -> int:
    """Days of finished freezes inside [start, end]: a pause never adds days of delay."""
    total = 0
    for began, ended in freezes or ():
        overlap = (min(ended, end) - max(began, start)).days
        if overlap > 0:
            total += overlap
    return total


def _unpaid(line: StudentCharge) -> bool:
    return line.status == OPEN and line.paid_amount < line.amount


def schedule(student: Student, lines=None, freezes=None, today: date | None = None) -> dict:
    """
    Where the student stands: the day the next payment is due, whether they are a debtor and by how much.
    Studying — as of today; frozen — as of the day of freezing (the pause adds no debt); others are not debtors
    here (who left with a debt is shown by debt_on()).
    """
    today = today or timezone.localdate()
    if lines is None:
        lines = student_lines(student)
    first_unpaid = next((line for line in lines if _unpaid(line)), None)
    if first_unpaid is not None:
        next_due = first_unpaid.period_start
    else:
        next_due = lines[-1].period_end if lines else anchor_of(student)
        if student.charge_resume_date and next_due < student.charge_resume_date:
            next_due = student.charge_resume_date

    if student.status == Student.Status.STUDYING:
        check = today
    elif student.status == Student.Status.FROZEN:
        check = freeze_day(student) or today
    else:
        check = None
    is_debtor = check is not None and check > next_due
    owed = [line for line in lines if _unpaid(line) and line.period_start < check] if is_debtor else []
    overdue = 0
    if is_debtor:
        if freezes is None:
            freezes = student_freezes(student)
        overdue = max(0, (check - next_due).days - _paused_days(freezes, next_due, check))
    return {
        'next_due': next_due,
        'is_debtor': is_debtor,
        'overdue_days': overdue,
        'paid_count': sum(1 for line in lines if line.status == OPEN and 0 < line.amount <= line.paid_amount),
        'debt_months': len(owed),
        'debt_amount': sum(line.amount - line.paid_amount for line in owed),
    }


def debt_on(student: Student, on_date: date | None = None, lines=None) -> dict | None:
    """
    What the student owes on `on_date` (default: the day they left, or today), whatever their status:
    the lines of months that had begun by that day and are not paid in full. None when nothing is owed.
    """
    if on_date is None:
        on_date = timezone.localtime(student.left_at).date() if student.left_at else timezone.localdate()
    if lines is None:
        lines = student_lines(student)
    owed = [line for line in lines if _unpaid(line) and line.period_start < on_date]
    if owed:
        prices = {line.amount for line in owed}
        return {
            'unpaid_since': owed[0].period_start,
            'months': len(owed),
            'days': (on_date - owed[0].period_start).days,
            # One price for every owed month, else 0 ("N × price" cannot be written)
            'monthly_price': prices.pop() if len(prices) == 1 else 0,
            'approx_amount': sum(line.amount - line.paid_amount for line in owed),
        }
    if lines:
        return None
    # No line at all: the student never had a group with a price. The months are still counted by the calendar
    due = anchor_of(student)
    if student.charge_resume_date and due < student.charge_resume_date:
        due = student.charge_resume_date
    if on_date <= due:
        return None
    months = 1
    while add_months(due, months) < on_date:
        months += 1
    return {'unpaid_since': due, 'months': months, 'days': (on_date - due).days, 'monthly_price': 0, 'approx_amount': 0}


def written_off(lines) -> dict | None:
    """Months the CEO wrote off: how many and what sum was forgiven."""
    gone = [line for line in lines if line.status == WRITTEN_OFF]
    if not gone:
        return None
    return {
        'months': len(gone),
        'amount': sum(max(0, line.amount - line.paid_amount) for line in gone),
        'since': gone[0].period_start,
    }


def serialize_lines(lines, today: date | None = None) -> list[dict]:
    """Lines for the student card, the newest first."""
    today = today or timezone.localdate()
    rows = []
    for line in lines:
        left = max(0, line.amount - line.paid_amount)
        if line.status == WRITTEN_OFF:
            state = 'written_off'
        elif left == 0:
            state = 'paid'
        elif line.period_start > today:
            state = 'ahead'      # a month paid partly in advance: not due yet
        elif line.paid_amount > 0:
            state = 'partial'
        else:
            state = 'unpaid'
        rows.append({
            'id': line.id,
            'period_start': line.period_start.isoformat(),
            'period_end': line.period_end.isoformat(),
            'group': line.group.name if line.group_id else '',
            'price': line.price,
            'discount': line.discount,
            'amount': line.amount,
            'paid': line.paid_amount,
            'left': left if line.status == OPEN else 0,
            'paid_at': line.paid_at.isoformat() if line.paid_at else None,
            'state': state,
        })
    rows.reverse()
    return rows


# ---------------------------------------------------------------------------
# Every day
# ---------------------------------------------------------------------------

def ensure_all(today: date | None = None) -> int:
    """
    Once a day: students whose next month has begun get its line. The first run after the update also
    writes the lines of everybody who has none yet (frozen, left, finished).
    """
    return ensure_for(Student.objects.all(), today)


def ensure_for(students, today: date | None = None) -> int:
    """Write the missing lines of these students (a group got a course, a course got a price, a new day came)."""
    today = today or timezone.localdate()
    need = students.exclude(status=Student.Status.LEFT_TRIAL).annotate(
        last_end=Max('charges__period_end'),
    ).filter(Q(last_end__isnull=True) | Q(status=Student.Status.STUDYING, last_end__lte=today))
    count = 0
    for student in need.select_related('group__course'):
        reallocate(student, today)
        count += 1
    return count


_done_day: date | None = None


def ensure_current() -> None:
    global _done_day
    today = timezone.localdate()
    if _done_day == today:
        return
    ensure_all(today)
    _done_day = today
    try:
        from crm.group_watch import check_groups

        check_groups(today)  # reminders about groups whose end date has passed / that are empty
    except Exception:
        import logging

        logging.getLogger(__name__).exception('Could not check the groups')


class DailyChargesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            ensure_current()
        except Exception:
            import logging

            logging.getLogger(__name__).exception('Could not write the lines of the new day')
        return self.get_response(request)
