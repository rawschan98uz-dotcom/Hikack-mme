<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface MyRecord {
  date: string;
  group: string;
  status: number;
  status_label: string;
  time: string;
}

interface MyAttendance {
  start_date: string | null;
  today: string;
  records: MyRecord[];
}

// Teacher attendance status (same as backend): 1 = present, 2 = late, 0 = absent
const PRESENT = 1;
const LATE = 2;
const ABSENT = 0;

type Period = 'all' | '30' | '7';
const PERIODS: { key: Period; label: string }[] = [
  { key: 'all', label: 'Всё' },
  { key: '30', label: '30 дней' },
  { key: '7', label: '7 дней' },
];
const WEEKDAY_LABELS = ['Пн', '', 'Ср', '', 'Пт', '', 'Вс'];

const data = ref<MyAttendance | null>(null);
const loading = ref(true);
const period = ref<Period>('30');

function parseDay(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function isoDay(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

function addDays(d: Date, n: number): Date {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + n);
  return copy;
}

const today = computed(() => parseDay(data.value?.today ?? isoDay(new Date())));

const fromDate = computed(() => {
  if (period.value === '7') return addDays(today.value, -6);
  if (period.value === '30') return addDays(today.value, -29);
  return data.value?.start_date ? parseDay(data.value.start_date) : addDays(today.value, -29);
});

const periodRecords = computed(() => {
  const from = isoDay(fromDate.value);
  const to = isoDay(today.value);
  return (data.value?.records ?? []).filter((r) => r.date >= from && r.date <= to);
});

const stats = computed(() => {
  const rows = periodRecords.value;
  const present = rows.filter((r) => r.status === PRESENT).length;
  const late = rows.filter((r) => r.status === LATE).length;
  const absent = rows.filter((r) => r.status === ABSENT).length;
  return {
    total: rows.length,
    present,
    late,
    absent,
    days: new Set(rows.map((r) => r.date)).size,
    onTimePct: rows.length ? Math.round((present / rows.length) * 100) : 0,
  };
});

const tiles = computed(() => [
  { label: 'Уроков отмечено', value: stats.value.total },
  { label: 'Вовремя', value: stats.value.present },
  { label: 'Опоздания', value: stats.value.late },
  { label: 'Пропуски', value: stats.value.absent },
  { label: 'Дней с уроками', value: stats.value.days },
  { label: 'Вовремя, %', value: `${stats.value.onTimePct}%` },
]);

const recordsByDay = computed(() => {
  const map = new Map<string, MyRecord[]>();
  for (const r of periodRecords.value) {
    const list = map.get(r.date) ?? [];
    list.push(r);
    map.set(r.date, list);
  }
  return map;
});

interface Cell {
  key: string;
  inRange: boolean;
  level: 'none' | 'present' | 'late' | 'absent';
  title: string;
}

/** Weeks as columns (Mon…Sun rows), like a contribution calendar. */
const weeks = computed<Cell[][]>(() => {
  const from = fromDate.value;
  const to = today.value;
  const mondayOffset = (from.getDay() + 6) % 7;
  let cursor = addDays(from, -mondayOffset);
  const result: Cell[][] = [];
  while (cursor <= to) {
    const week: Cell[] = [];
    for (let i = 0; i < 7; i += 1) {
      const key = isoDay(cursor);
      const inRange = cursor >= from && cursor <= to;
      const dayRecords = recordsByDay.value.get(key) ?? [];
      // the worst mark of the day decides the colour
      let level: Cell['level'] = 'none';
      if (dayRecords.some((r) => r.status === ABSENT)) level = 'absent';
      else if (dayRecords.some((r) => r.status === LATE)) level = 'late';
      else if (dayRecords.length) level = 'present';
      const dayLabel = key.split('-').reverse().join('.');
      const title = dayRecords.length
        ? `${dayLabel}\n${dayRecords.map((r) => `${r.group} · ${r.status_label} ${r.time}`).join('\n')}`
        : `${dayLabel} · нет отметки`;
      week.push({ key, inRange, level, title });
      cursor = addDays(cursor, 1);
    }
    result.push(week);
  }
  return result;
});

function cellClass(cell: Cell) {
  if (!cell.inRange) return 'bg-transparent';
  if (cell.level === 'present') return 'bg-emerald-500';
  if (cell.level === 'late') return 'bg-amber-400';
  if (cell.level === 'absent') return 'bg-red-500';
  return 'bg-fb-line';
}

async function load() {
  loading.value = true;
  try {
    const res = await client.get<ApiEnvelope<MyAttendance>>('/teacher-attendance/my');
    data.value = res.data.data;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="space-y-4">
    <div>
      <h1 class="text-xl font-semibold text-fb-text">Моя посещаемость</h1>
      <p class="text-sm text-fb-secondary">Ваши отметки «Я пришёл» по урокам</p>
    </div>

    <div class="max-w-3xl rounded-2xl border border-fb-line bg-fb-card p-4 sm:p-5">
      <div class="mb-4 flex items-center justify-end">
        <div class="flex gap-1 rounded-lg bg-fb-canvas p-1">
          <button
            v-for="p in PERIODS"
            :key="p.key"
            type="button"
            class="rounded-md px-3 py-1 text-sm transition-colors"
            :class="period === p.key ? 'bg-fb-card font-semibold text-fb-text shadow-sm' : 'text-fb-secondary hover:text-fb-text'"
            @click="period = p.key"
          >
            {{ p.label }}
          </button>
        </div>
      </div>

      <div v-if="loading" class="py-10 text-center text-sm text-fb-secondary">Загрузка…</div>
      <template v-else>
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <div v-for="tile in tiles" :key="tile.label" class="rounded-lg bg-fb-canvas px-3 py-2">
            <div class="text-xs text-fb-secondary">{{ tile.label }}</div>
            <div class="text-lg font-semibold text-fb-text">{{ tile.value }}</div>
          </div>
        </div>

        <div class="mt-4 flex gap-1 overflow-x-auto pb-1">
          <div class="mr-1 flex shrink-0 flex-col gap-1">
            <span v-for="(label, i) in WEEKDAY_LABELS" :key="i" class="flex h-4 items-center text-[10px] leading-none text-fb-secondary">
              {{ label }}
            </span>
          </div>
          <div v-for="(week, wi) in weeks" :key="wi" class="flex shrink-0 flex-col gap-1">
            <div
              v-for="cell in week"
              :key="cell.key"
              class="h-4 w-4 rounded-[3px]"
              :class="cellClass(cell)"
              :title="cell.inRange ? cell.title : ''"
            />
          </div>
        </div>

        <div class="mt-3 flex flex-wrap gap-4 text-xs text-fb-secondary">
          <span class="flex items-center gap-1.5"><span class="h-3 w-3 rounded-[3px] bg-emerald-500" />Вовремя</span>
          <span class="flex items-center gap-1.5"><span class="h-3 w-3 rounded-[3px] bg-amber-400" />Опоздал</span>
          <span class="flex items-center gap-1.5"><span class="h-3 w-3 rounded-[3px] bg-red-500" />Не был</span>
          <span class="flex items-center gap-1.5"><span class="h-3 w-3 rounded-[3px] bg-fb-line" />Нет отметки</span>
        </div>
        <p v-if="!periodRecords.length" class="mt-3 text-sm text-fb-secondary">
          За этот период отметок нет. Отметиться можно на главной странице кнопкой «Я пришёл».
        </p>
      </template>
    </div>
  </div>
</template>
