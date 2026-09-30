import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from crm.models import Course, Group, Student
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
    if raw or created:
        return
    from crm.debts import close_on_return, remind_about_unpaid_leave

    if getattr(instance, '_just_returned', False):
        # Back to studying: the debt is now in the ordinary "Debtors" list
        close_on_return(instance)
        return
    if not getattr(instance, '_just_left', False):
        return
    try:
        # Re-read so dates are real dates (callers may hold strings in memory)
        remind_about_unpaid_leave(Student.objects.select_related('group__course', 'company').get(pk=instance.pk))
    except Exception:
        # A reminder must never block saving the student
        logger.exception('Could not create unpaid-leave reminder for student %s', instance.pk)


def _count_waiting_money(students) -> None:
    """Online money waiting in the копилка for a course price: count it once the price is known."""
    from finance.models import Payment
    from finance.wallet import PRICE_PENDING, recalc_student_wallet

    waiting = Payment.objects.filter(
        student__in=students, month_price=PRICE_PENDING, transaction_type=Payment.TransactionType.PAYMENT,
    ).values_list('student_id', flat=True).distinct()
    for student in Student.objects.filter(pk__in=list(waiting)).select_related('group__course'):
        try:
            recalc_student_wallet(student)
            from crm.services import sync_student_paid_this_month
            sync_student_paid_this_month(student)
        except Exception:
            logger.exception('Could not count waiting копилка money for student %s', student.pk)


@receiver(post_save, sender=Student, dispatch_uid='crm_student_count_waiting_money')
def student_count_waiting_money(sender, instance: Student, created: bool, raw=False, **kwargs):
    """The student was put into a group (with a price) -> money waiting in the копилка becomes months."""
    if raw or created:
        return
    _count_waiting_money([instance.pk])


@receiver(post_save, sender=Group, dispatch_uid='crm_group_count_waiting_money')
def group_count_waiting_money(sender, instance: Group, created: bool, raw=False, **kwargs):
    """The group got a course (with a price)."""
    if raw or created:
        return
    _count_waiting_money(Student.objects.filter(group=instance).values_list('pk', flat=True))


@receiver(post_save, sender=Course, dispatch_uid='crm_course_count_waiting_money')
def course_count_waiting_money(sender, instance: Course, created: bool, raw=False, **kwargs):
    """The course got a price."""
    if raw or created or not instance.price:
        return
    _count_waiting_money(Student.objects.filter(group__course=instance).values_list('pk', flat=True))


@receiver(post_save, sender=Student, dispatch_uid='crm_student_scores_follow_group')
def student_scores_follow_group(sender, instance: Student, created: bool, raw=False, **kwargs):
    """
    Owner (2026-09-28): a student moved to another group (or another branch) takes the grades along.
    Leaving the centre keeps the grades where they were — the rating simply does not show them,
    but the places of the classmates move up (ranks are recounted on every save of a graded student).
    """
    if raw or created:
        return
    from operations.models import StudentScore

    scores = StudentScore.objects.filter(student_id=instance.pk)
    groups = set(scores.values_list('group_id', flat=True))
    if not groups:
        return
    try:
        from api.v1.views_misc import _recalculate_ranks

        if instance.group_id is not None and groups != {instance.group_id}:
            # One grade per student in a group: if the student already has one in the new group
            # (came back to it), the most recent grade wins
            keep = scores.order_by('-updated_at', '-id').first()
            scores.exclude(pk=keep.pk).delete()
            if keep.group_id != instance.group_id:
                StudentScore.objects.filter(pk=keep.pk).update(
                    group_id=instance.group_id, company_id=instance.company_id,
                )
            groups.add(instance.group_id)
        for group_id in groups:
            _recalculate_ranks(instance.company, group_id)
    except Exception:
        # Moving grades must never block saving the student
        logger.exception('Could not move grades of student %s to the new group', instance.pk)


@receiver(post_save, sender=Student, dispatch_uid='crm_student_freeze_journal')
def student_freeze_journal(sender, instance: Student, created: bool, raw=False, **kwargs):
    """Freeze periods (crm.StudentFreeze): a teacher's salary does not count lessons of a frozen student."""
    if raw:
        return
    from django.utils import timezone
    from crm.models import StudentFreeze

    today = timezone.localdate()
    if getattr(instance, '_freeze_ended', False):
        StudentFreeze.objects.filter(student=instance, end_date__isnull=True).update(end_date=today)
    if getattr(instance, '_freeze_started', False):
        start = timezone.localtime(instance.frozen_at).date() if instance.frozen_at else today
        if not StudentFreeze.objects.filter(student=instance, end_date__isnull=True).exists():
            StudentFreeze.objects.create(company_id=instance.company_id, student=instance, start_date=start)
