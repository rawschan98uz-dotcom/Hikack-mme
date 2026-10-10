<script setup lang="ts">
import AppConfirmDialog from './components/AppConfirmDialog.vue';
import AppToaster from './components/AppToaster.vue';
</script>

<template>
  <RouterView />
  <AppConfirmDialog />
  <AppToaster />
</template>
