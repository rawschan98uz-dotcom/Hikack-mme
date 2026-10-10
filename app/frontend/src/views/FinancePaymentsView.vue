<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { useRememberedFilters } from '../utils/rememberedFilters';
import EmptyState from '../components/EmptyState.vue';
import SkeletonBlock from '../components/SkeletonBlock.vue';
import PaymentPreviewHint from '../components/PaymentPreviewHint.vue';
import { todayIso } from '../utils/dates';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';
import ReceiptModal, { type ReceiptPayment } from '../components/ReceiptModal.vue';
import PaymentLinkModal, { type StudentPaymentLinkTarget } from '../components/PaymentLinkModal.vue';
import { t, type MessageKey } from '../i18n';
import { payMethodLabel } from '../i18n/labels';
import { confirmDialog, toast } from '../ui/feedback';
import { apiErrorMessage } from '../utils/apiError';

const auth = useAuthStore();
// The administrator takes and corrects payments and gives refunds; only the CEO deletes one (owner, 2026-09-28)
const canWriteFinance = computed(() => auth.can(PERM.PAYMENTS_WRITE));
const canDeletePayment = computed(() => auth.can(PERM.PAYMENTS_DELETE));

interface PaymentRow {
  id: number;
  date: string;
  payment_date?: string;
  name: string;
  student_id: number | null;
  student_name: string;
  sum: number;
  /** 'payment' or 'refund' (money given back — shown red with a minus). */
  transaction_type?: string;
  reverses_payment_id?: number | null;
  discount_amount?: number;
  months_covered?: number;
  /** Months taken back by refunds of this payment. */
  refunded_amount?: number;
  /** true = months counted from the money (копилка), false = entered by hand. */
  months_auto?: boolean;
  /** Price of a month for копилка payments; 0 = money waiting in the копилка for a course price. */
  month_price?: number | null;
  method: string;
  method_pay: string;
  teacher: string;
  teacher_name: string;
  comment: string;
  creator: string;
  /** Detail only: already given back / still possible to give back. */
  refunded_total?: number;
  refundable?: number;
}

interface StudentOption {
  id: number;
  full_name: string;
  phone: string;
  group?: string | null;
  group_teacher?: string;
  course_price?: number;
  wallet?: number;
  debt_amount?: number;
}

type PageArray<T> = T[] & { has_more?: boolean; next_offset?: number | null };

const METHODS = [
  { value: 'cash', label: 'payMethod.cash' as MessageKey },
  { value: 'card', label: 'payMethod.card' as MessageKey },
  { value: 'transfer', label: 'payMethod.transfer' as MessageKey },
] as const;

const rows = ref<PaymentRow[]>([]);
const hasMore = ref(false);
const nextOffset = ref<number | null>(null);
const loadingMore = ref(false);
const studentsList = ref<StudentOption[]>([]);
const studentSearchQuery = ref('');
const showStudentDropdown = ref(false);
const selectedStudent = ref<StudentOption | null>(null);

const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingRow = ref<PaymentRow | null>(null);
const detailRow = ref<PaymentRow | null>(null);

const showReceiptModal = ref(false);
const receiptPayment = ref<ReceiptPayment | null>(null);

function isRefund(row: PaymentRow | null | undefined) {
  return row?.transaction_type === 'refund';
}

function printPayment(row: PaymentRow) {
  receiptPayment.value = {
    id: row.id,
    date: row.date,
    student_name: row.student_name || row.name,
    amount: row.sum,
    months_covered: row.months_covered ?? 1,
    method: row.method,
    method_pay: row.method_pay,
    teacher: row.teacher,
    teacher_name: row.teacher_name,
    comment: row.comment,
    creator: row.creator,
  };
  showReceiptModal.value = true;
}

function printRowById(id: number) {
  const row = rows.value.find((r) => r.id === id);
  if (row) printPayment(row);
}

const showPaymentLinkModal = ref(false);
const paymentLinkStudent = ref<StudentPaymentLinkTarget | null>(null);

