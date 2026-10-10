<script lang="ts">
/** The HiJack LMS sign: an indigo tile with "HJ" and the name next to it. */
// Each sign needs its own gradient id: a hidden copy (e.g. the wide-screen logo on a phone) would hide it
let counter = 0;
</script>

<script setup lang="ts">
const gradientId = `hj-logo-fill-${++counter}`;
withDefaults(defineProps<{ size?: number; withText?: boolean; inverse?: boolean }>(), {
  size: 36,
  withText: true,
  inverse: false,
});
</script>

<template>
  <span class="inline-flex select-none items-center gap-2.5">
    <svg :width="size" :height="size" viewBox="0 0 40 40" aria-hidden="true" class="shrink-0">
      <defs>
        <linearGradient :id="gradientId" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#6366F1" />
          <stop offset="1" stop-color="#4338CA" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" :fill="inverse ? '#FFFFFF' : `url(#${gradientId})`" />
      <path
        d="M11 11v18M11 20h9M20 11v18"
        :stroke="inverse ? '#4F46E5' : '#FFFFFF'"
        stroke-width="3.4"
        stroke-linecap="round"
        fill="none"
      />
      <path
        d="M29 11v12.5a5.5 5.5 0 01-5.5 5.5"
        :stroke="inverse ? '#4F46E5' : '#C7D2FE'"
        stroke-width="3.4"
        stroke-linecap="round"
        fill="none"
      />
    </svg>
    <span v-if="withText" class="whitespace-nowrap leading-none" :style="{ fontSize: `${Math.round(size * 0.62)}px` }">
      <span class="font-bold tracking-tight" :class="inverse ? 'text-white' : 'text-fb-text'">HiJack</span>
      <span class="ml-1 font-medium" :class="inverse ? 'text-indigo-200' : 'text-fb-blue'">LMS</span>
    </span>
  </span>
</template>
