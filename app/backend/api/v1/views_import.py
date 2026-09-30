"""CSV import endpoints for teachers and staff."""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from django.utils import timezone
from accounts.models import TeacherBranch, User
from api.csv_utils import normalize_phone, parse_csv_upload
from api.utils import capitalize_name
from api.utils import is_valid_phone, parse_date_safe
from api.responses import fail, ok
from api.v1.views_extended import _company, _generate_password, teacher_create
from crm.models import Group, Lead, Student
from api.scope import branches_for, filter_groups_queryset

VALID_STAFF_ROLES = {choice[0] for choice in User.StaffRole.choices if choice[0] != User.StaffRole.CEO}


def _resolve_branch_ids(company, raw: str, user=None) -> list[int]:
    if not raw:
        default = branches_for(user, company).order_by('id').first()
        return [default.id] if default else []

    ids: list[int] = []
    for part in raw.replace('|', ',').split(','):
        token = part.strip()
        if not token:
            continue
        if token.isdigit():
            branch = branches_for(user, company).filter(pk=int(token)).first()
            if branch:
                ids.append(branch.id)
        else:
            branch = branches_for(user, company).filter(name__iexact=token).first()
            if branch:
                ids.append(branch.id)
    return list(dict.fromkeys(ids))


def _import_result(created: int, skipped: int, errors: list[dict], credentials: list[dict] | None = None) -> dict:
    result = {
        'created': created,
        'skipped': skipped,
        'errors': errors,
    }
    if credentials is not None:
        # Auto-generated passwords, shown once so the CEO can hand them out
        result['credentials'] = credentials
    return result


@api_view(['POST'])
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
        password = row.get('password') or ''
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
                'school': job_title or '—',
                'is_valid': False,
                'message': msg,
            })
            continue

        branch_ids = _resolve_branch_ids(company, branch_raw, request.user)
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

    credentials: list[dict] = []
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
        generated = (response.data.get('data') or {}).get('generated_password') if isinstance(response.data, dict) else None
        if generated:
            credentials.append({'row': row_n, 'phone': item['phone'], 'password': generated})

    return ok(_import_result(created, skipped, errors, credentials))


@api_view(['POST'])
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
    credentials: list[dict] = []

    for row in rows:
        row_num = int(row.get('_row', 0))
        first_name = row.get('first_name') or row.get('name', '').split(' ')[0]
        last_name = row.get('last_name', '')
        if not last_name and row.get('name') and ' ' in row['name']:
            parts = row['name'].split(' ', 1)
            first_name = first_name or parts[0]
            last_name = parts[1] if len(parts) > 1 else ''

        phone = normalize_phone(row.get('phone', ''))
        password = row.get('password') or ''
        generated_password = not password
        if generated_password:
            password = _generate_password()
        job_title = row.get('job_title', '')
        staff_role = (row.get('staff_role') or row.get('role') or User.StaffRole.ADMINISTRATOR).lower()
        # Old role names in files made before 2026-09-28: one office role now
        if staff_role in ('limited_admin', 'cashier'):
            staff_role = User.StaffRole.ADMINISTRATOR

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

        # E3: a branch director must be bound to one branch
        director_branch = None
        if staff_role == User.StaffRole.BRANCH_DIRECTOR:
            branch_raw = str(row.get('branch') or row.get('филиал') or row.get('filial') or '').strip()
            branch_ids = _resolve_branch_ids(company, branch_raw, request.user) if branch_raw else []
            if not branch_ids:
                skipped += 1
                errors.append({'row': row_num, 'message': 'Для директора филиала укажите филиал (колонка branch)'})
                continue
            director_branch = branch_ids[0]

        user = User.objects.create_user(
            phone=phone,
            password=password,
            first_name=first_name,
            last_name=last_name,
            company=company,
            user_type=User.UserType.STAFF,
            staff_role=staff_role,
            job_title=job_title,
            branch_id=director_branch,
        )
        created += 1
        if generated_password:
            credentials.append({'row': row_num, 'phone': phone, 'password': password})

    return ok(_import_result(created, skipped, errors, credentials))


