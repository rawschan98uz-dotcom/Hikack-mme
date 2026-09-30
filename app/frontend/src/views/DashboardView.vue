<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter, type RouteLocationRaw } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { useAuthStore } from '../stores/auth';
import DashboardCardIcon from '../components/DashboardCardIcon.vue';
import SchedulePanel from '../components/SchedulePanel.vue';
import TeacherCheckInPanel from '../components/TeacherCheckInPanel.vue';
import type { ScheduleRow } from '../types/schedule';
import { groupRoute, studentRoute } from '../utils/crossLinks';
import { canAccessRoute, PERM } from '../utils/rbac';

interface DashboardStats {
  active_leads: number;
  active_students: number;
  groups: number;
  debtors: number;
  trial_students: number;
  left_active_group: number;
  left_after_trial: number;
  finance_chart: { label: string; value: number }[];
  schedule: ScheduleRow[];
  unpaid_leavers?: UnpaidLeaver[];
  /** My overdue and today's reminders (without "left without paying", which has its own block). */
  reminders?: DashboardReminder[];
}

interface DashboardReminder {
  id: number;
  title: string;
  details: string;
  due_date: string;
  status: string;
  assigned_to_id: number | null;
  assigned_to: string;
  student_id: number | null;
  kind?: string;
}

/** Automatic reminder: a student left / finished the course with unpaid months. */
interface UnpaidLeaver {
  reminder_id: number;
  student_id: number | null;
  title: string;
  details: string;
  created_at: string;
  /** true while the debt is not paid: "Решено" is disabled (only CEO may write it off with a reason). */
  locked: boolean;
  debt_months: number;
  debt_amount: number;
}

const router = useRouter();
const auth = useAuthStore();
const stats = ref<DashboardStats | null>(null);
const loading = ref(true);

const cardsRowPrimary = [
  { key: 'active_leads', label: 'Active leads', icon: 'leads', to: '/leads' },
  { key: 'active_students', label: 'Active students', icon: 'students', to: '/students?statuses=1' },
  { key: 'groups', label: 'Groups', icon: 'groups', to: '/groups' },
  { key: 'debtors', label: 'Debtors', icon: 'debtors', to: '/students/debtors' },
] as const;

const cardsRowSecondary = [
  { key: 'trial_students', label: 'In a trial lesson', icon: 'trial', to: '/students?statuses=1' },
  { key: 'left_active_group', label: 'Left active group', icon: 'left-group', to: '/reports/left-students?status=8' },
  { key: 'left_after_trial', label: 'Left after trial period', icon: 'left-trial', to: '/reports/left-students?status=7' },
] as const;

type DashboardCard = (typeof cardsRowPrimary)[number] | (typeof cardsRowSecondary)[number];
// Teachers get no money figures (backend sends zeros and an empty chart).
// The revenue chart is a money report: CEO and branch director only, not the administrator
const showFinanceChart = computed(() => auth.isCeo || auth.can(PERM.FINANCE_VIEW));
// Debtors: everyone who works with payments (teachers never see money)
const showMoneyCards = computed(() => auth.role !== 'teacher');
const MONEY_CARDS: readonly string[] = ['debtors'];

// Show only cards that lead to a page the user may open (teacher: no leads, debtors, reports).
const dashboardCardRows = computed(() =>
  [cardsRowPrimary, cardsRowSecondary]
    .map((row) =>
      row.filter(
        (card) =>
          (showMoneyCards.value || !MONEY_CARDS.includes(card.key)) &&
          (auth.isCeo || canAccessRoute(card.to, auth.permissions)),
      ),
    )
    .filter((row) => row.length > 0),
);

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

const unpaidLeavers = computed(() => stats.value?.unpaid_leavers ?? []);
const canResolveReminders = computed(() => auth.isCeo || auth.can(PERM.REMINDERS_WRITE));
const resolvingId = ref<number | null>(null);

async function closeUnpaidLeaver(item: UnpaidLeaver, writeOffReason = '') {
  resolvingId.value = item.reminder_id;
  try {
    await client.post(`/reminders/${item.reminder_id}/complete`, writeOffReason ? { write_off_reason: writeOffReason } : {});
    if (stats.value?.unpaid_leavers) {
      stats.value.unpaid_leavers = stats.value.unpaid_leavers.filter((r) => r.reminder_id !== item.reminder_id);
    }
    window.dispatchEvent(new Event('reminders-changed'));
  } catch (error) {
    const message = (error as { response?: { data?: { message?: string } } })?.response?.data?.message;
    window.alert(message || 'Не удалось закрыть напоминание');
  } finally {
    resolvingId.value = null;
  }
}

