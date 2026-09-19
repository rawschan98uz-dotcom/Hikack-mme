"""
Вспомогательные функции для API.
Единое место для валидации, нормализации и пагинации.
"""

import os
import re
from datetime import date, datetime, time

from django.conf import settings


# ═══════════════════════════════════════════════════════════
# 🔢 БЕЗОПАСНОЕ ПРЕОБРАЗОВАНИЕ ЧИСЕЛ
# ═══════════════════════════════════════════════════════════

def safe_int(value, default=0, min_val=None, max_val=None):
    """
    Безопасное преобразование в int.
    
    Зачем:
        int("abc") → ValueError → 500 error
        int(None) → TypeError → 500 error
        int(999999999999) → может переполнить БД
    
    Использование:
        price = safe_int(request.data.get('price'), default=0, min_val=0)
        duration = safe_int(request.data.get('duration'), default=90, min_val=15, max_val=480)
    """
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    
    # Ограничения диапазона
    if min_val is not None:
        result = max(min_val, result)
    if max_val is not None:
        result = min(max_val, result)
    
    return result


def safe_float(value, default=0.0, min_val=None, max_val=None):
    """Аналогично safe_int, но для float (цены с копейками)."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if min_val is not None:
        result = max(min_val, result)
    if max_val is not None:
        result = min(max_val, result)
    return result


# ═══════════════════════════════════════════════════════════
# 📞 НОРМАЛИЗАЦИЯ ТЕЛЕФОНА
# ═══════════════════════════════════════════════════════════

def normalize_phone(phone):
    """
    Приводит любой формат номера к единому виду: 9 цифр.
    
    Зачем:
        "998901234567" → 12 цифр
        "901234567"    → 9 цифр
        "90 123 45 67" → 9 цифр (после очистки)
        
        Все три — ОДИН И ТОТ ЖЕ абонент.
        Без нормализации = дубликаты в БД.
    
    Обрабатывает:
        +998 90 123 45 67  → 901234567
        998901234567       → 901234567  
        8 90 123 45 67     → 901234567 (если 10 цифр и начинается с 8... нет, 8 = Россия)
        90-123-45-67       → 901234567
        901234567          → 901234567 (уже нормальный)
    """
    if not phone:
        return ''
    
    # Убираем всё кроме цифр
    digits = ''.join(ch for ch in str(phone) if ch.isdigit())
    
    # Убираем код страны Узбекистан (998)
    if digits.startswith('998') and len(digits) >= 10:
        digits = digits[3:]
    
    return digits


def is_valid_phone(phone):
    """Проверка: 9 цифр (формат Узбекистана)."""
    digits = normalize_phone(phone)
    return len(digits) == 9


# ═══════════════════════════════════════════════════════════
# 📄 ПАГИНАЦИЯ
# ═══════════════════════════════════════════════════════════

def paginate_queryset(qs, request, default_limit=200, max_limit=1000):
    """
    Простая пагинация через query-параметры.
    
    Параметры (URL):
        ?limit=50       — сколько записей (по умолчанию 200)
        ?offset=200     — с какой позиции (для следующей страницы)
    
    Ответ:
        {
            'count': 350,          — всего записей
            'has_more': True,      — есть ли ещё
            'next_offset': 400,    — offset для следующей страницы
            'results': [...]       — данные
        }
    
    Использование в views:
        page = paginate_queryset(students_qs, request)
        return ok({
            'count': page['count'],
            'has_more': page['has_more'],
            'next_offset': page['next_offset'],
            'results': [_serialize_student(s) for s in page['results']],
        })
    """
    try:
        limit = int(request.query_params.get('limit', default_limit))
        offset = int(request.query_params.get('offset', 0))
    except (TypeError, ValueError):
        limit = default_limit
        offset = 0
    
    # Защита от абсурдных значений
    limit = max(1, min(limit, max_limit))
    offset = max(0, offset)
    
    total = qs.count()
    items = list(qs[offset:offset + limit])
    
    has_more = offset + limit < total
    next_offset = offset + limit if has_more else None
    
    return {
        'count': total,
        'has_more': has_more,
        'next_offset': next_offset,
        'results': items,
    }


# ═══════════════════════════════════════════════════════════
# 🖼️ БЕЗОПАСНОЕ ФОТО
# ═══════════════════════════════════════════════════════════

def get_photo_url(field_file):
    """
    Возвращает URL фото ТОЛЬКО если файл существует на диске.
    
    Зачем:
        В БД путь есть, а файла нет (удалили вручную, сбой диска).
        Без проверки → битая картинка в браузере.
    """
    if not field_file:
        return None
    
    try:
        full_path = os.path.join(settings.MEDIA_ROOT, str(field_file))
        if os.path.exists(full_path):
            return field_file.url
    except (OSError, ValueError, AttributeError):
        pass
    
    return None


# ═══════════════════════════════════════════════════════════
# 📅 БЕЗОПАСНЫЕ ДАТЫ И ВРЕМЯ
# ═══════════════════════════════════════════════════════════

def parse_date_safe(value):
    """
    Парсит дату из строки. Возвращает None при ошибке.
    
    Поддерживает: '2024-03-15', '2024-03-15T10:00:00'
    """
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip()[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def parse_time_safe(value):
    """
    Парсит время. Возвращает None при ошибке.
    
    Поддерживает: '14:00', '14:30', '09:15', 1400 (int)
    """
    if value in (None, ''):
        return None
    try:
        raw = str(value).strip()
        # Формат HH:MM или HH:MM:SS
        if ':' in raw:
            parts = raw.split(':')
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            return time(hour, minute)
        # Формат HHMM (число)
        if raw.isdigit() and len(raw) == 4:
            return time(int(raw[:2]), int(raw[2:]))
        return None
    except (ValueError, TypeError):
        return None


# ═══════════════════════════════════════════════════════════
# 🔤 ВАЛИДАЦИЯ КОДОВ КУРСОВ
# ═══════════════════════════════════════════════════════════

# Разрешённые коды: буквы, цифры, дефис, подчёркивание
# 2-15 символов
COURSE_CODE_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{2,15}$')

def validate_course_code(code):
    """
    Проверяет код курса.
    
    Было: только a1, a2, b1, b2, c1, c2 (CEFR)
    Стало: любой разумный код (math, art, rus, python, a1, etc.)
    
    Возвращает (is_valid, error_message)
    """
    if not code:
        return False, 'Course code is required'
    
    code = str(code).strip().lower()
    
    if not COURSE_CODE_PATTERN.match(code):
        return False, 'Code must be 2-15 characters (letters, numbers, - or _)'
    
    return True, None
