"""Student card tabs: attendance journal and the current group's schedule in one request."""

from django.db.models import Count, Q
from rest_framework.decorators import api_view

from api.responses import fail, ok
from api.scope import can_access_student, filter_attendance_queryset
from api.v1.views import _serialize_group
from crm.models import AttendanceRecord, Student

# Enough for a school year of lessons; older marks stay in the attendance report
RECORDS_LIMIT = 200


@api_view(['GET'])
def student_attendance(request, student_id: int):
    company = request.user.company
    if company is None:
        return fail('Company not found', status_code=404)
    try:
        student = Student.objects.select_related('group__course', 'group__teacher', 'group__room', 'group__branch').get(
            pk=student_id, company=company,
        )
    except Student.DoesNotExist:
        return fail('Student not found', status_code=404)
    if not can_access_student(request.user, student):
        return fail('Student not found', status_code=404)

    # A teacher sees the marks of their own groups only; a branch director — of their branch
    records = filter_attendance_queryset(
        AttendanceRecord.objects.filter(company=company, student=student), request.user,
    )
    summary = records.aggregate(
        total=Count('id'),
        present=Count('id', filter=Q(status=AttendanceRecord.Status.PRESENT)),
        late=Count('id', filter=Q(status=AttendanceRecord.Status.LATE)),
        absent=Count('id', filter=Q(status=AttendanceRecord.Status.ABSENT)),
    )
    rows = records.select_related('group').order_by('-attend_date', '-id')[:RECORDS_LIMIT]

    return ok({
        'summary': summary,
        'records': [
            {
                'id': r.id,
                'date': r.attend_date.isoformat(),
                'group_id': r.group_id,
                'group': r.group.name,
                'status': r.status,
                'note': r.note,
            }
            for r in rows
        ],
        'group': _serialize_group(student.group) if student.group_id else None,
    })