function resolveUnpaidLeaver(item: UnpaidLeaver) {
  if (item.locked) return; // debt not paid yet
  if (!window.confirm(`Долг оплачен. Закрыть напоминание «${item.title}»?`)) return;
  closeUnpaidLeaver(item);
}

// CEO only: close without payment, the reason is kept in the history
const writeOffModal = reactive({
  show: false,
  item: null as UnpaidLeaver | null,
  reason: '',
  error: '',
});

function writeOffUnpaidLeaver(item: UnpaidLeaver) {
  writeOffModal.item = item;
  writeOffModal.reason = '';
  writeOffModal.error = '';
  writeOffModal.show = true;
}

async function confirmWriteOff() {
  if (!writeOffModal.item) return;
  const reason = writeOffModal.reason.trim();
  if (reason.length < 3) {
    writeOffModal.error = 'Укажите причину (минимум 3 символа).';
    return;
  }
  writeOffModal.show = false;
  await closeUnpaidLeaver(writeOffModal.item, reason);
}

// Ordinary reminders: overdue + today, so nobody has to open the Reminders page to notice them
const myReminders = computed(() => stats.value?.reminders ?? []);
const showReminders = computed(() => auth.isCeo || auth.can(PERM.REMINDERS_VIEW));
const completingReminderId = ref<number | null>(null);

function canCompleteReminder(reminder: DashboardReminder) {
  return auth.isCeo || auth.can(PERM.REMINDERS_WRITE) || reminder.assigned_to_id === auth.user?.id;
}

async function completeDashboardReminder(reminder: DashboardReminder) {
  completingReminderId.value = reminder.id;
  try {
    await client.post(`/reminders/${reminder.id}/complete`);
    if (stats.value?.reminders) {
      stats.value.reminders = stats.value.reminders.filter((r) => r.id !== reminder.id);
    }
    window.dispatchEvent(new Event('reminders-changed'));
  } catch (error) {
    const message = (error as { response?: { data?: { message?: string } } })?.response?.data?.message;
    window.alert(message || 'Не удалось отметить напоминание');
  } finally {
    completingReminderId.value = null;
  }
}

// A click opens the window that solves it: money without a course price -> the student's edit form
// (put them into a group, the копилка counts the months); other reminders about a student -> the card.
function openDashboardReminder(reminder: DashboardReminder) {
  if (reminder.kind === 'online_payment_check' && reminder.student_id) {
    goTo(studentRoute(reminder.student_id, { edit: '1' }));
  } else if (reminder.student_id) {
    goTo(studentRoute(reminder.student_id));
  } else {
    goTo('/reminders');
  }
}

