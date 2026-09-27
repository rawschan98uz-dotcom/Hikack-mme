"""Leads audit: conversion duplicates, re-conversion, validation, reports, query count."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from accounts.models import User
from crm.models import Lead, Student
from org.models import Branch, Company


class LeadAuditTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Leads Co', subdomain='leadsco')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.ceo = User.objects.create_user(
            phone='998909007701', password='password123', first_name='C', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.client.force_authenticate(self.ceo)

    def convert(self, lead, **extra):
        return self.client.post(f'/v1/leads/{lead.id}/convert', {'trial_date': '2026-09-01', **extra}, format='json')

    def test_convert_refuses_duplicate_of_active_student(self):
        Student.objects.create(company=self.company, branch=self.branch, first_name='Азиз', phone='901110011')
        lead = Lead.objects.create(company=self.company, branch=self.branch, first_name='азиз', phone='901110011')
        res = self.convert(lead)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Student.objects.filter(phone='901110011').count(), 1)
        # an explicit "force" still allows it (e.g. twins with the same name)
        self.assertEqual(self.convert(lead, force=True).status_code, 201)

    def test_reconverted_lead_points_to_new_student_and_blocks_third(self):
        lead = Lead.objects.create(company=self.company, branch=self.branch, first_name='Bek', phone='901110012')
        first = self.convert(lead).json()['data']['student']['id']
        self.client.delete(f'/v1/students/{first}')  # archived -> LEFT
        second = self.convert(lead).json()['data']['student']['id']
        data = self.client.get(f'/v1/leads/{lead.id}').json()['data']
        self.assertEqual(data['converted_student_id'], second)
        self.assertFalse(data['student_deleted'])
        self.assertEqual(self.convert(lead).status_code, 400)
        self.assertEqual(Student.objects.filter(lead=lead).count(), 2)

    def test_invalid_branch_or_course_is_rejected(self):
        res = self.client.post('/v1/leads', {'first_name': 'Z', 'phone': '901110099', 'branch_id': 99999}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.client.post('/v1/leads', {'first_name': 'Z', 'phone': '901110099', 'course_id': 99999}, format='json')
        self.assertEqual(res.status_code, 400)
        lead = Lead.objects.create(company=self.company, branch=self.branch, first_name='Y', phone='901110098')
        res = self.client.patch(f'/v1/leads/{lead.id}', {'branch_id': 99999}, format='json')
        self.assertEqual(res.status_code, 400)
        lead.refresh_from_db()
        self.assertEqual(lead.branch_id, self.branch.id)

    def test_reports_ignore_bad_dates(self):
        for url in ('/v1/reports/conversion?date_from=abc', '/v1/reports/leads?date_to=2026-13-40'):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_lead_list_does_not_query_per_lead(self):
        for i in range(20):
            Lead.objects.create(
                company=self.company, branch=self.branch, first_name=f'L{i}', phone=f'90111{i:04d}',
                stage=Lead.Stage.CONVERTED,
            )
        with CaptureQueriesContext(connection) as ctx:
            res = self.client.get('/v1/leads?stage=converted')
        self.assertEqual(res.status_code, 200)
        self.assertLess(len(ctx.captured_queries), 10)

    def test_convert_without_date_starts_today_not_on_old_trial(self):
        from datetime import date
        from django.utils import timezone
        lead = Lead.objects.create(
            company=self.company, branch=self.branch, first_name='Old', phone='901110077',
            trial_date=date(2026, 1, 5),
        )
        res = self.client.post(f'/v1/leads/{lead.id}/convert', {}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        student = Student.objects.get(pk=res.json()['data']['student']['id'])
        self.assertEqual(student.trial_date, timezone.localdate())
