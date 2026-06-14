"""Role-based access control — ModMe-style permission matrix."""

from __future__ import annotations

from accounts.models import User

# ---------------------------------------------------------------------------
# Permission codes (module.action or module.action.subaction)
# ---------------------------------------------------------------------------

PERM_DASHBOARD_VIEW = 'dashboard.view'

PERM_LEADS_VIEW = 'leads.view'
PERM_LEADS_WRITE = 'leads.write'

PERM_TEACHERS_VIEW = 'teachers.view'
PERM_TEACHERS_WRITE = 'teachers.write'

PERM_GROUPS_VIEW = 'groups.view'
PERM_GROUPS_WRITE = 'groups.write'
PERM_GROUPS_EXPORT = 'groups.export'

PERM_STUDENTS_VIEW = 'students.view'
PERM_STUDENTS_WRITE = 'students.write'

PERM_REMINDERS_VIEW = 'reminders.view'
PERM_REMINDERS_WRITE = 'reminders.write'

PERM_RATING_VIEW = 'rating.view'
PERM_RATING_WRITE = 'rating.write'

PERM_ATTENDANCE_VIEW = 'attendance.view'
PERM_ATTENDANCE_WRITE = 'attendance.write'

PERM_TEACHER_ATTENDANCE_VIEW = 'teacher_attendance.view'
PERM_TEACHER_ATTENDANCE_WRITE = 'teacher_attendance.write'

PERM_FINANCE_VIEW = 'finance.view'
PERM_FINANCE_WRITE = 'finance.write'

PERM_REPORTS_VIEW = 'reports.view'
PERM_REPORTS_WRITE = 'reports.write'

PERM_SETTINGS_COMPANY = 'settings.company'
PERM_SETTINGS_INTEGRATIONS = 'settings.integrations'
PERM_SETTINGS_GRADE = 'settings.grade'

PERM_STAFF_VIEW = 'staff.view'
PERM_STAFF_WRITE = 'staff.write'

PERM_COURSES_VIEW = 'courses.view'
PERM_COURSES_WRITE = 'courses.write'

PERM_ROOMS_VIEW = 'rooms.view'
PERM_ROOMS_WRITE = 'rooms.write'

PERM_HOLIDAYS_VIEW = 'holidays.view'
PERM_HOLIDAYS_WRITE = 'holidays.write'

PERM_ARCHIVE_VIEW = 'archive.view'
PERM_ARCHIVE_WRITE = 'archive.write'

PERM_TAGS_VIEW = 'tags.view'
PERM_TAGS_WRITE = 'tags.write'

PERM_FORMS_VIEW = 'forms.view'
PERM_FORMS_WRITE = 'forms.write'

PERM_LOGS_VIEW = 'logs.view'
PERM_BRANCH_VIEW = 'branch.view'
PERM_PROFILE_EDIT = 'profile.edit'
PERM_BILLING_VIEW = 'billing.view'

ALL_PERMISSIONS: frozenset[str] = frozenset(
    {
        PERM_DASHBOARD_VIEW,
        PERM_LEADS_VIEW,
        PERM_LEADS_WRITE,
        PERM_TEACHERS_VIEW,
        PERM_TEACHERS_WRITE,
        PERM_GROUPS_VIEW,
        PERM_GROUPS_WRITE,
        PERM_GROUPS_EXPORT,
        PERM_STUDENTS_VIEW,
        PERM_STUDENTS_WRITE,
        PERM_REMINDERS_VIEW,
        PERM_REMINDERS_WRITE,
        PERM_RATING_VIEW,
        PERM_RATING_WRITE,
        PERM_ATTENDANCE_VIEW,
        PERM_ATTENDANCE_WRITE,
        PERM_TEACHER_ATTENDANCE_VIEW,
        PERM_TEACHER_ATTENDANCE_WRITE,
        PERM_FINANCE_VIEW,
        PERM_FINANCE_WRITE,
        PERM_REPORTS_VIEW,
        PERM_REPORTS_WRITE,
        PERM_SETTINGS_COMPANY,
        PERM_SETTINGS_INTEGRATIONS,
        PERM_SETTINGS_GRADE,
        PERM_STAFF_VIEW,
        PERM_STAFF_WRITE,
        PERM_COURSES_VIEW,
        PERM_COURSES_WRITE,
        PERM_ROOMS_VIEW,
        PERM_ROOMS_WRITE,
        PERM_HOLIDAYS_VIEW,
        PERM_HOLIDAYS_WRITE,
        PERM_ARCHIVE_VIEW,
        PERM_ARCHIVE_WRITE,
        PERM_TAGS_VIEW,
        PERM_TAGS_WRITE,
        PERM_FORMS_VIEW,
        PERM_FORMS_WRITE,
        PERM_LOGS_VIEW,
        PERM_BRANCH_VIEW,
        PERM_PROFILE_EDIT,
        PERM_BILLING_VIEW,
    },
)

ROLE_CEO = 'ceo'
ROLE_ADMINISTRATOR = 'administrator'
ROLE_BRANCH_DIRECTOR = 'branch_director'
ROLE_LIMITED_ADMIN = 'limited_admin'
ROLE_MARKETER = 'marketer'
ROLE_CASHIER = 'cashier'
ROLE_TEACHER = 'teacher'

