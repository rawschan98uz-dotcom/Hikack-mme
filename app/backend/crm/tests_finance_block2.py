"""Finance audit, block 2 (2026-09-28): payment date & discount, strict payments, refunds, expense date & branch, P&L by branch."""
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm.models import Course, Group, Student
from finance.models import Expense, Payment, SalarySetting, Withdrawal
from operations.models import AuditLogRecord, Reminder
from org.models import Branch, Company


class Base(TestCase):
    def setUp(self):
        self.c = APIClient()
        self.company = Company.objects.create(name='Money Co', subdomain='money2')
        self.a = Branch.objects.create(company=self.company, name='A')
        self.b = Branch.objects.create(company=self.company, name='B')
        self.ceo = User.objects.create_user(
            phone='998905660001', password='x', first_name='Ceo', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.admin = User.objects.create_user(
            phone='998905660002', password='x', first_name='Admin', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.ADMINISTRATOR,
        )
        course = Course.objects.create(company=self.company, name='En', price=800_000)
        self.ga = Group.objects.create(company=self.company, branch=self.a, name='GA', course=course)
        self.gb = Group.objects.create(company=self.company, branch=self.b, name='GB', course=course)
        self.ali = Student.objects.create(company=self.company, branch=self.a, group=self.ga, first_name='Ali',
                                          phone='901000001', trial_date=date(2026, 9, 1))
        self.bek = Student.objects.create(company=self.company, branch=self.b, group=self.gb, first_name='Bek',
                                          phone='901000002', trial_date=date(2026, 9, 1))
        self.today = timezone.localdate()
        self.c.force_authenticate(self.ceo)

    def pay(self, student, amount=800_000, **kw):
        return self.c.post('/v1/replenishments', {'student_id': student.id, 'amount': amount, **kw}, format='json')


class StrictPaymentTests(Base):
    def test_student_must_be_chosen(self):
        res = self.c.post('/v1/replenishments', {'student_name': 'Ali', 'amount': 800_000}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Выберите ученика', res.json()['message'])
        self.assertEqual(self.c.post('/v1/replenishments', {'student_id': 999999, 'amount': 5}, format='json').status_code, 400)
        self.assertFalse(Payment.objects.exists())

    def test_whole_sums_only(self):
        self.assertEqual(self.pay(self.ali, 800_000.5).status_code, 400)
        self.assertEqual(self.pay(self.ali, 'abc').status_code, 400)
        self.assertEqual(self.pay(self.ali, -5).status_code, 400)
        self.assertEqual(self.pay(self.ali, '800 000').status_code, 201)

    def test_payment_date(self):
        yesterday = self.today - timedelta(days=1)
        res = self.pay(self.ali, payment_date=yesterday.isoformat())
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['data']['payment_date'], yesterday.isoformat())
        future = self.pay(self.ali, payment_date=(self.today + timedelta(days=1)).isoformat())
        self.assertEqual(future.status_code, 400)
        self.assertIn('позже сегодняшнего', future.json()['message'])
        self.assertEqual(self.pay(self.ali, payment_date='31.13.2026').status_code, 400)
        self.assertEqual(self.pay(self.ali).json()['data']['payment_date'], self.today.isoformat())

    def test_no_course_price_goes_to_wallet_with_reminder(self):
        self.ga.course = None
        self.ga.save()
        res = self.pay(self.ali, 1_000, months_covered=24)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['data']['months_covered'], 0)
        card = self.c.get(f'/v1/students/{self.ali.id}').json()['data']
        self.assertEqual(card['wallet'], 1_000)
        self.assertEqual(card['next_payment_date'], '2026-09-01')  # nothing was "paid for 24 months"
        self.assertTrue(Reminder.objects.filter(kind=Reminder.KIND_ONLINE_PAYMENT_CHECK, title__startswith='Оплата без цены').exists())


