/**
 * Ready-made values the office picks with one click (a lead's source, whose second phone, a level).
 * The value is saved as it always was (in Russian), so the records stay in one language;
 * only the button text follows the interface language.
 */
import { t, type MessageKey } from './index';

export interface Preset {
  value: string;
  label?: MessageKey;
}

export const LEAD_SOURCES: Preset[] = [
  { value: 'Instagram' },
  { value: 'Telegram' },
  { value: 'Звонок', label: 'preset.sourceCall' },
  { value: 'Рекомендация', label: 'preset.sourceReferral' },
  { value: 'Наружка', label: 'preset.sourceOutdoor' },
  { value: 'Сайт', label: 'preset.sourceWebsite' },
  { value: 'Другое', label: 'preset.sourceOther' },
];

export const PHONE_OWNERS: Preset[] = [
  { value: 'Мама', label: 'preset.ownerMother' },
  { value: 'Отец', label: 'preset.ownerFather' },
  { value: 'Брат', label: 'preset.ownerBrother' },
  { value: 'Сестра', label: 'preset.ownerSister' },
  { value: 'Бабушка', label: 'preset.ownerGrandmother' },
  { value: 'Дедушка', label: 'preset.ownerGrandfather' },
  { value: 'Родственник', label: 'preset.ownerRelative' },
];

/** Quick buttons for the second phone: the most common owners. */
export const PHONE_OWNER_BUTTONS = PHONE_OWNERS.filter((p) => ['Мама', 'Отец', 'Брат', 'Сестра', 'Родственник'].includes(p.value));

export const LANGUAGE_LEVELS: Preset[] = [
  { value: 'Beginner (A1)' },
  { value: 'Elementary (A2)' },
  { value: 'Pre-Intermediate' },
  { value: 'Intermediate (B1)' },
  { value: 'Upper-Intermediate (B2)' },
  { value: 'Advanced (C1)' },
  { value: 'IELTS / Экзамен', label: 'preset.levelIelts' },
];

export const MATH_LEVELS: Preset[] = [
  { value: '1-4 классы', label: 'preset.levelGrades14' },
  { value: '5-8 классы', label: 'preset.levelGrades58' },
  { value: '9-11 классы', label: 'preset.levelGrades911' },
  { value: 'ОГЭ / ЕГЭ / ДТМ', label: 'preset.levelExams' },
  { value: 'Олимпиадная', label: 'preset.levelOlympiad' },
];

export const GENERAL_LEVELS: Preset[] = [
  { value: 'Начальный (Beginner)', label: 'preset.levelBeginner' },
  { value: 'Базовый (Elementary)', label: 'preset.levelElementary' },
  { value: 'Средний (Intermediate)', label: 'preset.levelIntermediate' },
  { value: 'Продвинутый (Advanced)', label: 'preset.levelAdvanced' },
  { value: 'Экзамен / Тест', label: 'preset.levelTest' },
];

const ALL_PRESETS = [...LEAD_SOURCES, ...PHONE_OWNERS, ...LANGUAGE_LEVELS, ...MATH_LEVELS, ...GENERAL_LEVELS];

/** A saved value as the interface shows it ("Мама" → "Onasi" / "Mother"); typed-in text stays as it is. */
export function presetLabel(value: string | null | undefined): string {
  if (!value) return '';
  const preset = ALL_PRESETS.find((p) => p.value === value);
  return preset?.label ? t(preset.label) : value;
}
