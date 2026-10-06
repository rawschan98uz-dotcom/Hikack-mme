"""Refunds: money given back leaves the student's month lines (finance/charges.py)."""

from django.db.models import Sum

from finance.models import Payment


def recalc_refunded_months(payment: Payment) -> int:
    """
    The refunds of `payment` changed (a refund was made, edited or removed, or the payment itself was edited).
    The money that is left of the payment is spread over the student's lines again: a refund reopens
    the newest months it had closed. Example: 3 months paid, one month's price given back -> 2 months paid.
    """
    refunded = payment.reversals.filter(
        transaction_type=Payment.TransactionType.REFUND,
    ).aggregate(total=Sum('amount'))['total'] or 0
    refunded = min(refunded, payment.amount or 0)
    if payment.refunded_amount != refunded or payment.refunded_months:
        Payment.objects.filter(pk=payment.pk).update(refunded_amount=refunded, refunded_months=0)
        payment.refunded_amount, payment.refunded_months = refunded, 0
    if payment.student_id:
        from finance.charges import reallocate

        reallocate(payment.student)
    return 0
