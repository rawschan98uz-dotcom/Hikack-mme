<script setup lang="ts">
import { dateToIso } from '../utils/dates';
import { onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { downloadCsv } from '../utils/csvExport';

interface PnlSummary {
  total_revenue: number;
  total_expenses: number;
  total_withdrawals: number;
  net_profit: number;
  profit_margin: number;
  date_from?: string | null;
  date_to?: string | null;
}

interface RevenueItem {
  method: string;
  label: string;
  amount: number;
  percent: number;
}

interface ExpenseItem {
  id: number | null;
  name: string;
  amount: number;
  percent: number;
}

/** One branch: its income (payments of its groups minus refunds), its expenses and the profit. */
interface BranchRow {
  branch_id: number | null;
  name: string;
  revenue: number;
  expenses: number;
  profit: number;
}

interface PnlData {
  summary: PnlSummary;
  branches: BranchRow[];
  revenue_by_method: RevenueItem[];
  expense_by_category: ExpenseItem[];
}

const loading = ref(true);
const pnl = ref<PnlData | null>(null);

const filters = reactive({
  preset: 'this_month',
  date_from: '',
  date_to: '',
});

function money(value: number) {
  return Math.round(value).toLocaleString('ru-RU');
}

function setPreset(preset: string) {
  filters.preset = preset;
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();

  if (preset === 'this_month') {
    const start = new Date(year, month, 1);
    const end = new Date(year, month + 1, 0);
    filters.date_from = dateToIso(start);
    filters.date_to = dateToIso(end);
  } else if (preset === 'last_month') {
    const start = new Date(year, month - 1, 1);
    const end = new Date(year, month, 0);
    filters.date_from = dateToIso(start);
    filters.date_to = dateToIso(end);
  } else if (preset === 'this_quarter') {
    const quarter = Math.floor(month / 3);
    const start = new Date(year, quarter * 3, 1);
    const end = new Date(year, (quarter + 1) * 3, 0);
    filters.date_from = dateToIso(start);
    filters.date_to = dateToIso(end);
  } else if (preset === 'this_year') {
    const start = new Date(year, 0, 1);
    const end = new Date(year, 11, 31);
    filters.date_from = dateToIso(start);
    filters.date_to = dateToIso(end);
  } else if (preset === 'all_time') {
    filters.date_from = '';
    filters.date_to = '';
  }
  void loadPnl();
}

async function loadPnl() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;

    const { data } = await client.get<ApiEnvelope<PnlData>>('/reports/pnl', { params });
    pnl.value = data.data;
  } finally {
    loading.value = false;
  }
}

function printReport() {
  window.print();
}

function exportCsv() {
  if (!pnl.value) return;
  const data = pnl.value;
  const csvRows = [
    ['Финансовый отчет о прибылях и убытках (P&L)'],
    [`Период: ${filters.date_from || 'За все время'} - ${filters.date_to || 'по текущий момент'}`],
    [],
    ['СВОДКА', 'Сумма (UZS)'],
    ['Валовой доход (Revenue)', String(data.summary.total_revenue)],
    ['Общие расходы (Expenses)', String(data.summary.total_expenses)],
    ['Вывод средств (Withdrawals)', String(data.summary.total_withdrawals)],
    ['Чистая прибыль (Net Profit)', String(data.summary.net_profit)],
    ['Рентабельность (Margin %)', `${data.summary.profit_margin}%`],
    [],
    ['ПО ФИЛИАЛАМ', 'Доход', 'Расход', 'Прибыль'],
  ];
  for (const row of data.branches) {
    csvRows.push([row.name, String(row.revenue), String(row.expenses), String(row.profit)]);
  }
  csvRows.push(['Общие', String(data.summary.total_revenue), String(data.summary.total_expenses), String(data.summary.net_profit)]);
  csvRows.push(...[
    [],
    ['ДОХОДЫ ПО СПОСОБАМ ОПЛАТЫ', 'Сумма (UZS)', 'Доля (%)'],
  ]);
  for (const item of data.revenue_by_method) {
    csvRows.push([item.label, String(item.amount), `${item.percent}%`]);
  }
  csvRows.push([]);
  csvRows.push(['РАСХОДЫ ПО КАТЕГОРИЯМ', 'Сумма (UZS)', 'Доля (%)']);
  for (const item of data.expense_by_category) {
    csvRows.push([item.name, String(item.amount), `${item.percent}%`]);
  }
  // A real file, not a link: a «#» in a name used to cut the rest of the file off
  const [header, ...rest] = csvRows;
  downloadCsv(`pnl_report_${filters.date_from || 'start'}_${filters.date_to || 'end'}.csv`, header, rest);
}

