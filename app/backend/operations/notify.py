# -*- coding: utf-8 -*-
"""Telegram notification engine for Hi Jack LMS.

Rules are configured in backend/notifications.json (not in the UI).
Each rule entry looks like:

    {
      "name": "absence",
      "type": "attendance_absent",
      "enabled": true,
      "message": "...",
      ...type-specific params...
    }

Supported rule types:
  attendance_absent  - parent gets a message when the student was marked absent
                       params: min_age_minutes (wait before sending, so the
                       teacher can fix mistakes)
  payment_due        - reminder that the next payment date is coming
                       params: days_before
  payment_overdue    - payment date has passed
                       params: days_after, every_days

The next payment date is calculated from the last payment: same day of
month, next month (Jan 31 -> Feb 28). Payments are matched to students
by the student name stored in finance.Payment.student_name.
"""
import calendar
import json
import os
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.db.models import Count, Max, Min, Sum
from django.utils import timezone

from crm.models import AttendanceRecord, Student
from finance.models import Payment
from operations.models import NotificationLog
from org.models import Company

DEFAULT_CONFIG = {
    'enabled': False,
    'bot_token': '',
    'poll_interval_minutes': 10,
    'quiet_hours': {'enabled': False, 'from': '21:00', 'to': '09:00'},
    'rules': [],
}


def _config_path() -> Path:
    return Path(getattr(settings, 'NOTIFICATIONS_CONFIG', None) or (Path(settings.BASE_DIR) / 'notifications.json'))


def load_config() -> dict:
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    path = _config_path()
    try:
        raw = path.read_text(encoding='utf-8-sig')
    except OSError:
        return config
    try:
        data = json.loads(raw)
    except ValueError as exc:
        print(f'[notifications] invalid JSON in {path}: {exc}', flush=True)
        return config
    if isinstance(data, dict):
        for key, value in data.items():
            if key != 'rules':
                config[key] = value
        rules = data.get('rules')
        config['rules'] = rules if isinstance(rules, list) else []
    return config


class _SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'


def _fmt(template: str, ctx: dict) -> str:
    try:
        return str(template).format_map(_SafeDict(**ctx))
    except Exception:
        return str(template)


def _fmt_date(value) -> str:
    return value.strftime('%d.%m.%Y') if value else '-'


def telegram_call(token: str, method: str, payload: dict):
    """Call the Telegram Bot API. Returns (ok, result_or_error_text)."""
    if not token:
        return False, 'bot_token is not set'
    url = f'https://api.telegram.org/bot{token}/{method}'
    body = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode('utf-8'))
        except Exception:
            return False, f'HTTP {exc.code}'
        return False, str(data.get('description') or f'HTTP {exc.code}')
    except Exception as exc:
        return False, str(exc)
    if data.get('ok'):
        return True, data.get('result')
    return False, str(data.get('description') or 'unknown error')


_bot_username_cache = {'token': None, 'username': None, 'expires': 0.0}


def get_bot_username(token: str, ttl_seconds: float = 300):
    import time as _time

    now = _time.monotonic()
    cached = _bot_username_cache
    if cached['username'] and cached['token'] == token and now < cached['expires']:
        return cached['username']
    ok, me = telegram_call(token, 'getMe', {})
    username = me.get('username') if ok and isinstance(me, dict) else None
    cached.update({'token': token, 'username': username, 'expires': now + ttl_seconds})
    return username


def _resolve_target(raw: str):
    target = (raw or '').strip()
    if not target:
        return None
    if target.lstrip('+').isdigit():
        return target.lstrip('+')
    if target.startswith('@'):
        return target
    return '@' + target.lstrip('@')


def _student_ctx(student, extra: dict | None = None) -> dict:
    ctx = {
        'student': student.full_name,
        'first_name': student.first_name,
        'group': student.group.name if student.group_id else '-',
        'branch': student.branch.name if student.branch_id else '-',
        'school': student.school or '-',
        'phone': student.phone,
    }
    if extra:
        ctx.update(extra)
    return ctx


