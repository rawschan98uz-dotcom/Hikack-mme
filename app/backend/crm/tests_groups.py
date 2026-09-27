"""Groups audit: archiving with students, former students in the roster, counts, archive info."""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm.models import AttendanceRecord, Group, Student
from org.models import Branch, Company


class GroupAuditTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Groups Co', subdomain='groupsco')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.ceo = User.objects.create_user(
            phone='998909009101', password='password123', first_name='C', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.teacher = User.objects.create_user(
            phone='998909009102', password='password123', first_name='T', company=self.company,
            user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=self.teacher, branch=self.branch)
        self.group = Group.objects.create(
            company=self.company, branch=self.branch, name='G1', teacher=self.teacher, days=Group.Days.EVERY_DAY,
        )
        self.studying = Student.objects.create(company=self.company, branch=self.branch, group=self.group, first_name='Now', phone='901910001')
        self.client.force_authenticate(self.ceo)

    def make_former(self):
        former = Student.objects.create(company=self.company, branch=self.branch, group=self.group, first_name='Gone', phone='901910002')
        res = self.client.patch(f'/v1/students/{former.id}', {'status': Student.Status.LEFT}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        return former

    def test_cannot_archive_group_with_current_students(self):
        self.assertEqual(self.client.delete(f'/v1/groups/{self.group.id}').status_code, 400)
        self.assertEqual(self.client.patch(f'/v1/groups/{self.group.id}', {'status': Group.Status.ARCHIVE}, format='json').status_code, 400)
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, Group.Status.ACTIVE)

    def test_archive_via_edit_records_when_and_who_and_restore_clears(self):
        self.studying.status = Student.Status.GRADUATED
        self.studying.save()
        res = self.client.patch(f'/v1/groups/{self.group.id}', {'status': Group.Status.ARCHIVE}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.group.refresh_from_db()
        self.assertIsNotNone(self.group.archived_at)
        self.assertEqual(self.group.archived_by_id, self.ceo.id)
        self.client.patch(f'/v1/groups/{self.group.id}', {'status': Group.Status.ACTIVE}, format='json')
        self.group.refresh_from_db()
        self.assertIsNone(self.group.archived_at)

    def test_former_students_not_in_roster_or_count(self):
        former = self.make_former()
        data = self.client.get(f'/v1/groups/{self.group.id}').json()['data']
        self.assertEqual([s['id'] for s in data['students']], [self.studying.id])
        self.assertEqual(data['students_count'], 1)
        rows = self.client.get('/v1/groups').json()['data']['results']
        self.assertEqual(next(r for r in rows if r['id'] == self.group.id)['students_count'], 1)
        self.assertNotEqual(former.id, self.studying.id)

    def test_attendance_not_saved_for_former_students(self):
        former = self.make_former()
        res = self.client.post('/v1/reports/attendance', {
            'group_id': self.group.id, 'date': timezone.localdate().isoformat(),
            'records': [{'student_id': self.studying.id, 'status': 1}, {'student_id': former.id, 'status': 1}],
        }, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['saved'], 1)
        self.assertFalse(AttendanceRecord.objects.filter(student=former).exists())

    def test_roster_is_not_cut_at_100(self):
        for i in range(105):
            Student.objects.create(company=self.company, branch=self.branch, group=self.group, first_name=f'S{i:03d}', phone=f'9019{i:05d}')
        data = self.client.get(f'/v1/groups/{self.group.id}').json()['data']
        self.assertEqual(len(data['students']), 106)

    def test_moving_group_to_another_branch_moves_current_students(self):
        second = Branch.objects.create(company=self.company, name='Second')
        TeacherBranch.objects.create(teacher=self.teacher, branch=second)
        former = self.make_former()
        res = self.client.patch(f'/v1/groups/{self.group.id}', {'branch_id': second.id}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.studying.refresh_from_db()
        former.refresh_from_db()
        self.assertEqual(self.studying.branch_id, second.id)
        self.assertEqual(former.branch_id, self.branch.id)  # history stays where it happened
