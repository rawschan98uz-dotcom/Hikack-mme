/** Permission codes — mirror backend accounts/rbac.py */

export const PERM = {
  DASHBOARD_VIEW: 'dashboard.view',
  LEADS_VIEW: 'leads.view',
  LEADS_WRITE: 'leads.write',
  TEACHERS_VIEW: 'teachers.view',
  TEACHERS_WRITE: 'teachers.write',
  GROUPS_VIEW: 'groups.view',
  GROUPS_WRITE: 'groups.write',
  GROUPS_EXPORT: 'groups.export',
  STUDENTS_VIEW: 'students.view',
  STUDENTS_WRITE: 'students.write',
  REMINDERS_VIEW: 'reminders.view',
  REMINDERS_WRITE: 'reminders.write',
  RATING_VIEW: 'rating.view',
  RATING_WRITE: 'rating.write',
  ATTENDANCE_VIEW: 'attendance.view',
  ATTENDANCE_WRITE: 'attendance.write',
  TEACHER_ATTENDANCE_VIEW: 'teacher_attendance.view',
  TEACHER_ATTENDANCE_WRITE: 'teacher_attendance.write',
  FINANCE_VIEW: 'finance.view',
  FINANCE_WRITE: 'finance.write',
  FINANCE_COMPANY: 'finance.company',
  /** Student payments: the administrator takes payments and gives refunds; only the CEO deletes. */
  PAYMENTS_VIEW: 'payments.view',
  PAYMENTS_WRITE: 'payments.write',
  PAYMENTS_DELETE: 'payments.delete',
  REPORTS_VIEW: 'reports.view',
  REPORTS_WRITE: 'reports.write',
  SETTINGS_COMPANY: 'settings.company',
  SETTINGS_INTEGRATIONS: 'settings.integrations',
  SETTINGS_GRADE: 'settings.grade',
  STAFF_VIEW: 'staff.view',
  STAFF_WRITE: 'staff.write',
  COURSES_VIEW: 'courses.view',
  COURSES_WRITE: 'courses.write',
  ROOMS_VIEW: 'rooms.view',
  ROOMS_WRITE: 'rooms.write',
  HOLIDAYS_VIEW: 'holidays.view',
  HOLIDAYS_WRITE: 'holidays.write',
  ARCHIVE_VIEW: 'archive.view',
  ARCHIVE_WRITE: 'archive.write',
  TAGS_VIEW: 'tags.view',
  TAGS_WRITE: 'tags.write',
  FORMS_VIEW: 'forms.view',
  FORMS_WRITE: 'forms.write',
  LOGS_VIEW: 'logs.view',
  BRANCH_VIEW: 'branch.view',
  PROFILE_EDIT: 'profile.edit',
  BILLING_VIEW: 'billing.view',
} as const;

export type Permission = (typeof PERM)[keyof typeof PERM];

export function hasPermission(permissions: readonly string[] | undefined, perm: string): boolean {
  if (!permissions?.length) return false;
  return permissions.includes(perm);
}

export function canAny(permissions: readonly string[] | undefined, perms: string[]): boolean {
  return perms.some((p) => hasPermission(permissions, p));
}

/** Longest-prefix match for route → required view permission */
const ROUTE_PERMISSION_RULES: readonly [string, string | null][] = [
  ['/students/debtors', PERM.PAYMENTS_VIEW],
  ['/finance/', PERM.FINANCE_VIEW],
  ['/finance/payments', PERM.PAYMENTS_VIEW],
  ['/finance/pnl', PERM.FINANCE_COMPANY],
  ['/finance/cost', PERM.FINANCE_COMPANY],
  ['/finance/withdraw', PERM.FINANCE_COMPANY],
  ['/reports/attendance', PERM.ATTENDANCE_VIEW],
  // Debts of the students who left are money: not for the marketer
  ['/reports/left-students', PERM.PAYMENTS_VIEW],
  // The students' months and their unpaid tails are money too
  ['/reports/months', PERM.PAYMENTS_VIEW],
  ['/reports/', PERM.REPORTS_VIEW],
  ['/attendance-reports', PERM.ATTENDANCE_VIEW],
  ['/teacher-attendance-reports', PERM.TEACHER_ATTENDANCE_VIEW],
  ['/dashboard/', PERM.DASHBOARD_VIEW],
  ['/leads', PERM.LEADS_VIEW],
  ['/teachers', PERM.TEACHERS_VIEW],
  ['/groups', PERM.GROUPS_VIEW],
  ['/students', PERM.STUDENTS_VIEW],
  ['/reminders', PERM.REMINDERS_VIEW],
  ['/rating', PERM.RATING_VIEW],
  ['/settings-grade', PERM.SETTINGS_GRADE],
  ['/settings', PERM.SETTINGS_COMPANY],
  ['/admin/voip', PERM.SETTINGS_INTEGRATIONS],
  ['/auto-sms', PERM.SETTINGS_INTEGRATIONS],
  ['/staff/', PERM.STAFF_VIEW],
  ['/courses', PERM.COURSES_VIEW],
  ['/rooms', PERM.ROOMS_VIEW],
  ['/holiday', PERM.HOLIDAYS_VIEW],
  ['/archive/', PERM.ARCHIVE_VIEW],
  ['/left-students', PERM.PAYMENTS_VIEW],
  ['/tags', PERM.TAGS_VIEW],
  ['/form', PERM.FORMS_VIEW],
  ['/blog/', PERM.TAGS_VIEW],
  ['/sms', PERM.LOGS_VIEW],
  ['/call', PERM.LOGS_VIEW],
  ['/history/logs', PERM.LOGS_VIEW],
  ['/roadmap', PERM.SETTINGS_COMPANY],
  ['/user/profile', null],
];

export function permissionForRoute(path: string): string | null {
  const normalized = path.split('?')[0];
  let best: string | null = PERM.DASHBOARD_VIEW;
  let bestLen = 0;

  for (const [prefix, perm] of ROUTE_PERMISSION_RULES) {
    if (normalized === prefix || normalized.startsWith(`${prefix}/`) || normalized.startsWith(prefix)) {
      if (prefix.length >= bestLen) {
        bestLen = prefix.length;
        best = perm;
      }
    }
  }
  return best;
}

/**
 * Pages a teacher does not use: students are seen inside own groups, attendance and grading,
 * and "Reports" only duplicated the student attendance page.
 */
const TEACHER_HIDDEN_PREFIXES = ['/students', '/reports/', '/left-students'];

export function isHiddenForTeacher(path: string): boolean {
  const normalized = path.split('?')[0];
  return TEACHER_HIDDEN_PREFIXES.some((prefix) => normalized.startsWith(prefix));
}

export function canAccessRoute(path: string, permissions: readonly string[] | undefined): boolean {
  const required = permissionForRoute(path);
  if (required === null) return true;
  return hasPermission(permissions, required);
}
