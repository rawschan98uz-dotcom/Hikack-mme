from django.conf import settings
from django.db import models


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = 'cash', 'Cash'
        CARD = 'card', 'Card'
        TRANSFER = 'transfer', 'Transfer'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='payments')
    student = models.ForeignKey(
        'crm.Student',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
    )
    student_name = models.CharField(max_length=255)
    amount = models.IntegerField()
    months_covered = models.PositiveIntegerField(default=1)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
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
    student = models.ForeignKey('crm.Student', on_delete=models.CASCADE, related_name='payment_transactions')
    provider = models.CharField(max_length=20, choices=Provider.choices)
    trans_id = models.CharField(max_length=255)
    amount = models.IntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.SET_NULL, related_name='transactions')
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'provider', 'trans_id']),
        ]

    def __str__(self) -> str:
        return f'{self.provider} #{self.trans_id} ({self.status}) - {self.amount}'
