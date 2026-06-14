<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface Branch {
  id: number;
  name: string;
}

interface HolidayRow {
  id: number;
  name: string;
  date: string;
  created_at: string;
  affects_payment: boolean;
  branch_id: number;
  branch: string;
}

const rows = ref<HolidayRow[]>([]);
const branches = ref<Branch[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingRow = ref<HolidayRow | null>(null);
const detailRow = ref<HolidayRow | null>(null);
const activeTab = ref<'upcoming' | 'past'>('upcoming');

const form = reactive({
  name: '',
  date: '',
  branch_id: '' as number | '',
  affects_payment: false,
});

const isReadOnly = computed(() => Boolean(detailRow.value && !editingRow.value));
const panelTitle = computed(() =>
  editingRow.value ? 'Edit holiday' : detailRow.value ? 'Holiday details' : 'Add holiday',
);

const filteredRows = computed(() => {
  const today = new Date().toISOString().slice(0, 10);
  return rows.value.filter((row) =>
    activeTab.value === 'upcoming' ? row.date >= today : row.date < today,
  );
});

function resetForm() {
  form.name = '';
  form.date = new Date().toISOString().slice(0, 10);
  form.branch_id = branches.value[0]?.id ?? '';
  form.affects_payment = false;
  formError.value = '';
  editingRow.value = null;
  detailRow.value = null;
}

function fillForm(row: HolidayRow) {
  form.name = row.name;
  form.date = row.date;
  form.branch_id = row.branch_id;
  form.affects_payment = row.affects_payment;
}

async function loadMeta() {
  const [holidayRes, branchRes] = await Promise.all([
    client.get<ApiEnvelope<HolidayRow[]>>('/holidayRecalculation'),
    client.get<ApiEnvelope<Branch[]>>('/branch'),
  ]);
  rows.value = holidayRes.data.data;
  branches.value = branchRes.data.data;
}

async function loadRows() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<HolidayRow[]>>('/holidayRecalculation');
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
    const { data } = await client.get<ApiEnvelope<HolidayRow>>(`/holidayRecalculation/${id}`);
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
  if (!form.name.trim() || !form.date || !form.branch_id) {
    formError.value = 'Name, date and branch are required';
    return;
  }
  saving.value = true;
  try {
    const payload = {
      name: form.name.trim(),
      date: form.date,
      branch_id: form.branch_id,
      affects_payment: form.affects_payment,
    };
    if (editingRow.value) {
      await client.patch(`/holidayRecalculation/${editingRow.value.id}`, payload);
    } else {
      await client.post('/holidayRecalculation', payload);
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
  if (!detailRow.value || !window.confirm('Delete this holiday?')) return;
  deleting.value = true;
  try {
    await client.delete(`/holidayRecalculation/${detailRow.value.id}`);
    closePanel();
    await loadRows();
  } finally {
    deleting.value = false;
  }
}

onMounted(async () => {
  await loadMeta();
  loading.value = false;
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-xl font-semibold text-fb-text">Holidays</h1>
      <button type="button" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" @click="openCreate">
        ADD NEW
      </button>
    </div>

    <div class="flex gap-2 border-b border-fb-line">
      <button
        type="button"
        class="-mb-px border-b-2 px-4 py-2 text-sm"
        :class="activeTab === 'upcoming' ? 'border-fb-blue font-medium text-fb-blue' : 'border-transparent text-fb-secondary'"
        @click="activeTab = 'upcoming'"
      >
        Upcoming
      </button>
      <button
        type="button"
        class="-mb-px border-b-2 px-4 py-2 text-sm"
        :class="activeTab === 'past' ? 'border-fb-blue font-medium text-fb-blue' : 'border-transparent text-fb-secondary'"
        @click="activeTab = 'past'"
      >
        Past
      </button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!filteredRows.length" class="p-8 text-center text-fb-icon">No holidays</div>
      <table v-else class="w-full text-base">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Name</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Date</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Branch</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Affects payment</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filteredRows" :key="row.id" class="cursor-pointer border-b hover:bg-fb-hover/40" @click="openDetail(row.id)">
            <td class="px-5 py-4">{{ row.name }}</td>
            <td class="px-5 py-4">{{ row.date }}</td>
            <td class="px-5 py-4">{{ row.branch }}</td>
            <td class="px-5 py-4">{{ row.affects_payment ? 'Yes' : 'No' }}</td>
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
              <label class="mb-1 block text-sm font-medium">Name</label>
              <input v-model="form.name" :readonly="isReadOnly" required class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Date</label>
              <input v-model="form.date" type="date" :readonly="isReadOnly" required class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Branch</label>
              <select v-model="form.branch_id" :disabled="isReadOnly" class="w-full rounded-lg border px-3 py-2">
                <option v-for="b in branches" :key="b.id" :value="b.id">{{ b.name }}</option>
              </select>
            </div>
            <label class="flex items-center gap-2 text-sm">
              <input v-model="form.affects_payment" type="checkbox" :disabled="isReadOnly" />
              Affects payment
            </label>
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
