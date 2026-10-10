<script setup lang="ts">
/**
 * Grey placeholder bars while data loads: the page keeps its shape instead of a blank space or the
 * word "Loading", so it feels faster and nothing jumps when the data arrives.
 */
import { t } from '../i18n';

withDefaults(
  defineProps<{
    /** table — rows of a list; cards — tiles of a grid; detail — a card with photo and facts; lines — text */
    variant?: 'table' | 'cards' | 'detail' | 'lines';
    rows?: number;
    cols?: number;
  }>(),
  { variant: 'table', rows: 6, cols: 4 },
);

// Fixed "random" widths: bars of different length look like text, and they do not flicker
const WIDTHS = [72, 54, 86, 63, 45, 78, 58, 90, 50, 67];
function width(row: number, col: number) {
  return `${WIDTHS[(row * 3 + col * 7) % WIDTHS.length]}%`;
}
</script>

<template>
  <div role="status" aria-busy="true" :aria-label="t('common.loading')">
    <span class="sr-only">{{ t('common.loading') }}</span>

    <div v-if="variant === 'table'">
      <div
        v-for="row in rows"
        :key="row"
        class="flex items-center gap-5 border-b border-fb-line px-5 py-4 last:border-b-0"
      >
        <span class="sk h-9 w-9 shrink-0 rounded-full" />
        <span class="sk h-3.5 w-1/5 min-w-[90px]" :style="{ maxWidth: '220px' }" />
        <span v-for="col in cols - 1" :key="col" class="flex-1">
          <span class="sk block h-3.5" :style="{ width: width(row, col) }" />
        </span>
      </div>
    </div>

    <div v-else-if="variant === 'cards'" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <div v-for="row in rows" :key="row" class="rounded-xl border border-fb-line bg-fb-card p-5">
        <span class="sk block h-4" :style="{ width: width(row, 1) }" />
        <span class="sk mt-3 block h-3" :style="{ width: width(row, 2) }" />
        <span class="sk mt-2 block h-3" :style="{ width: width(row, 3) }" />
        <span class="sk mt-5 block h-8 w-1/3" />
      </div>
    </div>

    <div v-else-if="variant === 'detail'" class="p-6">
      <div class="flex items-center gap-5">
        <span class="sk h-24 w-24 shrink-0 rounded-full" />
        <div class="flex-1">
          <span class="sk block h-6 w-1/3" />
          <span class="sk mt-3 block h-4 w-24" />
          <span class="sk mt-3 block h-4 w-40" />
        </div>
      </div>
      <div class="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div v-for="tile in 6" :key="tile" class="rounded-xl border border-fb-line p-4">
          <span class="sk block h-3 w-1/3" />
          <span class="sk mt-3 block h-5" :style="{ width: width(tile, 2) }" />
        </div>
      </div>
      <div class="mt-6 space-y-3">
        <span v-for="line in rows" :key="line" class="sk block h-3.5" :style="{ width: width(line, 4) }" />
      </div>
    </div>

    <div v-else class="space-y-3 p-2">
      <span v-for="line in rows" :key="line" class="sk block h-3.5" :style="{ width: width(line, 5) }" />
    </div>
  </div>
</template>

<style scoped>
.sk {
  background: linear-gradient(90deg, var(--fb-canvas) 25%, var(--fb-line) 37%, var(--fb-canvas) 63%);
  background-size: 400% 100%;
  animation: sk-shimmer 1.4s ease infinite;
}
.sk:not(.rounded-full) {
  border-radius: 6px;
}
@keyframes sk-shimmer {
  0% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0 50%;
  }
}
@media (prefers-reduced-motion: reduce) {
  .sk {
    animation: none;
  }
}
</style>
