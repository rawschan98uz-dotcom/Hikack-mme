<script setup lang="ts">
import { todayIso } from '../utils/dates';
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { formatSum } from '../utils/wallet';
import PaymentPreviewHint from '../components/PaymentPreviewHint.vue';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';
import { downloadCsv } from '../utils/csvExport';
import ImportCsvModal from '../components/ImportCsvModal.vue';
import ReceiptModal, { type ReceiptPayment } from '../components/ReceiptModal.vue';
import PaymentLinkModal, { type StudentPaymentLinkTarget } from '../components/PaymentLinkModal.vue';
import {
  groupRoute,
  hasCreateFlag,
  routeWithoutCreate,
  studentRoute,
} from '../utils/crossLinks';
import { onCardsReturn, pathWithoutCards } from '../utils/cardStack';
import { t, type MessageKey } from '../i18n';
import { payMethodLabel, studentStatusLabel } from '../i18n/labels';
import { PHONE_OWNER_BUTTONS, PHONE_OWNERS, presetLabel } from '../i18n/presets';
import { toast } from '../ui/feedback';
import { apiErrorMessage } from '../utils/apiError';

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
  phone2_owner?: string;
  address?: string;
  comment?: string;
  level?: string;
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
  status: number;
  status_label: string;
  branch_id: number;
  branch: string;
  group_id: number | null;
  group: string | null;
  group_teacher?: string;
  course_price?: number;
  course_name?: string;
  /** Копилка: money waiting to close the next month, and the month price it is counted against. */
  wallet?: number | null;
  month_price?: number | null;
  wallet_missing?: number | null;
  /** Exact debt: every owed month at its own price. */
  debt_months?: number | null;
  debt_amount?: number | null;
  /** The student's months ("строки"): charged, paid, left. Newest first. */
  charges?: StudentCharge[] | null;
  created_at: string;
}

interface StudentCharge {
  id: number;
  period_start: string;
  period_end: string;
  group: string;
  price: number;
  discount: number;
  amount: number;
  paid: number;
  left: number;
  paid_at: string | null;
  state: 'paid' | 'partial' | 'unpaid' | 'ahead' | 'written_off';
}

const CHARGE_STATE: Record<StudentCharge['state'], { label: MessageKey; cls: string }> = {
  paid: { label: 'months.state.paid', cls: 'bg-emerald-100 text-emerald-700' },
  partial: { label: 'months.state.partial', cls: 'bg-amber-100 text-amber-800' },
  unpaid: { label: 'months.state.unpaid', cls: 'bg-red-100 text-red-700' },
  ahead: { label: 'months.state.ahead', cls: 'bg-sky-100 text-sky-800' },
  written_off: { label: 'months.state.writtenOff', cls: 'bg-slate-200 text-slate-700' },
};

interface StudentPayment {
  id: number;
  date: string;
  amount: number;
  /** 'refund' = money given back: shown red with a minus */
  transaction_type?: string;
  discount_amount?: number;
  months_covered: number;
  method: string;
  method_pay: string;
  comment: string;
  creator: string;
}

const STATUS_OPTIONS = [
  { value: 1, label: 'studentStatus.1' as MessageKey },
  { value: 2, label: 'studentStatus.2' as MessageKey },
  { value: 7, label: 'studentStatus.7' as MessageKey },
  { value: 8, label: 'studentStatus.8' as MessageKey },
  { value: 9, label: 'studentStatus.9' as MessageKey },
] as const;

// Card mode: the page shows only this student's card, on top of another page (see utils/cardStack)
const props = defineProps<{ cardId?: number; cardEdit?: boolean; cardLevel?: number }>();
const emit = defineEmits<{ close: [] }>();
const isCard = props.cardId != null;

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const rows = ref<StudentRow[]>([]);
const branches = ref<Branch[]>([]);
const groups = ref<GroupOption[]>([]);
const loading = ref(true);
const saving = ref(false);
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
const unfreezeDate = ref(todayIso());
const unfreezeSaving = ref(false);
const unfreezeError = ref('');

const studentPayments = ref<StudentPayment[]>([]);
const paymentsLoading = ref(false);
const showPayModal = ref(false);
const payForm = reactive({
  amount: 0,
  months_covered: 1,
  /** Discount as a sum, by hand, empty when there is none (owner, 2026-09-28) */
  discount: '' as number | '',
  payment_date: todayIso(),
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
    student_name: detailStudent.value?.full_name || t('months.student'),
    amount: p.amount,
    months_covered: p.months_covered ?? 1,
    method: p.method,
    method_pay: p.method_pay,
    teacher: detailStudent.value?.group_teacher || '',
    comment: p.comment,
    creator: p.creator,
  };
  showReceiptModal.value = true;
}

async function loadStudentPayments(studentId: number) {
  if (!canSeeMoney.value) {
    studentPayments.value = [];
    return;
  }
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
  payForm.discount = '';
  payForm.payment_date = todayIso();
  const coursePrice = detailStudent.value.course_price || 0;
  // A debtor: the sum of the debt is offered first; otherwise one month
  payForm.amount = detailStudent.value.debt_amount || coursePrice || 0;
  payForm.method = 'cash';
  payForm.comment = '';
  payError.value = '';
  showPayModal.value = true;
}

function onPayMonthsChange() {
  if (payForm.months_covered < 1) payForm.months_covered = 1;
  const coursePrice = detailStudent.value?.course_price || 0;
  if (coursePrice) {
    payForm.amount = Math.max(0, coursePrice * payForm.months_covered - (Number(payForm.discount) || 0));
  }
}

