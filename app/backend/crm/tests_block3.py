import os

from django.core.management import call_command
from django.db.models import ProtectedError
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from crm.models import Group, GroupEnrollment, GroupScheduleSlot, Lead, Student
from crm.services import days_overlap
from operations.models import AuditLogRecord
from org.models import Branch, Company, Room


class Block3ArchitectureTests(TestCase):
    """Block 3 (C1–C6): enrollment history, schedule weekdays, status aliases, branch protection, audit journal."""

    def setUp(self):
        self.client = APIClient()
        self.company = Company.objects.create(name='Block3 Co', subdomain='block3')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        self.ceo = User.objects.create_user(
            phone='998909003344',
            password='password123',
            first_name='B3',
            last_name='CEO',
            company=self.company,
            user_type=User.UserType.STAFF,
            staff_role=User.StaffRole.CEO,
        )
        self.group1 = Group.objects.create(company=self.company, branch=self.branch, name='G1')
        self.group2 = Group.objects.create(company=self.company, branch=self.branch, name='G2')
        self.client.force_authenticate(user=self.ceo)

    def _student(self, **kwargs):
        defaults = dict(
            company=self.company, branch=self.branch, first_name='Aziz', phone='901112233',
            status=Student.Status.STUDYING,
        )
        defaults.update(kwargs)
        return Student.objects.create(**defaults)

    def _open(self, student):
        return list(GroupEnrollment.objects.filter(student=student, left_date__isnull=True))

    # ── C1: history is kept on every save path ───────────────────────────
    def test_c1_direct_create_opens_enrollment(self):
        """Excel import / any ORM create path gets history via the signal."""
        student = self._student(group=self.group1)
        open_ = self._open(student)
        self.assertEqual(len(open_), 1)
        self.assertEqual(open_[0].group_id, self.group1.id)
        self.assertEqual(open_[0].status, GroupEnrollment.Status.ACTIVE)

    def test_c1_soft_delete_closes_enrollment(self):
        student = self._student(group=self.group1)
        res = self.client.delete(f'/v1/students/{student.id}')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self._open(student), [])
        closed = GroupEnrollment.objects.get(student=student, group=self.group1)
        self.assertEqual(closed.status, GroupEnrollment.Status.LEFT)
        self.assertIsNotNone(closed.left_date)

    def test_c1_lead_conversion_with_group_opens_enrollment(self):
        lead = Lead.objects.create(company=self.company, branch=self.branch, first_name='Lola', phone='901234000')
        res = self.client.post(
            f'/v1/leads/{lead.id}/convert', {'branch_id': self.branch.id, 'group_id': self.group1.id},
        )
        self.assertEqual(res.status_code, 201, res.content)
        student_id = res.json()['data']['student']['id']
        enrollment = GroupEnrollment.objects.get(student_id=student_id, left_date__isnull=True)
        self.assertEqual(enrollment.group_id, self.group1.id)

    def test_c1_paid_flag_save_does_not_touch_history(self):
        student = self._student(group=self.group1)
        before = GroupEnrollment.objects.filter(student=student).count()
        student.paid_this_month = True
        student.save(update_fields=['paid_this_month'])
        self.assertEqual(GroupEnrollment.objects.filter(student=student).count(), before)

    def test_c1_sync_command_repairs_missing_history(self):
        student = self._student(group=self.group1)
        GroupEnrollment.objects.filter(student=student).delete()
        with open(os.devnull, 'w') as devnull:
            call_command('sync_enrollments', '--dry-run', stdout=devnull)
            self.assertEqual(self._open(student), [])
            call_command('sync_enrollments', stdout=devnull)
        self.assertEqual(len(self._open(student)), 1)

    # ── C6: two bugs of the old sync function ────────────────────────────
    def test_c6_returning_student_in_same_group_gets_new_active_enrollment(self):
        student = self._student(group=self.group1)
        student.status = Student.Status.LEFT
        student.save()
        self.assertEqual(self._open(student), [])

        student.status = Student.Status.STUDYING
        student.save()
        open_ = self._open(student)
        self.assertEqual(len(open_), 1)
        self.assertEqual(open_[0].status, GroupEnrollment.Status.ACTIVE)
        self.assertEqual(GroupEnrollment.objects.filter(student=student).count(), 2)

    def test_c6_left_student_moved_to_new_group_is_not_frozen(self):
        student = self._student(group=self.group1)
        student.status = Student.Status.LEFT
        student.save()

        # Restored into another group -> ACTIVE, never FROZEN
        res = self.client.patch(
            f'/v1/students/{student.id}', {'group_id': self.group2.id, 'status': Student.Status.STUDYING},
        )
        self.assertEqual(res.status_code, 200, res.content)
        open_ = self._open(student)
        self.assertEqual(len(open_), 1)
        self.assertEqual(open_[0].group_id, self.group2.id)
        self.assertEqual(open_[0].status, GroupEnrollment.Status.ACTIVE)

        # Group changed while still LEFT -> no open enrollment at all
        other = self._student(first_name='Bek', phone='901112244', group=self.group1)
        other.status = Student.Status.LEFT
        other.save()
        other.group = self.group2
        other.save()
        self.assertEqual(self._open(other), [])

    def test_c6_freeze_and_graduate(self):
        student = self._student(group=self.group1)
        student.status = Student.Status.FROZEN
        student.save()
        self.assertEqual(self._open(student)[0].status, GroupEnrollment.Status.FROZEN)
        student.status = Student.Status.GRADUATED
        student.save()
        self.assertEqual(self._open(student), [])
        self.assertEqual(GroupEnrollment.objects.get(student=student).status, GroupEnrollment.Status.GRADUATED)

    def test_c6_transfer_marks_old_enrollment_transferred(self):
        student = self._student(group=self.group1)
        student.group = self.group2
        student.save()
        old = GroupEnrollment.objects.get(student=student, group=self.group1)
        self.assertEqual(old.status, GroupEnrollment.Status.TRANSFERRED)
        self.assertEqual(self._open(student)[0].group_id, self.group2.id)

    # ── C2: custom weekdays ──────────────────────────────────────────────
    def test_c2_custom_group_uses_explicit_weekdays(self):
        res = self.client.post('/v1/groups', {
            'name': 'Custom TT', 'branch_id': self.branch.id, 'days': Group.Days.CUSTOM,
            'weekdays': [1, 3], 'lesson_start_time': '10:00', 'lesson_end_time': '11:30',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        data = res.json()['data']
        self.assertEqual(data['weekdays'], [1, 3])
        weekdays = list(
            GroupScheduleSlot.objects.filter(group_id=data['id']).order_by('weekday').values_list('weekday', flat=True)
        )
        self.assertEqual(weekdays, [1, 3])

    def test_c2_custom_group_requires_weekdays(self):
        res = self.client.post('/v1/groups', {
            'name': 'Custom empty', 'branch_id': self.branch.id, 'days': Group.Days.CUSTOM,
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_c2_switching_away_from_custom_clears_weekdays(self):
        group = Group.objects.create(
            company=self.company, branch=self.branch, name='C', days=Group.Days.CUSTOM, weekdays=[1],
        )
        res = self.client.patch(f'/v1/groups/{group.id}', {'days': Group.Days.ODD}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        group.refresh_from_db()
        self.assertEqual(group.weekdays, [])

    def test_c2_days_overlap_uses_real_weekdays(self):
        self.assertFalse(days_overlap(Group.Days.CUSTOM, Group.Days.ODD, [1, 3], None))
        self.assertTrue(days_overlap(Group.Days.CUSTOM, Group.Days.ODD, [1, 2], None))
        self.assertFalse(days_overlap(Group.Days.CUSTOM, Group.Days.CUSTOM, [0], [6]))
        self.assertTrue(days_overlap(Group.Days.EVERY_DAY, Group.Days.CUSTOM, None, [6]))

    def test_c2_no_false_room_conflict_for_custom_group(self):
        room = Room.objects.create(branch=self.branch, name='R1')
        Group.objects.filter(pk=self.group1.pk).update(
            room=room, days=Group.Days.ODD, lesson_start_time='10:00', lesson_end_time='11:30',
        )
        payload = {
            'branch_id': self.branch.id, 'days': Group.Days.CUSTOM, 'room_id': room.id,
            'lesson_start_time': '10:00', 'lesson_end_time': '11:30',
        }
        res = self.client.post('/v1/groups', {**payload, 'name': 'Tue-Thu', 'weekdays': [1, 3]}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        # Real overlap (Monday) is still detected
        res = self.client.post('/v1/groups', {**payload, 'name': 'Mon', 'weekdays': [0]}, format='json')
        self.assertEqual(res.status_code, 409, res.content)

    # ── C3: no status aliases ────────────────────────────────────────────
    def test_c3_status_aliases_removed(self):
        for alias in ('ACTIVE', 'TRIAL', 'DEBTOR', 'LEFT_ACTIVE'):
            self.assertFalse(hasattr(Student.Status, alias), alias)
        self.assertEqual(Student._meta.get_field('status').default, Student.Status.STUDYING)

    # ── C4: branch cannot silently wipe students/groups ──────────────────
    def test_c4_branch_with_students_is_protected(self):
        self._student(group=self.group1)
        with self.assertRaises(ProtectedError):
            self.branch.delete()
        self.assertTrue(Student.objects.filter(branch=self.branch).exists())

    def test_c4_empty_branch_can_be_deleted(self):
        empty = Branch.objects.create(company=self.company, name='Empty')
        empty.delete()
        self.assertFalse(Branch.objects.filter(pk=empty.pk).exists())

    # ── C5: single audit journal ─────────────────────────────────────────
    def test_c5_lead_conversion_logged_in_audit_and_shown_in_history(self):
        lead = Lead.objects.create(company=self.company, branch=self.branch, first_name='Nodir', phone='901234111')
        res = self.client.post(f'/v1/leads/{lead.id}/convert', {'branch_id': self.branch.id})
        self.assertEqual(res.status_code, 201, res.content)
        record = AuditLogRecord.objects.get(company=self.company, entity_type='lead', entity_id=lead.id)
        self.assertEqual(record.action, 'convert')

        logs = self.client.get('/v1/history/logs').json()['data']
        self.assertTrue(any('converted to student' in row['action'] for row in logs))
