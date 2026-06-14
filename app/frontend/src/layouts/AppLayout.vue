<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import NavIcon from '../components/NavIcon.vue';
import QuickAddMenu, { type QuickAddMenuItem } from '../components/QuickAddMenu.vue';
import ScheduleDrawer from '../components/ScheduleDrawer.vue';
import { firstFlyoutLink, filterNavSections, flyoutSectionForPath, primaryNav, sectionForPath } from '../config/navigation';
import { useAuthStore } from '../stores/auth';
import { useLocaleStore, type LocaleCode } from '../stores/locale';
import { PERM } from '../utils/rbac';
import { withCreateQuery } from '../utils/crossLinks';

type QuickAddItem = QuickAddMenuItem;

const auth = useAuthStore();
const localeStore = useLocaleStore();
const route = useRoute();
const router = useRouter();

const brandName = 'Hi Jack LMS';
const userInitial = computed(() => (auth.user?.name?.[0] ?? 'U').toUpperCase());
const userShortName = computed(() => auth.user?.first_name || auth.user?.name || 'User');
const userRoleLabel = computed(() => auth.user?.role_label ?? '');

const openFlyoutId = ref<string | null>(null);
const showQuickAdd = ref(false);
const showAppGrid = ref(false);
const showUserMenu = ref(false);
const quickAddRoot = ref<InstanceType<typeof QuickAddMenu> | null>(null);
const appGridRoot = ref<HTMLElement | null>(null);
const userMenuRoot = ref<HTMLElement | null>(null);
const localeMenuRoot = ref<HTMLElement | null>(null);
const searchText = ref('');
const showLocaleMenu = ref(false);
const showScheduleFab = computed(() => auth.can(PERM.GROUPS_VIEW));

const quickAddItems = computed<QuickAddItem[]>(() => {
  const items: QuickAddItem[] = [
    { label: 'Add student', icon: 'plus', ...withCreateQuery('/students') },
    { label: 'Pay Student', icon: 'pay', ...withCreateQuery('/finance/payments') },
  ];
  return items.filter((item) => {
    if (item.path.startsWith('/finance')) return auth.can(PERM.FINANCE_WRITE);
    if (item.path.startsWith('/students')) return auth.can(PERM.STUDENTS_WRITE);
    return true;
  });
});

const visibleNav = computed(() => filterNavSections(primaryNav, (p) => auth.can(p)));

const appGridItems = computed(() => {
  const items = [
    { label: 'Dashboard', path: '/dashboard/default', permission: PERM.DASHBOARD_VIEW },
    { label: 'Leads', path: '/leads', permission: PERM.LEADS_VIEW },
    { label: 'Teachers', path: '/teachers', permission: PERM.TEACHERS_VIEW },
    { label: 'Groups', path: '/groups', permission: PERM.GROUPS_VIEW },
    { label: 'Students', path: '/students', permission: PERM.STUDENTS_VIEW },
    { label: 'Finance', path: '/finance/payments', permission: PERM.FINANCE_VIEW },
    { label: 'Reports', path: '/reports/conversion', permission: PERM.REPORTS_VIEW },
    { label: 'Settings', path: '/auto-sms', permission: PERM.SETTINGS_INTEGRATIONS },
  ];
  return items.filter((item) => auth.can(item.permission));
});

const activeSection = computed(() => sectionForPath(route.path));
const flyoutSection = computed(() => {
  const nav = visibleNav.value;
  const fromPath = flyoutSectionForPath(route.path, nav);
  if (openFlyoutId.value) {
    return nav.find((s) => s.id === openFlyoutId.value) ?? fromPath;
  }
  return fromPath;
});

const showFlyout = computed(() => Boolean(flyoutSection.value?.children?.length));

watch(
  () => route.path,
  (path) => {
    const flyout = flyoutSectionForPath(path, visibleNav.value);
    openFlyoutId.value = flyout?.id ?? null;
    showQuickAdd.value = false;
    showAppGrid.value = false;
    showUserMenu.value = false;
    showLocaleMenu.value = false;
  },
  { immediate: true },
);

watch(
  () => route.query.q,
  (q) => {
    searchText.value = typeof q === 'string' ? q : '';
  },
  { immediate: true },
);

function onDocumentClick(event: MouseEvent) {
  const target = event.target as Node | null;
  if (showAppGrid.value && appGridRoot.value && target && !appGridRoot.value.contains(target)) {
    showAppGrid.value = false;
  }
  if (showUserMenu.value && userMenuRoot.value && target && !userMenuRoot.value.contains(target)) {
    showUserMenu.value = false;
  }
  if (showLocaleMenu.value && localeMenuRoot.value && target && !localeMenuRoot.value.contains(target)) {
    showLocaleMenu.value = false;
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick);
});

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick);
});

