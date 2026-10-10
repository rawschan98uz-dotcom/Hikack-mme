<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import DataTable from '../components/DataTable.vue';
import { t } from '../i18n';

interface LogRow {
  action: string;
  actor: string;
  created_at: string;
}

const rows = ref<LogRow[]>([]);
const loading = ref(true);

const columns = computed(() => [
  { key: 'action', label: t('misc.action') },
  { key: 'actor', label: t('layout.user') },
  { key: 'created_at', label: t('common.date') },
]);

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
    <h1 class="text-xl font-semibold text-fb-text">{{ t('misc.activityLogs') }}</h1>
    <DataTable :columns="columns" :rows="rows" :loading="loading" />
  </div>
</template>
