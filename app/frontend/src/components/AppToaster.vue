<script setup lang="ts">
import { t } from '../i18n';
import { dismissToast, toasts, type ToastKind } from '../ui/feedback';

const icons: Record<ToastKind, string> = {
  success: 'M5 12.5l4.5 4.5L19 7.5',
  error: 'M12 7v6M12 16.5v.5',
  warning: 'M12 7v6M12 16.5v.5',
  info: 'M12 11v6M12 7.5v.5',
};
</script>

<template>
  <div class="toaster" aria-live="polite" aria-atomic="false">
    <TransitionGroup name="toast">
      <div
        v-for="item in toasts"
        :key="item.id"
        class="toast"
        :class="`toast--${item.kind}`"
        :role="item.kind === 'error' ? 'alert' : 'status'"
      >
        <span class="toast__icon" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path :d="icons[item.kind]" />
          </svg>
        </span>
        <span class="toast__text">{{ item.text }}</span>
        <button type="button" class="toast__close" :aria-label="t('common.close')" @click="dismissToast(item.id)">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toaster {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 210;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
  max-width: min(420px, calc(100vw - 32px));
  pointer-events: none;
}

.toast {
  pointer-events: auto;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 260px;
  padding: 12px 12px 12px 14px;
  border-radius: 12px;
  background: var(--fb-card);
  border: 1px solid var(--fb-line);
  border-left-width: 4px;
  box-shadow: 0 8px 24px rgb(0 0 0 / 0.14);
  color: var(--fb-text);
  font-size: 15px;
  line-height: 1.35;
}

.toast--success { border-left-color: #31a24c; }
.toast--error { border-left-color: var(--fb-danger); }
.toast--warning { border-left-color: #f5a623; }
.toast--info { border-left-color: var(--fb-blue); }

.toast__icon {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 9999px;
  color: #fff;
}

.toast--success .toast__icon { background: #31a24c; }
.toast--error .toast__icon { background: var(--fb-danger); }
.toast--warning .toast__icon { background: #f5a623; }
.toast--info .toast__icon { background: var(--fb-blue); }

.toast__text {
  flex: 1;
  padding-top: 2px;
  white-space: pre-line;
  word-break: break-word;
}

.toast__close {
  flex-shrink: 0;
  padding: 4px;
  border-radius: 6px;
  color: var(--fb-icon);
}

.toast__close:hover {
  background: var(--fb-canvas);
  color: var(--fb-text);
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 200ms var(--fb-ease), transform 200ms var(--fb-ease);
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (prefers-reduced-motion: reduce) {
  .toast-enter-active,
  .toast-leave-active {
    transition: none;
  }
}
</style>
