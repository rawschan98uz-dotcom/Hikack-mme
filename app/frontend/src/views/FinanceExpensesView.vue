<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface Category {
  id: number;
  name: string;
}

interface ExpenseRow {
  id: number;
  date: string;
  category_id: number | null;
  category: string;
  description: string;
  payee: string;
  method: string;
  method_pay: string;
  sum: number;
  amount: number;
  creator: string;
}

const METHODS = [
  { value: 'cash', label: 'Cash' },
  { value: 'card', label: 'Card' },
  { value: 'transfer', label: 'Transfer' },
] as const;

const rows = ref<ExpenseRow[]>([]);
const categories = ref<Category[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingRow = ref<ExpenseRow | null>(null);
const detailRow = ref<ExpenseRow | null>(null);
const filters = reactive({ date_from: '', date_to: '', category_id: '', q: '' });
const form = reactive({
  category_id: '' as number | '',
  description: '',
  payee: '',
  method: 'cash' as (typeof METHODS)[number]['value'],
  amount: 0,
});

const isReadOnly = computed(() => Boolean(detailRow.value && !editingRow.value));
const panelTitle = computed(() =>
  editingRow.value ? 'Edit expense' : detailRow.value ? 'Expense details' : 'New expense',
);
const tableRows = computed(() =>
  rows.value.map((r) => ({
    id: r.id,
    date: r.date,
    category: r.category,
    description: r.description || '—',
    payee: r.payee || '—',
    method_pay: r.method_pay,
    sum: r.sum.toLocaleString(),
    creator: r.creator,
  })),
);

function resetForm() {
  form.category_id = categories.value[0]?.id ?? '';
  form.description = '';
  form.payee = '';
  form.method = 'cash';
  form.amount = 0;
  formError.value = '';
  editingRow.value = null;
  detailRow.value = null;
}

function fillForm(row: ExpenseRow) {
  form.category_id = row.category_id ?? '';
  form.description = row.description;
  form.payee = row.payee;
  form.method = row.method as (typeof METHODS)[number]['value'];
  form.amount = row.sum;
}

async function loadCategories() {
  const { data } = await client.get<ApiEnvelope<Category[]>>('/expense_types');
  categories.value = data.data;
}

async function loadRows() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.category_id) params.category_id = filters.category_id;
    if (filters.q.trim()) params.q = filters.q.trim();
    const { data } = await client.get<ApiEnvelope<ExpenseRow[]>>('/expense', { params });
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
    const { data } = await client.get<ApiEnvelope<ExpenseRow>>(`/expense/${id}`);
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
  if (!form.amount) {
    formError.value = 'Enter amount';
    return;
  }
  saving.value = true;
  try {
    const payload = {
      category_id: form.category_id === '' ? null : form.category_id,
      description: form.description.trim(),
      payee: form.payee.trim(),
      method: form.method,
      amount: form.amount,
    };
    if (editingRow.value) {
      await client.patch(`/expense/${editingRow.value.id}`, payload);
    } else {
      await client.post('/expense', payload);
    }
    closePanel();
    await loadRows();
  } catch {
    formError.value = 'Could not save expense';
  } finally {
    saving.value = false;
  }
}

async function deleteRow() {
  if (!detailRow.value || !window.confirm('Delete this expense?')) return;
  deleting.value = true;
  try {
    await client.delete(`/expense/${detailRow.value.id}`);
    closePanel();
    await loadRows();
  } finally {
    deleting.value = false;
  }
}

onMounted(async () => {
  await loadCategories();
  await loadRows();
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-fb-text">Total Expenses</h1>
      <button type="button" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" @click="openCreate">
        New expense
      </button>
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">Category</label>
        <select v-model="filters.category_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option value="">All</option>
          <option v-for="c in categories" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
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
      <div v-else-if="!tableRows.length" class="p-8 text-center text-fb-icon">No expenses</div>
      <table v-else class="w-full text-base">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Date</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Category</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Description</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Payee</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Method</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Sum</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Creator</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in tableRows" :key="row.id" class="cursor-pointer border-b hover:bg-fb-hover/40" @click="openDetail(row.id)">
            <td class="px-5 py-4">{{ row.date }}</td>
            <td class="px-5 py-4">{{ row.category }}</td>
            <td class="px-5 py-4">{{ row.description }}</td>
            <td class="px-5 py-4">{{ row.payee }}</td>
            <td class="px-5 py-4">{{ row.method_pay }}</td>
            <td class="px-5 py-4 font-semibold text-fb-blue">{{ row.sum }}</td>
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
              <label class="mb-1 block text-sm font-medium">Category</label>
              <select v-model="form.category_id" :disabled="isReadOnly" class="w-full rounded-lg border px-3 py-2">
                <option value="">— None —</option>
                <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Description</label>
              <textarea v-model="form.description" :readonly="isReadOnly" rows="2" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Payee</label>
              <input v-model="form.payee" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Method</label>
              <select v-model="form.method" :disabled="isReadOnly" class="w-full rounded-lg border px-3 py-2">
                <option v-for="m in METHODS" :key="m.value" :value="m.value">{{ m.label }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Amount</label>
              <input v-model.number="form.amount" type="number" :readonly="isReadOnly" required class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
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
