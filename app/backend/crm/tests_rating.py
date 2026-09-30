"""Rating audit (2026-09-28): whole points, only students who study now, grades follow the student, edit = points only."""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import TeacherBranch, User
from crm.models import Course, Group, Student
from operations.models import StudentScore
from org.models import Branch, Company


class Base(TestCase):
    def setUp(self):
        self.c = APIClient()
        self.company = Company.objects.create(name='Rate Co', subdomain='rateco')
        self.b1 = Branch.objects.create(company=self.company, name='B1')
        self.b2 = Branch.objects.create(company=self.company, name='B2')
        self.ceo = User.objects.create_user(
            phone='998906660001', password='x', first_name='Ceo', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.t1 = User.objects.create_user(
            phone='998906660002', password='x', first_name='T1', company=self.company, user_type=User.UserType.TEACHER,
        )
        self.t2 = User.objects.create_user(
            phone='998906660003', password='x', first_name='T2', company=self.company, user_type=User.UserType.TEACHER,
        )
        TeacherBranch.objects.create(teacher=self.t1, branch=self.b1)
        TeacherBranch.objects.create(teacher=self.t2, branch=self.b1)
        course = Course.objects.create(company=self.company, name='En', price=100)
        # Every day: a grade needs a lesson of the group that day, whatever weekday the tests run on
        every = Group.Days.EVERY_DAY
        self.g1 = Group.objects.create(
            company=self.company, branch=self.b1, name='G1', course=course, teacher=self.t1, days=every,
        )
        self.g2 = Group.objects.create(
            company=self.company, branch=self.b1, name='G2', course=course, teacher=self.t2, days=every,
        )
        self.g3 = Group.objects.create(company=self.company, branch=self.b2, name='G3', course=course, days=every)
        self.ali = self.student('Ali', self.g1, '901000001')
        self.bek = self.student('Bek', self.g1, '901000002')
        self.cem = self.student('Cem', self.g2, '901000003')

    def student(self, name, group, phone):
        return Student.objects.create(
            company=self.company, branch=group.branch, group=group, first_name=name, phone=phone,
        )

    def as_(self, user):
        self.c.force_authenticate(user)
        return self.c

    def grade(self, student, group, value, user=None):
        return self.as_(user or self.ceo).post(
            '/v1/scores/branch', {'student_id': student.id, 'group_id': group.id, 'grade': value}, format='json',
        )

    def rating(self):
        return self.as_(self.ceo).get('/v1/scores/branch').json()['data']['rows']


class WholePointsTests(Base):
    def test_fractions_and_garbage_are_rejected(self):
        for bad in (99.9, '1.1', 'abc', 'nan', 'inf', None, 101, -1):
            res = self.grade(self.ali, self.g1, bad)
            self.assertEqual(res.status_code, 400, (bad, res.content))
        self.assertFalse(StudentScore.objects.exists())

    def test_whole_points_are_saved(self):
        self.assertEqual(self.grade(self.ali, self.g1, 85).status_code, 201)
        self.assertEqual(self.grade(self.bek, self.g1, '70').status_code, 201)
        self.assertEqual(self.grade(self.cem, self.g2, 60.0).status_code, 201)  # 60.0 is still a whole number
        self.assertEqual(sorted(StudentScore.objects.values_list('grade', flat=True)), [60, 70, 85])

    def test_bulk_skips_fractions(self):
        res = self.as_(self.ceo).post('/v1/scores/bulk', {'group_id': self.g1.id, 'items': [
            {'student_id': self.ali.id, 'grade': 90}, {'student_id': self.bek.id, 'grade': 55.5},
        ]}, format='json')
        self.assertEqual(res.json()['data']['saved_count'], 1)

    def test_edit_rejects_fraction(self):
        sid = self.grade(self.ali, self.g1, 80).json()['data']['id']
        self.assertEqual(self.c.patch(f'/v1/scores/{sid}', {'grade': 80.5}, format='json').status_code, 400)

    def test_grade_settings_reject_garbage_instead_of_crashing(self):
        c = self.as_(self.ceo)
        self.assertEqual(c.post('/v1/company/settings', {'grade_pass_score': 'abc'}, format='json').status_code, 400)
        self.assertEqual(c.post('/v1/company/settings', {'grade_scale_max': '10.5'}, format='json').status_code, 400)
        res = c.post('/v1/company/settings', {'grade_pass_score': 60, 'grade_scale_max': 100}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['data']['grade_pass_score'], 60)


class LeftCentreTests(Base):
    def test_student_who_left_disappears_from_rating_and_averages(self):
        self.grade(self.ali, self.g1, 95)
        self.grade(self.bek, self.g1, 50)
        self.as_(self.ceo).patch(f'/v1/students/{self.ali.id}', {'status': Student.Status.LEFT})
        rows = self.rating()
        self.assertEqual([(r['name'], r['no'], r['rank_in_group']) for r in rows], [('Bek', 1, 1)])
        g1 = [g for g in self.c.get('/v1/scores/groups').json()['data'] if g['group_id'] == self.g1.id][0]
        self.assertEqual(g1['avg_grade'], 50)
        self.assertEqual(g1['graded_count'], 1)
        # the grade itself is kept: if the student comes back, it is there again
        self.assertTrue(StudentScore.objects.filter(student=self.ali).exists())

    def test_frozen_student_leaves_rating_until_unfrozen(self):
        self.grade(self.ali, self.g1, 95)
        self.grade(self.bek, self.g1, 60)
        self.as_(self.ceo).patch(f'/v1/students/{self.ali.id}', {'status': Student.Status.FROZEN})
        self.assertEqual([(r['name'], r['rank_in_group']) for r in self.rating()], [('Bek', 1)])
        g1 = [g for g in self.c.get('/v1/scores/groups').json()['data'] if g['group_id'] == self.g1.id][0]
        self.assertEqual((g1['graded_count'], g1['enrolled_count']), (1, 1))  # only Bek studies now
        self.assertEqual(self.grade(self.ali, self.g1, 80).status_code, 400)  # no grade while frozen

    def test_left_student_cannot_be_graded(self):
        self.as_(self.ceo).patch(f'/v1/students/{self.ali.id}', {'status': Student.Status.LEFT})
        self.assertEqual(self.grade(self.ali, self.g1, 80).status_code, 400)


class GradesFollowStudentTests(Base):
    def test_moved_to_other_group_takes_grade_along(self):
        self.grade(self.ali, self.g1, 95)
        self.grade(self.bek, self.g1, 60)
        self.as_(self.ceo).patch(f'/v1/students/{self.ali.id}', {'group_id': self.g2.id})
        rows = {r['name']: (r['group'], r['rank_in_group']) for r in self.rating()}
        self.assertEqual(rows['Ali'], ('G2', 1))
        self.assertEqual(rows['Bek'], ('G1', 1))  # Bek is alone in G1 now -> first place

    def test_moved_to_other_branch_takes_grade_along(self):
        self.grade(self.ali, self.g1, 95)
        self.as_(self.ceo).patch(f'/v1/students/{self.ali.id}', {'group_id': self.g3.id})
        row = [r for r in self.rating() if r['name'] == 'Ali'][0]
        self.assertEqual((row['group'], row['branch']), ('G3', 'B2'))

    def test_back_to_old_group_latest_grade_wins(self):
        self.grade(self.ali, self.g1, 95)
        self.as_(self.ceo).patch(f'/v1/students/{self.ali.id}', {'group_id': self.g2.id})
        self.grade(self.ali, self.g2, 70)  # new test in the new group overwrites
        self.as_(self.ceo).patch(f'/v1/students/{self.ali.id}', {'group_id': self.g1.id})
        self.assertEqual(list(StudentScore.objects.filter(student=self.ali).values_list('group__name', 'grade')),
                         [('G1', 70)])


class EditOnlyPointsTests(Base):
    def test_edit_cannot_move_grade_to_other_group_or_student(self):
        sid = self.grade(self.ali, self.g1, 80, user=self.t1).json()['data']['id']
        c = self.as_(self.t1)
        # teacher 1 tried to move the grade into teacher 2's group / another student
        self.assertEqual(c.patch(f'/v1/scores/{sid}', {'group_id': self.g2.id}, format='json').status_code, 400)
        self.assertEqual(c.patch(f'/v1/scores/{sid}', {'student_id': self.cem.id}, format='json').status_code, 400)
        score = StudentScore.objects.get(pk=sid)
        self.assertEqual((score.group_id, score.student_id), (self.g1.id, self.ali.id))

    def test_edit_points_works_and_same_ids_are_fine(self):
        sid = self.grade(self.ali, self.g1, 80).json()['data']['id']
        res = self.c.patch(f'/v1/scores/{sid}', {'grade': 90, 'student_id': self.ali.id, 'group_id': self.g1.id},
                           format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['grade'], 90)


class HistoryTests(Base):
    def history(self, student):
        return self.as_(self.ceo).get('/v1/scores/history', {'student_id': student.id}).json()['data']

    def test_new_grade_replaces_rating_but_old_one_stays_in_history(self):
        self.grade(self.ali, self.g1, 70)
        self.grade(self.ali, self.g1, 90)
        self.assertEqual([r['grade'] for r in self.rating()], [90])
        rows = self.history(self.ali)
        self.assertEqual([r['grade'] for r in rows], [90, 70])
        self.assertEqual(rows[0]['group'], 'G1')
        self.assertEqual(rows[0]['course'], 'En')
        self.assertEqual(rows[0]['student'], 'Ali')

    def test_edit_fixes_the_latest_record_and_marks_it(self):
        self.grade(self.ali, self.g1, 70)
        sid = self.grade(self.ali, self.g1, 58).json()['data']['id']
        self.c.patch(f'/v1/scores/{sid}', {'grade': 85}, format='json')
        rows = self.history(self.ali)
        self.assertEqual([(r['grade'], r['corrected']) for r in rows], [(85, True), (70, False)])

    def test_history_keeps_old_group_name_after_transfer(self):
        self.grade(self.ali, self.g1, 70)
        self.as_(self.ceo).patch(f'/v1/students/{self.ali.id}', {'group_id': self.g2.id})
        self.grade(self.ali, self.g2, 88)
        self.assertEqual([(r['group'], r['grade']) for r in self.history(self.ali)], [('G2', 88), ('G1', 70)])

    def test_teacher_sees_history_only_of_own_students(self):
        self.grade(self.cem, self.g2, 70)
        self.assertEqual(self.as_(self.t1).get('/v1/scores/history', {'student_id': self.cem.id}).status_code, 404)
        self.assertEqual(self.as_(self.t2).get('/v1/scores/history', {'student_id': self.cem.id}).status_code, 200)

    def test_deleting_a_mistaken_grade_removes_it_but_keeps_earlier_ones(self):
        self.grade(self.ali, self.g1, 70)
        sid = self.grade(self.ali, self.g1, 5).json()['data']['id']
        self.c.delete(f'/v1/scores/{sid}')
        self.assertEqual([r['grade'] for r in self.history(self.ali)], [70])


class AbsentTodayTests(Base):
    def mark_absent(self, student, group):
        from django.utils import timezone
        from crm.models import AttendanceRecord
        AttendanceRecord.objects.create(
            company=self.company, group=group, student=student, attend_date=timezone.localdate(),
            status=AttendanceRecord.Status.ABSENT,
        )

    def test_absent_today_cannot_be_graded(self):
        self.mark_absent(self.ali, self.g1)
        res = self.grade(self.ali, self.g1, 90)
        self.assertEqual(res.status_code, 400)
        self.assertIn('отсутствует', res.json()['message'])

    def test_sheet_shows_absent_and_frozen_as_not_gradable(self):
        self.mark_absent(self.ali, self.g1)
        extra = self.student('Zed', self.g1, '901000009')
        self.as_(self.ceo).patch(f'/v1/students/{extra.id}', {'status': Student.Status.FROZEN})
        rows = {r['name']: (r['can_grade'], r['reason_label']) for r in
                self.c.get('/v1/scores/sheet', {'group_id': self.g1.id}).json()['data']['students']}
        self.assertEqual(rows['Ali'], (False, 'Отсутствует на уроке'))
        self.assertEqual(rows['Zed'], (False, 'Заморозка'))
        self.assertEqual(rows['Bek'], (True, ''))

    def test_sheet_saves_only_filled_boxes_and_skips_absent(self):
        self.mark_absent(self.ali, self.g1)
        extra = self.student('Zed', self.g1, '901000009')
        res = self.as_(self.ceo).post('/v1/scores/bulk', {'group_id': self.g1.id, 'items': [
            {'student_id': self.ali.id, 'grade': 90},     # absent today
            {'student_id': self.bek.id, 'grade': 75},
            {'student_id': extra.id, 'grade': None},      # empty box = not graded
        ]}, format='json').json()['data']
        self.assertEqual(res['saved_count'], 1)
        self.assertEqual(len(res['skipped']), 1)
        self.assertEqual(list(StudentScore.objects.values_list('student__first_name', 'grade')), [('Bek', 75)])

    def test_teacher_cannot_open_sheet_of_other_group(self):
        self.assertEqual(self.as_(self.t1).get('/v1/scores/sheet', {'group_id': self.g2.id}).status_code, 403)


class PlacesTests(Base):
    def test_equal_points_share_a_place_and_next_follows(self):
        dan = self.student('Dan', self.g1, '901000010')
        self.grade(self.ali, self.g1, 80)
        self.grade(self.bek, self.g1, 80)
        self.grade(dan, self.g1, 70)
        places = {r['name']: (r['no'], r['rank_in_group']) for r in self.rating()}
        self.assertEqual(places, {'Ali': (1, 1), 'Bek': (1, 1), 'Dan': (2, 2)})

    def test_card_shows_overall_and_group_place(self):
        self.grade(self.cem, self.g2, 99)   # best in the company, other group
        self.grade(self.ali, self.g1, 90)
        sid = self.grade(self.bek, self.g1, 80).json()['data']['id']
        card = self.as_(self.ceo).get(f'/v1/scores/{sid}').json()['data']
        self.assertEqual((card['no'], card['rank_in_group']), (3, 2))

    def test_pass_score_cannot_exceed_maximum(self):
        res = self.as_(self.ceo).post(
            '/v1/company/settings', {'grade_pass_score': 150, 'grade_scale_max': 100}, format='json',
        )
        self.assertEqual(res.status_code, 400)
        self.company.refresh_from_db()
        self.assertEqual(self.company.grade_pass_score, 70)


class LessonDateTests(Base):
    """Owner (2026-09-28): grades for today's lesson or one of the group's lessons of the last 7 days."""

    def setUp(self):
        super().setUp()
        from datetime import timedelta
        from django.utils import timezone
        self.today = timezone.localdate()
        self.day = lambda n: (self.today - timedelta(days=n))

    def grade_on(self, student, group, value, day, user=None):
        return self.as_(user or self.ceo).post('/v1/scores/branch', {
            'student_id': student.id, 'group_id': group.id, 'grade': value, 'lesson_date': day.isoformat(),
        }, format='json')

    def history(self, student):
        return self.as_(self.ceo).get('/v1/scores/history', {'student_id': student.id}).json()['data']

    def test_past_lesson_within_7_days_goes_to_history_with_that_date(self):
        res = self.grade_on(self.ali, self.g1, 80, self.day(3))
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(self.history(self.ali)[0]['date'], self.day(3).isoformat())

    def test_older_than_7_days_or_future_is_rejected(self):
        from datetime import timedelta
        self.assertEqual(self.grade_on(self.ali, self.g1, 80, self.day(8)).status_code, 400)
        self.assertEqual(self.grade_on(self.ali, self.g1, 80, self.today + timedelta(days=1)).status_code, 400)

    def test_only_days_of_the_group_schedule(self):
        weekday = self.day(2).weekday()
        self.g1.days = Group.Days.CUSTOM
        self.g1.weekdays = [weekday]  # one lesson a week: two days ago
        self.g1.save()
        self.assertEqual(self.grade_on(self.ali, self.g1, 80, self.day(2)).status_code, 201)
        res = self.grade_on(self.bek, self.g1, 80, self.day(1))
        self.assertEqual(res.status_code, 400)
        self.assertIn('день урока', res.json()['message'])
        # the sheet offers only that day
        sheet = self.c.get('/v1/scores/sheet', {'group_id': self.g1.id}).json()['data']
        self.assertEqual([d['date'] for d in sheet['lesson_dates']], [self.day(2).isoformat()])
        self.assertEqual(sheet['date'], self.day(2).isoformat())

    def test_branch_holiday_is_not_a_lesson(self):
        from operations.models import Holiday
        Holiday.objects.create(company=self.company, branch=self.b1, name='Bayram', holiday_date=self.day(1))
        self.assertEqual(self.grade_on(self.ali, self.g1, 80, self.day(1)).status_code, 400)

    def test_absent_that_day_cannot_get_grade_for_it(self):
        from crm.models import AttendanceRecord
        AttendanceRecord.objects.create(
            company=self.company, group=self.g1, student=self.ali, attend_date=self.day(2),
            status=AttendanceRecord.Status.ABSENT,
        )
        res = self.grade_on(self.ali, self.g1, 80, self.day(2))
        self.assertEqual(res.status_code, 400)
        self.assertIn('не был на уроке', res.json()['message'])
        self.assertEqual(self.grade_on(self.ali, self.g1, 80, self.day(1)).status_code, 201)  # other lesson is fine
        sheet = self.c.get('/v1/scores/sheet', {'group_id': self.g1.id, 'date': self.day(2).isoformat()}).json()['data']
        ali = [r for r in sheet['students'] if r['name'] == 'Ali'][0]
        self.assertEqual((ali['can_grade'], ali['reason_label']), (False, 'Отсутствует на уроке'))

    def test_grade_for_an_earlier_lesson_does_not_replace_the_latest_one(self):
        self.grade_on(self.ali, self.g1, 90, self.day(1))
        self.grade_on(self.ali, self.g1, 60, self.day(5))   # entered later, but for an older lesson
        self.assertEqual([r['grade'] for r in self.rating()], [90])
        self.assertEqual([(r['date'], r['grade']) for r in self.history(self.ali)],
                         [(self.day(1).isoformat(), 90), (self.day(5).isoformat(), 60)])

    def test_bulk_with_lesson_date(self):
        res = self.as_(self.ceo).post('/v1/scores/bulk', {
            'group_id': self.g1.id, 'lesson_date': self.day(4).isoformat(),
            'items': [{'student_id': self.ali.id, 'grade': 77}],
        }, format='json').json()['data']
        self.assertEqual(res['saved_count'], 1)
        self.assertEqual(self.history(self.ali)[0]['date'], self.day(4).isoformat())

    def test_group_without_lessons_this_week(self):
        self.g1.group_start_date = self.today + __import__('datetime').timedelta(days=10)
        self.g1.save()
        sheet = self.as_(self.ceo).get('/v1/scores/sheet', {'group_id': self.g1.id}).json()['data']
        self.assertIsNone(sheet['date'])
        self.assertEqual(sheet['lesson_dates'], [])
        self.assertTrue(all(not r['can_grade'] for r in sheet['students']))


class AbsentOnPastLessonTests(Base):
    """Owner's case: absent on Monday, the teacher remembers on Friday — still no grade for Monday."""

    grade_on = LessonDateTests.grade_on

    def setUp(self):
        super().setUp()
        from datetime import timedelta
        from django.utils import timezone
        from crm.models import AttendanceRecord
        today = timezone.localdate()
        self.day = lambda n: (today - timedelta(days=n))
        self.monday = self.day(4)
        AttendanceRecord.objects.create(
            company=self.company, group=self.g1, student=self.ali, attend_date=self.monday,
            status=AttendanceRecord.Status.ABSENT,
        )

    def test_add_grade_later_for_the_missed_lesson_is_refused(self):
        res = self.grade_on(self.ali, self.g1, 85, self.monday, user=self.t1)
        self.assertEqual(res.status_code, 400)
        self.assertFalse(StudentScore.objects.filter(student=self.ali).exists())

    def test_sheet_later_for_the_missed_lesson_skips_him(self):
        c = self.as_(self.t1)
        sheet = c.get('/v1/scores/sheet', {'group_id': self.g1.id, 'date': self.monday.isoformat()}).json()['data']
        ali = [r for r in sheet['students'] if r['name'] == 'Ali'][0]
        self.assertFalse(ali['can_grade'])
        res = c.post('/v1/scores/bulk', {
            'group_id': self.g1.id, 'lesson_date': self.monday.isoformat(),
            'items': [{'student_id': self.ali.id, 'grade': 85}, {'student_id': self.bek.id, 'grade': 70}],
        }, format='json').json()['data']
        self.assertEqual(res['saved_count'], 1)  # only Bek, who was there
        self.assertEqual(list(StudentScore.objects.values_list('student__first_name', flat=True)), ['Bek'])

    def test_other_lessons_are_fine(self):
        self.assertEqual(self.grade_on(self.ali, self.g1, 85, self.day(1), user=self.t1).status_code, 201)

    def test_teacher_cannot_change_that_attendance_to_get_round_it(self):
        from crm.models import AttendanceRecord
        record = AttendanceRecord.objects.get(student=self.ali, attend_date=self.monday)
        c = self.as_(self.t1)
        self.assertEqual(c.patch(f'/v1/reports/attendance/{record.id}', {'status': 1}, format='json').status_code, 403)
        self.assertEqual(self.grade_on(self.ali, self.g1, 85, self.monday, user=self.t1).status_code, 400)
