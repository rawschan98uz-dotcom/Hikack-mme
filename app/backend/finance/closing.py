"""
Closing a month (owner, 2026-09-29) — the rule of accounting systems like ERPNext / Odoo:
a month that is over and checked is closed by the CEO, and after that its numbers never change silently.

  * Salaries: an office worker's monthly sum is saved as it was at closing time (PayrollSnapshot).
    A teacher's month is counted from facts that cannot change any more — the lessons of the month are
    locked and every lesson gets its percent for good (stamp_percents) — so only a student's late payment
    adds to it ("the rest is paid when the students pay").
    A correction is a visible PayrollAdjustment (+/−, with a reason) — never a silent recount.
  * Money records dated in a closed month (payments, refunds, expenses, withdrawals, salary payout expenses)
    and teachers' lesson marks cannot be added, changed or deleted.
  * Only the CEO closes and reopens a month; both go to the journal.

Example: August is paid in full (576 923) and closed. In September the course price goes up —
August still shows 576 923, and the teacher is not suddenly "owed" 115 384.
"""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.utils import timezone

from finance.models import ClosedMonth, PayrollSnapshot

MONTH_NAMES = (
    'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
    'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
)


def month_key(day: date) -> str:
    return f'{day.year:04d}-{day.month:02d}'


def month_title(key: str) -> str:
    """'2026-08' -> 'Август 2026'."""
    year, month = key.split('-')
    return f'{MONTH_NAMES[int(month) - 1].capitalize()} {year}'


def closed_keys(company_id) -> set[str]:
    return set(ClosedMonth.objects.filter(company_id=company_id).values_list('month', flat=True))


def closed_error(company_id, *days) -> str | None:
    """Error text when any of the days falls in a closed month (None days are ignored), else None."""
    keys = {month_key(d) for d in days if d}
    if not keys:
        return None
    closed = sorted(keys & closed_keys(company_id))
    if not closed:
        return None
    title = month_title(closed[0])
    return (
        f'{title} закрыт: записи с датой в закрытом месяце нельзя добавлять, менять или удалять. '
        f'Проведите сегодняшней датой или попросите CEO открыть {title.split()[0].lower()} в разделе «Зарплаты».'
    )


def close_month(company, key: str, user) -> ClosedMonth:
    """Close a finished month: save everybody's salary for it. The caller checks the month is valid and over."""
    from accounts.models import User
    from finance.payroll import live_accrual, parse_month, payroll_people, stamp_percents

    _, start, end = parse_month(key)
    with transaction.atomic():
        closed = ClosedMonth.objects.create(company=company, month=key, closed_by=user)
        stamp_percents(company, start, end)
        for person in payroll_people(company, key, closed=None):
            if person.user_type == User.UserType.TEACHER:
                continue
            accrued, details = live_accrual(company, person, start, end)
            if accrued:
                PayrollSnapshot.objects.create(closed_month=closed, person=person, accrued=accrued, details=details)
    return closed


def month_is_over(key: str) -> bool:
    from finance.payroll import parse_month

    parsed = parse_month(key)
    return parsed is not None and parsed[2] < timezone.localdate()
