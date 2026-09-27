"""Teachers audit: safe delete, archived teachers, branch removal, reminders visibility."""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm.models import Group, Student
from finance.models import Payment, SalarySetting
from operations.models import Reminder
from org.models import Branch, Company


class TeacherAuditTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Teach Co', subdomain='teachco')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.other_branch = Branch.objects.create(company=self.company, name='Second')
        self.ceo = User.objects.create_user(
            phone='998909008801', password='password123', first_name='C', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.teacher = User.objects.create_user(
            phone='998909008802', password='password123', first_name='Tom', company=self.company,
            user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=self.teacher, branch=self.branch)
        self.client.force_authenticate(self.ceo)

    def test_delete_teacher_with_salary_setting_archives_instead_of_crashing(self):
        SalarySetting.objects.create(
            company=self.company, teacher=self.teacher, teacher_name='Tom',
            salary_type=SalarySetting.SalaryType.FIXED, amount=1000000,
        )
        res = self.client.delete(f'/v1/user/teacher/{self.teacher.id}')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()['data'].get('archived'))
        self.teacher.refresh_from_db()
        self.assertFalse(self.teacher.is_active)

    def test_delete_teacher_with_payments_keeps_payment_allocation(self):
        group = Group.objects.create(company=self.company, branch=self.branch, name='G', teacher=self.teacher)
        student = Student.objects.create(company=self.company, branch=self.branch, group=group, first_name='S', phone='901880001')
        payment = Payment.objects.create(
            company=self.company, student=student, student_name='S', amount=100000, group=group, teacher=self.teacher,
        )
        self.assertEqual(self.client.delete(f'/v1/user/teacher/{self.teacher.id}').status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.teacher_id, self.teacher.id)

    def test_teacher_without_history_is_really_deleted(self):
        self.assertEqual(self.client.delete(f'/v1/user/teacher/{self.teacher.id}').status_code, 200)
        self.assertFalse(User.objects.filter(pk=self.teacher.pk).exists())

    def test_archived_teacher_cannot_be_assigned_to_group(self):
        self.teacher.is_active = False
        self.teacher.save()
        group = Group.objects.create(company=self.company, branch=self.branch, name='G2')
        res = self.client.patch(f'/v1/groups/{group.id}', {'teacher_id': self.teacher.id}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_cannot_remove_branch_where_teacher_has_active_groups(self):
        Group.objects.create(company=self.company, branch=self.branch, name='Busy', teacher=self.teacher)
        res = self.client.patch(
            f'/v1/user/teacher/{self.teacher.id}', {'branches': [self.other_branch.id]}, format='json',
        )
        self.assertEqual(res.status_code, 400)
        self.assertTrue(TeacherBranch.objects.filter(teacher=self.teacher, branch=self.branch).exists())

    def test_teacher_sees_only_own_reminders(self):
        from django.utils import timezone
        today = timezone.localdate()
        mine = Reminder.objects.create(company=self.company, title='Mine', due_date=today, assigned_to=self.teacher)
        other = Reminder.objects.create(company=self.company, title='Call debtor', due_date=today, assigned_to=self.ceo)
        self.client.force_authenticate(self.teacher)
        rows = self.client.get('/v1/reminders').json()['data']
        rows = rows['items'] if isinstance(rows, dict) else rows
        self.assertEqual([r['id'] for r in rows], [mine.id])
        self.assertEqual(self.client.get(f'/v1/reminders/{other.id}').status_code, 404)
        dash = self.client.get('/v1/dashboard').json()['data']['reminders']
        self.assertEqual([r['id'] for r in dash], [mine.id])


class TeacherPayrollHistoryTests(TestCase):
    """Per-student rate uses group history; self check-in only on lesson days"""

    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Hist Co', subdomain='histco')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.ceo = User.objects.create_user(
            phone='998909008901', password='password123', first_name='C', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.teacher = User.objects.create_user(
            phone='998909008902', password='password123', first_name='Tom', company=self.company,
            user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=self.teacher, branch=self.branch)
        self.group = Group.objects.create(
            company=self.company, branch=self.branch, name='G', teacher=self.teacher, days=Group.Days.EVERY_DAY,
        )

    def test_per_student_rate_counts_students_of_that_month(self):
        from datetime import date
        from crm.models import GroupEnrollment
        SalarySetting.objects.create(
            company=self.company, teacher=self.teacher, teacher_name='Tom',
            salary_type=SalarySetting.SalaryType.PER_STUDENT, amount=100000,
        )
        for i in range(3):
            s = Student.objects.create(company=self.company, branch=self.branch, first_name=f'S{i}', phone=f'90188{i:04d}')
            GroupEnrollment.objects.filter(student=s).delete()
            # all three were in the group in August; two of them left on 20 September
            GroupEnrollment.objects.create(
                company=self.company, student=s, group=self.group, joined_date=date(2026, 8, 1),
                left_date=date(2026, 9, 20) if i < 2 else None,
                status=GroupEnrollment.Status.LEFT if i < 2 else GroupEnrollment.Status.ACTIVE,
            )
        self.client.force_authenticate(self.ceo)

        def accrued(month):
            rows = self.client.get(f'/v1/finance/payroll?month={month}').json()['data']['rows']
            return next(r['accrued'] for r in rows if r['teacher_id'] == self.teacher.id)

        self.assertEqual(accrued('2026-08'), 300000)  # 3 students in August, even if they left later
        self.assertEqual(accrued('2026-07'), 0)       # nobody was in the group yet

    def test_self_checkin_only_on_lesson_days(self):
        from django.utils import timezone
        today = timezone.localdate().weekday()
        self.client.force_authenticate(self.teacher)
        self.assertIn(self.client.post('/v1/teacher-attendance/self-checkin', {'group_id': self.group.id}).status_code, (200, 201))

        self.group.days = Group.Days.CUSTOM
        self.group.weekdays = [(today + 1) % 7]
        self.group.save()
        res = self.client.post('/v1/teacher-attendance/self-checkin', {'group_id': self.group.id})
        self.assertEqual(res.status_code, 400)

    def test_today_lessons_and_repeat_press_changes_nothing(self):
        from django.utils import timezone
        from operations.models import TeacherAttendanceRecord
        today = timezone.localdate().weekday()
        no_lesson = Group.objects.create(
            company=self.company, branch=self.branch, name='Not today', teacher=self.teacher,
            days=Group.Days.CUSTOM, weekdays=[(today + 1) % 7],
        )
        self.client.force_authenticate(self.teacher)
        rows = self.client.get('/v1/teacher-attendance/today').json()['data']
        self.assertEqual([r['group_id'] for r in rows], [self.group.id])
        self.assertFalse(rows[0]['checked_in'])
        self.assertNotIn(no_lesson.id, [r['group_id'] for r in rows])

        self.client.post('/v1/teacher-attendance/self-checkin', {'group_id': self.group.id})
        record = TeacherAttendanceRecord.objects.get(teacher=self.teacher, group=self.group)
        # admin corrects the mark; the teacher's second press must not overwrite it
        record.status = TeacherAttendanceRecord.Status.ABSENT
        record.save()
        self.client.post('/v1/teacher-attendance/self-checkin', {'group_id': self.group.id})
        record.refresh_from_db()
        self.assertEqual(record.status, TeacherAttendanceRecord.Status.ABSENT)
        self.assertTrue(self.client.get('/v1/teacher-attendance/today').json()['data'][0]['checked_in'])

    def test_today_lessons_empty_for_staff(self):
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.get('/v1/teacher-attendance/today').json()['data'], [])


