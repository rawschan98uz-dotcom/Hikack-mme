/**
 * Calendar dates for forms and filters. Never use `date.toISOString().slice(0, 10)`: it gives the
 * UTC date — "yesterday" before 05:00 in Tashkent, and for a date built as `new Date(y, m, d)` on a
 * Tashkent computer it is always one day earlier.
 */

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
