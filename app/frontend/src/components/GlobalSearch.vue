<script setup lang="ts">
/**
 * Quick search over the whole program (Ctrl+K or the search field in the header): type a name or a
 * phone and open the student, lead or group at once — or take a payment straight from the result.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRouter, type RouteLocationRaw } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import NavIcon from './NavIcon.vue';
import { t } from '../i18n';
import { leadStageLabel, studentStatusLabel } from '../i18n/labels';
import { useAuthStore } from '../stores/auth';
import { groupRoute, studentRoute } from '../utils/crossLinks';
import { PERM } from '../utils/rbac';

interface FoundStudent {
  id: number;
  full_name: string;
  phone: string;
  status: number;
  group: string | null;
}
interface FoundLead {
  id: number;
  full_name: string;
  phone: string;
  stage: string;
  archived: boolean;
}
interface FoundGroup {
  id: number;
  name: string;
  course: string | null;
  teacher: string | null;
  archived: boolean;
}
interface SearchResult {
  students: FoundStudent[];
  leads: FoundLead[];
  groups: FoundGroup[];
}

/** One line of the list: what the keyboard moves over and Enter opens. */
interface Item {
  key: string;
  section: 'students' | 'leads' | 'groups' | 'all';
  title: string;
  subtitle: string;
  badge?: string;
  badgeClass?: string;
  muted?: boolean;
  to: RouteLocationRaw;
  /** Students only: take a payment straight away */
  payTo?: RouteLocationRaw;
}

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ 'update:open': [value: boolean] }>();

const router = useRouter();
const auth = useAuthStore();

const query = ref('');
const result = ref<SearchResult>({ students: [], leads: [], groups: [] });
const loading = ref(false);
const failed = ref(false);
const active = ref(0);
const input = ref<HTMLInputElement | null>(null);
const listRoot = ref<HTMLElement | null>(null);

const canPay = computed(() => auth.can(PERM.PAYMENTS_WRITE));
const trimmed = computed(() => query.value.trim());
const tooShort = computed(() => trimmed.value.length < 2);

function formatPhone(phone: string) {
  const d = (phone || '').replace(/\D/g, '');
  if (d.length === 9) return `${d.slice(0, 2)} ${d.slice(2, 5)} ${d.slice(5, 7)} ${d.slice(7)}`;
  return phone || '';
}

const STATUS_CLASS: Record<number, string> = {
  1: 'bg-emerald-100 text-emerald-700',
  2: 'bg-sky-100 text-sky-700',
};

const sections = computed(() => {
  const list: Array<{ id: Item['section']; title: string; icon: string; items: Item[] }> = [];
  const r = result.value;
  if (r.students.length) {
    list.push({
      id: 'students',
      title: t('nav.students'),
      icon: 'students',
      items: r.students.map((s) => ({
        key: `s${s.id}`,
        section: 'students',
        title: s.full_name,
        subtitle: [formatPhone(s.phone), s.group].filter(Boolean).join(' · '),
        badge: studentStatusLabel(s.status),
        badgeClass: STATUS_CLASS[s.status] ?? 'bg-slate-100 text-slate-600',
        muted: s.status !== 1 && s.status !== 2,
        to: studentRoute(s.id),
        payTo: canPay.value && (s.status === 1 || s.status === 2) ? studentRoute(s.id, { pay: '1' }) : undefined,
      })),
    });
  }
  if (r.leads.length) {
    list.push({
      id: 'leads',
      title: t('nav.leads'),
      icon: 'leads',
      items: r.leads.map((lead) => ({
        key: `l${lead.id}`,
        section: 'leads',
        title: lead.full_name,
        subtitle: formatPhone(lead.phone),
        badge: lead.archived ? t('search.archived') : leadStageLabel(lead.stage),
        badgeClass: lead.archived ? 'bg-slate-100 text-slate-600' : 'bg-amber-100 text-amber-800',
        muted: lead.archived,
        to: {
          path: '/leads',
          query: { stage: 'all', ...(lead.archived ? { archived: '1' } : {}), open: String(lead.id) },
        },
      })),
    });
  }
  if (r.groups.length) {
    list.push({
      id: 'groups',
      title: t('nav.groups'),
      icon: 'groups',
      items: r.groups.map((g) => ({
        key: `g${g.id}`,
        section: 'groups',
        title: g.name,
        subtitle: [g.course, g.teacher].filter(Boolean).join(' · '),
        badge: g.archived ? t('search.archived') : undefined,
        badgeClass: 'bg-slate-100 text-slate-600',
        muted: g.archived,
        to: groupRoute(g.id),
      })),
    });
  }
  return list;
});

