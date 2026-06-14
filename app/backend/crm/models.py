from django.conf import settings
from django.db import models


class Course(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='courses')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=64, blank=True)
    price = models.PositiveIntegerField(default=0)
    lesson_duration = models.PositiveIntegerField(default=90)
    course_duration = models.PositiveIntegerField(default=12)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class Group(models.Model):
    class Status(models.IntegerChoices):
        ACTIVE = 2, 'Active'
        ARCHIVE = 3, 'Archive'

    class Days(models.IntegerChoices):
        ODD = 1, 'Odd days'
        EVEN = 2, 'Even days'
        WEEKEND = 3, 'Weekend days'
        EVERY_DAY = 4, 'Every day'
        CUSTOM = 5, 'Other'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='groups')
    branch = models.ForeignKey('org.Branch', on_delete=models.CASCADE, related_name='groups')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, related_name='groups')
    room = models.ForeignKey(
        'org.Room',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='groups',
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teaching_groups',
    )
    name = models.CharField(max_length=255)
    days = models.IntegerField(choices=Days.choices, default=Days.ODD)
    status = models.IntegerField(choices=Status.choices, default=Status.ACTIVE)
    lesson_start_time = models.TimeField(null=True, blank=True)
    lesson_end_time = models.TimeField(null=True, blank=True)
    group_start_date = models.DateField(null=True, blank=True)
    group_end_date = models.DateField(null=True, blank=True)
    tags = models.ManyToManyField('operations.Tag', blank=True, related_name='groups')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'groups'

    def __str__(self) -> str:
        return self.name


class Student(models.Model):
    class Status(models.IntegerChoices):
        TRIAL = 1, 'Trial'
        ACTIVE = 5, 'Active'
        DEBTOR = 6, 'Debtor'
        LEFT_TRIAL = 7, 'Left after trial'
        LEFT_ACTIVE = 8, 'Left active group'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='students')
    branch = models.ForeignKey('org.Branch', on_delete=models.CASCADE, related_name='students')
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=15)
    status = models.IntegerField(choices=Status.choices, default=Status.TRIAL)
    balance = models.IntegerField(default=0)
    paid_this_month = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def full_name(self) -> str:
        return f'{self.first_name} {self.last_name}'.strip()

    def __str__(self) -> str:
        return self.full_name


class Lead(models.Model):
    class Stage(models.TextChoices):
        INCOMING = 'incoming', 'Incoming'
        WAITING = 'waiting', 'Waiting'
        SET = 'set', 'Set'
        ATTENDED = 'attended', 'Attended'
        PAID = 'paid', 'Paid'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='leads')
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=15)
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.INCOMING)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.full_name


class AttendanceRecord(models.Model):
    class Status(models.IntegerChoices):
        PRESENT = 1, 'Present'
        ABSENT = 0, 'Absent'
        LATE = 2, 'Late'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='attendance_records')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='attendance_records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    attend_date = models.DateField()
    status = models.IntegerField(choices=Status.choices, default=Status.PRESENT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f'{self.student.full_name} — {self.attend_date}'
