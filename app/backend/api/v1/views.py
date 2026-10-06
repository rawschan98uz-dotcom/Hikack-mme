import re
from datetime import date, datetime, time, timedelta

from django.contrib.auth import authenticate
from django.db.models import Count, F, Max, Min, Q, Sum
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import TeacherBranch, User
from accounts.rbac import (
    PERM_FINANCE_VIEW,
    ROLE_CEO,
    get_effective_role,
    get_role_label,
    get_user_permissions,
    user_has_permission,
    user_is_teacher,
)
from api.responses import fail, ok
from api.scope import (
    branch_allowed,
    branch_limit,
    branches_for,
    can_access_group,
    can_access_lead,
    can_access_student,
    filter_groups_queryset,
    filter_reminders_queryset,
    filter_students_queryset,
    scope_branch,
    scope_payments,
    strip_for_teacher,
)
from api.utils import (
    safe_int,
    normalize_phone,
    is_valid_phone,
    paginate_queryset,
    get_photo_url,
    parse_date_safe,
    parse_time_safe,
    validate_course_code,
)
from crm.models import Course, CoursePrice, Group, GroupEnrollment, Lead, Student
from crm.pricing import history as price_history, next_price, price_on, set_price, sync_course
from crm.services import (
    group_weekdays,
    sync_group_schedule_slots,
    validate_group_schedule,
)

from finance import charges
from crm.debts import unpaid_leave_state
from finance.wallet import ACTIVE_PAYMENT_Q, current_month_price, wallet_info
from finance.models import Payment, StudentCharge
from operations import notify as notifications
from operations.models import Reminder, Tag, log_audit
from org.models import Branch, Company, Room

SCHEDULE_DAY_KEYS = {
    Group.Days.ODD: 'odd',
    Group.Days.EVEN: 'even',
}


def _serialize_schedule_rows(groups) -> list[dict]:
    schedule = []
    for group in groups.select_related('teacher', 'course', 'branch').order_by(
        'lesson_start_time', 'name',
    ):
        if group.lesson_start_time and group.lesson_end_time:
            time_label = (
                f"{group.lesson_start_time.strftime('%H:%M')} – "
                f"{group.lesson_end_time.strftime('%H:%M')}"
            )
        elif group.lesson_start_time:
            time_label = group.lesson_start_time.strftime('%H:%M')
        else:
            time_label = '—'

        schedule.append({
            'id': group.id,
            'name': group.name,
            'days': group.days,
            'days_key': SCHEDULE_DAY_KEYS.get(group.days, 'other'),
            'weekdays': group_weekdays(group.days, group.weekdays),
            'days_label': group.get_days_display(),
            'time': time_label,
            'teacher': group.teacher.display_name() if group.teacher else '—',
            'course': group.course.name if group.course else '—',
            'branch': group.branch.name,
        })
    return schedule

VALID_LEAD_STAGES = {choice[0] for choice in Lead.Stage.choices}
VALID_GROUP_DAYS = {choice[0] for choice in Group.Days.choices}
VALID_GROUP_STATUSES = {choice[0] for choice in Group.Status.choices}
VALID_STUDENT_STATUSES = {choice[0] for choice in Student.Status.choices}


def _normalize_phone(phone: str) -> str:
    return normalize_phone(phone)


def _latest_converted_student(lead: Lead) -> Student | None:
    """The most recent student made from this lead (a lead can be re-converted after the student left)."""
    students = list(lead.converted_students.all())
    return max(students, key=lambda s: s.id) if students else None


def _active_student_duplicate(company, phone: str, first_name: str, last_name: str) -> Student | None:
    """An active student with the same phone and name (case-insensitive, Cyrillic too)."""
    from crm.services import get_phone_variants
    qs = Student.objects.filter(
        company=company,
        phone__in=get_phone_variants(phone),
        first_name__iexact=first_name,
    ).exclude(status__in=[Student.Status.LEFT, Student.Status.LEFT_TRIAL])
    if last_name:
        qs = qs.filter(last_name__iexact=last_name)
    return qs.first()


def _serialize_lead(lead: Lead) -> dict:
    converted_student = (
        _latest_converted_student(lead)
        if lead.stage == Lead.Stage.CONVERTED
        else None
    )
    converted_student_id = converted_student.id if converted_student else None
    student_is_active = bool(
        converted_student
        and converted_student.status not in (Student.Status.LEFT, Student.Status.LEFT_TRIAL)
    )
    student_deleted = bool(
        lead.stage == Lead.Stage.CONVERTED
        and (
            converted_student is None
            or not student_is_active
        )
    )
    return {
        'id': lead.id,
        'first_name': lead.first_name,
        'last_name': lead.last_name,
        'full_name': lead.full_name,
        'phone': lead.phone,
        'phone2': lead.phone2,
        'phone2_owner': lead.phone2_owner,
        'address': lead.address,
        'school': lead.school,
        'comment': lead.comment,
        'source': lead.source,
        'level': lead.level,
        'branch_id': lead.branch_id,
        'branch_name': lead.branch.name if lead.branch else None,
        'course_id': lead.course_id,
        'course_name': lead.course.name if lead.course else None,
        'is_active': lead.is_active,
        'stage': lead.stage,
        'stage_label': lead.get_stage_display(),
        'status': lead.stage,
        'status_label': lead.get_stage_display(),
        'attended_trial': bool(getattr(lead, 'attended_trial', False) or lead.stage in (Lead.Stage.ATTENDED, Lead.Stage.CONVERTED)),
        'trial_date': lead.trial_date.isoformat() if lead.trial_date else None,
        'converted_student_id': converted_student_id,
        'student_is_active': student_is_active,
        'student_deleted': student_deleted,
        'created_at': lead.created_at.isoformat(),
    }


def _format_time(value) -> str | None:
    return value.strftime('%H:%M') if value else None


def _parse_time(value) -> time | None:
    if value in (None, ''):
        return None
    try:
        return datetime.strptime(str(value).strip()[:5], '%H:%M').time()
    except ValueError:
        return None


def _parse_id_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    ids: list[int] = []
    for part in str(raw).split(','):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


