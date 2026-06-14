<script setup lang="ts">
import { ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { useSchedule } from '../composables/useSchedule';
import { groupRoute } from '../utils/crossLinks';
import SchedulePanel from './SchedulePanel.vue';

const open = ref(false);
const router = useRouter();
const { rows, loading, loadSchedule } = useSchedule();

watch(open, (isOpen) => {
  if (isOpen) {
    void loadSchedule();
  }
});

function toggleDrawer() {
  open.value = !open.value;
}

function openDrawer() {
  open.value = true;
}

function closeDrawer() {
  open.value = false;
}

defineExpose({ open: openDrawer, close: closeDrawer, toggle: toggleDrawer });

function onSelectGroup(groupId: number) {
  closeDrawer();
  router.push(groupRoute(groupId));
}
</script>

<template>
  <div class="schedule-drawer-root">
    <button
      type="button"
      class="schedule-fab"
      :class="{ 'schedule-fab--open': open }"
      title="Schedule"
      aria-label="Open schedule"
      @click="toggleDrawer"
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="4" y="5" width="16" height="15" rx="2" stroke="currentColor" stroke-width="1.5" />
        <path d="M8 3v4M16 3v4M4 10h16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
      </svg>
    </button>

    <Transition name="schedule-drawer">
      <aside
        v-if="open"
        class="schedule-drawer"
        aria-label="Group schedule"
      >
        <SchedulePanel
          :rows="rows"
          :loading="loading"
          :show-title="false"
          @select-group="onSelectGroup"
        />
      </aside>
    </Transition>

    <Transition name="schedule-backdrop">
      <div
        v-if="open"
        class="schedule-backdrop"
        aria-hidden="true"
        @click="closeDrawer"
      />
    </Transition>
  </div>
</template>

<style scoped>
.schedule-drawer-root {
  pointer-events: none;
}

.schedule-fab,
.schedule-drawer,
.schedule-backdrop {
  pointer-events: auto;
}

.schedule-fab {
  position: fixed;
  right: 0;
  top: 50%;
  z-index: 45;
  display: flex;
  height: 44px;
  width: 36px;
  translate: 0 -50%;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--fb-line);
  border-right: none;
  border-radius: 6px 0 0 6px;
  background: var(--fb-card);
  color: var(--fb-blue);
  box-shadow: -2px 0 8px rgb(0 0 0 / 0.06);
  transition:
    background-color 0.2s ease,
    box-shadow 0.2s ease,
    color 0.2s ease;
}

.schedule-fab:hover {
  background: var(--fb-hover);
  color: var(--fb-blue-dark);
  box-shadow: -3px 0 12px rgb(0 0 0 / 0.1);
}

.schedule-fab--open {
  z-index: 47;
  border-color: var(--fb-blue);
  box-shadow: -3px 0 14px rgb(24 119 242 / 0.15);
}

.schedule-backdrop {
  position: fixed;
  inset: 72px 36px 0 128px;
  z-index: 44;
  background: rgb(0 0 0 / 0.12);
}

.schedule-drawer {
  position: fixed;
  top: 72px;
  right: 36px;
  bottom: 0;
  left: 128px;
  z-index: 46;
  width: auto;
  overflow-y: auto;
  border-left: 1px solid var(--fb-line);
  background: var(--fb-card);
  box-shadow: -8px 0 24px rgb(0 0 0 / 0.08);
}

.schedule-drawer-enter-active,
.schedule-drawer-leave-active {
  transition: transform 0.25s ease;
}

.schedule-drawer-enter-from,
.schedule-drawer-leave-to {
  transform: translateX(100%);
}

.schedule-backdrop-enter-active,
.schedule-backdrop-leave-active {
  transition: opacity 0.2s ease;
}

.schedule-backdrop-enter-from,
.schedule-backdrop-leave-to {
  opacity: 0;
}
</style>
