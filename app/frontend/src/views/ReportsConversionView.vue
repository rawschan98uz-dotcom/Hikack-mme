<script setup lang="ts">
/**
 * «Лиды и конверсия» — one page instead of the two old reports (conversion + leads), reports audit 2026-09-29.
 * The funnel shows what happened to every lead: 10 booked → 6 came (60%) → 3 enrolled (30%),
 * refusals split into «before the lesson» and «after it».
 */
import { todayIso } from '../utils/dates';
import { computed, onMounted, reactive, ref, watch } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { downloadCsv } from '../utils/csvExport';

interface ConversionRow {
  id: number;
  full_name: string;
  phone: string;
  stage: string;
  stage_label: string;
  source?: string;
  school?: string;
  course_name?: string | null;
  branch_name?: string | null;
  created_at: string;
  attended?: boolean;
  is_active?: boolean;
}

interface Option {
  id: number;
  name: string;
}

interface Funnel {
  booked: number;
  came: number;
  converted: number;
  thinking: number;
  waiting: number;
  rejected: number;
  rejected_before: number;
  rejected_after: number;
}

interface SourceRow {
  source: string;
  total: number;
  came: number;
  converted: number;
  rate: number;
}

interface ConversionData {
  funnel: Funnel;
  by_source: SourceRow[];
  sources: string[];
  rows: ConversionRow[];
  total: number;
  active: number;
  page?: number;
  total_pages?: number;
}

const STAGES = [
  { value: 'trial_booked', label: 'Записан на пробный' },
  { value: 'attended', label: 'Был на уроке (Думает)' },
  { value: 'converted', label: 'Зачислен (Студент)' },
  { value: 'rejected', label: 'Отказ' },
] as const;

const data = ref<ConversionData | null>(null);
const courses = ref<Option[]>([]);
const branches = ref<Option[]>([]);
const loading = ref(true);
const exporting = ref(false);
const currentPage = ref(1);
const totalPages = ref(1);

const filters = reactive({
  course_id: '',
  branch_id: '',
  source: '',
  stage: '',
  date_from: '',
  date_to: '',
  q: '',
  is_active: '',
});

function pct(part: number, whole: number) {
  return whole > 0 ? Math.round((part / whole) * 100) : 0;
}

const funnel = computed<Funnel>(() => data.value?.funnel ?? {
  booked: 0, came: 0, converted: 0, thinking: 0, waiting: 0, rejected: 0, rejected_before: 0, rejected_after: 0,
});

const funnelSteps = computed(() => {
  const f = funnel.value;
  return [
    { key: 'booked', title: '1. Записались на пробный', count: f.booked, rate: f.booked ? 100 : 0, hint: 'все лиды за период', color: 'blue' },
    { key: 'came', title: '2. Пришли на пробный', count: f.came, rate: pct(f.came, f.booked), hint: 'от записавшихся', color: 'emerald' },
    {
      key: 'converted',
      title: '3. Стали студентами',
      count: f.converted,
      rate: pct(f.converted, f.booked),
      hint: `от записавшихся · ${pct(f.converted, f.came)}% от пришедших`,
      color: 'indigo',
    },
  ];
});

const STEP_COLORS: Record<string, { box: string; title: string; num: string; bar: string; track: string }> = {
  blue: { box: 'border-blue-200 bg-blue-50/60', title: 'text-blue-800', num: 'text-blue-900', bar: 'bg-blue-600', track: 'bg-blue-200' },
  emerald: { box: 'border-emerald-200 bg-emerald-50/60', title: 'text-emerald-800', num: 'text-emerald-900', bar: 'bg-emerald-600', track: 'bg-emerald-200' },
  indigo: { box: 'border-indigo-200 bg-indigo-50/60', title: 'text-indigo-800', num: 'text-indigo-900', bar: 'bg-indigo-600', track: 'bg-indigo-200' },
};

function queryParams(extra: Record<string, string>) {
  const params: Record<string, string> = { ...extra };
  for (const key of ['course_id', 'branch_id', 'source', 'stage', 'date_from', 'date_to', 'is_active'] as const) {
    if (filters[key]) params[key] = filters[key];
  }
  if (filters.q.trim()) params.q = filters.q.trim();
  return params;
}

function applyFilters() {
  currentPage.value = 1;
  loadData();
}

function resetFilters() {
  Object.assign(filters, { course_id: '', branch_id: '', source: '', stage: '', date_from: '', date_to: '', q: '', is_active: '' });
  applyFilters();
}

