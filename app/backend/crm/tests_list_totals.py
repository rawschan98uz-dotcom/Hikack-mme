"""Money lists show the totals of the whole filtered period (big, in colour), not only of the page shown."""

from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from crm.models import Student
from finance.models import Expense, Payment, Withdrawal
from org.models import Branch, Company


class ListTotalsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Totals Co', subdomain='totalsco')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.ceo = User.objects.create_user(
            phone='998909008801', password='password123', first_name='C', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.client.force_authenticate(self.ceo)
        student = Student.objects.create(company=self.company, branch=self.branch, first_name='Ali', phone='901230088')
        for amount, kind, day in (
            (600_000, Payment.TransactionType.PAYMENT, date(2026, 9, 5)),
            (500_000, Payment.TransactionType.PAYMENT, date(2026, 10, 2)),
            (100_000, Payment.TransactionType.REFUND, date(2026, 10, 3)),
        ):
            Payment.objects.create(
                company=self.company, student=student, student_name='Ali', amount=amount,
                transaction_type=kind, payment_date=day,
            )
        Expense.objects.create(company=self.company, amount=300_000, expense_date=date(2026, 10, 1))
        Expense.objects.create(company=self.company, amount=200_000, expense_date=date(2026, 9, 1))
        Withdrawal.objects.create(company=self.company, name='Owner', amount=1_000_000, withdrawal_date=date(2026, 10, 4))

    def test_payment_totals_follow_the_filters_not_the_page(self):
        data = self.client.get('/v1/replenishments', {'limit': 1}).json()['data']
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['totals'], {'paid': 1_100_000, 'refunded': 100_000})
        data = self.client.get('/v1/replenishments', {'date_from': '2026-10-01'}).json()['data']
        self.assertEqual(data['totals'], {'paid': 500_000, 'refunded': 100_000})

    def test_expense_and_withdrawal_totals(self):
        data = self.client.get('/v1/expense', {'date_from': '2026-10-01'}).json()['data']
        self.assertEqual(data['total'], 300_000)
        self.assertEqual(self.client.get('/v1/expense').json()['data']['total'], 500_000)
        self.assertEqual(self.client.get('/v1/withdraws').json()['data']['total'], 1_000_000)
