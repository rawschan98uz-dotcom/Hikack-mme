<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';
import { downloadCsv } from '../utils/csvExport';

interface ArchiveRow {
  id: number;
  name: string;
  phone: string;
  roles: string;
  reason: string;
  comment: string;
  archived: string;
}

interface ArchiveReason {
  id: number;
  name: string;
}

interface ArchivePayload {
  quantity: number;
  rows: ArchiveRow[];
}

const ROLE_OPTIONS = ['', 'student', 'teacher', 'staff', 'lead'];

const rows = ref<ArchiveRow[]>([]);
const auth = useAuthStore();
const canExportArchive = computed(() => auth.can(PERM.ARCHIVE_VIEW));
const quantity = ref(0);
const reasons = ref<ArchiveReason[]>([]);
const loading = ref(true);
const bulkLoading = ref(false);
const showReasons = ref(false);
const selectedIds = ref<number[]>([]);

const filters = reactive({
  q: '',
  role: '',
  reason: '',
  date_from: '',
  date_to: '',
});

const allSelected = computed(
  () => rows.value.length > 0 && selectedIds.value.length === rows.value.length,
);

function toggleAll() {
  selectedIds.value = allSelected.value ? [] : rows.value.map((row) => row.id);
}

function toggleRow(id: number) {
  if (selectedIds.value.includes(id)) {
    selectedIds.value = selectedIds.value.filter((item) => item !== id);
  } else {
    selectedIds.value = [...selectedIds.value, id];
  }
}

async function loadReasons() {
  const { data } = await client.get<ApiEnvelope<ArchiveReason[]>>('/archiveReasons');
  reasons.value = data.data;
}

async function loadRows() {
  loading.value = true;
  selectedIds.value = [];
  try {
    const params: Record<string, string> = {};
    if (filters.q.trim()) params.q = filters.q.trim();
    if (filters.role) params.role = filters.role;
    if (filters.reason) params.reason = filters.reason;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    const { data } = await client.get<ApiEnvelope<ArchivePayload>>('/archive/list', { params });
    quantity.value = data.data.quantity;
    rows.value = data.data.rows;
  } finally {
    loading.value = false;
  }
}

async function bulkAction(action: 'delete' | 'restore') {
  if (!selectedIds.value.length) return;
  const label = action === 'delete' ? 'permanently delete' : 'reestablish';
  if (!window.confirm(`${label} ${selectedIds.value.length} record(s)?`)) return;

  bulkLoading.value = true;
  try {
    await client.post('/archive/list/bulk', { action, ids: selectedIds.value });
    await loadRows();
  } finally {
    bulkLoading.value = false;
  }
}

async function restoreOne(id: number) {
  if (!window.confirm('Reestablish this record?')) return;
  await client.post(`/archive/list/${id}/restore`);
  await loadRows();
}

async function deleteOne(id: number) {
  if (!window.confirm('Permanently delete this record?')) return;
  await client.delete(`/archive/list/${id}`);
  await loadRows();
}

function exportCsv() {
  downloadCsv(
    'archive.csv',
    ['Name', 'Phone', 'Roles', 'Reason', 'Comment', 'Archived'],
    rows.value.map((row) => [row.name, row.phone, row.roles, row.reason, row.comment, row.archived]),
  );
}

onMounted(async () => {
  await loadReasons();
  await loadRows();
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-fb-text">
        Archive
        <span class="ml-2 text-base font-normal text-fb-secondary">Quantity — {{ quantity }}</span>
      </h1>
      <button
        type="button"
        class="rounded-lg border border-fb-line px-4 py-2 text-sm"
        @click="showReasons = true"
      >
        Reasons for archiving
      </button>
    </div>

    <div class="space-y-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div class="flex flex-wrap items-end gap-3">
        <div class="min-w-[180px] flex-1">
          <label class="mb-1 block text-xs text-fb-secondary">Name or Phone</label>
          <input v-model="filters.q" type="search" class="w-full rounded-lg border px-3 py-2 text-sm" @keydown.enter="loadRows" />
        </div>
        <div>
          <label class="mb-1 block text-xs text-fb-secondary">Filter by role</label>
          <select v-model="filters.role" class="rounded-lg border px-3 py-2 text-sm">
            <option value="">All roles</option>
            <option v-for="role in ROLE_OPTIONS.filter(Boolean)" :key="role" :value="role">{{ role }}</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs text-fb-secondary">Filter by reason</label>
          <select v-model="filters.reason" class="rounded-lg border px-3 py-2 text-sm">
            <option value="">All reasons</option>
            <option v-for="reason in reasons" :key="reason.id" :value="reason.name">{{ reason.name }}</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs text-fb-secondary">Start date</label>
          <input v-model="filters.date_from" type="date" class="rounded-lg border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs text-fb-secondary">End date</label>
          <input v-model="filters.date_to" type="date" class="rounded-lg border px-3 py-2 text-sm" />
        </div>
        <button type="button" class="rounded-lg border px-4 py-2 text-sm" @click="loadRows">Apply</button>
      </div>

      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          class="rounded-lg border border-red-300 px-3 py-1.5 text-sm text-fb-danger disabled:opacity-40"
          :disabled="!selectedIds.length || bulkLoading"
          @click="bulkAction('delete')"
        >
          Delete
        </button>
        <button
          type="button"
          class="rounded-lg border border-emerald-300 px-3 py-1.5 text-sm text-emerald-700 disabled:opacity-40"
          :disabled="!selectedIds.length || bulkLoading"
          @click="bulkAction('restore')"
        >
          Reestablish
        </button>
        <button
          v-if="canExportArchive"
          type="button"
          class="ml-auto rounded-lg border px-3 py-1.5 text-sm"
          @click="exportCsv"
        >
          Export
        </button>
      </div>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!rows.length" class="p-8 text-center text-fb-icon">No Data</div>
      <table v-else class="w-full text-sm">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-4 py-3 text-left">
              <input type="checkbox" :checked="allSelected" @change="toggleAll" />
            </th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">Name</th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">Phone</th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">Roles</th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">Reasons for removal</th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">Comment</th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">Archived</th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" class="border-b">
            <td class="px-4 py-3">
              <input type="checkbox" :checked="selectedIds.includes(row.id)" @change="toggleRow(row.id)" />
            </td>
            <td class="px-4 py-3">{{ row.name }}</td>
            <td class="px-4 py-3">{{ row.phone }}</td>
            <td class="px-4 py-3">{{ row.roles }}</td>
            <td class="px-4 py-3">{{ row.reason }}</td>
            <td class="px-4 py-3">{{ row.comment }}</td>
            <td class="px-4 py-3">{{ row.archived }}</td>
            <td class="px-4 py-3">
              <div class="flex gap-2">
                <button type="button" class="text-emerald-700 hover:underline" @click="restoreOne(row.id)">Restore</button>
                <button type="button" class="text-fb-danger hover:underline" @click="deleteOne(row.id)">Delete</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showReasons" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/35" @click="showReasons = false" />
      <div class="modal-panel-fb max-w-md p-6">
        <div class="mb-4 flex items-center justify-between">
          <h2 class="text-lg font-semibold">Reasons for archiving</h2>
          <button type="button" @click="showReasons = false">✕</button>
        </div>
        <ul class="space-y-2">
          <li v-for="reason in reasons" :key="reason.id" class="rounded-lg border px-4 py-2 text-sm">
            {{ reason.name }}
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
