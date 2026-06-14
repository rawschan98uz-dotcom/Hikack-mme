"""CSV import endpoints for teachers and staff."""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from accounts.models import TeacherBranch, User
from api.csv_utils import normalize_phone, parse_csv_upload
from api.responses import fail, ok
from api.v1.views_extended import _company, teacher_create
from org.models import Branch

DEFAULT_IMPORT_PASSWORD = 'demo1234'
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
        honorific = row.get('honorific') or 'Mr'
        job_title = row.get('job_title', '')
        branch_raw = row.get('branch_ids') or row.get('branches') or row.get('branch', '')

        if not first_name or not phone:
            skipped += 1
            errors.append({'row': row_num, 'message': 'First name and phone are required'})
            continue

        if User.objects.filter(phone=phone).exists():
            skipped += 1
            errors.append({'row': row_num, 'message': f'Phone {phone} already exists'})
            continue

        branch_ids = _resolve_branch_ids(company, branch_raw)
        if not branch_ids:
            skipped += 1
            errors.append({'row': row_num, 'message': 'No valid branch found'})
            continue

        payload = {
            'first_name': first_name,
            'last_name': last_name,
            'phone': phone,
            'password': password,
            'honorific': honorific,
            'job_title': job_title,
            'branches': branch_ids,
        }
        class _Req:
            data = payload

        response = teacher_create(_Req(), company)
        if response.status_code >= 400:
            skipped += 1
            body = response.data if hasattr(response, 'data') else {}
            message = body.get('message') if isinstance(body, dict) else 'Could not create teacher'
            errors.append({'row': row_num, 'message': str(message)})
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
