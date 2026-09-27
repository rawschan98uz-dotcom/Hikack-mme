from datetime import date as date_cls, datetime, time

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from accounts.models import TeacherBranch, User
from accounts.rbac import (
    ROLE_CEO,
    PERM_FINANCE_VIEW,
    PERM_FINANCE_WRITE,
    PERM_SETTINGS_COMPANY,
    PERM_STAFF_WRITE,
    PERM_TEACHERS_WRITE,
    get_effective_role,
    get_role_label,
    user_has_permission,
    user_is_teacher,
)
from api.archive import archive_teacher
from finance.refunds import recalc_refunded_months
from finance.wallet import current_month_price, recalc_student_wallet
from finance.salary import find_overlapping_setting, overlap_error, resolve_salary_setting, students_in_groups_during
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
from api.utils import name_taken, normalize_phone, safe_int, parse_date_safe
from crm.models import AttendanceRecord, Group, Lead, Student
from operations.models import TeacherAttendanceRecord, WorklyRecord, log_audit
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
        return ok([_serialize_staff(u) for u in qs.select_related('branch').order_by('id')])

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


def _finance_date_filter(qs, params, field='created_at'):
    date_from = params.get('date_from')
    if date_from:
        qs = qs.filter(**{f'{field}__date__gte': date_from})
    date_to = params.get('date_to')
    if date_to:
        qs = qs.filter(**{f'{field}__date__lte': date_to})
    return qs


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
        student = None
        student_id = request.data.get('student_id')
        if student_id:
            try:
                student = Student.objects.get(pk=int(student_id), company=company)
            except (Student.DoesNotExist, TypeError, ValueError):
                pass

        student_name = str(request.data.get('student_name') or request.data.get('name') or '').strip()
        if student and not student_name:
            student_name = student.full_name
        elif not student and student_name:
            matched = [
                s for s in Student.objects.filter(company=company)
                if f"{s.first_name} {s.last_name}".strip().lower() == student_name.lower()
            ]
            if len(matched) == 1:
                student = matched[0]
            elif len(matched) > 1:
                return fail(
                    'Найдено несколько учеников с таким именем. Укажите student_id явно.',
                    status_code=400
                )
            else:
                partial = list(Student.objects.filter(company=company).filter(
                    Q(first_name__iexact=student_name) | Q(last_name__iexact=student_name)
                ))
                if len(partial) == 1:
                    student = partial[0]
                elif len(partial) > 1:
                    return fail(
                        'Найдено несколько учеников с таким именем. Укажите student_id явно.',
                        status_code=400
                    )

        if not student_name:
            return fail('Student name is required')
        try:
            amount = int(request.data.get('amount') or request.data.get('sum'))
            if amount <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            return fail('Valid positive amount is required')
        try:
            months_covered = max(1, int(request.data.get('months_covered') or 1))
        except (TypeError, ValueError):
            months_covered = 1
        method = str(request.data.get('method') or Payment.Method.CASH).strip().lower()
        if method not in {choice[0] for choice in Payment.Method.choices}:
            return fail('Invalid payment method')

        raw_payment_date = request.data.get('payment_date') or request.data.get('date')
        if raw_payment_date:
            payment_date = parse_date_safe(raw_payment_date) or timezone.localdate()
        else:
            payment_date = timezone.localdate()

        group = None
        course = None
        teacher = None
        if student and student.group:
            group = student.group
            course = student.group.course
            teacher = student.group.teacher
        elif request.data.get('group_id'):
            try:
                group = Group.objects.get(pk=int(request.data.get('group_id')), company=company)
                course = group.course
                teacher = group.teacher
            except (Group.DoesNotExist, TypeError, ValueError):
                pass

        teacher_name = str(request.data.get('teacher_name') or request.data.get('teacher') or '').strip()
        if not teacher_name and teacher:
            teacher_name = teacher.display_name()

        discount_amount = max(0, safe_int(request.data.get('discount_amount'), default=0))
        gross_amount = amount + discount_amount
        net_amount = amount

        # Копилка: with a known course price the months are counted from the money;
        # otherwise the administrator's months are used as before.
        month_price = current_month_price(student) if student else 0
        if month_price > 0:
            months_covered = 0  # filled in by recalc_student_wallet below

        payment = Payment.objects.create(
            company=company,
            student=student,
            group=group,
            course=course,
            teacher=teacher,
            student_name=student_name,
            amount=amount,
            gross_amount=gross_amount,
            net_amount=net_amount,
            discount_amount=discount_amount,
            transaction_type=Payment.TransactionType.PAYMENT,
            months_covered=months_covered,
            payment_date=payment_date,
            method=method,
            teacher_name=teacher_name,
            comment=str(request.data.get('comment') or '').strip(),
            created_by=request.user,
            month_price=month_price or None,
        )

        if student:
            if month_price > 0:
                recalc_student_wallet(student)
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

    return ok([_serialize_payment(payment) for payment in qs[:200]])


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
        if raw_amount is not None:
            try:
                refund_amount = int(raw_amount)
                if refund_amount <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                return fail('Valid positive refund amount is required', status_code=400)
            if refund_amount > available_to_refund:
                return fail(f'Refund amount exceeds available refundable amount ({available_to_refund})', status_code=400)
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

        if original.student:
            from crm.services import sync_student_paid_this_month
            sync_student_paid_this_month(original.student)

        return ok(_serialize_payment(refund), status_code=201)


