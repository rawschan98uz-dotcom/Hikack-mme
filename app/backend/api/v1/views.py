import re
from datetime import date, datetime, time, timedelta

from django.contrib.auth import authenticate
from django.db.models import Count, Q
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import TeacherBranch, User
from accounts.rbac import get_effective_role, get_role_label, get_user_permissions
from api.responses import fail, ok
from api.scope import filter_groups_queryset, filter_students_queryset, teacher_can_access_group, teacher_can_access_student
from crm.models import Course, Group, Lead, Student
from finance.models import Payment
from operations.models import Reminder, Tag
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
    return ''.join(ch for ch in phone if ch.isdigit())


def _serialize_lead(lead: Lead) -> dict:
    return {
        'id': lead.id,
        'full_name': lead.full_name,
        'phone': lead.phone,
        'is_active': lead.is_active,
        'stage': lead.stage,
        'stage_label': lead.get_stage_display(),
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


def _apply_group_tags(group: Group, company: Company, data: dict) -> str | None:
    if 'tag_ids' not in data:
        return None
    raw = data.get('tag_ids')
    if raw in (None, ''):
        group.tags.clear()
        return None
    ids = raw if isinstance(raw, list) else _parse_id_list(str(raw))
    tags = list(Tag.objects.filter(pk__in=ids, company=company))
    if len(tags) != len(set(ids)):
        return 'Invalid tag'
    group.tags.set(tags)
    return None


def _serialize_student(student: Student) -> dict:
    return {
        'id': student.id,
        'first_name': student.first_name,
        'last_name': student.last_name,
        'full_name': student.full_name,
        'phone': student.phone,
        'status': student.status,
        'status_label': student.get_status_display(),
        'balance': student.balance,
        'paid_this_month': student.paid_this_month,
        'branch_id': student.branch_id,
        'branch': student.branch.name if student.branch_id else '—',
        'group_id': student.group_id,
        'group': student.group.name if student.group_id else None,
        'created_at': student.created_at.isoformat(),
    }


def _apply_student_fields(student: Student, company: Company, data: dict) -> str | None:
    first_name = data.get('first_name')
    if first_name is not None:
        first_name = str(first_name).strip()
        if not first_name:
            return 'First name is required'
        student.first_name = first_name

    if 'last_name' in data:
        student.last_name = str(data.get('last_name') or '').strip()

    phone = data.get('phone')
    if phone is not None:
        phone = _normalize_phone(str(phone))
        if len(phone) < 9:
            return 'Valid phone is required'
        student.phone = phone

    status = data.get('status')
    if status is not None:
        try:
            status = int(status)
        except (TypeError, ValueError):
            return 'Invalid status'
        if status not in VALID_STUDENT_STATUSES:
            return 'Invalid status'
        student.status = status

    if 'balance' in data:
        try:
            student.balance = int(data.get('balance') or 0)
        except (TypeError, ValueError):
            return 'Invalid balance'

    if 'paid_this_month' in data:
        student.paid_this_month = bool(data.get('paid_this_month'))

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
                return fail('Valid phone is required')
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
    leads = Lead.objects.filter(company=company, is_active=True)

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

    return ok({
        'active_leads': leads.count(),
        'active_students': students.filter(status=Student.Status.ACTIVE).count(),
        'groups': groups.count(),
        'debtors': students.filter(status=Student.Status.DEBTOR).count(),
        'trial_students': students.filter(status=Student.Status.TRIAL).count(),
        'paid_during_month': students.filter(paid_this_month=True).count(),
        'left_active_group': students.filter(status=Student.Status.LEFT_ACTIVE).count(),
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

        days = request.data.get('days', Group.Days.ODD)
        try:
            days = int(days)
        except (TypeError, ValueError):
            return fail('Invalid schedule')
        if days not in VALID_GROUP_DAYS:
            return fail('Invalid schedule')

        group = Group(company=company, branch=branch, name=name, days=days)
        error = _apply_group_fields(group, company, request.data)
        if error:
            return fail(error)
        group.save()
        tag_error = _apply_group_tags(group, company, request.data)
        if tag_error:
            group.delete()
            return fail(tag_error)
        group = Group.objects.select_related('course', 'branch', 'teacher', 'room').prefetch_related(
            'tags',
        ).annotate(
            students_count=Count('students'),
        ).get(pk=group.pk)
        return ok(_serialize_group(group), status_code=201)

    branch_id = request.query_params.get('branch_id')
    teacher_id = request.query_params.get('teacher_id')
    teacher_ids = _parse_id_list(request.query_params.get('teacher_ids'))
    if teacher_id and not teacher_ids:
        teacher_ids = _parse_id_list(teacher_id)
    course_ids = _parse_id_list(request.query_params.get('course_ids'))
    day_ids = _parse_id_list(request.query_params.get('days'))
    tag_ids = _parse_id_list(request.query_params.get('tag_ids'))
    status = request.query_params.get('status')
    start_date = _parse_date_param(request.query_params.get('start_date'))
    end_date = _parse_date_param(request.query_params.get('end_date'))
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
        try:
            qs = qs.filter(status=int(status))
        except ValueError:
            pass
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

    return ok([_serialize_group(group) for group in qs[:200]])


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def group_detail(request, group_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        group = Group.objects.select_related('course', 'branch', 'teacher', 'room').prefetch_related(
            'tags',
        ).annotate(
            students_count=Count('students'),
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

    error = _apply_group_fields(group, company, request.data)
    if error:
        return fail(error)
    group.save()
    tag_error = _apply_group_tags(group, company, request.data)
    if tag_error:
        return fail(tag_error)
    group = Group.objects.select_related('course', 'branch', 'teacher', 'room').prefetch_related(
        'tags',
    ).annotate(
        students_count=Count('students'),
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

        phone = _normalize_phone(request.data.get('phone') or '')
        if len(phone) < 9:
            return fail('Valid phone is required')

        branch_id = request.data.get('branch_id')
        if not branch_id:
            return fail('Branch is required')
        try:
            branch = Branch.objects.get(pk=int(branch_id), company=company)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return fail('Invalid branch')

        status = request.data.get('status', Student.Status.TRIAL)
        try:
            status = int(status)
        except (TypeError, ValueError):
            return fail('Invalid status')
        if status not in VALID_STUDENT_STATUSES:
            return fail('Invalid status')

        student = Student(
            company=company,
            branch=branch,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            status=status,
        )
        error = _apply_student_fields(student, company, request.data)
        if error:
            return fail(error)
        student.save()
        student = Student.objects.select_related('group', 'branch').get(pk=student.pk)
        return ok(_serialize_student(student), status_code=201)

    qs = Student.objects.filter(company=company).select_related('group', 'branch').order_by(
        'first_name', 'last_name',
    )
    qs = filter_students_queryset(qs, request.user)

    statuses = request.query_params.get('statuses')
    if statuses:
        try:
            qs = qs.filter(status=int(statuses))
        except ValueError:
            pass

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
            | Q(phone__icontains=query),
        )

    return ok([_serialize_student(student) for student in qs[:200]])


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
        return ok(_serialize_student(student))

    if request.method == 'DELETE':
        student.delete()
        return ok({'deleted': True})

    error = _apply_student_fields(student, company, request.data)
    if error:
        return fail(error)
    student.save()
    student = Student.objects.select_related('group', 'branch').get(pk=student.pk)
    return ok(_serialize_student(student))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def lead_list(request):
    company = request.user.company
    if company is None:
        return ok([])

    if request.method == 'POST':
        full_name = (request.data.get('full_name') or '').strip()
        phone = _normalize_phone(request.data.get('phone') or '')
        stage = (request.data.get('stage') or Lead.Stage.INCOMING).strip().lower()

        if not full_name:
            return fail('Lead name is required')
        if len(phone) < 9:
            return fail('Valid phone is required')
        if stage not in VALID_LEAD_STAGES:
            return fail('Invalid lead stage')

        lead = Lead.objects.create(
            company=company,
            full_name=full_name,
            phone=phone,
            stage=stage,
            is_active=True,
        )
        return ok(_serialize_lead(lead), status_code=201)

    qs = Lead.objects.filter(company=company).order_by('-created_at', '-id')

    archived = request.query_params.get('archived', '0')
    if archived == '1':
        qs = qs.filter(is_active=False)
    elif archived != 'all':
        qs = qs.filter(is_active=True)

    stage = request.query_params.get('stage')
    if stage and stage in VALID_LEAD_STAGES:
        qs = qs.filter(stage=stage)

    query = (request.query_params.get('q') or '').strip()
    if query:
        qs = qs.filter(Q(full_name__icontains=query) | Q(phone__icontains=query))

    return ok([_serialize_lead(lead) for lead in qs[:200]])


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

    full_name = request.data.get('full_name')
    phone = request.data.get('phone')
    stage = request.data.get('stage')
    is_active = request.data.get('is_active')

    if full_name is not None:
        full_name = str(full_name).strip()
        if not full_name:
            return fail('Lead name is required')
        lead.full_name = full_name

    if phone is not None:
        phone = _normalize_phone(str(phone))
        if len(phone) < 9:
            return fail('Valid phone is required')
        lead.phone = phone

    if stage is not None:
        stage = str(stage).strip().lower()
        if stage not in VALID_LEAD_STAGES:
            return fail('Invalid lead stage')
        lead.stage = stage

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
        if not code:
            return fail('Course code is required')
        if not re.fullmatch(r'(a1|a2|b1|b2|c1|c2)', code):
            return fail('Course code must be a CEFR level: a1, a2, b1, b2, c1, c2')

        price = int(request.data.get('price') or 0)
        lesson_duration = int(request.data.get('lesson_duration') or 90)
        course_duration = int(request.data.get('course_duration') or 12)
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
        return ok({
            'id': course.id,
            'name': course.name,
            'code': course.code,
            'price': course.price,
            'lesson_duration': course.lesson_duration,
            'course_duration': course.course_duration,
            'description': course.description,
        }, status_code=201)

    data = [_serialize_course(course) for course in Course.objects.filter(company=company)]
    return ok(data)


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
        if not code:
            return fail('Course code is required')
        if not re.fullmatch(r'(a1|a2|b1|b2|c1|c2)', code):
            return fail('Course code must be a CEFR level: a1, a2, b1, b2, c1, c2')
        course.code = code

    if 'price' in request.data:
        course.price = int(request.data.get('price') or 0)

    if 'lesson_duration' in request.data:
        course.lesson_duration = int(request.data.get('lesson_duration') or 90)

    if 'course_duration' in request.data:
        course.course_duration = int(request.data.get('course_duration') or 12)

    if 'description' in request.data:
        course.description = str(request.data.get('description') or '').strip()

    course.save()
    return ok(_serialize_course(course))
