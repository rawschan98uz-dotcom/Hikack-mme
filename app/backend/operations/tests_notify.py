"""Telegram auto-notifications: run_once() must not crash (it used to fail with
NameError close_old_connections on every loop, so nothing was ever sent)."""
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from crm.models import AttendanceRecord, Course, Group, Student
from operations import notify
from operations.models import NotificationLog
from org.models import Branch, Company

ABSENT_RULE = {
    'name': 'absence',
    'type': 'attendance_absent',
    'enabled': True,
    'min_age_minutes': 0,
    'message': '{student} сегодня не был на занятии ({group}).',
}


def config(**kw):
    cfg = {'enabled': True, 'bot_token': '12345:test', 'quiet_hours': {'enabled': False}, 'rules': [ABSENT_RULE]}
    cfg.update(kw)
    return cfg


class RunOnceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Notify Co', subdomain='notify')
        self.branch = Branch.objects.create(company=self.company, name='Main')
        course = Course.objects.create(company=self.company, name='English', price=500_000)
        self.group = Group.objects.create(company=self.company, branch=self.branch, name='EN-1', course=course)
        self.student = Student.objects.create(
            company=self.company, branch=self.branch, group=self.group,
            first_name='Alisher', last_name='Karimov', phone='901234567', parent_telegram='123456789',
        )

    def test_disabled_config_does_not_crash(self):
        with patch('operations.notify.load_config', return_value={'enabled': False}):
            self.assertEqual(notify.run_once(), {'enabled': False})

    def test_absent_student_parent_gets_one_message(self):
        AttendanceRecord.objects.create(
            company=self.company, group=self.group, student=self.student,
            attend_date=timezone.localdate(), status=AttendanceRecord.Status.ABSENT,
        )
        with patch('operations.notify.load_config', return_value=config()), \
                patch('operations.notify.telegram_call', return_value=(True, {'message_id': 1})) as tg:
            summary = notify.run_once()
            self.assertEqual(summary['absence'], {'sent': 1})
            tg.assert_called_once()
            payload = tg.call_args[0][2]
            self.assertEqual(payload['chat_id'], '123456789')
            self.assertIn('Alisher Karimov', payload['text'])
            self.assertIn('EN-1', payload['text'])

            # next loop the same day must not send the message a second time
            notify.run_once()
            tg.assert_called_once()
        self.assertEqual(NotificationLog.objects.filter(student=self.student, ok=True).count(), 1)
