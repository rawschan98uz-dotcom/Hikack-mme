<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';
import { downloadCsv } from '../utils/csvExport';
import { hasCreateFlag, routeWithoutCreate } from '../utils/crossLinks';

interface LeadRow {
  id: number;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  phone2?: string;
  address?: string;
  comment?: string;
  stage: string;
  stage_label: string;
  status?: string;
  status_label?: string;
  trial_date?: string | null;
  is_active: boolean;
  created_at: string;
}

interface Branch {
  id: number;
  name: string;
}

interface GroupOption {
  id: number;
  name: string;
  branch_id: number;
}

const STAGES = [
  { value: 'trial_booked', label: 'Записан на пробный' },
  { value: 'attended', label: 'Был на уроке (Думает)' },
  { value: 'rejected', label: 'Отказ / Архив' },
] as const;

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const rows = ref<LeadRow[]>([]);
const loading = ref(true);
const saving = ref(false);
const archiving = ref(false);
const showPanel = ref(false);
const formError = ref('');
const editingLead = ref<LeadRow | null>(null);
const showFilters = ref(true);

const showConvertModal = ref(false);
const converting = ref(false);
const convertError = ref('');
const branches = ref<Branch[]>([]);
const groups = ref<GroupOption[]>([]);

const convertForm = reactive({
  first_name: '',
  last_name: '',
  phone: '',
  phone2: '',
  address: '',
  comment: '',
  branch_id: 0,
  group_id: '' as number | '',
  status: 1,
  trial_date: '',
});

const filteredConvertGroups = computed(() => {
  if (!convertForm.branch_id) return groups.value;
  return groups.value.filter((g) => g.branch_id === convertForm.branch_id);
});

const filters = reactive({
  stage: '',
  q: '',
  archived: '0',
});

const filteredRows = computed(() => {
  let list = rows.value;
  if (filters.stage) {
    list = list.filter((r) => r.stage === filters.stage);
  }
  const q = filters.q.trim().toLowerCase();
  if (!q) return list;
  const digits = q.replace(/\D/g, '');
  return list.filter((r) => {
    const nameMatch =
      r.full_name?.toLowerCase().includes(q) ||
      r.first_name?.toLowerCase().includes(q) ||
      r.last_name?.toLowerCase().includes(q);
    const phoneDigits1 = (r.phone || '').replace(/\D/g, '');
    const phoneDigits2 = (r.phone2 || '').replace(/\D/g, '');
    const phoneMatch = digits
      ? phoneDigits1.includes(digits) || phoneDigits2.includes(digits)
      : (r.phone && r.phone.toLowerCase().includes(q)) || (r.phone2 && r.phone2.toLowerCase().includes(q));
    const commentMatch = r.comment?.toLowerCase().includes(q);
    return Boolean(nameMatch || phoneMatch || commentMatch);
  });
});

const quantity = computed(() => filteredRows.value.length);
const totalQuantity = computed(() => rows.value.length);

const form = reactive({
  first_name: '',
  last_name: '',
  phone: '',
  phone2: '',
  address: '',
  comment: '',
  stage: 'trial_booked' as (typeof STAGES)[number]['value'],
  trial_date: new Date().toISOString().slice(0, 10),
});

const panelTitle = computed(() => (editingLead.value ? 'Lead details' : 'Add lead'));
const canExportLeads = computed(() => auth.can(PERM.LEADS_VIEW));

function exportCsv() {
  downloadCsv(
    'leads.csv',
    ['First name', 'Last name', 'Full name', 'Phone', 'Phone 2', 'Address', 'Comment', 'Trial date', 'Status', 'Active', 'Created'],
    rows.value.map((row) => [
      row.first_name || '',
      row.last_name || '',
      row.full_name,
      row.phone,
      row.phone2 || '',
      row.address || '',
      row.comment || '',
      row.trial_date || '',
      row.stage_label,
      row.is_active ? 'Yes' : 'No',
      row.created_at,
    ]),
  );
}

function resetForm() {
  form.first_name = '';
  form.last_name = '';
  form.phone = '';
  form.phone2 = '';
  form.address = '';
  form.comment = '';
  form.stage = 'trial_booked';
  form.trial_date = new Date().toISOString().slice(0, 10);
  formError.value = '';
  editingLead.value = null;
}

