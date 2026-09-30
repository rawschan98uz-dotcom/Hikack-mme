from datetime import date, timedelta

from django.db.models import Avg, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from accounts.rbac import (
    PERM_FINANCE_COMPANY,
    PERM_PAYMENTS_VIEW,
    PERM_REMINDERS_WRITE,
    get_effective_role,
    get_role_label,
    user_has_permission,
    user_is_teacher,
)
from api.responses import fail, ok
from api.archive import archive_teacher
from crm.debts import LOCKED_MESSAGE, close_unpaid_leave, unpaid_leave_state
from api.scope import (
    branch_allowed,
    branches_for,
    can_access_group,
    can_access_student,
    filter_attendance_queryset,
    filter_groups_queryset,
    filter_reminders_queryset,
    reminder_assignees_queryset,
    scope_branch,
)
from api.utils import name_taken
from crm.models import AttendanceRecord, Group, Student
from operations.models import (
    ArchiveReason,
    AuditLogRecord,
    ArchivedPerson,
    CallLog,
    Holiday,
    LeadForm,
    PlatformPayment,
    Reminder,
    SmsLog,
    StudentScore,
    StudentScoreHistory,
    Tag,
)
from org.models import Branch, Room


def _company(request):
    return request.user.company


VALID_REMINDER_STATUSES = {choice[0] for choice in Reminder.Status.choices}
REMINDER_CLOSED_MESSAGE = 'Напоминание уже закрыто — изменить его нельзя.'
REMINDER_TITLE_TOO_LONG = f'Название напоминания слишком длинное (не больше {Reminder.TITLE_MAX_LENGTH} символов).'


def _reminder_status_for_date(due_date: date) -> str:
    today = timezone.localdate()
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
        'status': reminder.current_status,
        'status_label': Reminder.Status(reminder.current_status).label,
        'assigned_to_id': reminder.assigned_to_id,
        'assigned_to': reminder.assigned_to.display_name() if reminder.assigned_to else '—',
        'created_by_id': reminder.created_by_id,
        'student_id': reminder.student_id,
        'kind': reminder.kind,
        'resolution': reminder.resolution,
        # "Left without paying": locked until the debt is paid; live remaining debt
        **unpaid_leave_state(reminder),
        'created_at': reminder.created_at.isoformat(),
    }


def _reminder_buckets(items: list[dict]) -> dict[str, list[dict]]:
    return {
        'overdue': [item for item in items if item['status'] == Reminder.Status.OVERDUE],
        'today': [item for item in items if item['status'] == Reminder.Status.TODAY],
        'future': [item for item in items if item['status'] == Reminder.Status.FUTURE],
    }


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _reminder_assignee(user, raw):
    """(assignee, error): only active staff / teachers the user may give reminders to (never students)."""
    if raw in (None, ''):
        return None, None
    try:
        return reminder_assignees_queryset(user).get(pk=int(raw)), None
    except (User.DoesNotExist, TypeError, ValueError):
        return None, 'Invalid assignee'


def _clean_title(raw) -> tuple[str, str | None]:
    title = str(raw or '').strip()
    if not title:
        return '', 'Reminder title is required'
    if len(title) > Reminder.TITLE_MAX_LENGTH:
        return '', REMINDER_TITLE_TOO_LONG
    return title, None


def _apply_reminder_fields(reminder: Reminder, request) -> str | None:
    data = request.data
    if data.get('title') is not None:
        title, error = _clean_title(data.get('title'))
        if error:
            return error
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
        reminder.status = _reminder_status_for_date(due_date)

    if 'assigned_to_id' in data:
        raw = data.get('assigned_to_id')
        if raw in (None, ''):
            reminder.assigned_to = None
        elif _int_or_none(raw) != reminder.assigned_to_id:
            # Keeping the current assignee is always fine (even if they were archived since)
            assignee, error = _reminder_assignee(request.user, raw)
            if error:
                return error
            reminder.assigned_to = assignee

    return None


@api_view(['GET'])
def reminder_assignees(request):
    """People a reminder can be given to (the "Assigned to" list): active staff and teachers."""
    if _company(request) is None:
        return ok([])
    return ok([
        {
            'id': u.id,
            'name': u.display_name(),
            'role': 'Учитель' if u.user_type == User.UserType.TEACHER else get_role_label(get_effective_role(u)),
        }
        for u in reminder_assignees_queryset(request.user).order_by('user_type', 'first_name', 'last_name', 'id')
    ])