/** The last line: the full list of students for this text (the old header search). */
const allStudentsItem = computed<Item | null>(() => {
  if (tooShort.value || !auth.can(PERM.STUDENTS_VIEW)) return null;
  return {
    key: 'all',
    section: 'all',
    title: t('search.allStudents', { q: trimmed.value }),
    subtitle: '',
    to: { path: '/students', query: { q: trimmed.value } },
  };
});

const flatItems = computed(() => {
  const items = sections.value.flatMap((s) => s.items);
  if (allStudentsItem.value) items.push(allStudentsItem.value);
  return items;
});

const nothingFound = computed(
  () => !tooShort.value && !loading.value && !failed.value && !sections.value.length,
);

function indexOf(item: Item) {
  return flatItems.value.findIndex((i) => i.key === item.key);
}

let timer: ReturnType<typeof setTimeout> | null = null;
let requestId = 0;

async function runSearch() {
  const q = trimmed.value;
  const id = ++requestId;
  if (q.length < 2) {
    result.value = { students: [], leads: [], groups: [] };
    loading.value = false;
    return;
  }
  loading.value = true;
  failed.value = false;
  try {
    const { data } = await client.get<ApiEnvelope<SearchResult>>('/search', { params: { q } });
    if (id !== requestId) return; // a newer search is already on its way
    result.value = data.data;
    active.value = 0;
  } catch {
    if (id === requestId) failed.value = true;
  } finally {
    if (id === requestId) loading.value = false;
  }
}

watch(query, () => {
  if (timer) clearTimeout(timer);
  timer = setTimeout(runSearch, 220);
});

watch(
  () => props.open,
  async (open) => {
    if (!open) return;
    active.value = 0;
    await nextTick();
    input.value?.focus();
    input.value?.select();
  },
);

function close() {
  emit('update:open', false);
}

function go(to: RouteLocationRaw) {
  close();
  void router.push(to);
}

function scrollActiveIntoView() {
  void nextTick(() => {
    listRoot.value?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' });
  });
}

function onKeydown(event: KeyboardEvent) {
  const count = flatItems.value.length;
  if (event.key === 'ArrowDown' && count) {
    event.preventDefault();
    active.value = (active.value + 1) % count;
    scrollActiveIntoView();
  } else if (event.key === 'ArrowUp' && count) {
    event.preventDefault();
    active.value = (active.value - 1 + count) % count;
    scrollActiveIntoView();
  } else if (event.key === 'Enter') {
    event.preventDefault();
    const item = flatItems.value[active.value];
    if (item) go(item.to);
  } else if (event.key === 'Escape') {
    event.preventDefault();
    close();
  }
}

// Ctrl+K (⌘K on a Mac) opens the search from any page
function onGlobalKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && !event.altKey && event.code === 'KeyK') {
    event.preventDefault();
    emit('update:open', !props.open);
  }
}

onMounted(() => document.addEventListener('keydown', onGlobalKeydown));
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onGlobalKeydown);
  if (timer) clearTimeout(timer);
});

defineExpose({
  /** Open with some text already typed (a letter typed into the header field). */
  setQuery(value: string) {
    query.value = value;
  },
});
</script>

