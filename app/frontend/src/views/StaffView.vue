<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import ImportCsvModal from '../components/ImportCsvModal.vue';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';
import { t, tMaybe, type MessageKey } from '../i18n';
import { confirmDialog, toast } from '../ui/feedback';
import { apiErrorMessage } from '../utils/apiError';

interface StaffRow {
  id: number;
  name: string;
  first_name: string;
  last_name: string;
  phone: string;
  role: string;
  job_title: string;
  staff_role?: string;
  staff_role_label?: string;
  branch_id?: number | null;
  branch?: string;
}

// Roles a CEO can give in the staff card (CEO itself is not assignable)
const STAFF_ROLES: { value: string; label: MessageKey }[] = [
  // "Ограниченный админ" and "Кассир" are the same person as the administrator (owner, 2026-09-28)
  { value: 'administrator', label: 'roles.administrator' },
  { value: 'branch_director', label: 'roles.branch_director' },
  { value: 'marketer', label: 'roles.marketer' },
];

function staffRoleLabel(role: string | undefined, fallback?: string) {
  if (!role) return fallback || '—';
  return tMaybe(`roles.${role}`, fallback || role);
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
const canDeleteStaff = computed(() => {
  if (!auth.isCeo) return false;
  if (!detailStaff.value) return false;
  return detailStaff.value.id !== auth.user?.id;
});

const form = reactive({
  first_name: '',
  last_name: '',
  phone: '',
  job_title: '',
  password: '',
  staff_role: 'administrator',
  branch_id: '' as number | '',
});

const branches = computed(() => auth.user?.branches ?? []);
// E3: only CEO sets roles and a director's branch; nobody changes own role
const canEditRole = computed(() => auth.isCeo && (!editingStaff.value || editingStaff.value.id !== auth.user?.id));
const isDirectorRole = computed(() => form.staff_role === 'branch_director');

const searchQuery = ref('');

const filteredRows = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return rows.value;
  const digits = q.replace(/\D/g, '');
  return rows.value.filter((row) => {
    const nameMatch =
      row.name?.toLowerCase().includes(q) ||
      row.first_name?.toLowerCase().includes(q) ||
      row.last_name?.toLowerCase().includes(q);
    const jobMatch =
      (row.job_title && row.job_title.toLowerCase().includes(q)) ||
      (row.role && row.role.toLowerCase().includes(q));
    const phoneDigits = (row.phone || '').replace(/\D/g, '');
    const phoneMatch = digits ? phoneDigits.includes(digits) : row.phone?.toLowerCase().includes(q);
    return Boolean(nameMatch || jobMatch || phoneMatch);
  });
});

const quantity = computed(() => filteredRows.value.length);
const totalQuantity = computed(() => rows.value.length);

const isReadOnly = computed(() => Boolean(detailStaff.value && !editingStaff.value));
const panelTitle = computed(() => {
  if (editingStaff.value) return t('staff.editTitle');
  if (detailStaff.value) return t('staff.detailTitle');
  return t('staff.addTitle');
});

function resetForm() {
  form.first_name = '';
  form.last_name = '';
  form.phone = '';
  form.job_title = '';
  form.password = '';
  form.staff_role = 'administrator';
  form.branch_id = '';
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
  form.staff_role = row.staff_role || 'administrator';
  form.branch_id = row.branch_id ?? '';
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
    formError.value = t('staff.namePhoneRequired');
    return;
  }
  if (canEditRole.value && isDirectorRole.value && !form.branch_id) {
    formError.value = t('staff.directorBranchRequired');
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
      ...(canEditRole.value
        ? { staff_role: form.staff_role, branch_id: isDirectorRole.value ? form.branch_id : null }
        : {}),
    };
    const wasEditing = Boolean(editingStaff.value);
    if (editingStaff.value) {
      await client.patch(`/user/staff/${editingStaff.value.id}`, payload);
    } else {
      await client.post('/user/staff', payload);
    }
    closePanel();
    toast.success(wasEditing ? t('toast.saved') : t('staff.created'));
    await loadRows();
  } catch (error) {
    formError.value = apiErrorMessage(error, t('errors.saveFailed'));
  } finally {
    saving.value = false;
  }
}