function isPrimaryActive(sectionId: string) {
  return activeSection.value?.id === sectionId || openFlyoutId.value === sectionId;
}

function isChildActive(to: string) {
  return route.path === to || route.path.startsWith(`${to}/`);
}

function onPrimaryClick(section: (typeof primaryNav)[number]) {
  const navSection = visibleNav.value.find((s) => s.id === section.id) ?? section;
  if (navSection.children?.length) {
    openFlyoutId.value = navSection.id;
    const inSection = navSection.children.some(
      (c) => c.type === 'link' && isChildActive(c.to),
    ) || navSection.paths?.some((p) => route.path === p || route.path.startsWith(`${p}/`));
    if (!inSection) {
      const first = firstFlyoutLink(navSection);
      if (first) router.push(first.to);
    }
    return;
  }
  openFlyoutId.value = null;
  if (navSection.to) router.push(navSection.to);
}

function goDashboard() {
  openFlyoutId.value = null;
  router.push('/dashboard/default');
}

function toggleAppGrid() {
  showAppGrid.value = !showAppGrid.value;
  showQuickAdd.value = false;
  showUserMenu.value = false;
  showLocaleMenu.value = false;
}

function toggleUserMenu() {
  showUserMenu.value = !showUserMenu.value;
  showQuickAdd.value = false;
  showAppGrid.value = false;
  showLocaleMenu.value = false;
}

function toggleLocaleMenu() {
  showLocaleMenu.value = !showLocaleMenu.value;
  showQuickAdd.value = false;
  showAppGrid.value = false;
  showUserMenu.value = false;
}

function selectLocale(code: LocaleCode) {
  localeStore.setLocale(code);
  showLocaleMenu.value = false;
}

function onAppGrid(path: string) {
  showAppGrid.value = false;
  router.push(path);
}

function onQuickAdd(item: QuickAddItem) {
  router.push(item.query ? { path: item.path, query: item.query } : item.path);
}

function submitSearch() {
  const q = searchText.value.trim();
  if (!q) return;
  router.push({ path: '/students', query: { q } });
}

function goReminders() {
  router.push('/reminders');
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    void document.documentElement.requestFullscreen();
    return;
  }
  void document.exitFullscreen();
}

function goAccount() {
  showUserMenu.value = false;
  router.push('/user/profile');
}

function logout() {
  showUserMenu.value = false;
  auth.logout();
  router.push('/login');
}
</script>

