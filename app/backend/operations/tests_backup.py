import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from operations import backup


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
