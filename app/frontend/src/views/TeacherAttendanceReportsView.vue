<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { groupRoute, teacherRoute } from '../utils/crossLinks';

interface Branch {
  id: number;
  name: string;
}

interface GroupOption {
  id: number;
  name: string;
  branch_id: number;
  teacher_id?: number | null;
}

interface TeacherOption {
  id: number;
  name: string;
}

interface TeacherAttendanceRow {
  id: number;
  teacher_id: number;
  teacher: string;
  group_id: number;
  group: string;
  branch_id: number;
  branch: string;
  date: string;
  status: number;
  status_label: string;
  note: string;
  created_at: string;
}

interface AttendanceSummary {
  present: number;
  absent: number;
  late: number;
  total: number;
}

interface AttendancePayload {
  summary: AttendanceSummary;
  rows: TeacherAttendanceRow[];
  total: number;
  page: number;
  total_pages: number;
}

const STATUS_OPTIONS = [
  { value: 1, label: 'Присутствовал' },
  { value: 0, label: 'Отсутствовал' },
  { value: 2, label: 'Опоздал' },
] as const;

const router = useRouter();

const rows = ref<TeacherAttendanceRow[]>([]);
const summary = ref<AttendanceSummary>({ present: 0, absent: 0, late: 0, total: 0 });
const branches = ref<Branch[]>([]);
const groups = ref<GroupOption[]>([]);
const teachers = ref<TeacherOption[]>([]);
const loading = ref(true);
const exporting = ref(false);

const currentPage = ref(1);
const totalPages = ref(1);

const filters = reactive({
  branch_id: '',
  group_id: '',
  teacher_id: '',
  status: '',
  date_from: '',
  date_to: '',
  q: '',
});

const filterGroups = computed(() => {
  if (!filters.branch_id) return groups.value;
  return groups.value.filter((g) => String(g.branch_id) === filters.branch_id);
});

const attendancePercentages = computed(() => {
  const t = summary.value.total;
  if (!t) return { present: 0, late: 0, absent: 0 };
  const p = Math.round((summary.value.present / t) * 100);
  const l = Math.round((summary.value.late / t) * 100);
  const a = Math.max(0, 100 - p - l);
  return { present: p, late: l, absent: a };
});

function statusClass(status: number) {
  if (status === 1) return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
  if (status === 0) return 'bg-red-50 text-fb-danger border border-red-200';
  return 'bg-amber-50 text-amber-700 border border-amber-200';
}

function resetFilters() {
  filters.branch_id = '';
  filters.group_id = '';
  filters.teacher_id = '';
  filters.status = '';
  filters.date_from = '';
  filters.date_to = '';
  filters.q = '';
  currentPage.value = 1;
  loadReport();
}

function applyFilters() {
  currentPage.value = 1;
  loadReport();
}

function changePage(delta: number) {
  currentPage.value += delta;
  loadReport();
}

