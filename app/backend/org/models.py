from django.db import models
from django.db.models.functions import Lower


class Company(models.Model):
    name = models.CharField(max_length=255)
    subdomain = models.SlugField(max_length=64, unique=True)
    phone = models.CharField(max_length=15, blank=True)
    address = models.CharField(max_length=500, blank=True)
    work_start_time = models.TimeField(null=True, blank=True)
    work_end_time = models.TimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, default='Asia/Tashkent')
    currency = models.CharField(max_length=8, default='UZS')
    sms_enabled = models.BooleanField(default=False)
    sms_advance_text = models.TextField(
        blank=True,
        default="Assalomu alaykum! Eslatma: ertaga dars uchun to'lov qilishingiz kerak.",
    )
    voip_enabled = models.BooleanField(default=False)
    voip_gateway = models.CharField(max_length=64, blank=True)
    voip_caller_id = models.CharField(max_length=32, blank=True)
    grade_pass_score = models.PositiveIntegerField(default=70)
    grade_scale_max = models.PositiveIntegerField(default=100)
    click_service_id = models.CharField(max_length=64, blank=True, default='')
    click_merchant_id = models.CharField(max_length=64, blank=True, default='')
    click_secret_key = models.CharField(max_length=128, blank=True, default='')
    payme_merchant_id = models.CharField(max_length=64, blank=True, default='')
    payme_secret_key = models.CharField(max_length=128, blank=True, default='')
    uzum_merchant_id = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'companies'

    def __str__(self) -> str:
        return self.name


class Branch(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'branches'
        constraints = [
            models.UniqueConstraint(Lower('name'), 'company', name='uniq_branch_name_per_company'),
        ]

    def __str__(self) -> str:
        return self.name


class Room(models.Model):
    # D2: real FK instead of a property through branch; always equals branch.company
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='rooms')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='rooms')
    name = models.CharField(max_length=255)
    capacity = models.PositiveIntegerField(default=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.branch_id and self.company_id != self.branch.company_id:
            self.company_id = self.branch.company_id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name
