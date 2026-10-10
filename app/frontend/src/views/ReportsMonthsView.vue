<script setup lang="ts">
/**
 * "Страница месяца": the students' months like pages of a paper ledger. Every month line of a student
 * (charged, paid, left) is shown on the page of the calendar month it begins in. A debt for September
 * paid in December disappears from the September page — and is December's income in the P&L.
 */
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { t, type MessageKey } from '../i18n';
import { apiErrorMessage } from '../utils/apiError';
import { formatMonthTitle } from '../utils/dates';
import { downloadCsv } from '../utils/csvExport';
import { studentRoute } from '../utils/crossLinks';
import { onCardsReturn } from '../utils/cardStack';

interface MonthRow {
  month: string;
  title: string;
  lines: number;
  charged: number;
  paid: number;
  left: number;
  written_off: number;
  debtors: number;
}

interface LineRow {
  id: number;
  student_id: number;
  student: string;
  phone: string;
  student_status_label: string;
  branch: string;
  group: string;
  period_start: string;
  period_end: string;
  price: number;
  discount: number;
  amount: number;
  paid: number;
  left: number;
  written_off: number;
  paid_at: string | null;
  state: 'paid' | 'partial' | 'unpaid' | 'ahead' | 'written_off';
}

interface MonthPage {
  month: string;
  title: string;
  summary: { lines: number; charged: number; paid: number; left: number; written_off: number; debtors: number };
  rows: LineRow[];
}

const STATE: Record<LineRow['state'], { label: MessageKey; cls: string }> = {
  paid: { label: 'months.state.paid', cls: 'bg-emerald-100 text-emerald-700' },
  partial: { label: 'months.state.partial', cls: 'bg-amber-100 text-amber-800' },
  unpaid: { label: 'months.state.unpaid', cls: 'bg-red-100 text-red-700' },
  ahead: { label: 'months.state.ahead', cls: 'bg-sky-100 text-sky-800' },
  written_off: { label: 'months.state.writtenOff', cls: 'bg-slate-200 text-slate-700' },
};

const router = useRouter();
const months = ref<MonthRow[]>([]);
const loading = ref(true);
const error = ref('');
const page = ref<MonthPage | null>(null);
const pageLoading = ref(false);
const onlyUnpaid = ref(true);

function money(value: number) {
  return Math.round(value || 0).toLocaleString('ru-RU');
}

function day(iso: string) {
  const [year, month, date] = iso.split('-');
  return `${date}.${month}.${year}`;
}

async function loadMonths(quiet = false) {
  if (!quiet) loading.value = true;
  error.value = '';
  try {
    const { data } = await client.get<ApiEnvelope<MonthRow[]>>('/reports/months');
    months.value = data.data;
  } catch (err: unknown) {
    error.value = apiErrorMessage(err, t('months.loadFailed'));
  } finally {
    loading.value = false;
  }
}

async function openMonth(month: string, quiet = false) {
  if (!quiet) pageLoading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<MonthPage>>('/reports/months', {
      params: { month, ...(onlyUnpaid.value ? { only_unpaid: 1 } : {}) },
    });
    page.value = data.data;
  } finally {
    pageLoading.value = false;
  }
}

function toggleUnpaid() {
  if (page.value) openMonth(page.value.month);
}

function exportPage() {
  if (!page.value) return;
  downloadCsv(
    `months-${page.value.month}.csv`,
    [
      t('months.student'), t('common.phone'), t('schedule.group'), t('common.branch'), t('months.monthFrom'),
      t('months.monthTo'), t('months.charged'), t('months.paid'), t('months.left'), t('months.state'),
    ],
    page.value.rows.map((row) => [
      row.student, row.phone, row.group, row.branch, day(row.period_start), day(row.period_end),
      row.amount, row.paid, row.left, t(STATE[row.state].label),
    ]),
  );
}

// A card opened from here is closed: show fresh data without the "Loading…" blink
onCardsReturn(-1, () => {
  void loadMonths(true);
  if (page.value) void openMonth(page.value.month, true);
});

