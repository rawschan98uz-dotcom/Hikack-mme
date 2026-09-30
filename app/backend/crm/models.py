import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class Course(models.Model):
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='courses')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=64, blank=True)
    price = models.PositiveBigIntegerField(default=0, verbose_name='Цена в месяц (UZS)')
    lesson_duration = models.PositiveIntegerField(default=90, verbose_name='Длительность урока (минуты)')
    course_duration = models.PositiveIntegerField(default=12, verbose_name='Длительность курса (месяцы)')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class Group(models.Model):
    class Status(models.IntegerChoices):
        ACTIVE = 2, 'Активная'
        ARCHIVE = 3, 'В архиве'

    class Days(models.IntegerChoices):
        ODD = 1, 'Нечётные дни'
        EVEN = 2, 'Чётные дни'
        WEEKEND = 3, 'Выходные'
        EVERY_DAY = 4, 'Каждый день'
        CUSTOM = 5, 'Свои дни'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='groups')
    branch = models.ForeignKey('org.Branch', on_delete=models.PROTECT, related_name='groups')
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
    # Explicit weekdays (0=Mon … 6=Sun), used only when days == CUSTOM.
    weekdays = models.JSONField(default=list, blank=True)
    status = models.IntegerField(choices=Status.choices, default=Status.ACTIVE)
    lesson_start_time = models.TimeField(null=True, blank=True)
    lesson_end_time = models.TimeField(null=True, blank=True)
    group_start_date = models.DateField(null=True, blank=True)
    group_end_date = models.DateField(null=True, blank=True)
    tags = models.ManyToManyField('operations.Tag', blank=True, related_name='groups')
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='archived_groups',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'groups'

    def __str__(self) -> str:
        return self.name


class Student(models.Model):
    class Status(models.IntegerChoices):
        STUDYING = 1, 'Обучается'
        FROZEN = 2, 'Заморозка'
        LEFT_TRIAL = 7, 'Ушел после пробного'
        LEFT = 8, 'Отчислен / Ушел'
        GRADUATED = 9, 'Завершил курс'

    # Statuses of students who are still members of their group (left / graduated ones are history)
    CURRENT_STATUSES = (Status.STUDYING, Status.FROZEN)

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='students')
    branch = models.ForeignKey('org.Branch', on_delete=models.PROTECT, related_name='students')
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=15)
    phone2 = models.CharField(max_length=15, blank=True, default='')
    phone2_owner = models.CharField(max_length=64, blank=True, default='')
    address = models.CharField(max_length=255, blank=True, default='')
    comment = models.TextField(blank=True, default='')
    level = models.CharField(max_length=64, blank=True, default='')
    lead = models.ForeignKey('crm.Lead', on_delete=models.SET_NULL, null=True, blank=True, related_name='converted_students')
    photo = models.ImageField(upload_to='students/photos/', null=True, blank=True)
    school = models.CharField(max_length=255, blank=True)
    telegram = models.CharField(max_length=64, blank=True)
    parent_telegram = models.CharField(max_length=64, blank=True)
    telegram_code = models.CharField(max_length=16, null=True, blank=True, unique=True)
    status = models.IntegerField(choices=Status.choices, default=Status.STUDYING)
    # "Копилка": money paid on top of whole months, waiting to close the next month (finance/wallet.py)
    wallet_amount = models.BigIntegerField(default=0)
    paid_this_month = models.BooleanField(default=False)
    trial_date = models.DateField(null=True, blank=True)
    payment_offset = models.IntegerField(default=0)
    left_at = models.DateTimeField(null=True, blank=True)
    frozen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def full_name(self) -> str:
        return f'{self.first_name} {self.last_name}'.strip()

    def save(self, *args, **kwargs):
        left_statuses = {self.Status.LEFT, self.Status.LEFT_TRIAL}
        update_fields = kwargs.get('update_fields')
        # F6: status is not being written -> no need to look up the old one
        status_untouched = update_fields is not None and 'status' not in update_fields
        # Read by crm/signals.py: the student has just left / finished -> check for unpaid months
        self._just_left = False
        self._just_returned = False
        # Read by crm/signals.py: the freeze journal (StudentFreeze) opens / closes a period
        self._freeze_started = False
        self._freeze_ended = False
        if self.pk and not status_untouched:
            old_status = Student.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            self._freeze_started = self.status == self.Status.FROZEN and old_status != self.Status.FROZEN
            self._freeze_ended = old_status == self.Status.FROZEN and self.status != self.Status.FROZEN
            self._just_left = old_status in self.CURRENT_STATUSES and self.status in (
                self.Status.LEFT, self.Status.GRADUATED,
            )
            self._just_returned = old_status in (self.Status.LEFT, self.Status.GRADUATED)                 and self.status in self.CURRENT_STATUSES
            if self.status in left_statuses and old_status not in left_statuses:
                if not self.left_at:
                    self.left_at = timezone.now()
            elif self.status not in left_statuses:
                self.left_at = None

            if self.status == self.Status.FROZEN and old_status != self.Status.FROZEN:
                if not self.frozen_at:
                    self.frozen_at = timezone.now()
            elif self.status != self.Status.FROZEN:
                self.frozen_at = None
        elif not self.pk:
            self._freeze_started = self.status == self.Status.FROZEN
            if self.status in left_statuses and not self.left_at:
                self.left_at = timezone.now()
            if self.status == self.Status.FROZEN and not self.frozen_at:
                self.frozen_at = timezone.now()

        if not self.telegram_code:
            alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
            for _ in range(20):
                code = ''.join(secrets.choice(alphabet) for _ in range(8))
                if not Student.objects.filter(telegram_code=code).exists():
                    self.telegram_code = code
                    break
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.full_name


