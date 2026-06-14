export interface NavLink {
  type: 'link';
  label: string;
  to: string;
  icon: string;
  permission?: string;
}

export interface NavHeader {
  type: 'header';
  label: string;
}

export type NavFlyoutItem = NavLink | NavHeader;

export interface NavSection {
  id: string;
  label: string;
  icon: string;
  to?: string;
  permission?: string;
  children?: NavFlyoutItem[];
  paths?: string[];
}

function matchesPath(path: string, prefix: string) {
  return path === prefix || path.startsWith(`${prefix}/`);
}

function childPaths(section: NavSection): string[] {
  if (!section.children) return [];
  return section.children
    .filter((c): c is NavLink => c.type === 'link')
    .map((c) => c.to);
}

function matchesSection(path: string, section: NavSection): boolean {
  if (section.children?.some((c) => c.type === 'link' && matchesPath(path, c.to))) {
    return true;
  }
  if (section.paths?.some((p) => matchesPath(path, p))) {
    if (section.id === 'students' && matchesPath(path, '/students/debtors')) {
      return false;
    }
    return true;
  }
  if (section.to && matchesPath(path, section.to)) {
    if (section.id === 'students' && matchesPath(path, '/students/debtors')) {
      return false;
    }
    return true;
  }
  return false;
}

export function firstFlyoutLink(section: NavSection): NavLink | null {
  const link = section.children?.find((c): c is NavLink => c.type === 'link');
  return link ?? null;
}

import { PERM } from '../utils/rbac';

export const primaryNav: NavSection[] = [
  {
    id: 'leads',
    label: 'Leads',
    icon: 'leads',
    to: '/leads',
    paths: ['/leads'],
    permission: PERM.LEADS_VIEW,
  },
  {
    id: 'teachers',
    label: 'Teachers',
    icon: 'teachers',
    to: '/teachers',
    paths: ['/teachers'],
    permission: PERM.TEACHERS_VIEW,
  },
  {
    id: 'groups',
    label: 'Groups',
    icon: 'groups',
    to: '/groups',
    paths: ['/groups'],
    permission: PERM.GROUPS_VIEW,
  },
  {
    id: 'students',
    label: 'Students',
    icon: 'students',
    to: '/students',
    paths: ['/students'],
    permission: PERM.STUDENTS_VIEW,
  },
  {
    id: 'reminders',
    label: 'Reminders',
    icon: 'reminders',
    to: '/reminders',
    paths: ['/reminders'],
    permission: PERM.REMINDERS_VIEW,
  },
  {
    id: 'rating',
    label: 'Rating',
    icon: 'rating',
    to: '/rating',
    paths: ['/rating'],
    permission: PERM.RATING_VIEW,
  },
  {
    id: 'attendance',
    label: 'Attendance reports',
    icon: 'attendance',
    to: '/attendance-reports',
    paths: ['/attendance-reports'],
    permission: PERM.ATTENDANCE_VIEW,
  },
  {
    id: 'teacher-attendance',
    label: 'Teacher attendance reports',
    icon: 'attendance',
    to: '/teacher-attendance-reports',
    paths: ['/teacher-attendance-reports'],
    permission: PERM.TEACHER_ATTENDANCE_VIEW,
  },
  {
    id: 'finance',
    label: 'Finance',
    icon: 'finance',
    permission: PERM.FINANCE_VIEW,
    paths: ['/finance', '/students/debtors'],
    children: [
      { type: 'link', label: 'All payments', to: '/finance/payments', icon: 'coins', permission: PERM.FINANCE_VIEW },
      { type: 'link', label: 'Withdraw', to: '/finance/withdraw', icon: 'coins', permission: PERM.FINANCE_VIEW },
      { type: 'link', label: 'Total Expenses', to: '/finance/cost', icon: 'expenses', permission: PERM.FINANCE_VIEW },
      { type: 'link', label: 'Salaries new', to: '/finance/new-salaries', icon: 'salaries', permission: PERM.FINANCE_VIEW },
      { type: 'link', label: 'Debtors', to: '/students/debtors', icon: 'debtors', permission: PERM.FINANCE_VIEW },
    ],
  },
  {
    id: 'reports',
    label: 'Reports',
    icon: 'reports',
    permission: PERM.REPORTS_VIEW,
    paths: ['/reports'],
    children: [
      { type: 'link', label: 'Conversion reports', to: '/reports/conversion', icon: 'conversion', permission: PERM.REPORTS_VIEW },
      { type: 'link', label: 'Attendance reports', to: '/reports/attendance', icon: 'attendance', permission: PERM.ATTENDANCE_VIEW },
      { type: 'link', label: 'Leads reports', to: '/reports/leads', icon: 'leads-report', permission: PERM.REPORTS_VIEW },
      { type: 'link', label: 'Students left the group', to: '/reports/left-students', icon: 'left-students', permission: PERM.REPORTS_VIEW },
      { type: 'link', label: 'Workly Report', to: '/reports/workly', icon: 'conversion', permission: PERM.REPORTS_VIEW },
    ],
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: 'settings',
    paths: [
      '/settings',
      '/settings-grade',
      '/staff',
      '/courses',
      '/rooms',
      '/holiday',
      '/archive',
      '/tags',
      '/form',
      '/roadmap',
      '/auto-sms',
      '/admin',
      '/left-students',
      '/blog',
    ],
    children: [
      { type: 'link', label: 'SMS settings', to: '/auto-sms', icon: 'auto-sms', permission: PERM.SETTINGS_INTEGRATIONS },
      { type: 'link', label: 'VoIP settings', to: '/admin/voip', icon: 'voip', permission: PERM.SETTINGS_INTEGRATIONS },
      { type: 'link', label: 'Grade', to: '/settings-grade', icon: 'grade', permission: PERM.SETTINGS_GRADE },
      { type: 'header', label: 'CEO' },
      { type: 'link', label: 'General settings', to: '/settings', icon: 'settings', permission: PERM.SETTINGS_COMPANY },
      { type: 'link', label: 'Staff', to: '/staff/list', icon: 'staff', permission: PERM.STAFF_VIEW },
      { type: 'link', label: 'Roadmap', to: '/roadmap', icon: 'roadmap', permission: PERM.SETTINGS_COMPANY },
      { type: 'header', label: 'Office' },
      { type: 'link', label: 'Courses', to: '/courses', icon: 'courses', permission: PERM.COURSES_VIEW },
      { type: 'link', label: 'Rooms', to: '/rooms', icon: 'rooms', permission: PERM.ROOMS_VIEW },
      { type: 'link', label: 'Holidays', to: '/holiday', icon: 'holidays', permission: PERM.HOLIDAYS_VIEW },
      { type: 'link', label: 'Archive', to: '/archive/list', icon: 'archive', permission: PERM.ARCHIVE_VIEW },
      { type: 'link', label: 'Students left the group', to: '/left-students', icon: 'left-students', permission: PERM.REPORTS_VIEW },
      { type: 'header', label: 'Forms' },
      { type: 'link', label: 'Forms', to: '/form', icon: 'puzzle', permission: PERM.FORMS_VIEW },
      { type: 'header', label: 'Blog' },
      { type: 'link', label: 'Tags', to: '/tags', icon: 'tags', permission: PERM.TAGS_VIEW },
      { type: 'link', label: "What's new", to: '/blog/news', icon: 'blog', permission: PERM.TAGS_VIEW },
    ],
  },
];

