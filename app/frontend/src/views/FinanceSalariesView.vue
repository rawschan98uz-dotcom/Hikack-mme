<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface SalaryRow {
  id: number;
  calc_setting: string;
  salary_type: string;
  salary_type_label: string;
  amount: number;
  teacher_name: string;
  teacher: string;
  course_name: string;
  course: string;
  group_name: string;
  group: string;
  created_by: string;
  updated_by: string;
}

const SALARY_TYPES = [
  { value: 'fixed', label: 'Fixed' },
  { value: 'percent', label: 'Percent' },
  { value: 'per_student', label: 'Per student' },
] as const;

const rows = ref<SalaryRow[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingRow = ref<SalaryRow | null>(null);
const detailRow = ref<SalaryRow | null>(null);
const filters = reactive({ q: '' });
const form = reactive({
  teacher_name: '',
  salary_type: 'fixed' as (typeof SALARY_TYPES)[number]['value'],
  amount: 0,
  course_name: '',
  group_name: '',
});

const isReadOnly = computed(() => Boolean(detailRow.value && !editingRow.value));
const panelTitle = computed(() =>
  editingRow.value ? 'Edit salary setting' : detailRow.value ? 'Salary details' : 'Add salary setting',
);
const tableRows = computed(() =>
  rows.value.map((r) => ({
    id: r.id,
    calc_setting: r.calc_setting,
    salary_type: r.salary_type_label,
    amount: r.amount.toLocaleString(),
    course: r.course,
    group: r.group,
    teacher: r.teacher,
    created_by: r.created_by,
  })),
);

function resetForm() {
  form.teacher_name = '';
  form.salary_type = 'fixed';
  form.amount = 0;
  form.course_name = '';
  form.group_name = '';
  formError.value = '';
  editingRow.value = null;
  detailRow.value = null;
}

function fillForm(row: SalaryRow) {
  form.teacher_name = row.teacher_name;
  form.salary_type = row.salary_type as (typeof SALARY_TYPES)[number]['value'];
  form.amount = row.amount;
  form.course_name = row.course_name;
  form.group_name = row.group_name;
}

async function loadRows() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.q.trim()) params.q = filters.q.trim();
    const { data } = await client.get<ApiEnvelope<SalaryRow[]>>('/salary-settings', { params });
    rows.value = data.data;
  } finally {
    loading.value = false;
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
    const { data } = await client.get<ApiEnvelope<SalaryRow>>(`/salary-settings/${id}`);
    detailRow.value = data.data;
    fillForm(data.data);
  } finally {
    panelLoading.value = false;
  }
}

function startEdit() {
  if (detailRow.value) editingRow.value = detailRow.value;
}

function closePanel() {
  showPanel.value = false;
  resetForm();
}

async function submitForm() {
  formError.value = '';
  if (!form.amount && form.salary_type === 'fixed') {
    formError.value = 'Enter amount';
    return;
  }
  saving.value = true;
  try {
    const payload = {
      teacher_name: form.teacher_name.trim(),
      salary_type: form.salary_type,
      amount: form.amount,
      course_name: form.course_name.trim(),
      group_name: form.group_name.trim(),
    };
    if (editingRow.value) {
      await client.patch(`/salary-settings/${editingRow.value.id}`, payload);
    } else {
      await client.post('/salary-settings', payload);
    }
    closePanel();
    await loadRows();
  } catch {
    formError.value = 'Could not save';
  } finally {
    saving.value = false;
  }
}

async function deleteRow() {
  if (!detailRow.value || !window.confirm('Delete this salary setting?')) return;
  deleting.value = true;
  try {
    await client.delete(`/salary-settings/${detailRow.value.id}`);
    closePanel();
    await loadRows();
  } finally {
    deleting.value = false;
  }
}

onMounted(loadRows);
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-fb-text">Salaries</h1>
      <button type="button" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" @click="openCreate">
        + Add setting
      </button>
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div class="min-w-[220px] flex-1">
        <label class="mb-1 block text-xs text-fb-secondary">Search teacher / course / group</label>
        <input v-model="filters.q" type="search" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm" @keydown.enter="loadRows" />
      </div>
      <button type="button" class="rounded-lg border border-fb-line px-4 py-2 text-sm" @click="loadRows">Apply</button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!tableRows.length" class="p-8 text-center text-fb-icon">No salary settings</div>
      <table v-else class="w-full text-base">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Calc setting</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Salary type</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Amount</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Course</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Group</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Teacher</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Created by</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in tableRows" :key="row.id" class="cursor-pointer border-b hover:bg-fb-hover/40" @click="openDetail(row.id)">
            <td class="px-5 py-4">{{ row.calc_setting }}</td>
            <td class="px-5 py-4">{{ row.salary_type }}</td>
            <td class="px-5 py-4 font-semibold text-fb-blue">{{ row.amount }}</td>
            <td class="px-5 py-4">{{ row.course }}</td>
            <td class="px-5 py-4">{{ row.group }}</td>
            <td class="px-5 py-4">{{ row.teacher }}</td>
            <td class="px-5 py-4">{{ row.created_by }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closePanel" />
      <div class="drawer-panel-fb max-w-lg">
        <div class="flex items-center justify-between border-b px-6 py-4">
          <h2 class="text-lg font-semibold">{{ panelTitle }}</h2>
          <button type="button" @click="closePanel">✕</button>
        </div>
        <div v-if="panelLoading" class="p-6 text-fb-secondary">Loading…</div>
        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitForm">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <div>
              <label class="mb-1 block text-sm font-medium">Teacher</label>
              <input v-model="form.teacher_name" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Salary type</label>
              <select v-model="form.salary_type" :disabled="isReadOnly" class="w-full rounded-lg border px-3 py-2">
                <option v-for="t in SALARY_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Amount</label>
              <input v-model.number="form.amount" type="number" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Course</label>
              <input v-model="form.course_name" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Group</label>
              <input v-model="form.group_name" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>
          <div class="flex gap-2 border-t px-6 py-4">
            <template v-if="isReadOnly && detailRow">
              <button type="button" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" @click="startEdit">Edit</button>
              <button type="button" class="rounded-lg border border-red-300 px-5 py-2 text-sm text-fb-danger" :disabled="deleting" @click="deleteRow">Delete</button>
            </template>
            <button v-else type="submit" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" :disabled="saving">
              {{ saving ? 'Saving…' : editingRow ? 'Save' : 'Create' }}
            </button>
            <button type="button" class="rounded-lg border px-5 py-2 text-sm" @click="closePanel">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