class Lead(models.Model):
    class Stage(models.TextChoices):
        TRIAL_BOOKED = 'trial_booked', 'Записан на пробный'
        ATTENDED = 'attended', 'Был на уроке (Думает)'
        REJECTED = 'rejected', 'Отказ'
        CONVERTED = 'converted', 'Зачислен (Студент)'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='leads')
    branch = models.ForeignKey('org.Branch', on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    course = models.ForeignKey('crm.Course', on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    first_name = models.CharField(max_length=150, default='')
    last_name = models.CharField(max_length=150, blank=True, default='')
    phone = models.CharField(max_length=15)
    phone2 = models.CharField(max_length=15, blank=True, default='')
    phone2_owner = models.CharField(max_length=64, blank=True, default='')
    address = models.CharField(max_length=255, blank=True, default='')
    school = models.CharField(max_length=255, blank=True, default='')
    comment = models.TextField(blank=True, default='')
    source = models.CharField(max_length=64, blank=True, default='')
    level = models.CharField(max_length=64, blank=True, default='')
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.TRIAL_BOOKED)
    attended_trial = models.BooleanField(default=False)
    trial_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def full_name(self) -> str:
        return f'{self.first_name} {self.last_name}'.strip()

    @property
    def status(self) -> str:
        return self.stage

    @status.setter
    def status(self, value: str):
        self.stage = value

    def save(self, *args, **kwargs):
        if self.stage == self.Stage.ATTENDED:
            self.attended_trial = True
        elif self.stage == self.Stage.TRIAL_BOOKED:
            # D3: moved back to "trial booked" -> the trial has not happened yet
            self.attended_trial = False
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.full_name


class AttendanceRecord(models.Model):
    class Status(models.IntegerChoices):
        PRESENT = 1, 'Был'
        ABSENT = 0, 'Не был'
        LATE = 2, 'Опоздал'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='attendance_records')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='attendance_records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    attend_date = models.DateField()
    status = models.IntegerField(choices=Status.choices, default=Status.PRESENT)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'student', 'group', 'attend_date'],
                name='uniq_student_attendance_per_group_day',
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'attend_date']),
            models.Index(fields=['group', 'attend_date']),
        ]

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError
        if self.student and self.group:
            if self.student.company_id != self.group.company_id:
                raise ValidationError('Student and group belong to different companies')
            if self.student.group_id != self.group.id:
                raise ValidationError('Student does not belong to this group')

    def __str__(self) -> str:
        return f'{self.student.full_name} — {self.attend_date}'


class GroupScheduleSlot(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='schedule_slots')
    weekday = models.SmallIntegerField(
        choices=[
            (0, 'Monday'),
            (1, 'Tuesday'),
            (2, 'Wednesday'),
            (3, 'Thursday'),
            (4, 'Friday'),
            (5, 'Saturday'),
            (6, 'Sunday'),
        ],
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.ForeignKey(
        'org.Room',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schedule_slots',
    )

    class Meta:
        indexes = [
            models.Index(fields=['group', 'weekday']),
        ]

    def __str__(self) -> str:
        return f'{self.group.name} - Day {self.weekday} ({self.start_time}-{self.end_time})'


class StudentFreeze(models.Model):
    """
    Freeze periods of a student (owner, 2026-09-28): a teacher's salary does not count the lessons a student
    was frozen for. start_date = the day of freezing; end_date = the day of unfreezing (NULL = still frozen).
    A lesson on day d is frozen when start_date <= d < end_date.
    """
    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='student_freezes')
    student = models.ForeignKey('Student', on_delete=models.CASCADE, related_name='freezes')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['student', 'start_date'])]


class GroupEnrollment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Учится'
        FROZEN = 'frozen', 'Заморозка'
        TRANSFERRED = 'transferred', 'Переведён'
        GRADUATED = 'graduated', 'Завершил курс'
        LEFT = 'left', 'Ушёл'

    company = models.ForeignKey('org.Company', on_delete=models.CASCADE, related_name='group_enrollments')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='enrollments')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    joined_date = models.DateField()
    left_date = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'student']),
            models.Index(fields=['group', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'group'],
                condition=models.Q(left_date__isnull=True),
                name='uniq_open_enrollment_per_student_group',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.student.full_name} in {self.group.name} ({self.status})'

