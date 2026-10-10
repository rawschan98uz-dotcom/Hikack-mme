/**
 * Filters are remembered while the program is open (this browser tab): pick a filter, go to another
 * page, come back — the filter is still there. A link that carries its own filters (a dashboard
 * tile, "debtors of this group") always wins over the remembered ones. Signing out forgets them all.
 *
 * Two kinds of pages:
 *  - lists that keep their filters in the address (students, leads): the router puts the
 *    remembered address back when the page is opened from the menu (`rememberedQueryFor`);
 *  - lists with filters only on the page: `useRememberedFilters(page, filters)`.
 */
import { computed, watch } from 'vue';
import type { LocationQuery, RouteLocationNormalized, RouteLocationRaw } from 'vue-router';

import { useAuthStore } from '../stores/auth';

const PREFIX = 'filters:';
/** Address parts that are not filters: open cards and one-time actions. */
const NOT_FILTERS = ['cards', 'open', 'create', 'edit', 'pay'];
/** Pages whose filters live in the address. */
const ADDRESS_FILTER_PATHS = ['/students', '/students/debtors', '/leads'];

function storageKey(name: string): string {
  const auth = useAuthStore();
  return `${PREFIX}${auth.user?.id ?? 'guest'}:${name}`;
}

function read(name: string): unknown {
  try {
    const raw = sessionStorage.getItem(storageKey(name));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function write(name: string, value: unknown) {
  try {
    sessionStorage.setItem(storageKey(name), JSON.stringify(value));
  } catch {
    // Storage is full or blocked: the filters simply are not remembered
  }
}

function filterPart(query: LocationQuery): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(query)) {
    if (NOT_FILTERS.includes(key) || value == null) continue;
    result[key] = String(Array.isArray(value) ? value[0] : value);
  }
  return result;
}

/** After every move: keep the filters of an address-filter page (also "no filters" after a reset). */
export function rememberQuery(to: RouteLocationNormalized) {
  if (!ADDRESS_FILTER_PATHS.includes(to.path)) return;
  write(`url:${to.path}`, filterPart(to.query));
}

/** Opening such a page without filters in the address: where to go instead, or null. */
export function rememberedQueryFor(to: RouteLocationNormalized): RouteLocationRaw | null {
  if (!ADDRESS_FILTER_PATHS.includes(to.path)) return null;
  if (Object.keys(filterPart(to.query)).length) return null;
  const saved = read(`url:${to.path}`);
  if (!saved || typeof saved !== 'object' || !Object.keys(saved).length) return null;
  return { path: to.path, query: { ...to.query, ...(saved as Record<string, string>) } };
}

/** Forget the remembered address filters of a page (its "Reset filters" button). */
export function forgetQuery(path: string) {
  write(`url:${path}`, {});
}

export function clearRememberedFilters() {
  try {
    for (const key of Object.keys(sessionStorage)) {
      if (key.startsWith(PREFIX)) sessionStorage.removeItem(key);
    }
  } catch {
    // nothing to clear
  }
}

function clone<V>(value: V): V {
  return JSON.parse(JSON.stringify(value)) as V;
}

/** A remembered value is used only if it has the same shape as the default ("" also takes a number). */
function fits(defaultValue: unknown, saved: unknown): boolean {
  if (Array.isArray(defaultValue)) return Array.isArray(saved);
  if (defaultValue === '' || defaultValue === null) {
    return saved === null || typeof saved === 'string' || typeof saved === 'number';
  }
  return typeof saved === typeof defaultValue;
}

/**
 * Remembers the filters of a page that keeps them only on the page. Call it right after the
 * `filters` object is created, before the first load. Values set from the address afterwards win.
 * `ignore` — fields that are not filters (e.g. a period preset that always has a value).
 */
export function useRememberedFilters<T extends Record<string, unknown>>(
  page: string,
  filters: T,
  options: { ignore?: Array<keyof T> } = {},
) {
  const defaults = clone(filters);
  const saved = read(`page:${page}`);
  if (saved && typeof saved === 'object') {
    for (const key of Object.keys(defaults) as Array<keyof T>) {
      const value = (saved as Record<string, unknown>)[key as string];
      if (value !== undefined && fits(defaults[key], value)) {
        filters[key] = value as T[keyof T];
      }
    }
  }

  watch(
    () => JSON.stringify(filters),
    (value) => write(`page:${page}`, JSON.parse(value)),
  );

  const ignore = options.ignore ?? [];
  /** Something is filtered: an empty list then says "nothing found" and offers a reset. */
  const isFiltered = computed(() =>
    (Object.keys(defaults) as Array<keyof T>).some(
      (key) => !ignore.includes(key) && JSON.stringify(filters[key]) !== JSON.stringify(defaults[key]),
    ),
  );

  function reset() {
    for (const key of Object.keys(defaults) as Array<keyof T>) {
      filters[key] = clone(defaults[key]);
    }
  }

  return { isFiltered, reset };
}
