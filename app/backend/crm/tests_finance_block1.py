"""Finance audit, block 1 (2026-09-28): online payments off, one "Administrator" role, money journal."""
import json
from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from accounts.rbac import ROLE_ADMINISTRATOR, get_effective_role
from crm.models import Course, Group, Student
from finance.models import Expense, Payment, PaymentTransaction, Withdrawal
from operations.models import AuditLogRecord
from org.models import Branch, Company


class Base(TestCase):
    def setUp(self):
        self.c = APIClient()
        self.company = Company.objects.create(name='Money Co', subdomain='moneyco')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.ceo = self.staff('998905550001', 'Ceo', User.StaffRole.CEO)
        self.admin = self.staff('998905550002', 'Admin', User.StaffRole.ADMINISTRATOR)
        self.director = self.staff('998905550003', 'Dir', User.StaffRole.BRANCH_DIRECTOR, branch=self.branch)
        course = Course.objects.create(company=self.company, name='En', price=800_000)
        self.group = Group.objects.create(company=self.company, branch=self.branch, name='G', course=course)
        self.ali = Student.objects.create(
            company=self.company, branch=self.branch, group=self.group, first_name='Ali', phone='901000001',
            trial_date=date(2026, 9, 1),
        )

    def staff(self, phone, name, role, **kw):
        return User.objects.create_user(
            phone=phone, password='x', first_name=name, company=self.company,
            user_type=User.UserType.STAFF, staff_role=role, **kw,
        )

    def as_(self, user):
        self.c.force_authenticate(user)
        return self.c

    def pay(self, user, amount=800_000):
        return self.as_(user).post('/v1/replenishments', {'student_id': self.ali.id, 'amount': amount}, format='json')


class OnlinePaymentsOffTests(Base):
    def test_payme_records_nothing(self):
        anon = APIClient()
        for method, params in (
            ('CreateTransaction', {'id': 'x1', 'time': 1, 'amount': 2_400_000 * 100, 'account': {'student_id': self.ali.id}}),
            ('PerformTransaction', {'id': 'x1'}),
        ):
            res = anon.post('/v1/payments/payme/webhook', json.dumps({'method': method, 'id': 7, 'params': params}),
                            content_type='application/json')
            self.assertEqual(res.json()['error']['code'], -32504)
            self.assertEqual(res.json()['id'], 7)
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_click_records_nothing(self):
        anon = APIClient()
        data = {'click_trans_id': '1', 'merchant_trans_id': str(self.ali.id), 'amount': '2400000', 'action': '1'}
        res = anon.post('/v1/payments/click/webhook', data)
        self.assertNotEqual(res.json()['error'], 0)
        self.assertFalse(Payment.objects.exists())


class AdministratorRoleTests(Base):
    def test_old_roles_are_gone_and_fallback_is_administrator(self):
        self.assertNotIn('cashier', User.StaffRole.values)
        self.assertNotIn('limited_admin', User.StaffRole.values)
        nobody = self.staff('998905550009', 'NoRole', '')
        self.assertEqual(get_effective_role(nobody), ROLE_ADMINISTRATOR)

    def test_administrator_takes_payment_and_refunds(self):
        res = self.pay(self.admin)
        self.assertEqual(res.status_code, 201, res.content)
        pid = res.json()['data']['id']
        self.assertEqual(self.c.post(f'/v1/replenishments/{pid}/refund', {'amount': 100_000}, format='json').status_code, 201)
        self.assertEqual(self.c.get('/v1/replenishments').status_code, 200)
        self.assertEqual(self.c.get('/v1/students?debtors=1').status_code, 200)

    def test_administrator_cannot_delete_payment_only_ceo(self):
        pid = self.pay(self.admin).json()['data']['id']
        self.assertEqual(self.c.delete(f'/v1/replenishments/{pid}').status_code, 403)
        self.assertTrue(Payment.objects.filter(pk=pid).exists())
        self.assertEqual(self.as_(self.ceo).delete(f'/v1/replenishments/{pid}').status_code, 200)

    def test_administrator_sees_no_company_money(self):
        c = self.as_(self.admin)
        for url in ('/v1/expense', '/v1/withdraws', '/v1/reports/pnl', '/v1/expense_types',
                    '/v1/finance/payroll', '/v1/salary-settings'):
            self.assertEqual(c.get(url).status_code, 403, url)
        self.assertEqual(c.post('/v1/expense', {'amount': 1000}, format='json').status_code, 403)
        self.assertEqual(c.post('/v1/withdraws', {'name': 'x', 'amount': 1000}, format='json').status_code, 403)
        self.assertEqual(c.get('/v1/dashboard').json()['data']['finance_chart'], [])

    def test_director_unchanged_views_but_cannot_take_payment(self):
        c = self.as_(self.director)
        self.assertEqual(c.get('/v1/replenishments').status_code, 200)
        self.assertEqual(c.get('/v1/finance/payroll').status_code, 200)
        self.assertEqual(self.pay(self.director).status_code, 403)

    def test_role_list_offers_only_administrator(self):
        c = self.as_(self.ceo)
        res = c.patch(f'/v1/user/staff/{self.admin.id}', {'staff_role': 'cashier'}, format='json')
        self.assertEqual(res.status_code, 400)


