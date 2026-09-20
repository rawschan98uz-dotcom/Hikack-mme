from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User, TeacherBranch
from crm.models import AttendanceRecord, Course, Group, GroupEnrollment, GroupScheduleSlot, Lead, Student
from finance.models import Payment, SalarySetting, PayrollPayment
from operations.models import AuditLogRecord, StudentScore, TeacherAttendanceRecord
from org.models import Company, Branch, Room



class UserDeletionPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Test Company', subdomain='testcomp')
        self.branch = Branch.objects.create(company=self.company, name='Main Branch')

        # CEO user
        self.ceo = User.objects.create_user(
            phone='998901111111',
            password='password123',
            first_name='Chief',
            last_name='Executive',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )

        # Administrator user
        self.admin = User.objects.create_user(
            phone='998902222222',
            password='password123',
            first_name='Admin',
            last_name='User',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.ADMINISTRATOR,
        )

        # Staff user
        self.staff = User.objects.create_user(
            phone='998903333333',
            password='password123',
            first_name='Staff',
            last_name='Member',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.LIMITED_ADMIN,
        )

        # Teacher user
        self.teacher = User.objects.create_user(
            phone='998904444444',
            password='password123',
            first_name='Teacher',
            last_name='One',
            company=self.company,
            user_type=User.UserType.TEACHER,
        )

    def test_ceo_cannot_delete_themselves_via_staff_endpoint(self):
        self.client.force_authenticate(user=self.ceo)
        response = self.client.delete(f'/v1/user/staff/{self.ceo.id}')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(id=self.ceo.id).exists())

    def test_staff_cannot_delete_themselves(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.delete(f'/v1/user/staff/{self.staff.id}')
        self.assertIn(response.status_code, [400, 403])
        self.assertTrue(User.objects.filter(id=self.staff.id).exists())

    def test_teacher_cannot_delete_themselves(self):
        self.client.force_authenticate(user=self.teacher)
        response = self.client.delete(f'/v1/user/teacher/{self.teacher.id}')
        self.assertIn(response.status_code, [400, 403])
        self.assertTrue(User.objects.filter(id=self.teacher.id).exists())

    def test_admin_cannot_delete_staff(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/v1/user/staff/{self.staff.id}')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(id=self.staff.id).exists())

    def test_admin_cannot_delete_teacher(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/v1/user/teacher/{self.teacher.id}')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(id=self.teacher.id).exists())

    def test_ceo_can_delete_staff(self):
        self.client.force_authenticate(user=self.ceo)
        response = self.client.delete(f'/v1/user/staff/{self.staff.id}')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(id=self.staff.id).exists())

    def test_ceo_can_delete_teacher(self):
        self.client.force_authenticate(user=self.ceo)
        response = self.client.delete(f'/v1/user/teacher/{self.teacher.id}')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(id=self.teacher.id).exists())


class LeadFieldsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Test Company', subdomain='testlead')
        self.branch = Branch.objects.create(company=self.company, name='Chilanzar Branch')
        self.course = Course.objects.create(company=self.company, name='Английский', price=600000)
        self.ceo = User.objects.create_user(
            phone='998909999999',
            password='password123',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )

    def test_create_and_retrieve_lead_with_extra_fields(self):
        self.client.force_authenticate(user=self.ceo)
        payload = {
            'first_name': 'Alisher',
            'last_name': 'Navoiy',
            'phone': '998901234567',
            'phone2': '998912345678',
            'address': 'Tashkent, Chilanzar 5',
            'comment': 'Interested in IELTS course, evenings',
            'source': 'Instagram',
            'level': 'Intermediate (B1)',
            'branch_id': self.branch.id,
            'course_id': self.course.id,
            'stage': 'trial_booked',
            'trial_date': '2025-05-15',
        }
        res = self.client.post('/v1/leads', payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()['data']
        self.assertEqual(data['first_name'], 'Alisher')
        self.assertEqual(data['last_name'], 'Navoiy')
        self.assertEqual(data['full_name'], 'Alisher Navoiy')
        self.assertEqual(data['phone'], '901234567')
        self.assertEqual(data['phone2'], '912345678')
        self.assertEqual(data['address'], 'Tashkent, Chilanzar 5')
        self.assertEqual(data['comment'], 'Interested in IELTS course, evenings')
        self.assertEqual(data['source'], 'Instagram')
        self.assertEqual(data['level'], 'Intermediate (B1)')
        self.assertEqual(data['branch_id'], self.branch.id)
        self.assertEqual(data['course_id'], self.course.id)
        self.assertEqual(data['course_name'], 'Английский')
        self.assertEqual(data['trial_date'], '2025-05-15')

        # Test search by first_name and address
        search_res = self.client.get('/v1/leads?q=Alisher')
        self.assertEqual(search_res.status_code, 200)
        self.assertEqual(len(search_res.json()['data']['results']), 1)

        # Test filter by branch_id, course_id, and level
        b_res = self.client.get(f'/v1/leads?branch_id={self.branch.id}')
        self.assertEqual(len(b_res.json()['data']['results']), 1)
        c_res = self.client.get(f'/v1/leads?course_id={self.course.id}')
        self.assertEqual(len(c_res.json()['data']['results']), 1)
        l_res = self.client.get('/v1/leads?level=Intermediate (B1)')
        self.assertEqual(len(l_res.json()['data']['results']), 1)

        # Test update
        lead_id = data['id']
        patch_res = self.client.patch(f'/v1/leads/{lead_id}', {
            'first_name': 'Bobur',
            'last_name': 'Mirzo',
            'address': 'Tashkent, Yunusabad',
            'comment': 'Changed mind, wants morning group',
            'source': 'Telegram',
            'level': 'Advanced (C1)',
            'trial_date': '2025-05-20',
        })
        self.assertEqual(patch_res.status_code, 200)
        updated = patch_res.json()['data']
        self.assertEqual(updated['first_name'], 'Bobur')
        self.assertEqual(updated['last_name'], 'Mirzo')
        self.assertEqual(updated['full_name'], 'Bobur Mirzo')
        self.assertEqual(updated['address'], 'Tashkent, Yunusabad')
        self.assertEqual(updated['comment'], 'Changed mind, wants morning group')
        self.assertEqual(updated['source'], 'Telegram')
        self.assertEqual(updated['level'], 'Advanced (C1)')
        self.assertEqual(updated['trial_date'], '2025-05-20')


class LeadToStudentConversionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Test Company', subdomain='testconvert')
        self.branch = Branch.objects.create(company=self.company, name='Central Branch')
        self.ceo = User.objects.create_user(
            phone='998908888888',
            password='password123',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )

    def test_create_student_with_extra_fields(self):
        self.client.force_authenticate(user=self.ceo)
        payload = {
            'first_name': 'Jasur',
            'last_name': 'Karimov',
            'phone': '998901112233',
            'phone2': '998934445566',
            'address': 'Tashkent, Mirzo-Ulugbek 12',
            'comment': 'Good English foundation',
            'level': 'Beginner (A1)',
            'branch_id': self.branch.id,
            'trial_date': '2025-05-10',
        }
        res = self.client.post('/v1/students', payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()['data']
        self.assertEqual(data['first_name'], 'Jasur')
        self.assertEqual(data['last_name'], 'Karimov')
        self.assertEqual(data['phone'], '901112233')
        self.assertEqual(data['phone2'], '934445566')
        self.assertEqual(data['address'], 'Tashkent, Mirzo-Ulugbek 12')
        self.assertEqual(data['comment'], 'Good English foundation')
        self.assertEqual(data['level'], 'Beginner (A1)')
        self.assertEqual(data['trial_date'], '2025-05-10')
        self.assertEqual(data['next_payment_date'], '2025-05-10')

        # Test search by comment or address
        search_res = self.client.get('/v1/students?q=Mirzo-Ulugbek')
        self.assertEqual(search_res.status_code, 200)
        self.assertEqual(len(search_res.json()['data']['results']), 1)

    def test_convert_lead_to_student(self):
        self.client.force_authenticate(user=self.ceo)
        # 1. Create a lead with first_name, last_name, and trial_date
        lead_payload = {
            'first_name': 'Nodirbek',
            'last_name': 'Rustamov',
            'phone': '998907776655',
            'phone2': '998918889900',
            'address': 'Samarkand, Registan 3',
            'comment': 'Trial lesson passed successfully',
            'level': 'Elementary (A2)',
            'stage': 'attended',
            'trial_date': '2025-05-12',
        }
        lead_res = self.client.post('/v1/leads', lead_payload)
        self.assertEqual(lead_res.status_code, 201)
        lead_id = lead_res.json()['data']['id']

        # 2. Convert lead to student
        convert_payload = {
            'branch_id': self.branch.id,
        }
        convert_res = self.client.post(f'/v1/leads/{lead_id}/convert', convert_payload)
        self.assertEqual(convert_res.status_code, 201)
        res_data = convert_res.json()['data']

        student_data = res_data['student']

        # Check student fields copied from lead
        self.assertEqual(student_data['first_name'], 'Nodirbek')
        self.assertEqual(student_data['last_name'], 'Rustamov')
        self.assertEqual(student_data['phone'], '907776655')
        self.assertEqual(student_data['phone2'], '918889900')
        self.assertEqual(student_data['address'], 'Samarkand, Registan 3')
        self.assertEqual(student_data['comment'], 'Trial lesson passed successfully')
        self.assertEqual(student_data['level'], 'Elementary (A2)')
        self.assertEqual(student_data['branch_id'], self.branch.id)
        self.assertEqual(student_data['status'], 1)  # STUDYING
        self.assertEqual(student_data['trial_date'], '2025-05-12')
        self.assertEqual(student_data['next_payment_date'], '2025-05-12')

        # Check lead is preserved in database with stage CONVERTED
        lead = Lead.objects.get(pk=lead_id)
        self.assertEqual(lead.stage, Lead.Stage.CONVERTED)
        self.assertEqual(lead.branch_id, self.branch.id)

        # Check student links to lead and has level copied
        student = Student.objects.get(pk=student_data['id'])
        self.assertEqual(student.lead_id, lead_id)
        self.assertEqual(student.level, 'Elementary (A2)')

    def test_convert_lead_rbac_forbidden(self):
        teacher = User.objects.create_user(
            phone='998905555555',
            password='password123',
            company=self.company,
            user_type=User.UserType.TEACHER,
        )
        self.client.force_authenticate(user=teacher)
        lead = Lead.objects.create(
            company=self.company,
            first_name='TestLead',
            phone='901234567',
        )
        res = self.client.post(f'/v1/leads/{lead.id}/convert', {'branch_id': self.branch.id})
        self.assertEqual(res.status_code, 403)

    def test_secondary_phone_validation(self):
        self.client.force_authenticate(user=self.ceo)
        # 1. Lead creation with short phone2 (8 digits) should fail
        res = self.client.post('/v1/leads', {
            'first_name': 'Test',
            'phone': '901234567',
            'phone2': '23232323',
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Secondary phone must contain 9 digits', res.json()['message'])

        # 2. Lead creation with valid phone2 (9 digits) should succeed
        res = self.client.post('/v1/leads', {
            'first_name': 'Test',
            'phone': '901234567',
            'phone2': '901234568',
            'phone2_owner': 'Father',
        })
        self.assertEqual(res.status_code, 201)
        lead_id = res.json()['data']['id']

        # 3. Lead update with short phone2 should fail
        res = self.client.patch(f'/v1/leads/{lead_id}', {
            'phone2': '12345678',
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Secondary phone must contain 9 digits', res.json()['message'])

        # 4. Student creation with short phone2 should fail
        res = self.client.post('/v1/students', {
            'first_name': 'StudentTest',
            'phone': '909998877',
            'phone2': '99812345',
            'trial_date': '2026-05-10',
            'branch_id': self.branch.id,
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Secondary phone must contain 9 digits', res.json()['message'])

        # 5. Student creation without trial_date should fail
        res = self.client.post('/v1/students', {
            'first_name': 'StudentNoDate',
            'phone': '909998877',
            'branch_id': self.branch.id,
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Trial / start date is required', res.json()['message'])

    def test_anchor_date_advance_and_debtor_status(self):
        self.client.force_authenticate(user=self.ceo)
        # Create student with anchor date 2026-10-15
        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Anvar',
            last_name='Toshmatov',
            phone='901239999',
            status=Student.Status.STUDYING,
            trial_date='2026-10-15',
        )

        # 0 payments: next payment date is 2026-10-15
        res0 = self.client.get(f'/v1/students/{student.id}')
        data0 = res0.json()['data']
        self.assertEqual(data0['next_payment_date'], '2026-10-15')
        self.assertEqual(data0['paid_count'], 0)

        # 1st payment made late (e.g. Nov 20): next payment advances to 2026-11-15 (NOT Nov 20!)
        Payment.objects.create(
            company=self.company,
            student_name=student.full_name,
            amount=500000,
        )

        res1 = self.client.get(f'/v1/students/{student.id}')
        data1 = res1.json()['data']
        self.assertEqual(data1['next_payment_date'], '2026-11-15')
        self.assertEqual(data1['paid_count'], 1)

        # 2nd payment made: advances to 2026-12-15
        Payment.objects.create(
            company=self.company,
            student_name=student.full_name,
            amount=500000,
        )

        res2 = self.client.get(f'/v1/students/{student.id}')
        data2 = res2.json()['data']
        self.assertEqual(data2['next_payment_date'], '2026-12-15')
        self.assertEqual(data2['paid_count'], 2)

    def test_unfreeze_student_with_new_anchor_date(self):
        self.client.force_authenticate(user=self.ceo)
        # 1. Student enrolled 2026-10-15, pays 1 month
        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Timur',
            last_name='Bek',
            phone='909998877',
            status=Student.Status.STUDYING,
            trial_date='2026-10-15',
        )
        Payment.objects.create(
            company=self.company,
            student_name=student.full_name,
            amount=500000,
        )
        # Next payment was 2026-11-15
        res = self.client.get(f'/v1/students/{student.id}')
        self.assertEqual(res.json()['data']['next_payment_date'], '2026-11-15')
        self.assertEqual(res.json()['data']['paid_count'], 1)

        # 2. Student goes to FROZEN on Nov 15
        self.client.patch(f'/v1/students/{student.id}', {'status': Student.Status.FROZEN})
        student.refresh_from_db()
        self.assertEqual(student.status, Student.Status.FROZEN)

        # 3. Student returns from freeze on 2026-12-05 with new anchor date
        patch_res = self.client.patch(f'/v1/students/{student.id}', {
            'status': Student.Status.STUDYING,
            'trial_date': '2026-12-05',
        })
        self.assertEqual(patch_res.status_code, 200)
        data = patch_res.json()['data']
        self.assertEqual(data['status'], Student.Status.STUDYING)
        self.assertEqual(data['trial_date'], '2026-12-05')
        self.assertEqual(data['payment_offset'], 1)
        self.assertEqual(data['paid_count'], 0)  # 0 new payments for the new period
        self.assertEqual(data['next_payment_date'], '2026-12-05')  # due on new start date

        # 4. Student pays for the new period
        Payment.objects.create(
            company=self.company,
            student_name=student.full_name,
            amount=500000,
        )
        res_after_pay = self.client.get(f'/v1/students/{student.id}')
        data_after = res_after_pay.json()['data']
        self.assertEqual(data_after['paid_count'], 1)
        self.assertEqual(data_after['next_payment_date'], '2027-01-05')


class SubscriptionBillingAndCategoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Billing Company', subdomain='billtest')
        self.branch = Branch.objects.create(company=self.company, name='Billing Branch')
        self.ceo = User.objects.create_user(
            phone='998905555555',
            password='password123',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )

    def test_payment_with_months_covered_and_paid_this_month(self):
        self.client.force_authenticate(user=self.ceo)
        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Dilshod',
            last_name='Ergashev',
            phone='901110022',
            status=Student.Status.STUDYING,
            trial_date='2026-05-10',
            paid_this_month=False,
        )

        # Make payment with months_covered=2 via replenishments endpoint
        res = self.client.post('/v1/replenishments', {
            'student_id': student.id,
            'amount': 1000000,
            'months_covered': 2,
            'method': 'cash',
            'comment': 'Paid for 2 months',
        })
        self.assertEqual(res.status_code, 201)
        pdata = res.json()['data']
        self.assertEqual(pdata['student_id'], student.id)
        self.assertEqual(pdata['months_covered'], 2)

        # Check student paid_this_month
        student.refresh_from_db()
        self.assertTrue(student.paid_this_month)

        # Check student next_payment_date advances by 2 months (from 2026-05-10 to 2026-07-10)
        sres = self.client.get(f'/v1/students/{student.id}')
        sdata = sres.json()['data']
        self.assertEqual(sdata['next_payment_date'], '2026-07-10')
        self.assertEqual(sdata['paid_count'], 2)

        # Test GET /v1/students/<id>/payments endpoint
        pres = self.client.get(f'/v1/students/{student.id}/payments')
        self.assertEqual(pres.status_code, 200)
        payments_list = pres.json()['data']
        self.assertEqual(len(payments_list), 1)
        self.assertEqual(payments_list[0]['amount'], 1000000)
        self.assertEqual(payments_list[0]['months_covered'], 2)

    def test_expense_categories_crud(self):
        self.client.force_authenticate(user=self.ceo)
        # Create category
        create_res = self.client.post('/v1/expense_types', {'name': 'Office Supplies'})
        self.assertEqual(create_res.status_code, 201)
        cat_id = create_res.json()['data']['id']
        self.assertEqual(create_res.json()['data']['name'], 'Office Supplies')

        # List categories
        list_res = self.client.get('/v1/expense_types')
        self.assertEqual(list_res.status_code, 200)
        names = [c['name'] for c in list_res.json()['data']]
        self.assertIn('Office Supplies', names)

        # Update category
        patch_res = self.client.patch(f'/v1/expense_types/{cat_id}', {'name': 'Office Rent'})
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()['data']['name'], 'Office Rent')

        # Delete category
        del_res = self.client.delete(f'/v1/expense_types/{cat_id}')
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json()['data']['deleted'])

    def test_pnl_report(self):
        self.client.force_authenticate(user=self.ceo)
        # Create payment
        Payment.objects.create(
            company=self.company,
            student_name='John Doe',
            amount=500000,
            method='cash',
            created_by=self.ceo,
        )
        # Create expense
        from finance.models import Expense, ExpenseCategory
        cat = ExpenseCategory.objects.create(company=self.company, name='Rent')
        Expense.objects.create(
            company=self.company,
            category=cat,
            description='Room rent',
            amount=200000,
            method='cash',
            created_by=self.ceo,
        )

        res = self.client.get('/v1/reports/pnl')
        self.assertEqual(res.status_code, 200)
        data = res.json()['data']
        summary = data['summary']
        self.assertEqual(summary['total_revenue'], 500000)
        self.assertEqual(summary['total_expenses'], 200000)
        self.assertEqual(summary['net_profit'], 300000)
        self.assertEqual(summary['profit_margin'], 60.0)
        self.assertEqual(len(data['revenue_by_method']), 3)
        self.assertEqual(len(data['expense_by_category']), 1)
        self.assertEqual(data['expense_by_category'][0]['name'], 'Rent')

    def test_payroll_calculation_and_pay(self):
        self.client.force_authenticate(user=self.ceo)
        teacher = User.objects.create_user(
            phone='998909998877',
            password='password123',
            first_name='Aziz',
            last_name='Karimov',
            company=self.company,
            user_type=User.UserType.TEACHER,
        )
        from finance.models import SalarySetting
        SalarySetting.objects.create(
            company=self.company,
            teacher_name=teacher.display_name(),
            salary_type=SalarySetting.SalaryType.FIXED,
            amount=3000000,
            created_by=self.ceo,
            updated_by=self.ceo,
        )

        # Get payroll summary
        res = self.client.get('/v1/finance/payroll')
        self.assertEqual(res.status_code, 200)
        pdata = res.json()['data']
        self.assertEqual(pdata['summary']['total_accrued'], 3000000)
        self.assertEqual(pdata['summary']['total_paid'], 0)
        self.assertEqual(pdata['summary']['total_balance'], 3000000)
        teacher_row = next(r for r in pdata['rows'] if r['teacher_id'] == teacher.id)
        self.assertEqual(teacher_row['accrued'], 3000000)
        self.assertEqual(teacher_row['balance'], 3000000)
        self.assertEqual(teacher_row['status'], 'unpaid')

        # Pay 1 000 000 UZS
        pay_res = self.client.post('/v1/finance/payroll/pay', {
            'teacher_id': teacher.id,
            'amount': 1000000,
            'method': 'cash',
            'comment': 'Advance payment',
        })
        self.assertEqual(pay_res.status_code, 201)

        # Check payroll summary after pay
        res2 = self.client.get('/v1/finance/payroll')
        pdata2 = res2.json()['data']
        teacher_row2 = next(r for r in pdata2['rows'] if r['teacher_id'] == teacher.id)
        self.assertEqual(teacher_row2['accrued'], 3000000)
        self.assertEqual(teacher_row2['paid'], 1000000)
        self.assertEqual(teacher_row2['balance'], 2000000)
        self.assertEqual(teacher_row2['status'], 'partial')

    def test_payment_gateways_and_links(self):
        self.client.force_authenticate(user=self.ceo)
        self.company.click_service_id = '11223'
        self.company.click_merchant_id = '33445'
        self.company.payme_merchant_id = 'payme_center_1'
        self.company.save()

        from crm.models import Course, Group
        course = Course.objects.create(company=self.company, name='IELTS', price=600000)
        group = Group.objects.create(company=self.company, branch=self.branch, course=course, name='IELTS-1')
        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            group=group,
            first_name='Anvar',
            last_name='Toshmatov',
            phone='998901234455',
            parent_telegram='998901234455',
        )

        res = self.client.get(f'/v1/students/{student.id}/payment-links')
        self.assertEqual(res.status_code, 200)
        data = res.json()['data']
        self.assertEqual(data['amount'], 600000)
        self.assertTrue(data['click']['configured'])
        self.assertIn('service_id=11223', data['click']['url'])
        self.assertIn(f'transaction_param={student.id}', data['click']['url'])
        self.assertTrue(data['payme']['configured'])
        self.assertTrue(data['payme']['url'].startswith('https://checkout.paycom.uz/'))

        # Test sending payment link via Telegram (mocked)
        from unittest.mock import patch
        mock_cfg = {'enabled': True, 'bot_token': '12345:test_token'}
        with patch('operations.notify.load_config', return_value=mock_cfg):
            with patch('operations.notify.telegram_call', return_value=(True, {'message_id': 101})) as mock_tg:
                send_res = self.client.post(f'/v1/students/{student.id}/send-payment-link', {'amount': 600000})
                self.assertEqual(send_res.status_code, 200)
                self.assertTrue(send_res.json()['data']['sent'])
                mock_tg.assert_called_once()

    def test_click_webhook_prepare_and_complete(self):
        self.company.click_service_id = '5001'
        self.company.click_secret_key = 'testsecret'
        self.company.save()

        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Bobur',
            last_name='Nazarov',
            phone='909990011',
            status=Student.Status.STUDYING,
            trial_date='2026-06-01',
        )

        import hashlib
        # 1. Prepare (action=0)
        click_trans_id = '999888'
        amount = '500000'
        sign_time = '2026-06-01 12:00:00'
        sign_str = f"{click_trans_id}5001testsecret{student.id}{amount}0{sign_time}"
        sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()

        prep_res = self.client.post('/v1/payments/click/webhook', {
            'click_trans_id': click_trans_id,
            'service_id': '5001',
            'merchant_trans_id': str(student.id),
            'amount': amount,
            'action': '0',
            'sign_time': sign_time,
            'sign_string': sign,
        })
        self.assertEqual(prep_res.status_code, 200)
        prep_data = prep_res.json()
        self.assertEqual(prep_data['error'], 0)
        prepare_id = prep_data['merchant_prepare_id']

        # 2. Complete (action=1)
        complete_sign_str = f"{click_trans_id}5001testsecret{student.id}{prepare_id}{amount}1{sign_time}"
        complete_sign = hashlib.md5(complete_sign_str.encode('utf-8')).hexdigest()

        from unittest.mock import patch
        with patch('operations.notify.telegram_call', return_value=(True, {})):
            comp_res = self.client.post('/v1/payments/click/webhook', {
                'click_trans_id': click_trans_id,
                'service_id': '5001',
                'merchant_trans_id': str(student.id),
                'merchant_prepare_id': str(prepare_id),
                'amount': amount,
                'action': '1',
                'sign_time': sign_time,
                'sign_string': complete_sign,
            })
        self.assertEqual(comp_res.status_code, 200)
        comp_data = comp_res.json()
        self.assertEqual(comp_data['error'], 0)

        # Assert payment was created and next_payment_date shifted
        payment = Payment.objects.filter(student=student).first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.amount, 500000)
        self.assertEqual(payment.months_covered, 1)

        student.refresh_from_db()
        self.assertTrue(student.paid_this_month)
        self.client.force_authenticate(user=self.ceo)
        sres = self.client.get(f'/v1/students/{student.id}')
        self.assertEqual(sres.json()['data']['next_payment_date'], '2026-07-01')

    def test_payme_webhook_lifecycle(self):
        import base64
        import json
        self.company.payme_merchant_id = 'payme_id_1'
        self.company.payme_secret_key = 'sec_key_123'
        self.company.save()

        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Malika',
            last_name='Usmanova',
            phone='909990022',
            status=Student.Status.STUDYING,
            trial_date='2026-04-15',
        )

        auth_header = 'Basic ' + base64.b64encode(b'Paycom:sec_key_123').decode('utf-8')

        # 1. CheckPerformTransaction
        res1 = self.client.post(
            '/v1/payments/payme/webhook',
            data=json.dumps({
                'id': 1,
                'method': 'CheckPerformTransaction',
                'params': {
                    'amount': 40000000,  # 400,000 UZS in tiyin
                    'account': {'student_id': student.id},
                },
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=auth_header,
        )
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.json()['result']['allow'])

        # 2. CreateTransaction
        res2 = self.client.post(
            '/v1/payments/payme/webhook',
            data=json.dumps({
                'id': 2,
                'method': 'CreateTransaction',
                'params': {
                    'id': 'payme_trans_777',
                    'time': 1715000000000,
                    'amount': 40000000,
                    'account': {'student_id': student.id},
                },
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=auth_header,
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()['result']['state'], 1)

        # 3. PerformTransaction
        from unittest.mock import patch
        with patch('operations.notify.telegram_call', return_value=(True, {})):
            res3 = self.client.post(
                '/v1/payments/payme/webhook',
                data=json.dumps({
                    'id': 3,
                    'method': 'PerformTransaction',
                    'params': {'id': 'payme_trans_777'},
                }),
                content_type='application/json',
                HTTP_AUTHORIZATION=auth_header,
            )
        self.assertEqual(res3.status_code, 200)
        self.assertEqual(res3.json()['result']['state'], 2)

        # Verify payment created
        p = Payment.objects.filter(student=student, amount=400000).first()
        self.assertIsNotNone(p)
        self.assertIn('Payme', p.comment)

        student.refresh_from_db()
        self.assertTrue(student.paid_this_month)
        self.client.force_authenticate(user=self.ceo)
        sres = self.client.get(f'/v1/students/{student.id}')
        self.assertEqual(sres.json()['data']['next_payment_date'], '2026-05-15')

    def test_leads_school_duplicate_prevention_and_auto_linking(self):
        self.client.force_authenticate(user=self.ceo)

        # 1. Create lead with school
        res = self.client.post('/v1/leads', {
            'first_name': 'Азиз',
            'last_name': 'Каримов',
            'phone': '909991122',
            'school': 'Школа № 178',
            'trial_date': '2026-09-20',
        })
        self.assertEqual(res.status_code, 201)
        lead_data = res.json()['data']
        lead_id = lead_data['id']
        self.assertEqual(lead_data['school'], 'Школа № 178')

        # 2. Convert lead to student and verify school is transferred
        c_res = self.client.post(f'/v1/leads/{lead_id}/convert', {
            'branch_id': self.branch.id,
            'trial_date': '2026-09-20',
        })
        self.assertEqual(c_res.status_code, 201)
        student_data = c_res.json()['data']['student']
        self.assertEqual(student_data['school'], 'Школа № 178')

        # 3. Attempt duplicate conversion -> must fail with 400
        c_dup = self.client.post(f'/v1/leads/{lead_id}/convert', {
            'branch_id': self.branch.id,
            'trial_date': '2026-09-20',
        })
        self.assertEqual(c_dup.status_code, 400)
        self.assertIn('уже зачислен как студент', c_dup.json()['message'])

        # 4. Check serialized lead has converted_student_id
        lead_get = self.client.get(f'/v1/leads/{lead_id}')
        self.assertEqual(lead_get.json()['data']['converted_student_id'], student_data['id'])

        # 5. Direct student creation links existing lead instead of deleting it
        l2_res = self.client.post('/v1/leads', {
            'first_name': 'Дильноза',
            'phone': '908887766',
            'school': 'Гимназия № 5',
            'trial_date': '2026-09-21',
        })
        l2_id = l2_res.json()['data']['id']

        s_direct = self.client.post('/v1/students', {
            'first_name': 'Дильноза',
            'phone': '908887766',
            'trial_date': '2026-09-21',
            'branch_id': self.branch.id,
        })
        self.assertEqual(s_direct.status_code, 201)
        created_student_id = s_direct.json()['data']['id']

        # Lead should still exist, with stage = CONVERTED
        lead2 = Lead.objects.filter(pk=l2_id).first()
        self.assertIsNotNone(lead2)
        self.assertEqual(lead2.stage, Lead.Stage.CONVERTED)
        student2 = Student.objects.get(pk=created_student_id)
        self.assertEqual(student2.lead_id, l2_id)

        # 6. Dashboard active_leads counts only pipeline leads (TRIAL_BOOKED, ATTENDED)
        # Create an active lead in pipeline
        self.client.post('/v1/leads', {
            'first_name': 'Активный',
            'phone': '901110099',
            'stage': 'trial_booked',
            'trial_date': '2026-09-22',
        })
        dash_res = self.client.get('/v1/dashboard')
        self.assertEqual(dash_res.status_code, 200)
        # Both converted leads (lead_id and l2_id) must NOT be in active_leads!
        self.assertEqual(dash_res.json()['data']['active_leads'], 1)


class CoreAuditedFeaturesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Audit Academy', subdomain='audit')
        self.branch = Branch.objects.create(company=self.company, name='Main Branch')
        self.course = Course.objects.create(company=self.company, name='English', price=500000)
        self.group = Group.objects.create(company=self.company, branch=self.branch, course=self.course, name='Group A')

        self.ceo = User.objects.create_user(
            phone='998901110001',
            password='password123',
            first_name='Chief',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )
        self.admin = User.objects.create_user(
            phone='998901110002',
            password='password123',
            first_name='Admin',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.ADMINISTRATOR,
        )

    def test_payment_isolation_between_namesakes(self):
        """Payment of Aziz Karimov #1 must NEVER be counted for Aziz Karimov #2."""
        self.client.force_authenticate(user=self.admin)
        s1 = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Aziz',
            last_name='Karimov',
            phone='901234567',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )
        s2 = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Aziz',
            last_name='Karimov',
            phone='907654321',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )
        Payment.objects.create(
            company=self.company,
            student=s1,
            student_name='Aziz Karimov',
            amount=500000,
            months_covered=2,
            method=Payment.Method.CASH,
        )

        res = self.client.get('/v1/students')
        self.assertEqual(res.status_code, 200)
        results = {r['id']: r for r in res.json()['data']['results']}

        self.assertEqual(results[s1.id]['paid_count'], 2)
        self.assertEqual(results[s2.id]['paid_count'], 0)

        p_res = self.client.get(f'/v1/students/{s2.id}/payments')
        self.assertEqual(p_res.status_code, 200)
        self.assertEqual(len(p_res.json()['data']), 0)

        p1_res = self.client.get(f'/v1/students/{s1.id}/payments')
        self.assertEqual(p1_res.status_code, 200)
        self.assertEqual(len(p1_res.json()['data']), 1)

    def test_student_soft_delete_preserves_attendance_and_scores(self):
        """Soft delete changes status to LEFT and preserves AttendanceRecord and StudentScore."""
        self.client.force_authenticate(user=self.admin)
        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            group=self.group,
            first_name='Test',
            last_name='Student',
            phone='901112233',
            status=Student.Status.STUDYING,
        )
        att = AttendanceRecord.objects.create(
            company=self.company,
            group=self.group,
            student=student,
            attend_date='2026-09-10',
            status=AttendanceRecord.Status.PRESENT,
        )
        score = StudentScore.objects.create(
            company=self.company,
            group=self.group,
            student=student,
            grade=95,
        )

        del_res = self.client.delete(f'/v1/students/{student.id}')
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json()['data']['archived'])

        student.refresh_from_db()
        self.assertEqual(student.status, Student.Status.LEFT)
        self.assertIsNotNone(student.left_at)
        self.assertIsNone(student.group)
        self.assertTrue(AttendanceRecord.objects.filter(pk=att.pk).exists())
        self.assertTrue(StudentScore.objects.filter(pk=score.pk).exists())

        hard_res = self.client.delete(f'/v1/students/{student.id}?hard=1')
        self.assertEqual(hard_res.status_code, 403)

        self.client.force_authenticate(user=self.ceo)
        ceo_hard = self.client.delete(f'/v1/students/{student.id}?hard=1')
        self.assertEqual(ceo_hard.status_code, 200)
        self.assertFalse(Student.objects.filter(pk=student.pk).exists())

    def test_brothers_safe_lead_student_matching(self):
        """Matching by phone variants must verify last_name to prevent wrong conversion."""
        self.client.force_authenticate(user=self.admin)
        l1 = Lead.objects.create(
            company=self.company,
            first_name='Muhammad',
            last_name='Karimov',
            phone='905554433',
            stage=Lead.Stage.TRIAL_BOOKED,
        )

        res = self.client.post('/v1/students', {
            'branch_id': self.branch.id,
            'first_name': 'Muhammad',
            'last_name': 'Rakhimov',
            'phone': '905554433',
            'trial_date': '2026-09-20',
        })
        self.assertEqual(res.status_code, 201)
        l1.refresh_from_db()
        self.assertEqual(l1.stage, Lead.Stage.TRIAL_BOOKED)

        res2 = self.client.post('/v1/students', {
            'branch_id': self.branch.id,
            'first_name': 'Muhammad',
            'last_name': 'Karimov',
            'phone': '905554433',
            'trial_date': '2026-09-20',
        })
        self.assertEqual(res2.status_code, 201)
        l1.refresh_from_db()
        self.assertEqual(l1.stage, Lead.Stage.CONVERTED)

    def test_phone_validation_standardization(self):
        """Standardized phone validation rejects length != 9 and accepts valid 9 digits."""
        self.client.force_authenticate(user=self.admin)

        # 1. Student create with 8 digits
        res = self.client.post('/v1/students', {
            'branch_id': self.branch.id,
            'first_name': 'Ali',
            'last_name': 'Valiyev',
            'phone': '90123456',
            'trial_date': '2026-09-20',
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('9 digits', res.json().get('message', ''))

        # 2. Student create with 10 digits
        res = self.client.post('/v1/students', {
            'branch_id': self.branch.id,
            'first_name': 'Ali',
            'last_name': 'Valiyev',
            'phone': '9012345678',
            'trial_date': '2026-09-20',
        })
        self.assertEqual(res.status_code, 400)

        # 3. Lead create with 10 digits
        res = self.client.post('/v1/leads', {
            'first_name': 'Vali',
            'last_name': 'Aliyev',
            'phone': '9012345678',
        })
        self.assertEqual(res.status_code, 400)

        # 4. Valid lead create (+998 prefix normalized to 9 digits)
        res = self.client.post('/v1/leads', {
            'first_name': 'Vali',
            'last_name': 'Aliyev',
            'phone': '+998901234567',
        })
        self.assertEqual(res.status_code, 201)
        lead_id = res.json()['data']['id']

        # 5. Lead patch with invalid phone
        patch_res = self.client.patch(f'/v1/leads/{lead_id}', {
            'phone': '12345',
        })
        self.assertEqual(patch_res.status_code, 400)

    def test_paid_this_month_lifecycle_sync(self):
        """Creating/deleting payments should immediately update student.paid_this_month."""
        self.client.force_authenticate(user=self.admin)
        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Dilshod',
            last_name='Nazarov',
            phone='909998877',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
            paid_this_month=False,
        )
        self.assertFalse(student.paid_this_month)

        # Create payment via replenishments endpoint
        res = self.client.post('/v1/replenishments', {
            'student_id': student.id,
            'amount': 350000,
            'method': Payment.Method.CASH,
        })
        self.assertEqual(res.status_code, 201)
        payment_id = res.json()['data']['id']

        student.refresh_from_db()
        self.assertTrue(student.paid_this_month)

        # Delete payment
        del_res = self.client.delete(f'/v1/replenishments/{payment_id}')
        self.assertEqual(del_res.status_code, 200)

        student.refresh_from_db()
        self.assertFalse(student.paid_this_month)

    def test_report_pagination_safe_offset(self):
        """Negative or zero page query parameter must not throw negative offset error."""
        self.client.force_authenticate(user=self.admin)
        res_conv = self.client.get('/v1/reports/conversion?page=-5')
        self.assertEqual(res_conv.status_code, 200)
        self.assertEqual(res_conv.json()['data']['page'], 1)

        res_leads = self.client.get('/v1/reports/leads?page=0')
        self.assertEqual(res_leads.status_code, 200)
        self.assertEqual(res_leads.json()['data']['page'], 1)

        res_att = self.client.get('/v1/reports/attendance?page=-1')
        self.assertEqual(res_att.status_code, 200)
        self.assertEqual(res_att.json()['data']['page'], 1)

    def test_report_conversion_archived_leads_and_filtering(self):
        """Conversion report should include archived leads by default and respect is_active filter."""
        self.client.force_authenticate(user=self.admin)
        active_lead = Lead.objects.create(
            company=self.company,
            first_name='Active',
            last_name='Lead',
            phone='901110021',
            stage=Lead.Stage.CONVERTED,
            is_active=True,
        )
        archived_lead = Lead.objects.create(
            company=self.company,
            first_name='Archived',
            last_name='Lead',
            phone='901110022',
            stage=Lead.Stage.CONVERTED,
            is_active=False,
        )

        # Default includes both
        res_all = self.client.get('/v1/reports/conversion')
        self.assertEqual(res_all.status_code, 200)
        row_ids = [r['id'] for r in res_all.json()['data']['rows']]
        self.assertIn(active_lead.id, row_ids)
        self.assertIn(archived_lead.id, row_ids)

        # Only active
        res_act = self.client.get('/v1/reports/conversion?is_active=true')
        self.assertEqual(res_act.status_code, 200)
        act_row_ids = [r['id'] for r in res_act.json()['data']['rows']]
        self.assertIn(active_lead.id, act_row_ids)
        self.assertNotIn(archived_lead.id, act_row_ids)

        # Only archived
        res_arc = self.client.get('/v1/reports/conversion?is_active=false')
        self.assertEqual(res_arc.status_code, 200)
        arc_row_ids = [r['id'] for r in res_arc.json()['data']['rows']]
        self.assertNotIn(active_lead.id, arc_row_ids)
        self.assertIn(archived_lead.id, arc_row_ids)


class P0RegressionTests(TestCase):
    """Regression tests for P0 critical fixes."""

    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='P0 Company', subdomain='p0test')
        self.branch = Branch.objects.create(company=self.company, name='P0 Branch')
        self.ceo = User.objects.create_user(
            phone='998901110000',
            password='password123',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )

    def test_unfreeze_payment_offset_uses_months_covered_not_count(self):
        """
        P0-1: If student has 1 Payment with months_covered=3, unfreeze must set
        payment_offset=3 (not 1). Otherwise the student gets free months.
        """
        self.client.force_authenticate(user=self.ceo)
        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Kamol',
            last_name='Rakhimov',
            phone='901112233',
            status=Student.Status.STUDYING,
            trial_date='2026-06-01',
        )
        # One payment covering 3 months
        Payment.objects.create(
            company=self.company,
            student=student,
            student_name=student.full_name,
            amount=1500000,
            months_covered=3,
        )

        # Verify initial billing: 3 months covered
        res = self.client.get(f'/v1/students/{student.id}')
        self.assertEqual(res.json()['data']['paid_count'], 3)
        self.assertEqual(res.json()['data']['next_payment_date'], '2026-09-01')

        # Freeze
        self.client.patch(f'/v1/students/{student.id}', {'status': Student.Status.FROZEN})
        student.refresh_from_db()
        self.assertEqual(student.status, Student.Status.FROZEN)

        # Unfreeze
        patch_res = self.client.patch(f'/v1/students/{student.id}', {
            'status': Student.Status.STUDYING,
            'trial_date': '2026-10-01',
        })
        self.assertEqual(patch_res.status_code, 200)
        data = patch_res.json()['data']

        # payment_offset must be 3 (Sum of months_covered), NOT 1 (.count())
        self.assertEqual(data['payment_offset'], 3)
        # paid_count = months_covered(3) - offset(3) = 0 new payments in new period
        self.assertEqual(data['paid_count'], 0)
        # Next due is the new anchor
        self.assertEqual(data['next_payment_date'], '2026-10-01')

    def test_paid_this_month_cannot_be_set_via_patch(self):
        """
        P0-2: PATCH /v1/students/<id> must NOT allow manual override of paid_this_month.
        The field must only reflect actual Payment records.
        """
        self.client.force_authenticate(user=self.ceo)
        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Nodir',
            last_name='Aliyev',
            phone='901223344',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
            paid_this_month=False,
        )
        self.assertFalse(student.paid_this_month)

        # Try to manually set paid_this_month=True via PATCH (no actual Payment exists)
        patch_res = self.client.patch(f'/v1/students/{student.id}', {
            'paid_this_month': True,
        })
        self.assertEqual(patch_res.status_code, 200)

        # Field must remain False — no Payment record exists
        student.refresh_from_db()
        self.assertFalse(student.paid_this_month)

    def test_student_creation_links_lead_only_after_save(self):
        """
        P0-3: When creating a Student that matches a Lead, the Lead must only be
        marked CONVERTED after the Student is successfully saved. Also verify that
        family enrichment (school, address) works correctly.
        """
        self.client.force_authenticate(user=self.ceo)

        # Create a lead with school and address
        lead = Lead.objects.create(
            company=self.company,
            first_name='Sardor',
            last_name='Tursunov',
            phone='901334455',
            school='School #42',
            address='Tashkent, Mirzo Ulugbek',
            stage=Lead.Stage.TRIAL_BOOKED,
        )
        self.assertEqual(lead.stage, Lead.Stage.TRIAL_BOOKED)

        # Create student with matching phone and name
        res = self.client.post('/v1/students', {
            'first_name': 'Sardor',
            'last_name': 'Tursunov',
            'phone': '901334455',
            'branch_id': self.branch.id,
            'trial_date': '2026-09-20',
        })
        self.assertEqual(res.status_code, 201)
        student_data = res.json()['data']

        # Student must be linked to lead
        student = Student.objects.get(pk=student_data['id'])
        self.assertEqual(student.lead_id, lead.id)

        # Lead must now be CONVERTED
        lead.refresh_from_db()
        self.assertEqual(lead.stage, Lead.Stage.CONVERTED)

    def test_student_creation_enriches_from_family_lead(self):
        """
        P0-3 (family): When creating a Student whose phone matches a Lead but name
        doesn't (sibling), family fields should be copied.
        """
        self.client.force_authenticate(user=self.ceo)

        # Create a lead for the older sibling
        Lead.objects.create(
            company=self.company,
            first_name='Aziza',
            last_name='Karimova',
            phone='901445566',
            school='Lyceum #7',
            address='Samarkand',
            phone2='901999888',
            phone2_owner='Father',
            stage=Lead.Stage.ATTENDED,
        )

        # Create student — same phone, different name (younger sibling)
        res = self.client.post('/v1/students', {
            'first_name': 'Bobur',
            'last_name': 'Karimov',
            'phone': '901445566',
            'branch_id': self.branch.id,
            'trial_date': '2026-09-20',
        })
        self.assertEqual(res.status_code, 201)
        student = Student.objects.get(pk=res.json()['data']['id'])

        # Family fields should be copied from lead
        self.assertEqual(student.school, 'Lyceum #7')
        self.assertEqual(student.address, 'Samarkand')
        self.assertEqual(student.phone2, '901999888')
        self.assertEqual(student.phone2_owner, 'Father')

        # But student.lead should NOT be set (name mismatch)
        self.assertIsNone(student.lead)

    def test_unfreeze_via_unfreeze_key_uses_months_covered(self):
        """
        P0-1 (second path): Unfreeze via data['unfreeze'] key must also use
        Sum('months_covered'), not .count().
        """
        self.client.force_authenticate(user=self.ceo)
        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Sherzod',
            last_name='Baymatov',
            phone='901556677',
            status=Student.Status.FROZEN,
            trial_date='2026-07-01',
        )
        # 2 payments: one covering 2 months, one covering 1 month = total 3
        Payment.objects.create(
            company=self.company,
            student=student,
            student_name=student.full_name,
            amount=1000000,
            months_covered=2,
        )
        Payment.objects.create(
            company=self.company,
            student=student,
            student_name=student.full_name,
            amount=500000,
            months_covered=1,
        )

        # Unfreeze via 'unfreeze' key
        patch_res = self.client.patch(f'/v1/students/{student.id}', {
            'unfreeze': True,
        })
        self.assertEqual(patch_res.status_code, 200)
        data = patch_res.json()['data']

        # payment_offset must be 3 (Sum), not 2 (.count())
        self.assertEqual(data['payment_offset'], 3)
        self.assertEqual(data['status'], Student.Status.STUDYING)


