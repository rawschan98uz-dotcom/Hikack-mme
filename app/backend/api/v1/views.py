import re
from datetime import date, datetime, time, timedelta

from django.contrib.auth import authenticate
from django.db.models import Count, Q
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import TeacherBranch, User
from accounts.rbac import get_effective_role, get_role_label, get_user_permissions
from api.responses import fail, ok
from api.scope import filter_groups_queryset, filter_students_queryset, teacher_can_access_group, teacher_can_access_student
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
from crm.models import Course, Group, Lead, Student
from finance.models import Payment
from operations import notify as notifications
from operations.models import ActivityLog, Reminder, Tag
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


def _serialize_lead(lead: Lead) -> dict:
    converted_student_id = (
        lead.converted_students.values_list('id', flat=True).first()
        if lead.stage == Lead.Stage.CONVERTED
        else None
    )
    student_deleted = (
        lead.stage == Lead.Stage.CONVERTED
        and converted_student_id is None
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


def _serialize_group(group: Group, *, detailed: bool = False) -> dict:
    week = _week_of_study(group)
    payload = {
        'id': group.id,
        'name': group.name,
        'days': group.days,
        'days_label': group.get_days_display(),
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
        'students_count': getattr(group, 'students_count', group.students.count()),
        'tags': [{'id': tag.id, 'name': tag.name} for tag in group.tags.all()],
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
            for student in group.students.order_by('first_name', 'last_name')[:100]
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
                group.teacher = User.objects.get(
                    pk=int(teacher_id),
                    company=company,
                    user_type=User.UserType.TEACHER,
                )
            except (User.DoesNotExist, TypeError, ValueError):
                return 'Invalid teacher'

    days = data.get('days')
    if days is not None:
        try:
            days = int(days)
        except (TypeError, ValueError):
            return 'Invalid schedule'
        if days not in VALID_GROUP_DAYS:
            return 'Invalid schedule'
        group.days = days

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
                group.room = Room.objects.get(pk=int(room_id), branch__company=company)
            except (Room.DoesNotExist, TypeError, ValueError):
                return 'Invalid room'

    return None




def _add_months(d: date, num_months: int) -> date:
    import calendar
    year = d.year + (d.month - 1 + num_months) // 12
    month = (d.month - 1 + num_months) % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, max_day))


def _get_student_payment_info(student: Student, info: dict | None = None) -> dict:
    if info is None:
        payments = Payment.objects.filter(
            Q(company=student.company) &
            (Q(student=student) | Q(student_name=student.full_name))
        )
        from django.db.models import Sum
        months_covered = payments.aggregate(total=Sum('months_covered'))['total'] or 0
        last = payments.order_by('-created_at').first()
        first = payments.order_by('created_at').first()
        last_date = timezone.localtime(last.created_at).date() if last else None
        first_date = timezone.localtime(first.created_at).date() if first else None
    else:
        months_covered = info.get('months_covered', info.get('count', 0))
        last_date = info.get('last_date')
        first_date = info.get('first_date')

    offset = getattr(student, 'payment_offset', 0) or 0
    effective_count = max(0, months_covered - offset)
    anchor_date = student.trial_date or first_date or student.created_at.date()
    next_due = _add_months(anchor_date, effective_count)

    today = timezone.localdate()
    # A student is only a debtor if currently studying and next payment due date is in the past
    is_debtor = (student.status == Student.Status.STUDYING) and (today > next_due)
    overdue_days = (today - next_due).days if is_debtor else 0

    return {
        'last_payment_date': last_date,
        'next_payment_date': next_due,
        'is_debtor': is_debtor,
        'overdue_days': overdue_days,
        'paid_count': effective_count,
    }


