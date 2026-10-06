"""
Refunds: money given back leaves the student's months, the newest first.

Since the month lines (2026-10-05) there is one rule for every payment — by the money itself: what is left of
the payment after the refund is spread over the months again. (The older rule "only whole months, counted from
hand-typed months" is gone together with hand-typed months.)
"""
from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from crm.models import Course, Group, Student
from finance.models import Payment
from org.models import Branch, Company


class RefundMonthsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Refund Co', subdomain='refund')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.ceo = User.objects.create_user(
            phone='998909770001', password='x', first_name='C', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        course = Course.objects.create(company=self.company, name='English', price=800_000)
        group = Group.objects.create(company=self.company, branch=self.branch, name='G', course=course)
        self.student = Student.objects.create(
            company=self.company, branch=self.branch, group=group, first_name='Dilnora',
            phone='901234500', trial_date=date(2026, 9, 1),
        )
        # 3 months × 800 000 = 2 400 000 -> paid until 1 December
        self.payment = Payment.objects.create(
            company=self.company, student=self.student, student_name='Dilnora', amount=2_400_000,
            transaction_type=Payment.TransactionType.PAYMENT, payment_date=date(2026, 9, 1),
        )
        self.client.force_authenticate(self.ceo)

    def refund(self, amount):
        res = self.client.post(f'/v1/payments/{self.payment.id}/refund', {'amount': amount})
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()['data']['id']

    def card(self):
        return self.client.get(f'/v1/students/{self.student.id}').json()['data']

    def due(self):
        return self.card()['next_payment_date']

    def test_before_any_refund_three_months_are_paid(self):
        self.assertEqual(self.due(), '2026-12-01')

    def test_small_refund_opens_the_newest_month_and_the_rest_waits_on_it(self):
        self.refund(50_000)
        card = self.card()
        self.assertEqual(card['next_payment_date'], '2026-11-01')
        self.assertEqual(card['wallet'], 750_000)  # already brought towards November
        self.assertFalse(card['is_debtor'])  # November has not begun yet

    def test_refund_of_one_monthly_price_takes_back_one_month(self):
        self.refund(800_000)
        self.assertEqual(self.due(), '2026-11-01')
        self.assertEqual(self.card()['wallet'], 0)

    def test_refunds_add_up(self):
        self.refund(500_000)
        self.assertEqual(self.due(), '2026-11-01')
        self.refund(500_000)  # 1 000 000 in total: October is open again
        card = self.card()
        self.assertEqual(card['next_payment_date'], '2026-10-01')
        self.assertEqual((card['is_debtor'], card['debt_amount']), (True, 200_000))

    def test_full_refund_takes_back_everything(self):
        self.refund(2_400_000)
        self.assertEqual(self.due(), '2026-09-01')

    def test_deleting_refund_gives_months_back(self):
        refund_id = self.refund(800_000)
        self.assertEqual(self.client.delete(f'/v1/replenishments/{refund_id}').status_code, 200)
        self.assertEqual(self.due(), '2026-12-01')

    def test_list_and_card_agree(self):
        self.refund(800_000)
        row = self.client.get('/v1/students').json()['data']['results'][0]
        self.assertEqual(row['next_payment_date'], '2026-11-01')

    def test_payments_list_shows_the_months_the_payment_still_closes(self):
        self.refund(800_000)
        payment = self.client.get(f'/v1/replenishments/{self.payment.id}').json()['data']
        self.assertEqual(payment['months_covered'], 2)


class ListAndCardSameDateTests(TestCase):
    """Problem 12: the list and the card show the day the money was actually brought."""

    def test_backdated_payment_date_is_the_same_everywhere(self):
        client = APIClient()
        company = Company.objects.create(name='Dates Co', subdomain='dates')
        branch = Branch.objects.create(company=company, name='Main')
        ceo = User.objects.create_user(
            phone='998909440001', password='x', first_name='C', company=company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        student = Student.objects.create(
            company=company, branch=branch, first_name='Madina', phone='901230001', trial_date=date(2026, 6, 1),
        )
        # brought on 10 June, entered into the program today
        Payment.objects.create(
            company=company, student=student, student_name='Madina', amount=800_000, months_covered=1,
            transaction_type=Payment.TransactionType.PAYMENT, payment_date=date(2026, 6, 10),
        )
        client.force_authenticate(ceo)
        row = client.get('/v1/students').json()['data']['results'][0]
        card = client.get(f'/v1/students/{student.id}').json()['data']
        self.assertEqual(row['last_payment_date'], '2026-06-10')
        self.assertEqual(card['last_payment_date'], '2026-06-10')
        self.assertEqual(row['next_payment_date'], card['next_payment_date'])
