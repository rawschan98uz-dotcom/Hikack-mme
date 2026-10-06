"""
Finance audit, block 3 (2026-09-28): teacher = percent of lessons held, staff = fixed, payouts by branch.
Since 2026-10-05 the percent is paid from what the students have really paid (their month lines), so the
students of these tests have paid September unless a test says otherwise.
"""
from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm.models import Course, Group, GroupEnrollment, Student, StudentFreeze
from finance.models import Expense, Payment, PayrollPayment, SalarySetting
from finance.payroll import lesson_days, parse_month, split_by_weights
from operations.models import AuditLogRecord, Holiday, TeacherAttendanceRecord
from org.models import Branch, Company

# September 2026: 1st is a Tuesday. EVEN days (Tue/Thu/Sat) -> 13 lessons, ODD (Mon/Wed/Fri) -> 13 lessons.
MONTH = '2026-09'
SEPT = date(2026, 9, 1)


class Base(TestCase):
    def setUp(self):
        self.c = APIClient()
        self.company = Company.objects.create(name='Pay Co', subdomain='payco')
        self.a = Branch.objects.create(company=self.company, name='A')
        self.b = Branch.objects.create(company=self.company, name='B')
        self.ceo = User.objects.create_user(
            phone='998905770001', password='x', first_name='Ceo', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.tom = User.objects.create_user(
            phone='998905770002', password='x', first_name='Tom', company=self.company, user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=self.tom, branch=self.a)
        TeacherBranch.objects.create(teacher=self.tom, branch=self.b)
        self.course = Course.objects.create(company=self.company, name='En', price=500_000)
        # Every Monday..Sunday: 30 possible lessons in September, easy numbers below use a custom schedule
        self.ga = Group.objects.create(
            company=self.company, branch=self.a, name='GA', course=self.course, teacher=self.tom,
            days=Group.Days.CUSTOM, weekdays=[0, 2, 4],  # Mon/Wed/Fri: 13 lessons in September 2026
        )
        self.c.force_authenticate(self.ceo)

    def student(self, name, group, phone, joined=SEPT, paid=True, **kw):
        s = Student.objects.create(company=self.company, branch=group.branch, group=group, first_name=name,
                                   phone=phone, trial_date=kw.pop('trial_date', SEPT), **kw)
        GroupEnrollment.objects.filter(student=s).update(joined_date=joined)
        if paid and s.status != Student.Status.LEFT_TRIAL:
            Payment.objects.create(company=self.company, student=s, student_name=name, amount=500_000,
                                   payment_date=SEPT)
        return s

    def held(self, group, days, teacher=None):
        for d in days:
            TeacherAttendanceRecord.objects.create(company=self.company, teacher=teacher or self.tom, group=group,
                                                   attend_date=d, status=1)

    def percent(self, value, **kw):
        return SalarySetting.objects.create(company=self.company, teacher=self.tom, teacher_name='Tom',
                                            salary_type='percent', amount=value, **kw)

    def row(self, person=None):
        rows = self.c.get('/v1/finance/payroll', {'month': MONTH}).json()['data']['rows']
        return next(r for r in rows if r['person_id'] == (person or self.tom).id)


class FormulaTests(Base):
    def test_owner_example_10_students_3_of_12_lessons_30_percent(self):
        # 12 possible lessons: a schedule with exactly 12 days in September
        self.ga.weekdays = [1, 3, 5]  # Tue/Thu/Sat -> 13; remove one by a holiday -> 12
        self.ga.save()
        Holiday.objects.create(company=self.company, branch=self.a, name='H', holiday_date=date(2026, 9, 1))
        self.assertEqual(len(lesson_days(self.ga, SEPT, date(2026, 9, 30))), 12)
        for i in range(10):
            self.student(f'S{i}', self.ga, f'90100{i:04d}')
        self.percent(30)
        self.held(self.ga, [date(2026, 9, 3), date(2026, 9, 5), date(2026, 9, 8)])
        # 10 × 500 000 = 5 000 000 ÷ 12 × 3 × 30% = 375 000
        self.assertEqual(self.row()['accrued'], 375_000)

    def test_a_debtor_brings_the_teacher_nothing_until_he_pays(self):
        # Owner (2026-10-05): the teacher is paid only from what the students have paid
        ali = self.student('Ali', self.ga, '901000001', paid=False)  # never paid anything
        self.percent(30)
        self.held(self.ga, [date(2026, 9, 7)])
        row = self.row()
        self.assertEqual((row['accrued'], row['waiting']), (0, 500_000 * 1 * 30 // (13 * 100)))
        Payment.objects.create(company=self.company, student=ali, student_name='Ali', amount=500_000)
        row = self.row()
        self.assertEqual((row['accrued'], row['waiting']), (500_000 * 1 * 30 // (13 * 100), 0))

    def test_student_joined_mid_month_counts_only_from_that_day(self):
        self.student('Ali', self.ga, '901000001')
        # His month starts on the 15th (start date): earlier lessons are not his
        self.student('Bek', self.ga, '901000002', joined=date(2026, 9, 15), trial_date=date(2026, 9, 15))
        self.percent(100)
        self.held(self.ga, [date(2026, 9, 7), date(2026, 9, 16)])  # Bek only on the 16th
        g = self.row()['groups'][0]
        self.assertEqual(g['student_lessons'], 3)
        self.assertEqual(g['accrued'], 500_000 * 3 // 13)

    def test_frozen_days_are_not_counted(self):
        ali = self.student('Ali', self.ga, '901000001')
        StudentFreeze.objects.create(company=self.company, student=ali, start_date=date(2026, 9, 10),
                                     end_date=date(2026, 9, 20))
        self.percent(100)
        self.held(self.ga, [date(2026, 9, 9), date(2026, 9, 14), date(2026, 9, 21)])
        self.assertEqual(self.row()['groups'][0]['student_lessons'], 2)  # the 14th is frozen

    def test_freeze_journal_follows_status(self):
        ali = self.student('Ali', self.ga, '901000001')
        self.c.patch(f'/v1/students/{ali.id}', {'status': Student.Status.FROZEN}, format='json')
        self.assertEqual(StudentFreeze.objects.filter(student=ali, end_date__isnull=True).count(), 1)
        ali.refresh_from_db()
        ali.status = Student.Status.STUDYING
        ali.save()
        self.assertFalse(StudentFreeze.objects.filter(student=ali, end_date__isnull=True).exists())

    def test_discount_lowers_the_base(self):
        ali = self.student('Ali', self.ga, '901000001', paid=False)
        Payment.objects.create(company=self.company, student=ali, student_name='Ali', amount=400_000,
                               discount_amount=100_000, months_covered=1, month_price=500_000,
                               payment_date=date(2026, 9, 2))
        self.percent(100)
        self.held(self.ga, [date(2026, 9, 7)])
        self.assertEqual(self.row()['accrued'], 400_000 // 13)

    def test_left_after_trial_is_not_counted(self):
        self.student('Ali', self.ga, '901000001', status=Student.Status.LEFT_TRIAL)
        self.percent(100)
        self.held(self.ga, [date(2026, 9, 7)])
        self.assertEqual(self.row()['accrued'], 0)

    def test_a_lesson_cannot_be_marked_on_a_day_without_one(self):
        # A mark is a fact once made (a later change of the schedule does not drop it), so the day is
        # checked when the lesson is marked
        self.student('Ali', self.ga, '901000001')
        res = self.c.post('/v1/reports/teacher-attendance', {'teacher_id': self.tom.id, 'group_id': self.ga.id,
                                                             'date': '2026-09-08'}, format='json')  # a Tuesday
        self.assertEqual(res.status_code, 400)

    def test_percent_group_over_course_over_general_and_no_rounding_loss(self):
        gb = Group.objects.create(company=self.company, branch=self.b, name='GB', course=self.course, teacher=self.tom,
                                  days=Group.Days.CUSTOM, weekdays=[0, 2, 4])
        for i in range(3):
            self.student(f'A{i}', self.ga, f'90200{i:04d}')
            self.student(f'B{i}', gb, f'90300{i:04d}')
        self.percent(20)
        self.percent(40, group=gb)
        self.held(self.ga, [date(2026, 9, 7)])
        self.held(gb, [date(2026, 9, 7)])
        groups = {g['group']: (g['percent'], g['percent_scope'], g['accrued']) for g in self.row()['groups']}
        # Counted student by student, in whole sums
        self.assertEqual(groups['GA'], (20, 'общий', 3 * (500_000 * 20 // (13 * 100))))
        self.assertEqual(groups['GB'], (40, 'группа', 3 * (500_000 * 40 // (13 * 100))))

    def test_substitute_teacher_gets_the_lesson(self):
        sub = User.objects.create_user(phone='998905770009', password='x', first_name='Sub', company=self.company,
                                       user_type=User.UserType.TEACHER)
        self.student('Ali', self.ga, '901000001')
        SalarySetting.objects.create(company=self.company, teacher=sub, teacher_name='Sub', salary_type='percent', amount=100)
        self.held(self.ga, [date(2026, 9, 7)], teacher=sub)
        self.assertEqual(self.row(sub)['accrued'], 500_000 // 13)


class RulesTests(Base):
    def test_teacher_percent_only_staff_fixed_only(self):
        admin = User.objects.create_user(phone='998905770010', password='x', first_name='Adm', company=self.company,
                                         user_type=User.UserType.STAFF, staff_role=User.StaffRole.ADMINISTRATOR,
                                         branch=None)
        post = lambda d: self.c.post('/v1/salary-settings', d, format='json')
        self.assertEqual(post({'teacher_id': self.tom.id, 'salary_type': 'fixed', 'amount': 4_000_000}).status_code, 400)
        self.assertEqual(post({'teacher_id': self.tom.id, 'amount': 150}).status_code, 400)
        self.assertEqual(post({'teacher_id': self.tom.id, 'amount': -5}).status_code, 400)
        self.assertEqual(post({'teacher_id': self.tom.id, 'amount': 30}).status_code, 201)
        self.assertEqual(post({'teacher_id': admin.id, 'salary_type': 'percent', 'amount': 30}).status_code, 400)
        self.assertEqual(post({'teacher_id': admin.id, 'amount': 3_000_000}).status_code, 201)
        self.assertEqual(post({'teacher_name': 'Tom', 'amount': 30}).status_code, 400)  # the person must be chosen

    def test_staff_fixed_salary_on_the_list(self):
        admin = User.objects.create_user(phone='998905770010', password='x', first_name='Adm', company=self.company,
                                         user_type=User.UserType.STAFF, staff_role=User.StaffRole.ADMINISTRATOR)
        SalarySetting.objects.create(company=self.company, teacher=admin, teacher_name='Adm', salary_type='fixed',
                                     amount=3_000_000, effective_from=SEPT)
        row = self.row(admin)
        self.assertEqual((row['kind'], row['accrued'], row['balance']), ('staff', 3_000_000, 3_000_000))
        # no branch of their own: the CEO picks one when paying
        res = self.c.post('/v1/finance/payroll/pay', {'teacher_id': admin.id, 'amount': 3_000_000, 'month': MONTH}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.c.post('/v1/finance/payroll/pay', {'teacher_id': admin.id, 'amount': 3_000_000, 'month': MONTH,
                                                      'branch_id': self.b.id}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(list(Expense.objects.values_list('branch__name', 'amount')), [('B', 3_000_000)])

    def test_month_must_be_real_and_one_format(self):
        self.percent(100)
        self.student('Ali', self.ga, '901000001')
        self.held(self.ga, [date(2026, 9, 7)])
        self.assertEqual(self.c.post('/v1/finance/payroll/pay', {'teacher_id': self.tom.id, 'amount': 1, 'month': '2026-13'},
                                     format='json').status_code, 400)
        self.assertEqual(self.c.post('/v1/finance/payroll/pay', {'teacher_id': self.tom.id, 'amount': 10_000, 'month': '2026-9'},
                                     format='json').status_code, 201)
        # "2026-9" was stored as "2026-09": the payout is seen, no second full payment
        self.assertEqual(PayrollPayment.objects.get().payroll_period, '2026-09')
        self.assertEqual(self.row()['paid'], 10_000)
        self.assertEqual(parse_month('2026-9')[0], '2026-09')

    def test_archived_teacher_with_unpaid_salary_stays_on_the_list(self):
        self.student('Ali', self.ga, '901000001')
        self.percent(100)
        self.held(self.ga, [date(2026, 9, 7)])
        self.tom.is_active = False
        self.tom.save()
        row = self.row()
        self.assertFalse(row['is_active'])
        self.assertGreater(row['balance'], 0)
        # a month with nothing: not listed
        rows = self.c.get('/v1/finance/payroll', {'month': '2026-11'}).json()['data']['rows']
        self.assertFalse(any(r['person_id'] == self.tom.id for r in rows))

    def test_total_owed_is_person_by_person(self):
        anna = User.objects.create_user(phone='998905770011', password='x', first_name='Anna', company=self.company,
                                        user_type=User.UserType.STAFF, staff_role=User.StaffRole.ADMINISTRATOR, branch=None)
        SalarySetting.objects.create(company=self.company, teacher=anna, teacher_name='Anna', salary_type='fixed',
                                     amount=3_000_000, effective_from=SEPT)
        boss = User.objects.create_user(phone='998905770012', password='x', first_name='Boss', company=self.company,
                                        user_type=User.UserType.STAFF, staff_role=User.StaffRole.ADMINISTRATOR, branch=self.a)
        SalarySetting.objects.create(company=self.company, teacher=boss, teacher_name='Boss', salary_type='fixed',
                                     amount=4_000_000, effective_from=SEPT)
        self.c.post('/v1/finance/payroll/pay', {'teacher_id': boss.id, 'amount': 5_000_000, 'month': MONTH, 'force': True}, format='json')
        summary = self.c.get('/v1/finance/payroll', {'month': MONTH}).json()['data']['summary']
        self.assertEqual(summary['total_balance'], 3_000_000)  # Anna is still owed all of it

    def test_payout_split_by_branches_of_groups(self):
        gb = Group.objects.create(company=self.company, branch=self.b, name='GB', course=self.course, teacher=self.tom,
                                  days=Group.Days.CUSTOM, weekdays=[0, 2, 4])
        self.student('A1', self.ga, '901000001')
        self.student('B1', gb, '901000002')
        self.student('B2', gb, '901000003')
        self.percent(100)
        self.held(self.ga, [date(2026, 9, 7)])
        self.held(gb, [date(2026, 9, 7)])
        accrued = self.row()['accrued']
        res = self.c.post('/v1/finance/payroll/pay', {'teacher_id': self.tom.id, 'amount': accrued, 'month': MONTH}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        parts = dict(Expense.objects.values_list('branch__name', 'amount'))
        self.assertEqual(sum(parts.values()), accrued)
        self.assertAlmostEqual(parts['B'] / parts['A'], 2, delta=0.01)

    def test_salary_expense_is_read_only_in_expenses_and_cancelled_in_payroll(self):
        self.student('Ali', self.ga, '901000001')
        self.percent(100)
        self.held(self.ga, [date(2026, 9, 7)])
        res = self.c.post('/v1/finance/payroll/pay', {'teacher_id': self.tom.id, 'amount': 1_000, 'month': MONTH}, format='json').json()['data']
        expense_id = res['expense_ids'][0]
        self.assertEqual(self.c.patch(f'/v1/expense/{expense_id}', {'amount': 1}, format='json').status_code, 400)
        self.assertEqual(self.c.delete(f'/v1/expense/{expense_id}').status_code, 400)
        self.assertEqual(self.c.delete(f"/v1/finance/payroll/payouts/{res['id']}").status_code, 200)
        self.assertFalse(PayrollPayment.objects.exists())
        self.assertFalse(Expense.objects.exists())
        self.assertTrue(AuditLogRecord.objects.filter(entity_type='payroll', action='delete').exists())
        self.assertEqual(self.row()['paid'], 0)

    def test_split_never_loses_a_sum(self):
        self.assertEqual(sum(split_by_weights(1_000_001, {1: 1, 2: 1, 3: 1}).values()), 1_000_001)
        self.assertEqual(split_by_weights(100, {1: 0, 2: 5}), {2: 100})
