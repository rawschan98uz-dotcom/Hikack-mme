<script setup lang="ts">
import { currentMonthIso } from '../utils/dates';
import { computed, onMounted, reactive, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';

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

const MONTH_NAMES = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
const monthTitle = computed(() => {
  const [y, m] = selectedMonth.value.split('-').map(Number);
  return m ? `${MONTH_NAMES[m - 1]} ${y}` : selectedMonth.value;
});

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
  } catch (err: any) {
    payrollError.value = err?.response?.data?.message || 'Не удалось загрузить ведомость';
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
  if (row.status === 'paid') return row.overpaid ? `Выплачено (+${money(row.overpaid)} сверх)` : 'Выплачено';
  if (row.status === 'partial') return 'Частично';
  if (row.status === 'unpaid') return 'Не выплачено';
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
  payModal.comment = `Зарплата за ${selectedMonth.value}: ${row.teacher_name}`;
  payModal.branch_id = '';
  payModal.force = false;
  payModal.overpay = false;
  payModal.error = '';
  payModal.show = true;
}

async function submitPay() {
  if (!payModal.row) return;
  if (!Number.isInteger(payModal.amount) || payModal.amount <= 0) {
    payModal.error = 'Сумма — целое положительное число.';
    return;
  }
  if (payNeedsBranch.value && payModal.branch_id === '') {
    payModal.error = 'Выберите филиал, на который записать зарплату.';
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
    payModal.show = false;
    await loadPayroll();
  } catch (err: any) {
    const data = err?.response?.data;
    payModal.overpay = data?.code === 'overpayment';
    payModal.error = payModal.overpay
      ? `Это больше начисленного: к выплате осталось ${money(data?.balance)} сум.`
      : data?.message || 'Не удалось провести выплату';
  } finally {
    payModal.saving = false;
  }
}

async function cancelPayout(row: PayrollRow, payout: Payout) {
  if (!payout.id) return;
  if (!window.confirm(`Отменить выплату ${money(payout.amount)} сум (${row.teacher_name})? Запись в расходах тоже будет удалена.`)) return;
  try {
    await client.delete(`/finance/payroll/payouts/${payout.id}`);
    await loadPayroll();
  } catch (err: any) {
    window.alert(err?.response?.data?.message || 'Не удалось отменить выплату');
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
    monthModal.error = 'Укажите причину, зачем открываете месяц.';
    return;
  }
  monthModal.saving = true;
  monthModal.error = '';
  try {
    await client.post(`/finance/months/${monthModal.mode}`, {
      month: selectedMonth.value,
      ...(monthModal.mode === 'reopen' ? { reason: monthModal.reason.trim() } : {}),
    });
    monthModal.show = false;
    await loadPayroll();
  } catch (err: any) {
    monthModal.error = err?.response?.data?.message || 'Не получилось';
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
    adjModal.error = 'Сумма — целое положительное число.';
    return;
  }
  if (adjModal.reason.trim().length < 3) {
    adjModal.error = 'Укажите причину поправки.';
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
    await loadPayroll();
  } catch (err: any) {
    adjModal.error = err?.response?.data?.message || 'Не удалось сохранить поправку';
  } finally {
    adjModal.saving = false;
  }
}

async function deleteAdjustment(row: PayrollRow, adj: Adjustment) {
  if (!window.confirm(`Удалить поправку ${adj.amount > 0 ? '+' : '−'}${money(Math.abs(adj.amount))} сум (${row.teacher_name})?`)) return;
  try {
    await client.delete(`/finance/payroll/adjustments/${adj.id}`);
    await loadPayroll();
  } catch (err: any) {
    window.alert(err?.response?.data?.message || 'Не удалось удалить поправку');
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
  return r.salary_type === 'percent' ? `${r.amount}%` : `${money(r.amount)} сум / мес`;
}

function rateScope(r: SalaryRow) {
  if (r.person_kind === 'staff') return 'Фикс в месяц';
  if (r.group_id) return `Группа: ${r.group}`;
  if (r.course_id) return `Курс: ${r.course}`;
  return 'Общий процент учителя';
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
    panel.error = 'Выберите учителя или сотрудника.';
    return;
  }
  if (!Number.isInteger(panel.amount) || Number(panel.amount) < 0) {
    panel.error = panelIsTeacher.value ? 'Процент — целое число от 0 до 100.' : 'Сумма — целое число, не меньше 0.';
    return;
  }
  if (panelIsTeacher.value && Number(panel.amount) > 100) {
    panel.error = 'Процент — целое число от 0 до 100.';
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
    await Promise.all([loadRates(), loadPayroll()]);
  } catch (err: any) {
    panel.error = err?.response?.data?.message || 'Не удалось сохранить';
  } finally {
    panel.saving = false;
  }
}

