<template>
  <div v-if="show" class="flex items-center justify-between mt-4 px-4">
    <!-- Информация -->
    <span class="text-sm text-gray-600">
      Показано {{ shownCount }} из {{ totalCount }}
    </span>

    <!-- Кнопки -->
    <div class="flex gap-2">
      <button
        v-if="hasPrev"
        @click="$emit('prev')"
        class="px-3 py-1 text-sm border rounded hover:bg-gray-100"
      >
        ← Назад
      </button>

      <button
        v-if="hasMore"
        @click="$emit('next')"
        class="px-3 py-1 text-sm border rounded hover:bg-gray-100"
      >
        Ещё {{ remaining }} →
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  totalCount: number
  shownCount: number
  hasMore: boolean
  currentOffset: number
}>()

defineEmits(['next', 'prev'])

const hasPrev = computed(() => props.currentOffset > 0)
const remaining = computed(() => props.totalCount - props.shownCount - props.currentOffset)
const show = computed(() => props.totalCount > 0)
</script>
