"""
Close every month up to and including --until for every company (owner, 2026-09-29: all months before
September 2026 are closed with the numbers they have now). Months already closed are skipped.

    python manage.py close_months --until 2026-08
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Min
from django.db.models.functions import TruncDate

from finance.closing import close_month, month_is_over, month_key, month_title
from finance.models import ClosedMonth, Expense, Payment, PayrollPayment, Withdrawal
from finance.payroll import parse_month
from operations.models import TeacherAttendanceRecord, log_audit
from org.models import Company


def _first_day(company) -> date | None:
    days = [
        Payment.objects.filter(company=company).aggregate(d=Min('payment_date'))['d'],
        Payment.objects.filter(company=company).annotate(d0=TruncDate('created_at')).aggregate(d=Min('d0'))['d'],
        Expense.objects.filter(company=company).aggregate(d=Min('expense_date'))['d'],
        Withdrawal.objects.filter(company=company).aggregate(d=Min('withdrawal_date'))['d'],
        TeacherAttendanceRecord.objects.filter(company=company).aggregate(d=Min('attend_date'))['d'],
    ]
    period = PayrollPayment.objects.filter(company=company).aggregate(p=Min('payroll_period'))['p']
    parsed = parse_month(period) if period else None
    if parsed:
        days.append(parsed[1])
    days = [d for d in days if d]
    return min(days) if days else None


class Command(BaseCommand):
    help = 'Close all months up to --until (YYYY-MM) for every company'

    def add_arguments(self, parser):
        parser.add_argument('--until', required=True)

    def handle(self, *args, **options):
        parsed = parse_month(options['until'])
        if parsed is None:
            raise CommandError('--until must be YYYY-MM')
        until = parsed[0]
        if not month_is_over(until):
            raise CommandError(f'{until} is not over yet')
        for company in Company.objects.all().order_by('id'):
            first = _first_day(company)
            if first is None:
                continue
            year, month = first.year, first.month
            while True:
                key = month_key(date(year, month, 1))
                if key > until:
                    break
                if not ClosedMonth.objects.filter(company=company, month=key).exists():
                    closed = close_month(company, key, None)
                    total = sum(s.accrued for s in closed.payroll.all())
                    log_audit(
                        company=company, actor=None, entity_type='finance_month', entity_id=closed.id, action='close',
                        new_values={'month': key},
                        reason=f'Закрыт месяц {month_title(key)} (закрытие прошлых месяцев по решению владельца)',
                    )
                    self.stdout.write(f'{company.name}: closed {key}, salaries {total:,}')
                month += 1
                if month > 12:
                    year, month = year + 1, 1
