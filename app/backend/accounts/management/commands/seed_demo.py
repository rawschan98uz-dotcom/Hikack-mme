from datetime import date, time, timedelta

from django.core.management.base import BaseCommand

from accounts.models import TeacherBranch, User
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


class Command(BaseCommand):
    help = 'Seed demo company, users, and sample CRM data'

    def handle(self, *args, **options):
        company, _ = Company.objects.get_or_create(
            subdomain='ravvatech',
            defaults={
                'name': 'Hi Jack LMS',
                'balance_mode': Company.PaymentMode.DAILY,
                'phone': '903708242',
                'address': 'Tashkent, Uzbekistan',
                'work_start_time': time(9, 0),
                'work_end_time': time(18, 0),
            },
        )

        branch, _ = Branch.objects.get_or_create(
            company=company,
            name='Main branch',
            defaults={'address': 'Tashkent'},
        )

        user, created = User.objects.get_or_create(
            phone='903708242',
            defaults={
                'first_name': 'Ravshan',
                'last_name': 'Demo',
                'company': company,
                'user_type': User.UserType.STAFF,
                'job_title': '',
                'is_staff': True,
                'is_superuser': True,
            },
        )
        user.set_password('50608991Zz!')
        user.company = company
        user.is_superuser = True
        user.is_staff = True
        user.job_title = ''
        user.staff_role = User.StaffRole.CEO
        user.save()

        Branch.objects.get_or_create(
            company=company,
            name='Branch 2',
            defaults={'address': 'Second campus'},
        )

        User.objects.filter(company=company, user_type=User.UserType.TEACHER).delete()

        teacher_data = [
            ('901001001', 'Nilufar', 'Karimova', 'Teacher'),
            ('901001002', 'Jamshid', 'Rakhimov', 'Senior teacher'),
        ]
        teachers = []
        for phone, first, last, title in teacher_data:
            t, _ = User.objects.get_or_create(
                phone=phone,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'company': company,
                    'user_type': User.UserType.TEACHER,
                    'job_title': title,
                },
            )
            t.company = company
            t.user_type = User.UserType.TEACHER
            t.job_title = title
            t.set_password('demo1234')
            t.save()
            TeacherBranch.objects.get_or_create(teacher=t, branch=branch)
            teachers.append(t)

        course, _ = Course.objects.update_or_create(
            company=company,
            code='a1',
            defaults={
                'name': 'English A1',
                'price': 500_000,
                'lesson_duration': 90,
                'course_duration': 12,
                'description': 'Beginner English course',
            },
        )
        Course.objects.filter(company=company, code='a1').exclude(pk=course.pk).delete()

        group, _ = Group.objects.get_or_create(
            company=company,
            branch=branch,
            name='English-1',
            defaults={
                'course': course,
                'teacher': teachers[0] if teachers else None,
                'days': Group.Days.ODD,
                'status': Group.Status.ACTIVE,
                'lesson_start_time': time(14, 0),
                'lesson_end_time': time(15, 30),
            },
        )
        group.teacher = teachers[0] if teachers else None
        group.save(update_fields=['teacher'])

        Group.objects.get_or_create(
            company=company,
            branch=branch,
            name='English-2',
            defaults={
                'course': course,
                'teacher': teachers[1] if len(teachers) > 1 else None,
                'days': Group.Days.EVEN,
                'status': Group.Status.ACTIVE,
                'lesson_start_time': time(16, 0),
                'lesson_end_time': time(17, 30),
            },
        )

        lead_data = [
            ('Aziza Karimova', '901112233', Lead.Stage.INCOMING),
            ('Jasur Aliyev', '902223344', Lead.Stage.WAITING),
            ('Dilshod Mirzayev', '903334455', Lead.Stage.SET),
            ('Gulnora Saidova', '904445566', Lead.Stage.ATTENDED),
            ('Rustam Erkinov', '905556677', Lead.Stage.PAID),
        ]
        for name, phone, stage in lead_data:
            Lead.objects.update_or_create(
                company=company,
                phone=phone,
                defaults={'full_name': name, 'stage': stage, 'is_active': True},
            )

        samples = [
            ('Sardor', 'Rahimov', Student.Status.ACTIVE, True, 0),
            ('Dilnoza', 'Tursunova', Student.Status.TRIAL, False, 0),
            ('Bobur', 'Nazarov', Student.Status.DEBTOR, False, -120_000),
            ('Malika', 'Yusupova', Student.Status.LEFT_ACTIVE, False, 0),
            ('Timur', 'Saidov', Student.Status.LEFT_TRIAL, False, 0),
        ]
        students = []
        for idx, (first, last, status, paid, balance) in enumerate(samples, start=1):
            s, _ = Student.objects.update_or_create(
                company=company,
                phone=f'9099900{idx}',
                defaults={
                    'branch': branch,
                    'group': group,
                    'first_name': first,
                    'last_name': last,
                    'status': status,
                    'paid_this_month': paid,
                    'balance': balance,
                },
            )
            students.append(s)

        Payment.objects.get_or_create(
            company=company,
            student_name='Sardor Rahimov',
            amount=500_000,
            defaults={
                'method': Payment.Method.CASH,
                'teacher_name': '—',
                'comment': 'Monthly payment',
                'created_by': user,
            },
        )
        Payment.objects.get_or_create(
            company=company,
            student_name='Dilnoza Tursunova',
            amount=250_000,
            defaults={
                'method': Payment.Method.CARD,
                'teacher_name': '—',
                'comment': 'Trial lesson fee',
                'created_by': user,
            },
        )

        Withdrawal.objects.get_or_create(
            company=company,
            name='Office rent',
            amount=1_500_000,
            defaults={'comment': 'March rent', 'created_by': user},
        )

        cat, _ = ExpenseCategory.objects.get_or_create(company=company, name='Rent')
        ExpenseCategory.objects.get_or_create(company=company, name='Utilities')
        Expense.objects.get_or_create(
            company=company,
            description='Electricity bill',
            defaults={
                'category': cat,
                'payee': 'Uzenergo',
                'method': Expense.Method.TRANSFER,
                'amount': 350_000,
                'created_by': user,
            },
        )

        SalarySetting.objects.get_or_create(
            company=company,
            teacher_name='Nilufar Karimova',
            group_name='English-1',
            defaults={
                'salary_type': SalarySetting.SalaryType.FIXED,
                'amount': 3_000_000,
                'course_name': 'English A1',
                'created_by': user,
                'updated_by': user,
            },
        )

        today = date.today()
        attendance_statuses = [
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.ABSENT,
            AttendanceRecord.Status.LATE,
        ]
        for i, student in enumerate(students[:3]):
            AttendanceRecord.objects.get_or_create(
                company=company,
                group=group,
                student=student,
                attend_date=today - timedelta(days=i),
                defaults={'status': attendance_statuses[i]},
            )

        group2 = Group.objects.get(company=company, name='English-2')
        teacher_attendance_rows = [
            (teachers[0], group, TeacherAttendanceRecord.Status.PRESENT, 'On time'),
            (teachers[1], group2, TeacherAttendanceRecord.Status.LATE, 'Traffic delay'),
        ]
        for i, (teacher, grp, status, note) in enumerate(teacher_attendance_rows):
            TeacherAttendanceRecord.objects.get_or_create(
                company=company,
                teacher=teacher,
                group=grp,
                attend_date=today - timedelta(days=i),
                defaults={'status': status, 'note': note},
            )

        staff_users = [
            ('901002001', 'Kamola', 'Yusupova', 'Administrator', User.StaffRole.ADMINISTRATOR),
            ('901002002', 'Sherzod', 'Qodirov', 'Marketer', User.StaffRole.MARKETER),
            ('901002003', 'Dilnoza', 'Rahimova', 'Cashier', User.StaffRole.CASHIER),
        ]
        staff_accounts = []
        for phone, first, last, title, staff_role in staff_users:
            s, _ = User.objects.get_or_create(
                phone=phone,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'company': company,
                    'user_type': User.UserType.STAFF,
                    'staff_role': staff_role,
                    'job_title': title,
                },
            )
            s.company = company
            s.user_type = User.UserType.STAFF
            s.staff_role = staff_role
            s.job_title = title
            s.set_password('demo1234')
            s.save()
            staff_accounts.append(s)

        workly_rows = [
            (staff_accounts[0], WorklyRecord.Status.AT_WORK, time(9, 0), time(18, 0), 'On time'),
            (staff_accounts[1], WorklyRecord.Status.LATE_IN, time(9, 45), time(18, 15), 'Late arrival'),
            (user, WorklyRecord.Status.AT_WORK, time(8, 55), time(17, 30), 'Director'),
        ]
        for i, (staff, status, clock_in, clock_out, note) in enumerate(workly_rows):
            WorklyRecord.objects.get_or_create(
                company=company,
                staff=staff,
                work_date=today - timedelta(days=i),
                defaults={'status': status, 'clock_in': clock_in, 'clock_out': clock_out, 'note': note},
            )

        room101, _ = Room.objects.get_or_create(branch=branch, name='Room 101', defaults={'capacity': 15})
        room202, _ = Room.objects.get_or_create(branch=branch, name='Room 202', defaults={'capacity': 20})

        group.group_start_date = date(today.year, 1, 15)
        group.group_end_date = date(today.year + 1, 6, 1)
        group.room = room101
        group.save(update_fields=['group_start_date', 'group_end_date', 'room'])
        group2 = Group.objects.get(company=company, branch=branch, name='English-2')
        group2.group_start_date = date(today.year, 2, 1)
        group2.group_end_date = date(today.year + 1, 8, 1)
        group2.room = room202
        group2.save(update_fields=['group_start_date', 'group_end_date', 'room'])

        Holiday.objects.get_or_create(
            company=company,
            branch=branch,
            name='Navruz',
            holiday_date=date(today.year, 3, 21),
            defaults={'affects_payment': True},
        )

        Reminder.objects.get_or_create(
            company=company,
            title='Call new lead Aziza',
            defaults={
                'details': 'Follow up after trial',
                'due_date': today,
                'status': Reminder.Status.TODAY,
                'assigned_to': user,
            },
        )
        Reminder.objects.get_or_create(
            company=company,
            title='Send payment reminder',
            defaults={
                'details': 'Debtors list',
                'due_date': today - timedelta(days=2),
                'status': Reminder.Status.OVERDUE,
                'assigned_to': user,
            },
        )
        Reminder.objects.get_or_create(
            company=company,
            title='Prepare monthly report',
            defaults={
                'details': 'Finance summary for director',
                'due_date': today + timedelta(days=5),
                'status': Reminder.Status.FUTURE,
                'assigned_to': user,
            },
        )

        for rank, student in enumerate(students[:4], start=1):
            StudentScore.objects.update_or_create(
                company=company,
                student=student,
                group=group,
                defaults={'grade': 95 - rank * 5, 'rank': rank},
            )

        Tag.objects.get_or_create(company=company, name='Instagram', defaults={'source': 'Students'})
        Tag.objects.get_or_create(company=company, name='Website', defaults={'source': 'Web'})
        Tag.objects.get_or_create(company=company, name='test', defaults={'source': 'Students'})
        instagram_tag = Tag.objects.get(company=company, name='Instagram')
        group.tags.set([instagram_tag])
        group2.tags.set([instagram_tag])
        LeadForm.objects.get_or_create(company=company, name='Main lead form', defaults={'form_type': 'lead'})

        for reason_name in ('Moved abroad', 'No longer studying', 'Payment issues'):
            ArchiveReason.objects.get_or_create(company=company, name=reason_name)

        ArchivedPerson.objects.get_or_create(
            company=company,
            phone='908887766',
            defaults={
                'name': 'Old Student Test',
                'roles': 'student',
                'reason': 'Moved abroad',
                'comment': 'Archived manually',
            },
        )

        SmsLog.objects.get_or_create(
            company=company,
            phone='90999001',
            message='Your lesson is tomorrow at 14:00',
            defaults={'status': 'delivered'},
        )
        CallLog.objects.get_or_create(
            company=company,
            caller='Ravshan',
            callee='Sardor Rahimov',
            defaults={
                'call_type': 'outgoing',
                'gateway': 'VoIP',
                'duration': '2:34',
                'result': 'answered',
            },
        )
        ActivityLog.objects.get_or_create(
            company=company,
            action='User logged in',
            defaults={'actor_name': 'Ravshan'},
        )
        PlatformPayment.objects.get_or_create(
            company=company,
            amount=1_200_000,
            defaults={},
        )

        self.stdout.write(self.style.SUCCESS(
            f'Demo ready: company={company.subdomain}, login=903708242'
        ))
