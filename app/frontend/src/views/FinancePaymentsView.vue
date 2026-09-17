<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import ReceiptModal, { type ReceiptPayment } from '../components/ReceiptModal.vue';
import PaymentLinkModal, { type StudentPaymentLinkTarget } from '../components/PaymentLinkModal.vue';

interface PaymentRow {
  id: number;
  date: string;
  name: string;
  student_id: number | null;
  student_name: string;
  sum: number;
  months_covered?: number;
  method: string;
  method_pay: string;
  teacher: string;
  teacher_name: string;
  comment: string;
  creator: string;
}

interface StudentOption {
  id: number;
  full_name: string;
  phone: string;
  group?: string | null;
  group_teacher?: string;
  course_price?: number;
}

const METHODS = [
  { value: 'cash', label: 'Cash' },
  { value: 'card', label: 'Card' },
  { value: 'transfer', label: 'Transfer' },
] as const;

const rows = ref<PaymentRow[]>([]);
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

function printPayment(row: PaymentRow) {
  receiptPayment.value = {
    id: row.id,
    date: row.date,
    student_name: row.student_name || row.name,
    amount: row.sum,
    months_covered: row.months_covered || 1,
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
const form = reactive({
  student_id: null as number | null,
  student_name: '',
  amount: 0,
  months_covered: 1,
  method: 'cash' as (typeof METHODS)[number]['value'],
  teacher_name: '',
  comment: '',
});

const isReadOnly = computed(() => Boolean(detailRow.value && !editingRow.value));
const panelTitle = computed(() =>
  editingRow.value ? 'Edit payment' : detailRow.value ? 'Payment details' : 'Add payment',
);
const tableRows = computed(() =>
  rows.value.map((r) => ({
    id: r.id,
    date: r.date,
    name: r.name,
    sum: r.sum.toLocaleString(),
    months_covered: r.months_covered || 1,
    method_pay: r.method_pay,
    teacher: r.teacher,
    comment: r.comment || '—',
    creator: r.creator,
  })),
);

const filteredStudents = computed(() => {
  const q = studentSearchQuery.value.trim().toLowerCase();
  if (!q) return studentsList.value.slice(0, 20);
  return studentsList.value
    .filter((s) => s.full_name.toLowerCase().includes(q) || s.phone.includes(q))
    .slice(0, 20);
});

function selectStudent(student: StudentOption) {
  selectedStudent.value = student;
  form.student_id = student.id;
  form.student_name = student.full_name;
  studentSearchQuery.value = student.full_name;
  if (student.group_teacher) {
    form.teacher_name = student.group_teacher;
  }
  if (student.course_price) {
    form.amount = student.course_price * form.months_covered;
  }
  showStudentDropdown.value = false;
}

function onMonthsChange() {
  if (form.months_covered < 1) form.months_covered = 1;
  if (selectedStudent.value?.course_price) {
    form.amount = selectedStudent.value.course_price * form.months_covered;
  }
}

function resetForm() {
  form.student_id = null;
  form.student_name = '';
  form.amount = 0;
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
  form.months_covered = row.months_covered || 1;
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
    }));
  } catch {
    studentsList.value = [];
  }
}

async function loadRows() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.method) params.method = filters.method;
    if (filters.q.trim()) params.q = filters.q.trim();
    const { data } = await client.get<ApiEnvelope<PaymentRow[]>>('/replenishments', { params });
    rows.value = data.data;
  } finally {
    loading.value = false;
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
  if (!form.student_name.trim()) {
    formError.value = 'Enter student name';
    return;
  }
  if (!form.amount) {
    formError.value = 'Enter amount';
    return;
  }
  saving.value = true;
  try {
    const payload = {
      student_id: form.student_id,
      student_name: form.student_name.trim(),
      amount: form.amount,
      months_covered: form.months_covered || 1,
      method: form.method,
      teacher_name: form.teacher_name.trim(),
      comment: form.comment.trim(),
    };
    if (editingRow.value) {
      await client.patch(`/replenishments/${editingRow.value.id}`, payload);
    } else {
      await client.post('/replenishments', payload);
    }
    closePanel();
    await loadRows();
  } catch {
    formError.value = 'Could not save payment';
  } finally {
    saving.value = false;
  }
}