def _company_payments_summary(company: Company) -> dict:
    from django.db.models import Count, Max, Min, Sum
    rows = (
        Payment.objects.filter(company=company)
        .values('student_id', 'student_name')
        .annotate(
            count=Count('id'),
            total_months=Sum('months_covered'),
            last_created=Max('created_at'),
            first_created=Min('created_at'),
        )
    )
    summary = {}
    for r in rows:
        item = {
            'count': r['count'],
            'months_covered': r['total_months'] or r['count'],
            'last_date': timezone.localtime(r['last_created']).date() if r['last_created'] else None,
            'first_date': timezone.localtime(r['first_created']).date() if r['first_created'] else None,
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
        if r['student_name']:
            sname = r['student_name']
            if sname in summary:
                summary[sname]['count'] += item['count']
                summary[sname]['months_covered'] += item['months_covered']
                if item['last_date'] and (not summary[sname]['last_date'] or item['last_date'] > summary[sname]['last_date']):
                    summary[sname]['last_date'] = item['last_date']
                if item['first_date'] and (not summary[sname]['first_date'] or item['first_date'] < summary[sname]['first_date']):
                    summary[sname]['first_date'] = item['first_date']
            else:
                summary[sname] = dict(item)
    return summary


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
        'balance': student.balance,
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
        'payment_offset': student.payment_offset,
        'branch_id': student.branch_id,
        'branch': student.branch.name if student.branch_id else '—',
        'group_id': student.group_id,
        'group': student.group.name if student.group_id else None,
        'group_teacher': student.group.teacher.display_name() if (student.group and student.group.teacher) else '',
        'course_price': student.group.course.price if (student.group and student.group.course) else 0,
        'course_name': student.group.course.name if (student.group and student.group.course) else '',
        'created_at': student.created_at.isoformat(),
    }
    if detailed:
        payload['telegram_code'] = student.telegram_code
    return payload


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
            if len(p2) < 9:
                return 'Secondary phone must contain at least 9 digits'
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
        if len(phone) < 9:
            return 'Phone must contain at least 9 digits'
        student.phone = phone

    was_frozen = bool(student.pk and student.status == Student.Status.FROZEN)
    status = data.get('status')
    if status is not None:
        status = safe_int(status, default=None)
        if status is None or status not in VALID_STUDENT_STATUSES:
            return 'Invalid status'
        if was_frozen and status == Student.Status.STUDYING:
            current_payments_count = Payment.objects.filter(
                company=company, student_name=student.full_name
            ).count()
            student.payment_offset = current_payments_count
            if 'trial_date' in data:
                student.trial_date = parse_date_safe(data.get('trial_date')) or timezone.localdate()
            else:
                student.trial_date = timezone.localdate()
        student.status = status
    elif data.get('unfreeze'):
        if was_frozen:
            current_payments_count = Payment.objects.filter(
                company=company, student_name=student.full_name
            ).count()
            student.payment_offset = current_payments_count
            if 'trial_date' in data:
                student.trial_date = parse_date_safe(data.get('trial_date')) or timezone.localdate()
            else:
                student.trial_date = timezone.localdate()
            student.status = Student.Status.STUDYING

    if 'payment_offset' in data:
        student.payment_offset = max(0, safe_int(data.get('payment_offset'), default=0))

    if 'balance' in data:
        # ✅ ИСПРАВЛЕНО: safe_int с ограничениями
        student.balance = safe_int(
            data.get('balance'), default=0,
            min_val=-100_000_000, max_val=100_000_000
        )

    if 'paid_this_month' in data:
        student.paid_this_month = bool(data.get('paid_this_month'))

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
            student.branch = Branch.objects.get(pk=int(branch_id), company=company)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return 'Invalid branch'

    group_id = data.get('group_id')
    if group_id is not None:
        if group_id in ('', None):
            student.group = None
        else:
            try:
                group = Group.objects.get(pk=int(group_id), company=company)
            except (Group.DoesNotExist, TypeError, ValueError):
                return 'Invalid group'
            student.group = group
            if student.branch_id and group.branch_id != student.branch_id:
                student.branch = group.branch

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
        'balance_mode': company.balance_mode,
        'payment_mode_label': _payment_mode_label(company.balance_mode),
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
        for branch in Branch.objects.filter(company=company).order_by('id')
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
@permission_classes([IsAuthenticated])
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
    phone = request.data.get('phone') or request.data.get('username')
    password = request.data.get('password')
    if not phone or not password:
        return fail('Phone and password are required')

    user = authenticate(request, phone=phone, password=password)
    if user is None:
        return fail('Invalid credentials', 401)

    refresh = RefreshToken.for_user(user)
    return ok({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': _serialize_user(user),
    })


