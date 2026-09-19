from datetime import time

from django.core.management.base import BaseCommand

from accounts.models import User
from crm.models import AttendanceRecord, Course, Group, Lead, Student
from finance.models import Expense, ExpenseCategory, Payment, SalarySetting, Withdrawal
from operations.models import (
    ActivityLog,
    ArchiveReason,
    ArchivedPerson,
    CallLog,
    Holiday,
    LeadForm,
    PlatformPayment,
    Reminder,
    SmsLog,
    StudentScore,
    Tag,
    TeacherAttendanceRecord,
    WorklyRecord,
)
from org.models import Branch, Company, Room

DEMO_PASSWORD = 'HiJack2024!'


class Command(BaseCommand):
    help = 'Initialize clean company and CEO account without dummy/sample data'

    def handle(self, *args, **options):
        # 1. Ensure company exists
        company, _ = Company.objects.get_or_create(
            subdomain='ravvatech',
            defaults={
                'name': 'Hi Jack LMS',
                'balance_mode': Company.PaymentMode.DAILY,
                'phone': '946263200',
                'address': 'Tashkent, Uzbekistan',
                'work_start_time': time(9, 0),
                'work_end_time': time(18, 0),
            },
        )

        # 2. Ensure main branch exists
        branch, _ = Branch.objects.get_or_create(
            company=company,
            name='Main branch',
            defaults={'address': 'Tashkent'},
        )
        Branch.objects.filter(company=company).exclude(pk=branch.pk).delete()

        # 3. Ensure CEO user exists with secure demo password
        user, _ = User.objects.get_or_create(
            phone='946263200',
            defaults={
                'first_name': 'Ravshan',
                'last_name': 'Demo',
                'company': company,
                'user_type': User.UserType.STAFF,
                'job_title': 'Director',
                'is_staff': True,
                'is_superuser': True,
            },
        )
        user.company = company
        user.is_superuser = True
        user.is_staff = True
        user.staff_role = User.StaffRole.CEO
        user.set_password(DEMO_PASSWORD)
        user.save()

        # Remove any other non-CEO users
        User.objects.filter(company=company).exclude(pk=user.pk).delete()

        # 4. Clean all transactional and sample data (0 students, 0 leads, 0 groups, etc.)
        Student.objects.filter(company=company).delete()
        Lead.objects.filter(company=company).delete()
        Group.objects.filter(company=company).delete()
        default_courses = [
            ('Английский', 'ENG', 600000),
            ('Математика', 'MATH', 500000),
            ('Немецкий', 'GER', 600000),
            ('Китайский', 'CHN', 650000),
        ]
        for c_name, c_code, c_price in default_courses:
            Course.objects.get_or_create(
                company=company,
                name=c_name,
                defaults={
                    'code': c_code,
                    'price': c_price,
                    'lesson_duration': 90,
                    'course_duration': 12,
                    'description': f'Курс {c_name}',
                }
            )
        Room.objects.filter(branch=branch).delete()
        Tag.objects.filter(company=company).delete()
        Payment.objects.filter(company=company).delete()
        Withdrawal.objects.filter(company=company).delete()
        Expense.objects.filter(company=company).delete()
        SalarySetting.objects.filter(company=company).delete()
        AttendanceRecord.objects.filter(company=company).delete()
        TeacherAttendanceRecord.objects.filter(company=company).delete()
        StudentScore.objects.filter(company=company).delete()
        Reminder.objects.filter(company=company).delete()
        ArchivedPerson.objects.filter(company=company).delete()
        WorklyRecord.objects.filter(company=company).delete()
        SmsLog.objects.filter(company=company).delete()
        CallLog.objects.filter(company=company).delete()
        ActivityLog.objects.filter(company=company).delete()
        PlatformPayment.objects.filter(company=company).delete()
        Holiday.objects.filter(company=company).delete()

        # 5. Standard справочники (categories & reasons for forms)
        for cat_name in ('Rent', 'Utilities', 'Salaries', 'Marketing', 'Office', 'Other'):
            ExpenseCategory.objects.get_or_create(company=company, name=cat_name)

        for reason in ('Moved abroad', 'No longer studying', 'Payment issues', 'Completed course'):
            ArchiveReason.objects.get_or_create(company=company, name=reason)

        LeadForm.objects.get_or_create(
            company=company,
            name='Main lead form',
            defaults={'form_type': 'lead'},
        )

        self.stdout.write(self.style.SUCCESS(
            f'Clean database ready: company={company.subdomain} ({company.name}), '
            f'login=946263200, password={DEMO_PASSWORD}\n'
            f'All sample data removed: 0 students, 0 leads, 0 groups, 0 courses.'
        ))
