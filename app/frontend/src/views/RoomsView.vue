<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface Branch {
  id: number;
  name: string;
}

interface RoomRow {
  id: number;
  name: string;
  room_capacity: number;
  branch_id: number;
  branch: string;
}

const rows = ref<RoomRow[]>([]);
const branches = ref<Branch[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingRow = ref<RoomRow | null>(null);
const detailRow = ref<RoomRow | null>(null);

const form = reactive({
  name: '',
  room_capacity: 20,
  branch_id: '' as number | '',
});

const isReadOnly = computed(() => Boolean(detailRow.value && !editingRow.value));
const panelTitle = computed(() =>
  editingRow.value ? 'Edit room' : detailRow.value ? 'Room details' : 'Add room',
);

function resetForm() {
  form.name = '';
  form.room_capacity = 20;
  form.branch_id = branches.value[0]?.id ?? '';
  formError.value = '';
  editingRow.value = null;
  detailRow.value = null;
}

function fillForm(row: RoomRow) {
  form.name = row.name;
  form.room_capacity = row.room_capacity;
  form.branch_id = row.branch_id;
}

async function loadMeta() {
  const [roomRes, branchRes] = await Promise.all([
    client.get<ApiEnvelope<RoomRow[]>>('/room'),
    client.get<ApiEnvelope<Branch[]>>('/branch'),
  ]);
  rows.value = roomRes.data.data;
  branches.value = branchRes.data.data;
}

async function loadRows() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<RoomRow[]>>('/room');
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
    const { data } = await client.get<ApiEnvelope<RoomRow>>(`/room/${id}`);
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
  if (!form.name.trim() || !form.branch_id) {
    formError.value = 'Name and branch are required';
    return;
  }
  saving.value = true;
  try {
    const payload = {
      name: form.name.trim(),
      room_capacity: form.room_capacity,
      branch_id: form.branch_id,
    };
    if (editingRow.value) {
      await client.patch(`/room/${editingRow.value.id}`, payload);
    } else {
      await client.post('/room', payload);
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
  if (!detailRow.value || !window.confirm('Delete this room?')) return;
  deleting.value = true;
  try {
    await client.delete(`/room/${detailRow.value.id}`);
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
      <h1 class="text-xl font-semibold text-fb-text">Rooms</h1>
      <button type="button" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" @click="openCreate">
        ADD NEW
      </button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <table v-else class="w-full text-base">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Name</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Capacity</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Branch</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" class="cursor-pointer border-b hover:bg-fb-hover/40" @click="openDetail(row.id)">
            <td class="px-5 py-4">{{ row.name }}</td>
            <td class="px-5 py-4">{{ row.room_capacity }}</td>
            <td class="px-5 py-4">{{ row.branch }}</td>
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
              <label class="mb-1 block text-sm font-medium">Capacity</label>
              <input v-model.number="form.room_capacity" type="number" min="1" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Branch</label>
              <select v-model="form.branch_id" :disabled="isReadOnly" class="w-full rounded-lg border px-3 py-2">
                <option v-for="b in branches" :key="b.id" :value="b.id">{{ b.name }}</option>
              </select>
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
