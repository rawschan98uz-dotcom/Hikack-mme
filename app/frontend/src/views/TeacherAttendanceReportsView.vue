<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { groupRoute, teacherRoute } from '../utils/crossLinks';
import { useAuthStore } from '../stores/auth';

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
  { value: 1, label: 'Present' },
  { value: 0, label: 'Absent' },
  { value: 2, label: 'Late' },
] as const;

const router = useRouter();
const authStore = useAuthStore();

const rows = ref<TeacherAttendanceRow[]>([]);
const summary = ref<AttendanceSummary>({ present: 0, absent: 0, late: 0, total: 0 });
const branches = ref<Branch[]>([]);
const groups = ref<GroupOption[]>([]);
const teachers = ref<TeacherOption[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingRecord = ref<TeacherAttendanceRow | null>(null);
const detailRecord = ref<TeacherAttendanceRow | null>(null);

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

const form = reactive({
  teacher_id: '' as number | '',
  group_id: '' as number | '',
  date: new Date().toISOString().slice(0, 10),
  status: 1,
  note: '',
});

const panelTitle = computed(() => {
  if (editingRecord.value) return 'Edit teacher attendance';
  if (detailRecord.value) return 'Attendance details';
  return 'Mark teacher attendance';
});

const isReadOnly = computed(() => Boolean(detailRecord.value && !editingRecord.value));
const isAdmin = computed(() => authStore.isCeo || authStore.role === 'admin' || authStore.role === 'manager');

const filterGroups = computed(() => {
  if (!filters.branch_id) return groups.value;
  return groups.value.filter((g) => String(g.branch_id) === filters.branch_id);
});

const formGroups = computed(() => {
  if (isAdmin.value) return groups.value;
  if (!form.teacher_id) return [];
  const filtered = groups.value.filter((g) => g.teacher_id === Number(form.teacher_id));
  return filtered.length ? filtered : groups.value;
});

const teacherHasNoGroups = computed(() => {
  if (!form.teacher_id || isAdmin.value) return false;
  return !groups.value.some((g) => g.teacher_id === Number(form.teacher_id));
});

watch(
  () => form.teacher_id,
  (newTeacherId) => {
    if (newTeacherId && !editingRecord.value) {
      const teacherGroups = groups.value.filter((g) => g.teacher_id === Number(newTeacherId));
      if (teacherGroups.length) {
        form.group_id = teacherGroups[0].id;
      }
    }
  },
);

function statusClass(status: number) {
  if (status === 1) return 'bg-emerald-50 text-emerald-700';
  if (status === 0) return 'bg-red-50 text-fb-danger';
  return 'bg-amber-50 text-amber-700';
}

function resetForm() {
  form.teacher_id = '';
  form.group_id = '';
  form.date = new Date().toISOString().slice(0, 10);
  form.status = 1;
  form.note = '';
  formError.value = '';
  editingRecord.value = null;
  detailRecord.value = null;
}

function fillForm(record: TeacherAttendanceRow) {
  form.teacher_id = record.teacher_id;
  form.group_id = record.group_id;
  form.date = record.date;
  form.status = record.status;
  form.note = record.note;
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
  const params: Record<string, string> = { export: '1' };
  if (filters.branch_id) params.branch_id = filters.branch_id;
  if (filters.group_id) params.group_id = filters.group_id;
  if (filters.teacher_id) params.teacher_id = filters.teacher_id;
  if (filters.status !== '') params.status = filters.status;
  if (filters.date_from) params.date_from = filters.date_from;
  if (filters.date_to) params.date_to = filters.date_to;
  if (filters.q.trim()) params.q = filters.q.trim();

  try {
    const { data } = await client.get<ApiEnvelope<AttendancePayload>>('/reports/teacher-attendance', { params });
    const csvRows = [
      ['Teacher', 'Group', 'Branch', 'Date', 'Status', 'Note']
    ];
    for (const row of data.data.rows) {
      csvRows.push([
        `"${row.teacher}"`,
        `"${row.group}"`,
        `"${row.branch}"`,
        `"${row.date}"`,
        `"${row.status_label}"`,
        `"${row.note || ''}"`
      ]);
    }
    const csvContent = "data:text/csv;charset=utf-8,\uFEFF" + csvRows.map(e => e.join(",")).join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "teacher_attendance.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } catch (err) {
    console.error(err);
    alert('Export failed');
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

function openCreatePanel() {
  resetForm();
  showPanel.value = true;
}

async function openDetailPanel(recordId: number) {
  resetForm();
  showPanel.value = true;
  panelLoading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<TeacherAttendanceRow>>(
      `/reports/teacher-attendance/${recordId}`,
    );
    detailRecord.value = data.data;
    fillForm(data.data);
  } finally {
    panelLoading.value = false;
  }
}

function startEdit() {
  if (!detailRecord.value) return;
  editingRecord.value = detailRecord.value;
}

function closePanel() {
  showPanel.value = false;
  resetForm();
}

async function submitRecord() {
  formError.value = '';
  if (!form.teacher_id || !form.group_id || !form.date) {
    formError.value = 'Fill in teacher, group and date';
    return;
  }

  saving.value = true;
  try {
    const payload = {
      teacher_id: form.teacher_id,
      group_id: form.group_id,
      date: form.date,
      status: form.status,
      note: form.note.trim(),
    };
    if (editingRecord.value) {
      await client.patch(`/reports/teacher-attendance/${editingRecord.value.id}`, payload);
    } else {
      await client.post('/reports/teacher-attendance', payload);
    }
    closePanel();
    await loadReport();
  } catch (err: any) {
    formError.value =
      err.response?.data?.message ||
      err.response?.data?.error ||
      (editingRecord.value ? 'Could not update record' : 'Could not create record');
  } finally {
    saving.value = false;
  }
}

async function deleteRecord() {
  if (!detailRecord.value) return;
  if (!window.confirm(`Delete attendance for ${detailRecord.value.teacher}?`)) return;

  deleting.value = true;
  try {
    await client.delete(`/reports/teacher-attendance/${detailRecord.value.id}`);
    closePanel();
    await loadReport();
  } catch {
    window.alert('Could not delete record');
  } finally {
    deleting.value = false;
  }
}

function goTeachers() {
  const id = detailRecord.value?.teacher_id;
  router.push(id ? teacherRoute(id) : '/teachers');
}

function goGroups() {
  const id = detailRecord.value?.group_id;
  router.push(id ? groupRoute(id) : '/groups');
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
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-fb-text">Teacher attendance reports</h1>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
          @click="exportCsv"
        >
          Export CSV
        </button>
        <button
          type="button"
          class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:bg-fb-blue-dark"
          @click="openCreatePanel"
        >
          + Mark attendance
        </button>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div class="rounded-xl border border-fb-line bg-fb-card p-4">
        <p class="text-sm text-fb-secondary">Total</p>
        <p class="mt-1 text-2xl font-bold text-fb-text">{{ summary.total }}</p>
      </div>
      <div class="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4">
        <p class="text-sm text-emerald-700">Present</p>
        <p class="mt-1 text-2xl font-bold text-emerald-800">{{ summary.present }}</p>
      </div>
      <div class="rounded-xl border border-red-200 bg-red-50/50 p-4">
        <p class="text-sm text-red-700">Absent</p>
        <p class="mt-1 text-2xl font-bold text-red-800">{{ summary.absent }}</p>
      </div>
      <div class="rounded-xl border border-amber-200 bg-amber-50/50 p-4">
        <p class="text-sm text-amber-700">Late</p>
        <p class="mt-1 text-2xl font-bold text-amber-800">{{ summary.late }}</p>
      </div>
    </div>

    <div>
      <input
        v-model="filters.q"
        type="search"
        placeholder="Search teacher by name..."
        class="w-full rounded-xl border border-fb-line bg-fb-card px-4 py-3 text-sm focus:border-fb-blue focus:outline-none focus:ring-1 focus:ring-fb-blue"
        @keydown.enter="applyFilters"
      />
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Branch</label>
        <select v-model="filters.branch_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option value="">All</option>
          <option v-for="branch in branches" :key="branch.id" :value="String(branch.id)">
            {{ branch.name }}
          </option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Group</label>
        <select v-model="filters.group_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option value="">All</option>
          <option v-for="group in filterGroups" :key="group.id" :value="String(group.id)">
            {{ group.name }}
          </option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Teacher</label>
        <select v-model="filters.teacher_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option value="">All</option>
          <option v-for="teacher in teachers" :key="teacher.id" :value="String(teacher.id)">
            {{ teacher.name }}
          </option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Status</label>
        <select v-model="filters.status" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option value="">All</option>
          <option v-for="option in STATUS_OPTIONS" :key="option.value" :value="String(option.value)">
            {{ option.label }}
          </option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">From</label>
        <input v-model="filters.date_from" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">To</label>
        <input v-model="filters.date_to" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div class="flex-1"></div>
      <button
        type="button"
        class="rounded-lg border border-fb-line px-4 py-2 text-sm text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
        @click="applyFilters"
      >
        Apply
      </button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!rows.length" class="p-8 text-center text-fb-icon">No teacher attendance records</div>
      <template v-else>
        <table class="w-full text-base">
          <thead class="border-b border-fb-line bg-fb-canvas">
            <tr>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Teacher</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Group</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Branch</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Date</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Status</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Note</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.id"
              class="cursor-pointer border-b border-fb-line hover:bg-fb-hover/40"
              @click="openDetailPanel(row.id)"
            >
              <td class="px-5 py-4 font-medium text-fb-text">{{ row.teacher }}</td>
              <td class="px-5 py-4 text-fb-secondary">{{ row.group }}</td>
              <td class="px-5 py-4 text-fb-secondary">{{ row.branch }}</td>
              <td class="px-5 py-4 text-fb-secondary">{{ row.date }}</td>
              <td class="px-5 py-4">
                <span class="rounded-full px-2 py-0.5 text-xs" :class="statusClass(row.status)">
                  {{ row.status_label }}
                </span>
              </td>
              <td class="px-5 py-4 text-fb-secondary">{{ row.note || '—' }}</td>
            </tr>
          </tbody>
        </table>
        
        <div class="flex items-center justify-between border-t border-fb-line px-5 py-4">
          <button
            type="button"
            class="rounded-lg border border-fb-line px-4 py-2 text-sm text-fb-secondary hover:text-fb-blue disabled:opacity-50"
            :disabled="currentPage <= 1"
            @click="changePage(-1)"
          >
            Previous
          </button>
          <span class="text-sm text-fb-secondary">
            Page {{ currentPage }} of {{ totalPages }}
          </span>
          <button
            type="button"
            class="rounded-lg border border-fb-line px-4 py-2 text-sm text-fb-secondary hover:text-fb-blue disabled:opacity-50"
            :disabled="currentPage >= totalPages"
            @click="changePage(1)"
          >
            Next
          </button>
        </div>
      </template>
    </div>

    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closePanel" />
      <div class="drawer-panel-fb max-w-lg">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-4">
          <h2 class="text-lg font-semibold text-fb-text">{{ panelTitle }}</h2>
          <button type="button" class="text-fb-icon hover:text-fb-secondary" @click="closePanel">✕</button>
        </div>

        <div v-if="panelLoading" class="flex-1 p-6 text-fb-secondary">Loading…</div>

        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitRecord">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Teacher</label>
              <select
                v-model="form.teacher_id"
                :disabled="isReadOnly || Boolean(editingRecord)"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option value="">Select teacher</option>
                <option v-for="teacher in teachers" :key="teacher.id" :value="teacher.id">
                  {{ teacher.name }}
                </option>
              </select>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Group</label>
              <select
                v-model="form.group_id"
                :disabled="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option value="">Select group</option>
                <option v-for="group in formGroups" :key="group.id" :value="group.id">
                  {{ group.name }}
                </option>
              </select>
              <p v-if="teacherHasNoGroups" class="mt-1 text-xs text-amber-600">
                Notice: This teacher has no groups assigned yet.
              </p>
              <p v-if="!isAdmin && !form.teacher_id" class="mt-1 text-xs text-amber-600">
                Please select a teacher first.
              </p>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Date</label>
              <input
                v-model="form.date"
                type="date"
                required
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas"
              />
            </div>

            <div v-if="isAdmin">
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Status</label>
              <select
                v-model="form.status"
                :disabled="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option v-for="option in STATUS_OPTIONS" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </div>
            
            <div v-else>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Status</label>
              <div class="rounded-lg border border-fb-line bg-fb-canvas px-3 py-2 text-sm text-fb-secondary">
                Auto-calculated (5 min threshold)
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Note</label>
              <textarea
                v-model="form.note"
                rows="3"
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas"
              />
            </div>

            <div
              v-if="detailRecord"
              class="rounded-lg border border-fb-line bg-fb-canvas px-4 py-3 text-sm"
            >
              <button type="button" class="text-fb-blue hover:underline" @click="goTeachers">
                Teachers →
              </button>
              <button type="button" class="ml-3 text-fb-blue hover:underline" @click="goGroups">
                Groups →
              </button>
            </div>

            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>

          <div class="flex flex-wrap gap-2 border-t border-fb-line px-6 py-4">
            <template v-if="isReadOnly && detailRecord">
              <button
                type="button"
                class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white hover:opacity-90"
                @click="startEdit"
              >
                Edit
              </button>
              <button
                type="button"
                class="rounded-lg border border-red-300 px-5 py-2 text-sm font-medium text-fb-danger hover:bg-red-50 disabled:opacity-50"
                :disabled="deleting"
                @click="deleteRecord"
              >
                Delete
              </button>
            </template>
            <template v-else>
              <button
                type="submit"
                class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                :disabled="saving"
              >
                {{ saving ? 'Saving…' : editingRecord ? 'Save' : 'Create' }}
              </button>
            </template>
            <button
              type="button"
              class="rounded-lg border border-fb-line px-5 py-2 text-sm font-medium text-fb-secondary"
              @click="closePanel"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
