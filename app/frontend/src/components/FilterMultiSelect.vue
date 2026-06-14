<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

export interface FilterOption {
  value: number;
  label: string;
}

const props = withDefaults(
  defineProps<{
    modelValue: number[];
    options: FilterOption[];
    placeholder?: string;
    maxVisibleTags?: number;
  }>(),
  {
    placeholder: 'Select',
    maxVisibleTags: 1,
  },
);

const emit = defineEmits<{
  'update:modelValue': [value: number[]];
}>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);

const selectedOptions = computed(() =>
  props.options.filter((option) => props.modelValue.includes(option.value)),
);

const visibleTags = computed(() => selectedOptions.value.slice(0, props.maxVisibleTags));
const hiddenCount = computed(() => Math.max(0, selectedOptions.value.length - props.maxVisibleTags));

function toggle(value: number) {
  const next = props.modelValue.includes(value)
    ? props.modelValue.filter((item) => item !== value)
    : [...props.modelValue, value];
  emit('update:modelValue', next);
}

function removeTag(value: number, event: Event) {
  event.stopPropagation();
  emit(
    'update:modelValue',
    props.modelValue.filter((item) => item !== value),
  );
}

function onDocumentClick(event: MouseEvent) {
  if (!root.value?.contains(event.target as Node)) {
    open.value = false;
  }
}

onMounted(() => document.addEventListener('click', onDocumentClick));
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick));
</script>

<template>
  <div ref="root" class="relative min-w-[140px] flex-1">
    <button
      type="button"
      class="filter-control-fb w-full"
      :class="{ 'border-fb-blue ring-1 ring-fb-blue/30': open }"
      @click.stop="open = !open"
    >
      <span class="flex min-h-[22px] flex-1 flex-wrap items-center gap-1.5 text-left">
        <template v-if="selectedOptions.length">
          <span
            v-for="tag in visibleTags"
            :key="tag.value"
            class="inline-flex max-w-[120px] items-center gap-1 rounded-md bg-fb-canvas px-2 py-0.5 text-xs text-fb-text"
          >
            <span class="truncate">{{ tag.label }}</span>
            <button
              type="button"
              class="shrink-0 rounded-full p-0.5 text-fb-icon hover:bg-fb-line hover:text-fb-secondary"
              @click="removeTag(tag.value, $event)"
            >
              ×
            </button>
          </span>
          <span
            v-if="hiddenCount"
            class="rounded-md bg-fb-canvas px-2 py-0.5 text-xs text-fb-secondary"
          >
            + {{ hiddenCount }}
          </span>
        </template>
        <span v-else class="text-sm text-fb-icon">{{ placeholder }}</span>
      </span>
      <svg
        class="h-4 w-4 shrink-0 text-fb-icon transition-transform"
        :class="{ 'rotate-180': open }"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fill-rule="evenodd"
          d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.94a.75.75 0 111.08 1.04l-4.24 4.5a.75.75 0 01-1.08 0l-4.24-4.5a.75.75 0 01.02-1.06z"
          clip-rule="evenodd"
        />
      </svg>
    </button>

    <div v-if="open" class="filter-dropdown-fb">
      <button
        v-for="option in options"
        :key="option.value"
        type="button"
        class="filter-dropdown-item-fb"
        :class="{ 'is-selected': modelValue.includes(option.value) }"
        @click="toggle(option.value)"
      >
        <span>{{ option.label }}</span>
        <svg
          v-if="modelValue.includes(option.value)"
          class="h-4 w-4 text-fb-blue"
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fill-rule="evenodd"
            d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
            clip-rule="evenodd"
          />
        </svg>
      </button>
    </div>
  </div>
</template>
