"""Students block, problem 5 → option 3: "копилка" — months are counted from money."""
from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from api.v1.views_payments import _after_online_payment
from crm.models import Course, Group, Student
from finance.models import Payment
from finance.wallet import recalc_student_wallet
from operations.models import Reminder
from org.models import Branch, Company


class WalletTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Wallet Co', subdomain='wallet')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.ceo = User.objects.create_user(
            phone='998909660001', password='x', first_name='C', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.teacher = User.objects.create_user(
            phone='998909660002', password='x', first_name='T', company=self.company,
            user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=self.teacher, branch=self.branch)
        course = Course.objects.create(company=self.company, name='English', price=800_000)
        self.group = Group.objects.create(
            company=self.company, branch=self.branch, name='G', course=course, teacher=self.teacher,
        )
        self.student = Student.objects.create(
            company=self.company, branch=self.branch, group=self.group, first_name='Dilnora',
            phone='901234511', trial_date=date(2026, 9, 1),
        )
        self.client.force_authenticate(self.ceo)

    def pay(self, amount, **extra):
        res = self.client.post('/v1/replenishments', {
            'student_id': self.student.id, 'student_name': 'Dilnora', 'amount': amount,
            'payment_date': extra.pop('payment_date', '2026-09-01'), 'months_covered': 5, **extra,
        })
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()['data']

    def card(self):
        return self.client.get(f'/v1/students/{self.student.id}').json()['data']

    def test_overpayment_goes_to_wallet_and_closes_month_later(self):
        first = self.pay(1_200_000)  # the "5 months" typed by hand is ignored: the price is known
        self.assertEqual(first['months_covered'], 1)
        self.assertTrue(first['months_auto'])
        card = self.card()
        self.assertEqual(card['next_payment_date'], '2026-10-01')
        self.assertEqual(card['wallet'], 400_000)
        self.assertEqual(card['wallet_missing'], 400_000)

        self.pay(400_000, payment_date='2026-09-20')
        card = self.card()
        self.assertEqual(card['next_payment_date'], '2026-11-01')
        self.assertEqual(card['wallet'], 0)
        self.assertIsNone(card['wallet_missing'])

    def test_underpayment_closes_nothing(self):
        self.pay(500_000)
        card = self.card()
        self.assertEqual(card['paid_count'], 0)
        self.assertEqual(card['next_payment_date'], '2026-09-01')
        self.assertEqual(card['wallet'], 500_000)
        self.assertEqual(card['wallet_missing'], 300_000)
        # the list agrees with the card (a 0-month payment is not counted as a month)
        row = self.client.get('/v1/students').json()['data']['results'][0]
        self.assertEqual(row['next_payment_date'], '2026-09-01')

    def test_discount_counts_as_paid(self):
        data = self.pay(600_000, discount_amount=200_000)
        self.assertEqual(data['months_covered'], 1)
        self.assertEqual(self.card()['wallet'], 0)

    def test_refund_takes_money_from_wallet_first(self):
        data = self.pay(1_200_000)
        self.client.post(f"/v1/payments/{data['id']}/refund", {'amount': 400_000})
        card = self.card()
        self.assertEqual(card['next_payment_date'], '2026-10-01')  # the month stays
        self.assertEqual(card['wallet'], 0)
        self.client.post(f"/v1/payments/{data['id']}/refund", {'amount': 100_000})
        card = self.card()
        self.assertEqual(card['next_payment_date'], '2026-09-01')  # 700 000 left < one month
        self.assertEqual(card['wallet'], 700_000)

    def test_edit_and_delete_recount(self):
        data = self.pay(800_000)
        self.client.patch(f"/v1/replenishments/{data['id']}", {'amount': 1_600_000})
        self.assertEqual(self.card()['next_payment_date'], '2026-11-01')
        self.client.delete(f"/v1/replenishments/{data['id']}")
        card = self.card()
        self.assertEqual(card['next_payment_date'], '2026-09-01')
        self.assertEqual(card['wallet'], 0)

    def test_no_course_price_keeps_hand_entered_months(self):
        self.group.course = None
        self.group.save()
        data = self.pay(1_000_000, months_covered=2)
        self.assertEqual(data['months_covered'], 2)
        self.assertFalse(data['months_auto'])
        self.assertEqual(self.card()['next_payment_date'], '2026-11-01')

    def test_old_hand_entered_payments_are_untouched(self):
        Payment.objects.create(
            company=self.company, student=self.student, student_name='Dilnora', amount=100,
            months_covered=2, transaction_type=Payment.TransactionType.PAYMENT, payment_date=date(2026, 9, 1),
        )
        self.pay(1_200_000, payment_date='2026-09-02')
        card = self.card()
        self.assertEqual(card['paid_count'], 3)  # 2 old + 1 from the new money
        self.assertEqual(card['wallet'], 400_000)

    def test_online_payment_uses_wallet(self):
        payment = Payment.objects.create(
            company=self.company, student=self.student, student_name='Dilnora', amount=1_000,
            months_covered=0, month_price=800_000, transaction_type=Payment.TransactionType.PAYMENT,
            payment_date=date(2026, 9, 1), method=Payment.Method.CARD,
        )
        _after_online_payment(self.student, payment)
        card = self.card()
        self.assertEqual(card['paid_count'], 0)  # 1 000 sum is not a month any more
        self.assertEqual(card['wallet'], 1_000)

    def test_online_payment_without_price_asks_office(self):
        payment = Payment.objects.create(
            company=self.company, student=self.student, student_name='Dilnora', amount=1_200_000,
            months_covered=0, transaction_type=Payment.TransactionType.PAYMENT, method=Payment.Method.CARD,
        )
        _after_online_payment(self.student, payment)
        reminder = Reminder.objects.get(kind='online_payment_check')
        self.assertIn('1 200 000', reminder.details)
        self.assertEqual(reminder.student_id, self.student.id)

    def test_backdated_payment_is_placed_in_date_order(self):
        self.pay(500_000, payment_date='2026-09-10')
        self.pay(500_000, payment_date='2026-09-01')
        recalc_student_wallet(self.student)
        card = self.card()
        self.assertEqual(card['paid_count'], 1)
        self.assertEqual(card['wallet'], 200_000)

    def test_teacher_does_not_see_wallet(self):
        self.pay(1_200_000)
        self.client.force_authenticate(self.teacher)
        card = self.client.get(f'/v1/students/{self.student.id}').json()['data']
        self.assertIsNone(card['wallet'])
        self.assertIsNone(card['wallet_missing'])