<template>
  <div class="app-shell fixed inset-0 flex overflow-hidden bg-fb-canvas">
    <!-- Left navigation: primary + flyout scroll independently from main content -->
    <div class="flex h-full shrink-0">
    <!-- Primary icon sidebar -->
    <aside class="z-20 flex h-full w-[128px] shrink-0 flex-col overflow-hidden border-r border-fb-line bg-fb-card">
      <nav class="sidebar-scroll min-h-0 flex-1 overflow-y-auto overscroll-y-contain py-4">
        <button
          v-for="section in visibleNav"
          :key="section.id"
          type="button"
          class="nav-sidebar-item group relative flex w-full flex-col items-center gap-2.5 px-2 py-5"
          :class="isPrimaryActive(section.id) ? 'is-active' : ''"
          @click="onPrimaryClick(section)"
        >
          <span
            v-if="isPrimaryActive(section.id)"
            class="absolute left-0 top-2 bottom-2 w-[5px] rounded-r bg-fb-blue"
          />

          <span class="nav-sidebar-icon-wrap">
            <NavIcon :name="section.icon" :size="44" />
          </span>

          <span class="nav-sidebar-label">
            {{ section.label }}
          </span>
        </button>
      </nav>
    </aside>

    <!-- Secondary flyout -->
    <aside
      v-if="showFlyout && flyoutSection"
      class="flex h-full shrink-0 flex-col overflow-hidden border-r border-fb-line bg-fb-card"
      :class="flyoutSection.id === 'settings' ? 'w-[280px]' : 'w-[248px]'"
    >
      <nav class="sidebar-scroll min-h-0 flex-1 overflow-y-auto overscroll-y-contain py-3">
        <template v-for="(child, idx) in flyoutSection.children" :key="`${child.type}-${idx}`">
          <div
            v-if="child.type === 'header'"
            class="flex items-center gap-2 px-5 pt-4 pb-1 text-[13px] font-semibold uppercase tracking-wide text-fb-icon"
          >
            <span>{{ child.label }}</span>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </div>
          <RouterLink
            v-else
            :to="child.to"
            class="flyout-link-fb"
            :class="isChildActive(child.to)
              ? 'text-fb-blue font-semibold bg-fb-hover/70'
              : 'text-fb-secondary hover:bg-fb-canvas hover:text-fb-text'"
          >
            <NavIcon :name="child.icon" :size="20" />
            <span class="leading-snug">{{ child.label }}</span>
          </RouterLink>
        </template>
      </nav>
    </aside>
    </div>

    <!-- Main column -->
    <div class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <!-- Top header (ModMe-style) -->
      <header class="relative z-30 h-[72px] overflow-visible border-b border-fb-line bg-fb-card px-6 flex items-center gap-5 shrink-0">
        <!-- Logo + quick add -->
        <div class="flex items-center gap-4 shrink-0">
          <button
            type="button"
            class="text-[26px] font-bold text-fb-blue tracking-tight leading-none hover:opacity-90"
            @click="goDashboard"
          >
            {{ brandName }}
          </button>
          <QuickAddMenu
            ref="quickAddRoot"
            v-model:open="showQuickAdd"
            :items="quickAddItems"
            @select="onQuickAdd"
          />
        </div>

        <!-- Search -->
        <div class="mx-auto w-full max-w-[640px] flex-1">
          <form class="relative" @submit.prevent="submitSearch">
            <svg
              class="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-fb-icon"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="M20 20l-4-4" />
            </svg>
            <input
              v-model="searchText"
              type="search"
              placeholder="Search"
              class="h-12 w-full rounded-full border border-fb-line bg-fb-canvas pl-12 pr-5 text-[16px] text-fb-text placeholder:text-fb-icon focus:border-fb-blue/40 focus:outline-none focus:ring-2 focus:ring-fb-blue/10"
            />
          </form>
        </div>

        <!-- Actions -->
        <div class="flex shrink-0 items-center gap-1 text-fb-icon">
          <div ref="localeMenuRoot" class="relative">
            <button
              type="button"
              class="min-w-[52px] rounded-full border border-fb-line px-3 py-1.5 text-[15px] font-normal lowercase text-fb-secondary hover:border-fb-line hover:text-fb-blue"
              :title="`Language: ${localeStore.code}`"
              @click.stop="toggleLocaleMenu"
            >
              {{ localeStore.code }}
            </button>
            <div
              v-if="showLocaleMenu"
              class="locale-menu absolute right-0 top-[calc(100%+10px)] z-50 min-w-[200px] rounded-md border border-fb-line bg-fb-card py-2 shadow-fb"
            >
              <button
                v-for="option in localeStore.options"
                :key="option.code"
                type="button"
                class="block w-full px-4 py-2.5 text-left text-[15px] transition-colors"
                :class="localeStore.code === option.code
                  ? 'bg-fb-hover font-medium text-fb-blue'
                  : 'text-fb-secondary hover:bg-fb-canvas hover:text-fb-blue'"
                @click="selectLocale(option.code)"
              >
                {{ option.code }} - {{ option.label }}
              </button>
            </div>
          </div>

          <div ref="appGridRoot" class="relative">
            <button
              type="button"
              class="icon-btn-fb"
              title="Modules"
              @click.stop="toggleAppGrid"
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
                <rect x="3" y="3" width="7" height="7" rx="1.5" />
                <rect x="14" y="3" width="7" height="7" rx="1.5" />
                <rect x="3" y="14" width="7" height="7" rx="1.5" />
                <rect x="14" y="14" width="7" height="7" rx="1.5" />
              </svg>
            </button>
            <div
              v-if="showAppGrid"
              class="absolute right-0 top-[calc(100%+6px)] z-50 grid min-w-[220px] grid-cols-2 gap-1 rounded-lg border border-fb-line bg-fb-card p-2 shadow-fb"
            >
              <button
                v-for="item in appGridItems"
                :key="item.path"
                type="button"
                class="rounded-md px-3 py-2 text-left text-[14px] text-fb-secondary hover:bg-fb-hover hover:text-fb-blue"
                @click="onAppGrid(item.path)"
              >
                {{ item.label }}
              </button>
            </div>
          </div>

          <button
            type="button"
            class="icon-btn-fb"
            title="Fullscreen"
            @click="toggleFullscreen"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
              <path d="M8 4H4v4M16 4h4v4M8 20H4v-4M16 20h4v-4" />
            </svg>
          </button>

          <button
            type="button"
            class="icon-btn-fb"
            title="Reminders"
            @click="goReminders"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v5l3 2" />
            </svg>
          </button>

          <button
            type="button"
            class="icon-btn-fb"
            title="Notifications"
            @click="goReminders"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
              <path d="M15 17h5l-1.4-1.4A2 2 0 0118 14.2V11a6 6 0 00-5-5.9V4a1 1 0 00-2 0v1.1A6 6 0 006 11v3.2c0 .5-.2 1-.6 1.4L4 17h5" />
              <path d="M10 20a2 2 0 004 0" />
            </svg>
          </button>

          <div ref="userMenuRoot" class="relative ml-2">
            <button
              type="button"
              class="flex items-center gap-2.5 rounded-lg py-1 pl-1 pr-2 hover:bg-fb-canvas"
              @click.stop="toggleUserMenu"
            >
              <span
                class="flex h-10 w-10 items-center justify-center rounded-full bg-fb-blue text-[17px] font-semibold text-white"
              >
                {{ userInitial }}
              </span>
              <span class="hidden max-w-[160px] truncate text-[16px] font-semibold text-fb-text xl:inline">
                {{ userShortName }}
              </span>
              <span
                v-if="userRoleLabel"
                class="hidden text-[12px] font-medium text-fb-icon xl:inline"
              >
                {{ userRoleLabel }}
              </span>
            </button>
            <div
              v-if="showUserMenu"
              class="absolute right-0 top-[calc(100%+6px)] z-50 min-w-[160px] overflow-hidden rounded-lg border border-fb-line bg-fb-card py-1 shadow-fb"
            >
              <button
                type="button"
                class="block w-full px-4 py-3 text-left text-[15px] text-fb-text hover:bg-fb-canvas"
                @click="goAccount"
              >
                Account
              </button>
              <p v-if="userRoleLabel" class="px-4 py-2 text-xs text-fb-icon">
                Role: {{ userRoleLabel }}
              </p>
              <div class="mx-3 border-t border-fb-line" />
              <button
                type="button"
                class="block w-full px-4 py-3 text-left text-[15px] text-fb-text hover:bg-fb-canvas"
                @click="logout"
              >
                Sign out
              </button>
            </div>
          </div>
        </div>
      </header>

      <main class="main-scroll min-h-0 flex-1 overflow-y-auto overscroll-y-contain bg-fb-canvas">
        <div class="p-6">
          <RouterView />
        </div>
      </main>
    </div>

    <ScheduleDrawer v-if="showScheduleFab" />
  </div>
