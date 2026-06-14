<script setup lang="ts">
import CourseLevelStars from './CourseLevelStars.vue';

defineProps<{
  label: string;
  color: string;
  starCount: number;
}>();
</script>

<template>
  <div
    class="course-level-badge relative flex size-full flex-col items-center justify-center rounded-full border border-fb-line shadow-fb-card"
    :style="{ backgroundColor: color }"
  >
    <div class="absolute inset-[5%] rounded-full border-[2.5px] border-white/95" />
    <span
      class="relative -rotate-12 select-none text-[clamp(24px,23cqw,42px)] font-bold italic leading-none text-white"
    >
      {{ label }}
    </span>
    <div class="relative mt-[6%]">
      <CourseLevelStars :count="starCount" />
    </div>
  </div>
</template>

<style scoped>
.course-level-badge {
  container-type: inline-size;
}
</style>
