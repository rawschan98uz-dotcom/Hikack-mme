"""Closing a month (owner, 2026-09-29): frozen salaries, locked money records, corrections, CEO only."""
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm.models import Course, Group, GroupEnrollment, Student
from finance.models import ClosedMonth, Expense, PayrollSnapshot, SalarySetting, Withdrawal
from operations.models import AuditLogRecord, TeacherAttendanceRecord
from org.models import Branch, Company

AUG = '2026-08'


class Base(TestCase):
    def setUp(self):
        self.c = APIClient()
        self.company = Company.objects.create(name='Close Co', subdomain='closeco')
        self.a = Branch.objects.create(company=self.company, name='A')
        self.ceo = User.objects.create_user(phone='998905880001', password='x', first_name='Ceo', company=self.company,
                                            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO)
        self.admin = User.objects.create_user(phone='998905880002', password='x', first_name='Adm', company=self.company,
                                              user_type=User.UserType.STAFF, staff_role=User.StaffRole.ADMINISTRATOR)
        self.tom = User.objects.create_user(phone='998905880003', password='x', first_name='Tom', company=self.company,
                                            user_type=User.UserType.TEACHER)
        TeacherBranch.objects.create(teacher=self.tom, branch=self.a)
        self.course = Course.objects.create(company=self.company, name='En', price=500_000)
        self.g = Group.objects.create(company=self.company, branch=self.a, name='G', course=self.course, teacher=self.tom,
                                      days=Group.Days.CUSTOM, weekdays=[0, 2, 4])  # Mon/Wed/Fri: 13 lessons in August
        for i in range(10):
            s = Student.objects.create(company=self.company, branch=self.a, group=self.g, first_name=f'S{i}',
                                       phone=f'90200{i:04d}', trial_date=date(2026, 8, 1))
            GroupEnrollment.objects.filter(student=s).update(joined_date=date(2026, 8, 1))
        self.ali = Student.objects.get(first_name='S0')
        self.setting = SalarySetting.objects.create(company=self.company, teacher=self.tom, teacher_name='Tom',
                                                    salary_type='percent', amount=30)
        self.marks = [
            TeacherAttendanceRecord.objects.create(company=self.company, teacher=self.tom, group=self.g,
                                                   attend_date=date(2026, 8, d), status=1)
            for d in (3, 5, 7, 10, 12)
        ]
        self.c.force_authenticate(self.ceo)

    # 10 students × 500 000 × 5 lessons × 30% ÷ 13 possible lessons
    ACCRUED = 10 * 500_000 * 5 * 30 // (13 * 100)

    def payroll(self, month=AUG):
        return self.c.get('/v1/finance/payroll', {'month': month}).json()['data']

    def row(self, month=AUG, person=None):
        return next(r for r in self.payroll(month)['rows'] if r['person_id'] == (person or self.tom).id)

    def close(self, month=AUG):
        return self.c.post('/v1/finance/months/close', {'month': month}, format='json')


