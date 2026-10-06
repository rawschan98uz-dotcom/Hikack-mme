"""Map HTTP method + API path to required RBAC permission."""

from __future__ import annotations

import re
from accounts import rbac as P

# Each rule: (methods tuple, regex on path after /v1/, permission or None to allow)
ROUTE_RULES: list[tuple[tuple[str, ...], str, str | None]] = [
    # Auth & public
    (('POST',), r'^auth/login$', None),
    (('GET',), r'^company/subdomain/', None),
    (('GET', 'POST'), r'^auth/me$', None),
    (('PATCH',), r'^auth/me$', P.PERM_PROFILE_EDIT),
    (('POST',), r'^payments/click/webhook$', None),
    (('POST',), r'^payments/payme/webhook$', None),

    (('GET',), r'^branch$', P.PERM_BRANCH_VIEW),
    (('GET',), r'^dashboard$', P.PERM_DASHBOARD_VIEW),
    (('GET',), r'^schedule$', P.PERM_GROUPS_VIEW),

    (('GET',), r'^groups$', P.PERM_GROUPS_VIEW),
    (('POST',), r'^groups$', P.PERM_GROUPS_WRITE),
    (('GET',), r'^groups/\d+$', P.PERM_GROUPS_VIEW),
    (('PATCH',), r'^groups/\d+$', P.PERM_GROUPS_WRITE),
    (('DELETE',), r'^groups/\d+$', P.PERM_GROUPS_WRITE),

    (('GET',), r'^students$', P.PERM_STUDENTS_VIEW),
    (('POST',), r'^students$', P.PERM_STUDENTS_WRITE),
    (('POST',), r'^students/import$', P.PERM_STUDENTS_WRITE),
    (('GET',), r'^students/\d+$', P.PERM_STUDENTS_VIEW),
    (('GET',), r'^students/\d+/payments$', P.PERM_STUDENTS_VIEW),
    (('POST',), r'^students/\d+/payment-preview$', P.PERM_PAYMENTS_WRITE),
    (('GET',), r'^students/\d+/payment-links$', P.PERM_STUDENTS_VIEW),
    (('POST',), r'^students/\d+/send-payment-link$', P.PERM_STUDENTS_WRITE),
    (('PATCH', 'POST'), r'^students/\d+$', P.PERM_STUDENTS_WRITE),
    (('DELETE',), r'^students/\d+$', P.PERM_STUDENTS_WRITE),
    (('POST', 'DELETE'), r'^students/\d+/photo$', P.PERM_STUDENTS_WRITE),
    (('GET',), r'^telegram/config$', P.PERM_STUDENTS_VIEW),

    (('GET',), r'^leads$', P.PERM_LEADS_VIEW),
    (('POST',), r'^leads$', P.PERM_LEADS_WRITE),
    (('GET',), r'^leads/\d+$', P.PERM_LEADS_VIEW),
    (('PATCH',), r'^leads/\d+$', P.PERM_LEADS_WRITE),
    (('POST',), r'^leads/\d+/archive$', P.PERM_LEADS_WRITE),
    (('POST',), r'^leads/\d+/convert$', P.PERM_LEADS_WRITE),

    (('GET',), r'^courses$', P.PERM_COURSES_VIEW),
    (('POST',), r'^courses$', P.PERM_COURSES_WRITE),
    (('GET',), r'^courses/\d+$', P.PERM_COURSES_VIEW),
    (('PATCH', 'DELETE'), r'^courses/\d+$', P.PERM_COURSES_WRITE),
    # Price history: the view lets only the CEO through
    (('PATCH', 'DELETE'), r'^courses/\d+/prices/\d+$', P.PERM_COURSES_WRITE),

    (('GET',), r'^user$', P.PERM_TEACHERS_VIEW),
    (('POST',), r'^user/staff$', P.PERM_STAFF_WRITE),
    (('GET',), r'^user/staff$', P.PERM_STAFF_VIEW),
    (('GET',), r'^user/staff/\d+$', P.PERM_STAFF_VIEW),
    (('PATCH',), r'^user/staff/\d+$', P.PERM_STAFF_WRITE),
    (('DELETE',), r'^user/staff/\d+$', P.PERM_STAFF_DELETE),
    (('POST',), r'^user/teacher/import$', P.PERM_TEACHERS_WRITE),
    (('POST',), r'^user/teacher$', P.PERM_TEACHERS_WRITE),
    (('GET',), r'^user/teacher/\d+$', P.PERM_TEACHERS_VIEW),
    (('PATCH',), r'^user/teacher/\d+$', P.PERM_TEACHERS_WRITE),
    (('DELETE',), r'^user/teacher/\d+$', P.PERM_TEACHERS_DELETE),

    (('POST',), r'^user/staff/import$', P.PERM_STAFF_WRITE),
    # Student payments: the administrator takes payments and gives refunds; only the CEO deletes
    (('GET',), r'^replenishments$', P.PERM_PAYMENTS_VIEW),
    (('POST',), r'^replenishments$', P.PERM_PAYMENTS_WRITE),
    (('POST',), r'^(?:replenishments|payments)/\d+/refund$', P.PERM_PAYMENTS_WRITE),
    (('GET',), r'^replenishments/\d+$', P.PERM_PAYMENTS_VIEW),
    (('PATCH',), r'^replenishments/\d+$', P.PERM_PAYMENTS_WRITE),
    (('DELETE',), r'^replenishments/\d+$', P.PERM_PAYMENTS_DELETE),

    (('GET',), r'^withdraws$', P.PERM_FINANCE_COMPANY),
    (('POST',), r'^withdraws$', P.PERM_FINANCE_WRITE),
    (('GET',), r'^withdraws/\d+$', P.PERM_FINANCE_COMPANY),
    (('PATCH', 'DELETE'), r'^withdraws/\d+$', P.PERM_FINANCE_WRITE),

    (('GET',), r'^expense$', P.PERM_FINANCE_COMPANY),
    (('POST',), r'^expense$', P.PERM_FINANCE_WRITE),
    (('GET',), r'^expense_types$', P.PERM_FINANCE_COMPANY),
    (('POST',), r'^expense_types$', P.PERM_FINANCE_WRITE),
    (('GET',), r'^expense_types/\d+$', P.PERM_FINANCE_COMPANY),
    (('PATCH', 'DELETE'), r'^expense_types/\d+$', P.PERM_FINANCE_WRITE),
    (('GET', 'PATCH', 'DELETE'), r'^expense/\d+$', P.PERM_FINANCE_WRITE),

    (('GET',), r'^salary-settings$', P.PERM_FINANCE_VIEW),
    (('POST',), r'^salary-settings$', P.PERM_FINANCE_WRITE),
    (('GET', 'PATCH', 'DELETE'), r'^salary-settings/\d+$', P.PERM_FINANCE_WRITE),
    (('GET',), r'^finance/payroll$', P.PERM_FINANCE_VIEW),
    (('POST',), r'^finance/payroll/pay$', P.PERM_FINANCE_WRITE),
    (('DELETE',), r'^finance/payroll/payouts/\d+$', P.PERM_FINANCE_WRITE),
    # Closing a month and salary corrections: finance.write here, and the CEO only (checked in the view)
    (('POST',), r'^finance/payroll/adjustments$', P.PERM_FINANCE_WRITE),
    (('DELETE',), r'^finance/payroll/adjustments/\d+$', P.PERM_FINANCE_WRITE),
    (('GET',), r'^finance/months$', P.PERM_FINANCE_VIEW),
    (('POST',), r'^finance/months/(?:close|reopen)$', P.PERM_FINANCE_WRITE),

    (('GET',), r'^reports/pnl$', P.PERM_FINANCE_COMPANY),
    (('GET',), r'^reports/conversion$', P.PERM_REPORTS_VIEW),
    # Debts of the students who left are money: not for the marketer (reports audit, 2026-09-29)
    (('GET',), r'^reports/left-students$', P.PERM_PAYMENTS_VIEW),
    (('GET',), r'^reports/months$', P.PERM_PAYMENTS_VIEW),
    (('GET',), r'^reports/attendance$', P.PERM_ATTENDANCE_VIEW),
    (('POST',), r'^reports/attendance$', P.PERM_ATTENDANCE_WRITE),
    (('GET',), r'^reports/attendance/(day|month)$', P.PERM_ATTENDANCE_VIEW),
    (('GET',), r'^reports/attendance/\d+$', P.PERM_ATTENDANCE_VIEW),
    (('PATCH', 'DELETE'), r'^reports/attendance/\d+$', P.PERM_ATTENDANCE_WRITE),

    (('GET',), r'^reports/teacher-attendance$', P.PERM_TEACHER_ATTENDANCE_VIEW),
    (('POST',), r'^reports/teacher-attendance$', P.PERM_TEACHER_ATTENDANCE_WRITE),
    (('GET',), r'^reports/teacher-attendance/lessons$', P.PERM_TEACHER_ATTENDANCE_VIEW),
    (('GET',), r'^reports/teacher-attendance/\d+$', P.PERM_TEACHER_ATTENDANCE_VIEW),
    (('PATCH', 'DELETE'), r'^reports/teacher-attendance/\d+$', P.PERM_TEACHER_ATTENDANCE_WRITE),
    (('POST',), r'^teacher-attendance/self-checkin$', P.PERM_TEACHER_ATTENDANCE_VIEW),
    (('GET',), r'^teacher-attendance/today$', P.PERM_TEACHER_ATTENDANCE_VIEW),
    (('GET',), r'^teacher-attendance/my$', P.PERM_TEACHER_ATTENDANCE_VIEW),


    (('GET',), r'^reminders$', P.PERM_REMINDERS_VIEW),
    (('POST',), r'^reminders$', P.PERM_REMINDERS_WRITE),
    (('GET',), r'^reminders/\d+$', P.PERM_REMINDERS_VIEW),
    (('PATCH', 'DELETE'), r'^reminders/\d+$', P.PERM_REMINDERS_WRITE),
    # A teacher may close reminders given to them (checked in the view)
    (('POST',), r'^reminders/\d+/complete$', P.PERM_REMINDERS_VIEW),
    (('GET',), r'^reminders/assignees$', P.PERM_REMINDERS_WRITE),
    (('GET',), r'^reminders/summary$', P.PERM_REMINDERS_VIEW),

    (('GET',), r'^scores/branch$', P.PERM_RATING_VIEW),
    (('POST',), r'^scores/branch$', P.PERM_RATING_WRITE),
    (('POST',), r'^scores/bulk$', P.PERM_RATING_WRITE),
    (('GET',), r'^scores/groups$', P.PERM_RATING_VIEW),
    (('GET',), r'^scores/sheet$', P.PERM_RATING_WRITE),
    (('GET',), r'^scores/history$', P.PERM_RATING_VIEW),
    (('GET', 'PATCH', 'DELETE'), r'^scores/\d+$', P.PERM_RATING_WRITE),

    (('POST',), r'^room$', P.PERM_ROOMS_WRITE),
    (('GET',), r'^room$', P.PERM_ROOMS_VIEW),
    (('GET',), r'^room/\d+$', P.PERM_ROOMS_VIEW),
    (('PATCH', 'DELETE'), r'^room/\d+$', P.PERM_ROOMS_WRITE),

    (('POST',), r'^holidays$', P.PERM_HOLIDAYS_WRITE),
    (('GET',), r'^holidays$', P.PERM_HOLIDAYS_VIEW),
    (('GET',), r'^holidays/\d+$', P.PERM_HOLIDAYS_VIEW),
    (('PATCH', 'DELETE'), r'^holidays/\d+$', P.PERM_HOLIDAYS_WRITE),

    (('GET',), r'^archiveReasons$', P.PERM_ARCHIVE_VIEW),
    (('POST',), r'^archive/list$', P.PERM_ARCHIVE_WRITE),
    (('GET',), r'^archive/list$', P.PERM_ARCHIVE_VIEW),
    (('POST',), r'^archive/list/bulk$', P.PERM_ARCHIVE_WRITE),
    (('GET',), r'^archive/list/\d+$', P.PERM_ARCHIVE_VIEW),
    (('DELETE',), r'^archive/list/\d+$', P.PERM_ARCHIVE_WRITE),
    (('POST',), r'^archive/list/\d+/restore$', P.PERM_ARCHIVE_WRITE),

    (('POST',), r'^tags$', P.PERM_TAGS_WRITE),
    (('GET',), r'^tags$', P.PERM_TAGS_VIEW),
    (('GET',), r'^tags/\d+$', P.PERM_TAGS_VIEW),
    (('PATCH', 'DELETE'), r'^tags/\d+$', P.PERM_TAGS_WRITE),

    (('POST',), r'^leadForm$', P.PERM_FORMS_WRITE),
    (('GET',), r'^leadForm$', P.PERM_FORMS_VIEW),
    (('GET',), r'^leadForm/\d+$', P.PERM_FORMS_VIEW),
    (('PATCH', 'DELETE'), r'^leadForm/\d+$', P.PERM_FORMS_WRITE),

    (('GET',), r'^sms/report$', P.PERM_LOGS_VIEW),
    (('GET',), r'^call/logs$', P.PERM_LOGS_VIEW),
    (('GET',), r'^history/logs$', P.PERM_LOGS_VIEW),

    (('GET', 'POST'), r'^company/settings$', P.PERM_SETTINGS_COMPANY),

    (('GET',), r'^company/\d+$', P.PERM_SETTINGS_COMPANY),
    (('GET',), r'^company/\d+/payments$', P.PERM_BILLING_VIEW),
]

_COMPILED_RULES: list[tuple[tuple[str, ...], re.Pattern[str], str | None]] | None = None


def _compile_rules() -> list[tuple[tuple[str, ...], re.Pattern[str], str | None]]:
    global _COMPILED_RULES
    if _COMPILED_RULES is None:
        _COMPILED_RULES = [
            (methods, re.compile(pattern), perm)
            for methods, pattern, perm in ROUTE_RULES
        ]
    return _COMPILED_RULES


def resolve_permission(method: str, path: str) -> str | None:
    """Return required permission for path, or None if route is open / unknown."""
    normalized = path.strip('/')
    if normalized.startswith('v1/'):
        normalized = normalized[3:]
    elif normalized == 'v1':
        normalized = ''

    method = method.upper()
    matched_perm: str | None = None
    matched = False

    for methods, pattern, perm in _compile_rules():
        if method not in methods:
            continue
        if pattern.search(normalized):
            matched = True
            matched_perm = perm
            break

    if not matched:
        return P.PERM_DENIED
    return matched_perm
