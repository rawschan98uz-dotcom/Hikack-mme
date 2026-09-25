"""Scope querysets for teacher role — own groups/students only."""

from accounts.models import User
from accounts.rbac import user_is_teacher
from crm.models import Group, Student


def filter_groups_queryset(qs, user: User):
    if user_is_teacher(user):
        return qs.filter(teacher=user)
    return qs


def filter_students_queryset(qs, user: User):
    if user_is_teacher(user):
        return qs.filter(group__teacher=user)
    return qs


def teacher_can_access_group(user: User, group: Group) -> bool:
    if not user_is_teacher(user):
        return True
    return group.teacher_id == user.id


def teacher_can_access_student(user: User, student: Student) -> bool:
    if not user_is_teacher(user):
        return True
    if student.group_id is None:
        return False
    return student.group.teacher_id == user.id


def filter_attendance_queryset(qs, user: User):
    if user_is_teacher(user):
        return qs.filter(group__teacher=user)
    return qs


def teacher_can_access_attendance(user: User, record) -> bool:
    if not user_is_teacher(user):
        return True
    if record.group_id is None:
        return False
    return record.group.teacher_id == user.id


# E1: money-related student fields a teacher must never see.
TEACHER_HIDDEN_STUDENT_FIELDS = (
    'balance',
    'paid_this_month',
    'last_payment_date',
    'next_payment_date',
    'is_debtor',
    'overdue_days',
    'paid_count',
    'payment_offset',
    'course_price',
)


def strip_for_teacher(payload: dict, user: User) -> dict:
    """Blank out financial fields of a serialized student for the teacher role."""
    if not user_is_teacher(user):
        return payload
    for key in TEACHER_HIDDEN_STUDENT_FIELDS:
        if key in payload:
            payload[key] = None
    return payload


def filter_teacher_attendance_queryset(qs, user: User):
    if user_is_teacher(user):
        return qs.filter(teacher=user)
    return qs