class DuplicatePolicyTests(TestCase):
    """Tests for duplicate prevention vs brothers/family allowance."""

    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Dup Company', subdomain='duptest')
        self.branch = Branch.objects.create(company=self.company, name='Main Branch')
        self.ceo = User.objects.create_user(
            phone='998901119999',
            password='password123',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )
        self.client.force_authenticate(user=self.ceo)

    def test_exact_duplicate_student_is_rejected(self):
        """Creating an exact duplicate student (same name, same phone) must return 400."""
        res1 = self.client.post('/v1/students', {
            'branch_id': self.branch.id,
            'first_name': 'thesame',
            'last_name': 'thesame',
            'phone': '999999999',
            'trial_date': '2026-09-20',
        })
        self.assertEqual(res1.status_code, 201)

        # Attempt to create identical student
        res2 = self.client.post('/v1/students', {
            'branch_id': self.branch.id,
            'first_name': 'thesame',
            'last_name': 'thesame',
            'phone': '999999999',
            'trial_date': '2026-09-20',
        })
        self.assertEqual(res2.status_code, 400)
        self.assertIn('уже существует', res2.json()['message'])

    def test_brothers_with_same_phone_are_allowed(self):
        """Brothers (same phone, different first_name) must be allowed and not blocked."""
        # Brother 1
        res1 = self.client.post('/v1/students', {
            'branch_id': self.branch.id,
            'first_name': 'Aziz',
            'last_name': 'Karimov',
            'phone': '999999999',
            'trial_date': '2026-09-20',
        })
        self.assertEqual(res1.status_code, 201)

        # Brother 2 (same family phone, different first_name)
        res2 = self.client.post('/v1/students', {
            'branch_id': self.branch.id,
            'first_name': 'Bobur',
            'last_name': 'Karimov',
            'phone': '999999999',
            'trial_date': '2026-09-20',
        })
        self.assertEqual(res2.status_code, 201)
        self.assertNotEqual(res1.json()['data']['id'], res2.json()['data']['id'])

    def test_exact_duplicate_lead_is_rejected(self):
        """Creating an exact duplicate lead (same name, same phone) must return 400."""
        res1 = self.client.post('/v1/leads', {
            'first_name': 'Alisher',
            'last_name': 'Navoiy',
            'phone': '901234567',
        })
        self.assertEqual(res1.status_code, 201)

        # Exact duplicate lead
        res2 = self.client.post('/v1/leads', {
            'first_name': 'Alisher',
            'last_name': 'Navoiy',
            'phone': '901234567',
        })
        self.assertEqual(res2.status_code, 400)
        self.assertIn('уже находится в воронке', res2.json()['message'])

    def test_lead_for_already_studying_student_is_rejected(self):
        """Creating a lead for someone who is already an active student must return 400."""
        Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Jasur',
            last_name='Umarov',
            phone='907654321',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )

        res = self.client.post('/v1/leads', {
            'first_name': 'Jasur',
            'last_name': 'Umarov',
            'phone': '907654321',
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('уже является активным учеником', res.json()['message'])

    def test_patch_student_to_duplicate_another_is_rejected(self):
        """Editing Student B to have identical name and phone as Student A must be rejected."""
        s1 = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Existing',
            last_name='Student',
            phone='901111111',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )
        s2 = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Another',
            last_name='Person',
            phone='902222222',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )

        # Attempt to edit s2 to duplicate s1
        patch_res = self.client.patch(f'/v1/students/{s2.id}', {
            'first_name': 'Existing',
            'last_name': 'Student',
            'phone': '901111111',
        })
        self.assertEqual(patch_res.status_code, 400)
        self.assertIn('уже существует', patch_res.json()['message'])

    def test_brother_enriches_family_info_from_studying_student(self):
        """Brother 2 must automatically inherit school, address, phone2 from Brother 1 who is already studying."""
        # Brother 1 created with family data
        Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Akmal',
            last_name='Yusupov',
            phone='903333333',
            school='Lyceum #1',
            address='Tashkent, Chilonzor',
            phone2='908888888',
            phone2_owner='Father',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )

        # Brother 2 created with same family phone, but different first_name, without entering school/address
        res = self.client.post('/v1/students', {
            'branch_id': self.branch.id,
            'first_name': 'Anvar',
            'last_name': 'Yusupov',
            'phone': '903333333',
            'trial_date': '2026-09-20',
        })
        self.assertEqual(res.status_code, 201)
        b2 = Student.objects.get(pk=res.json()['data']['id'])

        # Family data automatically inherited from Brother 1!
        self.assertEqual(b2.school, 'Lyceum #1')
        self.assertEqual(b2.address, 'Tashkent, Chilonzor')
        self.assertEqual(b2.phone2, '908888888')
        self.assertEqual(b2.phone2_owner, 'Father')


