from django.conf import settings
from django.db import models


class Reminder(models.Model):
    class Status(models.TextChoices):
        OVERDUE = 'overdue', 'Overdue'
        TODAY = 'today', 'Today'
        FUTURE = 'future', 'Future'
        DONE = 'done', 'Done'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='reminders')
    title = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODAY)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)


class Holiday(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='holidays')
    branch = models.ForeignKey('org.Branch', on_delete=models.CASCADE, related_name='holidays')
    name = models.CharField(max_length=255)
    holiday_date = models.DateField()
    affects_payment = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class StudentScore(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='scores')
    student = models.ForeignKey('crm.Student', on_delete=models.CASCADE, related_name='scores')
    group = models.ForeignKey('crm.Group', on_delete=models.CASCADE, related_name='scores')
    grade = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    rank = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class TeacherAttendanceRecord(models.Model):
    class Status(models.IntegerChoices):
        PRESENT = 1, 'Present'
        ABSENT = 0, 'Absent'
        LATE = 2, 'Late'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='teacher_attendance_records')
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='teacher_attendance_records',
    )
    group = models.ForeignKey('crm.Group', on_delete=models.CASCADE, related_name='teacher_attendance_records')
    attend_date = models.DateField()
    status = models.IntegerField(choices=Status.choices, default=Status.PRESENT)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['company', 'teacher', 'group', 'attend_date']]
        indexes = [
            models.Index(fields=['company', 'attend_date']),
        ]

    def __str__(self) -> str:
        return f'{self.teacher} — {self.attend_date}'


class WorklyRecord(models.Model):
    class Status(models.TextChoices):
        AT_WORK = 'at_work', 'At work'
        LATE_IN = 'late_in', 'Late in'
        ABSENT = 'absent', 'Absent'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='workly_records')
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workly_records',
    )
    work_date = models.DateField()
    clock_in = models.TimeField(null=True, blank=True)
    clock_out = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AT_WORK)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['company', 'staff', 'work_date']]
        indexes = [
            models.Index(fields=['company', 'work_date']),
        ]

    def __str__(self) -> str:
        return f'{self.staff} — {self.work_date}'


class Tag(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='tags')
    name = models.CharField(max_length=255)
    source = models.CharField(max_length=255, blank=True)

    def __str__(self) -> str:
        return self.name


class LeadForm(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='lead_forms')
    name = models.CharField(max_length=255)
    form_type = models.CharField(max_length=64, default='lead')


class ArchivedPerson(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='archived_people')
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=15)
    roles = models.CharField(max_length=255, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    comment = models.TextField(blank=True)
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'archived_at']),
        ]


class ArchiveReason(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='archive_reasons')
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class SmsLog(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='sms_logs')
    phone = models.CharField(max_length=15)
    message = models.TextField()
    status = models.CharField(max_length=32, default='sent')
    sent_at = models.DateTimeField(auto_now_add=True)


class CallLog(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='call_logs')
    call_type = models.CharField(max_length=32, default='outgoing')
    caller = models.CharField(max_length=255)
    callee = models.CharField(max_length=255)
    gateway = models.CharField(max_length=64, blank=True)
    duration = models.CharField(max_length=32, blank=True)
    result = models.CharField(max_length=64, blank=True)
    called_at = models.DateTimeField(auto_now_add=True)


class ActivityLog(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='activity_logs')
    action = models.CharField(max_length=255)
    actor_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PlatformPayment(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='platform_payments')
    amount = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
