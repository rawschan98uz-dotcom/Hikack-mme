from django.db.models.signals import post_save
from django.dispatch import receiver

from crm.models import Student
from crm.services import sync_student_group_enrollment


@receiver(post_save, sender=Student, dispatch_uid='crm_student_sync_group_enrollment')
def student_sync_group_enrollment(sender, instance: Student, created: bool, update_fields=None, raw=False, **kwargs):
    """Keep GroupEnrollment history in sync on every Student save (C1)."""
    if raw:
        return
    if update_fields is not None and not ({'group', 'group_id', 'status'} & set(update_fields)):
        return
    sync_student_group_enrollment(instance)