function openPaymentLink(studentOrRow?: StudentOption | PaymentRow | null) {
  const target = studentOrRow || selectedStudent.value;
  if (!target) return;
  if ('student_id' in target && target.student_id) {
    paymentLinkStudent.value = {
      id: target.student_id,
      full_name: target.student_name || target.name,
      phone: '',
      course_price: target.sum,
    };
  } else if ('full_name' in target) {
    paymentLinkStudent.value = {
      id: target.id,
      full_name: target.full_name,
      phone: target.phone,
      group: target.group,
      course_price: target.course_price,
    };
  }
  showPaymentLinkModal.value = true;
}

const filters = reactive({ date_from: '', date_to: '', method: '', q: '' });

// Leave the page and come back: the filters are still set
const { isFiltered, reset: resetFilters } = useRememberedFilters('payments', filters);

function resetAndReload() {
  resetFilters();
  void loadRows();
}
const form = reactive({
  student_id: null as number | null,
  student_name: '',
  amount: '' as number | '',
  /** Discount as a sum, given by hand; empty when there is none (owner, 2026-09-28) */
  discount: '' as number | '',
  payment_date: todayIso(),
  months_covered: 1,
  method: 'cash' as (typeof METHODS)[number]['value'],
  teacher_name: '',
  comment: '',
});

const isReadOnly = computed(() => Boolean(detailRow.value && !editingRow.value));
const panelTitle = computed(() => {
  if (isRefund(detailRow.value)) return t('payments.refundTitle');
  return editingRow.value ? t('payments.editTitle') : detailRow.value ? t('payments.detailTitle') : t('payments.addTitle');
});

function formatMoney(value: number) {
  return Math.round(value).toLocaleString('ru-RU');
}

const filteredStudents = computed(() => {
  const q = studentSearchQuery.value.trim().toLowerCase();
  if (!q) return studentsList.value.slice(0, 20);
  return studentsList.value
    .filter((s) => s.full_name.toLowerCase().includes(q) || s.phone.includes(q))
    .slice(0, 20);
});

/** New payment: the sum follows months × price − discount while the cashier has not typed it by hand. */
function refillAmount() {
  if (editingRow.value || detailRow.value) return;
  const price = selectedStudent.value?.course_price || 0;
  if (price) form.amount = Math.max(0, price * form.months_covered - (Number(form.discount) || 0));
}

function selectStudent(student: StudentOption) {
  selectedStudent.value = student;
  form.student_id = student.id;
  form.student_name = student.full_name;
  studentSearchQuery.value = student.full_name;
  if (student.group_teacher) {
    form.teacher_name = student.group_teacher;
  }
  refillAmount();
  // A debtor: the sum of the debt is offered first
  if (!editingRow.value && !detailRow.value && student.debt_amount) form.amount = student.debt_amount;
  showStudentDropdown.value = false;
}

function onMonthsChange() {
  if (form.months_covered < 1) form.months_covered = 1;
  // Editing money that already came: the amount is what was really paid, never recount it from months
  refillAmount();
}

function resetForm() {
  form.student_id = null;
  form.student_name = '';
  form.amount = '';
  form.discount = '';
  form.payment_date = todayIso();
  form.months_covered = 1;
  form.method = 'cash';
  form.teacher_name = '';
  form.comment = '';
  studentSearchQuery.value = '';
  selectedStudent.value = null;
  showStudentDropdown.value = false;
  formError.value = '';
  editingRow.value = null;
  detailRow.value = null;
}

function fillForm(row: PaymentRow) {
  form.student_id = row.student_id ?? null;
  form.student_name = row.student_name;
  form.amount = row.sum;
  form.discount = row.discount_amount ? row.discount_amount : '';
  form.payment_date = row.payment_date || row.date;
  // Копилка payments may close 0 months (money waiting); hand-entered ones are at least 1
  form.months_covered = row.months_auto ? (row.months_covered ?? 0) : (row.months_covered || 1);
  form.method = row.method as (typeof METHODS)[number]['value'];
  form.teacher_name = row.teacher_name;
  form.comment = row.comment;
  studentSearchQuery.value = row.student_name;
  selectedStudent.value = studentsList.value.find((s) => s.id === row.student_id) || null;
}

