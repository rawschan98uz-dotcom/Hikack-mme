from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from crm.models import Course, Lead, Student
from finance.models import Payment
from org.models import Company, Branch


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
        self.assertIn('Secondary phone must contain at least 9 digits', res.json()['message'])

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
        self.assertIn('Secondary phone must contain at least 9 digits', res.json()['message'])

        # 4. Student creation with short phone2 should fail
        res = self.client.post('/v1/students', {
            'first_name': 'StudentTest',
            'phone': '909998877',
            'phone2': '99812345',
            'trial_date': '2026-05-10',
            'branch_id': self.branch.id,
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Secondary phone must contain at least 9 digits', res.json()['message'])

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





