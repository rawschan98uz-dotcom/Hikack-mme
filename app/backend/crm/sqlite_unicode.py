"""
Unicode-aware LIKE for SQLite.

SQLite's built-in LIKE ignores case only for Latin letters, so Django's __iexact / __icontains /
__istartswith (all compiled to LIKE on SQLite) did not match "азиз" with "Азиз".
We replace LIKE on every SQLite connection with a Python version that folds case for any alphabet
(Cyrillic, Uzbek, Latin). SQLite's LIKE was already case-insensitive for Latin, so nothing else changes.
"""

import re
from functools import lru_cache

from django.db.backends.signals import connection_created


@lru_cache(maxsize=512)
def _like_regex(pattern: str, escape: str | None) -> re.Pattern:
    parts = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if escape and ch == escape and i + 1 < len(pattern):
            parts.append(re.escape(pattern[i + 1].casefold()))
            i += 2
            continue
        if ch == '%':
            parts.append('.*')
        elif ch == '_':
            parts.append('.')
        else:
            parts.append(re.escape(ch.casefold()))
        i += 1
    return re.compile(''.join(parts), re.DOTALL)


def unicode_like(pattern, value, escape=None):
    """SQLite calls like(pattern, value[, escape]) for `value LIKE pattern`."""
    if pattern is None or value is None:
        return None
    return _like_regex(str(pattern), escape).fullmatch(str(value).casefold()) is not None


def _install(sender, connection, **kwargs):
    if connection.vendor != 'sqlite':
        return
    raw = connection.connection
    raw.create_function('like', 2, unicode_like, deterministic=True)
    raw.create_function('like', 3, unicode_like, deterministic=True)


def register():
    connection_created.connect(_install, dispatch_uid='crm_sqlite_unicode_like')