async function loadStudentsList() {
  try {
    const { data } = await client.get('/students?statuses=1&limit=500');
    const list = Array.isArray(data.data) ? data.data : (data.data?.results || []);
    studentsList.value = list.map((s: any) => ({
      id: s.id,
      full_name: s.full_name || `${s.first_name || ''} ${s.last_name || ''}`.trim(),
      phone: s.phone || '',
      group: s.group || null,
      group_teacher: s.group_teacher || '',
      course_price: s.course_price || 0,
      wallet: s.wallet || 0,
      debt_amount: s.debt_amount || 0,
    }));
  } catch {
    studentsList.value = [];
  }
}

function listParams(offset = 0) {
  const params: Record<string, string | number> = { offset };
  if (filters.date_from) params.date_from = filters.date_from;
  if (filters.date_to) params.date_to = filters.date_to;
  if (filters.method) params.method = filters.method;
  if (filters.q.trim()) params.q = filters.q.trim();
  return params;
}

async function loadRows() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<PageArray<PaymentRow>>>('/replenishments', { params: listParams() });
    rows.value = [...data.data];
    hasMore.value = Boolean(data.data.has_more);
    nextOffset.value = data.data.next_offset ?? null;
  } finally {
    loading.value = false;
  }
}

/** "Show more": the next 200 payments (older ones). */
async function loadMore() {
  if (nextOffset.value === null) return;
  loadingMore.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<PageArray<PaymentRow>>>('/replenishments', {
      params: listParams(nextOffset.value),
    });
    rows.value = [...rows.value, ...data.data];
    hasMore.value = Boolean(data.data.has_more);
    nextOffset.value = data.data.next_offset ?? null;
  } finally {
    loadingMore.value = false;
  }
}

function openCreate() {
  resetForm();
  showPanel.value = true;
  if (!studentsList.value.length) {
    loadStudentsList();
  }
}

async function openDetail(id: number) {
  resetForm();
  showPanel.value = true;
  panelLoading.value = true;
  if (!studentsList.value.length) {
    loadStudentsList();
  }
  try {
    const { data } = await client.get<ApiEnvelope<PaymentRow>>(`/replenishments/${id}`);
    detailRow.value = data.data;
    fillForm(data.data);
  } finally {
    panelLoading.value = false;
  }
}

function startEdit() {
  if (detailRow.value) editingRow.value = detailRow.value;
}

function closePanel() {
  showPanel.value = false;
  resetForm();
}


async function submitForm() {
  formError.value = '';
  if (!editingRow.value && !form.student_id) {
    formError.value = t('payments.chooseStudent');
    return;
  }
  if (!Number.isInteger(form.amount) || Number(form.amount) <= 0) {
    formError.value = t('finance.amountPositive');
    return;
  }
  if (form.discount !== '' && (!Number.isInteger(form.discount) || Number(form.discount) < 0)) {
    formError.value = t('payments.discountInvalid');
    return;
  }
  if (!form.payment_date || form.payment_date > todayIso()) {
    formError.value = t('payments.dateNotFuture');
    return;
  }
  saving.value = true;
  try {
    if (editingRow.value) {
      const payload: Record<string, unknown> = {
        amount: form.amount,
        payment_date: form.payment_date,
        method: form.method,
        comment: form.comment.trim(),
      };
      if (!isRefund(editingRow.value)) {
        payload.discount_amount = form.discount === '' ? 0 : form.discount;
        payload.teacher_name = form.teacher_name.trim();
        if (!editingRow.value.months_auto) payload.months_covered = form.months_covered || 1;
      }
      await client.patch(`/replenishments/${editingRow.value.id}`, payload);
    } else {
      await client.post('/replenishments', {
        student_id: form.student_id,
        amount: form.amount,
        discount_amount: form.discount === '' ? 0 : form.discount,
        payment_date: form.payment_date,
        months_covered: form.months_covered || 1,
        method: form.method,
        comment: form.comment.trim(),
      });
    }
    const wasEditing = Boolean(editingRow.value);
    const studentName = form.student_name;
    const amount = Number(form.amount);
    closePanel();
    toast.success(wasEditing
      ? t('toast.saved')
      : t('payments.received', { amount: formatMoney(amount), name: studentName }));
    await loadRows();
  } catch (err: unknown) {
    formError.value = apiErrorMessage(err, t('payments.saveFailed'));
  } finally {
    saving.value = false;
  }
}

