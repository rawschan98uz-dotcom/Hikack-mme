"""Quick search over the whole program (Ctrl+K): students, leads and groups in one request."""

import re

from django.db.models import Case, IntegerField, Q, Value, When
from rest_framework.decorators import api_view

from accounts.rbac import (
    PERM_GROUPS_VIEW,
    PERM_LEADS_VIEW,
    PERM_STUDENTS_VIEW,
    user_has_permission,
)
from api.responses import ok
from api.scope import filter_groups_queryset, filter_students_queryset, scope_branch
from crm.models import Group, Lead, Student

# Enough to recognise the person; the full list is one click away
LIMIT = 6
MIN_LENGTH = 2


def _phone_digits(query: str) -> str:
    """The digits of a query that looks like a phone number ("+998 90 123", "90-123"), else ''."""
    if not re.fullmatch(r'[\d\s()+-]+', query):
        return ''
    digits = re.sub(r'\D', '', query)
    # Phones are stored as 9 digits: "998901234567" is the same subscriber as "901234567"
    if len(digits) > 9 and digits.startswith('998'):
        digits = digits[3:]
    return digits if len(digits) >= 3 else ''


def _person_filter(query: str) -> Q:
    """Every word must be found in the first name, last name or phone ("Азиз Карим" finds "Азиз Каримов")."""
    digits = _phone_digits(query)
    if digits:
        return Q(phone__contains=digits) | Q(phone2__contains=digits)
    condition = Q()
    for word in query.split()[:4]:
        condition &= (
            Q(first_name__icontains=word)
            | Q(last_name__icontains=word)
            | Q(phone__icontains=word)
            | Q(phone2__icontains=word)
        )
    return condition


def _students(request, company, query: str) -> list[dict]:
    # The money columns are left out on purpose: a teacher must not see them (E1), and the list
    # shows the debt itself; the search only has to find the person.
    qs = filter_students_queryset(
        Student.objects.filter(company=company).select_related('group'), request.user,
    ).filter(_person_filter(query))
    # Current students first, then those who left
    qs = qs.annotate(
        current=Case(When(status__in=Student.CURRENT_STATUSES, then=Value(0)), default=Value(1), output_field=IntegerField()),
    ).order_by('current', 'first_name', 'last_name')
    return [
        {
            'id': s.id,
            'full_name': s.full_name,
            'phone': s.phone,
            'status': s.status,
            'group': s.group.name if s.group_id else None,
        }
        for s in qs[:LIMIT]
    ]


def _leads(request, company, query: str) -> list[dict]:
    qs = scope_branch(Lead.objects.filter(company=company), request.user).filter(_person_filter(query))
    # Leads still in the funnel first; archived ones are found too (they are often the ones looked for)
    qs = qs.order_by('-is_active', '-created_at')
    return [
        {
            'id': lead.id,
            'full_name': f'{lead.first_name} {lead.last_name}'.strip(),
            'phone': lead.phone,
            'stage': lead.stage,
            'archived': not lead.is_active,
        }
        for lead in qs[:LIMIT]
    ]


def _groups(request, company, query: str) -> list[dict]:
    condition = Q()
    for word in query.split()[:4]:
        condition &= Q(name__icontains=word) | Q(course__name__icontains=word)
    qs = filter_groups_queryset(
        Group.objects.filter(company=company).select_related('course', 'teacher'), request.user,
    ).filter(condition).order_by('status', 'name')
    return [
        {
            'id': g.id,
            'name': g.name,
            'course': g.course.name if g.course_id else None,
            'teacher': g.teacher.display_name() if g.teacher_id else None,
            'archived': g.status == Group.Status.ARCHIVE,
        }
        for g in qs[:LIMIT]
    ]


@api_view(['GET'])
def global_search(request):
    company = request.user.company
    query = ' '.join((request.query_params.get('q') or '').split())[:100]
    result = {'students': [], 'leads': [], 'groups': []}
    if company is None or len(query) < MIN_LENGTH:
        return ok(result)

    user = request.user
    # Each section only for those who may open it; the row scope (branch, own groups) is the list's
    if user_has_permission(user, PERM_STUDENTS_VIEW):
        result['students'] = _students(request, company, query)
    if user_has_permission(user, PERM_LEADS_VIEW):
        result['leads'] = _leads(request, company, query)
    if user_has_permission(user, PERM_GROUPS_VIEW):
        result['groups'] = _groups(request, company, query)
    return ok(result)
