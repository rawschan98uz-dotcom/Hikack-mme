"""Salary setting rules shared by payroll summary and payout (D8)."""

from django.db.models import Q

from finance.models import SalarySetting


def _period_overlap_q(start_date, end_date) -> Q:
    q = Q()
    if end_date is not None:
        q &= Q(effective_from__isnull=True) | Q(effective_from__lte=end_date)
    if start_date is not None:
        q &= Q(effective_to__isnull=True) | Q(effective_to__gte=start_date)
    return q


def find_overlapping_setting(company, teacher, course_id, group_id, effective_from, effective_to, exclude_pk=None):
    """Another setting for the same teacher and scope whose period intersects the given one."""
    if teacher is None:
        return None
    qs = SalarySetting.objects.filter(
        company=company, teacher=teacher, course_id=course_id, group_id=group_id,
    ).filter(_period_overlap_q(effective_from, effective_to))
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.first()


def overlap_error(setting: SalarySetting) -> str:
    start = setting.effective_from.isoformat() if setting.effective_from else '…'
    end = setting.effective_to.isoformat() if setting.effective_to else '…'
    return f'У учителя уже есть ставка на пересекающийся период ({start} — {end}). Сначала закройте её датой окончания.'