</template>

<style scoped>
.nav-sidebar-item {
  color: var(--fb-text-secondary);
  transition: color 0.2s ease;
}

.nav-sidebar-item:hover,
.nav-sidebar-item.is-active {
  color: var(--fb-blue);
}

.nav-sidebar-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 4rem;
  height: 4rem;
  border-radius: 9999px;
  transition:
    background-color var(--fb-motion-fast) var(--fb-ease),
    box-shadow var(--fb-motion-fast) var(--fb-ease),
    color var(--fb-motion-fast) var(--fb-ease),
    transform var(--fb-motion-normal) var(--fb-ease);
}

.nav-sidebar-item:hover .nav-sidebar-icon-wrap,
.nav-sidebar-item.is-active .nav-sidebar-icon-wrap {
  background-color: var(--fb-hover);
  box-shadow: 0 0 0 2px rgb(24 119 242 / 0.22);
}

@media (prefers-reduced-motion: no-preference) {
  .nav-sidebar-item:hover .nav-sidebar-icon-wrap {
    transform: scale(1.06);
  }

  .nav-sidebar-item:active .nav-sidebar-icon-wrap {
    transform: scale(0.94);
  }

  .nav-sidebar-item.is-active .nav-sidebar-icon-wrap {
    transform: scale(1.04);
  }
}

.nav-sidebar-label {
  max-width: 118px;
  text-align: center;
  font-size: 13px;
  line-height: 1.3;
  font-weight: 600;
  color: var(--fb-text-secondary);
  transition: color 0.2s ease;
}

.nav-sidebar-item:hover .nav-sidebar-label,
.nav-sidebar-item.is-active .nav-sidebar-label {
  color: var(--fb-blue);
}

.sidebar-scroll,
.main-scroll {
  scrollbar-width: thin;
  scrollbar-color: rgb(203 213 225) transparent;
}

.sidebar-scroll::-webkit-scrollbar,
.main-scroll::-webkit-scrollbar {
  width: 6px;
}

.sidebar-scroll::-webkit-scrollbar-thumb,
.main-scroll::-webkit-scrollbar-thumb {
  border-radius: 9999px;
  background-color: rgb(203 213 225);
}

.locale-menu::before {
  content: '';
  position: absolute;
  top: -7px;
  right: 18px;
  width: 12px;
  height: 12px;
  background: var(--fb-card);
  border-left: 1px solid var(--fb-line);
  border-top: 1px solid var(--fb-line);
  transform: rotate(45deg);
}
</style>
