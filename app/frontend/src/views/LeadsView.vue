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
  full_name: string;
  phone: string;
  stage: string;
  stage_label: string;
  is_active: boolean;
  created_at: string;
}

const STAGES = [
  { value: 'incoming', label: 'Incoming' },
  { value: 'waiting', label: 'Waiting' },
  { value: 'set', label: 'Set' },
  { value: 'attended', label: 'Attended' },
  { value: 'paid', label: 'Paid' },
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

const filters = reactive({
  stage: '',
  q: '',
  archived: '0',
});

const form = reactive({
  full_name: '',
  phone: '',
  stage: 'incoming' as (typeof STAGES)[number]['value'],
});

const panelTitle = computed(() => (editingLead.value ? 'Lead details' : 'Add lead'));
const canExportLeads = computed(() => auth.can(PERM.LEADS_VIEW));

function exportCsv() {
  downloadCsv(
    'leads.csv',
    ['Name', 'Phone', 'Stage', 'Active', 'Created'],
    rows.value.map((row) => [
      row.full_name,
      row.phone,
      row.stage_label,
      row.is_active ? 'Yes' : 'No',
      row.created_at,
    ]),
  );
}

function resetForm() {
  form.full_name = '';
  form.phone = '';
  form.stage = 'incoming';
  formError.value = '';
  editingLead.value = null;
}

function openPanel(lead?: LeadRow) {
  resetForm();
  if (lead) {
    editingLead.value = lead;
    form.full_name = lead.full_name;
    form.phone = lead.phone;
    form.stage = lead.stage as (typeof STAGES)[number]['value'];
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
  if (!form.full_name.trim()) {
    formError.value = 'Enter lead name';
    return;
  }
  if (!form.phone.trim()) {
    formError.value = 'Enter phone number';
    return;
  }

  saving.value = true;
  try {
    const payload = {
      full_name: form.full_name.trim(),
      phone: form.phone.trim(),
      stage: form.stage,
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

function setStageFilter(stage: string) {
  filters.stage = stage;
}

function applyRouteQuery() {
  if (typeof route.query.stage === 'string') {
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

watch(
  () => [filters.stage, filters.q, filters.archived] as const,
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
      <h1 class="text-xl font-semibold text-fb-text">Leads</h1>
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
          All stages
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
        <div class="min-w-[220px] flex-1">
          <label class="mb-1 block text-sm font-medium text-fb-secondary">Search</label>
          <input
            v-model="filters.q"
            type="search"
            placeholder="Name or phone"
            class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
          />
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
      <div v-else-if="!rows.length" class="p-8 text-center text-fb-icon">
        No leads found. Click “+ Add lead” to create one.
      </div>
      <table v-else class="w-full text-base">
        <thead class="border-b border-fb-line bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Name</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Phone</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Stage</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            class="cursor-pointer border-b border-fb-line hover:bg-fb-hover/40"
            @click="openPanel(row)"
          >
            <td class="px-5 py-4 font-medium text-fb-text">{{ row.full_name }}</td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.phone }}</td>
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
          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Full name</label>
            <input
              v-model="form.full_name"
              type="text"
              required
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Phone</label>
            <input
              v-model="form.phone"
              type="tel"
              required
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Stage</label>
            <select
              v-model="form.stage"
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            >
              <option v-for="stage in STAGES" :key="stage.value" :value="stage.value">
                {{ stage.label }}
              </option>
            </select>
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
  </div>
</template>
