<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface SalaryRow {
  id: number;
  calc_setting: string;
  salary_type: string;
  salary_type_label: string;
  amount: number;
  teacher_name: string;
  teacher: string;
  course_name: string;
  course: string;
  group_name: string;
  group: string;
  created_by: string;
  updated_by: string;
}

interface PayrollRow {
  teacher_id: number;
  teacher_name: string;
  phone: string;
  groups_count: number;
  groups_names: string;
  lessons_count: number;
  students_count: number;
  group_payments: number;
  salary_type: string;
  salary_type_label: string;
  rate_amount: number;
  accrued: number;
  paid: number;
  balance: number;
  status: 'paid' | 'partial' | 'unpaid' | 'none';
}

interface PayrollSummary {
  total_accrued: number;
  total_paid: number;
  total_balance: number;
  teachers_count: number;
}

interface TeacherOption {
  id: number;
  name: string;
}

const SALARY_TYPES = [
  { value: 'fixed', label: 'Fixed' },
  { value: 'percent', label: 'Percent' },
  { value: 'per_student', label: 'Per student' },
] as const;

// Tabs
const activeTab = ref<'payroll' | 'settings'>('payroll');

// Payroll State
const selectedMonth = ref(new Date().toISOString().slice(0, 7));
const payrollRows = ref<PayrollRow[]>([]);
const payrollSummary = ref<PayrollSummary>({
  total_accrued: 0,
  total_paid: 0,
  total_balance: 0,
  teachers_count: 0,
});
const payrollLoading = ref(false);

// Pay Modal
const showPayModal = ref(false);
const payTeacher = ref<PayrollRow | null>(null);
const payForm = reactive({
  amount: 0,
  method: 'cash' as 'cash' | 'card' | 'transfer',
  comment: '',
});
const paySaving = ref(false);
const payError = ref('');

// Salary Settings State
const rows = ref<SalaryRow[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingRow = ref<SalaryRow | null>(null);
const detailRow = ref<SalaryRow | null>(null);
const teachers = ref<TeacherOption[]>([]);
const filters = reactive({ q: '' });

const filteredRows = computed(() => {
  const q = filters.q.trim().toLowerCase();
  if (!q) return rows.value;
  return rows.value.filter((r) => {
    return (
      r.teacher?.toLowerCase().includes(q) ||
      r.teacher_name?.toLowerCase().includes(q) ||
      r.course?.toLowerCase().includes(q) ||
      r.course_name?.toLowerCase().includes(q) ||
      r.group?.toLowerCase().includes(q) ||
      r.group_name?.toLowerCase().includes(q) ||
      r.salary_type?.toLowerCase().includes(q) ||
      r.salary_type_label?.toLowerCase().includes(q) ||
      r.calc_setting?.toLowerCase().includes(q)
    );
  });
});

let salarySearchDebounce: ReturnType<typeof setTimeout> | null = null;
watch(
  () => filters.q,
  () => {
    if (salarySearchDebounce) clearTimeout(salarySearchDebounce);
    salarySearchDebounce = setTimeout(() => {
      void loadRows();
    }, 400);
  },
);

const form = reactive({
  teacher_name: '',
  salary_type: 'fixed' as (typeof SALARY_TYPES)[number]['value'],
  amount: 0,
  course_name: '',
  group_name: '',
});

const isReadOnly = computed(() => Boolean(detailRow.value && !editingRow.value));
const panelTitle = computed(() =>
  editingRow.value ? 'Edit salary setting' : detailRow.value ? 'Salary details' : 'Add salary setting',
);
const tableRows = computed(() =>
  filteredRows.value.map((r) => ({
    id: r.id,
    calc_setting: r.calc_setting,
    salary_type: r.salary_type_label,
    amount: r.amount.toLocaleString(),
    course: r.course,
    group: r.group,
    teacher: r.teacher,
    created_by: r.created_by,
  })),
);

// --- Payroll methods ---
async function loadPayroll() {
  payrollLoading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<{ month: string; summary: PayrollSummary; rows: PayrollRow[] }>>(
      '/finance/payroll',
      { params: { month: selectedMonth.value } },
    );
    payrollSummary.value = data.data.summary;
    payrollRows.value = data.data.rows;
  } finally {
    payrollLoading.value = false;
  }
}