function formatDay(iso: string) {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
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
      <TeacherCheckInPanel v-if="auth.role === 'teacher'" />

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

      <div v-if="unpaidLeavers.length" class="border-b border-rose-200 bg-rose-50 px-5 py-4">
        <div class="mb-3 flex items-center justify-between gap-3">
          <h2 class="text-[15px] font-semibold text-rose-800">
            ⚠️ Ушли, не заплатив — {{ unpaidLeavers.length }}
          </h2>
          <button type="button" class="text-xs font-medium text-rose-700 hover:underline" @click="goTo('/reports/left-students?with_debt=1')">
            Все ушедшие с долгом →
          </button>
        </div>
        <ul class="space-y-2">
          <li
            v-for="item in unpaidLeavers"
            :key="item.reminder_id"
            class="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-rose-200 bg-white px-4 py-3"
          >
            <div
              class="min-w-0"
              :class="item.student_id ? 'cursor-pointer' : ''"
              title="Открыть карточку ученика"
              @click="item.student_id && goTo(studentRoute(item.student_id))"
            >
              <p class="text-sm font-semibold text-fb-text">{{ item.title }}</p>
              <p class="mt-0.5 whitespace-pre-line text-xs text-fb-secondary">{{ item.details }}</p>
              <p class="mt-1 text-[11px] text-fb-icon">Ушёл: {{ formatDay(item.created_at) }}</p>
              <p v-if="item.locked" class="mt-1 text-xs font-semibold text-rose-700">
                Осталось оплатить: {{ item.debt_months }} мес.<span v-if="item.debt_amount"> (≈ {{ formatSum(item.debt_amount) }} сум)</span>
              </p>
              <p v-else class="mt-1 text-xs font-semibold text-emerald-700">✓ Долг оплачен — можно закрыть</p>
            </div>
            <div class="flex shrink-0 gap-2">
              <button
                v-if="item.student_id"
                type="button"
                class="rounded-lg border border-fb-line px-3 py-1.5 text-xs font-medium text-fb-blue hover:bg-fb-hover"
                @click="goTo(studentRoute(item.student_id))"
              >
                Открыть ученика
              </button>
              <button
                v-if="auth.isCeo && item.locked"
                type="button"
                class="rounded-lg border border-rose-300 px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100"
                :disabled="resolvingId === item.reminder_id"
                @click="writeOffUnpaidLeaver(item)"
              >
                Списать долг
              </button>
              <button
                v-if="canResolveReminders"
                type="button"
                class="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-medium text-white"
                :class="item.locked ? 'cursor-not-allowed opacity-35' : 'shadow-md ring-2 ring-rose-300 hover:bg-rose-700'"
                :disabled="item.locked || resolvingId === item.reminder_id"
                :title="item.locked ? 'Сначала примите оплату в карточке ученика' : 'Долг оплачен — закрыть напоминание'"
                @click="resolveUnpaidLeaver(item)"
              >
                Решено
              </button>
            </div>
          </li>
        </ul>
      </div>

      <div v-if="showReminders && myReminders.length" class="border-b border-amber-200 bg-amber-50 px-5 py-4">
        <div class="mb-3 flex items-center justify-between gap-3">
          <h2 class="text-[15px] font-semibold text-amber-900">
            ⏰ Напоминания на сегодня и просроченные — {{ myReminders.length }}
          </h2>
          <button type="button" class="text-xs font-medium text-amber-800 hover:underline" @click="goTo('/reminders')">
            Все напоминания →
          </button>
        </div>
        <ul class="space-y-2">
          <li
            v-for="reminder in myReminders"
            :key="reminder.id"
            class="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-amber-200 bg-white px-4 py-3"
          >
            <div class="min-w-0 cursor-pointer" @click="openDashboardReminder(reminder)">
              <p class="text-sm font-semibold text-fb-text">{{ reminder.title }}</p>
              <p v-if="reminder.details" class="mt-0.5 whitespace-pre-line text-xs text-fb-secondary">{{ reminder.details }}</p>
              <p class="mt-1 text-[11px]" :class="reminder.status === 'overdue' ? 'font-semibold text-fb-danger' : 'text-fb-icon'">
                {{ reminder.status === 'overdue' ? 'Просрочено' : 'Сегодня' }} · {{ formatDay(reminder.due_date) }} · {{ reminder.assigned_to }}
              </p>
            </div>
            <div class="flex shrink-0 gap-2">
              <button
                v-if="reminder.student_id"
                type="button"
                class="rounded-lg border border-fb-line px-3 py-1.5 text-xs font-medium text-fb-blue hover:bg-fb-hover"
                @click="goTo(studentRoute(reminder.student_id))"
              >
                Открыть ученика
              </button>
              <button
                v-if="canCompleteReminder(reminder)"
                type="button"
                class="rounded-lg border border-emerald-300 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
                :disabled="completingReminderId === reminder.id"
                @click="completeDashboardReminder(reminder)"
              >
                ✓ Выполнено
              </button>
            </div>
          </li>
        </ul>
      </div>

      <div v-if="writeOffModal.show" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
        <div class="w-full max-w-md overflow-hidden rounded-2xl bg-fb-card shadow-2xl">
          <div class="border-b border-fb-line px-6 py-4">
            <h2 class="text-lg font-semibold text-rose-700">Списать долг без оплаты?</h2>
          </div>
          <div class="space-y-3 px-6 py-5">
            <p class="text-[15px] font-medium text-fb-text">{{ writeOffModal.item?.title }}</p>
            <p v-if="writeOffModal.item?.debt_months" class="text-sm text-fb-secondary">
              Будет списано: {{ writeOffModal.item.debt_months }} мес.<span v-if="writeOffModal.item.debt_amount">
                (≈ {{ formatSum(writeOffModal.item.debt_amount) }} сум)</span>.
              Долг исчезнет из отчётов, в отчёте «Ушедшие» останется пометка «Списано» с причиной.
            </p>
            <label class="block text-sm font-medium text-fb-secondary">Причина (обязательно)</label>
            <textarea
              v-model="writeOffModal.reason"
              rows="3"
              class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
              placeholder="Например: переехал в другой город, связаться не удалось"
            />
            <p v-if="writeOffModal.error" class="text-sm text-fb-danger">{{ writeOffModal.error }}</p>
          </div>
          <div class="flex justify-end gap-3 border-t border-fb-line px-6 py-4">
            <button
              type="button"
              class="rounded-lg border border-fb-line px-5 py-2 text-sm font-medium text-fb-secondary hover:bg-fb-hover"
              @click="writeOffModal.show = false"
            >
              Отмена
            </button>
            <button
              type="button"
              class="rounded-lg bg-rose-600 px-5 py-2 text-sm font-medium text-white hover:bg-rose-700"
              @click="confirmWriteOff"
            >
              Списать
            </button>
          </div>
        </div>
      </div>

      <div v-if="showFinanceChart" class="relative min-h-[300px] border-b border-fb-line bg-fb-card lg:min-h-[340px]">
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
