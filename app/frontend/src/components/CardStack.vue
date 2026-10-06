<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, type Component } from 'vue';

import { useCardStack, type CardKind } from '../utils/cardStack';
import GroupsView from '../views/GroupsView.vue';
import StudentsView from '../views/StudentsView.vue';
import TeachersView from '../views/TeachersView.vue';

// Each card is its own section page shown in "card only" mode, so a card is the same everywhere
const CARD_VIEWS: Record<CardKind, Component> = {
  teacher: TeachersView,
  group: GroupsView,
  student: StudentsView,
};

const { stack, closeTop } = useCardStack();

// The same card keeps its place (and its unsaved form) while other cards open and close above it
const layers = computed(() =>
  stack.value.map((card, index) => ({ card, index, key: `${index}:${card.kind}-${card.id}` })),
);

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape' || event.defaultPrevented || !stack.value.length) return;
  const target = event.target as HTMLElement | null;
  // Esc inside a field belongs to the field (clears a search, closes a date picker)
  if (target?.closest('input, textarea, select')) return;
  // A small window (payment, confirm) is open above the card: Esc must not throw the whole card away
  const top = document.querySelector(`[data-card-layer="${stack.value.length - 1}"]`);
  if (top?.querySelector('.fixed.inset-0')) return;
  closeTop();
}

onMounted(() => document.addEventListener('keydown', onKeydown));
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown));
</script>

<template>
  <div
    v-for="layer in layers"
    :key="layer.key"
    :data-card-layer="layer.index"
    class="fixed left-0 top-0"
    :style="{ zIndex: 70 + layer.index }"
  >
    <component
      :is="CARD_VIEWS[layer.card.kind]"
      :card-id="layer.card.id"
      :card-edit="layer.card.edit"
      :card-level="layer.index"
      @close="closeTop"
    />
  </div>
</template>
