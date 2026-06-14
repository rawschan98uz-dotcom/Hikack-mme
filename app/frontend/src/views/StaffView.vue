<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import ImportCsvModal from '../components/ImportCsvModal.vue';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';

interface StaffRow {
  id: number;
  name: string;
  first_name: string;
  last_name: string;
  phone: string;
  role: string;
  job_title: string;
}

const rows = ref<StaffRow[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingStaff = ref<StaffRow | null>(null);
const detailStaff = ref<StaffRow | null>(null);
const showImportModal = ref(false);

const auth = useAuthStore();
const canImportStaff = computed(() => auth.can(PERM.STAFF_WRITE));

const form = reactive({
  first_name: '',
  last_name: '',
  phone: '',
  job_title: '',
  password: '',
});

const isReadOnly = computed(() => Boolean(detailStaff.value && !editingStaff.value));
const panelTitle = computed(() => {
  if (editingStaff.value) return 'Edit staff';
  if (detailStaff.value) return 'Staff details';
  return 'Add staff';
});

function resetForm() {
  form.first_name = '';
  form.last_name = '';
  form.phone = '';
  form.job_title = '';
  form.password = '';
  formError.value = '';
  editingStaff.value = null;
  detailStaff.value = null;
}

function fillForm(row: StaffRow) {
  form.first_name = row.first_name || row.name.split(' ')[0] || '';
  form.last_name = row.last_name || row.name.split(' ').slice(1).join(' ') || '';
  form.phone = row.phone;
  form.job_title = row.job_title === '—' ? '' : row.job_title;
  form.password = '';
}

async function loadRows() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<StaffRow[]>>('/user', { params: { user_type: 'staff' } });
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
    const { data } = await client.get<ApiEnvelope<StaffRow>>(`/user/staff/${id}`);
    detailStaff.value = data.data;
    fillForm(data.data);
  } finally {
    panelLoading.value = false;
  }
}

function startEdit() {
  if (detailStaff.value) editingStaff.value = detailStaff.value;
}

function closePanel() {
  showPanel.value = false;
  resetForm();
}

async function submitForm() {
  formError.value = '';
  if (!form.first_name.trim() || !form.phone.trim()) {
    formError.value = 'First name and phone are required';
    return;
  }
  saving.value = true;
  try {
    const payload = {
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      phone: form.phone.trim(),
      job_title: form.job_title.trim(),
      ...(form.password ? { password: form.password } : {}),
    };
    if (editingStaff.value) {
      await client.patch(`/user/staff/${editingStaff.value.id}`, payload);
    } else {
      await client.post('/user/staff', payload);
    }
    closePanel();
    await loadRows();
  } catch {
    formError.value = 'Could not save';
  } finally {
    saving.value = false;
  }
}

async function deleteStaff() {
  if (!detailStaff.value || !window.confirm('Delete this staff member?')) return;
  deleting.value = true;
  try {
    await client.delete(`/user/staff/${detailStaff.value.id}`);
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
    <div class="flex items-center justify-between">
      <h1 class="text-xl font-semibold text-fb-text">Staff</h1>
      <div class="flex gap-2">
        <button
          v-if="canImportStaff"
          type="button"
          class="rounded-lg border border-fb-blue px-4 py-2 text-sm font-semibold text-fb-blue hover:bg-fb-hover"
          @click="showImportModal = true"
        >
          Import
        </button>
        <button type="button" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" @click="openCreate">
          ADD NEW
        </button>
      </div>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!rows.length" class="p-8 text-center text-fb-icon">No staff</div>
      <table v-else class="w-full text-base">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Name</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Job title</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Phone</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" class="cursor-pointer border-b hover:bg-fb-hover/40" @click="openDetail(row.id)">
            <td class="px-5 py-4">{{ row.name }}</td>
            <td class="px-5 py-4">{{ row.job_title }}</td>
            <td class="px-5 py-4">{{ row.phone }}</td>
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
              <label class="mb-1 block text-sm font-medium">First name</label>
              <input v-model="form.first_name" :readonly="isReadOnly" required class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Last name</label>
              <input v-model="form.last_name" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Phone</label>
              <input v-model="form.phone" :readonly="isReadOnly" required class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">Job title</label>
              <input v-model="form.job_title" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div v-if="!isReadOnly">
              <label class="mb-1 block text-sm font-medium">Password</label>
              <input v-model="form.password" type="password" :placeholder="editingStaff ? 'Leave blank to keep' : 'Default: demo1234'" class="w-full rounded-lg border px-3 py-2" />
            </div>
            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>
          <div class="flex gap-2 border-t px-6 py-4">
            <template v-if="isReadOnly && detailStaff">
              <button type="button" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" @click="startEdit">Edit</button>
              <button type="button" class="rounded-lg border border-red-300 px-5 py-2 text-sm text-fb-danger" :disabled="deleting" @click="deleteStaff">Delete</button>
            </template>
            <button v-else type="submit" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" :disabled="saving">
              {{ saving ? 'Saving…' : editingStaff ? 'Save' : 'Create' }}
            </button>
            <button type="button" class="rounded-lg border px-5 py-2 text-sm" @click="closePanel">Cancel</button>
          </div>
        </form>
      </div>
    </div>

    <ImportCsvModal
      v-model:open="showImportModal"
      title="Import staff"
      upload-url="/user/staff/import"
      template-filename="staff-import-template.csv"
      :template-header="['first_name', 'last_name', 'phone', 'password', 'job_title', 'staff_role']"
      :template-example="['Kamola', 'Yusupova', '901002010', 'demo1234', 'Administrator', 'administrator']"
      columns-help="Required: first_name, phone. Optional: last_name, password (default demo1234), job_title, staff_role (administrator, marketer, cashier, branch_director, limited_admin)."
      @imported="loadRows"
    />
  </div>
</template>