def _send(config: dict, student, rule: dict, trigger_date: date, ctx: dict) -> bool:
    target = _resolve_target(student.parent_telegram)
    if target is None:
        return False  # parents' telegram is not filled in yet for this student
    already = NotificationLog.objects.filter(
        student=student,
        rule=rule.get('name', '?'),
        trigger_date=trigger_date,
        ok=True,
    ).exists()
    if already:
        return True
    message = _fmt(rule.get('message', ''), ctx)
    ok, result = telegram_call(config.get('bot_token', ''), 'sendMessage', {
        'chat_id': target,
        'text': message,
        'disable_web_page_preview': True,
    })
    NotificationLog.objects.create(
        company=student.company,
        student=student,
        rule=rule.get('name', '?'),
        trigger_date=trigger_date,
        target=target,
        message=message,
        ok=ok,
        error='' if ok else str(result),
    )
    if not ok:
        print(f'[notifications] {rule.get("name")} -> {target}: {result}', flush=True)
    return ok


def _add_months(d: date, num_months: int) -> date:
    year = d.year + (d.month - 1 + num_months) // 12
    month = (d.month - 1 + num_months) % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, max_day))


def _payments_summary(company) -> dict:
    rows = (
        Payment.objects.filter(company=company)
        .values('student_id', 'student_name')
        .annotate(
            count=Count('id'),
            total_months=Sum('months_covered'),
            last_created=Max('created_at'),
            first_created=Min('created_at'),
        )
    )
    summary = {}
    for r in rows:
        item = {
            'count': r['count'],
            'months_covered': r['total_months'] or r['count'],
            'last_date': timezone.localtime(r['last_created']).date() if r['last_created'] else None,
            'first_date': timezone.localtime(r['first_created']).date() if r['first_created'] else None,
        }
        if r['student_id']:
            sid = r['student_id']
            if sid in summary:
                summary[sid]['count'] += item['count']
                summary[sid]['months_covered'] += item['months_covered']
                if item['last_date'] and (not summary[sid]['last_date'] or item['last_date'] > summary[sid]['last_date']):
                    summary[sid]['last_date'] = item['last_date']
                if item['first_date'] and (not summary[sid]['first_date'] or item['first_date'] < summary[sid]['first_date']):
                    summary[sid]['first_date'] = item['first_date']
            else:
                summary[sid] = dict(item)
        if r['student_name']:
            sname = r['student_name']
            if sname in summary:
                summary[sname]['count'] += item['count']
                summary[sname]['months_covered'] += item['months_covered']
                if item['last_date'] and (not summary[sname]['last_date'] or item['last_date'] > summary[sname]['last_date']):
                    summary[sname]['last_date'] = item['last_date']
                if item['first_date'] and (not summary[sname]['first_date'] or item['first_date'] < summary[sname]['first_date']):
                    summary[sname]['first_date'] = item['first_date']
            else:
                summary[sname] = dict(item)
    return summary


def _student_due(student, payments: dict):
    info = payments.get(student.id) or payments.get(student.full_name) or {}
    months_covered = info.get('months_covered', info.get('count', 0))
    last_date = info.get('last_date')
    first_date = info.get('first_date')

    offset = getattr(student, 'payment_offset', 0) or 0
    effective_count = max(0, months_covered - offset)
    anchor_date = student.trial_date or first_date or student.created_at.date()
    next_due = _add_months(anchor_date, effective_count)
    return last_date, next_due


PAYING_STATUSES = None  # filled lazily to avoid import-time surprises


def _paying_students(company):
    return (
        Student.objects.filter(
            company=company,
            status=Student.Status.STUDYING,
        )
        .select_related('group', 'branch')
        .order_by('first_name', 'last_name')
    )


