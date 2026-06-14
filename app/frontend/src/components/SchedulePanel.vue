<script setup lang="ts">
import { watch } from 'vue';

import { useSchedule } from '../composables/useSchedule';
import { SCHEDULE_TABS, SCHEDULE_WEEKDAYS, type ScheduleRow } from '../types/schedule';

const props = withDefaults(
  defineProps<{
    rows?: ScheduleRow[];
    loading?: boolean;
    showTitle?: boolean;
  }>(),
  {
    rows: () => [],
    loading: false,
    showTitle: true,
  },
);

const emit = defineEmits<{
  selectGroup: [groupId: number];
}>();

const {
  scheduleTab,
  scheduleLayout,
  otherWeekday,
  filteredSchedule,
  scheduleLayoutLabel,
  displayTimeSlots,
  groupsAtTimeSlot,
  setScheduleTab,
  toggleScheduleLayout,
  setRows,
} = useSchedule(props.rows);

watch(
  () => props.rows,
  (next) => setRows(next),
  { immediate: true },
);

function onSelectGroup(groupId: number) {
  emit('selectGroup', groupId);
}
</script>

<template>
  <div class="schedule-panel bg-fb-card">
    <h4
      v-if="showTitle"
      class="py-4 text-center text-[17px] font-normal text-fb-text"
    >
      Schedule
    </h4>

    <div v-if="loading" class="py-12 text-center text-[15px] text-fb-icon">
      Loading…
    </div>

    <template v-else>
      <div class="px-4 pb-3">
        <div class="flex flex-wrap items-center gap-3">
          <ul class="mr-auto flex items-center gap-5 sm:gap-6">
            <li v-for="tab in SCHEDULE_TABS" :key="tab.key">
              <button
                type="button"
                class="border-b-2 pb-1.5 text-[14px] transition-colors sm:text-[15px]"
                :class="scheduleTab === tab.key
                  ? 'border-fb-blue font-medium text-fb-blue'
                  : 'border-transparent text-fb-secondary hover:text-fb-text'"
                @click="setScheduleTab(tab.key)"
              >
                {{ tab.label }}
              </button>
            </li>
          </ul>

          <button
            type="button"
            class="flex cursor-pointer items-center gap-2 text-[14px] text-fb-secondary sm:text-[15px]"
            @click="toggleScheduleLayout"
          >
            <span>{{ scheduleLayoutLabel }}</span>
            <span
              class="relative h-5 w-5 rounded-full border border-fb-line"
              aria-hidden="true"
            >
              <template v-if="scheduleLayout === 'horizontal'">
                <span class="absolute inset-y-0 left-0 w-1/2 rounded-l-full bg-fb-blue" />
                <span class="absolute inset-y-0 right-0 w-1/2 rounded-r-full bg-fb-blue" />
              </template>
              <template v-else>
                <span class="absolute inset-x-0 top-0 h-1/2 rounded-t-full bg-fb-blue" />
                <span class="absolute inset-x-0 bottom-0 h-1/2 rounded-b-full bg-fb-blue" />
              </template>
            </span>
          </button>
        </div>

        <ul
          v-if="scheduleTab === 'other'"
          class="mt-3 flex flex-wrap items-center gap-4 sm:gap-5"
        >
          <li v-for="day in SCHEDULE_WEEKDAYS" :key="day.value">
            <button
              type="button"
              class="flex items-center gap-1.5 border-b-2 pb-1 text-[14px] transition-colors"
              :class="otherWeekday === day.value
                ? 'border-fb-blue font-medium text-fb-blue'
                : 'border-transparent text-fb-secondary hover:text-fb-text'"
              @click="otherWeekday = day.value"
            >
              <span
                v-if="otherWeekday === day.value"
                class="h-1.5 w-1.5 rounded-full bg-fb-blue"
              />
              {{ day.label }}
            </button>
          </li>
        </ul>
      </div>

      <div class="border-t border-fb-line">
        <div
          v-if="scheduleTab !== 'other' && scheduleLayout === 'horizontal'"
          class="overflow-x-auto px-4 pb-4 pt-3"
        >
          <table class="w-full border-collapse text-[14px]">
            <thead>
              <tr class="bg-fb-canvas">
                <template v-if="filteredSchedule.length">
                  <th class="border border-fb-line px-3 py-2 text-left font-medium text-fb-secondary">
                    Group
                  </th>
                  <th class="border border-fb-line px-3 py-2 text-left font-medium text-fb-secondary">
                    Time
                  </th>
                  <th class="border border-fb-line px-3 py-2 text-left font-medium text-fb-secondary">
                    Course
                  </th>
                  <th class="border border-fb-line px-3 py-2 text-left font-medium text-fb-secondary">
                    Teacher
                  </th>
                </template>
                <th v-else class="h-9 border border-fb-line font-normal" />
              </tr>
            </thead>
            <tbody v-if="filteredSchedule.length">
              <tr
                v-for="row in filteredSchedule"
                :key="row.id"
                class="cursor-pointer hover:bg-fb-hover"
                @click="onSelectGroup(row.id)"
              >
                <td class="border border-fb-line px-3 py-2.5 text-fb-text">{{ row.name }}</td>
                <td class="border border-fb-line px-3 py-2.5 text-fb-secondary">{{ row.time }}</td>
                <td class="border border-fb-line px-3 py-2.5 text-fb-secondary">{{ row.course }}</td>
                <td class="border border-fb-line px-3 py-2.5 text-fb-secondary">{{ row.teacher }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div
          v-else-if="scheduleTab !== 'other' && scheduleLayout === 'vertical'"
          class="overflow-x-auto px-4 pb-4 pt-3"
        >
          <div class="flex min-w-[640px] gap-0 border border-fb-line">
            <div class="w-16 shrink-0 border-r border-fb-line bg-fb-canvas" />
            <div
              v-for="slot in displayTimeSlots"
              :key="slot"
              class="flex min-h-[120px] flex-1 flex-col gap-2 border-r border-fb-line p-2 last:border-r-0"
            >
              <span class="text-center text-[11px] text-fb-icon">{{ slot }}</span>
              <button
                v-for="row in groupsAtTimeSlot(slot)"
                :key="row.id"
                type="button"
                class="rounded bg-fb-line px-2 py-2 text-left text-[12px] text-fb-secondary hover:bg-fb-line-strong"
                @click="onSelectGroup(row.id)"
              >
                {{ row.name }}
              </button>
              <div v-if="!groupsAtTimeSlot(slot).length" class="flex flex-1 flex-col gap-2">
                <div class="h-8 rounded bg-fb-canvas" />
                <div class="h-8 rounded bg-fb-canvas" />
              </div>
            </div>
          </div>
        </div>

        <div
          v-else-if="scheduleTab === 'other' && scheduleLayout === 'horizontal'"
          class="overflow-x-auto px-4 pb-4 pt-3"
        >
          <div class="grid min-w-[640px] grid-cols-5 gap-3">
            <div v-for="slot in displayTimeSlots" :key="slot" class="flex flex-col gap-2">
              <button
                v-for="row in groupsAtTimeSlot(slot)"
                :key="row.id"
                type="button"
                class="h-9 rounded bg-fb-line px-2 text-left text-[12px] text-fb-secondary hover:bg-fb-line-strong"
                @click="onSelectGroup(row.id)"
              >
                {{ row.name }}
              </button>
              <div
                v-for="n in Math.max(2 - groupsAtTimeSlot(slot).length, 0)"
                :key="`ph-${slot}-${n}`"
                class="h-9 rounded bg-fb-canvas"
              />
            </div>
          </div>
        </div>

        <div v-else class="overflow-x-auto px-4 pb-4 pt-3">
          <div class="grid min-w-[640px] grid-cols-5 gap-4">
            <div v-for="slot in displayTimeSlots" :key="slot" class="flex flex-col items-stretch gap-3">
              <button
                v-for="row in groupsAtTimeSlot(slot)"
                :key="row.id"
                type="button"
                class="h-10 w-full rounded bg-fb-line text-[12px] text-fb-secondary hover:bg-fb-line-strong"
                @click="onSelectGroup(row.id)"
              >
                {{ row.name }}
              </button>
              <div
                v-for="n in Math.max(2 - groupsAtTimeSlot(slot).length, 0)"
                :key="`vph-${slot}-${n}`"
                class="h-10 rounded bg-fb-canvas"
              />
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
