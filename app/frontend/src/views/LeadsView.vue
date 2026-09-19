<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';
import { downloadCsv } from '../utils/csvExport';
import { hasCreateFlag, routeWithoutCreate } from '../utils/crossLinks';

interface LeadRow {
  id: number;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  phone2?: string;
  phone2_owner?: string;
  address?: string;
  comment?: string;
  source?: string;
  level?: string;
  school?: string;
  branch_id?: number | null;
  branch_name?: string | null;
  course_id?: number | null;
  course_name?: string | null;
  stage: string;
  stage_label: string;
  status?: string;
  status_label?: string;
  trial_date?: string | null;
  converted_student_id?: number | null;
  student_deleted?: boolean;
  is_active: boolean;
  created_at: string;
}

interface Branch {
  id: number;
  name: string;
}

interface GroupOption {
  id: number;
  name: string;
  branch_id: number;
  course_id?: number;
}

interface CourseOption {
  id: number;
  name: string;
  code?: string;
  price?: number;
}

const STAGES = [
  { value: 'trial_booked', label: 'Записан на пробный' },
  { value: 'attended', label: 'Был на уроке (Думает)' },
  { value: 'converted', label: 'Зачислен (Студент)' },
  { value: 'rejected', label: 'Отказ' },
] as const;

const EDITABLE_STAGES = STAGES.filter((s) => s.value !== 'converted');

const POPULAR_SOURCES = [
  'Instagram',
  'Telegram',
  'Звонок',
  'Рекомендация',
  'Наружка',
  'Сайт',
  'Другое',
] as const;

const LANGUAGE_LEVEL_PRESETS = [
  'Beginner (A1)',
  'Elementary (A2)',
  'Pre-Intermediate',
  'Intermediate (B1)',
  'Upper-Intermediate (B2)',
  'Advanced (C1)',
  'IELTS / Экзамен',
] as const;

const MATH_LEVEL_PRESETS = [
  '1-4 классы',
  '5-8 классы',
  '9-11 классы',
  'ОГЭ / ЕГЭ / ДТМ',
  'Олимпиадная',
] as const;

const GENERAL_LEVEL_PRESETS = [
  'Начальный (Beginner)',
  'Базовый (Elementary)',
  'Средний (Intermediate)',
  'Продвинутый (Advanced)',
  'Экзамен / Тест',
] as const;

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const rows = ref<LeadRow[]>([]);
const loading = ref(true);
const saving = ref(false);
const archiving = ref(false);
const showPanel = ref(false);
const formError = ref('');
const editingLead = ref<LeadRow | null>(null);
const showFilters = ref(true);

const pageSize = ref(50);
const currentPage = ref(1);
const totalCount = ref(0);
const totalPages = computed(() => Math.max(1, Math.ceil(totalCount.value / pageSize.value)));

const showConvertModal = ref(false);
const converting = ref(false);
const convertError = ref('');
const branches = ref<Branch[]>([]);
const groups = ref<GroupOption[]>([]);
const courses = ref<CourseOption[]>([]);