function shiftMonth(delta: number) {
  const [y, m] = selectedMonth.value.split('-').map(Number);
  const date = new Date(y, m - 1 + delta, 1);
  const newY = date.getFullYear();
  const newM = String(date.getMonth() + 1).padStart(2, '0');
  selectedMonth.value = `${newY}-${newM}`;
  void loadPayroll();
}

function setThisMonth() {
  selectedMonth.value = new Date().toISOString().slice(0, 7);
  void loadPayroll();
}

function openPayModal(row: PayrollRow) {
  payTeacher.value = row;
  payForm.amount = row.balance > 0 ? row.balance : row.accrued;
  payForm.method = 'cash';
  payForm.comment = `Зарплата за ${selectedMonth.value}: ${row.teacher_name}`;
  payError.value = '';
  showPayModal.value = true;
}

async function submitSalaryPayment() {
  if (!payTeacher.value) return;
  if (payForm.amount <= 0) {
    payError.value = 'Укажите положительную сумму к выплате';
    return;
  }
  paySaving.value = true;
  payError.value = '';
  try {
    await client.post('/finance/payroll/pay', {
      teacher_id: payTeacher.value.teacher_id,
      amount: payForm.amount,
      method: payForm.method,
      month: selectedMonth.value,
      comment: payForm.comment,
    });
    showPayModal.value = false;
    await loadPayroll();
  } catch (err: any) {
    payError.value = err.response?.data?.message || err.response?.data?.error || 'Не удалось провести выплату';
  } finally {
    paySaving.value = false;
  }
}

// --- Settings methods ---
function resetForm() {
  form.teacher_name = '';
  form.salary_type = 'fixed';
  form.amount = 0;
  form.course_name = '';
  form.group_name = '';
  formError.value = '';
  editingRow.value = null;
  detailRow.value = null;
}

function fillForm(row: SalaryRow) {
  form.teacher_name = row.teacher_name;
  form.salary_type = row.salary_type as (typeof SALARY_TYPES)[number]['value'];
  form.amount = row.amount;
  form.course_name = row.course_name;
  form.group_name = row.group_name;
}

async function loadRows() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.q.trim()) params.q = filters.q.trim();
    const { data } = await client.get<ApiEnvelope<SalaryRow[]>>('/salary-settings', { params });
    rows.value = data.data;
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  resetForm();
  showPanel.value = true;
}

