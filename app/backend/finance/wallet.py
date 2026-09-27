"""
"Копилка" (owner's choice, 2026-09-27): the program counts whole months from the money itself.

Every payment adds money (paid + discount − refunded). Each time the money reaches the price
of one month, a month is closed; whatever is left waits in the student's копилка for the next
payment. Example with 800 000 a month:
    1 200 000 -> 1 month closed, 400 000 in the копилка
    +400 000  -> копилка reaches 800 000 -> one more month, копилка 0
    500 000   -> no month, 500 000 in the копилка ("не хватает 300 000")

Payments made before the копилка existed, and payments of students without a course price,
keep the months an administrator entered by hand (Payment.month_price IS NULL) and do not touch
the копилка.
"""

from django.db.models import F, Q

from finance.models import Payment

# Payments that still count for the student (dates of payment, "paid this month", debts):
#   копилка payments  -> not refunded in full;
#   hand-entered ones -> at least one month not taken back by refunds (problem 3, option B).
ACTIVE_PAYMENT_Q = (
    Q(month_price__isnull=False, amount__gt=F('refunded_amount'))
    | Q(month_price__isnull=True, refunded_months__lt=F('months_covered'))
)


def current_month_price(student) -> int:
    """Price of one month for the student right now: the course of their group (0 = unknown)."""
    group = getattr(student, 'group', None)
    course = getattr(group, 'course', None) if group else None
    return int(course.price or 0) if course else 0


def _chain(student):
    return Payment.objects.filter(
        student=student,
        transaction_type=Payment.TransactionType.PAYMENT,
        month_price__isnull=False,
    ).order_by('payment_date', 'created_at', 'id')


def recalc_student_wallet(student) -> int:
    """
    Recount the months closed by every копилка payment of the student (in date order) and the
    money left in the копилка. Stores Payment.months_covered and Student.wallet_amount.
    """
    if student is None or student.pk is None:
        return 0
    carry = 0
    for payment in _chain(student):
        value = max(0, (payment.amount or 0) + (payment.discount_amount or 0) - (payment.refunded_amount or 0))
        price = payment.month_price or 0
        total = carry + value
        months = total // price if price > 0 else 0
        carry = total - months * price
        if payment.months_covered != months or payment.refunded_months:
            Payment.objects.filter(pk=payment.pk).update(months_covered=months, refunded_months=0)
    if student.wallet_amount != carry:
        type(student).objects.filter(pk=student.pk).update(wallet_amount=carry)
        student.wallet_amount = carry
    return carry


def preview(student, amount: int, discount: int = 0) -> dict:
    """What a new payment would do: months it closes and what stays in the копилка."""
    price = current_month_price(student)
    if price <= 0:
        return {'price': 0, 'months': None, 'wallet_after': None}
    total = (student.wallet_amount or 0) + max(0, amount) + max(0, discount)
    months = total // price
    return {'price': price, 'months': months, 'wallet_after': total - months * price}


def wallet_info(student) -> dict:
    """Копилка for the student card: money waiting and how much is missing to close a month."""
    price = current_month_price(student)
    wallet = student.wallet_amount or 0
    return {
        'wallet': wallet,
        'month_price': price,
        'wallet_missing': (price - wallet) if (price > 0 and wallet > 0) else None,
    }
