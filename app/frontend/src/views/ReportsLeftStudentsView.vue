<script setup lang="ts">
import { todayIso } from '../utils/dates';
import { onMounted, reactive, ref, watch } from 'vue';
import { formatSum } from '../utils/money';
import { useRoute, useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { useRememberedFilters } from '../utils/rememberedFilters';
import SkeletonBlock from '../components/SkeletonBlock.vue';
import { downloadCsv } from '../utils/csvExport';
import { groupRoute, studentRoute } from '../utils/crossLinks';
import { onCardsReturn } from '../utils/cardStack';
import { t, type MessageKey } from '../i18n';
import { studentStatusLabel } from '../i18n/labels';
import { toast } from '../ui/feedback';

interface Branch {
  id: number;
  name: string;
}

interface GroupOption {
  id: number;
  name: string;
  branch_id: number;
}

interface LeftStudentRow {
  id: number;
  full_name: string;
  phone: string;
  status: number;
  status_label: string;
  branch_id: number;
  branch: string;
  group_id: number | null;
  group: string;
  comment?: string;
  left_at: string;
  /** Unpaid months at the moment of leaving (0 = left without debt). */
  debt_months?: number;
  debt_amount?: number;
  debt_since?: string | null;
  /** The CEO wrote the debt off: it is not a debt any more, shown as "Списано" with the reason. */
  written_off?: boolean;
  written_off_months?: number;
  written_off_amount?: number;
  written_off_note?: string;
}

interface Summary {
  left_active: number;
  left_trial: number;
  total: number;
  with_debt?: number;
  written_off?: number;
}

interface Payload {
  summary: Summary;
  rows: LeftStudentRow[];
  total?: number;
  page?: number;
  total_pages?: number;
}

const STATUS_OPTIONS: { value: string; label: MessageKey }[] = [
  { value: '', label: 'leftReport.allLeft' },
  { value: '8', label: 'leftReport.leftActive' },
  { value: '7', label: 'studentStatus.7' },
];

const router = useRouter();
const route = useRoute();

const rows = ref<LeftStudentRow[]>([]);
const summary = ref<Summary>({ left_active: 0, left_trial: 0, total: 0 });
const branches = ref<Branch[]>([]);
const groups = ref<GroupOption[]>([]);
const loading = ref(true);
const exporting = ref(false);
const currentPage = ref(1);
const totalPages = ref(1);
const totalCount = ref(0);

const filters = reactive({
  status: '',
  branch_id: '',
  group_id: '',
  date_from: '',
  date_to: '',
  q: '',
  with_debt: false,
});
// Leave the page and come back: the filters are still set
useRememberedFilters('left-students', filters);

function formatMoney(value: number) {
  return formatSum(value);
}

function showDebtors() {
  filters.with_debt = true;
  applyFilters();
}

async function loadMeta() {
  const [branchRes, groupRes] = await Promise.all([
    client.get<ApiEnvelope<Branch[]>>('/branch'),
    client.get<ApiEnvelope<GroupOption[]>>('/groups'),
  ]);
  branches.value = branchRes.data.data;
  groups.value = groupRes.data.data;
}

function applyFilters() {
  currentPage.value = 1;
  loadRows();
}

function resetFilters() {
  filters.status = '';
  filters.branch_id = '';
  filters.group_id = '';
  filters.date_from = '';
  filters.date_to = '';
  filters.q = '';
  filters.with_debt = false;
  currentPage.value = 1;
  loadRows();
}

function changePage(delta: number) {
  currentPage.value += delta;
  loadRows();
}

async function loadRows(quiet = false) {
  if (!quiet) loading.value = true;
  try {
    const params: Record<string, string> = { page: String(currentPage.value) };
    if (filters.status) params.status = filters.status;
    if (filters.branch_id) params.branch_id = filters.branch_id;
    if (filters.group_id) params.group_id = filters.group_id;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();
    if (filters.with_debt) params.with_debt = '1';
    const { data } = await client.get<ApiEnvelope<Payload>>('/reports/left-students', { params });
    summary.value = data.data.summary;
    rows.value = data.data.rows;
    totalPages.value = data.data.total_pages || 1;
    totalCount.value = data.data.total ?? summary.value.total;
  } finally {
    loading.value = false;
  }
}

async function exportCsv() {
  exporting.value = true;
  try {
    const params: Record<string, string> = { export: '1' };
    if (filters.status) params.status = filters.status;
    if (filters.branch_id) params.branch_id = filters.branch_id;
    if (filters.group_id) params.group_id = filters.group_id;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();
    if (filters.with_debt) params.with_debt = '1';

    const { data } = await client.get<ApiEnvelope<Payload>>('/reports/left-students', { params });
    downloadCsv(
      `left_students_${todayIso()}.csv`,
      [
        'ID', t('common.fullName'), t('common.phone'), t('common.status'), t('schedule.group'), t('common.branch'),
        t('leftReport.debtMonthsCsv'), t('leftReport.debtAmountCsv'), t('leftReport.writtenOffCsv'),
        t('leftReport.reason'), t('leftReport.leftAt'),
      ],
      data.data.rows.map((row) => [
        row.id,
        row.full_name,
        row.phone,
        studentStatusLabel(row.status, row.status_label),
        row.group,
        row.branch,
        row.debt_months ?? 0,
        row.debt_amount ?? 0,
        row.written_off ? `${t('receipt.months', { count: row.written_off_months ?? 0 })}; ${row.written_off_note || ''}` : '',
        row.comment || '',
        row.left_at,
      ]),
    );
  } catch (err) {
    console.error(err);
    toast.error(t('errors.exportFailed'));
  } finally {
    exporting.value = false;
  }
}

function openStudent(id: number) {
  router.push(studentRoute(id));
}

function openGroup(groupId: number) {
  router.push(groupRoute(groupId));
}

// A card opened from here is closed: show fresh data without the "Loading…" blink
onCardsReturn(-1, () => void loadRows(true));

onMounted(async () => {
  // Links from the dashboard: "Ушли, не заплатив" and the cards "Left active group" / "Left after trial period"
  if (route.query.with_debt === '1') filters.with_debt = true;
  const status = String(route.query.status ?? '');
  if (STATUS_OPTIONS.some((o) => o.value === status)) filters.status = status;
  await loadMeta();
  await loadRows();
});

let searchDebounce: ReturnType<typeof setTimeout> | null = null;
watch(
  () => filters.q,
  (newQ, oldQ) => {
    if (newQ === oldQ) return;
    if (searchDebounce) clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      applyFilters();
    }, 400);
  },
);
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold text-fb-text">{{ t('leftReport.title') }}</h1>
        <p class="text-xs text-fb-secondary mt-0.5">{{ t('leftReport.subtitle') }}</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="rounded-lg border border-fb-line bg-fb-card px-3.5 py-2 text-sm text-fb-secondary hover:border-fb-blue hover:text-fb-blue transition-colors disabled:opacity-50"
          :disabled="exporting"
          @click="exportCsv"
        >
          {{ exporting ? t('leftReport.exporting') : `📥 ${t('common.exportCsv')}` }}
        </button>
        <router-link
          to="/students"
          class="text-sm font-medium text-fb-blue hover:underline"
        >
          {{ t('leftReport.allStudents') }} →
        </router-link>
      </div>
    </div>

    <!-- Summary KPI cards -->
    <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
      <div class="rounded-xl border border-fb-line bg-fb-card p-5 text-center shadow-sm">
        <div class="text-3xl font-bold text-fb-text">{{ summary.total }}</div>
        <div class="mt-1 text-xs font-medium uppercase tracking-wider text-fb-secondary">{{ t('leftReport.totalLeft') }}</div>
      </div>
      <div class="rounded-xl border border-fb-line bg-fb-card p-5 text-center shadow-sm">
        <div class="text-3xl font-bold text-fb-blue">{{ summary.left_active }}</div>
        <div class="mt-1 text-xs font-medium uppercase tracking-wider text-fb-secondary">{{ t('leftReport.leftActiveGroup') }}</div>
      </div>
      <div class="rounded-xl border border-fb-line bg-fb-card p-5 text-center shadow-sm">
        <div class="text-3xl font-bold text-amber-600">{{ summary.left_trial }}</div>
        <div class="mt-1 text-xs font-medium uppercase tracking-wider text-fb-secondary">{{ t('leftReport.leftAfterTrial') }}</div>
      </div>
      <button
        type="button"
        class="rounded-xl border border-rose-200 bg-rose-50 p-5 text-center shadow-sm hover:border-rose-400 transition-colors"
        :title="t('leftReport.showDebtorsHint')"
        @click="showDebtors"
      >
        <div class="text-3xl font-bold text-rose-700">{{ summary.with_debt ?? 0 }}</div>
        <div class="mt-1 text-xs font-medium uppercase tracking-wider text-rose-700">{{ t('leftReport.leftWithDebt') }}</div>
        <div v-if="summary.written_off" class="mt-1 text-[11px] text-fb-secondary">+ {{ t('leftReport.writtenOffByCeo', { count: summary.written_off }) }}</div>
      </button>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('leftReport.category') }}</label>
        <select v-model="filters.status" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none">
          <option v-for="opt in STATUS_OPTIONS" :key="opt.value" :value="opt.value">{{ t(opt.label) }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('common.branch') }}</label>
        <select v-model="filters.branch_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none">
          <option value="">{{ t('common.allBranches') }}</option>
          <option v-for="b in branches" :key="b.id" :value="String(b.id)">{{ b.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('schedule.group') }}</label>
        <select v-model="filters.group_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none">
          <option value="">{{ t('teacherAtt.allGroups') }}</option>
          <option v-for="g in groups" :key="g.id" :value="String(g.id)">{{ g.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('leftReport.leftFrom') }}</label>
        <input v-model="filters.date_from" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('leftReport.leftTo') }}</label>
        <input v-model="filters.date_to" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
      </div>
      <div class="min-w-[180px] flex-1">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('common.search') }}</label>
        <input
          v-model="filters.q"
          type="search"
          :placeholder="t('leftReport.searchPlaceholder')"
          class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
          @keydown.enter="applyFilters"
        />
      </div>
      <label class="flex items-center gap-2 pb-2 text-sm text-fb-secondary">
        <input v-model="filters.with_debt" type="checkbox" />
        {{ t('leftReport.onlyWithDebt') }}
      </label>
      <button
        type="button"
        class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:bg-fb-blue-dark transition-colors"
        @click="applyFilters"
      >
        {{ t('common.apply') }}
      </button>
    </div>

    <!-- Table or Empty State -->
    <div class="table-cards-wrap overflow-hidden rounded-xl border border-fb-line bg-fb-card shadow-sm">
      <SkeletonBlock v-if="loading" :rows="8" :cols="6" />
      
      <!-- Empty State -->
      <div v-else-if="!rows.length" class="flex flex-col items-center justify-center p-12 text-center">
        <div class="flex h-16 w-16 items-center justify-center rounded-full bg-fb-hover text-2xl mb-3 text-fb-icon">
          🎓
        </div>
        <h3 class="text-base font-semibold text-fb-text">{{ t('leftReport.emptyTitle') }}</h3>
        <p class="mt-1 text-sm text-fb-secondary max-w-sm">
          {{ t('leftReport.emptyText') }}
        </p>
        <button
          type="button"
          class="mt-4 rounded-lg border border-fb-line bg-white px-4 py-2 text-xs font-medium text-fb-blue hover:bg-fb-canvas transition-colors"
          @click="resetFilters"
        >
          {{ t('common.resetFilters') }}
        </button>
      </div>

      <template v-else>
        <table class="table-cards w-full text-sm">
          <thead class="border-b border-fb-line bg-fb-canvas text-xs uppercase tracking-wider font-semibold text-fb-secondary">
            <tr>
              <th class="px-5 py-3.5 text-left">{{ t('common.fullName') }}</th>
              <th class="px-5 py-3.5 text-left">{{ t('common.phone') }}</th>
              <th class="px-5 py-3.5 text-left">{{ t('leftReport.categoryShort') }}</th>
              <th class="px-5 py-3.5 text-left">{{ t('schedule.group') }}</th>
              <th class="px-5 py-3.5 text-left">{{ t('common.branch') }}</th>
              <th class="px-5 py-3.5 text-left">{{ t('leftReport.debtWhenLeft') }}</th>
              <th class="px-5 py-3.5 text-left">{{ t('leftReport.reason') }}</th>
              <th class="px-5 py-3.5 text-left">{{ t('leftReport.leftAt') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-fb-line">
            <tr
              v-for="row in rows"
              :key="row.id"
              class="cursor-pointer hover:bg-fb-hover/40 transition-colors"
              @click="openStudent(row.id)"
            >
              <td class="cell-main px-5 py-3.5 font-medium text-fb-text">{{ row.full_name }}</td>
              <td :data-label="t('common.phone')" class="px-5 py-3.5 text-fb-secondary">{{ row.phone }}</td>
              <td :data-label="t('leftReport.categoryShort')" class="px-5 py-3.5">
                <span
                  class="rounded-full px-2.5 py-0.5 text-xs font-medium"
                  :class="row.status === 7 ? 'bg-amber-50 text-amber-700 border border-amber-200' : 'bg-gray-100 text-gray-700 border border-gray-200'"
                >
                  {{ studentStatusLabel(row.status, row.status_label) }}
                </span>
              </td>
              <td :data-label="t('schedule.group')" class="px-5 py-3.5">
                <button
                  v-if="row.group_id"
                  type="button"
                  class="text-fb-blue hover:underline font-medium"
                  @click.stop="openGroup(row.group_id)"
                >
                  {{ row.group }}
                </button>
                <span v-else class="text-fb-secondary">{{ row.group }}</span>
              </td>
              <td :data-label="t('common.branch')" class="px-5 py-3.5 text-fb-secondary">{{ row.branch }}</td>
              <td :data-label="t('leftReport.debtWhenLeft')" class="px-5 py-3.5">
                <span v-if="row.debt_months" class="font-semibold text-rose-700">
                  {{ t('receipt.months', { count: row.debt_months }) }}<span v-if="row.debt_amount"> · ≈ {{ t('common.sumAmount', { amount: formatMoney(row.debt_amount) }) }}</span>
                </span>
                <span v-else-if="row.written_off" class="text-fb-secondary" :title="row.written_off_note">
                  <span class="rounded-full border border-gray-300 bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700">{{ t('months.state.writtenOff') }}</span>
                  <span class="ml-1 text-xs">
                    {{ t('receipt.months', { count: row.written_off_months ?? 0 }) }}<span v-if="row.written_off_amount"> · ≈ {{ t('common.sumAmount', { amount: formatMoney(row.written_off_amount) }) }}</span>
                  </span>
                  <span class="mt-0.5 block max-w-[260px] text-[11px] leading-snug">{{ row.written_off_note }}</span>
                </span>
                <span v-else class="text-fb-secondary">—</span>
              </td>
              <td :data-label="t('leftReport.reason')" class="px-5 py-3.5 text-fb-secondary max-w-[240px] truncate" :title="row.comment">
                {{ row.comment || '—' }}
              </td>
              <td :data-label="t('leftReport.leftAt')" class="px-5 py-3.5 font-medium text-fb-text">{{ row.left_at }}</td>
            </tr>
          </tbody>
        </table>

        <!-- Pagination Bar -->
        <div class="flex items-center justify-between border-t border-fb-line px-5 py-3.5">
          <button
            type="button"
            class="rounded-lg border border-fb-line px-3.5 py-1.5 text-xs font-medium text-fb-secondary hover:text-fb-blue hover:border-fb-blue disabled:opacity-40 transition-colors"
            :disabled="currentPage <= 1"
            @click="changePage(-1)"
          >
            ← {{ t('common.prev') }}
          </button>
          <span class="text-xs text-fb-secondary font-medium">
            {{ t('common.page', { page: currentPage, pages: totalPages }) }} · {{ t('common.totalCount', { count: totalCount }) }}
          </span>
          <button
            type="button"
            class="rounded-lg border border-fb-line px-3.5 py-1.5 text-xs font-medium text-fb-secondary hover:text-fb-blue hover:border-fb-blue disabled:opacity-40 transition-colors"
            :disabled="currentPage >= totalPages"
            @click="changePage(1)"
          >
            {{ t('common.next') }} →
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
