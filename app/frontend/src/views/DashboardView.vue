<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter, type RouteLocationRaw } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import DashboardCardIcon from '../components/DashboardCardIcon.vue';
import SchedulePanel from '../components/SchedulePanel.vue';
import type { ScheduleRow } from '../types/schedule';
import { groupRoute } from '../utils/crossLinks';

interface DashboardStats {
  active_leads: number;
  active_students: number;
  groups: number;
  debtors: number;
  trial_students: number;
  paid_during_month: number;
  left_active_group: number;
  left_after_trial: number;
  finance_chart: { label: string; value: number }[];
  schedule: ScheduleRow[];
  reminders: ReminderRow[];
}

interface ReminderRow {
  id: number;
  title: string;
  details: string;
  due_date: string;
  status: string;
  assigned_to: string;
}

const router = useRouter();
const stats = ref<DashboardStats | null>(null);
const loading = ref(true);

const cardsRowPrimary = [
  { key: 'active_leads', label: 'Active leads', icon: 'leads', to: '/leads' },
  { key: 'active_students', label: 'Active students', icon: 'students', to: '/students?statuses=5' },
  { key: 'groups', label: 'Groups', icon: 'groups', to: '/groups' },
  { key: 'debtors', label: 'Debtors', icon: 'debtors', to: '/students/debtors' },
] as const;

const cardsRowSecondary = [
  { key: 'trial_students', label: 'In a trial lesson', icon: 'trial', to: '/students?statuses=1' },
  { key: 'paid_during_month', label: 'Paid during the month', icon: 'handshake', to: '/students?finance=paid_during_the_month' },
  { key: 'left_active_group', label: 'Left active group', icon: 'left-group', to: '/left-students?statuses=left_active_group' },
  { key: 'left_after_trial', label: 'Left after trial period', icon: 'left-trial', to: '/left-students?statuses=left_after_trial' },
] as const;

type DashboardCard = (typeof cardsRowPrimary)[number] | (typeof cardsRowSecondary)[number];
const dashboardCardRows = [cardsRowPrimary, cardsRowSecondary] as const;

const maxChartValue = computed(() => {
  const values = stats.value?.finance_chart.map((point) => point.value) ?? [0];
  return Math.max(...values, 1);
});

const hasChartData = computed(() => (stats.value?.finance_chart.length ?? 0) > 0);

function statValue(key: DashboardCard['key']) {
  return stats.value?.[key] ?? 0;
}

function formatSum(value: number) {
  return value.toLocaleString('en-US').replace(/,/g, ' ');
}

async function loadDashboard() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<DashboardStats>>('/dashboard');
    stats.value = data.data;
  } finally {
    loading.value = false;
  }
}

function goTo(to: RouteLocationRaw) {
  router.push(to);
}

function onSelectGroup(groupId: number) {
  router.push(groupRoute(groupId));
}

onMounted(loadDashboard);
</script>

<template>
  <div class="dashboard-page -m-6 min-h-full bg-fb-card border border-fb-line">
    <div v-if="loading" class="py-16 text-center text-[15px] text-fb-icon">
      Loading…
    </div>

    <template v-else>
      <div class="border-b border-fb-line">
        <div class="grid grid-cols-1 xl:grid-cols-2">
          <div
            v-for="(row, rowIndex) in dashboardCardRows"
            :key="rowIndex"
            class="grid grid-cols-2 gap-px bg-fb-line sm:grid-cols-4"
            :class="rowIndex === 0 ? 'xl:border-r xl:border-fb-line' : ''"
          >
            <button
              v-for="card in row"
              :key="card.key"
              type="button"
              class="dashboard-stat-card flex min-w-0 flex-col items-center bg-fb-card px-2 py-4 text-center hover:bg-fb-hover sm:px-3 sm:py-5"
              @click="goTo(card.to)"
            >
              <div class="dashboard-stat-icon mb-2 flex h-9 items-center justify-center text-fb-blue sm:mb-3 sm:h-10">
                <DashboardCardIcon :name="card.icon" :size="32" />
              </div>
              <p class="mb-1 text-[11px] font-semibold leading-tight text-fb-secondary sm:mb-2 sm:text-[13px] sm:leading-snug">
                {{ card.label }}
              </p>
              <p class="text-[22px] font-normal leading-none text-fb-blue sm:text-[28px]">
                {{ statValue(card.key) }}
              </p>
            </button>
          </div>
        </div>
      </div>

      <div class="relative min-h-[300px] border-b border-fb-line bg-fb-card lg:min-h-[340px]">
        <div
          v-if="!hasChartData"
          class="flex min-h-[300px] items-center justify-center text-[15px] text-fb-icon lg:min-h-[340px]"
        >
          No data to display
        </div>
        <div
          v-else
          class="flex min-h-[300px] items-end justify-center gap-8 px-8 pb-10 pt-8 lg:min-h-[340px]"
        >
          <div
            v-for="point in stats?.finance_chart"
            :key="point.label"
            class="flex flex-col items-center"
          >
            <div class="mb-3 flex h-[200px] w-12 items-end justify-center">
              <div
                class="w-10 rounded-t-sm bg-fb-blue"
                :style="{ height: `${Math.max((point.value / maxChartValue) * 100, 6)}%` }"
              />
            </div>
            <span class="text-[13px] text-fb-icon">{{ point.label }}</span>
            <span class="mt-1 text-[14px] font-medium text-fb-blue">{{ formatSum(point.value) }}</span>
          </div>
        </div>
      </div>

      <SchedulePanel
        :rows="stats?.schedule ?? []"
        @select-group="onSelectGroup"
      />
    </template>
  </div>
</template>

<style scoped>
.dashboard-stat-card {
  min-height: 118px;
}

@media (min-width: 1280px) {
  .dashboard-stat-card {
    min-height: 128px;
  }
}
</style>
