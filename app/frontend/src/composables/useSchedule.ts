import { computed, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import {
  DEFAULT_TIME_SLOTS,
  GROUP_DAYS_BY_WEEKDAY,
  type ScheduleLayout,
  type ScheduleRow,
  type ScheduleTab,
} from '../types/schedule';

export function parseTimeStart(time: string) {
  return time.split('–')[0]?.trim() ?? time;
}

export function useSchedule(initialRows?: ScheduleRow[]) {
  const rows = ref<ScheduleRow[]>(initialRows ?? []);
  const loading = ref(false);
  const scheduleTab = ref<ScheduleTab>('odd');
  const scheduleLayout = ref<ScheduleLayout>('horizontal');
  const otherWeekday = ref<number>(new Date().getDay());

  const filteredSchedule = computed(() =>
    rows.value.filter((row) => {
      if (row.days_key !== scheduleTab.value) return false;
      if (scheduleTab.value !== 'other') return true;
      const allowed = GROUP_DAYS_BY_WEEKDAY[otherWeekday.value] ?? [];
      return allowed.includes(row.days);
    }),
  );

  const scheduleLayoutLabel = computed(() =>
    scheduleLayout.value === 'horizontal' ? 'Horizontal' : 'Vertical',
  );

  const displayTimeSlots = computed(() => {
    const fromData = [
      ...new Set(filteredSchedule.value.map((row) => parseTimeStart(row.time)).filter(Boolean)),
    ].sort();
    return fromData.length ? fromData : DEFAULT_TIME_SLOTS;
  });

  function groupsAtTimeSlot(slot: string) {
    return filteredSchedule.value.filter((row) => parseTimeStart(row.time) === slot);
  }

  function setScheduleTab(tab: ScheduleTab) {
    scheduleTab.value = tab;
    if (tab === 'other') {
      scheduleLayout.value = 'vertical';
    }
  }

  function toggleScheduleLayout() {
    scheduleLayout.value = scheduleLayout.value === 'horizontal' ? 'vertical' : 'horizontal';
  }

  async function loadSchedule() {
    loading.value = true;
    try {
      const { data } = await client.get<ApiEnvelope<ScheduleRow[]>>('/schedule');
      rows.value = data.data;
    } finally {
      loading.value = false;
    }
  }

  function setRows(next: ScheduleRow[]) {
    rows.value = next;
  }

  return {
    rows,
    loading,
    scheduleTab,
    scheduleLayout,
    otherWeekday,
    filteredSchedule,
    scheduleLayoutLabel,
    displayTimeSlots,
    groupsAtTimeSlot,
    setScheduleTab,
    toggleScheduleLayout,
    loadSchedule,
    setRows,
  };
}
