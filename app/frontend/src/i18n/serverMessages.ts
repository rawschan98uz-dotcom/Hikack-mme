/**
 * The server answers in one language (mostly English, sometimes Russian). The phrases users meet
 * most often are translated here; anything unknown is shown as the server sent it.
 */
import { t, type MessageKey } from './index';

const CONTAINS: Array<[string, MessageKey]> = [
  ['Secondary phone must contain at least 9 digits', 'errors.secondPhoneMin9'],
  ['at least 9 digits', 'errors.phoneMin9'],
  ['You do not have permission to perform this action', 'errors.forbidden'],
  ['First name is required', 'errors.enterName'],
  ['Trial / start date is required', 'leads.trialRequired'],
];

export function translateServerMessage(raw: string): string {
  for (const [needle, key] of CONTAINS) {
    if (raw.includes(needle)) return t(key);
  }
  return raw;
}
