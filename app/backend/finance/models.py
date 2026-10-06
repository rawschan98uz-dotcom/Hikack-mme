from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = 'cash', 'Наличные'
        CARD = 'card', 'Карта'
        TRANSFER = 'transfer', 'Перевод'

    class TransactionType(models.TextChoices):
        PAYMENT = 'payment', 'Оплата'
        REFUND = 'refund', 'Возврат'
        ADJUSTMENT = 'adjustment', 'Корректировка'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='payments')
    student = models.ForeignKey(
        'crm.Student',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
    )
    student_name = models.CharField(max_length=255)
    payment_date = models.DateField(null=True, blank=True, db_index=True)
    amount = models.BigIntegerField()
    # How many month lines of the student this payment closed in full (written by finance/charges.py)
    months_covered = models.PositiveIntegerField(default=1)
    # Price of one month on the day of the payment — kept for reference; 0 = the student had no course
    # price then and the money was waiting for one (finance/wallet.py: PRICE_PENDING)
    month_price = models.BigIntegerField(null=True, blank=True)
    # Money given back by refunds of this payment: it leaves the month lines it had closed
    refunded_amount = models.BigIntegerField(default=0)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        default=TransactionType.PAYMENT,
    )
    reverses_payment = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reversals',
    )
    # Immutable allocation snapshots:
    group = models.ForeignKey(
        'crm.Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
    )
    course = models.ForeignKey(
        'crm.Course',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
    )
    discount_amount = models.BigIntegerField(default=0)
    # Over how many months the discount is spread ("3 months, 300 000 off" = 100 000 off each of them).
    # The discount lowers the sum of the month lines this payment pays, never more than half of a month.
    discount_months = models.PositiveSmallIntegerField(default=1)
    gross_amount = models.BigIntegerField(null=True, blank=True)
    net_amount = models.BigIntegerField(null=True, blank=True)
    teacher_name = models.CharField(max_length=255, blank=True)
    comment = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_payments',
    )
    created_at = models.DateTimeField(auto_now_add=True)


class Withdrawal(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='withdrawals')
    name = models.CharField(max_length=255)
    amount = models.BigIntegerField()
    # The day the money was taken (chosen in the form, today by default) — not the day it was typed in
    withdrawal_date = models.DateField(null=True, blank=True, db_index=True)
    comment = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_withdrawals',
    )
    created_at = models.DateTimeField(auto_now_add=True)


class ExpenseCategory(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='expense_categories')
    name = models.CharField(max_length=255)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower('name'), 'company', name='uniq_expense_category_per_company'),
        ]

    def __str__(self) -> str:
        return self.name


class Expense(models.Model):
    class Method(models.TextChoices):
        CASH = 'cash', 'Наличные'
        CARD = 'card', 'Карта'
        TRANSFER = 'transfer', 'Перевод'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='expenses')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True)
    # Owner (2026-09-28): every expense belongs to a branch (the CEO picks it) and has its own date,
    # so the September rent typed in on 2 October still goes to September of that branch
    branch = models.ForeignKey('org.Branch', on_delete=models.PROTECT, null=True, blank=True, related_name='expenses')
    expense_date = models.DateField(null=True, blank=True, db_index=True)
    # A salary payout (finance/payroll.py): one expense per branch; it is changed or cancelled only
    # in "Зарплаты", never in "Расходы", so the payroll and the P&L always agree
    payroll_payment = models.ForeignKey(
        'PayrollPayment', on_delete=models.CASCADE, null=True, blank=True, related_name='branch_expenses',
    )
    description = models.TextField(blank=True)
    payee = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    amount = models.BigIntegerField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_expenses',
    )
    created_at = models.DateTimeField(auto_now_add=True)


class SalarySetting(models.Model):
    class SalaryType(models.TextChoices):
        # Owner (2026-09-28): a teacher has only a percent; a fixed monthly amount is for office staff
        FIXED = 'fixed', 'Фиксированная'
        PERCENT = 'percent', 'Процент'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='salary_settings')
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='salary_settings',
    )
    course = models.ForeignKey(
        'crm.Course',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='salary_settings',
    )
    group = models.ForeignKey(
        'crm.Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='salary_settings',
    )
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    teacher_name = models.CharField(max_length=255)
    salary_type = models.CharField(max_length=20, choices=SalaryType.choices, default=SalaryType.FIXED)
    amount = models.BigIntegerField(default=0)
    course_name = models.CharField(max_length=255, blank=True)
    group_name = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_salary_settings',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='updated_salary_settings',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PayrollPayment(models.Model):
    class Method(models.TextChoices):
        CASH = 'cash', 'Наличные'
        CARD = 'card', 'Карта'
        TRANSFER = 'transfer', 'Перевод'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='payroll_payments')
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='payroll_payments',
    )
    payroll_period = models.CharField(max_length=7)  # 'YYYY-MM'
    amount = models.BigIntegerField()
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    comment = models.TextField(blank=True)
    expense = models.ForeignKey(
        Expense,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payroll_payments',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_payroll_payments',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f'{self.teacher} — {self.payroll_period}: {self.amount}'


class ClosedMonth(models.Model):
    """
    A month the CEO closed (owner, 2026-09-29; finance/closing.py). Its salaries are frozen in PayrollSnapshot,
    and payments, expenses, withdrawals and teacher lesson marks dated in it can no longer be added, changed
    or deleted — the numbers already seen never change silently. Only the CEO reopens it.
    """
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='closed_months')
    month = models.CharField(max_length=7)  # 'YYYY-MM'
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_months',
    )
    closed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['company', 'month'], name='uniq_closed_month'),
        ]

    def __str__(self) -> str:
        return f'{self.company_id}: {self.month}'


