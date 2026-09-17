<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';
import { downloadCsv } from '../utils/csvExport';
import ImportCsvModal from '../components/ImportCsvModal.vue';
import ReceiptModal, { type ReceiptPayment } from '../components/ReceiptModal.vue';
import PaymentLinkModal, { type StudentPaymentLinkTarget } from '../components/PaymentLinkModal.vue';
import {
  groupRoute,
  hasCreateFlag,
  parseOpenId,
  routeWithoutCreate,
  routeWithoutOpen,
} from '../utils/crossLinks';

interface Branch {
  id: number;
  name: string;
}

interface GroupOption {
  id: number;
  name: string;
  branch_id: number;
}

interface StudentRow {
  id: number;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  phone2?: string;
  address?: string;
  comment?: string;
  lead_id?: number | null;
  photo: string | null;
  school: string;
  telegram: string;
  parent_telegram: string;
  telegram_code?: string | null;
  trial_date?: string | null;
  last_payment_date?: string | null;
  next_payment_date?: string | null;
  is_debtor?: boolean;
  overdue_days?: number;
  paid_count?: number;
  payment_offset?: number;
  status: number;
  status_label: string;
  branch_id: number;
  branch: string;
  group_id: number | null;
  group: string | null;
  group_teacher?: string;
  course_price?: number;
  course_name?: string;
  created_at: string;
}

interface StudentPayment {
  id: number;
  date: string;
  amount: number;
  months_covered: number;
  method: string;
  method_pay: string;
  comment: string;
  creator: string;
}

const STATUS_OPTIONS = [
  { value: 1, label: 'Обучается' },
  { value: 2, label: 'Заморозка' },
  { value: 7, label: 'Ушел после пробного' },
  { value: 8, label: 'Отчислен / Ушел' },
  { value: 9, label: 'Завершил курс' },
] as const;

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const rows = ref<StudentRow[]>([]);
const branches = ref<Branch[]>([]);
const groups = ref<GroupOption[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingStudent = ref<StudentRow | null>(null);
const detailStudent = ref<StudentRow | null>(null);
const photoFile = ref<File | null>(null);
const photoPreview = ref('');
const photoMarkedRemove = ref(false);
const photoInput = ref<HTMLInputElement | null>(null);
const tgBotUsername = ref('');
const showImportModal = ref(false);
const showUnfreezeModal = ref(false);
const unfreezeStudent = ref<StudentRow | null>(null);
const unfreezeDate = ref(new Date().toISOString().slice(0, 10));
const unfreezeSaving = ref(false);
const unfreezeError = ref('');

const studentPayments = ref<StudentPayment[]>([]);
const paymentsLoading = ref(false);
const showPayModal = ref(false);
const payForm = reactive({
  amount: 0,
  months_covered: 1,
  method: 'cash' as 'cash' | 'card' | 'transfer',
  comment: '',
});
const paySaving = ref(false);
const payError = ref('');

const showReceiptModal = ref(false);
const receiptPayment = ref<ReceiptPayment | null>(null);

const showPaymentLinkModal = ref(false);
const paymentLinkStudent = ref<StudentPaymentLinkTarget | null>(null);

function openPaymentLinkModal(student?: StudentRow | null) {
  const target = student || detailStudent.value;
  if (!target) return;
  paymentLinkStudent.value = {
    id: target.id,
    full_name: target.full_name,
    phone: target.phone,
    group: target.group,
    course_price: target.course_price,
    parent_telegram: target.parent_telegram,
  };
  showPaymentLinkModal.value = true;
}

function printStudentPayment(p: StudentPayment) {
  receiptPayment.value = {
    id: p.id,
    date: p.date,
    student_name: detailStudent.value?.full_name || 'Ученик',
    amount: p.amount,
    months_covered: p.months_covered || 1,
    method: p.method,
    method_pay: p.method_pay,
    teacher: detailStudent.value?.group_teacher || '',
    comment: p.comment,
    creator: p.creator,
  };
  showReceiptModal.value = true;
}

async function loadStudentPayments(studentId: number) {
  paymentsLoading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<StudentPayment[]>>(`/students/${studentId}/payments`);
    studentPayments.value = data.data;
  } catch {
    studentPayments.value = [];
  } finally {
    paymentsLoading.value = false;
  }
}

function openAcceptPaymentModal() {
  if (!detailStudent.value) return;
  payForm.months_covered = 1;
  const coursePrice = detailStudent.value.course_price || 0;
  payForm.amount = coursePrice || 0;
  payForm.method = 'cash';
  payForm.comment = '';
  payError.value = '';
  showPayModal.value = true;
}

function onPayMonthsChange() {
  if (payForm.months_covered < 1) payForm.months_covered = 1;
  const coursePrice = detailStudent.value?.course_price || 0;
  if (coursePrice) {
    payForm.amount = coursePrice * payForm.months_covered;
  }
}

async function submitPayment() {
  if (!detailStudent.value) return;
  if (!payForm.amount) {
    payError.value = 'Введите сумму оплаты';
    return;
  }
  paySaving.value = true;
  payError.value = '';
  try {
    await client.post('/replenishments', {
      student_id: detailStudent.value.id,
      student_name: detailStudent.value.full_name,
      amount: payForm.amount,
      months_covered: payForm.months_covered || 1,
      method: payForm.method,
      comment: payForm.comment.trim(),
    });
    showPayModal.value = false;
    const studentId = detailStudent.value.id;
    const [{ data }] = await Promise.all([
      client.get<ApiEnvelope<StudentRow>>(`/students/${studentId}`),
      loadStudentPayments(studentId),
      loadStudents(),
    ]);
    detailStudent.value = data.data;
    fillForm(data.data);
  } catch (err: any) {
    payError.value = apiErrorMessage(err, 'Не удалось провести оплату');
  } finally {
    paySaving.value = false;
  }
}

