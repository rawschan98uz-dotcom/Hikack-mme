<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

export interface FilterSelectOption {
  value: string | number;
  label: string;
}

const props = withDefaults(
  defineProps<{
    modelValue: string | number;
    options: FilterSelectOption[];
    placeholder?: string;
  }>(),
  {
    placeholder: 'Select',
  },
);

const emit = defineEmits<{
  'update:modelValue': [value: string | number];
}>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);

const selectedLabel = computed(() => {
  const match = props.options.find((option) => String(option.value) === String(props.modelValue));
  return match?.label ?? '';
});

function choose(value: string | number) {
  emit('update:modelValue', value);
  open.value = false;
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
      <span class="truncate text-sm" :class="selectedLabel ? 'text-fb-text' : 'text-fb-icon'">
        {{ selectedLabel || placeholder }}
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
        :key="String(option.value)"
        type="button"
        class="filter-dropdown-item-fb"
        :class="{ 'is-selected': String(modelValue) === String(option.value) }"
        @click="choose(option.value)"
      >
        <span>{{ option.label }}</span>
        <svg
          v-if="String(modelValue) === String(option.value)"
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
