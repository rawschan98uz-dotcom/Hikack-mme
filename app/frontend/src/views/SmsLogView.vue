<script setup lang="ts">
import { onMounted, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import DataTable from '../components/DataTable.vue';

interface SmsRow {
  phone: string;
  message: string;
  status: string;
  sent_at: string;
}

const rows = ref<SmsRow[]>([]);
const loading = ref(true);

const columns = [
  { key: 'phone', label: 'Phone' },
  { key: 'message', label: 'Message' },
  { key: 'status', label: 'Status' },
  { key: 'sent_at', label: 'Sent at' },
];

onMounted(async () => {
  try {
    const { data } = await client.get<ApiEnvelope<SmsRow[]>>('/sms/report');
    rows.value = data.data;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-fb-text">Sent SMS log</h1>
    <DataTable :columns="columns" :rows="rows" :loading="loading" />
  </div>
</template>
