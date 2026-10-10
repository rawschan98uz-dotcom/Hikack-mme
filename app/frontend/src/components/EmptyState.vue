<script setup lang="ts">
/**
 * An empty list that explains itself: "No groups yet — [Create the first group]" instead of a blank
 * table; and when filters hide everything — "Nothing found — [Reset filters]".
 */
import NavIcon from './NavIcon.vue';
import { t } from '../i18n';

withDefaults(
  defineProps<{
    /** A menu icon name (students, groups, …) shown in the circle */
    icon?: string;
    title: string;
    hint?: string;
    /** Main button, e.g. "Create the first group"; hidden when empty (no right to create) */
    actionLabel?: string;
    /** The list is empty only because of filters or search */
    filtered?: boolean;
    /** Show "Reset filters" for a filtered list */
    canReset?: boolean;
    /** Smaller paddings — inside a card or a side panel */
    compact?: boolean;
  }>(),
  { icon: '', hint: '', actionLabel: '', filtered: false, canReset: true, compact: false },
);

const emit = defineEmits<{ action: []; reset: [] }>();
</script>

<template>
  <div class="flex flex-col items-center justify-center text-center" :class="compact ? 'px-4 py-8' : 'px-6 py-14'">
    <span
      class="flex items-center justify-center rounded-full bg-fb-canvas text-fb-icon"
      :class="compact ? 'h-12 w-12' : 'h-16 w-16'"
      aria-hidden="true"
    >
      <svg v-if="filtered || !icon" :width="compact ? 22 : 28" :height="compact ? 22 : 28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
        <template v-if="filtered">
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-4-4M8.5 11h5" />
        </template>
        <template v-else>
          <path d="M3 13l3-8h12l3 8v6a1 1 0 01-1 1H4a1 1 0 01-1-1z" />
          <path d="M3 13h5l1 2h6l1-2h5" />
        </template>
      </svg>
      <NavIcon v-else :name="icon" :size="compact ? 22 : 28" />
    </span>
    <p class="mt-4 font-semibold text-fb-text" :class="compact ? 'text-[15px]' : 'text-[17px]'">
      {{ filtered ? t('empty.filteredTitle') : title }}
    </p>
    <p v-if="filtered || hint" class="mt-1 max-w-md text-[14px] text-fb-secondary">
      {{ filtered ? t('empty.filteredHint') : hint }}
    </p>
    <button
      v-if="filtered && canReset"
      type="button"
      class="mt-4 rounded-lg border border-fb-line bg-fb-card px-4 py-2 text-sm font-medium text-fb-text hover:border-fb-blue hover:text-fb-blue"
      @click="emit('reset')"
    >
      {{ t('empty.resetFilters') }}
    </button>
    <button
      v-else-if="!filtered && actionLabel"
      type="button"
      class="mt-4 rounded-lg bg-fb-blue px-4 py-2 text-sm font-semibold text-white hover:bg-fb-blue-dark"
      @click="emit('action')"
    >
      + {{ actionLabel }}
    </button>
    <slot />
  </div>
</template>
