/**
 * Names of statuses and kinds that the server sends as codes (with a Russian label next to them).
 * The code is shown in the interface language; an unknown code falls back to the server's label.
 */
import { t, tMaybe } from './index';

type Code = string | number | null | undefined;

function byCode(prefix: string, code: Code, fallback?: string | null): string {
  if (code === null || code === undefined || code === '') return fallback || '—';
  return tMaybe(`${prefix}.${code}`, fallback || String(code));
}

export const studentStatusLabel = (code: Code, fallback?: string | null) => byCode('studentStatus', code, fallback);
export const groupStatusLabel = (code: Code, fallback?: string | null) => byCode('groupStatus', code, fallback);
export const groupDaysLabel = (code: Code, fallback?: string | null) => byCode('groupDays', code, fallback);
export const leadStageLabel = (code: Code, fallback?: string | null) => byCode('leadStage', code, fallback);
export const payMethodLabel = (code: Code, fallback?: string | null) =>
  byCode('payMethod', typeof code === 'string' ? code.toLowerCase() : code, fallback);
export const txTypeLabel = (code: Code, fallback?: string | null) => byCode('txType', code, fallback);
export const salaryTypeLabel = (code: Code, fallback?: string | null) => byCode('salaryType', code, fallback);
export const reminderStatusLabel = (code: Code, fallback?: string | null) => byCode('reminderStatus', code, fallback);
export const enrollmentStatusLabel = (code: Code, fallback?: string | null) => byCode('enrollment', code, fallback);
export const roleLabel = (code: Code, fallback?: string | null) => byCode('roles', code, fallback);

/** Lesson attendance (students and teachers): 1 = present, 2 = late, 0 = absent, null = not marked. */
export function attendanceLabel(code: Code, fallback?: string | null): string {
  if (code === 1 || code === '1') return t('teacherAtt.present');
  if (code === 2 || code === '2') return t('teacherAtt.late');
  if (code === 0 || code === '0') return t('teacherAtt.absent');
  return fallback || t('teacherAtt.notMarked');
}
