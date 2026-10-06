"""
"Копилка": money a student has already brought towards a month that is not paid in full yet.

Since the month lines (finance/charges.py, 2026-10-05) the months are no longer counted here: every payment
closes the student's lines, the oldest first, and what does not close a whole month simply lies on the
next line. Student.wallet_amount is that money, kept for the student card and the payment form.
    Example with 800 000 a month: 1 200 000 -> the first month is closed, 400 000 lie on the next one.

Online payments (Click / Payme) of a student without a course price wait (Payment.month_price =
PRICE_PENDING): as soon as the student is in a group whose course has a price, the lines are written and
the money closes them by itself.
"""

from django.db.models import F, Q

from finance.models import Payment

# Payments that still count for the student (dates of payment, "paid this month"): not given back in full
ACTIVE_PAYMENT_Q = Q(amount__gt=F('refunded_amount'))


# Payment.month_price of a payment made while the course price was unknown (see _apply_known_price)
PRICE_PENDING = 0


def current_month_price(student) -> int:
    """Price of one month for the student right now: the course of their group (0 = unknown)."""
    group = getattr(student, 'group', None)
    course = getattr(group, 'course', None) if group else None
    return int(course.price or 0) if course else 0


def _apply_known_price(student) -> None:
    """Money was waiting for a course price: the price is known now -> the office reminder is closed."""
    pending = Payment.objects.filter(
        student=student, transaction_type=Payment.TransactionType.PAYMENT, month_price=PRICE_PENDING,
    )
    if not pending.exists():
        return
    price = current_month_price(student)
    if price <= 0:
        return
    pending.update(month_price=price)
    from operations.models import Reminder

    Reminder.objects.filter(student=student, kind=Reminder.KIND_ONLINE_PAYMENT_CHECK).exclude(
        status=Reminder.Status.DONE,
    ).update(
        status=Reminder.Status.DONE,
        resolution=f'Цена курса известна ({price:,} сум) — деньги из копилки засчитаны автоматически'.replace(',', ' '),
    )


def recalc_student_wallet(student) -> int:
    """Spread the student's payments over their month lines again; returns the money left in the копилка."""
    if student is None or student.pk is None:
        return 0
    from finance.charges import reallocate

    _apply_known_price(student)
    reallocate(student)
    return student.wallet_amount or 0


def wallet_info(student) -> dict:
    """Копилка for the student card: money waiting and how much is missing to close a month."""
    price = current_month_price(student)
    wallet = student.wallet_amount or 0
    return {
        'wallet': wallet,
        'month_price': price,
        'wallet_missing': (price - wallet) if 0 < wallet < price else None,
    }