class P1RegressionTests(TestCase):
    """Regression tests for P1: Import trial_date/status modernization and legacy payment namesake isolation."""

    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='P1 Company', subdomain='p1test')
        self.branch = Branch.objects.create(company=self.company, name='P1 Branch')
        self.ceo = User.objects.create_user(
            phone='998901118888',
            password='password123',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )
        self.client.force_authenticate(user=self.ceo)

    def test_csv_import_trial_date_and_status_modernization(self):
        """
        P1-1 & P1-2:
        CSV import must properly parse trial_date (with fallback to today)
        and map old status synonyms (active, debtor, trial) into STUDYING with 'Обучается' label.
        """
        import io
        csv_content = (
            "name,phone,status,trial_date\n"
            "Vali Tursunov,901112233,активный,2026-08-15\n"
            "Sami Qodirov,902223344,должник,\n"
        )
        f = io.BytesIO(csv_content.encode('utf-8'))
        f.name = 'test_import.csv'

        # Preview mode
        res_preview = self.client.post('/v1/students/import', {'file': f, 'dry_run': 'true'}, format='multipart')
        self.assertEqual(res_preview.status_code, 200)
        rows = res_preview.json()['data']['rows']
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['status_label'], 'Обучается')
        self.assertEqual(rows[0]['trial_date'], '2026-08-15')
        self.assertEqual(rows[1]['status_label'], 'Обучается')  # debtor maps to Обучается, not 'Должник'
        self.assertEqual(rows[1]['trial_date'], timezone.localdate().isoformat())

        # Real import
        f.seek(0)
        res_import = self.client.post('/v1/students/import', {'file': f}, format='multipart')
        self.assertEqual(res_import.status_code, 200)

        s1 = Student.objects.get(company=self.company, phone='901112233')
        self.assertEqual(s1.status, Student.Status.STUDYING)
        self.assertEqual(s1.trial_date.isoformat(), '2026-08-15')

        s2 = Student.objects.get(company=self.company, phone='902223344')
        self.assertEqual(s2.status, Student.Status.STUDYING)
        self.assertEqual(s2.trial_date, timezone.localdate())

    def test_legacy_payment_namesake_protection(self):
        """
        P1-3:
        If multiple students have the exact same name, unlinked legacy payments
        (student IS NULL) must NOT be attributed to either student.
        A student with a unique name DOES get the legacy fallback.
        """
        # Two namesakes
        s1 = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Farrukh',
            last_name='Zokirov',
            phone='903330001',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )
        s2 = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Farrukh',
            last_name='Zokirov',
            phone='903330002',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )

        # Unique student
        s_unique = Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Sardor',
            last_name='Aliyev',
            phone='904440001',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )

        # Legacy payment for the namesake
        Payment.objects.create(
            company=self.company,
            student=None,
            student_name='Farrukh Zokirov',
            amount=500000,
            months_covered=1,
        )

        # Legacy payment for the unique student
        Payment.objects.create(
            company=self.company,
            student=None,
            student_name='Sardor Aliyev',
            amount=500000,
            months_covered=1,
        )

        # Verify: neither namesake gets the ambiguous legacy payment
        res1 = self.client.get(f'/v1/students/{s1.id}')
        self.assertEqual(res1.json()['data']['paid_count'], 0)

        res2 = self.client.get(f'/v1/students/{s2.id}')
        self.assertEqual(res2.json()['data']['paid_count'], 0)

        # Unique student gets the fallback safely
        res_u = self.client.get(f'/v1/students/{s_unique.id}')
        self.assertEqual(res_u.json()['data']['paid_count'], 1)

    def test_replenishment_by_name_rejects_ambiguous_namesakes(self):
        """
        P1-3:
        Creating a payment via /replenishments by name (without student_id)
        must reject with 400 if there are multiple students with that name.
        """
        Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Dilshod',
            last_name='Ergashev',
            phone='905550001',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )
        Student.objects.create(
            company=self.company,
            branch=self.branch,
            first_name='Dilshod',
            last_name='Ergashev',
            phone='905550002',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )

        # Payment by name without student_id
        res = self.client.post('/v1/replenishments', {
            'student_name': 'Dilshod Ergashev',
            'amount': 300000,
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('несколько учеников', res.json()['message'])


class P2RegressionTests(TestCase):
    """Regression tests for P2: Attendance group membership validation and lead student_deleted reflection."""

    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='P2 Company', subdomain='p2test')
        self.branch = Branch.objects.create(company=self.company, name='P2 Branch')
        self.group1 = Group.objects.create(company=self.company, branch=self.branch, name='English Group A')
        self.group2 = Group.objects.create(company=self.company, branch=self.branch, name='Math Group B')
        self.ceo = User.objects.create_user(
            phone='998901117777',
            password='password123',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )
        self.client.force_authenticate(user=self.ceo)

    def test_attendance_validation_rejects_mismatched_group(self):
        """
        P2-1:
        Marking attendance for student in a group they don't belong to must return 400.
        """
        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            group=self.group1,
            first_name='Anvar',
            last_name='Soliyev',
            phone='906661111',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )

        # Attempt to mark attendance in Group 2 (student is in Group 1)
        res_fail = self.client.post('/v1/reports/attendance', {
            'student_id': student.id,
            'group_id': self.group2.id,
            'date': '2026-09-20',
            'status': AttendanceRecord.Status.PRESENT,
        })
        self.assertEqual(res_fail.status_code, 400)
        self.assertIn('does not belong to this group', res_fail.json()['message'])

        # Mark attendance in Group 1 (correct group) -> succeeds
        res_ok = self.client.post('/v1/reports/attendance', {
            'student_id': student.id,
            'group_id': self.group1.id,
            'date': '2026-09-20',
            'status': AttendanceRecord.Status.PRESENT,
        })
        self.assertEqual(res_ok.status_code, 201)

    def test_lead_student_deleted_flag_reflects_soft_delete(self):
        """
        P2-2:
        When a converted student is soft-deleted (status=LEFT),
        the corresponding lead must serialize student_deleted=True and student_is_active=False.
        """
        lead = Lead.objects.create(
            company=self.company,
            first_name='Sherzod',
            last_name='Bekov',
            phone='907771122',
            stage=Lead.Stage.TRIAL_BOOKED,
        )

        # Convert lead to student
        convert_res = self.client.post(f'/v1/leads/{lead.id}/convert', {
            'branch_id': self.branch.id,
            'trial_date': '2026-09-20',
        })
        self.assertEqual(convert_res.status_code, 201)
        lead.refresh_from_db()
        self.assertEqual(lead.stage, Lead.Stage.CONVERTED)

        student = Student.objects.get(lead=lead)
        self.assertEqual(student.status, Student.Status.TRIAL)

        # Before soft delete: student is active
        lead_res1 = self.client.get(f'/v1/leads/{lead.id}')
        self.assertEqual(lead_res1.status_code, 200)
        self.assertFalse(lead_res1.json()['data']['student_deleted'])
        self.assertTrue(lead_res1.json()['data']['student_is_active'])

        # Soft delete the student (status=LEFT)
        del_res = self.client.delete(f'/v1/students/{student.id}')
        self.assertEqual(del_res.status_code, 200)

        # After soft delete: student_deleted must be True
        lead_res2 = self.client.get(f'/v1/leads/{lead.id}')
        self.assertEqual(lead_res2.status_code, 200)
        self.assertTrue(lead_res2.json()['data']['student_deleted'])
        self.assertFalse(lead_res2.json()['data']['student_is_active'])


