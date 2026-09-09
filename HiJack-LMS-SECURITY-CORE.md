# HiJack LMS — Ключевые компоненты безопасности и авторизации

В данном файле собраны 6 запрошенных модулей системы:

- **1. Настройки (SECRET_KEY, DEBUG, База данных)**: app/backend/config/settings.py
- **2. Аутентификация и бизнес-логика API**: app/backend/api/v1/views.py
- **3. Права доступа и роли (RBAC)**: app/backend/accounts/rbac.py
- **4. Уведомления (Telegram, SMS)**: app/backend/operations/notify.py
- **5. Хранилище авторизации и токены (Pinia)**: app/frontend/src/stores/auth.ts
- **6. Все эндпоинты API (Маршруты)**: app/backend/api/v1/urls.py

---

## 1. Настройки (SECRET_KEY, DEBUG, База данных)

**Файл:** app/backend/config/settings.py (155 строк)

`python
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_on_railway = bool(os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RAILWAY_PROJECT_ID'))

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-only-change-in-production-hijack-mme')
DEBUG = os.environ.get('DEBUG', 'true').lower() in ('1', 'true', 'yes')
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('ALLOWED_HOSTS', '*').split(',')
    if host.strip()
]

if _on_railway:
    for extra_host in (
        '.up.railway.app',
        '.railway.app',
        '.railway.internal',
        'localhost',
        '127.0.0.1',
    ):
        if extra_host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(extra_host)
    _railway_public = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '').strip()
    if _railway_public and _railway_public not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_railway_public)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'accounts',
    'org',
    'crm',
    'finance',
    'operations',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

database_url = os.environ.get('DATABASE_URL')
if database_url:
    import dj_database_url

    ssl_default = 'false' if _on_railway else 'true'
    DATABASES = {
        'default': dj_database_url.config(
            default=database_url,
            conn_max_age=600,
            ssl_require=os.environ.get('DATABASE_SSL', ssl_default).lower() in ('1', 'true', 'yes'),
        ),
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

FRONTEND_DIST = Path(os.environ.get('FRONTEND_DIST', BASE_DIR.parent / 'frontend' / 'dist'))
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.User'

CORS_ALLOW_ALL_ORIGINS = os.environ.get('CORS_ALLOW_ALL_ORIGINS', 'true').lower() in ('1', 'true', 'yes')

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
        'api.permissions.RbacPermission',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
}

csrf_origins = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in csrf_origins.split(',') if origin.strip()]

render_url = os.environ.get('RENDER_EXTERNAL_URL', '').rstrip('/')
if render_url and render_url not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(render_url)

railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '').strip()
if railway_domain:
    railway_origin = f'https://{railway_domain}'
    if railway_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(railway_origin)

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
`

---

## 2. Аутентификация и бизнес-логика API

**Файл:** app/backend/api/v1/views.py (1190 строк)

`python
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
from operations import notify as notifications
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


def _next_payment_date(student: Student):
    import calendar

    last = (
        Payment.objects.filter(company=student.company, student_name=student.full_name)
        .order_by('-created_at')
        .first()
    )
    if last is None:
        return None, None
    last_date = timezone.localtime(last.created_at).date()
    year, month = (last_date.year + 1, 1) if last_date.month == 12 else (last_date.year, last_date.month + 1)
    next_due = date(year, month, min(last_date.day, calendar.monthrange(year, month)[1]))
    return last_date, next_due


def _serialize_student(student: Student, *, detailed: bool = False) -> dict:
    payload = {
        'id': student.id,
        'first_name': student.first_name,
        'last_name': student.last_name,
        'full_name': student.full_name,
        'phone': student.phone,
        'photo': student.photo.url if student.photo else None,
        'school': student.school,
        'telegram': student.telegram,
        'parent_telegram': student.parent_telegram,
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
    if detailed:
        last_payment_date, next_payment_date = _next_payment_date(student)
        payload['last_payment_date'] = last_payment_date.isoformat() if last_payment_date else None
        payload['next_payment_date'] = next_payment_date.isoformat() if next_payment_date else None
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

    if 'school' in data:
        student.school = str(data.get('school') or '').strip()

    if 'telegram' in data:
        student.telegram = str(data.get('telegram') or '').strip()

    if 'parent_telegram' in data:
        student.parent_telegram = str(data.get('parent_telegram') or '').strip()

    phone = data.get('phone')
    if phone is not None:
        phone = _normalize_phone(str(phone))
        if len(phone) < 9:
            return 'Phone must contain at least 9 digits'
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
            return fail('Phone must contain at least 9 digits')

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
        return ok(_serialize_student(student, detailed=True))

    if request.method == 'DELETE':
        student.delete()
        return ok({'deleted': True})

    error = _apply_student_fields(student, company, request.data)
    if error:
        return fail(error)
    student.save()
    student = Student.objects.select_related('group', 'branch').get(pk=student.pk)
    return ok(_serialize_student(student))


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
        full_name = (request.data.get('full_name') or '').strip()
        phone = _normalize_phone(request.data.get('phone') or '')
        stage = (request.data.get('stage') or Lead.Stage.INCOMING).strip().lower()

        if not full_name:
            return fail('Lead name is required')
        if len(phone) < 9:
            return fail('Phone must contain at least 9 digits')
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
            return fail('Phone must contain at least 9 digits')
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
`

