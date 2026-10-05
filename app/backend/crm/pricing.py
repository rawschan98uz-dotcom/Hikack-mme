"""
Course prices with a start date (owner, 2026-10-05).

A price is never simply overwritten: every change is a record "from this day the course costs X"
(crm.CoursePrice). What already happened keeps the price of its own day.
    Example: «а1» costs 500 000; on 5 October the CEO sets 600 000 from 1 November.
    price_on(а1, 20 October) = 500 000, price_on(а1, 1 November) = 600 000.
Course.price is the price valid today; it switches by itself on the day a planned price starts
(first request of the day, see DailyPriceMiddleware).
"""

from __future__ import annotations

from datetime import date

from django.utils import timezone

from crm.models import Course, CoursePrice


def _entries(course: Course) -> list[CoursePrice]:
    cached = getattr(course, '_prefetched_objects_cache', {}).get('prices')
    if cached is not None:
        return sorted(cached, key=lambda e: (e.valid_from, e.id))
    return list(CoursePrice.objects.filter(course=course).order_by('valid_from', 'id'))


def price_on(course: Course, day: date | None = None) -> int:
    """Price of the course on `day` (today by default). Days before the first record get the first price."""
    day = day or timezone.localdate()
    entries = _entries(course)
    if not entries:
        return int(course.price or 0)
    current = entries[0]
    for entry in entries:
        if entry.valid_from <= day:
            current = entry
    return int(current.price)


def next_price(course: Course, day: date | None = None) -> CoursePrice | None:
    """The nearest price that is planned but has not started yet."""
    day = day or timezone.localdate()
    return next((e for e in _entries(course) if e.valid_from > day), None)


def sync_course(course: Course) -> bool:
    """Make Course.price the price valid today. Returns True when it changed."""
    course._prefetched_objects_cache = {}
    current = price_on(course)
    if int(course.price or 0) == current:
        return False
    course.price = current
    course.save(update_fields=['price'])
    return True


def set_price(course: Course, price: int, valid_from: date | None = None, user=None) -> CoursePrice:
    """The course costs `price` from `valid_from` (today by default); a record of the same day is replaced."""
    valid_from = valid_from or timezone.localdate()
    entry, _ = CoursePrice.objects.update_or_create(
        course=course, valid_from=valid_from, defaults={'price': int(price), 'created_by': user},
    )
    sync_course(course)
    return entry


def record_direct_price(course: Course) -> None:
    """
    Course.price was saved directly (a new course, the admin site, a script): keep the history true.
    A new course gets its first record; a changed price becomes "from today".
    """
    today = timezone.localdate()
    if not CoursePrice.objects.filter(course=course).exists():
        CoursePrice.objects.create(course=course, price=int(course.price or 0), valid_from=today)
        return
    course._prefetched_objects_cache = {}
    if int(course.price or 0) != price_on(course, today):
        CoursePrice.objects.update_or_create(
            course=course, valid_from=today, defaults={'price': int(course.price or 0)},
        )


def sync_all() -> int:
    """Switch every course whose planned price starts today (or earlier). Returns how many changed."""
    today = timezone.localdate()
    changed = 0
    course_ids = CoursePrice.objects.filter(valid_from__lte=today).values_list('course_id', flat=True).distinct()
    for course in Course.objects.filter(pk__in=list(course_ids)):
        if sync_course(course):
            changed += 1
    return changed


def history(course: Course) -> list[dict]:
    entries = _entries(course)
    today = timezone.localdate()
    current = None
    for entry in entries:
        if entry.valid_from <= today:
            current = entry
    current = current or (entries[0] if entries else None)
    return [
        {
            'id': entry.id,
            'price': int(entry.price),
            'valid_from': entry.valid_from.isoformat(),
            # The first record also covers every day before it
            'is_first': index == 0,
            'is_current': current is not None and entry.id == current.id,
            'is_future': entry.valid_from > today,
            'created_by': entry.created_by.display_name() if entry.created_by_id else '',
        }
        for index, entry in enumerate(entries)
    ]


_synced_day: date | None = None


def ensure_current() -> None:
    """Once a day (first request): planned prices that start today become the current ones."""
    global _synced_day
    today = timezone.localdate()
    if _synced_day == today:
        return
    sync_all()
    _synced_day = today


class DailyPriceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            ensure_current()
        except Exception:
            pass  # a price switch problem must never break a page
        return self.get_response(request)
