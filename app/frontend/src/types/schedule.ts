export interface ScheduleRow {
  id: number;
  name: string;
  days: number;
  days_key: 'odd' | 'even' | 'other';
  days_label: string;
  time: string;
  teacher: string;
  course: string;
  branch: string;
}

export type ScheduleTab = 'odd' | 'even' | 'other';
export type ScheduleLayout = 'horizontal' | 'vertical';

export const SCHEDULE_TABS: { key: ScheduleTab; label: string }[] = [
  { key: 'odd', label: 'Odd days' },
  { key: 'even', label: 'Even days' },
  { key: 'other', label: 'Other' },
];

export const SCHEDULE_WEEKDAYS = [
  { value: 1, label: 'Mon.' },
  { value: 2, label: 'Tue.' },
  { value: 3, label: 'Wed.' },
  { value: 4, label: 'Thu.' },
  { value: 5, label: 'Fri.' },
  { value: 6, label: 'Sat.' },
  { value: 0, label: 'Sun.' },
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