---

## 3. Права доступа и роли (RBAC)

**Файл:** app/backend/accounts/rbac.py (276 строк)

`python
"""Role-based access control — permission matrix."""

from __future__ import annotations

from accounts.models import User

# ---------------------------------------------------------------------------
# Permission codes (module.action or module.action.subaction)
# ---------------------------------------------------------------------------

PERM_DASHBOARD_VIEW = 'dashboard.view'

PERM_LEADS_VIEW = 'leads.view'
PERM_LEADS_WRITE = 'leads.write'

PERM_TEACHERS_VIEW = 'teachers.view'
PERM_TEACHERS_WRITE = 'teachers.write'

PERM_GROUPS_VIEW = 'groups.view'
PERM_GROUPS_WRITE = 'groups.write'
PERM_GROUPS_EXPORT = 'groups.export'

PERM_STUDENTS_VIEW = 'students.view'
PERM_STUDENTS_WRITE = 'students.write'

PERM_REMINDERS_VIEW = 'reminders.view'
PERM_REMINDERS_WRITE = 'reminders.write'

PERM_RATING_VIEW = 'rating.view'
PERM_RATING_WRITE = 'rating.write'

PERM_ATTENDANCE_VIEW = 'attendance.view'
PERM_ATTENDANCE_WRITE = 'attendance.write'

PERM_TEACHER_ATTENDANCE_VIEW = 'teacher_attendance.view'
PERM_TEACHER_ATTENDANCE_WRITE = 'teacher_attendance.write'

PERM_FINANCE_VIEW = 'finance.view'
PERM_FINANCE_WRITE = 'finance.write'

PERM_REPORTS_VIEW = 'reports.view'
PERM_REPORTS_WRITE = 'reports.write'

PERM_SETTINGS_COMPANY = 'settings.company'
PERM_SETTINGS_INTEGRATIONS = 'settings.integrations'
PERM_SETTINGS_GRADE = 'settings.grade'

PERM_STAFF_VIEW = 'staff.view'
PERM_STAFF_WRITE = 'staff.write'

PERM_COURSES_VIEW = 'courses.view'
PERM_COURSES_WRITE = 'courses.write'

PERM_ROOMS_VIEW = 'rooms.view'
PERM_ROOMS_WRITE = 'rooms.write'

PERM_HOLIDAYS_VIEW = 'holidays.view'
PERM_HOLIDAYS_WRITE = 'holidays.write'

PERM_ARCHIVE_VIEW = 'archive.view'
PERM_ARCHIVE_WRITE = 'archive.write'

PERM_TAGS_VIEW = 'tags.view'
PERM_TAGS_WRITE = 'tags.write'

PERM_FORMS_VIEW = 'forms.view'
PERM_FORMS_WRITE = 'forms.write'

PERM_LOGS_VIEW = 'logs.view'
PERM_BRANCH_VIEW = 'branch.view'
PERM_PROFILE_EDIT = 'profile.edit'
PERM_BILLING_VIEW = 'billing.view'

ALL_PERMISSIONS: frozenset[str] = frozenset(
    {
        PERM_DASHBOARD_VIEW,
        PERM_LEADS_VIEW,
        PERM_LEADS_WRITE,
        PERM_TEACHERS_VIEW,
        PERM_TEACHERS_WRITE,
        PERM_GROUPS_VIEW,
        PERM_GROUPS_WRITE,
        PERM_GROUPS_EXPORT,
        PERM_STUDENTS_VIEW,
        PERM_STUDENTS_WRITE,
        PERM_REMINDERS_VIEW,
        PERM_REMINDERS_WRITE,
        PERM_RATING_VIEW,
        PERM_RATING_WRITE,
        PERM_ATTENDANCE_VIEW,
        PERM_ATTENDANCE_WRITE,
        PERM_TEACHER_ATTENDANCE_VIEW,
        PERM_TEACHER_ATTENDANCE_WRITE,
        PERM_FINANCE_VIEW,
        PERM_FINANCE_WRITE,
        PERM_REPORTS_VIEW,
        PERM_REPORTS_WRITE,
        PERM_SETTINGS_COMPANY,
        PERM_SETTINGS_INTEGRATIONS,
        PERM_SETTINGS_GRADE,
        PERM_STAFF_VIEW,
        PERM_STAFF_WRITE,
        PERM_COURSES_VIEW,
        PERM_COURSES_WRITE,
        PERM_ROOMS_VIEW,
        PERM_ROOMS_WRITE,
        PERM_HOLIDAYS_VIEW,
        PERM_HOLIDAYS_WRITE,
        PERM_ARCHIVE_VIEW,
        PERM_ARCHIVE_WRITE,
        PERM_TAGS_VIEW,
        PERM_TAGS_WRITE,
        PERM_FORMS_VIEW,
        PERM_FORMS_WRITE,
        PERM_LOGS_VIEW,
        PERM_BRANCH_VIEW,
        PERM_PROFILE_EDIT,
        PERM_BILLING_VIEW,
    },
)

ROLE_CEO = 'ceo'
ROLE_ADMINISTRATOR = 'administrator'
ROLE_BRANCH_DIRECTOR = 'branch_director'
ROLE_LIMITED_ADMIN = 'limited_admin'
ROLE_MARKETER = 'marketer'
ROLE_CASHIER = 'cashier'
ROLE_TEACHER = 'teacher'

ROLE_LABELS: dict[str, str] = {
    ROLE_CEO: 'CEO',
    ROLE_ADMINISTRATOR: 'Administrator',
    ROLE_BRANCH_DIRECTOR: 'Branch director',
    ROLE_LIMITED_ADMIN: 'Limited admin',
    ROLE_MARKETER: 'Marketer',
    ROLE_CASHIER: 'Cashier',
    ROLE_TEACHER: 'Teacher',
}

_ADMIN_OFFICE: frozenset[str] = frozenset(
    {
        PERM_DASHBOARD_VIEW,
        PERM_LEADS_VIEW,
        PERM_LEADS_WRITE,
        PERM_TEACHERS_VIEW,
        PERM_TEACHERS_WRITE,
        PERM_GROUPS_VIEW,
        PERM_GROUPS_WRITE,
        PERM_GROUPS_EXPORT,
        PERM_STUDENTS_VIEW,
        PERM_STUDENTS_WRITE,
        PERM_REMINDERS_VIEW,
        PERM_REMINDERS_WRITE,
        PERM_RATING_VIEW,
        PERM_RATING_WRITE,
        PERM_ATTENDANCE_VIEW,
        PERM_ATTENDANCE_WRITE,
        PERM_TEACHER_ATTENDANCE_VIEW,
        PERM_TEACHER_ATTENDANCE_WRITE,
        PERM_REPORTS_VIEW,
        PERM_REPORTS_WRITE,
        PERM_COURSES_VIEW,
        PERM_COURSES_WRITE,
        PERM_ROOMS_VIEW,
        PERM_ROOMS_WRITE,
        PERM_HOLIDAYS_VIEW,
        PERM_HOLIDAYS_WRITE,
        PERM_ARCHIVE_VIEW,
        PERM_ARCHIVE_WRITE,
        PERM_TAGS_VIEW,
        PERM_TAGS_WRITE,
        PERM_FORMS_VIEW,
        PERM_FORMS_WRITE,
        PERM_LOGS_VIEW,
        PERM_BRANCH_VIEW,
        PERM_PROFILE_EDIT,
    },
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_CEO: ALL_PERMISSIONS,
    ROLE_ADMINISTRATOR: _ADMIN_OFFICE,
    ROLE_BRANCH_DIRECTOR: _ADMIN_OFFICE,
    ROLE_LIMITED_ADMIN: frozenset(
        {
            PERM_DASHBOARD_VIEW,
            PERM_GROUPS_VIEW,
            PERM_GROUPS_WRITE,
            PERM_GROUPS_EXPORT,
            PERM_COURSES_VIEW,
            PERM_COURSES_WRITE,
            PERM_TEACHERS_VIEW,
            PERM_TEACHERS_WRITE,
            PERM_STUDENTS_VIEW,
            PERM_STUDENTS_WRITE,
            PERM_BRANCH_VIEW,
            PERM_PROFILE_EDIT,
            PERM_RATING_VIEW,
            PERM_RATING_WRITE,
        },
    ),
    ROLE_MARKETER: frozenset(
        {
            PERM_DASHBOARD_VIEW,
            PERM_LEADS_VIEW,
            PERM_LEADS_WRITE,
            PERM_REPORTS_VIEW,
            PERM_PROFILE_EDIT,
        },
    ),
    ROLE_CASHIER: frozenset(
        {
            PERM_DASHBOARD_VIEW,
            PERM_STUDENTS_VIEW,
            PERM_STUDENTS_WRITE,
            PERM_FINANCE_VIEW,
            PERM_FINANCE_WRITE,
            PERM_REPORTS_VIEW,
            PERM_BRANCH_VIEW,
            PERM_PROFILE_EDIT,
        },
    ),
    ROLE_TEACHER: frozenset(
        {
            PERM_DASHBOARD_VIEW,
            PERM_GROUPS_VIEW,
            PERM_STUDENTS_VIEW,
            PERM_RATING_VIEW,
            PERM_RATING_WRITE,
            PERM_ATTENDANCE_VIEW,
            PERM_ATTENDANCE_WRITE,
            PERM_TEACHER_ATTENDANCE_VIEW,
            PERM_REMINDERS_VIEW,
            PERM_BRANCH_VIEW,
            PERM_PROFILE_EDIT,
        },
    ),
}


def get_effective_role(user: User) -> str:
    if user.is_superuser:
        return ROLE_CEO
    if user.user_type == User.UserType.TEACHER:
        return ROLE_TEACHER
    if user.staff_role:
        return user.staff_role
    if user.user_type == User.UserType.STAFF:
        return ROLE_ADMINISTRATOR
    return ROLE_ADMINISTRATOR


def get_role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role.replace('_', ' ').title())


def get_user_permissions(user: User) -> frozenset[str]:
    role = get_effective_role(user)
    perms = ROLE_PERMISSIONS.get(role, frozenset())
    if role == ROLE_CEO:
        return ALL_PERMISSIONS
    return perms


def user_has_permission(user: User, permission: str | None) -> bool:
    if permission is None:
        return True
    if not user or not user.is_authenticated:
        return False
    if get_effective_role(user) == ROLE_CEO:
        return True
    return permission in get_user_permissions(user)


def user_is_teacher(user: User) -> bool:
    return get_effective_role(user) == ROLE_TEACHER
`

