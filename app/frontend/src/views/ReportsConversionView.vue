<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface ConversionRow {
  id: number;
  full_name: string;
  phone: string;
  stage: string;
  stage_label: string;
  source?: string;
  school?: string;
  course_id?: number | null;
  course_name?: string | null;
  created_at: string;
  trial_booked?: boolean;
  attended?: boolean;
  converted?: boolean;
  rejected?: boolean;
  [key: string]: unknown;
}

interface CourseOption {
  id: number;
  name: string;
}

interface ConversionData {
  pipeline: Record<string, number>;
  rows: ConversionRow[];
  total?: number;
  page?: number;
  total_pages?: number;
}

const STAGES = [
  { key: 'trial_booked', label: 'Записан на пробный' },
  { key: 'attended', label: 'Был на уроке (Думает)' },
  { key: 'converted', label: 'Зачислен (Студент)' },
  { key: 'rejected', label: 'Отказ' },
] as const;

const POPULAR_SOURCES = [
  'Instagram',
  'Telegram',
  'Звонок',
  'Рекомендация',
  'Наружка',
  'Сайт',
  'Другое',
] as const;

const data = ref<ConversionData | null>(null);
const courses = ref<CourseOption[]>([]);
const loading = ref(true);
const exporting = ref(false);
const currentPage = ref(1);
const totalPages = ref(1);
const totalCount = ref(0);

const filters = reactive({ course_id: '', source: '', date_from: '', date_to: '', q: '' });

const pipelineCards = computed(() => {
  if (!data.value) return [];
  const p = data.value.pipeline;
  return STAGES.map((s) => ({ key: s.key, label: s.label, count: p[s.key] ?? 0 }));
});

const funnelStats = computed(() => {
  if (!data.value) return { total: 0, booked: 0, attended: 0, converted: 0, rejected: 0, attendedRate: 0, convertedRate: 0, rejectedRate: 0 };
  const p = data.value.pipeline;
  const booked = p['trial_booked'] ?? 0;
  const attended = p['attended'] ?? 0;
  const converted = p['converted'] ?? 0;
  const rejected = p['rejected'] ?? 0;
  const total = booked + attended + converted + rejected;
  const attendedRate = (booked + attended + converted) > 0 ? Math.round(((attended + converted) / (booked + attended + converted)) * 100) : 0;
  const convertedRate = total > 0 ? Math.round((converted / total) * 100) : 0;
  const rejectedRate = total > 0 ? Math.round((rejected / total) * 100) : 0;
  return { total, booked, attended, converted, rejected, attendedRate, convertedRate, rejectedRate };
});

function applyFilters() {
  currentPage.value = 1;
  loadData();
}

function resetFilters() {
  filters.course_id = '';
  filters.source = '';
  filters.date_from = '';
  filters.date_to = '';
  filters.q = '';
  currentPage.value = 1;
  loadData();
}

function changePage(delta: number) {
  currentPage.value += delta;
  loadData();
}

async function loadCourses() {
  try {
    const res = await client.get<ApiEnvelope<CourseOption[]>>('/courses');
    courses.value = res.data.data;
  } catch {
    // ignore
  }
}

async function loadData() {
  loading.value = true;
  try {
    const params: Record<string, string> = { page: String(currentPage.value) };
    if (filters.course_id) params.course_id = filters.course_id;
    if (filters.source) params.source = filters.source;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();
    const res = await client.get<ApiEnvelope<ConversionData>>('/reports/conversion', { params });
    data.value = res.data.data;
    totalPages.value = res.data.data.total_pages || 1;
    totalCount.value = res.data.data.total || res.data.data.rows?.length || 0;
  } finally {
    loading.value = false;
  }
}

