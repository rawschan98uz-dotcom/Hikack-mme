<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import DataTable from '../components/DataTable.vue';
import { t } from '../i18n';

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

const columns = computed(() => [
  { key: 'type', label: t('common.type') },
  { key: 'time', label: t('common.time') },
  { key: 'who', label: t('misc.callWho') },
  { key: 'to_whom', label: t('misc.callToWhom') },
  { key: 'gateway', label: t('misc.callGateway') },
  { key: 'duration', label: t('misc.callDuration') },
  { key: 'result', label: t('misc.callResult') },
]);

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
    <h1 class="text-xl font-semibold text-fb-text">{{ t('misc.callLog') }}</h1>
    <DataTable :columns="columns" :rows="rows" :loading="loading" />
  </div>
</template>