function openUnfreezeModal(student: StudentRow) {
  unfreezeStudent.value = student;
  unfreezeDate.value = new Date().toISOString().slice(0, 10);
  unfreezeError.value = '';
  showUnfreezeModal.value = true;
}

async function confirmUnfreeze() {
  if (!unfreezeStudent.value) return;
  if (!unfreezeDate.value) {
    unfreezeError.value = 'Укажите дату возобновления обучения';
    return;
  }
  unfreezeSaving.value = true;
  unfreezeError.value = '';
  try {
    const { data } = await client.patch<ApiEnvelope<StudentRow>>(
      `/students/${unfreezeStudent.value.id}`,
      {
        status: 1,
        trial_date: unfreezeDate.value,
      },
    );
    showUnfreezeModal.value = false;
    if (detailStudent.value && detailStudent.value.id === unfreezeStudent.value.id) {
      detailStudent.value = data.data;
      fillForm(data.data);
    }
    await loadStudents();
  } catch (error) {
    unfreezeError.value = apiErrorMessage(error, 'Не удалось возобновить обучение');
  } finally {
    unfreezeSaving.value = false;
  }
}

const filters = reactive({
  branch_id: '',
  group_id: '',
  status: '',
  q: '',
});

const form = reactive({
  first_name: '',
  last_name: '',
  phone: '',
  phone2: '',
  address: '',
  comment: '',
  school: '',
  telegram: '',
  parent_telegram: '',
  status: 1,
  trial_date: '',
  branch_id: 0,
  group_id: '' as number | '',
});

const title = computed(() => {
  if (route.path.includes('debtors')) return 'Debtors (Должники)';
  if (route.query.statuses === '1') return 'Обучающиеся';
  if (route.query.statuses === '2') return 'Замороженные';
  if (route.query.statuses === '7') return 'Ушедшие после пробного';
  if (route.query.statuses === '8') return 'Отчисленные / Ушедшие';
  if (route.query.statuses === '9') return 'Завершившие курс';
  if (route.query.q) return `Students — search “${route.query.q}”`;
  return 'Students';
});

const panelTitle = computed(() => {
  if (editingStudent.value) return 'Edit student';
  if (detailStudent.value) return 'Student details';
  return 'Add student';
});

const isReadOnly = computed(() => Boolean(detailStudent.value && !editingStudent.value));
const canExportStudents = computed(() => auth.can(PERM.STUDENTS_VIEW));
const canImportStudents = computed(() => auth.can(PERM.STUDENTS_WRITE));

function exportCsv() {
  downloadCsv(
    'students.csv',
    ['Name', 'Phone', 'Phone 2', 'Address', 'Comment', 'Status', 'Start Date', 'Next Payment', 'Payment Status', 'School', 'Group', 'Branch', 'Telegram (parents)'],
    rows.value.map((row) => [
      row.full_name,
      row.phone,
      row.phone2 || '',
      row.address || '',
      row.comment || '',
      row.status_label,
      row.trial_date || '',
      row.next_payment_date || '',
      row.is_debtor ? `Overdue (${row.overdue_days || 0} days)` : 'OK',
      row.school,
      row.group ?? '',
      row.branch,
      row.parent_telegram,
    ]),
  );
}

const filteredGroups = computed(() => {
  if (!form.branch_id) return groups.value;
  return groups.value.filter((group) => group.branch_id === form.branch_id);
});

function initials(name: string) {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

function formatAddedDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const dd = String(date.getDate()).padStart(2, '0');
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  return `${dd}.${mm}.${date.getFullYear()}`;
}

function statusBadgeClass(status: number) {
  if (status === 2) return 'bg-amber-100 text-amber-700';
  if (status === 7) return 'bg-orange-100 text-orange-700';
  if (status === 9) return 'bg-purple-100 text-purple-700';
  if (status === 8) return 'bg-gray-100 text-gray-700';
  return 'bg-emerald-100 text-emerald-700';
}

const filteredStudents = computed(() => {
  const q = filters.q.trim().toLowerCase();
  if (!q) return rows.value;
  const digits = q.replace(/\D/g, '');
  return rows.value.filter((row) => {
    const nameMatch =
      row.full_name?.toLowerCase().includes(q) ||
      row.first_name?.toLowerCase().includes(q) ||
      row.last_name?.toLowerCase().includes(q);
    const phoneDigits1 = (row.phone || '').replace(/\D/g, '');
    const phoneDigits2 = (row.phone2 || '').replace(/\D/g, '');
    const phoneMatch = digits
      ? phoneDigits1.includes(digits) || phoneDigits2.includes(digits)
      : (row.phone && row.phone.toLowerCase().includes(q)) || (row.phone2 && row.phone2.toLowerCase().includes(q));
    const schoolMatch = row.school?.toLowerCase().includes(q);
    const groupMatch = row.group?.toLowerCase().includes(q);
    return Boolean(nameMatch || phoneMatch || schoolMatch || groupMatch);
  });
});

