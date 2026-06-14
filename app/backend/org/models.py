from django.db import models


class Company(models.Model):
    class PaymentMode(models.IntegerChoices):
        DAILY = 1, 'Daily'
        MONTHLY = 2, 'Monthly'
        GROUP_START = 3, 'Group start'
        FULL_COURSE = 4, 'Full course'
        MODULE = 5, 'Module'
        INDIVIDUAL = 6, 'Individual'

    name = models.CharField(max_length=255)
    subdomain = models.SlugField(max_length=64, unique=True)
    balance_mode = models.IntegerField(choices=PaymentMode.choices, default=PaymentMode.DAILY)
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

    def __str__(self) -> str:
        return self.name


class Room(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='rooms')
    name = models.CharField(max_length=255)
    capacity = models.PositiveIntegerField(default=20)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def company(self):
        return self.branch.company

    def __str__(self) -> str:
        return self.name