@api_view(['GET', 'POST', 'PATCH'])
@permission_classes([IsAuthenticated])
def auth_me(request):
    user = request.user

    if request.method == 'PATCH':
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
            phone = ''.join(ch for ch in str(phone) if ch.isdigit())
            if len(phone) < 9:
                return fail('Phone must contain at least 9 digits')
            if User.objects.filter(phone=phone).exclude(pk=user.pk).exists():
                return fail('Phone already exists')
            user.phone = phone

        password = request.data.get('password')
        if password:
            user.set_password(str(password))

        user.save()
        return ok(_serialize_user(user))

    return ok(_serialize_user(user))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def branch_list(request):
    company = request.user.company
    if company is None:
        return ok([])
    branches = Branch.objects.filter(company=company).order_by('id')
    data = [{'id': b.id, 'name': b.name, 'address': b.address} for b in branches]
    return ok(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    company = request.user.company
    if company is None:
        return ok({})

    students = Student.objects.filter(company=company)
    groups = Group.objects.filter(company=company, status=Group.Status.ACTIVE)
    groups = filter_groups_queryset(groups, request.user)
    active_leads_count = Lead.objects.filter(
        company=company,
        is_active=True,
        stage__in=[Lead.Stage.TRIAL_BOOKED, Lead.Stage.ATTENDED],
    ).count()

    six_months_ago = timezone.now() - timedelta(days=180)
    monthly_payments = (
        Payment.objects.filter(company=company, created_at__gte=six_months_ago)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Sum('amount'))
        .order_by('month')
    )
    finance_chart = [
        {
            'label': row['month'].strftime('%b %Y'),
            'value': int(row['total'] or 0),
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
            'status': reminder.status,
            'assigned_to': reminder.assigned_to.display_name() if reminder.assigned_to else '—',
        }
        for reminder in Reminder.objects.filter(
            company=company,
            status__in=[Reminder.Status.OVERDUE, Reminder.Status.TODAY],
        ).select_related('assigned_to').order_by('due_date', 'id')[:8]
    ]

    studying_students = students.filter(status=Student.Status.STUDYING)
    payments_summary = _company_payments_summary(company)
    debtors_count = sum(
        1 for s in studying_students
        if _get_student_payment_info(s, payments_summary.get(s.id) or payments_summary.get(s.full_name))['is_debtor']
    )

    return ok({
        'active_leads': active_leads_count,
        'active_students': studying_students.count(),
        'groups': groups.count(),
        'debtors': debtors_count,
        'trial_students': 0,
        'paid_during_month': students.filter(paid_this_month=True).count(),
        'left_active_group': students.filter(status=Student.Status.LEFT).count(),
        'left_after_trial': students.filter(status=Student.Status.LEFT_TRIAL).count(),
        'finance_chart': finance_chart,
        'schedule': schedule,
        'reminders': reminders,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def schedule_list(request):
    company = request.user.company
    if company is None:
        return ok([])

    groups = Group.objects.filter(company=company, status=Group.Status.ACTIVE)
    groups = filter_groups_queryset(groups, request.user)
    return ok(_serialize_schedule_rows(groups))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
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
            branch = Branch.objects.get(pk=int(branch_id), company=company)
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

        # Сохраняем
        group.save()

        # Устанавливаем теги (уже валидированы)
        if tag_ids is not None:
            group.tags.set(existing_tags)

        # Перезагружаем для получения annotations
        group = Group.objects.select_related(
            'course', 'branch', 'teacher', 'room'
        ).prefetch_related('tags').annotate(
            students_count=Count('students')
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
    ).prefetch_related('tags').annotate(students_count=Count('students')).order_by('name')
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
@permission_classes([IsAuthenticated])
def group_detail(request, group_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        group = Group.objects.select_related(
            'course', 'branch', 'teacher', 'room'
        ).prefetch_related('tags').annotate(
            students_count=Count('students')
        ).get(pk=group_id, company=company)
    except Group.DoesNotExist:
        return fail('Group not found', status_code=404)

    if not teacher_can_access_group(request.user, group):
        return fail('Group not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_group(group, detailed=True))

    if request.method == 'DELETE':
        group.delete()
        return ok({'deleted': True})

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

    error = _apply_group_fields(group, company, request.data)
    if error:
        return fail(error)

    group.save()

    if tag_ids is not None:
        group.tags.set(existing_tags)

    # Перезагружаем
    group = Group.objects.select_related(
        'course', 'branch', 'teacher', 'room'
    ).prefetch_related('tags').annotate(
        students_count=Count('students')
    ).get(pk=group.pk)

    return ok(_serialize_group(group))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
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
        if len(phone) < 9:
            return fail('Phone must contain at least 9 digits')

        branch_id = request.data.get('branch_id')
        if not branch_id:
            return fail('Branch is required')
        try:
            branch = Branch.objects.get(pk=int(branch_id), company=company)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return fail('Invalid branch')

        status = safe_int(request.data.get('status', Student.Status.TRIAL),
                         default=Student.Status.TRIAL)
        if status not in VALID_STUDENT_STATUSES:
            return fail('Invalid status')

        trial_date_raw = request.data.get('trial_date')
        if not trial_date_raw:
            return fail('Trial / start date is required')
        trial_date = parse_date_safe(trial_date_raw)
        if not trial_date:
            return fail('Invalid trial / start date format')

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
            error = _apply_student_fields(student, company, request.data)
            if error:
                return fail(error)

            # Brothers logic: search by phone+name first (exact person), then phone only (family)
            phone_variants = [student.phone, f'998{student.phone}', f'+998{student.phone}']
            exact_lead = Lead.objects.filter(
                company=company,
                phone__in=phone_variants,
                first_name__iexact=student.first_name
            ).order_by('-created_at').first()

            if exact_lead:
                # Same person — link and mark as converted
                student.lead = exact_lead
                if exact_lead.stage != Lead.Stage.CONVERTED:
                    exact_lead.stage = Lead.Stage.CONVERTED
                    update_fields = ['stage']
                    if not exact_lead.branch and student.branch:
                        exact_lead.branch = student.branch
                        update_fields.append('branch')
                    if not exact_lead.course and student.group and student.group.course:
                        exact_lead.course = student.group.course
                        update_fields.append('course')
                    if not exact_lead.school and student.school:
                        exact_lead.school = student.school
                        update_fields.append('school')
                    exact_lead.save(update_fields=update_fields)
            else:
                # Different name = family member — copy family fields from matching leads, don't touch lead's stage
                family_leads = Lead.objects.filter(
                    company=company,
                    phone__in=phone_variants
                ).order_by('-created_at')
                for fl in family_leads:
                    if not student.school and fl.school:
                        student.school = fl.school
                    if not student.address and fl.address:
                        student.address = fl.address
                    if not student.phone2 and fl.phone2:
                        student.phone2 = fl.phone2
                        if not student.phone2_owner and fl.phone2_owner:
                            student.phone2_owner = fl.phone2_owner

            student.save()
            student = Student.objects.select_related('group', 'branch').get(pk=student.pk)
            return ok(_serialize_student(student, detailed=True), status_code=201)

    # GET
    qs = Student.objects.filter(company=company).select_related(
        'group', 'branch'
    ).order_by('first_name', 'last_name')
    qs = filter_students_queryset(qs, request.user)

    payments_summary = _company_payments_summary(company)

    debtors_filter = (
        request.query_params.get('debtors') == '1'
        or request.query_params.get('statuses') in ('6', 'debtor', 'debtors')
    )
    if debtors_filter:
        studying_students = list(qs.filter(status=Student.Status.STUDYING))
        debtor_ids = [
            s.id for s in studying_students
            if _get_student_payment_info(s, payments_summary.get(s.id) or payments_summary.get(s.full_name))['is_debtor']
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

    finance = request.query_params.get('finance')
    if finance == 'paid_during_the_month':
        qs = qs.filter(paid_this_month=True)

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
            _serialize_student(s, payment_info=_get_student_payment_info(s, payments_summary.get(s.id) or payments_summary.get(s.full_name)))
            for s in page['results']
        ],
    })


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
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

    if not teacher_can_access_student(request.user, student):
        return fail('Student not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_student(student, detailed=True))

    if request.method == 'DELETE':
        student.delete()
        return ok({'deleted': True})

    error = _apply_student_fields(student, company, request.data)
    if error:
        return fail(error)
    student.save()
    student = Student.objects.select_related('group', 'branch').get(pk=student.pk)
    return ok(_serialize_student(student, detailed=True))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
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

    if not teacher_can_access_student(request.user, student):
        return fail('Student not found', status_code=404)

    if request.method == 'DELETE':
        _delete_photo_file(student)
        student.photo = None
        student.save(update_fields=['photo'])
        return ok(_serialize_student(student))

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
    return ok(_serialize_student(student))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
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

        if len(phone) < 9:
            return fail('Phone must contain at least 9 digits')
        if stage not in VALID_LEAD_STAGES:
            return fail('Invalid lead status')

        phone2_raw = str(request.data.get('phone2') or request.data.get('extra_phone') or '').strip()
        if phone2_raw:
            phone2 = normalize_phone(phone2_raw)
            if len(phone2) < 9:
                return fail('Secondary phone must contain at least 9 digits')
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
                branch = Branch.objects.get(pk=int(branch_id), company=company)
            except (Branch.DoesNotExist, TypeError, ValueError):
                pass

        course = None
        course_id = request.data.get('course_id')
        if course_id:
            try:
                course = Course.objects.get(pk=int(course_id), company=company)
            except (Course.DoesNotExist, TypeError, ValueError):
                pass

        trial_date = parse_date_safe(request.data.get('trial_date')) or timezone.localdate()
        school = str(request.data.get('school') or '').strip()

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

    qs = Lead.objects.filter(company=company).select_related('branch', 'course').order_by('-created_at', '-id')

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
@permission_classes([IsAuthenticated])
def lead_detail(request, lead_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        lead = Lead.objects.get(pk=lead_id, company=company)
    except Lead.DoesNotExist:
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
        if len(phone) < 9:
            return fail('Phone must contain at least 9 digits')
        lead.phone = phone

    if 'phone2' in request.data or 'extra_phone' in request.data:
        p2_raw = str(request.data.get('phone2') or request.data.get('extra_phone') or '').strip()
        if p2_raw:
            p2 = normalize_phone(p2_raw)
            if len(p2) < 9:
                return fail('Secondary phone must contain at least 9 digits')
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
            lead.branch = None
        else:
            try:
                lead.branch = Branch.objects.get(pk=int(bid), company=company)
            except (Branch.DoesNotExist, TypeError, ValueError):
                pass

    if 'course_id' in request.data:
        cid = request.data.get('course_id')
        if not cid:
            lead.course = None
        else:
            try:
                lead.course = Course.objects.get(pk=int(cid), company=company)
            except (Course.DoesNotExist, TypeError, ValueError):
                pass

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
@permission_classes([IsAuthenticated])
def lead_archive(request, lead_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        lead = Lead.objects.get(pk=lead_id, company=company)
    except Lead.DoesNotExist:
        return fail('Lead not found', status_code=404)

    lead.is_active = False
    lead.save(update_fields=['is_active'])
    return ok(_serialize_lead(lead))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def lead_convert_to_student(request, lead_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)

    from accounts.rbac import user_has_permission, PERM_STUDENTS_WRITE, PERM_LEADS_WRITE
    if not user_has_permission(request.user, PERM_LEADS_WRITE) or not user_has_permission(request.user, PERM_STUDENTS_WRITE):
        return fail('You do not have permission to perform this action.', status_code=403)

    with transaction.atomic():
        try:
            lead = Lead.objects.get(pk=lead_id, company=company)
        except Lead.DoesNotExist:
            return fail('Lead not found', status_code=404)

        if lead.stage == Lead.Stage.CONVERTED and lead.converted_students.exists():
            existing_student = lead.converted_students.first()
            return fail(f'Этот лид уже зачислен как студент ({existing_student.full_name}).', status_code=400)

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
        if len(phone) < 9:
            return fail('Phone must contain at least 9 digits')

        phone2_raw = str(request.data.get('phone2') if 'phone2' in request.data else (lead.phone2 or '')).strip()
        if phone2_raw:
            phone2 = normalize_phone(phone2_raw)
            if len(phone2) < 9:
                return fail('Secondary phone must contain at least 9 digits')
        else:
            phone2 = ''
        phone2_owner = str(request.data.get('phone2_owner') or lead.phone2_owner or '').strip()
        address = str(request.data.get('address') or lead.address or '').strip()
        comment = str(request.data.get('comment') or lead.comment or '').strip()

        group = None
        group_id = request.data.get('group_id')
        if group_id:
            try:
                group = Group.objects.select_related('branch', 'course').get(pk=int(group_id), company=company)
            except (Group.DoesNotExist, TypeError, ValueError):
                return fail('Invalid group')
            branch = group.branch
        else:
            branch_id = request.data.get('branch_id')
            if not branch_id:
                branch = lead.branch
                if not branch:
                    branch = Branch.objects.filter(company=company).order_by('id').first()
                if not branch:
                    return fail('No branch available in company')
            else:
                try:
                    branch = Branch.objects.get(pk=int(branch_id), company=company)
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
        trial_date = parse_date_safe(request.data.get('trial_date')) or lead.trial_date or timezone.localdate()

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
            ActivityLog.objects.create(
                company=company,
                action=f'Lead "{lead_name}" converted to student',
                actor_name=request.user.display_name(),
            )
        except Exception:
            pass

        student = Student.objects.select_related('group', 'branch').get(pk=student.pk)
        return ok({
            'student': _serialize_student(student, detailed=True),
            'lead_id': lead_id_val,
            'converted': True,
        }, status_code=201)


def _serialize_course(course: Course) -> dict:
    return {
        'id': course.id,
        'name': course.name,
        'code': course.code,
        'price': course.price,
        'lesson_duration': course.lesson_duration,
        'course_duration': course.course_duration,
        'description': course.description,
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
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
        price = safe_int(request.data.get('price'), default=0,
                        min_val=0, max_val=100_000_000)
        lesson_duration = safe_int(request.data.get('lesson_duration'), default=90,
                                  min_val=15, max_val=480)
        course_duration = safe_int(request.data.get('course_duration'), default=12,
                                  min_val=1, max_val=120)
        description = (request.data.get('description') or '').strip()

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

    data = [_serialize_course(course) for course in Course.objects.filter(company=company)]
    return ok(data)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def course_detail(request, course_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        course = Course.objects.get(pk=course_id, company=company)
    except Course.DoesNotExist:
        return fail('Course not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_course(course))

    if request.method == 'DELETE':
        Group.objects.filter(course=course).update(course=None)
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
        
        # ✅ Гибкая валидация
        is_valid, error_msg = validate_course_code(code)
        if not is_valid:
            return fail(error_msg)

        # Проверка на дубликат (исключая текущий)
        if Course.objects.filter(
            company=company, code=code
        ).exclude(pk=course.pk).exists():
            return fail(f'Course with code "{code}" already exists')

        course.code = code

    # ✅ Безопасные числа
    if 'price' in request.data:
        course.price = safe_int(request.data.get('price'), default=0,
                               min_val=0, max_val=100_000_000)

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

    course.save()
    return ok(_serialize_course(course))
