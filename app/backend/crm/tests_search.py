"""Quick search (Ctrl+K): finds by name words and phone, stays inside the user's company and scope."""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm.models import Course, Group, Lead, Student
from org.models import Branch, Company


class GlobalSearchTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Search Co', subdomain='searchco')
        self.north = Branch.objects.create(company=self.company, name='North')
        self.south = Branch.objects.create(company=self.company, name='South')
        self.ceo = User.objects.create_user(
            phone='998909006601', password='password123', first_name='S', last_name='CEO',
            company=self.company, user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.director = User.objects.create_user(
            phone='998909006602', password='password123', first_name='North', last_name='Director',
            company=self.company, user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.BRANCH_DIRECTOR, branch=self.north,
        )
        self.teacher = User.objects.create_user(
            phone='998909006603', password='password123', first_name='Nilufar', last_name='Teacher',
            company=self.company, user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=self.teacher, branch=self.north)
        course = Course.objects.create(company=self.company, name='Математика', code='math', price=500_000)
        self.north_group = Group.objects.create(
            company=self.company, branch=self.north, name='Math Base', course=course, teacher=self.teacher,
        )
        self.south_group = Group.objects.create(company=self.company, branch=self.south, name='English A1')
        self.aziz = Student.objects.create(
            company=self.company, branch=self.north, group=self.north_group,
            first_name='Азиз', last_name='Каримов', phone='909990011',
        )
        self.aziza = Student.objects.create(
            company=self.company, branch=self.south, group=self.south_group,
            first_name='Азиза', last_name='Хасанова', phone='972223388',
        )
        self.lead = Lead.objects.create(company=self.company, branch=self.south, first_name='Азиз', last_name='Лидов', phone='935551122')

        other = Company.objects.create(name='Other Co', subdomain='otherco')
        other_branch = Branch.objects.create(company=other, name='Main')
        Student.objects.create(company=other, branch=other_branch, first_name='Азиз', last_name='Чужой', phone='909990012')

    def search(self, user, q):
        self.client.force_authenticate(user)
        res = self.client.get('/v1/search', {'q': q})
        self.assertEqual(res.status_code, 200)
        return res.json()['data']

    def test_every_word_must_match(self):
        data = self.search(self.ceo, 'азиз карим')
        self.assertEqual([s['id'] for s in data['students']], [self.aziz.id])
        self.assertEqual(data['students'][0]['group'], 'Math Base')

    def test_finds_by_phone_in_any_format(self):
        for q in ('+998 90 999 00 11', '90-999-00', '9990011'):
            data = self.search(self.ceo, q)
            self.assertEqual([s['id'] for s in data['students']], [self.aziz.id], q)

    def test_finds_leads_and_groups(self):
        data = self.search(self.ceo, 'азиз')
        self.assertEqual({s['id'] for s in data['students']}, {self.aziz.id, self.aziza.id})
        self.assertEqual([lead['id'] for lead in data['leads']], [self.lead.id])
        data = self.search(self.ceo, 'математ')
        self.assertEqual([g['id'] for g in data['groups']], [self.north_group.id])
        self.assertEqual(data['groups'][0]['teacher'], self.teacher.display_name())

    def test_never_shows_another_company(self):
        data = self.search(self.ceo, 'чужой')
        self.assertEqual(data['students'], [])

    def test_branch_director_sees_own_branch_only(self):
        data = self.search(self.director, 'азиз')
        self.assertEqual([s['id'] for s in data['students']], [self.aziz.id])
        self.assertEqual(data['leads'], [])  # the lead is in the other branch

    def test_teacher_sees_own_students_and_no_leads(self):
        data = self.search(self.teacher, 'азиз')
        self.assertEqual([s['id'] for s in data['students']], [self.aziz.id])
        self.assertEqual(data['leads'], [])
        data = self.search(self.teacher, 'english')
        self.assertEqual(data['groups'], [])

    def test_too_short_query_returns_nothing(self):
        data = self.search(self.ceo, 'а')
        self.assertEqual(data, {'students': [], 'leads': [], 'groups': []})