<template>
  <Transition name="search">
    <div v-if="open" class="search-backdrop" @click.self="close">
      <div class="search-panel" role="dialog" aria-modal="true" :aria-label="t('search.title')">
        <div class="flex items-center gap-3 border-b border-fb-line px-5">
          <svg class="shrink-0 text-fb-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-4-4" />
          </svg>
          <input
            ref="input"
            v-model="query"
            type="text"
            class="h-14 min-w-0 flex-1 bg-transparent text-[17px] text-fb-text placeholder:text-fb-icon focus:outline-none"
            :placeholder="t('search.placeholder')"
            autocomplete="off"
            spellcheck="false"
            role="combobox"
            aria-expanded="true"
            aria-controls="search-results"
            @keydown="onKeydown"
          />
          <span v-if="loading" class="search-spinner" aria-hidden="true" />
          <kbd class="search-kbd">Esc</kbd>
        </div>

        <div id="search-results" ref="listRoot" class="max-h-[min(60vh,520px)] overflow-y-auto py-2" role="listbox">
          <p v-if="tooShort" class="px-5 py-8 text-center text-[15px] text-fb-secondary">
            {{ t('search.hint') }}
          </p>
          <p v-else-if="failed" class="px-5 py-8 text-center text-[15px] text-fb-danger">
            {{ t('search.failed') }}
          </p>
          <p v-else-if="nothingFound" class="px-5 pb-4 pt-8 text-center text-[15px] text-fb-secondary">
            {{ t('search.nothing', { q: trimmed }) }}
          </p>

          <section v-for="section in sections" :key="section.id" class="pb-1">
            <h3 class="flex items-center gap-2 px-5 pb-1 pt-2 text-[12px] font-semibold uppercase tracking-wide text-fb-icon">
              <NavIcon :name="section.icon" :size="14" />
              {{ section.title }}
            </h3>
            <div
              v-for="item in section.items"
              :key="item.key"
              role="option"
              :aria-selected="indexOf(item) === active"
              :data-active="indexOf(item) === active"
              class="search-item"
              :class="{ 'search-item--active': indexOf(item) === active }"
              @mousemove="active = indexOf(item)"
              @click="go(item.to)"
            >
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <span class="truncate text-[15px] font-medium" :class="item.muted ? 'text-fb-secondary' : 'text-fb-text'">{{ item.title }}</span>
                  <span v-if="item.badge" class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium" :class="item.badgeClass">
                    {{ item.badge }}
                  </span>
                </div>
                <div v-if="item.subtitle" class="truncate text-[13px] text-fb-secondary">{{ item.subtitle }}</div>
              </div>
              <button
                v-if="item.payTo"
                type="button"
                class="shrink-0 rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-emerald-700"
                @click.stop="go(item.payTo)"
              >
                + {{ t('students.pay') }}
              </button>
            </div>
          </section>

          <div
            v-if="allStudentsItem"
            role="option"
            :aria-selected="indexOf(allStudentsItem) === active"
            :data-active="indexOf(allStudentsItem) === active"
            class="search-item mt-1 border-t border-fb-line text-fb-blue"
            :class="{ 'search-item--active': indexOf(allStudentsItem) === active }"
            @mousemove="active = indexOf(allStudentsItem)"
            @click="go(allStudentsItem.to)"
          >
            <span class="text-[14px] font-medium">{{ allStudentsItem.title }} →</span>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-fb-line px-5 py-2.5 text-[12px] text-fb-icon">
          <span><kbd class="search-kbd">↑</kbd> <kbd class="search-kbd">↓</kbd> {{ t('search.keysMove') }}</span>
          <span><kbd class="search-kbd">Enter</kbd> {{ t('search.keysOpen') }}</span>
          <span><kbd class="search-kbd">Ctrl</kbd> <kbd class="search-kbd">K</kbd> {{ t('search.keysToggle') }}</span>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.search-backdrop {
  position: fixed;
  inset: 0;
  z-index: 150;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 10vh 16px 16px;
  background: rgb(15 23 42 / 0.4);
}
.search-panel {
  width: 100%;
  max-width: 640px;
  overflow: hidden;
  border-radius: 16px;
  background: var(--fb-card);
  box-shadow: 0 24px 60px rgb(15 23 42 / 0.3);
}
.search-item {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  padding: 8px 20px;
}
.search-item--active {
  background: var(--fb-hover);
}
.search-kbd {
  display: inline-block;
  min-width: 20px;
  border: 1px solid var(--fb-line-strong);
  border-bottom-width: 2px;
  border-radius: 5px;
  padding: 0 5px;
  font-family: inherit;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
  color: var(--fb-text-secondary);
  background: var(--fb-canvas);
}
.search-spinner {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  border: 2px solid var(--fb-line-strong);
  border-top-color: var(--fb-blue);
  border-radius: 9999px;
  animation: search-spin 0.7s linear infinite;
}
@keyframes search-spin {
  to {
    transform: rotate(360deg);
  }
}
.search-enter-active,
.search-leave-active {
  transition: opacity 0.12s ease;
}
.search-enter-from,
.search-leave-to {
  opacity: 0;
}
</style>
