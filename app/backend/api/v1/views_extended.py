from datetime import date as date_cls, datetime, time

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from accounts.models import TeacherBranch, User
from accounts.rbac import (
    ROLE_CEO,
    PERM_PAYMENTS_DELETE,
    PERM_PAYMENTS_VIEW,
    PERM_PAYMENTS_WRITE,
    PERM_SETTINGS_COMPANY,
    PERM_STAFF_WRITE,
    PERM_TEACHERS_WRITE,
    get_effective_role,
    get_role_label,
    user_has_permission,
    user_is_teacher,
)
from api.archive import archive_teacher
from finance.closing import closed_error
from finance.refunds import recalc_refunded_months
from finance.wallet import PRICE_PENDING, current_month_price, recalc_student_wallet
from finance.salary import find_overlapping_setting, overlap_error
from api.responses import fail, ok
from api.scope import (
    filter_attendance_queryset,
    filter_teacher_attendance_queryset,
    branch_allowed,
    branch_limit,
    branches_for,
    can_access_attendance,
    can_access_group,
    can_access_payment,
    can_access_student,
    scope_branch,
    scope_payments,
    scope_teachers,
)
from api.utils import name_taken, normalize_phone, paginate_queryset, safe_int, parse_date_safe
from crm.models import AttendanceRecord, Group, Lead, Student
from crm.debts import written_off_debts
from operations.models import TeacherAttendanceRecord, log_audit
from org.models import Branch
from finance.models import Expense, ExpenseCategory, Payment, PayrollPayment, SalarySetting, Withdrawal
from org.models import Company


def _company(request):
    return request.user.company


def _creator_name(user) -> str:
    if not user:
        return '—'
    return user.get_full_name() or user.phone


def _format_phone(phone: str) -> str:
    digits = ''.join(ch for ch in phone if ch.isdigit())
    if len(digits) == 9:
        return f'{digits[:2]} {digits[2:5]} {digits[5:7]} {digits[7:9]}'
    if len(digits) == 12 and digits.startswith('998'):
        local = digits[3:]
        return f'{local[:2]} {local[2:5]} {local[5:7]} {local[7:9]}'
    return phone


def _serialize_teacher(user: User, *, groups_count: int | None = None) -> dict:
    branches = [
        {'id': link.branch_id, 'name': link.branch.name}
        for link in user.teacher_branches.select_related('branch')
    ]
    if groups_count is None:
        groups_count = getattr(user, '_groups_count', None)
        if groups_count is None:
            groups_count = Group.objects.filter(teacher=user).count()
    return {
        'id': user.id,
        'name': user.display_name(),
        'first_name': user.first_name,
        'last_name': user.last_name,
        'honorific': user.honorific,
        'phone': user.phone,
        'phone_formatted': _format_phone(user.phone),
        'role': user.user_type,
        'job_title': user.job_title or '—',
        'groups_count': groups_count,
        'groups_label': f'{groups_count} group{"s" if groups_count != 1 else ""}',
        'branches': branches,
    }


@api_view(['POST'])
def teacher_create_view(request):
    company = _company(request)
    if company is None:
        return fail('Company not found', 404)
    return teacher_create(request, company)


def _teacher_groups(teacher: User) -> list[dict]:
    return [
        {
            'id': group.id,
            'name': group.name,
            'course': group.course.name if group.course else '—',
            'branch': group.branch.name,
            'days_label': group.get_days_display(),
        }
        for group in Group.objects.filter(teacher=teacher).select_related('course', 'branch').order_by('name')
    ]


def _get_teacher(company: Company, teacher_id: int) -> User:
    return User.objects.get(
        pk=teacher_id,
        company=company,
        user_type=User.UserType.TEACHER,
    )