function openPanel(lead?: LeadRow) {
  resetForm();
  if (lead) {
    editingLead.value = lead;
    form.first_name = lead.first_name || (lead.full_name ? lead.full_name.split(' ')[0] : '');
    form.last_name = lead.last_name || (lead.full_name ? lead.full_name.split(' ').slice(1).join(' ') : '');
    form.phone = lead.phone;
    form.phone2 = lead.phone2 || '';
    form.address = lead.address || '';
    form.comment = lead.comment || '';
    form.stage = lead.stage as (typeof STAGES)[number]['value'];
    form.trial_date = lead.trial_date ? lead.trial_date.slice(0, 10) : new Date().toISOString().slice(0, 10);
  }
  showPanel.value = true;
}

function closePanel() {
  showPanel.value = false;
  formError.value = '';
  editingLead.value = null;
}

async function loadLeads() {
  loading.value = true;
  try {
    const params: Record<string, string> = {
      archived: filters.archived,
    };
    if (filters.stage) params.stage = filters.stage;
    if (filters.q.trim()) params.q = filters.q.trim();

    const { data } = await client.get<ApiEnvelope<LeadRow[]>>('/leads', { params });
    rows.value = data.data;
  } finally {
    loading.value = false;
  }
}

async function saveLead() {
  formError.value = '';
  if (!form.first_name.trim()) {
    formError.value = 'Enter first name';
    return;
  }
  if (!form.phone.trim()) {
    formError.value = 'Enter phone number';
    return;
  }

  saving.value = true;
  try {
    const payload = {
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      full_name: `${form.first_name.trim()} ${form.last_name.trim()}`.trim(),
      phone: form.phone.trim(),
      phone2: form.phone2.trim(),
      address: form.address.trim(),
      comment: form.comment.trim(),
      stage: form.stage,
      trial_date: form.trial_date || null,
    };

    if (editingLead.value) {
      await client.patch(`/leads/${editingLead.value.id}`, payload);
    } else {
      await client.post('/leads', payload);
    }

    await loadLeads();
    closePanel();
  } catch {
    formError.value = editingLead.value ? 'Could not update lead' : 'Could not create lead';
  } finally {
    saving.value = false;
  }
}

async function archiveLead() {
  if (!editingLead.value) return;

  archiving.value = true;
  try {
    await client.post(`/leads/${editingLead.value.id}/archive`);
    await loadLeads();
    closePanel();
  } catch {
    formError.value = 'Could not archive lead';
  } finally {
    archiving.value = false;
  }
}

async function restoreLead() {
  if (!editingLead.value) return;

  saving.value = true;
  try {
    await client.patch(`/leads/${editingLead.value.id}`, { is_active: true });
    await loadLeads();
    closePanel();
  } catch {
    formError.value = 'Could not restore lead';
  } finally {
    saving.value = false;
  }
}

async function loadBranchAndGroupOptions() {
  if (branches.value.length) return;
  try {
    const [bRes, gRes] = await Promise.all([
      client.get<ApiEnvelope<Branch[]>>('/branch'),
      client.get<ApiEnvelope<GroupOption[]>>('/groups'),
    ]);
    branches.value = bRes.data.data;
    groups.value = gRes.data.data;
    if (branches.value.length && !convertForm.branch_id) {
      convertForm.branch_id = branches.value[0].id;
    }
  } catch {
    // ignore
  }
}

async function openConvertModal() {
  if (!editingLead.value) return;
  convertForm.first_name = (form.first_name || editingLead.value.first_name || '').trim();
  convertForm.last_name = (form.last_name || editingLead.value.last_name || '').trim();
  if (!convertForm.first_name && editingLead.value.full_name) {
    const nameParts = editingLead.value.full_name.trim().split(' ');
    convertForm.first_name = nameParts[0] || '';
    convertForm.last_name = nameParts.slice(1).join(' ') || '';
  }
  convertForm.phone = form.phone || editingLead.value.phone;
  convertForm.phone2 = form.phone2 || editingLead.value.phone2 || '';
  convertForm.address = form.address || editingLead.value.address || '';
  convertForm.comment = form.comment || editingLead.value.comment || '';
  convertForm.group_id = '';
  convertForm.status = 1;
  convertForm.trial_date = form.trial_date || (editingLead.value.trial_date ? editingLead.value.trial_date.slice(0, 10) : new Date().toISOString().slice(0, 10));

  await loadBranchAndGroupOptions();
  if (branches.value.length && !convertForm.branch_id) {
    convertForm.branch_id = branches.value[0].id;
  }
  showConvertModal.value = true;
}