class Phase1SecurityTests(TestCase):
    def setUp(self):
        import datetime
        self.client = APIClient()
        self.company = Company.objects.create(name='Security Test Co', subdomain='sectest')
        self.branch = Branch.objects.create(company=self.company, name='Sec Branch')

        # Admin user
        self.admin = User.objects.create_user(
            phone='998909990001',
            password='adminpassword123',
            first_name='Admin',
            last_name='User',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.ADMINISTRATOR,
        )

        # Teacher A
        self.teacher_a = User.objects.create_user(
            phone='998909990002',
            password='teacherApassword123',
            first_name='Teacher',
            last_name='Alpha',
            company=self.company,
            user_type=User.UserType.TEACHER,
        )

        # Teacher B
        self.teacher_b = User.objects.create_user(
            phone='998909990003',
            password='teacherBpassword123',
            first_name='Teacher',
            last_name='Beta',
            company=self.company,
            user_type=User.UserType.TEACHER,
        )

        self.course = Course.objects.create(company=self.company, name='English A1')

        # Groups
        self.group_a = Group.objects.create(
            company=self.company,
            branch=self.branch,
            course=self.course,
            teacher=self.teacher_a,
            name='Group Alpha',
        )
        self.group_b = Group.objects.create(
            company=self.company,
            branch=self.branch,
            course=self.course,
            teacher=self.teacher_b,
            name='Group Beta',
        )

        # Students
        self.student_a = Student.objects.create(
            company=self.company,
            branch=self.branch,
            group=self.group_a,
            first_name='Student',
            last_name='Alpha',
            phone='998909991111',
            status=Student.Status.STUDYING,
        )
        self.student_b = Student.objects.create(
            company=self.company,
            branch=self.branch,
            group=self.group_b,
            first_name='Student',
            last_name='Beta',
            phone='998909992222',
            status=Student.Status.STUDYING,
        )

        self.today = timezone.localdate()

    def test_login_backdoor_removal(self):
        """Ensure fallback/backdoor passwords cannot authenticate accounts."""
        # Standard login works
        res_ok = self.client.post('/v1/auth/login', {
            'phone': self.teacher_a.phone,
            'password': 'teacherApassword123',
        })
        self.assertEqual(res_ok.status_code, 200)

        # Backdoors / fallback passwords must all fail with 401
        for bad_pw in ('HiJack2024!', '50608991Zz!', 'demo1234', '946263200', 'wrongpassword'):
            res_fail = self.client.post('/v1/auth/login', {
                'phone': self.teacher_a.phone,
                'password': bad_pw,
            })
            self.assertEqual(res_fail.status_code, 401)

    def test_student_attendance_teacher_scoping(self):
        """Teachers can only view, create, edit attendance for their own groups."""
        import datetime
        # Create attendance record for student A and student B
        rec_a = AttendanceRecord.objects.create(
            company=self.company,
            student=self.student_a,
            group=self.group_a,
            attend_date=self.today,
            status=AttendanceRecord.Status.PRESENT,
        )
        rec_b = AttendanceRecord.objects.create(
            company=self.company,
            student=self.student_b,
            group=self.group_b,
            attend_date=self.today,
            status=AttendanceRecord.Status.PRESENT,
        )

        self.client.force_authenticate(user=self.teacher_a)

        # 1. List attendance - Teacher A only sees rec_a
        list_res = self.client.get('/v1/reports/attendance')
        self.assertEqual(list_res.status_code, 200)
        ids = [row['id'] for row in list_res.json()['data']['rows']]
        self.assertIn(rec_a.id, ids)
        self.assertNotIn(rec_b.id, ids)

        # 2. Filter by group_id of Teacher B's group -> returns empty
        filtered_res = self.client.get(f'/v1/reports/attendance?group_id={self.group_b.id}')
        self.assertEqual(filtered_res.status_code, 200)
        self.assertEqual(len(filtered_res.json()['data']['rows']), 0)

        # 3. Create attendance for Teacher B's group -> 404
        post_foreign = self.client.post('/v1/reports/attendance', {
            'student_id': self.student_b.id,
            'group_id': self.group_b.id,
            'attend_date': self.today.isoformat(),
            'status': AttendanceRecord.Status.PRESENT,
        })
        self.assertEqual(post_foreign.status_code, 404)

        # 4. Detail view / patch / delete on foreign record -> 404
        self.assertEqual(self.client.get(f'/v1/reports/attendance/{rec_b.id}').status_code, 404)
        self.assertEqual(self.client.patch(f'/v1/reports/attendance/{rec_b.id}', {'status': 2}).status_code, 404)
        self.assertEqual(self.client.delete(f'/v1/reports/attendance/{rec_b.id}').status_code, 404)

        # 5. Future date rejected
        tomorrow = self.today + datetime.timedelta(days=1)
        post_future = self.client.post('/v1/reports/attendance', {
            'student_id': self.student_a.id,
            'group_id': self.group_a.id,
            'attend_date': tomorrow.isoformat(),
            'status': AttendanceRecord.Status.PRESENT,
        })
        self.assertEqual(post_future.status_code, 400)

    def test_attendance_detail_membership_invariant(self):
        """AttendanceDetail PATCH cannot break group/student membership."""
        rec_a = AttendanceRecord.objects.create(
            company=self.company,
            student=self.student_a,
            group=self.group_a,
            attend_date=self.today,
            status=AttendanceRecord.Status.PRESENT,
        )

        self.client.force_authenticate(user=self.admin)

        # Try changing student to student_b without changing group -> 400
        patch_res = self.client.patch(f'/v1/reports/attendance/{rec_a.id}', {
            'student_id': self.student_b.id,
        })
        self.assertEqual(patch_res.status_code, 400)
        self.assertIn('Student does not belong to this group', patch_res.json()['message'])

        # Try changing group to group_b without changing student -> 400
        patch_res2 = self.client.patch(f'/v1/reports/attendance/{rec_a.id}', {
            'group_id': self.group_b.id,
        })
        self.assertEqual(patch_res2.status_code, 400)

    def test_teacher_attendance_security_and_self_checkin(self):
        """Test teacher attendance RBAC, self check-in, and scoping."""
        import datetime
        self.client.force_authenticate(user=self.teacher_a)

        # Teacher cannot POST to /v1/reports/teacher-attendance (admin-only)
        post_res = self.client.post('/v1/reports/teacher-attendance', {
            'teacher_id': self.teacher_a.id,
            'group_id': self.group_a.id,
            'date': self.today.isoformat(),
            'status': TeacherAttendanceRecord.Status.PRESENT,
        })
        self.assertEqual(post_res.status_code, 403)

        # Teacher self-checkin on own group -> 200/201
        self.group_a.lesson_start_time = datetime.time(9, 0)
        self.group_a.save()
        checkin_ok = self.client.post('/v1/teacher-attendance/self-checkin', {
            'group_id': self.group_a.id,
            'note': 'On time',
        })
        self.assertIn(checkin_ok.status_code, (200, 201))
        self.assertEqual(checkin_ok.json()['data']['teacher_id'], self.teacher_a.id)

        # Teacher self-checkin on Teacher B's group -> 404
        checkin_fail = self.client.post('/v1/teacher-attendance/self-checkin', {
            'group_id': self.group_b.id,
        })
        self.assertEqual(checkin_fail.status_code, 404)

        # Admin marks teacher attendance with mismatch between teacher and group -> 400
        self.client.force_authenticate(user=self.admin)
        admin_mismatch = self.client.post('/v1/reports/teacher-attendance', {
            'teacher_id': self.teacher_a.id,
            'group_id': self.group_b.id,
            'date': self.today.isoformat(),
            'status': TeacherAttendanceRecord.Status.PRESENT,
        })
        self.assertEqual(admin_mismatch.status_code, 400)
        self.assertIn('Teacher is not the assigned teacher for this group', admin_mismatch.json()['message'])

        # Admin creates valid record for Teacher B
        admin_ok = self.client.post('/v1/reports/teacher-attendance', {
            'teacher_id': self.teacher_b.id,
            'group_id': self.group_b.id,
            'date': self.today.isoformat(),
            'status': TeacherAttendanceRecord.Status.PRESENT,
        })
        self.assertEqual(admin_ok.status_code, 201)
        rec_b_id = admin_ok.json()['data']['id']

        # Teacher A cannot view Teacher B's attendance detail
        self.client.force_authenticate(user=self.teacher_a)
        self.assertEqual(self.client.get(f'/v1/reports/teacher-attendance/{rec_b_id}').status_code, 404)

        # Teacher A listing teacher attendance only sees their own
        list_t_res = self.client.get('/v1/reports/teacher-attendance')
        self.assertEqual(list_t_res.status_code, 200)
        teacher_ids = [r['teacher_id'] for r in list_t_res.json()['data']['rows']]
        self.assertIn(self.teacher_a.id, teacher_ids)
        self.assertNotIn(self.teacher_b.id, teacher_ids)


