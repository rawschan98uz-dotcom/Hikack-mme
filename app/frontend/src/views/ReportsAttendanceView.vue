<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface Branch {
  id: number;
  name: string;
}

interface CourseInfo {
  id: number;
  name: string | null;
  price: number;
}

interface GroupTag {
  id: number;
  name: string;
}

interface GroupRow {
  id: number;
  name: string;
  days: number;
  days_label: string;
  status: number;
  status_label: string;
  branch_id: number;
  branch: string;
  course_id: number | null;
  course: CourseInfo | null;
  teacher_id: number | null;
  teacher: string | null;
  room_id: number | null;
  room: string | null;
  lesson_start_time: string | null;
  lesson_end_time: string | null;
  students_count: number;
  tags: GroupTag[];
}

interface GroupStudent {
  id: number;
  full_name: string;
  phone: string;
  status: number;
  status_label: string;
}

interface AttendanceRecordResponse {
  id: number;
  student_id: number;
  student: string;
  group_id: number;
  date: string;
  status: number;
  status_label: string;
  note?: string;
}

interface AttendanceSaveResult {
  saved: number;
  group_id: number;
  date: string;
}

// State
const loadingGroups = ref(true);
const branches = ref<Branch[]>([]);
const allGroups = ref<GroupRow[]>([]);

// Filter state
const todayStr = new Date().toISOString().slice(0, 10);
const selectedDate = ref(todayStr);
const selectedBranch = ref<string>('');
const searchQuery = ref<string>('');
const showSuggestions = ref(false);

// Pagination
const pageSize = 50;
const currentPage = ref(1);

// Modal / Drawer state for group roster
const showModal = ref(false);
const activeGroup = ref<GroupRow | null>(null);
const loadingStudents = ref(false);
const groupStudents = ref<GroupStudent[]>([]);
const studentStatuses = reactive<Record<number, number>>({});
const studentNotes = reactive<Record<number, string>>({});
const savingAttendance = ref(false);
const saveSuccessMessage = ref('');
const saveErrorMessage = ref('');

// Smart search & live filtering
const filteredGroups = computed(() => {
  let list = allGroups.value;

  if (selectedBranch.value) {
    const branchId = Number(selectedBranch.value);
    list = list.filter((g) => g.branch_id === branchId);
  }

  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return list;

  return list.filter((g) => {
    const nameMatch = g.name.toLowerCase().includes(q);
    const courseMatch = g.course?.name?.toLowerCase().includes(q);
    const teacherMatch = g.teacher?.toLowerCase().includes(q);
    const branchMatch = g.branch?.toLowerCase().includes(q);
    return Boolean(nameMatch || courseMatch || teacherMatch || branchMatch);
  });
});

// Autocomplete suggestions (top 6 matches based on input)
const searchSuggestions = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q || q.length < 1) return [];

  const matches: { group: GroupRow; highlightField: string }[] = [];
  for (const g of allGroups.value) {
    if (g.name.toLowerCase().includes(q)) {
      matches.push({ group: g, highlightField: g.name });
    } else if (g.course?.name?.toLowerCase().includes(q)) {
      matches.push({ group: g, highlightField: `${g.name} (${g.course.name})` });
    } else if (g.teacher?.toLowerCase().includes(q)) {
      matches.push({ group: g, highlightField: `${g.name} — ${g.teacher}` });
    } else if (g.branch?.toLowerCase().includes(q)) {
      matches.push({ group: g, highlightField: `${g.name} [${g.branch}]` });
    }
    if (matches.length >= 8) break;
  }
  return matches;
});

// Paginated groups for table
const totalPages = computed(() => Math.ceil(filteredGroups.value.length / pageSize) || 1);

const paginatedGroups = computed(() => {
  const start = (currentPage.value - 1) * pageSize;
  return filteredGroups.value.slice(start, start + pageSize);
});

// Reset page when filter changes
watch([selectedBranch, searchQuery], () => {
  currentPage.value = 1;
});

