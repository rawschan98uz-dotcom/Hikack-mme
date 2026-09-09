<script setup lang="ts">
defineProps<{ title: string; note?: string }>();
</script>

<template>
  <div class="bg-fb-card rounded-xl border border-fb-line p-8">
    <h1 class="text-xl font-semibold text-fb-text">{{ title }}</h1>
    <p class="text-fb-secondary mt-3">
      {{ note ?? 'This section is currently under development and will be available in an upcoming update.' }}
    </p>
  </div>
</template>