@api_view(['GET', 'PATCH', 'DELETE'])
def payment_detail(request, payment_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    is_ceo = (get_effective_role(request.user) == ROLE_CEO or request.user.is_superuser)
    if request.method in ('PATCH', 'DELETE'):
        if not is_ceo and not user_has_permission(request.user, PERM_FINANCE_WRITE):
            return fail('Permission denied', status_code=403)
    else:
        if not is_ceo and not user_has_permission(request.user, PERM_FINANCE_VIEW):
            return fail('Permission denied', status_code=403)

    try:
        payment = Payment.objects.select_related('created_by', 'student').get(pk=payment_id, company=company)
    except Payment.DoesNotExist:
        return fail('Payment not found', status_code=404)
    if not can_access_payment(request.user, payment):
        return fail('Payment not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_payment(payment))

    if request.method == 'DELETE':
        if payment.reversals.exists():
            return fail('Cannot delete a payment that has reversals or refunds', status_code=400)
        with transaction.atomic():
            student = payment.student
            refunded_payment = payment.reverses_payment
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
    if 'student_id' in request.data:
        sid = request.data.get('student_id')
        if sid in (None, '', 0):
            payment.student = None
        else:
            try:
                payment.student = Student.objects.get(pk=int(sid), company=company)
                if not request.data.get('student_name'):
                    payment.student_name = payment.student.full_name
            except (Student.DoesNotExist, TypeError, ValueError):
                pass

    if 'student_name' in request.data or 'name' in request.data:
        student_name = str(request.data.get('student_name') or request.data.get('name') or '').strip()
        if not student_name:
            return fail('Student name is required')
        payment.student_name = student_name
    if 'amount' in request.data or 'sum' in request.data:
        try:
            amt = int(request.data.get('amount') or request.data.get('sum'))
            if amt <= 0:
                return fail('Valid positive amount is required')
            payment.amount = amt
        except (TypeError, ValueError):
            return fail('Valid amount is required')
    if 'months_covered' in request.data and payment.month_price is None:
        # Копилка payments count their months from the money; only hand-entered ones take a number
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

    with transaction.atomic():
        payment.save()
        payment.refresh_from_db()
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


def _serialize_withdrawal(withdrawal: Withdrawal) -> dict:
    return {
        'id': withdrawal.id,
        'date': withdrawal.created_at.strftime('%Y-%m-%d'),
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
        try:
            amount = int(request.data.get('amount') or request.data.get('sum'))
            if amount <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            return fail('Valid positive amount is required')

        withdrawal = Withdrawal.objects.create(
            company=company,
            name=name,
            amount=amount,
            comment=str(request.data.get('comment') or '').strip(),
            created_by=request.user,
        )
        return ok(_serialize_withdrawal(withdrawal), status_code=201)

    qs = Withdrawal.objects.filter(company=company).select_related('created_by').order_by('-created_at')
    qs = _finance_date_filter(qs, request.query_params)
    query = (request.query_params.get('q') or '').strip()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(comment__icontains=query))

    return ok([_serialize_withdrawal(w) for w in qs[:200]])


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

    if request.method == 'DELETE':
        withdrawal.delete()
        return ok({'deleted': True})

    if 'name' in request.data:
        name = str(request.data.get('name') or '').strip()
        if not name:
            return fail('Name is required')
        withdrawal.name = name
    if 'amount' in request.data or 'sum' in request.data:
        try:
            amount = int(request.data.get('amount') or request.data.get('sum'))
            if amount <= 0:
                raise ValueError()
            withdrawal.amount = amount
        except (TypeError, ValueError):
            return fail('Valid positive amount is required')
    if 'comment' in request.data:
        withdrawal.comment = str(request.data.get('comment') or '').strip()

    withdrawal.save()
    withdrawal.refresh_from_db()
    return ok(_serialize_withdrawal(withdrawal))


def _serialize_expense(expense: Expense) -> dict:
    return {
        'id': expense.id,
        'date': expense.created_at.strftime('%Y-%m-%d'),
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
        try:
            amount = int(request.data.get('amount') or request.data.get('sum'))
            if amount <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            return fail('Valid positive amount is required')
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

        expense = Expense.objects.create(
            company=company,
            category=category,
            description=str(request.data.get('description') or '').strip(),
            payee=str(request.data.get('payee') or '').strip(),
            method=method,
            amount=amount,
            created_by=request.user,
        )
        expense = Expense.objects.select_related('category', 'created_by').get(pk=expense.pk)
        return ok(_serialize_expense(expense), status_code=201)

    qs = Expense.objects.filter(company=company).select_related('category', 'created_by').order_by('-created_at')
    qs = _finance_date_filter(qs, request.query_params)
    category_id = request.query_params.get('category_id')
    if category_id:
        qs = qs.filter(category_id=category_id)
    query = (request.query_params.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(description__icontains=query) | Q(payee__icontains=query) | Q(category__name__icontains=query),
        )

    return ok([_serialize_expense(e) for e in qs[:200]])


@api_view(['GET', 'PATCH', 'DELETE'])
def expense_detail(request, expense_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        expense = Expense.objects.select_related('category', 'created_by').get(pk=expense_id, company=company)
    except Expense.DoesNotExist:
        return fail('Expense not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_expense(expense))

    if request.method == 'DELETE':
        expense.delete()
        return ok({'deleted': True})

    if 'amount' in request.data or 'sum' in request.data:
        try:
            amount = int(request.data.get('amount') or request.data.get('sum'))
            if amount <= 0:
                raise ValueError()
            expense.amount = amount
        except (TypeError, ValueError):
            return fail('Valid positive amount is required')
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

    expense.save()
    expense = Expense.objects.select_related('category', 'created_by').get(pk=expense.pk)
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


@api_view(['GET', 'POST'])
def salary_settings(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        teacher = None
        teacher_id = request.data.get('teacher_id')
        if teacher_id:
            try:
                teacher = User.objects.get(pk=int(teacher_id), company=company, user_type=User.UserType.TEACHER)
            except (User.DoesNotExist, TypeError, ValueError):
                return fail('Invalid teacher')

        teacher_name = str(request.data.get('teacher_name') or request.data.get('teacher') or '').strip()
        if not teacher and teacher_name:
            for t in User.objects.filter(company=company, user_type=User.UserType.TEACHER):
                if teacher_name.lower() in (t.display_name().lower(), f"{t.first_name} {t.last_name}".strip().lower()):
                    teacher = t
                    break

        if teacher and not teacher_name:
            teacher_name = teacher.display_name()

        salary_type = str(request.data.get('salary_type') or SalarySetting.SalaryType.FIXED).strip().lower()
        if salary_type not in {choice[0] for choice in SalarySetting.SalaryType.choices}:
            return fail('Invalid salary type')
        try:
            amount = int(request.data.get('amount') or 0)
        except (TypeError, ValueError):
            return fail('Valid amount is required')

        effective_from = parse_date_safe(request.data.get('effective_from'))
        effective_to = parse_date_safe(request.data.get('effective_to'))
        if effective_from and effective_to and effective_from > effective_to:
            return fail('Effective from date cannot be later than effective to date')

        course = None
        course_id = request.data.get('course_id')
        if course_id:
            try:
                course = Course.objects.get(pk=int(course_id), company=company)
            except (Course.DoesNotExist, TypeError, ValueError):
                return fail('Invalid course')

        group = None
        group_id = request.data.get('group_id')
        if group_id:
            try:
                group = Group.objects.get(pk=int(group_id), company=company)
            except (Group.DoesNotExist, TypeError, ValueError):
                return fail('Invalid group')

        overlapping = find_overlapping_setting(
            company, teacher, course.id if course else None, group.id if group else None, effective_from, effective_to,
        )
        if overlapping:
            return fail(overlap_error(overlapping))

        setting = SalarySetting.objects.create(
            company=company,
            teacher=teacher,
            teacher_name=teacher_name or '—',
            course=course,
            course_name=course.name if course else str(request.data.get('course_name') or request.data.get('course') or '').strip(),
            group=group,
            group_name=group.name if group else str(request.data.get('group_name') or request.data.get('group') or '').strip(),
            effective_from=effective_from,
            effective_to=effective_to,
            salary_type=salary_type,
            amount=amount,
            created_by=request.user,
            updated_by=request.user,
        )
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

    if 'teacher_id' in request.data:
        t_id = request.data.get('teacher_id')
        if t_id in ('', None):
            setting.teacher = None
        else:
            try:
                setting.teacher = User.objects.get(pk=int(t_id), company=company, user_type=User.UserType.TEACHER)
                setting.teacher_name = setting.teacher.display_name()
            except (User.DoesNotExist, TypeError, ValueError):
                return fail('Invalid teacher')

    if 'teacher_name' in request.data or 'teacher' in request.data:
        t_name = str(request.data.get('teacher_name') or request.data.get('teacher') or '').strip()
        setting.teacher_name = t_name or '—'
        if not setting.teacher and t_name:
            for t in User.objects.filter(company=company, user_type=User.UserType.TEACHER):
                if t_name.lower() in (t.display_name().lower(), f"{t.first_name} {t.last_name}".strip().lower()):
                    setting.teacher = t
                    break

    if 'salary_type' in request.data:
        salary_type = str(request.data.get('salary_type')).strip().lower()
        if salary_type not in {choice[0] for choice in SalarySetting.SalaryType.choices}:
            return fail('Invalid salary type')
        setting.salary_type = salary_type

    if 'amount' in request.data:
        try:
            setting.amount = int(request.data.get('amount'))
        except (TypeError, ValueError):
            return fail('Valid amount is required')

    if 'effective_from' in request.data:
        setting.effective_from = parse_date_safe(request.data.get('effective_from'))
    if 'effective_to' in request.data:
        setting.effective_to = parse_date_safe(request.data.get('effective_to'))
    if setting.effective_from and setting.effective_to and setting.effective_from > setting.effective_to:
        return fail('Effective from date cannot be later than effective to date')

    if 'course_id' in request.data:
        c_id = request.data.get('course_id')
        if c_id in ('', None):
            setting.course = None
            setting.course_name = ''
        else:
            try:
                setting.course = Course.objects.get(pk=int(c_id), company=company)
                setting.course_name = setting.course.name
            except (Course.DoesNotExist, TypeError, ValueError):
                return fail('Invalid course')
    elif 'course_name' in request.data or 'course' in request.data:
        setting.course_name = str(request.data.get('course_name') or request.data.get('course') or '').strip()

    if 'group_id' in request.data:
        g_id = request.data.get('group_id')
        if g_id in ('', None):
            setting.group = None
            setting.group_name = ''
        else:
            try:
                setting.group = Group.objects.get(pk=int(g_id), company=company)
                setting.group_name = setting.group.name
            except (Group.DoesNotExist, TypeError, ValueError):
                return fail('Invalid group')
    elif 'group_name' in request.data or 'group' in request.data:
        setting.group_name = str(request.data.get('group_name') or request.data.get('group') or '').strip()

    overlapping = find_overlapping_setting(
        company, setting.teacher, setting.course_id, setting.group_id,
        setting.effective_from, setting.effective_to, exclude_pk=setting.pk,
    )
    if overlapping:
        return fail(overlap_error(overlapping))

    setting.updated_by = request.user
    setting.save()
    setting = SalarySetting.objects.select_related('created_by', 'updated_by', 'teacher', 'course', 'group').get(pk=setting.pk)
    return ok(_serialize_salary(setting))


@api_view(['GET'])
def report_conversion(request):
    company = _company(request)
    if company is None:
        return ok({'pipeline': {}, 'rows': [], 'total': 0, 'page': 1, 'total_pages': 1})

    leads = scope_branch(
        Lead.objects.filter(company=company).select_related('course', 'branch').order_by('-created_at'),
        request.user,
    )
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

    source = params.get('source')
    if source:
        leads = leads.filter(source__iexact=source.strip())

    course_id = params.get('course_id')
    if course_id:
        try:
            leads = leads.filter(course_id=int(course_id))
        except (TypeError, ValueError):
            pass

    branch_id = params.get('branch_id')
    if branch_id:
        try:
            leads = leads.filter(branch_id=int(branch_id))
        except (TypeError, ValueError):
            pass

    query = (params.get('q') or '').strip()
    if query:
        leads = leads.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(source__icontains=query)
            | Q(school__icontains=query)
        )

    stage_order = [choice[0] for choice in Lead.Stage.choices]
    stages = {stage: leads.filter(stage=stage).count() for stage in stage_order}
    total = leads.count()
    attended_total = leads.filter(
        Q(attended_trial=True) | Q(stage__in=[Lead.Stage.ATTENDED, Lead.Stage.CONVERTED])
    ).distinct().count()

    def _serialize_conversion_lead(lead: Lead) -> dict:
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
            'created_at': lead.created_at.date().isoformat(),
            'trial_booked': True,
            'attended': bool(getattr(lead, 'attended_trial', False) or lead.stage in (Lead.Stage.ATTENDED, Lead.Stage.CONVERTED)),
            'converted': lead.stage == Lead.Stage.CONVERTED,
            'rejected': lead.stage == Lead.Stage.REJECTED,
            'is_active': lead.is_active,
        }

    export = params.get('export', '0') == '1'
    if export:
        rows = [_serialize_conversion_lead(lead) for lead in leads]
        return ok({'pipeline': stages, 'attended_total': attended_total, 'rows': rows, 'total': total})

    try:
        page = max(1, int(params.get('page', 1)))
    except (ValueError, TypeError):
        page = 1

    page_size = 50
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    rows = [_serialize_conversion_lead(lead) for lead in leads[offset:offset + page_size]]
    return ok({
        'pipeline': stages,
        'attended_total': attended_total,
        'rows': rows,
        'total': total,
        'page': page,
        'total_pages': total_pages,
    })


VALID_ATTENDANCE_STATUSES = {choice[0] for choice in AttendanceRecord.Status.choices}


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



VALID_TEACHER_ATTENDANCE_STATUSES = {choice[0] for choice in TeacherAttendanceRecord.Status.choices}


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
        if group.teacher_id != teacher.id:
            return fail('Teacher is not the assigned teacher for this group', 400)

        if status is None:
            status = TeacherAttendanceRecord.Status.PRESENT

        if status not in VALID_TEACHER_ATTENDANCE_STATUSES:
            return fail('Invalid status')

        note = str(request.data.get('note') or '').strip()
        record, _created = TeacherAttendanceRecord.objects.update_or_create(
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

    if request.method == 'DELETE':
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
    if record.group.teacher_id != record.teacher_id:
        return fail('Teacher is not the assigned teacher for this group', 400)

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


@api_view(['GET'])
def report_leads(request):
    company = _company(request)
    if company is None:
        return ok({'total': 0, 'active': 0, 'by_stage': {}, 'rows': [], 'page': 1, 'total_pages': 1})

    leads = scope_branch(
        Lead.objects.filter(company=company).select_related('course', 'branch').order_by('-created_at'),
        request.user,
    )
    params = request.query_params

    if params.get('active') == '1':
        leads = leads.filter(is_active=True)

    stage = params.get('stage')
    if stage:
        leads = leads.filter(stage=stage)

    date_from = parse_date_safe(params.get('date_from'))
    if date_from:
        leads = leads.filter(created_at__date__gte=date_from)

    date_to = parse_date_safe(params.get('date_to'))
    if date_to:
        leads = leads.filter(created_at__date__lte=date_to)

    source = params.get('source')
    if source:
        leads = leads.filter(source__iexact=source.strip())

    course_id = params.get('course_id')
    if course_id:
        try:
            leads = leads.filter(course_id=int(course_id))
        except (TypeError, ValueError):
            pass

    branch_id = params.get('branch_id')
    if branch_id:
        try:
            leads = leads.filter(branch_id=int(branch_id))
        except (TypeError, ValueError):
            pass

    query = (params.get('q') or '').strip()
    if query:
        leads = leads.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(source__icontains=query)
            | Q(school__icontains=query)
        )

    by_stage = {stage: leads.filter(stage=stage).count() for stage, _ in Lead.Stage.choices}
    total = leads.count()
    active_count = leads.filter(is_active=True).count()

    def _serialize_report_lead(lead: Lead) -> dict:
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
            'is_active': lead.is_active,
            'created_at': lead.created_at.date().isoformat(),
        }

    export = params.get('export', '0') == '1'
    if export:
        rows = [_serialize_report_lead(lead) for lead in leads]
        return ok({
            'total': total,
            'active': active_count,
            'by_stage': by_stage,
            'rows': rows,
        })

    try:
        page = max(1, int(params.get('page', 1)))
    except (ValueError, TypeError):
        page = 1

    page_size = 50
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    rows = [_serialize_report_lead(lead) for lead in leads[offset:offset + page_size]]
    return ok({
        'total': total,
        'active': active_count,
        'by_stage': by_stage,
        'rows': rows,
        'page': page,
        'total_pages': total_pages,
    })


LEFT_STUDENT_STATUSES = {Student.Status.LEFT_TRIAL, Student.Status.LEFT}


def _left_debt(student: Student) -> dict | None:
    # Unpaid months at the moment of leaving; "left after trial" never owes (the trial is free)
    if student.status != Student.Status.LEFT:
        return None
    from api.v1.views import student_debt_on
    return student_debt_on(student)


def _serialize_left_student(student: Student) -> dict:
    left_dt = student.left_at or student.created_at
    debt = _left_debt(student)
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
        'left_at': left_dt.date().isoformat() if left_dt else '',
        'debt_months': debt['months'] if debt else 0,
        'debt_amount': debt['approx_amount'] if debt else 0,
        'debt_since': debt['unpaid_since'].isoformat() if debt else None,
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

    date_from = params.get('date_from')
    if date_from:
        qs = qs.filter(
            Q(left_at__date__gte=date_from) | Q(left_at__isnull=True, created_at__date__gte=date_from)
        )

    date_to = params.get('date_to')
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
    debtor_ids = [s.id for s in left_active if _left_debt(s)]
    if request.query_params.get('with_debt') in ('1', 'true'):
        qs = qs.filter(id__in=debtor_ids)
    total = qs.count()
    summary = _left_students_summary(qs)
    summary['with_debt'] = len(debtor_ids)

    export = request.query_params.get('export', '0') == '1'
    if export:
        return ok({
            'summary': summary,
            'rows': [_serialize_left_student(student) for student in qs],
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
        'rows': [_serialize_left_student(student) for student in qs[offset:offset + page_size]],
        'total': total,
        'page': page,
        'total_pages': total_pages,
    })


def _parse_time(value) -> time | None:
    if not value:
        return None
    if isinstance(value, time):
        return value
    text = str(value).strip()
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _serialize_workly(record: WorklyRecord) -> dict:
    return {
        'id': record.id,
        'staff_id': record.staff_id,
        'staff': record.staff.display_name(),
        'job_title': record.staff.job_title or '—',
        'work_date': record.work_date.isoformat(),
        'clock_in': record.clock_in.strftime('%H:%M') if record.clock_in else '',
        'clock_out': record.clock_out.strftime('%H:%M') if record.clock_out else '',
        'status': record.status,
        'status_label': record.get_status_display(),
        'note': record.note,
        'created_at': record.created_at.isoformat(),
    }


def _workly_queryset(company, params):
    qs = WorklyRecord.objects.filter(company=company).select_related('staff').order_by(
        '-work_date',
        'staff__first_name',
    )

    status = params.get('status')
    if status in {choice[0] for choice in WorklyRecord.Status.choices}:
        qs = qs.filter(status=status)

    staff_id = params.get('staff_id')
    if staff_id:
        qs = qs.filter(staff_id=staff_id)

    date_from = params.get('date_from')
    if date_from:
        qs = qs.filter(work_date__gte=date_from)

    date_to = params.get('date_to')
    if date_to:
        qs = qs.filter(work_date__lte=date_to)

    query = (params.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(staff__first_name__icontains=query)
            | Q(staff__last_name__icontains=query)
            | Q(note__icontains=query),
        )

    return qs


def _workly_summary(qs) -> dict:
    counts = qs.values('status').annotate(total=Count('id'))
    summary = {'at_work': 0, 'late_in': 0, 'absent': 0, 'total': 0}
    for row in counts:
        if row['status'] == WorklyRecord.Status.AT_WORK:
            summary['at_work'] = row['total']
        elif row['status'] == WorklyRecord.Status.LATE_IN:
            summary['late_in'] = row['total']
        elif row['status'] == WorklyRecord.Status.ABSENT:
            summary['absent'] = row['total']
        summary['total'] += row['total']
    return summary


VALID_WORKLY_STATUSES = {choice[0] for choice in WorklyRecord.Status.choices}


@api_view(['GET', 'POST'])
def report_workly(request):
    company = _company(request)
    if company is None:
        return ok({'summary': {'at_work': 0, 'late_in': 0, 'absent': 0, 'total': 0}, 'rows': []})

    if request.method == 'POST':
        try:
            staff_id = int(request.data.get('staff_id'))
        except (TypeError, ValueError):
            return fail('Staff is required')

        staff = User.objects.filter(pk=staff_id, company=company).first()
        if staff is None:
            return fail('Staff not found', status_code=404)

        work_date = request.data.get('work_date') or date_cls.today().isoformat()
        status = request.data.get('status', WorklyRecord.Status.AT_WORK)
        if status not in VALID_WORKLY_STATUSES:
            return fail('Invalid status')

        record, created = WorklyRecord.objects.get_or_create(
            company=company,
            staff=staff,
            work_date=work_date,
            defaults={
                'clock_in': _parse_time(request.data.get('clock_in')),
                'clock_out': _parse_time(request.data.get('clock_out')),
                'status': status,
                'note': str(request.data.get('note') or '').strip(),
            },
        )
        if not created:
            record.clock_in = _parse_time(request.data.get('clock_in')) or record.clock_in
            record.clock_out = _parse_time(request.data.get('clock_out')) or record.clock_out
            record.status = status
            if 'note' in request.data:
                record.note = str(request.data.get('note') or '').strip()
            record.save()

        record = WorklyRecord.objects.select_related('staff').get(pk=record.pk)
        return ok(_serialize_workly(record), status_code=201 if created else 200)

    qs = _workly_queryset(company, request.query_params)
    total = qs.count()
    summary = _workly_summary(qs)

    export = request.query_params.get('export', '0') == '1'
    if export:
        return ok({
            'summary': summary,
            'rows': [_serialize_workly(record) for record in qs],
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
        'rows': [_serialize_workly(record) for record in qs[offset:offset + page_size]],
        'total': total,
        'page': page,
        'total_pages': total_pages,
    })


@api_view(['GET', 'PATCH', 'DELETE'])
def workly_detail(request, record_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    record = WorklyRecord.objects.filter(company=company, pk=record_id).select_related('staff').first()
    if record is None:
        return fail('Record not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_workly(record))

    if request.method == 'DELETE':
        record.delete()
        return ok({'deleted': True})

    status = request.data.get('status')
    if status is not None:
        if status not in VALID_WORKLY_STATUSES:
            return fail('Invalid status')
        record.status = status

    if 'clock_in' in request.data:
        record.clock_in = _parse_time(request.data.get('clock_in'))
    if 'clock_out' in request.data:
        record.clock_out = _parse_time(request.data.get('clock_out'))
    if 'note' in request.data:
        record.note = str(request.data.get('note') or '').strip()
    if 'work_date' in request.data and request.data.get('work_date'):
        record.work_date = request.data.get('work_date')

    record.save()
    record = WorklyRecord.objects.select_related('staff').get(pk=record.pk)
    return ok(_serialize_workly(record))


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
        if 'grade_pass_score' in request.data:
            company.grade_pass_score = max(0, int(request.data['grade_pass_score']))
        if 'grade_scale_max' in request.data:
            company.grade_scale_max = max(1, int(request.data['grade_scale_max']))
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
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')
    branch_id = request.query_params.get('branch_id')

    payments_qs = Payment.objects.filter(company=company)
    expenses_qs = Expense.objects.filter(company=company)
    withdrawals_qs = Withdrawal.objects.filter(company=company)

    if date_from:
        payments_qs = payments_qs.filter(
            Q(payment_date__gte=date_from) | Q(payment_date__isnull=True, created_at__date__gte=date_from)
        )
        expenses_qs = expenses_qs.filter(created_at__date__gte=date_from)
        withdrawals_qs = withdrawals_qs.filter(created_at__date__gte=date_from)
    if date_to:
        payments_qs = payments_qs.filter(
            Q(payment_date__lte=date_to) | Q(payment_date__isnull=True, created_at__date__lte=date_to)
        )
        expenses_qs = expenses_qs.filter(created_at__date__lte=date_to)
        withdrawals_qs = withdrawals_qs.filter(created_at__date__lte=date_to)

    if branch_id:
        try:
            b_id = int(branch_id)
            payments_qs = payments_qs.filter(student__branch_id=b_id)
        except (ValueError, TypeError):
            pass

    total_paid = payments_qs.filter(
        transaction_type=Payment.TransactionType.PAYMENT
    ).aggregate(total=Sum('amount'))['total'] or 0
    total_refunded = payments_qs.filter(
        transaction_type=Payment.TransactionType.REFUND
    ).aggregate(total=Sum('amount'))['total'] or 0
    total_revenue = max(0, total_paid - total_refunded)

    total_expenses = expenses_qs.aggregate(total=Sum('amount'))['total'] or 0
    total_withdrawals = withdrawals_qs.aggregate(total=Sum('amount'))['total'] or 0
    net_profit = total_revenue - total_expenses
    profit_margin = round((net_profit / total_revenue * 100), 1) if total_revenue > 0 else 0

    revenue_by_method = []
    for method_code, method_name in Payment.Method.choices:
        paid_m = payments_qs.filter(
            method=method_code, transaction_type=Payment.TransactionType.PAYMENT
        ).aggregate(total=Sum('amount'))['total'] or 0
        refunded_m = payments_qs.filter(
            method=method_code, transaction_type=Payment.TransactionType.REFUND
        ).aggregate(total=Sum('amount'))['total'] or 0
        amount = max(0, paid_m - refunded_m)
        revenue_by_method.append({
            'method': method_code,
            'label': method_name,
            'amount': amount,
            'percent': round((amount / total_revenue * 100), 1) if total_revenue > 0 else 0,
        })

    expense_by_category = []
    uncat_amount = expenses_qs.filter(category__isnull=True).aggregate(total=Sum('amount'))['total'] or 0
    if uncat_amount > 0:
        expense_by_category.append({
            'id': None,
            'name': 'Без категории',
            'amount': uncat_amount,
            'percent': round((uncat_amount / total_expenses * 100), 1) if total_expenses > 0 else 0,
        })
    for cat in ExpenseCategory.objects.filter(company=company):
        cat_amount = expenses_qs.filter(category=cat).aggregate(total=Sum('amount'))['total'] or 0
        if cat_amount > 0:
            expense_by_category.append({
                'id': cat.id,
                'name': cat.name,
                'amount': cat_amount,
                'percent': round((cat_amount / total_expenses * 100), 1) if total_expenses > 0 else 0,
            })
    expense_by_category.sort(key=lambda x: x['amount'], reverse=True)

    return ok({
        'summary': {
            'total_revenue': total_revenue,
            'total_expenses': total_expenses,
            'total_withdrawals': total_withdrawals,
            'net_profit': net_profit,
            'profit_margin': profit_margin,
            'date_from': date_from,
            'date_to': date_to,
        },
        'revenue_by_method': revenue_by_method,
        'expense_by_category': expense_by_category,
    })


def _paid_between(start_date, end_date) -> Q:
    """Payments whose payment date (what the cashier entered) falls in the period;
    old records without payment_date fall back to the day they were entered."""
    return (
        Q(payment_date__gte=start_date, payment_date__lte=end_date)
        | Q(payment_date__isnull=True, created_at__date__gte=start_date, created_at__date__lte=end_date)
    )


@api_view(['GET'])
def payroll_summary(request):
    import calendar
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    month_str = request.query_params.get('month') or timezone.localdate().strftime('%Y-%m')
    try:
        parts = month_str.strip().split('-')
        year, month = int(parts[0]), int(parts[1])
        num_days = calendar.monthrange(year, month)[1]
        start_date = date_cls(year, month, 1)
        end_date = date_cls(year, month, num_days)
    except (ValueError, IndexError):
        today = timezone.localdate()
        year, month = today.year, today.month
        num_days = calendar.monthrange(year, month)[1]
        start_date = date_cls(year, month, 1)
        end_date = date_cls(year, month, num_days)
        month_str = today.strftime('%Y-%m')

    teachers = scope_teachers(User.objects.filter(
        company=company,
        user_type=User.UserType.TEACHER,
        is_active=True,
    ), request.user).order_by('first_name', 'last_name')

    total_accrued = 0
    total_paid = 0
    items = []

    for t in teachers:
        t_name = t.display_name()
        groups = Group.objects.filter(company=company, teacher=t)
        group_names = [g.name for g in groups]

        # Lessons held in month
        lessons_count = TeacherAttendanceRecord.objects.filter(
            company=company,
            teacher=t,
            attend_date__gte=start_date,
            attend_date__lte=end_date,
            status__in=[TeacherAttendanceRecord.Status.PRESENT, TeacherAttendanceRecord.Status.LATE],
        ).count()
        if lessons_count == 0 and groups.exists():
            lessons_count = AttendanceRecord.objects.filter(
                company=company,
                group__in=groups,
                attend_date__gte=start_date,
                attend_date__lte=end_date,
            ).values('attend_date').distinct().count()

        # Active students across groups
        # Per-student rate: students who were in the groups during that month (history), not today's list
        students_count = students_in_groups_during(company, groups, start_date, end_date)

        # Payments received from these students in month:
        # 1. Snapshotted payments allocated to this teacher
        snap_payments = Payment.objects.filter(
            _paid_between(start_date, end_date),
            company=company,
            teacher=t,
            transaction_type=Payment.TransactionType.PAYMENT,
        ).aggregate(total=Sum('amount'))['total'] or 0

        # 2. Minus snapshotted refunds for this teacher
        snap_refunds = Payment.objects.filter(
            _paid_between(start_date, end_date),
            company=company,
            teacher=t,
            transaction_type=Payment.TransactionType.REFUND,
        ).aggregate(total=Sum('amount'))['total'] or 0

        # 3. Plus legacy payments with teacher IS NULL that belonged to this teacher's groups
        legacy_payments = Payment.objects.filter(
            _paid_between(start_date, end_date),
            company=company,
            teacher__isnull=True,
            student__group__in=groups,
            transaction_type=Payment.TransactionType.PAYMENT,
        ).aggregate(total=Sum('amount'))['total'] or 0

        group_payments = max(0, snap_payments - snap_refunds + legacy_payments)

        # D8: one precedence rule shared with payroll_pay
        setting = resolve_salary_setting(company, t, start_date, end_date)

        accrued = 0
        salary_type_label = 'Не настроена'
        rate_amount = 0
        if setting:
            rate_amount = setting.amount
            salary_type_label = setting.get_salary_type_display()
            if setting.salary_type == SalarySetting.SalaryType.FIXED:
                accrued = setting.amount
            elif setting.salary_type == SalarySetting.SalaryType.PERCENT:
                accrued = int(group_payments * (setting.amount / 100.0))
            elif setting.salary_type == SalarySetting.SalaryType.PER_STUDENT:
                accrued = setting.amount * students_count

        # Paid in month (from PayrollPayment + legacy Expense)
        paid_from_payroll = PayrollPayment.objects.filter(
            company=company,
            teacher=t,
            payroll_period=month_str,
        ).aggregate(total=Sum('amount'))['total'] or 0

        paid_from_legacy_expense = Expense.objects.filter(
            company=company,
            payee=t_name,
            category__name__icontains='Зарплата',
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            payroll_payments__isnull=True,
        ).aggregate(total=Sum('amount'))['total'] or 0

        paid = paid_from_payroll + paid_from_legacy_expense
        balance = max(0, accrued - paid)
        total_accrued += accrued
        total_paid += paid

        status = 'paid' if accrued > 0 and balance <= 0 else ('partial' if paid > 0 else ('unpaid' if accrued > 0 else 'none'))

        items.append({
            'teacher_id': t.id,
            'teacher_name': t_name,
            'phone': t.phone,
            'groups_count': groups.count(),
            'groups_names': ', '.join(group_names) if group_names else '—',
            'lessons_count': lessons_count,
            'students_count': students_count,
            'group_payments': group_payments,
            'salary_type': setting.salary_type if setting else 'none',
            'salary_type_label': salary_type_label,
            'rate_amount': rate_amount,
            'accrued': accrued,
            'paid': paid,
            'balance': balance,
            'status': status,
        })

    return ok({
        'month': month_str,
        'summary': {
            'total_accrued': total_accrued,
            'total_paid': total_paid,
            'total_balance': max(0, total_accrued - total_paid),
            'teachers_count': len(teachers),
        },
        'rows': items,
    })


@api_view(['POST'])
def payroll_pay(request):
    import calendar
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    teacher_id = request.data.get('teacher_id')
    try:
        teacher = User.objects.get(pk=teacher_id, company=company)
    except (User.DoesNotExist, TypeError, ValueError):
        return fail('Teacher not found', status_code=404)

    try:
        amount = int(request.data.get('amount') or 0)
        if amount <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return fail('Valid positive amount is required', status_code=400)

    method = str(request.data.get('method') or 'cash').strip().lower()
    month = str(request.data.get('month') or timezone.localdate().strftime('%Y-%m')).strip()
    comment = str(request.data.get('comment') or f'Зарплата за {month}: {teacher.display_name()}').strip()

    # Calculate accrued and paid for overpayment validation
    try:
        parts = month.split('-')
        year, m_num = int(parts[0]), int(parts[1])
        num_days = calendar.monthrange(year, m_num)[1]
        start_date = date_cls(year, m_num, 1)
        end_date = date_cls(year, m_num, num_days)
    except Exception:
        today = timezone.localdate()
        year, m_num = today.year, today.month
        num_days = calendar.monthrange(year, m_num)[1]
        start_date = date_cls(year, m_num, 1)
        end_date = date_cls(year, m_num, num_days)

    t_groups = Group.objects.filter(company=company, teacher=teacher)
    students_count = students_in_groups_during(company, t_groups, start_date, end_date)

    snap_payments = Payment.objects.filter(
        _paid_between(start_date, end_date),
        company=company,
        teacher=teacher,
        transaction_type=Payment.TransactionType.PAYMENT,
    ).aggregate(total=Sum('amount'))['total'] or 0

    snap_refunds = Payment.objects.filter(
        _paid_between(start_date, end_date),
        company=company,
        teacher=teacher,
        transaction_type=Payment.TransactionType.REFUND,
    ).aggregate(total=Sum('amount'))['total'] or 0

    legacy_payments = Payment.objects.filter(
        _paid_between(start_date, end_date),
        company=company,
        teacher__isnull=True,
        student__group__in=t_groups,
        transaction_type=Payment.TransactionType.PAYMENT,
    ).aggregate(total=Sum('amount'))['total'] or 0

    g_payments = max(0, snap_payments - snap_refunds + legacy_payments)

    # D8: same precedence rule as payroll_summary
    setting = resolve_salary_setting(company, teacher, start_date, end_date)

    accrued = 0
    if setting:
        if setting.salary_type == SalarySetting.SalaryType.FIXED:
            accrued = setting.amount
        elif setting.salary_type == SalarySetting.SalaryType.PERCENT:
            accrued = int(g_payments * (setting.amount / 100.0))
        elif setting.salary_type == SalarySetting.SalaryType.PER_STUDENT:
            accrued = setting.amount * students_count

    already_paid = (PayrollPayment.objects.filter(
        company=company, teacher=teacher, payroll_period=month
    ).aggregate(total=Sum('amount'))['total'] or 0) + (Expense.objects.filter(
        company=company, payee=teacher.display_name(), category__name__icontains='Зарплата',
        created_at__date__gte=start_date, created_at__date__lte=end_date,
        payroll_payments__isnull=True,
    ).aggregate(total=Sum('amount'))['total'] or 0)

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

    salary_cat = next(
        (c for c in ExpenseCategory.objects.filter(company=company) if c.name.strip().casefold() == 'зарплата'),
        None,
    ) or ExpenseCategory.objects.create(company=company, name='Зарплата')

    with transaction.atomic():
        expense = Expense.objects.create(
            company=company,
            category=salary_cat,
            description=comment,
            payee=teacher.display_name(),
            method=method if method in {c[0] for c in Expense.Method.choices} else Expense.Method.CASH,
            amount=amount,
            created_by=request.user,
        )

        payroll_payment = PayrollPayment.objects.create(
            company=company,
            teacher=teacher,
            payroll_period=month,
            amount=amount,
            method=expense.method,
            comment=comment,
            expense=expense,
            created_by=request.user,
        )

        if (already_paid + amount > accrued):
            log_audit(
                company=company,
                actor=request.user,
                entity_type='payroll',
                entity_id=payroll_payment.id,
                action='force_overpayment',
                new_values={
                    'teacher_id': teacher.id,
                    'period': month,
                    'amount': amount,
                    'accrued': accrued,
                    'already_paid': already_paid,
                    'overpayment_amount': (already_paid + amount - accrued),
                },
                reason=comment or 'Forced payroll payout exceeding accrued balance',
            )
        else:
            log_audit(
                company=company,
                actor=request.user,
                entity_type='payroll',
                entity_id=payroll_payment.id,
                action='payout',
                new_values={
                    'teacher_id': teacher.id,
                    'period': month,
                    'amount': amount,
                },
                reason=comment,
            )


    return ok({
        'id': payroll_payment.id,
        'expense_id': expense.id,
        'teacher_id': teacher.id,
        'teacher_name': teacher.display_name(),
        'amount': amount,
        'method': expense.method,
        'comment': expense.description,
        'payroll_period': month,
        'date': expense.created_at.date().isoformat(),
    }, status_code=201)