@api_view(['GET'])
def reminder_summary(request):
    """Counter for the clock icon in the header: my open reminders for today and overdue ones."""
    company = _company(request)
    if company is None:
        return ok({'overdue': 0, 'today': 0, 'total': 0})
    today = timezone.localdate()
    qs = filter_reminders_queryset(Reminder.objects.filter(company=company), request.user).exclude(
        status=Reminder.Status.DONE,
    )
    overdue = qs.filter(due_date__lt=today).count()
    due_today = qs.filter(due_date=today).count()
    return ok({'overdue': overdue, 'today': due_today, 'total': overdue + due_today})


@api_view(['GET', 'POST'])
def reminder_index(request):
    company = _company(request)
    if company is None:
        return ok({'items': [], 'pinned': [], 'buckets': {'overdue': [], 'today': [], 'future': []}})

    if request.method == 'POST':
        title, error = _clean_title(request.data.get('title'))
        if error:
            return fail(error)

        details = str(request.data.get('details', '')).strip()
        due_date_raw = request.data.get('due_date')
        due_date = timezone.localdate()
        if due_date_raw:
            try:
                due_date = date.fromisoformat(str(due_date_raw)[:10])
            except ValueError:
                return fail('Invalid due date')

        assigned_to = request.user
        if 'assigned_to_id' in request.data:
            # null / '' = common reminder for the whole office
            assigned_to, error = _reminder_assignee(request.user, request.data.get('assigned_to_id'))
            if error:
                return fail(error)

        reminder = Reminder.objects.create(
            company=company,
            title=title,
            details=details,
            due_date=due_date,
            status=_reminder_status_for_date(due_date),
            assigned_to=assigned_to,
            created_by=request.user,
        )
        return ok(_serialize_reminder(reminder), status_code=201)

    qs = filter_reminders_queryset(Reminder.objects.filter(
        company=company,
    ), request.user).exclude(status=Reminder.Status.DONE).select_related('assigned_to').order_by('due_date', 'id')

    data = [_serialize_reminder(reminder) for reminder in qs]
    # Unpaid debts of students who left are pinned on top, outside the date tabs
    pinned = [item for item in data if item['kind'] == Reminder.KIND_UNPAID_LEAVE]
    regular = [item for item in data if item['kind'] != Reminder.KIND_UNPAID_LEAVE]
    return ok({'items': data, 'pinned': pinned, 'buckets': _reminder_buckets(regular)})


