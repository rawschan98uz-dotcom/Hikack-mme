"""E3 (branch director sees one branch) and B5 (teacher percent is taken from the discounted amount)."""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm.models import Course, AttendanceRecord, Group, Lead, Student
from finance.models import SalarySetting
from operations.models import Holiday
from org.models import Branch, Company, Room


class Block5Base(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Block5 Co', subdomain='block5')
        self.north = Branch.objects.create(company=self.company, name='North')
        self.south = Branch.objects.create(company=self.company, name='South')
        self.ceo = User.objects.create_user(
            phone='998909005501', password='password123', first_name='B5', last_name='CEO',
            company=self.company, user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.director = User.objects.create_user(
            phone='998909005502', password='password123', first_name='North', last_name='Director',
            company=self.company, user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.BRANCH_DIRECTOR, branch=self.north,
        )
        self.north_teacher = User.objects.create_user(
            phone='998909005503', password='password123', first_name='North', last_name='Teacher',
            company=self.company, user_type=User.UserType.TEACHER,
        )
        self.south_teacher = User.objects.create_user(
            phone='998909005504', password='password123', first_name='South', last_name='Teacher',
            company=self.company, user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=self.north_teacher, branch=self.north)
        TeacherBranch.objects.create(teacher=self.south_teacher, branch=self.south)
        self.north_group = Group.objects.create(
            company=self.company, branch=self.north, name='N-Group', teacher=self.north_teacher,
        )
        self.south_group = Group.objects.create(
            company=self.company, branch=self.south, name='S-Group', teacher=self.south_teacher,
        )
        self.north_student = Student.objects.create(
            company=self.company, branch=self.north, group=self.north_group, first_name='Nina', phone='901550001',
        )
        self.south_student = Student.objects.create(
            company=self.company, branch=self.south, group=self.south_group, first_name='Sam', phone='901550002',
        )
        self.north_lead = Lead.objects.create(company=self.company, branch=self.north, first_name='NL', phone='901550003')
        self.south_lead = Lead.objects.create(company=self.company, branch=self.south, first_name='SL', phone='901550004')


class BranchDirectorScopeTests(Block5Base):
    """E3"""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.director)

    def ids(self, url, key='results'):
        data = self.client.get(url).json()['data']
        rows = data[key] if isinstance(data, dict) else data
        return {r['id'] for r in rows}

    def test_sees_only_own_branch_lists(self):
        self.assertEqual(self.ids('/v1/branch'), {self.north.id})
        self.assertEqual(self.ids('/v1/students'), {self.north_student.id})
        self.assertEqual(self.ids('/v1/groups'), {self.north_group.id})
        self.assertEqual(self.ids('/v1/leads'), {self.north_lead.id})
        self.assertEqual(self.ids('/v1/user?user_type=teacher'), {self.north_teacher.id})
        me = self.client.post('/v1/auth/me').json()['data']
        self.assertEqual([b['id'] for b in me['branches']], [self.north.id])

    def test_other_branch_records_are_not_found(self):
        self.assertEqual(self.client.get(f'/v1/students/{self.south_student.id}').status_code, 404)
        self.assertEqual(self.client.get(f'/v1/groups/{self.south_group.id}').status_code, 404)
        self.assertEqual(self.client.get(f'/v1/leads/{self.south_lead.id}').status_code, 404)
        self.assertEqual(self.client.get(f'/v1/user/teacher/{self.south_teacher.id}').status_code, 404)
        self.assertEqual(self.client.get(f'/v1/students/{self.south_student.id}/payments').status_code, 404)
        self.assertEqual(self.client.get(f'/v1/students/{self.north_student.id}').status_code, 200)

    def test_cannot_create_or_move_into_other_branch(self):
        res = self.client.post('/v1/students', {
            'first_name': 'New', 'phone': '901550010', 'branch_id': self.south.id, 'trial_date': '2026-09-01',
        })
        self.assertEqual(res.status_code, 400)
        # the student's branch always follows the group's branch, so this changes nothing
        self.client.patch(f'/v1/students/{self.north_student.id}', {'branch_id': self.south.id}, format='json')
        res = self.client.patch(f'/v1/students/{self.north_student.id}', {'group_id': self.south_group.id}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.client.patch(f'/v1/groups/{self.north_group.id}', {'branch_id': self.south.id}, format='json')
        self.assertEqual(res.status_code, 400)
        self.north_student.refresh_from_db()
        self.assertEqual(self.north_student.branch_id, self.north.id)

    def test_new_lead_goes_to_director_branch(self):
        res = self.client.post('/v1/leads', {'first_name': 'Other', 'phone': '901550021', 'branch_id': self.south.id})
        self.assertEqual(res.status_code, 400)
        res = self.client.post('/v1/leads', {'first_name': 'Fresh', 'phone': '901550020'})
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(Lead.objects.get(pk=res.json()['data']['id']).branch_id, self.north.id)

    def test_rooms_holidays_attendance_scoped(self):
        Room.objects.create(company=self.company, branch=self.north, name='N1')
        Room.objects.create(company=self.company, branch=self.south, name='S1')
        Holiday.objects.create(company=self.company, branch=self.south, name='S-day', holiday_date=timezone.localdate())
        self.assertEqual({r['branch_id'] for r in self.client.get('/v1/room').json()['data']}, {self.north.id})
        self.assertEqual(self.client.get('/v1/holidays').json()['data'], [])
        AttendanceRecord.objects.create(
            company=self.company, student=self.south_student, group=self.south_group, attend_date=timezone.localdate(),
        )
        rows = self.client.get('/v1/reports/attendance').json()['data']
        rows = rows.get('rows', rows.get('results', [])) if isinstance(rows, dict) else rows
        self.assertEqual(rows, [])

    def test_director_without_branch_sees_nothing(self):
        self.director.branch = None
        self.director.save()
        self.assertEqual(self.ids('/v1/students'), set())
        self.assertEqual(self.ids('/v1/branch'), set())

    def test_ceo_still_sees_everything(self):
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.ids('/v1/students'), {self.north_student.id, self.south_student.id})


class StaffRoleAssignmentTests(Block5Base):
    """E3: CEO sets role + branch in the staff card"""

    def test_ceo_creates_director_with_branch(self):
        self.client.force_authenticate(self.ceo)
        res = self.client.post('/v1/user/staff', {
            'first_name': 'Dir', 'phone': '901550030', 'staff_role': 'branch_director', 'branch_id': self.south.id,
        })
        self.assertEqual(res.status_code, 201, res.content)
        user = User.objects.get(phone='901550030')
        self.assertEqual((user.staff_role, user.branch_id), ('branch_director', self.south.id))

    def test_director_requires_branch(self):
        self.client.force_authenticate(self.ceo)
        res = self.client.post('/v1/user/staff', {'first_name': 'Dir', 'phone': '901550031', 'staff_role': 'branch_director'})
        self.assertEqual(res.status_code, 400)

    def test_other_roles_drop_branch_and_ceo_role_not_assignable(self):
        self.client.force_authenticate(self.ceo)
        res = self.client.patch(f'/v1/user/staff/{self.director.id}', {'staff_role': 'marketer'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.director.refresh_from_db()
        self.assertIsNone(self.director.branch_id)
        res = self.client.patch(f'/v1/user/staff/{self.director.id}', {'staff_role': 'ceo'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_ceo_cannot_change_own_role(self):
        self.client.force_authenticate(self.ceo)
        res = self.client.patch(f'/v1/user/staff/{self.ceo.id}', {'staff_role': 'marketer'}, format='json')
        self.assertEqual(res.status_code, 400)


# DiscountSalaryTests: removed 2026-09-28 — a teacher's percent is no longer taken from payments; the
# discount rule of the new formula (course price − the student's monthly discount) is in tests_finance_block3.


class BranchDirectorFinanceTests(Block5Base):
    """E3: a director sees (read-only) the money of own branch only"""

    def setUp(self):
        super().setUp()
        from finance.models import Payment
        self.north_pay = Payment.objects.create(
            company=self.company, student=self.north_student, student_name='Nina', amount=300000,
            group=self.north_group, teacher=self.north_teacher,
        )
        self.south_pay = Payment.objects.create(
            company=self.company, student=self.south_student, student_name='Sam', amount=700000,
            group=self.south_group, teacher=self.south_teacher,
        )
        self.client.force_authenticate(self.director)

    def test_sees_only_own_branch_payments(self):
        ids = {p['id'] for p in self.client.get('/v1/replenishments').json()['data']['results']}
        self.assertEqual(ids, {self.north_pay.id})
        self.assertEqual(self.client.get(f'/v1/replenishments/{self.south_pay.id}').status_code, 404)
        self.assertEqual(self.client.get(f'/v1/replenishments/{self.north_pay.id}').status_code, 200)

    def test_dashboard_chart_is_own_branch_revenue(self):
        chart = self.client.get('/v1/dashboard').json()['data']['finance_chart']
        self.assertEqual(sum(p['value'] for p in chart), 300000)

    def test_payroll_lists_only_own_branch_teachers(self):
        rows = self.client.get('/v1/finance/payroll').json()['data']['rows']
        self.assertEqual({r['teacher_id'] for r in rows}, {self.north_teacher.id})

    def test_no_company_wide_money_and_no_writes(self):
        for url in ('/v1/expense', '/v1/withdraws', '/v1/reports/pnl', '/v1/expense_types'):
            self.assertEqual(self.client.get(url).status_code, 403, url)
        res = self.client.post('/v1/replenishments', {'student_id': self.north_student.id, 'amount': 1000})
        self.assertEqual(res.status_code, 403)

    def test_administrator_sees_payments_but_not_company_wide_money(self):
        # "Cashier" merged into "Administrator" (owner, 2026-09-28): payments yes, expenses / P&L no
        admin = User.objects.create_user(
            phone='998909005599', password='password123', first_name='Cash', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.ADMINISTRATOR,
        )
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get('/v1/expense').status_code, 403)
        self.assertEqual(len(self.client.get('/v1/replenishments').json()['data']['results']), 2)


class CyrillicCaseTests(Block5Base):
    """Case-insensitive search / matching works for Cyrillic, not only Latin"""

    def test_search_finds_cyrillic_name_in_any_case(self):
        Student.objects.create(company=self.company, branch=self.north, first_name='Азиз', last_name='Рахимов', phone='901550040')
        self.client.force_authenticate(self.ceo)
        rows = self.client.get('/v1/students?q=азиз').json()['data']['results']
        self.assertEqual([r['first_name'] for r in rows], ['Азиз'])

    def test_duplicate_student_detected_regardless_of_case(self):
        Student.objects.create(company=self.company, branch=self.north, first_name='Азиз', phone='901550041')
        self.client.force_authenticate(self.ceo)
        res = self.client.post('/v1/students', {
            'first_name': 'АЗИЗ', 'phone': '901550041', 'branch_id': self.north.id, 'trial_date': '2026-09-01',
        })
        self.assertEqual(res.status_code, 400)

    def test_import_matches_cyrillic_branch_and_group_names(self):
        import io
        branch = Branch.objects.create(company=self.company, name='Сергели')
        group = Group.objects.create(company=self.company, branch=branch, name='Английский А1')
        f = io.BytesIO('name,phone,branch,group\nВали Турсунов,901550042,сергели,английский а1\n'.encode('utf-8'))
        f.name = 'students.csv'
        self.client.force_authenticate(self.ceo)
        res = self.client.post('/v1/students/import', {'file': f}, format='multipart')
        self.assertEqual(res.status_code, 200, res.content)
        student = Student.objects.get(phone='901550042')
        self.assertEqual((student.branch_id, student.group_id), (branch.id, group.id))


# PayrollByPaymentDateTests: removed 2026-09-28 — salaries are counted by lessons held, not by payment dates
# (tests_finance_block3).

