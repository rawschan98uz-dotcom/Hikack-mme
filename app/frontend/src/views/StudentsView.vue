<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';
import { downloadCsv } from '../utils/csvExport';
import {
  groupRoute,
  hasCreateFlag,
  parseOpenId,
  routeWithoutCreate,
  routeWithoutOpen,
} from '../utils/crossLinks';

interface Branch {
  id: number;
  name: string;
}

interface GroupOption {
  id: number;
  name: string;
  branch_id: number;
}

interface StudentRow {
  id: number;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  status: number;
  status_label: string;
  balance: number;
  paid_this_month: boolean;
  branch_id: number;
  branch: string;
  group_id: number | null;
  group: string | null;
  created_at: string;
}

const STATUS_OPTIONS = [
  { value: 1, label: 'Trial' },
  { value: 5, label: 'Active' },
  { value: 6, label: 'Debtor' },
  { value: 7, label: 'Left after trial' },
  { value: 8, label: 'Left active group' },
] as const;

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const rows = ref<StudentRow[]>([]);
const branches = ref<Branch[]>([]);
const groups = ref<GroupOption[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingStudent = ref<StudentRow | null>(null);
const detailStudent = ref<StudentRow | null>(null);

const filters = reactive({
  branch_id: '',
  group_id: '',
  status: '',
  q: '',
});

const form = reactive({
  first_name: '',
  last_name: '',
  phone: '',
  status: 1,
  balance: 0,
  paid_this_month: false,
  branch_id: 0,
  group_id: '' as number | '',
});

const title = computed(() => {
  if (route.path.includes('debtors')) return 'Debtors';
  if (route.query.finance === 'paid_during_the_month') return 'Paid during the month';
  if (route.query.statuses === '1') return 'Trial students';
  if (route.query.statuses === '5') return 'Active students';
  if (route.query.statuses === '8') return 'Left active group';
  if (route.query.statuses === '7') return 'Left after trial period';
  if (route.query.q) return `Students — search “${route.query.q}”`;
  return 'Students';
});

const panelTitle = computed(() => {
  if (editingStudent.value) return 'Edit student';
  if (detailStudent.value) return 'Student details';
  return 'Add student';
});

const isReadOnly = computed(() => Boolean(detailStudent.value && !editingStudent.value));
const canExportStudents = computed(() => auth.can(PERM.STUDENTS_VIEW));

function exportCsv() {
  downloadCsv(
    'students.csv',
    ['Name', 'Phone', 'Status', 'Group', 'Branch', 'Balance'],
    rows.value.map((row) => [
      row.full_name,
      row.phone,
      row.status_label,
      row.group ?? '',
      row.branch,
      row.balance,
    ]),
  );
}

const filteredGroups = computed(() => {
  if (!form.branch_id) return groups.value;
  return groups.value.filter((group) => group.branch_id === form.branch_id);
});

const tableRows = computed(() =>
  rows.value.map((row) => ({
    id: row.id,
    full_name: row.full_name,
    phone: row.phone,
    statusText: row.status_label,
    group: row.group ?? '—',
    group_id: row.group_id,
    branch: row.branch,
    balance: row.balance.toLocaleString(),
    paidText: row.paid_this_month ? 'Yes' : 'No',
  })),
);

function syncFiltersFromRoute() {
  filters.branch_id = String(route.query.branch_id ?? '');
  filters.group_id = String(route.query.group_id ?? '');
  filters.q = String(route.query.q ?? '');

  if (route.path.includes('debtors')) {
    filters.status = '6';
  } else if (route.query.statuses) {
    filters.status = String(route.query.statuses);
  } else if (route.query.finance === 'paid_during_the_month') {
    filters.status = '';
  } else {
    filters.status = filters.status || '';
  }
}

function resetForm() {
  form.first_name = '';
  form.last_name = '';
  form.phone = '';
  form.status = 1;
  form.balance = 0;
  form.paid_this_month = false;
  form.branch_id = branches.value[0]?.id ?? 0;
  form.group_id = '';
  formError.value = '';
  editingStudent.value = null;
  detailStudent.value = null;
}

function fillForm(student: StudentRow) {
  form.first_name = student.first_name;
  form.last_name = student.last_name;
  form.phone = student.phone;
  form.status = student.status;
  form.balance = student.balance;
  form.paid_this_month = student.paid_this_month;
  form.branch_id = student.branch_id;
  form.group_id = student.group_id ?? '';
}

function openCreatePanel() {
  resetForm();
  showPanel.value = true;
}

async function openDetailPanel(studentId: number) {
  resetForm();
  showPanel.value = true;
  panelLoading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<StudentRow>>(`/students/${studentId}`);
    detailStudent.value = data.data;
    fillForm(data.data);
  } finally {
    panelLoading.value = false;
  }
}

