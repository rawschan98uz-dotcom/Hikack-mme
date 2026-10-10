<script setup lang="ts">
import { currentMonthIso, formatMonthTitle } from '../utils/dates';
import { computed, onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';
import { t, type MessageKey } from '../i18n';
import { confirmDialog, toast } from '../ui/feedback';
import { apiErrorMessage } from '../utils/apiError';

const auth = useAuthStore();
// Salaries and rates are the CEO's (finance.write); a branch director only looks
const canWriteFinance = computed(() => auth.can(PERM.FINANCE_WRITE));

/** A rate: a teacher's percent (general / course / group) or a staff member's fixed monthly sum. */
interface SalaryRow {
  id: number;
  person_kind: 'teacher' | 'staff';
  salary_type: 'percent' | 'fixed';
  salary_type_label: string;
  amount: number;
  teacher_id: number | null;
  teacher: string;
  course_id: number | null;
  course: string;
  group_id: number | null;
  group: string;
  effective_from: string | null;
  effective_to: string | null;
  updated_by: string;
}

/** How a teacher's salary for one group was counted (finance/payroll.py). */
interface GroupAccrual {
  group_id: number;
  group: string;
  branch: string;
  held_lessons: number;
  student_lessons: number;
  percent: number;
  percent_scope: string;
  /** Earned if every student pays in full / payable now from what is paid / still waiting for payments. */
  earned: number;
  accrued: number;
  waiting: number;
  students_unpaid: number;
}

interface Payout {
  id: number | null;
  amount: number;
  method: string;
  comment: string;
  date: string;
}

interface PayrollRow {
  person_id: number;
  teacher_id: number;
  teacher_name: string;
  phone: string;
  kind: 'teacher' | 'staff';
  kind_label: string;
  is_active: boolean;
  branch_id: number | null;
  groups: GroupAccrual[];
  fixed_amount: number | null;
  accrued: number;
  earned: number;
  waiting: number;
  paid: number;
  balance: number;
  overpaid: number;
  status: 'paid' | 'partial' | 'unpaid' | 'none';
  payouts: Payout[];
  month_closed: boolean;
  accrued_base: number;
  adjustments: Adjustment[];
}

/** A visible correction of a month's salary by the CEO (+ or −) with a reason. */
interface Adjustment {
  id: number;
  amount: number;
  reason: string;
  date: string;
  by: string;
}

interface ClosedInfo {
  month: string;
  closed_at: string;
  closed_by: string;
}

interface PayrollSummary {
  total_accrued: number;
  total_waiting?: number;
  total_paid: number;
  total_balance: number;
  teachers_count: number;
}

interface Option {
  id: number;
  name: string;
}

const activeTab = ref<'payroll' | 'settings'>('payroll');

function money(value: number | null | undefined) {
  return Math.round(value || 0).toLocaleString('ru-RU');
}

// ================= Payroll =================
const selectedMonth = ref(currentMonthIso());
const payrollRows = ref<PayrollRow[]>([]);
const payrollSummary = ref<PayrollSummary>({ total_accrued: 0, total_paid: 0, total_balance: 0, teachers_count: 0 });
const payrollLoading = ref(false);
const payrollError = ref('');
const expanded = ref<number | null>(null);
// Closing the month (CEO): salaries frozen, money records dated in the month locked
const monthClosed = ref<ClosedInfo | null>(null);
const canClose = ref(false);

const monthTitle = computed(() => formatMonthTitle(selectedMonth.value));

// Where a teacher's percent came from; the server names it in Russian
const PERCENT_SCOPES: Record<string, MessageKey> = {
  'группа': 'salaries.scopeGroup',
  'курс': 'salaries.scopeCourse',
  'общий': 'salaries.scopeGeneral',
  'не задан': 'salaries.scopeNone',
};

function percentScopeLabel(scope: string) {
  const key = PERCENT_SCOPES[scope];
  return key ? t(key) : scope;
}

function kindLabel(row: PayrollRow) {
  return row.kind === 'teacher' ? t('salaries.kindTeacher') : t('salaries.kindStaff');
}

async function loadPayroll() {
  payrollLoading.value = true;
  payrollError.value = '';
  try {
    const { data } = await client.get<
      ApiEnvelope<{ month: string; closed: ClosedInfo | null; can_close: boolean; summary: PayrollSummary; rows: PayrollRow[] }>
    >('/finance/payroll', { params: { month: selectedMonth.value } });
    payrollSummary.value = data.data.summary;
    payrollRows.value = data.data.rows;
    monthClosed.value = data.data.closed;
    canClose.value = data.data.can_close;
  } catch (err: unknown) {
    payrollError.value = apiErrorMessage(err, t('salaries.loadFailed'));
  } finally {
    payrollLoading.value = false;
  }
}

function shiftMonth(delta: number) {
  const [y, m] = selectedMonth.value.split('-').map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  selectedMonth.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  void loadPayroll();
}

function statusLabel(row: PayrollRow) {
  if (row.status === 'paid') return row.overpaid ? t('salaries.paidOver', { amount: money(row.overpaid) }) : t('salaries.paid');
  if (row.status === 'partial') return t('salaries.partial');
  if (row.status === 'unpaid') return t('salaries.unpaid');
  return '—';
}

function statusClass(row: PayrollRow) {
  if (row.status === 'paid') return 'bg-emerald-50 text-emerald-700';
  if (row.status === 'partial') return 'bg-amber-50 text-amber-700';
  if (row.status === 'unpaid') return 'bg-rose-50 text-rose-700';
  return 'bg-fb-canvas text-fb-secondary';
}

// Pay
const branches = ref<Option[]>([]);
const payModal = reactive({
  show: false,
  row: null as PayrollRow | null,
  amount: 0,
  method: 'cash' as 'cash' | 'card' | 'transfer',
  comment: '',
  branch_id: '' as number | '',
  force: false,
  overpay: false,
  error: '',
  saving: false,
});

const payNeedsBranch = computed(() => payModal.row?.kind === 'staff' && !payModal.row.branch_id);

function openPay(row: PayrollRow) {
  payModal.row = row;
  payModal.amount = row.balance > 0 ? row.balance : 0;
  payModal.method = 'cash';
  payModal.comment = t('salaries.payComment', { month: selectedMonth.value, name: row.teacher_name });
  payModal.branch_id = '';
  payModal.force = false;
  payModal.overpay = false;
  payModal.error = '';
  payModal.show = true;
}

async function submitPay() {
  if (!payModal.row) return;
  if (!Number.isInteger(payModal.amount) || payModal.amount <= 0) {
    payModal.error = t('finance.amountPositive');
    return;
  }
  if (payNeedsBranch.value && payModal.branch_id === '') {
    payModal.error = t('salaries.payBranchRequired');
    return;
  }
  payModal.saving = true;
  payModal.error = '';
  try {
    await client.post('/finance/payroll/pay', {
      teacher_id: payModal.row.person_id,
      amount: payModal.amount,
      method: payModal.method,
      month: selectedMonth.value,
      comment: payModal.comment,
      ...(payModal.branch_id !== '' ? { branch_id: payModal.branch_id } : {}),
      ...(payModal.force ? { force: true } : {}),
    });
    const paidName = payModal.row.teacher_name;
    const paidAmount = payModal.amount;
    payModal.show = false;
    toast.success(t('salaries.paidToast', { amount: money(paidAmount), name: paidName }));
    await loadPayroll();
  } catch (err: unknown) {
    const data = (err as { response?: { data?: { code?: string; balance?: number } } })?.response?.data;
    payModal.overpay = data?.code === 'overpayment';
    payModal.error = payModal.overpay
      ? t('salaries.overpay', { amount: money(data?.balance) })
      : apiErrorMessage(err, t('salaries.payFailed'));
  } finally {
    payModal.saving = false;
  }
}

async function cancelPayout(row: PayrollRow, payout: Payout) {
  if (!payout.id) return;
  const ok = await confirmDialog({
    title: t('salaries.cancelPayoutConfirm', { amount: money(payout.amount), name: row.teacher_name }),
    message: t('salaries.cancelPayoutHint'),
    danger: true,
    confirmText: t('salaries.cancelPayout'),
  });
  if (!ok) return;
  try {
    await client.delete(`/finance/payroll/payouts/${payout.id}`);
    toast.success(t('salaries.payoutCancelled'));
    await loadPayroll();
  } catch (err: unknown) {
    toast.error(apiErrorMessage(err, t('salaries.cancelPayoutFailed')));
  }
}

// Close / reopen the month (CEO only)
const monthModal = reactive({
  show: false,
  mode: 'close' as 'close' | 'reopen',
  reason: '',
  error: '',
  saving: false,
});

function openMonthModal(mode: 'close' | 'reopen') {
  monthModal.mode = mode;
  monthModal.reason = '';
  monthModal.error = '';
  monthModal.show = true;
}

async function submitMonth() {
  if (monthModal.mode === 'reopen' && monthModal.reason.trim().length < 3) {
    monthModal.error = t('salaries.reopenReasonRequired');
    return;
  }
  monthModal.saving = true;
  monthModal.error = '';
  try {
    await client.post(`/finance/months/${monthModal.mode}`, {
      month: selectedMonth.value,
      ...(monthModal.mode === 'reopen' ? { reason: monthModal.reason.trim() } : {}),
    });
    const closing = monthModal.mode === 'close';
    monthModal.show = false;
    toast.success(closing ? t('salaries.monthClosedToast', { month: monthTitle.value }) : t('salaries.monthReopenedToast', { month: monthTitle.value }));
    await loadPayroll();
  } catch (err: unknown) {
    monthModal.error = apiErrorMessage(err);
  } finally {
    monthModal.saving = false;
  }
}

// Salary correction (CEO only): + or − with a reason, shown in the row
const adjModal = reactive({
  show: false,
  row: null as PayrollRow | null,
  sign: 1 as 1 | -1,
  amount: '' as number | '',
  reason: '',
  error: '',
  saving: false,
});

function openAdjustment(row: PayrollRow) {
  adjModal.row = row;
  adjModal.sign = 1;
  adjModal.amount = '';
  adjModal.reason = '';
  adjModal.error = '';
  adjModal.show = true;
}

async function submitAdjustment() {
  if (!adjModal.row) return;
  if (!Number.isInteger(adjModal.amount) || Number(adjModal.amount) <= 0) {
    adjModal.error = t('finance.amountPositive');
    return;
  }
  if (adjModal.reason.trim().length < 3) {
    adjModal.error = t('salaries.adjReasonRequired');
    return;
  }
  adjModal.saving = true;
  adjModal.error = '';
  try {
    await client.post('/finance/payroll/adjustments', {
      person_id: adjModal.row.person_id,
      month: selectedMonth.value,
      amount: adjModal.sign * Number(adjModal.amount),
      reason: adjModal.reason.trim(),
    });
    adjModal.show = false;
    toast.success(t('salaries.adjSaved'));
    await loadPayroll();
  } catch (err: unknown) {
    adjModal.error = apiErrorMessage(err, t('salaries.adjSaveFailed'));
  } finally {
    adjModal.saving = false;
  }
}

async function deleteAdjustment(row: PayrollRow, adj: Adjustment) {
  const ok = await confirmDialog({
    title: t('salaries.adjDeleteConfirm', { amount: `${adj.amount > 0 ? '+' : '−'}${money(Math.abs(adj.amount))}`, name: row.teacher_name }),
    message: adj.reason,
    danger: true,
  });
  if (!ok) return;
  try {
    await client.delete(`/finance/payroll/adjustments/${adj.id}`);
    toast.success(t('toast.deleted'));
    await loadPayroll();
  } catch (err: unknown) {
    toast.error(apiErrorMessage(err, t('salaries.adjDeleteFailed')));
  }
}

// ================= Rates =================
const rates = ref<SalaryRow[]>([]);
const ratesLoading = ref(true);
const teachers = ref<Option[]>([]);
const staff = ref<Option[]>([]);
const groups = ref<Option[]>([]);
const courses = ref<Option[]>([]);

const panel = reactive({
  show: false,
  editing: null as SalaryRow | null,
  person_id: '' as number | '',
  amount: '' as number | '',
  course_id: '' as number | '',
  group_id: '' as number | '',
  effective_from: '',
  effective_to: '',
  error: '',
  saving: false,
});

const panelIsTeacher = computed(() => teachers.value.some((t) => t.id === panel.person_id));

async function loadRates() {
  ratesLoading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<SalaryRow[]>>('/salary-settings');
    rates.value = data.data;
  } finally {
    ratesLoading.value = false;
  }
}

