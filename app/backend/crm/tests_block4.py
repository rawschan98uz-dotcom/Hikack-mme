from datetime import date, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from api.csv_utils import normalize_phone as import_normalize_phone
from api.utils import capitalize_name
from crm.models import AttendanceRecord, Group, Lead, Student
from crm.services import match_student_to_lead
from finance.billing import split_monthly
from finance.models import ExpenseCategory, Payment, SalarySetting
from finance.salary import resolve_salary_setting
from operations.models import ArchivedPerson, Reminder, StudentScore, TeacherAttendanceRecord
from org.models import Branch, Company, Room


class Block4Base(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Block4 Co', subdomain='block4')
        self.other_company = Company.objects.create(name='Other Co', subdomain='other4')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.ceo = User.objects.create_user(
            phone='998909004455', password='password123', first_name='B4', last_name='CEO',
            company=self.company, user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.teacher = User.objects.create_user(
            phone='998909004466', password='password123', first_name='Own', last_name='Teacher',
            company=self.company, user_type=User.UserType.TEACHER,
        )
        self.other_teacher = User.objects.create_user(
            phone='998909004477', password='password123', first_name='Other', last_name='Teacher',
            company=self.company, user_type=User.UserType.TEACHER,
        )
        for t in (self.teacher, self.other_teacher):
            TeacherBranch.objects.create(teacher=t, branch=self.branch)
        self.own_group = Group.objects.create(company=self.company, branch=self.branch, name='Own', teacher=self.teacher)
        self.other_group = Group.objects.create(
            company=self.company, branch=self.branch, name='Other', teacher=self.other_teacher,
        )
        self.own_student = Student.objects.create(
            company=self.company, branch=self.branch, group=self.own_group, first_name='Mine', phone='901110001',
            status=Student.Status.STUDYING,
        )
        self.other_student = Student.objects.create(
            company=self.company, branch=self.branch, group=self.other_group, first_name='Theirs', phone='901110002',
            status=Student.Status.STUDYING,
        )


class TeacherScopeTests(Block4Base):
    """E1 + #29"""

    def test_teacher_sees_only_own_students_without_money_fields(self):
        self.client.force_authenticate(self.teacher)
        rows = self.client.get('/v1/students').json()['data']['results']
        self.assertEqual([r['id'] for r in rows], [self.own_student.id])
        for key in ('paid_this_month', 'is_debtor', 'overdue_days', 'next_payment_date', 'course_price'):
            self.assertIsNone(rows[0][key], key)

        detail = self.client.get(f'/v1/students/{self.own_student.id}').json()['data']
        self.assertIsNone(detail['next_payment_date'])
        self.assertEqual(self.client.get(f'/v1/students/{self.other_student.id}').status_code, 404)

    def test_staff_still_sees_money_fields(self):
        self.client.force_authenticate(self.ceo)
        detail = self.client.get(f'/v1/students/{self.own_student.id}').json()['data']
        self.assertIsNotNone(detail['next_payment_date'])

    def test_teacher_cannot_read_student_payments(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get(f'/v1/students/{self.own_student.id}/payments').status_code, 403)
        self.assertEqual(self.client.get(f'/v1/students/{self.own_student.id}/payment-links').status_code, 403)

    def test_teacher_dashboard_has_no_company_money(self):
        Payment.objects.create(
            company=self.company, student=self.own_student, student_name='Mine', amount=100000,
            transaction_type=Payment.TransactionType.PAYMENT,
        )
        self.client.force_authenticate(self.teacher)
        data = self.client.get('/v1/dashboard').json()['data']
        self.assertEqual(data['finance_chart'], [])
        self.assertEqual(data['debtors'], 0)
        self.assertEqual(data['active_students'], 1)

    def test_teacher_cannot_grade_other_groups(self):
        self.client.force_authenticate(self.teacher)
        res = self.client.post('/v1/scores/branch', {
            'student_id': self.other_student.id, 'group_id': self.other_group.id, 'grade': 90,
        })
        self.assertEqual(res.status_code, 403)
        res = self.client.post('/v1/scores/bulk', {
            'group_id': self.other_group.id, 'items': [{'student_id': self.other_student.id, 'grade': 90}],
        }, format='json')
        self.assertEqual(res.status_code, 403)
        res = self.client.post('/v1/scores/branch', {
            'student_id': self.own_student.id, 'group_id': self.own_group.id, 'grade': 90,
        })
        self.assertEqual(res.status_code, 201, res.content)

    def test_grade_only_students_of_that_group(self):
        self.client.force_authenticate(self.ceo)
        res = self.client.post('/v1/scores/branch', {
            'student_id': self.other_student.id, 'group_id': self.own_group.id, 'grade': 90,
        })
        self.assertEqual(res.status_code, 400)
        res = self.client.post('/v1/scores/bulk', {
            'group_id': self.own_group.id,
            'items': [{'student_id': self.other_student.id, 'grade': 90}, {'student_id': self.own_student.id, 'grade': 80}],
        }, format='json')
        self.assertEqual(res.json()['data']['saved_count'], 1)

    def test_teacher_cannot_edit_score_of_other_group(self):
        score = StudentScore.objects.create(company=self.company, student=self.other_student, group=self.other_group, grade=50)
        self.client.force_authenticate(self.teacher)
        # another teacher's grade is not even visible to this teacher
        self.assertEqual(self.client.patch(f'/v1/scores/{score.id}', {'grade': 99}).status_code, 404)
        score.refresh_from_db()
        self.assertEqual(score.grade, 50)

    def test_scores_limit_not_a_number_does_not_crash(self):
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.get('/v1/scores/branch?limit=abc').status_code, 200)


class TenantAndArchiveTests(Block4Base):
    """A4"""

    def test_legacy_trashed_route_removed(self):
        # P4-1: the duplicate route company/<id>/users/trashed is gone; archive/list is the only one
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.get(f'/v1/company/{self.company.id}/users/trashed').status_code, 404)
        self.assertEqual(self.client.get('/v1/archive/list').status_code, 200)

    def test_platform_payments_reject_foreign_company(self):
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.get(f'/v1/company/{self.other_company.id}/payments').status_code, 404)

    def test_teacher_delete_with_history_goes_to_archive(self):
        TeacherAttendanceRecord.objects.create(
            company=self.company, teacher=self.teacher, group=self.own_group, attend_date=timezone.localdate(),
        )
        self.client.force_authenticate(self.ceo)
        res = self.client.delete(f'/v1/user/teacher/{self.teacher.id}')
        self.assertEqual(res.status_code, 200, res.content)
        self.teacher.refresh_from_db()
        self.own_group.refresh_from_db()
        self.assertFalse(self.teacher.is_active)
        self.assertIsNone(self.own_group.teacher_id)
        self.assertTrue(ArchivedPerson.objects.filter(company=self.company, phone=self.teacher.phone).exists())