@api_view(['GET', 'PATCH', 'DELETE'])
def teacher_detail_view(request, teacher_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', 404)

    try:
        teacher = _get_teacher(company, teacher_id)
    except User.DoesNotExist:
        return fail('Teacher not found', 404)
    limit = branch_limit(request.user)
    if limit is not None and not TeacherBranch.objects.filter(teacher=teacher, branch_id=limit).exists():
        return fail('Teacher not found', 404)

    if request.method == 'GET':
        payload = _serialize_teacher(teacher)
        payload['groups'] = _teacher_groups(teacher)
        return ok(payload)

    if request.method == 'DELETE':
        if not (get_effective_role(request.user) == ROLE_CEO or request.user.is_superuser):
            return fail('Only CEO/owner can delete users', status_code=403)
        if request.user.pk == teacher.pk:
            return fail('Cannot delete your own account', status_code=400)

        # Payments, salary rates, payouts or groups keep the teacher for payroll/history:
        # such a teacher is archived (deactivated), never deleted, so no money loses its teacher.
        has_history = (
            TeacherAttendanceRecord.objects.filter(teacher=teacher).exists()
            or AttendanceRecord.objects.filter(group__teacher=teacher).exists()
            or Group.objects.filter(teacher=teacher).exists()
            or Payment.objects.filter(teacher=teacher).exists()
            or SalarySetting.objects.filter(teacher=teacher).exists()
            or PayrollPayment.objects.filter(teacher=teacher).exists()
            or teacher.payroll_snapshots.exists()
            or teacher.payroll_adjustments.exists()
        )
        if has_history:
            archive_teacher(company, teacher, reason='Deleted with history')
            return ok({'deleted': True, 'archived': True})

        teacher.delete()
        return ok({'deleted': True})

    is_ceo = (get_effective_role(request.user) == ROLE_CEO or request.user.is_superuser)

    first_name = request.data.get('first_name')
    last_name = request.data.get('last_name')
    phone = request.data.get('phone')
    password = request.data.get('password')
    honorific = request.data.get('honorific')
    job_title = request.data.get('job_title')
    branch_ids = request.data.get('branches')

    if first_name is not None:
        first_name = str(first_name).strip()
        if not first_name:
            return fail('First name is required')
        teacher.first_name = first_name

    if last_name is not None:
        teacher.last_name = str(last_name).strip()

    if phone is not None:
        phone = normalize_phone(str(phone))
        if not phone or len(phone) != 9:
            return fail('Valid 9-digit phone is required (e.g. 901234567)')
        if User.objects.filter(phone=phone).exclude(pk=teacher.pk).exists():
            return fail('Phone already exists')
        teacher.phone = phone

    if honorific is not None:
        teacher.honorific = str(honorific).strip() or 'Mr'

    if job_title is not None:
        teacher.job_title = str(job_title).strip()

    # Password changes restricted to CEO / superuser
    if password:
        if not is_ceo:
            return fail('Only CEO can change teacher passwords', status_code=403)
        teacher.set_password(str(password))

    # Deactivation support (used by archive flow)
    if 'is_active' in request.data:
        if not is_ceo:
            return fail('Only CEO can deactivate teachers', status_code=403)
        teacher.is_active = bool(request.data.get('is_active'))

    teacher.save()

    if branch_ids is not None:
        if not is_ceo:
            return fail('Only CEO can assign branches', status_code=403)
        valid_branch_ids = list(
            Branch.objects.filter(company=company, id__in=branch_ids).values_list('id', flat=True),
        )
        if not valid_branch_ids:
            return fail('Select at least one branch')
        busy = list(
            Group.objects.filter(teacher=teacher, status=Group.Status.ACTIVE)
            .exclude(branch_id__in=valid_branch_ids)
            .values_list('name', flat=True),
        )
        if busy:
            return fail(
                'Сначала передайте другому учителю группы в убираемом филиале: ' + ', '.join(busy),
            )
        TeacherBranch.objects.filter(teacher=teacher).delete()
        for branch_id in valid_branch_ids:
            TeacherBranch.objects.create(teacher=teacher, branch_id=branch_id)

    return ok(_serialize_teacher(teacher))


@api_view(['GET'])
def user_list(request):
    company = _company(request)
    if company is None:
        return ok([])

    user_type = request.query_params.get('user_type')
    qs = User.objects.filter(company=company)
    if user_type:
        qs = qs.filter(user_type=user_type)

    if user_type == 'teacher':
        limit = branch_limit(request.user)
        if limit is not None:
            qs = qs.filter(teacher_branches__branch_id=limit)
        teachers_qs = qs.filter(is_active=True).annotate(
            _groups_count=Count('teaching_groups')
        ).order_by('id')
        data = [_serialize_teacher(u) for u in teachers_qs]
        return ok(data)

    if user_type == 'staff':
        # Staff removed with salary history are archived (deactivated), not deleted: not listed any more
        return ok([_serialize_staff(u) for u in qs.filter(is_active=True).select_related('branch').order_by('id')])

    data = [
        {
            'id': u.id,
            'name': u.get_full_name() or u.phone,
            'phone': u.phone,
            'role': u.user_type,
            'job_title': u.job_title or '—',
        }
        for u in qs.order_by('id')
    ]
    return ok(data)


def _serialize_staff(user: User) -> dict:
    return {
        'id': user.id,
        'name': user.get_full_name() or user.phone,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'phone': user.phone,
        'role': user.user_type,
        'job_title': user.job_title or '—',
        'staff_role': user.staff_role or '',
        'staff_role_label': get_role_label(get_effective_role(user)),
        'branch_id': user.branch_id,
        'branch': user.branch.name if user.branch_id else '',
    }


ASSIGNABLE_STAFF_ROLES = {choice[0] for choice in User.StaffRole.choices if choice[0] != User.StaffRole.CEO}


def _apply_staff_role(staff: User, company: Company, data, actor: User, is_ceo: bool) -> tuple[str, int] | None:
    """E3: role and director branch of a staff member — CEO only. Returns (error, status) or None."""
    if 'staff_role' not in data and 'branch_id' not in data:
        return None
    if not is_ceo:
        return 'Only CEO can change roles and branches', 403

    role = staff.staff_role
    if 'staff_role' in data:
        role = str(data.get('staff_role') or '').strip().lower()
        if role not in ASSIGNABLE_STAFF_ROLES:
            return 'Invalid role', 400
        if staff.pk and staff.pk == actor.pk and role != staff.staff_role:
            return 'Нельзя менять свою собственную роль', 400

    branch = staff.branch
    if 'branch_id' in data:
        raw = data.get('branch_id')
        if raw in (None, ''):
            branch = None
        else:
            try:
                branch = Branch.objects.get(pk=int(raw), company=company)
            except (Branch.DoesNotExist, TypeError, ValueError):
                return 'Invalid branch', 400

    if role == User.StaffRole.BRANCH_DIRECTOR:
        if branch is None:
            return 'Выберите филиал для директора филиала', 400
    else:
        branch = None  # only a branch director is bound to one branch

    staff.staff_role = role
    staff.branch = branch
    return None


def _get_staff(company: Company, staff_id: int) -> User:
    return User.objects.get(
        pk=staff_id,
        company=company,
        user_type=User.UserType.STAFF,
    )


@api_view(['POST'])
def staff_create_view(request):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    is_ceo = (get_effective_role(request.user) == ROLE_CEO or request.user.is_superuser)
    if not is_ceo and not user_has_permission(request.user, PERM_STAFF_WRITE):
        return fail('Permission denied', status_code=403)

    first_name = (request.data.get('first_name') or request.data.get('name') or '').strip()
    if ' ' in first_name and not request.data.get('first_name'):
        parts = first_name.split(' ', 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ''
    else:
        last_name = (request.data.get('last_name') or '').strip()

    phone = normalize_phone(request.data.get('phone') or '')
    password = request.data.get('password')
    generated = False
    if not password:
        password = _generate_password()
        generated = True
    job_title = (request.data.get('job_title') or '').strip()

    if not first_name or not phone:
        return fail('First name and phone are required')

    if len(phone) != 9:
        return fail('Valid 9-digit phone is required (e.g. 901234567)')

    if User.objects.filter(phone=phone).exists():
        return fail('Phone already exists')

    user = User(company=company, user_type=User.UserType.STAFF)
    role_error = _apply_staff_role(user, company, request.data, request.user, is_ceo)
    if role_error:
        return fail(role_error[0], status_code=role_error[1])

    user = User.objects.create_user(
        phone=phone,
        password=password,
        first_name=first_name,
        last_name=last_name,
        company=company,
        user_type=User.UserType.STAFF,
        job_title=job_title,
        staff_role=user.staff_role,
        branch=user.branch,
    )
    payload = _serialize_staff(user)
    payload['generated_password'] = password if generated else None
    return ok(payload, status_code=201)


@api_view(['GET', 'PATCH', 'DELETE'])
def staff_detail_view(request, staff_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    is_ceo = (get_effective_role(request.user) == ROLE_CEO or request.user.is_superuser)
    if request.method in ('PATCH', 'DELETE'):
        if not is_ceo and not user_has_permission(request.user, PERM_STAFF_WRITE):
            return fail('Permission denied', status_code=403)

    try:
        staff = _get_staff(company, staff_id)
    except User.DoesNotExist:
        return fail('Staff not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_staff(staff))

    if request.method == 'DELETE':
        if not is_ceo:
            return fail('Only CEO/owner can delete users', status_code=403)
        if request.user.pk == staff.pk:
            return fail('Cannot delete your own account', status_code=400)

        # Salary history (rates, payouts, frozen salaries, corrections) keeps the person: archived, not deleted.
        # Deleting used to fail with a server error because that history is protected.
        from finance.models import PayrollAdjustment, PayrollSnapshot
        if (
            SalarySetting.objects.filter(teacher=staff).exists()
            or PayrollPayment.objects.filter(teacher=staff).exists()
            or PayrollSnapshot.objects.filter(person=staff).exists()
            or PayrollAdjustment.objects.filter(person=staff).exists()
        ):
            staff.is_active = False
            staff.save(update_fields=['is_active'])
            return ok({'deleted': True, 'archived': True})

        staff.delete()
        return ok({'deleted': True})

    first_name = request.data.get('first_name')
    if first_name is not None:
        first_name = str(first_name).strip()
        if not first_name:
            return fail('First name is required')
        staff.first_name = first_name

    if 'last_name' in request.data:
        staff.last_name = str(request.data.get('last_name') or '').strip()

    if 'job_title' in request.data:
        staff.job_title = str(request.data.get('job_title') or '').strip()

    phone = request.data.get('phone')
    if phone is not None:
        phone = normalize_phone(phone)
        if len(phone) != 9:
            return fail('Valid 9-digit phone is required (e.g. 901234567)')
        if User.objects.filter(phone=phone).exclude(pk=staff.pk).exists():
            return fail('Phone already exists')
        staff.phone = phone

    password = request.data.get('password')
    if password:
        if not is_ceo and request.user.pk != staff.pk:
            return fail('Only CEO can change passwords for other staff members', status_code=403)
        staff.set_password(str(password))

    role_error = _apply_staff_role(staff, company, request.data, request.user, is_ceo)
    if role_error:
        return fail(role_error[0], status_code=role_error[1])

    staff.save()
    return ok(_serialize_staff(staff))


def _generate_password(length: int = 8) -> str:
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def teacher_create(request, company: Company):
    first_name = (request.data.get('first_name') or '').strip()
    last_name = (request.data.get('last_name') or '').strip()
    phone = normalize_phone(request.data.get('phone') or '')
    password = request.data.get('password')
    honorific = (request.data.get('honorific') or 'Mr').strip()
    job_title = (request.data.get('job_title') or '').strip()
    branch_ids = request.data.get('branches') or []

    # Auto-generate password if not provided
    generated = False
    if not password:
        password = _generate_password()
        generated = True

    if not first_name or not phone:
        return fail('First name and phone are required')

    if len(phone) != 9:
        return fail('Valid 9-digit phone is required (e.g. 901234567)')

    if User.objects.filter(phone=phone).exists():
        return fail('Phone already exists')

    is_ceo = (get_effective_role(request.user) == ROLE_CEO or request.user.is_superuser)
    if not is_ceo and not user_has_permission(request.user, PERM_TEACHERS_WRITE):
        return fail('Permission denied', status_code=403)
    if not is_ceo and len(branch_ids) > 1:
        return fail('Only CEO can assign multiple branches to a teacher', status_code=403)

    valid_branch_ids = list(
        branches_for(request.user, company).filter(id__in=branch_ids).values_list('id', flat=True),
    )
    if not valid_branch_ids:
        default_branch = branches_for(request.user, company).order_by('id').first()
        if default_branch:
            valid_branch_ids = [default_branch.id]

    with transaction.atomic():
        user = User.objects.create_user(
            phone=phone,
            password=password,
            first_name=first_name,
            last_name=last_name,
            company=company,
            user_type=User.UserType.TEACHER,
            job_title=job_title,
            honorific=honorific,
        )
        for branch_id in valid_branch_ids:
            TeacherBranch.objects.create(teacher=user, branch_id=branch_id)

    payload = _serialize_teacher(user)
    payload['generated_password'] = password if generated else None
    return ok(payload, status_code=201)


def _expense_branch(company, raw):
    """(branch, error): owner (2026-09-28) — every expense belongs to a branch the CEO picks."""
    if raw in (None, ''):
        return None, 'Выберите филиал расхода.'
    try:
        return Branch.objects.get(pk=int(raw), company=company), None
    except (Branch.DoesNotExist, TypeError, ValueError):
        return None, 'Филиал не найден.'


def _money_day_filter(qs, params, field):
    """Filter by the day of the money record (a date field); broken dates in the filter are ignored."""
    date_from = parse_date_safe(params.get('date_from'))
    if date_from:
        qs = qs.filter(**{f'{field}__gte': date_from})
    date_to = parse_date_safe(params.get('date_to'))
    if date_to:
        qs = qs.filter(**{f'{field}__lte': date_to})
    return qs


# ---------------------------------------------------------------------------
# Money journal (owner, 2026-09-28): every edit / deletion of a payment, expense or withdrawal and every
# refund is written to the activity journal in plain words — who, when, what was and what became.
# ---------------------------------------------------------------------------

def _money_str(value) -> str:
    return f'{int(value or 0):,}'.replace(',', ' ')


def _day_str(value) -> str:
    return value.strftime('%d.%m.%Y') if value else '—'


PAYMENT_FIELD_LABELS = {
    'student': 'ученик',
    'amount': 'сумма',
    'discount': 'скидка',
    'months_covered': 'месяцев',
    'method': 'способ',
    'payment_date': 'дата',
    'teacher_name': 'учитель',
    'comment': 'комментарий',
}


def _payment_snapshot(payment: Payment) -> dict:
    return {
        'student': payment.student_name,
        'amount': _money_str(payment.amount),
        'discount': _money_str(payment.discount_amount),
        'months_covered': payment.months_covered,
        'method': payment.get_method_display(),
        'payment_date': _day_str(payment.payment_date),
        'teacher_name': payment.teacher_name,
        'comment': payment.comment,
    }


def _expense_snapshot(expense: Expense) -> dict:
    return {
        'amount': _money_str(expense.amount),
        'date': _day_str(expense.expense_date),
        'branch': expense.branch.name if expense.branch_id else '—',
        'category': expense.category.name if expense.category_id else '—',
        'payee': expense.payee,
        'method': expense.get_method_display(),
        'description': expense.description,
    }


EXPENSE_FIELD_LABELS = {
    'amount': 'сумма',
    'date': 'дата',
    'branch': 'филиал',
    'category': 'категория',
    'payee': 'получатель',
    'method': 'способ',
    'description': 'описание',
}


def _withdrawal_snapshot(withdrawal: Withdrawal) -> dict:
    return {
        'name': withdrawal.name,
        'amount': _money_str(withdrawal.amount),
        'date': _day_str(withdrawal.withdrawal_date),
        'comment': withdrawal.comment,
    }


WITHDRAWAL_FIELD_LABELS = {'name': 'кто', 'amount': 'сумма', 'date': 'дата', 'comment': 'комментарий'}


def _changes_text(old: dict, new: dict, labels: dict) -> str:
    parts = [
        f'{labels.get(key, key)}: {old.get(key) or "—"} → {new.get(key) or "—"}'
        for key in new
        if old.get(key) != new.get(key)
    ]
    return '; '.join(parts)


def _log_money_edit(company, actor, entity_type, entity_id, title, old, new, labels) -> None:
    changes = _changes_text(old, new, labels)
    if not changes:
        return
    log_audit(
        company=company, actor=actor, entity_type=entity_type, entity_id=entity_id, action='edit',
        old_values=old, new_values=new, reason=f'{title}: {changes}',
    )


def _log_money_delete(company, actor, entity_type, entity_id, text, old) -> None:
    log_audit(
        company=company, actor=actor, entity_type=entity_type, entity_id=entity_id, action='delete',
        old_values=old, reason=text,
    )


MONEY_MESSAGE = 'Сумма — целое положительное число.'


def _parse_money(raw, allow_zero: bool = False) -> int | None:
    """Whole sums only: 800000, "800 000", 800000.0 -> 800000; 800000.5 / "abc" / negative -> None."""
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, float):
        if not raw.is_integer():
            return None
        value = int(raw)
    else:
        text = str(raw).strip().replace(' ', '').replace('\u00a0', '')
        if not text.isdigit():
            return None
        value = int(text)
    if value < 0 or (value == 0 and not allow_zero):
        return None
    return value


def _parse_money_date(raw, label: str):
    """(date, error) of a payment / expense / withdrawal: nothing = today; not later than today."""
    today = timezone.localdate()
    if raw in (None, ''):
        return today, None
    day = parse_date_safe(raw)
    if day is None:
        return None, f'Неверная {label}.'
    if day > today:
        return None, f'{label[0].upper()}{label[1:]} не может быть позже сегодняшнего дня.'
    return day, None


def _discount_error(discount: int, month_price: int, months: int) -> str | None:
    """Owner (2026-09-28): a discount is a sum, given by hand, not more than the price of the months paid for."""
    if discount <= 0:
        return None
    if not month_price or month_price <= 0:
        return 'Скидку можно дать, только когда у ученика есть цена курса (группа с ценой).'
    limit = month_price * max(1, months)
    if discount > limit:
        return f'Скидка больше цены оплачиваемых месяцев ({_money_str(limit)} сум).'
    return None


def _payment_day(payment: Payment):
    return payment.payment_date or timezone.localtime(payment.created_at).date()


def _payment_money(payment: Payment) -> tuple:
    """What a closed month keeps unchanged in a payment (everything except the comment)."""
    return (
        payment.student_id, payment.amount, payment.discount_amount, payment.payment_date,
        payment.months_covered, payment.method, payment.teacher_name,
    )


def _serialize_payment(payment: Payment) -> dict:
    pay_date = payment.payment_date or timezone.localtime(payment.created_at).date()
    return {
        'id': payment.id,
        'date': pay_date.strftime('%Y-%m-%d'),
        'payment_date': pay_date.isoformat(),
        'student_id': payment.student_id,
        'group_id': payment.group_id,
        'course_id': payment.course_id,
        'teacher_id': payment.teacher_id,
        'name': payment.student_name,
        'student_name': payment.student_name,
        'sum': payment.amount,
        'amount': payment.amount,
        'discount_amount': getattr(payment, 'discount_amount', 0) or 0,
        'gross_amount': getattr(payment, 'gross_amount', None) or payment.amount,
        'net_amount': getattr(payment, 'net_amount', None) or payment.amount,
        'transaction_type': getattr(payment, 'transaction_type', 'payment') or 'payment',
        'reverses_payment_id': payment.reverses_payment_id,
        'months_covered': getattr(payment, 'months_covered', 1) if getattr(payment, 'months_covered', None) is not None else 1,
        'refunded_months': getattr(payment, 'refunded_months', 0) or 0,
        # Копилка payment (months counted from money) vs months entered by hand
        'month_price': getattr(payment, 'month_price', None),
        'months_auto': getattr(payment, 'month_price', None) is not None,
        'method': payment.method,
        'method_pay': payment.get_method_display(),
        'teacher': payment.teacher_name or '—',
        'teacher_name': payment.teacher_name,
        'comment': payment.comment,
        'creator': _creator_name(payment.created_by),
        'created_at': payment.created_at.isoformat(),
    }


@api_view(['GET', 'POST'])
def replenishments(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        # Owner (2026-09-28): a payment always belongs to a student chosen from the list —
        # no guessing by name (the money went to the wrong namesake or to nobody)
        student_id = request.data.get('student_id')
        if student_id in (None, '', 0):
            return fail('Выберите ученика из списка.')
        try:
            student = Student.objects.select_related('group__course', 'group__teacher').get(
                pk=int(student_id), company=company,
            )
        except (Student.DoesNotExist, TypeError, ValueError):
            return fail('Ученик не найден.')
        if not can_access_student(request.user, student):
            return fail('Ученик не найден.')

        amount = _parse_money(request.data.get('amount') if 'amount' in request.data else request.data.get('sum'))
        if amount is None:
            return fail(MONEY_MESSAGE)
        discount_amount = _parse_money(request.data.get('discount_amount') or 0, allow_zero=True)
        if discount_amount is None:
            return fail('Скидка — целое число (сумма), или оставьте поле пустым.')
        method = str(request.data.get('method') or Payment.Method.CASH).strip().lower()
        if method not in {choice[0] for choice in Payment.Method.choices}:
            return fail('Invalid payment method')
        payment_date, error = _parse_money_date(
            request.data.get('payment_date') or request.data.get('date'), 'дата оплаты',
        )
        if error:
            return fail(error)
        error = closed_error(company.id, payment_date)
        if error:
            return fail(error)

        # Копилка: the months are always counted from the money. Without a course price the money waits
        # in the копилка and is counted as soon as the student is in a group with a price.
        month_price = current_month_price(student)
        # How many months the cashier meant to pay for (the form fills the sum from it): limits the discount
        intended_months = safe_int(request.data.get('months_covered'), default=1) or 1
        error = _discount_error(discount_amount, month_price, intended_months)
        if error:
            return fail(error)

        group = student.group
        course = group.course if group else None
        teacher = group.teacher if group else None
        payment = Payment.objects.create(
            company=company,
            student=student,
            group=group,
            course=course,
            teacher=teacher,
            student_name=student.full_name,
            amount=amount,
            gross_amount=amount + discount_amount,
            net_amount=amount,
            discount_amount=discount_amount,
            transaction_type=Payment.TransactionType.PAYMENT,
            months_covered=0,  # filled in by the копилка
            payment_date=payment_date,
            method=method,
            teacher_name=teacher.display_name() if teacher else '',
            comment=str(request.data.get('comment') or '').strip(),
            created_by=request.user,
            month_price=month_price or PRICE_PENDING,
        )

        from api.v1.views_payments import _after_online_payment
        _after_online_payment(student, payment)  # копилка; no price -> reminder for the office
        payment.refresh_from_db()
        from crm.services import sync_student_paid_this_month
        sync_student_paid_this_month(student)

        # Send instant payment receipt to Telegram
        try:
            from operations.notify import send_payment_receipt_telegram
            send_payment_receipt_telegram(payment)
        except Exception:
            pass

        return ok(_serialize_payment(payment), status_code=201)

    # GET: return list of payments
    qs = Payment.objects.filter(company=company).select_related('created_by', 'student').order_by('-payment_date', '-created_at')
    qs = scope_payments(qs, request.user)
    date_from = request.query_params.get('date_from')
    if date_from:
        qs = qs.filter(Q(payment_date__gte=date_from) | Q(payment_date__isnull=True, created_at__date__gte=date_from))
    date_to = request.query_params.get('date_to')
    if date_to:
        qs = qs.filter(Q(payment_date__lte=date_to) | Q(payment_date__isnull=True, created_at__date__lte=date_to))
    method = request.query_params.get('method')
    if method:
        qs = qs.filter(method=method)
    student_id = request.query_params.get('student_id')
    if student_id:
        try:
            qs = qs.filter(student_id=int(student_id))
        except ValueError:
            pass
    query = (request.query_params.get('q') or '').strip()
    if query:
        qs = qs.filter(Q(student_name__icontains=query) | Q(comment__icontains=query))

    # "Show more": pages of 200 instead of silently cutting the list
    page = paginate_queryset(qs, request, default_limit=200)
    return ok({
        'count': page['count'],
        'has_more': page['has_more'],
        'next_offset': page['next_offset'],
        'results': [_serialize_payment(payment) for payment in page['results']],
    })


@api_view(['POST'])
def payment_refund(request, payment_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    with transaction.atomic():
        try:
            original = Payment.objects.select_for_update().get(pk=payment_id, company=company)
        except Payment.DoesNotExist:
            return fail('Payment not found', status_code=404)

        if not can_access_payment(request.user, original):
            return fail('Payment not found', status_code=404)
        if original.transaction_type == Payment.TransactionType.REFUND:
            return fail('Cannot refund a refund record', status_code=400)

        already_refunded = Payment.objects.filter(
            reverses_payment=original,
            transaction_type=Payment.TransactionType.REFUND,
        ).aggregate(total=Sum('amount'))['total'] or 0

        available_to_refund = original.amount - already_refunded
        if available_to_refund <= 0:
            return fail('Payment has already been fully refunded', status_code=400)

        raw_amount = request.data.get('amount')
        if raw_amount not in (None, ''):
            refund_amount = _parse_money(raw_amount)
            if refund_amount is None:
                return fail(MONEY_MESSAGE, status_code=400)
            if refund_amount > available_to_refund:
                return fail(
                    f'Возврат не может быть больше оплаты: можно вернуть не больше {_money_str(available_to_refund)} сум.',
                    status_code=400,
                )
        else:
            refund_amount = available_to_refund

        comment = str(request.data.get('comment') or f'Возврат по платежу #{original.id}').strip()

        refund = Payment.objects.create(
            company=company,
            student=original.student,
            group=original.group,
            course=original.course,
            teacher=original.teacher,
            student_name=original.student_name,
            amount=refund_amount,
            gross_amount=refund_amount,
            net_amount=refund_amount,
            discount_amount=0,
            transaction_type=Payment.TransactionType.REFUND,
            reverses_payment=original,
            months_covered=0,
            payment_date=timezone.localdate(),
            method=original.method,
            teacher_name=original.teacher_name,
            comment=comment,
            created_by=request.user,
        )
        # Owner's rule: whole months are taken back only when the refunded sum reaches the monthly price
        recalc_refunded_months(original)
        log_audit(
            company=company, actor=request.user, entity_type='payment', entity_id=refund.id, action='refund',
            new_values={'refund_of': original.id, 'amount': _money_str(refund_amount), 'comment': comment},
            reason=(
                f'Возврат #{refund.id} по оплате #{original.id} ({original.student_name}): '
                f'{_money_str(refund_amount)} сум из {_money_str(original.amount)} сум. {comment}'
            ),
        )

        if original.student:
            from crm.services import sync_student_paid_this_month
            sync_student_paid_this_month(original.student)

        return ok(_serialize_payment(refund), status_code=201)


@api_view(['GET', 'PATCH', 'DELETE'])
def payment_detail(request, payment_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    needed = {
        'GET': PERM_PAYMENTS_VIEW,
        'PATCH': PERM_PAYMENTS_WRITE,
        'DELETE': PERM_PAYMENTS_DELETE,  # only the CEO deletes a payment (owner, 2026-09-28)
    }[request.method]
    if not user_has_permission(request.user, needed):
        return fail('Permission denied', status_code=403)

    try:
        payment = Payment.objects.select_related('created_by', 'student').get(pk=payment_id, company=company)
    except Payment.DoesNotExist:
        return fail('Payment not found', status_code=404)
    if not can_access_payment(request.user, payment):
        return fail('Payment not found', status_code=404)

    if request.method == 'GET':
        data = _serialize_payment(payment)
        if payment.transaction_type == Payment.TransactionType.PAYMENT:
            refunded = payment.reversals.filter(transaction_type=Payment.TransactionType.REFUND).aggregate(
                total=Sum('amount'),
            )['total'] or 0
            # For the "Вернуть деньги" window: how much was given back and how much can still be
            data['refunded_total'] = refunded
            data['refundable'] = max(0, payment.amount - refunded)
        return ok(data)

    if request.method == 'DELETE':
        if payment.reversals.exists():
            return fail('Cannot delete a payment that has reversals or refunds', status_code=400)
        error = closed_error(company.id, _payment_day(payment))
        if error:
            return fail(error)
        with transaction.atomic():
            student = payment.student
            refunded_payment = payment.reverses_payment
            kind = 'возврат' if payment.transaction_type == Payment.TransactionType.REFUND else 'оплата'
            _log_money_delete(
                company, request.user, 'payment', payment.id,
                f'Удалена {kind} #{payment.id}: {payment.student_name}, {_money_str(payment.amount)} сум, '
                f'{payment.get_method_display().lower()}, дата {_day_str(payment.payment_date)}',
                _payment_snapshot(payment),
            )
            payment.delete()
            if refunded_payment is not None:
                # A refund record was removed -> its months come back to the original payment
                recalc_refunded_months(refunded_payment)
            elif student:
                recalc_student_wallet(student)  # money of a копилка payment leaves the копилка
            if student:
                from crm.services import sync_student_paid_this_month
                sync_student_paid_this_month(student)
        return ok({'deleted': True})

    old_student = payment.student
    old_snapshot = _payment_snapshot(payment)
    old_money, old_day = _payment_money(payment), _payment_day(payment)
    is_refund = payment.transaction_type == Payment.TransactionType.REFUND

    if 'student_id' in request.data and not is_refund:
        # Moving a payment to another student (it was put on the wrong one): only a real student
        sid = request.data.get('student_id')
        try:
            new_student = Student.objects.get(pk=int(sid), company=company)
        except (Student.DoesNotExist, TypeError, ValueError):
            return fail('Ученик не найден.')
        if not can_access_student(request.user, new_student):
            return fail('Ученик не найден.')
        payment.student = new_student
        payment.student_name = new_student.full_name

    if 'amount' in request.data or 'sum' in request.data:
        amt = _parse_money(request.data.get('amount') if 'amount' in request.data else request.data.get('sum'))
        if amt is None:
            return fail(MONEY_MESSAGE)
        if is_refund:
            # A refund can never give back more than is left of the payment
            original = payment.reverses_payment
            if original is not None:
                others = original.reversals.filter(transaction_type=Payment.TransactionType.REFUND).exclude(
                    pk=payment.pk,
                ).aggregate(total=Sum('amount'))['total'] or 0
                left = original.amount - others
                if amt > left:
                    return fail(f'Возврат не может быть больше оплаты: можно вернуть не больше {_money_str(left)} сум.')
        else:
            refunded = payment.reversals.filter(transaction_type=Payment.TransactionType.REFUND).aggregate(
                total=Sum('amount'),
            )['total'] or 0
            if amt < refunded:
                return fail(
                    f'Сумма оплаты не может быть меньше уже возвращённого ({_money_str(refunded)} сум).',
                )
        payment.amount = amt
        payment.net_amount = amt

    if ('payment_date' in request.data or 'date' in request.data):
        day, error = _parse_money_date(request.data.get('payment_date') or request.data.get('date'), 'дата оплаты')
        if error:
            return fail(error)
        payment.payment_date = day

    if 'discount_amount' in request.data and not is_refund:
        discount = _parse_money(request.data.get('discount_amount') or 0, allow_zero=True)
        if discount is None:
            return fail('Скидка — целое число (сумма), или оставьте поле пустым.')
        if discount != payment.discount_amount:
            error = _discount_error(discount, payment.month_price or 0, payment.months_covered or 1)
            if error:
                return fail(error)
            payment.discount_amount = discount

    if 'months_covered' in request.data and payment.month_price is None and not is_refund:
        # Копилка payments count their months from the money; only old hand-entered ones take a number
        try:
            payment.months_covered = max(1, int(request.data.get('months_covered') or 1))
        except (TypeError, ValueError):
            pass
    if 'method' in request.data:
        method = str(request.data.get('method')).strip().lower()
        if method not in {choice[0] for choice in Payment.Method.choices}:
            return fail('Invalid payment method')
        payment.method = method
    if 'teacher_name' in request.data or 'teacher' in request.data:
        payment.teacher_name = str(request.data.get('teacher_name') or request.data.get('teacher') or '').strip()
    if 'comment' in request.data:
        payment.comment = str(request.data.get('comment') or '').strip()
    payment.gross_amount = (payment.amount or 0) + (payment.discount_amount or 0)

    # Closed month: only the comment may still change (the sums already reported stay as they were)
    if _payment_money(payment) != old_money:
        error = closed_error(company.id, old_day, _payment_day(payment))
        if error:
            return fail(error)

    with transaction.atomic():
        payment.save()
        payment.refresh_from_db()
        kind = 'возврат' if payment.transaction_type == Payment.TransactionType.REFUND else 'оплата'
        _log_money_edit(
            company, request.user, 'payment', payment.id, f'Изменена {kind} #{payment.id} ({payment.student_name})',
            old_snapshot, _payment_snapshot(payment), PAYMENT_FIELD_LABELS,
        )
        # Amount / months changed -> the months taken back by refunds may change too
        recalc_refunded_months(payment.reverses_payment or payment)
        # Копилка: the money moved or changed -> recount both students
        if old_student and old_student != payment.student:
            recalc_student_wallet(old_student)
        if payment.student:
            recalc_student_wallet(payment.student)
        payment.refresh_from_db()

        from crm.services import sync_student_paid_this_month
        if old_student and old_student != payment.student:
            sync_student_paid_this_month(old_student)
        if payment.student:
            sync_student_paid_this_month(payment.student)

    return ok(_serialize_payment(payment))


@api_view(['GET'])
def student_payments(request, student_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)
    if user_is_teacher(request.user):
        return fail('Teachers cannot view student payments', status_code=403)

    try:
        student = Student.objects.get(pk=student_id, company=company)
    except Student.DoesNotExist:
        return fail('Student not found', status_code=404)
    if not can_access_student(request.user, student):
        return fail('Student not found', status_code=404)

    same_name_count = Student.objects.filter(
        company=company,
        first_name__iexact=student.first_name,
        last_name__iexact=student.last_name,
    ).count()
    if same_name_count == 1:
        payment_filter = Q(student=student) | Q(student__isnull=True, student_name=student.full_name)
    else:
        payment_filter = Q(student=student)

    qs = Payment.objects.filter(
        Q(company=company) & payment_filter
    ).select_related('created_by').order_by('-created_at')

    return ok([_serialize_payment(p) for p in qs[:100]])


def _withdrawal_day(withdrawal: Withdrawal):
    return withdrawal.withdrawal_date or timezone.localtime(withdrawal.created_at).date()


def _serialize_withdrawal(withdrawal: Withdrawal) -> dict:
    return {
        'id': withdrawal.id,
        # The day the money was taken (chosen in the form)
        'date': _withdrawal_day(withdrawal).isoformat(),
        'name': withdrawal.name,
        'sum': withdrawal.amount,
        'amount': withdrawal.amount,
        'comment': withdrawal.comment,
        'creator': _creator_name(withdrawal.created_by),
        'created_at': withdrawal.created_at.isoformat(),
    }


@api_view(['GET', 'POST'])
def withdraws(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        name = str(request.data.get('name') or '').strip()
        if not name:
            return fail('Name is required')
        amount = _parse_money(request.data.get('amount') if 'amount' in request.data else request.data.get('sum'))
        if amount is None:
            return fail(MONEY_MESSAGE)
        day, error = _parse_money_date(request.data.get('date') or request.data.get('withdrawal_date'), 'дата изъятия')
        if error:
            return fail(error)
        error = closed_error(company.id, day)
        if error:
            return fail(error)

        withdrawal = Withdrawal.objects.create(
            company=company,
            name=name,
            amount=amount,
            withdrawal_date=day,
            comment=str(request.data.get('comment') or '').strip(),
            created_by=request.user,
        )
        return ok(_serialize_withdrawal(withdrawal), status_code=201)

    qs = Withdrawal.objects.filter(company=company).select_related('created_by').order_by(
        '-withdrawal_date', '-created_at',
    )
    qs = _money_day_filter(qs, request.query_params, 'withdrawal_date')
    query = (request.query_params.get('q') or '').strip()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(comment__icontains=query))

    page = paginate_queryset(qs, request, default_limit=200)
    return ok({
        'count': page['count'],
        'has_more': page['has_more'],
        'next_offset': page['next_offset'],
        'results': [_serialize_withdrawal(w) for w in page['results']],
    })


@api_view(['GET', 'PATCH', 'DELETE'])
def withdrawal_detail(request, withdrawal_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        withdrawal = Withdrawal.objects.select_related('created_by').get(pk=withdrawal_id, company=company)
    except Withdrawal.DoesNotExist:
        return fail('Withdrawal not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_withdrawal(withdrawal))

    old_day = _withdrawal_day(withdrawal)
    if request.method == 'DELETE':
        error = closed_error(company.id, old_day)
        if error:
            return fail(error)
        _log_money_delete(
            company, request.user, 'withdrawal', withdrawal.id,
            f'Удалено изъятие #{withdrawal.id}: {withdrawal.name}, {_money_str(withdrawal.amount)} сум, '
            f'от {_day_str(_withdrawal_day(withdrawal))}',
            _withdrawal_snapshot(withdrawal),
        )
        withdrawal.delete()
        return ok({'deleted': True})

    old_snapshot = _withdrawal_snapshot(withdrawal)

    if 'name' in request.data:
        name = str(request.data.get('name') or '').strip()
        if not name:
            return fail('Name is required')
        withdrawal.name = name
    if 'amount' in request.data or 'sum' in request.data:
        amount = _parse_money(request.data.get('amount') if 'amount' in request.data else request.data.get('sum'))
        if amount is None:
            return fail(MONEY_MESSAGE)
        withdrawal.amount = amount
    if 'date' in request.data or 'withdrawal_date' in request.data:
        day, error = _parse_money_date(request.data.get('date') or request.data.get('withdrawal_date'), 'дата изъятия')
        if error:
            return fail(error)
        withdrawal.withdrawal_date = day
    if 'comment' in request.data:
        withdrawal.comment = str(request.data.get('comment') or '').strip()

    # Closed month: only the text may still change
    new_snapshot = _withdrawal_snapshot(withdrawal)
    if any(old_snapshot[k] != new_snapshot[k] for k in ('name', 'amount', 'date')):
        error = closed_error(company.id, old_day, _withdrawal_day(withdrawal))
        if error:
            return fail(error)

    withdrawal.save()
    withdrawal.refresh_from_db()
    _log_money_edit(
        company, request.user, 'withdrawal', withdrawal.id, f'Изменено изъятие #{withdrawal.id}',
        old_snapshot, _withdrawal_snapshot(withdrawal), WITHDRAWAL_FIELD_LABELS,
    )
    return ok(_serialize_withdrawal(withdrawal))


def _expense_day(expense: Expense):
    return expense.expense_date or timezone.localtime(expense.created_at).date()


def _serialize_expense(expense: Expense) -> dict:
    return {
        'id': expense.id,
        # The day of the expense (chosen in the form), and its branch
        'date': _expense_day(expense).isoformat(),
        'branch_id': expense.branch_id,
        'branch': expense.branch.name if expense.branch_id else '—',
        # A salary payout: read-only in "Расходы"
        'is_salary_payout': bool(expense.payroll_payment_id),
        'category_id': expense.category_id,
        'category': expense.category.name if expense.category else '—',
        'description': expense.description,
        'payee': expense.payee,
        'method': expense.method,
        'method_pay': expense.get_method_display(),
        'sum': expense.amount,
        'amount': expense.amount,
        'creator': _creator_name(expense.created_by),
        'created_at': expense.created_at.isoformat(),
    }


@api_view(['GET', 'POST'])
def expense_list(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        amount = _parse_money(request.data.get('amount') if 'amount' in request.data else request.data.get('sum'))
        if amount is None:
            return fail(MONEY_MESSAGE)
        method = str(request.data.get('method') or Expense.Method.CASH).strip().lower()
        if method not in {choice[0] for choice in Expense.Method.choices}:
            return fail('Invalid payment method')

        category = None
        category_id = request.data.get('category_id')
        if category_id not in (None, ''):
            try:
                category = ExpenseCategory.objects.get(pk=int(category_id), company=company)
            except (ExpenseCategory.DoesNotExist, TypeError, ValueError):
                return fail('Invalid category')
        branch, error = _expense_branch(company, request.data.get('branch_id'))
        if error:
            return fail(error)
        day, error = _parse_money_date(request.data.get('date') or request.data.get('expense_date'), 'дата расхода')
        if error:
            return fail(error)
        error = closed_error(company.id, day)
        if error:
            return fail(error)

        expense = Expense.objects.create(
            company=company,
            category=category,
            branch=branch,
            expense_date=day,
            description=str(request.data.get('description') or '').strip(),
            payee=str(request.data.get('payee') or '').strip(),
            method=method,
            amount=amount,
            created_by=request.user,
        )
        expense = Expense.objects.select_related('category', 'created_by', 'branch').get(pk=expense.pk)
        return ok(_serialize_expense(expense), status_code=201)

    qs = Expense.objects.filter(company=company).select_related('category', 'created_by', 'branch').order_by(
        '-expense_date', '-created_at',
    )
    qs = _money_day_filter(qs, request.query_params, 'expense_date')
    category_id = request.query_params.get('category_id')
    if category_id:
        qs = qs.filter(category_id=category_id)
    branch_id = request.query_params.get('branch_id')
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    query = (request.query_params.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(description__icontains=query) | Q(payee__icontains=query) | Q(category__name__icontains=query),
        )

    page = paginate_queryset(qs, request, default_limit=200)
    return ok({
        'count': page['count'],
        'has_more': page['has_more'],
        'next_offset': page['next_offset'],
        'results': [_serialize_expense(e) for e in page['results']],
    })


@api_view(['GET', 'PATCH', 'DELETE'])
def expense_detail(request, expense_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        expense = Expense.objects.select_related('category', 'created_by', 'branch').get(pk=expense_id, company=company)
    except Expense.DoesNotExist:
        return fail('Expense not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_expense(expense))

    if expense.payroll_payment_id or expense.payroll_payments.exists():
        # A salary payout: changed / cancelled only in "Зарплаты", otherwise the payroll and the P&L disagree
        return fail('Это выплата зарплаты. Изменить или отменить её можно только в разделе «Зарплаты».')

    old_day = _expense_day(expense)
    if request.method == 'DELETE':
        error = closed_error(company.id, old_day)
        if error:
            return fail(error)
        _log_money_delete(
            company, request.user, 'expense', expense.id,
            f'Удалён расход #{expense.id}: {_money_str(expense.amount)} сум, '
            f'{expense.category.name if expense.category_id else "без категории"}'
            f'{", " + expense.payee if expense.payee else ""}, от {_day_str(_expense_day(expense))}, '
            f'{expense.branch.name if expense.branch_id else "без филиала"}',
            _expense_snapshot(expense),
        )
        expense.delete()
        return ok({'deleted': True})

    old_snapshot = _expense_snapshot(expense)

    if 'amount' in request.data or 'sum' in request.data:
        amount = _parse_money(request.data.get('amount') if 'amount' in request.data else request.data.get('sum'))
        if amount is None:
            return fail(MONEY_MESSAGE)
        expense.amount = amount
    if 'branch_id' in request.data:
        branch, error = _expense_branch(company, request.data.get('branch_id'))
        if error:
            return fail(error)
        expense.branch = branch
    if 'date' in request.data or 'expense_date' in request.data:
        day, error = _parse_money_date(request.data.get('date') or request.data.get('expense_date'), 'дата расхода')
        if error:
            return fail(error)
        expense.expense_date = day
    if 'method' in request.data:
        method = str(request.data.get('method')).strip().lower()
        if method not in {choice[0] for choice in Expense.Method.choices}:
            return fail('Invalid payment method')
        expense.method = method
    if 'description' in request.data:
        expense.description = str(request.data.get('description') or '').strip()
    if 'payee' in request.data:
        expense.payee = str(request.data.get('payee') or '').strip()
    if 'category_id' in request.data:
        category_id = request.data.get('category_id')
        if category_id in (None, ''):
            expense.category = None
        else:
            try:
                expense.category = ExpenseCategory.objects.get(pk=int(category_id), company=company)
            except (ExpenseCategory.DoesNotExist, TypeError, ValueError):
                return fail('Invalid category')

    # Closed month: only the description and the payee may still change
    new_snapshot = _expense_snapshot(expense)
    if any(old_snapshot[k] != new_snapshot[k] for k in ('amount', 'date', 'branch', 'category', 'method')):
        error = closed_error(company.id, old_day, _expense_day(expense))
        if error:
            return fail(error)

    expense.save()
    expense = Expense.objects.select_related('category', 'created_by', 'branch').get(pk=expense.pk)
    _log_money_edit(
        company, request.user, 'expense', expense.id, f'Изменён расход #{expense.id}',
        old_snapshot, _expense_snapshot(expense), EXPENSE_FIELD_LABELS,
    )
    return ok(_serialize_expense(expense))


@api_view(['GET', 'POST'])
def expense_types(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        name = str(request.data.get('name') or '').strip()
        if not name:
            return fail('Category name is required')
        if name_taken(ExpenseCategory.objects.filter(company=company), name):
            return fail('Такая категория расходов уже есть')
        cat = ExpenseCategory.objects.create(company=company, name=name)
        return ok({'id': cat.id, 'name': cat.name}, status_code=201)

    data = [{'id': c.id, 'name': c.name} for c in ExpenseCategory.objects.filter(company=company).order_by('name')]
    return ok(data)


@api_view(['PATCH', 'DELETE'])
def expense_type_detail(request, category_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        cat = ExpenseCategory.objects.get(pk=category_id, company=company)
    except ExpenseCategory.DoesNotExist:
        return fail('Category not found', status_code=404)

    if request.method == 'DELETE':
        cat.delete()
        return ok({'deleted': True})

    name = str(request.data.get('name') or '').strip()
    if not name:
        return fail('Category name is required')
    if name_taken(ExpenseCategory.objects.filter(company=company), name, exclude_pk=cat.pk):
        return fail('Такая категория расходов уже есть')
    cat.name = name
    cat.save()
    return ok({'id': cat.id, 'name': cat.name})



def _serialize_salary(setting: SalarySetting) -> dict:
    teacher_name = setting.teacher.display_name() if setting.teacher else setting.teacher_name
    course_name = setting.course.name if setting.course else setting.course_name
    group_name = setting.group.name if setting.group else setting.group_name
    return {
        'id': setting.id,
        'person_kind': (
            'teacher' if setting.teacher and setting.teacher.user_type == User.UserType.TEACHER else 'staff'
        ),
        'calc_setting': 'Fixed',
        'salary_type': setting.salary_type,
        'salary_type_label': setting.get_salary_type_display(),
        'amount': setting.amount,
        'teacher_id': setting.teacher_id,
        'teacher_name': teacher_name,
        'teacher': teacher_name,
        'course_id': setting.course_id,
        'course_name': course_name,
        'course': course_name or '—',
        'group_id': setting.group_id,
        'group_name': group_name,
        'group': group_name or '—',
        'effective_from': setting.effective_from.isoformat() if setting.effective_from else None,
        'effective_to': setting.effective_to.isoformat() if setting.effective_to else None,
        'student': '—',
        'created_by': _creator_name(setting.created_by),
        'updated_by': _creator_name(setting.updated_by),
        'created_at': setting.created_at.isoformat(),
    }


def _salary_person(company, raw):
    """(person, error): a teacher (percent) or an office staff member (fixed monthly amount)."""
    if raw in (None, ''):
        return None, 'Выберите учителя или сотрудника.'
    try:
        return User.objects.get(
            pk=int(raw), company=company, user_type__in=(User.UserType.TEACHER, User.UserType.STAFF),
        ), None
    except (User.DoesNotExist, TypeError, ValueError):
        return None, 'Учитель или сотрудник не найден.'


def _salary_rule_error(setting: SalarySetting) -> str | None:
    """Owner (2026-09-28): a teacher — only a percent (0–100); office staff — only a fixed sum a month."""
    person = setting.teacher
    if person is None:
        return 'Выберите учителя или сотрудника.'
    if person.user_type == User.UserType.TEACHER:
        if setting.salary_type != SalarySetting.SalaryType.PERCENT:
            return 'У учителя только процент от учеников.'
        if not (0 <= setting.amount <= 100):
            return 'Процент — целое число от 0 до 100.'
    else:
        if setting.salary_type != SalarySetting.SalaryType.FIXED:
            return 'У сотрудника — фиксированная сумма в месяц.'
        if setting.amount < 0:
            return 'Сумма не может быть меньше 0.'
        if setting.group_id or setting.course_id:
            return 'Группа и курс указываются только для процента учителя.'
    return None


def _apply_salary_fields(setting: SalarySetting, company, data) -> str | None:
    if 'teacher_id' in data or 'person_id' in data:
        person, error = _salary_person(company, data.get('teacher_id') or data.get('person_id'))
        if error:
            return error
        setting.teacher = person
        setting.teacher_name = person.display_name()
        # The kind of salary follows the person unless it is given
        if 'salary_type' not in data:
            setting.salary_type = (
                SalarySetting.SalaryType.PERCENT if person.user_type == User.UserType.TEACHER
                else SalarySetting.SalaryType.FIXED
            )

    if 'salary_type' in data:
        salary_type = str(data.get('salary_type') or '').strip().lower()
        if salary_type not in {choice[0] for choice in SalarySetting.SalaryType.choices}:
            return 'Invalid salary type'
        setting.salary_type = salary_type

    if 'amount' in data:
        amount = _parse_money(data.get('amount'), allow_zero=True)
        if amount is None:
            return 'Сумма или процент — целое число, не меньше 0.'
        setting.amount = amount

    if 'effective_from' in data:
        setting.effective_from = parse_date_safe(data.get('effective_from'))
    if 'effective_to' in data:
        setting.effective_to = parse_date_safe(data.get('effective_to'))
    if setting.effective_from and setting.effective_to and setting.effective_from > setting.effective_to:
        return 'Effective from date cannot be later than effective to date'

    if 'course_id' in data:
        c_id = data.get('course_id')
        if c_id in ('', None):
            setting.course = None
            setting.course_name = ''
        else:
            try:
                setting.course = Course.objects.get(pk=int(c_id), company=company)
                setting.course_name = setting.course.name
            except (Course.DoesNotExist, TypeError, ValueError):
                return 'Invalid course'

    if 'group_id' in data:
        g_id = data.get('group_id')
        if g_id in ('', None):
            setting.group = None
            setting.group_name = ''
        else:
            try:
                setting.group = Group.objects.get(pk=int(g_id), company=company)
                setting.group_name = setting.group.name
            except (Group.DoesNotExist, TypeError, ValueError):
                return 'Invalid group'

    error = _salary_rule_error(setting)
    if error:
        return error
    overlapping = find_overlapping_setting(
        company, setting.teacher, setting.course_id, setting.group_id,
        setting.effective_from, setting.effective_to, exclude_pk=setting.pk,
    )
    if overlapping:
        return overlap_error(overlapping)
    return None


@api_view(['GET', 'POST'])
def salary_settings(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        setting = SalarySetting(company=company, amount=0, created_by=request.user, updated_by=request.user)
        data = request.data
        if 'teacher_id' not in data and 'person_id' not in data:
            return fail('Выберите учителя или сотрудника.')
        error = _apply_salary_fields(setting, company, data)
        if error:
            return fail(error)
        setting.save()
        setting = SalarySetting.objects.select_related('created_by', 'updated_by', 'teacher', 'course', 'group').get(pk=setting.pk)
        return ok(_serialize_salary(setting), status_code=201)

    qs = SalarySetting.objects.filter(company=company).select_related('created_by', 'updated_by', 'teacher', 'course', 'group')
    if branch_limit(request.user) is not None:
        qs = qs.filter(teacher__in=scope_teachers(User.objects.filter(company=company), request.user))
    query = (request.query_params.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(teacher_name__icontains=query)
            | Q(teacher__first_name__icontains=query)
            | Q(teacher__last_name__icontains=query)
            | Q(course_name__icontains=query)
            | Q(group_name__icontains=query),
        )

    return ok([_serialize_salary(s) for s in qs[:200]])


@api_view(['GET', 'PATCH', 'DELETE'])
def salary_setting_detail(request, setting_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        setting = SalarySetting.objects.select_related('created_by', 'updated_by', 'teacher', 'course', 'group').get(
            pk=setting_id,
            company=company,
        )
    except SalarySetting.DoesNotExist:
        return fail('Salary setting not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_salary(setting))

    if request.method == 'DELETE':
        setting.delete()
        return ok({'deleted': True})

    error = _apply_salary_fields(setting, company, request.data)
    if error:
        return fail(error)
    setting.updated_by = request.user
    setting.save()
    setting = SalarySetting.objects.select_related('created_by', 'updated_by', 'teacher', 'course', 'group').get(pk=setting.pk)
    return ok(_serialize_salary(setting))


@api_view(['GET'])
def report_conversion(request):
    """
    «Лиды и конверсия» — one report instead of two (reports audit, 2026-09-29).

    The funnel counts what happened to every lead, not only where it stands now.
    Example: 10 booked a trial; 4 never came and refused, 6 came — 3 refused after the lesson, 3 enrolled.
    Funnel: booked 10 (100%) → came 6 (60%) → enrolled 3 (30% of all, 50% of those who came);
    refused 7 = 4 before the lesson + 3 after it. (The old page showed «В урок: 100%».)
    """
    empty_funnel = {'booked': 0, 'came': 0, 'converted': 0, 'thinking': 0, 'waiting': 0,
                    'rejected': 0, 'rejected_before': 0, 'rejected_after': 0}
    company = _company(request)
    if company is None:
        return ok({'funnel': empty_funnel, 'pipeline': {}, 'by_source': [], 'sources': [], 'rows': [],
                   'total': 0, 'active': 0, 'page': 1, 'total_pages': 1})

    all_leads = scope_branch(Lead.objects.filter(company=company), request.user)
    leads = all_leads.select_related('course', 'branch').order_by('-created_at')
    params = request.query_params

    is_active_param = params.get('is_active')
    if is_active_param in ('true', '1'):
        leads = leads.filter(is_active=True)
    elif is_active_param in ('false', '0'):
        leads = leads.filter(is_active=False)

    date_from = parse_date_safe(params.get('date_from'))
    if date_from:
        leads = leads.filter(created_at__date__gte=date_from)

    date_to = parse_date_safe(params.get('date_to'))
    if date_to:
        leads = leads.filter(created_at__date__lte=date_to)

    source = (params.get('source') or '').strip()
    if source == '—':
        leads = leads.filter(source='')
    elif source:
        leads = leads.filter(source__iexact=source)

    for field in ('course_id', 'branch_id'):
        value = safe_int(params.get(field))
        if value:
            leads = leads.filter(**{field: value})

    query = (params.get('q') or '').strip()
    if query:
        leads = leads.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(source__icontains=query)
            | Q(school__icontains=query)
        )

    came_q = Q(attended_trial=True) | Q(stage__in=[Lead.Stage.ATTENDED, Lead.Stage.CONVERTED])
    # Funnel and sources ignore the stage filter: they describe the whole period
    funnel_qs = leads
    funnel = {
        'booked': funnel_qs.count(),
        'came': funnel_qs.filter(came_q).count(),
        'converted': funnel_qs.filter(stage=Lead.Stage.CONVERTED).count(),
        'thinking': funnel_qs.filter(stage=Lead.Stage.ATTENDED).count(),
        'waiting': funnel_qs.filter(stage=Lead.Stage.TRIAL_BOOKED).count(),
        'rejected': funnel_qs.filter(stage=Lead.Stage.REJECTED).count(),
        'rejected_before': funnel_qs.filter(stage=Lead.Stage.REJECTED, attended_trial=False).count(),
        'rejected_after': funnel_qs.filter(stage=Lead.Stage.REJECTED, attended_trial=True).count(),
    }

    # Which advertising works: leads → came → students per source
    by_source = []
    for row in (
        funnel_qs.values('source')
        .annotate(
            total=Count('id'),
            came=Count('id', filter=came_q),
            converted=Count('id', filter=Q(stage=Lead.Stage.CONVERTED)),
        )
        .order_by('-total', 'source')
    ):
        by_source.append({
            'source': row['source'] or '—',
            'total': row['total'],
            'came': row['came'],
            'converted': row['converted'],
            'rate': round(row['converted'] * 100 / row['total']) if row['total'] else 0,
        })

    stage = params.get('stage')
    if stage in Lead.Stage.values:
        leads = leads.filter(stage=stage)

    total = leads.count()
    active_count = leads.filter(is_active=True).count()
    # Every source ever typed, not only the 7 quick buttons («Facebook» typed by hand is filterable too)
    sources = sorted(
        {(src or '').strip() for src in all_leads.values_list('source', flat=True) if (src or '').strip()},
        key=str.lower,
    )

    def _serialize_conversion_lead(lead: Lead) -> dict:
        came = bool(lead.attended_trial or lead.stage in (Lead.Stage.ATTENDED, Lead.Stage.CONVERTED))
        return {
            'id': lead.id,
            'full_name': lead.full_name,
            'phone': lead.phone,
            'stage': lead.stage,
            'stage_label': lead.get_stage_display(),
            'source': lead.source,
            'school': lead.school,
            'course_id': lead.course_id,
            'course_name': lead.course.name if lead.course else None,
            'branch_id': lead.branch_id,
            'branch_name': lead.branch.name if lead.branch else None,
            # Tashkent date: a lead of 02:00 at night is «today», not «yesterday» (UTC)
            'created_at': timezone.localtime(lead.created_at).date().isoformat(),
            'attended': came,
            'converted': lead.stage == Lead.Stage.CONVERTED,
            'rejected': lead.stage == Lead.Stage.REJECTED,
            'is_active': lead.is_active,
        }

    payload = {
        'funnel': funnel,
        'pipeline': {value: funnel_qs.filter(stage=value).count() for value in Lead.Stage.values},
        'by_source': by_source,
        'sources': sources,
        'total': total,
        'active': active_count,
    }
    if params.get('export', '0') == '1':
        return ok({**payload, 'rows': [_serialize_conversion_lead(lead) for lead in leads]})

    try:
        page = max(1, int(params.get('page', 1)))
    except (ValueError, TypeError):
        page = 1

    page_size = 50
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    rows = [_serialize_conversion_lead(lead) for lead in leads[offset:offset + page_size]]
    return ok({**payload, 'rows': rows, 'page': page, 'total_pages': total_pages})

VALID_ATTENDANCE_STATUSES = {choice[0] for choice in AttendanceRecord.Status.choices}


def _lesson_day_error(group: Group, day) -> str | None:
    """
    Reports audit (2026-09-29): a mark (student or teacher) only on a lesson day of the group — its weekday
    schedule, inside its dates, not a holiday — and never in the future.
    Example: a Mon/Wed/Fri group marked on Sunday 27.09 gave the student an absence for a lesson that never was.
    """
    from finance.payroll import lesson_days
    if day > timezone.localdate():
        return 'Нельзя отмечать будущий день: урок ещё не прошёл.'
    if not lesson_days(group, day, day):
        return (
            f'{day:%d.%m.%Y} у группы «{group.name}» нет урока по расписанию '
            '(не её день недели, праздник или вне дат группы).'
        )
    return None


def _serialize_attendance(record: AttendanceRecord) -> dict:
    return {
        'id': record.id,
        'student_id': record.student_id,
        'student': record.student.full_name,
        'group_id': record.group_id,
        'group': record.group.name,
        'branch_id': record.group.branch_id,
        'branch': record.group.branch.name,
        'date': record.attend_date.isoformat(),
        'status': record.status,
        'status_label': record.get_status_display(),
        'note': record.note,
        'created_at': record.created_at.isoformat(),
    }


def _attendance_queryset(company, params, user=None):
    qs = AttendanceRecord.objects.filter(company=company).select_related(
        'student',
        'group',
        'group__branch',
    ).order_by('-attend_date', 'student__first_name')

    if user is not None:
        qs = filter_attendance_queryset(qs, user)

    group_id = params.get('group_id')
    if group_id:
        qs = qs.filter(group_id=group_id)

    branch_id = params.get('branch_id')
    if branch_id:
        qs = qs.filter(group__branch_id=branch_id)

    student_id = params.get('student_id')
    if student_id:
        qs = qs.filter(student_id=student_id)

    status = params.get('status')
    if status is not None and status != '':
        try:
            qs = qs.filter(status=int(status))
        except ValueError:
            pass

    date_from = params.get('date_from')
    if date_from:
        qs = qs.filter(attend_date__gte=date_from)

    date_to = params.get('date_to')
    if date_to:
        qs = qs.filter(attend_date__lte=date_to)

    query = (params.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(student__first_name__icontains=query) | Q(student__last_name__icontains=query),
        )

    return qs


def _attendance_summary(qs) -> dict:
    counts = qs.values('status').annotate(total=Count('id'))
    summary = {'present': 0, 'absent': 0, 'late': 0, 'total': 0}
    for row in counts:
        if row['status'] == AttendanceRecord.Status.PRESENT:
            summary['present'] = row['total']
        elif row['status'] == AttendanceRecord.Status.ABSENT:
            summary['absent'] = row['total']
        elif row['status'] == AttendanceRecord.Status.LATE:
            summary['late'] = row['total']
        summary['total'] += row['total']
    return summary


@api_view(['GET', 'POST'])
def report_attendance(request):
    company = _company(request)
    if company is None:
        return ok({'summary': {'present': 0, 'absent': 0, 'late': 0, 'total': 0}, 'rows': []})

    if request.method == 'POST':
        attend_date_raw = request.data.get('date') or request.data.get('attend_date')
        if not attend_date_raw:
            return fail('Date is required')
        try:
            attend_date = date_cls.fromisoformat(str(attend_date_raw)[:10])
        except ValueError:
            return fail('Invalid date')

        if attend_date > timezone.localdate():
            return fail('Attendance date cannot be in the future', 400)
        if user_is_teacher(request.user) and attend_date != timezone.localdate():
            return fail('Учитель отмечает посещаемость только за сегодня. За другие дни — администратор или CEO.', status_code=403)

        records_data = request.data.get('records')
        if isinstance(records_data, list):
            try:
                group_id = int(request.data.get('group_id'))
                group = Group.objects.select_related('branch').get(pk=group_id, company=company)
            except (TypeError, ValueError, Group.DoesNotExist):
                return fail('Valid group is required')

            if not can_access_group(request.user, group):
                return fail('Group not found', 404)
            error = _lesson_day_error(group, attend_date)
            if error:
                return fail(error)

            saved_count = 0
            # D5: the whole group's attendance is saved all-or-nothing
            with transaction.atomic():
                # only current members: former (left / graduated) students are not marked
                students_map = {
                    s.id: s for s in Student.objects.filter(
                        company=company, group=group, status__in=Student.CURRENT_STATUSES,
                    )
                }
                for item in records_data:
                    try:
                        s_id = int(item.get('student_id'))
                        st = int(item.get('status', AttendanceRecord.Status.PRESENT))
                    except (TypeError, ValueError):
                        continue
                    if st not in VALID_ATTENDANCE_STATUSES:
                        continue
                    note = str(item.get('note') or '').strip()
                    # D6: same checks as AttendanceRecord.clean() — student must be in this group
                    student = students_map.get(s_id)
                    if student is None:
                        continue

                    AttendanceRecord.objects.update_or_create(
                        company=company,
                        student=student,
                        group=group,
                        attend_date=attend_date,
                        defaults={'status': st, 'note': note},
                    )
                    saved_count += 1
            return ok({
                'saved': saved_count,
                'group_id': group.id,
                'date': attend_date.isoformat(),
            }, status_code=200)

        try:
            student_id = int(request.data.get('student_id'))
            group_id = int(request.data.get('group_id'))
            status = int(request.data.get('status', AttendanceRecord.Status.PRESENT))
        except (TypeError, ValueError):
            return fail('Student, group and status are required')

        if status not in VALID_ATTENDANCE_STATUSES:
            return fail('Invalid status')

        try:
            student = Student.objects.get(pk=student_id, company=company)
        except Student.DoesNotExist:
            return fail('Student not found')

        try:
            group = Group.objects.select_related('branch').get(pk=group_id, company=company)
        except Group.DoesNotExist:
            return fail('Group not found')

        if not can_access_group(request.user, group):
            return fail('Group not found', 404)

        if student.company_id != group.company_id:
            return fail('Student and group belong to different companies')
        if student.group_id != group.id or student.status not in Student.CURRENT_STATUSES:
            return fail('Student does not belong to this group')
        error = _lesson_day_error(group, attend_date)
        if error:
            return fail(error)

        note = str(request.data.get('note') or '').strip()

        record, _created = AttendanceRecord.objects.update_or_create(
            company=company,
            student=student,
            group=group,
            attend_date=attend_date,
            defaults={'status': status, 'note': note},
        )
        record = AttendanceRecord.objects.select_related(
            'student',
            'group',
            'group__branch',
        ).get(pk=record.pk)
        return ok(_serialize_attendance(record), status_code=201)

    qs = _attendance_queryset(company, request.query_params, user=request.user)
    summary = _attendance_summary(qs)

    export = request.query_params.get('export', '0') == '1'
    if export:
        rows = [_serialize_attendance(record) for record in qs]
        return ok({'summary': summary, 'rows': rows})

    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    
    page_size = 50
    total = qs.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    
    offset = (page - 1) * page_size
    rows = [_serialize_attendance(record) for record in qs[offset:offset + page_size]]

    return ok({
        'summary': summary,
        'rows': rows,
        'total': total,
        'page': page,
        'total_pages': total_pages
    })


@api_view(['GET', 'PATCH', 'DELETE'])
def attendance_detail(request, record_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        record = AttendanceRecord.objects.select_related(
            'student',
            'group',
            'group__branch',
        ).get(pk=record_id, company=company)
    except AttendanceRecord.DoesNotExist:
        return fail('Attendance record not found', status_code=404)

    if not can_access_attendance(request.user, record):
        return fail('Attendance record not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_attendance(record))

    # A teacher changes only today's marks and cannot move them to another day
    if user_is_teacher(request.user) and (
        record.attend_date != timezone.localdate()
        or ('date' in request.data and str(request.data.get('date'))[:10] != timezone.localdate().isoformat())
        or ('attend_date' in request.data and str(request.data.get('attend_date'))[:10] != timezone.localdate().isoformat())
    ):
        return fail('Учитель отмечает посещаемость только за сегодня. За другие дни — администратор или CEO.', status_code=403)

    if request.method == 'DELETE':
        old_val = {
            'student_id': record.student_id,
            'group_id': record.group_id,
            'attend_date': record.attend_date.isoformat(),
            'status': record.status,
            'note': record.note,
        }
        rec_id = record.pk
        record.delete()
        log_audit(
            company=company,
            actor=request.user,
            entity_type='attendance',
            entity_id=rec_id,
            action='delete',
            old_values=old_val,
        )
        return ok({'deleted': True})

    old_val = {
        'student_id': record.student_id,
        'group_id': record.group_id,
        'attend_date': record.attend_date.isoformat(),
        'status': record.status,
        'note': record.note,
    }

    status = request.data.get('status')
    if status is not None:
        try:
            status = int(status)
        except (TypeError, ValueError):
            return fail('Invalid status')
        if status not in VALID_ATTENDANCE_STATUSES:
            return fail('Invalid status')
        record.status = status

    attend_date_raw = request.data.get('date') or request.data.get('attend_date')
    if attend_date_raw is not None:
        try:
            new_date = date_cls.fromisoformat(str(attend_date_raw)[:10])
        except ValueError:
            return fail('Invalid date')
        if new_date > timezone.localdate():
            return fail('Attendance date cannot be in the future', 400)
        record.attend_date = new_date

    group_id = request.data.get('group_id')
    if group_id is not None:
        try:
            target_group = Group.objects.select_related('branch').get(
                pk=int(group_id),
                company=company,
            )
        except (Group.DoesNotExist, TypeError, ValueError):
            return fail('Group not found')
        if not can_access_group(request.user, target_group):
            return fail('Group not found', 404)
        record.group = target_group

    student_id = request.data.get('student_id')
    if student_id is not None:
        try:
            record.student = Student.objects.get(pk=int(student_id), company=company)
        except (Student.DoesNotExist, TypeError, ValueError):
            return fail('Student not found')

    if 'note' in request.data:
        record.note = str(request.data['note']).strip()

    # Core invariant checks
    if record.student.company_id != company.id or record.group.company_id != company.id:
        return fail('Student and group belong to different companies', 400)
    # D6: membership is checked only when the record is moved to another student/group,
    # so past attendance of a transferred student can still be corrected.
    moved = record.student_id != old_val['student_id'] or record.group_id != old_val['group_id']
    if moved and record.student.group_id != record.group_id:
        return fail('Student does not belong to this group', 400)
    if record.group_id != old_val['group_id'] or record.attend_date.isoformat() != old_val['attend_date']:
        error = _lesson_day_error(record.group, record.attend_date)
        if error:
            return fail(error)
    if not can_access_group(request.user, record.group):
        return fail('Group not found', 404)
    if AttendanceRecord.objects.filter(
        company=company, student_id=record.student_id, group_id=record.group_id, attend_date=record.attend_date,
    ).exclude(pk=record.pk).exists():
        return fail('На эту дату у студента уже есть отметка', 400)

    record.save()
    new_val = {
        'student_id': record.student_id,
        'group_id': record.group_id,
        'attend_date': record.attend_date.isoformat(),
        'status': record.status,
        'note': record.note,
    }
    log_audit(
        company=company,
        actor=request.user,
        entity_type='attendance',
        entity_id=record.pk,
        action='update',
        old_values=old_val,
        new_values=new_val,
    )

    record = AttendanceRecord.objects.select_related(
        'student',
        'group',
        'group__branch',
    ).get(pk=record.pk)
    return ok(_serialize_attendance(record))




def _visible_groups(company, user):
    """Groups the user may see in attendance reports: a teacher — own, a director — own branch."""
    qs = Group.objects.filter(company=company).select_related('branch', 'teacher', 'course')
    if user_is_teacher(user):
        return qs.filter(teacher=user)
    return scope_branch(qs, user)


def _group_lessons(group, start, end) -> list:
    """Lesson days of the group in [start, end]; a group archived without a date has none."""
    from finance.payroll import lesson_days
    if group.status != Group.Status.ACTIVE and not group.archived_at:
        return []
    return lesson_days(group, start, end)


@api_view(['GET'])
def attendance_day_status(request):
    """
    Reports audit (2026-09-29): for a date — which groups have a lesson and whether attendance is marked.
    Example: 20 groups, 3 teachers forgot to mark — the office sees «не отмечено» without opening every group.
    """
    company = _company(request)
    if company is None:
        return ok([])
    day = parse_date_safe(request.query_params.get('date')) or timezone.localdate()
    groups = list(_visible_groups(company, request.user))
    marked = dict(
        AttendanceRecord.objects.filter(company=company, attend_date=day, group__in=groups)
        .values('group_id').annotate(total=Count('id')).values_list('group_id', 'total')
    )
    members = dict(
        Student.objects.filter(company=company, group__in=groups, status__in=Student.CURRENT_STATUSES)
        .values('group_id').annotate(total=Count('id')).values_list('group_id', 'total')
    )
    return ok([
        {
            'group_id': g.id,
            'has_lesson': bool(_group_lessons(g, day, day)),
            'marked': marked.get(g.id, 0),
            'students': members.get(g.id, 0),
        }
        for g in groups
    ])


@api_view(['GET'])
def attendance_month(request):
    """
    Reports audit (2026-09-29): one group, one month — students × lesson days, absences and percent.
    Example: «сколько раз Азиз пропустил в сентябре?» — one row instead of opening 13 dates one by one.
    """
    from finance.payroll import parse_month

    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)
    parsed = parse_month(request.query_params.get('month') or timezone.localdate().strftime('%Y-%m'))
    if parsed is None:
        return fail('Неверный месяц (нужно ГГГГ-ММ).')
    month_key, start, end = parsed
    try:
        group = Group.objects.select_related('branch', 'teacher').get(
            pk=int(request.query_params.get('group_id')), company=company,
        )
    except (TypeError, ValueError, Group.DoesNotExist):
        return fail('Group not found', status_code=404)
    if not can_access_group(request.user, group):
        return fail('Group not found', status_code=404)

    records = list(AttendanceRecord.objects.filter(
        company=company, group=group, attend_date__gte=start, attend_date__lte=end,
    ).select_related('student'))
    # Old marks on a day without a lesson stay visible (nothing is hidden)
    days = sorted(set(_group_lessons(group, start, end)) | {r.attend_date for r in records})
    students = {s.id: s for s in Student.objects.filter(
        company=company, group=group, status__in=Student.CURRENT_STATUSES,
    )}
    for r in records:
        students.setdefault(r.student_id, r.student)
    marks: dict[int, dict] = {}
    for r in records:
        marks.setdefault(r.student_id, {})[r.attend_date.isoformat()] = r.status

    rows = []
    for st in sorted(students.values(), key=lambda s: s.full_name.lower()):
        own = marks.get(st.id, {})
        present = sum(1 for v in own.values() if v == AttendanceRecord.Status.PRESENT)
        late = sum(1 for v in own.values() if v == AttendanceRecord.Status.LATE)
        absent = sum(1 for v in own.values() if v == AttendanceRecord.Status.ABSENT)
        counted = present + late + absent
        rows.append({
            'student_id': st.id,
            'student': st.full_name,
            'status': st.status,
            'status_label': st.get_status_display(),
            'marks': own,
            'present': present,
            'late': late,
            'absent': absent,
            'percent': round((present + late) * 100 / counted) if counted else None,
        })
    today = timezone.localdate()
    return ok({
        'month': month_key,
        'group': {'id': group.id, 'name': group.name, 'branch': group.branch.name,
                  'teacher': group.teacher.display_name() if group.teacher_id else ''},
        'days': [{'date': d.isoformat(), 'future': d > today} for d in days],
        'rows': rows,
    })

VALID_TEACHER_ATTENDANCE_STATUSES = {choice[0] for choice in TeacherAttendanceRecord.Status.choices}



def _lesson_taken_error(group, day, teacher_id, status, exclude_pk=None) -> str | None:
    """
    One lesson is paid to one teacher (owner, 2026-09-29: the office may mark any teacher — a substitution).
    Example: Bob was ill on 22.09, Tom held the lesson in Bob's group. If Bob is already marked «Был» that day,
    marking Tom «Был» too would pay the same lesson twice — first set Bob to «Не был» or move the mark to Tom.
    """
    if status not in (TeacherAttendanceRecord.Status.PRESENT, TeacherAttendanceRecord.Status.LATE):
        return None
    other = (
        TeacherAttendanceRecord.objects.filter(
            group=group, attend_date=day,
            status__in=(TeacherAttendanceRecord.Status.PRESENT, TeacherAttendanceRecord.Status.LATE),
        )
        .exclude(teacher_id=teacher_id)
        .exclude(pk=exclude_pk)
        .select_related('teacher')
        .first()
    )
    if other is None:
        return None
    return (
        f'Урок группы «{group.name}» {day:%d.%m.%Y} уже отмечен за учителем {other.teacher.display_name()}. '
        'Один урок оплачивается одному учителю: сначала поставьте ему «Не был» '
        'или перенесите отметку на другого учителя.'
    )


def _serialize_teacher_attendance(record: TeacherAttendanceRecord) -> dict:
    return {
        'id': record.id,
        'teacher_id': record.teacher_id,
        'teacher': record.teacher.display_name(),
        'group_id': record.group_id,
        'group': record.group.name,
        'branch_id': record.group.branch_id,
        'branch': record.group.branch.name,
        'date': record.attend_date.isoformat(),
        'status': record.status,
        'status_label': record.get_status_display(),
        'note': record.note,
        'created_at': record.created_at.isoformat(),
    }


def _teacher_attendance_queryset(company, params, user=None):
    qs = TeacherAttendanceRecord.objects.filter(company=company).select_related(
        'teacher',
        'group',
        'group__branch',
    ).order_by('-attend_date', 'teacher__first_name')

    if user is not None:
        qs = filter_teacher_attendance_queryset(qs, user)

    group_id = params.get('group_id')
    if group_id:
        qs = qs.filter(group_id=group_id)

    branch_id = params.get('branch_id')
    if branch_id:
        qs = qs.filter(group__branch_id=branch_id)

    teacher_id = params.get('teacher_id')
    if teacher_id:
        qs = qs.filter(teacher_id=teacher_id)

    status = params.get('status')
    if status is not None and status != '':
        try:
            qs = qs.filter(status=int(status))
        except ValueError:
            pass

    date_from = params.get('date_from')
    if date_from:
        qs = qs.filter(attend_date__gte=date_from)

    date_to = params.get('date_to')
    if date_to:
        qs = qs.filter(attend_date__lte=date_to)

    query = (params.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(teacher__first_name__icontains=query) | Q(teacher__last_name__icontains=query),
        )

    return qs


def _teacher_attendance_summary(qs) -> dict:
    counts = qs.values('status').annotate(total=Count('id'))
    summary = {'present': 0, 'absent': 0, 'late': 0, 'total': 0}
    for row in counts:
        if row['status'] == TeacherAttendanceRecord.Status.PRESENT:
            summary['present'] = row['total']
        elif row['status'] == TeacherAttendanceRecord.Status.ABSENT:
            summary['absent'] = row['total']
        elif row['status'] == TeacherAttendanceRecord.Status.LATE:
            summary['late'] = row['total']
        summary['total'] += row['total']
    return summary


@api_view(['GET', 'POST'])
def report_teacher_attendance(request):
    company = _company(request)
    if company is None:
        return ok({'summary': {'present': 0, 'absent': 0, 'late': 0, 'total': 0}, 'rows': []})

    if request.method == 'POST':
        try:
            teacher_id = int(request.data.get('teacher_id'))
            group_id = int(request.data.get('group_id'))
            status = request.data.get('status')
            if status is not None:
                status = int(status)
        except (TypeError, ValueError):
            return fail('Teacher, group and status are required')

        attend_date_raw = request.data.get('date') or request.data.get('attend_date')
        if not attend_date_raw:
            return fail('Date is required')
        try:
            attend_date = date_cls.fromisoformat(str(attend_date_raw)[:10])
        except ValueError:
            return fail('Invalid date')

        try:
            teacher = User.objects.get(
                pk=teacher_id,
                company=company,
                user_type=User.UserType.TEACHER,
            )
        except User.DoesNotExist:
            return fail('Teacher not found')

        try:
            group = Group.objects.select_related('branch').get(pk=group_id, company=company)
        except Group.DoesNotExist:
            return fail('Group not found')

        if not can_access_group(request.user, group):
            return fail('Group not found')
        # Owner (2026-09-29): the office marks any teacher — a substitution, or the teacher who led the group
        # before it was given to another one. The teacher's own «Я пришёл» stays limited to own groups.

        if status is None:
            status = TeacherAttendanceRecord.Status.PRESENT

        if status not in VALID_TEACHER_ATTENDANCE_STATUSES:
            return fail('Invalid status')
        error = _lesson_taken_error(group, attend_date, teacher.id, status)
        if error:
            return fail(error)

        # A closed month keeps its lessons: the frozen salary was counted from them
        error = closed_error(company.id, attend_date)
        if error:
            return fail(error)
        # Reports audit: a lesson of tomorrow cannot be "held" today (the salary was accrued in advance)
        error = _lesson_day_error(group, attend_date)
        if error:
            return fail(error)

        note = str(request.data.get('note') or '').strip()
        old = TeacherAttendanceRecord.objects.filter(
            company=company, teacher=teacher, group=group, attend_date=attend_date,
        ).first()
        record, _created = TeacherAttendanceRecord.objects.update_or_create(
            company=company,
            teacher=teacher,
            group=group,
            attend_date=attend_date,
            defaults={'status': status, 'note': note},
        )
        # The office marked the lesson for the teacher: who and when goes to the journal
        log_audit(
            company=company,
            actor=request.user,
            entity_type='teacher_attendance',
            entity_id=record.pk,
            action='create' if _created else 'update',
            old_values={'status': old.status, 'note': old.note} if old else None,
            new_values={
                'teacher_id': teacher.id, 'group_id': group.id, 'attend_date': attend_date.isoformat(),
                'status': status, 'note': note,
            },
        )
        record = TeacherAttendanceRecord.objects.select_related(
            'teacher',
            'group',
            'group__branch',
        ).get(pk=record.pk)
        return ok(_serialize_teacher_attendance(record), status_code=201)

    qs = _teacher_attendance_queryset(company, request.query_params, user=request.user)
    summary = _teacher_attendance_summary(qs)

    export = request.query_params.get('export', '0') == '1'
    if export:
        rows = [_serialize_teacher_attendance(record) for record in qs]
        return ok({'summary': summary, 'rows': rows})

    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    
    page_size = 50
    total = qs.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    
    offset = (page - 1) * page_size
    rows = [_serialize_teacher_attendance(record) for record in qs[offset:offset + page_size]]

    return ok({
        'summary': summary,
        'rows': rows,
        'total': total,
        'page': page,
        'total_pages': total_pages
    })


@api_view(['GET', 'PATCH', 'DELETE'])
def teacher_attendance_detail(request, record_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        record = TeacherAttendanceRecord.objects.select_related(
            'teacher',
            'group',
            'group__branch',
        ).get(pk=record_id, company=company)
    except TeacherAttendanceRecord.DoesNotExist:
        return fail('Teacher attendance record not found', status_code=404)

    if user_is_teacher(request.user) and record.teacher_id != request.user.id:
        return fail('Teacher attendance record not found', status_code=404)
    if not branch_allowed(request.user, record.group.branch_id if record.group_id else None):
        return fail('Teacher attendance record not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_teacher_attendance(record))

    old_day = record.attend_date
    if request.method == 'DELETE':
        error = closed_error(company.id, old_day)
        if error:
            return fail(error)
        old_val = {
            'teacher_id': record.teacher_id,
            'group_id': record.group_id,
            'attend_date': record.attend_date.isoformat(),
            'status': record.status,
            'note': record.note,
        }
        rec_id = record.pk
        record.delete()
        log_audit(
            company=company,
            actor=request.user,
            entity_type='teacher_attendance',
            entity_id=rec_id,
            action='delete',
            old_values=old_val,
        )
        return ok({'deleted': True})

    old_val = {
        'teacher_id': record.teacher_id,
        'group_id': record.group_id,
        'attend_date': record.attend_date.isoformat(),
        'status': record.status,
        'note': record.note,
    }

    status = request.data.get('status')
    if status is not None:
        try:
            status = int(status)
        except (TypeError, ValueError):
            return fail('Invalid status')
        if status not in VALID_TEACHER_ATTENDANCE_STATUSES:
            return fail('Invalid status')
        record.status = status

    if 'note' in request.data:
        record.note = str(request.data.get('note') or '').strip()

    attend_date_raw = request.data.get('date') or request.data.get('attend_date')
    if attend_date_raw is not None:
        try:
            record.attend_date = date_cls.fromisoformat(str(attend_date_raw)[:10])
        except ValueError:
            return fail('Invalid date')

    group_id = request.data.get('group_id')
    if group_id is not None:
        try:
            record.group = Group.objects.select_related('branch').get(
                pk=int(group_id),
                company=company,
            )
        except (Group.DoesNotExist, TypeError, ValueError):
            return fail('Group not found')
        if not can_access_group(request.user, record.group):
            return fail('Group not found')

    teacher_id = request.data.get('teacher_id')
    if teacher_id is not None:
        try:
            record.teacher = User.objects.get(
                pk=int(teacher_id),
                company=company,
                user_type=User.UserType.TEACHER,
            )
        except (User.DoesNotExist, TypeError, ValueError):
            return fail('Teacher not found')

    if record.group.company_id != company.id or record.teacher.company_id != company.id:
        return fail('Group and teacher belong to different companies', 400)
    error = _lesson_taken_error(record.group, record.attend_date, record.teacher_id, record.status, exclude_pk=record.pk)
    if error:
        return fail(error)
    if record.teacher_id != old_val['teacher_id'] and TeacherAttendanceRecord.objects.filter(
        company=company, teacher_id=record.teacher_id, group_id=record.group_id, attend_date=record.attend_date,
    ).exclude(pk=record.pk).exists():
        return fail('У этого учителя уже есть отметка за этот урок.')
    if (record.attend_date, record.group_id) != (old_day, old_val['group_id']):
        error = _lesson_day_error(record.group, record.attend_date)
        if error:
            return fail(error)
    if (record.status, record.attend_date, record.group_id, record.teacher_id) != (
        old_val['status'], old_day, old_val['group_id'], old_val['teacher_id'],
    ):
        error = closed_error(company.id, old_day, record.attend_date)
        if error:
            return fail(error)

    record.save()
    new_val = {
        'teacher_id': record.teacher_id,
        'group_id': record.group_id,
        'attend_date': record.attend_date.isoformat(),
        'status': record.status,
        'note': record.note,
    }
    log_audit(
        company=company,
        actor=request.user,
        entity_type='teacher_attendance',
        entity_id=record.pk,
        action='update',
        old_values=old_val,
        new_values=new_val,
    )

    record = TeacherAttendanceRecord.objects.select_related(
        'teacher',
        'group',
        'group__branch',
    ).get(pk=record.pk)
    return ok(_serialize_teacher_attendance(record))




TEACHER_LESSON_STATUS_FILTER = {
    'present': TeacherAttendanceRecord.Status.PRESENT,
    'late': TeacherAttendanceRecord.Status.LATE,
    'absent': TeacherAttendanceRecord.Status.ABSENT,
}


@api_view(['GET'])
def teacher_lessons(request):
    """
    Reports audit (2026-09-29): every lesson of the schedule with the teacher's mark — the lessons nobody
    marked too. Example: Tom had 13 lessons and pressed «Я пришёл» 10 times — the report used to show a clean
    «Присутствовал 10, Отсутствовал 0»; now it shows 3 «не отметился», and the office can mark them.
    """
    from finance.closing import closed_keys, month_key

    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)
    params = request.query_params
    today = timezone.localdate()
    date_from = parse_date_safe(params.get('date_from')) or today.replace(day=1)
    date_to = min(parse_date_safe(params.get('date_to')) or today, today)
    empty = {'summary': {'lessons': 0, 'present': 0, 'late': 0, 'absent': 0, 'not_marked': 0}, 'rows': []}
    if date_from > date_to:
        return ok(empty)
    if (date_to - date_from).days > 92:
        return fail('Период — не больше 3 месяцев.')

    groups = _visible_groups(company, request.user)
    branch_id = safe_int(params.get('branch_id'))
    if branch_id:
        groups = groups.filter(branch_id=branch_id)
    group_id = safe_int(params.get('group_id'))
    if group_id:
        groups = groups.filter(id=group_id)
    groups = list(groups)

    records: dict[tuple, list] = {}
    rec_qs = TeacherAttendanceRecord.objects.filter(
        company=company, group__in=groups, attend_date__gte=date_from, attend_date__lte=date_to,
    ).select_related('teacher')
    if user_is_teacher(request.user):
        rec_qs = rec_qs.filter(teacher=request.user)
    for r in rec_qs:
        records.setdefault((r.group_id, r.attend_date), []).append(r)
    locked = closed_keys(company.id)

    rows = []
    for g in groups:
        days = set(_group_lessons(g, date_from, date_to)) | {d for (gid, d) in records if gid == g.id}
        for day in days:
            base = {
                'date': day.isoformat(),
                'group_id': g.id,
                'group': g.name,
                'branch': g.branch.name,
                'start_time': g.lesson_start_time.strftime('%H:%M') if g.lesson_start_time else '',
                'end_time': g.lesson_end_time.strftime('%H:%M') if g.lesson_end_time else '',
                'locked': month_key(day) in locked,
            }
            found = records.get((g.id, day))
            if found:
                for r in found:
                    rows.append({
                        **base,
                        'record_id': r.id,
                        'teacher_id': r.teacher_id,
                        'teacher': r.teacher.display_name(),
                        'status': r.status,
                        'status_label': r.get_status_display(),
                        'note': r.note,
                        'marked_at': timezone.localtime(r.created_at).strftime('%d.%m %H:%M'),
                    })
            else:
                rows.append({
                    **base,
                    'record_id': None,
                    'teacher_id': g.teacher_id,
                    'teacher': g.teacher.display_name() if g.teacher_id else '—',
                    'status': None,
                    'status_label': 'Не отметился',
                    'note': '',
                    'marked_at': '',
                })

    teacher_id = safe_int(params.get('teacher_id'))
    if teacher_id:
        rows = [r for r in rows if r['teacher_id'] == teacher_id]
    summary = {
        'lessons': len(rows),
        'present': sum(1 for r in rows if r['status'] == TeacherAttendanceRecord.Status.PRESENT),
        'late': sum(1 for r in rows if r['status'] == TeacherAttendanceRecord.Status.LATE),
        'absent': sum(1 for r in rows if r['status'] == TeacherAttendanceRecord.Status.ABSENT),
        'not_marked': sum(1 for r in rows if r['status'] is None),
    }
    status = params.get('status') or ''
    if status == 'not_marked':
        rows = [r for r in rows if r['status'] is None]
    elif status in TEACHER_LESSON_STATUS_FILTER:
        rows = [r for r in rows if r['status'] == TEACHER_LESSON_STATUS_FILTER[status]]
    rows.sort(key=lambda r: (r['date'], r['start_time'], r['group']), reverse=True)
    return ok({
        'summary': summary,
        'rows': rows,
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
    })

def _no_lesson_reason(group: Group, day) -> str | None:
    """Why the group has no lesson on `day` (None when it does): weekday schedule and the group's dates."""
    from crm.services import group_weekdays
    if group.status != Group.Status.ACTIVE:
        return 'Группа в архиве'
    if day.weekday() not in group_weekdays(group.days, group.weekdays):
        return 'Сегодня у этой группы нет урока по расписанию'
    if (group.group_start_date and day < group.group_start_date) or (
        group.group_end_date and day > group.group_end_date
    ):
        return 'Сегодня группа не занимается (вне дат начала и окончания группы)'
    return None


@api_view(['GET'])
def teacher_attendance_today(request):
    """The teacher's lessons today with the check-in state — for the "I came" block on the dashboard."""
    company = _company(request)
    if company is None or not user_is_teacher(request.user):
        return ok([])
    today = timezone.localdate()
    groups = Group.objects.filter(
        company=company, teacher=request.user, status=Group.Status.ACTIVE,
    ).select_related('branch', 'room').order_by('lesson_start_time', 'name')
    records = {
        r.group_id: r
        for r in TeacherAttendanceRecord.objects.filter(company=company, teacher=request.user, attend_date=today)
    }
    rows = []
    for group in groups:
        if _no_lesson_reason(group, today):
            continue
        record = records.get(group.id)
        rows.append({
            'group_id': group.id,
            'group': group.name,
            'branch': group.branch.name,
            'room': group.room.name if group.room_id else '',
            'start_time': group.lesson_start_time.strftime('%H:%M') if group.lesson_start_time else '',
            'end_time': group.lesson_end_time.strftime('%H:%M') if group.lesson_end_time else '',
            'checked_in': record is not None,
            'status': record.status if record else None,
            'status_label': record.get_status_display() if record else '',
            'checked_at': timezone.localtime(record.created_at).strftime('%H:%M') if record else '',
        })
    return ok(rows)


@api_view(['GET'])
def teacher_attendance_my(request):
    """All attendance marks of the logged-in teacher (for the "Моя посещаемость" calendar)."""
    company = _company(request)
    if company is None or not user_is_teacher(request.user):
        return ok({'start_date': None, 'today': timezone.localdate().isoformat(), 'records': []})
    records = TeacherAttendanceRecord.objects.filter(
        company=company, teacher=request.user,
    ).select_related('group').order_by('attend_date', 'id')
    first = records.first()
    joined = timezone.localtime(request.user.date_joined).date() if request.user.date_joined else None
    start = min(d for d in (joined, first.attend_date if first else None) if d) if (joined or first) else None
    return ok({
        'start_date': start.isoformat() if start else None,
        'today': timezone.localdate().isoformat(),
        'records': [
            {
                'date': r.attend_date.isoformat(),
                'group': r.group.name,
                'status': r.status,
                'status_label': r.get_status_display(),
                'time': timezone.localtime(r.created_at).strftime('%H:%M'),
            }
            for r in records
        ],
    })


@api_view(['POST'])
def teacher_attendance_self_checkin(request):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    if not user_is_teacher(request.user):
        return fail('Only teachers can perform self check-in', status_code=403)

    teacher = request.user
    group_id = request.data.get('group_id')
    if not group_id:
        return fail('Group is required')

    try:
        group = Group.objects.select_related('branch').get(
            pk=int(group_id),
            company=company,
        )
    except (Group.DoesNotExist, TypeError, ValueError):
        return fail('Group not found', status_code=404)

    if group.teacher_id != teacher.id:
        return fail('You are not assigned to this group', status_code=404)

    local_now = timezone.localtime(timezone.now())
    attend_date = local_now.date()

    # A teacher can mark "I came" only on a lesson day of this group's schedule
    no_lesson = _no_lesson_reason(group, attend_date)
    if no_lesson:
        return fail(no_lesson, status_code=400)

    if group.lesson_start_time:
        import datetime
        lesson_dt = timezone.make_aware(datetime.datetime.combine(attend_date, group.lesson_start_time))
        threshold_dt = lesson_dt + datetime.timedelta(minutes=5)
        if local_now > threshold_dt:
            status = TeacherAttendanceRecord.Status.LATE
        else:
            status = TeacherAttendanceRecord.Status.PRESENT
    else:
        status = TeacherAttendanceRecord.Status.PRESENT

    note = str(request.data.get('note') or '').strip()
    already = TeacherAttendanceRecord.objects.filter(
        company=company, teacher=teacher, group=group, attend_date=attend_date,
    ).exists()
    if not already:
        error = _lesson_taken_error(group, attend_date, teacher.id, status)
        if error:
            return fail(error)
    # A second press changes nothing: the first mark (or the admin's correction) stays as it is
    record, _created = TeacherAttendanceRecord.objects.get_or_create(
        company=company,
        teacher=teacher,
        group=group,
        attend_date=attend_date,
        defaults={'status': status, 'note': note},
    )
    record = TeacherAttendanceRecord.objects.select_related(
        'teacher',
        'group',
        'group__branch',
    ).get(pk=record.pk)
    return ok(_serialize_teacher_attendance(record), status_code=200 if not _created else 201)

LEFT_STUDENT_STATUSES = {Student.Status.LEFT_TRIAL, Student.Status.LEFT}


def _left_debt(student: Student) -> dict | None:
    # Unpaid months at the moment of leaving; "left after trial" never owes (the trial is free)
    if student.status != Student.Status.LEFT:
        return None
    from api.v1.views import student_debt_on
    return student_debt_on(student)


def _serialize_left_student(student: Student, written_off: dict | None = None) -> dict:
    left_dt = student.left_at or student.created_at
    debt = _left_debt(student)
    # The CEO wrote this debt off: it is not a debt any more, the report shows it as "written off"
    write_off_note = (written_off or {}).get(student.id) if debt else None
    return {
        'id': student.id,
        'full_name': student.full_name,
        'phone': student.phone,
        'status': student.status,
        'status_label': student.get_status_display(),
        'branch_id': student.branch_id,
        'branch': student.branch.name if student.branch_id else '—',
        'group_id': student.group_id,
        'group': student.group.name if student.group_id else '—',
        'comment': student.comment or '—',
        'left_at': timezone.localtime(left_dt).date().isoformat() if left_dt else '',
        'debt_months': debt['months'] if debt and write_off_note is None else 0,
        'debt_amount': debt['approx_amount'] if debt and write_off_note is None else 0,
        'debt_since': debt['unpaid_since'].isoformat() if debt and write_off_note is None else None,
        'written_off': write_off_note is not None,
        'written_off_months': debt['months'] if write_off_note is not None else 0,
        'written_off_amount': debt['approx_amount'] if write_off_note is not None else 0,
        'written_off_note': write_off_note or '',
    }


def _left_students_queryset(company, params):
    qs = Student.objects.filter(
        company=company,
        status__in=LEFT_STUDENT_STATUSES,
    ).select_related('branch', 'group').order_by(F('left_at').desc(nulls_last=True), '-created_at')

    status = params.get('status')
    if status:
        try:
            status_val = int(status)
            if status_val in LEFT_STUDENT_STATUSES:
                qs = qs.filter(status=status_val)
        except ValueError:
            if status == 'left_active_group':
                qs = qs.filter(status=Student.Status.LEFT)
            elif status == 'left_after_trial':
                qs = qs.filter(status=Student.Status.LEFT_TRIAL)

    branch_id = params.get('branch_id')
    if branch_id:
        qs = qs.filter(branch_id=branch_id)

    group_id = params.get('group_id')
    if group_id:
        qs = qs.filter(group_id=group_id)

    date_from = parse_date_safe(params.get('date_from'))
    if date_from:
        qs = qs.filter(
            Q(left_at__date__gte=date_from) | Q(left_at__isnull=True, created_at__date__gte=date_from)
        )

    date_to = parse_date_safe(params.get('date_to'))
    if date_to:
        qs = qs.filter(
            Q(left_at__date__lte=date_to) | Q(left_at__isnull=True, created_at__date__lte=date_to)
        )

    query = (params.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(comment__icontains=query),
        )

    return qs


def _left_students_summary(qs) -> dict:
    return {
        'left_active': qs.filter(status=Student.Status.LEFT).count(),
        'left_trial': qs.filter(status=Student.Status.LEFT_TRIAL).count(),
        'total': qs.count(),
    }


@api_view(['GET'])
def report_left_students(request):
    company = _company(request)
    if company is None:
        return ok({'summary': {'left_active': 0, 'left_trial': 0, 'total': 0}, 'rows': [], 'page': 1, 'total_pages': 1, 'total': 0})

    qs = scope_branch(_left_students_queryset(company, request.query_params), request.user)
    left_active = qs.filter(status=Student.Status.LEFT).select_related('group__course')
    written_off = written_off_debts(left_active.values_list('id', flat=True))
    with_debt_ids = [s.id for s in left_active if _left_debt(s)]
    # A written-off debt is not a debt any more
    debtor_ids = [sid for sid in with_debt_ids if sid not in written_off]
    written_off_ids = [sid for sid in with_debt_ids if sid in written_off]
    if request.query_params.get('with_debt') in ('1', 'true'):
        qs = qs.filter(id__in=debtor_ids)
    total = qs.count()
    summary = _left_students_summary(qs)
    summary['with_debt'] = len(debtor_ids)
    summary['written_off'] = len(written_off_ids)

    export = request.query_params.get('export', '0') == '1'
    if export:
        return ok({
            'summary': summary,
            'rows': [_serialize_left_student(student, written_off) for student in qs],
            'total': total,
        })

    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except (ValueError, TypeError):
        page = 1

    page_size = 50
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    return ok({
        'summary': summary,
        'rows': [_serialize_left_student(student, written_off) for student in qs[offset:offset + page_size]],
        'total': total,
        'page': page,
        'total_pages': total_pages,
    })


@api_view(['GET', 'POST'])
def company_settings(request):
    company = _company(request)
    if company is None:
        return fail('No company', 400)

    is_ceo = (get_effective_role(request.user) == ROLE_CEO or request.user.is_superuser)

    if request.method == 'POST':
        if not is_ceo and not user_has_permission(request.user, PERM_SETTINGS_COMPANY):
            return fail('Only administrators can update company settings', status_code=403)

        for field in ('name', 'phone', 'address', 'timezone', 'currency'):
            if field in request.data:
                setattr(company, field, request.data[field])
        if 'sms_enabled' in request.data:
            company.sms_enabled = bool(request.data['sms_enabled'])
        if 'sms_advance_text' in request.data:
            company.sms_advance_text = str(request.data['sms_advance_text'] or '').strip()
        if 'voip_enabled' in request.data:
            company.voip_enabled = bool(request.data['voip_enabled'])
        if 'voip_gateway' in request.data:
            company.voip_gateway = str(request.data['voip_gateway'] or '').strip()
        if 'voip_caller_id' in request.data:
            company.voip_caller_id = str(request.data['voip_caller_id'] or '').strip()
        # Whole numbers only; "abc" used to crash the server (500)
        for grade_field, minimum in (('grade_pass_score', 0), ('grade_scale_max', 1)):
            if grade_field in request.data:
                raw = str(request.data[grade_field]).strip()
                if not raw.isdigit():
                    return fail('Проходной балл и максимум — целые числа.')
                setattr(company, grade_field, max(minimum, int(raw)))
        if company.grade_pass_score > company.grade_scale_max:
            # e.g. pass 150 out of 100: nobody could ever pass
            return fail('Проходной балл не может быть больше максимума.')
        for gw_field in ('click_service_id', 'click_merchant_id', 'click_secret_key', 'payme_merchant_id', 'payme_secret_key', 'uzum_merchant_id'):
            if gw_field in request.data:
                if 'secret' in gw_field and not is_ceo:
                    continue
                val = str(request.data[gw_field] or '').strip()
                if val and val != '***':
                    setattr(company, gw_field, val)
        company.save()

    click_secret_key = company.click_secret_key if is_ceo else ('***' if company.click_secret_key else '')
    payme_secret_key = company.payme_secret_key if is_ceo else ('***' if company.payme_secret_key else '')

    return ok({
        'id': company.id,
        'name': company.name,
        'subdomain': company.subdomain,
        'phone': company.phone,
        'address': company.address,
        'work_start_time': str(company.work_start_time) if company.work_start_time else None,
        'work_end_time': str(company.work_end_time) if company.work_end_time else None,
        'timezone': company.timezone,
        'currency': company.currency,
        'balance_mode': 1,
        'sms_enabled': company.sms_enabled,
        'sms_advance_text': company.sms_advance_text,
        'voip_enabled': company.voip_enabled,
        'voip_gateway': company.voip_gateway,
        'voip_caller_id': company.voip_caller_id,
        'grade_pass_score': company.grade_pass_score,
        'grade_scale_max': company.grade_scale_max,
        'click_service_id': company.click_service_id,
        'click_merchant_id': company.click_merchant_id,
        'click_secret_key': click_secret_key,
        'payme_merchant_id': company.payme_merchant_id,
        'payme_secret_key': payme_secret_key,
        'uzum_merchant_id': company.uzum_merchant_id,
        'tabs': [
            'General settings', 'Payment methods', 'Sign in', 'Lead form',
            'Communication', 'Integrations', 'Exams', 'Invoice',
            'Accrual and payment', 'Landing page',
        ],
    })


@api_view(['GET'])
def report_pnl(request):
    """
    Owner (2026-09-28): every branch separately — income, expenses, profit — and "Общие" = all branches together.
    Income of a branch = payments of its groups (the group at payment time; without a group — the student's branch)
    minus refunds. Expenses carry their own branch and date. Withdrawals of the owner are shown apart.
    Nothing is hidden: refunds larger than payments give a negative income.
    """
    from django.db.models.functions import Coalesce

    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    date_from = parse_date_safe(request.query_params.get('date_from'))
    date_to = parse_date_safe(request.query_params.get('date_to'))

    payments_qs = Payment.objects.filter(company=company).annotate(
        money_branch=Coalesce('group__branch_id', 'student__branch_id'),
    )
    if date_from:
        payments_qs = payments_qs.filter(
            Q(payment_date__gte=date_from) | Q(payment_date__isnull=True, created_at__date__gte=date_from)
        )
    if date_to:
        payments_qs = payments_qs.filter(
            Q(payment_date__lte=date_to) | Q(payment_date__isnull=True, created_at__date__lte=date_to)
        )
    expenses_qs = _money_day_filter(Expense.objects.filter(company=company), request.query_params, 'expense_date')
    withdrawals_qs = _money_day_filter(
        Withdrawal.objects.filter(company=company), request.query_params, 'withdrawal_date',
    )

    paid_q = Q(transaction_type=Payment.TransactionType.PAYMENT)
    refund_q = Q(transaction_type=Payment.TransactionType.REFUND)

    income_by_branch = {
        row['money_branch']: (row['paid'] or 0) - (row['refunded'] or 0)
        for row in payments_qs.values('money_branch').annotate(
            paid=Sum('amount', filter=paid_q), refunded=Sum('amount', filter=refund_q),
        )
    }
    expenses_by_branch = {
        row['branch_id']: row['total'] or 0
        for row in expenses_qs.values('branch_id').annotate(total=Sum('amount'))
    }

    branch_rows = []
    for branch in Branch.objects.filter(company=company).order_by('name'):
        income = income_by_branch.pop(branch.id, 0)
        spent = expenses_by_branch.pop(branch.id, 0)
        branch_rows.append({
            'branch_id': branch.id,
            'name': branch.name,
            'revenue': income,
            'expenses': spent,
            'profit': income - spent,
        })
    # Old records that have no branch at all (should not happen, but never lose money silently)
    orphan_income = sum(income_by_branch.values())
    orphan_expenses = sum(expenses_by_branch.values())
    if orphan_income or orphan_expenses:
        branch_rows.append({
            'branch_id': None,
            'name': 'Без филиала',
            'revenue': orphan_income,
            'expenses': orphan_expenses,
            'profit': orphan_income - orphan_expenses,
        })

    total_revenue = sum(row['revenue'] for row in branch_rows)
    total_expenses = sum(row['expenses'] for row in branch_rows)
    total_withdrawals = withdrawals_qs.aggregate(total=Sum('amount'))['total'] or 0
    net_profit = total_revenue - total_expenses
    profit_margin = round((net_profit / total_revenue * 100), 1) if total_revenue > 0 else 0

    revenue_by_method = []
    for method_code, method_name in Payment.Method.choices:
        amount = (
            (payments_qs.filter(paid_q, method=method_code).aggregate(total=Sum('amount'))['total'] or 0)
            - (payments_qs.filter(refund_q, method=method_code).aggregate(total=Sum('amount'))['total'] or 0)
        )
        revenue_by_method.append({
            'method': method_code,
            'label': method_name,
            'amount': amount,
            'percent': round((amount / total_revenue * 100), 1) if total_revenue > 0 else 0,
        })

    expense_by_category = []
    for row in expenses_qs.values('category_id', 'category__name').annotate(total=Sum('amount')):
        expense_by_category.append({
            'id': row['category_id'],
            'name': row['category__name'] or 'Без категории',
            'amount': row['total'] or 0,
            'percent': round(((row['total'] or 0) / total_expenses * 100), 1) if total_expenses > 0 else 0,
        })
    expense_by_category.sort(key=lambda x: x['amount'], reverse=True)

    return ok({
        'summary': {
            'total_revenue': total_revenue,
            'total_expenses': total_expenses,
            'total_withdrawals': total_withdrawals,
            'net_profit': net_profit,
            'profit_margin': profit_margin,
            'date_from': date_from.isoformat() if date_from else None,
            'date_to': date_to.isoformat() if date_to else None,
        },
        'branches': branch_rows,
        'revenue_by_method': revenue_by_method,
        'expense_by_category': expense_by_category,
    })


def _salary_branch(company, person):
    """Branch of a salary expense: the teacher's branch, the staff member's branch, else the first branch."""
    teacher_branch = TeacherBranch.objects.filter(teacher=person).order_by('id').values_list('branch_id', flat=True).first()
    branch_id = teacher_branch or getattr(person, 'branch_id', None)
    if branch_id:
        return Branch.objects.filter(pk=branch_id, company=company).first()
    return Branch.objects.filter(company=company).order_by('id').first()


def _payroll_people(company, request_user, start_date, end_date, month_key):
    """
    Who is on the salary list of a month: active teachers, office staff with a monthly amount, and anybody
    archived who still has something accrued or paid in that month (so an unpaid salary never disappears).
    """
    from finance.payroll import closed_month_of, payroll_people, person_payroll

    teachers = scope_teachers(User.objects.filter(company=company, user_type=User.UserType.TEACHER), request_user)
    staff = User.objects.filter(company=company, user_type=User.UserType.STAFF)
    limit = branch_limit(request_user)
    if limit is not None:
        staff = staff.filter(branch_id=limit)
    closed = closed_month_of(company, month_key)

    rows = []
    for person in payroll_people(company, month_key, teachers=teachers, staff=staff, closed=closed):
        row = person_payroll(company, person, month_key, start_date, end_date, closed=closed)
        if not person.is_active and row['accrued'] <= 0 and row['paid'] <= 0:
            continue  # archived and nothing for this month
        rows.append(row)
    return rows


def _is_ceo(user) -> bool:
    return user.is_superuser or get_effective_role(user) == ROLE_CEO


def _closed_info(closed) -> dict | None:
    if closed is None:
        return None
    return {
        'month': closed.month,
        'closed_at': timezone.localtime(closed.closed_at).strftime('%d.%m.%Y %H:%M'),
        'closed_by': closed.closed_by.display_name() if closed.closed_by_id else '',
    }


@api_view(['GET'])
def payroll_summary(request):
    from finance.payroll import parse_month

    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    parsed = parse_month(request.query_params.get('month') or timezone.localdate().strftime('%Y-%m'))
    if parsed is None:
        return fail('Неверный месяц (нужно ГГГГ-ММ).')
    month_key, start_date, end_date = parsed

    from finance.closing import month_is_over
    from finance.payroll import closed_month_of

    rows = _payroll_people(company, request.user, start_date, end_date, month_key)
    closed = closed_month_of(company, month_key)
    return ok({
        'month': month_key,
        # Closing the month (owner, 2026-09-29): frozen salaries, locked money records
        'closed': _closed_info(closed),
        'can_close': closed is None and month_is_over(month_key),
        'summary': {
            'total_accrued': sum(r['accrued'] for r in rows),
            'total_paid': sum(r['paid'] for r in rows),
            # What is owed, person by person: an overpayment to one never hides a debt to another
            'total_balance': sum(r['balance'] for r in rows),
            'teachers_count': len(rows),
        },
        'rows': rows,
    })


@api_view(['POST'])
def payroll_pay(request):
    from finance.payroll import parse_month, person_payroll, split_by_weights

    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        person = User.objects.get(
            pk=int(request.data.get('teacher_id') or request.data.get('person_id')), company=company,
            user_type__in=(User.UserType.TEACHER, User.UserType.STAFF),
        )
    except (User.DoesNotExist, TypeError, ValueError):
        return fail('Сотрудник или учитель не найден.', status_code=404)

    amount = _parse_money(request.data.get('amount'))
    if amount is None:
        return fail(MONEY_MESSAGE)
    method = str(request.data.get('method') or 'cash').strip().lower()
    if method not in {c[0] for c in Expense.Method.choices}:
        return fail('Invalid payment method')
    parsed = parse_month(request.data.get('month') or timezone.localdate().strftime('%Y-%m'))
    if parsed is None:
        # "2026-13" used to be stored as a separate "month" and the salary could be paid twice
        return fail('Неверный месяц (нужно ГГГГ-ММ).')
    month_key, start_date, end_date = parsed
    comment = str(request.data.get('comment') or f'Зарплата за {month_key}: {person.display_name()}').strip()

    row = person_payroll(company, person, month_key, start_date, end_date)
    accrued, already_paid = row['accrued'], row['paid']
    is_elevated = (get_effective_role(request.user) == ROLE_CEO or request.user.is_superuser)
    force = bool(request.data.get('force'))
    if (already_paid + amount > accrued) and not (force and is_elevated):
        return fail(
            f'Payment exceeds accrued balance for this period ({max(0, accrued - already_paid)} remaining)',
            status_code=400,
            code='overpayment',
            accrued=accrued,
            already_paid=already_paid,
            balance=max(0, accrued - already_paid),
        )

    # Which branches the salary is recorded to
    if row['kind'] == 'teacher':
        weights = {}
        for g in row['groups']:
            weights[g['branch_id']] = weights.get(g['branch_id'], 0) + g['accrued']
        shares = split_by_weights(amount, weights)
        if not shares:
            branch = _salary_branch(company, person)
            shares = {branch.id if branch else None: amount}
    else:
        branch = None
        if request.data.get('branch_id') not in (None, ''):
            branch, error = _expense_branch(company, request.data.get('branch_id'))
            if error:
                return fail(error)
        elif person.branch_id:
            branch = person.branch
        if branch is None:
            return fail('Выберите филиал, на который записать зарплату.')
        shares = {branch.id: amount}

    salary_cat = next(
        (c for c in ExpenseCategory.objects.filter(company=company) if c.name.strip().casefold() == 'зарплата'),
        None,
    ) or ExpenseCategory.objects.create(company=company, name='Зарплата')

    with transaction.atomic():
        payroll_payment = PayrollPayment.objects.create(
            company=company,
            teacher=person,
            payroll_period=month_key,
            amount=amount,
            method=method,
            comment=comment,
            created_by=request.user,
        )
        expenses = [
            Expense.objects.create(
                company=company,
                category=salary_cat,
                description=comment,
                payee=person.display_name(),
                method=method,
                amount=part,
                branch_id=branch_id,
                expense_date=timezone.localdate(),
                payroll_payment=payroll_payment,
                created_by=request.user,
            )
            for branch_id, part in shares.items()
        ]
        overpaid = already_paid + amount > accrued
        log_audit(
            company=company,
            actor=request.user,
            entity_type='payroll',
            entity_id=payroll_payment.id,
            action='force_overpayment' if overpaid else 'payout',
            new_values={
                'teacher_id': person.id,
                'period': month_key,
                'amount': amount,
                'accrued': accrued,
                'already_paid': already_paid,
                **({'overpayment_amount': already_paid + amount - accrued} if overpaid else {}),
            },
            reason=(
                f'Выплата зарплаты #{payroll_payment.id}: {person.display_name()}, {month_key}, '
                f'{_money_str(amount)} сум' + (' (сверх начисленного)' if overpaid else '') + f'. {comment}'
            ),
        )

    return ok({
        'id': payroll_payment.id,
        'expense_id': expenses[0].id if expenses else None,
        'expense_ids': [e.id for e in expenses],
        'teacher_id': person.id,
        'teacher_name': person.display_name(),
        'amount': amount,
        'method': method,
        'comment': comment,
        'payroll_period': month_key,
        'date': timezone.localdate().isoformat(),
    }, status_code=201)


@api_view(['DELETE'])
def payroll_payout_cancel(request, payout_id: int):
    """Cancel a salary payout: the payout and its expenses go together, and it is written to the journal."""
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)
    try:
        payout = PayrollPayment.objects.select_related('teacher').get(pk=payout_id, company=company)
    except PayrollPayment.DoesNotExist:
        return fail('Выплата не найдена.', status_code=404)
    # The payout's expenses are in the P&L of the day it was paid: a closed month keeps them
    days = [_expense_day(e) for e in Expense.objects.filter(Q(payroll_payment=payout) | Q(pk=payout.expense_id))]
    error = closed_error(company.id, *days)
    if error:
        return fail(error)
    with transaction.atomic():
        log_audit(
            company=company, actor=request.user, entity_type='payroll', entity_id=payout.id, action='delete',
            old_values={'teacher_id': payout.teacher_id, 'period': payout.payroll_period, 'amount': payout.amount},
            reason=(
                f'Отменена выплата зарплаты #{payout.id}: {payout.teacher.display_name()}, '
                f'{payout.payroll_period}, {_money_str(payout.amount)} сум'
            ),
        )
        if payout.expense_id:  # payouts made before block 3 kept one expense in this field
            Expense.objects.filter(pk=payout.expense_id).delete()
        payout.delete()  # its branch expenses go with it (CASCADE)
    return ok({'deleted': True})


# ---------------------------------------------------------------------------
# Closing a month (owner, 2026-09-29): finance/closing.py
# ---------------------------------------------------------------------------

@api_view(['GET'])
def finance_months(request):
    """Closed months of the company, newest first."""
    from finance.closing import month_title
    from finance.models import ClosedMonth

    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)
    rows = ClosedMonth.objects.filter(company=company).select_related('closed_by').order_by('-month')
    return ok([{**_closed_info(c), 'title': month_title(c.month)} for c in rows])


@api_view(['POST'])
def finance_month_close(request):
    from finance.closing import close_month, month_is_over, month_title
    from finance.payroll import closed_month_of, parse_month

    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)
    if not _is_ceo(request.user):
        return fail('Закрыть месяц может только CEO.', status_code=403)
    parsed = parse_month(request.data.get('month'))
    if parsed is None:
        return fail('Неверный месяц (нужно ГГГГ-ММ).')
    key = parsed[0]
    if closed_month_of(company, key) is not None:
        return fail(f'{month_title(key)} уже закрыт.')
    if not month_is_over(key):
        return fail(f'{month_title(key)} ещё не закончился — закрыть можно только прошедший месяц.')
    closed = close_month(company, key, request.user)
    log_audit(
        company=company, actor=request.user, entity_type='finance_month', entity_id=closed.id, action='close',
        new_values={'month': key},
        reason=f'Закрыт месяц {month_title(key)}: зарплаты зафиксированы, записи с датой этого месяца заблокированы',
    )
    return ok(_closed_info(closed), status_code=201)


@api_view(['POST'])
def finance_month_reopen(request):
    from finance.closing import month_title
    from finance.payroll import closed_month_of, parse_month

    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)
    if not _is_ceo(request.user):
        return fail('Открыть месяц может только CEO.', status_code=403)
    parsed = parse_month(request.data.get('month'))
    if parsed is None:
        return fail('Неверный месяц (нужно ГГГГ-ММ).')
    key = parsed[0]
    closed = closed_month_of(company, key)
    if closed is None:
        return fail(f'{month_title(key)} не закрыт.')
    reason = str(request.data.get('reason') or '').strip()
    if len(reason) < 3:
        return fail('Укажите причину, зачем открываете месяц.')
    frozen = {str(s.person_id): s.accrued for s in closed.payroll.all()}
    with transaction.atomic():
        log_audit(
            company=company, actor=request.user, entity_type='finance_month', entity_id=closed.id, action='reopen',
            old_values={'month': key, 'closed_at': _closed_info(closed)['closed_at'], 'frozen_salaries': frozen},
            reason=f'Открыт месяц {month_title(key)}: {reason}',
        )
        closed.delete()  # the frozen salaries go with it: the month is counted from the data again
    return ok({'month': key, 'closed': None})


@api_view(['POST'])
def payroll_adjustment_create(request):
    from finance.closing import month_title
    from finance.models import PayrollAdjustment
    from finance.payroll import parse_month, person_payroll

    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)
    if not _is_ceo(request.user):
        return fail('Поправку к зарплате делает только CEO.', status_code=403)
    try:
        person = User.objects.get(
            pk=int(request.data.get('person_id') or request.data.get('teacher_id')), company=company,
            user_type__in=(User.UserType.TEACHER, User.UserType.STAFF),
        )
    except (User.DoesNotExist, TypeError, ValueError):
        return fail('Сотрудник или учитель не найден.', status_code=404)
    parsed = parse_month(request.data.get('month'))
    if parsed is None:
        return fail('Неверный месяц (нужно ГГГГ-ММ).')
    key, start_date, end_date = parsed
    raw = str(request.data.get('amount') if request.data.get('amount') is not None else '').replace(' ', '')
    negative = raw.startswith('-')
    amount = _parse_money(raw[1:] if negative else raw)
    if amount is None:
        return fail('Сумма поправки — целое число, например 50000 или -50000.')
    amount = -amount if negative else amount
    reason = str(request.data.get('reason') or '').strip()
    if len(reason) < 3:
        return fail('Укажите причину поправки.')
    row = person_payroll(company, person, key, start_date, end_date)
    if row['accrued'] + amount < 0:
        return fail(f'Начисление не может стать меньше нуля: можно убрать не больше {_money_str(row["accrued"])} сум.')
    adjustment = PayrollAdjustment.objects.create(
        company=company, person=person, payroll_period=key, amount=amount, reason=reason, created_by=request.user,
    )
    sign = '+' if amount > 0 else '−'
    log_audit(
        company=company, actor=request.user, entity_type='payroll', entity_id=adjustment.id, action='adjustment',
        new_values={'person_id': person.id, 'period': key, 'amount': amount},
        reason=(
            f'Поправка к зарплате: {person.display_name()}, {month_title(key)}, '
            f'{sign}{_money_str(abs(amount))} сум. {reason}'
        ),
    )
    return ok({'id': adjustment.id, 'amount': amount, 'reason': reason, 'month': key}, status_code=201)


@api_view(['DELETE'])
def payroll_adjustment_delete(request, adjustment_id: int):
    from finance.closing import month_title
    from finance.models import PayrollAdjustment
    from finance.payroll import parse_month, person_payroll

    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)
    if not _is_ceo(request.user):
        return fail('Поправку к зарплате удаляет только CEO.', status_code=403)
    try:
        adjustment = PayrollAdjustment.objects.select_related('person').get(pk=adjustment_id, company=company)
    except PayrollAdjustment.DoesNotExist:
        return fail('Поправка не найдена.', status_code=404)
    key, start_date, end_date = parse_month(adjustment.payroll_period)
    row = person_payroll(company, adjustment.person, key, start_date, end_date)
    if row['accrued'] - adjustment.amount < 0:
        return fail('Без этой поправки начисление станет меньше нуля — сначала удалите другие поправки.')
    with transaction.atomic():
        log_audit(
            company=company, actor=request.user, entity_type='payroll', entity_id=adjustment.id,
            action='adjustment_delete',
            old_values={'person_id': adjustment.person_id, 'period': key, 'amount': adjustment.amount},
            reason=(
                f'Удалена поправка к зарплате: {adjustment.person.display_name()}, {month_title(key)}, '
                f'{_money_str(adjustment.amount)} сум ({adjustment.reason})'
            ),
        )
        adjustment.delete()
    return ok({'deleted': True})


