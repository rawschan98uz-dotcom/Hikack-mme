<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  count: number;
}>();

const STAR_SIZE = 12;
const MIN_GAP = 8;

const positions = computed(() => {
  const count = Math.max(0, Math.min(props.count, 6));
  if (count === 0) {
    return [];
  }
  if (count === 1) {
    return [{ x: 0, y: 0 }];
  }

  if (count <= 4) {
    const step = STAR_SIZE + MIN_GAP;
    return Array.from({ length: count }, (_, index) => ({
      x: (index - (count - 1) / 2) * step,
      y: 0,
    }));
  }

  const radius = count === 5 ? 27 : 32;
  const spread = count === 5 ? 76 : 92;
  const startAngle = -spread / 2;

  return Array.from({ length: count }, (_, index) => {
    const angle = ((startAngle + (spread / (count - 1)) * index) * Math.PI) / 180;
    return {
      x: Math.sin(angle) * radius,
      y: Math.cos(angle) * radius * 0.22,
    };
  });
});

const containerWidth = computed(() => {
  const count = Math.max(0, Math.min(props.count, 6));
  if (count <= 1) {
    return STAR_SIZE;
  }
  if (count <= 4) {
    return (count - 1) * (STAR_SIZE + MIN_GAP) + STAR_SIZE;
  }
  return count === 5 ? 70 : 83;
});
</script>

<template>
  <div
    v-if="count > 0"
    class="relative"
    :style="{ width: `${containerWidth}px`, height: `${STAR_SIZE}px` }"
    aria-hidden="true"
  >
    <svg
      v-for="(pos, index) in positions"
      :key="index"
      viewBox="0 0 24 24"
      class="absolute left-1/2 top-1/2 fill-white drop-shadow-sm"
      :style="{
        width: `${STAR_SIZE}px`,
        height: `${STAR_SIZE}px`,
        transform: `translate(calc(-50% + ${pos.x}px), calc(-50% + ${pos.y}px))`,
      }"
    >
      <path
        d="M12 2.5l2.47 5.01 5.53.8-4 3.9.94 5.5L12 15.9l-4.94 2.81.94-5.5-4-3.9 5.53-.8L12 2.5z"
      />
    </svg>
  </div>
</template>