// Summary counts inside active group roster
const rosterSummary = computed(() => {
  let present = 0;
  let absent = 0;
  let late = 0;
  for (const student of groupStudents.value) {
    const st = studentStatuses[student.id];
    if (st === 1) present++;
    else if (st === 0) absent++;
    else if (st === 2) late++;
  }
  return { present, absent, late, total: groupStudents.value.length };
});

// Fetch groups & branches
async function loadInitialData() {
  loadingGroups.value = true;
  try {
    const [branchRes, groupsRes] = await Promise.all([
      client.get<ApiEnvelope<Branch[]>>('/branch'),
      client.get<ApiEnvelope<any>>('/groups', { params: { limit: '1000', status: '2' } }),
    ]);

    branches.value = Array.isArray(branchRes.data.data) ? branchRes.data.data : [];

    const rawGroups = groupsRes.data.data;
    if (Array.isArray(rawGroups)) {
      allGroups.value = rawGroups;
    } else if (rawGroups && Array.isArray(rawGroups.results)) {
      allGroups.value = rawGroups.results;
    } else {
      allGroups.value = [];
    }
  } catch (err) {
    console.error('Failed to load groups for attendance report:', err);
  } finally {
    loadingGroups.value = false;
  }
}

// Open group roster modal
async function openGroupRoster(group: GroupRow) {
  activeGroup.value = group;
  showModal.value = true;
  loadingStudents.value = true;
  saveSuccessMessage.value = '';
  saveErrorMessage.value = '';
  showSuggestions.value = false;

  // Clear previous entries
  groupStudents.value = [];
  Object.keys(studentStatuses).forEach((k) => delete studentStatuses[Number(k)]);
  Object.keys(studentNotes).forEach((k) => delete studentNotes[Number(k)]);

  try {
    // 1. Fetch group details including students
    const groupDetailPromise = client.get<ApiEnvelope<any>>(`/groups/${group.id}`);

    // 2. Fetch existing attendance records for this group and date
    const attendancePromise = client.get<ApiEnvelope<any>>('/reports/attendance', {
      params: {
        group_id: String(group.id),
        date_from: selectedDate.value,
        date_to: selectedDate.value,
        export: '1',
      },
    });

    const [groupRes, attendanceRes] = await Promise.all([groupDetailPromise, attendancePromise]);

    const groupData = groupRes.data.data;
    const students: GroupStudent[] = groupData.students || [];
    groupStudents.value = students;

    // Build map of existing attendance records
    const attendanceData = attendanceRes.data.data;
    const rows: AttendanceRecordResponse[] = attendanceData.rows || [];
    const attendanceMap = new Map<number, { status: number; note?: string }>();
    for (const row of rows) {
      attendanceMap.set(row.student_id, { status: row.status, note: row.note });
    }

    // Set statuses: default to 1 (Присутствовал) if no record yet
    for (const student of students) {
      const existing = attendanceMap.get(student.id);
      if (existing) {
        studentStatuses[student.id] = existing.status;
        studentNotes[student.id] = existing.note || '';
      } else {
        studentStatuses[student.id] = 1; // Default present
        studentNotes[student.id] = '';
      }
    }
  } catch (err) {
    console.error('Failed to load group students or attendance:', err);
    saveErrorMessage.value = 'Ошибка при загрузке данных учеников группы';
  } finally {
    loadingStudents.value = false;
  }
}

// Quick action: set all students to a given status
function markAll(status: number) {
  for (const student of groupStudents.value) {
    studentStatuses[student.id] = status;
  }
}