onMounted(() => {
  setPreset('this_month');
});
</script>

<template>
  <div class="space-y-6 print:p-0">
    <!-- Header & Actions -->
    <div class="flex flex-wrap items-center justify-between gap-4 no-print">
      <div>
        <h1 class="text-2xl font-bold text-fb-text">Финансовый отчет (P&L)</h1>
        <p class="mt-0.5 text-sm text-fb-secondary">
          Отчет о доходах, расходах и чистой операционной прибыли (Profit & Loss)
        </p>
      </div>

      <div class="flex items-center gap-2">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg border border-fb-line bg-white px-3.5 py-2 text-sm font-medium text-fb-secondary shadow-sm hover:border-fb-blue hover:text-fb-blue transition-colors"
          @click="exportCsv"
        >
          <span>📥</span>
          <span>Экспорт CSV</span>
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg border border-fb-line bg-white px-3.5 py-2 text-sm font-medium text-fb-secondary shadow-sm hover:border-fb-blue hover:text-fb-blue transition-colors"
          @click="printReport"
        >
          <span>🖨️</span>
          <span>Печать отчета</span>
        </button>
      </div>
    </div>

    <!-- Filters Bar (Hidden on print) -->
    <div class="rounded-2xl border border-fb-line bg-fb-card p-4 space-y-3 no-print">
      <!-- Quick Presets -->
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-xs font-medium text-fb-secondary mr-1">Период:</span>
        <button
          v-for="p in [
            { key: 'this_month', label: 'Текущий месяц' },
            { key: 'last_month', label: 'Прошлый месяц' },
            { key: 'this_quarter', label: 'Текущий квартал' },
            { key: 'this_year', label: 'Этот год' },
            { key: 'all_time', label: 'За всё время' },
          ]"
          :key="p.key"
          type="button"
          class="rounded-lg px-3 py-1.5 text-xs font-semibold transition-all"
          :class="
            filters.preset === p.key
              ? 'bg-fb-blue text-white shadow-sm'
              : 'bg-fb-canvas text-fb-secondary hover:bg-fb-hover hover:text-fb-text'
          "
          @click="setPreset(p.key)"
        >
          {{ p.label }}
        </button>
      </div>

      <!-- Date Inputs & Branch -->
      <div class="flex flex-wrap items-end gap-3 pt-1 border-t border-fb-line">
        <div>
          <label class="mb-1 block text-xs text-fb-secondary">С даты</label>
          <input
            v-model="filters.date_from"
            type="date"
            class="rounded-lg border border-fb-line px-3 py-1.5 text-sm focus:border-fb-blue focus:outline-none"
            @change="filters.preset = 'custom'"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs text-fb-secondary">По дату</label>
          <input
            v-model="filters.date_to"
            type="date"
            class="rounded-lg border border-fb-line px-3 py-1.5 text-sm focus:border-fb-blue focus:outline-none"
            @change="filters.preset = 'custom'"
          />
        </div>
        <button
          type="button"
          class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-semibold text-white hover:bg-fb-hoverBtn transition-colors"
          @click="loadPnl"
        >
          Применить
        </button>
      </div>
    </div>

    <!-- Print Header (Visible only on print) -->
    <div class="hidden print:block text-center border-b pb-4 mb-4">
      <h1 class="text-xl font-bold uppercase tracking-wider">Отчет о доходах и расходах (P&L)</h1>
      <p class="text-xs text-gray-500 mt-1">
        Период: {{ filters.date_from || '—' }} по {{ filters.date_to || '—' }}
      </p>
    </div>

    <div v-if="loading" class="p-12 text-center text-fb-secondary">
      Формирование отчета P&L…
    </div>

    <template v-else-if="pnl">
      <!-- KPI Cards -->
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <!-- Revenue Card -->
        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-emerald-700">
            <span>Валовой доход</span>
            <span class="text-base">📈</span>
          </div>
          <div class="mt-2 text-2xl font-black text-gray-900">
            {{ pnl.summary.total_revenue.toLocaleString() }} <span class="text-xs font-semibold text-fb-secondary">UZS</span>
          </div>
          <div class="mt-1 text-xs text-fb-secondary">Поступления от студентов</div>
        </div>

        <!-- Expenses Card -->
        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-rose-700">
            <span>Общие расходы</span>
            <span class="text-base">📉</span>
          </div>
          <div class="mt-2 text-2xl font-black text-gray-900">
            {{ pnl.summary.total_expenses.toLocaleString() }} <span class="text-xs font-semibold text-fb-secondary">UZS</span>
          </div>
          <div class="mt-1 text-xs text-fb-secondary">Аренда, зарплаты, хознужды</div>
        </div>

        <!-- Net Profit Card -->
        <div
          class="rounded-2xl border p-5 shadow-sm"
          :class="
            pnl.summary.net_profit >= 0
              ? 'border-emerald-200 bg-emerald-50/40 text-emerald-950'
              : 'border-red-200 bg-red-50/40 text-red-950'
          "
        >
          <div class="flex items-center justify-between text-xs font-semibold uppercase tracking-wider">
            <span>Чистая прибыль</span>
            <span class="text-base">{{ pnl.summary.net_profit >= 0 ? '💰' : '⚠️' }}</span>
          </div>
          <div
            class="mt-2 text-2xl font-black"
            :class="pnl.summary.net_profit >= 0 ? 'text-emerald-700' : 'text-red-700'"
          >
            {{ pnl.summary.net_profit.toLocaleString() }} <span class="text-xs font-semibold">UZS</span>
          </div>
          <div class="mt-1 text-xs opacity-75">Операционный остаток кассы</div>
        </div>

        <!-- Margin Card -->
        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-fb-blue">
            <span>Рентабельность</span>
            <span class="text-base">📊</span>
          </div>
          <div class="mt-2 text-2xl font-black text-gray-900">
            {{ pnl.summary.profit_margin }}%
          </div>
          <div class="mt-1 text-xs text-fb-secondary">Отношение прибыли к доходу</div>
        </div>
      </div>

      <!-- Every branch separately + "Общие" = all branches together (owner, 2026-09-28) -->
      <div class="overflow-hidden rounded-2xl border border-fb-line bg-fb-card shadow-sm">
        <div class="border-b border-fb-line px-5 py-3">
          <h2 class="text-base font-bold text-fb-text">По филиалам</h2>
          <p class="text-xs text-fb-secondary">
            Доход — оплаты групп филиала минус возвраты; расход — расходы, записанные на этот филиал.
          </p>
        </div>
        <table class="w-full text-sm">
          <thead class="border-b border-fb-line bg-fb-canvas text-xs font-semibold uppercase tracking-wider text-fb-secondary">
            <tr>
              <th class="px-5 py-3 text-left">Филиал</th>
              <th class="px-5 py-3 text-right">Доход</th>
              <th class="px-5 py-3 text-right">Расход</th>
              <th class="px-5 py-3 text-right">Прибыль</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-fb-line">
            <tr v-for="row in pnl.branches" :key="row.branch_id ?? 'none'">
              <td class="px-5 py-3 font-medium text-fb-text">{{ row.name }}</td>
              <td class="px-5 py-3 text-right text-emerald-700">{{ money(row.revenue) }}</td>
              <td class="px-5 py-3 text-right text-rose-700">{{ money(row.expenses) }}</td>
              <td class="px-5 py-3 text-right font-semibold" :class="row.profit >= 0 ? 'text-fb-text' : 'text-red-700'">
                {{ money(row.profit) }}
              </td>
            </tr>
            <tr class="bg-fb-canvas font-bold">
              <td class="px-5 py-3 text-fb-text">Общие</td>
              <td class="px-5 py-3 text-right text-emerald-700">{{ money(pnl.summary.total_revenue) }}</td>
              <td class="px-5 py-3 text-right text-rose-700">{{ money(pnl.summary.total_expenses) }}</td>
              <td class="px-5 py-3 text-right" :class="pnl.summary.net_profit >= 0 ? 'text-fb-text' : 'text-red-700'">
                {{ money(pnl.summary.net_profit) }}
              </td>
            </tr>
          </tbody>
        </table>
        <p class="border-t border-fb-line px-5 py-3 text-xs text-fb-secondary">
          Изъятия владельца за период: <strong class="text-fb-text">{{ money(pnl.summary.total_withdrawals) }} UZS</strong>
          (в прибыль не входят, показаны отдельно).
        </p>
      </div>

      <!-- Breakdown Columns -->
      <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <!-- Revenue Structure -->
        <div class="rounded-2xl border border-fb-line bg-fb-card p-6 shadow-sm space-y-4">
          <div class="flex items-center justify-between border-b border-fb-line pb-3">
            <h2 class="text-base font-bold text-fb-text flex items-center gap-2">
              <span>💳</span>
              <span>Структура доходов по способам оплаты</span>
            </h2>
            <span class="text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full">
              {{ pnl.summary.total_revenue.toLocaleString() }} UZS
            </span>
          </div>

          <div v-if="!pnl.revenue_by_method.length || pnl.summary.total_revenue === 0" class="py-6 text-center text-xs text-fb-secondary">
            Нет поступлений за выбранный период
          </div>
          <div v-else class="space-y-3.5">
            <div
              v-for="item in pnl.revenue_by_method"
              :key="item.method"
              class="space-y-1.5"
            >
              <div class="flex justify-between text-xs">
                <span class="font-medium text-fb-text">{{ item.label }}</span>
                <span class="font-bold text-fb-text">
                  {{ item.amount.toLocaleString() }} UZS
                  <span class="ml-1 text-[11px] font-normal text-fb-secondary">({{ item.percent }}%)</span>
                </span>
              </div>
              <div class="h-2 w-full rounded-full bg-gray-100 overflow-hidden">
                <div
                  class="h-full bg-emerald-500 rounded-full transition-all duration-500"
                  :style="{ width: `${item.percent}%` }"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- Expense Structure -->
        <div class="rounded-2xl border border-fb-line bg-fb-card p-6 shadow-sm space-y-4">
          <div class="flex items-center justify-between border-b border-fb-line pb-3">
            <h2 class="text-base font-bold text-fb-text flex items-center gap-2">
              <span>📑</span>
              <span>Структура расходов по категориям</span>
            </h2>
            <span class="text-xs font-semibold text-rose-700 bg-rose-50 px-2.5 py-1 rounded-full">
              {{ pnl.summary.total_expenses.toLocaleString() }} UZS
            </span>
          </div>

          <div v-if="!pnl.expense_by_category.length || pnl.summary.total_expenses === 0" class="py-6 text-center text-xs text-fb-secondary">
            Нет расходов за выбранный период
          </div>
          <div v-else class="space-y-3.5 max-h-80 overflow-y-auto pr-1">
            <div
              v-for="cat in pnl.expense_by_category"
              :key="cat.id || 'uncat'"
              class="space-y-1.5"
            >
              <div class="flex justify-between text-xs">
                <span class="font-medium text-fb-text">{{ cat.name }}</span>
                <span class="font-bold text-fb-text">
                  {{ cat.amount.toLocaleString() }} UZS
                  <span class="ml-1 text-[11px] font-normal text-fb-secondary">({{ cat.percent }}%)</span>
                </span>
              </div>
              <div class="h-2 w-full rounded-full bg-gray-100 overflow-hidden">
                <div
                  class="h-full bg-rose-500 rounded-full transition-all duration-500"
                  :style="{ width: `${cat.percent}%` }"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Detailed P&L Statement Table -->
      <div class="overflow-hidden rounded-2xl border border-fb-line bg-fb-card shadow-sm">
        <div class="border-b border-fb-line px-6 py-4 bg-fb-canvas/50">
          <h3 class="text-sm font-bold text-fb-text uppercase tracking-wider">Сводный отчет о прибылях и убытках</h3>
        </div>

        <table class="w-full text-left text-sm">
          <thead class="border-b border-fb-line bg-fb-canvas text-xs uppercase tracking-wider font-semibold text-fb-secondary">
            <tr>
              <th class="px-6 py-3">Статья отчета</th>
              <th class="px-6 py-3 text-right">Сумма (UZS)</th>
              <th class="px-6 py-3 text-right">Доля (%)</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-fb-line">
            <!-- 1. Revenue Group -->
            <tr class="bg-emerald-50/40 font-bold text-emerald-950">
              <td class="px-6 py-3">1. ВАЛОВЫЕ ДОХОДЫ (Поступления)</td>
              <td class="px-6 py-3 text-right text-emerald-700">{{ pnl.summary.total_revenue.toLocaleString() }}</td>
              <td class="px-6 py-3 text-right">100.0%</td>
            </tr>
            <tr v-for="rev in pnl.revenue_by_method" :key="rev.method" class="text-xs">
              <td class="px-8 py-2.5 text-fb-secondary">Оплата: {{ rev.label }}</td>
              <td class="px-6 py-2.5 text-right font-medium">{{ rev.amount.toLocaleString() }}</td>
              <td class="px-6 py-2.5 text-right text-fb-secondary">{{ rev.percent }}%</td>
            </tr>

            <!-- 2. Expense Group -->
            <tr class="bg-rose-50/40 font-bold text-rose-950">
              <td class="px-6 py-3">2. ОПЕРАЦИОННЫЕ РАСХОДЫ</td>
              <td class="px-6 py-3 text-right text-rose-700">{{ pnl.summary.total_expenses.toLocaleString() }}</td>
              <td class="px-6 py-3 text-right">
                {{ pnl.summary.total_revenue > 0 ? ((pnl.summary.total_expenses / pnl.summary.total_revenue) * 100).toFixed(1) : '0' }}%
              </td>
            </tr>
            <tr v-for="exp in pnl.expense_by_category" :key="exp.id || 'uncat'" class="text-xs">
              <td class="px-8 py-2.5 text-fb-secondary">Расход: {{ exp.name }}</td>
              <td class="px-6 py-2.5 text-right font-medium">{{ exp.amount.toLocaleString() }}</td>
              <td class="px-6 py-2.5 text-right text-fb-secondary">{{ exp.percent }}%</td>
            </tr>

            <!-- 3. Withdrawals if any -->
            <tr v-if="pnl.summary.total_withdrawals > 0" class="text-xs text-amber-900 bg-amber-50/30">
              <td class="px-6 py-2.5 font-medium">3. Инкассация / Вывод средств (Withdrawals)</td>
              <td class="px-6 py-2.5 text-right font-medium">{{ pnl.summary.total_withdrawals.toLocaleString() }}</td>
              <td class="px-6 py-2.5 text-right text-fb-secondary">—</td>
            </tr>

            <!-- 4. NET PROFIT TOTAL -->
            <tr class="border-t-2 border-fb-line bg-fb-canvas font-black text-base">
              <td class="px-6 py-4">ЧИСТАЯ ПРИБЫЛЬ (ОПЕРАЦИОННЫЙ ИТОГ)</td>
              <td
                class="px-6 py-4 text-right"
                :class="pnl.summary.net_profit >= 0 ? 'text-emerald-700' : 'text-red-700'"
              >
                {{ pnl.summary.net_profit.toLocaleString() }} UZS
              </td>
              <td class="px-6 py-4 text-right text-sm font-bold text-fb-blue">
                {{ pnl.summary.profit_margin }}%
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
@media print {
  .no-print {
    display: none !important;
  }
}
</style>