async function submitPayment() {
  if (!detailStudent.value) return;
  if (!Number.isInteger(payForm.amount) || payForm.amount <= 0) {
    payError.value = t('finance.amountPositive');
    return;
  }
  if (payForm.discount !== '' && (!Number.isInteger(payForm.discount) || payForm.discount < 0)) {
    payError.value = t('payments.discountInvalid');
    return;
  }
  if (!payForm.payment_date || payForm.payment_date > todayIso()) {
    payError.value = t('payments.dateNotFuture');
    return;
  }
  paySaving.value = true;
  payError.value = '';
  try {
    await client.post('/replenishments', {
      student_id: detailStudent.value.id,
      amount: payForm.amount,
      discount_amount: payForm.discount === '' ? 0 : payForm.discount,
      payment_date: payForm.payment_date,
      months_covered: payForm.months_covered || 1,
      method: payForm.method,
      comment: payForm.comment.trim(),
    });
    showPayModal.value = false;
    toast.success(t('payments.received', { amount: formatSum(payForm.amount), name: detailStudent.value.full_name }));
    const studentId = detailStudent.value.id;
    const [{ data }] = await Promise.all([
      client.get<ApiEnvelope<StudentRow>>(`/students/${studentId}`),
      loadStudentPayments(studentId),
      loadStudents(),
    ]);
    detailStudent.value = data.data;
    fillForm(data.data);
  } catch (err: unknown) {
    payError.value = apiErrorMessage(err, t('payments.saveFailed'));
  } finally {
    paySaving.value = false;
  }
}

function openUnfreezeModal(student: StudentRow) {
  unfreezeStudent.value = student;
  unfreezeDate.value = todayIso();
  unfreezeError.value = '';
  showUnfreezeModal.value = true;
}

