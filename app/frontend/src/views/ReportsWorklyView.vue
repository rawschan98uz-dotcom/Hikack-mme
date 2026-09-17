<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface StaffOption {
  id: number;
  name: string;
  job_title: string;
}

interface WorklyRow {
  id: number;
  staff_id: number;
  staff: string;
  job_title: string;
  work_date: string;
  clock_in: string;
  clock_out: string;
  status: string;
  status_label: string;
  note: string;
}

interface Summary {
  at_work: number;
  late_in: number;
  absent: number;
  total: number;
}

interface Payload {
  summary: Summary;
  rows: WorklyRow[];
  total?: number;
  page?: number;
  total_pages?: number;
}

const STATUS_OPTIONS = [
  { value: '', label: 'Все записи' },
  { value: 'at_work', label: 'На работе' },
  { value: 'late_in', label: 'Опоздал' },
  { value: 'absent', label: 'Отсутствовал' },
] as const;

const FORM_STATUSES = STATUS_OPTIONS.filter((s) => s.value !== '');

const rows = ref<WorklyRow[]>([]);
const summary = ref<Summary>({ at_work: 0, late_in: 0, absent: 0, total: 0 });
const staffList = ref<StaffOption[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const exporting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingRecord = ref<WorklyRow | null>(null);
const detailRecord = ref<WorklyRow | null>(null);
const currentPage = ref(1);
const totalPages = ref(1);
const totalCount = ref(0);

const filters = reactive({
  status: '',
  staff_id: '',
  date_from: '',
  date_to: '',
  q: '',
});

const form = reactive({
  staff_id: '' as number | '',
  work_date: new Date().toISOString().slice(0, 10),
  clock_in: '09:00',
  clock_out: '18:00',
  status: 'at_work' as (typeof FORM_STATUSES)[number]['value'],
  note: '',
});

const isReadOnly = computed(() => Boolean(detailRecord.value && !editingRecord.value));
const panelTitle = computed(() => {
  if (editingRecord.value) return 'Редактировать запись';
  if (detailRecord.value) return 'Детали табеля';
  return 'Добавить запись в табель';
});

function statusClass(status: string) {
  if (status === 'at_work') return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
  if (status === 'late_in') return 'bg-amber-50 text-amber-700 border border-amber-200';
  return 'bg-red-50 text-fb-danger border border-red-200';
}

function resetForm() {
  form.staff_id = staffList.value[0]?.id ?? '';
  form.work_date = new Date().toISOString().slice(0, 10);
  form.clock_in = '09:00';
  form.clock_out = '18:00';
  form.status = 'at_work';
  form.note = '';
  formError.value = '';
  editingRecord.value = null;
  detailRecord.value = null;
}

function fillForm(record: WorklyRow) {
  form.staff_id = record.staff_id;
  form.work_date = record.work_date;
  form.clock_in = record.clock_in || '09:00';
  form.clock_out = record.clock_out || '';
  form.status = record.status as (typeof FORM_STATUSES)[number]['value'];
  form.note = record.note;
}

async function loadStaff() {
  const { data } = await client.get<ApiEnvelope<StaffOption[]>>('/user', { params: { user_type: 'staff' } });
  staffList.value = data.data;
}

function applyFilters() {
  currentPage.value = 1;
  loadRows();
}

function resetFilters() {
  filters.status = '';
  filters.staff_id = '';
  filters.date_from = '';
  filters.date_to = '';
  filters.q = '';
  currentPage.value = 1;
  loadRows();
}

function changePage(delta: number) {
  currentPage.value += delta;
  loadRows();
}

async function loadRows() {
  loading.value = true;
  try {
    const params: Record<string, string> = { page: String(currentPage.value) };
    if (filters.status) params.status = filters.status;
    if (filters.staff_id) params.staff_id = filters.staff_id;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();
    const { data } = await client.get<ApiEnvelope<Payload>>('/reports/workly', { params });
    summary.value = data.data.summary;
    rows.value = data.data.rows;
    totalPages.value = data.data.total_pages || 1;
    totalCount.value = data.data.total ?? summary.value.total;
  } finally {
    loading.value = false;
  }
}

async function exportCsv() {
  exporting.value = true;
  try {
    const params: Record<string, string> = { export: '1' };
    if (filters.status) params.status = filters.status;
    if (filters.staff_id) params.staff_id = filters.staff_id;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();

    const { data } = await client.get<ApiEnvelope<Payload>>('/reports/workly', { params });
    const csvRows = [
      ['ID', 'Сотрудник (Staff)', 'Должность (Job Title)', 'Дата (Date)', 'Время прихода (Clock In)', 'Время ухода (Clock Out)', 'Статус (Status)', 'Заметка (Note)'],
    ];
    for (const row of data.data.rows) {
      csvRows.push([
        String(row.id),
        `"${row.staff}"`,
        `"${row.job_title}"`,
        `"${row.work_date}"`,
        `"${row.clock_in || ''}"`,
        `"${row.clock_out || ''}"`,
        `"${row.status_label}"`,
        `"${row.note || ''}"`,
      ]);
    }
    const csvContent = 'data:text/csv;charset=utf-8,﻿' + csvRows.map((e) => e.join(',')).join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `workly_report_${new Date().toISOString().slice(0, 10)}.csv`);
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

function openCreate() {
  resetForm();
  showPanel.value = true;
}

async function openDetail(id: number) {
  resetForm();
  showPanel.value = true;
  panelLoading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<WorklyRow>>(`/reports/workly/${id}`);
    detailRecord.value = data.data;
    fillForm(data.data);
  } finally {
    panelLoading.value = false;
  }
}

function startEdit() {
  if (detailRecord.value) editingRecord.value = detailRecord.value;
}

function closePanel() {
  showPanel.value = false;
  resetForm();
}

async function submitForm() {
  formError.value = '';
  if (!form.staff_id) {
    formError.value = 'Выберите сотрудника';
    return;
  }
  saving.value = true;
  try {
    const payload = {
      staff_id: form.staff_id,
      work_date: form.work_date,
      clock_in: form.clock_in,
      clock_out: form.clock_out,
      status: form.status,
      note: form.note.trim(),
    };
    if (editingRecord.value) {
      await client.patch(`/reports/workly/${editingRecord.value.id}`, payload);
    } else {
      await client.post('/reports/workly', payload);
    }
    closePanel();
    await loadRows();
  } catch {
    formError.value = 'Не удалось сохранить запись';
  } finally {
    saving.value = false;
  }
}

async function deleteRecord() {
  if (!detailRecord.value || !window.confirm('Удалить эту запись?')) return;
  deleting.value = true;
  try {
    await client.delete(`/reports/workly/${detailRecord.value.id}`);
    closePanel();
    await loadRows();
  } catch {
    alert('Не удалось удалить запись');
  } finally {
    deleting.value = false;
  }
}

function setTab(status: string) {
  filters.status = status;
  applyFilters();
}

onMounted(async () => {
  await loadStaff();
  await loadRows();
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
        <h1 class="text-xl font-semibold text-fb-text">Табель рабочего времени (Workly)</h1>
        <p class="text-xs text-fb-secondary mt-0.5">Учет рабочего времени сотрудников, опозданий и посещаемости</p>
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
        <button type="button" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:bg-fb-blue-dark transition-colors" @click="openCreate">
          + Добавить запись
        </button>
      </div>
    </div>

    <!-- Summary KPI Cards -->
    <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
      <div class="rounded-xl border border-fb-line bg-fb-card p-4 text-center shadow-sm">
        <div class="text-2xl font-bold text-fb-text">{{ summary.total }}</div>
        <div class="mt-1 text-xs uppercase tracking-wider text-fb-secondary">Всего записей</div>
      </div>
      <div class="rounded-xl border border-fb-line bg-fb-card p-4 text-center shadow-sm">
        <div class="text-2xl font-bold text-emerald-600">{{ summary.at_work }}</div>
        <div class="mt-1 text-xs uppercase tracking-wider text-fb-secondary">На работе</div>
      </div>
      <div class="rounded-xl border border-fb-line bg-fb-card p-4 text-center shadow-sm">
        <div class="text-2xl font-bold text-amber-600">{{ summary.late_in }}</div>
        <div class="mt-1 text-xs uppercase tracking-wider text-fb-secondary">Опоздали</div>
      </div>
      <div class="rounded-xl border border-fb-line bg-fb-card p-4 text-center shadow-sm">
        <div class="text-2xl font-bold text-fb-danger">{{ summary.absent }}</div>
        <div class="mt-1 text-xs uppercase tracking-wider text-fb-secondary">Отсутствовали</div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex flex-wrap gap-2">
      <button
        v-for="tab in STATUS_OPTIONS"
        :key="tab.value || 'all'"
        type="button"
        class="rounded-lg px-4 py-2 text-xs font-semibold transition-colors"
        :class="filters.status === tab.value ? 'bg-fb-blue text-white shadow-sm' : 'border border-fb-line bg-fb-card text-fb-secondary hover:bg-fb-hover'"
        @click="setTab(tab.value)"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Сотрудник</label>
        <select v-model="filters.staff_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none">
          <option value="">Все сотрудники</option>
          <option v-for="s in staffList" :key="s.id" :value="String(s.id)">{{ s.name }}</option>
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
          placeholder="Поиск по сотруднику или заметке…"
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

    <!-- Table or Empty State -->
    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card shadow-sm">
      <div v-if="loading" class="p-12 text-center text-fb-secondary">Загрузка табеля…</div>
      
      <!-- Empty State -->
      <div v-else-if="!rows.length" class="flex flex-col items-center justify-center p-12 text-center">
        <div class="flex h-16 w-16 items-center justify-center rounded-full bg-fb-hover text-2xl mb-3 text-fb-icon">
          ⏱️
        </div>
        <h3 class="text-base font-semibold text-fb-text">Записи в табеле не найдены</h3>
        <p class="mt-1 text-sm text-fb-secondary max-w-sm">
          За выбранный период или по заданным фильтрам нет записей учета времени.
        </p>
        <div class="mt-4 flex items-center gap-2">
          <button
            type="button"
            class="rounded-lg border border-fb-line bg-white px-4 py-2 text-xs font-medium text-fb-blue hover:bg-fb-canvas transition-colors"
            @click="resetFilters"
          >
            Сбросить фильтры
          </button>
          <button
            type="button"
            class="rounded-lg bg-fb-blue px-4 py-2 text-xs font-medium text-white hover:bg-fb-blue-dark transition-colors"
            @click="openCreate"
          >
            + Добавить запись
          </button>
        </div>
      </div>

      <template v-else>
        <table class="w-full text-sm">
          <thead class="border-b border-fb-line bg-fb-canvas text-xs uppercase tracking-wider font-semibold text-fb-secondary">
            <tr>
              <th class="px-5 py-3.5 text-left">Сотрудник</th>
              <th class="px-5 py-3.5 text-left">Должность</th>
              <th class="px-5 py-3.5 text-left">Дата</th>
              <th class="px-5 py-3.5 text-left">Приход</th>
              <th class="px-5 py-3.5 text-left">Уход</th>
              <th class="px-5 py-3.5 text-left">Статус</th>
              <th class="px-5 py-3.5 text-left">Заметка</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-fb-line">
            <tr
              v-for="row in rows"
              :key="row.id"
              class="cursor-pointer hover:bg-fb-hover/40 transition-colors"
              @click="openDetail(row.id)"
            >
              <td class="px-5 py-3.5 font-medium text-fb-text">{{ row.staff }}</td>
              <td class="px-5 py-3.5 text-fb-secondary">{{ row.job_title }}</td>
              <td class="px-5 py-3.5 text-fb-secondary">{{ row.work_date }}</td>
              <td class="px-5 py-3.5 text-fb-text font-medium">{{ row.clock_in || '—' }}</td>
              <td class="px-5 py-3.5 text-fb-text font-medium">{{ row.clock_out || '—' }}</td>
              <td class="px-5 py-3.5">
                <span class="rounded-full px-2.5 py-0.5 text-xs font-medium" :class="statusClass(row.status)">
                  {{ row.status_label }}
                </span>
              </td>
              <td class="px-5 py-3.5 text-fb-secondary">{{ row.note || '—' }}</td>
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
            Страница {{ currentPage }} из {{ totalPages }} (всего {{ totalCount }} записей)
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

    <!-- Drawer Panel -->
    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closePanel" />
      <div class="drawer-panel-fb max-w-lg">
        <div class="flex items-center justify-between border-b px-6 py-4">
          <h2 class="text-lg font-semibold">{{ panelTitle }}</h2>
          <button type="button" @click="closePanel">✕</button>
        </div>
        <div v-if="panelLoading" class="p-6 text-fb-secondary">Загрузка…</div>
        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitForm">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <div>
              <label class="mb-1 block text-sm font-medium">Сотрудник</label>
              <select v-model="form.staff_id" :disabled="isReadOnly || Boolean(editingRecord)" class="w-full rounded-lg border px-3 py-2">
                <option v-for="s in staffList" :key="s.id" :value="s.id">{{ s.name }} — {{ s.job_title }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Дата</label>
              <input v-model="form.work_date" type="date" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-sm font-medium">Время прихода</label>
                <input v-model="form.clock_in" type="time" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium">Время ухода</label>
                <input v-model="form.clock_out" type="time" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
              </div>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Статус</label>
              <select v-model="form.status" :disabled="isReadOnly" class="w-full rounded-lg border px-3 py-2">
                <option v-for="s in FORM_STATUSES" :key="s.value" :value="s.value">{{ s.label }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Заметка</label>
              <textarea v-model="form.note" :readonly="isReadOnly" rows="2" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>
          <div class="flex gap-2 border-t px-6 py-4">
            <template v-if="isReadOnly && detailRecord">
              <button type="button" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white font-medium" @click="startEdit">Редактировать</button>
              <button type="button" class="rounded-lg border border-red-300 px-5 py-2 text-sm text-fb-danger font-medium hover:bg-red-50" :disabled="deleting" @click="deleteRecord">Удалить</button>
            </template>
            <button v-else type="submit" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white font-medium hover:bg-fb-blue-dark" :disabled="saving">
              {{ saving ? 'Сохранение…' : editingRecord ? 'Сохранить' : 'Создать' }}
            </button>
            <button type="button" class="rounded-lg border border-fb-line px-5 py-2 text-sm text-fb-secondary font-medium" @click="closePanel">Отмена</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
