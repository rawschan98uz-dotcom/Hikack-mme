<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { t } from '../i18n';
import { closeConfirm, confirmState } from '../ui/feedback';

const typed = ref('');
const cancelButton = ref<HTMLButtonElement | null>(null);
const confirmButton = ref<HTMLButtonElement | null>(null);
const typeInput = ref<HTMLInputElement | null>(null);

const options = computed(() => confirmState.options);
const confirmLabel = computed(
  () => options.value.confirmText || (options.value.danger ? t('common.delete') : t('common.ok')),
);
// Case and apostrophes do not matter: "o'chirish" typed for "OʻCHIRISH" is accepted
function normalizeWord(value: string) {
  return value.toLowerCase().replace(/\p{Lm}|[^\p{L}\p{N}]/gu, '');
}

const locked = computed(() => {
  const word = options.value.typeToConfirm;
  return Boolean(word) && normalizeWord(typed.value) !== normalizeWord(word!);
});

watch(
  () => confirmState.open,
  async (open) => {
    if (!open) return;
    typed.value = '';
    await nextTick();
    // Dangerous questions start on "Cancel" so a stray Enter does not delete anything
    if (options.value.typeToConfirm) typeInput.value?.focus();
    else if (options.value.danger && !options.value.noCancel) cancelButton.value?.focus();
    else confirmButton.value?.focus();
  },
);

function onConfirm() {
  if (locked.value) return;
  closeConfirm(true);
}

function onCancel() {
  closeConfirm(false);
}

// Esc closes the question as "no" and must not also close the page's own window underneath
function onKeydown(event: KeyboardEvent) {
  if (!confirmState.open || event.key !== 'Escape') return;
  event.stopPropagation();
  event.preventDefault();
  onCancel();
}

onMounted(() => window.addEventListener('keydown', onKeydown, true));
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown, true));
</script>

<template>
  <Transition name="dialog">
    <div
      v-if="confirmState.open"
      class="dialog-backdrop"
      @click.self="onCancel"
    >
      <div
        class="dialog"
        role="alertdialog"
        aria-modal="true"
        :aria-labelledby="'confirm-title'"
      >
        <div class="flex items-start gap-4">
          <span class="dialog__icon" :class="options.danger ? 'dialog__icon--danger' : 'dialog__icon--info'" aria-hidden="true">
            <svg v-if="options.danger" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 9v4M12 17h.01" />
              <path d="M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
            </svg>
            <svg v-else width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 11v5M12 8h.01" />
            </svg>
          </span>
          <div class="min-w-0 flex-1">
            <h2 id="confirm-title" class="text-[18px] font-semibold leading-snug text-fb-text">{{ options.title }}</h2>
            <p v-if="options.message" class="mt-2 whitespace-pre-line text-[15px] leading-relaxed text-fb-secondary">
              {{ options.message }}
            </p>
            <label v-if="options.typeToConfirm" class="mt-4 block text-[14px] text-fb-secondary">
              {{ t('confirm.typeToConfirm', { word: options.typeToConfirm }) }}
              <input
                ref="typeInput"
                v-model="typed"
                type="text"
                class="input-fb mt-1.5"
                autocomplete="off"
                @keydown.enter.prevent="onConfirm"
              />
            </label>
          </div>
        </div>
        <div class="mt-6 flex justify-end gap-2">
          <button
            v-if="!options.noCancel"
            ref="cancelButton"
            type="button"
            class="btn-fb-secondary"
            @click="onCancel"
          >
            {{ options.cancelText || t('common.cancel') }}
          </button>
          <button
            ref="confirmButton"
            type="button"
            class="dialog__confirm"
            :class="options.danger ? 'dialog__confirm--danger' : 'dialog__confirm--primary'"
            :disabled="locked"
            @click="onConfirm"
          >
            {{ confirmLabel }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: rgb(0 0 0 / 0.45);
}

.dialog {
  width: 100%;
  max-width: 460px;
  padding: 24px;
  border-radius: 14px;
  background: var(--fb-card);
  box-shadow: 0 20px 50px rgb(0 0 0 / 0.25);
}

.dialog__icon {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 9999px;
}

.dialog__icon--danger {
  background: #fde8eb;
  color: var(--fb-danger);
}

.dialog__icon--info {
  background: var(--fb-hover);
  color: var(--fb-blue);
}

.dialog__confirm {
  border-radius: 8px;
  padding: 8px 18px;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
}

.dialog__confirm:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.dialog__confirm--primary {
  background: var(--fb-blue);
}

.dialog__confirm--primary:not(:disabled):hover {
  background: var(--fb-blue-dark);
}

.dialog__confirm--danger {
  background: var(--fb-danger);
}

.dialog__confirm--danger:not(:disabled):hover {
  background: #c8102e;
}

.dialog-enter-active,
.dialog-leave-active {
  transition: opacity 160ms var(--fb-ease);
}

.dialog-enter-active .dialog,
.dialog-leave-active .dialog {
  transition: transform 160ms var(--fb-ease);
}

.dialog-enter-from,
.dialog-leave-to {
  opacity: 0;
}

.dialog-enter-from .dialog,
.dialog-leave-to .dialog {
  transform: scale(0.96);
}

@media (prefers-reduced-motion: reduce) {
  .dialog-enter-active,
  .dialog-leave-active,
  .dialog-enter-active .dialog,
  .dialog-leave-active .dialog {
    transition: none;
  }
}
</style>