const tableRows = computed(() =>
  filteredStudents.value.map((row) => ({
    id: row.id,
    photo: row.photo,
    initials: initials(row.full_name),
    full_name: row.full_name,
    phone: row.phone,
    phone2: row.phone2 || '',
    status: row.status,
    statusText: row.status_label,
    school: row.school || '—',
    group: row.group ?? '—',
    group_id: row.group_id,
    branch: row.branch,
    trialDate: row.trial_date ? formatAddedDate(row.trial_date) : '—',
    nextPaymentDate: row.next_payment_date ? formatAddedDate(row.next_payment_date) : '—',
    isDebtor: Boolean(row.is_debtor),
    overdueDays: row.overdue_days || 0,
  })),
);

function syncFiltersFromRoute() {
  filters.branch_id = String(route.query.branch_id ?? '');
  filters.group_id = String(route.query.group_id ?? '');
  filters.q = String(route.query.q ?? '');

  if (route.path.includes('debtors')) {
    filters.status = 'debtors';
  } else if (route.query.statuses) {
    filters.status = String(route.query.statuses);
  } else {
    filters.status = filters.status || '';
  }
}

function resetForm() {
  form.first_name = '';
  form.last_name = '';
  form.phone = '';
  form.phone2 = '';
  form.address = '';
  form.comment = '';
  form.school = '';
  form.telegram = '';
  form.parent_telegram = '';
  form.status = 1;
  form.trial_date = '';
  form.branch_id = branches.value[0]?.id ?? 0;
  form.group_id = '';
  formError.value = '';
  editingStudent.value = null;
  detailStudent.value = null;
  studentPayments.value = [];
  showPayModal.value = false;
  photoFile.value = null;
  photoPreview.value = '';
  photoMarkedRemove.value = false;
}

function fillForm(student: StudentRow) {
  form.first_name = student.first_name;
  form.last_name = student.last_name;
  form.phone = student.phone;
  form.phone2 = student.phone2 ?? '';
  form.address = student.address ?? '';
  form.comment = student.comment ?? '';
  form.school = student.school ?? '';
  form.telegram = student.telegram ?? '';
  form.parent_telegram = student.parent_telegram ?? '';
  form.status = student.status;
  form.trial_date = student.trial_date ? student.trial_date.slice(0, 10) : '';
  form.branch_id = student.branch_id;
  form.group_id = student.group_id ?? '';
  photoFile.value = null;
  photoPreview.value = student.photo ?? '';
  photoMarkedRemove.value = false;
}

function openCreatePanel() {
  resetForm();
  showPanel.value = true;
}

async function openDetailPanel(studentId: number) {
  resetForm();
  showPanel.value = true;
  panelLoading.value = true;
  try {
    const [{ data }] = await Promise.all([
      client.get<ApiEnvelope<StudentRow>>(`/students/${studentId}`),
      loadStudentPayments(studentId),
    ]);
    detailStudent.value = data.data;
    fillForm(data.data);
  } finally {
    panelLoading.value = false;
  }
}

function startEdit() {
  if (!detailStudent.value) return;
  editingStudent.value = detailStudent.value;
}

function closePanel() {
  showPanel.value = false;
  resetForm();
  if (route.query.open) {
    router.replace(routeWithoutOpen(route));
  }
}

function parentTgLink(code: string | null | undefined) {
  if (!tgBotUsername.value || !code) return '';
  return `https://t.me/${tgBotUsername.value}?start=${code}`;
}

const detailParentTgLink = computed(() => parentTgLink(detailStudent.value?.telegram_code));

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = document.createElement('textarea');
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    document.body.removeChild(area);
  }
}

async function loadTelegramConfig() {
  try {
    const { data } = await client.get<ApiEnvelope<{ enabled: boolean; bot_username: string | null }>>('/telegram/config');
    if (data.data.enabled && data.data.bot_username) {
      tgBotUsername.value = data.data.bot_username;
    }
  } catch {
    // notifications module unavailable - hide invite links
  }
}

async function loadOptions() {
  const [branchRes, groupRes] = await Promise.all([
    client.get<ApiEnvelope<Branch[]>>('/branch'),
    client.get<ApiEnvelope<GroupOption[]>>('/groups'),
  ]);
  branches.value = branchRes.data.data;
  groups.value = groupRes.data.data.map((group) => ({
    id: group.id,
    name: group.name,
    branch_id: group.branch_id,
  }));
  if (!form.branch_id && branches.value.length) {
    form.branch_id = branches.value[0].id;
  }
}

async function loadStudents() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.branch_id) params.branch_id = filters.branch_id;
    if (filters.group_id) params.group_id = filters.group_id;
    if (route.path.includes('debtors') || filters.status === 'debtors') {
      params.debtors = '1';
    } else if (filters.status) {
      params.statuses = filters.status;
    }
    if (filters.q.trim()) params.q = filters.q.trim();

    const { data } = await client.get<ApiEnvelope<StudentRow[]>>('/students', { params });
    rows.value = data.data;
  } finally {
    loading.value = false;
  }
}

const ALLOWED_PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_PHOTO_MB = 10;

function onPhotoChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file) return;
  if (!ALLOWED_PHOTO_TYPES.includes(file.type)) {
    formError.value = 'Only JPG, PNG or WEBP photos are allowed';
    return;
  }
  if (file.size > MAX_PHOTO_MB * 1024 * 1024) {
    formError.value = `Photo is too large (max ${MAX_PHOTO_MB} MB)`;
    return;
  }
  formError.value = '';
  photoFile.value = file;
  photoMarkedRemove.value = false;
  photoPreview.value = URL.createObjectURL(file);
}

function triggerPhotoSelect() {
  photoInput.value?.click();
}

