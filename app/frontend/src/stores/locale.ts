import { defineStore } from 'pinia';
import { ref, watch } from 'vue';

export const localeOptions = [
  { code: 'en' as const, label: 'English' },
  { code: 'ru' as const, label: 'Русский' },
  { code: 'uz' as const, label: "O'zbekcha" },
];

export type LocaleCode = (typeof localeOptions)[number]['code'];

function readSavedLocale(): LocaleCode {
  const saved = localStorage.getItem('ui_locale');
  if (saved && localeOptions.some((option) => option.code === saved)) {
    return saved as LocaleCode;
  }
  return 'en';
}

export const useLocaleStore = defineStore('locale', () => {
  const code = ref<LocaleCode>(readSavedLocale());

  function setLocale(next: LocaleCode) {
    code.value = next;
    localStorage.setItem('ui_locale', next);
    document.documentElement.lang = next;
  }

  watch(
    code,
    (value) => {
      document.documentElement.lang = value;
    },
    { immediate: true },
  );

  return { code, setLocale, options: localeOptions };
});
