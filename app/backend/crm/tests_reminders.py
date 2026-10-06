"""Reminders audit (2026-09-28): who sees what, teachers close their own, write-off removes the debt, history is frozen."""

from datetime import date, datetime, timezone as dt_tz
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm.models import Course, Group, Student
from finance.models import Payment
from operations.models import AuditLogRecord, Reminder
from org.models import Branch, Company


class Base(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Rem Co', subdomain='remco')
        self.b1 = Branch.objects.create(company=self.company, name='B1')
        self.b2 = Branch.objects.create(company=self.company, name='B2')
        self.ceo = self.user('998907770001', 'Ceo', User.StaffRole.CEO)
        self.admin = self.user('998907770002', 'Admin', User.StaffRole.ADMINISTRATOR)
        self.admin2 = self.user('998907770003', 'Admin2', User.StaffRole.ADMINISTRATOR)
        self.dir1 = self.user('998907770004', 'Dir', User.StaffRole.BRANCH_DIRECTOR, branch=self.b1)
        self.staff_b2 = self.user('998907770005', 'Staff2', User.StaffRole.ADMINISTRATOR, branch=self.b2)
        self.teacher = User.objects.create_user(
            phone='998907770006', password='x', first_name='Teach', company=self.company,
            user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=self.teacher, branch=self.b1)
        self.teacher_b2 = User.objects.create_user(
            phone='998907770007', password='x', first_name='Teach2', company=self.company,
            user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=self.teacher_b2, branch=self.b2)
        self.student_user = User.objects.create_user(
            phone='998907770008', password='x', first_name='StudUser', company=self.company,
            user_type=User.UserType.STUDENT,
        )
        self.gone = self.user('998907770009', 'Gone', User.StaffRole.ADMINISTRATOR, is_active=False)
        self.course = Course.objects.create(company=self.company, name='En', price=800_000)
        self.g1 = Group.objects.create(company=self.company, branch=self.b1, name='G1', course=self.course)
        self.today = timezone.localdate()

    def user(self, phone, name, role, **kw):
        return User.objects.create_user(
            phone=phone, password='x', first_name=name, company=self.company,
            user_type=User.UserType.STAFF, staff_role=role, **kw,
        )

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def reminder(self, **kw):
        kw.setdefault('title', 'Call')
        kw.setdefault('due_date', self.today)
        return Reminder.objects.create(company=self.company, **kw)

    def ids(self, user):
        return {r['id'] for r in self.as_(user).get('/v1/reminders').json()['data']['items']}

    def left_with_debt(self, first_name='Ali'):
        s = Student.objects.create(
            company=self.company, branch=self.b1, group=self.g1, first_name=first_name, phone='901112233',
            trial_date=date(2026, 4, 1),
        )
        self.as_(self.ceo).patch(f'/v1/students/{s.id}', {'status': Student.Status.LEFT})
        return s, Reminder.objects.get(student=s, kind=Reminder.KIND_UNPAID_LEAVE)


class VisibilityTests(Base):
    def test_everybody_sees_own_ceo_sees_all(self):
        ceo_own = self.reminder(assigned_to=self.ceo, created_by=self.ceo)
        admin_own = self.reminder(assigned_to=self.admin, created_by=self.admin)
        given_by_admin = self.reminder(assigned_to=self.admin2, created_by=self.admin)
        common = self.reminder(assigned_to=None, created_by=self.ceo)

        self.assertEqual(self.ids(self.ceo), {ceo_own.id, admin_own.id, given_by_admin.id, common.id})
        # own + given by me + common office reminders
        self.assertEqual(self.ids(self.admin), {admin_own.id, given_by_admin.id, common.id})
        self.assertEqual(self.ids(self.admin2), {given_by_admin.id, common.id})
        # director: no longer sees (or deletes) the CEO's personal reminders
        self.assertNotIn(ceo_own.id, self.ids(self.dir1))
        self.assertEqual(self.as_(self.dir1).delete(f'/v1/reminders/{ceo_own.id}').status_code, 404)
        self.assertTrue(Reminder.objects.filter(pk=ceo_own.pk).exists())

    def test_director_common_reminders_only_about_own_branch(self):
        s2 = Student.objects.create(company=self.company, branch=self.b2, first_name='Far', phone='905550000')
        other_branch = self.reminder(student=s2, kind='online_payment_check')
        self.assertNotIn(other_branch.id, self.ids(self.dir1))
        self.assertIn(other_branch.id, self.ids(self.admin))

    def test_new_reminder_remembers_author(self):
        res = self.as_(self.admin).post(
            '/v1/reminders', {'title': 'Call parent', 'assigned_to_id': self.teacher.id}, format='json',
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(Reminder.objects.get(pk=res.json()['data']['id']).created_by_id, self.admin.id)
        self.assertIn(res.json()['data']['id'], self.ids(self.admin))

    def test_empty_assignee_is_common_reminder(self):
        res = self.as_(self.admin).post('/v1/reminders', {'title': 'Office', 'assigned_to_id': None}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertIsNone(Reminder.objects.get(pk=res.json()['data']['id']).assigned_to_id)
        self.assertIn(res.json()['data']['id'], self.ids(self.admin2))


class TeacherTests(Base):
    def test_teacher_closes_own_reminder_only(self):
        mine = self.reminder(assigned_to=self.teacher, created_by=self.admin)
        other = self.reminder(assigned_to=self.admin)
        c = self.as_(self.teacher)
        self.assertEqual(self.ids(self.teacher), {mine.id})
        self.assertEqual(c.post(f'/v1/reminders/{mine.id}/complete').status_code, 200)
        mine.refresh_from_db()
        self.assertEqual(mine.status, Reminder.Status.DONE)
        self.assertEqual(c.post(f'/v1/reminders/{other.id}/complete').status_code, 404)

    def test_teacher_still_cannot_create_edit_or_delete(self):
        mine = self.reminder(assigned_to=self.teacher)
        c = self.as_(self.teacher)
        self.assertEqual(c.post('/v1/reminders', {'title': 'x'}, format='json').status_code, 403)
        self.assertEqual(c.patch(f'/v1/reminders/{mine.id}', {'title': 'y'}, format='json').status_code, 403)
        self.assertEqual(c.delete(f'/v1/reminders/{mine.id}').status_code, 403)

    def test_teacher_counter(self):
        self.reminder(assigned_to=self.teacher, due_date=date(2026, 1, 1))
        self.reminder(assigned_to=self.teacher)
        self.reminder(assigned_to=self.admin)
        data = self.as_(self.teacher).get('/v1/reminders/summary').json()['data']
        self.assertEqual(data, {'overdue': 1, 'today': 1, 'total': 2})


class AssigneeTests(Base):
    def test_list_has_active_staff_and_teachers_no_students(self):
        rows = self.as_(self.admin).get('/v1/reminders/assignees').json()['data']
        ids = {r['id'] for r in rows}
        self.assertIn(self.teacher.id, ids)
        self.assertIn(self.ceo.id, ids)
        self.assertNotIn(self.student_user.id, ids)
        self.assertNotIn(self.gone.id, ids)

    def test_server_rejects_student_and_inactive(self):
        c = self.as_(self.admin)
        for bad in (self.student_user, self.gone):
            res = c.post('/v1/reminders', {'title': 't', 'assigned_to_id': bad.id}, format='json')
            self.assertEqual(res.status_code, 400)

    def test_director_gives_reminders_within_branch(self):
        ids = {r['id'] for r in self.as_(self.dir1).get('/v1/reminders/assignees').json()['data']}
        self.assertIn(self.teacher.id, ids)
        self.assertIn(self.ceo.id, ids)  # staff without a branch
        self.assertNotIn(self.teacher_b2.id, ids)
        self.assertNotIn(self.staff_b2.id, ids)
        res = self.client.post('/v1/reminders', {'title': 't', 'assigned_to_id': self.teacher_b2.id}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_teacher_has_no_access_to_assignees(self):
        self.assertEqual(self.as_(self.teacher).get('/v1/reminders/assignees').status_code, 403)

    def test_title_length_checked(self):
        res = self.as_(self.admin).post('/v1/reminders', {'title': 'x' * 256}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('255', res.json()['message'])
        rem = self.reminder(assigned_to=self.admin)
        res = self.client.patch(f'/v1/reminders/{rem.id}', {'title': 'x' * 300}, format='json')
        self.assertEqual(res.status_code, 400)


class ClosedAreFrozenTests(Base):
    def test_done_reminder_cannot_be_changed(self):
        rem = self.reminder(assigned_to=self.admin, status=Reminder.Status.DONE)
        c = self.as_(self.admin)
        self.assertEqual(c.patch(f'/v1/reminders/{rem.id}', {'title': 'y'}, format='json').status_code, 400)
        self.assertEqual(c.delete(f'/v1/reminders/{rem.id}').status_code, 400)
        self.assertEqual(c.post(f'/v1/reminders/{rem.id}/complete').status_code, 400)

    def test_write_off_history_cannot_be_rewritten(self):
        s, rem = self.left_with_debt()
        c = self.as_(self.ceo)
        res = c.post(f'/v1/reminders/{rem.id}/complete', {'write_off_reason': 'moved away'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        rem.refresh_from_db()
        self.assertTrue(rem.written_off)
        note = rem.resolution
        self.assertIn('moved away', note)
        admin = self.as_(self.admin)
        self.assertEqual(admin.post(f'/v1/reminders/{rem.id}/complete').status_code, 400)
        self.assertEqual(admin.patch(f'/v1/reminders/{rem.id}', {'title': 'x'}, format='json').status_code, 400)
        self.assertEqual(admin.delete(f'/v1/reminders/{rem.id}').status_code, 400)
        rem.refresh_from_db()
        self.assertEqual(rem.resolution, note)
        self.assertTrue(AuditLogRecord.objects.filter(action='debt_write_off', entity_id=s.id).exists())
        # gone from the interface
        self.assertNotIn(rem.id, self.ids(self.ceo))
        self.assertEqual(self.as_(self.ceo).get('/v1/dashboard').json()['data']['unpaid_leavers'], [])


class WriteOffInReportsTests(Base):
    def report(self, **params):
        return self.as_(self.ceo).get('/v1/reports/left-students', params).json()['data']

    def test_written_off_debt_is_not_a_debt_any_more(self):
        s, rem = self.left_with_debt()
        before = self.report()
        self.assertEqual(before['summary']['with_debt'], 1)
        self.as_(self.ceo).post(f'/v1/reminders/{rem.id}/complete', {'write_off_reason': 'moved away'}, format='json')

        data = self.report()
        self.assertEqual(data['summary']['with_debt'], 0)
        self.assertEqual(data['summary']['written_off'], 1)
        row = data['rows'][0]
        self.assertEqual(row['debt_months'], 0)
        self.assertTrue(row['written_off'])
        self.assertEqual(row['written_off_months'], before['rows'][0]['debt_months'])
        self.assertEqual(row['written_off_amount'], before['rows'][0]['debt_amount'])
        self.assertIn('moved away', row['written_off_note'])
        # "only with debt" filter no longer lists them
        self.assertEqual(self.report(with_debt='1')['rows'], [])

    def test_paid_debt_is_real_income_and_closes_normally(self):
        s, rem = self.left_with_debt()
        months = self.report()['rows'][0]['debt_months']
        # the office takes the money in the student's card: an ordinary payment (shows in finance income)
        Payment.objects.create(
            company=self.company, student=s, student_name=s.full_name, amount=800_000 * months,
            months_covered=months, transaction_type=Payment.TransactionType.PAYMENT,
        )
        res = self.as_(self.admin).post(f'/v1/reminders/{rem.id}/complete')
        self.assertEqual(res.status_code, 200, res.content)
        rem.refresh_from_db()
        self.assertFalse(rem.written_off)
        self.assertIn('оплачен', rem.resolution)
        row = self.report()['rows'][0]
        self.assertEqual(row['debt_months'], 0)
        self.assertFalse(row['written_off'])

    def test_leaving_again_after_write_off_is_a_new_debt(self):
        from datetime import timedelta
        from django.utils import timezone

        s, rem = self.left_with_debt()
        self.as_(self.ceo).post(f'/v1/reminders/{rem.id}/complete', {'write_off_reason': 'moved away'}, format='json')
        # Month lines (2026-10-05): the forgiven months stay forgiven and the months of absence are not
        # charged — a new month starts on the day of return
        self.client.patch(f'/v1/students/{s.id}', {'status': Student.Status.STUDYING, 'group_id': self.g1.id})
        self.assertFalse(self.client.get(f'/v1/students/{s.id}').json()['data']['is_debtor'])
        # Studies 40 days without paying and leaves again: that is a new debt, of the new months only
        later = timezone.now() + timedelta(days=40)
        with mock.patch('django.utils.timezone.now', return_value=later):
            self.client.patch(f'/v1/students/{s.id}', {'status': Student.Status.LEFT})
        self.assertEqual(Reminder.objects.filter(student=s, kind=Reminder.KIND_UNPAID_LEAVE).count(), 2)
        row = self.report()['rows'][0]
        # The month that was running when they left (and was forgiven) simply went on; the next one
        # began after the return and is the new debt
        self.assertEqual(row['debt_months'], 1)
        self.assertTrue(row['written_off'])  # the old months are still shown as forgiven


class ReturnAndDatesTests(Base):
    def test_returned_student_leaves_the_red_block(self):
        s, rem = self.left_with_debt()
        self.as_(self.ceo).patch(f'/v1/students/{s.id}', {'status': Student.Status.STUDYING, 'group_id': self.g1.id})
        rem.refresh_from_db()
        self.assertEqual(rem.status, Reminder.Status.DONE)
        self.assertIn('вернулся', rem.resolution)
        self.assertEqual(self.client.get('/v1/reminders').json()['data']['pinned'], [])
        # the debt itself is kept: now an ordinary debtor
        self.assertTrue(self.client.get(f'/v1/students/{s.id}').json()['data']['is_debtor'])

    def test_dashboard_leave_date_is_tashkent_date(self):
        s = Student.objects.create(
            company=self.company, branch=self.b1, group=self.g1, first_name='Night', phone='901113344',
            trial_date=date(2026, 4, 1),
        )
        # 02:00 in Tashkent on 28 Sep = 21:00 UTC on 27 Sep
        with mock.patch('django.utils.timezone.now', return_value=datetime(2026, 9, 27, 21, 0, tzinfo=dt_tz.utc)):
            self.as_(self.ceo).patch(f'/v1/students/{s.id}', {'status': Student.Status.LEFT})
        leavers = self.client.get('/v1/dashboard').json()['data']['unpaid_leavers']
        self.assertEqual(leavers[0]['created_at'], '2026-09-28')
        row = self.client.get('/v1/reports/left-students').json()['data']['rows'][0]
        self.assertEqual(row['left_at'], '2026-09-28')

    def test_dashboard_lists_ordinary_reminders_separately(self):
        s, leave = self.left_with_debt()
        overdue = self.reminder(assigned_to=self.ceo, due_date=date(2026, 1, 1))
        future = self.reminder(assigned_to=self.ceo, due_date=date(2099, 1, 1))
        ids = [r['id'] for r in self.as_(self.ceo).get('/v1/dashboard').json()['data']['reminders']]
        self.assertIn(overdue.id, ids)
        self.assertNotIn(future.id, ids)
        self.assertNotIn(leave.id, ids)


class OnlineMoneyWaitsInWalletTests(Base):
    """Online money of a student without a course price waits in the копилка and is counted by itself."""

    def setUp(self):
        super().setUp()
        from api.v1.views_payments import _after_online_payment
        from finance.wallet import PRICE_PENDING

        self.s = Student.objects.create(
            company=self.company, branch=self.b1, first_name='Aziz', phone='901115566', trial_date=date(2026, 9, 1),
        )
        self.payment = Payment.objects.create(
            company=self.company, student=self.s, student_name='Aziz', amount=800_000, months_covered=0,
            month_price=PRICE_PENDING, transaction_type=Payment.TransactionType.PAYMENT,
            payment_date=date(2026, 9, 1), method=Payment.Method.CARD,
        )
        _after_online_payment(self.s, self.payment)
        self.client.force_authenticate(self.ceo)

    def card(self):
        return self.client.get(f'/v1/students/{self.s.id}').json()['data']

    def test_money_waits_in_wallet_with_reminder(self):
        card = self.card()
        self.assertEqual(card['wallet'], 800_000)
        self.assertEqual(card['paid_count'], 0)
        rem = Reminder.objects.get(kind=Reminder.KIND_ONLINE_PAYMENT_CHECK)
        self.assertIn('копилке', rem.details)
        self.assertEqual(rem.student_id, self.s.id)

    def test_putting_into_group_counts_months_and_closes_reminder(self):
        course = Course.objects.create(company=self.company, name='Kids', price=600_000)
        group = Group.objects.create(company=self.company, branch=self.b1, name='K1', course=course)
        res = self.client.patch(f'/v1/students/{self.s.id}', {'group_id': group.id}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, 800_000)  # money never changes
        self.assertEqual(self.payment.month_price, 600_000)
        self.assertEqual(self.payment.months_covered, 1)
        card = self.card()
        self.assertEqual(card['wallet'], 200_000)
        rem = Reminder.objects.get(kind=Reminder.KIND_ONLINE_PAYMENT_CHECK)
        self.assertEqual(rem.status, Reminder.Status.DONE)
        self.assertIn('засчитаны', rem.resolution)

    def test_group_gets_priced_course_later(self):
        group = Group.objects.create(company=self.company, branch=self.b1, name='NoCourse')
        self.client.patch(f'/v1/students/{self.s.id}', {'group_id': group.id}, format='json')
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.months_covered, 0)
        course = Course.objects.create(company=self.company, name='Free', price=0)
        group.course = course
        group.save()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.months_covered, 0)  # price still unknown
        course.price = 400_000
        course.save()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.months_covered, 2)
        self.assertEqual(self.card()['wallet'], 0)

    def test_months_of_waiting_money_are_not_typed_by_hand(self):
        res = self.client.patch(f'/v1/replenishments/{self.payment.id}', {'months_covered': 5}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.months_covered, 0)
        self.assertEqual(self.payment.amount, 800_000)
