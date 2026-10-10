<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import SkeletonBlock from '../components/SkeletonBlock.vue';
import EmptyState from '../components/EmptyState.vue';

import client, { type ApiEnvelope } from '../api/client';
import { t } from '../i18n';
import { confirmDialog, toast } from '../ui/feedback';
import { apiErrorMessage } from '../utils/apiError';

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
  editingRow.value ? t('rooms.editTitle') : detailRow.value ? t('rooms.detailTitle') : t('rooms.addTitle'),
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
    formError.value = t('rooms.nameBranchRequired');
    return;
  }
  saving.value = true;
  try {
    const payload = {
      name: form.name.trim(),
      room_capacity: form.room_capacity,
      branch_id: form.branch_id,
    };
    const wasEditing = Boolean(editingRow.value);
    if (editingRow.value) {
      await client.patch(`/room/${editingRow.value.id}`, payload);
    } else {
      await client.post('/room', payload);
    }
    closePanel();
    toast.success(wasEditing ? t('toast.saved') : t('toast.created'));
    await loadRows();
  } catch (err: unknown) {
    formError.value = apiErrorMessage(err, t('errors.saveFailed'));
  } finally {
    saving.value = false;
  }
}

async function deleteRow() {
  if (!detailRow.value) return;
  const ok = await confirmDialog({
    title: t('rooms.deleteConfirm', { name: detailRow.value.name }),
    message: t('confirm.cannotUndo'),
    danger: true,
  });
  if (!ok || !detailRow.value) return;
  deleting.value = true;
  try {
    await client.delete(`/room/${detailRow.value.id}`);
    closePanel();
    toast.success(t('toast.deleted'));
    await loadRows();
  } catch (err: unknown) {
    toast.error(apiErrorMessage(err, t('errors.deleteFailed')));
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
      <h1 class="text-xl font-semibold text-fb-text">{{ t('nav.rooms') }}</h1>
      <button type="button" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" @click="openCreate">
        {{ t('common.addNew') }}
      </button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <SkeletonBlock v-if="loading" :rows="4" :cols="3" />
      <EmptyState
        v-else-if="!rows.length"
        icon="rooms"
        :title="t('rooms.emptyTitle')"
        :hint="t('rooms.emptyHint')"
        :action-label="t('rooms.addTitle')"
        @action="openCreate"
      />
      <table v-else class="w-full text-base">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.name') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('rooms.capacity') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.branch') }}</th>
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
          <button type="button" :aria-label="t('common.close')" @click="closePanel">✕</button>
        </div>
        <SkeletonBlock v-if="panelLoading" variant="lines" :rows="5" class="p-6" />
        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitForm">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('common.name') }}</label>
              <input v-model="form.name" :readonly="isReadOnly" required class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('rooms.capacity') }}</label>
              <input v-model.number="form.room_capacity" type="number" min="1" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('common.branch') }}</label>
              <select v-model="form.branch_id" :disabled="isReadOnly" class="w-full rounded-lg border px-3 py-2">
                <option v-for="b in branches" :key="b.id" :value="b.id">{{ b.name }}</option>
              </select>
            </div>
            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>
          <div class="flex gap-2 border-t px-6 py-4">
            <template v-if="isReadOnly && detailRow">
              <button type="button" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" @click="startEdit">{{ t('common.edit') }}</button>
              <button type="button" class="rounded-lg border border-red-300 px-5 py-2 text-sm text-fb-danger" :disabled="deleting" @click="deleteRow">{{ t('common.delete') }}</button>
            </template>
            <button v-else type="submit" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" :disabled="saving">
              {{ saving ? t('common.saving') : editingRow ? t('common.save') : t('common.create') }}
            </button>
            <button type="button" class="rounded-lg border px-5 py-2 text-sm" @click="closePanel">{{ t('common.cancel') }}</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
