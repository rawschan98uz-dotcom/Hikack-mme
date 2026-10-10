<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { useRememberedFilters } from '../utils/rememberedFilters';
import EmptyState from '../components/EmptyState.vue';
import SkeletonBlock from '../components/SkeletonBlock.vue';
import { t, tMaybe } from '../i18n';
import { confirmDialog, toast } from '../ui/feedback';
import { apiErrorMessage } from '../utils/apiError';
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

const ROLE_OPTIONS = ['', 'student', 'teacher', 'staff'];

function roleLabel(role: string) {
  return tMaybe(`archive.role.${(role || '').toLowerCase()}`, role);
}

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

// Leave the page and come back: the filters are still set
const { isFiltered, reset: resetFilters } = useRememberedFilters('archive', filters);

function resetAndReload() {
  resetFilters();
  void loadRows();
}

const filteredRows = computed(() => {
  const q = filters.q.trim().toLowerCase();
  if (!q) return rows.value;
  const digits = q.replace(/\D/g, '');
  return rows.value.filter((row) => {
    const nameMatch = row.name?.toLowerCase().includes(q);
    const phoneDigits = (row.phone || '').replace(/\D/g, '');
    const phoneMatch = digits ? phoneDigits.includes(digits) : row.phone?.toLowerCase().includes(q);
    const roleMatch = row.roles?.toLowerCase().includes(q);
    const reasonMatch = row.reason?.toLowerCase().includes(q);
    return Boolean(nameMatch || phoneMatch || roleMatch || reasonMatch);
  });
});

let archiveSearchDebounce: ReturnType<typeof setTimeout> | null = null;
watch(
  () => filters.q,
  () => {
    if (archiveSearchDebounce) clearTimeout(archiveSearchDebounce);
    archiveSearchDebounce = setTimeout(() => {
      void loadRows();
    }, 400);
  },
);

watch(
  () => [filters.role, filters.reason, filters.date_from, filters.date_to] as const,
  () => {
    void loadRows();
  },
);

const allSelected = computed(
  () => filteredRows.value.length > 0 && selectedIds.value.length === filteredRows.value.length,
);

function toggleAll() {
  selectedIds.value = allSelected.value ? [] : filteredRows.value.map((row) => row.id);
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
  const count = selectedIds.value.length;
  const ok = action === 'delete'
    ? await confirmDialog({
      title: t('archive.bulkDeleteTitle', { count }),
      message: t('archive.deleteForeverHint'),
      danger: true,
      confirmText: t('archive.deleteForever'),
      typeToConfirm: t('confirm.deleteWord'),
    })
    : await confirmDialog({
      title: t('archive.bulkRestoreTitle', { count }),
      confirmText: t('common.restore'),
    });
  if (!ok) return;

  bulkLoading.value = true;
  try {
    await client.post('/archive/list/bulk', { action, ids: selectedIds.value });
    toast.success(action === 'delete' ? t('archive.deletedCount', { count }) : t('archive.restoredCount', { count }));
    await loadRows();
  } catch (err: unknown) {
    toast.error(apiErrorMessage(err));
  } finally {
    bulkLoading.value = false;
  }
}

async function restoreOne(row: ArchiveRow) {
  const ok = await confirmDialog({
    title: t('archive.restoreTitle', { name: row.name }),
    confirmText: t('common.restore'),
  });
  if (!ok) return;
  try {
    await client.post(`/archive/list/${row.id}/restore`);
    toast.success(t('toast.restored'));
    await loadRows();
  } catch (err: unknown) {
    toast.error(apiErrorMessage(err));
  }
}

async function deleteOne(row: ArchiveRow) {
  const ok = await confirmDialog({
    title: t('archive.deleteTitle', { name: row.name }),
    message: t('archive.deleteForeverHint'),
    danger: true,
    confirmText: t('archive.deleteForever'),
    typeToConfirm: t('confirm.deleteWord'),
  });
  if (!ok) return;
  try {
    await client.delete(`/archive/list/${row.id}`);
    toast.success(t('toast.deleted'));
    await loadRows();
  } catch (err: unknown) {
    toast.error(apiErrorMessage(err, t('errors.deleteFailed')));
  }
}