// Save attendance for the whole group
async function saveGroupAttendance() {
  if (!activeGroup.value || !selectedDate.value) return;

  savingAttendance.value = true;
  saveSuccessMessage.value = '';
  saveErrorMessage.value = '';

  const records = groupStudents.value.map((student) => ({
    student_id: student.id,
    status: studentStatuses[student.id] ?? 1,
    note: (studentNotes[student.id] || '').trim(),
  }));

  try {
    await client.post<ApiEnvelope<AttendanceSaveResult>>('/reports/attendance', {
      group_id: activeGroup.value.id,
      date: selectedDate.value,
      records,
    });

    saveSuccessMessage.value = `Посещаемость успешно сохранена! (отмечено учеников: ${records.length})`;
  } catch (err: any) {
    console.error('Failed to save group attendance:', err);
    saveErrorMessage.value = err?.response?.data?.error || err?.message || 'Не удалось сохранить посещаемость';
  } finally {
    savingAttendance.value = false;
  }
}

function closeModal() {
  showModal.value = false;
  activeGroup.value = null;
  saveSuccessMessage.value = '';
  saveErrorMessage.value = '';
}

function selectSuggestion(suggestion: { group: GroupRow; highlightField: string }) {
  searchQuery.value = suggestion.group.name;
  showSuggestions.value = false;
  openGroupRoster(suggestion.group);
}

function setDateToday() {
  selectedDate.value = todayStr;
  if (activeGroup.value) {
    openGroupRoster(activeGroup.value);
  }
}

function setDateYesterday() {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  selectedDate.value = d.toISOString().slice(0, 10);
  if (activeGroup.value) {
    openGroupRoster(activeGroup.value);
  }
}

function onDateChange() {
  if (activeGroup.value) {
    openGroupRoster(activeGroup.value);
  }
}

function resetSearchAndFilters() {
  searchQuery.value = '';
  selectedBranch.value = '';
  currentPage.value = 1;
}

function statusBadgeClass(status: number) {
  if (status === 1) return 'bg-emerald-100 text-emerald-800 border-emerald-300';
  if (status === 0) return 'bg-red-100 text-red-800 border-red-300';
  return 'bg-amber-100 text-amber-800 border-amber-300';
}

function studentStatusPill(status: number) {
  if (status === 1) return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  if (status === 2) return 'bg-sky-50 text-sky-700 border-sky-200';
  if (status === 7 || status === 8) return 'bg-red-50 text-red-700 border-red-200';
  return 'bg-gray-50 text-gray-700 border-gray-200';
}