class DiscountTests(Base):
    def test_discount_counts_as_paid(self):
        res = self.pay(self.ali, 700_000, discount_amount=100_000)
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()['data']['months_covered'], 1)
        self.assertEqual(res.json()['data']['discount_amount'], 100_000)

    def test_discount_not_more_than_months_paid_for(self):
        res = self.pay(self.ali, 1_000, discount_amount=9_600_000)
        self.assertEqual(res.status_code, 400)
        self.assertIn('50%', res.json()['message'])
        # Owner (2026-10-05): not more than half. Paying for 2 months of 800 000: up to 800 000 of discount
        self.assertEqual(self.pay(self.ali, 100_000, discount_amount=800_001, months_covered=2).status_code, 400)
        self.assertEqual(self.pay(self.ali, 800_000, discount_amount=800_000, months_covered=2).status_code, 201)

    def test_discount_needs_course_price(self):
        self.ga.course = None
        self.ga.save()
        self.assertEqual(self.pay(self.ali, 700_000, discount_amount=100_000).status_code, 400)

    def test_edit_discount_is_checked_and_logged(self):
        pid = self.pay(self.ali, 700_000, discount_amount=100_000).json()['data']['id']
        self.assertEqual(self.c.patch(f'/v1/replenishments/{pid}', {'discount_amount': 5_000_000}, format='json').status_code, 400)
        self.assertEqual(self.c.patch(f'/v1/replenishments/{pid}', {'discount_amount': 50_000}, format='json').status_code, 200)
        self.assertTrue(AuditLogRecord.objects.filter(action='edit', reason__contains='скидка').exists())