class Phase2ScheduleAndArchiveTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Phase 2 Company', subdomain='p2comp')
        self.branch_a = Branch.objects.create(company=self.company, name='Branch A')
        self.branch_b = Branch.objects.create(company=self.company, name='Branch B')

        self.room_a1 = Room.objects.create(branch=self.branch_a, name='Room A-1', capacity=20)
        self.room_b1 = Room.objects.create(branch=self.branch_b, name='Room B-1', capacity=25)

        self.ceo = User.objects.create_user(
            phone='998907770001',
            password='password123',
            first_name='Chief',
            last_name='Exec',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )
        self.admin = User.objects.create_user(
            phone='998907770002',
            password='password123',
            first_name='Branch',
            last_name='Admin',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.ADMINISTRATOR,
        )
        self.teacher_a = User.objects.create_user(
            phone='998907770003',
            password='password123',
            first_name='Teacher',
            last_name='Alpha',
            company=self.company,
            user_type=User.UserType.TEACHER,
        )
        # Teacher A assigned only to Branch A
        TeacherBranch.objects.create(teacher=self.teacher_a, branch=self.branch_a)

        self.teacher_b = User.objects.create_user(
            phone='998907770004',
            password='password123',
            first_name='Teacher',
            last_name='Beta',
            company=self.company,
            user_type=User.UserType.TEACHER,
        )
        # Teacher B assigned only to Branch B
        TeacherBranch.objects.create(teacher=self.teacher_b, branch=self.branch_b)

        self.course = Course.objects.create(company=self.company, name='Math')

    def test_room_branch_mismatch(self):
        """Room from Branch B cannot be assigned to Group in Branch A."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.post('/v1/groups', {
            'name': 'Group In A With Room In B',
            'branch_id': self.branch_a.id,
            'room_id': self.room_b1.id,
            'days': Group.Days.ODD,
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Room belongs to a different branch', res.json()['message'])

    def test_teacher_branch_mismatch(self):
        """Teacher assigned only to Branch B cannot be assigned to Group in Branch A."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.post('/v1/groups', {
            'name': 'Group In A With Teacher B',
            'branch_id': self.branch_a.id,
            'teacher_id': self.teacher_b.id,
            'days': Group.Days.ODD,
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Teacher is not assigned to this branch', res.json()['message'])

    def test_invalid_date_and_time_ranges(self):
        """Invalid date ranges or inverted start/end times should be rejected with 400."""
        self.client.force_authenticate(user=self.admin)

        # Inverted dates (start > end)
        res_dates = self.client.post('/v1/groups', {
            'name': 'Bad Dates',
            'branch_id': self.branch_a.id,
            'days': Group.Days.ODD,
            'group_start_date': '2026-10-01',
            'group_end_date': '2026-09-01',
        })
        self.assertEqual(res_dates.status_code, 400)
        self.assertIn('start date must be before or equal to group end date', res_dates.json()['message'].lower())

        # Inverted times (start >= end)
        res_times = self.client.post('/v1/groups', {
            'name': 'Bad Times',
            'branch_id': self.branch_a.id,
            'days': Group.Days.ODD,
            'lesson_start_time': '10:00',
            'lesson_end_time': '09:00',
        })
        self.assertEqual(res_times.status_code, 400)
        self.assertIn('start time must be before lesson end time', res_times.json()['message'].lower())

    def test_schedule_conflicts_detection(self):
        """Room and Teacher collision detection returning 409 Conflict with structured payload."""
        self.client.force_authenticate(user=self.admin)

        # 1. Create base group in Room A-1 with Teacher A, Mon/Wed/Fri (ODD), 09:00-10:30
        res1 = self.client.post('/v1/groups', {
            'name': 'Base Group A1',
            'branch_id': self.branch_a.id,
            'room_id': self.room_a1.id,
            'teacher_id': self.teacher_a.id,
            'days': Group.Days.ODD,
            'lesson_start_time': '09:00',
            'lesson_end_time': '10:30',
            'group_start_date': '2026-09-01',
            'group_end_date': '2026-12-01',
        })
        self.assertEqual(res1.status_code, 201)

        # 2. Collision on ROOM: Different teacher, but same room, overlapping time (10:00-11:30), same days
        teacher_a2 = User.objects.create_user(
            phone='998907770005',
            password='password123',
            first_name='Teacher',
            last_name='Gamma',
            company=self.company,
            user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=teacher_a2, branch=self.branch_a)

        res_room_conflict = self.client.post('/v1/groups', {
            'name': 'Conflicting Room Group',
            'branch_id': self.branch_a.id,
            'room_id': self.room_a1.id,
            'teacher_id': teacher_a2.id,
            'days': Group.Days.ODD,
            'lesson_start_time': '10:00',
            'lesson_end_time': '11:30',
            'group_start_date': '2026-09-01',
            'group_end_date': '2026-12-01',
        })
        self.assertEqual(res_room_conflict.status_code, 409)
        self.assertIn('Room collision', res_room_conflict.json()['message'])
        conflicts = res_room_conflict.json().get('conflicts', [])
        self.assertTrue(any(c['type'] == 'room' for c in conflicts))

        # 3. Collision on TEACHER: Different room, but same teacher, overlapping time, same days
        room_a2 = Room.objects.create(branch=self.branch_a, name='Room A-2', capacity=20)
        res_teacher_conflict = self.client.post('/v1/groups', {
            'name': 'Conflicting Teacher Group',
            'branch_id': self.branch_a.id,
            'room_id': room_a2.id,
            'teacher_id': self.teacher_a.id,
            'days': Group.Days.ODD,
            'lesson_start_time': '09:30',
            'lesson_end_time': '11:00',
            'group_start_date': '2026-09-01',
            'group_end_date': '2026-12-01',
        })
        self.assertEqual(res_teacher_conflict.status_code, 409)
        self.assertIn('Teacher collision', res_teacher_conflict.json()['message'])
        conflicts_t = res_teacher_conflict.json().get('conflicts', [])
        self.assertTrue(any(c['type'] == 'teacher' for c in conflicts_t))

        # 4. Valid non-colliding group: Same room & teacher, but different days (EVEN days)
        res_ok_days = self.client.post('/v1/groups', {
            'name': 'Non Colliding Even Days',
            'branch_id': self.branch_a.id,
            'room_id': self.room_a1.id,
            'teacher_id': self.teacher_a.id,
            'days': Group.Days.EVEN,
            'lesson_start_time': '09:00',
            'lesson_end_time': '10:30',
            'group_start_date': '2026-09-01',
            'group_end_date': '2026-12-01',
        })
        self.assertEqual(res_ok_days.status_code, 201)

        # 5. Valid non-colliding group: Same days & room, but non-overlapping time (11:00-12:30)
        res_ok_times = self.client.post('/v1/groups', {
            'name': 'Non Colliding Times',
            'branch_id': self.branch_a.id,
            'room_id': self.room_a1.id,
            'teacher_id': teacher_a2.id,
            'days': Group.Days.ODD,
            'lesson_start_time': '11:00',
            'lesson_end_time': '12:30',
            'group_start_date': '2026-09-01',
            'group_end_date': '2026-12-01',
        })
        self.assertEqual(res_ok_times.status_code, 201)

    def test_student_branch_invariant_from_group(self):
        """Student branch is guaranteed to match group.branch upon creation and update."""
        self.client.force_authenticate(user=self.admin)

        group_b = Group.objects.create(
            company=self.company,
            branch=self.branch_b,
            name='Group in Branch B',
            days=Group.Days.ODD,
        )
        group_a = Group.objects.create(
            company=self.company,
            branch=self.branch_a,
            name='Group in Branch A',
            days=Group.Days.ODD,
        )

        # Create student with branch_id=branch_a but group_id=group_b -> branch must become branch_b
        res_create = self.client.post('/v1/students', {
            'first_name': 'Invar',
            'last_name': 'Student',
            'phone': '998908880001',
            'branch_id': self.branch_a.id,
            'group_id': group_b.id,
            'trial_date': '2026-09-01',
        })
        self.assertEqual(res_create.status_code, 201)
        student_id = res_create.json()['data']['id']
        student = Student.objects.get(pk=student_id)
        self.assertEqual(student.branch_id, self.branch_b.id)

        # Update student to group_a -> branch must become branch_a
        res_patch = self.client.patch(f'/v1/students/{student_id}', {
            'group_id': group_a.id,
        })
        self.assertEqual(res_patch.status_code, 200)
        student.refresh_from_db()
        self.assertEqual(student.branch_id, self.branch_a.id)

    def test_group_soft_archive_and_attendance_preserved(self):
        """DELETE /v1/groups/{id} sets ARCHIVE status and preserves attendance records."""
        self.client.force_authenticate(user=self.admin)

        group = Group.objects.create(
            company=self.company,
            branch=self.branch_a,
            name='Group To Archive',
            days=Group.Days.ODD,
            status=Group.Status.ACTIVE,
        )
        student = Student.objects.create(
            company=self.company,
            branch=self.branch_a,
            group=group,
            first_name='Study',
            last_name='Kid',
            phone='998908880002',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )
        att_rec = AttendanceRecord.objects.create(
            company=self.company,
            student=student,
            group=group,
            attend_date='2026-09-05',
            status=AttendanceRecord.Status.PRESENT,
        )

        res_del = self.client.delete(f'/v1/groups/{group.id}')
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.json()['data']['archived'])

        # Check group still exists in DB and is archived
        group.refresh_from_db()
        self.assertEqual(group.status, Group.Status.ARCHIVE)
        self.assertIsNotNone(group.archived_at)
        self.assertEqual(group.archived_by_id, self.admin.id)

        # Attendance record is intact!
        self.assertTrue(AttendanceRecord.objects.filter(pk=att_rec.pk).exists())

    def test_teacher_soft_deactivation_on_history(self):
        """DELETE /v1/teachers/{id} sets is_active=False if attendance history exists; hard deletes if none."""
        self.client.force_authenticate(user=self.ceo)

        # Teacher 1 has attendance history
        group = Group.objects.create(
            company=self.company,
            branch=self.branch_a,
            teacher=self.teacher_a,
            name='Teacher Alpha Group',
            days=Group.Days.ODD,
        )
        TeacherAttendanceRecord.objects.create(
            company=self.company,
            teacher=self.teacher_a,
            group=group,
            attend_date='2026-09-05',
            status=TeacherAttendanceRecord.Status.PRESENT,
        )

        res1 = self.client.delete(f'/v1/user/teacher/{self.teacher_a.id}')
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.json()['data'].get('archived'))

        self.teacher_a.refresh_from_db()
        self.assertFalse(self.teacher_a.is_active)

        # Teacher Beta has NO history -> should be hard-deleted
        res2 = self.client.delete(f'/v1/user/teacher/{self.teacher_b.id}')
        self.assertEqual(res2.status_code, 200)
        self.assertFalse(res2.json()['data'].get('archived', False))
        self.assertFalse(User.objects.filter(pk=self.teacher_b.pk).exists())