onMounted(() => loadMonths());
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="!mb-1 text-[28px] font-normal text-fb-secondary">{{ t('months.title') }}</h1>
      <p class="text-sm text-fb-secondary">
        {{ t('months.subtitle') }}
      </p>
    </div>

    <div class="overflow-hidden rounded-2xl border border-fb-line bg-fb-card shadow-sm">
      <div v-if="loading" class="p-12 text-center text-fb-secondary">{{ t('common.loading') }}</div>
      <div v-else-if="error" class="p-12 text-center text-fb-danger">{{ error }}</div>
      <div v-else-if="!months.length" class="p-12 text-center text-fb-secondary">
        {{ t('months.empty') }}
      </div>
      <table v-else class="w-full text-left text-sm">
        <thead class="border-b border-fb-line bg-fb-canvas text-xs font-semibold uppercase tracking-wider text-fb-secondary">
          <tr>
            <th class="px-5 py-3">{{ t('common.month') }}</th>
            <th class="px-5 py-3 text-right">{{ t('months.lines') }}</th>
            <th class="px-5 py-3 text-right">{{ t('months.charged') }}</th>
            <th class="px-5 py-3 text-right">{{ t('months.paid') }}</th>
            <th class="px-5 py-3 text-right">{{ t('months.tail') }}</th>
            <th class="px-5 py-3 text-right">{{ t('months.debtors') }}</th>
            <th class="px-5 py-3 text-right">{{ t('months.writtenOff') }}</th>
            <th class="px-5 py-3" />
          </tr>
        </thead>
        <tbody class="divide-y divide-fb-line">
          <tr
            v-for="row in months"
            :key="row.month"
            class="cursor-pointer hover:bg-fb-hover/40"
            :class="page?.month === row.month ? 'bg-fb-hover/60' : ''"
            @click="openMonth(row.month)"
          >
            <td class="px-5 py-3 font-semibold text-fb-text">{{ formatMonthTitle(row.month) }}</td>
            <td class="px-5 py-3 text-right text-fb-secondary">{{ row.lines }}</td>
            <td class="px-5 py-3 text-right">{{ money(row.charged) }}</td>
            <td class="px-5 py-3 text-right text-emerald-700">{{ money(row.paid) }}</td>
            <td class="px-5 py-3 text-right font-semibold" :class="row.left ? 'text-rose-700' : 'text-fb-secondary'">
              {{ money(row.left) }}
            </td>
            <td class="px-5 py-3 text-right" :class="row.debtors ? 'text-rose-700' : 'text-fb-secondary'">{{ row.debtors }}</td>
            <td class="px-5 py-3 text-right text-fb-secondary">{{ row.written_off ? money(row.written_off) : '—' }}</td>
            <td class="px-5 py-3 text-right text-xs font-medium text-fb-blue">{{ t('months.openPage') }} →</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="page || pageLoading" class="overflow-hidden rounded-2xl border border-fb-line bg-fb-card shadow-sm">
      <div v-if="pageLoading && !page" class="p-12 text-center text-fb-secondary">{{ t('common.loading') }}</div>
      <template v-else-if="page">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-fb-line px-5 py-4">
          <div>
            <div class="text-lg font-semibold text-fb-text">{{ formatMonthTitle(page.month) }}</div>
            <div class="text-xs text-fb-secondary">
              {{ t('months.summaryCharged', { amount: money(page.summary.charged) }) }} ·
              {{ t('months.summaryPaid', { amount: money(page.summary.paid) }) }} ·
              <span class="font-semibold text-rose-700">{{ t('months.summaryTail', { amount: money(page.summary.left) }) }}</span>
              <template v-if="page.summary.debtors"> ({{ t('months.summaryDebtors', { count: page.summary.debtors }) }})</template>
            </div>
          </div>
          <div class="flex items-center gap-4">
            <label class="flex cursor-pointer items-center gap-2 text-sm text-fb-secondary">
              <input v-model="onlyUnpaid" type="checkbox" class="h-4 w-4" @change="toggleUnpaid" />
              {{ t('months.onlyUnpaid') }}
            </label>
            <button
              type="button"
              class="rounded-lg border border-fb-line px-3 py-1.5 text-sm text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
              @click="exportPage"
            >
              {{ t('common.export') }}
            </button>
          </div>
        </div>
        <div v-if="!page.rows.length" class="p-10 text-center text-fb-secondary">
          {{ onlyUnpaid ? t('months.allPaid') : t('months.noLines') }}
        </div>
        <table v-else class="w-full text-left text-sm">
          <thead class="border-b border-fb-line bg-fb-canvas text-xs font-semibold uppercase tracking-wider text-fb-secondary">
            <tr>
              <th class="px-5 py-3">{{ t('months.student') }}</th>
              <th class="px-5 py-3">{{ t('schedule.group') }}</th>
              <th class="px-5 py-3">{{ t('months.hisMonth') }}</th>
              <th class="px-5 py-3 text-right">{{ t('months.charged') }}</th>
              <th class="px-5 py-3 text-right">{{ t('months.paid') }}</th>
              <th class="px-5 py-3 text-right">{{ t('months.left') }}</th>
              <th class="px-5 py-3" />
            </tr>
          </thead>
          <tbody class="divide-y divide-fb-line">
            <tr v-for="row in page.rows" :key="row.id" class="hover:bg-fb-hover/40">
              <td class="px-5 py-3">
                <button type="button" class="font-semibold text-fb-blue hover:underline" @click="router.push(studentRoute(row.student_id))">
                  {{ row.student }}
                </button>
                <div class="text-xs text-fb-secondary">{{ row.phone }} · {{ row.student_status_label }}</div>
              </td>
              <td class="px-5 py-3 text-fb-secondary">{{ row.group || '—' }}</td>
              <td class="whitespace-nowrap px-5 py-3 text-fb-secondary">{{ day(row.period_start) }} — {{ day(row.period_end) }}</td>
              <td class="px-5 py-3 text-right">
                {{ money(row.amount) }}
                <div v-if="row.discount" class="text-[11px] text-fb-secondary">{{ t('payHint.discount', { amount: money(row.discount) }) }}</div>
              </td>
              <td class="px-5 py-3 text-right text-emerald-700">{{ money(row.paid) }}</td>
              <td class="px-5 py-3 text-right font-semibold" :class="row.left ? 'text-rose-700' : 'text-fb-secondary'">
                {{ money(row.left) }}
              </td>
              <td class="px-5 py-3 text-right">
                <span class="inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium" :class="STATE[row.state].cls">
                  {{ t(STATE[row.state].label) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>
  </div>
</template>