function getTodayDateString(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

const convertForm = reactive({
  first_name: '',
  last_name: '',
  phone: '',
  phone2: '',
  phone2_owner: '',
  address: '',
  school: '',
  comment: '',
  level: '',
  branch_id: 0,
  group_id: '' as number | '',
  status: 1,
  trial_date: getTodayDateString(),
  attended_trial: true,
});

const filteredConvertGroups = computed(() => {
  if (!convertForm.branch_id) return groups.value;
  return groups.value.filter((g) => g.branch_id === convertForm.branch_id);
});

watch(
  () => convertForm.branch_id,
  (newBranchId) => {
    if (convertForm.group_id) {
      const selectedG = groups.value.find((g) => g.id === convertForm.group_id);
      if (selectedG && selectedG.branch_id !== newBranchId) {
        convertForm.group_id = '';
      }
    }
  },
);

watch(
  () => convertForm.group_id,
  (newGroupId) => {
    if (newGroupId) {
      const selectedG = groups.value.find((g) => g.id === newGroupId);
      if (selectedG && selectedG.branch_id) {
        convertForm.branch_id = selectedG.branch_id;
      }
    }
  },
);

const filters = reactive({
  stage: 'trial_booked',
  course_id: '' as number | '',
  level: '',
  q: '',
  archived: '0',
});

const ALL_FILTER_LEVEL_PRESETS = [
  ...LANGUAGE_LEVEL_PRESETS,
  ...MATH_LEVEL_PRESETS,
] as const;

const customLevels = ref<string[]>([]);

const activeFilterLevelPresets = computed(() => {
  if (!filters.course_id) {
    return ALL_FILTER_LEVEL_PRESETS;
  }
  const selectedCourse = courses.value.find((c) => c.id === Number(filters.course_id));
  const name = (selectedCourse?.name || '').toLowerCase();
  if (name.includes('мат') || name.includes('math')) {
    return MATH_LEVEL_PRESETS;
  }
  if (
    name.includes('англ') ||
    name.includes('english') ||
    name.includes('нем') ||
    name.includes('deutsch') ||
    name.includes('кит') ||
    name.includes('chinese') ||
    name.includes('язык')
  ) {
    return LANGUAGE_LEVEL_PRESETS;
  }
  return GENERAL_LEVEL_PRESETS;
});

const availableFilterLevels = computed(() => {
  const set = new Set<string>(activeFilterLevelPresets.value);
  if (!filters.course_id) {
    for (const lvl of customLevels.value) {
      if (lvl.trim()) set.add(lvl.trim());
    }
  }
  return Array.from(set);
});

watch(
  () => filters.course_id,
  () => {
    if (filters.level && !availableFilterLevels.value.includes(filters.level)) {
      filters.level = '';
    }
  },
);

// Client-side filtering is removed since the backend handles it with pagination

const form = reactive({
  first_name: '',
  last_name: '',
  phone: '',
  phone2: '',
  phone2_owner: '',
  address: '',
  school: '',
  comment: '',
  source: '',
  level: '',
  branch_id: '' as number | '',
  course_id: '' as number | '',
  stage: 'trial_booked' as (typeof STAGES)[number]['value'],
  trial_date: getTodayDateString(),
});

const activeLevelPresets = computed(() => {
  const selectedCourse = courses.value.find((c) => c.id === form.course_id);
  const name = (selectedCourse?.name || '').toLowerCase();
  if (name.includes('мат') || name.includes('math')) {
    return MATH_LEVEL_PRESETS;
  }
  if (
    name.includes('англ') ||
    name.includes('english') ||
    name.includes('нем') ||
    name.includes('deutsch') ||
    name.includes('кит') ||
    name.includes('chinese') ||
    name.includes('язык')
  ) {
    return LANGUAGE_LEVEL_PRESETS;
  }
  return GENERAL_LEVEL_PRESETS;
});

const panelTitle = computed(() => (editingLead.value ? 'Lead details' : 'Add lead'));
const canExportLeads = computed(() => auth.can(PERM.LEADS_VIEW));
const canConvertLead = computed(() => auth.can(PERM.STUDENTS_WRITE) && auth.can(PERM.LEADS_WRITE));

function exportCsv() {
  downloadCsv(
    'leads.csv',
    ['First name', 'Last name', 'Full name', 'Phone', 'Phone 2', 'Phone 2 Owner', 'Branch', 'Course', 'Level', 'School', 'Source', 'Address', 'Comment', 'Trial date', 'Status', 'Active', 'Created'],
    rows.value.map((row) => [
      row.first_name || '',
      row.last_name || '',
      row.full_name,
      row.phone,
      row.phone2 || '',
      row.phone2_owner || '',
      row.branch_name || '',
      row.course_name || '',
      row.level || '',
      row.school || '',
      row.source || '',
      row.address || '',
      row.comment || '',
      row.trial_date || '',
      row.stage_label,
      row.is_active ? 'Yes' : 'No',
      row.created_at,
    ]),
  );
}

function resetForm() {
  form.first_name = '';
  form.last_name = '';
  form.phone = '';
  form.phone2 = '';
  form.phone2_owner = '';
  form.address = '';
  form.school = '';
  form.comment = '';
  form.source = '';
  form.level = '';
  form.branch_id = '';
  form.course_id = '';
  form.stage = 'trial_booked';
  form.trial_date = getTodayDateString();
  formError.value = '';
  editingLead.value = null;
}

function openPanel(lead?: LeadRow) {
  resetForm();
  void loadBranchAndGroupOptions();
  if (lead) {
    editingLead.value = lead;
    form.first_name = lead.first_name || (lead.full_name ? lead.full_name.split(' ')[0] : '');
    form.last_name = lead.last_name || (lead.full_name ? lead.full_name.split(' ').slice(1).join(' ') : '');
    form.phone = lead.phone;
    form.phone2 = lead.phone2 || '';
    form.phone2_owner = lead.phone2_owner || '';
    form.address = lead.address || '';
    form.school = lead.school || '';
    form.comment = lead.comment || '';
    form.source = lead.source || '';
    form.level = lead.level || '';
    form.branch_id = (lead.branch_id ?? '') as number | '';
    form.course_id = (lead.course_id ?? '') as number | '';
    form.stage = lead.stage as (typeof STAGES)[number]['value'];
    form.trial_date = lead.trial_date ? lead.trial_date.slice(0, 10) : getTodayDateString();
  }
  showPanel.value = true;
}

function closePanel() {
  showPanel.value = false;
  formError.value = '';
  editingLead.value = null;
}

async function loadLeads() {
  loading.value = true;
  try {
    const params: Record<string, string> = {
      archived: filters.archived,
      limit: String(pageSize.value),
      offset: String((currentPage.value - 1) * pageSize.value),
    };
    if (filters.stage) params.stage = filters.stage;
    if (filters.course_id) params.course_id = String(filters.course_id);
    if (filters.level) params.level = filters.level;
    if (filters.q.trim()) params.q = filters.q.trim();

    const { data } = await client.get<ApiEnvelope<LeadRow[]>>('/leads', { params });
    rows.value = data.data;
    totalCount.value = (data.data as any).count ?? data.data.length;
    for (const r of data.data) {
      if (r.level?.trim() && !customLevels.value.includes(r.level.trim())) {
        customLevels.value.push(r.level.trim());
      }
    }
  } finally {
    loading.value = false;
  }
}

function cleanPhoneDigits(raw: string): string {
  let d = raw.replace(/\D/g, '');
  if (d.startsWith('998') && d.length >= 10) {
    d = d.slice(3);
  }
  return d;
}

function apiErrorMessage(error: unknown, fallback: string): string {
  const data = (error as { response?: { data?: { message?: string; error?: string; detail?: string } } })?.response?.data;
  const msg = data?.message || data?.error || data?.detail;
  if (!msg) return fallback;
  if (msg.includes('Secondary phone must contain at least 9 digits')) {
    return 'Дополнительный номер должен содержать минимум 9 цифр (например, 90 123 45 67)';
  }
  if (msg.includes('at least 9 digits')) {
    return 'Номер телефона должен содержать минимум 9 цифр (например, 90 123 45 67)';
  }
  if (msg.includes('First name is required')) {
    return 'Введите имя лида';
  }
  if (msg.includes('Trial / start date is required')) {
    return 'Укажите дату старта / пробного урока';
  }
  return msg;
}

async function saveLead() {
  formError.value = '';
  if (!form.first_name.trim()) {
    formError.value = 'Введите имя';
    return;
  }
  if (!form.phone.trim()) {
    formError.value = 'Введите номер телефона';
    return;
  }
  const digits = cleanPhoneDigits(form.phone);
  if (digits.length < 9) {
    formError.value = 'Номер телефона должен содержать минимум 9 цифр (например, 90 123 45 67)';
    return;
  }
  if (form.phone2.trim()) {
    const digits2 = cleanPhoneDigits(form.phone2);
    if (digits2.length < 9) {
      formError.value = 'Дополнительный номер должен содержать минимум 9 цифр (например, 90 123 45 67)';
      return;
    }
  }
  if (!form.trial_date) {
    formError.value = 'Укажите дату старта / пробного урока';
    return;
  }

  saving.value = true;
  try {
    const payload = {
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      full_name: `${form.first_name.trim()} ${form.last_name.trim()}`.trim(),
      phone: form.phone.trim(),
      phone2: form.phone2.trim(),
      phone2_owner: form.phone2_owner.trim(),
      address: form.address.trim(),
      school: form.school.trim(),
      comment: form.comment.trim(),
      source: form.source.trim(),
      level: form.level.trim(),
      branch_id: form.branch_id || null,
      course_id: form.course_id || null,
      stage: form.stage,
      trial_date: form.trial_date || null,
    };

    if (editingLead.value) {
      await client.patch(`/leads/${editingLead.value.id}`, payload);
    } else {
      await client.post('/leads', payload);
    }

    await loadLeads();
    if (form.level.trim() && !customLevels.value.includes(form.level.trim())) {
      customLevels.value.push(form.level.trim());
    }
    closePanel();
  } catch (err: unknown) {
    formError.value = apiErrorMessage(err, editingLead.value ? 'Не удалось обновить лид' : 'Не удалось создать лид');
  } finally {
    saving.value = false;
  }
}

async function archiveLead() {
  if (!editingLead.value) return;

  archiving.value = true;
  try {
    await client.post(`/leads/${editingLead.value.id}/archive`);
    await loadLeads();
    closePanel();
  } catch (err: unknown) {
    formError.value = apiErrorMessage(err, 'Не удалось архивировать лид');
  } finally {
    archiving.value = false;
  }
}

async function restoreLead() {
  if (!editingLead.value) return;

  saving.value = true;
  try {
    await client.patch(`/leads/${editingLead.value.id}`, { is_active: true });
    await loadLeads();
    closePanel();
  } catch (err: unknown) {
    formError.value = apiErrorMessage(err, 'Не удалось восстановить лид');
  } finally {
    saving.value = false;
  }
}

async function returnLeadToWork() {
  if (!editingLead.value) return;
  saving.value = true;
  try {
    await client.patch(`/leads/${editingLead.value.id}`, { stage: 'trial_booked', is_active: true });
    await loadLeads();
    closePanel();
  } catch (err: unknown) {
    formError.value = apiErrorMessage(err, 'Не удалось вернуть лид в работу');
  } finally {
    saving.value = false;
  }
}

async function loadBranchAndGroupOptions() {
  try {
    const [bRes, gRes, cRes] = await Promise.all([
      client.get<ApiEnvelope<Branch[]>>('/branch'),
      client.get<ApiEnvelope<GroupOption[]>>('/groups'),
      client.get<ApiEnvelope<CourseOption[]>>('/courses'),
    ]);
    branches.value = bRes.data.data;
    groups.value = gRes.data.data;
    courses.value = cRes.data.data;
    if (branches.value.length && !convertForm.branch_id) {
      convertForm.branch_id = branches.value[0].id;
    }
  } catch {
    // ignore
  }
}

async function openConvertModal() {
  if (!editingLead.value || (editingLead.value.stage === 'converted' && !editingLead.value.student_deleted)) return;
  convertForm.first_name = (form.first_name || editingLead.value.first_name || '').trim();
  convertForm.last_name = (form.last_name || editingLead.value.last_name || '').trim();
  if (!convertForm.first_name && editingLead.value.full_name) {
    const nameParts = editingLead.value.full_name.trim().split(' ');
    convertForm.first_name = nameParts[0] || '';
    convertForm.last_name = nameParts.slice(1).join(' ') || '';
  }
  convertForm.phone = form.phone || editingLead.value.phone;
  convertForm.phone2 = form.phone2 || editingLead.value.phone2 || '';
  convertForm.phone2_owner = form.phone2_owner || editingLead.value.phone2_owner || '';
  convertForm.address = form.address || editingLead.value.address || '';
  convertForm.school = form.school || editingLead.value.school || '';
  convertForm.comment = form.comment || editingLead.value.comment || '';
  convertForm.level = form.level || editingLead.value.level || '';
  convertForm.group_id = '';
  convertForm.status = 1;
  convertForm.trial_date = form.trial_date || (editingLead.value.trial_date ? editingLead.value.trial_date.slice(0, 10) : getTodayDateString());
  convertForm.attended_trial = true;

  await loadBranchAndGroupOptions();
  if (editingLead.value.branch_id) {
    convertForm.branch_id = editingLead.value.branch_id;
  } else if (branches.value.length && !convertForm.branch_id) {
    convertForm.branch_id = branches.value[0].id;
  }
  showConvertModal.value = true;
}

function closeConvertModal() {
  showConvertModal.value = false;
  convertError.value = '';
}

async function handleConvert() {
  if (!editingLead.value || (editingLead.value.stage === 'converted' && !editingLead.value.student_deleted)) return;
  convertError.value = '';

  if (!convertForm.first_name.trim()) {
    convertError.value = 'Введите имя';
    return;
  }
  if (!convertForm.phone.trim()) {
    convertError.value = 'Введите номер телефона';
    return;
  }
  const digits = cleanPhoneDigits(convertForm.phone);
  if (digits.length < 9) {
    convertError.value = 'Номер телефона должен содержать минимум 9 цифр (например, 90 123 45 67)';
    return;
  }
  if (convertForm.phone2.trim()) {
    const digits2 = cleanPhoneDigits(convertForm.phone2);
    if (digits2.length < 9) {
      convertError.value = 'Дополнительный номер должен содержать минимум 9 цифр (например, 90 123 45 67)';
      return;
    }
  }
  if (!convertForm.branch_id) {
    convertError.value = 'Выберите филиал';
    return;
  }
  if (!convertForm.trial_date) {
    convertError.value = 'Укажите дату старта / пробного урока';
    return;
  }

  converting.value = true;
  try {
    const payload = {
      first_name: convertForm.first_name.trim(),
      last_name: convertForm.last_name.trim(),
      phone: convertForm.phone.trim(),
      phone2: convertForm.phone2.trim(),
      phone2_owner: convertForm.phone2_owner.trim(),
      address: convertForm.address.trim(),
      school: convertForm.school.trim(),
      comment: convertForm.comment.trim(),
      level: convertForm.level.trim(),
      branch_id: convertForm.branch_id,
      group_id: convertForm.group_id || null,
      status: convertForm.status,
      trial_date: convertForm.trial_date || null,
      attended_trial: convertForm.attended_trial,
    };

    const convertedLeadId = editingLead.value.id;
    const res = await client.post<{ data: { student: { id: number } } }>(
      `/leads/${convertedLeadId}/convert`,
      payload,
    );
    const createdStudentId = res.data.data?.student?.id;

    rows.value = rows.value.filter((r) => r.id !== convertedLeadId);
    closeConvertModal();
    closePanel();
    await loadLeads();

    if (createdStudentId) {
      router.push({ path: '/students', query: { open: String(createdStudentId) } });
    }
  } catch (err: unknown) {
    convertError.value = apiErrorMessage(err, 'Не удалось перевести лид в студенты');
  } finally {
    converting.value = false;
  }
}

function setStageFilter(stage: string) {
  filters.archived = '0';
  filters.stage = stage;
}

function applyRouteQuery() {
  if (typeof route.query.archived === 'string') {
    filters.archived = route.query.archived;
  }
  if (typeof route.query.status === 'string') {
    filters.stage = route.query.status === 'all' ? '' : route.query.status;
  } else if (typeof route.query.stage === 'string') {
    filters.stage = route.query.stage === 'all' ? '' : route.query.stage;
  } else {
    filters.stage = 'trial_booked';
  }
  if (typeof route.query.course_id === 'string' && route.query.course_id) {
    filters.course_id = Number(route.query.course_id) || '';
  }
  if (typeof route.query.level === 'string') {
    filters.level = route.query.level;
  }
  if (typeof route.query.q === 'string') {
    filters.q = route.query.q;
  }
}

function syncQueryToRoute() {
  const query: Record<string, string> = {};
  if (filters.archived === '1') {
    query.archived = '1';
  }
  if (filters.stage) {
    query.stage = filters.stage;
  } else {
    query.stage = 'all';
  }
  if (filters.course_id) query.course_id = String(filters.course_id);
  if (filters.level) query.level = filters.level;
  if (filters.q.trim()) query.q = filters.q.trim();
  router.replace({ path: '/leads', query });
}

function maybeCreateFromRoute() {
  if (!hasCreateFlag(route.query) || showPanel.value) return;
  openPanel();
  router.replace(routeWithoutCreate(route));
}

watch(
  () => route.query.create,
  () => {
    maybeCreateFromRoute();
  },
);

watch(
  () => [route.query.stage, route.query.status] as const,
  ([newStage, newStatus]) => {
    const raw = typeof newStatus === 'string' ? newStatus : typeof newStage === 'string' ? newStage : undefined;
    const targetStage = raw === undefined ? 'trial_booked' : raw === 'all' ? '' : raw;
    if (filters.stage !== targetStage) {
      filters.stage = targetStage;
    }
  },
);

let leadSearchDebounce: ReturnType<typeof setTimeout> | null = null;
watch(
  () => filters.q,
  (newQ) => {
    if (newQ.trim() === String(route.query.q ?? '').trim()) return;
    if (leadSearchDebounce) clearTimeout(leadSearchDebounce);
    leadSearchDebounce = setTimeout(() => {
      currentPage.value = 1;
      syncQueryToRoute();
      void loadLeads();
    }, 400);
  },
);

watch(
  () => [filters.stage, filters.course_id, filters.level, filters.archived] as const,
  () => {
    currentPage.value = 1;
    syncQueryToRoute();
    void loadLeads();
  },
);

onMounted(async () => {
  applyRouteQuery();
  await Promise.all([loadLeads(), loadBranchAndGroupOptions()]);
  maybeCreateFromRoute();
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-baseline gap-3">
        <h1 class="text-xl font-semibold text-fb-text">Leads</h1>
        <span v-if="!loading" class="text-sm text-fb-secondary">
          Quantity — {{ totalCount }}
        </span>
      </div>
      <div class="flex flex-wrap gap-2">
        <button
          v-if="canExportLeads"
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
          @click="exportCsv"
        >
          Export
        </button>
        <button
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
          @click="showFilters = !showFilters"
        >
          {{ showFilters ? 'Hide filters' : 'Show filters' }}
        </button>
        <button
          type="button"
          class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          @click="openPanel()"
        >
          + Add lead
        </button>
      </div>
    </div>

    <div v-if="showFilters" class="rounded-xl border border-fb-line bg-fb-card p-4 space-y-4">
      <div class="flex flex-wrap gap-2">
        <button
          v-for="stage in STAGES"
          :key="stage.value"
          type="button"
          class="rounded-full px-3 py-1.5 text-sm transition-colors"
          :class="filters.stage === stage.value && filters.archived !== '1'
            ? 'bg-fb-hover font-medium text-fb-blue'
            : 'bg-fb-canvas text-fb-secondary hover:text-fb-text'"
          @click="setStageFilter(stage.value)"
        >
          {{ stage.label }}
        </button>
        <button
          type="button"
          class="rounded-full px-3 py-1.5 text-sm transition-colors"
          :class="!filters.stage && filters.archived !== '1'
            ? 'bg-fb-hover font-medium text-fb-blue'
            : 'bg-fb-canvas text-fb-secondary hover:text-fb-text'"
          @click="setStageFilter('')"
        >
          Все статусы
        </button>
        <button
          type="button"
          class="rounded-full px-3 py-1.5 text-sm transition-colors"
          :class="filters.archived === '1'
            ? 'bg-fb-hover font-medium text-fb-blue'
            : 'bg-fb-canvas text-fb-secondary hover:text-fb-text'"
          @click="filters.archived = filters.archived === '1' ? '0' : '1'; filters.stage = '';"
        >
          📦 Архивные
        </button>
      </div>

      <div class="flex flex-wrap items-end gap-3">
        <div class="min-w-[240px] flex-1">
          <label class="mb-1 block text-sm font-medium text-fb-secondary">Search</label>
          <div class="relative">
            <input
              v-model="filters.q"
              type="search"
              placeholder="Search by name, phone, or comment…"
              class="w-full rounded-lg border border-fb-line pl-9 pr-4 py-2 focus:border-fb-blue focus:outline-none"
            />
            <svg class="absolute left-3 top-2.5 text-fb-secondary" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
          </div>
        </div>
        <div v-if="courses.length">
          <label class="mb-1 block text-sm font-medium text-fb-secondary">Course</label>
          <select
            v-model="filters.course_id"
            class="rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none text-sm min-w-[150px]"
          >
            <option :value="''">All courses</option>
            <option v-for="c in courses" :key="c.id" :value="c.id">
              {{ c.name }}
            </option>
          </select>
        </div>
        <div v-if="availableFilterLevels.length">
          <label class="mb-1 block text-sm font-medium text-fb-secondary">Level</label>
          <select
            v-model="filters.level"
            class="rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none text-sm min-w-[140px]"
          >
            <option value="">All levels</option>
            <option v-for="lvl in availableFilterLevels" :key="lvl" :value="lvl">
              {{ lvl }}
            </option>
          </select>
        </div>
      </div>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!rows.length" class="p-8 text-center text-fb-icon">
        {{ rows.length ? 'No leads match your search.' : 'No leads found. Click “+ Add lead” to create one.' }}
      </div>
      <table v-else class="w-full text-base">
        <thead class="border-b border-fb-line bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Name</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Phone</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Address</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Comment</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Trial date</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            class="cursor-pointer border-b border-fb-line hover:bg-fb-hover/40"
            @click="openPanel(row)"
          >
            <td class="px-5 py-4 font-medium text-fb-text">
              <div>{{ row.full_name }}</div>
              <div class="mt-1 flex flex-wrap items-center gap-1.5 text-xs font-normal">
                <span
                  v-if="row.course_name"
                  class="rounded-md bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 border border-blue-200"
                >
                  📚 {{ row.course_name }}
                </span>
                <span
                  v-if="row.level"
                  class="rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800 border border-emerald-200"
                >
                  🎯 {{ row.level }}
                </span>
                <span
                  v-if="row.school"
                  class="rounded-md bg-teal-50 px-2 py-0.5 text-[11px] font-medium text-teal-800 border border-teal-200"
                >
                  🏫 {{ row.school }}
                </span>
                <span
                  v-if="row.branch_name"
                  class="rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 border border-amber-200"
                >
                  📍 {{ row.branch_name }}
                </span>
                <span
                  v-if="row.source"
                  class="rounded-md bg-purple-50 px-2 py-0.5 text-[11px] font-medium text-purple-700 border border-purple-200"
                >
                  📢 {{ row.source }}
                </span>
              </div>
            </td>
            <td class="px-5 py-4 text-fb-secondary">
              <div>{{ row.phone }}</div>
              <div v-if="row.phone2" class="text-xs text-fb-icon flex items-center gap-1 mt-0.5">
                <span v-if="row.phone2_owner" class="font-medium text-fb-secondary">({{ row.phone2_owner }})</span>
                <span>{{ row.phone2 }}</span>
              </div>
            </td>
            <td class="px-5 py-4 text-fb-secondary max-w-[160px] truncate" :title="row.address">
              {{ row.address || '—' }}
            </td>
            <td class="px-5 py-4 text-fb-secondary max-w-[180px] truncate" :title="row.comment">
              {{ row.comment || '—' }}
            </td>
            <td class="px-5 py-4 text-fb-secondary font-medium whitespace-nowrap">
              {{ row.trial_date || '—' }}
            </td>
            <td class="px-5 py-4 text-fb-secondary">
              <span
                class="rounded-full px-2.5 py-1 text-xs font-medium"
                :class="
                  row.stage === 'converted' && row.student_deleted
                    ? 'bg-amber-100 text-amber-900 border border-amber-300'
                    : row.stage === 'converted'
                    ? 'bg-emerald-100 text-emerald-800'
                    : row.stage === 'attended'
                    ? 'bg-amber-100 text-amber-800'
                    : row.stage === 'rejected'
                    ? 'bg-rose-100 text-rose-800'
                    : 'bg-blue-100 text-blue-800'
                "
              >
                {{ row.stage === 'converted' && row.student_deleted ? '⚠️ Студент удален' : row.stage_label }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="!loading && totalCount > 0" class="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-fb-line bg-fb-card px-5 py-3">
      <div class="flex items-center gap-2 text-sm text-fb-secondary">
        <span>Показывать по:</span>
        <select
          :value="pageSize"
          @change="pageSize = Number(($event.target as HTMLSelectElement).value); currentPage = 1; loadLeads();"
          class="rounded-lg border border-fb-line px-2 py-1 text-sm focus:border-fb-blue focus:outline-none"
        >
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
        <span class="ml-2">
          Показано {{ Math.min((currentPage - 1) * pageSize + 1, totalCount) }}–{{ Math.min(currentPage * pageSize, totalCount) }} из {{ totalCount }}
        </span>
      </div>
      <div v-if="totalPages > 1" class="flex items-center gap-1">
        <button
          type="button"
          class="rounded-lg border border-fb-line px-3 py-1 text-sm font-medium text-fb-secondary hover:bg-fb-canvas disabled:opacity-40"
          :disabled="currentPage <= 1"
          @click="currentPage--; loadLeads();"
        >
          ← Назад
        </button>
        <template v-for="p in totalPages" :key="p">
          <button
            v-if="p === 1 || p === totalPages || (p >= currentPage - 2 && p <= currentPage + 2)"
            type="button"
            class="rounded-lg px-3 py-1 text-sm font-medium"
            :class="p === currentPage ? 'bg-fb-blue text-white' : 'border border-fb-line text-fb-secondary hover:bg-fb-canvas'"
            @click="currentPage = p; loadLeads();"
          >
            {{ p }}
          </button>
          <span
            v-else-if="p === 2 || p === totalPages - 1"
            class="px-1 text-fb-icon"
          >
            …
          </span>
        </template>
        <button
          type="button"
          class="rounded-lg border border-fb-line px-3 py-1 text-sm font-medium text-fb-secondary hover:bg-fb-canvas disabled:opacity-40"
          :disabled="currentPage >= totalPages"
          @click="currentPage++; loadLeads();"
        >
          Вперёд →
        </button>
      </div>
    </div>

    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closePanel" />
      <aside class="drawer-panel-fb max-w-lg">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-5">
          <h2 class="text-[22px] font-semibold text-fb-text">{{ panelTitle }}</h2>
          <button
            type="button"
            class="text-2xl leading-none text-fb-icon hover:text-fb-secondary"
            @click="closePanel"
          >
            ×
          </button>
        </div>

        <form class="flex-1 space-y-5 overflow-y-auto px-6 py-6" @submit.prevent="saveLead">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-2 block text-[15px] font-medium text-fb-secondary">First name</label>
              <input
                v-model="form.first_name"
                type="text"
                required
                class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Last name</label>
              <input
                v-model="form.last_name"
                type="text"
                class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Phone</label>
            <input
              v-model="form.phone"
              type="tel"
              required
              placeholder="e.g. 90 123 45 67"
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">Second phone (optional)</label>
                <input
                  v-model="form.phone2"
                  type="tel"
                  placeholder="Additional phone number"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">Whose number? (Чей номер)</label>
                <input
                  v-model="form.phone2_owner"
                  list="phone2-owners-lead"
                  type="text"
                  placeholder="e.g. Мама, Отец, Брат..."
                  class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
                />
                <datalist id="phone2-owners-lead">
                  <option value="Мама" />
                  <option value="Отец" />
                  <option value="Брат" />
                  <option value="Сестра" />
                  <option value="Бабушка" />
                  <option value="Дедушка" />
                  <option value="Родственник" />
                </datalist>
              </div>
            </div>
            <div class="mt-1.5 flex flex-wrap items-center gap-1.5">
              <span class="text-xs text-fb-icon">Быстрый выбор:</span>
              <button
                v-for="owner in ['Мама', 'Отец', 'Брат', 'Сестра', 'Родственник']"
                :key="owner"
                type="button"
                class="rounded-md border px-2 py-0.5 text-xs transition-colors"
                :class="form.phone2_owner === owner ? 'bg-fb-blue text-white border-fb-blue' : 'border-fb-line text-fb-secondary hover:bg-fb-canvas'"
                @click="form.phone2_owner = form.phone2_owner === owner ? '' : owner"
              >
                {{ owner }}
              </button>
            </div>
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Address</label>
            <input
              v-model="form.address"
              type="text"
              placeholder="e.g. Tashkent, Chilanzar"
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">School (Школа / Номер школы)</label>
            <input
              v-model="form.school"
              type="text"
              placeholder="например, Школа № 178"
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Branch (Филиал)</label>
              <select
                v-model="form.branch_id"
                class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
              >
                <option :value="''">— All / Not specified —</option>
                <option v-for="b in branches" :key="b.id" :value="b.id">
                  {{ b.name }}
                </option>
              </select>
            </div>
            <div>
              <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Course (Курс / Предмет)</label>
              <select
                v-model="form.course_id"
                class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
              >
                <option :value="''">— Not selected —</option>
                <option v-for="c in courses" :key="c.id" :value="c.id">
                  {{ c.name }}
                </option>
              </select>
            </div>
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">
              Level (Уровень знаний / класс)
            </label>
            <input
              v-model="form.level"
              list="lead-levels-list"
              type="text"
              placeholder="e.g. Beginner, Elementary, Intermediate, 5 класс, IELTS..."
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            />
            <datalist id="lead-levels-list">
              <option v-for="lvl in activeLevelPresets" :key="lvl" :value="lvl" />
            </datalist>
            <div class="mt-1.5 flex flex-wrap items-center gap-1.5">
              <span class="text-xs text-fb-icon">Быстрый выбор:</span>
              <button
                v-for="lvl in activeLevelPresets"
                :key="lvl"
                type="button"
                class="rounded-md border px-2 py-0.5 text-xs transition-colors"
                :class="form.level === lvl ? 'bg-emerald-600 text-white border-emerald-600' : 'border-fb-line text-fb-secondary hover:bg-fb-canvas'"
                @click="form.level = form.level === lvl ? '' : lvl"
              >
                {{ lvl }}
              </button>
            </div>
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Source (Откуда узнал о нас)</label>
            <input
              v-model="form.source"
              list="lead-sources-list"
              type="text"
              placeholder="e.g. Instagram, Telegram, Рекомендация..."
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            />
            <datalist id="lead-sources-list">
              <option v-for="src in POPULAR_SOURCES" :key="src" :value="src" />
            </datalist>
            <div class="mt-1.5 flex flex-wrap items-center gap-1.5">
              <span class="text-xs text-fb-icon">Быстрый выбор:</span>
              <button
                v-for="src in POPULAR_SOURCES"
                :key="src"
                type="button"
                class="rounded-md border px-2 py-0.5 text-xs transition-colors"
                :class="form.source === src ? 'bg-fb-blue text-white border-fb-blue' : 'border-fb-line text-fb-secondary hover:bg-fb-canvas'"
                @click="form.source = form.source === src ? '' : src"
              >
                {{ src }}
              </button>
            </div>
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Comments</label>
            <textarea
              v-model="form.comment"
              rows="3"
              placeholder="Add notes or comments about lead..."
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            ></textarea>
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">Status</label>
            <div
              v-if="editingLead && editingLead.stage === 'converted' && editingLead.student_deleted"
              class="rounded-lg border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm font-semibold text-amber-800 flex items-center gap-2"
            >
              <span>⚠️</span> Зачислен (студент был удалён)
            </div>
            <div
              v-else-if="editingLead && editingLead.stage === 'converted'"
              class="rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-2.5 text-sm font-semibold text-emerald-800 flex items-center gap-2"
            >
              <span>✅</span> Зачислен (Студент)
            </div>
            <select
              v-else
              v-model="form.stage"
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            >
              <option v-for="stage in EDITABLE_STAGES" :key="stage.value" :value="stage.value">
                {{ stage.label }}
              </option>
            </select>
          </div>

          <div>
            <label class="mb-2 block text-[15px] font-medium text-fb-secondary">
              Trial lesson date (Дата пробного урока) <span class="text-rose-500">*</span>
            </label>
            <input
              v-model="form.trial_date"
              type="date"
              required
              class="w-full rounded-lg border border-fb-line px-4 py-2.5 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <p v-if="editingLead" class="text-sm text-fb-icon">
            Created: {{ editingLead.created_at.slice(0, 10) }}
          </p>

          <p v-if="formError" class="text-[15px] text-fb-danger">{{ formError }}</p>

          <div class="flex flex-wrap gap-2">
            <button
              type="submit"
              class="rounded-full bg-fb-blue px-8 py-3 text-[16px] font-semibold text-white hover:opacity-90 disabled:opacity-60"
              :disabled="saving"
            >
              {{ saving ? 'Saving…' : editingLead ? 'Save changes' : 'Create lead' }}
            </button>

            <!-- Zombie lead: student was deleted -->
            <div
              v-if="editingLead && editingLead.stage === 'converted' && editingLead.student_deleted"
              class="w-full space-y-2"
            >
              <div class="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                ⚠️ Студент был удалён из базы. Выберите действие:
              </div>
              <div class="flex flex-wrap gap-2">
                <button
                  type="button"
                  class="rounded-full border border-fb-line px-5 py-2.5 text-[14px] font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
                  @click="returnLeadToWork"
                  :disabled="saving"
                >
                  🔄 Вернуть как лида
                </button>
                <button
                  type="button"
                  class="rounded-full bg-emerald-600 px-5 py-2.5 text-[14px] font-semibold text-white hover:bg-emerald-700"
                  @click="openConvertModal"
                >
                  🎓 Восстановить как студента
                </button>
              </div>
            </div>

            <!-- Normal converted lead: student exists -->
            <div
              v-else-if="editingLead && editingLead.stage === 'converted'"
              class="flex flex-wrap items-center gap-2"
            >
              <span class="rounded-full bg-emerald-100 text-emerald-800 px-4 py-3 text-[14px] font-semibold flex items-center gap-1.5 border border-emerald-300">
                <span>✅</span> Уже зачислен как студент
              </span>
              <button
                v-if="editingLead.converted_student_id"
                type="button"
                class="rounded-full bg-fb-blue px-5 py-3 text-[14px] font-semibold text-white hover:opacity-90 flex items-center gap-1.5"
                @click="router.push({ path: '/students', query: { open: String(editingLead.converted_student_id) } })"
              >
                <span>🎓</span> Открыть карточку студента
              </button>
            </div>

            <button
              v-else-if="editingLead && canConvertLead"
              type="button"
              class="rounded-full bg-emerald-600 px-6 py-3 text-[15px] font-semibold text-white hover:bg-emerald-700 disabled:opacity-60 flex items-center gap-1.5"
              @click="openConvertModal"
            >
              <span>🎓</span> Convert to student
            </button>

            <button
              v-if="editingLead && editingLead.is_active"
              type="button"
              class="rounded-full border border-red-300 px-6 py-3 text-[15px] font-medium text-fb-danger hover:bg-red-50 disabled:opacity-60"
              :disabled="archiving"
              @click="archiveLead"
            >
              {{ archiving ? 'В архив…' : 'Скрыть в архив' }}
            </button>

            <button
              v-if="editingLead && !editingLead.is_active"
              type="button"
              class="rounded-full border border-fb-line px-6 py-3 text-[15px] font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue disabled:opacity-60"
              :disabled="saving"
              @click="restoreLead"
            >
              Restore
            </button>
          </div>
        </form>
      </aside>
    </div>

    <!-- Convert to Student Modal -->
    <div v-if="showConvertModal" class="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/50" @click="closeConvertModal" />
      <div class="relative w-full max-w-lg rounded-2xl border border-fb-line bg-fb-card shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-4 bg-fb-canvas">
          <div>
            <h3 class="text-lg font-bold text-fb-text flex items-center gap-2">
              <span>🎓</span> Convert lead to student
            </h3>
            <p class="text-xs text-fb-secondary mt-0.5">
              Переводит лид в статус "Зачислен (Студент)" и создает профиль студента.
            </p>
          </div>
          <button type="button" class="text-2xl leading-none text-fb-icon hover:text-fb-secondary" @click="closeConvertModal">
            ×
          </button>
        </div>

        <form class="flex-1 overflow-y-auto p-6 space-y-4" @submit.prevent="handleConvert">
          <div v-if="editingLead" class="rounded-lg bg-blue-50/70 border border-blue-200 p-3 text-xs flex flex-wrap items-center gap-3">
            <span v-if="editingLead.course_name" class="font-medium text-blue-800">📚 {{ editingLead.course_name }}</span>
            <span v-if="convertForm.level" class="font-semibold text-emerald-800">🎯 {{ convertForm.level }}</span>
            <span v-if="editingLead.branch_name" class="text-amber-800">📍 {{ editingLead.branch_name }}</span>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">First name</label>
              <input
                v-model="convertForm.first_name"
                type="text"
                required
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Last name</label>
              <input
                v-model="convertForm.last_name"
                type="text"
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              />
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Phone</label>
              <input
                v-model="convertForm.phone"
                type="tel"
                required
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Second phone</label>
              <input
                v-model="convertForm.phone2"
                type="tel"
                placeholder="Optional"
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Чей номер</label>
              <input
                v-model="convertForm.phone2_owner"
                list="phone2-owners-lead"
                type="text"
                placeholder="Мама, Отец..."
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              />
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Address</label>
              <input
                v-model="convertForm.address"
                type="text"
                placeholder="e.g. Tashkent, Chilanzar"
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">School (Школа / Номер школы)</label>
              <input
                v-model="convertForm.school"
                type="text"
                placeholder="например, Школа № 178"
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">Level (Уровень знаний / класс)</label>
            <input
              v-model="convertForm.level"
              type="text"
              placeholder="e.g. Beginner, Intermediate..."
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">Comments</label>
            <textarea
              v-model="convertForm.comment"
              rows="2"
              placeholder="Student notes..."
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            ></textarea>
          </div>

          <div class="border-t border-fb-line pt-3 grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Branch *</label>
              <select
                v-model="convertForm.branch_id"
                required
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              >
                <option v-for="b in branches" :key="b.id" :value="b.id">
                  {{ b.name }}
                </option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Group</label>
              <select
                v-model="convertForm.group_id"
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              >
                <option value="">— No group —</option>
                <option v-for="g in filteredConvertGroups" :key="g.id" :value="g.id">
                  {{ g.name }}
                </option>
              </select>
            </div>
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">
              Trial lesson date (Дата старта / пробного урока) <span class="text-rose-500">*</span>
            </label>
            <input
              v-model="convertForm.trial_date"
              type="date"
              required
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            />
          </div>

          <label class="flex items-center gap-2 text-sm text-fb-secondary cursor-pointer">
            <input
              v-model="convertForm.attended_trial"
              type="checkbox"
              class="rounded border-fb-line text-fb-blue focus:ring-fb-blue"
            />
            Был на пробном уроке (отключите, если записался сразу без пробного)
          </label>

          <p v-if="convertError" class="text-sm text-fb-danger">{{ convertError }}</p>

          <div class="flex justify-end gap-2 pt-2 border-t border-fb-line">
            <button
              type="button"
              class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:bg-fb-canvas"
              @click="closeConvertModal"
            >
              Cancel
            </button>
            <button
              type="submit"
              class="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60 flex items-center gap-1.5"
              :disabled="converting"
            >
              <span v-if="converting">Converting…</span>
              <span v-else>Confirm & Convert</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