class Phase3PayrollAndSalaryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Phase 3 Company', subdomain='p3comp')
        self.branch = Branch.objects.create(company=self.company, name='Branch 3')
        self.room = Room.objects.create(branch=self.branch, name='Room 3-1', capacity=20)

        self.ceo = User.objects.create_user(
            phone='998909990001',
            password='password123',
            first_name='Chief',
            last_name='Officer',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )
        self.admin = User.objects.create_user(
            phone='998909990002',
            password='password123',
            first_name='Fin',
            last_name='Admin',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.ADMINISTRATOR,
        )
        self.teacher_a = User.objects.create_user(
            phone='998909990003',
            password='password123',
            first_name='Anvar',
            last_name='Teacher',
            company=self.company,
            user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=self.teacher_a, branch=self.branch)

        self.teacher_b = User.objects.create_user(
            phone='998909990004',
            password='password123',
            first_name='Bekzod',
            last_name='Teacher',
            company=self.company,
            user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=self.teacher_b, branch=self.branch)

        self.course = Course.objects.create(company=self.company, name='English Course', price=1000000)
        self.group_a = Group.objects.create(
            company=self.company,
            branch=self.branch,
            course=self.course,
            teacher=self.teacher_a,
            room=self.room,
            name='Group Alpha',
            days=Group.Days.ODD,
        )
        self.group_b = Group.objects.create(
            company=self.company,
            branch=self.branch,
            course=self.course,
            teacher=self.teacher_b,
            room=self.room,
            name='Group Beta',
            days=Group.Days.EVEN,
        )

    def test_teacher_rbac_salary_denial(self):
        """Teachers and non-finance staff must receive 403 Forbidden on salary-settings and payroll endpoints."""
        self.client.force_authenticate(user=self.teacher_a)

        # GET /v1/salary-settings -> 403
        self.assertEqual(self.client.get('/v1/salary-settings').status_code, 403)

        # POST /v1/salary-settings -> 403
        self.assertEqual(self.client.post('/v1/salary-settings', {
            'teacher_id': self.teacher_a.id,
            'amount': 1000,
        }).status_code, 403)

        # GET /v1/finance/payroll -> 403
        self.assertEqual(self.client.get('/v1/finance/payroll').status_code, 403)

        # POST /v1/finance/payroll/pay -> 403
        self.assertEqual(self.client.post('/v1/finance/payroll/pay', {
            'teacher_id': self.teacher_a.id,
            'amount': 1000,
        }).status_code, 403)

        # Office Admin without finance permission also denied -> 403
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.client.get('/v1/salary-settings').status_code, 403)
        self.assertEqual(self.client.get('/v1/finance/payroll').status_code, 403)

        # CEO has finance permissions -> 200
        self.client.force_authenticate(user=self.ceo)
        self.assertEqual(self.client.get('/v1/salary-settings').status_code, 200)
        self.assertEqual(self.client.get('/v1/finance/payroll').status_code, 200)

    def test_salary_setting_teacher_fk_and_rename_resilience(self):
        """Salary setting linked by teacher FK survives teacher name changes without breaking calculations."""
        self.client.force_authenticate(user=self.ceo)

        # Create setting linked by teacher_id
        res = self.client.post('/v1/salary-settings', {
            'teacher_id': self.teacher_a.id,
            'salary_type': SalarySetting.SalaryType.PERCENT,
            'amount': 40,
        })
        self.assertEqual(res.status_code, 201)
        setting_id = res.json()['data']['id']

        setting = SalarySetting.objects.get(pk=setting_id)
        self.assertEqual(setting.teacher_id, self.teacher_a.id)

        # Create student and payment in Group Alpha (Teacher A)
        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            group=self.group_a,
            first_name='Alisher',
            last_name='Student',
            phone='998909991111',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )
        self.client.post('/v1/replenishments', {
            'student_id': student.id,
            'amount': 1000000,
            'method': 'cash',
        })

        # Rename Teacher A
        self.teacher_a.first_name = 'Anvarjon'
        self.teacher_a.last_name = 'Qodirov'
        self.teacher_a.save()

        # Check payroll calculation: setting is still resolved by FK and accrues 40% of 1,000,000 = 400,000
        payroll_res = self.client.get('/v1/finance/payroll')
        self.assertEqual(payroll_res.status_code, 200)
        rows = payroll_res.json()['data']['rows']
        teacher_row = next(r for r in rows if r['teacher_id'] == self.teacher_a.id)
        self.assertEqual(teacher_row['accrued'], 400000)

    def test_effective_dates_scoping(self):
        """Historical payroll calculation respects effective date ranges."""
        self.client.force_authenticate(user=self.ceo)

        # August rate: 30%
        SalarySetting.objects.create(
            company=self.company,
            teacher=self.teacher_a,
            teacher_name=self.teacher_a.display_name(),
            salary_type=SalarySetting.SalaryType.PERCENT,
            amount=30,
            effective_from='2026-08-01',
            effective_to='2026-08-31',
        )

        # September rate: 50%
        SalarySetting.objects.create(
            company=self.company,
            teacher=self.teacher_a,
            teacher_name=self.teacher_a.display_name(),
            salary_type=SalarySetting.SalaryType.PERCENT,
            amount=50,
            effective_from='2026-09-01',
        )

        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            group=self.group_a,
            first_name='Vali',
            last_name='Student',
            phone='998909991112',
            status=Student.Status.STUDYING,
            trial_date='2026-08-01',
        )

        # August payment
        p_aug = Payment.objects.create(
            company=self.company,
            student=student,
            group=self.group_a,
            course=self.course,
            teacher=self.teacher_a,
            student_name=student.full_name,
            amount=1000000,
            gross_amount=1000000,
            net_amount=1000000,
            transaction_type=Payment.TransactionType.PAYMENT,
        )
        import datetime as dt
        p_aug.created_at = timezone.make_aware(dt.datetime(2026, 8, 15, 12, 0))
        p_aug.save()

        # September payment
        p_sep = Payment.objects.create(
            company=self.company,
            student=student,
            group=self.group_a,
            course=self.course,
            teacher=self.teacher_a,
            student_name=student.full_name,
            amount=1000000,
            gross_amount=1000000,
            net_amount=1000000,
            transaction_type=Payment.TransactionType.PAYMENT,
        )
        p_sep.created_at = timezone.make_aware(dt.datetime(2026, 9, 15, 12, 0))
        p_sep.save()

        # Check August payroll: 30% of 1,000,000 = 300,000
        res_aug = self.client.get('/v1/finance/payroll?month=2026-08')
        row_aug = next(r for r in res_aug.json()['data']['rows'] if r['teacher_id'] == self.teacher_a.id)
        self.assertEqual(row_aug['accrued'], 300000)

        # Check September payroll: 50% of 1,000,000 = 500,000
        res_sep = self.client.get('/v1/finance/payroll?month=2026-09')
        row_sep = next(r for r in res_sep.json()['data']['rows'] if r['teacher_id'] == self.teacher_a.id)
        self.assertEqual(row_sep['accrued'], 500000)

    def test_immutable_payment_allocation_on_student_group_transfer(self):
        """Student transfer to another group does not move historical payment percentage to the new teacher."""
        self.client.force_authenticate(user=self.ceo)

        # Both teachers have 40%
        SalarySetting.objects.create(
            company=self.company,
            teacher=self.teacher_a,
            salary_type=SalarySetting.SalaryType.PERCENT,
            amount=40,
        )
        SalarySetting.objects.create(
            company=self.company,
            teacher=self.teacher_b,
            salary_type=SalarySetting.SalaryType.PERCENT,
            amount=40,
        )

        # Student starts in Teacher A's group
        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            group=self.group_a,
            first_name='Bobur',
            last_name='Student',
            phone='998909991113',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )

        # Student pays tuition while in Group Alpha
        res_pay = self.client.post('/v1/replenishments', {
            'student_id': student.id,
            'amount': 2000000,
            'method': 'cash',
        })
        self.assertEqual(res_pay.status_code, 201)
        payment_id = res_pay.json()['data']['id']
        pay_obj = Payment.objects.get(pk=payment_id)
        self.assertEqual(pay_obj.teacher_id, self.teacher_a.id)
        self.assertEqual(pay_obj.group_id, self.group_a.id)

        # Later, student is transferred to Teacher B's group
        student.group = self.group_b
        student.save()

        # Recalculate payroll for the month of payment
        current_month = timezone.localdate().strftime('%Y-%m')
        payroll_res = self.client.get(f'/v1/finance/payroll?month={current_month}')
        rows = payroll_res.json()['data']['rows']

        teacher_a_row = next(r for r in rows if r['teacher_id'] == self.teacher_a.id)
        teacher_b_row = next(r for r in rows if r['teacher_id'] == self.teacher_b.id)

        # Teacher A keeps the payment (40% of 2,000,000 = 800,000)
        self.assertEqual(teacher_a_row['group_payments'], 2000000)
        self.assertEqual(teacher_a_row['accrued'], 800000)

        # Teacher B does NOT get the historical payment
        self.assertEqual(teacher_b_row['group_payments'], 0)
        self.assertEqual(teacher_b_row['accrued'], 0)

    def test_refund_reduces_eligible_revenue(self):
        """Refund endpoint correctly deducts from eligible group payments and accrued salary."""
        self.client.force_authenticate(user=self.ceo)

        SalarySetting.objects.create(
            company=self.company,
            teacher=self.teacher_a,
            salary_type=SalarySetting.SalaryType.PERCENT,
            amount=50,
        )

        student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            group=self.group_a,
            first_name='Davron',
            last_name='Student',
            phone='998909991114',
            status=Student.Status.STUDYING,
            trial_date='2026-09-01',
        )

        # Initial payment 1,000,000
        res_pay = self.client.post('/v1/replenishments', {
            'student_id': student.id,
            'amount': 1000000,
            'method': 'cash',
        })
        payment_id = res_pay.json()['data']['id']

        # Refund 300,000
        res_refund = self.client.post(f'/v1/payments/{payment_id}/refund', {
            'amount': 300000,
            'comment': 'Partial course refund',
        })
        self.assertEqual(res_refund.status_code, 201)
        self.assertEqual(res_refund.json()['data']['transaction_type'], 'refund')

        # Check payroll: net payments = 700,000; accrued = 50% of 700,000 = 350,000
        current_month = timezone.localdate().strftime('%Y-%m')
        payroll_res = self.client.get(f'/v1/finance/payroll?month={current_month}')
        teacher_a_row = next(r for r in payroll_res.json()['data']['rows'] if r['teacher_id'] == self.teacher_a.id)

        self.assertEqual(teacher_a_row['group_payments'], 700000)
        self.assertEqual(teacher_a_row['accrued'], 350000)

    def test_payroll_pay_and_overpayment_protection(self):
        """Payroll payment creates first-class PayrollPayment record and guards against overpayments."""
        self.client.force_authenticate(user=self.ceo)

        # Fixed salary 500,000
        SalarySetting.objects.create(
            company=self.company,
            teacher=self.teacher_a,
            salary_type=SalarySetting.SalaryType.FIXED,
            amount=500000,
        )

        current_month = timezone.localdate().strftime('%Y-%m')

        # Attempt to pay 600,000 without force (exceeds 500,000 accrued) -> 400 Bad Request
        res_over = self.client.post('/v1/finance/payroll/pay', {
            'teacher_id': self.teacher_a.id,
            'amount': 600000,
            'month': current_month,
        })
        self.assertEqual(res_over.status_code, 400)
        self.assertEqual(res_over.json()['code'], 'overpayment')

        # Pay valid partial amount 300,000 -> 201 Created
        res_pay1 = self.client.post('/v1/finance/payroll/pay', {
            'teacher_id': self.teacher_a.id,
            'amount': 300000,
            'method': 'cash',
            'month': current_month,
        })
        self.assertEqual(res_pay1.status_code, 201)
        self.assertTrue(PayrollPayment.objects.filter(teacher=self.teacher_a, amount=300000, payroll_period=current_month).exists())

        # Check payroll: accrued=500,000, paid=300,000, balance=200,000, status='partial'
        res_payroll = self.client.get(f'/v1/finance/payroll?month={current_month}')
        teacher_row = next(r for r in res_payroll.json()['data']['rows'] if r['teacher_id'] == self.teacher_a.id)
        self.assertEqual(teacher_row['paid'], 300000)
        self.assertEqual(teacher_row['balance'], 200000)
        self.assertEqual(teacher_row['status'], 'partial')

        # CEO can override with force=True
        res_force = self.client.post('/v1/finance/payroll/pay', {
            'teacher_id': self.teacher_a.id,
            'amount': 300000,
            'month': current_month,
            'force': True,
        })
        self.assertEqual(res_force.status_code, 201)


