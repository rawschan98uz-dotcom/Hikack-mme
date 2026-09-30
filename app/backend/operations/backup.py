"""
Daily backup of the whole program and the real database to a private GitHub repository (owner, 2026-09-30).

All data lives only on this computer, so once a day — on the first request to the server that day
(opening the program, logging in, any click) — a background thread:
  1. takes a consistent copy of db.sqlite3 (SQLite backup API, safe while the server is writing);
  2. mirrors the program folder (app, runtime, launcher, media …) into a local git clone;
  3. commits and pushes it.
Restoring = clone the repository and run Start-HiJack-LMS.bat.

Enabled only when backend/backup.json exists, e.g. {"dir": "C:\\Users\\user\\HiJack-Backup"}:
  <dir>/repo            git clone of the backup repository (made once by hand, see Подключить-бэкап.bat)
  <dir>/last_success.txt date of the last successful push
  <dir>/backup.log       what happened
A failed attempt (no internet, expired GitHub login) is retried an hour later, never blocks the program.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

from django.conf import settings
from django.utils import timezone

CONFIG_FILE = Path(settings.BASE_DIR) / 'backup.json'
SOURCE_ROOT = Path(settings.BASE_DIR).parent.parent  # the program folder (…/HiJack-LMS)
DB_REL = Path('app') / 'backend' / 'db.sqlite3'
SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv'}
SKIP_SUFFIXES = ('.pyc', '.log', '.sqlite3-journal', '.sqlite3-wal', '.sqlite3-shm')
RETRY_SECONDS = 3600
GIT_TIMEOUT = 600

_lock = threading.Lock()
_running = False
_done_day = None       # day already backed up (cached, so normal requests cost nothing)
_next_try = 0.0        # monotonic time before which a failed backup is not retried


def _config() -> dict | None:
    if 'runserver' not in sys.argv:
        return None  # tests, migrate, shell …
    return read_config()


def read_config() -> dict | None:
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None
    return cfg if cfg.get('dir') else None


def _log(base: Path, text: str) -> None:
    stamp = timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(base / 'backup.log', 'a', encoding='utf-8') as f:
            f.write(f'{stamp} {text}\n')
    except OSError:
        pass


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, GCM_INTERACTIVE='never', GIT_TERMINAL_PROMPT='0')
    return subprocess.run(
        [shutil.which('git') or 'git', *args],
        cwd=repo, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=GIT_TIMEOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )


def _skip(rel: Path) -> bool:
    return any(part in SKIP_DIRS for part in rel.parts) or rel.name.endswith(SKIP_SUFFIXES) or rel == DB_REL


def mirror(source: Path, target: Path) -> None:
    """Make `target` a copy of `source` (except .git and skipped files); only changed files are copied."""
    wanted = set()
    for dirpath, dirnames, filenames in os.walk(source):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            src = Path(dirpath) / name
            rel = src.relative_to(source)
            if _skip(rel):
                continue
            wanted.add(rel)
            dst = target / rel
            st = src.stat()
            if dst.exists():
                dt = dst.stat()
                if dt.st_size == st.st_size and int(dt.st_mtime) == int(st.st_mtime):
                    continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if d != '.git']
        for name in filenames:
            rel = (Path(dirpath) / name).relative_to(target)
            if rel not in wanted and rel != DB_REL and rel.name != '.gitattributes':
                (target / rel).unlink()


def copy_database(db_path: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def run_backup(base: Path) -> bool:
    repo = base / 'repo'
    if not (repo / '.git').is_dir():
        _log(base, f'ОШИБКА: нет клона репозитория в {repo} — запустите Подключить-бэкап.bat')
        return False

    mirror(SOURCE_ROOT, repo)
    copy_database(Path(settings.DATABASES['default']['NAME']), repo / DB_REL)
    attrs = repo / '.gitattributes'
    if not attrs.exists():
        attrs.write_text('*.sqlite3 binary\n', encoding='utf-8')

    if not _git(repo, 'config', 'user.email').stdout.strip():
        _git(repo, 'config', 'user.email', 'backup@hijack-lms.local')
        _git(repo, 'config', 'user.name', 'HiJack LMS backup')
    _git(repo, 'add', '-A')
    if _git(repo, 'status', '--porcelain').stdout.strip():
        stamp = timezone.localtime().strftime('%Y-%m-%d %H:%M')
        res = _git(repo, 'commit', '-q', '-m', f'Бэкап {stamp}')
        if res.returncode != 0:
            _log(base, f'ОШИБКА commit: {res.stderr.strip()[:500]}')
            return False
    res = _git(repo, 'push', '-q', 'origin', 'HEAD:main')
    if res.returncode != 0:
        _log(base, f'ОШИБКА push (нет интернета или истёк вход в GitHub): {res.stderr.strip()[:500]}')
        return False
    return True


def _worker(base: Path, today) -> None:
    global _running, _done_day, _next_try
    try:
        base.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        if run_backup(base):
            (base / 'last_success.txt').write_text(today.isoformat(), encoding='utf-8')
            _done_day = today
            _log(base, f'OK за {time.monotonic() - started:.0f} с')
        else:
            _next_try = time.monotonic() + RETRY_SECONDS
    except Exception:
        _next_try = time.monotonic() + RETRY_SECONDS
        _log(base, 'ОШИБКА:\n' + traceback.format_exc())
    finally:
        with _lock:
            _running = False


def maybe_start() -> None:
    """Start today's backup in the background if it has not been made yet. Cheap after the first call."""
    global _running, _done_day
    today = timezone.localdate()
    if _done_day == today or time.monotonic() < _next_try:
        return
    cfg = _config()
    if cfg is None:
        _done_day = today  # not configured: look again tomorrow
        return
    base = Path(cfg['dir'])
    try:
        if (base / 'last_success.txt').read_text(encoding='utf-8').strip() == today.isoformat():
            _done_day = today
            return
    except OSError:
        pass
    with _lock:
        if _running:
            return
        _running = True
    threading.Thread(target=_worker, args=(base, today), name='daily-backup', daemon=True).start()


class DailyBackupMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            maybe_start()
        except Exception:
            pass  # a backup problem must never break a page
        return self.get_response(request)