async function exportCsv() {
  exporting.value = true;
  const params: Record<string, string> = { export: '1' };
  if (filters.branch_id) params.branch_id = filters.branch_id;
  if (filters.group_id) params.group_id = filters.group_id;
  if (filters.teacher_id) params.teacher_id = filters.teacher_id;
  if (filters.status !== '') params.status = filters.status;
  if (filters.date_from) params.date_from = filters.date_from;
  if (filters.date_to) params.date_to = filters.date_to;
  if (filters.q.trim()) params.q = filters.q.trim();

  try {
    const { data } = await client.get<ApiEnvelope<AttendancePayload>>(
      '/reports/teacher-attendance',
      { params },
    );
    const csvRows = [
      ['Преподаватель (Teacher)', 'Группа (Group)', 'Филиал (Branch)', 'Дата (Date)', 'Статус (Status)', 'Заметка (Note)'],
    ];
    for (const row of data.data.rows) {
      csvRows.push([
        `"${row.teacher}"`,
        `"${row.group}"`,
        `"${row.branch}"`,
        `"${row.date}"`,
        `"${row.status_label}"`,
        `"${row.note || ''}"`,
      ]);
    }
    const csvContent = 'data:text/csv;charset=utf-8,\uFEFF' + csvRows.map((e) => e.join(',')).join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `teacher_attendance_report_${new Date().toISOString().slice(0, 10)}.csv`);
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

async function loadReport() {
  loading.value = true;
  try {
    const params: Record<string, string> = { page: String(currentPage.value) };
    if (filters.branch_id) params.branch_id = filters.branch_id;
    if (filters.group_id) params.group_id = filters.group_id;
    if (filters.teacher_id) params.teacher_id = filters.teacher_id;
    if (filters.status !== '') params.status = filters.status;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();

    const { data } = await client.get<ApiEnvelope<AttendancePayload>>(
      '/reports/teacher-attendance',
      { params },
    );
    summary.value = data.data.summary;
    rows.value = data.data.rows;
    totalPages.value = data.data.total_pages || 1;
  } finally {
    loading.value = false;
  }
}

async function loadOptions() {
  const [branchRes, groupRes, teacherRes] = await Promise.all([
    client.get<ApiEnvelope<Branch[]>>('/branch'),
    client.get<ApiEnvelope<GroupOption[]>>('/groups'),
    client.get<ApiEnvelope<TeacherOption[]>>('/user', { params: { user_type: 'teacher' } }),
  ]);
  branches.value = branchRes.data.data;
  groups.value = (groupRes.data.data as any[]).map((group) => ({
    id: group.id,
    name: group.name,
    branch_id: group.branch_id,
    teacher_id: group.teacher_id ?? null,
  }));
  teachers.value = teacherRes.data.data.map((teacher) => ({
    id: teacher.id,
    name: teacher.name,
  }));
}

function goTeacher(teacherId: number) {
  router.push(teacherRoute(teacherId));
}

function goGroup(groupId: number) {
  router.push(groupRoute(groupId));
}

onMounted(async () => {
  try {
    await Promise.all([loadOptions(), loadReport()]);
  } finally {
    loading.value = false;
  }
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
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold text-fb-text">Отчет по посещаемости преподавателей</h1>
        <p class="text-xs text-fb-secondary mt-0.5">Учет проведения уроков, явок и опозданий преподавателей</p>
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

    <!-- Summary Cards -->
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div class="rounded-xl border border-fb-line bg-fb-card p-4">
        <p class="text-xs uppercase tracking-wider font-medium text-fb-secondary">Всего записей</p>
        <p class="mt-1 text-2xl font-bold text-fb-text">{{ summary.total }}</p>
      </div>
      <div class="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4">
        <div class="flex items-center justify-between">
          <p class="text-xs uppercase tracking-wider font-medium text-emerald-700">Присутствовал</p>
          <span class="text-xs font-semibold text-emerald-700">{{ attendancePercentages.present }}%</span>
        </div>
        <p class="mt-1 text-2xl font-bold text-emerald-800">{{ summary.present }}</p>
      </div>
      <div class="rounded-xl border border-amber-200 bg-amber-50/50 p-4">
        <div class="flex items-center justify-between">
          <p class="text-xs uppercase tracking-wider font-medium text-amber-700">Опоздал</p>
          <span class="text-xs font-semibold text-amber-700">{{ attendancePercentages.late }}%</span>
        </div>
        <p class="mt-1 text-2xl font-bold text-amber-800">{{ summary.late }}</p>
      </div>
      <div class="rounded-xl border border-red-200 bg-red-50/50 p-4">
        <div class="flex items-center justify-between">
          <p class="text-xs uppercase tracking-wider font-medium text-red-700">Отсутствовал</p>
          <span class="text-xs font-semibold text-red-700">{{ attendancePercentages.absent }}%</span>
        </div>
        <p class="mt-1 text-2xl font-bold text-red-800">{{ summary.absent }}</p>
      </div>
    </div>

    <!-- Visual Chart: Attendance Distribution Bar -->
    <div v-if="summary.total > 0" class="rounded-xl border border-fb-line bg-fb-card p-4">
      <div class="flex items-center justify-between text-xs font-medium text-fb-secondary mb-2">
        <span>Распределение посещаемости преподавателей</span>
        <div class="flex items-center gap-4">
          <span class="inline-flex items-center gap-1.5">
            <span class="h-2.5 w-2.5 rounded-full bg-emerald-500" /> Присутствие ({{ attendancePercentages.present }}%)
          </span>
          <span class="inline-flex items-center gap-1.5">
            <span class="h-2.5 w-2.5 rounded-full bg-amber-500" /> Опоздания ({{ attendancePercentages.late }}%)
          </span>
          <span class="inline-flex items-center gap-1.5">
            <span class="h-2.5 w-2.5 rounded-full bg-red-500" /> Пропуски ({{ attendancePercentages.absent }}%)
          </span>
        </div>
      </div>
      <div class="h-3.5 w-full overflow-hidden rounded-full bg-fb-line flex">
        <div
          v-if="attendancePercentages.present > 0"
          class="h-full bg-emerald-500 transition-all duration-500"
          :style="{ width: `${attendancePercentages.present}%` }"
          :title="`Присутствие: ${attendancePercentages.present}%`"
        />
        <div
          v-if="attendancePercentages.late > 0"
          class="h-full bg-amber-500 transition-all duration-500"
          :style="{ width: `${attendancePercentages.late}%` }"
          :title="`Опоздания: ${attendancePercentages.late}%`"
        />
        <div
          v-if="attendancePercentages.absent > 0"
          class="h-full bg-red-500 transition-all duration-500"
          :style="{ width: `${attendancePercentages.absent}%` }"
          :title="`Пропуски: ${attendancePercentages.absent}%`"
        />
      </div>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Филиал</label>
        <select
          v-model="filters.branch_id"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
          @change="applyFilters"
        >
          <option value="">Все филиалы</option>
          <option v-for="branch in branches" :key="branch.id" :value="String(branch.id)">
            {{ branch.name }}
          </option>
        </select>
      </div>

      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Группа</label>
        <select
          v-model="filters.group_id"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
          @change="applyFilters"
        >
          <option value="">Все группы</option>
          <option v-for="group in filterGroups" :key="group.id" :value="String(group.id)">
            {{ group.name }}
          </option>
        </select>
      </div>

      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Преподаватель</label>
        <select
          v-model="filters.teacher_id"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
          @change="applyFilters"
        >
          <option value="">Все преподаватели</option>
          <option v-for="teacher in teachers" :key="teacher.id" :value="String(teacher.id)">
            {{ teacher.name }}
          </option>
        </select>
      </div>

      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Статус</label>
        <select
          v-model="filters.status"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
          @change="applyFilters"
        >
          <option value="">Все статусы</option>
          <option v-for="option in STATUS_OPTIONS" :key="option.value" :value="String(option.value)">
            {{ option.label }}
          </option>
        </select>
      </div>

      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">С даты</label>
        <input
          v-model="filters.date_from"
          type="date"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
        />
      </div>

      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">По дату</label>
        <input
          v-model="filters.date_to"
          type="date"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
        />
      </div>

      <div class="min-w-[180px] flex-1">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Поиск</label>
        <input
          v-model="filters.q"
          type="search"
          placeholder="Поиск по имени…"
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
      <div v-if="loading" class="p-12 text-center text-fb-secondary">Загрузка посещаемости…</div>

      <!-- Empty State -->
      <div v-else-if="!rows.length" class="flex flex-col items-center justify-center p-12 text-center">
        <div class="flex h-16 w-16 items-center justify-center rounded-full bg-fb-hover text-2xl mb-3 text-fb-icon">
          👨‍🏫
        </div>
        <h3 class="text-base font-semibold text-fb-text">Записи посещаемости не найдены</h3>
        <p class="mt-1 text-sm text-fb-secondary max-w-sm">
          За выбранный период или по указанным фильтрам нет записей посещаемости преподавателей.
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
              <th class="px-5 py-3.5 text-left">Преподаватель</th>
              <th class="px-5 py-3.5 text-left">Группа</th>
              <th class="px-5 py-3.5 text-left">Филиал</th>
              <th class="px-5 py-3.5 text-left">Дата</th>
              <th class="px-5 py-3.5 text-left">Статус</th>
              <th class="px-5 py-3.5 text-left">Заметка</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-fb-line">
            <tr
              v-for="row in rows"
              :key="row.id"
              class="hover:bg-fb-hover/40 transition-colors"
            >
              <td class="px-5 py-3.5 font-medium text-fb-text">
                <button
                  type="button"
                  class="text-left font-medium text-fb-text hover:text-fb-blue hover:underline"
                  @click="goTeacher(row.teacher_id)"
                >
                  {{ row.teacher }}
                </button>
              </td>
              <td class="px-5 py-3.5 text-fb-secondary">
                <button
                  type="button"
                  class="text-left text-fb-secondary hover:text-fb-blue hover:underline"
                  @click="goGroup(row.group_id)"
                >
                  {{ row.group }}
                </button>
              </td>
              <td class="px-5 py-3.5 text-fb-secondary">{{ row.branch }}</td>
              <td class="px-5 py-3.5 text-fb-secondary">{{ row.date }}</td>
              <td class="px-5 py-3.5">
                <span class="rounded-full px-2.5 py-0.5 text-xs font-medium" :class="statusClass(row.status)">
                  {{ row.status_label }}
                </span>
              </td>
              <td class="px-5 py-3.5 text-fb-secondary">{{ row.note || '—' }}</td>
            </tr>
          </tbody>
        </table>

        <!-- Pagination -->
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
            Страница {{ currentPage }} из {{ totalPages }} (всего {{ summary.total }} записей)
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
