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
