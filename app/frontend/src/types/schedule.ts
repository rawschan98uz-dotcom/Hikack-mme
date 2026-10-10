import type { MessageKey } from '../i18n';

export interface ScheduleRow {
  id: number;
  name: string;
  days: number;
  days_key: 'odd' | 'even' | 'other';
  /** Real lesson weekdays, 0 = Monday … 6 = Sunday. */
  weekdays?: number[];
  days_label: string;
  time: string;
  teacher: string;
  course: string;
  branch: string;
}

export type ScheduleTab = 'odd' | 'even' | 'other';
export type ScheduleLayout = 'horizontal' | 'vertical';

export const SCHEDULE_TABS: { key: ScheduleTab; label: MessageKey }[] = [
  { key: 'odd', label: 'schedule.oddDays' },
  { key: 'even', label: 'schedule.evenDays' },
  { key: 'other', label: 'schedule.otherDays' },
];

export const SCHEDULE_WEEKDAYS = [
  { value: 1, label: 'weekday.mon' },
  { value: 2, label: 'weekday.tue' },
  { value: 3, label: 'weekday.wed' },
  { value: 4, label: 'weekday.thu' },
  { value: 5, label: 'weekday.fri' },
  { value: 6, label: 'weekday.sat' },
  { value: 0, label: 'weekday.sun' },
] as const;

/** Group.Days values that appear on each weekday (Other tab). */
export const GROUP_DAYS_BY_WEEKDAY: Record<number, number[]> = {
  1: [1, 4, 5],
  2: [2, 4, 5],
  3: [1, 4, 5],
  4: [2, 4, 5],
  5: [1, 4, 5],
  6: [2, 3, 4, 5],
  0: [3, 4, 5],
};

export const DEFAULT_TIME_SLOTS = ['09:00', '11:00', '14:00', '16:00', '18:00'];
