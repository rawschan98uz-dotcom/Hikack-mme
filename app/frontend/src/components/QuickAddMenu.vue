<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';

import NavIcon from './NavIcon.vue';

export interface QuickAddMenuItem {
  label: string;
  path: string;
  query?: Record<string, string>;
  icon: 'plus' | 'pay' | 'leads' | 'teachers' | 'groups' | 'students' | 'courses' | 'reminders';
}

const props = defineProps<{
  items: QuickAddMenuItem[];
  open: boolean;
}>();

const emit = defineEmits<{
  'update:open': [value: boolean];
  select: [item: QuickAddMenuItem];
}>();

const root = ref<HTMLElement | null>(null);

function toggle() {
  emit('update:open', !props.open);
}

function close() {
  emit('update:open', false);
}

function onSelect(item: QuickAddMenuItem) {
  close();
  emit('select', item);
}

function onDocumentClick(event: MouseEvent) {
  if (!props.open) return;
  const target = event.target as Node | null;
  if (root.value && target && !root.value.contains(target)) {
    close();
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick);
});

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick);
});

watch(
  () => props.items,
  () => {
    if (props.open) close();
  },
);

defineExpose({ close });
</script>

<template>
  <div ref="root" class="relative">
    <button
      type="button"
      class="quick-add-trigger flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-fb-line bg-fb-card p-0 text-fb-icon hover:border-fb-blue hover:text-fb-blue"
      :class="open ? 'is-open' : ''"
      title="Quick add"
      aria-haspopup="menu"
      :aria-expanded="open"
      @click.stop="toggle"
    >
      <svg
        class="block shrink-0"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
      >
        <path d="M12 5v14" />
        <path d="M5 12h14" />
      </svg>
    </button>

    <Transition name="quick-add-pop">
      <div
        v-if="open"
        class="quick-add-menu absolute left-0 top-[calc(100%+10px)] z-[100] min-w-[220px] rounded-md border border-fb-line bg-fb-card py-2 shadow-fb"
        role="menu"
      >
        <button
          v-for="item in items"
          :key="item.label"
          type="button"
          role="menuitem"
          class="flex w-full items-center gap-3 px-4 py-2.5 text-left text-[15px] text-fb-secondary hover:bg-fb-canvas hover:text-fb-blue"
          @click="onSelect(item)"
        >
          <span class="flex h-6 w-6 shrink-0 items-center justify-center text-fb-icon">
            <svg
              v-if="item.icon === 'plus'"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.75"
            >
              <circle cx="12" cy="12" r="9" />
              <path d="M12 8v8M8 12h8" />
            </svg>
            <svg
              v-else-if="item.icon === 'pay'"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.75"
            >
              <path d="M12 3v18" />
              <path d="M8 7c0-2 2-3 4-3s4 1 4 3-2 3-4 3-4-1-4-3z" />
              <path d="M8 17c0 2 2 3 4 3s4-1 4-3-2-3-4-3-4 1-4 3z" />
            </svg>
            <NavIcon v-else :name="item.icon" :size="20" />
          </span>
          <span>{{ item.label }}</span>
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.quick-add-trigger {
  transition:
    transform var(--fb-motion-normal) var(--fb-ease),
    background-color var(--fb-motion-fast) var(--fb-ease),
    border-color var(--fb-motion-fast) var(--fb-ease),
    color var(--fb-motion-fast) var(--fb-ease);
}

.quick-add-trigger svg {
  display: block;
  transition: transform var(--fb-motion-normal) var(--fb-ease);
}

.quick-add-menu::before {
  content: '';
  position: absolute;
  top: -7px;
  left: 14px;
  width: 12px;
  height: 12px;
  background: var(--fb-card);
  border-left: 1px solid var(--fb-line);
  border-top: 1px solid var(--fb-line);
  transform: rotate(45deg);
}
</style>
