import { createRouter, createWebHistory } from 'vue-router';

import { useAuthStore } from '../stores/auth';
import { filterNavSections, primaryNav } from '../config/navigation';
import { canAccessRoute } from '../utils/rbac';
import AppLayout from '../layouts/AppLayout.vue';
import ActivityLogsView from '../views/ActivityLogsView.vue';
import ArchiveView from '../views/ArchiveView.vue';
import AutoSmsView from '../views/AutoSmsView.vue';
import CallLogView from '../views/CallLogView.vue';
import CoursesView from '../views/CoursesView.vue';
import DashboardView from '../views/DashboardView.vue';
import FinanceExpensesView from '../views/FinanceExpensesView.vue';
import FinancePaymentsView from '../views/FinancePaymentsView.vue';
import FinanceSalariesView from '../views/FinanceSalariesView.vue';
import FinanceWithdrawView from '../views/FinanceWithdrawView.vue';
import FormsView from '../views/FormsView.vue';
import GradeSettingsView from '../views/GradeSettingsView.vue';
import GroupsView from '../views/GroupsView.vue';
import HolidaysView from '../views/HolidaysView.vue';
import LeadsView from '../views/LeadsView.vue';
import LoginView from '../views/LoginView.vue';
import ProfileView from '../views/ProfileView.vue';
import RatingView from '../views/RatingView.vue';
import RemindersView from '../views/RemindersView.vue';
import ReportsAttendanceView from '../views/ReportsAttendanceView.vue';
import ReportsConversionView from '../views/ReportsConversionView.vue';
import ReportsLeftStudentsView from '../views/ReportsLeftStudentsView.vue';
import ReportsLeadsView from '../views/ReportsLeadsView.vue';
import ReportsWorklyView from '../views/ReportsWorklyView.vue';
import RoadmapView from '../views/RoadmapView.vue';
import RoomsView from '../views/RoomsView.vue';
import SettingsView from '../views/SettingsView.vue';
import SmsLogView from '../views/SmsLogView.vue';
import StaffView from '../views/StaffView.vue';
import StudentsView from '../views/StudentsView.vue';
import TagsView from '../views/TagsView.vue';
import TeacherAttendanceReportsView from '../views/TeacherAttendanceReportsView.vue';
import TeachersView from '../views/TeachersView.vue';
import VoipSettingsView from '../views/VoipSettingsView.vue';
import WhatsNewView from '../views/WhatsNewView.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', redirect: '/dashboard/default' },
        { path: 'dashboard/default', name: 'dashboard', component: DashboardView },
        { path: 'leads', component: LeadsView },
        { path: 'teachers', component: TeachersView },
        { path: 'teachers/list', component: TeachersView },
        { path: 'groups', component: GroupsView },
        { path: 'groups/list', component: GroupsView },
        { path: 'students', component: StudentsView },
        { path: 'students/list', component: StudentsView },
        { path: 'students/debtors', component: StudentsView },
        { path: 'user/profile', component: ProfileView },
        { path: 'reminders', component: RemindersView },
        { path: 'rating', component: RatingView },
        { path: 'attendance-reports', component: ReportsAttendanceView },
        { path: 'teacher-attendance-reports', component: TeacherAttendanceReportsView },
        { path: 'finance/payments', component: FinancePaymentsView },
        { path: 'finance/withdraw', component: FinanceWithdrawView },
        { path: 'finance/cost', component: FinanceExpensesView },
        { path: 'finance/new-salaries', component: FinanceSalariesView },
        { path: 'reports/conversion', component: ReportsConversionView },
        { path: 'reports/attendance', component: ReportsAttendanceView },
        { path: 'reports/leads', component: ReportsLeadsView },
        { path: 'reports/left-students', component: ReportsLeftStudentsView },
        { path: 'reports/workly', component: ReportsWorklyView },
        { path: 'settings', component: SettingsView },
        { path: 'settings-grade', component: GradeSettingsView },
        { path: 'admin/voip', component: VoipSettingsView },
        { path: 'roadmap', component: RoadmapView },
        { path: 'left-students', component: ReportsLeftStudentsView },
        {
          path: 'blog/news',
          component: WhatsNewView,
        },
        { path: 'courses', component: CoursesView },
        { path: 'courses/list', component: CoursesView },
        { path: 'rooms', component: RoomsView },
        { path: 'rooms/list', component: RoomsView },
        { path: 'holiday', component: HolidaysView },
        { path: 'staff/list', component: StaffView },
        { path: 'archive/list', component: ArchiveView },
        { path: 'sms', component: SmsLogView },
        { path: 'sms/logs', component: SmsLogView },
        { path: 'call', component: CallLogView },
        { path: 'call/logs', component: CallLogView },
        { path: 'history/logs', component: ActivityLogsView },
        { path: 'auto-sms', component: AutoSmsView },
        { path: 'tags', component: TagsView },
        { path: 'form', component: FormsView },
        { path: 'form/list', component: FormsView },
        { path: ':pathMatch(.*)*', redirect: '/dashboard/default' },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (to.meta.public) {
    if (auth.token && to.name === 'login') return '/dashboard/default';
    return true;
  }
  if (!auth.token) return '/login';
  if (!auth.user) {
    try {
      await auth.fetchMe();
    } catch {
      auth.logout();
      return '/login';
    }
  }
  if (auth.user && !canAccessRoute(to.path, auth.user.permissions)) {
    if (auth.can('dashboard.view')) {
      return '/dashboard/default';
    }
    const fallback = filterNavSections(primaryNav, (p) => auth.can(p))[0];
    if (fallback?.to) return fallback.to;
    const firstChild = fallback?.children?.find((c) => c.type === 'link');
    if (firstChild && firstChild.type === 'link') return firstChild.to;
    auth.logout();
    return '/login';
  }
  return true;
});

export default router;
