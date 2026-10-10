/**
 * Money is always written the same way: "1 250 000 сум" — thousands split by a space that never breaks
 * the number across lines, a real minus "−" for money going out.
 */
import { t } from '../i18n';

const NBSP = ' ';

/** 1250000 → "1 250 000" (no currency). */
export function formatSum(value: number | null | undefined): string {
  const n = Math.round(Number(value) || 0);
  const digits = String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  return n < 0 ? `−${digits}` : digits;
}

/** 1250000 → "1 250 000 сум" / "1 250 000 soʻm" / "1 250 000 UZS". */
export function formatMoney(value: number | null | undefined): string {
  return `${formatSum(value)}${NBSP}${t('common.sum')}`;
}