async function loadOptions() {
  const safe = async <T,>(url: string, params?: Record<string, string>) => {
    try {
      const { data } = await client.get<ApiEnvelope<T[]>>(url, { params });
      return data.data;
    } catch {
      return [] as T[];
    }
  };
  const [t, s, g, c, b] = await Promise.all([
    safe<{ id: number; name: string }>('/user', { user_type: 'teacher' }),
    safe<{ id: number; name: string }>('/user', { user_type: 'staff' }),
    safe<{ id: number; name: string }>('/groups'),
    safe<{ id: number; name: string }>('/courses'),
    safe<{ id: number; name: string }>('/branch'),
  ]);
  teachers.value = t.map((x) => ({ id: x.id, name: x.name }));
  staff.value = s.map((x) => ({ id: x.id, name: x.name }));
  groups.value = g.map((x) => ({ id: x.id, name: x.name }));
  courses.value = c.map((x) => ({ id: x.id, name: x.name }));
  branches.value = b.map((x) => ({ id: x.id, name: x.name }));
}

function rateText(r: SalaryRow) {
  return r.salary_type === 'percent' ? `${r.amount}%` : t('payments.perMonth', { amount: money(r.amount) });
}

function rateScope(r: SalaryRow) {
  if (r.person_kind === 'staff') return t('salaries.fixedMonthly');
  if (r.group_id) return t('salaries.forGroup', { name: r.group });
  if (r.course_id) return t('salaries.forCourse', { name: r.course });
  return t('salaries.generalPercent');
}

