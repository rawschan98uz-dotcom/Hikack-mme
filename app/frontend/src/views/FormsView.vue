<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { t } from '../i18n';
import { confirmDialog, toast } from '../ui/feedback';
import { apiErrorMessage } from '../utils/apiError';

interface FormRow {
  id: number;
  name: string;
  type: string;
}

const rows = ref<FormRow[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const formError = ref('');
const editingRow = ref<FormRow | null>(null);

const form = reactive({ name: '', type: 'lead' });

function resetForm() {
  form.name = '';
  form.type = 'lead';
  formError.value = '';
  editingRow.value = null;
}

function fillForm(row: FormRow) {
  form.name = row.name;
  form.type = row.type;
}

async function loadRows() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<FormRow[]>>('/leadForm');
    rows.value = data.data;
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  resetForm();
  showPanel.value = true;
}

function openEdit(row: FormRow) {
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
    formError.value = t('forms.nameRequired');
    return;
  }
  saving.value = true;
  try {
    const payload = { name: form.name.trim(), type: form.type };
    const wasEditing = Boolean(editingRow.value);
    if (editingRow.value) {
      await client.patch(`/leadForm/${editingRow.value.id}`, payload);
    } else {
      await client.post('/leadForm', payload);
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

async function deleteRow(row: FormRow) {
  const ok = await confirmDialog({
    title: t('forms.deleteConfirm', { name: row.name }),
    message: t('confirm.cannotUndo'),
    danger: true,
  });
  if (!ok) return;
  deleting.value = true;
  try {
    await client.delete(`/leadForm/${row.id}`);
    toast.success(t('toast.deleted'));
    await loadRows();
  } catch (err: unknown) {
    toast.error(apiErrorMessage(err, t('errors.deleteFailed')));
  } finally {
    deleting.value = false;
  }
}

onMounted(loadRows);
</script>

<template>
  <div class="space-y-5">
    <div class="flex items-center justify-between">
      <h1 class="text-[28px] font-normal text-fb-secondary">{{ t('nav.forms') }}</h1>
      <button
        type="button"
        class="rounded-full bg-fb-blue px-6 py-2.5 text-sm font-semibold text-white hover:opacity-90"
        @click="openCreate"
      >
        {{ t('common.addNew') }}
      </button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card shadow-sm">
      <div v-if="loading" class="p-10 text-center text-fb-secondary">{{ t('common.loading') }}</div>
      <table v-else class="w-full text-[15px]">
        <thead class="border-b border-fb-line">
          <tr class="text-left text-fb-secondary">
            <th class="px-6 py-4 font-medium">id</th>
            <th class="px-6 py-4 font-medium">{{ t('common.name') }}</th>
            <th class="px-6 py-4 font-medium">{{ t('common.type') }}</th>
            <th class="px-6 py-4 font-medium">{{ t('common.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!rows.length">
            <td colspan="4" class="px-6 py-10 text-center text-fb-icon">{{ t('forms.empty') }}</td>
          </tr>
          <tr v-for="row in rows" :key="row.id" class="border-b border-fb-line last:border-0">
            <td class="px-6 py-4 text-fb-secondary">{{ row.id }}</td>
            <td class="px-6 py-4 text-fb-text">{{ row.name }}</td>
            <td class="px-6 py-4 text-fb-secondary">{{ row.type }}</td>
            <td class="px-6 py-4">
              <div class="flex items-center gap-3">
                <button
                  type="button"
                  class="text-red-500 hover:text-fb-danger disabled:opacity-40"
                  :title="t('common.delete')"
                  :disabled="deleting"
                  @click="deleteRow(row)"
                >
                  🗑
                </button>
                <button
                  type="button"
                  class="text-amber-500 hover:text-amber-600"
                  :title="t('common.edit')"
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
          <h2 class="text-lg font-semibold">{{ editingRow ? t('forms.editTitle') : t('forms.addTitle') }}</h2>
          <button type="button" class="text-2xl text-fb-icon" :aria-label="t('common.close')" @click="closePanel">×</button>
        </div>
        <form class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitForm">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.name') }}</label>
              <input v-model="form.name" required class="w-full rounded-lg border px-3 py-2" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.type') }}</label>
              <input v-model="form.type" class="w-full rounded-lg border px-3 py-2" />
            </div>
            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>
          <div class="border-t px-6 py-4">
            <button
              type="submit"
              class="rounded-full bg-fb-blue px-8 py-2.5 text-sm font-semibold text-white disabled:opacity-60"
              :disabled="saving"
            >
              {{ saving ? t('common.saving') : t('common.save') }}
            </button>
          </div>
        </form>
      </aside>
    </div>
  </div>
</template>