def _rule_attendance_absent(config: dict, rule: dict) -> dict:
    today = timezone.localdate()
    min_age = int(rule.get('min_age_minutes', 0) or 0)
    threshold = timezone.now() - timedelta(minutes=min_age)
    sent = 0
    records = (
        AttendanceRecord.objects.filter(attend_date=today, status=AttendanceRecord.Status.ABSENT)
        .select_related('student', 'group', 'student__branch')
        .order_by('id')
    )
    for record in records:
        if record.created_at and record.created_at > threshold:
            continue  # just marked, give the teacher time to fix mistakes
        ctx = _student_ctx(
            record.student,
            {
                'date': _fmt_date(record.attend_date),
                'group': record.group.name if record.group_id else '-',
            },
        )
        if _send(config, record.student, rule, record.attend_date, ctx):
            sent += 1
    return {'sent': sent}


def _rule_payment_due(config: dict, rule: dict) -> dict:
    today = timezone.localdate()
    days_before = int(rule.get('days_before', 0) or 0)
    sent = 0
    for company in Company.objects.all():
        payments = _payments_summary(company)
        for student in _paying_students(company):
            due = _student_due(student, payments)
            if due is None:
                continue
            last_date, next_due = due
            if next_due < today or (next_due - today).days > days_before:
                continue
            ctx = _student_ctx(student, {
                'date': _fmt_date(today),
                'due_date': _fmt_date(next_due),
                'last_payment_date': _fmt_date(last_date),
            })
            if _send(config, student, rule, next_due, ctx):
                sent += 1
    return {'sent': sent}


def _rule_payment_overdue(config: dict, rule: dict) -> dict:
    today = timezone.localdate()
    days_after = int(rule.get('days_after', 1) or 0)
    every_days = max(int(rule.get('every_days', 1) or 1), 1)
    sent = 0
    for company in Company.objects.all():
        payments = _payments_summary(company)
        for student in _paying_students(company):
            due = _student_due(student, payments)
            if due is None:
                continue
            last_date, next_due = due
            days_over = (today - next_due).days
            if days_over < days_after or (days_over - days_after) % every_days != 0:
                continue
            ctx = _student_ctx(student, {
                'date': _fmt_date(today),
                'due_date': _fmt_date(next_due),
                'days': days_over,
                'last_payment_date': _fmt_date(last_date),
            })
            if _send(config, student, rule, today, ctx):
                sent += 1
    return {'sent': sent}


HANDLERS = {
    'attendance_absent': _rule_attendance_absent,
    'payment_due': _rule_payment_due,
    'payment_overdue': _rule_payment_overdue,
}


def _parse_hhmm(value) -> int:
    parts = str(value).strip().split(':')
    return int(parts[0]) * 60 + int(parts[1])


def _in_quiet_hours(config: dict) -> bool:
    qh = config.get('quiet_hours') or {}
    if not qh.get('enabled'):
        return False
    now = timezone.localtime()
    minutes = now.hour * 60 + now.minute
    try:
        start = _parse_hhmm(qh.get('from', '21:00'))
        end = _parse_hhmm(qh.get('to', '09:00'))
    except (ValueError, IndexError):
        return False
    if start <= end:
        return start <= minutes < end
    return minutes >= start or minutes < end


def run_once() -> dict:
    close_old_connections()
    config = load_config()
    if not config.get('enabled'):
        return {'enabled': False}
    if _in_quiet_hours(config):
        return {'quiet_hours': True}
    summary = {}
    for rule in config.get('rules', []):
        if not isinstance(rule, dict) or not rule.get('enabled', True):
            continue
        handler = HANDLERS.get(rule.get('type'))
        if handler is None:
            print(f'[notifications] unknown rule type: {rule.get("type")!r}', flush=True)
            continue
        try:
            summary[str(rule.get('name', rule.get('type')))] = handler(config, rule)
        except Exception:
            traceback.print_exc()
    close_old_connections()
    return summary


