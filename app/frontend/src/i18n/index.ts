import { ref, watch } from 'vue';

import { messages, type MessageKey } from './messages';

export type { MessageKey } from './messages';

export const localeOptions = [
  { code: 'uz' as const, short: 'uz', label: 'Oʻzbekcha' },
  { code: 'ru' as const, short: 'ru', label: 'Русский' },
  { code: 'en' as const, short: 'en', label: 'English' },
];

export type LocaleCode = (typeof localeOptions)[number]['code'];

const STORAGE_KEY = 'ui_locale';
const DEFAULT_LOCALE: LocaleCode = 'ru';

function readSavedLocale(): LocaleCode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && localeOptions.some((option) => option.code === saved)) {
      return saved as LocaleCode;
    }
  } catch {
    // Storage may be blocked — fall back to the default language
  }
  return DEFAULT_LOCALE;
}

/** The interface language. Reading it inside a template or computed makes the text follow a switch. */
export const locale = ref<LocaleCode>(readSavedLocale());

watch(
  locale,
  (value) => {
    document.documentElement.lang = value;
    try {
      localStorage.setItem(STORAGE_KEY, value);
    } catch {
      // ignore
    }
  },
  { immediate: true },
);

export function setLocale(next: LocaleCode) {
  locale.value = next;
}

/** Locale for Intl / toLocaleString: month and weekday names follow the interface language. */
export function intlLocale(code: LocaleCode = locale.value): string {
  if (code === 'uz') return 'uz-Latn-UZ';
  if (code === 'ru') return 'ru-RU';
  return 'en-US';
}

export type TParams = Record<string, string | number | null | undefined>;

const pluralRules: Partial<Record<LocaleCode, Intl.PluralRules>> = {};

function pickPlural(text: string, count: number, code: LocaleCode): string {
  const forms = text.split(' | ');
  if (forms.length < 2) return text;
  const rules = (pluralRules[code] ??= new Intl.PluralRules(intlLocale(code)));
  const category = rules.select(count);
  if (code === 'ru') {
    // one: 1, 21 … · few: 2–4, 22–24 … · many: 5–20, 0 …
    if (category === 'one') return forms[0];
    if (category === 'few') return forms[1] ?? forms[0];
    return forms[2] ?? forms[forms.length - 1];
  }
  return category === 'one' ? forms[0] : forms[1];
}

/** Translate a phrase into the current interface language. */
export function t(key: MessageKey, params?: TParams): string {
  const code = locale.value;
  const phrase = messages[key];
  let text: string = phrase ? phrase[code] : key;
  if (params && typeof params.count === 'number') {
    text = pickPlural(text, params.count, code);
  }
  if (params) {
    text = text.replace(/\{(\w+)\}/g, (match, name: string) => {
      const value = params[name];
      return value === undefined || value === null ? match : String(value);
    });
  }
  return text;
}

/** Translate a phrase whose key is only known at run time (a status or role code from the server). */
export function tMaybe(key: string, fallback: string, params?: TParams): string {
  return key in messages ? t(key as MessageKey, params) : fallback;
}