class Phase4HardeningAndRbacTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Alpha Academy', subdomain='alpha')
        self.branch = Branch.objects.create(company=self.company, name='Alpha Main')
        self.room = Room.objects.create(branch=self.branch, name='Alpha Room 1')


        self.ceo = User.objects.create_user(
            phone='998901114444',
            password='password123',
            first_name='Alpha',
            last_name='CEO',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )

        self.teacher = User.objects.create_user(
            phone='998902224444',
            password='password123',
            first_name='Alpha',
            last_name='Teacher',
            company=self.company,
            user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=self.teacher, branch=self.branch)

        self.course = Course.objects.create(
            company=self.company,
            name='Alpha Math',
            price=600000,
        )

        self.group = Group.objects.create(
            company=self.company,
            branch=self.branch,
            course=self.course,
            teacher=self.teacher,
            room=self.room,
            name='Alpha Group 1',
            days=Group.Days.ODD,
            lesson_start_time='09:00',
            lesson_end_time='10:30',
        )

        self.student = Student.objects.create(
            company=self.company,
            branch=self.branch,
            group=self.group,
            first_name='Student',
            last_name='One',
            phone='998903334444',
            status=Student.Status.STUDYING,
        )

        # Company B for cross-company isolation
        self.company_b = Company.objects.create(name='Beta Academy', subdomain='beta')
        self.branch_b = Branch.objects.create(company=self.company_b, name='Beta Branch')
        self.ceo_b = User.objects.create_user(
            phone='998905554444',
            password='password123',
            first_name='Beta',
            last_name='CEO',
            company=self.company_b,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )
        self.group_b = Group.objects.create(
            company=self.company_b,
            branch=self.branch_b,
            name='Beta Group',
        )
        self.student_b = Student.objects.create(
            company=self.company_b,
            branch=self.branch_b,
            first_name='Beta',
            last_name='Student',
            phone='998906664444',
        )

    def test_duplicate_attendance_db_constraint(self):
        """AttendanceRecord raises IntegrityError when duplicate (company, student, group, attend_date) is inserted."""
        today = timezone.localdate()
        AttendanceRecord.objects.create(
            company=self.company,
            student=self.student,
            group=self.group,
            attend_date=today,
            status=AttendanceRecord.Status.PRESENT,
        )

        with self.assertRaises(IntegrityError):
            AttendanceRecord.objects.create(
                company=self.company,
                student=self.student,
                group=self.group,
                attend_date=today,
                status=AttendanceRecord.Status.ABSENT,
            )

    def test_group_schedule_slots_sync(self):
        """Creating and updating groups synchronizes normalized GroupScheduleSlot rows."""
        self.client.force_authenticate(user=self.ceo)

        # 1. Create group with Days.ODD (Mon, Wed, Fri -> 0, 2, 4)
        res = self.client.post('/v1/groups', {
            'name': 'Slots Group',
            'branch_id': self.branch.id,
            'course_id': self.course.id,
            'teacher_id': self.teacher.id,
            'room_id': self.room.id,
            'days': Group.Days.ODD,
            'lesson_start_time': '14:00',
            'lesson_end_time': '15:30',
        })
        self.assertEqual(res.status_code, 201)
        group_id = res.json()['data']['id']

        slots = GroupScheduleSlot.objects.filter(group_id=group_id).order_by('weekday')
        self.assertEqual(slots.count(), 3)
        self.assertEqual(list(slots.values_list('weekday', flat=True)), [0, 2, 4])

        # 2. Update group to Days.WEEKEND (Sat, Sun -> 5, 6)
        patch_res = self.client.patch(f'/v1/groups/{group_id}', {
            'days': Group.Days.WEEKEND,
        })
        self.assertEqual(patch_res.status_code, 200)

        updated_slots = GroupScheduleSlot.objects.filter(group_id=group_id).order_by('weekday')
        self.assertEqual(updated_slots.count(), 2)
        self.assertEqual(list(updated_slots.values_list('weekday', flat=True)), [5, 6])

    def test_group_enrollment_history(self):
        """Student group assignment, transfer, and status change maintains GroupEnrollment history."""
        self.client.force_authenticate(user=self.ceo)

        group_2 = Group.objects.create(
            company=self.company,
            branch=self.branch,
            name='Alpha Group 2',
        )

        # 1. Create student assigned to group 1
        res = self.client.post('/v1/students', {
            'first_name': 'Enrollment',
            'last_name': 'Test',
            'phone': '998907774444',
            'trial_date': '2026-09-20',
            'branch_id': self.branch.id,
            'group_id': self.group.id,
            'status': Student.Status.STUDYING,
        })
        self.assertEqual(res.status_code, 201)
        student_id = res.json()['data']['id']

        active_enrollment = GroupEnrollment.objects.get(student_id=student_id, group=self.group)
        self.assertEqual(active_enrollment.status, GroupEnrollment.Status.ACTIVE)
        self.assertIsNone(active_enrollment.left_date)

        # 2. Transfer student to group 2
        patch_res = self.client.patch(f'/v1/students/{student_id}', {
            'group_id': group_2.id,
        })
        self.assertEqual(patch_res.status_code, 200)

        old_enrollment = GroupEnrollment.objects.get(student_id=student_id, group=self.group)
        self.assertEqual(old_enrollment.status, GroupEnrollment.Status.TRANSFERRED)
        self.assertIsNotNone(old_enrollment.left_date)

        new_enrollment = GroupEnrollment.objects.get(student_id=student_id, group=group_2)
        self.assertEqual(new_enrollment.status, GroupEnrollment.Status.ACTIVE)
        self.assertIsNone(new_enrollment.left_date)

        # 3. Change status to LEFT
        left_res = self.client.patch(f'/v1/students/{student_id}', {
            'status': Student.Status.LEFT,
        })
        self.assertEqual(left_res.status_code, 200)

        final_enrollment = GroupEnrollment.objects.get(student_id=student_id, group=group_2)
        self.assertEqual(final_enrollment.status, GroupEnrollment.Status.LEFT)
        self.assertIsNotNone(final_enrollment.left_date)

    def test_audit_log_recorded_on_attendance_correction(self):
        """Attendance corrections and deletions record AuditLogRecord entries."""
        self.client.force_authenticate(user=self.ceo)
        today = timezone.localdate()

        record = AttendanceRecord.objects.create(
            company=self.company,
            student=self.student,
            group=self.group,
            attend_date=today,
            status=AttendanceRecord.Status.PRESENT,
        )

        # PATCH attendance status to ABSENT
        patch_res = self.client.patch(f'/v1/reports/attendance/{record.id}', {
            'status': AttendanceRecord.Status.ABSENT,
        })
        self.assertEqual(patch_res.status_code, 200)

        update_log = AuditLogRecord.objects.filter(
            company=self.company,
            entity_type='attendance',
            entity_id=record.id,
            action='update',
        ).latest('created_at')
        self.assertEqual(update_log.old_values['status'], AttendanceRecord.Status.PRESENT)
        self.assertEqual(update_log.new_values['status'], AttendanceRecord.Status.ABSENT)
        self.assertEqual(update_log.actor, self.ceo)

        # DELETE attendance
        del_res = self.client.delete(f'/v1/reports/attendance/{record.id}')
        self.assertEqual(del_res.status_code, 200)

        del_log = AuditLogRecord.objects.filter(
            company=self.company,
            entity_type='attendance',
            entity_id=record.id,
            action='delete',
        ).latest('created_at')
        self.assertEqual(del_log.actor, self.ceo)
        self.assertEqual(del_log.old_values['student_id'], self.student.id)

    def test_cross_company_isolation_matrix(self):
        """Company A cannot access, mutate, or view Company B's groups, students, or records."""
        self.client.force_authenticate(user=self.ceo)

        # Attempt to access Company B group -> 404
        res_group = self.client.get(f'/v1/groups/{self.group_b.id}')
        self.assertEqual(res_group.status_code, 404)

        # Attempt to access Company B student -> 404
        res_student = self.client.get(f'/v1/students/{self.student_b.id}')
        self.assertEqual(res_student.status_code, 404)

        # Attempt to delete Company B group -> 404
        res_del_group = self.client.delete(f'/v1/groups/{self.group_b.id}')
        self.assertEqual(res_del_group.status_code, 404)

    def test_private_routes_reject_anonymous(self):
        """Unauthenticated requests to private routes are rejected (401 or 403)."""
        self.client.force_authenticate(user=None)

        routes = [
            ('/v1/groups', 'get'),
            ('/v1/students', 'get'),
            ('/v1/reports/attendance', 'get'),
            ('/v1/finance/payroll', 'get'),
            ('/v1/salary-settings', 'get'),
        ]
        for url, method in routes:
            handler = getattr(self.client, method)
            res = handler(url)
            self.assertIn(res.status_code, [401, 403], f"Route {url} should be protected but returned {res.status_code}")









