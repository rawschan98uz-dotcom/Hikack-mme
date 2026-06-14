<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

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
}

const STATUS_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'at_work', label: 'At work' },
  { value: 'late_in', label: 'Late in' },
  { value: 'absent', label: 'Absent' },
] as const;

const FORM_STATUSES = STATUS_OPTIONS.filter((s) => s.value !== '');

const rows = ref<WorklyRow[]>([]);
const summary = ref<Summary>({ at_work: 0, late_in: 0, absent: 0, total: 0 });
const staffList = ref<StaffOption[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingRecord = ref<WorklyRow | null>(null);
const detailRecord = ref<WorklyRow | null>(null);

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
  if (editingRecord.value) return 'Edit work record';
  if (detailRecord.value) return 'Work record details';
  return 'Add work record';
});

function statusClass(status: string) {
  if (status === 'at_work') return 'bg-emerald-50 text-emerald-700';
  if (status === 'late_in') return 'bg-amber-50 text-amber-700';
  return 'bg-red-50 text-fb-danger';
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

async function loadRows() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.status) params.status = filters.status;
    if (filters.staff_id) params.staff_id = filters.staff_id;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();
    const { data } = await client.get<ApiEnvelope<Payload>>('/reports/workly', { params });
    summary.value = data.data.summary;
    rows.value = data.data.rows;
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
    formError.value = 'Select staff member';
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
    formError.value = 'Could not save record';
  } finally {
    saving.value = false;
  }
}

async function deleteRecord() {
  if (!detailRecord.value || !window.confirm('Delete this record?')) return;
  deleting.value = true;
  try {
    await client.delete(`/reports/workly/${detailRecord.value.id}`);
    closePanel();
    await loadRows();
  } finally {
    deleting.value = false;
  }
}

function setTab(status: string) {
  filters.status = status;
  loadRows();
}

onMounted(async () => {
  await loadStaff();
  await loadRows();
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-fb-text">Workly Report</h1>
      <button type="button" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" @click="openCreate">
        + Add record
      </button>
    </div>

    <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
      <div class="rounded-xl border border-fb-line bg-fb-card p-4 text-center">
        <div class="text-2xl font-bold text-fb-text">{{ summary.total }}</div>
        <div class="mt-1 text-sm text-fb-secondary">Total</div>
      </div>
      <div class="rounded-xl border border-fb-line bg-fb-card p-4 text-center">
        <div class="text-2xl font-bold text-emerald-600">{{ summary.at_work }}</div>
        <div class="mt-1 text-sm text-fb-secondary">At work</div>
      </div>
      <div class="rounded-xl border border-fb-line bg-fb-card p-4 text-center">
        <div class="text-2xl font-bold text-amber-600">{{ summary.late_in }}</div>
        <div class="mt-1 text-sm text-fb-secondary">Late in</div>
      </div>
      <div class="rounded-xl border border-fb-line bg-fb-card p-4 text-center">
        <div class="text-2xl font-bold text-fb-danger">{{ summary.absent }}</div>
        <div class="mt-1 text-sm text-fb-secondary">Absent</div>
      </div>
    </div>

    <div class="flex flex-wrap gap-2">
      <button
        v-for="tab in STATUS_OPTIONS"
        :key="tab.value || 'all'"
        type="button"
        class="rounded-lg px-4 py-2 text-sm"
        :class="filters.status === tab.value ? 'bg-fb-blue text-white' : 'border border-fb-line bg-fb-card'"
        @click="setTab(tab.value)"
      >
        {{ tab.label }}
      </button>
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">Staff</label>
        <select v-model="filters.staff_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option value="">All</option>
          <option v-for="s in staffList" :key="s.id" :value="String(s.id)">{{ s.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">From</label>
        <input v-model="filters.date_from" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">To</label>
        <input v-model="filters.date_to" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div class="min-w-[180px] flex-1">
        <label class="mb-1 block text-xs text-fb-secondary">Search</label>
        <input v-model="filters.q" type="search" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm" @keydown.enter="loadRows" />
      </div>
      <button type="button" class="rounded-lg border border-fb-line px-4 py-2 text-sm" @click="loadRows">Apply</button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!rows.length" class="p-8 text-center text-fb-icon">No records</div>
      <table v-else class="w-full text-base">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Staff</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Role</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Date</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Clock in</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Clock out</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Status</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Note</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            class="cursor-pointer border-b hover:bg-fb-hover/40"
            @click="openDetail(row.id)"
          >
            <td class="px-5 py-4">{{ row.staff }}</td>
            <td class="px-5 py-4">{{ row.job_title }}</td>
            <td class="px-5 py-4">{{ row.work_date }}</td>
            <td class="px-5 py-4">{{ row.clock_in || '—' }}</td>
            <td class="px-5 py-4">{{ row.clock_out || '—' }}</td>
            <td class="px-5 py-4">
              <span class="rounded-full px-2 py-1 text-xs font-medium" :class="statusClass(row.status)">
                {{ row.status_label }}
              </span>
            </td>
            <td class="px-5 py-4">{{ row.note || '—' }}</td>
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
              <label class="mb-1 block text-sm font-medium">Staff</label>
              <select v-model="form.staff_id" :disabled="isReadOnly || Boolean(editingRecord)" class="w-full rounded-lg border px-3 py-2">
                <option v-for="s in staffList" :key="s.id" :value="s.id">{{ s.name }} — {{ s.job_title }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Date</label>
              <input v-model="form.work_date" type="date" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-sm font-medium">Clock in</label>
                <input v-model="form.clock_in" type="time" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium">Clock out</label>
                <input v-model="form.clock_out" type="time" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
              </div>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Status</label>
              <select v-model="form.status" :disabled="isReadOnly" class="w-full rounded-lg border px-3 py-2">
                <option v-for="s in FORM_STATUSES" :key="s.value" :value="s.value">{{ s.label }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Note</label>
              <textarea v-model="form.note" :readonly="isReadOnly" rows="2" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>
          <div class="flex gap-2 border-t px-6 py-4">
            <template v-if="isReadOnly && detailRecord">
              <button type="button" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" @click="startEdit">Edit</button>
              <button type="button" class="rounded-lg border border-red-300 px-5 py-2 text-sm text-fb-danger" :disabled="deleting" @click="deleteRecord">Delete</button>
            </template>
            <button v-else type="submit" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" :disabled="saving">
              {{ saving ? 'Saving…' : editingRecord ? 'Save' : 'Create' }}
            </button>
            <button type="button" class="rounded-lg border px-5 py-2 text-sm" @click="closePanel">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