class TeacherScreensTests(TestCase):
    """Teacher screens: attendance only for today, grades of own groups only, "my attendance" data"""

    def setUp(self):
        from django.utils import timezone
        self.client = APIClient()
        self.today = timezone.localdate()
        self.company = Company.objects.create(name='Screens Co', subdomain='screensco')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.teacher = User.objects.create_user(
            phone='998909009001', password='password123', first_name='Own', company=self.company,
            user_type=User.UserType.TEACHER,
        )
        self.other = User.objects.create_user(
            phone='998909009002', password='password123', first_name='Other', company=self.company,
            user_type=User.UserType.TEACHER,
        )
        self.admin = User.objects.create_user(
            phone='998909009003', password='password123', first_name='Adm', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.ADMINISTRATOR,
        )
        for t in (self.teacher, self.other):
            TeacherBranch.objects.create(teacher=t, branch=self.branch)
        self.group = Group.objects.create(company=self.company, branch=self.branch, name='Own', teacher=self.teacher)
        self.other_group = Group.objects.create(company=self.company, branch=self.branch, name='Other', teacher=self.other)
        self.student = Student.objects.create(company=self.company, branch=self.branch, group=self.group, first_name='S', phone='901990001')
        self.other_student = Student.objects.create(
            company=self.company, branch=self.branch, group=self.other_group, first_name='O', phone='901990002',
        )

    def mark(self, day):
        return self.client.post('/v1/reports/attendance', {
            'group_id': self.group.id, 'date': day.isoformat(),
            'records': [{'student_id': self.student.id, 'status': 1}],
        }, format='json')

    def test_teacher_marks_students_only_today_admin_any_past_day(self):
        from datetime import timedelta
        from crm.models import AttendanceRecord
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.mark(self.today).status_code, 200)
        self.assertEqual(self.mark(self.today - timedelta(days=1)).status_code, 403)

        old = AttendanceRecord.objects.create(
            company=self.company, student=self.student, group=self.group, attend_date=self.today - timedelta(days=2),
        )
        self.assertEqual(self.client.patch(f'/v1/reports/attendance/{old.id}', {'status': 0}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'/v1/reports/attendance/{old.id}').status_code, 403)

        self.client.force_authenticate(self.admin)
        self.assertEqual(self.mark(self.today - timedelta(days=1)).status_code, 200)

    def test_teacher_sees_only_own_groups_grades(self):
        from operations.models import StudentScore
        StudentScore.objects.create(company=self.company, student=self.student, group=self.group, grade=90)
        StudentScore.objects.create(company=self.company, student=self.other_student, group=self.other_group, grade=50)
        self.client.force_authenticate(self.teacher)
        rows = self.client.get('/v1/scores/branch').json()['data']['rows']
        self.assertEqual([r['student_id'] for r in rows], [self.student.id])
        groups = self.client.get('/v1/scores/groups').json()['data']
        self.assertEqual([g['group_id'] if 'group_id' in g else g['id'] for g in groups], [self.group.id])

    def test_my_attendance_returns_own_marks_only(self):
        from operations.models import TeacherAttendanceRecord
        TeacherAttendanceRecord.objects.create(company=self.company, teacher=self.teacher, group=self.group, attend_date=self.today)
        TeacherAttendanceRecord.objects.create(company=self.company, teacher=self.other, group=self.other_group, attend_date=self.today)
        self.client.force_authenticate(self.teacher)
        data = self.client.get('/v1/teacher-attendance/my').json()['data']
        self.assertEqual(len(data['records']), 1)
        self.assertEqual(data['records'][0]['group'], 'Own')
        self.assertIsNotNone(data['start_date'])