async function exportCsv() {
  exporting.value = true;
  try {
    const params: Record<string, string> = { export: '1' };
    if (filters.course_id) params.course_id = filters.course_id;
    if (filters.source) params.source = filters.source;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();

    const res = await client.get<ApiEnvelope<ConversionData>>('/reports/conversion', { params });
    const csvRows = [
      ['ID', 'ФИО (Full Name)', 'Телефон (Phone)', 'Курс (Course)', 'Источник (Source)', 'Школа (School)', 'Текущий этап (Stage)', 'Записан на пробный', 'Был на уроке', 'Зачислен (Студент)', 'Отказ', 'Дата создания'],
    ];
    for (const row of res.data.data.rows) {
      csvRows.push([
        String(row.id),
        `"${row.full_name || ''}"`,
        `"${row.phone || ''}"`,
        `"${row.course_name || '—'}"`,
        `"${row.source || '—'}"`,
        `"${row.school || '—'}"`,
        `"${row.stage_label || ''}"`,
        row.trial_booked ? 'Да' : 'Нет',
        row.attended ? 'Да' : 'Нет',
        row.converted ? 'Да' : 'Нет',
        row.rejected ? 'Да' : 'Нет',
        `"${row.created_at || ''}"`,
      ]);
    }
    const csvContent = 'data:text/csv;charset=utf-8,\uFEFF' + csvRows.map((e) => e.join(',')).join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `conversion_report_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } catch (err) {
    console.error(err);
    alert('Не удалось экспортировать отчет в CSV');
  } finally {
    exporting.value = false;
  }
}

onMounted(async () => {
  await Promise.all([loadData(), loadCourses()]);
});

let searchDebounce: ReturnType<typeof setTimeout> | null = null;
watch(
  () => filters.q,
  (newQ, oldQ) => {
    if (newQ === oldQ) return;
    if (searchDebounce) clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      applyFilters();
    }, 400);
  },
);
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold text-fb-text">Отчет по конверсии</h1>
        <p class="text-xs text-fb-secondary mt-0.5">Воронка прохождения пробных занятий и конверсии лидов</p>
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
        <select v-model="filters.course_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none">
          <option value="">Все курсы</option>
          <option v-for="c in courses" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Источник</label>
        <select v-model="filters.source" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none">
          <option value="">Все источники</option>
          <option v-for="src in POPULAR_SOURCES" :key="src" :value="src">{{ src }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">С даты</label>
        <input v-model="filters.date_from" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">По дату</label>
        <input v-model="filters.date_to" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
      </div>
      <div class="min-w-[180px] flex-1">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Поиск</label>
        <input
          v-model="filters.q"
          type="search"
          placeholder="Поиск по имени, телефону, источнику…"
          class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
          @keydown.enter="applyFilters"
        />
      </div>
      <button
        type="button"
        class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:bg-fb-blue-dark transition-colors"
        @click="applyFilters"
      >
        Применить
      </button>
    </div>

    <div v-if="loading" class="p-12 text-center text-fb-secondary">Загрузка данных…</div>
    <template v-else>
      <!-- Pipeline stages cards -->
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div
          v-for="card in pipelineCards"
          :key="card.key"
          class="rounded-xl border border-fb-line bg-fb-card p-5 text-center shadow-sm"
        >
          <div class="text-3xl font-bold text-fb-blue">{{ card.count }}</div>
          <div class="mt-1 text-sm font-medium text-fb-text">{{ card.label }}</div>
        </div>
      </div>

      <!-- Visual Funnel Diagram -->
      <div v-if="funnelStats.total > 0" class="rounded-xl border border-fb-line bg-fb-card p-5 shadow-sm">
        <div class="flex flex-wrap items-center justify-between gap-2 text-xs font-medium text-fb-secondary mb-3">
          <span>Воронка движения лидов</span>
          <div class="flex items-center gap-4">
            <span>В урок: <strong class="text-emerald-700">{{ funnelStats.attendedRate }}%</strong></span>
            <span>В студенты: <strong class="text-indigo-600">{{ funnelStats.convertedRate }}%</strong></span>
          </div>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
          <!-- Step 1 -->
          <div class="relative flex flex-col justify-between rounded-lg border border-blue-200 bg-blue-50/60 p-3.5">
            <div class="flex items-center justify-between">
              <span class="text-xs font-semibold uppercase tracking-wider text-blue-800">1. Записан</span>
              <span class="text-xs font-medium text-blue-600">100%</span>
            </div>
            <div class="mt-2 text-2xl font-bold text-blue-900">{{ funnelStats.booked }}</div>
            <div class="mt-2 h-1.5 w-full rounded-full bg-blue-200">
              <div class="h-1.5 rounded-full bg-blue-600" style="width: 100%" />
            </div>
          </div>

          <!-- Step 2 -->
          <div class="relative flex flex-col justify-between rounded-lg border border-emerald-200 bg-emerald-50/60 p-3.5">
            <div class="flex items-center justify-between">
              <span class="text-xs font-semibold uppercase tracking-wider text-emerald-800">2. Был на уроке</span>
              <span class="text-xs font-bold text-emerald-700">{{ funnelStats.attendedRate }}%</span>
            </div>
            <div class="mt-2 text-2xl font-bold text-emerald-900">{{ funnelStats.attended }}</div>
            <div class="mt-2 h-1.5 w-full rounded-full bg-emerald-200">
              <div class="h-1.5 rounded-full bg-emerald-600" :style="{ width: `${funnelStats.attendedRate}%` }" />
            </div>
          </div>

          <!-- Step 3 -->
          <div class="relative flex flex-col justify-between rounded-lg border border-indigo-200 bg-indigo-50/60 p-3.5">
            <div class="flex items-center justify-between">
              <span class="text-xs font-semibold uppercase tracking-wider text-indigo-800">3. Зачислен (Студент)</span>
              <span class="text-xs font-bold text-indigo-700">{{ funnelStats.convertedRate }}%</span>
            </div>
            <div class="mt-2 text-2xl font-bold text-indigo-900">{{ funnelStats.converted }}</div>
            <div class="mt-2 h-1.5 w-full rounded-full bg-indigo-200">
              <div class="h-1.5 rounded-full bg-indigo-600" :style="{ width: `${funnelStats.convertedRate}%` }" />
            </div>
          </div>

          <!-- Step 4 -->
          <div class="relative flex flex-col justify-between rounded-lg border border-gray-200 bg-gray-50/60 p-3.5">
            <div class="flex items-center justify-between">
              <span class="text-xs font-semibold uppercase tracking-wider text-gray-700">4. Отказ</span>
              <span class="text-xs font-medium text-gray-500">{{ funnelStats.rejectedRate }}%</span>
            </div>
            <div class="mt-2 text-2xl font-bold text-gray-800">{{ funnelStats.rejected }}</div>
            <div class="mt-2 h-1.5 w-full rounded-full bg-gray-200">
              <div class="h-1.5 rounded-full bg-gray-500" :style="{ width: `${funnelStats.rejectedRate}%` }" />
            </div>
          </div>
        </div>
      </div>

      <!-- Table or Empty State -->
      <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card shadow-sm">
        <div v-if="!data?.rows.length" class="flex flex-col items-center justify-center p-12 text-center">
          <div class="flex h-16 w-16 items-center justify-center rounded-full bg-fb-hover text-2xl mb-3 text-fb-icon">
            🔄
          </div>
          <h3 class="text-base font-semibold text-fb-text">Лиды в воронке не найдены</h3>
          <p class="mt-1 text-sm text-fb-secondary max-w-sm">
            За указанный период нет активных лидов на этапах воронки. Попробуйте изменить фильтры дат.
          </p>
          <button
            type="button"
            class="mt-4 rounded-lg border border-fb-line bg-white px-4 py-2 text-xs font-medium text-fb-blue hover:bg-fb-canvas transition-colors"
            @click="resetFilters"
          >
            Сбросить фильтры
          </button>
        </div>

        <template v-else>
          <table class="w-full text-sm">
            <thead class="border-b border-fb-line bg-fb-canvas text-xs uppercase tracking-wider font-semibold text-fb-secondary">
              <tr>
                <th class="px-5 py-3.5 text-left">ФИО</th>
                <th class="px-5 py-3.5 text-left">Телефон</th>
                <th class="px-4 py-3.5 text-left">Курс</th>
                <th class="px-4 py-3.5 text-left">Источник</th>
                <th class="px-5 py-3.5 text-left">Текущий статус</th>
                <th v-for="stage in STAGES" :key="stage.key" class="px-3 py-3.5 text-center">
                  {{ stage.label }}
                </th>
                <th class="px-5 py-3.5 text-left">Дата</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-fb-line">
              <tr v-for="row in data.rows" :key="row.id" class="hover:bg-fb-hover/40 transition-colors">
                <td class="px-5 py-3.5 font-medium text-fb-text">{{ row.full_name }}</td>
                <td class="px-5 py-3.5 text-fb-secondary">{{ row.phone }}</td>
                <td class="px-4 py-3.5 text-fb-secondary text-xs">{{ row.course_name || '—' }}</td>
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
                <td v-for="stage in STAGES" :key="stage.key" class="px-3 py-3.5 text-center">
                  <span v-if="row[stage.key]" class="font-bold text-emerald-600">✓</span>
                  <span v-else class="text-fb-icon">—</span>
                </td>
                <td class="px-5 py-3.5 text-fb-secondary">{{ row.created_at }}</td>
              </tr>
            </tbody>
          </table>

          <!-- Pagination Bar -->
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
              Страница {{ currentPage }} из {{ totalPages }} (всего {{ totalCount }} лидов)
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