function openRate(r?: SalaryRow) {
  panel.editing = r ?? null;
  panel.person_id = r?.teacher_id ?? '';
  panel.amount = r ? r.amount : '';
  panel.course_id = r?.course_id ?? '';
  panel.group_id = r?.group_id ?? '';
  panel.effective_from = r?.effective_from ?? '';
  panel.effective_to = r?.effective_to ?? '';
  panel.error = '';
  panel.show = true;
}

async function saveRate() {
  panel.error = '';
  if (panel.person_id === '') {
    panel.error = t('salaries.choosePerson');
    return;
  }
  if (!Number.isInteger(panel.amount) || Number(panel.amount) < 0) {
    panel.error = panelIsTeacher.value ? t('salaries.percentRange') : t('salaries.amountNonNegative');
    return;
  }
  if (panelIsTeacher.value && Number(panel.amount) > 100) {
    panel.error = t('salaries.percentRange');
    return;
  }
  const payload = {
    teacher_id: panel.person_id,
    salary_type: panelIsTeacher.value ? 'percent' : 'fixed',
    amount: panel.amount,
    course_id: panelIsTeacher.value && panel.course_id !== '' ? panel.course_id : null,
    group_id: panelIsTeacher.value && panel.group_id !== '' ? panel.group_id : null,
    effective_from: panel.effective_from || null,
    effective_to: panel.effective_to || null,
  };
  panel.saving = true;
  try {
    if (panel.editing) {
      await client.patch(`/salary-settings/${panel.editing.id}`, payload);
    } else {
      await client.post('/salary-settings', payload);
    }
    panel.show = false;
    toast.success(t('toast.saved'));
    await Promise.all([loadRates(), loadPayroll()]);
  } catch (err: unknown) {
    panel.error = apiErrorMessage(err, t('errors.saveFailed'));
  } finally {
    panel.saving = false;
  }
}

