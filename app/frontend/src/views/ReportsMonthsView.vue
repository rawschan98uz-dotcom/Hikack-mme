<script setup lang="ts">
/**
 * "Страница месяца": the students' months like pages of a paper ledger. Every month line of a student
 * (charged, paid, left) is shown on the page of the calendar month it begins in. A debt for September
 * paid in December disappears from the September page — and is December's income in the P&L.
 */
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { downloadCsv } from '../utils/csvExport';
import { studentRoute } from '../utils/crossLinks';

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

const STATE: Record<LineRow['state'], { label: string; cls: string }> = {
  paid: { label: 'Оплачено', cls: 'bg-emerald-100 text-emerald-700' },
  partial: { label: 'Оплачено частично', cls: 'bg-amber-100 text-amber-800' },
  unpaid: { label: 'Не оплачено', cls: 'bg-red-100 text-red-700' },
  ahead: { label: 'Аванс', cls: 'bg-sky-100 text-sky-800' },
  written_off: { label: 'Списано', cls: 'bg-slate-200 text-slate-700' },
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

async function loadMonths() {
  loading.value = true;
  error.value = '';
  try {
    const { data } = await client.get<ApiEnvelope<MonthRow[]>>('/reports/months');
    months.value = data.data;
  } catch (err: any) {
    error.value = err?.response?.data?.message || 'Не удалось загрузить месяцы';
  } finally {
    loading.value = false;
  }
}

async function openMonth(month: string) {
  pageLoading.value = true;
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
    ['Ученик', 'Телефон', 'Группа', 'Филиал', 'Месяц с', 'Месяц по', 'Начислено', 'Оплачено', 'Осталось', 'Состояние'],
    page.value.rows.map((row) => [
      row.student, row.phone, row.group, row.branch, day(row.period_start), day(row.period_end),
      row.amount, row.paid, row.left, STATE[row.state].label,
    ]),
  );
}

onMounted(loadMonths);
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="!mb-1 text-[28px] font-normal text-fb-secondary">Месяцы учеников</h1>
      <p class="text-sm text-fb-secondary">
        Как страницы тетради: у каждого ученика на каждый его месяц есть строка — сколько начислено, сколько оплачено
        и что осталось. Сумма строки не меняется. Долг за сентябрь, оплаченный в декабре, исчезает со страницы
        сентября (а в отчёте о прибыли это приход декабря).
      </p>
    </div>

    <div class="overflow-hidden rounded-2xl border border-fb-line bg-fb-card shadow-sm">
      <div v-if="loading" class="p-12 text-center text-fb-secondary">Загружаю…</div>
      <div v-else-if="error" class="p-12 text-center text-fb-danger">{{ error }}</div>
      <div v-else-if="!months.length" class="p-12 text-center text-fb-secondary">
        Пока нет ни одной строки: месяцы появляются у учеников, которые состоят в группе с ценой курса.
      </div>
      <table v-else class="w-full text-left text-sm">
        <thead class="border-b border-fb-line bg-fb-canvas text-xs font-semibold uppercase tracking-wider text-fb-secondary">
          <tr>
            <th class="px-5 py-3">Месяц</th>
            <th class="px-5 py-3 text-right">Строк</th>
            <th class="px-5 py-3 text-right">Начислено</th>
            <th class="px-5 py-3 text-right">Оплачено</th>
            <th class="px-5 py-3 text-right">Хвост (не оплачено)</th>
            <th class="px-5 py-3 text-right">Должников</th>
            <th class="px-5 py-3 text-right">Списано</th>
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
            <td class="px-5 py-3 font-semibold text-fb-text">{{ row.title }}</td>
            <td class="px-5 py-3 text-right text-fb-secondary">{{ row.lines }}</td>
            <td class="px-5 py-3 text-right">{{ money(row.charged) }}</td>
            <td class="px-5 py-3 text-right text-emerald-700">{{ money(row.paid) }}</td>
            <td class="px-5 py-3 text-right font-semibold" :class="row.left ? 'text-rose-700' : 'text-fb-secondary'">
              {{ money(row.left) }}
            </td>
            <td class="px-5 py-3 text-right" :class="row.debtors ? 'text-rose-700' : 'text-fb-secondary'">{{ row.debtors }}</td>
            <td class="px-5 py-3 text-right text-fb-secondary">{{ row.written_off ? money(row.written_off) : '—' }}</td>
            <td class="px-5 py-3 text-right text-xs font-medium text-fb-blue">Открыть страницу →</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="page || pageLoading" class="overflow-hidden rounded-2xl border border-fb-line bg-fb-card shadow-sm">
      <div v-if="pageLoading && !page" class="p-12 text-center text-fb-secondary">Загружаю…</div>
      <template v-else-if="page">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-fb-line px-5 py-4">
          <div>
            <div class="text-lg font-semibold text-fb-text">{{ page.title }}</div>
            <div class="text-xs text-fb-secondary">
              Начислено {{ money(page.summary.charged) }} · оплачено {{ money(page.summary.paid) }} ·
              <span class="font-semibold text-rose-700">хвост {{ money(page.summary.left) }}</span>
              <template v-if="page.summary.debtors"> (должников: {{ page.summary.debtors }})</template>
            </div>
          </div>
          <div class="flex items-center gap-4">
            <label class="flex cursor-pointer items-center gap-2 text-sm text-fb-secondary">
              <input v-model="onlyUnpaid" type="checkbox" class="h-4 w-4" @change="toggleUnpaid" />
              Только неоплаченные
            </label>
            <button
              type="button"
              class="rounded-lg border border-fb-line px-3 py-1.5 text-sm text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
              @click="exportPage"
            >
              Export
            </button>
          </div>
        </div>
        <div v-if="!page.rows.length" class="p-10 text-center text-fb-secondary">
          {{ onlyUnpaid ? 'На этой странице всё оплачено.' : 'На этой странице нет строк.' }}
        </div>
        <table v-else class="w-full text-left text-sm">
          <thead class="border-b border-fb-line bg-fb-canvas text-xs font-semibold uppercase tracking-wider text-fb-secondary">
            <tr>
              <th class="px-5 py-3">Ученик</th>
              <th class="px-5 py-3">Группа</th>
              <th class="px-5 py-3">Его месяц</th>
              <th class="px-5 py-3 text-right">Начислено</th>
              <th class="px-5 py-3 text-right">Оплачено</th>
              <th class="px-5 py-3 text-right">Осталось</th>
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
                <div v-if="row.discount" class="text-[11px] text-fb-secondary">скидка {{ money(row.discount) }}</div>
              </td>
              <td class="px-5 py-3 text-right text-emerald-700">{{ money(row.paid) }}</td>
              <td class="px-5 py-3 text-right font-semibold" :class="row.left ? 'text-rose-700' : 'text-fb-secondary'">
                {{ money(row.left) }}
              </td>
              <td class="px-5 py-3 text-right">
                <span class="inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium" :class="STATE[row.state].cls">
                  {{ STATE[row.state].label }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>
  </div>
</template>