class LeadIntegrityTests(Block4Base):
    """D3, D4"""

    def test_back_to_trial_resets_attended_flag(self):
        lead = Lead.objects.create(company=self.company, first_name='A', phone='901230000', stage=Lead.Stage.ATTENDED)
        self.assertTrue(lead.attended_trial)
        lead.stage = Lead.Stage.TRIAL_BOOKED
        lead.save()
        self.assertFalse(lead.attended_trial)

    def test_cannot_create_lead_directly_as_converted(self):
        self.client.force_authenticate(self.ceo)
        res = self.client.post('/v1/leads', {'first_name': 'X', 'phone': '901239999', 'stage': 'converted'})
        self.assertEqual(res.status_code, 400)

    def test_converted_lead_is_not_matched_again(self):
        Lead.objects.create(company=self.company, first_name='Mine', phone='901110001', stage=Lead.Stage.CONVERTED)
        brother = Student(company=self.company, branch=self.branch, first_name='Mine', phone='901110001')
        self.assertIsNone(match_student_to_lead(brother))


class NormalizationTests(TestCase):
    """D9 + names"""

    def test_import_phone_uses_common_format(self):
        self.assertEqual(import_normalize_phone('+998 90 123-45-67'), '901234567')
        self.assertEqual(import_normalize_phone('998901234567 / 901112233'), '901234567')

    def test_capitalize_name_keeps_particles(self):
        self.assertEqual(capitalize_name("ALIJON VALIYEV OG'LI"), "Alijon Valiyev og'li")
        self.assertEqual(capitalize_name("g'ulom qodirova qizi"), "G'ulom Qodirova qizi")
        self.assertEqual(capitalize_name('ИВАНОВ-ПЕТРОВ ИВАН ОГЛЫ'), 'Иванов-Петров Иван оглы')
        self.assertEqual(capitalize_name('McDonald'), 'McDonald')