async function deleteRate() {
  if (!panel.editing) return;
  const ok = await confirmDialog({
    title: t('salaries.rateDeleteConfirm', { name: panel.editing.teacher, rate: rateText(panel.editing) }),
    message: t('salaries.rateDeleteHint'),
    danger: true,
  });
  if (!ok || !panel.editing) return;
  try {
    await client.delete(`/salary-settings/${panel.editing.id}`);
    panel.show = false;
    toast.success(t('toast.deleted'));
    await Promise.all([loadRates(), loadPayroll()]);
  } catch (err: unknown) {
    panel.error = apiErrorMessage(err, t('errors.deleteFailed'));
  }
}

onMounted(async () => {
  await Promise.all([loadPayroll(), loadRates(), loadOptions()]);
});
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-fb-text">{{ t('nav.salaries') }}</h1>
        <p class="mt-0.5 text-sm text-fb-secondary">
          {{ t('salaries.subtitle') }}
        </p>
      </div>
      <button
        v-if="activeTab === 'settings' && canWriteFinance"
        type="button"
        class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-semibold text-white shadow-sm"
        @click="openRate()"
      >
        + {{ t('salaries.addRate') }}
      </button>
    </div>

    <div class="flex border-b border-fb-line">
      <button
        type="button"
        class="border-b-2 px-6 py-3 text-sm font-semibold"
        :class="activeTab === 'payroll' ? 'border-fb-blue text-fb-blue' : 'border-transparent text-fb-secondary'"
        @click="activeTab = 'payroll'"
      >
        📑 {{ t('salaries.payrollTab') }}
      </button>
      <button
        type="button"
        class="border-b-2 px-6 py-3 text-sm font-semibold"
        :class="activeTab === 'settings' ? 'border-fb-blue text-fb-blue' : 'border-transparent text-fb-secondary'"
        @click="activeTab = 'settings'"
      >
        ⚙️ {{ t('salaries.ratesTab') }} ({{ rates.length }})
      </button>
    </div>

    <!-- ================= Payroll ================= -->
    <div v-if="activeTab === 'payroll'" class="space-y-6">
      <div class="flex flex-wrap items-center gap-3 rounded-2xl border border-fb-line bg-fb-card p-4">
        <span class="text-sm font-semibold text-fb-text">{{ t('common.month') }}:</span>
        <div class="flex items-center gap-1 rounded-xl border border-fb-line bg-white p-1">
          <button type="button" class="rounded-lg px-2.5 py-1 text-xs text-fb-secondary hover:bg-fb-canvas" @click="shiftMonth(-1)">◀</button>
          <input v-model="selectedMonth" type="month" class="border-none bg-transparent px-2 py-0.5 text-sm font-bold focus:outline-none" @change="loadPayroll" />
          <button type="button" class="rounded-lg px-2.5 py-1 text-xs text-fb-secondary hover:bg-fb-canvas" @click="shiftMonth(1)">▶</button>
        </div>
        <span
          v-if="monthClosed"
          class="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700"
        >
          🔒 {{ t('salaries.monthClosed') }}
        </span>
        <button
          v-if="auth.isCeo && canClose"
          type="button"
          class="ml-auto rounded-lg border border-slate-400 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-fb-canvas"
          @click="openMonthModal('close')"
        >
          🔒 {{ t('salaries.closeMonthNamed', { month: monthTitle }) }}
        </button>
        <button
          v-if="auth.isCeo && monthClosed"
          type="button"
          class="ml-auto rounded-lg border border-rose-300 px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-50"
          @click="openMonthModal('reopen')"
        >
          {{ t('salaries.reopenMonth') }}
        </button>
      </div>

      <div v-if="monthClosed" class="rounded-2xl border border-slate-300 bg-slate-50 px-5 py-3 text-sm text-slate-700">
        <strong class="capitalize">{{ monthTitle }}</strong> — {{ t('salaries.closedOn', { date: monthClosed.closed_at }) }}{{ monthClosed.closed_by ? ` (${monthClosed.closed_by})` : '' }}.
        {{ t('salaries.closedText') }}
      </div>

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="text-xs font-semibold uppercase tracking-wider text-fb-secondary">{{ t('salaries.payable') }}</div>
          <div class="mt-2 text-2xl font-black text-fb-text">{{ money(payrollSummary.total_accrued) }} <span class="text-xs text-fb-secondary">{{ t('common.sum') }}</span></div>
          <div class="mt-1 text-xs text-fb-secondary">{{ t('salaries.payableHint') }}</div>
        </div>
        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="text-xs font-semibold uppercase tracking-wider text-amber-700">{{ t('salaries.waiting') }}</div>
          <div class="mt-2 text-2xl font-black text-amber-700">{{ money(payrollSummary.total_waiting ?? 0) }} <span class="text-xs text-fb-secondary">{{ t('common.sum') }}</span></div>
          <div class="mt-1 text-xs text-fb-secondary">{{ t('salaries.waitingHint') }}</div>
        </div>
        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="text-xs font-semibold uppercase tracking-wider text-emerald-700">{{ t('salaries.paid') }}</div>
          <div class="mt-2 text-2xl font-black text-emerald-700">{{ money(payrollSummary.total_paid) }} <span class="text-xs text-fb-secondary">{{ t('common.sum') }}</span></div>
        </div>
        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="text-xs font-semibold uppercase tracking-wider text-rose-700">{{ t('salaries.leftToPay') }}</div>
          <div class="mt-2 text-2xl font-black text-rose-700">{{ money(payrollSummary.total_balance) }} <span class="text-xs text-fb-secondary">{{ t('common.sum') }}</span></div>
          <div class="mt-1 text-xs text-fb-secondary">{{ t('salaries.leftToPayHint') }}</div>
        </div>
      </div>

      <div class="overflow-hidden rounded-2xl border border-fb-line bg-fb-card shadow-sm">
        <div v-if="payrollLoading" class="p-12 text-center text-fb-secondary">{{ t('salaries.counting') }}</div>
        <div v-else-if="payrollError" class="p-12 text-center text-fb-danger">{{ payrollError }}</div>
        <div v-else-if="!payrollRows.length" class="p-12 text-center text-fb-secondary">{{ t('salaries.noData') }}</div>
        <table v-else class="w-full text-left text-sm">
          <thead class="border-b border-fb-line bg-fb-canvas text-xs font-semibold uppercase tracking-wider text-fb-secondary">
            <tr>
              <th class="px-5 py-3">{{ t('salaries.who') }}</th>
              <th class="px-5 py-3 text-right">{{ t('salaries.payable') }}</th>
              <th class="px-5 py-3 text-right">{{ t('salaries.waiting') }}</th>
              <th class="px-5 py-3 text-right">{{ t('salaries.paid') }}</th>
              <th class="px-5 py-3 text-right">{{ t('months.left') }}</th>
              <th class="px-5 py-3">{{ t('common.status') }}</th>
              <th class="px-5 py-3 text-right" />
            </tr>
          </thead>
          <tbody class="divide-y divide-fb-line">
            <template v-for="row in payrollRows" :key="row.person_id">
              <tr class="hover:bg-fb-hover/40">
                <td class="px-5 py-3">
                  <div class="font-semibold text-fb-text">
                    {{ row.teacher_name }}
                    <span v-if="!row.is_active" class="ml-1 rounded bg-gray-100 px-1.5 py-0.5 text-[11px] font-medium text-gray-600">{{ t('conversion.archivedLabel') }}</span>
                  </div>
                  <div class="text-xs text-fb-secondary">{{ kindLabel(row) }}</div>
                </td>
                <td class="px-5 py-3 text-right font-semibold">
                  {{ money(row.accrued) }}
                  <div v-if="row.adjustments.length" class="text-[11px] font-normal text-fb-secondary">
                    {{ t('salaries.inclAdjustments') }} {{ row.accrued - row.accrued_base >= 0 ? '+' : '−' }}{{ money(Math.abs(row.accrued - row.accrued_base)) }}
                  </div>
                </td>
                <td class="px-5 py-3 text-right text-amber-700">{{ row.waiting ? money(row.waiting) : '—' }}</td>
                <td class="px-5 py-3 text-right text-emerald-700">{{ money(row.paid) }}</td>
                <td class="px-5 py-3 text-right font-semibold text-rose-700">{{ money(row.balance) }}</td>
                <td class="px-5 py-3">
                  <span class="rounded-full px-2.5 py-0.5 text-xs font-semibold" :class="statusClass(row)">{{ statusLabel(row) }}</span>
                </td>
                <td class="whitespace-nowrap px-5 py-3 text-right">
                  <button
                    type="button"
                    class="mr-2 text-xs font-medium text-fb-blue hover:underline"
                    @click="expanded = expanded === row.person_id ? null : row.person_id"
                  >
                    {{ expanded === row.person_id ? t('salaries.hide') : t('salaries.howCounted') }}
                  </button>
                  <button
                    v-if="canWriteFinance"
                    type="button"
                    class="rounded-lg bg-fb-blue px-3 py-1.5 text-xs font-semibold text-white"
                    @click="openPay(row)"
                  >
                    {{ t('salaries.pay') }}
                  </button>
                </td>
              </tr>
              <tr v-if="expanded === row.person_id" class="bg-fb-canvas/50">
                <td colspan="7" class="px-5 py-4">
                  <div v-if="row.kind === 'teacher'">
                    <p class="mb-2 text-xs text-fb-secondary">
                      {{ t('salaries.howText') }}
                    </p>
                    <table class="w-full text-xs">
                      <thead class="text-fb-secondary">
                        <tr>
                          <th class="py-1 text-left">{{ t('schedule.group') }}</th>
                          <th class="py-1 text-left">{{ t('common.branch') }}</th>
                          <th class="py-1 text-right">{{ t('salaries.heldLessons') }}</th>
                          <th class="py-1 text-right">{{ t('salaries.studentLessons') }}</th>
                          <th class="py-1 text-right">{{ t('salaryType.percent') }}</th>
                          <th class="py-1 text-right">{{ t('salaries.earned') }}</th>
                          <th class="py-1 text-right">{{ t('salaries.waitingShort') }}</th>
                          <th class="py-1 text-right">{{ t('salaries.payable') }}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="g in row.groups" :key="g.group_id">
                          <td class="py-1">{{ g.group }}</td>
                          <td class="py-1">{{ g.branch }}</td>
                          <td class="py-1 text-right">{{ g.held_lessons }}</td>
                          <td class="py-1 text-right">{{ g.student_lessons }}</td>
                          <td class="py-1 text-right" :class="g.percent_scope === 'не задан' ? 'text-rose-700' : ''">
                            {{ g.percent }}% <span class="text-fb-secondary">({{ percentScopeLabel(g.percent_scope) }})</span>
                          </td>
                          <td class="py-1 text-right">{{ money(g.earned) }}</td>
                          <td class="py-1 text-right text-amber-700">
                            {{ g.waiting ? money(g.waiting) : '—' }}
                            <span v-if="g.students_unpaid" class="text-fb-secondary">({{ t('months.summaryDebtors', { count: g.students_unpaid }) }})</span>
                          </td>
                          <td class="py-1 text-right font-semibold">{{ money(g.accrued) }}</td>
                        </tr>
                        <tr v-if="!row.groups.length"><td colspan="8" class="py-1 text-fb-secondary">{{ t('salaries.noGroupsMonth') }}</td></tr>
                      </tbody>
                    </table>
                  </div>
                  <p v-else class="text-xs text-fb-secondary">
                    {{ t('salaries.fixedMonthlyAmount') }}: <strong>{{ row.fixed_amount === null ? t('salaries.notSet') : t('common.sumAmount', { amount: money(row.fixed_amount) }) }}</strong>
                  </p>
                  <p v-if="row.month_closed" class="mt-2 text-[11px] text-slate-600">
                    🔒 {{ t('salaries.rowClosedText') }}
                  </p>
                  <div v-if="row.adjustments.length || auth.isCeo" class="mt-3">
                    <p class="mb-1 flex items-center gap-3 text-xs font-semibold text-fb-text">
                      {{ t('salaries.adjustments') }}
                      <button
                        v-if="auth.isCeo"
                        type="button"
                        class="font-medium text-fb-blue hover:underline"
                        @click="openAdjustment(row)"
                      >
                        + {{ t('salaries.addAdjustment') }}
                      </button>
                    </p>
                    <p v-if="!row.adjustments.length" class="text-xs text-fb-secondary">{{ t('salaries.noAdjustments') }}</p>
                    <ul v-else class="space-y-1 text-xs">
                      <li v-for="a in row.adjustments" :key="a.id" class="flex items-center gap-3">
                        <span class="font-semibold" :class="a.amount >= 0 ? 'text-emerald-700' : 'text-rose-700'">
                          {{ a.amount >= 0 ? '+' : '−' }}{{ t('common.sumAmount', { amount: money(Math.abs(a.amount)) }) }}
                        </span>
                        <span class="text-fb-secondary">{{ a.date }} · {{ a.reason }}{{ a.by ? ` · ${a.by}` : '' }}</span>
                        <button v-if="auth.isCeo" type="button" class="text-rose-700 hover:underline" @click="deleteAdjustment(row, a)">
                          {{ t('common.delete') }}
                        </button>
                      </li>
                    </ul>
                  </div>
                  <div class="mt-3">
                    <p class="mb-1 text-xs font-semibold text-fb-text">{{ t('salaries.payoutsMonth') }}</p>
                    <p v-if="!row.payouts.length" class="text-xs text-fb-secondary">{{ t('salaries.noPayouts') }}</p>
                    <ul v-else class="space-y-1 text-xs">
                      <li v-for="(p, idx) in row.payouts" :key="p.id ?? `legacy-${idx}`" class="flex items-center gap-3">
                        <span class="font-semibold">{{ t('common.sumAmount', { amount: money(p.amount) }) }}</span>
                        <span class="text-fb-secondary">{{ p.date }} {{ p.comment }}</span>
                        <button
                          v-if="canWriteFinance && p.id"
                          type="button"
                          class="text-rose-700 hover:underline"
                          @click="cancelPayout(row, p)"
                        >
                          {{ t('salaries.cancelPayout') }}
                        </button>
                      </li>
                    </ul>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ================= Rates ================= -->
    <div v-else class="overflow-hidden rounded-2xl border border-fb-line bg-fb-card shadow-sm">
      <div v-if="ratesLoading" class="p-12 text-center text-fb-secondary">{{ t('common.loading') }}</div>
      <div v-else-if="!rates.length" class="p-12 text-center text-fb-secondary">
        {{ t('salaries.noRates') }}
      </div>
      <table v-else class="w-full text-left text-sm">
        <thead class="border-b border-fb-line bg-fb-canvas text-xs font-semibold uppercase tracking-wider text-fb-secondary">
          <tr>
            <th class="px-5 py-3">{{ t('salaries.who') }}</th>
            <th class="px-5 py-3">{{ t('salaries.rate') }}</th>
            <th class="px-5 py-3">{{ t('salaries.appliesTo') }}</th>
            <th class="px-5 py-3">{{ t('common.period') }}</th>
            <th class="px-5 py-3">{{ t('salaries.changedBy') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-fb-line">
          <tr
            v-for="r in rates"
            :key="r.id"
            class="hover:bg-fb-hover/40"
            :class="canWriteFinance ? 'cursor-pointer' : ''"
            @click="canWriteFinance && openRate(r)"
          >
            <td class="px-5 py-3 font-semibold">{{ r.teacher }}</td>
            <td class="px-5 py-3 font-semibold text-fb-blue">{{ rateText(r) }}</td>
            <td class="px-5 py-3">{{ rateScope(r) }}</td>
            <td class="px-5 py-3 text-xs text-fb-secondary">{{ r.effective_from || '…' }} — {{ r.effective_to || '…' }}</td>
            <td class="px-5 py-3 text-xs text-fb-secondary">{{ r.updated_by }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Rate panel -->
    <div v-if="panel.show" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="panel.show = false" />
      <div class="drawer-panel-fb max-w-lg">
        <div class="flex items-center justify-between border-b px-6 py-4">
          <h2 class="text-lg font-semibold">{{ panel.editing ? t('salaries.rate') : t('salaries.newRate') }}</h2>
          <button type="button" :aria-label="t('common.close')" @click="panel.show = false">✕</button>
        </div>
        <div class="flex-1 space-y-4 overflow-y-auto p-6">
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('salaries.person') }}</label>
            <select v-model="panel.person_id" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm">
              <option value="">— {{ t('common.select') }} —</option>
              <optgroup :label="t('salaries.teachersPercent')">
                <option v-for="t in teachers" :key="t.id" :value="t.id">{{ t.name }}</option>
              </optgroup>
              <optgroup :label="t('salaries.staffFixed')">
                <option v-for="s in staff" :key="s.id" :value="s.id">{{ s.name }}</option>
              </optgroup>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">
              {{ panelIsTeacher ? t('salaries.percentLabel') : t('salaries.monthlyAmountLabel') }}
            </label>
            <input
              v-model.number="panel.amount"
              type="number"
              min="0"
              :max="panelIsTeacher ? 100 : undefined"
              step="1"
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm"
            />
          </div>
          <template v-if="panelIsTeacher">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('salaries.onlyGroup') }}</label>
              <select v-model="panel.group_id" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm">
                <option value="">— {{ t('salaries.allTeacherGroups') }} —</option>
                <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('salaries.onlyCourse') }}</label>
              <select v-model="panel.course_id" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm">
                <option value="">— {{ t('conversion.allCourses') }} —</option>
                <option v-for="c in courses" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
              <p class="mt-1 text-[11px] text-fb-secondary">
                {{ t('salaries.percentOrder') }}
              </p>
            </div>
          </template>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('salaries.validFrom') }}</label>
              <input v-model="panel.effective_from" type="date" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('salaries.validTo') }}</label>
              <input v-model="panel.effective_to" type="date" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm" />
            </div>
          </div>
          <p class="text-[11px] text-fb-secondary">
            <template v-if="panelIsTeacher">
              {{ t('salaries.percentHint') }}
            </template>
            <template v-else>
              {{ t('salaries.fixedHint') }}
            </template>
          </p>
          <p v-if="panel.error" class="text-sm text-fb-danger">{{ panel.error }}</p>
        </div>
        <div class="flex gap-2 border-t px-6 py-4">
          <button type="button" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" :disabled="panel.saving" @click="saveRate">
            {{ panel.saving ? t('common.saving') : t('common.save') }}
          </button>
          <button v-if="panel.editing" type="button" class="rounded-lg border border-red-300 px-5 py-2 text-sm text-fb-danger" @click="deleteRate">
            {{ t('common.delete') }}
          </button>
          <button type="button" class="rounded-lg border px-5 py-2 text-sm" @click="panel.show = false">{{ t('common.cancel') }}</button>
        </div>
      </div>
    </div>

    <!-- Pay modal -->
    <div v-if="payModal.show" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div class="w-full max-w-md overflow-hidden rounded-2xl bg-fb-card shadow-2xl">
        <div class="border-b border-fb-line px-6 py-4">
          <h2 class="text-lg font-semibold text-fb-text">{{ t('salaries.payTitle') }}</h2>
          <p class="text-sm text-fb-secondary">
            {{ payModal.row?.teacher_name }} · {{ monthTitle }} ·
            {{ t('salaries.payableLeft', { payable: money(payModal.row?.accrued), left: money(payModal.row?.balance) }) }}
          </p>
        </div>
        <div class="space-y-3 px-6 py-5">
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.amount') }}</label>
            <input v-model.number="payModal.amount" type="number" min="1" step="1" class="w-full rounded-lg border border-fb-line px-3 py-2" />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('expenses.method') }}</label>
            <select v-model="payModal.method" class="w-full rounded-lg border border-fb-line px-3 py-2">
              <option value="cash">{{ t('payMethod.cash') }}</option>
              <option value="card">{{ t('payMethod.card') }}</option>
              <option value="transfer">{{ t('payMethod.transfer') }}</option>
            </select>
          </div>
          <div v-if="payNeedsBranch">
            <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('salaries.payBranch') }}</label>
            <select v-model="payModal.branch_id" class="w-full rounded-lg border border-fb-line px-3 py-2">
              <option value="">— {{ t('staff.chooseBranch') }} —</option>
              <option v-for="b in branches" :key="b.id" :value="b.id">{{ b.name }}</option>
            </select>
          </div>
          <p v-else-if="payModal.row?.kind === 'teacher'" class="text-[11px] text-fb-secondary">
            {{ t('salaries.payBranchesHint') }}
          </p>
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.comment') }}</label>
            <input v-model="payModal.comment" class="w-full rounded-lg border border-fb-line px-3 py-2" />
          </div>
          <label v-if="payModal.overpay && auth.isCeo" class="flex items-center gap-2 text-sm text-rose-700">
            <input v-model="payModal.force" type="checkbox" />
            {{ t('salaries.payOver') }}
          </label>
          <p v-if="payModal.error" class="text-sm text-fb-danger">{{ payModal.error }}</p>
        </div>
        <div class="flex justify-end gap-3 border-t border-fb-line px-6 py-4">
          <button type="button" class="rounded-lg border border-fb-line px-5 py-2 text-sm" @click="payModal.show = false">{{ t('common.cancel') }}</button>
          <button
            type="button"
            class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white disabled:opacity-50"
            :disabled="payModal.saving"
            @click="submitPay"
          >
            {{ payModal.saving ? t('common.saving') : t('salaries.pay') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Close / reopen month modal -->
    <div v-if="monthModal.show" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div class="w-full max-w-md overflow-hidden rounded-2xl bg-fb-card shadow-2xl">
        <div class="border-b border-fb-line px-6 py-4">
          <h2 class="text-lg font-semibold text-fb-text">
            {{ monthModal.mode === 'close' ? t('salaries.closeMonthQ', { month: monthTitle }) : t('salaries.reopenMonthQ', { month: monthTitle }) }}
          </h2>
        </div>
        <div class="space-y-3 px-6 py-5 text-sm text-fb-text">
          <template v-if="monthModal.mode === 'close'">
            <p>{{ t('salaries.afterClose') }}</p>
            <ul class="list-disc space-y-1 pl-5 text-fb-secondary">
              <li>{{ t('salaries.afterClose1') }}</li>
              <li>{{ t('salaries.afterClose2') }}</li>
              <li>{{ t('salaries.afterClose3') }}</li>
            </ul>
            <p class="text-fb-secondary">{{ t('salaries.afterCloseCheck') }}</p>
          </template>
          <template v-else>
            <p class="text-fb-secondary">
              {{ t('salaries.reopenText') }}
            </p>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('salaries.reason') }}</label>
              <input v-model="monthModal.reason" class="w-full rounded-lg border border-fb-line px-3 py-2" :placeholder="t('salaries.reopenPlaceholder')" />
            </div>
          </template>
          <p v-if="monthModal.error" class="text-sm text-fb-danger">{{ monthModal.error }}</p>
        </div>
        <div class="flex justify-end gap-3 border-t border-fb-line px-6 py-4">
          <button type="button" class="rounded-lg border border-fb-line px-5 py-2 text-sm" @click="monthModal.show = false">{{ t('common.cancel') }}</button>
          <button
            type="button"
            class="rounded-lg px-5 py-2 text-sm font-medium text-white disabled:opacity-50"
            :class="monthModal.mode === 'close' ? 'bg-slate-700' : 'bg-rose-600'"
            :disabled="monthModal.saving"
            @click="submitMonth"
          >
            {{ monthModal.saving ? t('common.saving') : monthModal.mode === 'close' ? t('salaries.closeMonth') : t('salaries.reopenMonth') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Salary correction modal -->
    <div v-if="adjModal.show" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div class="w-full max-w-md overflow-hidden rounded-2xl bg-fb-card shadow-2xl">
        <div class="border-b border-fb-line px-6 py-4">
          <h2 class="text-lg font-semibold text-fb-text">{{ t('salaries.adjTitle') }}</h2>
          <p class="text-sm text-fb-secondary">{{ adjModal.row?.teacher_name }} · {{ monthTitle }} · {{ t('salaries.payable') }} {{ money(adjModal.row?.accrued) }}</p>
        </div>
        <div class="space-y-3 px-6 py-5">
          <div class="flex gap-2">
            <button
              type="button"
              class="flex-1 rounded-lg border px-3 py-2 text-sm font-semibold"
              :class="adjModal.sign === 1 ? 'border-emerald-500 bg-emerald-50 text-emerald-700' : 'border-fb-line text-fb-secondary'"
              @click="adjModal.sign = 1"
            >
              + {{ t('salaries.adjAdd') }}
            </button>
            <button
              type="button"
              class="flex-1 rounded-lg border px-3 py-2 text-sm font-semibold"
              :class="adjModal.sign === -1 ? 'border-rose-500 bg-rose-50 text-rose-700' : 'border-fb-line text-fb-secondary'"
              @click="adjModal.sign = -1"
            >
              − {{ t('salaries.adjRemove') }}
            </button>
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.amount') }}</label>
            <input v-model.number="adjModal.amount" type="number" min="1" step="1" class="w-full rounded-lg border border-fb-line px-3 py-2" />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('salaries.reason') }}</label>
            <input v-model="adjModal.reason" class="w-full rounded-lg border border-fb-line px-3 py-2" :placeholder="t('salaries.adjPlaceholder')" />
          </div>
          <p class="text-[11px] text-fb-secondary">{{ t('salaries.adjHint') }}</p>
          <p v-if="adjModal.error" class="text-sm text-fb-danger">{{ adjModal.error }}</p>
        </div>
        <div class="flex justify-end gap-3 border-t border-fb-line px-6 py-4">
          <button type="button" class="rounded-lg border border-fb-line px-5 py-2 text-sm" @click="adjModal.show = false">{{ t('common.cancel') }}</button>
          <button
            type="button"
            class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white disabled:opacity-50"
            :disabled="adjModal.saving"
            @click="submitAdjustment"
          >
            {{ adjModal.saving ? t('common.saving') : t('common.save') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