class PayrollSnapshot(models.Model):
    """The salary of one person for a closed month, as counted at closing time ("расчётный лист")."""
    closed_month = models.ForeignKey(ClosedMonth, on_delete=models.CASCADE, related_name='payroll')
    person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payroll_snapshots')
    accrued = models.BigIntegerField(default=0)
    # How it was counted: groups (teacher) or the fixed amount (staff), shown in "Как посчитано"
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['closed_month', 'person'], name='uniq_payroll_snapshot'),
        ]


class PayrollAdjustment(models.Model):
    """A visible correction of a month's salary by the CEO (+ or −) with a reason, e.g. a forgotten lesson."""
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='payroll_adjustments')
    person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payroll_adjustments')
    payroll_period = models.CharField(max_length=7)  # 'YYYY-MM'
    amount = models.BigIntegerField()
    reason = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_payroll_adjustments',
    )
    created_at = models.DateTimeField(auto_now_add=True)


class PaymentTransaction(models.Model):
    class Provider(models.TextChoices):
        CLICK = 'click', 'Click'
        PAYME = 'payme', 'Payme'
        UZUM = 'uzum', 'Uzum'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает'
        COMPLETED = 'completed', 'Проведён'
        CANCELLED = 'cancelled', 'Отменён'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='payment_transactions')
    student = models.ForeignKey(
        'crm.Student',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_transactions',
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    trans_id = models.CharField(max_length=255)
    amount = models.BigIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.SET_NULL, related_name='transactions')
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['company', 'provider', 'trans_id'], name='uniq_provider_transaction'),
        ]

    def __str__(self) -> str:
        return f'{self.provider} #{self.trans_id} ({self.status}) - {self.amount}'


class StudentCharge(models.Model):
    """
    "Строка" (owner, 2026-10-05; finance/charges.py): one month of one student — who, which month, what sum.
    The sum is written once, when the month starts, at the course price of that day, and is never recounted:
    later changes of prices, groups or schedules do not touch it. Payments are attached to lines
    (PaymentAllocation), the oldest unpaid line first.
    A student's month runs from their start date: came on 17 September -> 17.09–17.10, then 17.10–17.11.
    """

    class Status(models.TextChoices):
        OPEN = 'open', 'Действует'
        WRITTEN_OFF = 'written_off', 'Списано CEO'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='student_charges')
    student = models.ForeignKey('crm.Student', on_delete=models.CASCADE, related_name='charges')
    # Snapshots of the day the month started
    group = models.ForeignKey('crm.Group', on_delete=models.SET_NULL, null=True, blank=True, related_name='charges')
    course = models.ForeignKey('crm.Course', on_delete=models.SET_NULL, null=True, blank=True, related_name='charges')
    seq = models.PositiveIntegerField()  # 0 = the student's first month
    period_start = models.DateField(db_index=True)
    period_end = models.DateField()  # the first day of the NEXT month of the student
    # Day of the month the student's months turn on (31 -> 28 February -> 31 March: no drift)
    pay_day = models.PositiveSmallIntegerField()
    price = models.BigIntegerField()
    discount = models.BigIntegerField(default=0)
    amount = models.BigIntegerField()  # to pay: price − discount
    paid_amount = models.BigIntegerField(default=0)  # the sum of its allocations
    paid_at = models.DateField(null=True, blank=True)  # the day it was paid in full
    # Lessons the group could have in this month by the schedule of that day (teacher's share per lesson)
    lessons_planned = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['student_id', 'seq']
        constraints = [
            models.UniqueConstraint(fields=['student', 'seq'], name='uniq_student_charge_seq'),
        ]

    @property
    def remaining(self) -> int:
        return max(0, self.amount - self.paid_amount) if self.status == self.Status.OPEN else 0

    def __str__(self) -> str:
        return f'{self.student_id}: {self.period_start} — {self.period_end} = {self.amount}'


class PaymentAllocation(models.Model):
    """Which line a payment's money closed (the September debt paid in December closes the September line)."""
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='allocations')
    charge = models.ForeignKey(StudentCharge, on_delete=models.CASCADE, related_name='allocations')
    amount = models.BigIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['payment', 'charge'], name='uniq_payment_charge_allocation'),
        ]