function removePhoto() {
  photoFile.value = null;
  photoPreview.value = '';
  photoMarkedRemove.value = true;
}

function buildPayload() {
  return {
    first_name: form.first_name.trim(),
    last_name: form.last_name.trim(),
    phone: form.phone.trim(),
    phone2: form.phone2.trim(),
    address: form.address.trim(),
    comment: form.comment.trim(),
    school: form.school.trim(),
    telegram: form.telegram.trim(),
    parent_telegram: form.parent_telegram.trim(),
    status: form.status,
    trial_date: form.trial_date || null,
    branch_id: form.branch_id,
    group_id: form.group_id === '' ? null : form.group_id,
  };
}

function apiErrorMessage(error: unknown, fallback: string) {
  const response = (error as { response?: { data?: { message?: string } } }).response;
  return response?.data?.message || fallback;
}

async function submitStudent() {
  formError.value = '';
  if (!form.first_name.trim()) {
    formError.value = 'Enter first name';
    return;
  }
  if (!form.phone.trim()) {
    formError.value = 'Enter phone number';
    return;
  }
  if (!form.branch_id) {
    formError.value = 'Select a branch';
    return;
  }

  saving.value = true;
  try {
    const payload = buildPayload();
    let studentId: number | null = editingStudent.value?.id ?? null;
    if (editingStudent.value) {
      await client.patch(`/students/${editingStudent.value.id}`, payload);
    } else {
      const { data } = await client.post<ApiEnvelope<StudentRow>>('/students', payload);
      studentId = data.data.id;
    }
    if (studentId) {
      if (photoFile.value) {
        const formData = new FormData();
        formData.append('photo', photoFile.value);
        await client.post(`/students/${studentId}/photo`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      } else if (photoMarkedRemove.value) {
        await client.delete(`/students/${studentId}/photo`);
      }
    }
    closePanel();
    await loadStudents();
  } catch (error) {
    formError.value = apiErrorMessage(
      error,
      editingStudent.value ? 'Could not update student' : 'Could not create student',
    );
  } finally {
    saving.value = false;
  }
}

async function deleteStudent() {
  if (!detailStudent.value) return;
  if (!window.confirm(`Delete ${detailStudent.value.full_name}?`)) return;

  deleting.value = true;
  try {
    await client.delete(`/students/${detailStudent.value.id}`);
    closePanel();
    await loadStudents();
  } catch (error) {
    window.alert(apiErrorMessage(error, 'Could not delete student'));
  } finally {
    deleting.value = false;
  }
}

function goGroup(student: StudentRow | { group_id: number | null }) {
  if (!student.group_id) return;
  router.push(groupRoute(student.group_id));
}

async function maybeOpenFromRoute() {
  const id = parseOpenId(route.query);
  if (id == null || showPanel.value) return;
  await openDetailPanel(id);
}

function maybeCreateFromRoute() {
  if (!hasCreateFlag(route.query) || showPanel.value) return;
  openCreatePanel();
  router.replace(routeWithoutCreate(route));
}

function goGroupFromTable(groupId: number) {
  router.push(groupRoute(groupId));
}

function applyFilters() {
  const query: Record<string, string> = {};
  if (filters.branch_id) query.branch_id = filters.branch_id;
  if (filters.group_id) query.group_id = filters.group_id;
  if (filters.status) query.statuses = filters.status;
  if (filters.q.trim()) query.q = filters.q.trim();

  const basePath = route.path.includes('debtors') ? '/students/debtors' : '/students';
  router.push({ path: basePath, query });
}

watch(
  () => route.fullPath,
  async () => {
    syncFiltersFromRoute();
    await loadStudents();
    await maybeOpenFromRoute();
    maybeCreateFromRoute();
  },
);

watch(
  () => form.status,
  (newStatus, oldStatus) => {
    if (editingStudent.value && editingStudent.value.status === 2 && newStatus === 1 && oldStatus !== 1) {
      if (!form.trial_date || form.trial_date === editingStudent.value.trial_date?.slice(0, 10)) {
        form.trial_date = new Date().toISOString().slice(0, 10);
      }
    }
  },
);

let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
watch(
  () => filters.q,
  (newQ) => {
    if (newQ.trim() === String(route.query.q ?? '').trim()) return;
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      applyFilters();
    }, 450);
  },
);

