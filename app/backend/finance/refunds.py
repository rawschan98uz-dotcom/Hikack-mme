"""How refunds change the paid period of a payment (owner's rule, 2026-09-27)."""

from django.db.models import F, Sum

from finance.models import Payment


def months_taken_back(payment: Payment, refunded_total: int) -> int:
    """
    Whole months a refund takes back: refunded sum // price of one month of THIS payment
    (amount / months_covered, so a discounted payment uses its discounted monthly price).
    A full refund takes back every month.
    """
    months = payment.months_covered or 0
    if months <= 0 or refunded_total <= 0 or not payment.amount:
        return 0
    if refunded_total >= payment.amount:
        return months
    return min(months, refunded_total * months // payment.amount)


def recalc_refunded_months(payment: Payment) -> int:
    """
    Apply the refunds of `payment`.
    Копилка payments: the refunded money leaves the student's копилка / months (finance/wallet.py).
    Hand-entered payments: whole months are taken back (problem 3, option B). Returns months taken back.
    """
    refunded_total = payment.reversals.filter(
        transaction_type=Payment.TransactionType.REFUND,
    ).aggregate(total=Sum('amount'))['total'] or 0

    if payment.month_price is not None:
        from finance.wallet import recalc_student_wallet

        refunded_total = min(refunded_total, payment.amount or 0)
        if payment.refunded_amount != refunded_total:
            payment.refunded_amount = refunded_total
            payment.save(update_fields=['refunded_amount'])
        recalc_student_wallet(payment.student)
        return 0

    value = months_taken_back(payment, refunded_total)
    if payment.refunded_months != value:
        payment.refunded_months = value
        payment.save(update_fields=['refunded_months'])
    return value


# Months of a payment that still count after refunds
EFFECTIVE_MONTHS = F('months_covered') - F('refunded_months')
