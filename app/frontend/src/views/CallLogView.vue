<script setup lang="ts">
import { onMounted, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import DataTable from '../components/DataTable.vue';

interface CallRow {
  type: string;
  time: string;
  who: string;
  to_whom: string;
  gateway: string;
  duration: string;
  result: string;
}

const rows = ref<CallRow[]>([]);
const loading = ref(true);

const columns = [
  { key: 'type', label: 'Type' },
  { key: 'time', label: 'Time' },
  { key: 'who', label: 'Who' },
  { key: 'to_whom', label: 'To whom' },
  { key: 'gateway', label: 'Gateway' },
  { key: 'duration', label: 'Duration' },
  { key: 'result', label: 'Result' },
];

onMounted(async () => {
  try {
    const { data } = await client.get<ApiEnvelope<CallRow[]>>('/call/logs');
    rows.value = data.data;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-fb-text">Call log</h1>
    <DataTable :columns="columns" :rows="rows" :loading="loading" />
  </div>
</template>