onMounted(async () => {
  syncFiltersFromRoute();
  loadTelegramConfig();
  try {
    await Promise.all([loadOptions(), loadStudents()]);
    await maybeOpenFromRoute();
    maybeCreateFromRoute();
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-baseline gap-3">
        <h1 class="text-xl font-semibold text-fb-text">{{ title }}</h1>
        <span v-if="!loading" class="text-sm text-fb-secondary">
          Quantity — {{ tableRows.length }}<span v-if="filters.q.trim() && rows.length !== tableRows.length"> (of {{ rows.length }})</span>
        </span>
      </div>
      <div class="flex flex-wrap gap-2">
        <button
          v-if="canExportStudents"
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
          @click="exportCsv"
        >
          Export
        </button>
        <button
          v-if="canImportStudents"
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
          @click="showImportModal = true"
        >
          Import
        </button>
        <button
          type="button"
          class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:bg-fb-blue-dark"
          @click="openCreatePanel"
        >
          + Add student
        </button>
      </div>
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div v-if="!route.path.includes('debtors')">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Branch</label>
        <select
          v-model="filters.branch_id"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm"
        >
          <option value="">All branches</option>
          <option v-for="branch in branches" :key="branch.id" :value="String(branch.id)">
            {{ branch.name }}
          </option>
        </select>
      </div>
      <div v-if="!route.path.includes('debtors')">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Group</label>
        <select
          v-model="filters.group_id"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm"
        >
          <option value="">All groups</option>
          <option v-for="group in groups" :key="group.id" :value="String(group.id)">
            {{ group.name }}
          </option>
        </select>
      </div>
      <div v-if="!route.path.includes('debtors')">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Status</label>
        <select
          v-model="filters.status"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          <option v-for="option in STATUS_OPTIONS" :key="option.value" :value="String(option.value)">
            {{ option.label }}
          </option>
        </select>
      </div>
      <div class="min-w-[240px] flex-1">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Search</label>
        <div class="relative">
          <input
            v-model="filters.q"
            type="search"
            placeholder="Search by name, phone, school or group…"
            class="w-full h-10 pl-9 pr-4 rounded-lg border border-fb-line text-sm focus:outline-none focus:border-fb-blue"
            @keydown.enter="applyFilters"
          />
          <svg class="absolute left-3 top-2.5 text-fb-secondary" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
        </div>
      </div>
      <button
        v-if="!route.path.includes('debtors')"
        type="button"
        class="rounded-lg border border-fb-line px-4 py-2 text-sm text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
        @click="applyFilters"
      >
        Apply
      </button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!tableRows.length" class="p-8 text-center text-fb-icon">
        {{ rows.length ? 'No students match your search.' : 'No students' }}
      </div>
      <table v-else class="w-full text-base">
        <thead class="border-b border-fb-line bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Student</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Phone</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Status</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">School</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Group</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Branch</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Start date</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Next payment</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in tableRows"
            :key="row.id"
            class="cursor-pointer border-b border-fb-line"
            :class="row.isDebtor ? 'bg-red-50/70 hover:bg-red-100/70' : 'hover:bg-fb-hover/40'"
            @click="openDetailPanel(row.id)"
          >
            <td class="px-5 py-4">
              <div class="flex items-center gap-3">
                <img
                  v-if="row.photo"
                  :src="row.photo"
                  alt=""
                  class="h-9 w-9 shrink-0 rounded-full border border-fb-line object-cover"
                />
                <div
                  v-else
                  class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-fb-line bg-fb-canvas text-xs font-semibold text-fb-secondary"
                >
                  {{ row.initials }}
                </div>
                <span class="font-medium text-fb-text">{{ row.full_name }}</span>
              </div>
            </td>
            <td class="px-5 py-4 text-fb-secondary">
              <div>{{ row.phone }}</div>
              <div v-if="row.phone2" class="text-xs text-fb-icon">{{ row.phone2 }}</div>
            </td>
            <td class="px-5 py-4 text-fb-secondary">
              <span
                class="inline-block rounded-full px-2.5 py-0.5 text-xs font-medium"
                :class="statusBadgeClass(row.status)"
              >
                {{ row.statusText }}
              </span>
            </td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.school }}</td>
            <td class="px-5 py-4 text-fb-secondary">
              <button
                v-if="row.group_id"
                type="button"
                class="text-fb-blue hover:underline"
                @click.stop="goGroupFromTable(row.group_id)"
              >
                {{ row.group }}
              </button>
              <span v-else>{{ row.group }}</span>
            </td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.branch }}</td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.trialDate }}</td>
            <td class="px-5 py-4 text-fb-secondary">
              <div v-if="row.isDebtor" class="flex flex-col items-start gap-1">
                <span class="inline-flex items-center rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-700">
                  Просрочено на {{ row.overdueDays }} дн.
                </span>
                <span class="text-xs font-medium text-red-600">{{ row.nextPaymentDate }}</span>
              </div>
              <div v-else-if="row.nextPaymentDate !== '—'" class="flex items-center gap-1.5">
                <span class="text-sm font-medium text-fb-text">{{ row.nextPaymentDate }}</span>
              </div>
              <span v-else class="text-fb-secondary">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closePanel" />
      <div class="drawer-panel-fb max-w-lg">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-4">
          <h2 class="text-lg font-semibold text-fb-text">{{ panelTitle }}</h2>
          <button type="button" class="text-fb-icon hover:text-fb-secondary" @click="closePanel">✕</button>
        </div>

        <div v-if="panelLoading" class="flex-1 p-6 text-fb-secondary">Loading…</div>

        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitStudent">
          <div v-if="isReadOnly && detailStudent" class="flex-1 overflow-y-auto p-6">
            <div class="flex items-center gap-4">
              <img
                v-if="photoPreview"
                :src="photoPreview"
                alt=""
                class="h-24 w-24 shrink-0 rounded-full border border-fb-line object-cover"
              />
              <div
                v-else
                class="flex h-24 w-24 shrink-0 items-center justify-center rounded-full border border-fb-line bg-fb-canvas text-2xl font-semibold text-fb-secondary"
              >
                {{ initials(detailStudent.full_name) }}
              </div>
              <div class="min-w-0">
                <div class="truncate text-lg font-semibold text-fb-text">{{ detailStudent.full_name }}</div>
                <span
                  class="mt-1 inline-block rounded-full px-2.5 py-0.5 text-xs font-medium"
                  :class="statusBadgeClass(detailStudent.status)"
                >
                  {{ detailStudent.status_label }}
                </span>
                <div class="mt-1 text-sm text-fb-secondary">
                  <div>{{ detailStudent.phone }}</div>
                  <div v-if="detailStudent.phone2" class="text-xs text-fb-icon">Extra: {{ detailStudent.phone2 }}</div>
                </div>
              </div>
            </div>

            <dl class="mt-6 space-y-3 text-sm">
              <div v-if="detailStudent.address" class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">Address</dt>
                <dd class="text-right font-medium text-fb-text">{{ detailStudent.address }}</dd>
              </div>
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">School</dt>
                <dd class="text-right font-medium text-fb-text">{{ detailStudent.school || '-' }}</dd>
              </div>
              <div v-if="detailStudent.comment" class="flex items-start justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">Comment</dt>
                <dd class="text-right font-medium text-fb-text whitespace-pre-wrap max-w-[240px]">{{ detailStudent.comment }}</dd>
              </div>
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">Telegram (student)</dt>
                <dd class="text-right font-medium text-fb-text">{{ detailStudent.telegram || '-' }}</dd>
              </div>
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">Telegram (parents)</dt>
                <dd class="text-right font-medium" :class="detailStudent.parent_telegram ? 'text-fb-text' : 'text-fb-secondary'">
                  {{ detailStudent.parent_telegram || 'not set' }}
                </dd>
              </div>
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">Start date / Anchor date (Дата старта)</dt>
                <dd class="text-right font-medium text-fb-text">
                  {{ detailStudent.trial_date ? formatAddedDate(detailStudent.trial_date) : '-' }}
                </dd>
              </div>
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">Last payment (Последняя оплата)</dt>
                <dd class="text-right font-medium text-fb-text">
                  {{ detailStudent.last_payment_date ? formatAddedDate(detailStudent.last_payment_date) : 'Нет платежей' }}
                </dd>
              </div>
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">Next payment (Следующая оплата)</dt>
                <dd class="text-right flex items-center justify-end flex-wrap gap-2">
                  <span class="font-medium text-fb-text">
                    {{ detailStudent.next_payment_date ? formatAddedDate(detailStudent.next_payment_date) : '-' }}
                  </span>
                  <span
                    v-if="detailStudent.is_debtor"
                    class="inline-block rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700"
                  >
                    Просрочено на {{ detailStudent.overdue_days }} дн.
                  </span>
                  <span
                    v-else-if="detailStudent.next_payment_date"
                    class="inline-block rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700"
                  >
                    Оплачено
                  </span>
                  <button
                    type="button"
                    class="rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700"
                    @click="openAcceptPaymentModal"
                  >
                    + Оплатить
                  </button>
                </dd>
              </div>
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">Group</dt>
                <dd class="text-right">
                  <button
                    v-if="detailStudent.group_id"
                    type="button"
                    class="font-medium text-fb-blue hover:underline"
                    @click="goGroup(detailStudent)"
                  >
                    {{ detailStudent.group }}
                  </button>
                  <span v-else class="font-medium text-fb-text">-</span>
                </dd>
              </div>
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">Branch</dt>
                <dd class="text-right font-medium text-fb-text">{{ detailStudent.branch }}</dd>
              </div>
              <div class="flex items-center justify-between gap-4">
                <dt class="text-fb-secondary">Added</dt>
                <dd class="text-right font-medium text-fb-text">{{ formatAddedDate(detailStudent.created_at) }}</dd>
              </div>
            </dl>

            <div v-if="detailParentTgLink" class="mt-5 rounded-lg border border-fb-line bg-fb-canvas px-4 py-3 text-sm">
              <div class="font-medium text-fb-text">Parents invite link</div>
              <p class="mt-1 text-fb-secondary">
                Send this link to the parents. They open it, press Start, and the bot starts sending them notifications automatically.
              </p>
              <div class="mt-2 flex items-center gap-2">
                <a :href="detailParentTgLink" target="_blank" rel="noopener" class="break-all text-fb-blue hover:underline">
                  {{ detailParentTgLink }}
                </a>
                <button
                  type="button"
                  class="ml-auto shrink-0 rounded-lg border border-fb-line px-3 py-1 text-xs font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
                  @click="copyText(detailParentTgLink)"
                >
                  Copy
                </button>
              </div>
            </div>

            <!-- Payment History Section -->
            <div class="mt-5 rounded-xl border border-fb-line bg-fb-canvas p-4 text-sm">
              <div class="flex items-center justify-between border-b border-fb-line pb-3">
                <div class="flex items-center gap-2">
                  <span class="font-semibold text-fb-text">История оплат</span>
                  <span class="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-fb-secondary shadow-sm">
                    {{ studentPayments.length }}
                  </span>
                </div>
                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    class="rounded-lg border border-fb-line bg-white px-2.5 py-1 text-xs font-semibold text-fb-secondary hover:border-fb-blue hover:text-fb-blue shadow-sm transition-colors"
                    title="Ссылка на оплату Click / Payme / Uzum"
                    @click="openPaymentLinkModal(detailStudent)"
                  >
                    💳 Ссылка на оплату
                  </button>
                  <button
                    type="button"
                    class="rounded-lg bg-emerald-600 px-3 py-1 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700"
                    @click="openAcceptPaymentModal"
                  >
                    + Принять оплату
                  </button>
                </div>
              </div>

              <div v-if="paymentsLoading" class="py-6 text-center text-xs text-fb-secondary">
                Загрузка платежей…
              </div>
              <div v-else-if="!studentPayments.length" class="py-6 text-center text-xs text-fb-secondary">
                Оплат пока не зафиксировано
              </div>
              <div v-else class="mt-3 space-y-2 max-h-56 overflow-y-auto pr-1">
                <div
                  v-for="p in studentPayments"
                  :key="p.id"
                  class="flex items-center justify-between rounded-lg border border-fb-line bg-white p-3 shadow-sm"
                >
                  <div>
                    <div class="flex items-center gap-2">
                      <span class="font-semibold text-fb-blue">{{ p.amount.toLocaleString() }} UZS</span>
                      <span class="rounded bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-fb-blue">
                        {{ p.months_covered || 1 }} мес.
                      </span>
                    </div>
                    <div class="mt-1 text-xs text-fb-secondary">
                      {{ p.date }} • {{ p.method_pay || p.method }}
                      <span v-if="p.creator"> • Принял: {{ p.creator }}</span>
                    </div>
                    <div v-if="p.comment" class="mt-1 text-xs italic text-fb-secondary">
                      {{ p.comment }}
                    </div>
                  </div>
                  <button
                    type="button"
                    title="Печать квитанции"
                    class="ml-2 inline-flex items-center gap-1 rounded-lg border border-fb-line bg-fb-canvas/50 px-2.5 py-1 text-xs font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue transition-colors"
                    @click="printStudentPayment(p)"
                  >
                    <span>🖨️</span>
                    <span>Чек</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="flex-1 space-y-4 overflow-y-auto p-6">
            <div class="flex items-center gap-4">
              <img
                v-if="photoPreview"
                :src="photoPreview"
                alt=""
                class="h-20 w-20 shrink-0 rounded-full border border-fb-line object-cover"
              />
              <div
                v-else
                class="flex h-20 w-20 shrink-0 items-center justify-center rounded-full border border-fb-line bg-fb-canvas text-lg font-semibold text-fb-secondary"
              >
                {{ initials([form.first_name, form.last_name].filter(Boolean).join(' ')) }}
              </div>
              <div class="flex flex-col items-start gap-2">
                <input
                  ref="photoInput"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  class="hidden"
                  @change="onPhotoChange"
                />
                <button
                  type="button"
                  class="rounded-lg border border-fb-line px-3 py-1.5 text-sm font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
                  @click="triggerPhotoSelect"
                >
                  Upload photo
                </button>
                <button
                  v-if="photoPreview || photoMarkedRemove"
                  type="button"
                  class="text-xs text-fb-danger hover:underline"
                  @click="removePhoto"
                >
                  Remove photo
                </button>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">First name</label>
                <input
                  v-model="form.first_name"
                  type="text"
                  required
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">Last name</label>
                <input
                  v-model="form.last_name"
                  type="text"
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Phone</label>
              <input
                v-model="form.phone"
                type="tel"
                required
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Second phone (optional)</label>
              <input
                v-model="form.phone2"
                type="tel"
                placeholder="Additional phone number"
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">School</label>
              <input
                v-model="form.school"
                type="text"
                placeholder="e.g. School #45"
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Address</label>
              <input
                v-model="form.address"
                type="text"
                placeholder="e.g. Tashkent, Chilanzar"
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">Telegram (student)</label>
                <input
                  v-model="form.telegram"
                  type="text"
                  placeholder="@username"
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">Telegram (parents)</label>
                <input
                  v-model="form.parent_telegram"
                  type="text"
                  placeholder="@username or chat_id"
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Comments</label>
              <textarea
                v-model="form.comment"
                rows="2"
                placeholder="Add notes or comments about student..."
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              ></textarea>
            </div>

            <div v-if="detailParentTgLink" class="rounded-lg border border-fb-line bg-fb-canvas px-4 py-3 text-sm">
              <div class="font-medium text-fb-text">Parents invite link</div>
              <p class="mt-1 text-fb-secondary">
                Send this link to the parents. They open it, press Start, and the bot starts sending them notifications automatically.
              </p>
              <div class="mt-2 flex items-center gap-2">
                <a :href="detailParentTgLink" target="_blank" rel="noopener" class="break-all text-fb-blue hover:underline">
                  {{ detailParentTgLink }}
                </a>
                <button
                  type="button"
                  class="ml-auto shrink-0 rounded-lg border border-fb-line px-3 py-1 text-xs font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
                  @click="copyText(detailParentTgLink)"
                >
                  Copy
                </button>
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Branch</label>
              <select
                v-model="form.branch_id"
                :disabled="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option v-for="branch in branches" :key="branch.id" :value="branch.id">
                  {{ branch.name }}
                </option>
              </select>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Group</label>
              <select
                v-model="form.group_id"
                :disabled="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option value="">— No group —</option>
                <option v-for="group in filteredGroups" :key="group.id" :value="group.id">
                  {{ group.name }}
                </option>
              </select>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Status</label>
              <select
                v-model="form.status"
                :disabled="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option v-for="option in STATUS_OPTIONS" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </div>

            <div
              v-if="editingStudent?.status === 2 && form.status === 1"
              class="rounded-xl border border-emerald-200 bg-emerald-50 p-3"
            >
              <div class="text-xs font-semibold text-emerald-900">
                ⚡ Возобновление обучения из заморозки
              </div>
              <p class="mt-0.5 text-xs text-emerald-700">
                Укажите ниже дату возобновления — она станет новой датой расчета оплаты (Anchor date).
              </p>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Дата старта / число оплаты (Anchor date)</label>
              <input
                v-model="form.trial_date"
                type="date"
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div
              v-if="detailStudent?.group_id"
              class="rounded-lg border border-fb-line bg-fb-canvas px-4 py-3 text-sm"
            >
              <span class="text-fb-secondary">Group: </span>
              <span class="font-medium text-fb-text">{{ detailStudent.group }}</span>
              <button
                type="button"
                class="ml-3 text-fb-blue hover:underline"
                @click="goGroup(detailStudent)"
              >
                Open groups →
              </button>
            </div>

            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>

          <div class="flex flex-wrap gap-2 border-t border-fb-line px-6 py-4">
            <template v-if="isReadOnly">
              <button
                v-if="detailStudent?.status === 2"
                type="button"
                class="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
                @click="openUnfreezeModal(detailStudent)"
              >
                Возобновить обучение
              </button>
              <button
                type="button"
                class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white hover:opacity-90"
                @click="startEdit"
              >
                Edit
              </button>
              <button
                type="button"
                class="rounded-lg border border-red-300 px-5 py-2 text-sm font-medium text-fb-danger hover:bg-red-50 disabled:opacity-50"
                :disabled="deleting"
                @click="deleteStudent"
              >
                Delete
              </button>
            </template>
            <template v-else>
              <button
                type="submit"
                class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                :disabled="saving"
              >
                {{ saving ? 'Saving…' : editingStudent ? 'Save' : 'Create' }}
              </button>
            </template>
            <button
              type="button"
              class="rounded-lg border border-fb-line px-5 py-2 text-sm font-medium text-fb-secondary"
              @click="closePanel"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Unfreeze modal -->
    <div v-if="showUnfreezeModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="fixed inset-0 bg-black/40" @click="showUnfreezeModal = false" />
      <div class="relative w-full max-w-md rounded-2xl border border-fb-line bg-fb-card p-6 shadow-xl">
        <div class="flex items-center justify-between border-b border-fb-line pb-3">
          <h3 class="text-lg font-semibold text-fb-text">Возобновление обучения</h3>
          <button
            type="button"
            class="text-fb-icon hover:text-fb-secondary"
            @click="showUnfreezeModal = false"
          >
            ✕
          </button>
        </div>

        <div class="mt-4 space-y-4">
          <p class="text-sm text-fb-secondary">
            Ученик <strong class="text-fb-text">{{ unfreezeStudent?.full_name }}</strong> возвращается из заморозки в статус «Обучается».
          </p>
          <div class="rounded-lg bg-fb-canvas p-3 text-xs text-fb-secondary">
            Укажите дату возобновления занятий. Это число месяца станет новой <strong>якорной датой</strong> для расчета последующих платежей.
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-text">
              Дата расчета оплаты и возобновления:
            </label>
            <input
              v-model="unfreezeDate"
              type="date"
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            />
          </div>

          <p v-if="unfreezeError" class="text-xs text-fb-danger">{{ unfreezeError }}</p>

          <div class="flex justify-end gap-2 pt-2">
            <button
              type="button"
              class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:bg-fb-canvas"
              @click="showUnfreezeModal = false"
            >
              Отмена
            </button>
            <button
              type="button"
              class="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              :disabled="unfreezeSaving"
              @click="confirmUnfreeze"
            >
              {{ unfreezeSaving ? 'Сохранение…' : 'Подтвердить и возобновить' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Принять оплату -->
    <div v-if="showPayModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="fixed inset-0 bg-black/40" @click="showPayModal = false" />
      <div class="relative w-full max-w-md rounded-2xl border border-fb-line bg-fb-card p-6 shadow-2xl">
        <div class="flex items-center justify-between border-b border-fb-line pb-3">
          <div>
            <h3 class="text-base font-semibold text-fb-text">Принять оплату</h3>
            <p class="text-xs text-fb-secondary mt-0.5">{{ detailStudent?.full_name }}</p>
          </div>
          <button type="button" class="text-fb-secondary hover:text-fb-text" @click="showPayModal = false">✕</button>
        </div>

        <form class="mt-4 space-y-4" @submit.prevent="submitPayment">
          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">Оплачено месяцев (Период)</label>
            <input
              v-model.number="payForm.months_covered"
              type="number"
              min="1"
              required
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              @input="onPayMonthsChange"
            />
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">Сумма к оплате (UZS)</label>
            <input
              v-model.number="payForm.amount"
              type="number"
              required
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm font-semibold focus:border-fb-blue focus:outline-none"
            />
            <p v-if="detailStudent?.course_price" class="mt-1 text-[11px] text-fb-secondary">
              Стоимость курса: {{ detailStudent.course_price.toLocaleString() }} UZS / мес.
            </p>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">Способ оплаты</label>
            <select
              v-model="payForm.method"
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            >
              <option value="cash">Наличные (Cash)</option>
              <option value="card">Карта (Card)</option>
              <option value="transfer">Перевод (Transfer)</option>
            </select>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">Комментарий / Примечание</label>
            <textarea
              v-model="payForm.comment"
              rows="2"
              placeholder="Опционально..."
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
              {{ paySaving ? 'Проведение…' : 'Провести оплату' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <ImportCsvModal
      v-model:open="showImportModal"
      title="Импорт учеников"
      upload-url="/students/import"
      template-filename="students-import-template.csv"
      :template-header="['first_name', 'last_name', 'phone', 'school', 'branch', 'group', 'status', 'parent_telegram']"
      :template-example="['Ali', 'Valiyev', '998901234567', 'School #5', 'Main branch', '', 'Active', '@parent_tg']"
      columns-help="Поддерживаются файлы Excel (.xlsx, .xls) и CSV. Обязательные данные: имя и номер телефона. Программа автоматически разделит ФИО, очистит телефон и сопоставит группы."
      @imported="loadStudents"
    />

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