async function deleteRow() {
  if (!detailRow.value || !window.confirm('Delete this payment?')) return;
  deleting.value = true;
  try {
    await client.delete(`/replenishments/${detailRow.value.id}`);
    closePanel();
    await loadRows();
  } finally {
    deleting.value = false;
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
      <h1 class="text-xl font-semibold text-fb-text">All payments</h1>
      <button type="button" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" @click="openCreate">
        + Add payment
      </button>
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">From</label>
        <input v-model="filters.date_from" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">To</label>
        <input v-model="filters.date_to" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">Method</label>
        <select v-model="filters.method" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option value="">All</option>
          <option v-for="m in METHODS" :key="m.value" :value="m.value">{{ m.label }}</option>
        </select>
      </div>
      <div class="min-w-[180px] flex-1">
        <label class="mb-1 block text-xs text-fb-secondary">Search</label>
        <input v-model="filters.q" type="search" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm" @keydown.enter="loadRows" />
      </div>
      <button type="button" class="rounded-lg border border-fb-line px-4 py-2 text-sm" @click="loadRows">Apply</button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!tableRows.length" class="p-8 text-center text-fb-icon">No payments</div>
      <table v-else class="w-full text-base">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Date</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Name</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Sum</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Period</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Method</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Teacher</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Comment</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Creator</th>
            <th class="px-5 py-4 text-right font-semibold text-fb-secondary">Чек</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in tableRows" :key="row.id" class="cursor-pointer border-b hover:bg-fb-hover/40" @click="openDetail(row.id)">
            <td class="px-5 py-4">{{ row.date }}</td>
            <td class="px-5 py-4 font-medium">{{ row.name }}</td>
            <td class="px-5 py-4 font-semibold text-fb-blue">{{ row.sum }}</td>
            <td class="px-5 py-4">
              <span class="inline-flex items-center rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-fb-blue">
                {{ row.months_covered }} mo
              </span>
            </td>
            <td class="px-5 py-4">{{ row.method_pay }}</td>
            <td class="px-5 py-4">{{ row.teacher }}</td>
            <td class="px-5 py-4">{{ row.comment }}</td>
            <td class="px-5 py-4">{{ row.creator }}</td>
            <td class="px-5 py-4 text-right" @click.stop>
              <button
                type="button"
                title="Печать квитанции"
                class="inline-flex items-center gap-1 rounded-lg border border-fb-line bg-white px-2.5 py-1 text-xs font-medium text-fb-secondary shadow-sm hover:border-fb-blue hover:text-fb-blue transition-colors"
                @click="printRowById(row.id)"
              >
                <span>🖨️</span>
                <span>Чек</span>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

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
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Student</label>
              <div v-if="!isReadOnly" class="relative">
                <input
                  v-model="studentSearchQuery"
                  type="text"
                  required
                  placeholder="Type to search or enter name…"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
                  @focus="showStudentDropdown = true"
                  @input="showStudentDropdown = true; form.student_name = studentSearchQuery; form.student_id = null"
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
                      {{ s.course_price.toLocaleString() }} UZS/mo
                    </span>
                  </button>
                </div>
              </div>
              <input
                v-else
                :value="form.student_name"
                readonly
                class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Months paid (Количество месяцев)</label>
              <input
                v-model.number="form.months_covered"
                type="number"
                min="1"
                :readonly="isReadOnly"
                required
                class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                @input="onMonthsChange"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Amount (Сумма)</label>
              <input
                v-model.number="form.amount"
                type="number"
                :readonly="isReadOnly"
                required
                class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Method</label>
              <select v-model="form.method" :disabled="isReadOnly" class="w-full rounded-lg border px-3 py-2 text-sm">
                <option v-for="m in METHODS" :key="m.value" :value="m.value">{{ m.label }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Teacher</label>
              <input v-model="form.teacher_name" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Comment</label>
              <textarea v-model="form.comment" :readonly="isReadOnly" rows="3" class="w-full rounded-lg border px-3 py-2 text-sm read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none" />
            </div>
            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>
          <div class="flex gap-2 border-t px-6 py-4">
            <template v-if="isReadOnly && detailRow">
              <button
                type="button"
                class="inline-flex items-center gap-1.5 rounded-lg border border-fb-line bg-white px-4 py-2 text-sm font-medium text-fb-text hover:border-fb-blue hover:text-fb-blue transition-colors"
                @click="printPayment(detailRow)"
              >
                <span>🖨️</span>
                <span>Печать чека</span>
              </button>
              <button
                v-if="detailRow.student_id"
                type="button"
                class="inline-flex items-center gap-1.5 rounded-lg border border-fb-line bg-white px-3 py-2 text-sm font-medium text-fb-text hover:border-fb-blue hover:text-fb-blue transition-colors"
                @click="openPaymentLink(detailRow)"
              >
                <span>💳</span>
                <span>Ссылка</span>
              </button>
              <button type="button" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" @click="startEdit">Edit</button>
              <button type="button" class="rounded-lg border border-red-300 px-5 py-2 text-sm text-fb-danger" :disabled="deleting" @click="deleteRow">Delete</button>
            </template>
            <template v-else>
              <button
                v-if="selectedStudent"
                type="button"
                class="inline-flex items-center gap-1.5 rounded-lg border border-fb-line bg-white px-3 py-2 text-sm font-medium text-fb-text hover:border-fb-blue hover:text-fb-blue transition-colors"
                @click="openPaymentLink(selectedStudent)"
              >
                <span>💳</span>
                <span>Ссылка</span>
              </button>
              <button type="submit" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" :disabled="saving">
                {{ saving ? 'Saving…' : editingRow ? 'Save' : 'Create' }}
              </button>
            </template>
            <button type="button" class="rounded-lg border px-5 py-2 text-sm" @click="closePanel">Cancel</button>
          </div>
        </form>
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