function closeConvertModal() {
  showConvertModal.value = false;
  convertError.value = '';
}

async function handleConvert() {
  if (!editingLead.value) return;
  convertError.value = '';

  if (!convertForm.first_name.trim()) {
    convertError.value = 'First name is required';
    return;
  }
  if (!convertForm.phone.trim()) {
    convertError.value = 'Phone number is required';
    return;
  }
  if (!convertForm.branch_id) {
    convertError.value = 'Branch is required';
    return;
  }

  converting.value = true;
  try {
    const payload = {
      first_name: convertForm.first_name.trim(),
      last_name: convertForm.last_name.trim(),
      phone: convertForm.phone.trim(),
      phone2: convertForm.phone2.trim(),
      address: convertForm.address.trim(),
      comment: convertForm.comment.trim(),
      branch_id: convertForm.branch_id,
      group_id: convertForm.group_id || null,
      status: convertForm.status,
      trial_date: convertForm.trial_date || null,
    };

    const convertedLeadId = editingLead.value.id;
    const res = await client.post<{ data: { student: { id: number } } }>(
      `/leads/${convertedLeadId}/convert`,
      payload,
    );
    const createdStudentId = res.data.data?.student?.id;

    rows.value = rows.value.filter((r) => r.id !== convertedLeadId);
    closeConvertModal();
    closePanel();
    await loadLeads();

    if (createdStudentId) {
      router.push({ path: '/students', query: { open: String(createdStudentId) } });
    }
  } catch (err: unknown) {
    const response = (err as { response?: { data?: { message?: string } } }).response;
    convertError.value = response?.data?.message || 'Could not convert lead to student';
  } finally {
    converting.value = false;
  }
}

function setStageFilter(stage: string) {
  filters.stage = stage;
}

function applyRouteQuery() {
  if (typeof route.query.status === 'string') {
    filters.stage = route.query.status;
  } else if (typeof route.query.stage === 'string') {
    filters.stage = route.query.stage;
  }
  if (typeof route.query.q === 'string') {
    filters.q = route.query.q;
  }
}

function syncQueryToRoute() {
  const query: Record<string, string> = {};
  if (filters.stage) query.stage = filters.stage;
  if (filters.q.trim()) query.q = filters.q.trim();
  if (filters.archived === '1') query.archived = '1';
  router.replace({ path: '/leads', query });
}

function maybeCreateFromRoute() {
  if (!hasCreateFlag(route.query) || showPanel.value) return;
  openPanel();
  router.replace(routeWithoutCreate(route));
}

watch(
  () => route.query.create,
  () => {
    maybeCreateFromRoute();
  },
);

let leadSearchDebounce: ReturnType<typeof setTimeout> | null = null;
watch(
  () => filters.q,
  (newQ) => {
    if (newQ.trim() === String(route.query.q ?? '').trim()) return;
    if (leadSearchDebounce) clearTimeout(leadSearchDebounce);
    leadSearchDebounce = setTimeout(() => {
      syncQueryToRoute();
      void loadLeads();
    }, 400);
  },
);

watch(
  () => [filters.stage, filters.archived] as const,
  () => {
    syncQueryToRoute();
    void loadLeads();
  },
);

