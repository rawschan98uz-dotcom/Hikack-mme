<script setup lang="ts">
defineProps<{ title: string; note?: string }>();
</script>

<template>
  <div class="bg-fb-card rounded-xl border border-fb-line p-8">
    <h1 class="text-xl font-semibold text-fb-text">{{ title }}</h1>
    <p class="text-fb-secondary mt-3">
      {{ note ?? 'Section not implemented yet. Reference screenshots in captured/sections/.' }}
    </p>
    <p class="text-xs text-fb-icon mt-4">
      Compare with live ModMe at the same route while building this page.
    </p>
  </div>
</template>
