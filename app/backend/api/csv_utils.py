"""CSV parsing helpers for import endpoints."""

from __future__ import annotations

import csv
import io


def normalize_header(key: str) -> str:
    return key.strip().lower().replace(' ', '_').replace('-', '_')


def normalize_phone(raw: str) -> str:
    return ''.join(ch for ch in str(raw or '') if ch.isdigit())


def parse_csv_upload(uploaded_file) -> tuple[list[dict[str, str]], str | None]:
    if uploaded_file is None:
        return [], 'CSV file is required'

    try:
        raw_bytes = uploaded_file.read()
    except OSError:
        return [], 'Could not read uploaded file'

    for encoding in ('utf-8-sig', 'utf-8', 'cp1251'):
        try:
            content = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            content = None
    if content is None:
        return [], 'File must be UTF-8 or Windows-1251 CSV'

    if not content.strip():
        return [], 'CSV file is empty'

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return [], 'CSV header row is missing'

    rows: list[dict[str, str]] = []
    for line_number, raw_row in enumerate(reader, start=2):
        normalized: dict[str, str] = {}
        has_value = False
        for key, value in raw_row.items():
            if key is None:
                continue
            cell = str(value or '').strip()
            if cell:
                has_value = True
            normalized[normalize_header(key)] = cell
        if has_value:
            normalized['_row'] = str(line_number)
            rows.append(normalized)

    if not rows:
        return [], 'No data rows found in CSV'

    return rows, None
