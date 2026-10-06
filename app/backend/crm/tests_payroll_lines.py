"""
Finance rebuild, stage 4 (2026-10-05): a teacher is paid their percent only from what the students have
really paid, and only for the lessons really held; nothing that happens later recounts the past.
"""
from datetime import date

from accounts.models import TeacherBranch, User
from crm.models import Group, Student
from crm.tests_charges import Base
from finance.models import SalarySetting
from operations.models import TeacherAttendanceRecord

SEP, OCT = '2026-09', '2026-10'
# Mon / Wed / Fri of September 2026: 13 lessons
SEP_DAYS = [date(2026, 9, d) for d in (2, 4, 7, 9, 11, 14, 16, 18, 21, 23, 25, 28, 30)]


class PayrollBase(Base):
    def setUp(self):
        super().setUp()
        self.rate = SalarySetting.objects.create(company=self.company, teacher=self.tom, teacher_name='Tom',
                                                 salary_type='percent', amount=20)

    def held(self, days, teacher=None, group=None):
        for day in days:
            TeacherAttendanceRecord.objects.create(company=self.company, teacher=teacher or self.tom,
                                                   group=group or self.g, attend_date=day, status=1)

    def row(self, month=SEP, person=None):
        rows = self.c.get('/v1/finance/payroll', {'month': month}).json()['data']['rows']
        return next(r for r in rows if r['person_id'] == (person or self.tom).id)

    def money(self, month=SEP, person=None):
        r = self.row(month, person)
        return r['earned'], r['accrued'], r['waiting']