function startEdit() {
  if (!detailStudent.value) return;
  editingStudent.value = detailStudent.value;
}

function closePanel() {
  showPanel.value = false;
  resetForm();
  if (route.query.open) {
    router.replace(routeWithoutOpen(route));
  }
}

async function loadOptions() {
  const [branchRes, groupRes] = await Promise.all([
    client.get<ApiEnvelope<Branch[]>>('/branch'),
    client.get<ApiEnvelope<GroupOption[]>>('/groups'),
  ]);
  branches.value = branchRes.data.data;
  groups.value = groupRes.data.data.map((group) => ({
    id: group.id,
    name: group.name,
    branch_id: group.branch_id,
  }));
  if (!form.branch_id && branches.value.length) {
    form.branch_id = branches.value[0].id;
  }
}

async function loadStudents() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.branch_id) params.branch_id = filters.branch_id;
    if (filters.group_id) params.group_id = filters.group_id;
    if (filters.status) params.statuses = filters.status;
    if (filters.q.trim()) params.q = filters.q.trim();
    if (route.query.finance) params.finance = String(route.query.finance);

    const { data } = await client.get<ApiEnvelope<StudentRow[]>>('/students', { params });
    rows.value = data.data;
  } finally {
    loading.value = false;
  }
}

function buildPayload() {
  return {
    first_name: form.first_name.trim(),
    last_name: form.last_name.trim(),
    phone: form.phone.trim(),
    status: form.status,
    balance: form.balance,
    paid_this_month: form.paid_this_month,
    branch_id: form.branch_id,
    group_id: form.group_id === '' ? null : form.group_id,
  };
}

async function submitStudent() {
  formError.value = '';
  if (!form.first_name.trim()) {
    formError.value = 'Enter first name';
    return;
  }
  if (!form.phone.trim()) {
    formError.value = 'Enter phone number';
    return;
  }
  if (!form.branch_id) {
    formError.value = 'Select a branch';
    return;
  }

  saving.value = true;
  try {
    const payload = buildPayload();
    if (editingStudent.value) {
      await client.patch(`/students/${editingStudent.value.id}`, payload);
    } else {
      await client.post('/students', payload);
    }
    closePanel();
    await loadStudents();
  } catch {
    formError.value = editingStudent.value
      ? 'Could not update student'
      : 'Could not create student';
  } finally {
    saving.value = false;
  }
}

async function deleteStudent() {
  if (!detailStudent.value) return;
  if (!window.confirm(`Delete ${detailStudent.value.full_name}?`)) return;

  deleting.value = true;
  try {
    await client.delete(`/students/${detailStudent.value.id}`);
    closePanel();
    await loadStudents();
  } catch {
    window.alert('Could not delete student');
  } finally {
    deleting.value = false;
  }
}

function goGroup(student: StudentRow | { group_id: number | null }) {
  if (!student.group_id) return;
  router.push(groupRoute(student.group_id));
}

async function maybeOpenFromRoute() {
  const id = parseOpenId(route.query);
  if (id == null || showPanel.value) return;
  await openDetailPanel(id);
}

function maybeCreateFromRoute() {
  if (!hasCreateFlag(route.query) || showPanel.value) return;
  openCreatePanel();
  router.replace(routeWithoutCreate(route));
}

function goGroupFromTable(groupId: number) {
  router.push(groupRoute(groupId));
}

function applyFilters() {
  const query: Record<string, string> = {};
  if (filters.branch_id) query.branch_id = filters.branch_id;
  if (filters.group_id) query.group_id = filters.group_id;
  if (filters.status) query.statuses = filters.status;
  if (filters.q.trim()) query.q = filters.q.trim();

  const basePath = route.path.includes('debtors') ? '/students/debtors' : '/students';
  router.push({ path: basePath, query });
}

watch(
  () => route.fullPath,
  async () => {
    syncFiltersFromRoute();
    await loadStudents();
    await maybeOpenFromRoute();
    maybeCreateFromRoute();
  },
);

