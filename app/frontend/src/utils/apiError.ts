import { t } from '../i18n';
import { translateServerMessage } from '../i18n/serverMessages';

interface ErrorBody {
  message?: unknown;
  error?: unknown;
  detail?: unknown;
  errors?: unknown;
}

function firstText(value: unknown): string {
  if (!value) return '';
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return firstText(value[0]);
  if (typeof value === 'object') {
    for (const inner of Object.values(value as Record<string, unknown>)) {
      const text = firstText(inner);
      if (text) return text;
    }
  }
  return '';
}

/** The server's explanation of a failed request (in the interface language when we know the phrase). */
export function apiErrorMessage(error: unknown, fallback?: string): string {
  const response = (error as { response?: { status?: number; data?: ErrorBody } })?.response;
  const data = response?.data;
  const raw = firstText(data?.message) || firstText(data?.error) || firstText(data?.detail) || firstText(data?.errors);
  if (raw) return translateServerMessage(raw);
  if (!response) {
    // No answer at all: the server is off or the internet is down
    return t('errors.network');
  }
  if (response.status === 403) return t('errors.forbidden');
  return fallback ?? t('errors.generic');
}
