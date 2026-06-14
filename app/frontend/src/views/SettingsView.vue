<script setup lang="ts">
import { onMounted, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface SettingsData {
  name: string;
  phone: string;
  address: string;
  timezone: string;
  currency: string;
  balance_mode: number;
  sms_enabled: boolean;
  tabs: string[];
}

const settings = ref<SettingsData | null>(null);
const activeTab = ref('General settings');
const loading = ref(true);
const saving = ref(false);
const message = ref('');

const paymentModes = [
  { value: 1, label: 'Daily' },
  { value: 2, label: 'Monthly' },
  { value: 3, label: 'Group start' },
  { value: 4, label: 'Full course' },
  { value: 5, label: 'Module' },
  { value: 6, label: 'Individual' },
];

async function load() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<SettingsData>>('/company/settings');
    settings.value = data.data;
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (!settings.value) return;
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
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-fb-text">General settings</h1>

    <div v-if="loading" class="text-fb-secondary">Loading…</div>

    <template v-else-if="settings">
      <div class="flex flex-wrap gap-2 border-b border-fb-line pb-2">
        <button
          v-for="tab in settings.tabs"
          :key="tab"
          type="button"
          class="px-3 py-1.5 rounded-lg text-sm"
          :class="activeTab === tab ? 'bg-fb-hover text-fb-blue font-medium' : 'text-fb-secondary hover:bg-fb-canvas'"
          @click="activeTab = tab"
        >
          {{ tab }}
        </button>
      </div>

      <div v-if="activeTab === 'General settings'" class="bg-fb-card rounded-xl border border-fb-line p-6 space-y-4 max-w-xl">
        <div>
          <label class="block text-sm font-medium text-fb-secondary mb-1">Center name</label>
          <input v-model="settings.name" class="w-full rounded-lg border px-3 py-2" />
        </div>
        <div>
          <label class="block text-sm font-medium text-fb-secondary mb-1">Phone</label>
          <input v-model="settings.phone" class="w-full rounded-lg border px-3 py-2" />
        </div>
        <div>
          <label class="block text-sm font-medium text-fb-secondary mb-1">Address</label>
          <input v-model="settings.address" class="w-full rounded-lg border px-3 py-2" />
        </div>
        <div>
          <label class="block text-sm font-medium text-fb-secondary mb-1">Payment mode</label>
          <select v-model.number="settings.balance_mode" class="w-full rounded-lg border px-3 py-2">
            <option v-for="m in paymentModes" :key="m.value" :value="m.value">{{ m.label }}</option>
          </select>
        </div>
        <label class="flex items-center gap-2 text-sm">
          <input v-model="settings.sms_enabled" type="checkbox" />
          SMS enabled
        </label>
        <div class="flex items-center gap-3">
          <button
            type="button"
            class="px-4 py-2 rounded-lg bg-fb-blue text-white text-sm font-medium disabled:opacity-60"
            :disabled="saving"
            @click="save"
          >
            Save
          </button>
          <span v-if="message" class="text-sm text-fb-secondary">{{ message }}</span>
        </div>
      </div>

      <div v-else class="bg-fb-card rounded-xl border border-fb-line p-8 text-fb-secondary">
        Tab «{{ activeTab }}» — configure using screenshot
        <code class="text-xs">captured/sections/settings.png</code>
      </div>
    </template>
  </div>
</template>
