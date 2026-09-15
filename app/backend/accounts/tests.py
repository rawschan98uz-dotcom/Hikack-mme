from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from crm.models import Lead, Student
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
            'stage': 'incoming',
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
        self.assertEqual(data['trial_date'], '2025-05-15')

        # Test search by first_name and address
        search_res = self.client.get('/v1/leads?q=Alisher')
        self.assertEqual(search_res.status_code, 200)
        self.assertEqual(len(search_res.json()['data']['results']), 1)

        # Test update
        lead_id = data['id']
        patch_res = self.client.patch(f'/v1/leads/{lead_id}', {
            'first_name': 'Bobur',
            'last_name': 'Mirzo',
            'address': 'Tashkent, Yunusabad',
            'comment': 'Changed mind, wants morning group',
            'trial_date': '2025-05-20',
        })
        self.assertEqual(patch_res.status_code, 200)
        updated = patch_res.json()['data']
        self.assertEqual(updated['first_name'], 'Bobur')
        self.assertEqual(updated['last_name'], 'Mirzo')
        self.assertEqual(updated['full_name'], 'Bobur Mirzo')
        self.assertEqual(updated['address'], 'Tashkent, Yunusabad')
        self.assertEqual(updated['comment'], 'Changed mind, wants morning group')
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
        self.assertEqual(student_data['branch_id'], self.branch.id)
        self.assertEqual(student_data['status'], 1)  # STUDYING
        self.assertEqual(student_data['trial_date'], '2025-05-12')
        self.assertEqual(student_data['next_payment_date'], '2025-05-12')

        # Check lead is completely removed from database
        self.assertFalse(Lead.objects.filter(pk=lead_id).exists())

        # Check lead is gone from leads list endpoint
        lead_list_res = self.client.get('/v1/leads')
        self.assertEqual(lead_list_res.json()['data']['count'], 0)

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



