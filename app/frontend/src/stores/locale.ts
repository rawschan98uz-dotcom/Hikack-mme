import { defineStore } from 'pinia';

import { locale, localeOptions, setLocale, type LocaleCode } from '../i18n';

export { localeOptions, type LocaleCode };

/** The interface language; the phrases themselves live in `src/i18n`. */
export const useLocaleStore = defineStore('locale', () => {
  return { code: locale, setLocale, options: localeOptions };
});