async function deleteRate() {
  if (!panel.editing || !window.confirm('Удалить эту ставку?')) return;
  try {
    await client.delete(`/salary-settings/${panel.editing.id}`);
    panel.show = false;
    await Promise.all([loadRates(), loadPayroll()]);
  } catch (err: any) {
    panel.error = err?.response?.data?.message || 'Не удалось удалить';
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
        <h1 class="text-2xl font-bold text-fb-text">Зарплаты</h1>
        <p class="mt-0.5 text-sm text-fb-secondary">
          Учителя — процент с оплаченных месяцев учеников за проведённые уроки, сотрудники — фиксированная сумма в месяц
        </p>
      </div>
      <button
        v-if="activeTab === 'settings' && canWriteFinance"
        type="button"
        class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-semibold text-white shadow-sm"
        @click="openRate()"
      >
        + Добавить ставку
      </button>
    </div>

    <div class="flex border-b border-fb-line">
      <button
        type="button"
        class="border-b-2 px-6 py-3 text-sm font-semibold"
        :class="activeTab === 'payroll' ? 'border-fb-blue text-fb-blue' : 'border-transparent text-fb-secondary'"
        @click="activeTab = 'payroll'"
      >
        📑 Ведомость
      </button>
      <button
        type="button"
        class="border-b-2 px-6 py-3 text-sm font-semibold"
        :class="activeTab === 'settings' ? 'border-fb-blue text-fb-blue' : 'border-transparent text-fb-secondary'"
        @click="activeTab = 'settings'"
      >
        ⚙️ Ставки ({{ rates.length }})
      </button>
    </div>

    <!-- ================= Payroll ================= -->
    <div v-if="activeTab === 'payroll'" class="space-y-6">
      <div class="flex flex-wrap items-center gap-3 rounded-2xl border border-fb-line bg-fb-card p-4">
        <span class="text-sm font-semibold text-fb-text">Месяц:</span>
        <div class="flex items-center gap-1 rounded-xl border border-fb-line bg-white p-1">
          <button type="button" class="rounded-lg px-2.5 py-1 text-xs text-fb-secondary hover:bg-fb-canvas" @click="shiftMonth(-1)">◀</button>
          <input v-model="selectedMonth" type="month" class="border-none bg-transparent px-2 py-0.5 text-sm font-bold focus:outline-none" @change="loadPayroll" />
          <button type="button" class="rounded-lg px-2.5 py-1 text-xs text-fb-secondary hover:bg-fb-canvas" @click="shiftMonth(1)">▶</button>
        </div>
        <span
          v-if="monthClosed"
          class="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700"
        >
          🔒 Месяц закрыт
        </span>
        <button
          v-if="auth.isCeo && canClose"
          type="button"
          class="ml-auto rounded-lg border border-slate-400 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-fb-canvas"
          @click="openMonthModal('close')"
        >
          🔒 Закрыть {{ monthTitle }}
        </button>
        <button
          v-if="auth.isCeo && monthClosed"
          type="button"
          class="ml-auto rounded-lg border border-rose-300 px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-50"
          @click="openMonthModal('reopen')"
        >
          Открыть месяц
        </button>
      </div>

      <div v-if="monthClosed" class="rounded-2xl border border-slate-300 bg-slate-50 px-5 py-3 text-sm text-slate-700">
        <strong class="capitalize">{{ monthTitle }}</strong> закрыт {{ monthClosed.closed_at }}{{ monthClosed.closed_by ? ` (${monthClosed.closed_by})` : '' }}.
        Оплаты, расходы, изъятия и отметки учителей с датой этого месяца менять нельзя; оклады сотрудников
        зафиксированы. Учителю доначисляется только когда ученик гасит долг за этот месяц. Исправление —
        «Поправкой» (CEO) или открыв месяц.
      </div>

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="text-xs font-semibold uppercase tracking-wider text-fb-secondary">К выплате</div>
          <div class="mt-2 text-2xl font-black text-fb-text">{{ money(payrollSummary.total_accrued) }} <span class="text-xs text-fb-secondary">UZS</span></div>
          <div class="mt-1 text-xs text-fb-secondary">С того, что ученики уже оплатили</div>
        </div>
        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="text-xs font-semibold uppercase tracking-wider text-amber-700">Ждёт оплаты учеников</div>
          <div class="mt-2 text-2xl font-black text-amber-700">{{ money(payrollSummary.total_waiting ?? 0) }} <span class="text-xs text-fb-secondary">UZS</span></div>
          <div class="mt-1 text-xs text-fb-secondary">Добавится к выплате, когда должники заплатят</div>
        </div>
        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="text-xs font-semibold uppercase tracking-wider text-emerald-700">Выплачено</div>
          <div class="mt-2 text-2xl font-black text-emerald-700">{{ money(payrollSummary.total_paid) }} <span class="text-xs text-fb-secondary">UZS</span></div>
        </div>
        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="text-xs font-semibold uppercase tracking-wider text-rose-700">Осталось выплатить</div>
          <div class="mt-2 text-2xl font-black text-rose-700">{{ money(payrollSummary.total_balance) }} <span class="text-xs text-fb-secondary">UZS</span></div>
          <div class="mt-1 text-xs text-fb-secondary">Сумма долгов каждому человеку</div>
        </div>
      </div>

      <div class="overflow-hidden rounded-2xl border border-fb-line bg-fb-card shadow-sm">
        <div v-if="payrollLoading" class="p-12 text-center text-fb-secondary">Считаю…</div>
        <div v-else-if="payrollError" class="p-12 text-center text-fb-danger">{{ payrollError }}</div>
        <div v-else-if="!payrollRows.length" class="p-12 text-center text-fb-secondary">Нет данных за этот месяц</div>
        <table v-else class="w-full text-left text-sm">
          <thead class="border-b border-fb-line bg-fb-canvas text-xs font-semibold uppercase tracking-wider text-fb-secondary">
            <tr>
              <th class="px-5 py-3">Кто</th>
              <th class="px-5 py-3 text-right">К выплате</th>
              <th class="px-5 py-3 text-right">Ждёт оплаты учеников</th>
              <th class="px-5 py-3 text-right">Выплачено</th>
              <th class="px-5 py-3 text-right">Осталось</th>
              <th class="px-5 py-3">Статус</th>
              <th class="px-5 py-3 text-right" />
            </tr>
          </thead>
          <tbody class="divide-y divide-fb-line">
            <template v-for="row in payrollRows" :key="row.person_id">
              <tr class="hover:bg-fb-hover/40">
                <td class="px-5 py-3">
                  <div class="font-semibold text-fb-text">
                    {{ row.teacher_name }}
                    <span v-if="!row.is_active" class="ml-1 rounded bg-gray-100 px-1.5 py-0.5 text-[11px] font-medium text-gray-600">в архиве</span>
                  </div>
                  <div class="text-xs text-fb-secondary">{{ row.kind_label }}</div>
                </td>
                <td class="px-5 py-3 text-right font-semibold">
                  {{ money(row.accrued) }}
                  <div v-if="row.adjustments.length" class="text-[11px] font-normal text-fb-secondary">
                    в т.ч. поправки {{ row.accrued - row.accrued_base >= 0 ? '+' : '−' }}{{ money(Math.abs(row.accrued - row.accrued_base)) }}
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
                    {{ expanded === row.person_id ? 'Скрыть' : 'Как посчитано' }}
                  </button>
                  <button
                    v-if="canWriteFinance"
                    type="button"
                    class="rounded-lg bg-fb-blue px-3 py-1.5 text-xs font-semibold text-white"
                    @click="openPay(row)"
                  >
                    Выплатить
                  </button>
                </td>
              </tr>
              <tr v-if="expanded === row.person_id" class="bg-fb-canvas/50">
                <td colspan="7" class="px-5 py-4">
                  <div v-if="row.kind === 'teacher'">
                    <p class="mb-2 text-xs text-fb-secondary">
                      Урок ученика = сумма его месяца ÷ уроков в этом месяце. Учитель получает свой процент за каждый
                      проведённый урок — но только с тех денег, что ученик уже заплатил. Заплатили 7 из 10 — к выплате
                      за семерых; остальное добавится, когда должники заплатят. Процент берётся тот, что был в день урока.
                    </p>
                    <table class="w-full text-xs">
                      <thead class="text-fb-secondary">
                        <tr>
                          <th class="py-1 text-left">Группа</th>
                          <th class="py-1 text-left">Филиал</th>
                          <th class="py-1 text-right">Уроков проведено</th>
                          <th class="py-1 text-right">Ученико-уроков</th>
                          <th class="py-1 text-right">Процент</th>
                          <th class="py-1 text-right">Заработано</th>
                          <th class="py-1 text-right">Ждёт оплаты</th>
                          <th class="py-1 text-right">К выплате</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="g in row.groups" :key="g.group_id">
                          <td class="py-1">{{ g.group }}</td>
                          <td class="py-1">{{ g.branch }}</td>
                          <td class="py-1 text-right">{{ g.held_lessons }}</td>
                          <td class="py-1 text-right">{{ g.student_lessons }}</td>
                          <td class="py-1 text-right" :class="g.percent_scope === 'не задан' ? 'text-rose-700' : ''">
                            {{ g.percent }}% <span class="text-fb-secondary">({{ g.percent_scope }})</span>
                          </td>
                          <td class="py-1 text-right">{{ money(g.earned) }}</td>
                          <td class="py-1 text-right text-amber-700">
                            {{ g.waiting ? money(g.waiting) : '—' }}
                            <span v-if="g.students_unpaid" class="text-fb-secondary">(должников: {{ g.students_unpaid }})</span>
                          </td>
                          <td class="py-1 text-right font-semibold">{{ money(g.accrued) }}</td>
                        </tr>
                        <tr v-if="!row.groups.length"><td colspan="8" class="py-1 text-fb-secondary">Нет групп и отметок «Я пришёл» за месяц</td></tr>
                      </tbody>
                    </table>
                  </div>
                  <p v-else class="text-xs text-fb-secondary">
                    Фиксированная сумма в месяц: <strong>{{ row.fixed_amount === null ? 'не задана' : money(row.fixed_amount) + ' сум' }}</strong>
                  </p>
                  <p v-if="row.month_closed" class="mt-2 text-[11px] text-slate-600">
                    🔒 Месяц закрыт: уроки и их проценты зафиксированы. Поздние изменения цен, процентов и расписания
                    сюда не попадают — добавляется только оплата учеником долга за этот месяц.
                  </p>
                  <div v-if="row.adjustments.length || auth.isCeo" class="mt-3">
                    <p class="mb-1 flex items-center gap-3 text-xs font-semibold text-fb-text">
                      Поправки
                      <button
                        v-if="auth.isCeo"
                        type="button"
                        class="font-medium text-fb-blue hover:underline"
                        @click="openAdjustment(row)"
                      >
                        + Добавить поправку
                      </button>
                    </p>
                    <p v-if="!row.adjustments.length" class="text-xs text-fb-secondary">Поправок нет</p>
                    <ul v-else class="space-y-1 text-xs">
                      <li v-for="a in row.adjustments" :key="a.id" class="flex items-center gap-3">
                        <span class="font-semibold" :class="a.amount >= 0 ? 'text-emerald-700' : 'text-rose-700'">
                          {{ a.amount >= 0 ? '+' : '−' }}{{ money(Math.abs(a.amount)) }} сум
                        </span>
                        <span class="text-fb-secondary">{{ a.date }} · {{ a.reason }}{{ a.by ? ` · ${a.by}` : '' }}</span>
                        <button v-if="auth.isCeo" type="button" class="text-rose-700 hover:underline" @click="deleteAdjustment(row, a)">
                          Удалить
                        </button>
                      </li>
                    </ul>
                  </div>
                  <div class="mt-3">
                    <p class="mb-1 text-xs font-semibold text-fb-text">Выплаты за месяц</p>
                    <p v-if="!row.payouts.length" class="text-xs text-fb-secondary">Выплат нет</p>
                    <ul v-else class="space-y-1 text-xs">
                      <li v-for="(p, idx) in row.payouts" :key="p.id ?? `legacy-${idx}`" class="flex items-center gap-3">
                        <span class="font-semibold">{{ money(p.amount) }} сум</span>
                        <span class="text-fb-secondary">{{ p.date }} {{ p.comment }}</span>
                        <button
                          v-if="canWriteFinance && p.id"
                          type="button"
                          class="text-rose-700 hover:underline"
                          @click="cancelPayout(row, p)"
                        >
                          Отменить
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
      <div v-if="ratesLoading" class="p-12 text-center text-fb-secondary">Загрузка…</div>
      <div v-else-if="!rates.length" class="p-12 text-center text-fb-secondary">
        Ставок нет. Добавьте учителю процент, сотруднику — сумму в месяц.
      </div>
      <table v-else class="w-full text-left text-sm">
        <thead class="border-b border-fb-line bg-fb-canvas text-xs font-semibold uppercase tracking-wider text-fb-secondary">
          <tr>
            <th class="px-5 py-3">Кто</th>
            <th class="px-5 py-3">Ставка</th>
            <th class="px-5 py-3">На что</th>
            <th class="px-5 py-3">Период</th>
            <th class="px-5 py-3">Изменил</th>
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
          <h2 class="text-lg font-semibold">{{ panel.editing ? 'Ставка' : 'Новая ставка' }}</h2>
          <button type="button" @click="panel.show = false">✕</button>
        </div>
        <div class="flex-1 space-y-4 overflow-y-auto p-6">
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">Учитель или сотрудник</label>
            <select v-model="panel.person_id" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm">
              <option value="">— Выберите —</option>
              <optgroup label="Учителя (процент)">
                <option v-for="t in teachers" :key="t.id" :value="t.id">{{ t.name }}</option>
              </optgroup>
              <optgroup label="Сотрудники (сумма в месяц)">
                <option v-for="s in staff" :key="s.id" :value="s.id">{{ s.name }}</option>
              </optgroup>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">
              {{ panelIsTeacher ? 'Процент от учеников (0–100)' : 'Сумма в месяц (сум)' }}
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
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Только для группы (необязательно)</label>
              <select v-model="panel.group_id" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm">
                <option value="">— Для всех групп учителя —</option>
                <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Только для курса (необязательно)</label>
              <select v-model="panel.course_id" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm">
                <option value="">— Для всех курсов —</option>
                <option v-for="c in courses" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
              <p class="mt-1 text-[11px] text-fb-secondary">
                Какой процент берётся: процент группы → процент курса → общий процент учителя.
              </p>
            </div>
          </template>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Действует с</label>
              <input v-model="panel.effective_from" type="date" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">по</label>
              <input v-model="panel.effective_to" type="date" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm" />
            </div>
          </div>
          <p class="text-[11px] text-fb-secondary">
            <template v-if="panelIsTeacher">
              Процент запоминается в день, когда отмечен урок: уже проведённые уроки при его изменении не
              пересчитываются. Исправить прошлое можно «Поправкой» в ведомости.
            </template>
            <template v-else>
              Оклад без даты «действует с» считается со дня, когда он введён: за прошлые месяцы он не начисляется.
            </template>
          </p>
          <p v-if="panel.error" class="text-sm text-fb-danger">{{ panel.error }}</p>
        </div>
        <div class="flex gap-2 border-t px-6 py-4">
          <button type="button" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" :disabled="panel.saving" @click="saveRate">
            {{ panel.saving ? 'Сохраняю…' : 'Сохранить' }}
          </button>
          <button v-if="panel.editing" type="button" class="rounded-lg border border-red-300 px-5 py-2 text-sm text-fb-danger" @click="deleteRate">
            Удалить
          </button>
          <button type="button" class="rounded-lg border px-5 py-2 text-sm" @click="panel.show = false">Отмена</button>
        </div>
      </div>
    </div>

    <!-- Pay modal -->
    <div v-if="payModal.show" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div class="w-full max-w-md overflow-hidden rounded-2xl bg-fb-card shadow-2xl">
        <div class="border-b border-fb-line px-6 py-4">
          <h2 class="text-lg font-semibold text-fb-text">Выплата зарплаты</h2>
          <p class="text-sm text-fb-secondary">
            {{ payModal.row?.teacher_name }} · {{ selectedMonth }} · к выплате {{ money(payModal.row?.accrued) }}, осталось
            {{ money(payModal.row?.balance) }}
          </p>
        </div>
        <div class="space-y-3 px-6 py-5">
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">Сумма</label>
            <input v-model.number="payModal.amount" type="number" min="1" step="1" class="w-full rounded-lg border border-fb-line px-3 py-2" />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">Способ</label>
            <select v-model="payModal.method" class="w-full rounded-lg border border-fb-line px-3 py-2">
              <option value="cash">Наличные</option>
              <option value="card">Карта</option>
              <option value="transfer">Перевод</option>
            </select>
          </div>
          <div v-if="payNeedsBranch">
            <label class="mb-1 block text-sm font-medium text-fb-secondary">На какой филиал записать</label>
            <select v-model="payModal.branch_id" class="w-full rounded-lg border border-fb-line px-3 py-2">
              <option value="">— Выберите филиал —</option>
              <option v-for="b in branches" :key="b.id" :value="b.id">{{ b.name }}</option>
            </select>
          </div>
          <p v-else-if="payModal.row?.kind === 'teacher'" class="text-[11px] text-fb-secondary">
            В расходах выплата разложится по филиалам групп, за которые начислена зарплата.
          </p>
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">Комментарий</label>
            <input v-model="payModal.comment" class="w-full rounded-lg border border-fb-line px-3 py-2" />
          </div>
          <label v-if="payModal.overpay && auth.isCeo" class="flex items-center gap-2 text-sm text-rose-700">
            <input v-model="payModal.force" type="checkbox" />
            Выплатить сверх начисленного (запишется в журнал)
          </label>
          <p v-if="payModal.error" class="text-sm text-fb-danger">{{ payModal.error }}</p>
        </div>
        <div class="flex justify-end gap-3 border-t border-fb-line px-6 py-4">
          <button type="button" class="rounded-lg border border-fb-line px-5 py-2 text-sm" @click="payModal.show = false">Отмена</button>
          <button
            type="button"
            class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white disabled:opacity-50"
            :disabled="payModal.saving"
            @click="submitPay"
          >
            {{ payModal.saving ? 'Провожу…' : 'Выплатить' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Close / reopen month modal -->
    <div v-if="monthModal.show" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div class="w-full max-w-md overflow-hidden rounded-2xl bg-fb-card shadow-2xl">
        <div class="border-b border-fb-line px-6 py-4">
          <h2 class="text-lg font-semibold text-fb-text">
            {{ monthModal.mode === 'close' ? 'Закрыть' : 'Открыть' }} <span>{{ monthTitle }}</span>?
          </h2>
        </div>
        <div class="space-y-3 px-6 py-5 text-sm text-fb-text">
          <template v-if="monthModal.mode === 'close'">
            <p>После закрытия:</p>
            <ul class="list-disc space-y-1 pl-5 text-fb-secondary">
              <li>зарплата каждого за этот месяц сохранится как сейчас и больше не будет пересчитываться;</li>
              <li>оплаты, возвраты, расходы, изъятия и отметки учителей с датой этого месяца нельзя будет добавить, изменить или удалить;</li>
              <li>выплатить зарплату за этот месяц можно, как и раньше.</li>
            </ul>
            <p class="text-fb-secondary">Проверьте цифры перед закрытием. Открыть месяц обратно сможет только CEO.</p>
          </template>
          <template v-else>
            <p class="text-fb-secondary">
              Месяц снова станет изменяемым, а зарплаты пересчитаются по текущим данным (цены, проценты, отметки).
              Это попадёт в журнал.
            </p>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Причина</label>
              <input v-model="monthModal.reason" class="w-full rounded-lg border border-fb-line px-3 py-2" placeholder="Например: забыли внести аренду" />
            </div>
          </template>
          <p v-if="monthModal.error" class="text-sm text-fb-danger">{{ monthModal.error }}</p>
        </div>
        <div class="flex justify-end gap-3 border-t border-fb-line px-6 py-4">
          <button type="button" class="rounded-lg border border-fb-line px-5 py-2 text-sm" @click="monthModal.show = false">Отмена</button>
          <button
            type="button"
            class="rounded-lg px-5 py-2 text-sm font-medium text-white disabled:opacity-50"
            :class="monthModal.mode === 'close' ? 'bg-slate-700' : 'bg-rose-600'"
            :disabled="monthModal.saving"
            @click="submitMonth"
          >
            {{ monthModal.saving ? 'Секунду…' : monthModal.mode === 'close' ? 'Закрыть месяц' : 'Открыть месяц' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Salary correction modal -->
    <div v-if="adjModal.show" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div class="w-full max-w-md overflow-hidden rounded-2xl bg-fb-card shadow-2xl">
        <div class="border-b border-fb-line px-6 py-4">
          <h2 class="text-lg font-semibold text-fb-text">Поправка к зарплате</h2>
          <p class="text-sm text-fb-secondary">{{ adjModal.row?.teacher_name }} · {{ monthTitle }} · к выплате {{ money(adjModal.row?.accrued) }}</p>
        </div>
        <div class="space-y-3 px-6 py-5">
          <div class="flex gap-2">
            <button
              type="button"
              class="flex-1 rounded-lg border px-3 py-2 text-sm font-semibold"
              :class="adjModal.sign === 1 ? 'border-emerald-500 bg-emerald-50 text-emerald-700' : 'border-fb-line text-fb-secondary'"
              @click="adjModal.sign = 1"
            >
              + Добавить
            </button>
            <button
              type="button"
              class="flex-1 rounded-lg border px-3 py-2 text-sm font-semibold"
              :class="adjModal.sign === -1 ? 'border-rose-500 bg-rose-50 text-rose-700' : 'border-fb-line text-fb-secondary'"
              @click="adjModal.sign = -1"
            >
              − Убрать
            </button>
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">Сумма</label>
            <input v-model.number="adjModal.amount" type="number" min="1" step="1" class="w-full rounded-lg border border-fb-line px-3 py-2" />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">Причина</label>
            <input v-model="adjModal.reason" class="w-full rounded-lg border border-fb-line px-3 py-2" placeholder="Например: забыли отметить урок 12.08" />
          </div>
          <p class="text-[11px] text-fb-secondary">Поправка видна в строке учителя и пишется в журнал.</p>
          <p v-if="adjModal.error" class="text-sm text-fb-danger">{{ adjModal.error }}</p>
        </div>
        <div class="flex justify-end gap-3 border-t border-fb-line px-6 py-4">
          <button type="button" class="rounded-lg border border-fb-line px-5 py-2 text-sm" @click="adjModal.show = false">Отмена</button>
          <button
            type="button"
            class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white disabled:opacity-50"
            :disabled="adjModal.saving"
            @click="submitAdjustment"
          >
            {{ adjModal.saving ? 'Сохраняю…' : 'Сохранить' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