onMounted(async () => {
  applyRouteQuery();
  await loadLeads();
  maybeCreateFromRoute();
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-baseline gap-3">
        <h1 class="text-xl font-semibold text-fb-text">Leads</h1>
        <span v-if="!loading" class="text-sm text-fb-secondary">
          Quantity — {{ quantity }}<span v-if="filters.q.trim() && totalQuantity !== quantity"> (of {{ totalQuantity }})</span>
        </span>
      </div>
      <div class="flex flex-wrap gap-2">
        <button
          v-if="canExportLeads"
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
          @click="exportCsv"
        >
          Export
        </button>
        <button
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
          @click="showFilters = !showFilters"
        >
          {{ showFilters ? 'Hide filters' : 'Show filters' }}
        </button>
        <button
          type="button"
          class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          @click="openPanel()"
        >
          + Add lead
        </button>
      </div>
    </div>

    <div v-if="showFilters" class="rounded-xl border border-fb-line bg-fb-card p-4 space-y-4">
      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          class="rounded-full px-3 py-1.5 text-sm transition-colors"
          :class="!filters.stage
            ? 'bg-fb-hover font-medium text-fb-blue'
            : 'bg-fb-canvas text-fb-secondary hover:text-fb-text'"
          @click="setStageFilter('')"
        >
          All statuses
        </button>
        <button
          v-for="stage in STAGES"
          :key="stage.value"
          type="button"
          class="rounded-full px-3 py-1.5 text-sm transition-colors"
          :class="filters.stage === stage.value
            ? 'bg-fb-hover font-medium text-fb-blue'
            : 'bg-fb-canvas text-fb-secondary hover:text-fb-text'"
          @click="setStageFilter(stage.value)"
        >
          {{ stage.label }}
        </button>
      </div>

      <div class="flex flex-wrap items-end gap-3">
        <div class="min-w-[240px] flex-1">
          <label class="mb-1 block text-sm font-medium text-fb-secondary">Search</label>
          <div class="relative">
            <input
              v-model="filters.q"
              type="search"
              placeholder="Search by name, phone, or comment…"
              class="w-full rounded-lg border border-fb-line pl-9 pr-4 py-2 focus:border-fb-blue focus:outline-none"
            />
            <svg class="absolute left-3 top-2.5 text-fb-secondary" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
          </div>
        </div>
        <div>
          <label class="mb-1 block text-sm font-medium text-fb-secondary">View</label>
          <select
            v-model="filters.archived"
            class="rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
          >
            <option value="0">Active leads</option>
            <option value="1">Archived</option>
            <option value="all">All</option>
          </select>
        </div>
      </div>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!filteredRows.length" class="p-8 text-center text-fb-icon">
        {{ rows.length ? 'No leads match your search.' : 'No leads found. Click “+ Add lead” to create one.' }}
      </div>
      <table v-else class="w-full text-base">
        <thead class="border-b border-fb-line bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Name</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Phone</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Address</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Comment</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Trial date</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Status</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Record</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in filteredRows"
            :key="row.id"
            class="cursor-pointer border-b border-fb-line hover:bg-fb-hover/40"
            @click="openPanel(row)"
          >
            <td class="px-5 py-4 font-medium text-fb-text">{{ row.full_name }}</td>
            <td class="px-5 py-4 text-fb-secondary">
              <div>{{ row.phone }}</div>
              <div v-if="row.phone2" class="text-xs text-fb-icon">{{ row.phone2 }}</div>
            </td>
            <td class="px-5 py-4 text-fb-secondary max-w-[160px] truncate" :title="row.address">
              {{ row.address || '—' }}
            </td>
            <td class="px-5 py-4 text-fb-secondary max-w-[180px] truncate" :title="row.comment">
              {{ row.comment || '—' }}
            </td>
            <td class="px-5 py-4 text-fb-secondary font-medium whitespace-nowrap">
              {{ row.trial_date || '—' }}
            </td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.stage_label }}</td>
            <td class="px-5 py-4">
              <span
                class="rounded-full px-2.5 py-0.5 text-xs font-medium"
                :class="row.is_active ? 'bg-green-50 text-green-700' : 'bg-fb-canvas text-fb-secondary'"
              >
                {{ row.is_active ? 'Active' : 'Archived' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closePanel" />
      <aside class="drawer-panel-fb max-w-md">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-5">
          <h2 class="text-[22px] font-semibold text-fb-text">{{ panelTitle }}</h2>
          <button
            type="button"
            class="text-2xl leading-none text-fb-icon hover:text-fb-secondary"
            @click="closePanel"
          >
            ×
          </button>
        </div>

        <form class="flex-1 space-y-5 overflow-y-auto px-6 py-6" @submit.prevent="saveLead">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-2 block text-[15px] font-medium text-fb-secondary">First name</label>
              <input
                v-model="form.first_name"
                type="text"
                required
                class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Last name</label>
              <input
                v-model="form.last_name"
                type="text"
                class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Phone</label>
            <input
              v-model="form.phone"
              type="tel"
              required
              placeholder="e.g. 90 123 45 67"
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Second phone (optional)</label>
            <input
              v-model="form.phone2"
              type="tel"
              placeholder="Additional phone number"
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Address</label>
            <input
              v-model="form.address"
              type="text"
              placeholder="e.g. Tashkent, Chilanzar"
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Comments</label>
            <textarea
              v-model="form.comment"
              rows="3"
              placeholder="Add notes or comments about lead..."
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            ></textarea>
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Status</label>
            <select
              v-model="form.stage"
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            >
              <option v-for="stage in STAGES" :key="stage.value" :value="stage.value">
                {{ stage.label }}
              </option>
            </select>
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Trial lesson date (Дата пробного урока)</label>
            <input
              v-model="form.trial_date"
              type="date"
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <p v-if="editingLead" class="text-sm text-fb-icon">
            Created: {{ editingLead.created_at.slice(0, 10) }}
          </p>

          <p v-if="formError" class="text-[15px] text-fb-danger">{{ formError }}</p>

          <div class="flex flex-wrap gap-2">
            <button
              type="submit"
              class="rounded-full bg-fb-blue px-8 py-3 text-[16px] font-semibold text-white hover:opacity-90 disabled:opacity-60"
              :disabled="saving"
            >
              {{ saving ? 'Saving…' : editingLead ? 'Save changes' : 'Create lead' }}
            </button>

            <button
              v-if="editingLead"
              type="button"
              class="rounded-full bg-emerald-600 px-6 py-3 text-[15px] font-semibold text-white hover:bg-emerald-700 disabled:opacity-60 flex items-center gap-1.5"
              @click="openConvertModal"
            >
              <span>🎓</span> Convert to student
            </button>

            <button
              v-if="editingLead && editingLead.is_active"
              type="button"
              class="rounded-full border border-red-300 px-6 py-3 text-[15px] font-medium text-fb-danger hover:bg-red-50 disabled:opacity-60"
              :disabled="archiving"
              @click="archiveLead"
            >
              {{ archiving ? 'Archiving…' : 'Archive' }}
            </button>

            <button
              v-if="editingLead && !editingLead.is_active"
              type="button"
              class="rounded-full border border-fb-line px-6 py-3 text-[15px] font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue disabled:opacity-60"
              :disabled="saving"
              @click="restoreLead"
            >
              Restore
            </button>
          </div>
        </form>
      </aside>
    </div>

    <!-- Convert to Student Modal -->
    <div v-if="showConvertModal" class="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/50" @click="closeConvertModal" />
      <div class="relative w-full max-w-lg rounded-2xl border border-fb-line bg-fb-card shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-4 bg-fb-canvas">
          <div>
            <h3 class="text-lg font-bold text-fb-text flex items-center gap-2">
              <span>🎓</span> Convert lead to student
            </h3>
            <p class="text-xs text-fb-secondary mt-0.5">
              Transfers lead entirely to students and removes from leads.
            </p>
          </div>
          <button type="button" class="text-2xl leading-none text-fb-icon hover:text-fb-secondary" @click="closeConvertModal">
            ×
          </button>
        </div>

        <form class="flex-1 overflow-y-auto p-6 space-y-4" @submit.prevent="handleConvert">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">First name</label>
              <input
                v-model="convertForm.first_name"
                type="text"
                required
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Last name</label>
              <input
                v-model="convertForm.last_name"
                type="text"
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              />
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Phone</label>
              <input
                v-model="convertForm.phone"
                type="tel"
                required
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Second phone</label>
              <input
                v-model="convertForm.phone2"
                type="tel"
                placeholder="Optional"
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">Address</label>
            <input
              v-model="convertForm.address"
              type="text"
              placeholder="e.g. Tashkent, Chilanzar"
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">Comments</label>
            <textarea
              v-model="convertForm.comment"
              rows="2"
              placeholder="Student notes..."
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            ></textarea>
          </div>

          <div class="border-t border-fb-line pt-3 grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Branch *</label>
              <select
                v-model="convertForm.branch_id"
                required
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              >
                <option v-for="b in branches" :key="b.id" :value="b.id">
                  {{ b.name }}
                </option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Group</label>
              <select
                v-model="convertForm.group_id"
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              >
                <option value="">— No group —</option>
                <option v-for="g in filteredConvertGroups" :key="g.id" :value="g.id">
                  {{ g.name }}
                </option>
              </select>
            </div>
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">Trial lesson date (Дата старта / пробного урока)</label>
            <input
              v-model="convertForm.trial_date"
              type="date"
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            />
          </div>

          <p v-if="convertError" class="text-sm text-fb-danger">{{ convertError }}</p>

          <div class="flex justify-end gap-2 pt-2 border-t border-fb-line">
            <button
              type="button"
              class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:bg-fb-canvas"
              @click="closeConvertModal"
            >
              Cancel
            </button>
            <button
              type="submit"
              class="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60 flex items-center gap-1.5"
              :disabled="converting"
            >
              <span v-if="converting">Converting…</span>
              <span v-else>Confirm & Convert</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
