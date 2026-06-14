<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface ConversionRow {
  id: number;
  full_name: string;
  phone: string;
  stage: string;
  stage_label: string;
  created_at: string;
  incoming: boolean;
  waiting: boolean;
  set: boolean;
  attended: boolean;
  paid: boolean;
}

interface ConversionData {
  pipeline: Record<string, number>;
  rows: ConversionRow[];
}

const STAGES = [
  { key: 'incoming', label: 'Incoming' },
  { key: 'waiting', label: 'Waiting' },
  { key: 'set', label: 'Set' },
  { key: 'attended', label: 'Attended' },
  { key: 'paid', label: 'Paid' },
] as const;

const data = ref<ConversionData | null>(null);
const loading = ref(true);
const filters = reactive({ date_from: '', date_to: '', q: '' });

const pipelineCards = computed(() => {
  if (!data.value) return [];
  const p = data.value.pipeline;
  return STAGES.map((s) => ({ key: s.key, label: s.label, count: p[s.key] ?? 0 }));
});

async function loadData() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();
    const res = await client.get<ApiEnvelope<ConversionData>>('/reports/conversion', { params });
    data.value = res.data.data;
  } finally {
    loading.value = false;
  }
}

onMounted(loadData);
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-fb-text">Conversion reports</h1>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
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
        <input v-model="filters.q" type="search" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm" @keydown.enter="loadData" />
      </div>
      <button type="button" class="rounded-lg border border-fb-line px-4 py-2 text-sm" @click="loadData">Apply</button>
    </div>

    <div v-if="loading" class="text-fb-secondary">Loading…</div>
    <template v-else>
      <div class="grid grid-cols-2 gap-3 md:grid-cols-5">
        <div
          v-for="card in pipelineCards"
          :key="card.key"
          class="rounded-xl border border-fb-line bg-fb-card p-4 text-center"
        >
          <div class="text-2xl font-bold text-fb-blue">{{ card.count }}</div>
          <div class="mt-1 text-sm text-fb-secondary">{{ card.label }}</div>
        </div>
      </div>

      <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
        <div v-if="!data?.rows.length" class="p-8 text-center text-fb-icon">No leads</div>
        <table v-else class="w-full text-sm">
          <thead class="border-b bg-fb-canvas">
            <tr>
              <th class="px-4 py-3 text-left font-semibold text-fb-secondary">Full name</th>
              <th class="px-4 py-3 text-left font-semibold text-fb-secondary">Phone</th>
              <th class="px-4 py-3 text-left font-semibold text-fb-secondary">Stage</th>
              <th v-for="stage in STAGES" :key="stage.key" class="px-3 py-3 text-center font-semibold text-fb-secondary">
                {{ stage.label }}
              </th>
              <th class="px-4 py-3 text-left font-semibold text-fb-secondary">Date</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in data.rows" :key="row.id" class="border-b">
              <td class="px-4 py-3">{{ row.full_name }}</td>
              <td class="px-4 py-3">{{ row.phone }}</td>
              <td class="px-4 py-3">{{ row.stage_label }}</td>
              <td v-for="stage in STAGES" :key="stage.key" class="px-3 py-3 text-center">
                <span v-if="row[stage.key]" class="text-fb-blue">✓</span>
                <span v-else class="text-fb-icon">—</span>
              </td>
              <td class="px-4 py-3">{{ row.created_at }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>
