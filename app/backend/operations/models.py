from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class Reminder(models.Model):
    class Status(models.TextChoices):
        OVERDUE = 'overdue', 'Просрочено'
        TODAY = 'today', 'Сегодня'
        FUTURE = 'future', 'Предстоит'
        DONE = 'done', 'Выполнено'

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
    # Set for automatic reminders about a student (e.g. "left without paying"): link to the card
    # and branch scoping for branch directors.
    student = models.ForeignKey(
        'crm.Student',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reminders',
    )
    # '' = created by a person; 'unpaid_leave' = automatic "student left without paying"
    kind = models.CharField(max_length=32, blank=True, default='')
    # How an automatic reminder was closed ("оплачено" / "списано CEO: причина")
    resolution = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    KIND_UNPAID_LEAVE = 'unpaid_leave'

    @property
    def current_status(self) -> str:
        """D7: OVERDUE/TODAY/FUTURE is computed from due_date on every read; only DONE is stored."""
        from django.utils import timezone

        if self.status == self.Status.DONE:
            return self.Status.DONE
        today = timezone.localdate()
        if self.due_date < today:
            return self.Status.OVERDUE
        if self.due_date > today:
            return self.Status.FUTURE
        return self.Status.TODAY


class Holiday(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='holidays')
    branch = models.ForeignKey('org.Branch', on_delete=models.CASCADE, related_name='holidays')
    name = models.CharField(max_length=255)
    holiday_date = models.DateField()
    affects_payment = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['company', 'branch', 'holiday_date'], name='uniq_holiday_per_branch_day'),
        ]


class StudentScore(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='scores')
    student = models.ForeignKey('crm.Student', on_delete=models.CASCADE, related_name='scores')
    group = models.ForeignKey('crm.Group', on_delete=models.CASCADE, related_name='scores')
    grade = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    rank = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['student', 'group'], name='uniq_score_per_student_group'),
        ]


class TeacherAttendanceRecord(models.Model):
    class Status(models.IntegerChoices):
        PRESENT = 1, 'Был'
        ABSENT = 0, 'Не был'
        LATE = 2, 'Опоздал'

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
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'teacher', 'group', 'attend_date'],
                name='uniq_teacher_attendance_per_day',
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'attend_date']),
        ]

    def __str__(self) -> str:
        return f'{self.teacher} — {self.attend_date}'


class WorklyRecord(models.Model):
    class Status(models.TextChoices):
        AT_WORK = 'at_work', 'На работе'
        LATE_IN = 'late_in', 'Опоздал'
        ABSENT = 'absent', 'Отсутствовал'

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
        constraints = [
            models.UniqueConstraint(fields=['company', 'staff', 'work_date'], name='uniq_workly_per_day'),
        ]
        indexes = [
            models.Index(fields=['company', 'work_date']),
        ]

    def __str__(self) -> str:
        return f'{self.staff} — {self.work_date}'


class Tag(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='tags')
    name = models.CharField(max_length=255)
    source = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower('name'), 'company', name='uniq_tag_name_per_company'),
        ]

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


class NotificationLog(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='notification_logs')
    student = models.ForeignKey('crm.Student', on_delete=models.CASCADE, related_name='notification_logs')
    rule = models.CharField(max_length=64)
    trigger_date = models.DateField()
    target = models.CharField(max_length=64, blank=True)
    message = models.TextField()
    ok = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'rule', 'trigger_date']),
            models.Index(fields=['student', 'created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'rule', 'trigger_date'],
                condition=models.Q(ok=True),
                name='uniq_ok_notification_per_day',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.student} | {self.rule} | {self.trigger_date}'


class CallLog(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='call_logs')
    call_type = models.CharField(max_length=32, default='outgoing')
    caller = models.CharField(max_length=255)
    callee = models.CharField(max_length=255)
    gateway = models.CharField(max_length=64, blank=True)
    duration = models.CharField(max_length=32, blank=True)
    result = models.CharField(max_length=64, blank=True)
    called_at = models.DateTimeField(auto_now_add=True)


class PlatformPayment(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='platform_payments')
    amount = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class AuditLogRecord(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='audit_log_records')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_log_records',
    )
    actor_name = models.CharField(max_length=255, blank=True)
    entity_type = models.CharField(max_length=64)
    entity_id = models.PositiveIntegerField()
    action = models.CharField(max_length=32)
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'entity_type', 'created_at']),
            models.Index(fields=['entity_type', 'entity_id']),
        ]

    def __str__(self) -> str:
        return f'{self.actor_name or "System"} {self.action} {self.entity_type}#{self.entity_id}'


def log_audit(
    company,
    actor=None,
    entity_type: str = '',
    entity_id: int = 0,
    action: str = '',
    old_values: dict | None = None,
    new_values: dict | None = None,
    reason: str = '',
) -> AuditLogRecord:
    actor_name = ''
    actual_actor = None
    if actor and getattr(actor, 'is_authenticated', False) and getattr(actor, 'pk', None):
        actual_actor = actor
        if hasattr(actor, 'display_name'):
            actor_name = actor.display_name()
        elif hasattr(actor, 'get_full_name'):
            actor_name = actor.get_full_name() or getattr(actor, 'phone', '')
        else:
            actor_name = str(actor)

    return AuditLogRecord.objects.create(
        company=company,
        actor=actual_actor,
        actor_name=actor_name,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_values=old_values or {},
        new_values=new_values or {},
        reason=reason,
    )