async function deleteRow() {
  if (!detailRow.value) return;
  const ok = await confirmDialog({
    title: t('payments.deleteConfirm', { amount: formatMoney(detailRow.value.sum), name: detailRow.value.student_name || detailRow.value.name }),
    message: t('payments.deleteHint'),
    danger: true,
  });
  if (!ok || !detailRow.value) return;
  deleting.value = true;
  try {
    await client.delete(`/replenishments/${detailRow.value.id}`);
    closePanel();
    toast.success(t('toast.deleted'));
    await loadRows();
  } catch (err: unknown) {
    formError.value = apiErrorMessage(err, t('errors.deleteFailed'));
  } finally {
    deleting.value = false;
  }
}

// "Вернуть деньги": a refund of this payment (sum + reason), shown in the list in red with a minus
const refundModal = reactive({
  show: false,
  amount: '' as number | '',
  reason: '',
  error: '',
  saving: false,
});

function openRefund() {
  if (!detailRow.value) return;
  refundModal.amount = detailRow.value.refundable ?? detailRow.value.sum;
  refundModal.reason = '';
  refundModal.error = '';
  refundModal.show = true;
}

async function confirmRefund() {
  if (!detailRow.value) return;
  const max = detailRow.value.refundable ?? detailRow.value.sum;
  if (!Number.isInteger(refundModal.amount) || Number(refundModal.amount) <= 0) {
    refundModal.error = t('payments.refundAmountPositive');
    return;
  }
  if (Number(refundModal.amount) > max) {
    refundModal.error = t('payments.refundMax', { amount: formatMoney(max) });
    return;
  }
  if (refundModal.reason.trim().length < 3) {
    refundModal.error = t('payments.refundReasonRequired');
    return;
  }
  refundModal.saving = true;
  try {
    await client.post(`/replenishments/${detailRow.value.id}/refund`, {
      amount: refundModal.amount,
      // Saved into the payment record (data, not interface text): one wording whatever the screen language
      comment: `Возврат: ${refundModal.reason.trim()}`,
    });
    const refunded = Number(refundModal.amount);
    refundModal.show = false;
    closePanel();
    toast.success(t('payments.refunded', { amount: formatMoney(refunded) }));
    await loadRows();
  } catch (err: unknown) {
    refundModal.error = apiErrorMessage(err, t('payments.refundFailed'));
  } finally {
    refundModal.saving = false;
  }
}

onMounted(() => {
  loadRows();
  loadStudentsList();
});

let searchDebounce: ReturnType<typeof setTimeout> | null = null;
watch(
  () => filters.q,
  (newQ, oldQ) => {
    if (newQ === oldQ) return;
    if (searchDebounce) clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      loadRows();
    }, 400);
  },
);