---

## 4. Уведомления (Telegram, SMS)

**Файл:** app/backend/operations/notify.py (468 строк)

`python
# -*- coding: utf-8 -*-
"""Telegram notification engine for Hi Jack LMS.

Rules are configured in backend/notifications.json (not in the UI).
Each rule entry looks like:

    {
      "name": "absence",
      "type": "attendance_absent",
      "enabled": true,
      "message": "...",
      ...type-specific params...
    }

Supported rule types:
  attendance_absent  - parent gets a message when the student was marked absent
                       params: min_age_minutes (wait before sending, so the
                       teacher can fix mistakes)
  payment_due        - reminder that the next payment date is coming
                       params: days_before
  payment_overdue    - payment date has passed
                       params: days_after, every_days

The next payment date is calculated from the last payment: same day of
month, next month (Jan 31 -> Feb 28). Payments are matched to students
by the student name stored in finance.Payment.student_name.
"""
import calendar
import json
import os
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections
from django.db.models import Max
from django.utils import timezone

from crm.models import AttendanceRecord, Student
from finance.models import Payment
from operations.models import NotificationLog
from org.models import Company

DEFAULT_CONFIG = {
    'enabled': False,
    'bot_token': '',
    'poll_interval_minutes': 10,
    'quiet_hours': {'enabled': False, 'from': '21:00', 'to': '09:00'},
    'rules': [],
}


def _config_path() -> Path:
    return Path(getattr(settings, 'NOTIFICATIONS_CONFIG', None) or (Path(settings.BASE_DIR) / 'notifications.json'))


def load_config() -> dict:
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    path = _config_path()
    try:
        raw = path.read_text(encoding='utf-8-sig')
    except OSError:
        return config
    try:
        data = json.loads(raw)
    except ValueError as exc:
        print(f'[notifications] invalid JSON in {path}: {exc}', flush=True)
        return config
    if isinstance(data, dict):
        for key, value in data.items():
            if key != 'rules':
                config[key] = value
        rules = data.get('rules')
        config['rules'] = rules if isinstance(rules, list) else []
    return config


class _SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'


def _fmt(template: str, ctx: dict) -> str:
    try:
        return str(template).format_map(_SafeDict(**ctx))
    except Exception:
        return str(template)


def _fmt_date(value) -> str:
    return value.strftime('%d.%m.%Y') if value else '-'


def telegram_call(token: str, method: str, payload: dict):
    """Call the Telegram Bot API. Returns (ok, result_or_error_text)."""
    if not token:
        return False, 'bot_token is not set'
    url = f'https://api.telegram.org/bot{token}/{method}'
    body = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode('utf-8'))
        except Exception:
            return False, f'HTTP {exc.code}'
        return False, str(data.get('description') or f'HTTP {exc.code}')
    except Exception as exc:
        return False, str(exc)
    if data.get('ok'):
        return True, data.get('result')
    return False, str(data.get('description') or 'unknown error')


_bot_username_cache = {'token': None, 'username': None, 'expires': 0.0}


def get_bot_username(token: str, ttl_seconds: float = 300):
    import time as _time

    now = _time.monotonic()
    cached = _bot_username_cache
    if cached['username'] and cached['token'] == token and now < cached['expires']:
        return cached['username']
    ok, me = telegram_call(token, 'getMe', {})
    username = me.get('username') if ok and isinstance(me, dict) else None
    cached.update({'token': token, 'username': username, 'expires': now + ttl_seconds})
    return username


def _resolve_target(raw: str):
    target = (raw or '').strip()
    if not target:
        return None
    if target.lstrip('+').isdigit():
        return target.lstrip('+')
    if target.startswith('@'):
        return target
    return '@' + target.lstrip('@')


def _student_ctx(student, extra: dict | None = None) -> dict:
    ctx = {
        'student': student.full_name,
        'first_name': student.first_name,
        'group': student.group.name if student.group_id else '-',
        'branch': student.branch.name if student.branch_id else '-',
        'school': student.school or '-',
        'phone': student.phone,
    }
    if extra:
        ctx.update(extra)
    return ctx


def _send(config: dict, student, rule: dict, trigger_date: date, ctx: dict) -> bool:
    target = _resolve_target(student.parent_telegram)
    if target is None:
        return False  # parents' telegram is not filled in yet for this student
    already = NotificationLog.objects.filter(
        student=student,
        rule=rule.get('name', '?'),
        trigger_date=trigger_date,
        ok=True,
    ).exists()
    if already:
        return True
    message = _fmt(rule.get('message', ''), ctx)
    ok, result = telegram_call(config.get('bot_token', ''), 'sendMessage', {
        'chat_id': target,
        'text': message,
        'disable_web_page_preview': True,
    })
    NotificationLog.objects.create(
        company=student.company,
        student=student,
        rule=rule.get('name', '?'),
        trigger_date=trigger_date,
        target=target,
        message=message,
        ok=ok,
        error='' if ok else str(result),
    )
    if not ok:
        print(f'[notifications] {rule.get("name")} -> {target}: {result}', flush=True)
    return ok


def _add_month(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _last_payment_dates(company) -> dict:
    rows = (
        Payment.objects.filter(company=company)
        .values('student_name')
        .annotate(last=Max('created_at'))
    )
    return {row['student_name']: timezone.localtime(row['last']).date() for row in rows if row['last']}


def _student_due(student, payments: dict):
    last = payments.get(student.full_name)
    if last is None:
        return None
    return last, _add_month(last)


PAYING_STATUSES = None  # filled lazily to avoid import-time surprises


def _paying_students(company):
    return (
        Student.objects.filter(
            company=company,
            status__in=[Student.Status.ACTIVE, Student.Status.DEBTOR],
        )
        .select_related('group', 'branch')
        .order_by('first_name', 'last_name')
    )


def _rule_attendance_absent(config: dict, rule: dict) -> dict:
    today = timezone.localdate()
    min_age = int(rule.get('min_age_minutes', 0) or 0)
    threshold = timezone.now() - timedelta(minutes=min_age)
    sent = 0
    records = (
        AttendanceRecord.objects.filter(attend_date=today, status=AttendanceRecord.Status.ABSENT)
        .select_related('student', 'group', 'student__branch')
        .order_by('id')
    )
    for record in records:
        if record.created_at and record.created_at > threshold:
            continue  # just marked, give the teacher time to fix mistakes
        ctx = _student_ctx(
            record.student,
            {
                'date': _fmt_date(record.attend_date),
                'group': record.group.name if record.group_id else '-',
            },
        )
        if _send(config, record.student, rule, record.attend_date, ctx):
            sent += 1
    return {'sent': sent}


def _rule_payment_due(config: dict, rule: dict) -> dict:
    today = timezone.localdate()
    days_before = int(rule.get('days_before', 0) or 0)
    sent = 0
    for company in Company.objects.all():
        payments = _last_payment_dates(company)
        for student in _paying_students(company):
            due = _student_due(student, payments)
            if due is None:
                continue
            last_date, next_due = due
            if next_due < today or (next_due - today).days > days_before:
                continue
            ctx = _student_ctx(student, {
                'date': _fmt_date(today),
                'due_date': _fmt_date(next_due),
                'last_payment_date': _fmt_date(last_date),
            })
            if _send(config, student, rule, next_due, ctx):
                sent += 1
    return {'sent': sent}


def _rule_payment_overdue(config: dict, rule: dict) -> dict:
    today = timezone.localdate()
    days_after = int(rule.get('days_after', 1) or 0)
    every_days = max(int(rule.get('every_days', 1) or 1), 1)
    sent = 0
    for company in Company.objects.all():
        payments = _last_payment_dates(company)
        for student in _paying_students(company):
            due = _student_due(student, payments)
            if due is None:
                continue
            last_date, next_due = due
            days_over = (today - next_due).days
            if days_over < days_after or (days_over - days_after) % every_days != 0:
                continue
            ctx = _student_ctx(student, {
                'date': _fmt_date(today),
                'due_date': _fmt_date(next_due),
                'days': days_over,
                'last_payment_date': _fmt_date(last_date),
            })
            if _send(config, student, rule, today, ctx):
                sent += 1
    return {'sent': sent}


HANDLERS = {
    'attendance_absent': _rule_attendance_absent,
    'payment_due': _rule_payment_due,
    'payment_overdue': _rule_payment_overdue,
}


def _parse_hhmm(value) -> int:
    parts = str(value).strip().split(':')
    return int(parts[0]) * 60 + int(parts[1])


def _in_quiet_hours(config: dict) -> bool:
    qh = config.get('quiet_hours') or {}
    if not qh.get('enabled'):
        return False
    now = timezone.localtime()
    minutes = now.hour * 60 + now.minute
    try:
        start = _parse_hhmm(qh.get('from', '21:00'))
        end = _parse_hhmm(qh.get('to', '09:00'))
    except (ValueError, IndexError):
        return False
    if start <= end:
        return start <= minutes < end
    return minutes >= start or minutes < end


def run_once() -> dict:
    close_old_connections()
    config = load_config()
    if not config.get('enabled'):
        return {'enabled': False}
    if _in_quiet_hours(config):
        return {'quiet_hours': True}
    summary = {}
    for rule in config.get('rules', []):
        if not isinstance(rule, dict) or not rule.get('enabled', True):
            continue
        handler = HANDLERS.get(rule.get('type'))
        if handler is None:
            print(f'[notifications] unknown rule type: {rule.get("type")!r}', flush=True)
            continue
        try:
            summary[str(rule.get('name', rule.get('type')))] = handler(config, rule)
        except Exception:
            traceback.print_exc()
    close_old_connections()
    return summary


DEFAULT_HELP_REPLY = (
    'Здравствуйте! Это бот уведомлений учебного центра.\n'
    'Чтобы получать уведомления о вашем ребёнке, откройте персональную ссылку, '
    'которую выдал администратор, и нажмите Start.'
)
DEFAULT_SUBSCRIBED_REPLY = (
    'Готово! Теперь вам будут приходить уведомления об ученике {student} ({group}).'
)
DEFAULT_UNKNOWN_CODE_REPLY = (
    'Не нашёл ученика по этой ссылке. Проверьте ссылку или обратитесь к администратору.'
)

_update_offset = 0


def _handle_start_payload(config: dict, chat_id, payload: str) -> str:
    auto = config.get('auto_reply') or {}
    code = str(payload).strip().upper()
    student = (
        Student.objects.filter(telegram_code=code)
        .select_related('group', 'branch')
        .first()
    )
    if student is None:
        return str(auto.get('unknown_code_message') or DEFAULT_UNKNOWN_CODE_REPLY)
    student.parent_telegram = str(chat_id)
    student.save(update_fields=['parent_telegram'])
    group = student.group.name if student.group_id else '-'
    template = str(auto.get('subscribed_message') or DEFAULT_SUBSCRIBED_REPLY)
    return template.format(student=student.full_name, group=group)


def _poll_updates(config: dict) -> None:
    """Telegram-side self-service: parents open the personal link
    (t.me/<bot>?start=<code>) and press Start - the bot links their chat
    to the student and notifications start flowing automatically."""
    global _update_offset
    if not config.get('enabled'):
        return
    auto = config.get('auto_reply') or {}
    if not auto.get('enabled', True):
        return
    ok, result = telegram_call(config.get('bot_token', ''), 'getUpdates', {
        'offset': _update_offset,
        'timeout': 0,
    })
    if not ok or not isinstance(result, list):
        return
    help_reply = str(auto.get('message') or DEFAULT_HELP_REPLY)
    for update in result:
        try:
            _update_offset = max(_update_offset, int(update.get('update_id', 0)) + 1)
        except (TypeError, ValueError):
            continue
        message = update.get('message') or {}
        chat = message.get('chat') or {}
        if chat.get('type') != 'private' or chat.get('id') is None:
            continue
        text = str(message.get('text') or '').strip()
        payload = ''
        if text.lower().startswith('/start'):
            parts = text.split(maxsplit=1)
            payload = parts[1].strip() if len(parts) > 1 else ''
        if payload:
            reply = _handle_start_payload(config, chat['id'], payload)
        else:
            reply = help_reply
        telegram_call(config.get('bot_token', ''), 'sendMessage', {
            'chat_id': chat['id'],
            'text': reply,
        })


def _loop() -> None:
    ticks = 0
    while True:
        try:
            config = load_config()
            interval_minutes = max(int(config.get('poll_interval_minutes', 10) or 10), 1)
        except Exception:
            config = {}
            interval_minutes = 10
        try:
            _poll_updates(config)
        except Exception:
            traceback.print_exc()
        ticks += 1
        if ticks >= interval_minutes * 2:  # rules run every poll_interval_minutes
            ticks = 0
            try:
                summary = run_once()
                if any(isinstance(v, dict) and v.get('sent') for v in summary.values()):
                    print(f'[notifications] {summary}', flush=True)
            except Exception:
                traceback.print_exc()
        time.sleep(30)


_thread = None


def start_background_thread() -> None:
    global _thread
    if _thread is not None:
        return
    if 'runserver' not in sys.argv:
        return
    if os.environ.get('RUN_MAIN') != 'true' and '--noreload' not in sys.argv:
        return  # django reloader parent process - the child will run the loop
    _thread = threading.Thread(target=_loop, name='telegram-notifications', daemon=True)
    _thread.start()
    print('[notifications] background thread started', flush=True)
`

