<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import DataTable from '../components/DataTable.vue';
import { t } from '../i18n';

interface SmsRow {
  phone: string;
  message: string;
  status: string;
  sent_at: string;
}

const rows = ref<SmsRow[]>([]);
const loading = ref(true);

const columns = computed(() => [
  { key: 'phone', label: t('common.phone') },
  { key: 'message', label: t('misc.message') },
  { key: 'status', label: t('common.status') },
  { key: 'sent_at', label: t('misc.sentAt') },
]);

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
    <h1 class="text-xl font-semibold text-fb-text">{{ t('misc.smsLog') }}</h1>
    <DataTable :columns="columns" :rows="rows" :loading="loading" />
  </div>
</template>
