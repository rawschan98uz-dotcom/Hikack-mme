"""Money helpers for per-lesson billing (B6)."""


def split_monthly(price: int, lesson_dates) -> dict:
    """
    Split a monthly price across the month's lessons in whole sums without losing any.

    Every lesson gets price // n; the remainder of the integer division is added to the last
    lesson, so the parts always add up to exactly `price`.
    Example: 1 000 000 over 12 lessons -> 11 × 83 333 and the last one 83 337.
    """
    dates = sorted(lesson_dates)
    if not dates:
        return {}
    price = int(price)
    base, remainder = divmod(price, len(dates))
    parts = {d: base for d in dates}
    parts[dates[-1]] += remainder
    return parts
