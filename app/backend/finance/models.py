from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = 'cash', 'Cash'
        CARD = 'card', 'Card'
        TRANSFER = 'transfer', 'Transfer'

    class TransactionType(models.TextChoices):
        PAYMENT = 'payment', 'Payment'
        REFUND = 'refund', 'Refund'
        ADJUSTMENT = 'adjustment', 'Adjustment'

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
    amount = models.IntegerField()
    months_covered = models.PositiveIntegerField(default=1)
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
    discount_amount = models.IntegerField(default=0)
    gross_amount = models.IntegerField(null=True, blank=True)
    net_amount = models.IntegerField(null=True, blank=True)
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
    amount = models.IntegerField()
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
        CASH = 'cash', 'Cash'
        CARD = 'card', 'Card'
        TRANSFER = 'transfer', 'Transfer'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='expenses')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True)
    description = models.TextField(blank=True)
    payee = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    amount = models.IntegerField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_expenses',
    )
    created_at = models.DateTimeField(auto_now_add=True)


class SalarySetting(models.Model):
    class SalaryType(models.TextChoices):
        FIXED = 'fixed', 'Fixed'
        PERCENT = 'percent', 'Percent'
        PER_STUDENT = 'per_student', 'Per student'

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
    amount = models.IntegerField(default=0)
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
        CASH = 'cash', 'Cash'
        CARD = 'card', 'Card'
        TRANSFER = 'transfer', 'Transfer'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='payroll_payments')
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='payroll_payments',
    )
    payroll_period = models.CharField(max_length=7)  # 'YYYY-MM'
    amount = models.IntegerField()
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


class PaymentTransaction(models.Model):
    class Provider(models.TextChoices):
        CLICK = 'click', 'Click'
        PAYME = 'payme', 'Payme'
        UZUM = 'uzum', 'Uzum'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

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
    amount = models.IntegerField()
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