class UniquenessTests(Block4Base):
    """D1, D2, section 7 p.12"""

    def test_duplicate_tag_and_category_rejected_nicely(self):
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.post('/v1/tags', {'name': 'VIP'}).status_code, 201)
        self.assertEqual(self.client.post('/v1/tags', {'name': 'vip'}).status_code, 400)
        self.assertEqual(self.client.post('/v1/expense_types', {'name': 'Аренда'}).status_code, 201)
        self.assertEqual(self.client.post('/v1/expense_types', {'name': 'аренда'}).status_code, 400)

    def test_duplicate_holiday_rejected(self):
        self.client.force_authenticate(self.ceo)
        payload = {'name': 'Navruz', 'holiday_date': '2026-03-21', 'branch_id': self.branch.id}
        self.assertEqual(self.client.post('/v1/holidays', payload).status_code, 201)
        self.assertEqual(self.client.post('/v1/holidays', payload).status_code, 400)

    def test_salary_category_reused_case_insensitively(self):
        ExpenseCategory.objects.create(company=self.company, name='зарплата')
        SalarySetting.objects.create(
            company=self.company, teacher=self.teacher, teacher_name='Own', amount=1000000,
            salary_type=SalarySetting.SalaryType.FIXED,
        )
        self.client.force_authenticate(self.ceo)
        res = self.client.post('/v1/finance/payroll/pay', {'teacher_id': self.teacher.id, 'amount': 100000})
        self.assertIn(res.status_code, (200, 201), res.content)
        self.assertEqual(ExpenseCategory.objects.filter(company=self.company).count(), 1)

    def test_room_company_filled_from_branch(self):
        room = Room.objects.create(branch=self.branch, name='R')
        self.assertEqual(room.company_id, self.company.id)


class AttendanceTests(Block4Base):
    """D5, D6"""

    def test_bulk_attendance_saves_only_group_students(self):
        self.client.force_authenticate(self.teacher)
        res = self.client.post('/v1/reports/attendance', {
            'date': timezone.localdate().isoformat(), 'group_id': self.own_group.id,
            'records': [{'student_id': self.own_student.id, 'status': 1}, {'student_id': self.other_student.id, 'status': 1}],
        }, format='json')
        self.assertEqual(res.json()['data']['saved'], 1)

    def test_old_record_of_transferred_student_can_be_corrected(self):
        day = timezone.localdate() - timedelta(days=3)
        record = AttendanceRecord.objects.create(
            company=self.company, student=self.own_student, group=self.own_group, attend_date=day,
        )
        self.own_student.group = self.other_group
        self.own_student.save()
        self.client.force_authenticate(self.ceo)
        res = self.client.patch(f'/v1/reports/attendance/{record.id}', {'status': 0})
        self.assertEqual(res.status_code, 200, res.content)

    def test_moving_record_onto_existing_date_is_rejected(self):
        d1 = timezone.localdate() - timedelta(days=2)
        d2 = timezone.localdate() - timedelta(days=1)
        AttendanceRecord.objects.create(company=self.company, student=self.own_student, group=self.own_group, attend_date=d1)
        second = AttendanceRecord.objects.create(
            company=self.company, student=self.own_student, group=self.own_group, attend_date=d2,
        )
        self.client.force_authenticate(self.ceo)
        res = self.client.patch(f'/v1/reports/attendance/{second.id}', {'date': d1.isoformat()})
        self.assertEqual(res.status_code, 400)


