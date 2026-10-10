/**
 * Calendar dates for forms and filters. Never use `date.toISOString().slice(0, 10)`: it gives the
 * UTC date — "yesterday" before 05:00 in Tashkent, and for a date built as `new Date(y, m, d)` on a
 * Tashkent computer it is always one day earlier.
 */

import { t, type MessageKey } from '../i18n';

const TASHKENT = 'Asia/Tashkent';

/** Today in Tashkent as YYYY-MM-DD (the business works on Tashkent time whatever the PC clock says). */
export function todayIso(): string {
  // en-CA formats as YYYY-MM-DD
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: TASHKENT,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
}

/** Current month in Tashkent as YYYY-MM. */
export function currentMonthIso(): string {
  return todayIso().slice(0, 7);
}

/** A calendar date built with `new Date(year, month, day)` as YYYY-MM-DD (no time zone shift). */
export function dateToIso(d: Date): string {
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${month}-${day}`;
}

/** Month name in the interface language: monthName(8) → "Сентябрь" / "Sentabr" / "September". */
export function monthName(monthIndex: number, short = false): string {
  return t(`${short ? 'monthShort' : 'month'}.${monthIndex + 1}` as MessageKey);
}

/** "Сентябрь 2026" / "Sentabr 2026" / "September 2026" (short: "Сен 2026"). */
export function formatMonthYear(date: Date, short = false): string {
  return `${monthName(date.getMonth(), short)} ${date.getFullYear()}`;
}

const WEEKDAY_KEYS = ['weekday.sun', 'weekday.mon', 'weekday.tue', 'weekday.wed', 'weekday.thu', 'weekday.fri', 'weekday.sat'] as const;

/** Short weekday name in the interface language: "Пн" / "Du" / "Mon". */
export function weekdayShort(date: Date): string {
  return t(WEEKDAY_KEYS[date.getDay()]);
}

/** "2026-09" → "Сентябрь 2026" / "Sentabr 2026" / "September 2026" in the interface language. */
export function formatMonthTitle(yearMonth: string): string {
  const [year, month] = yearMonth.split('-').map(Number);
  if (!year || !month) return yearMonth;
  return formatMonthYear(new Date(year, month - 1, 1));
}
