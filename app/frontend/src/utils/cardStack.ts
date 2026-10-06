/**
 * Card stack (like Bitrix24 sliders): a teacher / group / student card opens ON TOP of the page the
 * user is on, the left menu section does not change, and closing a card shows the one under it.
 *
 * The stack lives in the address: ?cards=teacher-3,group-5,student-12 — so the browser "Back" button
 * closes the top card and a page reload keeps the cards open.
 */
import { computed, watch } from 'vue';
import {
  useRoute,
  useRouter,
  type LocationQuery,
  type RouteLocationNormalized,
  type RouteLocationRaw,
} from 'vue-router';

import { parseOpenId } from './crossLinks';

export type CardKind = 'teacher' | 'group' | 'student';

export interface CardRef {
  kind: CardKind;
  id: number;
  /** Open straight in the edit form (e.g. a reminder "put the student into a group"). */
  edit: boolean;
}

/** The section each card belongs to: its view permission decides who may open the card. */
export const CARD_PATHS: Record<CardKind, string> = {
  teacher: '/teachers',
  group: '/groups',
  student: '/students',
};

const CARD_PATTERN = /^(teacher|group|student)-(\d+)(-edit)?$/;

export function parseCards(query: LocationQuery): CardRef[] {
  const raw = Array.isArray(query.cards) ? query.cards[0] : query.cards;
  if (!raw) return [];
  const cards: CardRef[] = [];
  for (const part of String(raw).split(',')) {
    const match = CARD_PATTERN.exec(part);
    if (match) {
      cards.push({ kind: match[1] as CardKind, id: Number(match[2]), edit: Boolean(match[3]) });
    }
  }
  return cards;
}

function serializeCards(cards: CardRef[]): string {
  return cards.map((card) => `${card.kind}-${card.id}${card.edit ? '-edit' : ''}`).join(',');
}

export function queryWithCards(query: LocationQuery, cards: CardRef[]): LocationQuery {
  const next: LocationQuery = { ...query };
  delete next.cards;
  if (cards.length) next.cards = serializeCards(cards);
  return next;
}

/** The page address without the open cards: list pages reload on it, not on every opened card. */
export function pathWithoutCards(route: { path: string; query: LocationQuery }): string {
  const query = queryWithCards(route.query, []);
  return `${route.path}?${JSON.stringify(query)}`;
}

function cardFromLink(to: RouteLocationNormalized): CardRef | null {
  const id = parseOpenId(to.query);
  if (id == null) return null;
  const path = to.path.replace(/\/list$/, '');
  const kind = (Object.keys(CARD_PATHS) as CardKind[]).find((key) => CARD_PATHS[key] === path);
  if (!kind) return null;
  return { kind, id, edit: to.query.edit === '1' };
}

/** Is this a link to a card ("/students?open=5")? */
export function isCardLink(to: RouteLocationNormalized): boolean {
  return cardFromLink(to) != null;
}

/**
 * A link "/students?open=5" (also /groups, /teachers) no longer moves the user to that section:
 * the card is put on top of the page they are on. Returns where to go instead, or null for other links.
 */
export function resolveCardLink(to: RouteLocationNormalized, from: RouteLocationNormalized): RouteLocationRaw | null {
  const card = cardFromLink(to);
  if (!card) return null;

  // No page under the card yet (a pasted link, a page reload, right after login): its own list is the page
  const hasPage = from.matched.length > 0 && !from.meta.public;
  const host = hasPage ? from : to;
  const stack = hasPage ? parseCards(from.query) : [];
  const query: LocationQuery = { ...host.query };
  delete query.open;
  delete query.edit;

  const top = stack[stack.length - 1];
  const below = stack[stack.length - 2];
  let next: CardRef[];
  if (top && top.kind === card.kind && top.id === card.id) {
    next = [...stack.slice(0, -1), card];
  } else if (below && below.kind === card.kind && below.id === card.id) {
    // teacher -> group -> the same teacher again: step back instead of piling up copies
    next = stack.slice(0, -1);
  } else {
    next = [...stack, card];
  }
  return { path: host.path, query: queryWithCards(query, next) };
}

export function useCardStack() {
  const route = useRoute();
  const router = useRouter();
  const stack = computed(() => parseCards(route.query));

  /** Close the top card: the one under it (or the page) is shown again. */
  function closeTop() {
    if (!stack.value.length) return;
    const target = { path: route.path, query: queryWithCards(route.query, stack.value.slice(0, -1)) };
    // Opened from here by a click: stepping back in history keeps "Back" and "✕" the same thing
    const previous = window.history.state?.back;
    if (typeof previous === 'string' && previous === router.resolve(target).fullPath) {
      router.back();
    } else {
      router.replace(target);
    }
  }

  return { stack, closeTop };
}

/**
 * Runs `refresh` when the cards above are closed and this layer is seen again
 * (level -1 = the page itself, 0 = the first card, 1 = the card on top of it, …).
 */
export function onCardsReturn(level: number, refresh: () => void) {
  const route = useRoute();
  watch(
    () => parseCards(route.query).length,
    (now, before) => {
      if (now < before && now === level + 1) refresh();
    },
  );
}
