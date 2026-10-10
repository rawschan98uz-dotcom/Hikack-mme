/**
 * One phrase in all three interface languages. Keeping the three side by side means a phrase can
 * never be added in one language and forgotten in another — the type check refuses it.
 *
 * Placeholders: `{name}` is replaced by `t('key', { name: '...' })`.
 * Plural forms: separate them with ` | ` and pass `count` — Russian takes three forms
 * (1 урок | 2 урока | 5 уроков), Uzbek and English take two (1 lesson | 5 lessons).
 */
export interface Phrase {
  uz: string;
  ru: string;
  en: string;
}

export function defineMessages<const T extends Record<string, Phrase>>(messages: T): T {
  return messages;
}
