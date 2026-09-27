from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, phone: str, password: str | None = None, **extra):
        if not phone:
            raise ValueError('Phone is required')
        user = self.model(phone=phone, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone: str, password: str | None = None, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        return self.create_user(phone, password, **extra)


class User(AbstractUser):
    class UserType(models.TextChoices):
        STAFF = 'staff', 'Сотрудник'
        TEACHER = 'teacher', 'Учитель'
        STUDENT = 'student', 'Студент'

    class StaffRole(models.TextChoices):
        CEO = 'ceo', 'CEO'
        ADMINISTRATOR = 'administrator', 'Администратор'
        BRANCH_DIRECTOR = 'branch_director', 'Директор филиала'
        LIMITED_ADMIN = 'limited_admin', 'Ограниченный админ'
        MARKETER = 'marketer', 'Маркетолог'
        CASHIER = 'cashier', 'Кассир'

    username = None
    email = None
    phone = models.CharField(max_length=15, unique=True)
    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.STAFF,
    )
    staff_role = models.CharField(
        max_length=32,
        choices=StaffRole.choices,
        blank=True,
        default='',
    )
    job_title = models.CharField(max_length=255, blank=True)
    honorific = models.CharField(max_length=10, blank=True)
    company = models.ForeignKey(
        'org.Company',
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True,
    )

    # E3: the only branch a branch director works with (sees no other branch's data)
    branch = models.ForeignKey(
        'org.Branch',
        on_delete=models.SET_NULL,
        related_name='directors',
        null=True,
        blank=True,
        verbose_name='Филиал директора',
    )

    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def display_name(self) -> str:
        full = f'{self.first_name} {self.last_name}'.strip()
        if self.honorific and full:
            return f'{self.honorific}. {full}'
        return full or self.phone

    def __str__(self) -> str:
        return self.phone


class TeacherBranch(models.Model):
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='teacher_branches')
    branch = models.ForeignKey('org.Branch', on_delete=models.CASCADE, related_name='teacher_links')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['teacher', 'branch'], name='uniq_teacher_branch'),
        ]
