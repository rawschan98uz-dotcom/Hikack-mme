"""
A group's end date is a plan, not a switch (owner, 2026-10-05).

It used to stop the group silently: after that day nobody could mark a lesson or attendance, the teacher's
salary for it became 0, and the group still looked alive. Now the date blocks nothing — a group is closed
only by a person — and the office is reminded once a day:
  * the end date has passed but students still study in the group -> "extend the date or close the group";
  * nobody is left in a group that had students -> "close the group?".
A reminder closes by itself when its reason is gone, and is not repeated once somebody has answered it.
"""

from __future__ import annotations

from datetime import date, datetime, time

from django.db.models import Count, Max, Q
from django.utils import timezone

from crm.models import Group, Student
from operations.models import Reminder

GROUP_KINDS = (Reminder.KIND_GROUP_END_PASSED, Reminder.KIND_GROUP_EMPTY)


def _since(day: date):
    return timezone.make_aware(datetime.combine(day, time.min))


def _sync(group: Group, kind: str, wanted: bool, since: date | None, title: str, details: str, today: date) -> None:
    open_ones = Reminder.objects.filter(group=group, kind=kind).exclude(status=Reminder.Status.DONE)
    if not wanted:
        open_ones.update(status=Reminder.Status.DONE, resolution='Закрыто автоматически: причина исчезла')
        return
    if open_ones.exists():
        open_ones.update(title=title[:Reminder.TITLE_MAX_LENGTH], details=details)
        return
    # Somebody has already answered a reminder about this very situation: do not nag again
    answered = Reminder.objects.filter(group=group, kind=kind)
    if since is not None:
        answered = answered.filter(created_at__gte=_since(since))
    if answered.exists():
        return
    Reminder.objects.create(
        company_id=group.company_id, group=group, kind=kind, title=title[:Reminder.TITLE_MAX_LENGTH],
        details=details, due_date=today, status=Reminder.Status.TODAY,
    )


def check_groups(today: date | None = None) -> None:
    today = today or timezone.localdate()
    groups = Group.objects.filter(status=Group.Status.ACTIVE).annotate(
        current=Count('students', filter=Q(students__status__in=Student.CURRENT_STATUSES), distinct=True),
        ever=Count('enrollments', distinct=True),
        last_left=Max('enrollments__left_date'),
    )
    for group in groups:
        end = group.group_end_date
        _sync(
            group, Reminder.KIND_GROUP_END_PASSED,
            wanted=bool(end and end < today and group.current > 0),
            since=end,
            title=f'Срок группы «{group.name}» вышел, а в ней учатся: {group.current}',
            details=(
                f'Дата окончания группы была {end.strftime("%d.%m.%Y")}. Уроки и посещаемость отмечаются как обычно.\n'
                'Продлите дату окончания в карточке группы или закройте группу, когда ученики закончат.'
            ) if end else '',
            today=today,
        )
        _sync(
            group, Reminder.KIND_GROUP_EMPTY,
            wanted=group.current == 0 and group.ever > 0,
            since=group.last_left,
            title=f'В группе «{group.name}» не осталось учеников',
            details=(
                'Если набор в группу закончен — закройте её: Groups → группа → статус «В архиве».\n'
                'Если группа ждёт новых учеников, просто отметьте это напоминание выполненным.'
            ),
            today=today,
        )
    # A closed group needs no reminders any more
    Reminder.objects.filter(kind__in=GROUP_KINDS, group__status=Group.Status.ARCHIVE).exclude(
        status=Reminder.Status.DONE,
    ).update(status=Reminder.Status.DONE, resolution='Закрыто автоматически: группа в архиве')
