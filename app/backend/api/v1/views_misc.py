from datetime import date

from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from api.responses import fail, ok
from crm.models import Group, Student
from operations.models import (
    ActivityLog,
    ArchiveReason,
    ArchivedPerson,
    CallLog,
    Holiday,
    LeadForm,
    PlatformPayment,
    Reminder,
    SmsLog,
    StudentScore,
    Tag,
)
from org.models import Branch, Room


def _company(request):
    return request.user.company


VALID_REMINDER_STATUSES = {choice[0] for choice in Reminder.Status.choices}
ACTIVE_REMINDER_STATUSES = {
    Reminder.Status.OVERDUE,
    Reminder.Status.TODAY,
    Reminder.Status.FUTURE,
}


def _reminder_status_for_date(due_date: date) -> str:
    today = timezone.now().date()
    if due_date < today:
        return Reminder.Status.OVERDUE
    if due_date > today:
        return Reminder.Status.FUTURE
    return Reminder.Status.TODAY


def _serialize_reminder(reminder: Reminder) -> dict:
    return {
        'id': reminder.id,
        'title': reminder.title,
        'details': reminder.details,
        'due_date': reminder.due_date.isoformat(),
        'status': reminder.status,
        'status_label': reminder.get_status_display(),
        'assigned_to_id': reminder.assigned_to_id,
        'assigned_to': reminder.assigned_to.display_name() if reminder.assigned_to else '—',
        'created_at': reminder.created_at.isoformat(),
    }


def _reminder_buckets(items: list[dict]) -> dict[str, list[dict]]:
    return {
        'overdue': [item for item in items if item['status'] == Reminder.Status.OVERDUE],
        'today': [item for item in items if item['status'] == Reminder.Status.TODAY],
        'future': [item for item in items if item['status'] == Reminder.Status.FUTURE],
    }


