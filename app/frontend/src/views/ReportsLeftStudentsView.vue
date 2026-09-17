<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { groupRoute, studentRoute } from '../utils/crossLinks';

interface Branch {
  id: number;
  name: string;
}

interface GroupOption {
  id: number;
  name: string;
  branch_id: number;
}

interface LeftStudentRow {
  id: number;
  full_name: string;
  phone: string;
  status: number;
  status_label: string;
  branch_id: number;
  branch: string;
  group_id: number | null;
  group: string;
  balance?: number;
  comment?: string;
  left_at: string;
}

interface Summary {
  left_active: number;
  left_trial: number;
  total: number;
}

interface Payload {
  summary: Summary;
  rows: LeftStudentRow[];
  total?: number;
  page?: number;
  total_pages?: number;
}

const STATUS_OPTIONS = [
  { value: '', label: 'Все ушедшие' },
  { value: '8', label: 'Ушел из группы (активный)' },
  { value: '7', label: 'Ушел после пробного' },
] as const;

const router = useRouter();
const route = useRoute();

const isSettingsView = computed(() => route.path === '/left-students');

const rows = ref<LeftStudentRow[]>([]);
const summary = ref<Summary>({ left_active: 0, left_trial: 0, total: 0 });
const branches = ref<Branch[]>([]);
const groups = ref<GroupOption[]>([]);
const loading = ref(true);
const exporting = ref(false);
const currentPage = ref(1);
const totalPages = ref(1);
const totalCount = ref(0);

const filters = reactive({
  status: '',
  branch_id: '',
  group_id: '',
  date_from: '',
  date_to: '',
  q: '',
});

async function loadMeta() {
  const [branchRes, groupRes] = await Promise.all([
    client.get<ApiEnvelope<Branch[]>>('/branch'),
    client.get<ApiEnvelope<GroupOption[]>>('/groups'),
  ]);
  branches.value = branchRes.data.data;
  groups.value = groupRes.data.data;
}

function applyFilters() {
  currentPage.value = 1;
  loadRows();
}

function resetFilters() {
  filters.status = '';
  filters.branch_id = '';
  filters.group_id = '';
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
    if (filters.branch_id) params.branch_id = filters.branch_id;
    if (filters.group_id) params.group_id = filters.group_id;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();
    const { data } = await client.get<ApiEnvelope<Payload>>('/reports/left-students', { params });
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
    if (filters.branch_id) params.branch_id = filters.branch_id;
    if (filters.group_id) params.group_id = filters.group_id;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();

    const { data } = await client.get<ApiEnvelope<Payload>>('/reports/left-students', { params });
    const csvRows = [
      ['ID', 'ФИО (Name)', 'Телефон (Phone)', 'Статус (Status)', 'Группа (Group)', 'Филиал (Branch)', 'Баланс (Balance)', 'Причина ухода / Комментарий (Comment)', 'Дата ухода (Left Date)'],
    ];
    for (const row of data.data.rows) {
      csvRows.push([
        String(row.id),
        `"${row.full_name}"`,
        `"${row.phone}"`,
        `"${row.status_label}"`,
        `"${row.group}"`,
        `"${row.branch}"`,
        String(row.balance ?? 0),
        `"${row.comment || ''}"`,
        `"${row.left_at}"`,
      ]);
    }
    const csvContent = 'data:text/csv;charset=utf-8,﻿' + csvRows.map((e) => e.join(',')).join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `left_students_${new Date().toISOString().slice(0, 10)}.csv`);
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

function openStudent(id: number) {
  router.push(studentRoute(id));
}

function openGroup(groupId: number) {
  router.push(groupRoute(groupId));
}