</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-fb-text">{{ t('nav.allPayments') }}</h1>
      <button v-if="canWriteFinance" type="button" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" @click="openCreate">
        + {{ t('payments.addTitle') }}
      </button>
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">{{ t('common.from') }}</label>
        <input v-model="filters.date_from" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">{{ t('common.to') }}</label>
        <input v-model="filters.date_to" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">{{ t('expenses.method') }}</label>
        <select v-model="filters.method" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option value="">{{ t('common.all') }}</option>
          <option v-for="m in METHODS" :key="m.value" :value="m.value">{{ t(m.label) }}</option>
        </select>
      </div>
      <div class="min-w-[180px] flex-1">
        <label class="mb-1 block text-xs text-fb-secondary">{{ t('common.search') }}</label>
        <input v-model="filters.q" type="search" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm" @keydown.enter="loadRows" />
      </div>
      <button type="button" class="rounded-lg border border-fb-line px-4 py-2 text-sm" @click="loadRows">{{ t('common.apply') }}</button>
      <button v-if="isFiltered" type="button" class="rounded-lg px-3 py-2 text-sm text-fb-secondary hover:text-fb-danger" @click="resetAndReload">
        ✕ {{ t('empty.resetFilters') }}
      </button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <SkeletonBlock v-if="loading" :rows="8" :cols="6" />
      <EmptyState
        v-else-if="!rows.length"
        icon="coins"
        :filtered="isFiltered"
        :title="t('payments.emptyTitle')"
        :hint="t('payments.emptyHint')"
        :action-label="canWriteFinance ? t('payments.addTitle') : ''"
        @action="openCreate"
        @reset="resetAndReload"
      />
      <table v-else class="w-full text-base">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.date') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('months.student') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.amount') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.period') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('expenses.method') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('schedule.teacher') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.comment') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('finance.creator') }}</th>
            <th class="px-5 py-4 text-right font-semibold text-fb-secondary">{{ t('payments.receipt') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            class="cursor-pointer border-b hover:bg-fb-hover/40"
            :class="isRefund(row) ? 'bg-rose-50/40' : ''"
            @click="openDetail(row.id)"
          >
            <td class="px-5 py-4">{{ row.date }}</td>
            <td class="px-5 py-4 font-medium">{{ row.name }}</td>
            <td class="px-5 py-4 font-semibold" :class="isRefund(row) ? 'text-rose-700' : 'text-fb-blue'">
              <template v-if="isRefund(row)">−{{ formatMoney(row.sum) }}</template>
              <template v-else>{{ formatMoney(row.sum) }}</template>
              <span v-if="row.discount_amount" class="ml-1 block text-[11px] font-medium text-amber-700">
                {{ t('payHint.discount', { amount: formatMoney(row.discount_amount) }) }}
              </span>
            </td>
            <td class="px-5 py-4">
              <span
                v-if="isRefund(row)"
                class="inline-flex items-center rounded-full bg-rose-100 px-2.5 py-0.5 text-xs font-semibold text-rose-700"
              >
                {{ t('txType.refund') }}
              </span>
              <template v-else>
                <span class="inline-flex items-center rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-fb-blue">
                  {{ t('receipt.months', { count: row.months_covered ?? 1 }) }}
                </span>
                <span
                  v-if="row.refunded_amount"
                  class="ml-1 inline-flex items-center rounded-full bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700"
                  :title="t('payments.refundedHint')"
                >
                  {{ t('payments.refundedShort', { amount: formatMoney(row.refunded_amount) }) }}
                </span>
              </template>
            </td>
            <td class="px-5 py-4">{{ payMethodLabel(row.method, row.method_pay) }}</td>
            <td class="px-5 py-4">{{ row.teacher }}</td>
            <td class="px-5 py-4">{{ row.comment || '—' }}</td>
            <td class="px-5 py-4">{{ row.creator }}</td>
            <td class="px-5 py-4 text-right" @click.stop>
              <button
                v-if="!isRefund(row)"
                type="button"
                :title="t('payments.printReceipt')"
                class="inline-flex items-center gap-1 rounded-lg border border-fb-line bg-white px-2.5 py-1 text-xs font-medium text-fb-secondary shadow-sm hover:border-fb-blue hover:text-fb-blue transition-colors"
                @click="printRowById(row.id)"
              >
                <span>🖨️</span>
                <span>{{ t('payments.receipt') }}</span>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="hasMore" class="border-t border-fb-line p-3 text-center">
        <button
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-blue hover:bg-fb-hover disabled:opacity-50"
          :disabled="loadingMore"
          @click="loadMore"
        >
          {{ loadingMore ? t('common.loading') : t('common.showMore') }}
        </button>
      </div>
    </div>

    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closePanel" />
      <div class="drawer-panel-fb max-w-lg">
        <div class="flex items-center justify-between border-b px-6 py-4">
          <h2 class="text-lg font-semibold">{{ panelTitle }}</h2>
          <button type="button" :aria-label="t('common.close')" @click="closePanel">✕</button>
        </div>
        <SkeletonBlock v-if="panelLoading" variant="lines" :rows="6" class="p-6" />
        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitForm">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <p v-if="isRefund(detailRow)" class="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800">
              {{ t('payments.isRefundOf', { id: detailRow?.reverses_payment_id ?? '' }) }}
            </p>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('months.student') }}</label>
              <div v-if="!detailRow" class="relative">
                <input
                  v-model="studentSearchQuery"
                  type="text"
                  required
                  :placeholder="t('payments.studentPlaceholder')"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
                  @focus="showStudentDropdown = true"
                  @input="showStudentDropdown = true; form.student_name = studentSearchQuery; form.student_id = null; selectedStudent = null"
                />
                <div
                  v-if="showStudentDropdown && filteredStudents.length"
                  class="absolute left-0 right-0 top-full z-20 mt-1 max-h-48 overflow-y-auto rounded-lg border border-fb-line bg-white shadow-lg"
                >
                  <button
                    v-for="s in filteredStudents"
                    :key="s.id"
                    type="button"
                    class="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-fb-canvas"
                    @mousedown.prevent="selectStudent(s)"
                  >
                    <div>
                      <span class="font-medium text-fb-text">{{ s.full_name }}</span>
                      <span v-if="s.group" class="ml-2 text-xs text-fb-secondary">({{ s.group }})</span>
                    </div>
                    <span v-if="s.course_price" class="text-xs font-semibold text-fb-blue">
                      {{ t('payments.perMonth', { amount: formatMoney(s.course_price) }) }}
                    </span>
                  </button>
                </div>
                <p v-if="studentSearchQuery && !form.student_id" class="mt-1 text-xs text-amber-700">
                  {{ t('payments.chooseFromList') }}
                </p>
              </div>
              <input
                v-else
                :value="form.student_name"
                readonly
                class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('payments.date') }}</label>
              <input
                v-model="form.payment_date"
                type="date"
                :max="todayIso()"
                :readonly="isReadOnly"
                required
                class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>
            <div v-if="!isRefund(detailRow)">
              <label class="mb-1 block text-sm font-medium text-fb-secondary">
                {{
                  detailRow?.months_auto
                    ? t('payments.monthsClosedAuto')
                    : editingRow
                      ? t('payments.monthsEditing')
                      : t('payments.monthsNew')
                }}
              </label>
              <p v-if="detailRow?.months_auto && detailRow?.month_price === 0" class="mb-1 text-xs text-amber-700">
                {{ t('payments.moneyWaiting') }}
              </p>
              <input
                v-model.number="form.months_covered"
                type="number"
                min="1"
                :readonly="isReadOnly || Boolean(detailRow?.months_auto)"
                required
                class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                @input="onMonthsChange"
              />
            </div>
            <div v-if="!isRefund(detailRow)">
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('payments.discount') }}</label>
              <input
                v-model.number="form.discount"
                type="number"
                min="0"
                step="1"
                :placeholder="t('payments.noDiscount')"
                :readonly="isReadOnly"
                class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                @input="refillAmount"
              />
              <p v-if="!detailRow" class="mt-1 text-[11px] text-fb-secondary">
                {{ t('payments.discountHint') }}
              </p>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">
                {{ isRefund(detailRow) ? t('payments.refundAmount') : t('common.amount') }}
              </label>
              <input
                v-model.number="form.amount"
                type="number"
                min="1"
                step="1"
                :readonly="isReadOnly"
                required
                class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
              <PaymentPreviewHint
                v-if="!editingRow && !detailRow"
                :student-id="selectedStudent?.id"
                :amount="Number(form.amount) || 0"
                :discount="Number(form.discount) || 0"
                :months="form.months_covered"
                :date="form.payment_date"
              />
              <p v-if="detailRow && !isRefund(detailRow) && detailRow.refunded_total" class="mt-1 text-xs text-rose-700">
                {{ t('payments.alreadyRefunded', { amount: formatMoney(detailRow.refunded_total) }) }}
              </p>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('expenses.method') }}</label>
              <select v-model="form.method" :disabled="isReadOnly" class="w-full rounded-lg border px-3 py-2 text-sm">
                <option v-for="m in METHODS" :key="m.value" :value="m.value">{{ t(m.label) }}</option>
              </select>
            </div>
            <div v-if="detailRow && !isRefund(detailRow)">
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('schedule.teacher') }}</label>
              <input v-model="form.teacher_name" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.comment') }}</label>
              <textarea v-model="form.comment" :readonly="isReadOnly" rows="3" class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none" />
            </div>
            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>
          <div class="flex flex-wrap gap-2 border-t px-6 py-4">
            <template v-if="isReadOnly && detailRow">
              <button
                v-if="!isRefund(detailRow)"
                type="button"
                class="inline-flex items-center gap-1.5 rounded-lg border border-fb-line bg-white px-4 py-2 text-sm font-medium text-fb-text hover:border-fb-blue hover:text-fb-blue transition-colors"
                @click="printPayment(detailRow)"
              >
                <span>🖨️</span>
                <span>{{ t('payments.printReceipt') }}</span>
              </button>
              <button
                v-if="detailRow.student_id && !isRefund(detailRow)"
                type="button"
                class="inline-flex items-center gap-1.5 rounded-lg border border-fb-line bg-white px-3 py-2 text-sm font-medium text-fb-text hover:border-fb-blue hover:text-fb-blue transition-colors"
                @click="openPaymentLink(detailRow)"
              >
                <span>💳</span>
                <span>{{ t('payments.link') }}</span>
              </button>
              <button v-if="canWriteFinance" type="button" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" @click="startEdit">{{ t('common.edit') }}</button>
              <button
                v-if="canWriteFinance && !isRefund(detailRow) && (detailRow.refundable ?? 0) > 0"
                type="button"
                class="rounded-lg border border-rose-300 px-4 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50"
                @click="openRefund"
              >
                {{ t('payments.refundTitle') }}
              </button>
              <button v-if="canDeletePayment" type="button" class="rounded-lg border border-red-300 px-5 py-2 text-sm text-fb-danger" :disabled="deleting" @click="deleteRow">{{ t('common.delete') }}</button>
            </template>
            <template v-else>
              <button
                v-if="selectedStudent"
                type="button"
                class="inline-flex items-center gap-1.5 rounded-lg border border-fb-line bg-white px-3 py-2 text-sm font-medium text-fb-text hover:border-fb-blue hover:text-fb-blue transition-colors"
                @click="openPaymentLink(selectedStudent)"
              >
                <span>💳</span>
                <span>{{ t('payments.link') }}</span>
              </button>
              <button type="submit" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" :disabled="saving">
                {{ saving ? t('common.saving') : editingRow ? t('common.save') : t('payments.takePayment') }}
              </button>
            </template>
            <button type="button" class="rounded-lg border px-5 py-2 text-sm" @click="closePanel">{{ t('common.cancel') }}</button>
          </div>
        </form>
      </div>
    </div>

    <!-- "Вернуть деньги" -->
    <div v-if="refundModal.show" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div class="w-full max-w-md overflow-hidden rounded-2xl bg-fb-card shadow-2xl">
        <div class="border-b border-fb-line px-6 py-4">
          <h2 class="text-lg font-semibold text-rose-700">{{ t('payments.refundTitle') }}</h2>
          <p class="text-sm text-fb-secondary">{{ detailRow?.student_name }} · {{ t('payments.paymentOf', { amount: formatMoney(detailRow?.sum ?? 0) }) }}</p>
        </div>
        <div class="space-y-3 px-6 py-5">
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('payments.refundAmount') }}</label>
            <input
              v-model.number="refundModal.amount"
              type="number"
              min="1"
              step="1"
              class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
            />
            <p class="mt-1 text-[11px] text-fb-secondary">{{ t('payments.refundUpTo', { amount: formatMoney(detailRow?.refundable ?? 0) }) }}</p>
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('dashboard.reasonRequired') }}</label>
            <textarea
              v-model="refundModal.reason"
              rows="3"
              class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
              :placeholder="t('payments.refundReasonPlaceholder')"
            />
          </div>
          <p v-if="refundModal.error" class="text-sm text-fb-danger">{{ refundModal.error }}</p>
        </div>
        <div class="flex justify-end gap-3 border-t border-fb-line px-6 py-4">
          <button type="button" class="rounded-lg border border-fb-line px-5 py-2 text-sm" @click="refundModal.show = false">{{ t('common.cancel') }}</button>
          <button
            type="button"
            class="rounded-lg bg-rose-600 px-5 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50"
            :disabled="refundModal.saving"
            @click="confirmRefund"
          >
            {{ refundModal.saving ? t('common.saving') : t('payments.refundButton') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Receipt Modal -->
    <ReceiptModal
      v-model:open="showReceiptModal"
      :payment="receiptPayment"
    />

    <!-- Payment Link Modal -->
    <PaymentLinkModal
      v-model:open="showPaymentLinkModal"
      :student="paymentLinkStudent"
    />
  </div>
</template>