def _apply_reminder_fields(reminder: Reminder, company, data: dict) -> str | None:
    title = data.get('title')
    if title is not None:
        title = str(title).strip()
        if not title:
            return 'Reminder title is required'
        reminder.title = title

    if 'details' in data:
        reminder.details = str(data.get('details') or '').strip()

    due_date_raw = data.get('due_date')
    if due_date_raw is not None:
        if due_date_raw in ('', None):
            return 'Due date is required'
        try:
            due_date = date.fromisoformat(str(due_date_raw)[:10])
        except ValueError:
            return 'Invalid due date'
        reminder.due_date = due_date
        if reminder.status != Reminder.Status.DONE:
            reminder.status = _reminder_status_for_date(due_date)

    assigned_to_id = data.get('assigned_to_id')
    if assigned_to_id is not None:
        if assigned_to_id in ('', None):
            reminder.assigned_to = None
        else:
            try:
                reminder.assigned_to = User.objects.get(
                    pk=int(assigned_to_id),
                    company=company,
                )
            except (User.DoesNotExist, TypeError, ValueError):
                return 'Invalid assignee'

    return None


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def reminder_index(request):
    company = _company(request)
    if company is None:
        return ok({'items': [], 'buckets': {'overdue': [], 'today': [], 'future': []}})

    if request.method == 'POST':
        title = str(request.data.get('title', '')).strip()
        if not title:
            return fail('Reminder title is required')

        details = str(request.data.get('details', '')).strip()
        due_date_raw = request.data.get('due_date')
        due_date = timezone.now().date()
        if due_date_raw:
            try:
                due_date = date.fromisoformat(str(due_date_raw)[:10])
            except ValueError:
                return fail('Invalid due date')

        assigned_to = request.user
        assigned_to_id = request.data.get('assigned_to_id')
        if assigned_to_id not in (None, ''):
            try:
                assigned_to = User.objects.get(pk=int(assigned_to_id), company=company)
            except (User.DoesNotExist, TypeError, ValueError):
                return fail('Invalid assignee')

        reminder = Reminder.objects.create(
            company=company,
            title=title,
            details=details,
            due_date=due_date,
            status=_reminder_status_for_date(due_date),
            assigned_to=assigned_to,
        )
        return ok(_serialize_reminder(reminder), status_code=201)

    qs = Reminder.objects.filter(
        company=company,
        status__in=ACTIVE_REMINDER_STATUSES,
    ).select_related('assigned_to').order_by('due_date', 'id')

    data = [_serialize_reminder(reminder) for reminder in qs]
    return ok({'items': data, 'buckets': _reminder_buckets(data)})


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def reminder_detail(request, reminder_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        reminder = Reminder.objects.select_related('assigned_to').get(
            pk=reminder_id,
            company=company,
        )
    except Reminder.DoesNotExist:
        return fail('Reminder not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_reminder(reminder))

    if request.method == 'DELETE':
        reminder.delete()
        return ok({'deleted': True})

    error = _apply_reminder_fields(reminder, company, request.data)
    if error:
        return fail(error)
    reminder.save()
    reminder.refresh_from_db()
    return ok(_serialize_reminder(reminder))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reminder_complete(request, reminder_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        reminder = Reminder.objects.get(pk=reminder_id, company=company)
    except Reminder.DoesNotExist:
        return fail('Reminder not found', status_code=404)

    reminder.status = Reminder.Status.DONE
    reminder.save(update_fields=['status'])
    return ok({'id': reminder.id, 'status': reminder.status})


def _serialize_score(score: StudentScore, rank: int) -> dict:
    return {
        'id': score.id,
        'no': rank,
        'student_id': score.student_id,
        'name': score.student.full_name,
        'group_id': score.group_id,
        'group': score.group.name,
        'branch_id': score.group.branch_id,
        'branch': score.group.branch.name,
        'grade': float(score.grade),
        'rank': score.rank,
        'updated_at': score.updated_at.isoformat(),
    }


def _recalculate_ranks(company, group_id: int | None = None) -> None:
    groups = Group.objects.filter(company=company)
    if group_id is not None:
        groups = groups.filter(pk=group_id)
    for group in groups:
        scores = StudentScore.objects.filter(company=company, group=group).order_by(
            '-grade',
            'student__first_name',
            'student__last_name',
        )
        for rank, score in enumerate(scores, start=1):
            if score.rank != rank:
                StudentScore.objects.filter(pk=score.pk).update(rank=rank)


def _score_queryset(company, params):
    qs = StudentScore.objects.filter(company=company).select_related(
        'student',
        'group',
        'group__branch',
    ).order_by('-grade', 'student__first_name', 'student__last_name')

    branch_id = params.get('branch_id')
    if branch_id:
        qs = qs.filter(group__branch_id=branch_id)

    group_id = params.get('group_id')
    if group_id:
        qs = qs.filter(group_id=group_id)

    query = (params.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(student__first_name__icontains=query) | Q(student__last_name__icontains=query),
        )

    return qs


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def scores_branch(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        try:
            student_id = int(request.data.get('student_id'))
            group_id = int(request.data.get('group_id'))
            grade = float(request.data.get('grade'))
        except (TypeError, ValueError):
            return fail('Student, group and grade are required')

        if grade < 0 or grade > 100:
            return fail('Grade must be between 0 and 100')

        try:
            student = Student.objects.get(pk=student_id, company=company)
        except Student.DoesNotExist:
            return fail('Student not found')

        try:
            group = Group.objects.select_related('branch').get(pk=group_id, company=company)
        except Group.DoesNotExist:
            return fail('Group not found')

        score, _created = StudentScore.objects.update_or_create(
            company=company,
            student=student,
            group=group,
            defaults={'grade': grade},
        )
        _recalculate_ranks(company, group.id)
        score.refresh_from_db()
        score = StudentScore.objects.select_related('student', 'group', 'group__branch').get(pk=score.pk)
        rank = StudentScore.objects.filter(
            company=company,
            group=group,
            grade__gt=score.grade,
        ).count() + 1
        return ok(_serialize_score(score, rank), status_code=201)

    scores = list(_score_queryset(company, request.query_params)[:200])
    rows = [_serialize_score(score, idx) for idx, score in enumerate(scores, start=1)]
    return ok(rows)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def score_detail(request, score_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        score = StudentScore.objects.select_related('student', 'group', 'group__branch').get(
            pk=score_id,
            company=company,
        )
    except StudentScore.DoesNotExist:
        return fail('Score not found', status_code=404)

    if request.method == 'GET':
        rank = StudentScore.objects.filter(
            company=company,
            group=score.group,
            grade__gt=score.grade,
        ).count() + 1
        return ok(_serialize_score(score, rank))

    group_id = score.group_id

    if request.method == 'DELETE':
        score.delete()
        _recalculate_ranks(company, group_id)
        return ok({'deleted': True})

    if 'grade' in request.data:
        try:
            grade = float(request.data.get('grade'))
        except (TypeError, ValueError):
            return fail('Invalid grade')
        if grade < 0 or grade > 100:
            return fail('Grade must be between 0 and 100')
        score.grade = grade

    student_id = request.data.get('student_id')
    if student_id is not None:
        try:
            score.student = Student.objects.get(pk=int(student_id), company=company)
        except (Student.DoesNotExist, TypeError, ValueError):
            return fail('Student not found')

    group_id_raw = request.data.get('group_id')
    if group_id_raw is not None:
        try:
            score.group = Group.objects.get(pk=int(group_id_raw), company=company)
        except (Group.DoesNotExist, TypeError, ValueError):
            return fail('Group not found')
        group_id = score.group_id

    score.save()
    _recalculate_ranks(company, group_id)
    score.refresh_from_db()
    rank = StudentScore.objects.filter(
        company=company,
        group=score.group,
        grade__gt=score.grade,
    ).count() + 1
    return ok(_serialize_score(score, rank))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def room_list(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        try:
            branch_id = int(request.data.get('branch_id'))
            capacity = int(request.data.get('room_capacity') or request.data.get('capacity') or 20)
        except (TypeError, ValueError):
            return fail('Branch and capacity are required')

        name = str(request.data.get('name') or '').strip()
        if not name:
            return fail('Room name is required')

        try:
            branch = Branch.objects.get(pk=branch_id, company=company)
        except Branch.DoesNotExist:
            return fail('Branch not found')

        room = Room.objects.create(branch=branch, name=name, capacity=max(capacity, 1))
        return ok(_serialize_room(room), status_code=201)

    rooms = Room.objects.filter(branch__company=company).select_related('branch')
    return ok([_serialize_room(r) for r in rooms])


def _serialize_room(room: Room) -> dict:
    return {
        'id': room.id,
        'name': room.name,
        'room_capacity': room.capacity,
        'branch_id': room.branch_id,
        'branch': room.branch.name,
    }


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def room_detail(request, room_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    room = Room.objects.filter(pk=room_id, branch__company=company).select_related('branch').first()
    if room is None:
        return fail('Room not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_room(room))

    if request.method == 'DELETE':
        room.delete()
        return ok({'deleted': True})

    if 'name' in request.data:
        name = str(request.data.get('name') or '').strip()
        if not name:
            return fail('Room name is required')
        room.name = name

    capacity = request.data.get('room_capacity', request.data.get('capacity'))
    if capacity is not None:
        try:
            room.capacity = max(int(capacity), 1)
        except (TypeError, ValueError):
            return fail('Invalid capacity')

    branch_id = request.data.get('branch_id')
    if branch_id is not None:
        try:
            room.branch = Branch.objects.get(pk=int(branch_id), company=company)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return fail('Branch not found')

    room.save()
    room.refresh_from_db()
    return ok(_serialize_room(room))


def _serialize_holiday(holiday: Holiday) -> dict:
    return {
        'id': holiday.id,
        'name': holiday.name,
        'date': holiday.holiday_date.isoformat(),
        'created_at': holiday.created_at.strftime('%Y-%m-%d'),
        'affects_payment': holiday.affects_payment,
        'branch_id': holiday.branch_id,
        'branch': holiday.branch.name,
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def holiday_list(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        name = str(request.data.get('name') or '').strip()
        if not name:
            return fail('Holiday name is required')

        date_raw = request.data.get('date') or request.data.get('holiday_date')
        if not date_raw:
            return fail('Date is required')
        try:
            holiday_date = date.fromisoformat(str(date_raw)[:10])
        except ValueError:
            return fail('Invalid date')

        try:
            branch_id = int(request.data.get('branch_id'))
            branch = Branch.objects.get(pk=branch_id, company=company)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return fail('Branch is required')

        holiday = Holiday.objects.create(
            company=company,
            branch=branch,
            name=name,
            holiday_date=holiday_date,
            affects_payment=bool(request.data.get('affects_payment')),
        )
        return ok(_serialize_holiday(holiday), status_code=201)

    holidays = Holiday.objects.filter(company=company).select_related('branch').order_by('-holiday_date')
    return ok([_serialize_holiday(h) for h in holidays])


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def holiday_detail(request, holiday_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    holiday = Holiday.objects.filter(pk=holiday_id, company=company).select_related('branch').first()
    if holiday is None:
        return fail('Holiday not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_holiday(holiday))

    if request.method == 'DELETE':
        holiday.delete()
        return ok({'deleted': True})

    if 'name' in request.data:
        name = str(request.data.get('name') or '').strip()
        if not name:
            return fail('Holiday name is required')
        holiday.name = name

    date_raw = request.data.get('date') or request.data.get('holiday_date')
    if date_raw:
        try:
            holiday.holiday_date = date.fromisoformat(str(date_raw)[:10])
        except ValueError:
            return fail('Invalid date')

    if 'affects_payment' in request.data:
        holiday.affects_payment = bool(request.data.get('affects_payment'))

    branch_id = request.data.get('branch_id')
    if branch_id is not None:
        try:
            holiday.branch = Branch.objects.get(pk=int(branch_id), company=company)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return fail('Branch not found')

    holiday.save()
    holiday.refresh_from_db()
    return ok(_serialize_holiday(holiday))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def archive_reasons(request):
    company = _company(request)
    if company is None:
        return ok([])

    reasons = ArchiveReason.objects.filter(company=company).order_by('name')
    if not reasons.exists():
        return ok([
            {'id': 1, 'name': 'Moved abroad'},
            {'id': 2, 'name': 'No longer studying'},
            {'id': 3, 'name': 'Payment issues'},
        ])

    return ok([{'id': r.id, 'name': r.name} for r in reasons])


def _serialize_archived(person: ArchivedPerson) -> dict:
    return {
        'id': person.id,
        'name': person.name,
        'phone': person.phone,
        'roles': person.roles or '—',
        'reason': person.reason or '—',
        'comment': person.comment or '—',
        'archived': person.archived_at.strftime('%Y-%m-%d'),
    }


def _archive_queryset(company, params):
    qs = ArchivedPerson.objects.filter(company=company).order_by('-archived_at')

    query = (params.get('q') or '').strip()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(phone__icontains=query))

    role = (params.get('role') or '').strip()
    if role:
        qs = qs.filter(roles__icontains=role)

    reason = (params.get('reason') or '').strip()
    if reason:
        qs = qs.filter(reason__icontains=reason)

    date_from = params.get('date_from')
    if date_from:
        qs = qs.filter(archived_at__date__gte=date_from)

    date_to = params.get('date_to')
    if date_to:
        qs = qs.filter(archived_at__date__lte=date_to)

    return qs


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def archive_list(request):
    company = _company(request)
    if company is None:
        return ok({'quantity': 0, 'rows': []})

    if request.method == 'POST':
        name = str(request.data.get('name') or '').strip()
        phone = ''.join(ch for ch in str(request.data.get('phone') or '') if ch.isdigit())
        if not name or not phone:
            return fail('Name and phone are required')

        person = ArchivedPerson.objects.create(
            company=company,
            name=name,
            phone=phone,
            roles=str(request.data.get('roles') or request.data.get('role') or '').strip(),
            reason=str(request.data.get('reason') or '').strip(),
            comment=str(request.data.get('comment') or '').strip(),
        )
        return ok(_serialize_archived(person), status_code=201)

    qs = _archive_queryset(company, request.query_params)
    rows = [_serialize_archived(person) for person in qs[:500]]
    return ok({'quantity': qs.count(), 'rows': rows})


@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def archive_detail(request, person_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    person = ArchivedPerson.objects.filter(pk=person_id, company=company).first()
    if person is None:
        return fail('Archived record not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_archived(person))

    person.delete()
    return ok({'deleted': True})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def archive_restore(request, person_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    person = ArchivedPerson.objects.filter(pk=person_id, company=company).first()
    if person is None:
        return fail('Archived record not found', status_code=404)

    payload = _serialize_archived(person)
    person.delete()
    return ok({'restored': True, 'person': payload})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def archive_bulk(request):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    action = request.data.get('action')
    if action not in {'delete', 'restore'}:
        return fail('Invalid action')

    raw_ids = request.data.get('ids') or []
    try:
        ids = [int(item) for item in raw_ids]
    except (TypeError, ValueError):
        return fail('Invalid ids')

    people = list(ArchivedPerson.objects.filter(company=company, pk__in=ids))
    count = len(people)
    for person in people:
        person.delete()

    return ok({'action': action, 'count': count})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def tags_list(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        name = str(request.data.get('name') or '').strip()
        if not name:
            return fail('Tag name is required')
        tag = Tag.objects.create(
            company=company,
            name=name,
            source=str(request.data.get('from_where') or request.data.get('source') or '').strip(),
        )
        return ok(_serialize_tag(tag), status_code=201)

    return ok([_serialize_tag(t) for t in Tag.objects.filter(company=company)])


def _serialize_tag(tag: Tag) -> dict:
    return {'id': tag.id, 'name': tag.name, 'from_where': tag.source or '—'}


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def tag_detail(request, tag_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    tag = Tag.objects.filter(pk=tag_id, company=company).first()
    if tag is None:
        return fail('Tag not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_tag(tag))

    if request.method == 'DELETE':
        tag.delete()
        return ok({'deleted': True})

    if 'name' in request.data:
        name = str(request.data.get('name') or '').strip()
        if not name:
            return fail('Tag name is required')
        tag.name = name

    if 'from_where' in request.data or 'source' in request.data:
        tag.source = str(request.data.get('from_where') or request.data.get('source') or '').strip()

    tag.save()
    return ok(_serialize_tag(tag))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def lead_form_list(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        name = str(request.data.get('name') or '').strip()
        if not name:
            return fail('Form name is required')
        form = LeadForm.objects.create(
            company=company,
            name=name,
            form_type=str(request.data.get('type') or request.data.get('form_type') or 'lead').strip(),
        )
        return ok(_serialize_lead_form(form), status_code=201)

    return ok([_serialize_lead_form(f) for f in LeadForm.objects.filter(company=company)])


def _serialize_lead_form(form: LeadForm) -> dict:
    return {'id': form.id, 'name': form.name, 'type': form.form_type}


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def lead_form_detail(request, form_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    form = LeadForm.objects.filter(pk=form_id, company=company).first()
    if form is None:
        return fail('Form not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_lead_form(form))

    if request.method == 'DELETE':
        form.delete()
        return ok({'deleted': True})

    if 'name' in request.data:
        name = str(request.data.get('name') or '').strip()
        if not name:
            return fail('Form name is required')
        form.name = name

    if 'type' in request.data or 'form_type' in request.data:
        form.form_type = str(request.data.get('type') or request.data.get('form_type') or 'lead').strip()

    form.save()
    return ok(_serialize_lead_form(form))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sms_report(request):
    company = _company(request)
    if company is None:
        return ok([])

    return ok([
        {
            'phone': s.phone,
            'message': s.message,
            'status': s.status,
            'sent_at': s.sent_at.strftime('%Y-%m-%d %H:%M'),
        }
        for s in SmsLog.objects.filter(company=company).order_by('-sent_at')[:200]
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def call_logs(request):
    company = _company(request)
    if company is None:
        return ok([])

    return ok([
        {
            'type': c.call_type,
            'time': c.called_at.strftime('%Y-%m-%d %H:%M'),
            'who': c.caller,
            'to_whom': c.callee,
            'gateway': c.gateway,
            'duration': c.duration,
            'result': c.result,
        }
        for c in CallLog.objects.filter(company=company).order_by('-called_at')[:200]
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def activity_logs(request):
    company = _company(request)
    if company is None:
        return ok([])

    return ok([
        {
            'action': log.action,
            'actor': log.actor_name,
            'created_at': log.created_at.strftime('%Y-%m-%d %H:%M'),
        }
        for log in ActivityLog.objects.filter(company=company).order_by('-created_at')[:200]
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def company_platform_payments(request, company_id: int):
    company = _company(request)
    if company is None or company.id != company_id:
        return ok([])

    return ok([
        {'sum': p.amount, 'created_at': p.created_at.strftime('%Y-%m-%d')}
        for p in PlatformPayment.objects.filter(company=company).order_by('-created_at')
    ])
