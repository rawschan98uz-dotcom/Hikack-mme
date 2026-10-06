"""Students block: freeze keeps debts (problem 1) and office reminder about students who left without paying."""
from datetime import date, datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm.models import Course, Group, Student
from finance.models import Payment
from operations.models import Reminder
from org.models import Branch, Company


def aware(d: date):
    return timezone.make_aware(datetime(d.year, d.month, d.day, 12, 0))


class Base(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Freeze Co', subdomain='freeze')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.other_branch = Branch.objects.create(company=self.company, name='Second')
        self.ceo = User.objects.create_user(
            phone='998909880001', password='x', first_name='C', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.course = Course.objects.create(company=self.company, name='English', price=800_000)
        self.group = Group.objects.create(company=self.company, branch=self.branch, name='G', course=self.course)
        self.client.force_authenticate(self.ceo)

    def student(self, trial, **kw):
        return Student.objects.create(
            company=self.company, branch=kw.pop('branch', self.branch), group=kw.pop('group', self.group),
            first_name=kw.pop('first_name', 'Alisher'), phone=kw.pop('phone', '901234567'), trial_date=trial, **kw,
        )

    def pay(self, s, months):
        Payment.objects.create(
            company=self.company, student=s, student_name=s.full_name, amount=800_000 * months,
            months_covered=months, transaction_type=Payment.TransactionType.PAYMENT,
        )

    def detail(self, s):
        return self.client.get(f'/v1/students/{s.id}').json()['data']

    def freeze(self, s, frozen_on, resume_on):
        self.client.patch(f'/v1/students/{s.id}', {'status': 2})
        Student.objects.filter(pk=s.pk).update(frozen_at=aware(frozen_on))
        return self.client.patch(f'/v1/students/{s.id}', {'status': 1, 'trial_date': resume_on.isoformat()})


class FreezeKeepsScheduleTests(Base):
    def test_freeze_does_not_forgive_debt(self):
        s = self.student(date(2026, 4, 1))
        self.pay(s, 1)  # paid April only -> unpaid since 1 May
        res = self.freeze(s, date(2026, 9, 26), date(2026, 9, 27))
        self.assertEqual(res.status_code, 200, res.content)
        d = self.detail(s)
        self.assertTrue(d['is_debtor'])
        # Month lines (2026-10-05): the unpaid May line is history and keeps its own date; the same
        # months are owed as on the day of freezing (the 1-day pause is only taken out of the days of delay)
        self.assertEqual(d['next_payment_date'], '2026-05-01')
        self.assertGreaterEqual(d['debt_months'], 5)  # May … September, and whatever began after the return

    def test_prepaid_time_is_kept(self):
        s = self.student(date(2026, 6, 1))
        self.pay(s, 3)  # paid until 1 Sep
        self.freeze(s, date(2026, 7, 1), date(2026, 10, 1))
        self.assertEqual(self.detail(s)['next_payment_date'], '2026-12-01')

    def test_repeated_freezes_give_no_free_months(self):
        s = self.student(date(2026, 1, 1))
        self.pay(s, 3)  # paid until 1 Apr
        self.freeze(s, date(2026, 2, 1), date(2026, 5, 1))   # 2 months left -> until 1 Jul
        self.freeze(s, date(2026, 6, 1), date(2026, 9, 1))   # 1 month left -> until 1 Oct
        self.assertEqual(self.detail(s)['next_payment_date'], '2026-10-01')

    def test_prepaid_days_are_kept_too(self):
        s = self.student(date(2026, 6, 1))
        self.pay(s, 1)  # paid until 1 Jul
        self.freeze(s, date(2026, 6, 21), date(2026, 8, 1))   # 10 days left
        self.assertEqual(self.detail(s)['next_payment_date'], '2026-08-11')

    def test_resume_before_freeze_is_rejected(self):
        s = self.student(date(2026, 6, 1))
        res = self.freeze(s, date(2026, 9, 10), date(2026, 9, 1))
        self.assertEqual(res.status_code, 400)
        self.assertIn('раньше даты заморозки', res.json()['message'])
        s.refresh_from_db()
        self.assertEqual(s.status, Student.Status.FROZEN)


class UnpaidLeaveReminderTests(Base):
    def test_leaving_with_debt_creates_reminder_and_dashboard_block(self):
        s = self.student(date(2026, 4, 1), parent_telegram='@mom')
        self.pay(s, 1)
        self.client.patch(f'/v1/students/{s.id}', {'status': Student.Status.LEFT})

        reminder = Reminder.objects.get(student=s, kind=Reminder.KIND_UNPAID_LEAVE)
        self.assertIn('Alisher', reminder.title)
        self.assertIn('с 01.05.2026', reminder.details)
        self.assertIn('800 000', reminder.details)
        self.assertIn('@mom', reminder.details)
        self.assertIsNone(reminder.assigned_to_id)

        block = self.client.get('/v1/dashboard').json()['data']['unpaid_leavers']
        self.assertEqual([r['student_id'] for r in block], [s.id])

        # "Решено" is locked until the debt is paid; once paid it removes the block from the dashboard
        self.assertTrue(block[0]['locked'])
        self.assertEqual(self.client.post(f'/v1/reminders/{reminder.id}/complete').status_code, 400)
        self.pay(s, 6)
        self.assertEqual(self.client.post(f'/v1/reminders/{reminder.id}/complete').status_code, 200)
        self.assertEqual(self.client.get('/v1/dashboard').json()['data']['unpaid_leavers'], [])

    def test_delete_button_also_reminds_and_keeps_price_from_history(self):
        s = self.student(date(2026, 4, 1))
        self.pay(s, 1)
        self.client.delete(f'/v1/students/{s.id}')
        reminder = Reminder.objects.get(student=s, kind=Reminder.KIND_UNPAID_LEAVE)
        self.assertIn('800 000', reminder.details)

    def test_graduated_with_debt_reminds(self):
        s = self.student(date(2026, 4, 1))
        self.pay(s, 1)
        self.client.patch(f'/v1/students/{s.id}', {'status': Student.Status.GRADUATED})
        self.assertTrue(Reminder.objects.filter(student=s, title__startswith='Завершил курс').exists())

    def test_no_reminder_when_everything_paid_or_after_trial(self):
        paid = self.student(date(2026, 9, 1))
        self.pay(paid, 3)
        self.client.patch(f'/v1/students/{paid.id}', {'status': Student.Status.LEFT})
        trial = self.student(date(2026, 4, 1), first_name='Trial', phone='901234568')
        self.client.patch(f'/v1/students/{trial.id}', {'status': Student.Status.LEFT_TRIAL})
        self.assertFalse(Reminder.objects.filter(kind=Reminder.KIND_UNPAID_LEAVE).exists())

    def test_no_duplicate_reminder(self):
        s = self.student(date(2026, 4, 1))
        self.client.patch(f'/v1/students/{s.id}', {'status': Student.Status.LEFT})
        self.client.patch(f'/v1/students/{s.id}', {'comment': 'called parents'})
        self.assertEqual(Reminder.objects.filter(student=s).count(), 1)

    def test_left_report_shows_debt_and_filters(self):
        debtor = self.student(date(2026, 4, 1))
        self.pay(debtor, 1)
        clean = self.student(date(2026, 9, 1), first_name='Clean', phone='901234569')
        self.pay(clean, 3)
        for s in (debtor, clean):
            self.client.patch(f'/v1/students/{s.id}', {'status': Student.Status.LEFT})

        data = self.client.get('/v1/reports/left-students').json()['data']
        self.assertEqual(data['summary']['with_debt'], 1)
        rows = {r['full_name']: r for r in data['rows']}
        self.assertGreaterEqual(rows['Alisher']['debt_months'], 5)
        self.assertEqual(rows['Alisher']['debt_amount'], rows['Alisher']['debt_months'] * 800_000)
        self.assertEqual(rows['Clean']['debt_months'], 0)

        only = self.client.get('/v1/reports/left-students?with_debt=1').json()['data']['rows']
        self.assertEqual([r['full_name'] for r in only], ['Alisher'])

    def test_teacher_and_other_branch_director_do_not_see_it(self):
        other_group = Group.objects.create(company=self.company, branch=self.other_branch, name='G2', course=self.course)
        s = self.student(date(2026, 4, 1), branch=self.other_branch, group=other_group)
        self.client.patch(f'/v1/students/{s.id}', {'status': Student.Status.LEFT})
        reminder = Reminder.objects.get(student=s)

        director = User.objects.create_user(
            phone='998909880002', password='x', first_name='D', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.BRANCH_DIRECTOR, branch=self.branch,
        )
        teacher = User.objects.create_user(
            phone='998909880003', password='x', first_name='T', company=self.company,
            user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=teacher, branch=self.branch)
        for user in (director, teacher):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get('/v1/dashboard').json()['data'].get('unpaid_leavers', []), [])
        self.client.force_authenticate(director)
        self.assertEqual(self.client.post(f'/v1/reminders/{reminder.id}/complete').status_code, 404)


class DebtReminderLockTests(Base):
    """Owner, 2026-09-27: the unpaid-leave reminder cannot be closed until paid; only CEO may write it off."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            phone='998909880010', password='x', first_name='Adm', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.ADMINISTRATOR,
        )
        self.s = self.student(date(2026, 4, 1))
        self.pay(self.s, 1)  # unpaid since 1 May
        self.client.patch(f'/v1/students/{self.s.id}', {'status': Student.Status.LEFT})
        self.reminder = Reminder.objects.get(student=self.s, kind=Reminder.KIND_UNPAID_LEAVE)

    def test_admin_cannot_close_edit_or_delete_while_unpaid(self):
        self.client.force_authenticate(self.admin)
        url = f'/v1/reminders/{self.reminder.id}'
        self.assertEqual(self.client.post(f'{url}/complete').status_code, 400)
        self.assertEqual(self.client.post(f'{url}/complete', {'write_off_reason': 'просто так'}).status_code, 400)
        self.assertEqual(self.client.patch(url, {'title': 'x'}).status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 400)
        self.assertTrue(Reminder.objects.filter(pk=self.reminder.pk).exclude(status=Reminder.Status.DONE).exists())

    def test_partial_payment_keeps_it_locked_full_payment_unlocks(self):
        self.client.force_authenticate(self.admin)
        self.pay(self.s, 1)
        item = self.client.get('/v1/reminders').json()['data']['pinned'][0]
        self.assertTrue(item['locked'])
        before = item['debt_months']
        self.pay(self.s, before)
        item = self.client.get('/v1/reminders').json()['data']['pinned'][0]
        self.assertFalse(item['locked'])
        res = self.client.post(f'/v1/reminders/{self.reminder.id}/complete')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn('оплачен', res.json()['data']['resolution'])

    def test_ceo_write_off_needs_reason_and_is_logged(self):
        from operations.models import AuditLogRecord

        url = f'/v1/reminders/{self.reminder.id}/complete'
        self.assertEqual(self.client.post(url).status_code, 400)
        res = self.client.post(url, {'write_off_reason': 'родители отказались, списали'})
        self.assertEqual(res.status_code, 200, res.content)
        self.reminder.refresh_from_db()
        self.assertEqual(self.reminder.status, Reminder.Status.DONE)
        self.assertIn('родители отказались', self.reminder.resolution)
        self.assertTrue(AuditLogRecord.objects.filter(
            entity_type='student', entity_id=self.s.id, action='debt_write_off',
        ).exists())

    def test_pinned_on_top_not_in_tabs(self):
        Reminder.objects.create(company=self.company, title='Call parents', due_date=timezone.localdate())
        data = self.client.get('/v1/reminders').json()['data']
        self.assertEqual([r['id'] for r in data['pinned']], [self.reminder.id])
        in_tabs = [r['id'] for tab in data['buckets'].values() for r in tab]
        self.assertNotIn(self.reminder.id, in_tabs)
        self.assertEqual(len(in_tabs), 1)

    def test_regular_reminders_still_close_normally(self):
        other = Reminder.objects.create(company=self.company, title='Buy markers', due_date=timezone.localdate())
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f'/v1/reminders/{other.id}/complete').status_code, 200)
        self.assertEqual(self.client.delete(f'/v1/reminders/{self.reminder.id}').status_code, 400)


class OneWayToLeaveTests(Base):
    """Owner, 2026-09-27: the "Отчислить" button is gone; leaving always keeps the last group."""

    def test_leaving_keeps_group_for_left_report(self):
        a = self.student(date(2026, 9, 1), first_name='A', phone='901000101')
        b = self.student(date(2026, 9, 1), first_name='B', phone='901000102')
        self.pay(a, 1)
        self.pay(b, 1)
        self.client.delete(f'/v1/students/{a.id}')  # old API path behaves like the status change
        self.client.patch(f'/v1/students/{b.id}', {'status': Student.Status.LEFT})
        for s in (a, b):
            s.refresh_from_db()
            self.assertEqual(s.group_id, self.group.id)
            self.assertEqual(s.status, Student.Status.LEFT)
        rows = self.client.get(f'/v1/reports/left-students?group_id={self.group.id}').json()['data']['rows']
        self.assertEqual(sorted(r['full_name'] for r in rows), ['A', 'B'])
        # a student who left is not a member of the group any more
        members = self.client.get(f'/v1/groups/{self.group.id}').json()['data']['students']
        self.assertEqual(members, [])


class FrozenDebtorsVisibleTests(Base):
    """Owner, 2026-09-27 (problem 15, option A): a debt from before the freeze is shown in "Должники"."""

    def test_frozen_student_with_old_debt_is_listed(self):
        s = self.student(date(2026, 3, 1))  # studied March, paid nothing -> owes since 1 March
        self.client.patch(f'/v1/students/{s.id}', {'status': 2})
        Student.objects.filter(pk=s.pk).update(frozen_at=aware(date(2026, 4, 1)))

        card = self.detail(s)
        self.assertTrue(card['is_debtor'])
        self.assertEqual(card['overdue_days'], 31)  # counted up to the freeze, the pause adds nothing

        ids = [r['id'] for r in self.client.get('/v1/students?debtors=1').json()['data']['results']]
        self.assertEqual(ids, [s.id])
        self.assertEqual(self.client.get('/v1/dashboard').json()['data']['debtors'], 1)

    def test_frozen_student_without_debt_is_not_listed(self):
        s = self.student(date(2026, 3, 1))
        self.pay(s, 1)  # paid until 1 April
        self.client.patch(f'/v1/students/{s.id}', {'status': 2})
        Student.objects.filter(pk=s.pk).update(frozen_at=aware(date(2026, 3, 20)))
        self.assertFalse(self.detail(s)['is_debtor'])
        self.assertEqual(self.client.get('/v1/students?debtors=1').json()['data']['results'], [])