export function sectionForPath(path: string): NavSection | null {
  const withChildren = primaryNav.filter((s) => s.children);
  for (const section of withChildren) {
    if (matchesSection(path, section)) return section;
  }
  for (const section of primaryNav) {
    if (matchesSection(path, section)) return section;
  }
  if (matchesPath(path, '/dashboard')) {
    return { id: 'dashboard', label: 'Dashboard', icon: 'dashboard', to: '/dashboard/default' };
  }
  return null;
}

export function flyoutSectionForPath(path: string, sections: NavSection[] = primaryNav): NavSection | null {
  for (const section of sections) {
    if (!section.children) continue;
    if (matchesSection(path, section)) return section;
  }
  return null;
}

export function allFlyoutPaths(section: NavSection): string[] {
  return [...(section.paths ?? []), ...childPaths(section)];
}

export function filterFlyoutChildren(
  children: NavFlyoutItem[],
  can: (permission: string) => boolean,
): NavFlyoutItem[] {
  const filtered: NavFlyoutItem[] = [];
  let pendingHeader: NavFlyoutItem | null = null;

  for (const item of children) {
    if (item.type === 'header') {
      pendingHeader = item;
      continue;
    }
    if (item.permission && !can(item.permission)) {
      continue;
    }
    if (pendingHeader) {
      filtered.push(pendingHeader);
      pendingHeader = null;
    }
    filtered.push(item);
  }
  return filtered;
}

export function filterNavSections(
  sections: NavSection[],
  can: (permission: string) => boolean,
): NavSection[] {
  return sections
    .map((section) => {
      if (section.children?.length) {
        const children = filterFlyoutChildren(section.children, can);
        if (children.length === 0) {
          return null;
        }
        const sectionPerm = section.permission;
        if (sectionPerm && !can(sectionPerm)) {
          const hasAnyChildPerm = children.some((c) => c.type === 'link');
          if (!hasAnyChildPerm) {
            return null;
          }
        }
        return { ...section, children };
      }
      if (section.permission && !can(section.permission)) {
        return null;
      }
      return section;
    })
    .filter((section): section is NavSection => section !== null);
}
