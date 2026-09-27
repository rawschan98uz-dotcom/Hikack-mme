import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from crm.models import Student
from crm.services import sync_student_group_enrollment

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Student, dispatch_uid='crm_student_sync_group_enrollment')
def student_sync_group_enrollment(sender, instance: Student, created: bool, update_fields=None, raw=False, **kwargs):
    """Keep GroupEnrollment history in sync on every Student save (C1)."""
    if raw:
        return
    if update_fields is not None and not ({'group', 'group_id', 'status'} & set(update_fields)):
        return
    sync_student_group_enrollment(instance)


@receiver(post_save, sender=Student, dispatch_uid='crm_student_unpaid_leave_reminder')
def student_unpaid_leave_reminder(sender, instance: Student, created: bool, raw=False, **kwargs):
    """Left / finished with unpaid months -> reminder for administrators and the CEO."""
    if raw or created or not getattr(instance, '_just_left', False):
        return
    from crm.debts import remind_about_unpaid_leave

    try:
        # Re-read so dates are real dates (callers may hold strings in memory)
        remind_about_unpaid_leave(Student.objects.select_related('group__course', 'company').get(pk=instance.pk))
    except Exception:
        # A reminder must never block saving the student
        logger.exception('Could not create unpaid-leave reminder for student %s', instance.pk)
