"""CSV import endpoints for teachers and staff."""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from accounts.models import TeacherBranch, User
from api.csv_utils import normalize_phone, parse_csv_upload
from api.responses import fail, ok
from api.v1.views_extended import _company, teacher_create
from crm.models import Group, Student
from org.models import Branch

DEFAULT_IMPORT_PASSWORD = '946263200'
VALID_STAFF_ROLES = {choice[0] for choice in User.StaffRole.choices if choice[0] != User.StaffRole.CEO}


def _resolve_branch_ids(company, raw: str) -> list[int]:
    if not raw:
        default = Branch.objects.filter(company=company).order_by('id').first()
        return [default.id] if default else []

    ids: list[int] = []
    for part in raw.replace('|', ',').split(','):
        token = part.strip()
        if not token:
            continue
        if token.isdigit():
            branch = Branch.objects.filter(company=company, pk=int(token)).first()
            if branch:
                ids.append(branch.id)
        else:
            branch = Branch.objects.filter(company=company, name__iexact=token).first()
            if branch:
                ids.append(branch.id)
    return list(dict.fromkeys(ids))


def _import_result(created: int, skipped: int, errors: list[dict]) -> dict:
    return {
        'created': created,
        'skipped': skipped,
        'errors': errors,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def teacher_import(request):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    dry_run = (
        request.data.get('dry_run') in ('true', '1', 1, True)
        or request.query_params.get('dry_run') in ('true', '1', 1, True)
    )

    rows, parse_error = parse_csv_upload(request.FILES.get('file'))
    if parse_error:
        return fail(parse_error)

    created = 0
    skipped = 0
    errors: list[dict] = []
    preview_rows: list[dict] = []
    valid_payloads: list[dict] = []

    for row in rows:
        row_num = int(row.get('_row', 0))
        first_name = row.get('first_name') or row.get('name', '').split(' ')[0]
        last_name = row.get('last_name', '')
        if not last_name and row.get('name') and ' ' in row['name']:
            parts = row['name'].split(' ', 1)
            first_name = first_name or parts[0]
            last_name = parts[1] if len(parts) > 1 else ''

        phone = normalize_phone(row.get('phone', ''))
        password = row.get('password') or DEFAULT_IMPORT_PASSWORD
        honorific = row.get('honorific') or 'Mr'
        job_title = row.get('job_title', '')
        branch_raw = row.get('branch_ids') or row.get('branches') or row.get('branch', '')

        if not first_name or not phone:
            skipped += 1
            msg = 'Имя и номер телефона обязательны'
            errors.append({'row': row_num, 'message': msg})
            preview_rows.append({
                'row': row_num,
                'first_name': first_name,
                'last_name': last_name,
                'full_name': f"{first_name} {last_name}".strip(),
                'phone': phone,
                'formatted_phone': phone or '—',
                'branch_name': '—',
                'group_name': '—',
                'status_label': 'Преподаватель',
                'balance': 0,
                'school': job_title or '—',
                'is_valid': False,
                'message': msg,
            })
            continue

        if User.objects.filter(phone=phone).exists():
            skipped += 1
            msg = f'Телефон {phone} уже зарегистрирован'
            errors.append({'row': row_num, 'message': msg})
            preview_rows.append({
                'row': row_num,
                'first_name': first_name,
                'last_name': last_name,
                'full_name': f"{first_name} {last_name}".strip(),
                'phone': phone,
                'formatted_phone': phone,
                'branch_name': '—',
                'group_name': '—',
                'status_label': 'Преподаватель',
                'balance': 0,
                'school': job_title or '—',
                'is_valid': False,
                'message': msg,
            })
            continue

        branch_ids = _resolve_branch_ids(company, branch_raw)
        if not branch_ids:
            skipped += 1
            msg = 'Филиал не найден'
            errors.append({'row': row_num, 'message': msg})
            preview_rows.append({
                'row': row_num,
                'first_name': first_name,
                'last_name': last_name,
                'full_name': f"{first_name} {last_name}".strip(),
                'phone': phone,
                'formatted_phone': phone,
                'branch_name': '—',
                'group_name': '—',
                'status_label': 'Преподаватель',
                'balance': 0,
                'school': job_title or '—',
                'is_valid': False,
                'message': msg,
            })
            continue

        if len(phone) == 9 and phone.isdigit():
            formatted_phone = f"+998 ({phone[:2]}) {phone[2:5]}-{phone[5:7]}-{phone[7:9]}"
        elif len(phone) == 12 and phone.startswith('998') and phone.isdigit():
            formatted_phone = f"+998 ({phone[3:5]}) {phone[5:8]}-{phone[8:10]}-{phone[10:12]}"
        else:
            formatted_phone = phone

        preview_rows.append({
            'row': row_num,
            'first_name': first_name,
            'last_name': last_name,
            'full_name': f"{first_name} {last_name}".strip(),
            'phone': phone,
            'formatted_phone': formatted_phone,
            'branch_name': 'Основной',
            'group_name': '—',
            'status_label': 'Преподаватель',
            'balance': 0,
            'school': job_title or '—',
            'is_valid': True,
            'message': '',
        })

        valid_payloads.append({
            'first_name': first_name,
            'last_name': last_name,
            'phone': phone,
            'password': password,
            'honorific': honorific,
            'job_title': job_title,
            'branches': branch_ids,
            'row_num': row_num,
        })

    if dry_run:
        return ok({
            'dry_run': True,
            'total': len(preview_rows),
            'valid': len([r for r in preview_rows if r['is_valid']]),
            'skipped': len([r for r in preview_rows if not r['is_valid']]),
            'errors': errors,
            'rows': preview_rows,
        })

    for item in valid_payloads:
        row_n = item.pop('row_num')
        class _Req:
            data = item

        response = teacher_create(_Req(), company)
        if response.status_code >= 400:
            skipped += 1
            body = response.data if hasattr(response, 'data') else {}
            message = body.get('message') if isinstance(body, dict) else 'Could not create teacher'
            errors.append({'row': row_n, 'message': str(message)})
            continue

        created += 1

    return ok(_import_result(created, skipped, errors))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def staff_import(request):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    rows, parse_error = parse_csv_upload(request.FILES.get('file'))
    if parse_error:
        return fail(parse_error)

    created = 0
    skipped = 0
    errors: list[dict] = []

    for row in rows:
        row_num = int(row.get('_row', 0))
        first_name = row.get('first_name') or row.get('name', '').split(' ')[0]
        last_name = row.get('last_name', '')
        if not last_name and row.get('name') and ' ' in row['name']:
            parts = row['name'].split(' ', 1)
            first_name = first_name or parts[0]
            last_name = parts[1] if len(parts) > 1 else ''

        phone = normalize_phone(row.get('phone', ''))
        password = row.get('password') or DEFAULT_IMPORT_PASSWORD
        job_title = row.get('job_title', '')
        staff_role = (row.get('staff_role') or row.get('role') or User.StaffRole.ADMINISTRATOR).lower()

        if not first_name or not phone:
            skipped += 1
            errors.append({'row': row_num, 'message': 'First name and phone are required'})
            continue

        if staff_role not in VALID_STAFF_ROLES:
            skipped += 1
            errors.append({
                'row': row_num,
                'message': f'Invalid staff_role: {staff_role}',
            })
            continue

        if User.objects.filter(phone=phone).exists():
            skipped += 1
            errors.append({'row': row_num, 'message': f'Phone {phone} already exists'})
            continue

        user = User.objects.create_user(
            phone=phone,
            password=password,
            first_name=first_name,
            last_name=last_name,
            company=company,
            user_type=User.UserType.STAFF,
            staff_role=staff_role,
            job_title=job_title,
        )
        created += 1

    return ok(_import_result(created, skipped, errors))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def student_import(request):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    dry_run = (
        request.data.get('dry_run') in ('true', '1', 1, True)
        or request.query_params.get('dry_run') in ('true', '1', 1, True)
    )

    rows, parse_error = parse_csv_upload(request.FILES.get('file'))
    if parse_error:
        return fail(parse_error)

    created = 0
    skipped = 0
    errors: list[dict] = []
    preview_rows: list[dict] = []
    valid_students_to_create: list[dict] = []

    default_branch = Branch.objects.filter(company=company).order_by('id').first()

    status_map = {
        'trial': Student.Status.TRIAL,
        'active': Student.Status.ACTIVE,
        'debtor': Student.Status.DEBTOR,
        'left_trial': Student.Status.LEFT_TRIAL,
        'left_active': Student.Status.LEFT_ACTIVE,
        'пробный': Student.Status.TRIAL,
        'активный': Student.Status.ACTIVE,
        'должник': Student.Status.DEBTOR,
        '1': Student.Status.TRIAL,
        '5': Student.Status.ACTIVE,
        '6': Student.Status.DEBTOR,
        '7': Student.Status.LEFT_TRIAL,
        '8': Student.Status.LEFT_ACTIVE,
    }

    status_label_map = {
        Student.Status.TRIAL: 'Пробный',
        Student.Status.ACTIVE: 'Активный',
        Student.Status.DEBTOR: 'Должник',
        Student.Status.LEFT_TRIAL: 'Ушел (пробный)',
        Student.Status.LEFT_ACTIVE: 'Ушел (активный)',
    }

    for row in rows:
        row_num = int(row.get('_row', 0))

        # Direct lookups first
        first_name = (
            row.get('first_name')
            or row.get('имя')
            or row.get('ism')
            or row.get('name', '').split(' ')[0]
            or row.get('фио', '').split(' ')[0]
            or row.get('ф_и_о', '').split(' ')[0]
            or row.get('fio', '').split(' ')[0]
            or row.get('студент', '').split(' ')[0]
            or row.get('ученик', '').split(' ')[0]
            or row.get('student', '').split(' ')[0]
            or row.get('учащийся', '').split(' ')[0]
            or row.get('полное_имя', '').split(' ')[0]
        )
        last_name = row.get('last_name') or row.get('фамилия') or row.get('familiya') or row.get('surname') or ''

        # Fuzzy search for name if not found directly
        if not first_name:
            for k, v in row.items():
                if k.startswith('_'):
                    continue
                if any(tag in k for tag in ('имя', 'фио', 'fio', 'name', 'студент', 'ученик', 'student', 'учащ')):
                    first_name = str(v).strip()
                    break

        if not last_name:
            for fio_key in ('name', 'фио', 'ф_и_о', 'fio', 'студент', 'ученик', 'student', 'учащийся', 'полное_имя'):
                full = str(row.get(fio_key) or '').strip()
                if ' ' in full:
                    parts = full.split(' ', 1)
                    first_name = parts[0]
                    last_name = parts[1]
                    break
            if not last_name and ' ' in first_name:
                parts = first_name.split(' ', 1)
                first_name = parts[0]
                last_name = parts[1]

        first_name = str(first_name or '').strip()
        last_name = str(last_name or '').strip()

        phone = normalize_phone(
            row.get('phone')
            or row.get('телефон')
            or row.get('номер')
            or row.get('номер_телефона')
            or row.get('тел')
            or row.get('контакты')
            or row.get('contact')
            or row.get('моб')
            or row.get('моб_тел')
            or row.get('telefon')
            or row.get('tel')
            or ''
        )

        # Fuzzy search for phone if not found directly
        if len(phone) < 9:
            for k, v in row.items():
                if k.startswith('_'):
                    continue
                if any(tag in k for tag in ('тел', 'phone', 'номер', 'contact', 'контакт', 'моб', 'gsm')):
                    cand = normalize_phone(str(v))
                    if len(cand) >= 9:
                        phone = cand
                        break

        # If still no phone, check all cell values for a 9-12 digit sequence
        if len(phone) < 9:
            for k, v in row.items():
                if k.startswith('_'):
                    continue
                cand = normalize_phone(str(v))
                if 9 <= len(cand) <= 13:
                    phone = cand
                    break

        full_check = f"{first_name} {last_name}".lower()
        if any(tag in full_check for tag in ('итого', 'всего', 'total', 'summary', 'jami')):
            continue

        if not first_name:
            skipped += 1
            msg = 'Не указано имя ученика'
            errors.append({'row': row_num, 'message': msg})
            preview_rows.append({
                'row': row_num,
                'first_name': '',
                'last_name': '',
                'full_name': '—',
                'phone': '',
                'formatted_phone': '—',
                'branch_name': '—',
                'group_name': '—',
                'status_label': '—',
                'balance': 0,
                'school': '',
                'parent_telegram': '',
                'is_valid': False,
                'message': msg,
            })
            continue

        if len(phone) < 9:
            skipped += 1
            msg = f'Не найден номер телефона для "{first_name}"'
            errors.append({'row': row_num, 'message': msg})
            preview_rows.append({
                'row': row_num,
                'first_name': first_name,
                'last_name': last_name,
                'full_name': f"{first_name} {last_name}".strip(),
                'phone': phone,
                'formatted_phone': phone or '—',
                'branch_name': '—',
                'group_name': '—',
                'status_label': '—',
                'balance': 0,
                'school': '',
                'parent_telegram': '',
                'is_valid': False,
                'message': msg,
            })
            continue

        branch_raw = (
            row.get('branch')
            or row.get('филиал')
            or row.get('filial')
            or row.get('branch_id')
            or ''
        )
        branch = None
        if branch_raw:
            token = str(branch_raw).strip()
            if token.isdigit():
                branch = Branch.objects.filter(company=company, pk=int(token)).first()
            else:
                branch = Branch.objects.filter(company=company, name__iexact=token).first()
        if not branch:
            branch = default_branch
        if not branch:
            skipped += 1
            msg = 'Филиал не найден'
            errors.append({'row': row_num, 'message': msg})
            preview_rows.append({
                'row': row_num,
                'first_name': first_name,
                'last_name': last_name,
                'full_name': f"{first_name} {last_name}".strip(),
                'phone': phone,
                'formatted_phone': phone,
                'branch_name': '—',
                'group_name': '—',
                'status_label': '—',
                'balance': 0,
                'school': '',
                'parent_telegram': '',
                'is_valid': False,
                'message': msg,
            })
            continue

        group_raw = (
            row.get('group')
            or row.get('группа')
            or row.get('guruh')
            or row.get('group_id')
            or ''
        )
        group = None
        if group_raw:
            token = str(group_raw).strip()
            if token.isdigit():
                group = Group.objects.filter(company=company, pk=int(token)).first()
            else:
                group = Group.objects.filter(company=company, name__iexact=token).first()

        status_raw = str(
            row.get('status')
            or row.get('статус')
            or row.get('holat')
            or ''
        ).lower().strip()
        status = status_map.get(status_raw, Student.Status.ACTIVE if status_raw in ('active', 'активный') else Student.Status.TRIAL)

        balance = 0
        balance_raw = row.get('balance') or row.get('баланс') or row.get('balans')
        if balance_raw is not None and str(balance_raw).strip():
            try:
                balance = int(float(str(balance_raw).replace(' ', '').replace(',', '')))
            except ValueError:
                balance = 0

        school = str(row.get('school') or row.get('школа') or row.get('maktab') or '').strip()
        telegram = str(row.get('telegram') or row.get('телеграм') or '').strip()
        parent_telegram = str(
            row.get('parent_telegram')
            or row.get('родитель_телеграм')
            or row.get('телеграм_родителя')
            or ''
        ).strip()
        paid_this_month = str(
            row.get('paid_this_month')
            or row.get('оплачено_в_этом_месяце')
            or row.get('оплачено')
            or ''
        ).lower().strip() in ('true', '1', 'yes', 'да', 'ha')

        if len(phone) == 9 and phone.isdigit():
            formatted_phone = f"+998 ({phone[:2]}) {phone[2:5]}-{phone[5:7]}-{phone[7:9]}"
        elif len(phone) == 12 and phone.startswith('998') and phone.isdigit():
            formatted_phone = f"+998 ({phone[3:5]}) {phone[5:8]}-{phone[8:10]}-{phone[10:12]}"
        else:
            formatted_phone = phone

        preview_rows.append({
            'row': row_num,
            'first_name': first_name,
            'last_name': last_name,
            'full_name': f"{first_name} {last_name}".strip(),
            'phone': phone,
            'formatted_phone': formatted_phone,
            'branch_name': branch.name if branch else 'Основной',
            'group_name': group.name if group else (str(group_raw) if group_raw else '—'),
            'status_label': status_label_map.get(status, 'Активный'),
            'balance': balance,
            'school': school or '—',
            'parent_telegram': parent_telegram or '—',
            'is_valid': True,
            'message': '',
        })

        valid_students_to_create.append({
            'company': company,
            'branch': branch,
            'group': group,
            'first_name': first_name,
            'last_name': last_name,
            'phone': phone,
            'status': status,
            'balance': balance,
            'school': school,
            'telegram': telegram,
            'parent_telegram': parent_telegram,
            'paid_this_month': paid_this_month,
        })

    if dry_run:
        return ok({
            'dry_run': True,
            'total': len(preview_rows),
            'valid': len([r for r in preview_rows if r['is_valid']]),
            'skipped': len([r for r in preview_rows if not r['is_valid']]),
            'errors': errors,
            'rows': preview_rows,
        })

    for item in valid_students_to_create:
        Student.objects.create(**item)
        created += 1

    return ok(_import_result(created, skipped, errors))