async function confirmUnfreeze() {
  if (!unfreezeStudent.value) return;
  if (!unfreezeDate.value) {
    unfreezeError.value = t('students.resumeDateRequired');
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
    toast.success(t('students.resumed', { name: unfreezeStudent.value.full_name }));
    if (detailStudent.value && detailStudent.value.id === unfreezeStudent.value.id) {
      detailStudent.value = data.data;
      fillForm(data.data);
    }
    await loadStudents();
  } catch (error) {
    unfreezeError.value = apiErrorMessage(error, t('students.resumeFailed'));
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

function getTodayDateString(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

const form = reactive({
  first_name: '',
  last_name: '',
  phone: '',
  phone2: '',
  phone2_owner: '',
  address: '',
  comment: '',
  level: '',
  school: '',
  telegram: '',
  parent_telegram: '',
  status: 1,
  trial_date: getTodayDateString(),
  branch_id: 0,
  group_id: '' as number | '',
});

const title = computed(() => {
  if (route.path.includes('debtors')) return t('nav.debtors');
  if (route.query.statuses === '1') return t('students.titleStudying');
  if (route.query.statuses === '2') return t('students.titleFrozen');
  if (route.query.statuses === '7') return t('students.titleLeftTrial');
  if (route.query.statuses === '8') return t('students.titleLeft');
  if (route.query.statuses === '9') return t('students.titleGraduated');
  if (route.query.q) return t('students.titleSearch', { q: String(route.query.q) });
  return t('nav.students');
});

const panelTitle = computed(() => {
  if (editingStudent.value) return t('students.editTitle');
  if (detailStudent.value) return t('students.detailTitle');
  return t('layout.addStudent');
});

const isReadOnly = computed(() => Boolean(detailStudent.value && !editingStudent.value));
const canExportStudents = computed(() => auth.can(PERM.STUDENTS_VIEW));
const canImportStudents = computed(() => auth.can(PERM.STUDENTS_WRITE));
const canWriteStudents = computed(() => auth.can(PERM.STUDENTS_WRITE));
// Teachers never see money fields — backend returns them as null (strip_for_teacher).
const canSeeMoney = computed(() => auth.role !== 'teacher');
const canAcceptPayment = computed(() => auth.can(PERM.PAYMENTS_WRITE));

function exportCsv() {
  downloadCsv(
    'students.csv',
    [
      t('common.fullName'), t('common.phone'), t('leads.phone2'), t('leads.phone2Owner'), t('settings.address'),
      t('common.comment'), t('common.status'), t('students.startDate'), t('students.nextPayment'),
      t('students.paymentStatus'), t('import.school'), t('schedule.group'), t('common.branch'), t('students.telegramParents'),
    ],
    rows.value.map((row) => [
      row.full_name,
      row.phone,
      row.phone2 || '',
      presetLabel(row.phone2_owner),
      row.address || '',
      row.comment || '',
      studentStatusLabel(row.status, row.status_label),
      row.trial_date || '',
      row.next_payment_date || '',
      row.is_debtor ? t('students.overdueDays', { count: row.overdue_days || 0 }) : t('students.paymentOk'),
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
    const ownerMatch = row.phone2_owner?.toLowerCase().includes(q);
    const schoolMatch = row.school?.toLowerCase().includes(q);
    const groupMatch = row.group?.toLowerCase().includes(q);
    return Boolean(nameMatch || phoneMatch || ownerMatch || schoolMatch || groupMatch);
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
    phone2_owner: row.phone2_owner || '',
    status: row.status,
    statusText: studentStatusLabel(row.status, row.status_label),
    level: row.level || '',
    school: row.school || '—',
    group: row.group ?? '—',
    group_id: row.group_id,
    branch: row.branch,
    trialDate: row.trial_date ? formatAddedDate(row.trial_date) : '—',
    nextPaymentDate: row.next_payment_date ? formatAddedDate(row.next_payment_date) : '—',
    isDebtor: Boolean(row.is_debtor),
    overdueDays: row.overdue_days || 0,
    debtAmount: row.debt_amount || 0,
    isFrozen: row.status === 2,
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
  form.phone2_owner = '';
  form.address = '';
  form.comment = '';
  form.level = '';
  form.school = '';
  form.telegram = '';
  form.parent_telegram = '';
  form.status = 1;
  form.trial_date = getTodayDateString();
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
  form.phone2_owner = student.phone2_owner ?? '';
  form.address = student.address ?? '';
  form.comment = student.comment ?? '';
  form.level = student.level ?? '';
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

/** The same card again, without the "Loading…" blink: after a return from a card above. */
async function refreshDetail() {
  const id = detailStudent.value?.id;
  // An edit form in progress is not touched
  if (!id || editingStudent.value) return;
  const [{ data }] = await Promise.all([
    client.get<ApiEnvelope<StudentRow>>(`/students/${id}`),
    loadStudentPayments(id),
  ]);
  if (detailStudent.value?.id !== id || editingStudent.value) return;
  detailStudent.value = data.data;
  fillForm(data.data);
}

function openCard(studentId: number) {
  router.push(studentRoute(studentId));
}

function closePanel() {
  if (isCard) {
    emit('close');
    return;
  }
  showPanel.value = false;
  resetForm();
}

function parentTgLink(code: string | null | undefined) {
  if (!tgBotUsername.value || !code) return '';
  return `https://t.me/${tgBotUsername.value}?start=${code}`;
}

const detailParentTgLink = computed(() => parentTgLink(detailStudent.value?.telegram_code));

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(t('common.copied'));
  } catch {
    const area = document.createElement('textarea');
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    document.body.removeChild(area);
    toast.success(t('common.copied'));
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

async function loadStudents(quiet = false) {
  if (isCard) return;
  // quiet: the table stays in place (and keeps its scroll) while fresh rows arrive
  if (!quiet) loading.value = true;
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
    formError.value = t('students.photoType');
    return;
  }
  if (file.size > MAX_PHOTO_MB * 1024 * 1024) {
    formError.value = t('students.photoSize', { mb: MAX_PHOTO_MB });
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
    phone2_owner: form.phone2_owner.trim(),
    address: form.address.trim(),
    comment: form.comment.trim(),
    level: form.level.trim(),
    school: form.school.trim(),
    telegram: form.telegram.trim(),
    parent_telegram: form.parent_telegram.trim(),
    status: form.status,
    trial_date: form.trial_date || null,
    branch_id: form.branch_id,
    group_id: form.group_id === '' ? null : form.group_id,
  };
}

function cleanPhoneDigits(raw: string): string {
  let d = raw.replace(/\D/g, '');
  if (d.startsWith('998') && d.length >= 10) {
    d = d.slice(3);
  }
  return d;
}

async function submitStudent() {
  formError.value = '';
  if (!form.first_name.trim()) {
    formError.value = t('errors.enterName');
    return;
  }
  if (!form.phone.trim()) {
    formError.value = t('errors.enterPhone');
    return;
  }
  const digits = cleanPhoneDigits(form.phone);
  if (digits.length < 9) {
    formError.value = t('errors.phoneMin9');
    return;
  }
  if (form.phone2.trim()) {
    const digits2 = cleanPhoneDigits(form.phone2);
    if (digits2.length < 9) {
      formError.value = t('errors.secondPhoneMin9');
      return;
    }
  }
  if (!form.branch_id) {
    formError.value = t('groups.branchRequired');
    return;
  }
  if (!form.trial_date) {
    formError.value = t('leads.startDateRequired');
    return;
  }

  saving.value = true;
  try {
    const payload = buildPayload();
    const wasEditing = Boolean(editingStudent.value);
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
    toast.success(wasEditing ? t('toast.saved') : t('students.created'));
    await loadStudents();
  } catch (error) {
    formError.value = apiErrorMessage(error, t('errors.saveFailed'));
  } finally {
    saving.value = false;
  }
}

function goGroup(student: StudentRow | { group_id: number | null }) {
  if (!student.group_id) return;
  router.push(groupRoute(student.group_id));
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

if (!isCard) {
  watch(
    () => pathWithoutCards(route),
    async () => {
      syncFiltersFromRoute();
      await loadStudents();
      maybeCreateFromRoute();
    },
  );
}

// The cards above are closed: show fresh data (the group could change)
onCardsReturn(props.cardLevel ?? -1, () => {
  if (isCard) void refreshDetail();
  else void loadStudents(true);
});

watch(
  () => form.status,
  (newStatus, oldStatus) => {
    if (editingStudent.value && editingStudent.value.status === 2 && newStatus === 1 && oldStatus !== 1) {
      if (!form.trial_date || form.trial_date === editingStudent.value.trial_date?.slice(0, 10)) {
        form.trial_date = todayIso();
      }
    }
  },
);

let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
watch(
  () => filters.q,
  (newQ) => {
    if (isCard) return;
    if (newQ.trim() === String(route.query.q ?? '').trim()) return;
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      applyFilters();
    }, 450);
  },
);

onMounted(async () => {
  if (isCard) {
    loadTelegramConfig();
    await Promise.all([loadOptions(), openDetailPanel(props.cardId as number)]);
    // straight into the edit form (e.g. from a reminder "put the student into a group")
    if (props.cardEdit && canWriteStudents.value) startEdit();
    return;
  }
  syncFiltersFromRoute();
  loadTelegramConfig();
  try {
    await Promise.all([loadOptions(), loadStudents()]);
    maybeCreateFromRoute();
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="space-y-4">
    <template v-if="!isCard">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-baseline gap-3">
        <h1 class="text-xl font-semibold text-fb-text">{{ title }}</h1>
        <span v-if="!loading" class="text-sm text-fb-secondary">
          {{ t('archive.quantity', { count: tableRows.length }) }}<span v-if="filters.q.trim() && rows.length !== tableRows.length"> ({{ t('archive.ofTotal', { total: rows.length }) }})</span>
        </span>
      </div>
      <div class="flex flex-wrap gap-2">
        <button
          v-if="canExportStudents"
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
          @click="exportCsv"
        >
          {{ t('common.export') }}
        </button>
        <button
          v-if="canImportStudents"
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
          @click="showImportModal = true"
        >
          {{ t('common.import') }}
        </button>
        <button
          v-if="canWriteStudents"
          type="button"
          class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:bg-fb-blue-dark"
          @click="openCreatePanel"
        >
          + {{ t('layout.addStudent') }}
        </button>
      </div>
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div v-if="!route.path.includes('debtors')">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('common.branch') }}</label>
        <select
          v-model="filters.branch_id"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm"
        >
          <option value="">{{ t('common.allBranches') }}</option>
          <option v-for="branch in branches" :key="branch.id" :value="String(branch.id)">
            {{ branch.name }}
          </option>
        </select>
      </div>
      <div v-if="!route.path.includes('debtors')">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('schedule.group') }}</label>
        <select
          v-model="filters.group_id"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm"
        >
          <option value="">{{ t('teacherAtt.allGroups') }}</option>
          <option v-for="group in groups" :key="group.id" :value="String(group.id)">
            {{ group.name }}
          </option>
        </select>
      </div>
      <div v-if="!route.path.includes('debtors')">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('common.status') }}</label>
        <select
          v-model="filters.status"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm"
        >
          <option value="">{{ t('rating.allStatuses') }}</option>
          <option v-for="option in STATUS_OPTIONS" :key="option.value" :value="String(option.value)">
            {{ t(option.label) }}
          </option>
        </select>
      </div>
      <div class="min-w-[240px] flex-1">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('common.search') }}</label>
        <div class="relative">
          <input
            v-model="filters.q"
            type="search"
            :placeholder="t('students.searchPlaceholder')"
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
        {{ t('common.apply') }}
      </button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">{{ t('common.loading') }}</div>
      <div v-else-if="!tableRows.length" class="p-8 text-center text-fb-icon">
        {{ rows.length ? t('common.nothingFound') : t('students.empty') }}
      </div>
      <table v-else class="w-full text-base">
        <thead class="border-b border-fb-line bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('months.student') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.phone') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.status') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('import.school') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('schedule.group') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.branch') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('students.startDate') }}</th>
            <th v-if="canSeeMoney" class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('students.nextPayment') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in tableRows"
            :key="row.id"
            class="cursor-pointer border-b border-fb-line"
            :class="canSeeMoney && row.isDebtor ? 'bg-red-50/70 hover:bg-red-100/70' : 'hover:bg-fb-hover/40'"
            @click="openCard(row.id)"
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
                <div>
                  <span class="font-medium text-fb-text">{{ row.full_name }}</span>
                  <div v-if="row.level" class="mt-0.5">
                    <span class="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-800 border border-emerald-200">
                      🎯 {{ presetLabel(row.level) }}
                    </span>
                  </div>
                </div>
              </div>
            </td>
            <td class="px-5 py-4 text-fb-secondary">
              <div>{{ row.phone }}</div>
              <div v-if="row.phone2" class="text-xs text-fb-icon flex items-center gap-1 mt-0.5">
                <span v-if="row.phone2_owner" class="font-medium text-fb-secondary">({{ presetLabel(row.phone2_owner) }})</span>
                <span>{{ row.phone2 }}</span>
              </div>
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
            <td v-if="canSeeMoney" class="px-5 py-4 text-fb-secondary">
              <div v-if="row.isDebtor" class="flex flex-col items-start gap-1">
                <span class="inline-flex items-center rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-700">
                  {{ t('students.overdueDays', { count: row.overdueDays }) }}
                </span>
                <span v-if="row.debtAmount" class="text-xs font-semibold text-red-700">
                  {{ t('students.debtAmount', { amount: formatSum(row.debtAmount) }) }}
                </span>
                <span
                  v-if="row.isFrozen"
                  class="inline-flex items-center rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-700"
                  :title="t('students.frozenHint')"
                >
                  {{ t('students.frozen') }}
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
    </template>

    <div v-if="showPanel" class="drawer-wide-shell">
      <div class="drawer-panel-fb">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-4">
          <h2 class="text-lg font-semibold text-fb-text">{{ panelTitle }}</h2>
          <button type="button" class="text-fb-icon hover:text-fb-secondary" :aria-label="t('common.close')" @click="closePanel">✕</button>
        </div>

        <div v-if="panelLoading" class="flex-1 p-6 text-fb-secondary">{{ t('common.loading') }}</div>

        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitStudent">
          <div v-if="isReadOnly && detailStudent" class="flex-1 overflow-y-auto p-6">
            <div class="flex flex-wrap items-center gap-5">
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
                <div class="truncate text-2xl font-semibold text-fb-text">{{ detailStudent.full_name }}</div>
                <span
                  class="mt-1 inline-block rounded-full px-2.5 py-0.5 text-xs font-medium"
                  :class="statusBadgeClass(detailStudent.status)"
                >
                  {{ studentStatusLabel(detailStudent.status, detailStudent.status_label) }}
                </span>
                <div class="mt-1 text-base text-fb-text">
                  <span class="font-semibold">{{ detailStudent.phone }}</span>
                  <span v-if="detailStudent.phone2" class="ml-3 text-sm text-fb-secondary">
                    {{ detailStudent.phone2_owner ? `${presetLabel(detailStudent.phone2_owner)}: ` : `${t('leads.phone2')}: ` }}{{ detailStudent.phone2 }}
                  </span>
                </div>
              </div>
            </div>

            <!-- Key facts at a glance -->
            <div class="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
              <div v-if="canSeeMoney" class="fact-tile-fb" :class="detailStudent.is_debtor ? '!border-red-200 !bg-red-50' : ''">
                <div class="fact-label">{{ t('groups.debt') }}</div>
                <div v-if="detailStudent.debt_amount" class="fact-value !text-red-700">
                  {{ t('common.sumAmount', { amount: formatSum(detailStudent.debt_amount) }) }}
                </div>
                <div v-else-if="detailStudent.is_debtor" class="fact-value !text-red-700">{{ t('common.yes') }}</div>
                <div v-else class="fact-value !text-emerald-700">{{ t('common.no') }}</div>
                <div v-if="detailStudent.debt_amount" class="text-xs text-fb-secondary">
                  {{ t('students.unpaidMonths', { count: detailStudent.debt_months ?? 0 }) }}
                </div>
                <div v-else-if="detailStudent.is_debtor" class="text-xs text-fb-secondary">
                  {{ t('students.debtUnknown') }}
                </div>
              </div>
              <div v-if="canSeeMoney" class="fact-tile-fb">
                <div class="fact-label">{{ t('students.nextPayment') }}</div>
                <div class="fact-value">
                  {{ detailStudent.next_payment_date ? formatAddedDate(detailStudent.next_payment_date) : '—' }}
                </div>
                <div class="mt-1 flex flex-wrap items-center gap-2">
                  <span
                    v-if="detailStudent.is_debtor"
                    class="inline-block rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700"
                  >
                    {{ t('students.overdueDays', { count: detailStudent.overdue_days ?? 0 }) }}<template v-if="detailStudent.status === 2"> ({{ t('students.frozen') }})</template>
                  </span>
                  <span
                    v-else-if="detailStudent.next_payment_date"
                    class="inline-block rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700"
                  >
                    {{ t('months.state.paid') }}
                  </span>
                  <button
                    v-if="canAcceptPayment"
                    type="button"
                    class="rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700"
                    @click="openAcceptPaymentModal"
                  >
                    + {{ t('students.pay') }}
                  </button>
                </div>
              </div>
              <div v-if="canSeeMoney" class="fact-tile-fb">
                <div class="fact-label">{{ t('students.lastPayment') }}</div>
                <div class="fact-value">
                  {{ detailStudent.last_payment_date ? formatAddedDate(detailStudent.last_payment_date) : t('students.noPaymentsYet') }}
                </div>
                <div v-if="detailStudent.wallet" class="text-xs text-amber-700">
                  {{ t('students.wallet', { amount: formatSum(detailStudent.wallet) }) }}<template v-if="detailStudent.wallet_missing">
                    · {{ t('students.walletMissing', { amount: formatSum(detailStudent.wallet_missing) }) }}</template>
                </div>
              </div>
              <div class="fact-tile-fb">
                <div class="fact-label">{{ t('schedule.group') }}</div>
                <div class="fact-value">
                  <button
                    v-if="detailStudent.group_id"
                    type="button"
                    class="text-left text-fb-blue hover:underline"
                    @click="goGroup(detailStudent)"
                  >
                    {{ detailStudent.group }}
                  </button>
                  <span v-else>—</span>
                </div>
                <div v-if="detailStudent.group_teacher" class="text-xs text-fb-secondary">
                  {{ t('students.teacherIs', { name: detailStudent.group_teacher }) }}
                </div>
              </div>
              <div class="fact-tile-fb">
                <div class="fact-label">{{ t('schedule.course') }}</div>
                <div class="fact-value">{{ detailStudent.course_name || '—' }}</div>
                <div v-if="canSeeMoney && detailStudent.course_price" class="text-xs text-fb-secondary">
                  {{ t('payments.perMonth', { amount: formatSum(detailStudent.course_price) }) }}
                </div>
              </div>
              <div class="fact-tile-fb">
                <div class="fact-label">{{ t('students.startDate') }}</div>
                <div class="fact-value">
                  {{ detailStudent.trial_date ? formatAddedDate(detailStudent.trial_date) : '—' }}
                </div>
                <div class="text-xs text-fb-secondary">{{ t('students.startDateHint') }}</div>
              </div>
            </div>

            <div class="mt-6 grid items-start gap-6" :class="canSeeMoney ? 'xl:grid-cols-3' : ''">
            <div>
            <div class="mb-2 text-base font-semibold text-fb-text">{{ t('students.info') }}</div>
            <dl class="space-y-3 text-sm">
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">{{ t('common.branch') }}</dt>
                <dd class="text-right font-medium text-fb-text">{{ detailStudent.branch }}</dd>
              </div>
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">{{ t('settings.address') }}</dt>
                <dd class="text-right font-medium text-fb-text">{{ detailStudent.address || '-' }}</dd>
              </div>
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">{{ t('import.school') }}</dt>
                <dd class="text-right font-medium text-fb-text">{{ detailStudent.school || '-' }}</dd>
              </div>
              <div v-if="detailStudent.level" class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">{{ t('leads.level') }}</dt>
                <dd class="text-right font-medium text-fb-text">{{ presetLabel(detailStudent.level) }}</dd>
              </div>
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">{{ t('students.telegramStudent') }}</dt>
                <dd class="text-right font-medium text-fb-text">{{ detailStudent.telegram || '-' }}</dd>
              </div>
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">{{ t('students.telegramParents') }}</dt>
                <dd class="text-right font-medium" :class="detailStudent.parent_telegram ? 'text-fb-text' : 'text-fb-secondary'">
                  {{ detailStudent.parent_telegram || t('common.notSet') }}
                </dd>
              </div>
              <div class="flex items-center justify-between gap-4 border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">{{ t('students.added') }}</dt>
                <dd class="text-right font-medium text-fb-text">{{ formatAddedDate(detailStudent.created_at) }}</dd>
              </div>
              <div v-if="detailStudent.comment" class="border-b border-fb-line pb-2">
                <dt class="text-fb-secondary">{{ t('common.comment') }}</dt>
                <dd class="mt-1 whitespace-pre-wrap font-medium text-fb-text">{{ detailStudent.comment }}</dd>
              </div>
            </dl>

            <div v-if="detailParentTgLink" class="mt-5 rounded-lg border border-fb-line bg-fb-canvas px-4 py-3 text-sm">
              <div class="font-medium text-fb-text">{{ t('students.parentsLink') }}</div>
              <p class="mt-1 text-fb-secondary">
                {{ t('students.parentsLinkHint') }}
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
                  {{ t('common.copy') }}
                </button>
              </div>
            </div>
            </div>

            <!-- The student's months: one line per month, its sum never changes -->
            <div v-if="canSeeMoney" class="rounded-xl border border-fb-line bg-fb-canvas p-4 text-sm">
              <div class="flex items-center gap-2 border-b border-fb-line pb-3">
                <span class="font-semibold text-fb-text">{{ t('students.months') }}</span>
                <span class="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-fb-secondary shadow-sm">
                  {{ detailStudent.charges?.length || 0 }}
                </span>
              </div>
              <div v-if="!detailStudent.charges?.length" class="py-6 text-center text-xs text-fb-secondary">
                {{ t('students.monthsEmpty') }}
              </div>
              <div v-else class="max-h-[55vh] overflow-y-auto">
                <table class="w-full text-left">
                  <thead class="text-xs text-fb-secondary">
                    <tr>
                      <th class="py-2 pr-2 font-medium">{{ t('common.month') }}</th>
                      <th class="py-2 pr-2 text-right font-medium">{{ t('months.charged') }}</th>
                      <th class="py-2 pr-2 text-right font-medium">{{ t('months.paid') }}</th>
                      <th class="py-2 text-right font-medium">{{ t('months.left') }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="line in detailStudent.charges" :key="line.id" class="border-t border-fb-line">
                      <td class="py-2 pr-2 text-fb-text">
                        <div class="whitespace-nowrap">
                          {{ formatAddedDate(line.period_start) }} — {{ formatAddedDate(line.period_end) }}
                        </div>
                        <span class="mt-1 inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium" :class="CHARGE_STATE[line.state].cls">
                          {{ t(CHARGE_STATE[line.state].label) }}
                        </span>
                      </td>
                      <td class="py-2 pr-2 text-right align-top text-fb-text">{{ formatSum(line.amount) }}</td>
                      <td class="py-2 pr-2 text-right align-top text-fb-text">{{ formatSum(line.paid) }}</td>
                      <td class="py-2 text-right align-top font-semibold" :class="line.left ? 'text-red-700' : 'text-fb-secondary'">
                        {{ formatSum(line.left) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p class="mt-2 text-xs text-fb-secondary">
                {{ t('students.monthsHint') }}
              </p>
            </div>

            <!-- Payment History Section -->
            <div v-if="canSeeMoney" class="rounded-xl border border-fb-line bg-fb-canvas p-4 text-sm">
              <div class="flex flex-wrap items-center justify-between gap-2 border-b border-fb-line pb-3">
                <div class="flex items-center gap-2">
                  <span class="whitespace-nowrap font-semibold text-fb-text">{{ t('students.paymentHistory') }}</span>
                  <span class="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-fb-secondary shadow-sm">
                    {{ studentPayments.length }}
                  </span>
                </div>
                <div class="flex items-center gap-2">
                  <button
                    v-if="canWriteStudents"
                    type="button"
                    class="whitespace-nowrap rounded-lg border border-fb-line bg-white px-2.5 py-1 text-xs font-semibold text-fb-secondary hover:border-fb-blue hover:text-fb-blue shadow-sm transition-colors"
                    :title="t('students.payLinkHint')"
                    @click="openPaymentLinkModal(detailStudent)"
                  >
                    💳 {{ t('students.payLink') }}
                  </button>
                  <button
                    v-if="canAcceptPayment"
                    type="button"
                    class="whitespace-nowrap rounded-lg bg-emerald-600 px-3 py-1 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700"
                    @click="openAcceptPaymentModal"
                  >
                    + {{ t('payments.addTitle') }}
                  </button>
                </div>
              </div>

              <div v-if="paymentsLoading" class="py-6 text-center text-xs text-fb-secondary">
                {{ t('common.loading') }}
              </div>
              <div v-else-if="!studentPayments.length" class="py-6 text-center text-xs text-fb-secondary">
                {{ t('students.noPayments') }}
              </div>
              <div v-else class="mt-3 space-y-2 max-h-[55vh] overflow-y-auto pr-1">
                <div
                  v-for="p in studentPayments"
                  :key="p.id"
                  class="flex items-center justify-between rounded-lg border border-fb-line bg-white p-3 shadow-sm"
                >
                  <div>
                    <div class="flex items-center gap-2">
                      <template v-if="p.transaction_type === 'refund'">
                        <span class="font-semibold text-rose-700">−{{ t('common.sumAmount', { amount: formatSum(p.amount) }) }}</span>
                        <span class="rounded bg-rose-100 px-2 py-0.5 text-[11px] font-semibold text-rose-700">{{ t('txType.refund') }}</span>
                      </template>
                      <template v-else>
                        <span class="font-semibold text-fb-blue">{{ t('common.sumAmount', { amount: formatSum(p.amount) }) }}</span>
                        <span class="rounded bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-fb-blue">
                          {{ t('receipt.months', { count: p.months_covered ?? 1 }) }}
                        </span>
                        <span v-if="p.discount_amount" class="rounded bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">
                          {{ t('payHint.discount', { amount: formatSum(p.discount_amount) }) }}
                        </span>
                      </template>
                    </div>
                    <div class="mt-1 text-xs text-fb-secondary">
                      {{ p.date }} • {{ payMethodLabel(p.method, p.method_pay) }}
                      <span v-if="p.creator"> • {{ t('students.receivedBy', { name: p.creator }) }}</span>
                    </div>
                    <div v-if="p.comment" class="mt-1 text-xs italic text-fb-secondary">
                      {{ p.comment }}
                    </div>
                  </div>
                  <button
                    v-if="p.transaction_type !== 'refund'"
                    type="button"
                    :title="t('payments.printReceipt')"
                    class="ml-2 inline-flex items-center gap-1 rounded-lg border border-fb-line bg-fb-canvas/50 px-2.5 py-1 text-xs font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue transition-colors"
                    @click="printStudentPayment(p)"
                  >
                    <span>🖨️</span>
                    <span>{{ t('payments.receipt') }}</span>
                  </button>
                </div>
              </div>
            </div>
            </div>
          </div>

          <div v-else class="grid flex-1 content-start gap-x-6 gap-y-4 overflow-y-auto p-6 lg:grid-cols-2 2xl:grid-cols-3">
            <div class="col-span-full flex items-center gap-4">
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
                  {{ t('students.uploadPhoto') }}
                </button>
                <button
                  v-if="photoPreview || photoMarkedRemove"
                  type="button"
                  class="text-xs text-fb-danger hover:underline"
                  @click="removePhoto"
                >
                  {{ t('students.removePhoto') }}
                </button>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.firstName') }}</label>
                <input
                  v-model="form.first_name"
                  type="text"
                  required
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.lastName') }}</label>
                <input
                  v-model="form.last_name"
                  type="text"
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.phone') }}</label>
              <input
                v-model="form.phone"
                type="tel"
                required
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('leads.phone2Optional') }}</label>
                  <input
                    v-model="form.phone2"
                    type="tel"
                    :placeholder="t('leads.phone2Placeholder')"
                    :readonly="isReadOnly"
                    class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('leads.phone2Owner') }}</label>
                  <input
                    v-model="form.phone2_owner"
                    list="phone2-owners-student"
                    type="text"
                    :placeholder="t('leads.phone2OwnerPlaceholder')"
                    :readonly="isReadOnly"
                    class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                  />
                  <datalist id="phone2-owners-student">
                    <option v-for="owner in PHONE_OWNERS" :key="owner.value" :value="owner.value" :label="presetLabel(owner.value)" />
                  </datalist>
                </div>
              </div>
              <div v-if="!isReadOnly" class="mt-1.5 flex flex-wrap items-center gap-1.5">
                <span class="text-xs text-fb-icon">{{ t('leads.quickPick') }}:</span>
                <button
                  v-for="owner in PHONE_OWNER_BUTTONS"
                  :key="owner.value"
                  type="button"
                  class="rounded-md border px-2 py-0.5 text-xs transition-colors"
                  :class="form.phone2_owner === owner.value ? 'bg-fb-blue text-white border-fb-blue' : 'border-fb-line text-fb-secondary hover:bg-fb-canvas'"
                  @click="form.phone2_owner = form.phone2_owner === owner.value ? '' : owner.value"
                >
                  {{ presetLabel(owner.value) }}
                </button>
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('import.school') }}</label>
              <input
                v-model="form.school"
                type="text"
                :placeholder="t('leads.schoolPlaceholder')"
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('settings.address') }}</label>
              <input
                v-model="form.address"
                type="text"
                :placeholder="t('leads.addressPlaceholder')"
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('students.telegramStudent') }}</label>
                <input
                  v-model="form.telegram"
                  type="text"
                  placeholder="@username"
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('students.telegramParents') }}</label>
                <input
                  v-model="form.parent_telegram"
                  type="text"
                  :placeholder="t('students.tgParentsPlaceholder')"
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.comment') }}</label>
              <textarea
                v-model="form.comment"
                rows="2"
                :placeholder="t('leads.commentPlaceholder')"
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              ></textarea>
            </div>

            <div v-if="detailParentTgLink" class="rounded-lg border border-fb-line bg-fb-canvas px-4 py-3 text-sm">
              <div class="font-medium text-fb-text">{{ t('students.parentsLink') }}</div>
              <p class="mt-1 text-fb-secondary">
                {{ t('students.parentsLinkHint') }}
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
                  {{ t('common.copy') }}
                </button>
              </div>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('leads.levelLong') }}</label>
              <input
                v-model="form.level"
                type="text"
                :placeholder="t('leads.levelPlaceholder')"
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.branch') }}</label>
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
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('schedule.group') }}</label>
              <select
                v-model="form.group_id"
                :disabled="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option value="">— {{ t('leads.noGroup') }} —</option>
                <option v-for="group in filteredGroups" :key="group.id" :value="group.id">
                  {{ group.name }}
                </option>
              </select>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.status') }}</label>
              <select
                v-model="form.status"
                :disabled="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option v-for="option in STATUS_OPTIONS" :key="option.value" :value="option.value">
                  {{ t(option.label) }}
                </option>
              </select>
            </div>

            <div
              v-if="editingStudent?.status === 2 && form.status === 1"
              class="rounded-xl border border-emerald-200 bg-emerald-50 p-3"
            >
              <div class="text-xs font-semibold text-emerald-900">
                ⚡ {{ t('students.resumeFromFreeze') }}
              </div>
              <p class="mt-0.5 text-xs text-emerald-700">
                {{ t('students.resumeFromFreezeHint') }}
              </p>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">
                {{ t('leads.startDate') }} <span class="text-rose-500">*</span>
              </label>
              <input
                v-model="form.trial_date"
                type="date"
                required
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div
              v-if="detailStudent?.group_id"
              class="rounded-lg border border-fb-line bg-fb-canvas px-4 py-3 text-sm"
            >
              <span class="text-fb-secondary">{{ t('schedule.group') }}: </span>
              <span class="font-medium text-fb-text">{{ detailStudent.group }}</span>
              <button
                type="button"
                class="ml-3 text-fb-blue hover:underline"
                @click="goGroup(detailStudent)"
              >
                {{ t('rating.groupPage') }} →
              </button>
            </div>

            <p v-if="formError" class="col-span-full text-sm text-fb-danger">{{ formError }}</p>
          </div>

          <div class="flex flex-wrap gap-2 border-t border-fb-line px-6 py-4">
            <template v-if="isReadOnly && canWriteStudents">
              <button
                v-if="detailStudent?.status === 2"
                type="button"
                class="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
                @click="openUnfreezeModal(detailStudent)"
              >
                {{ t('students.resume') }}
              </button>
              <button
                type="button"
                class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white hover:opacity-90"
                @click="startEdit"
              >
                {{ t('common.edit') }}
              </button>
            </template>
            <template v-else-if="!isReadOnly">
              <button
                type="submit"
                class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                :disabled="saving"
              >
                {{ saving ? t('common.saving') : editingStudent ? t('common.save') : t('common.create') }}
              </button>
            </template>
            <button
              type="button"
              class="rounded-lg border border-fb-line px-5 py-2 text-sm font-medium text-fb-secondary"
              @click="closePanel"
            >
              {{ t('common.cancel') }}
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
          <h3 class="text-lg font-semibold text-fb-text">{{ t('students.resumeTitle') }}</h3>
          <button
            type="button"
            class="text-fb-icon hover:text-fb-secondary"
            :aria-label="t('common.close')"
            @click="showUnfreezeModal = false"
          >
            ✕
          </button>
        </div>

        <div class="mt-4 space-y-4">
          <p class="text-sm text-fb-secondary">
            {{ t('students.resumeText', { name: unfreezeStudent?.full_name ?? '' }) }}
          </p>
          <div class="rounded-lg bg-fb-canvas p-3 text-xs text-fb-secondary">
            {{ t('students.resumeDateHint') }}
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-text">
              {{ t('students.resumeDate') }}:
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
              {{ t('common.cancel') }}
            </button>
            <button
              type="button"
              class="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              :disabled="unfreezeSaving"
              @click="confirmUnfreeze"
            >
              {{ unfreezeSaving ? t('common.saving') : t('students.resumeConfirm') }}
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
            <h3 class="text-base font-semibold text-fb-text">{{ t('payments.addTitle') }}</h3>
            <p class="text-xs text-fb-secondary mt-0.5">{{ detailStudent?.full_name }}</p>
          </div>
          <button type="button" class="text-fb-secondary hover:text-fb-text" :aria-label="t('common.close')" @click="showPayModal = false">✕</button>
        </div>

        <form class="mt-4 space-y-4" @submit.prevent="submitPayment">
          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">
              {{ t('payments.monthsNew') }}
            </label>
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
            <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('payments.discount') }}</label>
            <input
              v-model.number="payForm.discount"
              type="number"
              min="0"
              step="1"
              :placeholder="t('payments.noDiscount')"
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              @input="onPayMonthsChange"
            />
            <p class="mt-1 text-[11px] text-fb-secondary">{{ t('payments.discountHint') }}</p>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('payLink.amount') }}</label>
            <input
              v-model.number="payForm.amount"
              type="number"
              min="1"
              step="1"
              required
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm font-semibold focus:border-fb-blue focus:outline-none"
            />
            <p v-if="detailStudent?.course_price" class="mt-1 text-[11px] text-fb-secondary">
              {{ t('payLink.basePrice', { amount: formatSum(detailStudent.course_price) }) }}
            </p>
            <PaymentPreviewHint
              :student-id="detailStudent?.id"
              :amount="payForm.amount"
              :discount="Number(payForm.discount) || 0"
              :months="payForm.months_covered"
              :date="payForm.payment_date"
            />
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('payments.date') }}</label>
            <input
              v-model="payForm.payment_date"
              type="date"
              :max="todayIso()"
              required
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('receipt.method').replace(':', '') }}</label>
            <select
              v-model="payForm.method"
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            >
              <option value="cash">{{ t('payMethod.cash') }}</option>
              <option value="card">{{ t('payMethod.card') }}</option>
              <option value="transfer">{{ t('payMethod.transfer') }}</option>
            </select>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">{{ t('common.comment') }}</label>
            <textarea
              v-model="payForm.comment"
              rows="2"
              :placeholder="t('common.optional')"
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
              {{ t('common.cancel') }}
            </button>
            <button
              type="submit"
              class="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
              :disabled="paySaving"
            >
              {{ paySaving ? t('common.saving') : t('payments.takePayment') }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <ImportCsvModal
      v-if="!isCard"
      v-model:open="showImportModal"
      :title="t('students.importTitle')"
      upload-url="/students/import"
      template-filename="students-import-template.csv"
      :template-header="['first_name', 'last_name', 'phone', 'school', 'branch', 'group', 'status', 'parent_telegram']"
      :template-example="['Ali', 'Valiyev', '998901234567', 'School #5', 'Main branch', '', 'Active', '@parent_tg']"
      :columns-help="t('students.importHelp')"
      @imported="loadStudents()"
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