async function openDetail(id: number) {
  resetForm();
  showPanel.value = true;
  panelLoading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<SalaryRow>>(`/salary-settings/${id}`);
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

async function loadTeachers() {
  try {
    const { data } = await client.get<ApiEnvelope<{ id: number; name: string }[]>>('/user', {
      params: { user_type: 'teacher' },
    });
    teachers.value = data.data.map((t) => ({ id: t.id, name: t.name }));
  } catch {
    // fallback
  }
}

async function submitForm() {
  formError.value = '';
  if (!form.teacher_name.trim()) {
    formError.value = 'Teacher name is required';
    return;
  }
  saving.value = true;
  try {
    const payload = {
      teacher_name: form.teacher_name.trim(),
      salary_type: form.salary_type,
      amount: form.amount,
      course_name: form.course_name.trim(),
      group_name: form.group_name.trim(),
    };
    if (editingRow.value) {
      await client.patch(`/salary-settings/${editingRow.value.id}`, payload);
    } else {
      await client.post('/salary-settings', payload);
    }
    closePanel();
    await loadRows();
    await loadPayroll();
  } catch (err: any) {
    formError.value = err.response?.data?.message || err.response?.data?.error || 'Could not save';
  } finally {
    saving.value = false;
  }
}

async function deleteRow() {
  if (!detailRow.value || !window.confirm('Delete this salary setting?')) return;
  deleting.value = true;
  try {
    await client.delete(`/salary-settings/${detailRow.value.id}`);
    closePanel();
    await loadRows();
    await loadPayroll();
  } finally {
    deleting.value = false;
  }
}

onMounted(async () => {
  await Promise.all([loadPayroll(), loadRows(), loadTeachers()]);
});
</script>

<template>
  <div class="space-y-6">
    <!-- Header & Tab Navigation -->
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-fb-text">Зарплаты преподавателей</h1>
        <p class="mt-0.5 text-sm text-fb-secondary">
          Зарплатная ведомость, расчет начислений и управление ставками оплаты
        </p>
      </div>

      <div class="flex items-center gap-2">
        <button
          v-if="activeTab === 'settings'"
          type="button"
          class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-fb-hoverBtn transition-colors"
          @click="openCreate"
        >
          + Добавить ставку
        </button>
      </div>
    </div>

    <!-- Tabs Switcher -->
    <div class="flex border-b border-fb-line">
      <button
        type="button"
        class="border-b-2 px-6 py-3 text-sm font-semibold transition-all"
        :class="
          activeTab === 'payroll'
            ? 'border-fb-blue text-fb-blue'
            : 'border-transparent text-fb-secondary hover:text-fb-text'
        "
        @click="activeTab = 'payroll'"
      >
        📑 Зарплатная ведомость
      </button>
      <button
        type="button"
        class="border-b-2 px-6 py-3 text-sm font-semibold transition-all"
        :class="
          activeTab === 'settings'
            ? 'border-fb-blue text-fb-blue'
            : 'border-transparent text-fb-secondary hover:text-fb-text'
        "
        @click="activeTab = 'settings'"
      >
        ⚙️ Настройки ставок ({{ rows.length }})
      </button>
    </div>

    <!-- ================= TAB 1: PAYROLL ================= -->
    <div v-if="activeTab === 'payroll'" class="space-y-6">
      <!-- Month Controls -->
      <div class="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-fb-line bg-fb-card p-4">
        <div class="flex items-center gap-3">
          <span class="text-sm font-semibold text-fb-text">Период:</span>
          <div class="flex items-center gap-1 rounded-xl border border-fb-line bg-white p-1">
            <button
              type="button"
              class="rounded-lg px-2.5 py-1 text-xs text-fb-secondary hover:bg-fb-canvas hover:text-fb-text"
              @click="shiftMonth(-1)"
            >
              ◀
            </button>
            <input
              v-model="selectedMonth"
              type="month"
              class="border-none bg-transparent px-2 py-0.5 text-sm font-bold text-fb-text focus:outline-none"
              @change="loadPayroll"
            />
            <button
              type="button"
              class="rounded-lg px-2.5 py-1 text-xs text-fb-secondary hover:bg-fb-canvas hover:text-fb-text"
              @click="shiftMonth(1)"
            >
              ▶
            </button>
          </div>
          <button
            type="button"
            class="rounded-lg border border-fb-line px-3 py-1 text-xs font-medium text-fb-secondary hover:bg-fb-canvas"
            @click="setThisMonth"
          >
            Текущий месяц
          </button>
        </div>

        <button
          type="button"
          class="rounded-lg border border-fb-line px-3.5 py-1.5 text-xs font-semibold text-fb-secondary hover:text-fb-text"
          @click="loadPayroll"
        >
          🔄 Обновить расчет
        </button>
      </div>

      <!-- Summary KPI Cards -->
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="text-xs font-semibold uppercase tracking-wider text-fb-secondary">Всего начислено</div>
          <div class="mt-2 text-2xl font-black text-fb-text">
            {{ payrollSummary.total_accrued.toLocaleString() }} <span class="text-xs font-semibold text-fb-secondary">UZS</span>
          </div>
          <div class="mt-1 text-xs text-fb-secondary">По формулам ставок преподавателей</div>
        </div>

        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="text-xs font-semibold uppercase tracking-wider text-emerald-700">Выплачено за месяц</div>
          <div class="mt-2 text-2xl font-black text-emerald-700">
            {{ payrollSummary.total_paid.toLocaleString() }} <span class="text-xs font-semibold text-fb-secondary">UZS</span>
          </div>
          <div class="mt-1 text-xs text-fb-secondary">Зафиксировано в кассе / расходах</div>
        </div>

        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="text-xs font-semibold uppercase tracking-wider text-rose-700">Остаток к выплате</div>
          <div class="mt-2 text-2xl font-black text-rose-700">
            {{ payrollSummary.total_balance.toLocaleString() }} <span class="text-xs font-semibold text-fb-secondary">UZS</span>
          </div>
          <div class="mt-1 text-xs text-fb-secondary">Текущая задолженность центра</div>
        </div>

        <div class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
          <div class="text-xs font-semibold uppercase tracking-wider text-fb-secondary">Преподавателей в штате</div>
          <div class="mt-2 text-2xl font-black text-fb-text">
            {{ payrollSummary.teachers_count }}
          </div>
          <div class="mt-1 text-xs text-fb-secondary">Активных преподавателей компании</div>
        </div>
      </div>

      <!-- Payroll Table -->
      <div class="overflow-hidden rounded-2xl border border-fb-line bg-fb-card shadow-sm">
        <div v-if="payrollLoading" class="p-12 text-center text-fb-secondary">
          Вычисление зарплатной ведомости…
        </div>
        <div v-else-if="!payrollRows.length" class="p-12 text-center text-fb-secondary">
          Преподавателей не найдено
        </div>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead class="border-b border-fb-line bg-fb-canvas text-xs uppercase tracking-wider font-semibold text-fb-secondary">
              <tr>
                <th class="px-5 py-4">Преподаватель</th>
                <th class="px-5 py-4">Группы</th>
                <th class="px-5 py-4 text-center">Уроков</th>
                <th class="px-5 py-4 text-center">Учеников</th>
                <th class="px-5 py-4">Ставка</th>
                <th class="px-5 py-4 text-right">Начислено</th>
                <th class="px-5 py-4 text-right">Выплачено</th>
                <th class="px-5 py-4 text-right">Остаток</th>
                <th class="px-5 py-4 text-center">Статус</th>
                <th class="px-5 py-4 text-right">Действие</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-fb-line">
              <tr
                v-for="row in payrollRows"
                :key="row.teacher_id"
                class="hover:bg-fb-canvas/50 transition-colors"
              >
                <!-- Teacher -->
                <td class="px-5 py-4 font-semibold text-fb-text">
                  <div>{{ row.teacher_name }}</div>
                  <div class="text-xs font-normal text-fb-secondary">{{ row.phone }}</div>
                </td>

                <!-- Groups -->
                <td class="px-5 py-4 text-xs text-fb-secondary max-w-[180px] truncate" :title="row.groups_names">
                  {{ row.groups_names }}
                </td>

                <!-- Lessons count -->
                <td class="px-5 py-4 text-center text-xs font-medium">
                  {{ row.lessons_count }}
                </td>

                <!-- Students count -->
                <td class="px-5 py-4 text-center text-xs font-medium">
                  {{ row.students_count }}
                </td>

                <!-- Salary Type / Rate -->
                <td class="px-5 py-4 text-xs">
                  <div class="font-medium text-fb-text">{{ row.salary_type_label }}</div>
                  <div v-if="row.rate_amount" class="text-fb-secondary">
                    {{ row.rate_amount.toLocaleString() }} {{ row.salary_type === 'percent' ? '%' : 'UZS' }}
                  </div>
                </td>

                <!-- Accrued -->
                <td class="px-5 py-4 text-right font-bold text-fb-text">
                  {{ row.accrued.toLocaleString() }}
                </td>

                <!-- Paid -->
                <td class="px-5 py-4 text-right font-medium text-emerald-700">
                  {{ row.paid.toLocaleString() }}
                </td>

                <!-- Balance -->
                <td
                  class="px-5 py-4 text-right font-black"
                  :class="row.balance > 0 ? 'text-rose-700' : 'text-fb-secondary'"
                >
                  {{ row.balance.toLocaleString() }}
                </td>

                <!-- Status Badge -->
                <td class="px-5 py-4 text-center">
                  <span
                    v-if="row.status === 'paid'"
                    class="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-800"
                  >
                    Выплачено
                  </span>
                  <span
                    v-else-if="row.status === 'partial'"
                    class="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800"
                  >
                    Частично
                  </span>
                  <span
                    v-else-if="row.status === 'unpaid'"
                    class="rounded-full bg-rose-100 px-2.5 py-0.5 text-xs font-semibold text-rose-800"
                  >
                    К выплате
                  </span>
                  <span
                    v-else
                    class="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-500"
                  >
                    —
                  </span>
                </td>

                <!-- Action Button -->
                <td class="px-5 py-4 text-right">
                  <button
                    type="button"
                    class="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700 disabled:opacity-40 transition-colors"
                    :disabled="row.accrued === 0 && row.balance === 0"
                    @click="openPayModal(row)"
                  >
                    <span>💸</span>
                    <span>Выплатить</span>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ================= TAB 2: SALARY SETTINGS ================= -->
    <div v-else-if="activeTab === 'settings'" class="space-y-4">
      <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
        <div class="min-w-[240px] flex-1">
          <label class="mb-1 block text-xs text-fb-secondary">Search</label>
          <div class="relative">
            <input
              v-model="filters.q"
              type="search"
              placeholder="Search by teacher, course, group, or salary type…"
              class="w-full h-10 pl-9 pr-4 rounded-lg border border-fb-line text-sm focus:outline-none focus:border-fb-blue"
              @keydown.enter="loadRows"
            />
            <svg class="absolute left-3 top-2.5 text-fb-secondary" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
          </div>
        </div>
        <button type="button" class="rounded-lg border border-fb-line px-4 py-2 text-sm" @click="loadRows">Apply</button>
      </div>

      <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
        <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
        <div v-else-if="!tableRows.length" class="p-8 text-center text-fb-icon">
          {{ rows.length ? 'No salary settings match your search.' : 'No salary settings' }}
        </div>
        <table v-else class="w-full text-base">
          <thead class="border-b bg-fb-canvas">
            <tr>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Calc setting</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Salary type</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Amount</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Course</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Group</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Teacher</th>
              <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Creator</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in tableRows" :key="row.id" class="cursor-pointer border-b hover:bg-fb-hover/40" @click="openDetail(row.id)">
              <td class="px-5 py-4">{{ row.calc_setting }}</td>
              <td class="px-5 py-4">{{ row.salary_type }}</td>
              <td class="px-5 py-4 font-semibold text-fb-blue">{{ row.amount }}</td>
              <td class="px-5 py-4">{{ row.course }}</td>
              <td class="px-5 py-4">{{ row.group }}</td>
              <td class="px-5 py-4 font-medium">{{ row.teacher }}</td>
              <td class="px-5 py-4 text-fb-secondary">{{ row.created_by }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal: Выплата зарплаты -->
    <div v-if="showPayModal && payTeacher" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="fixed inset-0 bg-black/40" @click="showPayModal = false" />
      <div class="relative w-full max-w-md rounded-2xl border border-fb-line bg-fb-card p-6 shadow-2xl">
        <div class="flex items-center justify-between border-b border-fb-line pb-3">
          <div>
            <h3 class="text-base font-bold text-fb-text">Выплата зарплаты</h3>
            <p class="text-xs text-fb-secondary mt-0.5">
              {{ payTeacher.teacher_name }} • Период: {{ selectedMonth }}
            </p>
          </div>
          <button type="button" class="text-fb-secondary hover:text-fb-text" @click="showPayModal = false">✕</button>
        </div>

        <form class="mt-4 space-y-4" @submit.prevent="submitSalaryPayment">
          <div class="rounded-xl border border-fb-line bg-fb-canvas/50 p-3 text-xs space-y-1">
            <div class="flex justify-between">
              <span class="text-fb-secondary">Начислено за месяц:</span>
              <span class="font-bold text-fb-text">{{ payTeacher.accrued.toLocaleString() }} UZS</span>
            </div>
            <div class="flex justify-between">
              <span class="text-fb-secondary">Уже выплачено:</span>
              <span class="font-medium text-emerald-700">{{ payTeacher.paid.toLocaleString() }} UZS</span>
            </div>
            <div class="flex justify-between border-t border-fb-line pt-1">
              <span class="font-semibold text-fb-secondary">Остаток к выплате:</span>
              <span class="font-black text-rose-700">{{ payTeacher.balance.toLocaleString() }} UZS</span>
            </div>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">Сумма выплаты (UZS)</label>
            <input
              v-model.number="payForm.amount"
              type="number"
              min="1"
              required
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-base font-bold text-gray-950 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">Способ выплаты (Касса)</label>
            <select
              v-model="payForm.method"
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            >
              <option value="cash">Наличные (Касса)</option>
              <option value="card">Банковская карта (Перевод)</option>
              <option value="transfer">Расчетный счет (Банк)</option>
            </select>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">Комментарий / Назначение</label>
            <input
              v-model="payForm.comment"
              type="text"
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            />
          </div>

          <p v-if="payError" class="text-xs text-fb-danger">{{ payError }}</p>

          <div class="flex justify-end gap-2 border-t border-fb-line pt-4">
            <button
              type="button"
              class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:bg-fb-canvas"
              @click="showPayModal = false"
            >
              Отмена
            </button>
            <button
              type="submit"
              class="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
              :disabled="paySaving"
            >
              {{ paySaving ? 'Проведение…' : 'Подтвердить выплату' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Drawer Panel: Salary Setting Detail / Edit / Create -->
    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closePanel" />
      <div class="drawer-panel-fb max-w-lg">
        <div class="flex items-center justify-between border-b px-6 py-4">
          <h2 class="text-lg font-semibold">{{ panelTitle }}</h2>
          <button type="button" @click="closePanel">✕</button>
        </div>
        <div v-if="panelLoading" class="p-6 text-fb-secondary">Loading…</div>
        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitForm">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Teacher</label>
              <select
                v-if="!isReadOnly && teachers.length"
                v-model="form.teacher_name"
                class="w-full rounded-lg border px-3 py-2 text-sm"
              >
                <option value="">Select teacher</option>
                <option v-for="t in teachers" :key="t.id" :value="t.name">{{ t.name }}</option>
              </select>
              <input
                v-else
                v-model="form.teacher_name"
                :readonly="isReadOnly"
                required
                class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Salary type</label>
              <select v-model="form.salary_type" :disabled="isReadOnly" class="w-full rounded-lg border px-3 py-2 text-sm">
                <option v-for="st in SALARY_TYPES" :key="st.value" :value="st.value">{{ st.label }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Amount (Fixed or % or per student)</label>
              <input v-model.number="form.amount" type="number" :readonly="isReadOnly" required class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Course (optional)</label>
              <input v-model="form.course_name" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Group (optional)</label>
              <input v-model="form.group_name" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas" />
            </div>
            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>
          <div class="flex gap-2 border-t px-6 py-4">
            <template v-if="isReadOnly && detailRow">
              <button type="button" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" @click="startEdit">Edit</button>
              <button type="button" class="rounded-lg border border-red-300 px-5 py-2 text-sm text-fb-danger" :disabled="deleting" @click="deleteRow">Delete</button>
            </template>
            <button v-else type="submit" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" :disabled="saving">
              {{ saving ? 'Saving…' : editingRow ? 'Save' : 'Create' }}
            </button>
            <button type="button" class="rounded-lg border px-5 py-2 text-sm" @click="closePanel">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