class PaidOnlyFromPaidTests(PayrollBase):
    def test_ten_students_seven_paid(self):
        """The owner's rule: 10 students, 7 paid -> the teacher is paid for 7 now, for 3 when they pay."""
        students = [self.student(date(2026, 9, 1), name=f'S{i}') for i in range(10)]
        self.held(SEP_DAYS)
        for s in students[:7]:
            self.pay(s, 500_000, date(2026, 9, 3))
        # 10 × 500 000 × 20% = 1 000 000 if everybody pays; 700 000 is payable now
        self.assertEqual(self.money(), (1_000_000, 700_000, 300_000))
        self.assertEqual(self.row()['groups'][0]['students_unpaid'], 3)

        # The salary can be paid only from what is payable
        res = self.c.post('/v1/finance/payroll/pay', {'teacher_id': self.tom.id, 'amount': 700_001, 'month': SEP},
                          format='json')
        self.assertEqual(res.status_code, 400)
        res = self.c.post('/v1/finance/payroll/pay', {'teacher_id': self.tom.id, 'amount': 700_000, 'month': SEP},
                          format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(self.row()['balance'], 0)

        # One debtor pays September in December: the rest for him becomes payable — on the September sheet
        self.at(date(2026, 12, 20))
        self.pay(students[7], 500_000)
        row = self.row()
        self.assertEqual((row['earned'], row['accrued'], row['waiting'], row['balance']),
                         (1_000_000, 800_000, 200_000, 100_000))

    def test_only_lessons_really_held(self):
        aziz = self.student(date(2026, 9, 1))
        self.pay(aziz, 500_000, date(2026, 9, 3))
        self.held(SEP_DAYS[:10])  # missed 3 of 13
        self.assertEqual(self.money(), (76_923, 76_923, 0))  # 500 000 × 10 ÷ 13 × 20%

    def test_part_of_a_month_paid_part_is_payable(self):
        aziz = self.student(date(2026, 9, 1))
        self.pay(aziz, 250_000, date(2026, 9, 3))
        self.held(SEP_DAYS[:12])
        self.assertEqual(self.money(), (92_307, 46_153, 46_154))

    def test_nobody_paid_nothing_is_payable(self):
        self.student(date(2026, 9, 1))
        self.held(SEP_DAYS)
        self.assertEqual(self.money(), (100_000, 0, 100_000))
        res = self.c.post('/v1/finance/payroll/pay', {'teacher_id': self.tom.id, 'amount': 1, 'month': SEP}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_discount_lowers_what_the_teacher_gets(self):
        aziz = self.student(date(2026, 9, 1))
        self.pay(aziz, 400_000, date(2026, 9, 3), discount_amount=100_000)
        self.held(SEP_DAYS)
        self.assertEqual(self.money(), (80_000, 80_000, 0))  # 20% of the 400 000 really paid

    def test_refund_takes_the_payable_back(self):
        aziz = self.student(date(2026, 9, 1))
        payment = self.pay(aziz, 500_000, date(2026, 9, 3))
        self.held(SEP_DAYS)
        self.c.post('/v1/finance/payroll/pay', {'teacher_id': self.tom.id, 'amount': 100_000, 'month': SEP}, format='json')
        self.c.post(f'/v1/replenishments/{payment["id"]}/refund', {'amount': 500_000, 'comment': 'x'}, format='json')
        row = self.row()
        self.assertEqual((row['accrued'], row['waiting'], row['overpaid']), (0, 100_000, 100_000))

    def test_month_of_the_student_runs_from_the_start_date(self):
        aziz = self.student(date(2026, 9, 17))  # his month 17.09–17.10 has 13 lessons too
        self.pay(aziz, 500_000, date(2026, 9, 17))
        self.held(SEP_DAYS)
        self.held([date(2026, 10, 2), date(2026, 10, 5)])
        # In September Tom gave him 6 lessons (18, 21, 23, 25, 28, 30), in October 2 so far
        self.assertEqual(self.money(SEP), (46_153, 46_153, 0))
        self.assertEqual(self.money(OCT), (15_384, 15_384, 0))

    def test_substitute_is_paid_for_the_lessons_they_held(self):
        sam = User.objects.create_user(phone='998905550004', password='x', first_name='Sam', company=self.company,
                                       user_type=User.UserType.TEACHER)
        TeacherBranch.objects.create(teacher=sam, branch=self.a)
        SalarySetting.objects.create(company=self.company, teacher=sam, teacher_name='Sam', salary_type='percent', amount=30)
        aziz = self.student(date(2026, 9, 1))
        self.pay(aziz, 500_000, date(2026, 9, 3))
        self.held(SEP_DAYS[:10])
        self.held(SEP_DAYS[10:], teacher=sam)
        self.assertEqual(self.money()[1], 76_923)                    # 10 lessons at 20%
        self.assertEqual(self.money(person=sam)[1], 34_615)          # 3 lessons at 30%

    def test_frozen_days_and_trial_leavers_are_not_counted(self):
        aziz = self.student(date(2026, 9, 1))
        self.pay(aziz, 500_000, date(2026, 9, 3))
        self.student(date(2026, 9, 1), name='Trial', status=Student.Status.LEFT_TRIAL)
        from crm.models import StudentFreeze
        StudentFreeze.objects.create(company=self.company, student=aziz, start_date=date(2026, 9, 10),
                                     end_date=date(2026, 9, 20))
        self.held([date(2026, 9, 9), date(2026, 9, 14), date(2026, 9, 21)])  # the 14th falls into the freeze
        row = self.row()
        self.assertEqual(row['groups'][0]['student_lessons'], 2)
        self.assertEqual(row['accrued'], 500_000 * 2 * 20 // (13 * 100))


class NothingRecountsThePastTests(PayrollBase):
    """What used to change a month already worked: price, percent, schedule, course."""

    def setUp(self):
        super().setUp()
        self.students = [self.student(date(2026, 9, 1), name=f'S{i}') for i in range(10)]
        self.held(SEP_DAYS)
        for s in self.students:
            self.pay(s, 500_000, date(2026, 9, 3))
        self.assertEqual(self.money(), (1_000_000, 1_000_000, 0))

    def test_price_raised_in_october(self):
        """The hole the owner found: September unpaid to the teacher, the price goes up in October."""
        self.c.patch(f'/v1/courses/{self.course.id}', {'price': 5_000_000}, format='json')
        self.assertEqual(self.money(), (1_000_000, 1_000_000, 0))

    def test_percent_changed_later(self):
        res = self.c.patch(f'/v1/salary-settings/{self.rate.id}', {'amount': 30}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.money(), (1_000_000, 1_000_000, 0))
        # A lesson marked after the change gets the new percent
        self.held([date(2026, 10, 2)])
        self.assertEqual(TeacherAttendanceRecord.objects.get(attend_date=date(2026, 10, 2)).percent, 30)

    def test_schedule_changed_later(self):
        res = self.c.patch(f'/v1/groups/{self.g.id}', {'days': Group.Days.CUSTOM, 'weekdays': [1, 3, 5]}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.money(), (1_000_000, 1_000_000, 0))
        self.assertEqual(self.row()['groups'][0]['held_lessons'], 13)

    def test_group_moved_to_a_dearer_course(self):
        from crm.models import Course
        dear = Course.objects.create(company=self.company, name='Dear', code='b2', price=800_000)
        self.c.patch(f'/v1/groups/{self.g.id}', {'course_id': dear.id}, format='json')
        self.assertEqual(self.money(), (1_000_000, 1_000_000, 0))

    def test_closed_month_grows_only_by_a_late_payment(self):
        late = self.student(date(2026, 9, 1), name='Late')  # an 11th student who has not paid
        self.assertEqual(self.money(), (1_100_000, 1_000_000, 100_000))
        self.assertEqual(self.c.post('/v1/finance/months/close', {'month': SEP}, format='json').status_code, 201)
        self.c.patch(f'/v1/salary-settings/{self.rate.id}', {'amount': 50}, format='json')
        self.c.patch(f'/v1/courses/{self.course.id}', {'price': 5_000_000}, format='json')
        self.assertEqual(self.money(), (1_100_000, 1_000_000, 100_000))
        self.pay(late, 500_000)  # today's money for the September month
        self.assertEqual(self.money(), (1_100_000, 1_100_000, 0))


class PercentAndStaffTests(PayrollBase):
    def test_percent_set_after_the_lessons_still_applies_to_them(self):
        """Real start: lessons are marked first, the CEO sets the percents later."""
        self.rate.delete()
        aziz = self.student(date(2026, 9, 1))
        self.pay(aziz, 500_000, date(2026, 9, 3))
        self.held(SEP_DAYS)
        row = self.row()
        self.assertEqual((row['accrued'], row['groups'][0]['percent_scope']), (0, 'не задан'))
        SalarySetting.objects.create(company=self.company, teacher=self.tom, teacher_name='Tom',
                                     salary_type='percent', amount=20)
        self.assertEqual(self.money(), (100_000, 100_000, 0))

    def test_office_salary_counts_from_the_day_it_was_set(self):
        res = self.c.post('/v1/salary-settings', {'person_id': self.admin.id, 'amount': 3_000_000}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        march = self.c.get('/v1/finance/payroll', {'month': '2026-03'}).json()['data']['rows']
        self.assertEqual([r['accrued'] for r in march if r['person_id'] == self.admin.id and r['accrued']], [])
        self.assertEqual(self.row(OCT, self.admin)['accrued'], 3_000_000)
        res = self.c.post('/v1/finance/payroll/pay', {'person_id': self.admin.id, 'amount': 3_000_000, 'month': '2026-03',
                                                      'branch_id': self.a.id}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_percent_for_a_course_can_be_saved(self):
        # The form crashed here (server error): the course was looked up without being imported
        self.rate.delete()
        res = self.c.post('/v1/salary-settings', {'teacher_id': self.tom.id, 'amount': 25, 'course_id': self.course.id,
                                                  'group_id': None}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        aziz = self.student(date(2026, 9, 1))
        self.pay(aziz, 500_000, date(2026, 9, 3))
        self.held(SEP_DAYS)
        row = self.row()
        self.assertEqual((row['accrued'], row['groups'][0]['percent_scope']), (125_000, 'курс'))
