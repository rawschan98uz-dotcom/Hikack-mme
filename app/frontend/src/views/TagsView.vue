<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface TagRow {
  id: number;
  name: string;
  from_where: string;
}

const SOURCE_OPTIONS = ['Students', 'Leads', 'Teachers', 'Staff', 'Social', 'Web'] as const;

const rows = ref<TagRow[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const formError = ref('');
const editingRow = ref<TagRow | null>(null);

const form = reactive({ name: '', from_where: 'Students' as (typeof SOURCE_OPTIONS)[number] });

function resetForm() {
  form.name = '';
  form.from_where = 'Students';
  formError.value = '';
  editingRow.value = null;
}

function fillForm(row: TagRow) {
  form.name = row.name;
  const source = row.from_where === '—' ? 'Students' : row.from_where;
  form.from_where = SOURCE_OPTIONS.includes(source as (typeof SOURCE_OPTIONS)[number])
    ? (source as (typeof SOURCE_OPTIONS)[number])
    : 'Students';
}

function sourceBadgeClass(source: string) {
  if (source === 'Students') return 'bg-fb-blue text-white';
  return 'bg-fb-canvas text-fb-secondary';
}

async function loadRows() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<TagRow[]>>('/tags');
    rows.value = data.data;
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  resetForm();
  showPanel.value = true;
}

function openEdit(row: TagRow) {
  resetForm();
  editingRow.value = row;
  fillForm(row);
  showPanel.value = true;
}

function closePanel() {
  showPanel.value = false;
  resetForm();
}

async function submitForm() {
  formError.value = '';
  if (!form.name.trim()) {
    formError.value = 'Name is required';
    return;
  }
  saving.value = true;
  try {
    const payload = { name: form.name.trim(), from_where: form.from_where };
    if (editingRow.value) {
      await client.patch(`/tags/${editingRow.value.id}`, payload);
    } else {
      await client.post('/tags', payload);
    }
    closePanel();
    await loadRows();
  } catch {
    formError.value = 'Could not save';
  } finally {
    saving.value = false;
  }
}

async function deleteRow(row: TagRow) {
  if (!window.confirm(`Delete tag "${row.name}"?`)) return;
  deleting.value = true;
  try {
    await client.delete(`/tags/${row.id}`);
    await loadRows();
  } finally {
    deleting.value = false;
  }
}

onMounted(loadRows);
</script>

<template>
  <div class="space-y-5">
    <div class="flex items-center justify-between">
      <h1 class="text-[28px] font-normal text-fb-secondary">Tags</h1>
      <button
        type="button"
        class="rounded-full bg-fb-blue px-6 py-2.5 text-sm font-semibold tracking-wide text-white hover:opacity-90"
        @click="openCreate"
      >
        ADD NEW
      </button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card shadow-sm">
      <div v-if="loading" class="p-10 text-center text-fb-secondary">Loading…</div>
      <table v-else class="w-full text-[15px]">
        <thead class="border-b border-fb-line">
          <tr class="text-left text-fb-secondary">
            <th class="px-6 py-4 font-medium">id</th>
            <th class="px-6 py-4 font-medium">Name</th>
            <th class="px-6 py-4 font-medium">From Where</th>
            <th class="px-6 py-4 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!rows.length">
            <td colspan="4" class="px-6 py-10 text-center text-fb-icon">No tags yet</td>
          </tr>
          <tr v-for="row in rows" :key="row.id" class="border-b border-fb-line last:border-0">
            <td class="px-6 py-4 text-fb-secondary">{{ row.id }}</td>
            <td class="px-6 py-4 text-fb-text">{{ row.name }}</td>
            <td class="px-6 py-4">
              <span
                class="inline-block rounded-full px-3 py-1 text-xs font-medium"
                :class="sourceBadgeClass(row.from_where)"
              >
                {{ row.from_where }}
              </span>
            </td>
            <td class="px-6 py-4">
              <div class="flex items-center gap-3">
                <button
                  type="button"
                  class="text-red-500 hover:text-fb-danger disabled:opacity-40"
                  title="Delete"
                  :disabled="deleting"
                  @click="deleteRow(row)"
                >
                  🗑
                </button>
                <button
                  type="button"
                  class="text-amber-500 hover:text-amber-600"
                  title="Edit"
                  @click="openEdit(row)"
                >
                  ✏
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closePanel" />
      <aside class="drawer-panel-fb max-w-md">
        <div class="flex items-center justify-between border-b px-6 py-4">
          <h2 class="text-lg font-semibold">{{ editingRow ? 'Edit tag' : 'Add tag' }}</h2>
          <button type="button" class="text-2xl text-fb-icon" @click="closePanel">×</button>
        </div>
        <form class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitForm">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Name</label>
              <input v-model="form.name" required class="w-full rounded-lg border px-3 py-2" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">From Where</label>
              <select v-model="form.from_where" class="w-full rounded-lg border px-3 py-2">
                <option v-for="source in SOURCE_OPTIONS" :key="source" :value="source">{{ source }}</option>
              </select>
            </div>
            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>
          <div class="border-t px-6 py-4">
            <button
              type="submit"
              class="rounded-full bg-fb-blue px-8 py-2.5 text-sm font-semibold text-white disabled:opacity-60"
              :disabled="saving"
            >
              {{ saving ? 'Saving…' : 'Save' }}
            </button>
          </div>
        </form>
      </aside>
    </div>
  </div>
</template>