DEFAULT_HELP_REPLY = (
    'Здравствуйте! Это бот уведомлений учебного центра.\n'
    'Чтобы получать уведомления о вашем ребёнке, откройте персональную ссылку, '
    'которую выдал администратор, и нажмите Start.'
)
DEFAULT_SUBSCRIBED_REPLY = (
    'Готово! Теперь вам будут приходить уведомления об ученике {student} ({group}).'
)
DEFAULT_UNKNOWN_CODE_REPLY = (
    'Не нашёл ученика по этой ссылке. Проверьте ссылку или обратитесь к администратору.'
)

_update_offset = 0


def _handle_start_payload(config: dict, chat_id, payload: str) -> str:
    auto = config.get('auto_reply') or {}
    code = str(payload).strip().upper()
    student = (
        Student.objects.filter(telegram_code=code)
        .select_related('group', 'branch')
        .first()
    )
    if student is None:
        return str(auto.get('unknown_code_message') or DEFAULT_UNKNOWN_CODE_REPLY)
    student.parent_telegram = str(chat_id)
    student.save(update_fields=['parent_telegram'])
    group = student.group.name if student.group_id else '-'
    template = str(auto.get('subscribed_message') or DEFAULT_SUBSCRIBED_REPLY)
    return template.format(student=student.full_name, group=group)


def _poll_updates(config: dict) -> None:
    """Telegram-side self-service: parents open the personal link
    (t.me/<bot>?start=<code>) and press Start - the bot links their chat
    to the student and notifications start flowing automatically."""
    global _update_offset
    if not config.get('enabled'):
        return
    auto = config.get('auto_reply') or {}
    if not auto.get('enabled', True):
        return
    ok, result = telegram_call(config.get('bot_token', ''), 'getUpdates', {
        'offset': _update_offset,
        'timeout': 0,
    })
    if not ok or not isinstance(result, list):
        return
    help_reply = str(auto.get('message') or DEFAULT_HELP_REPLY)
    for update in result:
        try:
            _update_offset = max(_update_offset, int(update.get('update_id', 0)) + 1)
        except (TypeError, ValueError):
            continue
        message = update.get('message') or {}
        chat = message.get('chat') or {}
        if chat.get('type') != 'private' or chat.get('id') is None:
            continue
        text = str(message.get('text') or '').strip()
        payload = ''
        if text.lower().startswith('/start'):
            parts = text.split(maxsplit=1)
            payload = parts[1].strip() if len(parts) > 1 else ''
        if payload:
            reply = _handle_start_payload(config, chat['id'], payload)
        else:
            reply = help_reply
        telegram_call(config.get('bot_token', ''), 'sendMessage', {
            'chat_id': chat['id'],
            'text': reply,
        })


def _loop() -> None:
    ticks = 0
    while True:
        try:
            config = load_config()
            interval_minutes = max(int(config.get('poll_interval_minutes', 10) or 10), 1)
        except Exception:
            config = {}
            interval_minutes = 10
        try:
            _poll_updates(config)
        except Exception:
            traceback.print_exc()
        ticks += 1
        if ticks >= interval_minutes * 2:  # rules run every poll_interval_minutes
            ticks = 0
            try:
                summary = run_once()
                if any(isinstance(v, dict) and v.get('sent') for v in summary.values()):
                    print(f'[notifications] {summary}', flush=True)
            except Exception:
                traceback.print_exc()
        time.sleep(30)


_thread = None


def start_background_thread() -> None:
    global _thread
    if _thread is not None:
        return
    if 'runserver' not in sys.argv:
        return
    if os.environ.get('RUN_MAIN') != 'true' and '--noreload' not in sys.argv:
        return  # django reloader parent process - the child will run the loop
    _thread = threading.Thread(target=_loop, name='telegram-notifications', daemon=True)
    _thread.start()
    print('[notifications] background thread started', flush=True)
