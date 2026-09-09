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
        return [], 'File is required'

    filename = (getattr(uploaded_file, 'name', '') or '').lower()

    if filename.endswith('.xlsx'):
        return _parse_xlsx(uploaded_file)
    elif filename.endswith('.xls'):
        return _parse_xls(uploaded_file)
    else:
        return _parse_csv(uploaded_file)


def _parse_xlsx(uploaded_file) -> tuple[list[dict[str, str]], str | None]:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(uploaded_file, data_only=True)
        sheet = wb.active
        if not sheet:
            return [], 'Excel sheet is empty'

        headers: list[str] = []
        for cell in sheet[1]:
            val = str(cell.value or '').strip()
            headers.append(normalize_header(val) if val else '')

        if not any(headers):
            return [], 'Header row is missing in Excel file'

        rows: list[dict[str, str]] = []
        for line_number, row_cells in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            normalized: dict[str, str] = {}
            has_value = False
            for header, val in zip(headers, row_cells):
                if not header:
                    continue
                if isinstance(val, float) and val.is_integer():
                    cell_str = str(int(val))
                elif val is not None:
                    cell_str = str(val).strip()
                else:
                    cell_str = ''
                if cell_str:
                    has_value = True
                normalized[header] = cell_str
            if has_value:
                normalized['_row'] = str(line_number)
                rows.append(normalized)

        if not rows:
            return [], 'No data rows found in Excel file'
        return rows, None
    except Exception as e:
        return [], f'Could not read Excel (.xlsx) file: {e}'


def _parse_xls(uploaded_file) -> tuple[list[dict[str, str]], str | None]:
    try:
        import xlrd
        content = uploaded_file.read()
        wb = xlrd.open_workbook(file_contents=content)
        sheet = wb.sheet_by_index(0)
        if sheet.nrows < 1:
            return [], 'Excel sheet is empty'

        headers = [normalize_header(str(sheet.cell_value(0, col)).strip()) for col in range(sheet.ncols)]
        if not any(headers):
            return [], 'Header row is missing in Excel file'

        rows: list[dict[str, str]] = []
        for line_number in range(1, sheet.nrows):
            normalized = {}
            has_value = False
            for col, header in enumerate(headers):
                if not header:
                    continue
                val = sheet.cell_value(line_number, col)
                if isinstance(val, float) and val.is_integer():
                    cell_str = str(int(val))
                elif val is not None:
                    cell_str = str(val).strip()
                else:
                    cell_str = ''
                if cell_str:
                    has_value = True
                normalized[header] = cell_str
            if has_value:
                normalized['_row'] = str(line_number + 1)
                rows.append(normalized)

        if not rows:
            return [], 'No data rows found in Excel file'
        return rows, None
    except Exception as e:
        return [], f'Could not read Excel (.xls) file: {e}'


def _parse_csv(uploaded_file) -> tuple[list[dict[str, str]], str | None]:
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

    first_line = content.splitlines()[0] if content.splitlines() else ''
    delimiter = ';' if ';' in first_line and first_line.count(';') > first_line.count(',') else ','

    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
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
