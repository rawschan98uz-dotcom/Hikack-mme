<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface WithdrawRow {
  id: number;
  date: string;
  name: string;
  sum: number;
  amount: number;
  comment: string;
  creator: string;
}

const rows = ref<WithdrawRow[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingRow = ref<WithdrawRow | null>(null);
const detailRow = ref<WithdrawRow | null>(null);
const filters = reactive({ date_from: '', date_to: '', q: '' });
const form = reactive({ name: '', amount: 0, comment: '' });

const isReadOnly = computed(() => Boolean(detailRow.value && !editingRow.value));
const panelTitle = computed(() =>
  editingRow.value ? 'Edit withdrawal' : detailRow.value ? 'Withdrawal details' : 'Add withdrawal',
);
const tableRows = computed(() =>
  rows.value.map((r) => ({
    id: r.id,
    date: r.date,
    name: r.name,
    sum: r.sum.toLocaleString(),
    comment: r.comment || '—',
    creator: r.creator,
  })),
);

function resetForm() {
  form.name = '';
  form.amount = 0;
  form.comment = '';
  formError.value = '';
  editingRow.value = null;
  detailRow.value = null;
}

function fillForm(row: WithdrawRow) {
  form.name = row.name;
  form.amount = row.sum;
  form.comment = row.comment;
}

async function loadRows() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();
    const { data } = await client.get<ApiEnvelope<WithdrawRow[]>>('/withdraws', { params });
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
    const { data } = await client.get<ApiEnvelope<WithdrawRow>>(`/withdraws/${id}`);
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
  if (!form.name.trim() || !form.amount) {
    formError.value = 'Fill name and amount';
    return;
  }
  saving.value = true;
  try {
    const payload = { name: form.name.trim(), amount: form.amount, comment: form.comment.trim() };
    if (editingRow.value) {
      await client.patch(`/withdraws/${editingRow.value.id}`, payload);
    } else {
      await client.post('/withdraws', payload);
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
  if (!detailRow.value || !window.confirm('Delete this withdrawal?')) return;
  deleting.value = true;
  try {
    await client.delete(`/withdraws/${detailRow.value.id}`);
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
      <h1 class="text-xl font-semibold text-fb-text">Withdraw</h1>
      <button type="button" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" @click="openCreate">
        + Add withdrawal
      </button>
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
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
      <div v-else-if="!tableRows.length" class="p-8 text-center text-fb-icon">No withdrawals</div>
      <table v-else class="w-full text-base">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Date</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Name</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Sum</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Comment</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Creator</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in tableRows" :key="row.id" class="cursor-pointer border-b hover:bg-fb-hover/40" @click="openDetail(row.id)">
            <td class="px-5 py-4">{{ row.date }}</td>
            <td class="px-5 py-4 font-medium">{{ row.name }}</td>
            <td class="px-5 py-4 font-semibold text-fb-blue">{{ row.sum }}</td>
            <td class="px-5 py-4">{{ row.comment }}</td>
            <td class="px-5 py-4">{{ row.creator }}</td>
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
              <label class="mb-1 block text-sm font-medium">Amount</label>
              <input v-model.number="form.amount" type="number" :readonly="isReadOnly" required class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Comment</label>
              <textarea v-model="form.comment" :readonly="isReadOnly" rows="3" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
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
