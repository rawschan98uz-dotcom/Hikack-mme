from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from finance.models import Payment


def _spread_again(instance: Payment, raw: bool = False) -> None:
    """Money of a student appeared, changed or disappeared: spread it over their month lines again."""
    if raw or instance.student_id is None:
        return
    from crm.models import Student
    from finance.charges import reallocate

    student = Student.objects.filter(pk=instance.student_id).select_related('group__course').first()
    if student is not None:
        reallocate(student)


@receiver(post_save, sender=Payment, dispatch_uid='finance_payment_lines_saved')
def payment_saved(sender, instance: Payment, raw=False, **kwargs):
    _spread_again(instance, raw)


@receiver(post_delete, sender=Payment, dispatch_uid='finance_payment_lines_deleted')
def payment_deleted(sender, instance: Payment, **kwargs):
    _spread_again(instance)