class MoneyJournalTests(Base):
    def journal(self, user):
        return [row['action'] for row in self.as_(user).get('/v1/history/logs').json()['data']]

    def test_payment_edit_delete_and_refund_are_written(self):
        pid = self.pay(self.admin).json()['data']['id']
        self.c.patch(f'/v1/replenishments/{pid}', {'amount': 700_000}, format='json')
        self.c.post(f'/v1/replenishments/{pid}/refund', {'amount': 100_000, 'comment': 'переплата'}, format='json')
        refund = Payment.objects.get(transaction_type='refund')
        self.as_(self.ceo).delete(f'/v1/replenishments/{refund.id}')
        rows = self.journal(self.ceo)
        self.assertTrue(any('Изменена оплата' in r and '800 000 → 700 000' in r for r in rows), rows)
        self.assertTrue(any('Возврат' in r and '100 000' in r for r in rows), rows)
        self.assertTrue(any('Удалён' in r or 'Удалена' in r for r in rows), rows)
        record = AuditLogRecord.objects.get(entity_type='payment', action='edit')
        self.assertEqual(record.actor, self.admin)
        self.assertEqual(record.old_values['amount'], '800 000')

    def test_expense_and_withdrawal_edits_and_deletions_are_written(self):
        exp = Expense.objects.create(company=self.company, amount=1_000_000, payee='Landlord')
        wd = Withdrawal.objects.create(company=self.company, name='Owner', amount=500_000)
        c = self.as_(self.ceo)
        c.patch(f'/v1/expense/{exp.id}', {'amount': 1_200_000}, format='json')
        c.delete(f'/v1/expense/{exp.id}')
        c.patch(f'/v1/withdraws/{wd.id}', {'amount': 400_000}, format='json')
        c.delete(f'/v1/withdraws/{wd.id}')
        actions = list(AuditLogRecord.objects.values_list('entity_type', 'action'))
        for expected in (('expense', 'edit'), ('expense', 'delete'), ('withdrawal', 'edit'), ('withdrawal', 'delete')):
            self.assertIn(expected, actions)

    def test_nothing_changed_nothing_written(self):
        pid = self.pay(self.admin).json()['data']['id']
        self.c.patch(f'/v1/replenishments/{pid}', {'amount': 800_000}, format='json')
        self.assertFalse(AuditLogRecord.objects.filter(action='edit').exists())

    def test_administrator_does_not_see_expense_records_in_journal(self):
        exp = Expense.objects.create(company=self.company, amount=1_000_000)
        self.as_(self.ceo).delete(f'/v1/expense/{exp.id}')
        pid = self.pay(self.admin).json()['data']['id']
        self.c.patch(f'/v1/replenishments/{pid}', {'amount': 600_000}, format='json')
        admin_rows = self.journal(self.admin)
        self.assertFalse(any('расход' in r for r in admin_rows), admin_rows)
        self.assertTrue(any('Изменена оплата' in r for r in admin_rows))
        self.assertTrue(any('Удалён расход' in r for r in self.journal(self.ceo)))