async function exportAllAttendanceCsv() {
  try {
    const params: Record<string, string> = {
      export: '1',
      date_from: selectedDate.value,
      date_to: selectedDate.value,
    };
    if (selectedBranch.value) params.branch_id = selectedBranch.value;

    const { data } = await client.get<ApiEnvelope<any>>('/reports/attendance', { params });
    const rows = data?.data?.rows || [];
    if (!rows.length) {
      alert('За выбранную дату нет сохраненных записей посещаемости для экспорта.');
      return;
    }

    const csvRows = [
      ['Ученик', 'Группа', 'Филиал', 'Дата', 'Статус', 'Заметка'],
    ];
    for (const r of rows) {
      csvRows.push([
        `"${r.student}"`,
        `"${r.group}"`,
        `"${r.branch}"`,
        `"${r.date}"`,
        `"${r.status_label}"`,
        `"${r.note || ''}"`,
      ]);
    }
    const csvContent = 'data:text/csv;charset=utf-8,\uFEFF' + csvRows.map((e) => e.join(',')).join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `attendance_${selectedDate.value}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } catch (err) {
    console.error(err);
    alert('Не удалось экспортировать отчет в CSV');
  }
}

onMounted(() => {
  loadInitialData();
});
</script>

<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-xl font-bold text-fb-text flex items-center gap-2">
          <span>📋</span>
          <span>Посещаемость учеников</span>
        </h1>
        <p class="text-xs text-fb-secondary mt-0.5">
          Журнал учета посещаемости по группам. Нажмите на название группы для просмотра списка учеников и быстрой отметки.
        </p>
      </div>

      <div class="flex items-center gap-2">
        <button
          type="button"
          class="rounded-lg border border-fb-line bg-fb-card px-3.5 py-2 text-sm text-fb-secondary hover:border-fb-blue hover:text-fb-blue transition-colors flex items-center gap-1.5 shadow-sm"
          title="Экспортировать сохраненную посещаемость за выбранную дату"
          @click="exportAllAttendanceCsv"
        >
          <span>📥</span>
          <span>Экспорт CSV за дату</span>
        </button>
      </div>
    </div>

    <!-- Filter & Control Panel -->
    <div class="rounded-xl border border-fb-line bg-fb-card p-4 shadow-sm space-y-3">
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-12 items-end">
        <!-- Date Picker -->
        <div class="lg:col-span-4">
          <div class="flex items-center justify-between mb-1">
            <label class="block text-xs font-semibold text-fb-text">
              Дата занятия:
            </label>
            <div class="flex items-center gap-1.5 text-xs">
              <button
                type="button"
                class="text-fb-blue hover:underline font-medium"
                @click="setDateToday"
              >
                Сегодня
              </button>
              <span class="text-fb-secondary">|</span>
              <button
                type="button"
                class="text-fb-blue hover:underline font-medium"
                @click="setDateYesterday"
              >
                Вчера
              </button>
            </div>
          </div>
          <input
            v-model="selectedDate"
            type="date"
            class="w-full rounded-lg border border-fb-line bg-white px-3 py-2 text-sm text-fb-text focus:border-fb-blue focus:outline-none focus:ring-1 focus:ring-fb-blue"
            @change="onDateChange"
          />
        </div>

        <!-- Smart Search Input with Autocomplete Dropdown -->
        <div class="relative lg:col-span-5">
          <label class="mb-1 block text-xs font-semibold text-fb-text flex items-center justify-between">
            <span>Умный поиск группы</span>
            <span v-if="searchQuery" class="text-[11px] font-normal text-fb-secondary">
              Найдено: {{ filteredGroups.length }}
            </span>
          </label>
          <div class="relative">
            <input
              v-model="searchQuery"
              type="search"
              placeholder="Введите название группы, курс или учителя..."
              autocomplete="off"
              class="w-full rounded-lg border border-fb-line bg-white pl-9 pr-8 py-2 text-sm text-fb-text placeholder-fb-secondary/70 focus:border-fb-blue focus:outline-none focus:ring-1 focus:ring-fb-blue"
              @focus="showSuggestions = true"
              @input="showSuggestions = true"
            />
            <span class="absolute left-3 top-2.5 text-fb-secondary text-sm pointer-events-none">
              🔍
            </span>
            <button
              v-if="searchQuery"
              type="button"
              class="absolute right-2.5 top-2.5 text-fb-secondary hover:text-fb-text text-sm"
              title="Очистить поиск"
              @click="searchQuery = ''; showSuggestions = false;"
            >
              ✕
            </button>
          </div>

          <!-- Autocomplete Dropdown Menu -->
          <div
            v-if="showSuggestions && searchSuggestions.length > 0"
            class="absolute left-0 right-0 top-full mt-1 z-30 rounded-xl border border-fb-line bg-white shadow-xl overflow-hidden divide-y divide-fb-line max-h-64 overflow-y-auto"
          >
            <div class="bg-fb-canvas px-3 py-1.5 text-[11px] font-semibold text-fb-secondary uppercase tracking-wider">
              Подсказки (нажмите для открытия журнала):
            </div>
            <button
              v-for="item in searchSuggestions"
              :key="item.group.id"
              type="button"
              class="w-full px-3 py-2 text-left hover:bg-fb-hover transition-colors flex items-center justify-between gap-2 group"
              @mousedown.prevent="selectSuggestion(item)"
            >
              <div class="truncate">
                <span class="font-medium text-sm text-fb-text group-hover:text-fb-blue">
                  {{ item.group.name }}
                </span>
                <span v-if="item.group.course" class="text-xs text-fb-secondary ml-2">
                  {{ item.group.course.name }}
                </span>
                <span v-if="item.group.teacher" class="text-xs text-fb-secondary/80 ml-2">
                  • {{ item.group.teacher }}
                </span>
              </div>
              <span class="shrink-0 text-xs text-fb-secondary bg-fb-canvas px-2 py-0.5 rounded-md border border-fb-line">
                👥 {{ item.group.students_count }} уч.
              </span>
            </button>
          </div>
        </div>

        <!-- Branch Select -->
        <div class="lg:col-span-3">
          <label class="mb-1 block text-xs font-semibold text-fb-text">
            Филиал
          </label>
          <select
            v-model="selectedBranch"
            class="w-full rounded-lg border border-fb-line bg-white px-3 py-2 text-sm text-fb-text focus:border-fb-blue focus:outline-none focus:ring-1 focus:ring-fb-blue"
          >
            <option value="">Все филиалы</option>
            <option v-for="b in branches" :key="b.id" :value="String(b.id)">
              {{ b.name }}
            </option>
          </select>
        </div>
      </div>

      <!-- Filter Subbar: Active groups count & Reset button -->
      <div class="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-fb-line/60 text-xs">
        <span class="text-fb-secondary">
          Всего групп: <strong class="text-fb-text">{{ filteredGroups.length }}</strong>
        </span>

        <button
          v-if="searchQuery || selectedBranch"
          type="button"
          class="text-fb-blue hover:underline font-medium"
          @click="resetSearchAndFilters"
        >
          Сбросить фильтры
        </button>
      </div>
    </div>

    <!-- Groups Table Card -->
    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card shadow-sm">
      <!-- Loading State -->
      <div v-if="loadingGroups" class="p-16 text-center text-fb-secondary">
        <div class="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-fb-blue border-r-transparent mb-3" />
        <p class="text-sm font-medium text-fb-text">Загрузка списка групп…</p>
      </div>

      <!-- Empty State -->
      <div v-else-if="!filteredGroups.length" class="flex flex-col items-center justify-center p-14 text-center">
        <div class="flex h-16 w-16 items-center justify-center rounded-full bg-fb-hover text-2xl mb-3 text-fb-icon">
          👥
        </div>
        <h3 class="text-base font-semibold text-fb-text">Группы не найдены</h3>
        <p class="mt-1 text-sm text-fb-secondary max-w-sm">
          По текущим параметрам поиска и фильтрам группы отсутствуют.
        </p>
        <button
          type="button"
          class="mt-4 rounded-lg bg-fb-blue px-4 py-2 text-xs font-medium text-white hover:bg-fb-blue-dark transition-colors shadow-sm"
          @click="resetSearchAndFilters"
        >
          Сбросить фильтры поиска
        </button>
      </div>

      <!-- Table of Groups -->
      <template v-else>
        <div class="overflow-x-auto">
          <table class="w-full text-sm text-left">
            <thead class="border-b border-fb-line bg-fb-canvas text-xs uppercase tracking-wider font-semibold text-fb-secondary">
              <tr>
                <th class="px-5 py-3.5">Группа</th>
                <th class="px-5 py-3.5">Курс</th>
                <th class="px-5 py-3.5">Преподаватель</th>
                <th class="px-5 py-3.5">Филиал</th>
                <th class="px-5 py-3.5">Дни / Время</th>
                <th class="px-5 py-3.5 text-center">Учеников</th>
                <th class="px-5 py-3.5 text-right">Действие</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-fb-line">
              <tr
                v-for="group in paginatedGroups"
                :key="group.id"
                class="hover:bg-fb-hover/50 transition-colors group cursor-pointer"
                @click="openGroupRoster(group)"
              >
                <!-- Group Name (Clickable) -->
                <td class="px-5 py-3.5 font-medium">
                  <div class="flex items-center gap-2">
                    <span class="text-blue-600 hover:underline font-semibold text-sm group-hover:text-blue-700">
                      {{ group.name }}
                    </span>
                  </div>
                  <div v-if="group.tags && group.tags.length" class="flex flex-wrap gap-1 mt-1">
                    <span
                      v-for="tag in group.tags"
                      :key="tag.id"
                      class="rounded px-1.5 py-0.2 text-[10px] bg-sky-50 text-sky-700 border border-sky-200"
                    >
                      #{{ tag.name }}
                    </span>
                  </div>
                </td>

                <!-- Course -->
                <td class="px-5 py-3.5 text-fb-secondary">
                  <span v-if="group.course" class="font-medium text-fb-text">
                    {{ group.course.name }}
                  </span>
                  <span v-else class="text-fb-secondary/70">—</span>
                </td>

                <!-- Teacher -->
                <td class="px-5 py-3.5 text-fb-secondary">
                  <span v-if="group.teacher" class="font-medium text-fb-text">
                    {{ group.teacher }}
                  </span>
                  <span v-else class="text-fb-secondary/70">—</span>
                </td>

                <!-- Branch -->
                <td class="px-5 py-3.5 text-fb-secondary">
                  {{ group.branch }}
                </td>

                <!-- Days & Time -->
                <td class="px-5 py-3.5 text-fb-secondary">
                  <div class="text-xs">
                    <span class="font-medium text-fb-text">{{ group.days_label }}</span>
                    <span v-if="group.lesson_start_time" class="block text-[11px] text-fb-secondary">
                      {{ group.lesson_start_time }} - {{ group.lesson_end_time || '?' }}
                    </span>
                  </div>
                </td>

                <!-- Students Count -->
                <td class="px-5 py-3.5 text-center">
                  <span class="inline-flex items-center justify-center rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-semibold text-blue-700 border border-blue-200">
                    {{ group.students_count }}
                  </span>
                </td>

                <!-- Action Button -->
                <td class="px-5 py-3.5 text-right" @click.stop>
                  <button
                    type="button"
                    class="inline-flex items-center gap-1.5 rounded-lg bg-fb-blue px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-fb-blue-dark transition-colors"
                    @click="openGroupRoster(group)"
                  >
                    <span>📝</span>
                    <span>Отметить</span>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pagination Bar (50 groups per page) -->
        <div class="flex flex-wrap items-center justify-between border-t border-fb-line px-5 py-3.5 bg-fb-canvas/40 gap-3">
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="rounded-lg border border-fb-line bg-white px-3.5 py-1.5 text-xs font-semibold text-fb-text hover:text-fb-blue hover:border-fb-blue disabled:opacity-40 disabled:hover:text-fb-text disabled:hover:border-fb-line transition-colors shadow-sm"
              :disabled="currentPage <= 1"
              @click="currentPage--"
            >
              ← Назад
            </button>
            <button
              type="button"
              class="rounded-lg border border-fb-line bg-white px-3.5 py-1.5 text-xs font-semibold text-fb-text hover:text-fb-blue hover:border-fb-blue disabled:opacity-40 disabled:hover:text-fb-text disabled:hover:border-fb-line transition-colors shadow-sm"
              :disabled="currentPage >= totalPages"
              @click="currentPage++"
            >
              Вперед →
            </button>
          </div>

          <span class="text-xs text-fb-secondary font-medium">
            Страница <strong class="text-fb-text">{{ currentPage }}</strong> из <strong class="text-fb-text">{{ totalPages }}</strong>
            <span class="ml-1 text-fb-secondary/80">
              (показано {{ paginatedGroups.length }} из {{ filteredGroups.length }} групп, по 50 на стр.)
            </span>
          </span>
        </div>
      </template>
    </div>

    <!-- Group Attendance Roster Modal -->
    <div
      v-if="showModal && activeGroup"
      class="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/50 backdrop-blur-sm overflow-y-auto"
      @click.self="closeModal"
    >
      <div class="relative w-full max-w-3xl rounded-2xl border border-fb-line bg-white shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        <!-- Modal Header -->
        <div class="flex flex-wrap items-center justify-between border-b border-fb-line bg-fb-canvas px-6 py-4 gap-3">
          <div>
            <div class="flex items-center gap-2">
              <h2 class="text-lg font-bold text-fb-text">
                {{ activeGroup.name }}
              </h2>
              <span class="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-800 border border-blue-200">
                {{ groupStudents.length }} учеников
              </span>
            </div>
            <p class="text-xs text-fb-secondary mt-0.5">
              <span v-if="activeGroup.course">{{ activeGroup.course.name }} • </span>
              <span v-if="activeGroup.teacher">{{ activeGroup.teacher }} • </span>
              <span>{{ activeGroup.branch }}</span>
            </p>
          </div>

          <div class="flex items-center gap-3">
            <!-- Inline Date Picker in Modal -->
            <div class="flex items-center gap-2">
              <span class="text-xs font-semibold text-fb-secondary">Дата:</span>
              <input
                v-model="selectedDate"
                type="date"
                class="rounded-lg border border-fb-line bg-white px-2.5 py-1 text-xs font-medium text-fb-text focus:border-fb-blue focus:outline-none"
                @change="onDateChange"
              />
            </div>
            <button
              type="button"
              class="rounded-lg p-1.5 text-fb-secondary hover:bg-fb-hover hover:text-fb-text transition-colors"
              title="Закрыть"
              @click="closeModal"
            >
              <span class="text-lg leading-none">✕</span>
            </button>
          </div>
        </div>

        <!-- Quick Bulk Actions & Counters Bar -->
        <div class="border-b border-fb-line bg-white px-6 py-3 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div class="flex items-center gap-2">
            <span class="font-medium text-fb-secondary">Быстрая отметка:</span>
            <button
              type="button"
              class="rounded-lg bg-emerald-50 border border-emerald-300 text-emerald-800 px-2.5 py-1 font-semibold hover:bg-emerald-100 transition-colors"
              @click="markAll(1)"
            >
              ✓ Все присутствовали
            </button>
            <button
              type="button"
              class="rounded-lg bg-red-50 border border-red-300 text-red-800 px-2.5 py-1 font-semibold hover:bg-red-100 transition-colors"
              @click="markAll(0)"
            >
              ✕ Все отсутствовали
            </button>
          </div>

          <!-- Roster Counters -->
          <div class="flex items-center gap-2">
            <span class="rounded-full bg-emerald-100 text-emerald-800 px-2 py-0.5 font-semibold text-[11px] border border-emerald-200">
              Присутствуют: {{ rosterSummary.present }}
            </span>
            <span class="rounded-full bg-red-100 text-red-800 px-2 py-0.5 font-semibold text-[11px] border border-red-200">
              Отсутствуют: {{ rosterSummary.absent }}
            </span>
            <span class="rounded-full bg-amber-100 text-amber-800 px-2 py-0.5 font-semibold text-[11px] border border-amber-200">
              Опоздали: {{ rosterSummary.late }}
            </span>
          </div>
        </div>

        <!-- Feedback Alert Messages -->
        <div v-if="saveSuccessMessage" class="px-6 pt-3">
          <div class="rounded-xl border border-emerald-300 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800 flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span>✅</span>
              <span>{{ saveSuccessMessage }}</span>
            </div>
            <button type="button" class="text-emerald-700 hover:text-emerald-900" @click="saveSuccessMessage = ''">✕</button>
          </div>
        </div>

        <div v-if="saveErrorMessage" class="px-6 pt-3">
          <div class="rounded-xl border border-red-300 bg-red-50 p-3 text-xs font-semibold text-red-800 flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span>⚠️</span>
              <span>{{ saveErrorMessage }}</span>
            </div>
            <button type="button" class="text-red-700 hover:text-red-900" @click="saveErrorMessage = ''">✕</button>
          </div>
        </div>

        <!-- Modal Body: Student List -->
        <div class="flex-1 overflow-y-auto px-6 py-3">
          <!-- Loading Students -->
          <div v-if="loadingStudents" class="py-16 text-center text-fb-secondary">
            <div class="inline-block h-7 w-7 animate-spin rounded-full border-4 border-solid border-fb-blue border-r-transparent mb-2" />
            <p class="text-sm font-medium">Загрузка списка учеников группы…</p>
          </div>

          <!-- Empty Students State -->
          <div v-else-if="!groupStudents.length" class="py-12 text-center text-fb-secondary">
            <div class="text-3xl mb-2">👤</div>
            <p class="font-semibold text-fb-text text-sm">В этой группе пока нет учеников</p>
            <p class="text-xs text-fb-secondary mt-1">
              Добавьте учеников в группу в разделе «Группы» или переведите лидов в статус «Обучается».
            </p>
          </div>

          <!-- Student Roster Table -->
          <div v-else class="divide-y divide-fb-line">
            <div
              v-for="(student, index) in groupStudents"
              :key="student.id"
              class="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-fb-canvas/50 px-2 rounded-lg transition-colors"
            >
              <!-- Left: Student Info (Full Name, Phone, Status) -->
              <div class="flex items-center gap-3 min-w-0">
                <span class="text-xs font-bold text-fb-secondary/70 w-5 shrink-0">
                  {{ index + 1 }}.
                </span>
                <div class="truncate">
                  <div class="flex items-center gap-2">
                    <span class="font-semibold text-sm text-fb-text">
                      {{ student.full_name }}
                    </span>
                    <span
                      class="rounded-full px-2 py-0.2 text-[10px] font-semibold border"
                      :class="studentStatusPill(student.status)"
                    >
                      {{ student.status_label }}
                    </span>
                  </div>
                  <div v-if="student.phone" class="text-xs text-fb-secondary mt-0.5">
                    📞 {{ student.phone }}
                  </div>
                </div>
              </div>

              <!-- Right: Attendance Dropdown & Optional Note -->
              <div class="flex items-center gap-2 shrink-0 self-end sm:self-center">
                <!-- Status Dropdown -->
                <select
                  v-model="studentStatuses[student.id]"
                  class="rounded-lg border px-3 py-1.5 text-xs font-semibold focus:outline-none focus:ring-1 focus:ring-fb-blue transition-colors cursor-pointer shadow-sm"
                  :class="statusBadgeClass(studentStatuses[student.id])"
                >
                  <option :value="1">Присутствовал</option>
                  <option :value="0">Отсутствовал</option>
                  <option :value="2">Опоздал</option>
                </select>

                <!-- Note input -->
                <input
                  v-model="studentNotes[student.id]"
                  type="text"
                  placeholder="Заметка…"
                  class="w-32 sm:w-40 rounded-lg border border-fb-line px-2.5 py-1.5 text-xs text-fb-text placeholder-fb-secondary/60 focus:border-fb-blue focus:outline-none"
                  title="Заметка к посещаемости"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- Modal Footer with Batch Save Button -->
        <div class="border-t border-fb-line bg-fb-canvas px-6 py-4 flex flex-wrap items-center justify-between gap-3">
          <div class="text-xs text-fb-secondary">
            Дата сохранения: <strong class="text-fb-text">{{ selectedDate }}</strong>
          </div>

          <div class="flex items-center gap-3">
            <button
              type="button"
              class="rounded-lg border border-fb-line bg-white px-4 py-2 text-xs font-semibold text-fb-secondary hover:text-fb-text transition-colors"
              @click="closeModal"
            >
              Отмена
            </button>

            <button
              type="button"
              class="rounded-lg bg-emerald-600 px-5 py-2 text-xs font-bold text-white shadow hover:bg-emerald-700 transition-colors disabled:opacity-50 flex items-center gap-2"
              :disabled="savingAttendance || !groupStudents.length"
              @click="saveGroupAttendance"
            >
              <span v-if="savingAttendance" class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-solid border-white border-r-transparent" />
              <span>💾 Сохранить посещаемость группы</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
