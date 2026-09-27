"""Row-level scope: a teacher sees own groups/students, a branch director sees one branch only."""

from django.db.models import Q

from accounts.models import User
from accounts.rbac import ROLE_BRANCH_DIRECTOR, get_effective_role, user_is_teacher
from crm.models import Group, Student
from org.models import Branch

# A branch id that never exists: a director without a branch sees nothing.
NO_BRANCH = 0


def branch_limit(user: User) -> int | None:
    """E3: the branch id the user is limited to, or None when the user sees every branch."""
    if user is None or not user.is_authenticated:
        return None
    if get_effective_role(user) != ROLE_BRANCH_DIRECTOR:
        return None
    return user.branch_id or NO_BRANCH


def scope_branch(qs, user: User, field: str = 'branch'):
    """Keep only rows of the director's branch; `field` is the lookup to the branch (e.g. 'group__branch')."""
    limit = branch_limit(user)
    if limit is None:
        return qs
    return qs.filter(**{field: limit})


def branch_allowed(user: User, branch_id) -> bool:
    limit = branch_limit(user)
    return limit is None or (branch_id is not None and int(branch_id) == limit)


def branches_for(user: User, company):
    """Branches of the company the user may see or pick."""
    return scope_branch(Branch.objects.filter(company=company), user, 'id')


def filter_groups_queryset(qs, user: User):
    if user_is_teacher(user):
        return qs.filter(teacher=user)
    return scope_branch(qs, user)


def filter_students_queryset(qs, user: User):
    if user_is_teacher(user):
        return qs.filter(group__teacher=user)
    return scope_branch(qs, user)


def can_access_group(user: User, group: Group) -> bool:
    if user_is_teacher(user):
        return group.teacher_id == user.id
    return branch_allowed(user, group.branch_id)


def can_access_student(user: User, student: Student) -> bool:
    if user_is_teacher(user):
        if student.group_id is None:
            return False
        return student.group.teacher_id == user.id
    return branch_allowed(user, student.branch_id)


def scope_payments(qs, user: User):
    """E3: payments of the director's branch — by the group snapshot, else by the student's branch."""
    limit = branch_limit(user)
    if limit is None:
        return qs
    return qs.filter(Q(group__branch_id=limit) | Q(group__isnull=True, student__branch_id=limit))


def can_access_payment(user: User, payment) -> bool:
    limit = branch_limit(user)
    if limit is None:
        return True
    if payment.group_id:
        return payment.group.branch_id == limit
    return payment.student_id is not None and payment.student.branch_id == limit


def scope_teachers(qs, user: User):
    """E3: teachers who work in the director's branch."""
    limit = branch_limit(user)
    if limit is None:
        return qs
    return qs.filter(teacher_branches__branch_id=limit).distinct()


def can_access_lead(user: User, lead) -> bool:
    return branch_allowed(user, lead.branch_id)


def filter_attendance_queryset(qs, user: User):
    if user_is_teacher(user):
        return qs.filter(group__teacher=user)
    return scope_branch(qs, user, 'group__branch')


def can_access_attendance(user: User, record) -> bool:
    if record.group_id is None:
        return not user_is_teacher(user) and branch_limit(user) is None
    return can_access_group(user, record.group)


# E1: money-related student fields a teacher must never see.
TEACHER_HIDDEN_STUDENT_FIELDS = (
    'paid_this_month',
    'last_payment_date',
    'next_payment_date',
    'is_debtor',
    'overdue_days',
    'paid_count',
    'payment_offset',
    'course_price',
    'wallet',
    'month_price',
    'wallet_missing',
)


def strip_for_teacher(payload: dict, user: User) -> dict:
    """Blank out financial fields of a serialized student for the teacher role."""
    if not user_is_teacher(user):
        return payload
    for key in TEACHER_HIDDEN_STUDENT_FIELDS:
        if key in payload:
            payload[key] = None
    return payload


def filter_reminders_queryset(qs, user: User):
    """A teacher sees only reminders assigned to them (others may be about debts or other staff)."""
    if user_is_teacher(user):
        return qs.filter(assigned_to=user)
    limit = branch_limit(user)
    if limit is not None:
        # Branch director: reminders about students of other branches are not theirs
        return qs.filter(Q(student__isnull=True) | Q(student__branch_id=limit))
    return qs.all()


def filter_teacher_attendance_queryset(qs, user: User):
    if user_is_teacher(user):
        return qs.filter(teacher=user)
    return scope_branch(qs, user, 'group__branch')