onMounted(async () => {
  await loadMeta();
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
        <h1 class="text-xl font-semibold text-fb-text">Отчет по ушедшим студентам</h1>
        <p class="text-xs text-fb-secondary mt-0.5">Учет отчисленных студентов из групп и ушедших после пробных уроков</p>
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
        <router-link
          v-if="!isSettingsView"
          to="/students"
          class="text-sm font-medium text-fb-blue hover:underline"
        >
          Все студенты →
        </router-link>
      </div>
    </div>

    <!-- Summary KPI cards -->
    <div v-if="!isSettingsView" class="grid grid-cols-1 gap-3 md:grid-cols-3">
      <div class="rounded-xl border border-fb-line bg-fb-card p-5 text-center shadow-sm">
        <div class="text-3xl font-bold text-fb-text">{{ summary.total }}</div>
        <div class="mt-1 text-xs font-medium uppercase tracking-wider text-fb-secondary">Всего ушло</div>
      </div>
      <div class="rounded-xl border border-fb-line bg-fb-card p-5 text-center shadow-sm">
        <div class="text-3xl font-bold text-fb-blue">{{ summary.left_active }}</div>
        <div class="mt-1 text-xs font-medium uppercase tracking-wider text-fb-secondary">Ушли из активной группы</div>
      </div>
      <div class="rounded-xl border border-fb-line bg-fb-card p-5 text-center shadow-sm">
        <div class="text-3xl font-bold text-amber-600">{{ summary.left_trial }}</div>
        <div class="mt-1 text-xs font-medium uppercase tracking-wider text-fb-secondary">Ушли после пробного</div>
      </div>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Категория ухода</label>
        <select v-model="filters.status" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none">
          <option v-for="opt in STATUS_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Филиал</label>
        <select v-model="filters.branch_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none">
          <option value="">Все филиалы</option>
          <option v-for="b in branches" :key="b.id" :value="String(b.id)">{{ b.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Группа</label>
        <select v-model="filters.group_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none">
          <option value="">Все группы</option>
          <option v-for="g in groups" :key="g.id" :value="String(g.id)">{{ g.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">С даты ухода</label>
        <input v-model="filters.date_from" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">По дату ухода</label>
        <input v-model="filters.date_to" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
      </div>
      <div class="min-w-[180px] flex-1">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Поиск</label>
        <input
          v-model="filters.q"
          type="search"
          placeholder="Поиск по имени или телефону…"
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
      <div v-if="loading" class="p-12 text-center text-fb-secondary">Загрузка данных…</div>
      
      <!-- Empty State -->
      <div v-else-if="!rows.length" class="flex flex-col items-center justify-center p-12 text-center">
        <div class="flex h-16 w-16 items-center justify-center rounded-full bg-fb-hover text-2xl mb-3 text-fb-icon">
          🎓
        </div>
        <h3 class="text-base font-semibold text-fb-text">Ушедшие студенты не найдены</h3>
        <p class="mt-1 text-sm text-fb-secondary max-w-sm">
          По заданным параметрам фильтра не найдено ни одного отчисленного студента.
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
              <th class="px-5 py-3.5 text-left">ФИО студента</th>
              <th class="px-5 py-3.5 text-left">Телефон</th>
              <th class="px-5 py-3.5 text-left">Категория</th>
              <th class="px-5 py-3.5 text-left">Группа</th>
              <th class="px-5 py-3.5 text-left">Филиал</th>
              <th class="px-5 py-3.5 text-left">Причина ухода (Комментарий)</th>
              <th class="px-5 py-3.5 text-left">Дата ухода</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-fb-line">
            <tr
              v-for="row in rows"
              :key="row.id"
              class="cursor-pointer hover:bg-fb-hover/40 transition-colors"
              @click="openStudent(row.id)"
            >
              <td class="px-5 py-3.5 font-medium text-fb-text">{{ row.full_name }}</td>
              <td class="px-5 py-3.5 text-fb-secondary">{{ row.phone }}</td>
              <td class="px-5 py-3.5">
                <span
                  class="rounded-full px-2.5 py-0.5 text-xs font-medium"
                  :class="row.status === 7 ? 'bg-amber-50 text-amber-700 border border-amber-200' : 'bg-gray-100 text-gray-700 border border-gray-200'"
                >
                  {{ row.status_label }}
                </span>
              </td>
              <td class="px-5 py-3.5">
                <button
                  v-if="row.group_id"
                  type="button"
                  class="text-fb-blue hover:underline font-medium"
                  @click.stop="openGroup(row.group_id)"
                >
                  {{ row.group }}
                </button>
                <span v-else class="text-fb-secondary">{{ row.group }}</span>
              </td>
              <td class="px-5 py-3.5 text-fb-secondary">{{ row.branch }}</td>
              <td class="px-5 py-3.5 text-fb-secondary max-w-[240px] truncate" :title="row.comment">
                {{ row.comment || '—' }}
              </td>
              <td class="px-5 py-3.5 font-medium text-fb-text">{{ row.left_at }}</td>
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
            Страница {{ currentPage }} из {{ totalPages }} (всего {{ totalCount }} ушедших)
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
  </div>
</template>
