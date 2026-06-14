<script setup lang="ts">
import { onMounted, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface SettingsPayload {
  sms_enabled: boolean;
  sms_advance_text: string;
}

const smsEnabled = ref(false);
const smsText = ref('');
const loading = ref(true);
const saving = ref(false);
const message = ref('');

async function load() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<SettingsPayload>>('/company/settings');
    smsEnabled.value = data.data.sms_enabled;
    smsText.value = data.data.sms_advance_text || '';
  } finally {
    loading.value = false;
  }
}

async function save() {
  saving.value = true;
  message.value = '';
  try {
    await client.post('/company/settings', {
      sms_enabled: smsEnabled.value,
      sms_advance_text: smsText.value,
    });
    message.value = 'Saved';
  } catch {
    message.value = 'Save failed';
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-xl font-semibold text-fb-text">Auto-SMS</h1>
    <div v-if="loading" class="text-sm text-fb-secondary">Loading…</div>
    <form v-else class="max-w-2xl space-y-4 rounded-xl border border-fb-line bg-fb-card p-6" @submit.prevent="save">
      <label class="flex items-center gap-3 text-sm text-fb-secondary">
        <input v-model="smsEnabled" type="checkbox" class="rounded border-fb-line" />
        Enable automatic SMS notifications
      </label>
      <div>
        <h2 class="mb-2 text-sm font-medium text-fb-secondary">SMS text: Advance payment notification</h2>
        <textarea v-model="smsText" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm" rows="4" />
      </div>
      <div class="flex items-center gap-3">
        <button type="submit" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" :disabled="saving">
          {{ saving ? 'Saving…' : 'Save' }}
        </button>
        <span v-if="message" class="text-sm text-fb-secondary">{{ message }}</span>
      </div>
    </form>
  </div>
</template>
