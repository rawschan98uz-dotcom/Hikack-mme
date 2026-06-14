<script setup lang="ts">
import { onMounted, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import DataTable from '../components/DataTable.vue';

interface LogRow {
  action: string;
  actor: string;
  created_at: string;
}

const rows = ref<LogRow[]>([]);
const loading = ref(true);

const columns = [
  { key: 'action', label: 'Action' },
  { key: 'actor', label: 'User' },
  { key: 'created_at', label: 'Date' },
];

onMounted(async () => {
  try {
    const { data } = await client.get<ApiEnvelope<LogRow[]>>('/history/logs');
    rows.value = data.data;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-fb-text">Activity logs</h1>
    <DataTable :columns="columns" :rows="rows" :loading="loading" />
  </div>
</template>
