<script setup lang="ts">
import { onMounted, ref } from 'vue';
import SkeletonBlock from '../components/SkeletonBlock.vue';

import client, { type ApiEnvelope } from '../api/client';
import { t } from '../i18n';
import { toast } from '../ui/feedback';
import { apiErrorMessage } from '../utils/apiError';

interface GradeSettings {
  grade_pass_score: number;
  grade_scale_max: number;
}

const settings = ref<GradeSettings>({ grade_pass_score: 70, grade_scale_max: 100 });
const loading = ref(true);
const saving = ref(false);

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
  try {
    await client.post('/company/settings', settings.value);
    toast.success(t('toast.saved'));
  } catch (err: unknown) {
    toast.error(apiErrorMessage(err, t('errors.saveFailed')));
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-xl font-semibold text-fb-text">{{ t('settings.gradeTitle') }}</h1>
    <SkeletonBlock v-if="loading" variant="lines" :rows="4" />
    <form v-else class="max-w-2xl space-y-4 rounded-xl border border-fb-line bg-fb-card p-6" @submit.prevent="save">
      <div>
        <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('settings.passScore') }}</label>
        <input v-model.number="settings.grade_pass_score" type="number" min="0" step="1" class="w-full rounded-lg border px-3 py-2" />
        <p class="mt-1 text-xs text-fb-secondary">{{ t('settings.passScoreHint') }}</p>
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('settings.scaleMax') }}</label>
        <input v-model.number="settings.grade_scale_max" type="number" min="1" step="1" class="w-full rounded-lg border px-3 py-2" />
      </div>
      <div class="flex items-center gap-3">
        <button type="submit" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" :disabled="saving">
          {{ saving ? t('common.saving') : t('common.save') }}
        </button>
      </div>
    </form>
  </div>
</template>
