"""Finance rebuild, stage 2 (2026-10-05): month lines of a student, exact debts, a group's end date is a plan."""
import datetime as dt
from datetime import date
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm import pricing
from crm.group_watch import check_groups
from crm.models import Course, CoursePrice, Group, GroupEnrollment, Student
from finance import charges
from finance.models import Payment, PaymentAllocation, StudentCharge
from operations.models import AuditLogRecord, Reminder
from org.models import Branch, Company

TASHKENT = ZoneInfo('Asia/Tashkent')
TODAY = date(2026, 10, 5)  # a Monday


class Base(TestCase):
    def at(self, day: date):
        """Make the server clock show noon of `day` (Tashkent); the daily jobs run again on the next request."""
        if getattr(self, '_clock', None):
            self._clock.stop()
        self._clock = mock.patch(
            'django.utils.timezone.now', return_value=dt.datetime(day.year, day.month, day.day, 12, 0, tzinfo=TASHKENT),
        )
        self._clock.start()
        pricing._synced_day = None
        charges._done_day = None

    def setUp(self):
        self._clock = None
        self.at(TODAY)
        self.addCleanup(lambda: self._clock.stop())
        self.c = APIClient()
        self.company = Company.objects.create(name='Lines Co', subdomain='linesco')
        self.a = Branch.objects.create(company=self.company, name='A')
        self.ceo = User.objects.create_user(phone='998905550001', password='x', first_name='Ceo', company=self.company,
                                            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO)
        self.admin = User.objects.create_user(phone='998905550002', password='x', first_name='Adm', company=self.company,
                                              user_type=User.UserType.STAFF, staff_role=User.StaffRole.ADMINISTRATOR)
        self.tom = User.objects.create_user(phone='998905550003', password='x', first_name='Tom', company=self.company,
                                            user_type=User.UserType.TEACHER)
        TeacherBranch.objects.create(teacher=self.tom, branch=self.a)
        self.course = Course.objects.create(company=self.company, name='а1', code='a1', price=500_000)
        CoursePrice.objects.filter(course=self.course).update(valid_from=date(2026, 6, 1))
        self.g = Group.objects.create(company=self.company, branch=self.a, name='G', course=self.course, teacher=self.tom,
                                      days=Group.Days.CUSTOM, weekdays=[0, 2, 4])
        self.c.force_authenticate(self.ceo)

    def student(self, start: date, name='Aziz', group='default', **kw):
        group = self.g if group == 'default' else group
        return Student.objects.create(company=self.company, branch=self.a, group=group, first_name=name,
                                      phone=f'90{abs(hash(name)) % 10_000_000:07d}', trial_date=start, **kw)

    def lines(self, s):
        return [(l.period_start, l.period_end, l.amount, l.paid_amount)
                for l in StudentCharge.objects.filter(student=s).order_by('seq')]

    def card(self, s):
        return self.c.get(f'/v1/students/{s.id}').json()['data']

    def pay(self, s, amount, day=None, **extra):
        body = {'student_id': s.id, 'amount': amount, **extra}
        if day:
            body['payment_date'] = day.isoformat()
        res = self.c.post('/v1/replenishments', body, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()['data']


class LinesTests(Base):
    def test_a_month_runs_from_the_start_date(self):
        aziz = self.student(date(2026, 9, 17))
        self.assertEqual(self.lines(aziz), [(date(2026, 9, 17), date(2026, 10, 17), 500_000, 0)])
        card = self.card(aziz)
        self.assertEqual((card['is_debtor'], card['debt_months'], card['debt_amount']), (True, 1, 500_000))
        self.assertEqual(card['next_payment_date'], '2026-09-17')
        self.assertEqual([(r['period_start'], r['period_end'], r['left'], r['state']) for r in card['charges']],
                         [('2026-09-17', '2026-10-17', 500_000, 'unpaid')])

        self.at(date(2026, 10, 17))  # the second month begins: its line appears by itself
        self.c.get('/v1/students')
        self.assertEqual(self.lines(aziz)[1], (date(2026, 10, 17), date(2026, 11, 17), 500_000, 0))

    def test_the_line_of_a_new_month_is_not_a_debt_on_its_first_day(self):
        aziz = self.student(TODAY)
        card = self.card(aziz)
        self.assertEqual(len(card['charges']), 1)
        self.assertFalse(card['is_debtor'])
        self.at(date(2026, 10, 6))
        self.assertTrue(self.card(aziz)['is_debtor'])

    def test_the_31st_does_not_drift(self):
        s = self.student(date(2026, 1, 31))
        starts = [l[0] for l in self.lines(s)]
        self.assertEqual(starts[:4], [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)])

    def test_a_new_price_touches_only_new_months(self):
        """The owner's case: September stays September, whatever the price becomes later."""
        aziz = self.student(date(2026, 9, 17))
        res = self.c.patch(f'/v1/courses/{self.course.id}', {'price': 600_000, 'price_from': '2026-11-01'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.at(date(2026, 12, 20))
        self.c.get('/v1/students')
        self.assertEqual([l[2] for l in self.lines(aziz)], [500_000, 500_000, 600_000, 600_000])
        self.assertEqual(self.card(aziz)['debt_amount'], 2_200_000)

        # He brings 500 000 on 20 December: it closes the September line and nothing else
        payment = self.pay(aziz, 500_000)
        closed = PaymentAllocation.objects.get(payment_id=payment['id'])
        self.assertEqual((closed.charge.period_start, closed.amount), (date(2026, 9, 17), 500_000))
        card = self.card(aziz)
        self.assertEqual((card['debt_months'], card['debt_amount']), (3, 1_700_000))
        self.assertEqual(card['next_payment_date'], '2026-10-17')
        # For the owner it is December money
        pnl = self.c.get('/v1/reports/pnl', {'date_from': '2026-12-01', 'date_to': '2026-12-31'}).json()['data']
        self.assertEqual(pnl['summary']['total_revenue'], 500_000)
        september = self.c.get('/v1/reports/pnl', {'date_from': '2026-09-01', 'date_to': '2026-09-30'}).json()['data']
        self.assertEqual(september['summary']['total_revenue'], 0)

    def test_price_changed_today_does_not_recount_the_running_month(self):
        aziz = self.student(date(2026, 9, 17))
        self.c.patch(f'/v1/courses/{self.course.id}', {'price': 900_000}, format='json')
        self.assertEqual(self.card(aziz)['debt_amount'], 500_000)
        self.at(date(2026, 10, 17))
        self.c.get('/v1/students')
        self.assertEqual([l[2] for l in self.lines(aziz)], [500_000, 900_000])

    def test_no_group_with_a_price_no_lines_yet(self):
        nobody = self.student(date(2026, 9, 1), name='Nogroup', group=None)
        self.assertEqual(self.lines(nobody), [])
        card = self.card(nobody)
        self.assertEqual((card['is_debtor'], card['debt_amount']), (True, 0))  # owes by the calendar, sum unknown
        self.c.patch(f'/v1/students/{nobody.id}', {'group_id': self.g.id}, format='json')
        self.assertEqual([l[0] for l in self.lines(nobody)], [date(2026, 9, 1), date(2026, 10, 1)])

    def test_left_after_trial_has_no_lines(self):
        s = self.student(date(2026, 9, 1), name='Trial', status=Student.Status.LEFT_TRIAL)
        self.assertEqual(self.lines(s), [])

    def test_teacher_does_not_see_the_money_lines(self):
        aziz = self.student(date(2026, 9, 17))
        self.c.force_authenticate(self.tom)
        card = self.c.get(f'/v1/students/{aziz.id}').json()['data']
        self.assertEqual((card['charges'], card['debt_amount'], card['debt_months']), (None, None, None))


class MoneyOnLinesTests(Base):
    def test_part_of_a_month_then_the_rest(self):
        aziz = self.student(date(2026, 9, 17))
        first = self.pay(aziz, 300_000)
        self.assertEqual(first['months_covered'], 0)
        card = self.card(aziz)
        self.assertEqual((card['charges'][0]['paid'], card['charges'][0]['left'], card['charges'][0]['state']),
                         (300_000, 200_000, 'partial'))
        self.assertEqual((card['wallet'], card['debt_amount'], card['is_debtor']), (300_000, 200_000, True))
        second = self.pay(aziz, 200_000)
        self.assertEqual(second['months_covered'], 1)
        card = self.card(aziz)
        self.assertEqual((card['charges'][0]['state'], card['wallet'], card['is_debtor']), ('paid', 0, False))

    def test_paying_ahead_fixes_the_price_of_those_months(self):
        aziz = self.student(date(2026, 9, 17))
        self.c.patch(f'/v1/courses/{self.course.id}', {'price': 600_000, 'price_from': '2026-11-01'}, format='json')
        payment = self.pay(aziz, 1_500_000)  # September and two months ahead, on 5 October
        self.assertEqual(payment['months_covered'], 3)
        self.assertEqual(self.lines(aziz), [
            (date(2026, 9, 17), date(2026, 10, 17), 500_000, 500_000),
            (date(2026, 10, 17), date(2026, 11, 17), 500_000, 500_000),
            (date(2026, 11, 17), date(2026, 12, 17), 500_000, 500_000),  # paid before the rise: old price
        ])
        card = self.card(aziz)
        self.assertEqual((card['is_debtor'], card['next_payment_date']), (False, '2026-12-17'))
        self.at(date(2026, 12, 17))
        self.c.get('/v1/students')
        self.assertEqual(self.lines(aziz)[3][2], 600_000)  # the next month is at the new price

    def test_removed_advance_payment_takes_the_future_months_away(self):
        aziz = self.student(date(2026, 9, 17))
        payment = self.pay(aziz, 1_500_000)
        self.assertEqual(self.c.delete(f'/v1/replenishments/{payment["id"]}').status_code, 200)
        self.assertEqual(self.lines(aziz), [(date(2026, 9, 17), date(2026, 10, 17), 500_000, 0)])
        self.assertEqual(self.card(aziz)['debt_amount'], 500_000)

    def test_refund_reopens_the_newest_month(self):
        aziz = self.student(date(2026, 8, 17))  # two months have begun
        payment = self.pay(aziz, 1_000_000)
        self.assertFalse(self.card(aziz)['is_debtor'])
        res = self.c.post(f'/v1/replenishments/{payment["id"]}/refund', {'amount': 500_000, 'comment': 'x'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual([l[3] for l in self.lines(aziz)], [500_000, 0])
        card = self.card(aziz)
        self.assertEqual((card['is_debtor'], card['debt_amount'], card['next_payment_date']),
                         (True, 500_000, '2026-09-17'))

    def test_money_without_a_price_waits_and_then_closes_the_months(self):
        nobody = self.student(date(2026, 9, 1), name='Nogroup', group=None)
        self.pay(nobody, 700_000)
        self.assertEqual(self.card(nobody)['wallet'], 700_000)
        self.c.patch(f'/v1/students/{nobody.id}', {'group_id': self.g.id}, format='json')
        self.assertEqual([l[3] for l in self.lines(nobody)], [500_000, 200_000])

    def test_a_sum_with_extra_zeros_cannot_pay_hundreds_of_months(self):
        # The owner's fear: the price is still the placeholder 500 and somebody enters a real 500 000
        Course.objects.filter(pk=self.course.pk).update(price=500)
        CoursePrice.objects.filter(course=self.course).update(price=500)
        aziz = self.student(date(2026, 9, 17))
        payment = self.pay(aziz, 500_000)
        self.assertEqual(payment['months_covered'], 25)  # the running month and two years ahead, not 1000 months
        self.assertEqual(self.card(aziz)['wallet'], 500_000 - 25 * 500)  # the rest is in plain sight

    def test_payment_made_by_hand_in_the_base_is_counted_too(self):
        aziz = self.student(date(2026, 9, 17))
        Payment.objects.create(company=self.company, student=aziz, student_name='Aziz', amount=500_000,
                               payment_date=TODAY)
        self.assertEqual(self.lines(aziz)[0][3], 500_000)


class FreezeTests(Base):
    def test_the_running_month_continues_after_the_pause(self):
        aziz = self.student(date(2026, 9, 17))
        self.pay(aziz, 500_000)
        self.c.patch(f'/v1/students/{aziz.id}', {'status': Student.Status.FROZEN}, format='json')  # 12 days left
        self.at(date(2026, 11, 1))
        res = self.c.patch(f'/v1/students/{aziz.id}', {'status': Student.Status.STUDYING}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.lines(aziz), [(date(2026, 9, 17), date(2026, 11, 13), 500_000, 500_000)])
        self.assertEqual(self.card(aziz)['next_payment_date'], '2026-11-13')
        self.at(date(2026, 11, 13))
        self.c.get('/v1/students')
        self.assertEqual(self.lines(aziz)[1][:2], (date(2026, 11, 13), date(2026, 12, 13)))

    def test_no_new_months_while_frozen_and_the_debt_stays(self):
        aziz = self.student(date(2026, 9, 17))
        self.c.patch(f'/v1/students/{aziz.id}', {'status': Student.Status.FROZEN}, format='json')
        self.at(date(2026, 12, 1))
        self.c.get('/v1/students')
        self.assertEqual(len(self.lines(aziz)), 1)
        card = self.card(aziz)
        self.assertEqual((card['is_debtor'], card['debt_amount'], card['overdue_days']), (True, 500_000, 18))
        # Back on 1 December: the same month is still owed, and the pause added no days of delay
        self.c.patch(f'/v1/students/{aziz.id}', {'status': Student.Status.STUDYING}, format='json')
        card = self.card(aziz)
        self.assertEqual((card['debt_amount'], card['overdue_days'], card['next_payment_date']),
                         (500_000, 18, '2026-09-17'))

    def test_frozen_on_the_first_day_of_a_month_does_not_start_it(self):
        aziz = self.student(date(2026, 9, 5))  # the second month would begin today, 5 October
        self.pay(aziz, 500_000, date(2026, 9, 5))
        self.c.patch(f'/v1/students/{aziz.id}', {'status': Student.Status.FROZEN}, format='json')
        self.assertEqual(len(self.lines(aziz)), 1)
        self.at(date(2026, 10, 20))
        self.c.patch(f'/v1/students/{aziz.id}', {'status': Student.Status.STUDYING}, format='json')
        self.assertEqual(self.lines(aziz)[1][:2], (date(2026, 10, 20), date(2026, 11, 20)))


class StartDateTests(Base):
    def test_only_ceo_moves_the_start_date_once_months_are_charged(self):
        aziz = self.student(date(2026, 9, 1))  # owes September and October
        self.assertEqual(self.card(aziz)['debt_amount'], 1_000_000)
        self.c.force_authenticate(self.admin)
        res = self.c.patch(f'/v1/students/{aziz.id}', {'trial_date': '2026-10-05'}, format='json')
        self.assertEqual(res.status_code, 403)
        self.assertIn('только CEO', res.json()['message'])
        # The edit form sends the unchanged date together with the other fields: that is fine
        res = self.c.patch(f'/v1/students/{aziz.id}', {'trial_date': '2026-09-01', 'comment': 'звонили'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.card(aziz)['debt_amount'], 1_000_000)

        self.c.force_authenticate(self.ceo)
        res = self.c.patch(f'/v1/students/{aziz.id}', {'trial_date': '2026-09-20'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.lines(aziz), [(date(2026, 9, 20), date(2026, 10, 20), 500_000, 0)])
        log = AuditLogRecord.objects.get(entity_type='student', action='start_date_change')
        self.assertIn('01.09.2026 → 20.09.2026', log.reason)
        self.assertIn('1 000 000 → 500 000', log.reason)


class LeftTests(Base):
    def test_leaving_stops_the_months_and_keeps_the_exact_debt(self):
        aziz = self.student(date(2026, 9, 1))
        self.c.patch(f'/v1/courses/{self.course.id}', {'price': 700_000, 'price_from': '2026-10-01'}, format='json')
        aziz2 = self.student(date(2026, 9, 1), name='Bek')
        for s in (aziz, aziz2):
            self.c.patch(f'/v1/students/{s.id}', {'status': Student.Status.LEFT}, format='json')
        self.at(date(2026, 12, 1))
        self.c.get('/v1/students')
        self.assertEqual(len(self.lines(aziz)), 2)  # nothing new after leaving
        reminder = Reminder.objects.get(student=aziz2, kind=Reminder.KIND_UNPAID_LEAVE)
        self.assertIn('1 200 000 сум', reminder.details)  # September at 500 000 + October at 700 000
        rows = self.c.get('/v1/reports/left-students').json()['data']['rows']
        row = next(r for r in rows if r['id'] == aziz2.id)
        self.assertEqual((row['debt_months'], row['debt_amount']), (2, 1_200_000))

    def test_ceo_write_off_closes_the_lines(self):
        aziz = self.student(date(2026, 9, 1))
        self.c.patch(f'/v1/students/{aziz.id}', {'status': Student.Status.LEFT}, format='json')
        reminder = Reminder.objects.get(student=aziz, kind=Reminder.KIND_UNPAID_LEAVE)
        res = self.c.post(f'/v1/reminders/{reminder.id}/complete', {'write_off_reason': 'переехали'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(set(StudentCharge.objects.filter(student=aziz).values_list('status', flat=True)), {'written_off'})
        row = next(r for r in self.c.get('/v1/reports/left-students').json()['data']['rows'] if r['id'] == aziz.id)
        self.assertEqual((row['debt_amount'], row['written_off'], row['written_off_months'], row['written_off_amount']),
                         (0, True, 2, 1_000_000))
        self.assertIn('переехали', row['written_off_note'])


class GroupEndDateTests(Base):
    def setUp(self):
        super().setUp()
        self.g.group_end_date = date(2026, 9, 30)
        self.g.save()
        self.aziz = self.student(date(2026, 9, 1))

    def test_lessons_go_on_after_the_planned_end(self):
        res = self.c.post('/v1/reports/teacher-attendance', {'teacher_id': self.tom.id, 'group_id': self.g.id,
                                                             'date': TODAY.isoformat()}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(self.c.post('/v1/reports/attendance', {
            'student_id': self.aziz.id, 'group_id': self.g.id, 'date': TODAY.isoformat(), 'status': 1,
        }, format='json').status_code, 201)

    def test_office_is_reminded_once_and_the_reminder_closes_by_itself(self):
        check_groups()
        reminder = Reminder.objects.get(kind=Reminder.KIND_GROUP_END_PASSED)
        self.assertEqual(reminder.group_id, self.g.id)
        self.assertIn('30.09.2026', reminder.details)
        check_groups()
        self.assertEqual(Reminder.objects.filter(kind=Reminder.KIND_GROUP_END_PASSED).count(), 1)
        # Somebody answered it: no nagging about the same date again
        Reminder.objects.filter(pk=reminder.pk).update(status=Reminder.Status.DONE)
        check_groups()
        self.assertEqual(Reminder.objects.filter(kind=Reminder.KIND_GROUP_END_PASSED).count(), 1)

    def test_extending_the_date_closes_the_reminder(self):
        check_groups()
        self.c.patch(f'/v1/groups/{self.g.id}', {'group_end_date': '2026-12-31'}, format='json')
        check_groups()
        self.assertEqual(Reminder.objects.get(kind=Reminder.KIND_GROUP_END_PASSED).status, Reminder.Status.DONE)

    def test_empty_group_asks_to_be_closed(self):
        check_groups()
        self.assertFalse(Reminder.objects.filter(kind=Reminder.KIND_GROUP_EMPTY).exists())
        self.c.patch(f'/v1/students/{self.aziz.id}', {'status': Student.Status.LEFT}, format='json')
        check_groups()
        empty = Reminder.objects.get(kind=Reminder.KIND_GROUP_EMPTY)
        self.assertIn('не осталось учеников', empty.title)
        # The "end date passed" reminder is not needed any more: nobody studies there
        self.assertEqual(Reminder.objects.get(kind=Reminder.KIND_GROUP_END_PASSED).status, Reminder.Status.DONE)

    def test_a_new_group_without_students_is_left_alone(self):
        Group.objects.create(company=self.company, branch=self.a, name='New', course=self.course)
        check_groups()
        self.assertFalse(Reminder.objects.filter(kind=Reminder.KIND_GROUP_EMPTY).exists())


class FixWrongPriceTests(Base):
    """Real case: «500» was typed instead of «500 000» and the months were already written at 500."""

    def setUp(self):
        super().setUp()
        Course.objects.filter(pk=self.course.pk).update(price=500)
        CoursePrice.objects.filter(course=self.course).update(price=500)
        self.aziz = self.student(date(2026, 9, 1))
        self.bek = self.student(date(2026, 9, 1), name='Bek')
        self.entry = CoursePrice.objects.get(course=self.course)

    def test_unpaid_months_get_the_right_price_paid_ones_stay(self):
        self.pay(self.bek, 500, date(2026, 9, 2))  # Bek really paid September at 500
        self.assertEqual(self.card(self.aziz)['debt_amount'], 1_000)
        res = self.c.patch(f'/v1/courses/{self.course.id}/prices/{self.entry.id}', {'price': 500_000}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual([l[2] for l in self.lines(self.aziz)], [500_000, 500_000])
        self.assertEqual(self.card(self.aziz)['debt_amount'], 1_000_000)
        self.assertEqual([l[2] for l in self.lines(self.bek)], [500, 500_000])  # the paid month is a fact
        log = AuditLogRecord.objects.get(action='price_fix')
        self.assertIn('исправлено: 3', log.reason)
        self.assertIn('оставлено как было: 1', log.reason)

    def test_a_new_price_from_a_date_never_reprices_old_months(self):
        self.c.patch(f'/v1/courses/{self.course.id}', {'price': 500_000}, format='json')  # "from today", not a fix
        self.assertEqual([l[2] for l in self.lines(self.aziz)], [500, 500])


class ReturnTests(Base):
    def test_coming_back_does_not_charge_the_months_of_absence(self):
        aziz = self.student(date(2026, 6, 1))
        with mock.patch('django.utils.timezone.now',
                        return_value=dt.datetime(2026, 7, 10, 12, 0, tzinfo=TASHKENT)):
            self.c.patch(f'/v1/students/{aziz.id}', {'status': Student.Status.LEFT}, format='json')
        self.assertEqual(len(self.lines(aziz)), 2)  # June and July had begun
        # Back on 5 October: August and September are not charged; the old debt is still a debt
        self.c.patch(f'/v1/students/{aziz.id}', {'status': Student.Status.STUDYING}, format='json')
        self.assertEqual([l[0] for l in self.lines(aziz)], [date(2026, 6, 1), date(2026, 7, 1), TODAY])
        card = self.card(aziz)
        self.assertEqual((card['is_debtor'], card['debt_months'], card['debt_amount']), (True, 2, 1_000_000))


class DiscountTests(Base):
    """Stage 3: a discount lowers the month it is given for (never more than half), it is not money."""

    def test_discount_lowers_the_month(self):
        aziz = self.student(date(2026, 9, 17))
        payment = self.pay(aziz, 400_000, discount_amount=100_000)
        self.assertEqual(payment['months_covered'], 1)
        line = self.card(aziz)['charges'][0]
        self.assertEqual((line['price'], line['discount'], line['amount'], line['paid'], line['state']),
                         (500_000, 100_000, 400_000, 400_000, 'paid'))

    def test_not_more_than_half_of_the_price(self):
        aziz = self.student(date(2026, 9, 17))
        res = self.c.post('/v1/replenishments', {'student_id': aziz.id, 'amount': 1, 'discount_amount': 250_001},
                          format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('50%', res.json()['message'])
        self.c.force_authenticate(self.admin)  # the administrator gives a discount freely inside the limit
        self.pay(aziz, 250_000, discount_amount=250_000)
        self.assertEqual(self.card(aziz)['charges'][0]['state'], 'paid')

    def test_discount_is_spread_over_the_months_it_was_given_for(self):
        aziz = self.student(date(2026, 8, 5))  # August, September and October have begun
        payment = self.pay(aziz, 1_200_000, discount_amount=300_000, months_covered=3)
        self.assertEqual(payment['months_covered'], 3)
        self.assertEqual([(l[2], l[3]) for l in self.lines(aziz)], [(400_000, 400_000)] * 3)

    def test_discount_goes_away_with_its_payment(self):
        aziz = self.student(date(2026, 9, 17))
        payment = self.pay(aziz, 400_000, discount_amount=100_000)
        self.c.delete(f'/v1/replenishments/{payment["id"]}')
        line = self.card(aziz)['charges'][0]
        self.assertEqual((line['discount'], line['amount'], line['paid']), (0, 500_000, 0))

    def test_money_is_not_lost_when_a_partly_paid_month_is_written_off(self):
        aziz = self.student(date(2026, 9, 1))
        self.pay(aziz, 300_000, date(2026, 9, 2))
        self.c.patch(f'/v1/students/{aziz.id}', {'status': Student.Status.LEFT}, format='json')
        reminder = Reminder.objects.get(student=aziz, kind=Reminder.KIND_UNPAID_LEAVE)
        self.c.post(f'/v1/reminders/{reminder.id}/complete', {'write_off_reason': 'переехали'}, format='json')
        self.assertEqual([l[3] for l in self.lines(aziz)], [300_000, 0])  # the 300 000 stay on September
        row = next(r for r in self.c.get('/v1/reports/left-students').json()['data']['rows'] if r['id'] == aziz.id)
        self.assertEqual((row['written_off_months'], row['written_off_amount']), (2, 700_000))


class PreviewTests(Base):
    def preview(self, s, **body):
        res = self.c.post(f'/v1/students/{s.id}/payment-preview', body, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()['data']

    def test_shows_what_the_sum_will_do_and_saves_nothing(self):
        aziz = self.student(date(2026, 9, 1))  # owes September and October
        data = self.preview(aziz, amount=800_000)
        self.assertEqual((data['debt_before'], data['debt_after'], data['months_closed']), (1_000_000, 200_000, 1))
        self.assertEqual([(c['period_start'], c['pays'], c['left_after']) for c in data['closes']],
                         [('2026-09-01', 500_000, 0), ('2026-10-01', 300_000, 200_000)])
        self.assertEqual(data['next_payment_date'], '2026-10-01')
        self.assertFalse(Payment.objects.exists())
        self.assertEqual([l[3] for l in self.lines(aziz)], [0, 0])
        self.assertEqual(self.card(aziz)['wallet'], 0)

    def test_months_ahead_are_shown_too(self):
        aziz = self.student(date(2026, 9, 17))
        data = self.preview(aziz, amount=1_000_000)
        self.assertEqual([(c['period_start'], c['ahead']) for c in data['closes']],
                         [('2026-09-17', False), ('2026-10-17', True)])
        self.assertEqual(len(self.lines(aziz)), 1)  # the month ahead was not really written

    def test_too_big_discount_is_reported_and_not_applied(self):
        aziz = self.student(date(2026, 9, 17))
        data = self.preview(aziz, amount=200_000, discount_amount=300_000)
        self.assertIn('50%', data['discount_error'])
        self.assertEqual(data['closes'][0]['amount'], 500_000)

    def test_teacher_cannot_preview(self):
        aziz = self.student(date(2026, 9, 17))
        self.c.force_authenticate(self.tom)
        self.assertEqual(self.c.post(f'/v1/students/{aziz.id}/payment-preview', {'amount': 1}, format='json').status_code, 403)


class MonthPageTests(Base):
    """Stage 5: the «month page» — the students' month lines by the month they begin in."""

    def test_a_debt_paid_later_leaves_its_own_month_page(self):
        aziz = self.student(date(2026, 9, 1))               # September and October
        bek = self.student(date(2026, 9, 17), name='Bek')    # September only
        self.pay(bek, 300_000, date(2026, 9, 20))
        months = {m['month']: m for m in self.c.get('/v1/reports/months').json()['data']}
        self.assertEqual(sorted(months), ['2026-09', '2026-10'])
        sep = months['2026-09']
        self.assertEqual((sep['title'], sep['lines'], sep['charged'], sep['paid'], sep['left'], sep['debtors']),
                         ('Сентябрь 2026', 2, 1_000_000, 300_000, 700_000, 2))

        page = self.c.get('/v1/reports/months', {'month': '2026-09'}).json()['data']
        self.assertEqual([(r['student'], r['left'], r['state']) for r in page['rows']],
                         [('Aziz', 500_000, 'unpaid'), ('Bek', 200_000, 'partial')])

        # Aziz pays September in December: the September page shows it paid, October is still owed
        self.at(date(2026, 12, 20))
        self.pay(aziz, 500_000)
        page = self.c.get('/v1/reports/months', {'month': '2026-09', 'only_unpaid': 1}).json()['data']
        self.assertEqual([r['student'] for r in page['rows']], ['Bek'])
        self.assertEqual(page['summary']['left'], 200_000)

    def test_who_sees_it(self):
        self.student(date(2026, 9, 1))
        self.c.force_authenticate(self.admin)   # takes payments: sees debts
        self.assertEqual(self.c.get('/v1/reports/months').status_code, 200)
        self.c.force_authenticate(self.tom)     # a teacher never sees money
        self.assertEqual(self.c.get('/v1/reports/months').status_code, 403)


class BigCardsTests(Base):
    """The wide group and teacher cards: who owes in a group (never shown to a teacher), the teacher's groups."""

    def test_group_card_shows_who_owes(self):
        aziz = self.student(date(2026, 9, 1))
        bek = self.student(date(2026, 9, 1), name='Bek')
        self.pay(bek, 1_000_000, date(2026, 9, 2))
        data = self.c.get(f'/v1/groups/{self.g.id}').json()['data']
        self.assertEqual((data['debtors_count'], data['debt_total']), (1, 1_000_000))
        rows = {r['id']: r for r in data['students']}
        self.assertEqual((rows[aziz.id]['is_debtor'], rows[aziz.id]['debt_amount']), (True, 1_000_000))
        self.assertEqual((rows[bek.id]['is_debtor'], rows[bek.id]['debt_amount']), (False, 0))

    def test_teacher_sees_the_group_without_money(self):
        self.student(date(2026, 9, 1))
        self.c.force_authenticate(self.tom)
        data = self.c.get(f'/v1/groups/{self.g.id}').json()['data']
        self.assertNotIn('debtors_count', data)
        self.assertNotIn('debt_amount', data['students'][0])

    def test_teacher_card_lists_groups_with_time_and_students(self):
        self.student(date(2026, 9, 1))
        data = self.c.get(f'/v1/user/teacher/{self.tom.id}').json()['data']
        group = data['groups'][0]
        self.assertEqual((group['name'], group['students_count'], group['status']), ('G', 1, 2))