ROLE_LABELS: dict[str, str] = {
    ROLE_CEO: 'CEO',
    ROLE_ADMINISTRATOR: 'Administrator',
    ROLE_BRANCH_DIRECTOR: 'Branch director',
    ROLE_LIMITED_ADMIN: 'Limited admin',
    ROLE_MARKETER: 'Marketer',
    ROLE_CASHIER: 'Cashier',
    ROLE_TEACHER: 'Teacher',
}

_ADMIN_OFFICE: frozenset[str] = frozenset(
    {
        PERM_DASHBOARD_VIEW,
        PERM_LEADS_VIEW,
        PERM_LEADS_WRITE,
        PERM_TEACHERS_VIEW,
        PERM_TEACHERS_WRITE,
        PERM_GROUPS_VIEW,
        PERM_GROUPS_WRITE,
        PERM_GROUPS_EXPORT,
        PERM_STUDENTS_VIEW,
        PERM_STUDENTS_WRITE,
        PERM_REMINDERS_VIEW,
        PERM_REMINDERS_WRITE,
        PERM_RATING_VIEW,
        PERM_RATING_WRITE,
        PERM_ATTENDANCE_VIEW,
        PERM_ATTENDANCE_WRITE,
        PERM_TEACHER_ATTENDANCE_VIEW,
        PERM_TEACHER_ATTENDANCE_WRITE,
        PERM_REPORTS_VIEW,
        PERM_REPORTS_WRITE,
        PERM_COURSES_VIEW,
        PERM_COURSES_WRITE,
        PERM_ROOMS_VIEW,
        PERM_ROOMS_WRITE,
        PERM_HOLIDAYS_VIEW,
        PERM_HOLIDAYS_WRITE,
        PERM_ARCHIVE_VIEW,
        PERM_ARCHIVE_WRITE,
        PERM_TAGS_VIEW,
        PERM_TAGS_WRITE,
        PERM_FORMS_VIEW,
        PERM_FORMS_WRITE,
        PERM_LOGS_VIEW,
        PERM_BRANCH_VIEW,
        PERM_PROFILE_EDIT,
    },
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_CEO: ALL_PERMISSIONS,
    ROLE_ADMINISTRATOR: _ADMIN_OFFICE,
    ROLE_BRANCH_DIRECTOR: _ADMIN_OFFICE,
    ROLE_LIMITED_ADMIN: frozenset(
        {
            PERM_DASHBOARD_VIEW,
            PERM_GROUPS_VIEW,
            PERM_GROUPS_WRITE,
            PERM_GROUPS_EXPORT,
            PERM_COURSES_VIEW,
            PERM_COURSES_WRITE,
            PERM_TEACHERS_VIEW,
            PERM_TEACHERS_WRITE,
            PERM_STUDENTS_VIEW,
            PERM_STUDENTS_WRITE,
            PERM_BRANCH_VIEW,
            PERM_PROFILE_EDIT,
            PERM_RATING_VIEW,
            PERM_RATING_WRITE,
        },
    ),
    ROLE_MARKETER: frozenset(
        {
            PERM_DASHBOARD_VIEW,
            PERM_LEADS_VIEW,
            PERM_LEADS_WRITE,
            PERM_REPORTS_VIEW,
            PERM_PROFILE_EDIT,
        },
    ),
    ROLE_CASHIER: frozenset(
        {
            PERM_DASHBOARD_VIEW,
            PERM_STUDENTS_VIEW,
            PERM_STUDENTS_WRITE,
            PERM_FINANCE_VIEW,
            PERM_FINANCE_WRITE,
            PERM_REPORTS_VIEW,
            PERM_BRANCH_VIEW,
            PERM_PROFILE_EDIT,
        },
    ),
    ROLE_TEACHER: frozenset(
        {
            PERM_DASHBOARD_VIEW,
            PERM_GROUPS_VIEW,
            PERM_STUDENTS_VIEW,
            PERM_RATING_VIEW,
            PERM_RATING_WRITE,
            PERM_ATTENDANCE_VIEW,
            PERM_ATTENDANCE_WRITE,
            PERM_TEACHER_ATTENDANCE_VIEW,
            PERM_REMINDERS_VIEW,
            PERM_BRANCH_VIEW,
            PERM_PROFILE_EDIT,
        },
    ),
}


def get_effective_role(user: User) -> str:
    if user.is_superuser:
        return ROLE_CEO
    if user.user_type == User.UserType.TEACHER:
        return ROLE_TEACHER
    if user.staff_role:
        return user.staff_role
    if user.user_type == User.UserType.STAFF:
        return ROLE_ADMINISTRATOR
    return ROLE_ADMINISTRATOR


def get_role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role.replace('_', ' ').title())


def get_user_permissions(user: User) -> frozenset[str]:
    role = get_effective_role(user)
    perms = ROLE_PERMISSIONS.get(role, frozenset())
    if role == ROLE_CEO:
        return ALL_PERMISSIONS
    return perms


def user_has_permission(user: User, permission: str | None) -> bool:
    if permission is None:
        return True
    if not user or not user.is_authenticated:
        return False
    if get_effective_role(user) == ROLE_CEO:
        return True
    return permission in get_user_permissions(user)


def user_is_teacher(user: User) -> bool:
    return get_effective_role(user) == ROLE_TEACHER