async function deleteStaff() {
  if (!canDeleteStaff.value || !detailStaff.value) return;
  const ok = await confirmDialog({
    title: t('staff.deleteConfirm', { name: detailStaff.value.name }),
    message: t('staff.deleteHint'),
    danger: true,
  });
  if (!ok || !detailStaff.value) return;
  deleting.value = true;
  try {
    await client.delete(`/user/staff/${detailStaff.value.id}`);
    closePanel();
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
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-baseline gap-3">
        <h1 class="text-xl font-semibold text-fb-text">{{ t('nav.staff') }}</h1>
        <span v-if="!loading" class="text-sm text-fb-secondary">
          {{ t('archive.quantity', { count: quantity }) }}<span v-if="searchQuery.trim() && totalQuantity !== quantity"> ({{ t('archive.ofTotal', { total: totalQuantity }) }})</span>
        </span>
      </div>
      <div class="flex gap-2">
        <button
          v-if="canImportStaff"
          type="button"
          class="rounded-lg border border-fb-blue px-4 py-2 text-sm font-semibold text-fb-blue hover:bg-fb-hover"
          @click="showImportModal = true"
        >
          {{ t('common.import') }}
        </button>
        <button type="button" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" @click="openCreate">
          {{ t('common.addNew') }}
        </button>
      </div>
    </div>

    <!-- Instant search bar -->
    <div class="relative w-full max-w-md">
      <input
        v-model="searchQuery"
        type="search"
        :placeholder="t('staff.searchPlaceholder')"
        class="w-full h-11 pl-10 pr-4 rounded-xl border border-fb-line bg-fb-card text-[15px] focus:outline-none focus:border-fb-blue"
      />
      <svg class="absolute left-3.5 top-3 text-fb-secondary" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8" />
        <path d="M21 21l-4.35-4.35" />
      </svg>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">{{ t('common.loading') }}</div>
      <div v-else-if="!filteredRows.length" class="p-8 text-center text-fb-icon">
        {{ rows.length ? t('common.nothingFound') : t('staff.empty') }}
      </div>
      <table v-else class="w-full text-base">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.fullName') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('profile.jobTitle') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('staff.role') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.phone') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filteredRows" :key="row.id" class="cursor-pointer border-b hover:bg-fb-hover/40" @click="openDetail(row.id)">
            <td class="px-5 py-4">{{ row.name }}</td>
            <td class="px-5 py-4">{{ row.job_title }}</td>
            <td class="px-5 py-4">
              {{ staffRoleLabel(row.staff_role, row.staff_role_label) }}<span v-if="row.branch" class="text-fb-secondary"> · {{ row.branch }}</span>
            </td>
            <td class="px-5 py-4">{{ row.phone }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showPanel" class="drawer-wide-shell">
      <div class="drawer-panel-fb">
        <div class="flex items-center justify-between border-b px-6 py-4">
          <h2 class="text-lg font-semibold">{{ panelTitle }}</h2>
          <button type="button" :aria-label="t('common.close')" @click="closePanel">✕</button>
        </div>
        <div v-if="panelLoading" class="p-6 text-fb-secondary">{{ t('common.loading') }}</div>
        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitForm">
          <div class="grid flex-1 content-start gap-5 overflow-y-auto p-6 md:grid-cols-2 xl:grid-cols-3">
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('common.firstName') }}</label>
              <input v-model="form.first_name" :readonly="isReadOnly" required class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('common.lastName') }}</label>
              <input v-model="form.last_name" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('common.phone') }}</label>
              <input v-model="form.phone" :readonly="isReadOnly" required class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('profile.jobTitle') }}</label>
              <input v-model="form.job_title" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('staff.role') }}</label>
              <select
                v-if="!isReadOnly && canEditRole"
                v-model="form.staff_role"
                class="w-full rounded-lg border px-3 py-2"
              >
                <option v-for="r in STAFF_ROLES" :key="r.value" :value="r.value">{{ t(r.label) }}</option>
              </select>
              <input
                v-else
                :value="staffRoleLabel(detailStaff?.staff_role || form.staff_role, detailStaff?.staff_role_label)"
                readonly
                class="w-full rounded-lg border bg-fb-canvas px-3 py-2"
              />
            </div>
            <div v-if="isDirectorRole">
              <label class="mb-1 block text-sm font-medium">{{ t('staff.directorBranch') }}</label>
              <select
                v-if="!isReadOnly && canEditRole"
                v-model="form.branch_id"
                required
                class="w-full rounded-lg border px-3 py-2"
              >
                <option value="">— {{ t('staff.chooseBranch') }} —</option>
                <option v-for="b in branches" :key="b.id" :value="b.id">{{ b.name }}</option>
              </select>
              <input v-else :value="detailStaff?.branch || '—'" readonly class="w-full rounded-lg border bg-fb-canvas px-3 py-2" />
              <p class="mt-1 text-xs text-fb-secondary">
                {{ t('staff.directorHint') }}
              </p>
            </div>
            <div v-if="!isReadOnly">
              <label class="mb-1 block text-sm font-medium">{{ t('login.password') }}</label>
              <input v-model="form.password" type="password" :placeholder="editingStaff ? t('profile.newPasswordPlaceholder') : t('staff.defaultPassword')" class="w-full rounded-lg border px-3 py-2" />
            </div>
            <p v-if="formError" class="col-span-full text-sm text-fb-danger">{{ formError }}</p>
          </div>
          <div class="flex gap-2 border-t px-6 py-4">
            <template v-if="isReadOnly && detailStaff">
              <button type="button" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" @click="startEdit">{{ t('common.edit') }}</button>
              <button v-if="canDeleteStaff" type="button" class="rounded-lg border border-red-300 px-5 py-2 text-sm text-fb-danger" :disabled="deleting" @click="deleteStaff">{{ t('common.delete') }}</button>
            </template>
            <button v-else type="submit" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" :disabled="saving">
              {{ saving ? t('common.saving') : editingStaff ? t('common.save') : t('common.create') }}
            </button>
            <button type="button" class="rounded-lg border px-5 py-2 text-sm" @click="closePanel">{{ t('common.cancel') }}</button>
          </div>
        </form>
      </div>
    </div>

    <ImportCsvModal
      v-model:open="showImportModal"
      :title="t('staff.importTitle')"
      upload-url="/user/staff/import"
      template-filename="staff-import-template.csv"
      :template-header="['first_name', 'last_name', 'phone', 'password', 'job_title', 'staff_role', 'branch']"
      :template-example="['Kamola', 'Yusupova', '901002010', 'demo1234', 'Administrator', 'administrator', '']"
      :columns-help="t('staff.importHelp')"
      @imported="loadRows"
    />
  </div>
</template>
