<script setup lang="ts">
import { onMounted, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface VoipSettings {
  voip_enabled: boolean;
  voip_gateway: string;
  voip_caller_id: string;
}

const settings = ref<VoipSettings>({
  voip_enabled: false,
  voip_gateway: '',
  voip_caller_id: '',
});
const loading = ref(true);
const saving = ref(false);
const message = ref('');

async function load() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<VoipSettings>>('/company/settings');
    settings.value = {
      voip_enabled: data.data.voip_enabled,
      voip_gateway: data.data.voip_gateway || '',
      voip_caller_id: data.data.voip_caller_id || '',
    };
  } finally {
    loading.value = false;
  }
}

async function save() {
  saving.value = true;
  message.value = '';
  try {
    await client.post('/company/settings', settings.value);
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
    <h1 class="text-xl font-semibold text-fb-text">VoIP settings</h1>
    <div v-if="loading" class="text-sm text-fb-secondary">Loading…</div>
    <form v-else class="max-w-2xl space-y-4 rounded-xl border border-fb-line bg-fb-card p-6" @submit.prevent="save">
      <label class="flex items-center gap-3 text-sm text-fb-secondary">
        <input v-model="settings.voip_enabled" type="checkbox" class="rounded border-fb-line" />
        Enable VoIP integration
      </label>
      <div>
        <label class="mb-1 block text-sm font-medium text-fb-secondary">Gateway</label>
        <input v-model="settings.voip_gateway" type="text" placeholder="e.g. Modme VoIP" class="w-full rounded-lg border px-3 py-2" />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium text-fb-secondary">Caller ID</label>
        <input v-model="settings.voip_caller_id" type="text" placeholder="998901234567" class="w-full rounded-lg border px-3 py-2" />
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
