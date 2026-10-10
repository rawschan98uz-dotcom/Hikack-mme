/**
 * Feedback for the user: short pop-up notices ("Сохранено ✓") and the confirmation window
 * that replaces the browser's grey `confirm()` / `alert()`.
 */
import { reactive } from 'vue';

export type ToastKind = 'success' | 'error' | 'info' | 'warning';

export interface ToastItem {
  id: number;
  kind: ToastKind;
  text: string;
}

const MAX_TOASTS = 4;
let nextToastId = 1;

export const toasts = reactive<ToastItem[]>([]);

export function dismissToast(id: number) {
  const index = toasts.findIndex((item) => item.id === id);
  if (index >= 0) toasts.splice(index, 1);
}

function pushToast(kind: ToastKind, text: string, durationMs: number) {
  if (!text) return;
  // The same notice twice in a row (a double click) is shown once
  const last = toasts[toasts.length - 1];
  if (last && last.kind === kind && last.text === text) {
    dismissToast(last.id);
  }
  const id = nextToastId++;
  toasts.push({ id, kind, text });
  while (toasts.length > MAX_TOASTS) toasts.shift();
  window.setTimeout(() => dismissToast(id), durationMs);
}

export const toast = {
  success: (text: string) => pushToast('success', text, 3500),
  info: (text: string) => pushToast('info', text, 4500),
  warning: (text: string) => pushToast('warning', text, 6000),
  error: (text: string) => pushToast('error', text, 7000),
};

export interface ConfirmOptions {
  title: string;
  message?: string;
  /** Text of the main button; defaults to "Delete" for danger and "OK" otherwise. */
  confirmText?: string;
  cancelText?: string;
  /** A red button — for deleting and other actions that cannot be undone. */
  danger?: boolean;
  /** For the most dangerous actions: the button unlocks only after this word is typed. */
  typeToConfirm?: string;
  /** Show only the main button (an important notice instead of a question). */
  noCancel?: boolean;
}

interface ConfirmState {
  open: boolean;
  options: ConfirmOptions;
  resolve: ((value: boolean) => void) | null;
}

export const confirmState = reactive<ConfirmState>({
  open: false,
  options: { title: '' },
  resolve: null,
});

/** Ask the user; resolves to true only if they pressed the main button. */
export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  // A new question closes the previous one as "no"
  if (confirmState.resolve) confirmState.resolve(false);
  return new Promise<boolean>((resolve) => {
    confirmState.options = options;
    confirmState.resolve = resolve;
    confirmState.open = true;
  });
}

/** An important notice that must be read; resolves when it is closed. */
export async function alertDialog(options: Omit<ConfirmOptions, 'noCancel' | 'danger' | 'typeToConfirm'>): Promise<void> {
  await confirmDialog({ ...options, noCancel: true });
}

export function closeConfirm(answer: boolean) {
  const resolve = confirmState.resolve;
  confirmState.open = false;
  confirmState.resolve = null;
  resolve?.(answer);
}
