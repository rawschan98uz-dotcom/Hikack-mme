"""Student card "Attendance" tab: the student's marks and current group, within the user's scope."""

from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm.models import AttendanceRecord, Group, Student
from org.models import Branch, Company


class StudentAttendanceTabTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Card Co', subdomain='cardco')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.ceo = User.objects.create_user(
            phone='998909007701', password='password123', first_name='C', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.teacher = User.objects.create_user(
            phone='998909007702', password='password123', first_name='T', company=self.company,
            user_type=User.UserType.TEACHER,
        )
        self.other_teacher = User.objects.create_user(
            phone='998909007703', password='password123', first_name='O', company=self.company,
            user_type=User.UserType.TEACHER,
        )
        for t in (self.teacher, self.other_teacher):
            TeacherBranch.objects.create(teacher=t, branch=self.branch)
        self.old_group = Group.objects.create(company=self.company, branch=self.branch, name='Old', teacher=self.other_teacher)
        self.group = Group.objects.create(company=self.company, branch=self.branch, name='New', teacher=self.teacher)
        self.student = Student.objects.create(
            company=self.company, branch=self.branch, group=self.group, first_name='Ali', phone='901230001',
        )
        # Marks from the previous group were made while the student was in it
        AttendanceRecord.objects.create(
            company=self.company, group=self.old_group, student=self.student, attend_date=date(2026, 9, 1), status=0,
        )
        for day, status in ((2, 1), (4, 2), (6, 1)):
            AttendanceRecord.objects.create(
                company=self.company, group=self.group, student=self.student, attend_date=date(2026, 10, day), status=status,
            )

    def get(self, user):
        self.client.force_authenticate(user)
        return self.client.get(f'/v1/students/{self.student.id}/attendance')

    def test_ceo_sees_all_marks_newest_first_and_the_group(self):
        res = self.get(self.ceo)
        self.assertEqual(res.status_code, 200)
        data = res.json()['data']
        self.assertEqual(data['summary'], {'total': 4, 'present': 2, 'late': 1, 'absent': 1})
        self.assertEqual([r['date'] for r in data['records']], ['2026-10-06', '2026-10-04', '2026-10-02', '2026-09-01'])
        self.assertEqual(data['group']['name'], 'New')

    def test_teacher_sees_only_marks_of_own_group(self):
        data = self.get(self.teacher).json()['data']
        self.assertEqual(data['summary']['total'], 3)
        self.assertEqual({r['group'] for r in data['records']}, {'New'})

    def test_teacher_of_another_group_gets_not_found(self):
        self.assertEqual(self.get(self.other_teacher).status_code, 404)

    def test_other_company_gets_not_found(self):
        other = Company.objects.create(name='Other', subdomain='othercard')
        stranger = User.objects.create_user(
            phone='998909007704', password='password123', first_name='S', company=other,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.assertEqual(self.get(stranger).status_code, 404)