function exportCsv() {
  downloadCsv(
    'archive.csv',
    [t('common.fullName'), t('common.phone'), t('archive.roles'), t('archive.reason'), t('common.comment'), t('archive.archived')],
    rows.value.map((row) => [row.name, row.phone, roleLabel(row.roles), row.reason, row.comment, row.archived]),
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
        {{ t('nav.archive') }}
        <span class="ml-2 text-base font-normal text-fb-secondary">
          {{ t('archive.quantity', { count: filteredRows.length }) }}<span v-if="filters.q.trim() && rows.length !== filteredRows.length"> ({{ t('archive.ofTotal', { total: quantity }) }})</span>
        </span>
      </h1>
      <button
        type="button"
        class="rounded-lg border border-fb-line px-4 py-2 text-sm"
        @click="showReasons = true"
      >
        {{ t('archive.reasonsTitle') }}
      </button>
    </div>

    <div class="space-y-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div class="flex flex-wrap items-end gap-3">
        <div class="min-w-[220px] flex-1">
          <label class="mb-1 block text-xs text-fb-secondary">{{ t('common.search') }}</label>
          <div class="relative">
            <input
              v-model="filters.q"
              type="search"
              :placeholder="t('archive.searchPlaceholder')"
              class="w-full h-10 pl-9 pr-4 rounded-lg border px-3 py-2 text-sm focus:outline-none focus:border-fb-blue"
              @keydown.enter="loadRows"
            />
            <svg class="absolute left-3 top-2.5 text-fb-secondary" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
          </div>
        </div>
        <div>
          <label class="mb-1 block text-xs text-fb-secondary">{{ t('archive.filterRole') }}</label>
          <select v-model="filters.role" class="rounded-lg border px-3 py-2 text-sm">
            <option value="">{{ t('archive.allRoles') }}</option>
            <option v-for="role in ROLE_OPTIONS.filter(Boolean)" :key="role" :value="role">{{ roleLabel(role) }}</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs text-fb-secondary">{{ t('archive.filterReason') }}</label>
          <select v-model="filters.reason" class="rounded-lg border px-3 py-2 text-sm">
            <option value="">{{ t('archive.allReasons') }}</option>
            <option v-for="reason in reasons" :key="reason.id" :value="reason.name">{{ reason.name }}</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs text-fb-secondary">{{ t('archive.startDate') }}</label>
          <input v-model="filters.date_from" type="date" class="rounded-lg border px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="mb-1 block text-xs text-fb-secondary">{{ t('archive.endDate') }}</label>
          <input v-model="filters.date_to" type="date" class="rounded-lg border px-3 py-2 text-sm" />
        </div>
        <button type="button" class="rounded-lg border px-4 py-2 text-sm" @click="loadRows">{{ t('common.apply') }}</button>
        <button v-if="isFiltered" type="button" class="rounded-lg px-3 py-2 text-sm text-fb-secondary hover:text-fb-danger" @click="resetAndReload">
          ✕ {{ t('empty.resetFilters') }}
        </button>
      </div>

      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          class="rounded-lg border border-red-300 px-3 py-1.5 text-sm text-fb-danger disabled:opacity-40"
          :disabled="!selectedIds.length || bulkLoading"
          @click="bulkAction('delete')"
        >
          {{ t('common.delete') }}
        </button>
        <button
          type="button"
          class="rounded-lg border border-emerald-300 px-3 py-1.5 text-sm text-emerald-700 disabled:opacity-40"
          :disabled="!selectedIds.length || bulkLoading"
          @click="bulkAction('restore')"
        >
          {{ t('common.restore') }}
        </button>
        <button
          v-if="canExportArchive"
          type="button"
          class="ml-auto rounded-lg border px-3 py-1.5 text-sm"
          @click="exportCsv"
        >
          {{ t('common.export') }}
        </button>
      </div>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <SkeletonBlock v-if="loading" :rows="8" :cols="6" />
      <EmptyState
        v-else-if="!filteredRows.length"
        icon="archive"
        :filtered="isFiltered"
        :title="t('archive.emptyTitle')"
        :hint="t('archive.emptyHint')"
        @reset="resetAndReload"
      />
      <table v-else class="w-full text-sm">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-4 py-3 text-left">
              <input type="checkbox" :checked="allSelected" @change="toggleAll" />
            </th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">{{ t('common.fullName') }}</th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">{{ t('common.phone') }}</th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">{{ t('archive.roles') }}</th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">{{ t('archive.reason') }}</th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">{{ t('common.comment') }}</th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">{{ t('archive.archived') }}</th>
            <th class="px-4 py-3 text-left font-semibold text-fb-secondary">{{ t('common.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filteredRows" :key="row.id" class="border-b">
            <td class="px-4 py-3">
              <input type="checkbox" :checked="selectedIds.includes(row.id)" @change="toggleRow(row.id)" />
            </td>
            <td class="px-4 py-3">{{ row.name }}</td>
            <td class="px-4 py-3">{{ row.phone }}</td>
            <td class="px-4 py-3">{{ roleLabel(row.roles) }}</td>
            <td class="px-4 py-3">{{ row.reason }}</td>
            <td class="px-4 py-3">{{ row.comment }}</td>
            <td class="px-4 py-3">{{ row.archived }}</td>
            <td class="px-4 py-3">
              <div class="flex gap-2">
                <button type="button" class="text-emerald-700 hover:underline" @click="restoreOne(row)">{{ t('common.restore') }}</button>
                <button type="button" class="text-fb-danger hover:underline" @click="deleteOne(row)">{{ t('common.delete') }}</button>
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
          <h2 class="text-lg font-semibold">{{ t('archive.reasonsTitle') }}</h2>
          <button type="button" :aria-label="t('common.close')" @click="showReasons = false">✕</button>
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
