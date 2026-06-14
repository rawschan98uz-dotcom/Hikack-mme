<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import DataTable from '../components/DataTable.vue';
import { useAuthStore } from '../stores/auth';

interface PaymentRow {
  sum: number;
  created_at: string;
}

const auth = useAuthStore();
const rows = ref<PaymentRow[]>([]);
const loading = ref(true);

const companyId = computed(() => auth.user?.company?.id);

const columns = [
  { key: 'sum', label: 'Sum' },
  { key: 'created_at', label: 'Created at' },
];

onMounted(async () => {
  if (!companyId.value) {
    loading.value = false;
    return;
  }
  try {
    const { data } = await client.get<ApiEnvelope<PaymentRow[]>>(
      `/company/${companyId.value}/payments`,
    );
    rows.value = data.data.map((row) => ({
      ...row,
      sum: row.sum.toLocaleString('ru-RU'),
    })) as unknown as PaymentRow[];
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-fb-text">Payment for the platform</h1>
    <p class="text-sm text-fb-secondary">History payments</p>
    <DataTable :columns="columns" :rows="rows" :loading="loading" />
  </div>
</template>
