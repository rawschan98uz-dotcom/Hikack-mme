from datetime import date as date_cls, datetime, time

from django.db.models import Count, Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from accounts.models import TeacherBranch, User
from api.responses import fail, ok
from crm.models import AttendanceRecord, Group, Lead, Student
from operations.models import TeacherAttendanceRecord, WorklyRecord
from org.models import Branch
from finance.models import Expense, ExpenseCategory, Payment, SalarySetting, Withdrawal
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


def _serialize_teacher(user: User) -> dict:
    branches = [
        {'id': link.branch_id, 'name': link.branch.name}
        for link in user.teacher_branches.select_related('branch')
    ]
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
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
def teacher_detail_view(request, teacher_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', 404)

    try:
        teacher = _get_teacher(company, teacher_id)
    except User.DoesNotExist:
        return fail('Teacher not found', 404)

    if request.method == 'GET':
        payload = _serialize_teacher(teacher)
        payload['groups'] = _teacher_groups(teacher)
        return ok(payload)

    if request.method == 'DELETE':
        Group.objects.filter(teacher=teacher).update(teacher=None)
        teacher.delete()
        return ok({'deleted': True})

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
        phone = ''.join(ch for ch in str(phone) if ch.isdigit())
        if not phone:
            return fail('Valid phone is required')
        if User.objects.filter(phone=phone).exclude(pk=teacher.pk).exists():
            return fail('Phone already exists')
        teacher.phone = phone

    if honorific is not None:
        teacher.honorific = str(honorific).strip() or 'Mr'

    if job_title is not None:
        teacher.job_title = str(job_title).strip()

    if password:
        teacher.set_password(str(password))

    teacher.save()

    if branch_ids is not None:
        valid_branch_ids = list(
            Branch.objects.filter(company=company, id__in=branch_ids).values_list('id', flat=True),
        )
        if not valid_branch_ids:
            return fail('Select at least one branch')
        TeacherBranch.objects.filter(teacher=teacher).delete()
        for branch_id in valid_branch_ids:
            TeacherBranch.objects.create(teacher=teacher, branch_id=branch_id)

    return ok(_serialize_teacher(teacher))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_list(request):
    company = _company(request)
    if company is None:
        return ok([])

    user_type = request.query_params.get('user_type')
    qs = User.objects.filter(company=company)
    if user_type:
        qs = qs.filter(user_type=user_type)

    if user_type == 'teacher':
        data = [_serialize_teacher(u) for u in qs.order_by('id')]
        return ok(data)

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
    }