---

## 5. Хранилище авторизации и токены (Pinia)

**Файл:** app/frontend/src/stores/auth.ts (117 строк)

`typescript
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { hasPermission } from '../utils/rbac';

export interface Company {
  id: number;
  name: string;
  subdomain: string;
  balance_mode: number;
  payment_mode_label: string;
}

export interface BranchRef {
  id: number;
  name: string;
}

export interface AuthUser {
  id: number;
  name: string;
  first_name: string;
  last_name: string;
  phone: string;
  phone_formatted: string;
  user_type: string;
  staff_role: string | null;
  role: string;
  job_title: string;
  role_label: string;
  permissions: string[];
  branches: BranchRef[];
  company: Company | null;
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null);
  const token = ref<string | null>(localStorage.getItem('access_token'));
  const loading = ref(false);
  const error = ref('');

  const permissions = computed(() => user.value?.permissions ?? []);
  const role = computed(() => user.value?.role ?? '');
  const isCeo = computed(() => role.value === 'ceo');

  function can(permission: string): boolean {
    if (isCeo.value) return true;
    return hasPermission(permissions.value, permission);
  }

  async function login(phone: string, password: string) {
    loading.value = true;
    error.value = '';
    try {
      const { data } = await client.post<ApiEnvelope<{ access: string; user: AuthUser }>>(
        '/auth/login',
        { phone, password },
      );
      token.value = data.data.access;
      user.value = data.data.user;
      localStorage.setItem('access_token', data.data.access);
    } catch (e: unknown) {
      error.value = 'Invalid phone or password';
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function fetchMe() {
    if (!token.value) return;
    const { data } = await client.post<ApiEnvelope<AuthUser>>('/auth/me');
    user.value = data.data;
  }

  async function updateProfile(payload: {
    first_name?: string;
    last_name?: string;
    job_title?: string;
    phone?: string;
    password?: string;
  }) {
    const { data } = await client.patch<ApiEnvelope<AuthUser>>('/auth/me', payload);
    user.value = data.data;
    return data.data;
  }

  function logout() {
    user.value = null;
    token.value = null;
    localStorage.removeItem('access_token');
  }

  function syncTokenFromStorage() {
    token.value = localStorage.getItem('access_token');
    if (!token.value) {
      user.value = null;
    }
  }

  return {
    user,
    token,
    loading,
    error,
    permissions,
    role,
    isCeo,
    can,
    login,
    fetchMe,
    updateProfile,
    logout,
    syncTokenFromStorage,
  };
});
`

