<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';

interface LeadRow {
  id: number;
  full_name: string;
  phone: string;
  stage: string;
  stage_label: string;
  source?: string;
  school?: string;
  course_id?: number | null;
  course_name?: string | null;
  is_active: boolean;
  created_at: string;
}

interface CourseOption {
  id: number;
  name: string;
}

interface LeadsReport {
  total: number;
  active: number;
  by_stage: Record<string, number>;
  rows: LeadRow[];
  page?: number;
  total_pages?: number;
}

const STAGES = [
  { value: '', label: 'Все статусы' },
  { value: 'trial_booked', label: 'Записан на пробный' },
  { value: 'attended', label: 'Был на уроке (Думает)' },
  { value: 'converted', label: 'Зачислен (Студент)' },
  { value: 'rejected', label: 'Отказ' },
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

const router = useRouter();

const report = ref<LeadsReport | null>(null);
const courses = ref<CourseOption[]>([]);
const loading = ref(true);
const exporting = ref(false);
const currentPage = ref(1);
const totalPages = ref(1);

const filters = reactive({ stage: '', course_id: '', source: '', date_from: '', date_to: '', q: '', active: '1' });

const stageCards = computed(() => {
  if (!report.value) return [];
  return STAGES.filter((s) => s.value).map((s) => ({
    key: s.value,
    label: s.label,
    count: report.value?.by_stage[s.value] ?? 0,
  }));
});

function applyFilters() {
  currentPage.value = 1;
  loadReport();
}

function resetFilters() {
  filters.stage = '';
  filters.course_id = '';
  filters.source = '';
  filters.date_from = '';
  filters.date_to = '';
  filters.q = '';
  filters.active = '1';
  currentPage.value = 1;
  loadReport();
}

function changePage(delta: number) {
  currentPage.value += delta;
  loadReport();
}

async function loadCourses() {
  try {
    const res = await client.get<ApiEnvelope<CourseOption[]>>('/courses');
    courses.value = res.data.data;
  } catch {
    // ignore
  }
}

async function loadReport() {
  loading.value = true;
  try {
    const params: Record<string, string> = { page: String(currentPage.value) };
    if (filters.stage) params.stage = filters.stage;
    if (filters.course_id) params.course_id = filters.course_id;
    if (filters.source) params.source = filters.source;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();
    if (filters.active) params.active = filters.active;
    const { data } = await client.get<ApiEnvelope<LeadsReport>>('/reports/leads', { params });
    report.value = data.data;
    totalPages.value = data.data.total_pages || 1;
  } finally {
    loading.value = false;
  }
}

async function exportCsv() {
  exporting.value = true;
  try {
    const params: Record<string, string> = { export: '1' };
    if (filters.stage) params.stage = filters.stage;
    if (filters.course_id) params.course_id = filters.course_id;
    if (filters.source) params.source = filters.source;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();
    if (filters.active) params.active = filters.active;

    const { data } = await client.get<ApiEnvelope<LeadsReport>>('/reports/leads', { params });
    const csvRows = [
      ['ID', 'ФИО (Full Name)', 'Телефон (Phone)', 'Курс (Course)', 'Источник (Source)', 'Школа (School)', 'Статус (Status)', 'Активен (Active)', 'Дата обращения (Created At)'],
    ];
    for (const row of data.data.rows) {
      csvRows.push([
        String(row.id),
        `"${row.full_name || ''}"`,
        `"${row.phone || ''}"`,
        `"${row.course_name || '—'}"`,
        `"${row.source || '—'}"`,
        `"${row.school || '—'}"`,
        `"${row.stage_label || ''}"`,
        row.is_active ? 'Да' : 'Нет',
        `"${row.created_at || ''}"`,
      ]);
    }
    const csvContent = 'data:text/csv;charset=utf-8,\uFEFF' + csvRows.map((e) => e.join(',')).join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `leads_report_${new Date().toISOString().slice(0, 10)}.csv`);
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

function openLeads() {
  router.push({ path: '/leads', query: { stage: 'all' } });
}

onMounted(async () => {
  await Promise.all([loadReport(), loadCourses()]);
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
        <h1 class="text-xl font-semibold text-fb-text">Отчет по лидам</h1>
        <p class="text-xs text-fb-secondary mt-0.5">Статистика обращений и распределение по этапам воронки</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="rounded-lg border border-fb-line bg-fb-card px-3.5 py-2 text-sm text-fb-secondary hover:border-fb-blue hover:text-fb-blue transition-colors disabled:opacity-50"
          :disabled="exporting"
          @click="exportCsv"
        >
          {{ exporting ? 'Экспорт…' : '📥 Экспорт CSV' }}
        </button>
        <button
          type="button"
          class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:bg-fb-blue-dark transition-colors"
          @click="openLeads"
        >
          Все лиды →
        </button>
      </div>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Статус</label>
        <select v-model="filters.stage" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none">
          <option v-for="s in STAGES" :key="s.value || 'all'" :value="s.value">{{ s.label }}</option>
        </select>
      </div>
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
    <template v-else-if="report">
      <!-- KPI Cards -->
      <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div class="rounded-xl border border-fb-line bg-fb-card p-6 shadow-sm">
          <div class="text-xs font-medium uppercase tracking-wider text-fb-secondary">Всего лидов</div>
          <div class="mt-2 text-3xl font-bold text-fb-text">{{ report.total }}</div>
          <div class="mt-1 text-xs text-fb-secondary">За весь выбранный период</div>
        </div>
        <div class="rounded-xl border border-fb-line bg-fb-card p-6 shadow-sm">
          <div class="text-xs font-medium uppercase tracking-wider text-fb-secondary">Активные лиды</div>
          <div class="mt-2 text-3xl font-bold text-fb-blue">{{ report.active }}</div>
          <div class="mt-1 text-xs text-fb-secondary">Находящиеся в работе</div>
        </div>
        <div class="rounded-xl border border-fb-line bg-fb-card p-6 shadow-sm">
          <div class="mb-3 text-xs font-medium uppercase tracking-wider text-fb-secondary">По статусам воронки</div>
          <div v-for="card in stageCards" :key="card.key" class="flex justify-between py-1 text-sm border-b border-fb-line/50 last:border-0">
            <span class="text-fb-secondary">{{ card.label }}</span>
            <span class="font-semibold text-fb-text">{{ card.count }}</span>
          </div>
        </div>
      </div>

      <!-- Table or Empty State -->
      <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card shadow-sm">
        <!-- Empty State -->
        <div v-if="!report.rows.length" class="flex flex-col items-center justify-center p-12 text-center">
          <div class="flex h-16 w-16 items-center justify-center rounded-full bg-fb-hover text-2xl mb-3 text-fb-icon">
            👥
          </div>
          <h3 class="text-base font-semibold text-fb-text">Лиды не найдены</h3>
          <p class="mt-1 text-sm text-fb-secondary max-w-sm">
            По указанным фильтрам обращений не обнаружено. Попробуйте сбросить параметры поиска.
          </p>
          <button
            type="button"
            class="mt-4 rounded-lg border border-fb-line bg-white px-4 py-2 text-xs font-medium text-fb-blue hover:bg-fb-canvas transition-colors"
            @click="resetFilters"
          >
            Сбросить фильтры
          </button>
        </div>

        <!-- Table -->
        <template v-else>
          <table class="w-full text-sm">
            <thead class="border-b border-fb-line bg-fb-canvas text-xs uppercase tracking-wider font-semibold text-fb-secondary">
              <tr>
                <th class="px-5 py-3.5 text-left">ФИО лида</th>
                <th class="px-5 py-3.5 text-left">Телефон</th>
                <th class="px-5 py-3.5 text-left">Курс</th>
                <th class="px-5 py-3.5 text-left">Источник</th>
                <th class="px-5 py-3.5 text-left">Статус воронки</th>
                <th class="px-5 py-3.5 text-left">Дата обращения</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-fb-line">
              <tr v-for="row in report.rows" :key="row.id" class="hover:bg-fb-hover/40 transition-colors">
                <td class="px-5 py-3.5 font-medium text-fb-text">{{ row.full_name }}</td>
                <td class="px-5 py-3.5 text-fb-secondary">{{ row.phone }}</td>
                <td class="px-5 py-3.5 text-fb-secondary">{{ row.course_name || '—' }}</td>
                <td class="px-5 py-3.5">
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
              Страница {{ currentPage }} из {{ totalPages }} (всего {{ report.total }} лидов)
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