function pickSource(source: string) {
  filters.source = filters.source === source ? '' : source;
  applyFilters();
}

function pickStage(stage: string) {
  filters.stage = filters.stage === stage ? '' : stage;
  applyFilters();
}

function changePage(delta: number) {
  currentPage.value += delta;
  loadData();
}

async function loadOptions() {
  const [courseRes, branchRes] = await Promise.allSettled([
    client.get<ApiEnvelope<Option[]>>('/courses'),
    client.get<ApiEnvelope<Option[]>>('/branch'),
  ]);
  if (courseRes.status === 'fulfilled') courses.value = courseRes.value.data.data;
  if (branchRes.status === 'fulfilled') branches.value = branchRes.value.data.data;
}

async function loadData() {
  loading.value = true;
  try {
    const res = await client.get<ApiEnvelope<ConversionData>>('/reports/conversion', {
      params: queryParams({ page: String(currentPage.value) }),
    });
    data.value = res.data.data;
    totalPages.value = res.data.data.total_pages || 1;
  } finally {
    loading.value = false;
  }
}

async function exportCsv() {
  exporting.value = true;
  try {
    const res = await client.get<ApiEnvelope<ConversionData>>('/reports/conversion', { params: queryParams({ export: '1' }) });
    downloadCsv(
      `leads_conversion_${todayIso()}.csv`,
      ['ID', 'ФИО', 'Телефон', 'Курс', 'Филиал', 'Источник', 'Школа', 'Этап', 'Пришёл на пробный', 'Статус', 'Дата обращения'],
      res.data.data.rows.map((row) => [
        row.id,
        row.full_name,
        row.phone,
        row.course_name || '—',
        row.branch_name || '—',
        row.source || '—',
        row.school || '—',
        row.stage_label,
        row.attended ? 'Да' : 'Нет',
        row.is_active === false ? 'В архиве' : 'Активный',
        row.created_at,
      ]),
    );
  } catch (err) {
    console.error(err);
    alert('Не удалось экспортировать отчет в CSV');
  } finally {
    exporting.value = false;
  }
}

onMounted(async () => {
  await Promise.all([loadData(), loadOptions()]);
});