class FrozenSalaryTests(Base):
    def setUp(self):
        super().setUp()
        res = self.c.post('/v1/finance/payroll/pay', {'teacher_id': self.tom.id, 'amount': self.ACCRUED, 'month': AUG},
                          format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(self.close().status_code, 201)

    def assert_unchanged(self):
        r = self.row()
        self.assertEqual((r['accrued'], r['paid'], r['balance'], r['overpaid'], r['status']),
                         (self.ACCRUED, self.ACCRUED, 0, 0, 'paid'))
        self.assertTrue(r['month_closed'])

    def test_price_raised_later(self):
        self.course.price = 600_000
        self.course.save()
        self.assert_unchanged()

    def test_percent_edited_later(self):
        self.assertEqual(self.c.patch(f'/v1/salary-settings/{self.setting.id}', {'amount': 40}, format='json').status_code, 200)
        self.assert_unchanged()

    def test_holiday_and_schedule_changed_later(self):
        self.c.post('/v1/holidays', {'name': 'H', 'holiday_date': '2026-08-31', 'branch_id': self.a.id}, format='json')
        self.c.patch(f'/v1/groups/{self.g.id}', {'days': Group.Days.CUSTOM, 'weekdays': [0, 2]}, format='json')
        self.assert_unchanged()

    def test_lesson_marks_of_closed_month_are_locked(self):
        res = self.c.delete(f'/v1/reports/teacher-attendance/{self.marks[0].id}')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Август 2026 закрыт', res.json()['message'])
        res = self.c.post('/v1/reports/teacher-attendance', {'teacher_id': self.tom.id, 'group_id': self.g.id,
                                                             'date': '2026-08-14'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.c.patch(f'/v1/reports/teacher-attendance/{self.marks[0].id}', {'status': 0},
                                      format='json').status_code, 400)
        self.assertEqual(self.c.patch(f'/v1/reports/teacher-attendance/{self.marks[0].id}', {'note': 'ok'},
                                      format='json').status_code, 200)  # a note is not money
        self.assert_unchanged()

    def test_the_breakdown_is_frozen_too(self):
        self.course.price = 600_000
        self.course.save()
        g = self.row()['groups'][0]
        self.assertEqual((g['course_price'], g['held_lessons'], g['percent']), (500_000, 5, 30))

    def test_open_month_is_still_counted_live(self):
        TeacherAttendanceRecord.objects.create(company=self.company, teacher=self.tom, group=self.g,
                                               attend_date=date(2026, 9, 7), status=1)
        before = self.row('2026-09')['accrued']
        self.course.price = 600_000
        self.course.save()
        self.assertGreater(self.row('2026-09')['accrued'], before)
        self.assertFalse(self.row('2026-09')['month_closed'])

    def test_reopen_counts_again_and_is_logged(self):
        self.course.price = 600_000
        self.course.save()
        self.assertEqual(self.c.post('/v1/finance/months/reopen', {'month': AUG}, format='json').status_code, 400)
        res = self.c.post('/v1/finance/months/reopen', {'month': AUG, 'reason': 'Ошибка в цене'}, format='json')
        self.assertEqual(res.status_code, 200)
        r = self.row()
        self.assertFalse(r['month_closed'])
        self.assertEqual(r['accrued'], 10 * 600_000 * 5 * 30 // (13 * 100))
        self.assertTrue(AuditLogRecord.objects.filter(entity_type='finance_month', action='reopen',
                                                      reason__contains='Ошибка в цене').exists())

    def test_salary_of_closed_month_can_still_be_paid(self):
        # Closing does not stop paying August's salary in September (the payout is dated today)
        self.c.post('/v1/finance/months/reopen', {'month': AUG, 'reason': 'test'}, format='json')
        self.c.delete(f'/v1/finance/payroll/payouts/{self.row()["payouts"][0]["id"]}')
        self.close()
        res = self.c.post('/v1/finance/payroll/pay', {'teacher_id': self.tom.id, 'amount': 1_000, 'month': AUG},
                          format='json')
        self.assertEqual(res.status_code, 201, res.content)


class AdjustmentTests(Base):
    def setUp(self):
        super().setUp()
        self.close()

    def test_ceo_adds_a_visible_correction(self):
        res = self.c.post('/v1/finance/payroll/adjustments', {'person_id': self.tom.id, 'month': AUG,
                                                              'amount': 50_000, 'reason': 'Забыли урок 14.08'},
                          format='json')
        self.assertEqual(res.status_code, 201, res.content)
        r = self.row()
        self.assertEqual((r['accrued_base'], r['accrued']), (self.ACCRUED, self.ACCRUED + 50_000))
        self.assertEqual(r['adjustments'][0]['reason'], 'Забыли урок 14.08')
        self.assertEqual(r['status'], 'unpaid')

    def test_negative_correction_and_limits(self):
        ok = self.c.post('/v1/finance/payroll/adjustments', {'person_id': self.tom.id, 'month': AUG,
                                                             'amount': -10_000, 'reason': 'Лишний урок'}, format='json')
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertEqual(self.row()['accrued'], self.ACCRUED - 10_000)
        too_much = self.c.post('/v1/finance/payroll/adjustments', {'person_id': self.tom.id, 'month': AUG,
                                                                   'amount': -10_000_000, 'reason': 'x x'}, format='json')
        self.assertEqual(too_much.status_code, 400)
        no_reason = self.c.post('/v1/finance/payroll/adjustments', {'person_id': self.tom.id, 'month': AUG,
                                                                    'amount': 5}, format='json')
        self.assertEqual(no_reason.status_code, 400)
        self.assertEqual(self.c.post('/v1/finance/payroll/adjustments', {'person_id': self.tom.id, 'month': AUG,
                                                                         'amount': '1.5', 'reason': 'abc'},
                                     format='json').status_code, 400)

    def test_delete_correction(self):
        aid = self.c.post('/v1/finance/payroll/adjustments', {'person_id': self.tom.id, 'month': AUG,
                                                              'amount': 50_000, 'reason': 'abc'}, format='json').json()['data']['id']
        self.assertEqual(self.c.delete(f'/v1/finance/payroll/adjustments/{aid}').status_code, 200)
        self.assertEqual(self.row()['accrued'], self.ACCRUED)
        self.assertTrue(AuditLogRecord.objects.filter(action='adjustment_delete').exists())

    def test_only_ceo(self):
        self.c.force_authenticate(self.admin)
        res = self.c.post('/v1/finance/payroll/adjustments', {'person_id': self.tom.id, 'month': AUG,
                                                              'amount': 50_000, 'reason': 'abc'}, format='json')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.c.post('/v1/finance/months/reopen', {'month': AUG, 'reason': 'abc'},
                                     format='json').status_code, 403)


class CloseRulesTests(Base):
    def test_only_a_finished_month_and_only_once(self):
        self.assertEqual(self.close('2026-09').status_code, 400)  # today is in September
        self.assertEqual(self.close('2026-13').status_code, 400)
        self.assertTrue(self.payroll()['can_close'])
        self.assertEqual(self.close().status_code, 201)
        self.assertEqual(self.close().status_code, 400)
        data = self.payroll()
        self.assertFalse(data['can_close'])
        self.assertEqual(data['closed']['closed_by'], self.ceo.display_name())
        self.assertTrue(AuditLogRecord.objects.filter(entity_type='finance_month', action='close').exists())

    def test_administrator_cannot_close(self):
        self.c.force_authenticate(self.admin)
        self.assertEqual(self.close().status_code, 403)
        self.assertFalse(ClosedMonth.objects.exists())

    def test_staff_fixed_salary_is_frozen(self):
        SalarySetting.objects.create(company=self.company, teacher=self.admin, teacher_name='Adm',
                                     salary_type='fixed', amount=3_000_000)
        self.close()
        SalarySetting.objects.filter(teacher=self.admin).update(amount=4_000_000)
        r = self.row(person=self.admin)
        self.assertEqual((r['accrued'], r['fixed_amount']), (3_000_000, 3_000_000))

    def test_closed_months_list(self):
        self.close()
        rows = self.c.get('/v1/finance/months').json()['data']
        self.assertEqual([(r['month'], r['title']) for r in rows], [(AUG, 'Август 2026')])


class LockedMoneyTests(Base):
    def setUp(self):
        super().setUp()
        pay = self.c.post('/v1/replenishments', {'student_id': self.ali.id, 'amount': 500_000,
                                                 'payment_date': '2026-08-05'}, format='json')
        self.pid = pay.json()['data']['id']
        self.expense = Expense.objects.create(company=self.company, amount=100_000, branch=self.a,
                                              expense_date=date(2026, 8, 10))
        self.withdrawal = Withdrawal.objects.create(company=self.company, name='Owner', amount=200_000,
                                                    withdrawal_date=date(2026, 8, 11))
        self.close()

    def pnl(self):
        return self.c.get('/v1/reports/pnl', {'date_from': '2026-08-01', 'date_to': '2026-08-31'}).json()['data']['summary']

    def test_august_pnl_cannot_change(self):
        before = self.pnl()
        cases = [
            self.c.post('/v1/replenishments', {'student_id': self.ali.id, 'amount': 500_000,
                                               'payment_date': '2026-08-20'}, format='json'),
            self.c.patch(f'/v1/replenishments/{self.pid}', {'amount': 300_000}, format='json'),
            self.c.patch(f'/v1/replenishments/{self.pid}', {'payment_date': '2026-09-02'}, format='json'),
            self.c.delete(f'/v1/replenishments/{self.pid}'),
            self.c.post('/v1/expense', {'amount': 700_000, 'branch_id': self.a.id, 'date': '2026-08-15'}, format='json'),
            self.c.patch(f'/v1/expense/{self.expense.id}', {'amount': 1}, format='json'),
            self.c.delete(f'/v1/expense/{self.expense.id}'),
            self.c.post('/v1/withdraws', {'name': 'X', 'amount': 1, 'date': '2026-08-15'}, format='json'),
            self.c.patch(f'/v1/withdraws/{self.withdrawal.id}', {'amount': 1}, format='json'),
            self.c.delete(f'/v1/withdraws/{self.withdrawal.id}'),
        ]
        self.assertEqual([r.status_code for r in cases], [400] * len(cases))
        self.assertIn('попросите CEO открыть август', cases[0].json()['message'])
        self.assertEqual(self.pnl(), before)

    def test_moving_a_september_record_into_august_is_locked(self):
        sep = Expense.objects.create(company=self.company, amount=5, branch=self.a, expense_date=date(2026, 9, 2))
        self.assertEqual(self.c.patch(f'/v1/expense/{sep.id}', {'date': '2026-08-31'}, format='json').status_code, 400)

    def test_comments_may_still_change(self):
        self.assertEqual(self.c.patch(f'/v1/replenishments/{self.pid}', {'comment': 'чек №5'},
                                      format='json').status_code, 200)
        self.assertEqual(self.c.patch(f'/v1/expense/{self.expense.id}', {'description': 'аренда'},
                                      format='json').status_code, 200)

    def test_refund_today_of_an_august_payment_is_allowed(self):
        res = self.c.post(f'/v1/replenishments/{self.pid}/refund', {'amount': 100_000}, format='json')
        self.assertEqual(res.status_code, 201, res.content)

    def test_september_is_open(self):
        res = self.c.post('/v1/replenishments', {'student_id': self.ali.id, 'amount': 500_000}, format='json')
        self.assertEqual(res.status_code, 201)


class CommandAndStaffTests(Base):
    def test_close_months_command(self):
        TeacherAttendanceRecord.objects.create(company=self.company, teacher=self.tom, group=self.g,
                                               attend_date=date(2026, 7, 6), status=1)
        call_command('close_months', '--until', AUG, stdout=StringIO())
        self.assertEqual(set(ClosedMonth.objects.values_list('month', flat=True)), {'2026-07', AUG})
        self.assertEqual(PayrollSnapshot.objects.get(closed_month__month=AUG, person=self.tom).accrued, self.ACCRUED)
        call_command('close_months', '--until', AUG, stdout=StringIO())  # twice is harmless
        self.assertEqual(ClosedMonth.objects.count(), 2)

    def test_staff_with_salary_history_is_archived_not_500(self):
        SalarySetting.objects.create(company=self.company, teacher=self.admin, teacher_name='Adm',
                                     salary_type='fixed', amount=3_000_000)
        res = self.c.delete(f'/v1/user/staff/{self.admin.id}')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()['data']['archived'])
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_active)
        staff_ids = [s['id'] for s in self.c.get('/v1/user', {'user_type': 'staff'}).json()['data']]
        self.assertNotIn(self.admin.id, staff_ids)
