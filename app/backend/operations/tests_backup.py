import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from accounts.models import User
from operations import backup
from operations.models import Reminder
from org.models import Company


class BackupReminderTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Bk Co', subdomain='bkco')
        self.ceo = User.objects.create_user(
            phone='998907771001', password=None, first_name='Ceo', company=self.company,
            user_type=User.UserType.STAFF, staff_role=User.StaffRole.CEO,
        )
        self.today = timezone.localdate()
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def succeeded(self, days_ago):
        (self.base / 'last_success.txt').write_text((self.today - timedelta(days=days_ago)).isoformat())

    def open_reminders(self):
        return Reminder.objects.filter(kind=Reminder.KIND_BACKUP_FAILED).exclude(status=Reminder.Status.DONE)

    def test_no_reminder_while_backup_is_recent(self):
        self.succeeded(2)
        backup.warn_if_stale(self.base, self.today)
        self.assertFalse(self.open_reminders().exists())

    def test_ceo_is_warned_once_after_three_days(self):
        self.succeeded(3)
        backup.warn_if_stale(self.base, self.today)
        backup.warn_if_stale(self.base, self.today)  # the hourly retry does not duplicate it
        reminder = self.open_reminders().get()
        self.assertEqual(reminder.assigned_to, self.ceo)
        self.assertEqual(reminder.due_date, self.today)

    def test_closed_by_hand_is_not_recreated_the_same_day(self):
        self.succeeded(5)
        backup.warn_if_stale(self.base, self.today)
        self.open_reminders().update(status=Reminder.Status.DONE)
        backup.warn_if_stale(self.base, self.today)
        self.assertFalse(self.open_reminders().exists())

    def test_success_closes_the_warning(self):
        self.succeeded(4)
        backup.warn_if_stale(self.base, self.today)
        backup.mark_success(self.base, self.today)
        self.assertFalse(self.open_reminders().exists())
        self.assertEqual(backup.last_success(self.base), self.today)
        self.assertIn('закрыто автоматически', Reminder.objects.get(kind=Reminder.KIND_BACKUP_FAILED).resolution)


class BackupTests(SimpleTestCase):
    def test_disabled_outside_runserver(self):
        # tests / migrate / shell never back up, even when backup.json exists
        with mock.patch.object(backup, 'CONFIG_FILE', Path('does-not-matter.json')):
            self.assertIsNone(backup._config())

    def test_mirror_copies_changes_and_removes_deleted_files(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            src, dst = Path(src), Path(dst)
            (src / 'app' / 'backend' / '__pycache__').mkdir(parents=True)
            (src / 'app' / 'backend' / 'views.py').write_text('v1')
            (src / 'app' / 'backend' / '__pycache__' / 'x.pyc').write_text('skip')
            (src / 'app' / 'backend' / 'db.sqlite3').write_text('copied separately')
            (dst / '.git').mkdir()
            (dst / '.git' / 'HEAD').write_text('keep')
            (dst / 'old.txt').write_text('gone from the program')

            backup.mirror(src, dst)

            self.assertEqual((dst / 'app' / 'backend' / 'views.py').read_text(), 'v1')
            self.assertFalse((dst / 'app' / 'backend' / '__pycache__').exists())
            self.assertFalse((dst / 'app' / 'backend' / 'db.sqlite3').exists())
            self.assertFalse((dst / 'old.txt').exists())
            self.assertEqual((dst / '.git' / 'HEAD').read_text(), 'keep')

    def test_copy_database_is_a_readable_sqlite_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            con = sqlite3.connect(tmp / 'db.sqlite3')
            con.execute('create table t (x)')
            con.execute('insert into t values (42)')
            con.commit()
            con.close()

            backup.copy_database(tmp / 'db.sqlite3', tmp / 'out' / 'db.sqlite3')

            copy = sqlite3.connect(tmp / 'out' / 'db.sqlite3')
            self.assertEqual(copy.execute('select x from t').fetchone(), (42,))
            copy.close()