---

## 6. Все эндпоинты API (Маршруты)

**Файл:** app/backend/api/v1/urls.py (77 строк)

`python
from django.urls import path

from api.v1 import views, views_extended, views_import, views_misc

urlpatterns = [
    path('company/subdomain/<slug:subdomain>', views.company_by_subdomain),
    path('company/<int:company_id>', views.company_detail),
    path('company/settings', views_extended.company_settings),
    path('auth/login', views.auth_login),
    path('auth/me', views.auth_me),
    path('branch', views.branch_list),
    path('dashboard', views.dashboard),
    path('schedule', views.schedule_list),
    path('groups', views.group_list),
    path('groups/<int:group_id>', views.group_detail),
    path('students', views.student_list),
    path('students/import', views_import.student_import),
    path('students/<int:student_id>', views.student_detail),
    path('students/<int:student_id>/photo', views.student_photo),
    path('telegram/config', views.telegram_config),
    path('leads', views.lead_list),
    path('leads/<int:lead_id>', views.lead_detail),
    path('leads/<int:lead_id>/archive', views.lead_archive),
    path('courses', views.course_list),
    path('courses/<int:course_id>', views.course_detail),
    path('user', views_extended.user_list),
    path('user/staff', views_extended.staff_create_view),
    path('user/staff/import', views_import.staff_import),
    path('user/staff/<int:staff_id>', views_extended.staff_detail_view),
    path('user/teacher', views_extended.teacher_create_view),
    path('user/teacher/import', views_import.teacher_import),
    path('user/teacher/<int:teacher_id>', views_extended.teacher_detail_view),
    path('replenishments', views_extended.replenishments),
    path('replenishments/<int:payment_id>', views_extended.payment_detail),
    path('withdraws', views_extended.withdraws),
    path('withdraws/<int:withdrawal_id>', views_extended.withdrawal_detail),
    path('expense', views_extended.expense_list),
    path('expense/<int:expense_id>', views_extended.expense_detail),
    path('expense_types', views_extended.expense_types),
    path('salary-settings', views_extended.salary_settings),
    path('salary-settings/<int:setting_id>', views_extended.salary_setting_detail),
    path('reports/conversion', views_extended.report_conversion),
    path('reports/attendance', views_extended.report_attendance),
    path('reports/attendance/<int:record_id>', views_extended.attendance_detail),
    path('reports/teacher-attendance', views_extended.report_teacher_attendance),
    path('reports/teacher-attendance/<int:record_id>', views_extended.teacher_attendance_detail),
    path('reports/leads', views_extended.report_leads),
    path('reports/left-students', views_extended.report_left_students),
    path('reports/workly', views_extended.report_workly),
    path('reports/workly/<int:record_id>', views_extended.workly_detail),
    path('reminders', views_misc.reminder_index),
    path('reminders/<int:reminder_id>', views_misc.reminder_detail),
    path('reminders/<int:reminder_id>/complete', views_misc.reminder_complete),
    path('reminder/index', views_misc.reminder_index),
    path('scores/branch', views_misc.scores_branch),
    path('scores/<int:score_id>', views_misc.score_detail),
    path('room', views_misc.room_list),
    path('room/<int:room_id>', views_misc.room_detail),
    path('holidays', views_misc.holiday_list),
    path('holidays/<int:holiday_id>', views_misc.holiday_detail),
    path('holidayRecalculation', views_misc.holiday_list),
    path('holidayRecalculation/<int:holiday_id>', views_misc.holiday_detail),
    path('archive/list', views_misc.archive_list),
    path('archive/list/bulk', views_misc.archive_bulk),
    path('archive/list/<int:person_id>', views_misc.archive_detail),
    path('archive/list/<int:person_id>/restore', views_misc.archive_restore),
    path('archiveReasons', views_misc.archive_reasons),
    path('company/<int:company_id>/users/trashed', views_misc.archive_list),
    path('tags', views_misc.tags_list),
    path('tags/<int:tag_id>', views_misc.tag_detail),
    path('leadForm', views_misc.lead_form_list),
    path('leadForm/<int:form_id>', views_misc.lead_form_detail),
    path('sms/report', views_misc.sms_report),
    path('call/logs', views_misc.call_logs),
    path('history/logs', views_misc.activity_logs),
    path('company/<int:company_id>/payments', views_misc.company_platform_payments),
]
`

---

