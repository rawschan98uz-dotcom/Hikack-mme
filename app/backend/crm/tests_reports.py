"""Reports audit (2026-09-29): teachers' lessons, student attendance summary, leads & conversion, left students."""
from datetime import date, datetime, timedelta, timezone as dt_tz

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm.models import AttendanceRecord, Course, Group, GroupEnrollment, Lead, Student
from finance.models import ClosedMonth, SalarySetting
from finance.payroll import teacher_accrual
from operations.models import AuditLogRecord, Holiday, TeacherAttendanceRecord
from org.models import Branch, Company

# September 2026: Mon/Wed/Fri lessons from the 1st to the 13th are 2, 4, 7, 9, 11 — five lessons.
D = lambda day: date(2026, 9, day)  # noqa: E731


class Base(TestCase):
    def setUp(self):
        self.c = APIClient()
        self.company = Company.objects.create(name='Rep Co', subdomain='repco')
        self.a = Branch.objects.create(company=self.company, name='A')
        self.b = Branch.objects.create(company=self.company, name='B')
        self.ceo = self.staff('998906660001', 'Ceo', User.StaffRole.CEO)
        self.admin = self.staff('998906660002', 'Admin', User.StaffRole.ADMINISTRATOR)
        self.dir_b = self.staff('998906660003', 'DirB', User.StaffRole.BRANCH_DIRECTOR, branch=self.b)
        self.marketer = self.staff('998906660004', 'Mark', User.StaffRole.MARKETER)
        self.tom = User.objects.create_user(phone='998906660005', password='x', first_name='Tom',
                                            company=self.company, user_type=User.UserType.TEACHER)
        self.bob = User.objects.create_user(phone='998906660006', password='x', first_name='Bob',
                                            company=self.company, user_type=User.UserType.TEACHER)
        TeacherBranch.objects.create(teacher=self.tom, branch=self.a)
        TeacherBranch.objects.create(teacher=self.bob, branch=self.b)
        self.course = Course.objects.create(company=self.company, name='En', price=600_000)
        self.g = Group.objects.create(company=self.company, branch=self.a, name='GA', course=self.course,
                                      teacher=self.tom, days=Group.Days.CUSTOM, weekdays=[0, 2, 4])
        self.gb = Group.objects.create(company=self.company, branch=self.b, name='GB', course=self.course,
                                       teacher=self.bob, days=Group.Days.CUSTOM, weekdays=[0, 2, 4])
        self.today = timezone.localdate()

    def staff(self, phone, name, role, **kw):
        return User.objects.create_user(phone=phone, password='x', first_name=name, company=self.company,
                                        user_type=User.UserType.STAFF, staff_role=role, **kw)

    def as_(self, user):
        self.c.force_authenticate(user)
        return self.c

    def student(self, name, group=None, phone='901111111'):
        group = group or self.g
        s = Student.objects.create(company=self.company, branch=group.branch, group=group, first_name=name,
                                   phone=phone, trial_date=D(1))
        GroupEnrollment.objects.filter(student=s).update(joined_date=D(1))
        return s

    def next_lesson_day(self):
        day = self.today + timedelta(days=1)
        while day.weekday() not in (0, 2, 4):
            day += timedelta(days=1)
        return day