def _get_staff(company: Company, staff_id: int) -> User:
    return User.objects.get(
        pk=staff_id,
        company=company,
        user_type=User.UserType.STAFF,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def staff_create_view(request):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    first_name = (request.data.get('first_name') or request.data.get('name') or '').strip()
    if ' ' in first_name and not request.data.get('first_name'):
        parts = first_name.split(' ', 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ''
    else:
        last_name = (request.data.get('last_name') or '').strip()

    phone = ''.join(ch for ch in str(request.data.get('phone') or '') if ch.isdigit())
    password = request.data.get('password') or 'demo1234'
    job_title = (request.data.get('job_title') or '').strip()

    if not first_name or not phone:
        return fail('First name and phone are required')

    if User.objects.filter(phone=phone).exists():
        return fail('Phone already exists')

    user = User.objects.create_user(
        phone=phone,
        password=password,
        first_name=first_name,
        last_name=last_name,
        company=company,
        user_type=User.UserType.STAFF,
        job_title=job_title,
    )
    return ok(_serialize_staff(user), status_code=201)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def staff_detail_view(request, staff_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        staff = _get_staff(company, staff_id)
    except User.DoesNotExist:
        return fail('Staff not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_staff(staff))

    if request.method == 'DELETE':
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
        phone = ''.join(ch for ch in str(phone) if ch.isdigit())
        if not phone:
            return fail('Valid phone is required')
        if User.objects.filter(phone=phone).exclude(pk=staff.pk).exists():
            return fail('Phone already exists')
        staff.phone = phone

    password = request.data.get('password')
    if password:
        staff.set_password(str(password))

    staff.save()
    return ok(_serialize_staff(staff))


def teacher_create(request, company: Company):
    first_name = (request.data.get('first_name') or '').strip()
    last_name = (request.data.get('last_name') or '').strip()
    phone = ''.join(ch for ch in str(request.data.get('phone') or '') if ch.isdigit())
    password = request.data.get('password')
    honorific = (request.data.get('honorific') or 'Mr').strip()
    job_title = (request.data.get('job_title') or '').strip()
    branch_ids = request.data.get('branches') or []

    if not first_name or not phone or not password:
        return fail('First name, phone and password are required')

    if User.objects.filter(phone=phone).exists():
        return fail('Phone already exists')

    valid_branch_ids = list(
        Branch.objects.filter(company=company, id__in=branch_ids).values_list('id', flat=True),
    )
    if not valid_branch_ids:
        default_branch = Branch.objects.filter(company=company).order_by('id').first()
        if default_branch:
            valid_branch_ids = [default_branch.id]

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

    return ok(_serialize_teacher(user), status_code=201)


def _finance_date_filter(qs, params, field='created_at'):
    date_from = params.get('date_from')
    if date_from:
        qs = qs.filter(**{f'{field}__date__gte': date_from})
    date_to = params.get('date_to')
    if date_to:
        qs = qs.filter(**{f'{field}__date__lte': date_to})
    return qs


def _serialize_payment(payment: Payment) -> dict:
    return {
        'id': payment.id,
        'date': payment.created_at.strftime('%Y-%m-%d'),
        'name': payment.student_name,
        'student_name': payment.student_name,
        'sum': payment.amount,
        'method': payment.method,
        'method_pay': payment.get_method_display(),
        'teacher': payment.teacher_name or '—',
        'teacher_name': payment.teacher_name,
        'comment': payment.comment,
        'creator': _creator_name(payment.created_by),
        'created_at': payment.created_at.isoformat(),
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def replenishments(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        student_name = str(request.data.get('student_name') or request.data.get('name') or '').strip()
        if not student_name:
            return fail('Student name is required')
        try:
            amount = int(request.data.get('amount') or request.data.get('sum'))
        except (TypeError, ValueError):
            return fail('Valid amount is required')
        method = str(request.data.get('method') or Payment.Method.CASH).strip().lower()
        if method not in {choice[0] for choice in Payment.Method.choices}:
            return fail('Invalid payment method')

        payment = Payment.objects.create(
            company=company,
            student_name=student_name,
            amount=amount,
            method=method,
            teacher_name=str(request.data.get('teacher_name') or request.data.get('teacher') or '').strip(),
            comment=str(request.data.get('comment') or '').strip(),
            created_by=request.user,
        )
        return ok(_serialize_payment(payment), status_code=201)

    qs = Payment.objects.filter(company=company).select_related('created_by').order_by('-created_at')
    qs = _finance_date_filter(qs, request.query_params)
    method = request.query_params.get('method')
    if method:
        qs = qs.filter(method=method)
    query = (request.query_params.get('q') or '').strip()
    if query:
        qs = qs.filter(Q(student_name__icontains=query) | Q(comment__icontains=query))

    return ok([_serialize_payment(payment) for payment in qs[:200]])


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def payment_detail(request, payment_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        payment = Payment.objects.select_related('created_by').get(pk=payment_id, company=company)
    except Payment.DoesNotExist:
        return fail('Payment not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_payment(payment))

    if request.method == 'DELETE':
        payment.delete()
        return ok({'deleted': True})

    if 'student_name' in request.data or 'name' in request.data:
        student_name = str(request.data.get('student_name') or request.data.get('name') or '').strip()
        if not student_name:
            return fail('Student name is required')
        payment.student_name = student_name
    if 'amount' in request.data or 'sum' in request.data:
        try:
            payment.amount = int(request.data.get('amount') or request.data.get('sum'))
        except (TypeError, ValueError):
            return fail('Valid amount is required')
    if 'method' in request.data:
        method = str(request.data.get('method')).strip().lower()
        if method not in {choice[0] for choice in Payment.Method.choices}:
            return fail('Invalid payment method')
        payment.method = method
    if 'teacher_name' in request.data or 'teacher' in request.data:
        payment.teacher_name = str(request.data.get('teacher_name') or request.data.get('teacher') or '').strip()
    if 'comment' in request.data:
        payment.comment = str(request.data.get('comment') or '').strip()

    payment.save()
    payment.refresh_from_db()
    return ok(_serialize_payment(payment))


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
@permission_classes([IsAuthenticated])
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
        except (TypeError, ValueError):
            return fail('Valid amount is required')

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
@permission_classes([IsAuthenticated])
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
            withdrawal.amount = int(request.data.get('amount') or request.data.get('sum'))
        except (TypeError, ValueError):
            return fail('Valid amount is required')
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
@permission_classes([IsAuthenticated])
def expense_list(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        try:
            amount = int(request.data.get('amount') or request.data.get('sum'))
        except (TypeError, ValueError):
            return fail('Valid amount is required')
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
@permission_classes([IsAuthenticated])
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
            expense.amount = int(request.data.get('amount') or request.data.get('sum'))
        except (TypeError, ValueError):
            return fail('Valid amount is required')
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def expense_types(request):
    company = _company(request)
    if company is None:
        return ok([])

    data = [{'id': c.id, 'name': c.name} for c in ExpenseCategory.objects.filter(company=company)]
    return ok(data)


def _serialize_salary(setting: SalarySetting) -> dict:
    return {
        'id': setting.id,
        'calc_setting': 'Fixed',
        'salary_type': setting.salary_type,
        'salary_type_label': setting.get_salary_type_display(),
        'amount': setting.amount,
        'teacher_name': setting.teacher_name,
        'teacher': setting.teacher_name,
        'course_name': setting.course_name,
        'course': setting.course_name or '—',
        'group_name': setting.group_name,
        'group': setting.group_name or '—',
        'student': '—',
        'created_by': _creator_name(setting.created_by),
        'updated_by': _creator_name(setting.updated_by),
        'created_at': setting.created_at.isoformat(),
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def salary_settings(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        teacher_name = str(request.data.get('teacher_name') or request.data.get('teacher') or '').strip()
        salary_type = str(request.data.get('salary_type') or SalarySetting.SalaryType.FIXED).strip().lower()
        if salary_type not in {choice[0] for choice in SalarySetting.SalaryType.choices}:
            return fail('Invalid salary type')
        try:
            amount = int(request.data.get('amount') or 0)
        except (TypeError, ValueError):
            return fail('Valid amount is required')

        setting = SalarySetting.objects.create(
            company=company,
            teacher_name=teacher_name or '—',
            salary_type=salary_type,
            amount=amount,
            course_name=str(request.data.get('course_name') or request.data.get('course') or '').strip(),
            group_name=str(request.data.get('group_name') or request.data.get('group') or '').strip(),
            created_by=request.user,
            updated_by=request.user,
        )
        setting = SalarySetting.objects.select_related('created_by', 'updated_by').get(pk=setting.pk)
        return ok(_serialize_salary(setting), status_code=201)

    qs = SalarySetting.objects.filter(company=company).select_related('created_by', 'updated_by')
    query = (request.query_params.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(teacher_name__icontains=query)
            | Q(course_name__icontains=query)
            | Q(group_name__icontains=query),
        )

    return ok([_serialize_salary(s) for s in qs[:200]])


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def salary_setting_detail(request, setting_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        setting = SalarySetting.objects.select_related('created_by', 'updated_by').get(
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

    if 'teacher_name' in request.data or 'teacher' in request.data:
        setting.teacher_name = str(request.data.get('teacher_name') or request.data.get('teacher') or '').strip() or '—'
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
    if 'course_name' in request.data or 'course' in request.data:
        setting.course_name = str(request.data.get('course_name') or request.data.get('course') or '').strip()
    if 'group_name' in request.data or 'group' in request.data:
        setting.group_name = str(request.data.get('group_name') or request.data.get('group') or '').strip()

    setting.updated_by = request.user
    setting.save()
    setting = SalarySetting.objects.select_related('created_by', 'updated_by').get(pk=setting.pk)
    return ok(_serialize_salary(setting))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_conversion(request):
    company = _company(request)
    if company is None:
        return ok({'pipeline': {}, 'rows': []})

    leads = Lead.objects.filter(company=company, is_active=True).order_by('-created_at')
    params = request.query_params

    date_from = params.get('date_from')
    if date_from:
        leads = leads.filter(created_at__date__gte=date_from)

    date_to = params.get('date_to')
    if date_to:
        leads = leads.filter(created_at__date__lte=date_to)

    query = (params.get('q') or '').strip()
    if query:
        leads = leads.filter(Q(full_name__icontains=query) | Q(phone__icontains=query))

    stage_order = [choice[0] for choice in Lead.Stage.choices]
    stages = {stage: leads.filter(stage=stage).count() for stage in stage_order}
    rows = []
    for lead in leads[:200]:
        stage_idx = stage_order.index(lead.stage) if lead.stage in stage_order else -1
        row = {
            'id': lead.id,
            'full_name': lead.full_name,
            'phone': lead.phone,
            'stage': lead.stage,
            'stage_label': lead.get_stage_display(),
            'created_at': lead.created_at.date().isoformat(),
        }
        for idx, stage in enumerate(stage_order):
            row[stage] = idx <= stage_idx
        rows.append(row)
    return ok({'pipeline': stages, 'rows': rows})


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
        'created_at': record.created_at.isoformat(),
    }


def _attendance_queryset(company, params):
    qs = AttendanceRecord.objects.filter(company=company).select_related(
        'student',
        'group',
        'group__branch',
    ).order_by('-attend_date', 'student__first_name')

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
@permission_classes([IsAuthenticated])
def report_attendance(request):
    company = _company(request)
    if company is None:
        return ok({'summary': {'present': 0, 'absent': 0, 'late': 0, 'total': 0}, 'rows': []})

    if request.method == 'POST':
        try:
            student_id = int(request.data.get('student_id'))
            group_id = int(request.data.get('group_id'))
            status = int(request.data.get('status', AttendanceRecord.Status.PRESENT))
        except (TypeError, ValueError):
            return fail('Student, group and status are required')

        if status not in VALID_ATTENDANCE_STATUSES:
            return fail('Invalid status')

        attend_date_raw = request.data.get('date') or request.data.get('attend_date')
        if not attend_date_raw:
            return fail('Date is required')
        try:
            attend_date = date_cls.fromisoformat(str(attend_date_raw)[:10])
        except ValueError:
            return fail('Invalid date')

        try:
            student = Student.objects.get(pk=student_id, company=company)
        except Student.DoesNotExist:
            return fail('Student not found')

        try:
            group = Group.objects.select_related('branch').get(pk=group_id, company=company)
        except Group.DoesNotExist:
            return fail('Group not found')

        record, _created = AttendanceRecord.objects.update_or_create(
            company=company,
            student=student,
            group=group,
            attend_date=attend_date,
            defaults={'status': status},
        )
        record = AttendanceRecord.objects.select_related(
            'student',
            'group',
            'group__branch',
        ).get(pk=record.pk)
        return ok(_serialize_attendance(record), status_code=201)

    qs = _attendance_queryset(company, request.query_params)
    summary = _attendance_summary(qs)
    rows = [_serialize_attendance(record) for record in qs[:200]]
    return ok({'summary': summary, 'rows': rows})


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
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

    if request.method == 'GET':
        return ok(_serialize_attendance(record))

    if request.method == 'DELETE':
        record.delete()
        return ok({'deleted': True})

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

    student_id = request.data.get('student_id')
    if student_id is not None:
        try:
            record.student = Student.objects.get(pk=int(student_id), company=company)
        except (Student.DoesNotExist, TypeError, ValueError):
            return fail('Student not found')

    record.save()
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


def _teacher_attendance_queryset(company, params):
    qs = TeacherAttendanceRecord.objects.filter(company=company).select_related(
        'teacher',
        'group',
        'group__branch',
    ).order_by('-attend_date', 'teacher__first_name')

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
@permission_classes([IsAuthenticated])
def report_teacher_attendance(request):
    company = _company(request)
    if company is None:
        return ok({'summary': {'present': 0, 'absent': 0, 'late': 0, 'total': 0}, 'rows': []})

    if request.method == 'POST':
        try:
            teacher_id = int(request.data.get('teacher_id'))
            group_id = int(request.data.get('group_id'))
            status = int(request.data.get('status', TeacherAttendanceRecord.Status.PRESENT))
        except (TypeError, ValueError):
            return fail('Teacher, group and status are required')

        if status not in VALID_TEACHER_ATTENDANCE_STATUSES:
            return fail('Invalid status')

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

    qs = _teacher_attendance_queryset(company, request.query_params)
    summary = _teacher_attendance_summary(qs)
    rows = [_serialize_teacher_attendance(record) for record in qs[:200]]
    return ok({'summary': summary, 'rows': rows})


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
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

    if request.method == 'GET':
        return ok(_serialize_teacher_attendance(record))

    if request.method == 'DELETE':
        record.delete()
        return ok({'deleted': True})

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

    record.save()
    record = TeacherAttendanceRecord.objects.select_related(
        'teacher',
        'group',
        'group__branch',
    ).get(pk=record.pk)
    return ok(_serialize_teacher_attendance(record))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_leads(request):
    company = _company(request)
    if company is None:
        return ok({'total': 0, 'active': 0, 'by_stage': {}, 'rows': []})

    leads = Lead.objects.filter(company=company).order_by('-created_at')
    params = request.query_params

    if params.get('active') == '1':
        leads = leads.filter(is_active=True)

    stage = params.get('stage')
    if stage:
        leads = leads.filter(stage=stage)

    date_from = params.get('date_from')
    if date_from:
        leads = leads.filter(created_at__date__gte=date_from)

    date_to = params.get('date_to')
    if date_to:
        leads = leads.filter(created_at__date__lte=date_to)

    query = (params.get('q') or '').strip()
    if query:
        leads = leads.filter(Q(full_name__icontains=query) | Q(phone__icontains=query))

    by_stage = {stage: leads.filter(stage=stage).count() for stage, _ in Lead.Stage.choices}
    rows = [
        {
            'id': lead.id,
            'full_name': lead.full_name,
            'phone': lead.phone,
            'stage': lead.stage,
            'stage_label': lead.get_stage_display(),
            'is_active': lead.is_active,
            'created_at': lead.created_at.date().isoformat(),
        }
        for lead in leads[:200]
    ]
    return ok({
        'total': leads.count(),
        'active': leads.filter(is_active=True).count(),
        'by_stage': by_stage,
        'rows': rows,
    })


LEFT_STUDENT_STATUSES = {Student.Status.LEFT_TRIAL, Student.Status.LEFT_ACTIVE}


def _serialize_left_student(student: Student) -> dict:
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
        'balance': student.balance,
        'left_at': student.created_at.date().isoformat(),
    }


def _left_students_queryset(company, params):
    qs = Student.objects.filter(
        company=company,
        status__in=LEFT_STUDENT_STATUSES,
    ).select_related('branch', 'group').order_by('-created_at')

    status = params.get('status')
    if status:
        try:
            status_val = int(status)
            if status_val in LEFT_STUDENT_STATUSES:
                qs = qs.filter(status=status_val)
        except ValueError:
            if status == 'left_active_group':
                qs = qs.filter(status=Student.Status.LEFT_ACTIVE)
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
        qs = qs.filter(created_at__date__gte=date_from)

    date_to = params.get('date_to')
    if date_to:
        qs = qs.filter(created_at__lte=date_to)

    query = (params.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(phone__icontains=query),
        )

    return qs


def _left_students_summary(qs) -> dict:
    return {
        'left_active': qs.filter(status=Student.Status.LEFT_ACTIVE).count(),
        'left_trial': qs.filter(status=Student.Status.LEFT_TRIAL).count(),
        'total': qs.count(),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_left_students(request):
    company = _company(request)
    if company is None:
        return ok({'summary': {'left_active': 0, 'left_trial': 0, 'total': 0}, 'rows': []})

    qs = _left_students_queryset(company, request.query_params)
    return ok({
        'summary': _left_students_summary(qs),
        'rows': [_serialize_left_student(student) for student in qs[:200]],
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
@permission_classes([IsAuthenticated])
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
    return ok({
        'summary': _workly_summary(qs),
        'rows': [_serialize_workly(record) for record in qs[:200]],
    })


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
def company_settings(request):
    company = _company(request)
    if company is None:
        return fail('No company', 400)

    if request.method == 'POST':
        for field in ('name', 'phone', 'address', 'timezone', 'currency'):
            if field in request.data:
                setattr(company, field, request.data[field])
        if 'sms_enabled' in request.data:
            company.sms_enabled = bool(request.data['sms_enabled'])
        if 'sms_advance_text' in request.data:
            company.sms_advance_text = str(request.data['sms_advance_text'] or '').strip()
        if 'balance_mode' in request.data:
            company.balance_mode = int(request.data['balance_mode'])
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
        company.save()

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
        'balance_mode': company.balance_mode,
        'sms_enabled': company.sms_enabled,
        'sms_advance_text': company.sms_advance_text,
        'voip_enabled': company.voip_enabled,
        'voip_gateway': company.voip_gateway,
        'voip_caller_id': company.voip_caller_id,
        'grade_pass_score': company.grade_pass_score,
        'grade_scale_max': company.grade_scale_max,
        'tabs': [
            'General settings', 'Sign in', 'Lead form', 'Payment methods',
            'Communication', 'Integrations', 'Exams', 'Invoice',
            'Accrual and payment', 'Landing page',
        ],
    })
