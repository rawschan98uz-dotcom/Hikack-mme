/**
 * Light or dark look of the program. "system" follows Windows / the phone. Remembered on this computer;
 * index.html puts the dark look on before the first paint, this module keeps it in sync afterwards.
 */
import { computed, ref, watch } from 'vue';

export type ThemeChoice = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'ui_theme';
const media = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

function readSaved(): ThemeChoice {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'dark' || saved === 'system' || saved === 'light') return saved;
  } catch {
    // storage blocked: light
  }
  return 'light';
}

export const themeChoice = ref<ThemeChoice>(readSaved());
const systemDark = ref(Boolean(media?.matches));
media?.addEventListener('change', (event) => {
  systemDark.value = event.matches;
});

/** The look actually shown now. */
export const isDark = computed(() => themeChoice.value === 'dark' || (themeChoice.value === 'system' && systemDark.value));

watch(
  isDark,
  (dark) => {
    if (dark) document.documentElement.setAttribute('data-theme', 'dark');
    else document.documentElement.removeAttribute('data-theme');
  },
  { immediate: true },
);

watch(themeChoice, (choice) => {
  try {
    localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    // not remembered, still applied
  }
});

export const THEME_OPTIONS: Array<{ id: ThemeChoice; label: 'theme.light' | 'theme.dark' | 'theme.system' }> = [
  { id: 'light', label: 'theme.light' },
  { id: 'dark', label: 'theme.dark' },
  { id: 'system', label: 'theme.system' },
];