class TeacherLessonsTests(Base):
    def lessons(self, user, **params):
        self.as_(user)
        params.setdefault('date_from', '2026-09-01')
        params.setdefault('date_to', '2026-09-13')
        return self.c.get('/v1/reports/teacher-attendance/lessons', params).json()['data']

    def test_forgotten_lessons_are_visible_as_not_marked(self):
        # Tom pressed «Я пришёл» 3 times out of 5 lessons: the old report showed 100%
        for d in (2, 4, 7):
            TeacherAttendanceRecord.objects.create(company=self.company, teacher=self.tom, group=self.g,
                                                   attend_date=D(d), status=1)
        data = self.lessons(self.ceo, group_id=self.g.id)
        self.assertEqual(data['summary'], {'lessons': 5, 'present': 3, 'late': 0, 'absent': 0, 'not_marked': 2})
        missing = [r for r in data['rows'] if r['status'] is None]
        self.assertEqual(sorted(r['date'] for r in missing), ['2026-09-09', '2026-09-11'])
        self.assertTrue(all(r['teacher_id'] == self.tom.id for r in missing))

    def test_filter_not_marked_and_teacher(self):
        TeacherAttendanceRecord.objects.create(company=self.company, teacher=self.tom, group=self.g,
                                               attend_date=D(2), status=1)
        data = self.lessons(self.ceo, status='not_marked', teacher_id=self.tom.id)
        self.assertEqual(len(data['rows']), 4)
        self.assertEqual({r['group'] for r in data['rows']}, {'GA'})

    def test_office_marks_forgotten_lesson_and_the_teacher_is_paid(self):
        SalarySetting.objects.create(company=self.company, teacher=self.tom, teacher_name='Tom',
                                     salary_type='percent', amount=50)
        self.student('Ali')
        before = teacher_accrual(self.company, self.tom, D(1), D(30))['accrued']
        r = self.as_(self.admin).post('/v1/reports/teacher-attendance', {
            'teacher_id': self.tom.id, 'group_id': self.g.id, 'date': '2026-09-09', 'status': 1,
        }, format='json')
        self.assertEqual(r.status_code, 201, r.json())
        self.assertGreater(teacher_accrual(self.company, self.tom, D(1), D(30))['accrued'], before)
        # The journal says who marked it
        log = AuditLogRecord.objects.filter(entity_type='teacher_attendance', action='create').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor_id, self.admin.id)

    def test_future_lesson_cannot_be_marked(self):
        SalarySetting.objects.create(company=self.company, teacher=self.tom, teacher_name='Tom',
                                     salary_type='percent', amount=50)
        self.student('Ali')
        future = self.next_lesson_day()
        r = self.as_(self.ceo).post('/v1/reports/teacher-attendance', {
            'teacher_id': self.tom.id, 'group_id': self.g.id, 'date': future.isoformat(), 'status': 1,
        }, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(TeacherAttendanceRecord.objects.filter(attend_date=future).exists())

    def test_mark_moved_to_the_future_is_refused(self):
        rec = TeacherAttendanceRecord.objects.create(company=self.company, teacher=self.tom, group=self.g,
                                                     attend_date=D(2), status=1)
        r = self.as_(self.ceo).patch(f'/v1/reports/teacher-attendance/{rec.id}',
                                     {'date': self.next_lesson_day().isoformat()}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_teacher_mark_on_a_day_without_lesson_is_refused(self):
        r = self.as_(self.ceo).post('/v1/reports/teacher-attendance', {
            'teacher_id': self.tom.id, 'group_id': self.g.id, 'date': '2026-09-06', 'status': 1,  # Sunday
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_holiday_is_not_a_lesson(self):
        Holiday.objects.create(company=self.company, branch=self.a, name='H', holiday_date=D(9))
        data = self.lessons(self.ceo, group_id=self.g.id)
        self.assertEqual(data['summary']['lessons'], 4)

    def test_closed_month_rows_are_locked(self):
        ClosedMonth.objects.create(company=self.company, month='2026-09', closed_by=self.ceo)
        data = self.lessons(self.ceo, group_id=self.g.id)
        self.assertTrue(all(r['locked'] for r in data['rows']))
        r = self.c.post('/v1/reports/teacher-attendance', {
            'teacher_id': self.tom.id, 'group_id': self.g.id, 'date': '2026-09-09', 'status': 1,
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_director_sees_only_own_branch(self):
        data = self.lessons(self.dir_b)
        self.assertEqual({r['group'] for r in data['rows']}, {'GB'})

    def test_teacher_sees_only_own_lessons(self):
        data = self.lessons(self.tom)
        self.assertEqual({r['group'] for r in data['rows']}, {'GA'})

    def test_period_is_limited(self):
        r = self.as_(self.ceo).get('/v1/reports/teacher-attendance/lessons',
                                   {'date_from': '2025-01-01', 'date_to': '2026-09-13'})
        self.assertEqual(r.status_code, 400)


class StudentAttendanceTests(Base):
    def test_mark_on_sunday_is_refused(self):
        ali = self.student('Ali')
        r = self.as_(self.ceo).post('/v1/reports/attendance', {
            'group_id': self.g.id, 'date': '2026-09-06', 'records': [{'student_id': ali.id, 'status': 0}],
        }, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_mark_on_holiday_is_refused_and_lesson_day_works(self):
        ali = self.student('Ali')
        Holiday.objects.create(company=self.company, branch=self.a, name='H', holiday_date=D(9))
        r = self.as_(self.ceo).post('/v1/reports/attendance', {
            'student_id': ali.id, 'group_id': self.g.id, 'date': '2026-09-09', 'status': 0,
        }, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.c.post('/v1/reports/attendance', {
            'student_id': ali.id, 'group_id': self.g.id, 'date': '2026-09-07', 'status': 0,
        }, format='json')
        self.assertEqual(r.status_code, 201)

    def test_moving_a_mark_to_a_day_without_lesson_is_refused(self):
        ali = self.student('Ali')
        rec = AttendanceRecord.objects.create(company=self.company, student=ali, group=self.g, attend_date=D(7))
        r = self.as_(self.ceo).patch(f'/v1/reports/attendance/{rec.id}', {'date': '2026-09-06'}, format='json')
        self.assertEqual(r.status_code, 400)
        # a status change on the same day is fine
        r = self.c.patch(f'/v1/reports/attendance/{rec.id}', {'status': 0}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_day_status_shows_marked_and_not_marked_groups(self):
        ali = self.student('Ali')
        self.student('Bek', group=self.gb, phone='902222222')
        AttendanceRecord.objects.create(company=self.company, student=ali, group=self.g, attend_date=D(7))
        rows = {r['group_id']: r for r in self.as_(self.ceo).get('/v1/reports/attendance/day',
                                                                 {'date': '2026-09-07'}).json()['data']}
        self.assertEqual(rows[self.g.id], {'group_id': self.g.id, 'has_lesson': True, 'marked': 1, 'students': 1})
        self.assertEqual(rows[self.gb.id]['marked'], 0)
        sunday = {r['group_id']: r for r in self.c.get('/v1/reports/attendance/day',
                                                         {'date': '2026-09-06'}).json()['data']}
        self.assertFalse(sunday[self.g.id]['has_lesson'])

    def test_month_summary_counts_absences(self):
        ali = self.student('Ali')
        bek = self.student('Bek', phone='902222222')
        for day, st in ((2, 1), (4, 0), (7, 0), (9, 2)):
            AttendanceRecord.objects.create(company=self.company, student=ali, group=self.g, attend_date=D(day), status=st)
        AttendanceRecord.objects.create(company=self.company, student=bek, group=self.g, attend_date=D(2), status=1)
        data = self.as_(self.ceo).get('/v1/reports/attendance/month',
                                      {'group_id': self.g.id, 'month': '2026-09'}).json()['data']
        self.assertEqual(len(data['days']), 13)  # Mon/Wed/Fri of September 2026
        rows = {r['student']: r for r in data['rows']}
        self.assertEqual((rows['Ali']['present'], rows['Ali']['late'], rows['Ali']['absent']), (1, 1, 2))
        self.assertEqual(rows['Ali']['percent'], 50)
        self.assertEqual(rows['Ali']['marks']['2026-09-04'], 0)
        self.assertEqual(rows['Bek']['percent'], 100)

    def test_month_summary_keeps_a_student_who_left(self):
        ali = self.student('Ali')
        AttendanceRecord.objects.create(company=self.company, student=ali, group=self.g, attend_date=D(2), status=0)
        ali.status = Student.Status.LEFT
        ali.save()
        data = self.as_(self.ceo).get('/v1/reports/attendance/month',
                                      {'group_id': self.g.id, 'month': '2026-09'}).json()['data']
        self.assertEqual([r['student'] for r in data['rows']], ['Ali'])

    def test_month_summary_of_another_teachers_group_is_hidden(self):
        r = self.as_(self.tom).get('/v1/reports/attendance/month', {'group_id': self.gb.id, 'month': '2026-09'})
        self.assertEqual(r.status_code, 404)
        r = self.as_(self.dir_b).get('/v1/reports/attendance/month', {'group_id': self.g.id, 'month': '2026-09'})
        self.assertEqual(r.status_code, 404)


class ConversionTests(Base):
    def lead(self, name, stage='trial_booked', source='Instagram', **kw):
        return Lead.objects.create(company=self.company, first_name=name, phone=f'90{abs(hash(name)) % 10**7:07d}',
                                   stage=stage, source=source, **kw)

    def make_ten(self):
        # 10 booked; 4 never came and refused, 6 came: 3 refused after the lesson, 3 enrolled
        for i in range(4):
            self.lead(f'No{i}', 'rejected')
        for i in range(3):
            lead = self.lead(f'Came{i}', 'attended', source='Telegram')
            lead.stage = 'rejected'
            lead.save()
        for i in range(3):
            self.lead(f'En{i}', 'converted', attended_trial=True)

    def test_funnel_counts_what_happened_to_every_lead(self):
        self.make_ten()
        f = self.as_(self.ceo).get('/v1/reports/conversion').json()['data']['funnel']
        self.assertEqual((f['booked'], f['came'], f['converted']), (10, 6, 3))
        self.assertEqual((f['rejected'], f['rejected_before'], f['rejected_after']), (7, 4, 3))

    def test_stage_filter_does_not_change_the_funnel(self):
        self.make_ten()
        data = self.as_(self.ceo).get('/v1/reports/conversion', {'stage': 'converted'}).json()['data']
        self.assertEqual(data['funnel']['booked'], 10)
        self.assertEqual(data['total'], 3)

    def test_by_source_and_hand_typed_sources(self):
        self.make_ten()
        self.lead('Fb', source='Facebook')
        data = self.as_(self.ceo).get('/v1/reports/conversion').json()['data']
        by = {r['source']: r for r in data['by_source']}
        self.assertEqual((by['Instagram']['total'], by['Instagram']['converted'], by['Instagram']['rate']), (7, 3, 43))
        self.assertEqual((by['Telegram']['total'], by['Telegram']['came']), (3, 3))
        self.assertIn('Facebook', data['sources'])
        only_fb = self.c.get('/v1/reports/conversion', {'source': 'Facebook'}).json()['data']
        self.assertEqual([r['full_name'] for r in only_fb['rows']], ['Fb'])

    def test_lead_date_is_tashkent_date(self):
        lead = self.lead('Night')
        # 29 Sep 02:00 in Tashkent = 28 Sep 21:00 UTC
        Lead.objects.filter(pk=lead.pk).update(created_at=datetime(2026, 9, 28, 21, 0, tzinfo=dt_tz.utc))
        data = self.as_(self.ceo).get('/v1/reports/conversion', {'date_from': '2026-09-29'}).json()['data']
        self.assertEqual(data['rows'][0]['created_at'], '2026-09-29')

    def test_active_and_archived_counts(self):
        self.lead('Act')
        self.lead('Arc', is_active=False)
        data = self.as_(self.ceo).get('/v1/reports/conversion').json()['data']
        self.assertEqual((data['total'], data['active']), (2, 1))
        arc = self.c.get('/v1/reports/conversion', {'is_active': 'false'}).json()['data']
        self.assertEqual([r['full_name'] for r in arc['rows']], ['Arc'])

    def test_branch_filter(self):
        Lead.objects.create(company=self.company, branch=self.a, first_name='InA', phone='901000001')
        Lead.objects.create(company=self.company, branch=self.b, first_name='InB', phone='901000002')
        data = self.as_(self.ceo).get('/v1/reports/conversion', {'branch_id': self.b.id}).json()['data']
        self.assertEqual([r['full_name'] for r in data['rows']], ['InB'])

    def test_old_leads_and_workly_reports_are_gone(self):
        self.as_(self.ceo)
        self.assertEqual(self.c.get('/v1/reports/leads').status_code, 404)
        self.assertEqual(self.c.get('/v1/reports/workly').status_code, 404)


class LeftStudentsTests(Base):
    def left(self):
        s = Student.objects.create(company=self.company, branch=self.a, group=self.g, first_name='Aziz',
                                   phone='901111111', trial_date=self.today - timedelta(days=120))
        s.status = Student.Status.LEFT
        s.left_at = timezone.now()
        s.save()
        return s

    def test_marketer_sees_leads_but_not_debts(self):
        self.left()
        self.as_(self.marketer)
        self.assertEqual(self.c.get('/v1/reports/conversion').status_code, 200)
        self.assertEqual(self.c.get('/v1/reports/left-students').status_code, 403)
        self.assertEqual(self.c.get('/v1/dashboard').json()['data']['unpaid_leavers'], [])

    def test_office_still_sees_left_students(self):
        self.left()
        for user in (self.ceo, self.admin):
            rows = self.as_(user).get('/v1/reports/left-students', {'status': '8'}).json()['data']['rows']
            self.assertEqual([r['full_name'] for r in rows], ['Aziz'])

    def test_bad_dates_do_not_break_the_report(self):
        self.as_(self.ceo)
        r = self.c.get('/v1/reports/left-students', {'date_from': 'abc', 'date_to': '2026-13-40'})
        self.assertEqual(r.status_code, 200)


class SubstitutionTests(Base):
    """Owner (2026-09-29): the office may mark any teacher for a lesson — one lesson is paid to one teacher."""

    def post(self, teacher, day, status=1, user=None):
        return self.as_(user or self.admin).post('/v1/reports/teacher-attendance', {
            'teacher_id': teacher.id, 'group_id': self.g.id, 'date': f'2026-09-{day:02d}', 'status': status,
        }, format='json')

    def setUp(self):
        super().setUp()
        for who in (self.tom, self.bob):
            SalarySetting.objects.create(company=self.company, teacher=who, teacher_name=who.first_name,
                                         salary_type='percent', amount=50)
        self.student('Ali')

    def test_case_a_former_teacher_is_marked_after_the_group_changed_hands(self):
        # GA was Tom's until the 15th, then it was given to Bob; Tom forgot the 9th
        self.g.teacher = self.bob
        self.g.save()
        r = self.post(self.tom, 9)
        self.assertEqual(r.status_code, 201, r.json())
        self.assertGreater(teacher_accrual(self.company, self.tom, D(1), D(30))['accrued'], 0)

    def test_old_mark_of_former_teacher_can_be_corrected(self):
        rec = TeacherAttendanceRecord.objects.create(company=self.company, teacher=self.tom, group=self.g,
                                                     attend_date=D(9), status=0)
        self.g.teacher = self.bob
        self.g.save()
        r = self.as_(self.ceo).patch(f'/v1/reports/teacher-attendance/{rec.id}', {'status': 1}, format='json')
        self.assertEqual(r.status_code, 200, r.json())

    def test_case_b_substitute_is_paid_and_the_absent_teacher_is_not(self):
        # Tom (GA's teacher) was ill on the 9th, Bob held the lesson
        r = self.post(self.bob, 9)
        self.assertEqual(r.status_code, 201, r.json())
        self.assertGreater(teacher_accrual(self.company, self.bob, D(1), D(30))['accrued'], 0)
        self.assertEqual(teacher_accrual(self.company, self.tom, D(1), D(30))['accrued'], 0)

    def test_one_lesson_is_never_paid_twice(self):
        self.assertEqual(self.post(self.tom, 9).status_code, 201)
        r = self.post(self.bob, 9)
        self.assertEqual(r.status_code, 400)
        self.assertIn('Tom', r.json()['message'])
        # «Не был» for the absent teacher is fine, then the substitute can be marked
        self.assertEqual(self.post(self.bob, 9, status=0).status_code, 201)

    def test_mark_moved_to_the_substitute(self):
        rec = TeacherAttendanceRecord.objects.create(company=self.company, teacher=self.tom, group=self.g,
                                                     attend_date=D(9), status=1)
        r = self.as_(self.admin).patch(f'/v1/reports/teacher-attendance/{rec.id}',
                                       {'teacher_id': self.bob.id, 'status': 1}, format='json')
        self.assertEqual(r.status_code, 200, r.json())
        self.assertEqual(teacher_accrual(self.company, self.tom, D(1), D(30))['accrued'], 0)
        self.assertGreater(teacher_accrual(self.company, self.bob, D(1), D(30))['accrued'], 0)

    def test_teachers_own_checkin_is_still_only_for_own_groups(self):
        r = self.as_(self.bob).post('/v1/teacher-attendance/self-checkin', {'group_id': self.g.id}, format='json')
        self.assertEqual(r.status_code, 404)
        r = self.post(self.bob, 9, user=self.bob)  # a teacher cannot mark through the office form
        self.assertEqual(r.status_code, 403)

    def test_self_checkin_after_the_office_marked_a_substitute(self):
        self.g.days = Group.Days.EVERY_DAY
        self.g.save()
        TeacherAttendanceRecord.objects.create(company=self.company, teacher=self.bob, group=self.g,
                                               attend_date=self.today, status=1)
        r = self.as_(self.tom).post('/v1/teacher-attendance/self-checkin', {'group_id': self.g.id}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(TeacherAttendanceRecord.objects.filter(teacher=self.tom).exists())
