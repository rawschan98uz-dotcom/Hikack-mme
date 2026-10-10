<script setup lang="ts">
import { t } from '../i18n';

defineProps<{ title: string; note?: string }>();
</script>

<template>
  <div class="bg-fb-card rounded-xl border border-fb-line p-8">
    <h1 class="text-xl font-semibold text-fb-text">{{ title }}</h1>
    <p class="text-fb-secondary mt-3">
      {{ note ?? t('misc.underDevelopment') }}
    </p>
  </div>
</template>
