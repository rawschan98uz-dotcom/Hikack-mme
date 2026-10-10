<script setup lang="ts">
/**
 * Totals of a money list, big and in colour: money coming in is green with "+", money going out is
 * red with "−". The figures are for the whole filtered period, not only the rows on the screen.
 */
import { formatMoney } from '../utils/money';

export interface MoneyTotalItem {
  label: string;
  value: number;
  /** in — money received (green), out — money paid away (red), neutral — a plain total */
  tone: 'in' | 'out' | 'neutral';
}

defineProps<{ items: MoneyTotalItem[]; note?: string }>();

function shown(item: MoneyTotalItem) {
  const amount = formatMoney(Math.abs(item.value));
  if (item.tone === 'in' && item.value > 0) return `+${amount}`;
  if (item.tone === 'out' && item.value > 0) return `−${amount}`;
  return formatMoney(item.value);
}
</script>

<template>
  <div class="flex flex-wrap items-end gap-x-10 gap-y-3 rounded-xl border border-fb-line bg-fb-card px-5 py-4">
    <div v-for="item in items" :key="item.label">
      <div class="text-xs font-semibold uppercase tracking-wide text-fb-secondary">{{ item.label }}</div>
      <div
        class="mt-1 whitespace-nowrap text-2xl font-bold tabular-nums"
        :class="{
          'text-emerald-600': item.tone === 'in' && item.value > 0,
          'text-red-600': item.tone === 'out' && item.value > 0,
          'text-fb-text': item.tone === 'neutral' || !item.value,
        }"
      >
        {{ shown(item) }}
      </div>
    </div>
    <p v-if="note" class="ml-auto self-center text-sm text-fb-secondary">{{ note }}</p>
  </div>
</template>