class ReminderStatusTests(Block4Base):
    """D7"""

    def test_status_is_computed_from_date(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        # Stored as "future" long ago — must still read as overdue now
        reminder = Reminder.objects.create(
            company=self.company, title='Call', due_date=yesterday, status=Reminder.Status.FUTURE,
        )
        self.assertEqual(reminder.current_status, Reminder.Status.OVERDUE)
        self.client.force_authenticate(self.ceo)
        data = self.client.get('/v1/reminders').json()['data']
        self.assertEqual([r['id'] for r in data['buckets']['overdue']], [reminder.id])
        dash = self.client.get('/v1/dashboard').json()['data']
        self.assertEqual([r['id'] for r in dash['reminders']], [reminder.id])


class SalaryTests(Block4Base):
    """D8"""

    def test_overlapping_setting_rejected(self):
        self.client.force_authenticate(self.ceo)
        base = {'teacher_id': self.teacher.id, 'salary_type': 'fixed', 'amount': 1000000}
        self.assertEqual(self.client.post('/v1/salary-settings', {**base, 'effective_from': '2026-01-01'}).status_code, 201)
        res = self.client.post('/v1/salary-settings', {**base, 'effective_from': '2026-06-01'})
        self.assertEqual(res.status_code, 400)

    def test_newest_period_wins(self):
        SalarySetting.objects.create(
            company=self.company, teacher=self.teacher, teacher_name='t', amount=1,
            effective_from=date(2026, 1, 1), effective_to=date(2026, 6, 15),
        )
        newer = SalarySetting.objects.create(
            company=self.company, teacher=self.teacher, teacher_name='t', amount=2, effective_from=date(2026, 6, 16),
        )
        self.assertEqual(resolve_salary_setting(self.company, self.teacher, date(2026, 6, 1), date(2026, 6, 30)), newer)


class CapacityTests(Block4Base):
    """D10 was removed by the owner (2026-09-27): room capacity no longer limits a group."""

    def test_room_capacity_does_not_block(self):
        room = Room.objects.create(branch=self.branch, name='Tiny', capacity=1)
        self.own_group.room = room
        self.own_group.save()
        self.client.force_authenticate(self.ceo)
        res = self.client.patch(f'/v1/students/{self.other_student.id}', {'group_id': self.own_group.id})
        self.assertEqual(res.status_code, 200, res.content)
        res = self.client.patch(f'/v1/groups/{self.own_group.id}', {'room_id': room.id})
        self.assertEqual(res.status_code, 200, res.content)


class BillingAndImportTests(Block4Base):
    """B6 + import passwords"""

    def test_split_monthly_keeps_every_sum(self):
        dates = [date(2026, 9, d) for d in range(1, 13)]
        parts = split_monthly(1_000_000, dates)
        self.assertEqual(sum(parts.values()), 1_000_000)
        self.assertEqual(parts[dates[0]], 83_333)
        self.assertEqual(parts[dates[-1]], 83_337)
        self.assertEqual(split_monthly(100, []), {})

    def test_staff_import_generates_unique_passwords(self):
        self.client.force_authenticate(self.ceo)
        csv = 'first_name,phone\nAli,901000001\nVali,901000002\n'.encode('utf-8')
        res = self.client.post(
            '/v1/user/staff/import', {'file': SimpleUploadedFile('staff.csv', csv, content_type='text/csv')},
            format='multipart',
        )
        self.assertEqual(res.status_code, 200, res.content)
        creds = res.json()['data']['credentials']
        self.assertEqual(len(creds), 2)
        self.assertNotEqual(creds[0]['password'], creds[1]['password'])
        user = User.objects.get(phone='901000001')
        self.assertFalse(user.check_password('946263200'))
        self.assertTrue(user.check_password(creds[0]['password']))
