"""Salary setting rules shared by payroll summary and payout (D8)."""

from django.db.models import F, Q

from finance.models import SalarySetting


def _period_overlap_q(start_date, end_date) -> Q:
    q = Q()
    if end_date is not None:
        q &= Q(effective_from__isnull=True) | Q(effective_from__lte=end_date)
    if start_date is not None:
        q &= Q(effective_to__isnull=True) | Q(effective_to__gte=start_date)
    return q


def _by_seniority(qs):
    # Precedence: the most recently started period wins; open start (NULL) is the oldest; then newest record.
    return qs.order_by(F('effective_from').desc(nulls_last=True), '-id')


def resolve_salary_setting(company, teacher, start_date, end_date) -> SalarySetting | None:
    """The single salary setting that applies to `teacher` for the period [start_date, end_date]."""
    period = _period_overlap_q(start_date, end_date)
    setting = _by_seniority(SalarySetting.objects.filter(company=company, teacher=teacher).filter(period)).first()
    if setting:
        return setting

    # Legacy settings saved only with a teacher name
    name = teacher.display_name().strip().lower()
    for candidate in _by_seniority(SalarySetting.objects.filter(company=company, teacher__isnull=True).filter(period)):
        if candidate.teacher_name.strip().lower() == name:
            return candidate
    return None


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