@api_view(['POST'])
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
    seen_in_file: set[tuple[str, str, str]] = set()
    from api.v1.views import _active_student_duplicate

    default_branch = branches_for(request.user, company).order_by('id').first()

    status_map = {
        'trial': Student.Status.STUDYING,
        'active': Student.Status.STUDYING,
        'debtor': Student.Status.STUDYING,
        'studying': Student.Status.STUDYING,
        'обучается': Student.Status.STUDYING,
        'пробный': Student.Status.STUDYING,
        'активный': Student.Status.STUDYING,
        'должник': Student.Status.STUDYING,
        "o'qiydi": Student.Status.STUDYING,
        '1': Student.Status.STUDYING,
        '5': Student.Status.STUDYING,
        '6': Student.Status.STUDYING,
        'frozen': Student.Status.FROZEN,
        'заморозка': Student.Status.FROZEN,
        'muzlatilgan': Student.Status.FROZEN,
        '2': Student.Status.FROZEN,
        'left_trial': Student.Status.LEFT_TRIAL,
        'ушел_пробный': Student.Status.LEFT_TRIAL,
        '7': Student.Status.LEFT_TRIAL,
        'left': Student.Status.LEFT,
        'left_active': Student.Status.LEFT,
        'ушел': Student.Status.LEFT,
        'отчислен': Student.Status.LEFT,
        'кетган': Student.Status.LEFT,
        '8': Student.Status.LEFT,
        'graduated': Student.Status.GRADUATED,
        'завершил': Student.Status.GRADUATED,
        'bitirgan': Student.Status.GRADUATED,
        '9': Student.Status.GRADUATED,
    }

    status_label_map = {
        Student.Status.STUDYING: 'Обучается',
        Student.Status.FROZEN: 'Заморозка',
        Student.Status.LEFT_TRIAL: 'Ушел (пробный)',
        Student.Status.LEFT: 'Отчислен / Ушел',
        Student.Status.GRADUATED: 'Завершил курс',
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

        first_name = capitalize_name(first_name)
        last_name = capitalize_name(last_name)

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
                'school': '',
                'parent_telegram': '',
                'is_valid': False,
                'message': msg,
            })
            continue

        if not is_valid_phone(phone):
            skipped += 1
            msg = f'Не найден или некорректный номер телефона для "{first_name}" (требуется 9 цифр)'
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
                'school': '',
                'parent_telegram': '',
                'is_valid': False,
                'message': msg,
            })
            continue

        # Same rule as adding a student by hand: an active student with the same name + phone
        # already exists (or appeared earlier in this file) -> skip, so loading a file twice
        # does not create twins. Students who left are not counted: a returning student can be loaded.
        file_key = (phone, first_name.casefold(), last_name.casefold())
        existing = _active_student_duplicate(company, phone, first_name, last_name)
        if existing or file_key in seen_in_file:
            skipped += 1
            msg = 'Уже есть в базе — пропущено' if existing else 'Повтор в этом файле — пропущено'
            errors.append({'row': row_num, 'message': f'{first_name} {last_name}'.strip() + f': {msg}'})
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
                'school': '',
                'parent_telegram': '',
                'is_valid': False,
                'message': msg,
            })
            continue
        seen_in_file.add(file_key)

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
                branch = branches_for(request.user, company).filter(pk=int(token)).first()
            else:
                branch = branches_for(request.user, company).filter(name__iexact=token).first()
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
                group = filter_groups_queryset(Group.objects.filter(company=company, pk=int(token)), request.user).first()
            else:
                group = filter_groups_queryset(Group.objects.filter(company=company, name__iexact=token), request.user).first()

        status_raw = str(
            row.get('status')
            or row.get('статус')
            or row.get('holat')
            or ''
        ).lower().strip()
        status = status_map.get(status_raw, Student.Status.STUDYING)

        trial_date_raw = (
            row.get('trial_date')
            or row.get('start_date')
            or row.get('дата_начала')
            or row.get('дата_пробного')
            or row.get('дата')
            or row.get('date')
            or row.get('sana')
            or row.get('boshlanish_sana')
            or ''
        )
        trial_date = parse_date_safe(str(trial_date_raw).strip()) or timezone.localdate()

        school = str(row.get('school') or row.get('школа') or row.get('maktab') or '').strip()
        telegram = str(row.get('telegram') or row.get('телеграм') or '').strip()
        parent_telegram = str(
            row.get('parent_telegram')
            or row.get('родитель_телеграм')
            or row.get('телеграм_родителя')
            or ''
        ).strip()
        # paid_this_month is computed from Payment records only (sync_student_paid_this_month).
        # CSV import no longer sets this flag directly to prevent inconsistency.

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
            'status_label': status_label_map.get(status, 'Обучается'),
            'trial_date': trial_date.isoformat(),
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
            'trial_date': trial_date,
            'school': school,
            'telegram': telegram,
            'parent_telegram': parent_telegram,
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

    from crm.services import match_student_to_lead, enrich_student_from_lead, update_lead_on_conversion
    for item in valid_students_to_create:
        student = Student.objects.create(**item)
        # Match and enrich from lead IN MEMORY
        matched_lead = match_student_to_lead(student)
        enrich_student_from_lead(student, matched_lead)
        student.save(update_fields=['lead', 'school', 'address', 'phone2', 'phone2_owner'])
        # Update lead AFTER student is saved
        if matched_lead:
            update_lead_on_conversion(student, matched_lead)
        created += 1

    return ok(_import_result(created, skipped, errors))