class RefundTests(Base):
    def test_refund_not_more_than_left(self):
        pid = self.pay(self.ali).json()['data']['id']
        self.assertEqual(self.c.post(f'/v1/replenishments/{pid}/refund', {'amount': 900_000}, format='json').status_code, 400)
        self.assertEqual(self.c.post(f'/v1/replenishments/{pid}/refund', {'amount': 500_000}, format='json').status_code, 201)
        res = self.c.post(f'/v1/replenishments/{pid}/refund', {'amount': 400_000}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('300 000', res.json()['message'])
        detail = self.c.get(f'/v1/replenishments/{pid}').json()['data']
        self.assertEqual((detail['refunded_total'], detail['refundable']), (500_000, 300_000))

    def test_payment_cannot_go_below_refunded_and_refund_cannot_grow(self):
        pid = self.pay(self.ali).json()['data']['id']
        self.c.post(f'/v1/replenishments/{pid}/refund', {'amount': 500_000}, format='json')
        res = self.c.patch(f'/v1/replenishments/{pid}', {'amount': 100_000}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('меньше уже возвращённого', res.json()['message'])
        refund = Payment.objects.get(transaction_type='refund')
        self.assertEqual(self.c.patch(f'/v1/replenishments/{refund.id}', {'amount': 5_000_000}, format='json').status_code, 400)
        self.assertEqual(self.c.patch(f'/v1/replenishments/{refund.id}', {'amount': 600_000}, format='json').status_code, 200)

    def test_refund_rows_are_marked_in_list(self):
        pid = self.pay(self.ali).json()['data']['id']
        self.c.post(f'/v1/replenishments/{pid}/refund', {'amount': 300_000, 'comment': 'Возврат: ушёл'}, format='json')
        rows = self.c.get('/v1/replenishments').json()['data']['results']
        self.assertEqual(sorted((r['transaction_type'], r['sum']) for r in rows),
                         [('payment', 800_000), ('refund', 300_000)])


class ExpenseAndWithdrawalTests(Base):
    def test_expense_needs_branch_and_keeps_its_date(self):
        self.assertEqual(self.c.post('/v1/expense', {'amount': 3_000_000}, format='json').status_code, 400)
        sept = self.today - timedelta(days=5)
        res = self.c.post('/v1/expense', {'amount': 3_000_000, 'branch_id': self.b.id, 'date': sept.isoformat(),
                                          'description': 'September rent'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual((res.json()['data']['date'], res.json()['data']['branch']), (sept.isoformat(), 'B'))
        future = self.c.post('/v1/expense', {'amount': 1, 'branch_id': self.b.id,
                                             'date': (self.today + timedelta(days=3)).isoformat()}, format='json')
        self.assertEqual(future.status_code, 400)

    def test_withdrawal_date(self):
        day = self.today - timedelta(days=10)
        res = self.c.post('/v1/withdraws', {'name': 'Owner', 'amount': 500_000, 'date': day.isoformat()}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['data']['date'], day.isoformat())
        self.assertEqual(Withdrawal.objects.get().withdrawal_date, day)

    def test_lists_are_paged(self):
        for i in range(205):
            Expense.objects.create(company=self.company, amount=1_000 + i, branch=self.a, expense_date=self.today)
        first = self.c.get('/v1/expense').json()['data']
        self.assertEqual(len(first['results']), 200)
        self.assertTrue(first['has_more'])
        second = self.c.get('/v1/expense', {'offset': first['next_offset']}).json()['data']
        self.assertEqual(len(second['results']), 5)

    def test_salary_expense_gets_branch_and_date(self):
        teacher = User.objects.create_user(phone='998905660009', password='x', first_name='Tom', company=self.company,
                                           user_type=User.UserType.TEACHER)
        TeacherBranch.objects.create(teacher=teacher, branch=self.b)
        # No lessons held: nothing is split by groups, so the salary goes to the teacher's branch (forced payout)
        res = self.c.post('/v1/finance/payroll/pay', {'teacher_id': teacher.id, 'amount': 1_000_000, 'force': True},
                          format='json')
        self.assertEqual(res.status_code, 201, res.content)
        expense = Expense.objects.get(pk=res.json()['data']['expense_id'])
        self.assertEqual((expense.branch_id, expense.expense_date), (self.b.id, self.today))


class PnlByBranchTests(Base):
    def test_every_branch_separately_and_all_together(self):
        self.pay(self.ali, 1_000_000)
        self.pay(self.bek, 1_000_000)
        Expense.objects.create(company=self.company, amount=300_000, branch=self.a, expense_date=self.today)
        Expense.objects.create(company=self.company, amount=500_000, branch=self.b, expense_date=self.today)
        data = self.c.get('/v1/reports/pnl').json()['data']
        rows = {r['name']: (r['revenue'], r['expenses'], r['profit']) for r in data['branches']}
        self.assertEqual(rows, {'A': (1_000_000, 300_000, 700_000), 'B': (1_000_000, 500_000, 500_000)})
        self.assertEqual((data['summary']['total_revenue'], data['summary']['total_expenses'],
                          data['summary']['net_profit']), (2_000_000, 800_000, 1_200_000))

    def test_expense_goes_to_the_month_of_its_date(self):
        Expense.objects.create(company=self.company, amount=3_000_000, branch=self.a, expense_date=date(2026, 8, 31))
        aug = self.c.get('/v1/reports/pnl', {'date_from': '2026-08-01', 'date_to': '2026-08-31'}).json()['data']
        sep = self.c.get('/v1/reports/pnl', {'date_from': '2026-09-01', 'date_to': '2026-09-30'}).json()['data']
        self.assertEqual(aug['summary']['total_expenses'], 3_000_000)
        self.assertEqual(sep['summary']['total_expenses'], 0)

    def test_refunds_larger_than_payments_are_not_hidden(self):
        # paid in August, refunded in September: September income is negative, not 0
        pid = self.pay(self.ali, 800_000, payment_date='2026-08-20').json()['data']['id']
        self.c.post(f'/v1/replenishments/{pid}/refund', {'amount': 500_000}, format='json')
        Payment.objects.filter(transaction_type='refund').update(payment_date=date(2026, 9, 5))
        sep = self.c.get('/v1/reports/pnl', {'date_from': '2026-09-01', 'date_to': '2026-09-30'}).json()['data']
        self.assertEqual(sep['summary']['total_revenue'], -500_000)

    def test_payment_without_group_counts_for_student_branch(self):
        Payment.objects.create(company=self.company, student=self.bek, student_name='Bek', amount=400_000,
                               payment_date=self.today, month_price=800_000)
        rows = {r['name']: r['revenue'] for r in self.c.get('/v1/reports/pnl').json()['data']['branches']}
        self.assertEqual(rows['B'], 400_000)

    def test_dashboard_chart_by_payment_date(self):
        last_month_day = self.today.replace(day=1) - timedelta(days=1)
        self.pay(self.ali, 900_000, payment_date=last_month_day.isoformat())
        chart = self.c.get('/v1/dashboard').json()['data']['finance_chart']
        self.assertEqual(chart, [{'label': last_month_day.strftime('%b %Y'), 'value': 900_000}])
