<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';

interface LeadRow {
  id: number;
  full_name: string;
  phone: string;
  stage: string;
  stage_label: string;
  is_active: boolean;
  created_at: string;
}

interface LeadsReport {
  total: number;
  active: number;
  by_stage: Record<string, number>;
  rows: LeadRow[];
}

const STAGES = [
  { value: '', label: 'All stages' },
  { value: 'incoming', label: 'Incoming' },
  { value: 'waiting', label: 'Waiting' },
  { value: 'set', label: 'Set' },
  { value: 'attended', label: 'Attended' },
  { value: 'paid', label: 'Paid' },
] as const;

const router = useRouter();

const report = ref<LeadsReport | null>(null);
const loading = ref(true);
const filters = reactive({ stage: '', date_from: '', date_to: '', q: '', active: '1' });

const stageCards = computed(() => {
  if (!report.value) return [];
  return STAGES.filter((s) => s.value).map((s) => ({
    key: s.value,
    label: s.label,
    count: report.value?.by_stage[s.value] ?? 0,
  }));
});

async function loadReport() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.stage) params.stage = filters.stage;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();
    if (filters.active) params.active = filters.active;
    const { data } = await client.get<ApiEnvelope<LeadsReport>>('/reports/leads', { params });
    report.value = data.data;
  } finally {
    loading.value = false;
  }
}

function openLeads() {
  router.push('/leads');
}

onMounted(loadReport);
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-fb-text">Leads reports</h1>
      <button type="button" class="text-sm text-fb-blue hover:underline" @click="openLeads">All leads →</button>
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">Stage</label>
        <select v-model="filters.stage" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option v-for="s in STAGES" :key="s.value || 'all'" :value="s.value">{{ s.label }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">From</label>
        <input v-model="filters.date_from" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">To</label>
        <input v-model="filters.date_to" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div class="min-w-[180px] flex-1">
        <label class="mb-1 block text-xs text-fb-secondary">Search</label>
        <input v-model="filters.q" type="search" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm" @keydown.enter="loadReport" />
      </div>
      <button type="button" class="rounded-lg border border-fb-line px-4 py-2 text-sm" @click="loadReport">Apply</button>
    </div>

    <div v-if="loading" class="text-fb-secondary">Loading…</div>
    <template v-else-if="report">
      <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div class="rounded-xl border bg-fb-card p-6">
          <div class="text-sm text-fb-secondary">Total leads</div>
          <div class="mt-2 text-3xl font-bold text-fb-text">{{ report.total }}</div>
        </div>
        <div class="rounded-xl border bg-fb-card p-6">
          <div class="text-sm text-fb-secondary">Active leads</div>
          <div class="mt-2 text-3xl font-bold text-fb-blue">{{ report.active }}</div>
        </div>
        <div class="rounded-xl border bg-fb-card p-6">
          <div class="mb-3 text-sm text-fb-secondary">By stage</div>
          <div v-for="card in stageCards" :key="card.key" class="flex justify-between py-1 text-sm">
            <span class="text-fb-secondary">{{ card.label }}</span>
            <span class="font-medium">{{ card.count }}</span>
          </div>
        </div>
      </div>

      <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
        <div v-if="!report.rows.length" class="p-8 text-center text-fb-icon">No leads</div>
        <table v-else class="w-full text-base">
          <thead class="border-b bg-fb-canvas">
            <tr>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Full name</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Phone</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Stage</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Date</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in report.rows" :key="row.id" class="border-b">
              <td class="px-5 py-4">{{ row.full_name }}</td>
              <td class="px-5 py-4">{{ row.phone }}</td>
              <td class="px-5 py-4">{{ row.stage_label }}</td>
              <td class="px-5 py-4">{{ row.created_at }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