let searchDebounce: ReturnType<typeof setTimeout> | null = null;
watch(
  () => filters.q,
  (newQ, oldQ) => {
    if (newQ === oldQ) return;
    if (searchDebounce) clearTimeout(searchDebounce);
    searchDebounce = setTimeout(applyFilters, 400);
  },
);
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold text-fb-text">Лиды и конверсия</h1>
        <p class="text-xs text-fb-secondary mt-0.5">Сколько записалось на пробный, сколько пришло и сколько стало студентами</p>
      </div>
      <button
        type="button"
        class="rounded-lg border border-fb-line bg-fb-card px-3.5 py-2 text-sm text-fb-secondary hover:border-fb-blue hover:text-fb-blue transition-colors disabled:opacity-50"
        :disabled="exporting"
        @click="exportCsv"
      >
        {{ exporting ? 'Экспорт…' : '📥 Экспорт CSV' }}
      </button>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Курс</label>
        <select v-model="filters.course_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" @change="applyFilters">
          <option value="">Все курсы</option>
          <option v-for="c in courses" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
        </select>
      </div>
      <div v-if="branches.length > 1">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Филиал</label>
        <select v-model="filters.branch_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" @change="applyFilters">
          <option value="">Все филиалы</option>
          <option v-for="b in branches" :key="b.id" :value="String(b.id)">{{ b.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Источник</label>
        <select v-model="filters.source" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" @change="applyFilters">
          <option value="">Все источники</option>
          <option v-for="src in data?.sources ?? []" :key="src" :value="src">{{ src }}</option>
          <option value="—">Без источника</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Этап</label>
        <select v-model="filters.stage" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" @change="applyFilters">
          <option value="">Все этапы</option>
          <option v-for="s in STAGES" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Лиды</label>
        <select v-model="filters.is_active" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" @change="applyFilters">
          <option value="">Все (включая архив)</option>
          <option value="true">Только активные</option>
          <option value="false">Только архив</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">С даты</label>
        <input v-model="filters.date_from" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" @change="applyFilters" />
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">По дату</label>
        <input v-model="filters.date_to" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" @change="applyFilters" />
      </div>
      <div class="min-w-[180px] flex-1">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Поиск</label>
        <input
          v-model="filters.q"
          type="search"
          placeholder="Имя, телефон, источник, школа…"
          class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
          @keydown.enter="applyFilters"
        />
      </div>
      <button type="button" class="rounded-lg border border-fb-line px-4 py-2 text-sm text-fb-secondary hover:text-fb-blue" @click="resetFilters">
        Сбросить
      </button>
    </div>

    <div v-if="loading && !data" class="p-12 text-center text-fb-secondary">Загрузка данных…</div>
    <template v-else-if="data">
      <!-- Funnel: what happened to every lead of the period -->
      <div class="rounded-xl border border-fb-line bg-fb-card p-5 shadow-sm">
        <div class="mb-3 text-xs font-medium text-fb-secondary">Воронка за выбранный период</div>
        <div class="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div
            v-for="step in funnelSteps"
            :key="step.key"
            class="flex flex-col justify-between rounded-lg border p-3.5"
            :class="STEP_COLORS[step.color].box"
          >
            <div class="flex items-center justify-between">
              <span class="text-xs font-semibold uppercase tracking-wider" :class="STEP_COLORS[step.color].title">{{ step.title }}</span>
              <span class="text-sm font-bold" :class="STEP_COLORS[step.color].title">{{ step.rate }}%</span>
            </div>
            <div class="mt-2 text-2xl font-bold" :class="STEP_COLORS[step.color].num">{{ step.count }}</div>
            <div class="mt-1 text-[11px] text-fb-secondary">{{ step.hint }}</div>
            <div class="mt-2 h-1.5 w-full rounded-full" :class="STEP_COLORS[step.color].track">
              <div class="h-1.5 rounded-full" :class="STEP_COLORS[step.color].bar" :style="{ width: `${step.rate}%` }" />
            </div>
          </div>
        </div>
        <div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3 text-sm">
          <button type="button" class="rounded-lg border border-fb-line px-3 py-2 text-left hover:border-fb-blue" :class="filters.stage === 'trial_booked' ? 'border-fb-blue bg-fb-hover' : ''" @click="pickStage('trial_booked')">
            <span class="text-fb-secondary">Ещё не были на пробном:</span>
            <strong class="ml-1 text-fb-text">{{ funnel.waiting }}</strong>
          </button>
          <button type="button" class="rounded-lg border border-fb-line px-3 py-2 text-left hover:border-fb-blue" :class="filters.stage === 'attended' ? 'border-fb-blue bg-fb-hover' : ''" @click="pickStage('attended')">
            <span class="text-fb-secondary">Были, думают:</span>
            <strong class="ml-1 text-fb-text">{{ funnel.thinking }}</strong>
          </button>
          <button type="button" class="rounded-lg border border-fb-line px-3 py-2 text-left hover:border-fb-blue" :class="filters.stage === 'rejected' ? 'border-fb-blue bg-fb-hover' : ''" @click="pickStage('rejected')">
            <span class="text-fb-secondary">Отказ:</span>
            <strong class="ml-1 text-fb-text">{{ funnel.rejected }}</strong>
            <span class="ml-1 text-xs text-fb-secondary">(до урока {{ funnel.rejected_before }}, после урока {{ funnel.rejected_after }})</span>
          </button>
        </div>
      </div>

      <!-- Which advertising works -->
      <div v-if="data.by_source.length" class="overflow-hidden rounded-xl border border-fb-line bg-fb-card shadow-sm">
        <div class="border-b border-fb-line px-5 py-3 text-sm font-semibold text-fb-text">По источникам — какая реклама приводит студентов</div>
        <table class="w-full text-sm">
          <thead class="border-b border-fb-line bg-fb-canvas text-xs uppercase tracking-wider font-semibold text-fb-secondary">
            <tr>
              <th class="px-5 py-2.5 text-left">Источник</th>
              <th class="px-4 py-2.5 text-right">Лидов</th>
              <th class="px-4 py-2.5 text-right">Пришли на пробный</th>
              <th class="px-4 py-2.5 text-right">Стали студентами</th>
              <th class="px-5 py-2.5 text-right">Конверсия</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-fb-line">
            <tr
              v-for="src in data.by_source"
              :key="src.source"
              class="cursor-pointer hover:bg-fb-hover/40"
              :class="filters.source === src.source ? 'bg-fb-hover' : ''"
              title="Нажмите, чтобы показать лидов этого источника"
              @click="pickSource(src.source)"
            >
              <td class="px-5 py-2.5 font-medium text-fb-text">{{ src.source === '—' ? 'Без источника' : src.source }}</td>
              <td class="px-4 py-2.5 text-right">{{ src.total }}</td>
              <td class="px-4 py-2.5 text-right">{{ src.came }}</td>
              <td class="px-4 py-2.5 text-right">{{ src.converted }}</td>
              <td class="px-5 py-2.5 text-right font-semibold text-indigo-700">{{ src.rate }}%</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Leads -->
      <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card shadow-sm">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-fb-line px-5 py-3 text-sm">
          <span class="font-semibold text-fb-text">Лиды</span>
          <span class="text-fb-secondary">Всего: <strong class="text-fb-text">{{ data.total }}</strong> · активных: <strong class="text-fb-text">{{ data.active }}</strong> · в архиве: <strong class="text-fb-text">{{ data.total - data.active }}</strong></span>
        </div>
        <div v-if="!data.rows.length" class="flex flex-col items-center justify-center p-12 text-center">
          <h3 class="text-base font-semibold text-fb-text">Лиды не найдены</h3>
          <p class="mt-1 text-sm text-fb-secondary max-w-sm">По выбранным фильтрам лидов нет. Попробуйте изменить период или сбросить фильтры.</p>
        </div>

        <template v-else>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead class="border-b border-fb-line bg-fb-canvas text-xs uppercase tracking-wider font-semibold text-fb-secondary">
                <tr>
                  <th class="px-5 py-3.5 text-left">ФИО</th>
                  <th class="px-5 py-3.5 text-left">Телефон</th>
                  <th class="px-4 py-3.5 text-left">Курс</th>
                  <th v-if="branches.length > 1" class="px-4 py-3.5 text-left">Филиал</th>
                  <th class="px-4 py-3.5 text-left">Источник</th>
                  <th class="px-5 py-3.5 text-left">Этап</th>
                  <th class="px-3 py-3.5 text-center">Был на пробном</th>
                  <th class="px-5 py-3.5 text-left">Дата</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-fb-line">
                <tr v-for="row in data.rows" :key="row.id" class="hover:bg-fb-hover/40 transition-colors">
                  <td class="px-5 py-3.5 font-medium text-fb-text">
                    <div class="flex items-center gap-2">
                      <span>{{ row.full_name }}</span>
                      <span
                        v-if="row.is_active === false"
                        class="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 border border-amber-200"
                        title="Лид находится в архиве"
                      >
                        Архив
                      </span>
                    </div>
                  </td>
                  <td class="px-5 py-3.5 text-fb-secondary">{{ row.phone }}</td>
                  <td class="px-4 py-3.5 text-fb-secondary text-xs">{{ row.course_name || '—' }}</td>
                  <td v-if="branches.length > 1" class="px-4 py-3.5 text-fb-secondary text-xs">{{ row.branch_name || '—' }}</td>
                  <td class="px-4 py-3.5">
                    <span v-if="row.source" class="rounded bg-sky-50 px-2 py-0.5 text-xs text-sky-700 font-medium border border-sky-200">
                      {{ row.source }}
                    </span>
                    <span v-else class="text-fb-secondary text-xs">—</span>
                  </td>
                  <td class="px-5 py-3.5">
                    <span class="rounded-full bg-fb-canvas border border-fb-line px-2.5 py-0.5 text-xs font-medium text-fb-text">
                      {{ row.stage_label }}
                    </span>
                  </td>
                  <td class="px-3 py-3.5 text-center">
                    <span v-if="row.attended" class="font-bold text-emerald-600">✓</span>
                    <span v-else class="text-fb-icon">—</span>
                  </td>
                  <td class="px-5 py-3.5 text-fb-secondary">{{ row.created_at.split('-').reverse().join('.') }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="flex items-center justify-between border-t border-fb-line px-5 py-3.5">
            <button
              type="button"
              class="rounded-lg border border-fb-line px-3.5 py-1.5 text-xs font-medium text-fb-secondary hover:text-fb-blue hover:border-fb-blue disabled:opacity-40 transition-colors"
              :disabled="currentPage <= 1"
              @click="changePage(-1)"
            >
              ← Назад
            </button>
            <span class="text-xs text-fb-secondary font-medium">
              Страница {{ currentPage }} из {{ totalPages }} (всего {{ data.total }} лидов)
            </span>
            <button
              type="button"
              class="rounded-lg border border-fb-line px-3.5 py-1.5 text-xs font-medium text-fb-secondary hover:text-fb-blue hover:border-fb-blue disabled:opacity-40 transition-colors"
              :disabled="currentPage >= totalPages"
              @click="changePage(1)"
            >
              Вперед →
            </button>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>
