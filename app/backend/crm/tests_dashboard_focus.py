"""The top of the dashboard depends on the role: money for the head, the day for the office, lessons for a teacher."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm.models import AttendanceRecord, Course, CoursePrice, Group, Lead, Student
from finance.models import Payment
from org.models import Branch, Company


class DashboardFocusTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.today = timezone.localdate()
        self.company = Company.objects.create(name='Focus Co', subdomain='focusco')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.ceo = User.objects.create_user(
            phone='998909009901', password='password123', first_name='C', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.admin = User.objects.create_user(
            phone='998909009902', password='password123', first_name='A', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.ADMINISTRATOR, branch=self.branch,
        )
        self.teacher = User.objects.create_user(
            phone='998909009903', password='password123', first_name='T', company=self.company,
            user_type=User.UserType.TEACHER,
        )
        self.other_teacher = User.objects.create_user(
            phone='998909009904', password='password123', first_name='O', company=self.company,
            user_type=User.UserType.TEACHER,
        )
        for teacher in (self.teacher, self.other_teacher):
            TeacherBranch.objects.create(teacher=teacher, branch=self.branch)
        course = Course.objects.create(company=self.company, name='Math', code='m1', price=500_000)
        CoursePrice.objects.filter(course=course).update(valid_from=self.today - timedelta(days=400))
        weekday = [self.today.weekday()]
        self.group = Group.objects.create(
            company=self.company, branch=self.branch, name='Today A', course=course, teacher=self.teacher,
            days=Group.Days.CUSTOM, weekdays=weekday,
        )
        self.other_group = Group.objects.create(
            company=self.company, branch=self.branch, name='Today B', course=course, teacher=self.other_teacher,
            days=Group.Days.CUSTOM, weekdays=weekday,
        )
        # Started 40 days ago and never paid: owes for the first month
        self.debtor = Student.objects.create(
            company=self.company, branch=self.branch, group=self.group, first_name='Debtor', phone='901110001',
            trial_date=self.today - timedelta(days=40),
        )
        AttendanceRecord.objects.create(
            company=self.company, group=self.group, student=self.debtor, attend_date=self.today, status=1,
        )
        Payment.objects.create(
            company=self.company, student_name='Cash', amount=300_000,
            transaction_type=Payment.TransactionType.PAYMENT, payment_date=self.today,
        )
        Payment.objects.create(
            company=self.company, student_name='Old', amount=900_000,
            transaction_type=Payment.TransactionType.PAYMENT, payment_date=self.today.replace(day=1) - timedelta(days=1),
        )
        Lead.objects.create(
            company=self.company, branch=self.branch, first_name='Trial', phone='901110002',
            stage=Lead.Stage.TRIAL_BOOKED, trial_date=self.today,
        )

    def focus(self, user):
        self.client.force_authenticate(user)
        res = self.client.get('/v1/dashboard')
        self.assertEqual(res.status_code, 200)
        return res.json()['data']['focus']

    def test_head_sees_money_debts_and_leads(self):
        focus = self.focus(self.ceo)
        self.assertEqual(focus['money']['today'], 300_000)
        self.assertEqual(focus['money']['month'], 300_000)  # last month's payment is not this month
        self.assertEqual(focus['debts']['count'], 1)
        self.assertGreater(focus['debts']['total'], 0)
        self.assertEqual([row['id'] for row in focus['call_list']], [self.debtor.id])
        self.assertEqual(focus['new_leads'], {'today': 1, 'week': 1})
        self.assertEqual([lead['full_name'] for lead in focus['trials_today']], ['Trial'])
        lessons = {row['name']: row for row in focus['lessons_today']}
        self.assertEqual(set(lessons), {'Today A', 'Today B'})
        self.assertTrue(lessons['Today A']['marked'])
        self.assertFalse(lessons['Today B']['marked'])
        self.assertEqual(focus['attendance_today'], {'present': 1, 'late': 0, 'absent': 0})

    def test_administrator_sees_the_day_but_not_company_money(self):
        focus = self.focus(self.admin)
        self.assertNotIn('money', focus)
        self.assertEqual(focus['debts']['count'], 1)
        self.assertEqual(len(focus['lessons_today']), 2)

    def test_teacher_sees_only_own_lessons_and_no_money(self):
        focus = self.focus(self.teacher)
        self.assertEqual([row['name'] for row in focus['lessons_today']], ['Today A'])
        for key in ('money', 'debts', 'call_list', 'new_leads', 'trials_today'):
            self.assertNotIn(key, focus)