onMounted(async () => {
  syncFiltersFromRoute();
  try {
    await Promise.all([loadOptions(), loadStudents()]);
    await maybeOpenFromRoute();
    maybeCreateFromRoute();
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-fb-text">{{ title }}</h1>
      <div class="flex flex-wrap gap-2">
        <button
          v-if="canExportStudents"
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
          @click="exportCsv"
        >
          Export
        </button>
        <button
          type="button"
          class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:bg-fb-blue-dark"
          @click="openCreatePanel"
        >
          + Add student
        </button>
      </div>
    </div>

    <div
      v-if="!route.path.includes('debtors') && route.query.finance !== 'paid_during_the_month'"
      class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4"
    >
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Branch</label>
        <select
          v-model="filters.branch_id"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm"
        >
          <option value="">All branches</option>
          <option v-for="branch in branches" :key="branch.id" :value="String(branch.id)">
            {{ branch.name }}
          </option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Group</label>
        <select
          v-model="filters.group_id"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm"
        >
          <option value="">All groups</option>
          <option v-for="group in groups" :key="group.id" :value="String(group.id)">
            {{ group.name }}
          </option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Status</label>
        <select
          v-model="filters.status"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          <option v-for="option in STATUS_OPTIONS" :key="option.value" :value="String(option.value)">
            {{ option.label }}
          </option>
        </select>
      </div>
      <div class="min-w-[220px] flex-1">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Search</label>
        <input
          v-model="filters.q"
          type="search"
          placeholder="Name or phone"
          class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm"
          @keydown.enter="applyFilters"
        />
      </div>
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
      <div v-else-if="!tableRows.length" class="p-8 text-center text-fb-icon">No students</div>
      <table v-else class="w-full text-base">
        <thead class="border-b border-fb-line bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Name</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Phone</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Status</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Group</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Branch</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Balance</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Paid this month</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in tableRows"
            :key="row.id"
            class="cursor-pointer border-b border-fb-line hover:bg-fb-hover/40"
            @click="openDetailPanel(row.id)"
          >
            <td class="px-5 py-4 font-medium text-fb-text">{{ row.full_name }}</td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.phone }}</td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.statusText }}</td>
            <td class="px-5 py-4 text-fb-secondary">
              <button
                v-if="row.group_id"
                type="button"
                class="text-fb-blue hover:underline"
                @click.stop="goGroupFromTable(row.group_id)"
              >
                {{ row.group }}
              </button>
              <span v-else>{{ row.group }}</span>
            </td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.branch }}</td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.balance }}</td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.paidText }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closePanel" />
      <div class="drawer-panel-fb max-w-lg">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-4">
          <h2 class="text-lg font-semibold text-fb-text">{{ panelTitle }}</h2>
          <button type="button" class="text-fb-icon hover:text-fb-secondary" @click="closePanel">✕</button>
        </div>

        <div v-if="panelLoading" class="flex-1 p-6 text-fb-secondary">Loading…</div>

        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitStudent">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">First name</label>
                <input
                  v-model="form.first_name"
                  type="text"
                  required
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">Last name</label>
                <input
                  v-model="form.last_name"
                  type="text"
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Phone</label>
              <input
                v-model="form.phone"
                type="tel"
                required
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Branch</label>
              <select
                v-model="form.branch_id"
                :disabled="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option v-for="branch in branches" :key="branch.id" :value="branch.id">
                  {{ branch.name }}
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
                <option value="">— No group —</option>
                <option v-for="group in filteredGroups" :key="group.id" :value="group.id">
                  {{ group.name }}
                </option>
              </select>
            </div>

            <div>
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

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">Balance</label>
                <input
                  v-model.number="form.balance"
                  type="number"
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas"
                />
              </div>
              <div class="flex items-end pb-2">
                <label class="flex items-center gap-2 text-sm text-fb-secondary">
                  <input
                    v-model="form.paid_this_month"
                    type="checkbox"
                    :disabled="isReadOnly"
                  />
                  Paid this month
                </label>
              </div>
            </div>

            <div
              v-if="detailStudent?.group_id"
              class="rounded-lg border border-fb-line bg-fb-canvas px-4 py-3 text-sm"
            >
              <span class="text-fb-secondary">Group: </span>
              <span class="font-medium text-fb-text">{{ detailStudent.group }}</span>
              <button
                type="button"
                class="ml-3 text-fb-blue hover:underline"
                @click="goGroup(detailStudent)"
              >
                Open groups →
              </button>
            </div>

            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>

          <div class="flex flex-wrap gap-2 border-t border-fb-line px-6 py-4">
            <template v-if="isReadOnly">
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
                @click="deleteStudent"
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
                {{ saving ? 'Saving…' : editingStudent ? 'Save' : 'Create' }}
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
