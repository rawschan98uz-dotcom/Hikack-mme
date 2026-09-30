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
    months_covered = models.PositiveIntegerField(default=1)
    # Months taken back by refunds of this payment (finance/refunds.py). Only whole months:
    # a refund smaller than the price of one month does not change the paid period.
    refunded_months = models.PositiveIntegerField(default=0)
    # "Копилка" mode (finance/wallet.py). Price of one month when the payment was made.
    # NULL = months were set by hand (payments before the копилка, or the student had no course price).
    month_price = models.BigIntegerField(null=True, blank=True)
    # Money given back by refunds of this payment (копилка mode takes it out of the student's money)
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
