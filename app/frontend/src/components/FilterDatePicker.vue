<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

const props = withDefaults(
  defineProps<{
    modelValue: string;
    placeholder?: string;
  }>(),
  {
    placeholder: 'Select date',
  },
);

const emit = defineEmits<{
  'update:modelValue': [value: string];
}>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const viewDate = ref(new Date());

const weekdayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;

const monthLabel = computed(() =>
  viewDate.value.toLocaleDateString('en-US', { month: 'long', year: 'numeric' }),
);

const calendarCells = computed(() => {
  const year = viewDate.value.getFullYear();
  const month = viewDate.value.getMonth();
  const firstDay = new Date(year, month, 1);
  const startOffset = firstDay.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const prevMonthDays = new Date(year, month, 0).getDate();

  const cells: Array<{
    key: string;
    day: number;
    iso: string;
    muted: boolean;
    selected: boolean;
    today: boolean;
  }> = [];

  for (let index = 0; index < startOffset; index += 1) {
    const day = prevMonthDays - startOffset + index + 1;
    const date = new Date(year, month - 1, day);
    cells.push(makeCell(date, day, true));
  }

  for (let day = 1; day <= daysInMonth; day += 1) {
    const date = new Date(year, month, day);
    cells.push(makeCell(date, day, false));
  }

  while (cells.length % 7 !== 0) {
    const day = cells.length - (startOffset + daysInMonth) + 1;
    const date = new Date(year, month + 1, day);
    cells.push(makeCell(date, day, true));
  }

  return cells;
});

function pad(value: number) {
  return String(value).padStart(2, '0');
}

function toIso(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function makeCell(date: Date, day: number, muted: boolean) {
  const iso = toIso(date);
  const todayIso = toIso(new Date());
  return {
    key: iso,
    day,
    iso,
    muted,
    selected: props.modelValue === iso,
    today: iso === todayIso,
  };
}

function shiftMonth(delta: number) {
  const next = new Date(viewDate.value);
  next.setMonth(next.getMonth() + delta);
  viewDate.value = next;
}

function shiftYear(delta: number) {
  const next = new Date(viewDate.value);
  next.setFullYear(next.getFullYear() + delta);
  viewDate.value = next;
}

function selectDate(iso: string) {
  emit('update:modelValue', iso);
  open.value = false;
}

function onDocumentClick(event: MouseEvent) {
  if (!root.value?.contains(event.target as Node)) {
    open.value = false;
  }
}

watch(
  () => props.modelValue,
  (value) => {
    if (!value) return;
    const parsed = new Date(`${value}T00:00:00`);
    if (!Number.isNaN(parsed.getTime())) {
      viewDate.value = parsed;
    }
  },
  { immediate: true },
);

onMounted(() => document.addEventListener('click', onDocumentClick));
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick));
</script>

<template>
  <div ref="root" class="relative min-w-[150px] flex-1">
    <button
      type="button"
      class="filter-control-fb w-full"
      :class="{ 'border-fb-blue ring-1 ring-fb-blue/30': open }"
      @click.stop="open = !open"
    >
      <svg class="h-4 w-4 shrink-0 text-fb-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path
          d="M5.25 3A2.25 2.25 0 003 5.25v9.5A2.25 2.25 0 005.25 17h9.5A2.25 2.25 0 0017 14.75v-9.5A2.25 2.25 0 0014.75 3h-9.5zM4.5 7.75h11v7a.75.75 0 01-.75.75h-9.5a.75.75 0 01-.75-.75v-7zM6.5 4.5a.75.75 0 000 1.5h.75v.75a.75.75 0 001.5 0V6h3v.75a.75.75 0 001.5 0V6h.75a.75.75 0 000-1.5h-.75V4a.75.75 0 00-1.5 0v.5h-3V4a.75.75 0 00-1.5 0v.5h-.75z"
        />
      </svg>
      <span class="truncate text-sm" :class="modelValue ? 'text-fb-text' : 'text-fb-icon'">
        {{ modelValue || placeholder }}
      </span>
    </button>

    <div v-if="open" class="filter-dropdown-fb filter-date-picker-fb">
      <div class="mb-3 flex items-center justify-between px-1">
        <div class="flex items-center gap-1">
          <button type="button" class="filter-date-nav-fb" @click="shiftYear(-1)">«</button>
          <button type="button" class="filter-date-nav-fb" @click="shiftMonth(-1)">‹</button>
        </div>
        <div class="text-sm font-medium text-fb-text">{{ monthLabel }}</div>
        <div class="flex items-center gap-1">
          <button type="button" class="filter-date-nav-fb" @click="shiftMonth(1)">›</button>
          <button type="button" class="filter-date-nav-fb" @click="shiftYear(1)">»</button>
        </div>
      </div>

      <div class="grid grid-cols-7 gap-1 text-center text-xs text-fb-secondary">
        <span v-for="label in weekdayLabels" :key="label">{{ label }}</span>
      </div>

      <div class="mt-2 grid grid-cols-7 gap-1">
        <button
          v-for="cell in calendarCells"
          :key="cell.key"
          type="button"
          class="filter-date-cell-fb"
          :class="{
            'is-muted': cell.muted,
            'is-selected': cell.selected,
            'is-today': cell.today && !cell.selected,
          }"
          @click="selectDate(cell.iso)"
        >
          {{ cell.day }}
        </button>
      </div>
    </div>
  </div>
</template>
