<script setup lang="ts">
import { onMounted, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface GradeSettings {
  grade_pass_score: number;
  grade_scale_max: number;
}

const settings = ref<GradeSettings>({ grade_pass_score: 70, grade_scale_max: 100 });
const loading = ref(true);
const saving = ref(false);
const message = ref('');

async function load() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<GradeSettings>>('/company/settings');
    settings.value = {
      grade_pass_score: data.data.grade_pass_score,
      grade_scale_max: data.data.grade_scale_max,
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
    <h1 class="text-xl font-semibold text-fb-text">Grade settings</h1>
    <div v-if="loading" class="text-sm text-fb-secondary">Loading…</div>
    <form v-else class="max-w-2xl space-y-4 rounded-xl border border-fb-line bg-fb-card p-6" @submit.prevent="save">
      <div>
        <label class="mb-1 block text-sm font-medium text-fb-secondary">Passing score</label>
        <input v-model.number="settings.grade_pass_score" type="number" min="0" class="w-full rounded-lg border px-3 py-2" />
        <p class="mt-1 text-xs text-fb-secondary">Minimum grade to pass (used in Rating reports).</p>
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium text-fb-secondary">Maximum scale</label>
        <input v-model.number="settings.grade_scale_max" type="number" min="1" class="w-full rounded-lg border px-3 py-2" />
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