@api_view(['GET', 'PATCH', 'DELETE'])
def reminder_detail(request, reminder_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        reminder = filter_reminders_queryset(Reminder.objects, request.user).select_related('assigned_to').get(
            pk=reminder_id,
            company=company,
        )
    except Reminder.DoesNotExist:
        return fail('Reminder not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_reminder(reminder))

    if reminder.status == Reminder.Status.DONE:
        # Closed reminders (and debt write-offs) stay as history: nobody can change or delete them
        return fail(REMINDER_CLOSED_MESSAGE)

    if unpaid_leave_state(reminder)['locked']:
        # "Left without paying" cannot be edited or removed until the debt is paid (or written off by CEO)
        return fail(LOCKED_MESSAGE)

    if request.method == 'DELETE':
        reminder.delete()
        return ok({'deleted': True})

    error = _apply_reminder_fields(reminder, request)
    if error:
        return fail(error)
    reminder.save()
    reminder.refresh_from_db()
    return ok(_serialize_reminder(reminder))


@api_view(['POST'])
def reminder_complete(request, reminder_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        reminder = filter_reminders_queryset(Reminder.objects, request.user).get(pk=reminder_id, company=company)
    except Reminder.DoesNotExist:
        return fail('Reminder not found', status_code=404)

    # A teacher (view-only) may close only the reminders given to them
    if not user_has_permission(request.user, PERM_REMINDERS_WRITE) and reminder.assigned_to_id != request.user.id:
        return fail('Forbidden', status_code=403)

    if reminder.status == Reminder.Status.DONE:
        return fail(REMINDER_CLOSED_MESSAGE)

    if reminder.kind == Reminder.KIND_UNPAID_LEAVE:
        error = close_unpaid_leave(reminder, request.user, request.data.get('write_off_reason') or '')
        if error:
            return fail(error)
        return ok({'id': reminder.id, 'status': reminder.status, 'resolution': reminder.resolution})

    reminder.status = Reminder.Status.DONE
    reminder.save(update_fields=['status'])
    return ok({'id': reminder.id, 'status': reminder.status})


GRADE_WHOLE_MESSAGE = 'Оценка — целое число от 0 до {max}.'
ABSENT_MESSAGE = '{name} сегодня отсутствует на уроке — оценку поставить нельзя.'
FROZEN_MESSAGE = '{name} в заморозке — оценку поставить нельзя.'
NOT_IN_GROUP_MESSAGE = '{name} не учится в этой группе.'


def _parse_grade(raw, max_scale: int) -> tuple[int | None, str | None]:
    """Whole points only (owner, 2026-09-28): 85 is fine, 85.5 / 'abc' / NaN are not."""
    error = GRADE_WHOLE_MESSAGE.format(max=max_scale)
    if isinstance(raw, bool) or raw is None:
        return None, error
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, float):
        if not raw.is_integer():
            return None, error
        value = int(raw)
    else:
        text = str(raw).strip()
        if not text.isdigit():
            return None, error
        value = int(text)
    if value < 0 or value > max_scale:
        return None, error
    return value, None


def _current_scores(qs):
    """
    Only students who study now are in the rating (owner, 2026-09-28): those who left the centre
    and those in a freeze are not. Their grades are kept and come back with the student.
    """
    return qs.filter(student__status=Student.Status.STUDYING)


def _dense_places(grades) -> dict:
    """Equal points share a place and the next place follows: 90, 80, 80, 70 -> 1, 2, 2, 3."""
    return {grade: place for place, grade in enumerate(sorted(set(grades), reverse=True), start=1)}


def _company_places(company) -> dict:
    """Overall place of every grade among all students of the company who study now."""
    return _dense_places(
        _current_scores(StudentScore.objects.filter(company=company)).values_list('grade', flat=True),
    )


# Owner (2026-09-28): a grade belongs to a lesson — today or one of the group's lessons of the last 7 days
LESSON_DATE_DAYS_BACK = 7
LESSON_DATE_MESSAGE = 'Выберите день урока этой группы за последние 7 дней.'
WEEKDAY_SHORT = ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс')


def _lesson_dates(group) -> list:
    """
    Days (newest first, today included) of the last week when the group had a lesson:
    its weekday schedule, its start / end dates, and no holiday in its branch.
    """
    from api.v1.views_extended import _no_lesson_reason

    today = timezone.localdate()
    first = today - timedelta(days=LESSON_DATE_DAYS_BACK)
    holidays = set(Holiday.objects.filter(
        company_id=group.company_id, branch_id=group.branch_id, holiday_date__gte=first, holiday_date__lte=today,
    ).values_list('holiday_date', flat=True))
    days = [today - timedelta(days=n) for n in range(LESSON_DATE_DAYS_BACK + 1)]
    return [day for day in days if day not in holidays and _no_lesson_reason(group, day) is None]


def _lesson_date_label(day) -> str:
    label = f'{WEEKDAY_SHORT[day.weekday()]} {day.strftime("%d.%m")}'
    return f'{label} (сегодня)' if day == timezone.localdate() else label


def _parse_lesson_date(raw, group) -> tuple:
    """(lesson day, error): the day the grade is for; nothing sent = today. Must be one of the group's lessons."""
    if raw in (None, ''):
        day = timezone.localdate()
    else:
        try:
            day = date.fromisoformat(str(raw)[:10])
        except ValueError:
            return None, LESSON_DATE_MESSAGE
    if day not in _lesson_dates(group):
        return None, LESSON_DATE_MESSAGE
    return day, None


def _absent_on(group, student_ids, day) -> set:
    """Students marked "absent" in the attendance of this group on that day: no grade for that lesson."""
    return set(AttendanceRecord.objects.filter(
        group=group,
        student_id__in=list(student_ids),
        attend_date=day,
        status=AttendanceRecord.Status.ABSENT,
    ).values_list('student_id', flat=True))


def _absent_message(name: str, day) -> str:
    if day == timezone.localdate():
        return ABSENT_MESSAGE.format(name=name)
    return f'{name} не был на уроке {day.strftime("%d.%m.%Y")} — оценку за этот урок поставить нельзя.'


def _grading_blocker(student, group, day) -> str | None:
    """Why the student cannot get a grade for this lesson of the group (None = can)."""
    name = student.full_name
    if student.group_id != group.id or student.status not in Student.CURRENT_STATUSES:
        return NOT_IN_GROUP_MESSAGE.format(name=name)
    if student.status == Student.Status.FROZEN:
        return FROZEN_MESSAGE.format(name=name)
    if student.id in _absent_on(group, [student.id], day):
        return _absent_message(name, day)
    return None


def _latest_record(score):
    """The history record the rating shows: the grade of the latest lesson."""
    return score.history.order_by('-graded_on', '-id').first()


def _save_grade(company, student, group, grade: int, user, day) -> StudentScore:
    """
    Every grade goes to the student's history with the lesson day. The rating shows the grade of the
    latest lesson: a grade entered later for an earlier lesson stays only in the history.
    """
    score, _created = StudentScore.objects.get_or_create(
        company=company,
        student=student,
        group=group,
        defaults={'grade': grade},
    )
    StudentScoreHistory.objects.create(
        company=company,
        student=student,
        score=score,
        group=group,
        group_name=group.name,
        course_name=group.course.name if group.course_id else '',
        grade=grade,
        graded_on=day,
        graded_by=user,
    )
    latest = _latest_record(score)
    if latest is not None and score.grade != latest.grade:
        score.grade = latest.grade
        score.save()
    return score


def _serialize_score(score: StudentScore, place: int, company=None) -> dict:
    """`place` = overall place in the company rating; `rank_in_group` = place inside the group."""
    pass_score = company.grade_pass_score if company else 70
    max_scale = company.grade_scale_max if company else 100
    grade_val = int(score.grade)

    teacher_name = ''
    if score.group and score.group.teacher:
        teacher_name = (
            score.group.teacher.display_name()
            if hasattr(score.group.teacher, 'display_name')
            else (score.group.teacher.get_full_name() or score.group.teacher.phone)
        )

    course_name = ''
    if score.group and score.group.course:
        course_name = score.group.course.name

    return {
        'id': score.id,
        'no': place,
        'rank_in_group': score.rank,
        'student_id': score.student_id,
        'name': score.student.full_name,
        'group_id': score.group_id,
        'group': score.group.name if score.group else '',
        'course_id': score.group.course_id if score.group else None,
        'course': course_name,
        'teacher_id': score.group.teacher_id if score.group else None,
        'teacher': teacher_name,
        'branch_id': score.group.branch_id if score.group else None,
        'branch': score.group.branch.name if (score.group and score.group.branch) else '',
        'grade': grade_val,
        'rank': score.rank,
        'is_passed': grade_val >= pass_score,
        'pass_score': pass_score,
        'max_scale': max_scale,
        'updated_at': score.updated_at.isoformat(),
    }


def _recalculate_ranks(company, group_id: int | None = None) -> None:
    """Place inside the group among students who study now; equal points share a place."""
    groups = Group.objects.filter(company=company)
    if group_id is not None:
        groups = groups.filter(pk=group_id)
    for group in groups:
        scores = list(_current_scores(StudentScore.objects.filter(company=company, group=group)))
        places = _dense_places(score.grade for score in scores)
        for score in scores:
            if score.rank != places[score.grade]:
                StudentScore.objects.filter(pk=score.pk).update(rank=places[score.grade])


def _score_queryset(company, params):
    qs = _current_scores(StudentScore.objects.filter(company=company)).select_related(
        'student',
        'group',
        'group__branch',
        'group__course',
        'group__teacher',
    ).order_by('-grade', 'student__first_name', 'student__last_name')

    branch_id = params.get('branch_id')
    if branch_id:
        qs = qs.filter(group__branch_id=branch_id)

    group_id = params.get('group_id')
    if group_id:
        qs = qs.filter(group_id=group_id)

    teacher_id = params.get('teacher_id')
    if teacher_id:
        qs = qs.filter(group__teacher_id=teacher_id)

    course_id = params.get('course_id')
    if course_id:
        qs = qs.filter(group__course_id=course_id)

    pass_score = company.grade_pass_score if company else 70
    status = params.get('status')
    if status == 'passed':
        qs = qs.filter(grade__gte=pass_score)
    elif status == 'failed':
        qs = qs.filter(grade__lt=pass_score)

    query = (params.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(student__first_name__icontains=query) | Q(student__last_name__icontains=query),
        )

    return qs


def _group_for_grading(request, company, raw_group_id):
    """(group, error response) for grading endpoints: the group must exist and be the user's."""
    try:
        group = Group.objects.select_related('branch', 'course', 'teacher').get(pk=int(raw_group_id), company=company)
    except (Group.DoesNotExist, TypeError, ValueError):
        return None, fail('Group not found', status_code=404)
    if not can_access_group(request.user, group):
        return None, fail('You can grade only your own groups', status_code=403)
    return group, None


@api_view(['GET', 'POST'])
def scores_branch(request):
    company = _company(request)
    if company is None:
        return ok({'summary': {'total': 0, 'avg_grade': 0, 'passed_count': 0, 'failed_count': 0, 'pass_rate': 0, 'pass_score': 70, 'max_scale': 100}, 'rows': []})

    max_scale = company.grade_scale_max or 100
    pass_score = company.grade_pass_score or 70

    if request.method == 'POST':
        try:
            student_id = int(request.data.get('student_id'))
        except (TypeError, ValueError):
            return fail('Student, group and grade are required')
        grade, error = _parse_grade(request.data.get('grade'), max_scale)
        if error:
            return fail(error)

        try:
            student = Student.objects.get(pk=student_id, company=company)
        except Student.DoesNotExist:
            return fail('Student not found')

        group, error_response = _group_for_grading(request, company, request.data.get('group_id'))
        if error_response:
            return error_response
        day, error = _parse_lesson_date(request.data.get('lesson_date'), group)
        if error:
            return fail(error)
        blocker = _grading_blocker(student, group, day)
        if blocker:
            return fail(blocker)

        score = _save_grade(company, student, group, grade, request.user, day)
        _recalculate_ranks(company, group.id)
        score = StudentScore.objects.select_related(
            'student', 'group', 'group__branch', 'group__course', 'group__teacher',
        ).get(pk=score.pk)
        return ok(_serialize_score(score, _company_places(company).get(score.grade, 1), company), status_code=201)

    # a teacher sees grades of own groups only (same group-based rule as attendance)
    qs = filter_attendance_queryset(
        scope_branch(_score_queryset(company, request.query_params), request.user, 'group__branch'),
        request.user,
    )
    total = qs.count()
    avg_grade = qs.aggregate(avg=Avg('grade'))['avg'] or 0
    passed_count = qs.filter(grade__gte=pass_score).count()
    failed_count = total - passed_count
    pass_rate = round((passed_count / total * 100), 1) if total > 0 else 0

    status = request.query_params.get('status')
    if status == 'top10':
        qs = qs[:10]
    else:
        try:
            limit = int(request.query_params.get('limit') or 500)
        except (TypeError, ValueError):
            limit = 500
        qs = qs[:max(1, min(limit, 500))]

    places = _company_places(company)
    rows = [_serialize_score(score, places.get(score.grade, 0), company) for score in qs]

    summary = {
        'total': total,
        'avg_grade': round(float(avg_grade), 1),
        'passed_count': passed_count,
        'failed_count': failed_count,
        'pass_rate': pass_rate,
        'pass_score': pass_score,
        'max_scale': max_scale,
    }

    return ok({'summary': summary, 'rows': rows})


@api_view(['GET'])
def scores_sheet(request):
    """
    Grading sheet of one group for one lesson: the group's lesson days of the last 7 days to choose from
    (?date=, newest by default), every student who studies in the group, the last grade, and whether a grade
    can be given for that lesson (absent that day in the attendance / in a freeze -> no).
    """
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)
    group, error_response = _group_for_grading(request, company, request.query_params.get('group_id'))
    if error_response:
        return error_response

    lesson_dates = _lesson_dates(group)
    day = None
    raw_day = request.query_params.get('date')
    if raw_day:
        day, error = _parse_lesson_date(raw_day, group)
        if error:
            return fail(error)
    elif lesson_dates:
        day = lesson_dates[0]

    students = list(Student.objects.filter(
        company=company, group=group, status__in=Student.CURRENT_STATUSES,
    ).order_by('first_name', 'last_name'))
    absent = _absent_on(group, [s.id for s in students], day) if day else set()
    last_grades = dict(StudentScore.objects.filter(group=group, student__in=students).values_list('student_id', 'grade'))

    rows = []
    for student in students:
        reason, reason_label = '', ''
        if day is None:
            reason, reason_label = 'no_lesson', 'Нет урока'
        elif student.status == Student.Status.FROZEN:
            reason, reason_label = 'frozen', 'Заморозка'
        elif student.id in absent:
            reason, reason_label = 'absent', 'Отсутствует на уроке'
        rows.append({
            'student_id': student.id,
            'name': student.full_name,
            'last_grade': last_grades.get(student.id),
            'can_grade': not reason,
            'reason': reason,
            'reason_label': reason_label,
        })
    return ok({
        'group_id': group.id,
        'group': group.name,
        # The lesson the grades are for; None = the group had no lesson in the last 7 days
        'date': day.isoformat() if day else None,
        'lesson_dates': [{'date': d.isoformat(), 'label': _lesson_date_label(d)} for d in lesson_dates],
        'max_scale': company.grade_scale_max or 100,
        'pass_score': company.grade_pass_score or 70,
        'students': rows,
    })


@api_view(['POST'])
def scores_bulk(request):
    """Grades for a whole group at once. An empty box = not graded (nothing is saved for that student)."""
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    items = request.data.get('items')
    if not request.data.get('group_id') or not isinstance(items, list):
        return fail('group_id and items list are required')
    group, error_response = _group_for_grading(request, company, request.data.get('group_id'))
    if error_response:
        return error_response

    max_scale = company.grade_scale_max or 100
    student_ids = [item.get('student_id') for item in items if isinstance(item, dict) and item.get('student_id')]
    students_map = {
        s.id: s for s in Student.objects.filter(pk__in=student_ids, company=company, group=group)
    }
    day, error = _parse_lesson_date(request.data.get('lesson_date'), group)
    if error:
        return fail(error)
    absent = _absent_on(group, students_map.keys(), day)

    saved_count = 0
    skipped = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw = item.get('grade')
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue  # not graded
        student = students_map.get(item.get('student_id'))
        if student is None or student.status not in Student.CURRENT_STATUSES:
            skipped.append({'student_id': item.get('student_id'), 'reason': 'Не учится в этой группе'})
            continue
        if student.status == Student.Status.FROZEN:
            skipped.append({'student_id': student.id, 'reason': FROZEN_MESSAGE.format(name=student.full_name)})
            continue
        if student.id in absent:
            skipped.append({'student_id': student.id, 'reason': _absent_message(student.full_name, day)})
            continue
        grade, error = _parse_grade(raw, max_scale)
        if error:
            skipped.append({'student_id': student.id, 'reason': f'{student.full_name}: {error}'})
            continue
        _save_grade(company, student, group, grade, request.user, day)
        saved_count += 1

    _recalculate_ranks(company, group.id)

    places = _company_places(company)
    updated_scores = list(
        _current_scores(StudentScore.objects.filter(company=company, group=group))
        .select_related('student', 'group', 'group__branch', 'group__course', 'group__teacher')
        .order_by('-grade', 'student__first_name', 'student__last_name')
    )
    rows = [_serialize_score(sc, places.get(sc.grade, 0), company) for sc in updated_scores]
    return ok({'saved_count': saved_count, 'skipped': skipped, 'rows': rows})


@api_view(['GET'])
def scores_history(request):
    """Every grade of one student (the rating shows only the latest one)."""
    company = _company(request)
    if company is None:
        return ok([])
    try:
        student = Student.objects.select_related('group').get(pk=int(request.query_params.get('student_id')), company=company)
    except (Student.DoesNotExist, TypeError, ValueError):
        return fail('Student not found', status_code=404)
    if not can_access_student(request.user, student):
        return fail('Student not found', status_code=404)

    records = StudentScoreHistory.objects.filter(company=company, student=student).select_related(
        'graded_by', 'corrected_by',
    )
    return ok([
        {
            'id': record.id,
            'date': record.graded_on.isoformat(),
            'student': student.full_name,
            'group': record.group_name,
            'course': record.course_name,
            'grade': record.grade,
            'graded_by': record.graded_by.display_name() if record.graded_by else '',
            'corrected': record.corrected,
            'corrected_at': timezone.localtime(record.corrected_at).date().isoformat() if record.corrected_at else None,
            'corrected_by': record.corrected_by.display_name() if record.corrected_by else '',
        }
        for record in records
    ])


@api_view(['GET'])
def scores_groups(request):
    """Returns group leaderboard: average grade per group, course, teacher, student counts, pass rate."""
    company = _company(request)
    if company is None:
        return ok([])

    branch_id = request.query_params.get('branch_id')
    course_id = request.query_params.get('course_id')
    teacher_id = request.query_params.get('teacher_id')

    groups_qs = Group.objects.filter(company=company, status=Group.Status.ACTIVE).select_related(
        'branch', 'course', 'teacher'
    )
    groups_qs = filter_groups_queryset(groups_qs, request.user)
    if branch_id:
        groups_qs = groups_qs.filter(branch_id=branch_id)
    if course_id:
        groups_qs = groups_qs.filter(course_id=course_id)
    if teacher_id:
        groups_qs = groups_qs.filter(teacher_id=teacher_id)

    pass_score = company.grade_pass_score or 70
    max_scale = company.grade_scale_max or 100

    group_stats = []
    for g in groups_qs:
        scores = _current_scores(StudentScore.objects.filter(company=company, group=g))
        graded_count = scores.count()
        # Only students who study now (a frozen student does not study at the moment)
        enrolled_count = g.students.filter(status=Student.Status.STUDYING).count()
        if graded_count == 0:
            avg_grade = 0.0
            pass_rate = 0.0
            passed_count = 0
        else:
            avg_grade = float(scores.aggregate(avg=Avg('grade'))['avg'] or 0)
            passed_count = scores.filter(grade__gte=pass_score).count()
            pass_rate = round((passed_count / graded_count) * 100, 1)

        teacher_name = ''
        if g.teacher:
            teacher_name = (
                g.teacher.display_name()
                if hasattr(g.teacher, 'display_name')
                else (g.teacher.get_full_name() or g.teacher.phone)
            )

        group_stats.append({
            'group_id': g.id,
            'group_name': g.name,
            'branch_id': g.branch_id,
            'branch_name': g.branch.name if g.branch else '',
            'course_id': g.course_id,
            'course_name': g.course.name if g.course else '—',
            'teacher_id': g.teacher_id,
            'teacher_name': teacher_name or '—',
            'enrolled_count': enrolled_count,
            'graded_count': graded_count,
            'passed_count': passed_count,
            'avg_grade': round(avg_grade, 1),
            'pass_rate': pass_rate,
            'pass_score': pass_score,
            'max_scale': max_scale,
        })

    group_stats.sort(key=lambda x: (x['avg_grade'], x['graded_count']), reverse=True)
    for idx, item in enumerate(group_stats, start=1):
        item['rank'] = idx

    return ok(group_stats)


@api_view(['GET', 'PATCH', 'DELETE'])
def score_detail(request, score_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        score = StudentScore.objects.select_related(
            'student', 'group', 'group__branch', 'group__course', 'group__teacher'
        ).get(
            pk=score_id,
            company=company,
        )
    except StudentScore.DoesNotExist:
        return fail('Score not found', status_code=404)
    if not branch_allowed(request.user, score.group.branch_id if score.group_id else None):
        return fail('Score not found', status_code=404)
    if user_is_teacher(request.user) and (score.group is None or score.group.teacher_id != request.user.id):
        return fail('Score not found', status_code=404)

    if request.method == 'GET':
        return ok(_serialize_score(score, _company_places(company).get(score.grade, 0), company))

    if score.group is None or not can_access_group(request.user, score.group):
        return fail('You can grade only your own groups', status_code=403)

    group_id = score.group_id
    max_scale = company.grade_scale_max or 100

    if request.method == 'DELETE':
        # The grade was a mistake: it leaves the rating together with its (latest) history record;
        # earlier grades of the student stay in the history
        latest = _latest_record(score)
        if latest is not None:
            latest.delete()
        score.delete()
        _recalculate_ranks(company, group_id)
        return ok({'deleted': True})

    # Only the points can be changed; the student and the group of a grade never change here
    # (a grade follows the student to a new group by itself — crm/signals.py)
    for field, current in (('student_id', score.student_id), ('group_id', score.group_id)):
        raw = request.data.get(field)
        if raw not in (None, '') and str(raw) != str(current):
            return fail('Можно изменить только балл. Ученика и группу у оценки менять нельзя.')

    if 'grade' in request.data:
        grade, error = _parse_grade(request.data.get('grade'), max_scale)
        if error:
            return fail(error)
        if grade != score.grade:
            score.grade = grade
            # A correction of a typo, not a new grade: the latest history record is fixed and marked
            latest = _latest_record(score)
            if latest is None:
                latest = StudentScoreHistory(
                    company=company, student=score.student, score=score, group=score.group,
                    group_name=score.group.name, course_name=score.group.course.name if score.group.course_id else '',
                    graded_on=timezone.localdate(), graded_by=request.user,
                )
            latest.grade = grade
            latest.corrected = True
            latest.corrected_at = timezone.now()
            latest.corrected_by = request.user
            latest.save()

    score.save()
    _recalculate_ranks(company, group_id)
    score.refresh_from_db()
    return ok(_serialize_score(score, _company_places(company).get(score.grade, 0), company))


@api_view(['GET', 'POST'])
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
            branch = branches_for(request.user, company).get(pk=branch_id)
        except Branch.DoesNotExist:
            return fail('Branch not found')

        room = Room.objects.create(company=company, branch=branch, name=name, capacity=max(capacity, 1))
        return ok(_serialize_room(room), status_code=201)

    rooms = scope_branch(Room.objects.filter(company=company).select_related('branch'), request.user)
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
def room_detail(request, room_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    room = scope_branch(Room.objects.filter(pk=room_id, company=company), request.user).select_related('branch').first()
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
            room.branch = branches_for(request.user, company).get(pk=int(branch_id))
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
            branch = branches_for(request.user, company).get(pk=branch_id)
        except (Branch.DoesNotExist, TypeError, ValueError):
            return fail('Branch is required')

        if Holiday.objects.filter(company=company, branch=branch, holiday_date=holiday_date).exists():
            return fail('На эту дату в этом филиале уже есть праздник')
        holiday = Holiday.objects.create(
            company=company,
            branch=branch,
            name=name,
            holiday_date=holiday_date,
            affects_payment=bool(request.data.get('affects_payment')),
        )
        return ok(_serialize_holiday(holiday), status_code=201)

    holidays = scope_branch(Holiday.objects.filter(company=company), request.user).select_related('branch').order_by('-holiday_date')
    return ok([_serialize_holiday(h) for h in holidays])


@api_view(['GET', 'PATCH', 'DELETE'])
def holiday_detail(request, holiday_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    holiday = scope_branch(Holiday.objects.filter(pk=holiday_id, company=company), request.user).select_related('branch').first()
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
            holiday.branch = branches_for(request.user, company).get(pk=int(branch_id))
        except (Branch.DoesNotExist, TypeError, ValueError):
            return fail('Branch not found')

    if Holiday.objects.filter(
        company=company, branch_id=holiday.branch_id, holiday_date=holiday.holiday_date,
    ).exclude(pk=holiday.pk).exists():
        return fail('На эту дату в этом филиале уже есть праздник')
    holiday.save()
    holiday.refresh_from_db()
    return ok(_serialize_holiday(holiday))


@api_view(['GET'])
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
def archive_list(request):
    company = _company(request)
    if company is None:
        return ok({'quantity': 0, 'rows': []})

    if request.method == 'POST':
        name = str(request.data.get('name') or '').strip()
        phone = ''.join(ch for ch in str(request.data.get('phone') or '') if ch.isdigit())
        if not name or not phone:
            return fail('Name and phone are required')

        roles = str(request.data.get('roles') or request.data.get('role') or '').strip()
        person = ArchivedPerson.objects.create(
            company=company,
            name=name,
            phone=phone,
            roles=roles,
            reason=str(request.data.get('reason') or '').strip(),
            comment=str(request.data.get('comment') or '').strip(),
        )
        if 'teacher' in roles.lower():
            teacher = User.objects.filter(company=company, phone=phone, user_type=User.UserType.TEACHER).first()
            if teacher:
                archive_teacher(company, teacher, create_record=False)
        return ok(_serialize_archived(person), status_code=201)

    qs = _archive_queryset(company, request.query_params)
    rows = [_serialize_archived(person) for person in qs[:500]]
    return ok({'quantity': qs.count(), 'rows': rows})


@api_view(['GET', 'DELETE'])
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
def archive_restore(request, person_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    person = ArchivedPerson.objects.filter(pk=person_id, company=company).first()
    if person is None:
        return fail('Archived record not found', status_code=404)

    payload = _serialize_archived(person)
    if 'teacher' in (person.roles or '').lower():
        User.objects.filter(company=company, phone=person.phone, user_type=User.UserType.TEACHER).update(is_active=True)
    person.delete()
    return ok({'restored': True, 'person': payload})


@api_view(['POST'])
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
    if action == 'restore':
        teacher_phones = [p.phone for p in people if 'teacher' in (p.roles or '').lower()]
        if teacher_phones:
            User.objects.filter(company=company, phone__in=teacher_phones, user_type=User.UserType.TEACHER).update(is_active=True)
    for person in people:
        person.delete()

    return ok({'action': action, 'count': count})


@api_view(['GET', 'POST'])
def tags_list(request):
    company = _company(request)
    if company is None:
        return ok([])

    if request.method == 'POST':
        name = str(request.data.get('name') or '').strip()
        if not name:
            return fail('Tag name is required')
        if name_taken(Tag.objects.filter(company=company), name):
            return fail('Такой тег уже есть')
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
        if name_taken(Tag.objects.filter(company=company), name, exclude_pk=tag.pk):
            return fail('Такой тег уже есть')
        tag.name = name

    if 'from_where' in request.data or 'source' in request.data:
        tag.source = str(request.data.get('from_where') or request.data.get('source') or '').strip()

    tag.save()
    return ok(_serialize_tag(tag))


@api_view(['GET', 'POST'])
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
def activity_logs(request):
    company = _company(request)
    if company is None:
        return ok([])

    # Single audit journal (C5): human-readable view over AuditLogRecord.
    # Money records are shown only to those who may see that money (owner, 2026-09-28): expenses,
    # withdrawals and salaries — company finance (CEO); student payments — whoever sees payments.
    logs = AuditLogRecord.objects.filter(company=company)
    if not user_has_permission(request.user, PERM_FINANCE_COMPANY):
        logs = logs.exclude(entity_type__in=('expense', 'withdrawal', 'payroll', 'finance_month'))
    if not user_has_permission(request.user, PERM_PAYMENTS_VIEW):
        logs = logs.exclude(entity_type='payment')
    return ok([
        {
            'action': log.reason or f'{log.action} {log.entity_type} #{log.entity_id}',
            'actor': log.actor_name or 'System',
            'created_at': timezone.localtime(log.created_at).strftime('%Y-%m-%d %H:%M'),
        }
        for log in logs.order_by('-created_at')[:200]
    ])


@api_view(['GET'])
def company_platform_payments(request, company_id: int):
    company = _company(request)
    if company is None or company.id != company_id:
        return fail('Company not found', status_code=404)

    return ok([
        {'sum': p.amount, 'created_at': p.created_at.strftime('%Y-%m-%d')}
        for p in PlatformPayment.objects.filter(company=company).order_by('-created_at')
    ])
