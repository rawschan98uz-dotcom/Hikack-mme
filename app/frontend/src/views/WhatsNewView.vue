<script setup lang="ts">
import { computed } from 'vue';

import { t } from '../i18n';

const updates = computed(() => [
  { date: '2026-06-10', title: t('news.crossLinksTitle'), body: t('news.crossLinksBody') },
  { date: '2026-06-10', title: t('news.settingsTitle'), body: t('news.settingsBody') },
  { date: '2026-06-09', title: t('news.financeTitle'), body: t('news.financeBody') },
  { date: '2026-06-08', title: t('news.coreTitle'), body: t('news.coreBody') },
]);
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-[28px] font-normal text-fb-text">{{ t('nav.whatsNew') }}</h1>
      <p class="mt-2 text-fb-secondary">
        {{ t('news.subtitle') }}
      </p>
    </div>

    <div class="space-y-4">
      <article
        v-for="item in updates"
        :key="item.title"
        class="rounded-xl border border-fb-line bg-fb-card p-6"
      >
        <time class="text-sm text-fb-icon">{{ item.date }}</time>
        <h2 class="mt-1 text-lg font-semibold text-fb-text">{{ item.title }}</h2>
        <p class="mt-2 text-fb-secondary">{{ item.body }}</p>
      </article>
    </div>
  </div>
</template>
