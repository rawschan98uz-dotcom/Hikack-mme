"""Students block, problem 7: importing the same people twice must not create twins."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from crm.models import Student
from org.models import Branch, Company


class ImportDuplicatesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Import Co', subdomain='importco')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        ceo = User.objects.create_user(
            phone='998909550001', password='x', first_name='C', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.client.force_authenticate(ceo)

    def upload(self, text, dry_run='0'):
        res = self.client.post('/v1/students/import', {
            'file': SimpleUploadedFile('s.csv', text.encode('utf-8'), content_type='text/csv'), 'dry_run': dry_run,
        }, format='multipart')
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()['data']

    def test_same_file_twice_creates_no_twins(self):
        csv = 'first_name,last_name,phone\nVali,Karimov,901112233\nAli,Umarov,901112244\n'
        self.assertEqual(self.upload(csv)['created'], 2)
        second = self.upload(csv)
        self.assertEqual(second['created'], 0)
        self.assertEqual(second['skipped'], 2)
        self.assertEqual(Student.objects.filter(company=self.company).count(), 2)

    def test_preview_marks_existing_rows(self):
        self.upload('first_name,last_name,phone\nVali,Karimov,901112233\n')
        preview = self.upload('first_name,last_name,phone\nvali,KARIMOV,+998 90 111 22 33\nNew,Kid,901119999\n', dry_run='1')
        rows = {r['full_name']: r for r in preview['rows']}
        self.assertFalse(rows['Vali Karimov']['is_valid'])
        self.assertIn('Уже есть в базе', rows['Vali Karimov']['message'])
        self.assertTrue(rows['New Kid']['is_valid'])

    def test_repeat_inside_one_file(self):
        data = self.upload('first_name,last_name,phone\nVali,Karimov,901112233\nVali,Karimov,901112233\n')
        self.assertEqual(data['created'], 1)
        self.assertEqual(data['skipped'], 1)

    def test_student_who_left_can_be_loaded_again(self):
        old = Student.objects.create(
            company=self.company, branch=self.branch, first_name='Vali', last_name='Karimov', phone='901112233',
            status=Student.Status.LEFT,
        )
        self.assertEqual(self.upload('first_name,last_name,phone\nVali,Karimov,901112233\n')['created'], 1)
        self.assertEqual(Student.objects.filter(first_name='Vali').exclude(pk=old.pk).count(), 1)

    def test_brothers_with_one_phone_are_both_loaded(self):
        data = self.upload('first_name,last_name,phone\nVali,Karimov,901112233\nSardor,Karimov,901112233\n')
        self.assertEqual(data['created'], 2)