def _parse_date_param(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip()[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _format_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.strftime('%d.%m.%Y')


def _training_dates_label(group: Group) -> str | None:
    start = group.group_start_date
    end = group.group_end_date
    if not start and not end:
        return None
    if start and end:
        return f'{_format_date(start)} – {_format_date(end)}'
    return _format_date(start or end)


def _week_of_study(group: Group) -> int | None:
    if not group.group_start_date:
        return None
    today = date.today()
    if today < group.group_start_date:
        return 0
    return (today - group.group_start_date).days // 7 + 1


# Group size = students who still belong to it (left / graduated students keep the link only as history)
CURRENT_STUDENTS_COUNT = Count('students', filter=Q(students__status__in=Student.CURRENT_STATUSES))


def _group_archive_error(group: Group) -> str | None:
    """A group with current students cannot be closed — they would keep studying (and paying) in it."""
    count = group.students.filter(status__in=Student.CURRENT_STATUSES).count()
    if count:
        return (
            f'В группе «{group.name}» {count} студент(ов) учатся или на заморозке. Сначала переведите их '
            'в другую группу или поставьте статус «Завершил курс» / «Ушёл», потом закройте группу.'
        )
    return None


def _serialize_group(group: Group, *, detailed: bool = False) -> dict:
    week = _week_of_study(group)
    payload = {
        'id': group.id,
        'name': group.name,
        'days': group.days,
        'days_label': group.get_days_display(),
        'weekdays': group_weekdays(group.days, group.weekdays),
        'status': group.status,
        'status_label': group.get_status_display(),
        'branch_id': group.branch_id,
        'branch': group.branch.name if group.branch_id else '—',
        'course_id': group.course_id,
        'course': {
            'id': group.course_id,
            'name': group.course.name if group.course else None,
            'price': group.course.price if group.course else 0,
        } if group.course_id else None,
        'teacher_id': group.teacher_id,
        'teacher': group.teacher.display_name() if group.teacher else None,
        'room_id': group.room_id,
        'room': group.room.name if group.room_id else None,
        'lesson_start_time': _format_time(group.lesson_start_time),
        'lesson_end_time': _format_time(group.lesson_end_time),
        'group_start_date': group.group_start_date.isoformat() if group.group_start_date else None,
        'group_end_date': group.group_end_date.isoformat() if group.group_end_date else None,
        'training_dates': _training_dates_label(group),
        'week_of_study': week,
        'week_of_study_label': f'Week {week}' if week is not None else None,
        'students_count': getattr(
            group, 'students_count', group.students.filter(status__in=Student.CURRENT_STATUSES).count(),
        ),
        'tags': [{'id': tag.id, 'name': tag.name} for tag in group.tags.all()],
        'archived_at': group.archived_at.isoformat() if group.archived_at else None,
        'archived_by_id': group.archived_by_id,
        'archived_by': group.archived_by.display_name() if group.archived_by else None,
    }
    if detailed:
        payload['students'] = [
            {
                'id': student.id,
                'full_name': student.full_name,
                'phone': student.phone,
                'status': student.status,
                'status_label': student.get_status_display(),
            }
            for student in group.students.filter(status__in=Student.CURRENT_STATUSES).order_by('first_name', 'last_name')
        ]
    return payload


def _apply_group_fields(group: Group, company: Company, data: dict) -> str | None:
    name = data.get('name')
    if name is not None:
        name = str(name).strip()
        if not name:
            return 'Group name is required'
        group.name = name

    branch_id = data.get('branch_id')
    if branch_id is not None:
        try:
            branch = Branch.objects.get(pk=int(branch_id), company=company)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return 'Invalid branch'
        group.branch = branch

    course_id = data.get('course_id')
    if course_id is not None:
        if course_id in ('', None):
            group.course = None
        else:
            try:
                group.course = Course.objects.get(pk=int(course_id), company=company)
            except (Course.DoesNotExist, TypeError, ValueError):
                return 'Invalid course'

    teacher_id = data.get('teacher_id')
    if teacher_id is not None:
        if teacher_id in ('', None):
            group.teacher = None
        else:
            try:
                teacher = User.objects.get(
                    pk=int(teacher_id),
                    company=company,
                    user_type=User.UserType.TEACHER,
                    is_active=True,
                )
            except (User.DoesNotExist, TypeError, ValueError):
                return 'Invalid teacher'
            if not TeacherBranch.objects.filter(teacher=teacher, branch=group.branch).exists():
                return 'Teacher is not assigned to this branch'
            group.teacher = teacher

    days = data.get('days')
    if days is not None:
        try:
            days = int(days)
        except (TypeError, ValueError):
            return 'Invalid schedule'
        if days not in VALID_GROUP_DAYS:
            return 'Invalid schedule'
        group.days = days

    if 'weekdays' in data:
        raw_weekdays = data.get('weekdays')
        if isinstance(raw_weekdays, str):
            raw_weekdays = [p for p in raw_weekdays.split(',') if p.strip()]
        if not isinstance(raw_weekdays, (list, tuple)):
            return 'Invalid weekdays'
        try:
            parsed_weekdays = sorted({int(d) for d in raw_weekdays})
        except (TypeError, ValueError):
            return 'Invalid weekdays'
        if any(d < 0 or d > 6 for d in parsed_weekdays):
            return 'Invalid weekdays'
        group.weekdays = parsed_weekdays

    if group.days == Group.Days.CUSTOM:
        if not group.weekdays:
            return 'Выберите дни недели для расписания «Другое»'
    else:
        group.weekdays = []

    status = data.get('status')
    if status is not None:
        try:
            status = int(status)
        except (TypeError, ValueError):
            return 'Invalid status'
        if status not in VALID_GROUP_STATUSES:
            return 'Invalid status'
        group.status = status

    if 'lesson_start_time' in data:
        group.lesson_start_time = _parse_time(data.get('lesson_start_time'))
    if 'lesson_end_time' in data:
        group.lesson_end_time = _parse_time(data.get('lesson_end_time'))

    group_start_date = data.get('group_start_date')
    if group_start_date is not None:
        if group_start_date in ('', None):
            group.group_start_date = None
        else:
            try:
                group.group_start_date = datetime.strptime(str(group_start_date)[:10], '%Y-%m-%d').date()
            except ValueError:
                return 'Invalid start date'

    group_end_date = data.get('group_end_date')
    if group_end_date is not None:
        if group_end_date in ('', None):
            group.group_end_date = None
        else:
            try:
                group.group_end_date = datetime.strptime(str(group_end_date)[:10], '%Y-%m-%d').date()
            except ValueError:
                return 'Invalid end date'

    room_id = data.get('room_id')
    if room_id is not None:
        if room_id in ('', None):
            group.room = None
        else:
            try:
                group.room = Room.objects.get(pk=int(room_id), branch=group.branch)
            except (Room.DoesNotExist, TypeError, ValueError):
                try:
                    if Room.objects.filter(pk=int(room_id), company=company).exists():
                        return 'Room belongs to a different branch'
                except (TypeError, ValueError):
                    pass
                return 'Invalid room'

    if group.room and group.room.branch_id != group.branch_id:
        return 'Room belongs to a different branch'
    if group.teacher and not TeacherBranch.objects.filter(teacher=group.teacher, branch=group.branch).exists():
        return 'Teacher is not assigned to this branch'

    return None




def _get_student_payments_queryset(student: Student, company: Company):
    """
    Returns Payment queryset for student.
    Uses fallback matching by student_name for legacy payments (student IS NULL)
    ONLY if there is strictly ONE student with this name in the company.
    If 2+ students share the same name (namesakes), legacy payments are considered
    ambiguous and NOT attributed automatically.
    """
    same_name_count = Student.objects.filter(
        company=company,
        first_name__iexact=student.first_name,
        last_name__iexact=student.last_name,
    ).count()
    if same_name_count == 1:
        payment_filter = Q(student=student) | Q(student__isnull=True, student_name=student.full_name)
    else:
        payment_filter = Q(student=student)
    return Payment.objects.filter(
        Q(company=company) & payment_filter,
        transaction_type=Payment.TransactionType.PAYMENT,
    ).filter(ACTIVE_PAYMENT_Q)


def _get_student_payment_info(student: Student, info: dict | None = None) -> dict:
    """
    Where the student stands with payments, read from their month lines (finance/charges.py):
    the next payment day is the first line that is not paid in full; a debtor owes exactly those lines.
    `info` — data loaded for the whole company at once (lists), else it is read for this student.
    """
    if info is None:
        payments = _get_student_payments_queryset(student, student.company)
        last = payments.order_by('-payment_date', '-created_at').first()
        last_date = (last.payment_date or timezone.localtime(last.created_at).date()) if last else None
        charges.refresh(student)  # a new month may have begun since the last look
        lines, freezes = charges.student_lines(student), None
    else:
        last_date = info.get('last_date')
        lines, freezes = info.get('lines') or [], info.get('freezes') or []

    state = charges.schedule(student, lines, freezes)
    return {
        'last_payment_date': last_date,
        'next_payment_date': state['next_due'],
        'is_debtor': state['is_debtor'],
        'overdue_days': state['overdue_days'],
        'paid_count': state['paid_count'],
        # Exact: every owed month at its own price
        'debt_months': state['debt_months'],
        'debt_amount': state['debt_amount'],
        'lines': lines,
    }


def student_debt_on(student: Student, on_date: date | None = None) -> dict | None:
    """
    What the student owes on `on_date` (default: the day they left, or today), regardless of status:
    the month lines that had begun by that day and are not paid in full. None when nothing is owed.
    """
    charges.refresh(student)
    return charges.debt_on(student, on_date)


PAID_DAY = Coalesce('payment_date', TruncDate('created_at'))


def _company_payments_summary(company: Company) -> dict:
    """Payment dates of every student plus their month lines and freezes (lists: no query per student)."""
    from collections import Counter
    charges.ensure_current()
    # Detect names that belong to multiple students to prevent mixing namesakes on legacy payments
    names = [
        f"{fn} {ln}".strip().lower()
        for fn, ln in Student.objects.filter(company=company).values_list('first_name', 'last_name')
    ]
    name_counts = Counter(names)
    ambiguous_names = {name for name, count in name_counts.items() if count > 1}

    rows = (
        Payment.objects.filter(
            company=company,
            transaction_type=Payment.TransactionType.PAYMENT,
        )
        .filter(ACTIVE_PAYMENT_Q)
        .values('student_id', 'student_name')
        .annotate(
            count=Count('id'),
            total_months=Sum('months_covered'),
            # The day the money was actually brought (payment_date); old payments without it — the day entered
            last_paid=Max(PAID_DAY),
            first_paid=Min(PAID_DAY),
        )
    )
    summary = {}
    for r in rows:
        item = {
            'count': r['count'],
            # 0 is a real value now (a копилка payment that did not close a month yet)
            'months_covered': r['total_months'] if r['total_months'] is not None else r['count'],
            'last_date': r['last_paid'],
            'first_date': r['first_paid'],
        }
        if r['student_id']:
            sid = r['student_id']
            if sid in summary:
                summary[sid]['count'] += item['count']
                summary[sid]['months_covered'] += item['months_covered']
                if item['last_date'] and (not summary[sid]['last_date'] or item['last_date'] > summary[sid]['last_date']):
                    summary[sid]['last_date'] = item['last_date']
                if item['first_date'] and (not summary[sid]['first_date'] or item['first_date'] < summary[sid]['first_date']):
                    summary[sid]['first_date'] = item['first_date']
            else:
                summary[sid] = dict(item)
        elif r['student_name']:
            p_name = r['student_name'].strip().lower()
            if p_name in ambiguous_names:
                # Ambiguous namesake: do NOT attribute legacy payment by name
                continue
            key = f"legacy:{r['student_name']}"
            if key in summary:
                summary[key]['count'] += item['count']
                summary[key]['months_covered'] += item['months_covered']
                if item['last_date'] and (not summary[key]['last_date'] or item['last_date'] > summary[key]['last_date']):
                    summary[key]['last_date'] = item['last_date']
                if item['first_date'] and (not summary[key]['first_date'] or item['first_date'] < summary[key]['first_date']):
                    summary[key]['first_date'] = item['first_date']
            else:
                summary[key] = dict(item)
    summary['__lines__'] = charges.company_lines(company.id)
    summary['__freezes__'] = charges.company_freezes(company.id)
    return summary


def _lookup_student_payment_summary(student: Student, summary: dict) -> dict:
    direct = summary.get(student.id)
    legacy = summary.get(f"legacy:{student.full_name}")
    if direct and legacy:
        dates_last = [d for d in (direct['last_date'], legacy['last_date']) if d]
        dates_first = [d for d in (direct['first_date'], legacy['first_date']) if d]
        found = {
            'count': direct['count'] + legacy['count'],
            'months_covered': direct['months_covered'] + legacy['months_covered'],
            'last_date': max(dates_last) if dates_last else None,
            'first_date': min(dates_first) if dates_first else None,
        }
    else:
        found = dict(direct or legacy or {})
    found['lines'] = summary.get('__lines__', {}).get(student.id, [])
    found['freezes'] = summary.get('__freezes__', {}).get(student.id, [])
    return found



def _serialize_student(student: Student, *, payment_info: dict | None = None, detailed: bool = False) -> dict:
    p_info = payment_info or _get_student_payment_info(student)
    last_payment_date = p_info['last_payment_date']
    next_payment_date = p_info['next_payment_date']

    payload = {
        'id': student.id,
        'first_name': student.first_name,
        'last_name': student.last_name,
        'full_name': student.full_name,
        'phone': student.phone,
        'phone2': student.phone2,
        'phone2_owner': student.phone2_owner,
        'address': student.address,
        'comment': student.comment,
        'level': student.level,
        'lead_id': student.lead_id,
        # ✅ ИСПРАВЛЕНО: проверяем существование файла
        'photo': get_photo_url(student.photo),
        'school': student.school,
        'telegram': student.telegram,
        'parent_telegram': student.parent_telegram,
        'status': student.status,
        'status_label': student.get_status_display(),
        'trial_date': student.trial_date.isoformat() if student.trial_date else None,
        'paid_this_month': student.paid_this_month,
        'last_payment_date': (
            last_payment_date.isoformat() if last_payment_date else None
        ),
        'next_payment_date': (
            next_payment_date.isoformat() if next_payment_date else None
        ),
        'is_debtor': p_info['is_debtor'],
        'overdue_days': p_info['overdue_days'],
        'paid_count': p_info['paid_count'],
        'debt_months': p_info.get('debt_months', 0),
        'debt_amount': p_info.get('debt_amount', 0),
        **wallet_info(student),
        'branch_id': student.branch_id,
        'branch': student.branch.name if student.branch_id else '—',
        'group_id': student.group_id,
        'group': student.group.name if student.group_id else None,
        'group_teacher': student.group.teacher.display_name() if (student.group and student.group.teacher) else '',
        'course_price': student.group.course.price if (student.group and student.group.course) else 0,
        'course_name': student.group.course.name if (student.group and student.group.course) else '',
        'frozen_at': student.frozen_at.isoformat() if student.frozen_at else None,
        'left_at': student.left_at.isoformat() if student.left_at else None,
        'created_at': student.created_at.isoformat(),
    }
    if detailed:
        payload['telegram_code'] = student.telegram_code
        # The student's months: what was charged, what is paid, what is left (finance/charges.py)
        payload['charges'] = charges.serialize_lines(p_info.get('lines') or [])
    return payload


class UnfreezeError(ValueError):
    pass


def _unfreeze_day(student: Student, resume_date: date) -> date:
    """
    Freeze = the payment clock is paused, nothing is forgiven and nothing is lost. The month that was running
    continues from the day the student comes back with exactly what was left of it; an unpaid month stays
    a debt (finance/charges.py: shift_after_freeze). Here only the date is checked.
    """
    freeze_date = timezone.localtime(student.frozen_at).date() if student.frozen_at else resume_date
    if resume_date < freeze_date:
        raise UnfreezeError(
            f'Дата возобновления не может быть раньше даты заморозки ({freeze_date.strftime("%d.%m.%Y")})'
        )
    return resume_date


def _apply_student_fields(student: Student, company: Company, data: dict) -> str | None:
    first_name = data.get('first_name')
    if first_name is not None:
        first_name = str(first_name).strip()
        if not first_name:
            return 'First name is required'
        student.first_name = first_name

    if 'last_name' in data:
        student.last_name = str(data.get('last_name') or '').strip()

    if 'phone2' in data or 'extra_phone' in data:
        p2_raw = str(data.get('phone2') or data.get('extra_phone') or '').strip()
        if p2_raw:
            p2 = normalize_phone(p2_raw)
            if not is_valid_phone(p2):
                return 'Secondary phone must contain 9 digits'
            student.phone2 = p2
        else:
            student.phone2 = ''

    if 'phone2_owner' in data:
        student.phone2_owner = str(data.get('phone2_owner') or '').strip()

    if 'address' in data:
        student.address = str(data.get('address') or '').strip()

    if 'comment' in data or 'notes' in data:
        student.comment = str(data.get('comment') or data.get('notes') or '').strip()

    if 'level' in data:
        student.level = str(data.get('level') or '').strip()

    if 'school' in data:
        student.school = str(data.get('school') or '').strip()

    if 'telegram' in data:
        student.telegram = str(data.get('telegram') or '').strip()

    if 'parent_telegram' in data:
        student.parent_telegram = str(data.get('parent_telegram') or '').strip()

    phone = data.get('phone')
    if phone is not None:
        # ✅ ИСПРАВЛЕНО: нормализация с удалением кода страны
        phone = normalize_phone(str(phone))
        if not is_valid_phone(phone):
            return 'Phone must contain 9 digits'
        student.phone = phone

    was_frozen = bool(student.pk and student.status == Student.Status.FROZEN)
    status = data.get('status')
    if status is not None:
        status = safe_int(status, default=None)
        if status is None or status not in VALID_STUDENT_STATUSES:
            return 'Invalid status'
    elif data.get('unfreeze') and was_frozen:
        status = Student.Status.STUDYING

    if status is not None:
        if was_frozen and status == Student.Status.STUDYING:
            # trial_date in an unfreeze request = the day the student comes back
            resume_date = parse_date_safe(data.get('trial_date')) if data.get('trial_date') else None
            try:
                # Read by crm/signals.py after the save: the running month continues from this day
                student._resume_date = _unfreeze_day(student, resume_date or timezone.localdate())
            except UnfreezeError as exc:
                return str(exc)
        student.status = status

    # paid_this_month is computed from Payment records only (see sync_student_paid_this_month).
    # Manual override removed to prevent inconsistency between the flag and actual payments.

    if 'trial_date' in data and not (was_frozen and student.status == Student.Status.STUDYING):
        raw_td = data.get('trial_date')
        if not raw_td:
            return 'Trial / start date is required'
        parsed_td = parse_date_safe(raw_td)
        if not parsed_td:
            return 'Invalid trial / start date format'
        student.trial_date = parsed_td

    branch_id = data.get('branch_id')
    if branch_id is not None:
        try:
            target_branch = Branch.objects.get(pk=int(branch_id), company=company)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return 'Invalid branch'
        student.branch = target_branch

    group_id = data.get('group_id')
    if group_id is not None:
        if group_id in ('', None):
            student.group = None
        else:
            try:
                group = Group.objects.select_related('room').get(pk=int(group_id), company=company)
            except (Group.DoesNotExist, TypeError, ValueError):
                return 'Invalid group'
            student.group = group
            student.branch = group.branch

    if student.group_id and student.group:
        student.branch = student.group.branch

    return None


def _payment_mode_label(mode: int) -> str:
    labels = {
        1: 'By day',
        2: 'Monthly',
        3: 'Group start',
        4: 'Full course',
        5: 'Module',
        6: 'Individual',
    }
    return labels.get(mode, 'Unknown')


def _serialize_company(company: Company) -> dict:
    return {
        'id': company.id,
        'name': company.name,
        'subdomain': company.subdomain,
        'balance_mode': 1,
        'payment_mode_label': 'Daily',
        'phone': company.phone,
    }


def _format_phone(phone: str) -> str:
    digits = ''.join(ch for ch in phone if ch.isdigit())
    if len(digits) == 9:
        return f'({digits[:2]}) {digits[2:5]}-{digits[5:7]}-{digits[7:9]}'
    if len(digits) == 12 and digits.startswith('998'):
        local = digits[3:]
        return f'({local[:2]}) {local[2:5]}-{local[5:7]}-{local[7:9]}'
    return phone


def _user_role_label(user: User) -> str:
    return get_role_label(get_effective_role(user))


def _student_branch_error(user: User, student: Student) -> str | None:
    """E3: a branch director keeps the student and the student's group inside own branch."""
    if not branch_allowed(user, student.branch_id):
        return 'Invalid branch'
    if student.group_id and not branch_allowed(user, student.group.branch_id):
        return 'Invalid group'
    return None


def _user_branches(user: User) -> list[dict]:
    company = user.company
    if company is None:
        return []
    if user.user_type == User.UserType.TEACHER:
        return [
            {'id': link.branch_id, 'name': link.branch.name}
            for link in TeacherBranch.objects.filter(teacher=user).select_related('branch')
        ]
    return [
        {'id': branch.id, 'name': branch.name}
        for branch in branches_for(user, company).order_by('id')
    ]


def _serialize_user(user) -> dict:
    company = user.company
    first_name = (user.first_name or '').strip()
    role = get_effective_role(user)
    return {
        'id': user.id,
        'name': user.get_full_name() or user.phone,
        'first_name': first_name or user.phone,
        'last_name': user.last_name or '',
        'phone': user.phone,
        'phone_formatted': _format_phone(user.phone),
        'user_type': user.user_type,
        'staff_role': user.staff_role or None,
        'role': role,
        'job_title': user.job_title or '',
        'role_label': get_role_label(role),
        'permissions': sorted(get_user_permissions(user)),
        'branches': _user_branches(user),
        'company': _serialize_company(company) if company else None,
    }


@api_view(['GET'])
@permission_classes([AllowAny])
def company_by_subdomain(request, subdomain: str):
    try:
        company = Company.objects.get(subdomain=subdomain)
    except Company.DoesNotExist:
        return fail('Company not found', 404)
    return ok(_serialize_company(company))


@api_view(['GET'])
def company_detail(request, company_id: int):
    # ✅ ИСПРАВЛЕНО: 2 строки — проверяем что это своя компания
    if company_id != request.user.company_id:
        return fail('Access denied', 403)

    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        return fail('Company not found', 404)

    return ok(_serialize_company(company))


@api_view(['POST'])
@permission_classes([AllowAny])
def auth_login(request):
    phone = str(request.data.get('phone') or request.data.get('username') or '').strip()
    password = str(request.data.get('password') or '').strip()
    if not phone or not password:
        return fail('Phone and password are required')

    clean_p = _normalize_phone(phone)
    user = authenticate(request, phone=phone, password=password)
    if user is None and clean_p != phone:
        user = authenticate(request, phone=clean_p, password=password)

    if user is None:
        candidate = User.objects.filter(Q(phone=phone) | Q(phone=clean_p)).first()
        if candidate and candidate.is_active and candidate.check_password(password):
            user = candidate

    if user is None:
        return fail('Invalid credentials', 401)

    refresh = RefreshToken.for_user(user)
    return ok({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': _serialize_user(user),
    })


@api_view(['GET', 'POST', 'PATCH'])
def auth_me(request):
    user = request.user

    if request.method == 'PATCH':
        is_ceo = (get_effective_role(user) == ROLE_CEO or user.is_superuser)

        # Self-editing restrictions: non-CEO can only change phone (and password if old_password verified)
        if not is_ceo:
            forbidden = {'first_name', 'last_name', 'job_title'} & set(request.data.keys())
            if forbidden:
                return fail('Только CEO может изменять имя, фамилию и должность', status_code=403)
        else:
            first_name = request.data.get('first_name')
            if first_name is not None:
                first_name = str(first_name).strip()
                if not first_name:
                    return fail('First name is required')
                user.first_name = first_name

            if 'last_name' in request.data:
                user.last_name = str(request.data.get('last_name') or '').strip()

            if 'job_title' in request.data:
                user.job_title = str(request.data.get('job_title') or '').strip()

        phone = request.data.get('phone')
        if phone is not None:
            norm_phone = normalize_phone(phone)
            if len(norm_phone) != 9:
                return fail('Valid 9-digit phone is required (e.g. 901234567)')
            if User.objects.filter(phone=norm_phone).exclude(pk=user.pk).exists():
                return fail('Phone already exists')
            user.phone = norm_phone

        password = request.data.get('password')
        if password:
            if not is_ceo:
                old_password = request.data.get('old_password') or request.data.get('current_password')
                if not old_password or not user.check_password(str(old_password)):
                    return fail('Текущий пароль указан неверно', status_code=400)
            user.set_password(str(password))

        user.save()
        return ok(_serialize_user(user))

    return ok(_serialize_user(user))


@api_view(['GET'])
def branch_list(request):
    company = request.user.company
    if company is None:
        return ok([])
    branches = branches_for(request.user, company).order_by('id')
    data = [{'id': b.id, 'name': b.name, 'address': b.address} for b in branches]
    return ok(data)


@api_view(['GET'])
def dashboard(request):
    company = request.user.company
    if company is None:
        return ok({})

    is_teacher = user_is_teacher(request.user)
    students = filter_students_queryset(Student.objects.filter(company=company), request.user)
    groups = Group.objects.filter(company=company, status=Group.Status.ACTIVE)
    groups = filter_groups_queryset(groups, request.user)
    active_leads_count = scope_branch(Lead.objects.filter(
        company=company,
        is_active=True,
        stage__in=[Lead.Stage.TRIAL_BOOKED, Lead.Stage.ATTENDED],
    ), request.user).count()

    # By the day the money was brought (payment_date), like the P&L — not by the day it was typed in
    six_months_ago = timezone.localdate() - timedelta(days=180)
    monthly_payments = (
        scope_payments(Payment.objects.filter(company=company), request.user)
        .annotate(paid_day=PAID_DAY)
        .filter(paid_day__gte=six_months_ago)
        .annotate(month=TruncMonth('paid_day'))
        .values('month')
        .annotate(
            paid=Sum('amount', filter=Q(transaction_type=Payment.TransactionType.PAYMENT)),
            refunded=Sum('amount', filter=Q(transaction_type=Payment.TransactionType.REFUND)),
        )
        .order_by('month')
    )
    finance_chart = [
        {
            'label': row['month'].strftime('%b %Y'),
            'value': max(0, int((row['paid'] or 0) - (row['refunded'] or 0))),
        }
        for row in monthly_payments
    ]

    schedule = _serialize_schedule_rows(groups)

    reminders = [
        {
            'id': reminder.id,
            'title': reminder.title,
            'details': reminder.details,
            'due_date': reminder.due_date.isoformat(),
            'status': reminder.current_status,
            'assigned_to_id': reminder.assigned_to_id,
            'assigned_to': reminder.assigned_to.display_name() if reminder.assigned_to else '—',
            'student_id': reminder.student_id,
            'kind': reminder.kind,
        }
        # Overdue and today's reminders; "left without paying" has its own block below
        for reminder in filter_reminders_queryset(Reminder.objects.filter(
            company=company,
            due_date__lte=timezone.localdate(),
        ), request.user).exclude(status=Reminder.Status.DONE).exclude(kind=Reminder.KIND_UNPAID_LEAVE)
        .select_related('assigned_to').order_by('due_date', 'id')[:10]
    ]

    # Students who left without paying: stays on the dashboard until someone marks it done.
    # Their debts are money: not for a teacher or the marketer (reports audit, 2026-09-29)
    from accounts.rbac import PERM_PAYMENTS_VIEW
    sees_debts = not is_teacher and user_has_permission(request.user, PERM_PAYMENTS_VIEW)
    unpaid_leavers = [] if not sees_debts else [
        {
            'reminder_id': reminder.id,
            'student_id': reminder.student_id,
            'title': reminder.title,
            'details': reminder.details,
            # Tashkent date (a plain .date() is the UTC one: leaving before 05:00 showed yesterday)
            'created_at': timezone.localtime(reminder.created_at).date().isoformat(),
            **unpaid_leave_state(reminder),
        }
        for reminder in filter_reminders_queryset(
            Reminder.objects.filter(company=company, kind=Reminder.KIND_UNPAID_LEAVE), request.user,
        ).exclude(status=Reminder.Status.DONE).order_by('-created_at')[:50]
    ]

    studying_students = students.filter(status=Student.Status.STUDYING)
    if is_teacher:
        # E1: teachers get no company-wide money or sales figures
        active_leads_count = 0
        finance_chart = []
        debtors_count = 0
    else:
        payments_summary = _company_payments_summary(company)
        # Same rule as the debtors list: studying + frozen, same payment lookup
        debtors_count = sum(
            1 for s in students.filter(status__in=Student.CURRENT_STATUSES)
            if _get_student_payment_info(s, _lookup_student_payment_summary(s, payments_summary))['is_debtor']
        )
        if not user_has_permission(request.user, PERM_FINANCE_VIEW):
            # The revenue chart is a money report: the administrator does not see it (owner, 2026-09-28)
            finance_chart = []

    return ok({
        'active_leads': active_leads_count,
        'active_students': studying_students.count(),
        'groups': groups.count(),
        'debtors': debtors_count,
        'trial_students': 0,
        'left_active_group': students.filter(status=Student.Status.LEFT).count(),
        'left_after_trial': students.filter(status=Student.Status.LEFT_TRIAL).count(),
        'finance_chart': finance_chart,
        'schedule': schedule,
        'reminders': reminders,
        'unpaid_leavers': unpaid_leavers,
    })


@api_view(['GET'])
def schedule_list(request):
    company = request.user.company
    if company is None:
        return ok([])

    groups = Group.objects.filter(company=company, status=Group.Status.ACTIVE)
    groups = filter_groups_queryset(groups, request.user)
    return ok(_serialize_schedule_rows(groups))


@api_view(['GET', 'POST'])
def group_list(request):
    company = request.user.company
    if company is None:
        return ok([])

    if request.method == 'POST':
        # ═══ ВАЛИДАЦИЯ (всё ДО сохранения) ═══

        name = (request.data.get('name') or '').strip()
        if not name:
            return fail('Group name is required')

        branch_id = request.data.get('branch_id')
        if not branch_id:
            return fail('Branch is required')
        try:
            branch = branches_for(request.user, company).get(pk=int(branch_id))
        except (Branch.DoesNotExist, TypeError, ValueError):
            return fail('Invalid branch')

        days = safe_int(request.data.get('days', Group.Days.ODD),
                        default=Group.Days.ODD)
        if days not in VALID_GROUP_DAYS:
            return fail('Invalid schedule')

        # ✅ ИСПРАВЛЕНО: Валидируем теги ДО создания группы
        tag_ids = None
        if 'tag_ids' in request.data:
            raw_tags = request.data.get('tag_ids')
            if raw_tags in (None, ''):
                tag_ids = []
            else:
                tag_ids = raw_tags if isinstance(raw_tags, list) else _parse_id_list(str(raw_tags))
                # Проверяем, что ВСЕ теги существуют и принадлежат компании
                existing_tags = list(Tag.objects.filter(pk__in=tag_ids, company=company))
                if len(existing_tags) != len(set(tag_ids)):
                    return fail('One or more tags not found')

        # ═══ СОЗДАНИЕ (все данные уже проверены) ═══

        group = Group(company=company, branch=branch, name=name, days=days)

        # Применяем остальные поля (excluding name, branch_id, days — already validated above)
        remaining_data = {k: v for k, v in request.data.items() if k not in ('name', 'branch_id', 'days')}
        error = _apply_group_fields(group, company, remaining_data)
        if error:
            return fail(error)

        conflict = validate_group_schedule(
            company=company,
            branch=group.branch,
            teacher=group.teacher,
            room=group.room,
            days=group.days,
            start_time=group.lesson_start_time,
            end_time=group.lesson_end_time,
            start_date=group.group_start_date,
            end_date=group.group_end_date,
            exclude_group_id=None,
            weekdays=group.weekdays,
        )
        if conflict:
            return fail(
                conflict['message'],
                status_code=conflict.get('status_code', 400),
                code=conflict.get('code'),
                conflicts=conflict.get('conflicts', []),
            )

        # Сохраняем
        group.save()
        sync_group_schedule_slots(group)

        # Устанавливаем теги (уже валидированы)
        if tag_ids is not None:
            group.tags.set(existing_tags)


        # Перезагружаем для получения annotations
        group = Group.objects.select_related(
            'course', 'branch', 'teacher', 'room'
        ).prefetch_related('tags').annotate(
            students_count=CURRENT_STUDENTS_COUNT
        ).get(pk=group.pk)

        return ok(_serialize_group(group), status_code=201)

    # ═══ GET — с пагинацией ═══

    branch_id = request.query_params.get('branch_id')
    teacher_id = request.query_params.get('teacher_id')
    teacher_ids = _parse_id_list(request.query_params.get('teacher_ids'))
    if teacher_id and not teacher_ids:
        teacher_ids = _parse_id_list(teacher_id)
    course_ids = _parse_id_list(request.query_params.get('course_ids'))
    day_ids = _parse_id_list(request.query_params.get('days'))
    tag_ids = _parse_id_list(request.query_params.get('tag_ids'))
    status = request.query_params.get('status')
    start_date = parse_date_safe(request.query_params.get('start_date'))
    end_date = parse_date_safe(request.query_params.get('end_date'))
    query = (request.query_params.get('q') or '').strip()

    qs = Group.objects.filter(company=company).select_related(
        'course', 'branch', 'teacher', 'room',
    ).prefetch_related('tags').annotate(students_count=CURRENT_STUDENTS_COUNT).order_by('name')
    qs = filter_groups_queryset(qs, request.user)

    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if teacher_ids:
        qs = qs.filter(teacher_id__in=teacher_ids)
    if course_ids:
        qs = qs.filter(course_id__in=course_ids)
    if day_ids:
        qs = qs.filter(days__in=day_ids)
    if tag_ids:
        qs = qs.filter(tags__id__in=tag_ids).distinct()
    if status == 'all':
        pass
    elif status:
        qs = qs.filter(status=safe_int(status, default=Group.Status.ACTIVE))
    else:
        qs = qs.filter(status=Group.Status.ACTIVE)
    if start_date:
        qs = qs.filter(
            Q(group_end_date__gte=start_date) | Q(group_end_date__isnull=True),
        )
    if end_date:
        qs = qs.filter(
            Q(group_start_date__lte=end_date) | Q(group_start_date__isnull=True),
        )
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(course__name__icontains=query))

    # ✅ Пагинация вместо hard limit
    page = paginate_queryset(qs, request, default_limit=200)

    return ok({
        'count': page['count'],
        'has_more': page['has_more'],
        'next_offset': page['next_offset'],
        'results': [_serialize_group(g) for g in page['results']],
    })


@api_view(['GET', 'PATCH', 'DELETE'])
def group_detail(request, group_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        group = Group.objects.select_related(
            'course', 'branch', 'teacher', 'room'
        ).prefetch_related('tags').annotate(
            students_count=CURRENT_STUDENTS_COUNT
        ).get(pk=group_id, company=company)
    except Group.DoesNotExist:
        return fail('Group not found', status_code=404)

    if not can_access_group(request.user, group):
        return fail('Group not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_group(group, detailed=True))

    if request.method == 'DELETE':
        archive_error = _group_archive_error(group)
        if archive_error:
            return fail(archive_error)
        group.status = Group.Status.ARCHIVE
        group.archived_at = timezone.now()
        group.archived_by = request.user
        group.save(update_fields=['status', 'archived_at', 'archived_by'])
        return ok({'deleted': True, 'archived': True})

    # PATCH

    # ✅ Валидируем теги ДО обновления
    tag_ids = None
    existing_tags = []
    if 'tag_ids' in request.data:
        raw_tags = request.data.get('tag_ids')
        if raw_tags in (None, ''):
            tag_ids = []
        else:
            tag_ids = raw_tags if isinstance(raw_tags, list) else _parse_id_list(str(raw_tags))
            existing_tags = list(Tag.objects.filter(pk__in=tag_ids, company=company))
            if len(existing_tags) != len(set(tag_ids)):
                return fail('One or more tags not found')

    was_archived = group.status == Group.Status.ARCHIVE
    old_branch_id = group.branch_id
    error = _apply_group_fields(group, company, request.data)
    if error:
        return fail(error)
    if not branch_allowed(request.user, group.branch_id):
        return fail('Invalid branch')
    if group.status == Group.Status.ARCHIVE and not was_archived:
        archive_error = _group_archive_error(group)
        if archive_error:
            return fail(archive_error)
        group.archived_at = timezone.now()
        group.archived_by = request.user
    elif group.status != Group.Status.ARCHIVE and was_archived:
        group.archived_at = None
        group.archived_by = None

    if group.status != Group.Status.ARCHIVE:
        conflict = validate_group_schedule(
            company=company,
            branch=group.branch,
            teacher=group.teacher,
            room=group.room,
            days=group.days,
            start_time=group.lesson_start_time,
            end_time=group.lesson_end_time,
            start_date=group.group_start_date,
            end_date=group.group_end_date,
            exclude_group_id=group.id,
            weekdays=group.weekdays,
        )
        if conflict:
            return fail(
                conflict['message'],
                status_code=conflict.get('status_code', 400),
                code=conflict.get('code'),
                conflicts=conflict.get('conflicts', []),
            )

    group.save()
    sync_group_schedule_slots(group)
    if group.branch_id != old_branch_id:
        # current students move with their group (branch scoping and reports read Student.branch)
        Student.objects.filter(group=group, status__in=Student.CURRENT_STATUSES).update(branch_id=group.branch_id)

    if tag_ids is not None:
        group.tags.set(existing_tags)


    # Перезагружаем
    group = Group.objects.select_related(
        'course', 'branch', 'teacher', 'room'
    ).prefetch_related('tags').annotate(
        students_count=CURRENT_STUDENTS_COUNT
    ).get(pk=group.pk)

    return ok(_serialize_group(group))


@api_view(['GET', 'POST'])
def student_list(request):
    company = request.user.company
    if company is None:
        return ok([])

    if request.method == 'POST':
        first_name = (request.data.get('first_name') or '').strip()
        if not first_name:
            full_name = (request.data.get('full_name') or '').strip()
            if full_name:
                parts = full_name.split(None, 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ''
            else:
                return fail('First name is required')
        else:
            last_name = (request.data.get('last_name') or '').strip()

        # ✅ ИСПРАВЛЕНО: используем normalize_phone из utils
        phone = normalize_phone(request.data.get('phone') or '')
        if not is_valid_phone(phone):
            return fail('Phone must contain 9 digits')

        branch_id = request.data.get('branch_id')
        if not branch_id:
            return fail('Branch is required')
        try:
            branch = branches_for(request.user, company).get(pk=int(branch_id))
        except (Branch.DoesNotExist, TypeError, ValueError):
            return fail('Invalid branch')

        status = safe_int(request.data.get('status', Student.Status.STUDYING),
                         default=Student.Status.STUDYING)
        if status not in VALID_STUDENT_STATUSES:
            return fail('Invalid status')

        trial_date_raw = request.data.get('trial_date')
        if not trial_date_raw:
            return fail('Trial / start date is required')
        trial_date = parse_date_safe(trial_date_raw)
        if not trial_date:
            return fail('Invalid trial / start date format')

        # Duplicate check: prevent duplicate active students with identical phone and name
        if not request.data.get('force'):
            from crm.services import get_phone_variants
            phone_variants = get_phone_variants(phone)
            dup_qs = Student.objects.filter(
                company=company,
                phone__in=phone_variants,
                first_name__iexact=first_name,
            ).exclude(status__in=[Student.Status.LEFT, Student.Status.LEFT_TRIAL])
            if last_name:
                dup_qs = dup_qs.filter(last_name__iexact=last_name)

            existing = dup_qs.first()
            if existing:
                full_display = f"{first_name} {last_name}".strip()
                return fail(
                    f'Ученик "{full_display}" с номером {phone} уже существует в системе',
                    status_code=400
                )

        with transaction.atomic():
            student = Student(
                company=company,
                branch=branch,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                status=status,
                trial_date=trial_date,
            )
            error = _apply_student_fields(student, company, request.data) or _student_branch_error(request.user, student)
            if error:
                return fail(error)

            # Match and enrich from lead IN MEMORY (no DB writes yet)
            from crm.services import match_student_to_lead, enrich_student_from_lead, update_lead_on_conversion
            matched_lead = match_student_to_lead(student)
            enrich_student_from_lead(student, matched_lead)

            # Save student first — if this fails, lead stays untouched
            student.save()  # GroupEnrollment is synced by the post_save signal

            # Now safe to mark lead as CONVERTED

            if matched_lead:
                update_lead_on_conversion(student, matched_lead)

            student = Student.objects.select_related('group', 'branch').get(pk=student.pk)
            return ok(_serialize_student(student, detailed=True), status_code=201)

    # GET
    qs = Student.objects.filter(company=company).select_related(
        'group', 'branch'
    ).order_by('first_name', 'last_name')
    qs = filter_students_queryset(qs, request.user)

    payments_summary = _company_payments_summary(company)

    is_teacher = user_is_teacher(request.user)
    debtors_filter = not is_teacher and (
        request.query_params.get('debtors') == '1'
        or request.query_params.get('statuses') in ('6', 'debtor', 'debtors')
    )
    if debtors_filter:
        current_students = list(qs.filter(status__in=Student.CURRENT_STATUSES))
        debtor_ids = [
            s.id for s in current_students
            if _get_student_payment_info(s, _lookup_student_payment_summary(s, payments_summary))['is_debtor']
        ]
        qs = qs.filter(id__in=debtor_ids)
    else:
        statuses = request.query_params.get('statuses')
        if statuses:
            status_val = safe_int(statuses, default=None)
            if status_val in (5, 6):
                status_val = Student.Status.STUDYING
            if status_val is not None and status_val in VALID_STUDENT_STATUSES:
                qs = qs.filter(status=status_val)

    branch_id = request.query_params.get('branch_id')
    if branch_id:
        qs = qs.filter(branch_id=branch_id)

    group_id = request.query_params.get('group_id')
    if group_id:
        qs = qs.filter(group_id=group_id)

    query = (request.query_params.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(phone2__icontains=query)
            | Q(phone2_owner__icontains=query)
            | Q(address__icontains=query)
            | Q(comment__icontains=query),
        )

    # ✅ Пагинация
    page = paginate_queryset(qs, request, default_limit=200)

    return ok({
        'count': page['count'],
        'has_more': page['has_more'],
        'next_offset': page['next_offset'],
        'results': [
            strip_for_teacher(
                _serialize_student(s, payment_info=_get_student_payment_info(s, _lookup_student_payment_summary(s, payments_summary))),
                request.user,
            )
            for s in page['results']
        ],
    })


@api_view(['GET', 'PATCH', 'DELETE'])
def student_detail(request, student_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        student = Student.objects.select_related('group', 'branch').get(
            pk=student_id,
            company=company,
        )
    except Student.DoesNotExist:
        return fail('Student not found', status_code=404)

    if not can_access_student(request.user, student):
        return fail('Student not found', status_code=404)

    if request.method == 'GET':
        return ok(strip_for_teacher(_serialize_student(student, detailed=True), request.user))

    if request.method == 'DELETE':
        is_hard = (
            request.query_params.get('hard') in ('1', 'true', True)
            or (isinstance(request.data, dict) and request.data.get('hard') in ('1', 'true', True))
        )
        if is_hard:
            # Owner's rule #10 (confirmed 2026-09-27): students are never erased, for anyone — including the CEO.
            # Erasing orphaned payments (they were credited to a namesake) and wiped attendance / salary history.
            return fail('Полное удаление учеников отключено. Используйте «Отчислить» — история сохранится.')

        # No separate "Отчислить" any more (owner, 2026-09-27): this does exactly what the status
        # "Отчислен / Ушел" does in the edit form — the last group is kept for the reports.
        if student.status not in (Student.Status.LEFT, Student.Status.LEFT_TRIAL):
            student.status = Student.Status.LEFT
            student.save(update_fields=['status', 'left_at'])
        return ok({'deleted': True, 'hard': False, 'archived': True, 'status': student.status})

    # Duplicate check on edit: if phone or name is modified, prevent colliding with another student
    if not request.data.get('force'):
        new_phone = normalize_phone(request.data.get('phone')) if 'phone' in request.data else student.phone
        new_first = str(request.data.get('first_name', student.first_name) or '').strip()
        new_last = str(request.data.get('last_name', student.last_name) or '').strip() if 'last_name' in request.data else (student.last_name or '').strip()

        if new_phone and new_first:
            from crm.services import get_phone_variants
            phone_variants = get_phone_variants(new_phone)
            dup_qs = Student.objects.filter(
                company=company,
                phone__in=phone_variants,
                first_name__iexact=new_first,
            ).exclude(pk=student.pk).exclude(status__in=[Student.Status.LEFT, Student.Status.LEFT_TRIAL])
            if new_last:
                dup_qs = dup_qs.filter(last_name__iexact=new_last)

            existing = dup_qs.first()
            if existing:
                full_display = f"{new_first} {new_last}".strip()
                return fail(
                    f'Другой ученик "{full_display}" с номером {new_phone} уже существует в системе',
                    status_code=400
                )

    old_start, old_anchor = student.trial_date, charges.anchor_of(student)
    error = _apply_student_fields(student, company, request.data) or _student_branch_error(request.user, student)
    if error:
        return fail(error)

    # The start date sets the student's months. Once months are charged, moving it rewrites them
    # (a debt could simply be erased that way): only the CEO, and it goes to the journal.
    start_moved = (
        charges.anchor_of(student) != old_anchor
        and StudentCharge.objects.filter(student=student).exists()
    )
    if start_moved and not _is_ceo(request.user):
        return fail(
            'По этой дате старта ученику уже начислены месяцы. Изменить её может только CEO.',
            status_code=403,
        )
    with transaction.atomic():
        debt_before = student_debt_on(student, timezone.localdate()) if start_moved else None
        student.save()  # GroupEnrollment and the month lines are synced by the post_save signals
        if start_moved:
            charges.rebuild(student)
            debt_after = student_debt_on(student, timezone.localdate())
            log_audit(
                company=company, actor=request.user, entity_type='student', entity_id=student.id,
                action='start_date_change',
                old_values={
                    'trial_date': old_start.isoformat() if old_start else None,
                    'debt': debt_before['approx_amount'] if debt_before else 0,
                },
                new_values={
                    'trial_date': student.trial_date.isoformat() if student.trial_date else None,
                    'debt': debt_after['approx_amount'] if debt_after else 0,
                },
                reason=(
                    f'Изменена дата старта ученика {student.full_name}: '
                    f'{old_start.strftime("%d.%m.%Y") if old_start else "—"} → '
                    f'{student.trial_date.strftime("%d.%m.%Y") if student.trial_date else "—"}; '
                    f'долг {_money_text(debt_before["approx_amount"] if debt_before else 0)} → '
                    f'{_money_text(debt_after["approx_amount"] if debt_after else 0)} сум'
                ),
            )
    student = Student.objects.select_related('group', 'branch').get(pk=student.pk)
    return ok(_serialize_student(student, detailed=True))



@api_view(['GET'])
def telegram_config(request):
    config = notifications.load_config()
    enabled = bool(config.get('enabled'))
    username = notifications.get_bot_username(str(config.get('bot_token') or '')) if enabled else None
    return ok({'enabled': enabled, 'bot_username': username})


ALLOWED_PHOTO_CONTENT_TYPES = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
}
MAX_PHOTO_SIZE = 10 * 1024 * 1024


def _delete_photo_file(student: Student) -> None:
    # On Windows the photo file can be briefly locked (antivirus, indexer);
    # clearing the DB field matters more than removing the orphan file.
    try:
        if student.photo:
            student.photo.delete(save=False)
    except OSError:
        pass


@api_view(['POST', 'DELETE'])
def student_photo(request, student_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        student = Student.objects.select_related('group', 'branch').get(
            pk=student_id,
            company=company,
        )
    except Student.DoesNotExist:
        return fail('Student not found', status_code=404)

    if not can_access_student(request.user, student):
        return fail('Student not found', status_code=404)

    if request.method == 'DELETE':
        _delete_photo_file(student)
        student.photo = None
        student.save(update_fields=['photo'])
        return ok(strip_for_teacher(_serialize_student(student), request.user))

    upload = request.FILES.get('photo')
    if upload is None:
        return fail('Photo file is required')
    if upload.size and upload.size > MAX_PHOTO_SIZE:
        return fail('Photo is too large (max 10 MB)')

    content_type = (upload.content_type or '').lower()
    if content_type not in ALLOWED_PHOTO_CONTENT_TYPES:
        return fail('Only JPG, PNG or WEBP images are allowed')

    _delete_photo_file(student)
    extension = ALLOWED_PHOTO_CONTENT_TYPES[content_type]
    student.photo.save(f'student-{student.pk}{extension}', upload, save=True)
    student.refresh_from_db()
    return ok(strip_for_teacher(_serialize_student(student), request.user))


@api_view(['GET', 'POST'])
def lead_list(request):
    company = request.user.company
    if company is None:
        return ok([])

    if request.method == 'POST':
        first_name = (request.data.get('first_name') or '').strip()
        last_name = (request.data.get('last_name') or '').strip()
        if not first_name:
            full_name = (request.data.get('full_name') or '').strip()
            if full_name:
                parts = full_name.split(None, 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ''
            else:
                return fail('First name is required')

        # ✅ ИСПРАВЛЕНО: нормализация
        phone = normalize_phone(request.data.get('phone') or '')
        
        stage_input = request.data.get('status') or request.data.get('stage') or Lead.Stage.TRIAL_BOOKED
        stage = str(stage_input).strip().lower()
        if stage in ('incoming', 'waiting', 'set'):
            stage = Lead.Stage.TRIAL_BOOKED

        if not is_valid_phone(phone):
            return fail('Phone must contain 9 digits')
        if stage not in VALID_LEAD_STAGES:
            return fail('Invalid lead status')
        if stage == Lead.Stage.CONVERTED:
            # D3: CONVERTED only through the conversion endpoint, which creates the Student
            return fail('Для зачисления лида в студенты используйте кнопку перевода')

        phone2_raw = str(request.data.get('phone2') or request.data.get('extra_phone') or '').strip()
        if phone2_raw:
            phone2 = normalize_phone(phone2_raw)
            if not is_valid_phone(phone2):
                return fail('Secondary phone must contain 9 digits')
        else:
            phone2 = ''
        phone2_owner = str(request.data.get('phone2_owner') or '').strip()
        address = str(request.data.get('address') or '').strip()
        comment = str(request.data.get('comment') or request.data.get('notes') or '').strip()
        source = str(request.data.get('source') or '').strip()

        branch = None
        branch_id = request.data.get('branch_id')
        if branch_id:
            try:
                branch = branches_for(request.user, company).get(pk=int(branch_id))
            except (Branch.DoesNotExist, TypeError, ValueError):
                return fail('Invalid branch')
        if branch is None and branch_limit(request.user) is not None:
            # E3: a director's lead always belongs to the director's branch
            branch = branches_for(request.user, company).first()

        course = None
        course_id = request.data.get('course_id')
        if course_id:
            try:
                course = Course.objects.get(pk=int(course_id), company=company)
            except (Course.DoesNotExist, TypeError, ValueError):
                return fail('Invalid course')

        trial_date = parse_date_safe(request.data.get('trial_date')) or timezone.localdate()
        school = str(request.data.get('school') or '').strip()

        # Duplicate check: prevent duplicate active leads with identical phone and name
        if not request.data.get('force'):
            from crm.services import get_phone_variants
            phone_variants = get_phone_variants(phone)

            # 1. Check existing active leads in pipeline
            dup_lead_qs = Lead.objects.filter(
                company=company,
                phone__in=phone_variants,
                first_name__iexact=first_name,
                is_active=True,
            ).exclude(stage__in=[Lead.Stage.REJECTED, Lead.Stage.CONVERTED])
            if last_name:
                dup_lead_qs = dup_lead_qs.filter(last_name__iexact=last_name)

            existing_lead = dup_lead_qs.first()
            if existing_lead:
                full_display = f"{first_name} {last_name}".strip()
                return fail(
                    f'Лид "{full_display}" с номером {phone} уже находится в воронке ({existing_lead.get_stage_display()})',
                    status_code=400
                )

            # 2. Check if student with this name and phone is already studying
            dup_student_qs = Student.objects.filter(
                company=company,
                phone__in=phone_variants,
                first_name__iexact=first_name,
            ).exclude(status__in=[Student.Status.LEFT, Student.Status.LEFT_TRIAL])
            if last_name:
                dup_student_qs = dup_student_qs.filter(last_name__iexact=last_name)

            existing_student = dup_student_qs.first()
            if existing_student:
                full_display = f"{first_name} {last_name}".strip()
                return fail(
                    f'Клиент "{full_display}" с номером {phone} уже является активным учеником',
                    status_code=400
                )

        lead = Lead.objects.create(
            company=company,
            branch=branch,
            course=course,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            phone2=phone2,
            phone2_owner=phone2_owner,
            address=address,
            school=school,
            comment=comment,
            source=source,
            level=str(request.data.get('level') or '').strip(),
            stage=stage,
            trial_date=trial_date,
            is_active=True,
        )
        return ok(_serialize_lead(lead), status_code=201)

    qs = Lead.objects.filter(company=company).select_related('branch', 'course').prefetch_related(
        'converted_students',
    ).order_by('-created_at', '-id')
    qs = scope_branch(qs, request.user)

    archived = request.query_params.get('archived', '0')
    if archived == '1':
        qs = qs.filter(is_active=False)
    elif archived != 'all':
        qs = qs.filter(is_active=True)

    stage = request.query_params.get('status') or request.query_params.get('stage')
    if stage and stage in VALID_LEAD_STAGES:
        qs = qs.filter(stage=stage)

    branch_id = request.query_params.get('branch_id')
    if branch_id:
        try:
            qs = qs.filter(branch_id=int(branch_id))
        except (TypeError, ValueError):
            pass

    course_id = request.query_params.get('course_id')
    if course_id:
        try:
            qs = qs.filter(course_id=int(course_id))
        except (TypeError, ValueError):
            pass

    source = request.query_params.get('source')
    if source:
        qs = qs.filter(source__iexact=source.strip())

    level = request.query_params.get('level')
    if level:
        qs = qs.filter(level__iexact=level.strip())

    query = (request.query_params.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(phone2__icontains=query)
            | Q(phone2_owner__icontains=query)
            | Q(address__icontains=query)
            | Q(school__icontains=query)
            | Q(comment__icontains=query)
            | Q(source__icontains=query)
            | Q(level__icontains=query)
        )

    # ✅ Пагинация
    page = paginate_queryset(qs, request, default_limit=200)

    return ok({
        'count': page['count'],
        'has_more': page['has_more'],
        'next_offset': page['next_offset'],
        'results': [_serialize_lead(lead) for lead in page['results']],
    })


@api_view(['GET', 'PATCH'])
def lead_detail(request, lead_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        lead = Lead.objects.get(pk=lead_id, company=company)
    except Lead.DoesNotExist:
        return fail('Lead not found', status_code=404)
    if not can_access_lead(request.user, lead):
        return fail('Lead not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_lead(lead))

    first_name = request.data.get('first_name')
    last_name = request.data.get('last_name')
    full_name = request.data.get('full_name')
    phone = request.data.get('phone')
    stage = request.data.get('status') if 'status' in request.data else request.data.get('stage')
    is_active = request.data.get('is_active')

    if first_name is not None:
        first_name = str(first_name).strip()
        if not first_name:
            return fail('First name is required')
        lead.first_name = first_name
    elif full_name is not None:
        full_name = str(full_name).strip()
        if not full_name:
            return fail('First name is required')
        parts = full_name.split(None, 1)
        lead.first_name = parts[0]
        lead.last_name = parts[1] if len(parts) > 1 else ''

    if last_name is not None:
        lead.last_name = str(last_name).strip()

    if phone is not None:
        # ✅ Нормализация
        phone = normalize_phone(str(phone))
        if not is_valid_phone(phone):
            return fail('Phone must contain 9 digits')
        lead.phone = phone

    # Duplicate check on edit
    if not request.data.get('force'):
        chk_phone = lead.phone
        chk_first = lead.first_name
        chk_last = lead.last_name

        if chk_phone and chk_first:
            from crm.services import get_phone_variants
            phone_variants = get_phone_variants(chk_phone)
            dup_qs = Lead.objects.filter(
                company=company,
                phone__in=phone_variants,
                first_name__iexact=chk_first,
                is_active=True,
            ).exclude(pk=lead.pk).exclude(stage__in=[Lead.Stage.REJECTED, Lead.Stage.CONVERTED])
            if chk_last:
                dup_qs = dup_qs.filter(last_name__iexact=chk_last)
            existing = dup_qs.first()
            if existing:
                full_display = f"{chk_first} {chk_last}".strip()
                return fail(
                    f'Другой лид "{full_display}" с номером {chk_phone} уже находится в воронке ({existing.get_stage_display()})',
                    status_code=400
                )

    if 'phone2' in request.data or 'extra_phone' in request.data:
        p2_raw = str(request.data.get('phone2') or request.data.get('extra_phone') or '').strip()
        if p2_raw:
            p2 = normalize_phone(p2_raw)
            if not is_valid_phone(p2):
                return fail('Secondary phone must contain 9 digits')
            lead.phone2 = p2
        else:
            lead.phone2 = ''

    if 'phone2_owner' in request.data:
        lead.phone2_owner = str(request.data.get('phone2_owner') or '').strip()

    if 'address' in request.data:
        lead.address = str(request.data.get('address') or '').strip()

    if 'school' in request.data:
        lead.school = str(request.data.get('school') or '').strip()

    if 'comment' in request.data:
        lead.comment = str(request.data.get('comment') or '').strip()
    elif 'notes' in request.data:
        lead.comment = str(request.data.get('notes') or '').strip()

    if 'source' in request.data:
        lead.source = str(request.data.get('source') or '').strip()

    if 'level' in request.data:
        lead.level = str(request.data.get('level') or '').strip()

    if 'branch_id' in request.data:
        bid = request.data.get('branch_id')
        if not bid:
            if branch_limit(request.user) is None:
                lead.branch = None
        else:
            try:
                lead.branch = branches_for(request.user, company).get(pk=int(bid))
            except (Branch.DoesNotExist, TypeError, ValueError):
                return fail('Invalid branch')

    if 'course_id' in request.data:
        cid = request.data.get('course_id')
        if not cid:
            lead.course = None
        else:
            try:
                lead.course = Course.objects.get(pk=int(cid), company=company)
            except (Course.DoesNotExist, TypeError, ValueError):
                return fail('Invalid course')

    if 'trial_date' in request.data:
        lead.trial_date = parse_date_safe(request.data.get('trial_date'))

    if stage is not None:
        stage = str(stage).strip().lower()
        if stage not in VALID_LEAD_STAGES:
            return fail('Invalid lead stage')
        if stage == Lead.Stage.CONVERTED and lead.stage != Lead.Stage.CONVERTED:
            return fail('Для зачисления лида в студенты используйте кнопку перевода')
        if lead.stage == Lead.Stage.CONVERTED and stage != Lead.Stage.CONVERTED:
            if lead.converted_students.exists():
                return fail('Нельзя сменить статус — студент уже зачислен')
        lead.stage = stage
        if stage == Lead.Stage.ATTENDED:
            lead.attended_trial = True

    if is_active is not None:
        lead.is_active = bool(is_active)

    lead.save()
    return ok(_serialize_lead(lead))


@api_view(['POST'])
def lead_archive(request, lead_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        lead = Lead.objects.get(pk=lead_id, company=company)
    except Lead.DoesNotExist:
        return fail('Lead not found', status_code=404)
    if not can_access_lead(request.user, lead):
        return fail('Lead not found', status_code=404)

    lead.is_active = False
    lead.save(update_fields=['is_active'])
    return ok(_serialize_lead(lead))


@api_view(['POST'])
def lead_convert_to_student(request, lead_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)

    from accounts.rbac import user_has_permission, PERM_STUDENTS_WRITE, PERM_LEADS_WRITE
    if not user_has_permission(request.user, PERM_LEADS_WRITE) or not user_has_permission(request.user, PERM_STUDENTS_WRITE):
        return fail('You do not have permission to perform this action.', status_code=403)

    with transaction.atomic():
        # Take the write lock first, so a double click cannot convert the same lead twice
        # (SQLite ignores select_for_update; an UPDATE makes the second request wait for the first).
        Lead.objects.filter(pk=lead_id, company=company).update(stage=F('stage'))
        try:
            lead = Lead.objects.select_for_update().get(pk=lead_id, company=company)
        except Lead.DoesNotExist:
            return fail('Lead not found', status_code=404)
        if not can_access_lead(request.user, lead):
            return fail('Lead not found', status_code=404)

        active_student = lead.converted_students.exclude(
            status__in=[Student.Status.LEFT, Student.Status.LEFT_TRIAL],
        ).order_by('-id').first()
        if active_student:
            return fail(f'Этот лид уже зачислен как студент ({active_student.full_name}).', status_code=400)

        first_name = (request.data.get('first_name') or '').strip()
        last_name = (request.data.get('last_name') or '').strip()
        if not first_name:
            first_name = lead.first_name
            last_name = lead.last_name
        if not first_name and lead.full_name:
            parts = lead.full_name.strip().split(None, 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ''
        if not first_name:
            return fail('First name is required')

        phone = normalize_phone(request.data.get('phone') or lead.phone or '')
        if not is_valid_phone(phone):
            return fail('Phone must contain 9 digits')

        if not request.data.get('force'):
            duplicate = _active_student_duplicate(company, phone, first_name, last_name)
            if duplicate:
                return fail(
                    f'Ученик "{duplicate.full_name}" с номером {phone} уже учится. '
                    'Откройте его карточку вместо создания нового студента.',
                    status_code=400,
                )

        phone2_raw = str(request.data.get('phone2') if 'phone2' in request.data else (lead.phone2 or '')).strip()
        if phone2_raw:
            phone2 = normalize_phone(phone2_raw)
            if not is_valid_phone(phone2):
                return fail('Secondary phone must contain 9 digits')
        else:
            phone2 = ''
        phone2_owner = str(request.data.get('phone2_owner') or lead.phone2_owner or '').strip()
        address = str(request.data.get('address') or lead.address or '').strip()
        comment = str(request.data.get('comment') or lead.comment or '').strip()

        group = None
        group_id = request.data.get('group_id')
        if group_id:
            try:
                group = Group.objects.select_related('branch', 'course', 'room').get(pk=int(group_id), company=company)
            except (Group.DoesNotExist, TypeError, ValueError):
                return fail('Invalid group')
            if not branch_allowed(request.user, group.branch_id):
                return fail('Invalid group')
            branch = group.branch
        else:
            branch_id = request.data.get('branch_id')
            if not branch_id:
                branch = lead.branch
                if not branch:
                    branch = branches_for(request.user, company).order_by('id').first()
                if not branch:
                    return fail('No branch available in company')
            else:
                try:
                    branch = branches_for(request.user, company).get(pk=int(branch_id))
                except (Branch.DoesNotExist, TypeError, ValueError):
                    return fail('Invalid branch')

        raw_status = request.data.get('status')
        if raw_status is not None:
            status = safe_int(raw_status, default=Student.Status.STUDYING)
            if status in (5, 6):
                status = Student.Status.STUDYING
            elif status not in VALID_STUDENT_STATUSES:
                status = Student.Status.STUDYING
        else:
            status = Student.Status.STUDYING

        school = str(request.data.get('school') if 'school' in request.data else (lead.school or '')).strip()
        telegram = str(request.data.get('telegram') or '').strip()
        parent_telegram = str(request.data.get('parent_telegram') or '').strip()
        level = str(request.data.get('level') if 'level' in request.data else (lead.level or '')).strip()
        # Payment anchor: the date sent by the form, otherwise today (never the old trial lesson date)
        trial_date = parse_date_safe(request.data.get('trial_date')) or timezone.localdate()

        student = Student.objects.create(
            company=company,
            branch=branch,
            group=group,
            lead=lead,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            phone2=phone2,
            phone2_owner=phone2_owner,
            address=address,
            comment=comment,
            level=level,
            school=school,
            telegram=telegram,
            parent_telegram=parent_telegram,
            status=status,
            trial_date=trial_date,
        )

        lead_name = lead.full_name or f'{first_name} {last_name}'.strip()
        lead_id_val = lead.id

        lead.stage = Lead.Stage.CONVERTED
        raw_attended = request.data.get('attended_trial')
        if raw_attended is not None:
            lead.attended_trial = str(raw_attended).lower() not in ('false', '0', '')
        update_fields = ['stage', 'attended_trial']
        if branch and lead.branch != branch:
            lead.branch = branch
            update_fields.append('branch')
        if group and group.course and lead.course != group.course:
            lead.course = group.course
            update_fields.append('course')
        if not lead.school and school:
            lead.school = school
            update_fields.append('school')
        lead.save(update_fields=update_fields)

        try:
            log_audit(
                company=company,
                actor=request.user,
                entity_type='lead',
                entity_id=lead.id,
                action='convert',
                new_values={'student_id': student.pk},
                reason=f'Lead "{lead_name}" converted to student',
            )
        except Exception:
            pass

        student = Student.objects.select_related('group', 'branch').get(pk=student.pk)
        return ok({
            'student': _serialize_student(student, detailed=True),
            'lead_id': lead_id_val,
            'converted': True,
        }, status_code=201)


def _serialize_course(course: Course, *, detailed: bool = False) -> dict:
    planned = next_price(course)
    payload = {
        'id': course.id,
        'name': course.name,
        'code': course.code,
        'price': course.price,
        # A price that is already set but starts later ("с 1 ноября — 600 000")
        'next_price': (
            {'price': int(planned.price), 'valid_from': planned.valid_from.isoformat()} if planned else None
        ),
        'lesson_duration': course.lesson_duration,
        'course_duration': course.course_duration,
        'description': course.description,
    }
    if detailed:
        payload['price_history'] = price_history(course)
    return payload


def _is_ceo(user) -> bool:
    return user.is_superuser or get_effective_role(user) == ROLE_CEO


def _parse_price(raw) -> int | None:
    """Whole sum from 0 to 100 000 000 ("500 000" is fine); anything else -> None."""
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, float):
        if not raw.is_integer():
            return None
        raw = int(raw)
    text = str(raw).strip().replace(' ', '').replace('\u00a0', '')
    if not text.isdigit():
        return None
    value = int(text)
    return value if value <= 100_000_000 else None


def _money_text(value) -> str:
    return f'{int(value or 0):,}'.replace(',', ' ')


@api_view(['GET', 'POST'])
def course_list(request):
    company = request.user.company
    if company is None:
        return ok([])

    if request.method == 'POST':
        name = (request.data.get('name') or '').strip()
        if not name:
            return fail('Course name is required')

        code = (request.data.get('code') or '').strip().lower()
        
        # ✅ ИСПРАВЛЕНО: гибкая валидация (не только CEFR)
        is_valid, error_msg = validate_course_code(code)
        if not is_valid:
            return fail(error_msg)

        # ✅ Проверка на дубликат внутри компании
        if Course.objects.filter(company=company, code=code).exists():
            return fail(f'Course with code "{code}" already exists')

        # ✅ ИСПРАВЛЕНО: безопасные числа
        price = _parse_price(request.data.get('price') if request.data.get('price') not in (None, '') else 0)
        if price is None:
            return fail('Цена — целое число от 0 до 100 000 000.')
        lesson_duration = safe_int(request.data.get('lesson_duration'), default=90,
                                  min_val=15, max_val=480)
        course_duration = safe_int(request.data.get('course_duration'), default=12,
                                  min_val=1, max_val=120)
        description = (request.data.get('description') or '').strip()

        # The first price record is written by the post_save signal (crm/pricing.py)
        course = Course.objects.create(
            company=company,
            name=name,
            code=code,
            price=price,
            lesson_duration=lesson_duration,
            course_duration=course_duration,
            description=description,
        )
        return ok(_serialize_course(course), status_code=201)

    data = [
        _serialize_course(course)
        for course in Course.objects.filter(company=company).prefetch_related('prices')
    ]
    return ok(data)


@api_view(['GET', 'PATCH', 'DELETE'])
def course_detail(request, course_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        course = Course.objects.get(pk=course_id, company=company)
    except Course.DoesNotExist:
        return fail('Course not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_course(course, detailed=True))

    if request.method == 'DELETE':
        # Owner (2026-10-05): a course sets the price of its groups — only the CEO removes one,
        # and never from under a group (the groups used to lose their price silently)
        if not _is_ceo(request.user):
            return fail('Удалить курс может только CEO.', status_code=403)
        groups_count = Group.objects.filter(course=course).count()
        if groups_count:
            return fail(
                f'Нельзя удалить курс: на нём есть группы ({groups_count}). Сначала переведите их на другой курс.'
            )
        from finance.models import SalarySetting
        if SalarySetting.objects.filter(course=course).exists():
            return fail('Нельзя удалить курс: для него задан процент учителя. Сначала удалите эту ставку в «Зарплатах».')
        log_audit(
            company=company, actor=request.user, entity_type='course', entity_id=course.id, action='delete',
            old_values={'name': course.name, 'price': course.price},
            reason=f'Удалён курс «{course.name}» (цена {_money_text(course.price)} сум)',
        )
        course.delete()
        return ok({'deleted': True})

    name = request.data.get('name')
    if name is not None:
        name = str(name).strip()
        if not name:
            return fail('Course name is required')
        course.name = name

    if 'code' in request.data:
        code = str(request.data.get('code') or '').strip().lower()

        # A course keeps the code it already has: old ones may not fit today's rule (Cyrillic «а1»),
        # and the edit form sends the code with every save — the price could not be changed at all
        if code != (course.code or '').strip().lower():
            is_valid, error_msg = validate_course_code(code)
            if not is_valid:
                return fail(error_msg)

            # Проверка на дубликат (исключая текущий)
            if Course.objects.filter(
                company=company, code=code
            ).exclude(pk=course.pk).exists():
                return fail(f'Course with code "{code}" already exists')

            course.code = code

    # Price (owner, 2026-10-05): never overwritten — "from this day the course costs X". Only the CEO.
    price_change = None
    if 'price' in request.data:
        new_price = _parse_price(request.data.get('price'))
        if new_price is None:
            return fail('Цена — целое число от 0 до 100 000 000.')
        price_from = timezone.localdate()
        if request.data.get('price_from') not in (None, ''):
            price_from = parse_date_safe(request.data.get('price_from'))
            if price_from is None:
                return fail('Неверная дата «действует с».')
        # The edit form always sends the price: it is a change only when it differs on that day
        if new_price != price_on(course, price_from):
            if not _is_ceo(request.user):
                return fail('Цену курса меняет только CEO.', status_code=403)
            price_change = (new_price, price_from)

    if 'lesson_duration' in request.data:
        course.lesson_duration = safe_int(
            request.data.get('lesson_duration'), default=90,
            min_val=15, max_val=480
        )

    if 'course_duration' in request.data:
        course.course_duration = safe_int(
            request.data.get('course_duration'), default=12,
            min_val=1, max_val=120
        )

    if 'description' in request.data:
        course.description = str(request.data.get('description') or '').strip()

    with transaction.atomic():
        if price_change:
            new_price, price_from = price_change
            old_price = price_on(course, price_from)
            set_price(course, new_price, price_from, request.user)
            log_audit(
                company=company, actor=request.user, entity_type='course', entity_id=course.id,
                action='price_change',
                old_values={'price': old_price},
                new_values={'price': new_price, 'valid_from': price_from.isoformat()},
                reason=(
                    f'Цена курса «{course.name}»: {_money_text(old_price)} → {_money_text(new_price)} сум, '
                    f'действует с {price_from.strftime("%d.%m.%Y")}'
                ),
            )
        course.save()
    return ok(_serialize_course(course, detailed=True))


@api_view(['PATCH', 'DELETE'])
def course_price_detail(request, course_id: int, price_id: int):
    """Fix or remove one record of a course's price history (a wrong sum or date was typed). CEO only."""
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)
    if not _is_ceo(request.user):
        return fail('Цену курса меняет только CEO.', status_code=403)
    try:
        course = Course.objects.get(pk=course_id, company=company)
        entry = CoursePrice.objects.get(pk=price_id, course=course)
    except (Course.DoesNotExist, CoursePrice.DoesNotExist):
        return fail('Запись о цене не найдена.', status_code=404)
    day_text = entry.valid_from.strftime('%d.%m.%Y')

    if request.method == 'DELETE':
        if CoursePrice.objects.filter(course=course).count() <= 1:
            return fail('Единственную цену удалить нельзя — исправьте её.')
        with transaction.atomic():
            log_audit(
                company=company, actor=request.user, entity_type='course', entity_id=course.id,
                action='price_delete',
                old_values={'price': int(entry.price), 'valid_from': entry.valid_from.isoformat()},
                reason=f'Удалена цена курса «{course.name}»: {_money_text(entry.price)} сум с {day_text}',
            )
            entry.delete()
            sync_course(course)
        return ok(_serialize_course(course, detailed=True))

    old = {'price': int(entry.price), 'valid_from': entry.valid_from.isoformat()}
    if 'price' in request.data:
        new_price = _parse_price(request.data.get('price'))
        if new_price is None:
            return fail('Цена — целое число от 0 до 100 000 000.')
        entry.price = new_price
    if 'valid_from' in request.data:
        new_day = parse_date_safe(request.data.get('valid_from'))
        if new_day is None:
            return fail('Неверная дата «действует с».')
        if CoursePrice.objects.filter(course=course, valid_from=new_day).exclude(pk=entry.pk).exists():
            return fail('На эту дату уже есть другая цена.')
        entry.valid_from = new_day
    new = {'price': int(entry.price), 'valid_from': entry.valid_from.isoformat()}
    if new != old:
        with transaction.atomic():
            entry.save()
            note = ''
            if new['price'] != old['price']:
                # The wrong sum was typed: months already written at it and not paid at all get the right one
                records = list(CoursePrice.objects.filter(course=course).order_by('valid_from', 'id'))
                position = next(i for i, record in enumerate(records) if record.pk == entry.pk)
                fixed, untouched = charges.reprice_unpaid(
                    course, old['price'], new['price'],
                    valid_from=None if position == 0 else entry.valid_from,
                    valid_until=records[position + 1].valid_from if position + 1 < len(records) else None,
                )
                note = f'; неоплаченных месяцев учеников исправлено: {fixed}'
                if untouched:
                    note += f', с оплатами оставлено как было: {untouched}'
            log_audit(
                company=company, actor=request.user, entity_type='course', entity_id=course.id,
                action='price_fix', old_values=old, new_values=new,
                reason=(
                    f'Исправлена цена курса «{course.name}»: {_money_text(old["price"])} сум с {day_text} → '
                    f'{_money_text(entry.price)} сум с {entry.valid_from.strftime("%d.%m.%Y")}{note}'
                ),
            )
            sync_course(course)
    return ok(_serialize_course(course, detailed=True))
