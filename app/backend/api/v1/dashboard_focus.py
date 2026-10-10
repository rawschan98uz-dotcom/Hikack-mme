"""
The top of the dashboard, different for each role (owner, 2026-10):
  - the head (who sees company money): money today and this month, students' debts, new leads;
  - the administrator: today's lessons and whether they are marked, who came, whom to call;
  - the teacher: own lessons today with a "mark attendance" button.
Each block is sent only to those who may see it; the page shows whatever came.
"""

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from accounts.rbac import PERM_FINANCE_VIEW, PERM_LEADS_VIEW, user_has_permission, user_is_teacher
from api.scope import filter_attendance_queryset, scope_branch, scope_payments
from crm.models import AttendanceRecord, Group, Lead, Student
from finance.models import Payment

CALL_LIST_SIZE = 6
TRIALS_LIMIT = 10


def _time_label(group: Group) -> str:
    if group.lesson_start_time and group.lesson_end_time:
        return f"{group.lesson_start_time.strftime('%H:%M')} – {group.lesson_end_time.strftime('%H:%M')}"
    return group.lesson_start_time.strftime('%H:%M') if group.lesson_start_time else '—'


def _lessons_today(company, groups, today) -> list[dict]:
    """Groups that have a lesson today (schedule, start date, no holiday) and whether it is marked."""
    from api.v1.views_extended import _no_lesson_reason
    from operations.models import Holiday

    holiday_branches = set(
        Holiday.objects.filter(company=company, holiday_date=today).values_list('branch_id', flat=True),
    )
    lesson_groups = [
        g for g in groups.select_related('teacher', 'course', 'room').annotate(
            current_students=Count('students', filter=Q(students__status__in=Student.CURRENT_STATUSES)),
        )
        if g.branch_id not in holiday_branches and _no_lesson_reason(g, today) is None
    ]
    marked = set(
        AttendanceRecord.objects.filter(
            company=company, attend_date=today, group_id__in=[g.id for g in lesson_groups],
        ).values_list('group_id', flat=True),
    )
    lesson_groups.sort(key=lambda g: (g.lesson_start_time is None, g.lesson_start_time, g.name))
    return [
        {
            'group_id': g.id,
            'name': g.name,
            'time': _time_label(g),
            'course': g.course.name if g.course_id else None,
            'teacher': g.teacher.display_name() if g.teacher_id else None,
            'room': g.room.name if g.room_id else None,
            'students': g.current_students,
            'marked': g.id in marked,
        }
        for g in lesson_groups
    ]


def _net_payments(qs) -> int:
    totals = qs.aggregate(
        paid=Sum('amount', filter=Q(transaction_type=Payment.TransactionType.PAYMENT)),
        refunded=Sum('amount', filter=Q(transaction_type=Payment.TransactionType.REFUND)),
    )
    return int((totals['paid'] or 0) - (totals['refunded'] or 0))


def dashboard_focus(request, company, groups, debtors: list[tuple[Student, dict]] | None) -> dict:
    """`debtors` — current students who owe, with their payment info; None for those who see no money."""
    from api.v1.views import PAID_DAY

    user = request.user
    today = timezone.localdate()
    focus: dict = {'lessons_today': _lessons_today(company, groups, today)}

    marks = filter_attendance_queryset(
        AttendanceRecord.objects.filter(company=company, attend_date=today), user,
    ).aggregate(
        present=Count('id', filter=Q(status=AttendanceRecord.Status.PRESENT)),
        late=Count('id', filter=Q(status=AttendanceRecord.Status.LATE)),
        absent=Count('id', filter=Q(status=AttendanceRecord.Status.ABSENT)),
    )
    focus['attendance_today'] = marks

    if user_is_teacher(user):
        return focus

    if user_has_permission(user, PERM_LEADS_VIEW):
        leads = scope_branch(Lead.objects.filter(company=company), user)
        focus['new_leads'] = {
            'today': leads.filter(created_at__date=today).count(),
            'week': leads.filter(created_at__date__gte=today - timedelta(days=6)).count(),
        }
        focus['trials_today'] = [
            {
                'id': lead.id,
                'full_name': f'{lead.first_name} {lead.last_name}'.strip(),
                'phone': lead.phone,
                'course': lead.course.name if lead.course_id else None,
            }
            for lead in leads.filter(
                is_active=True, stage=Lead.Stage.TRIAL_BOOKED, trial_date=today,
            ).select_related('course').order_by('first_name')[:TRIALS_LIMIT]
        ]

    # Company money: the same rule as the revenue chart (the administrator does not see it, owner 2026-09-28)
    if user_has_permission(user, PERM_FINANCE_VIEW):
        payments = scope_payments(Payment.objects.filter(company=company), user).annotate(paid_day=PAID_DAY)
        focus['money'] = {
            'today': _net_payments(payments.filter(paid_day=today)),
            'month': _net_payments(payments.filter(paid_day__gte=today.replace(day=1), paid_day__lte=today)),
        }

    if debtors is not None:
        focus['debts'] = {
            'count': len(debtors),
            'total': sum(info.get('debt_amount') or 0 for _, info in debtors),
        }
        # Whom to call first: the longest overdue
        longest = sorted(debtors, key=lambda pair: pair[1].get('overdue_days') or 0, reverse=True)[:CALL_LIST_SIZE]
        focus['call_list'] = [
            {
                'id': student.id,
                'full_name': student.full_name,
                'phone': student.phone,
                'debt_amount': info.get('debt_amount') or 0,
                'overdue_days': info.get('overdue_days') or 0,
            }
            for student, info in longest
        ]
    return focus
