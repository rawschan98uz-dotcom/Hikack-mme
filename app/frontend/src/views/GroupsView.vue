<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import FilterDatePicker from '../components/FilterDatePicker.vue';
import FilterMultiSelect from '../components/FilterMultiSelect.vue';
import FilterSelect from '../components/FilterSelect.vue';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';
import { downloadCsv } from '../utils/csvExport';
import {
  hasCreateFlag,
  parseOpenId,
  routeWithoutCreate,
  routeWithoutOpen,
  studentRoute,
  studentsByGroup,
  teacherRoute,
} from '../utils/crossLinks';

interface Branch {
  id: number;
  name: string;
}

interface CourseOption {
  id: number;
  name: string;
  price: number;
}

interface TeacherOption {
  id: number;
  name: string;
}

interface TagOption {
  id: number;
  name: string;
}

interface RoomOption {
  id: number;
  name: string;
  branch_id: number;
}

interface GroupTag {
  id: number;
  name: string;
}

interface GroupStudent {
  id: number;
  full_name: string;
  phone: string;
  status_label: string;
}

interface GroupRow {
  id: number;
  name: string;
  days: number;
  days_label: string;
  status: number;
  status_label: string;
  branch_id: number;
  branch: string;
  course_id: number | null;
  course: { id: number; name: string; price: number } | null;
  teacher_id: number | null;
  teacher: string | null;
  room_id: number | null;
  room: string | null;
  lesson_start_time: string | null;
  lesson_end_time: string | null;
  group_start_date: string | null;
  group_end_date: string | null;
  training_dates: string | null;
  week_of_study: number | null;
  week_of_study_label: string | null;
  students_count: number;
  tags: GroupTag[];
  students?: GroupStudent[];
}

type SortKey =
  | 'name'
  | 'courseName'
  | 'teacher'
  | 'daysText'
  | 'trainingDates'
  | 'weekOfStudy'
  | 'room'
  | 'tagsText'
  | 'students';

interface ColumnDef {
  key: SortKey | 'actions';
  label: string;
  sortable: boolean;
}

const DAYS_OPTIONS = [
  { value: 1, label: 'Odd days' },
  { value: 2, label: 'Even days' },
  { value: 3, label: 'Weekend days' },
  { value: 4, label: 'Every day' },
  { value: 5, label: 'Other' },
] as const;

const STATUS_FILTER_OPTIONS: { value: number; label: string }[] = [
  { value: 2, label: 'Active groups' },
  { value: 3, label: 'Archive' },
];

const STATUS_FORM_OPTIONS = [
  { value: 2, label: 'Active' },
  { value: 3, label: 'Archive' },
] as const;

const TABLE_COLUMNS: ColumnDef[] = [
  { key: 'name', label: 'Group', sortable: true },
  { key: 'courseName', label: 'Course', sortable: true },
  { key: 'teacher', label: 'Teacher', sortable: true },
  { key: 'daysText', label: 'Days', sortable: true },
  { key: 'trainingDates', label: 'Training dates', sortable: true },
  { key: 'weekOfStudy', label: 'Week of study', sortable: true },
  { key: 'room', label: 'Room', sortable: true },
  { key: 'tagsText', label: 'Tags', sortable: true },
  { key: 'students', label: 'Students', sortable: true },
  { key: 'actions', label: 'Actions', sortable: false },
];

const COLUMN_STORAGE_KEY = 'groups-visible-columns';

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();

const rows = ref<GroupRow[]>([]);
const branches = ref<Branch[]>([]);
const courses = ref<CourseOption[]>([]);
const teachers = ref<TeacherOption[]>([]);
const tags = ref<TagOption[]>([]);
const rooms = ref<RoomOption[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingGroup = ref<GroupRow | null>(null);
const detailGroup = ref<GroupRow | null>(null);
const showFiltersPanel = ref(false);
const showColumnsPanel = ref(false);
const sortKey = ref<SortKey>('name');
const sortDir = ref<'asc' | 'desc'>('asc');

const filters = reactive({
  status: 2 as number,
  teacher_ids: [] as number[],
  course_ids: [] as number[],
  days: '' as number | '',
  tag_ids: [] as number[],
  start_date: '',
  end_date: '',
  branch_id: '' as number | '',
  q: '',
});

const form = reactive({
  name: '',
  branch_id: 0,
  course_id: '' as number | '',
  teacher_id: '' as number | '',
  room_id: '' as number | '',
  tag_ids: [] as number[],
  days: 1,
  status: 2,
  lesson_start_time: '',
  lesson_end_time: '',
  group_start_date: '',
  group_end_date: '',
});

const visibleColumns = ref<Record<string, boolean>>(
  TABLE_COLUMNS.reduce<Record<string, boolean>>((acc, column) => {
    acc[column.key] = true;
    return acc;
  }, {}),
);

const quantity = computed(() => rows.value.length);

const teacherFilterOptions = computed(() =>
  teachers.value.map((teacher) => ({ value: teacher.id, label: teacher.name })),
);

const courseFilterOptions = computed(() =>
  courses.value.map((course) => ({ value: course.id, label: course.name })),
);

const tagFilterOptions = computed(() => tags.value.map((tag) => ({ value: tag.id, label: tag.name })));

const daysFilterOptions = computed(() => [
  { value: '', label: 'All days' },
  ...DAYS_OPTIONS.map((option) => ({ value: option.value, label: option.label })),
]);

const filteredRooms = computed(() => {
  if (!form.branch_id) return rooms.value;
  return rooms.value.filter((room) => room.branch_id === form.branch_id);
});

const activeColumns = computed(() =>
  TABLE_COLUMNS.filter((column) => visibleColumns.value[column.key] !== false),
);

const hasActiveFilters = computed(
  () =>
    filters.status !== 2
    || filters.teacher_ids.length > 0
    || filters.course_ids.length > 0
    || filters.days !== ''
    || filters.tag_ids.length > 0
    || Boolean(filters.start_date)
    || Boolean(filters.end_date)
    || filters.branch_id !== ''
    || Boolean(filters.q.trim()),
);

const canExportGroups = computed(() => auth.can(PERM.GROUPS_EXPORT));

const panelTitle = computed(() =>
  editingGroup.value ? 'Edit group' : detailGroup.value ? 'Group details' : 'New group',
);

const isReadOnly = computed(() => Boolean(detailGroup.value && !editingGroup.value));

const tableRows = computed(() => {
  const mapped = rows.value.map((row) => ({
    id: row.id,
    name: row.name,
    courseName: row.course?.name ?? '—',
    teacher: row.teacher ?? '—',
    teacher_id: row.teacher_id,
    daysText: row.days_label,
    trainingDates: row.training_dates ?? '—',
    weekOfStudy: row.week_of_study_label ?? '—',
    room: row.room ?? '—',
    tagsText: row.tags.length ? row.tags.map((tag) => tag.name).join(', ') : '—',
    students: row.students_count,
    statusText: row.status_label,
  }));

  const sorted = [...mapped].sort((left, right) => {
    const key = sortKey.value;
    const leftValue = left[key];
    const rightValue = right[key];
    if (typeof leftValue === 'number' && typeof rightValue === 'number') {
      return sortDir.value === 'asc' ? leftValue - rightValue : rightValue - leftValue;
    }
    const leftText = String(leftValue ?? '').toLowerCase();
    const rightText = String(rightValue ?? '').toLowerCase();
    if (leftText === rightText) return 0;
    const result = leftText > rightText ? 1 : -1;
    return sortDir.value === 'asc' ? result : -result;
  });

  return sorted;
});

function loadColumnPrefs() {
  try {
    const raw = localStorage.getItem(COLUMN_STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as Record<string, boolean>;
    TABLE_COLUMNS.forEach((column) => {
      if (typeof parsed[column.key] === 'boolean') {
        visibleColumns.value[column.key] = parsed[column.key];
      }
    });
  } catch {
    // ignore invalid storage
  }
}

function saveColumnPrefs() {
  localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(visibleColumns.value));
}

function toggleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc';
    return;
  }
  sortKey.value = key;
  sortDir.value = 'asc';
}

function syncFiltersFromRoute() {
  filters.branch_id = route.query.branch_id ? Number(route.query.branch_id) : '';
  if (route.query.teacher_id) {
    filters.teacher_ids = [Number(route.query.teacher_id)];
  }
  filters.q = String(route.query.q ?? '');
}

function resetForm() {
  form.name = '';
  form.branch_id = branches.value[0]?.id ?? 0;
  form.course_id = '';
  form.teacher_id = '';
  form.room_id = '';
  form.tag_ids = [];
  form.days = 1;
  form.status = 2;
  form.lesson_start_time = '';
  form.lesson_end_time = '';
  form.group_start_date = '';
  form.group_end_date = '';
  formError.value = '';
  editingGroup.value = null;
  detailGroup.value = null;
}

function fillForm(group: GroupRow) {
  form.name = group.name;
  form.branch_id = group.branch_id;
  form.course_id = group.course_id ?? '';
  form.teacher_id = group.teacher_id ?? '';
  form.room_id = group.room_id ?? '';
  form.tag_ids = group.tags.map((tag) => tag.id);
  form.days = group.days;
  form.status = group.status;
  form.lesson_start_time = group.lesson_start_time ?? '';
  form.lesson_end_time = group.lesson_end_time ?? '';
  form.group_start_date = group.group_start_date ?? '';
  form.group_end_date = group.group_end_date ?? '';
}

function clearFilters() {
  filters.status = 2;
  filters.teacher_ids = [];
  filters.course_ids = [];
  filters.days = '';
  filters.tag_ids = [];
  filters.start_date = '';
  filters.end_date = '';
  filters.branch_id = '';
  filters.q = '';
  void loadGroups();
}

function openCreatePanel() {
  resetForm();
  showPanel.value = true;
}

async function openDetailPanel(groupId: number) {
  resetForm();
  showPanel.value = true;
  panelLoading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<GroupRow>>(`/groups/${groupId}`);
    detailGroup.value = data.data;
    fillForm(data.data);
  } finally {
    panelLoading.value = false;
  }
}

function startEdit() {
  if (!detailGroup.value) return;
  editingGroup.value = detailGroup.value;
}

function closePanel() {
  showPanel.value = false;
  resetForm();
  if (route.query.open) {
    router.replace(routeWithoutOpen(route));
  }
}

function buildListParams() {
  const params: Record<string, string> = {};
  if (filters.status) params.status = String(filters.status);
  if (filters.teacher_ids.length) params.teacher_ids = filters.teacher_ids.join(',');
  if (filters.course_ids.length) params.course_ids = filters.course_ids.join(',');
  if (filters.days !== '') params.days = String(filters.days);
  if (filters.tag_ids.length) params.tag_ids = filters.tag_ids.join(',');
  if (filters.start_date) params.start_date = filters.start_date;
  if (filters.end_date) params.end_date = filters.end_date;
  if (filters.branch_id !== '') params.branch_id = String(filters.branch_id);
  if (filters.q.trim()) params.q = filters.q.trim();
  return params;
}

async function loadGroups() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<GroupRow[]>>('/groups', {
      params: buildListParams(),
    });
    rows.value = data.data;
  } finally {
    loading.value = false;
  }
}

async function loadOptions() {
  const [branchRes, courseRes, teacherRes, tagRes, roomRes] = await Promise.all([
    client.get<ApiEnvelope<Branch[]>>('/branch'),
    client.get<ApiEnvelope<CourseOption[]>>('/courses'),
    client.get<ApiEnvelope<TeacherOption[]>>('/user', { params: { user_type: 'teacher' } }),
    client.get<ApiEnvelope<TagOption[]>>('/tags'),
    client.get<ApiEnvelope<RoomOption[]>>('/room'),
  ]);
  branches.value = branchRes.data.data;
  courses.value = courseRes.data.data;
  teachers.value = teacherRes.data.data.map((teacher) => ({
    id: teacher.id,
    name: teacher.name,
  }));
  tags.value = tagRes.data.data;
  rooms.value = roomRes.data.data.map((room) => ({
    id: room.id,
    name: room.name,
    branch_id: room.branch_id,
  }));
  if (!form.branch_id && branches.value.length) {
    form.branch_id = branches.value[0].id;
  }
}

function buildPayload() {
  return {
    name: form.name.trim(),
    branch_id: form.branch_id,
    course_id: form.course_id === '' ? null : form.course_id,
    teacher_id: form.teacher_id === '' ? null : form.teacher_id,
    room_id: form.room_id === '' ? null : form.room_id,
    tag_ids: form.tag_ids,
    days: form.days,
    status: form.status,
    lesson_start_time: form.lesson_start_time || null,
    lesson_end_time: form.lesson_end_time || null,
    group_start_date: form.group_start_date || null,
    group_end_date: form.group_end_date || null,
  };
}

async function submitGroup() {
  formError.value = '';
  if (!form.name.trim()) {
    formError.value = 'Enter group name';
    return;
  }
  if (!form.branch_id) {
    formError.value = 'Select a branch';
    return;
  }

  saving.value = true;
  try {
    const payload = buildPayload();
    if (editingGroup.value) {
      await client.patch(`/groups/${editingGroup.value.id}`, payload);
    } else {
      await client.post('/groups', payload);
    }
    closePanel();
    await loadGroups();
  } catch {
    formError.value = editingGroup.value ? 'Could not update group' : 'Could not create group';
  } finally {
    saving.value = false;
  }
}

async function deleteGroup() {
  if (!detailGroup.value) return;
  if (!window.confirm(`Delete group "${detailGroup.value.name}"?`)) return;

  deleting.value = true;
  try {
    await client.delete(`/groups/${detailGroup.value.id}`);
    closePanel();
    await loadGroups();
  } catch {
    window.alert('Could not delete group');
  } finally {
    deleting.value = false;
  }
}

function exportCsv() {
  const columns = activeColumns.value.filter((column) => column.key !== 'actions');
  downloadCsv(
    'groups.csv',
    columns.map((column) => column.label),
    tableRows.value.map((row) =>
      columns.map((column) => row[column.key as SortKey]),
    ),
  );
}

function goStudents(groupId: number) {
  router.push(studentsByGroup(groupId));
}

function goTeacher(group: GroupRow) {
  if (!group.teacher_id) return;
  router.push(teacherRoute(group.teacher_id));
}

function goStudent(studentId: number) {
  router.push(studentRoute(studentId));
}

function goTeacherFromTable(teacherId: number) {
  router.push(teacherRoute(teacherId));
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

watch(
  () => [
    filters.status,
    filters.teacher_ids,
    filters.course_ids,
    filters.days,
    filters.tag_ids,
    filters.start_date,
    filters.end_date,
    filters.branch_id,
    filters.q,
  ],
  () => {
    void loadGroups();
  },
  { deep: true },
);

watch(visibleColumns, saveColumnPrefs, { deep: true });

watch(
  () => route.fullPath,
  async () => {
    syncFiltersFromRoute();
    await loadGroups();
    await maybeOpenFromRoute();
    maybeCreateFromRoute();
  },
);

onMounted(async () => {
  loadColumnPrefs();
  syncFiltersFromRoute();
  try {
    await Promise.all([loadOptions(), loadGroups()]);
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
      <div class="flex flex-wrap items-baseline gap-3">
        <h1>Groups</h1>
        <span class="text-sm text-fb-secondary">Quantity — {{ quantity }}</span>
      </div>
      <button type="button" class="btn-fb-primary uppercase tracking-wide" @click="openCreatePanel">
        Add new
      </button>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <FilterSelect
        v-model="filters.status"
        :options="STATUS_FILTER_OPTIONS"
        placeholder="Active groups"
        class="min-w-[150px]"
      />
      <FilterMultiSelect
        v-model="filters.teacher_ids"
        :options="teacherFilterOptions"
        placeholder="Teachers"
      />
      <FilterMultiSelect
        v-model="filters.course_ids"
        :options="courseFilterOptions"
        placeholder="Courses"
      />
      <FilterSelect v-model="filters.days" :options="daysFilterOptions" placeholder="Days" />
      <FilterMultiSelect v-model="filters.tag_ids" :options="tagFilterOptions" placeholder="Tags" />
      <FilterDatePicker v-model="filters.start_date" placeholder="Start date" />
      <FilterDatePicker v-model="filters.end_date" placeholder="End date" />
      <button
        type="button"
        class="filter-clear-fb"
        :class="{ 'opacity-40': !hasActiveFilters }"
        title="Clear filters"
        :disabled="!hasActiveFilters"
        @click="clearFilters"
      >
        <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
          />
        </svg>
      </button>
    </div>

    <div class="relative flex flex-wrap items-center justify-end gap-2">
      <div class="relative">
        <button type="button" class="groups-toolbar-btn-fb" @click="showFiltersPanel = !showFiltersPanel">
          <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path
              fill-rule="evenodd"
              d="M7.84 1.804A1 1 0 018.82 1h2.36a1 1 0 01.98.804l.331 1.652a6.993 6.993 0 011.929 1.115l1.598-.54a1 1 0 011.186.447l1.18 2.044a1 1 0 01-.205 1.251l-1.267 1.113a7.047 7.047 0 010 2.228l1.267 1.113a1 1 0 01.205 1.251l-1.18 2.044a1 1 0 01-1.186.447l-1.598-.54a6.993 6.993 0 01-1.929 1.115l-.331 1.652a1 1 0 01-.98.804H8.82a1 1 0 01-.98-.804l-.331-1.652a6.993 6.993 0 01-1.929-1.115l-1.598.54a1 1 0 01-1.186-.447l-1.18-2.044a1 1 0 01.205-1.251l1.267-1.113a7.047 7.047 0 010-2.228L2.92 6.398a1 1 0 01-.205-1.251l1.18-2.044a1 1 0 011.186-.447l1.598.54A6.993 6.993 0 017.708 2.14l.331-1.652zM10 13a3 3 0 100-6 3 3 0 000 6z"
              clip-rule="evenodd"
            />
          </svg>
          Filters
        </button>
        <div
          v-if="showFiltersPanel"
          class="absolute right-0 top-[calc(100%+8px)] z-30 w-72 rounded-xl border border-fb-line bg-fb-card p-4 shadow-lg"
        >
          <label class="mb-1 block text-xs font-medium text-fb-secondary">Branch</label>
          <select v-model="filters.branch_id" class="mb-3 w-full rounded-lg border border-fb-line px-3 py-2 text-sm">
            <option value="">All branches</option>
            <option v-for="branch in branches" :key="branch.id" :value="branch.id">
              {{ branch.name }}
            </option>
          </select>
          <label class="mb-1 block text-xs font-medium text-fb-secondary">Search</label>
          <input
            v-model="filters.q"
            type="search"
            placeholder="Group or course name"
            class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm"
          />
        </div>
      </div>

      <div class="relative">
        <button type="button" class="groups-toolbar-btn-fb" @click="showColumnsPanel = !showColumnsPanel">
          <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path
              fill-rule="evenodd"
              d="M7.84 1.804A1 1 0 018.82 1h2.36a1 1 0 01.98.804l.331 1.652a6.993 6.993 0 011.929 1.115l1.598-.54a1 1 0 011.186.447l1.18 2.044a1 1 0 01-.205 1.251l-1.267 1.113a7.047 7.047 0 010 2.228l1.267 1.113a1 1 0 01.205 1.251l-1.18 2.044a1 1 0 01-1.186.447l-1.598-.54a6.993 6.993 0 01-1.929 1.115l-.331 1.652a1 1 0 01-.98.804H8.82a1 1 0 01-.98-.804l-.331-1.652a6.993 6.993 0 01-1.929-1.115l-1.598.54a1 1 0 01-1.186-.447l-1.18-2.044a1 1 0 01.205-1.251l1.267-1.113a7.047 7.047 0 010-2.228L2.92 6.398a1 1 0 01-.205-1.251l1.18-2.044a1 1 0 011.186-.447l1.598.54A6.993 6.993 0 017.708 2.14l.331-1.652zM10 13a3 3 0 100-6 3 3 0 000 6z"
              clip-rule="evenodd"
            />
          </svg>
          Columns
        </button>
        <div
          v-if="showColumnsPanel"
          class="absolute right-0 top-[calc(100%+8px)] z-30 w-56 rounded-xl border border-fb-line bg-fb-card p-3 shadow-lg"
        >
          <label
            v-for="column in TABLE_COLUMNS.filter((item) => item.key !== 'actions')"
            :key="column.key"
            class="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-fb-hover"
          >
            <input v-model="visibleColumns[column.key]" type="checkbox" class="rounded border-fb-line text-fb-blue" />
            {{ column.label }}
          </label>
        </div>
      </div>

      <button
        v-if="canExportGroups"
        type="button"
        class="groups-toolbar-btn-fb"
        title="Export"
        @click="exportCsv"
      >
        <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            d="M10.75 2.75a.75.75 0 00-1.5 0v8.614L6.295 8.235a.75.75 0 10-1.09 1.03l4.25 4.5a.75.75 0 001.09 0l4.25-4.5a.75.75 0 00-1.09-1.03l-2.955 3.129V2.75z"
          />
          <path
            d="M3.5 12.75a.75.75 0 00-1.5 0v2.5A2.75 2.75 0 004.75 18h10.5A2.75 2.75 0 0018 15.25v-2.5a.75.75 0 00-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5z"
          />
        </svg>
      </button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!tableRows.length" class="p-8 text-center text-fb-icon">No groups</div>
      <div v-else class="overflow-x-auto">
        <table class="table-fb min-w-full">
          <thead>
            <tr>
              <th v-for="column in activeColumns" :key="column.key" class="whitespace-nowrap">
                <button
                  v-if="column.sortable"
                  type="button"
                  class="sortable-th-fb"
                  @click="toggleSort(column.key as SortKey)"
                >
                  {{ column.label }}
                  <span class="text-xs text-fb-icon">
                    {{ sortKey === column.key ? (sortDir === 'asc' ? '↑' : '↓') : '↕' }}
                  </span>
                </button>
                <span v-else>{{ column.label }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in tableRows"
              :key="row.id"
              class="table-row-fb cursor-pointer"
              @click="openDetailPanel(row.id)"
            >
              <td v-if="visibleColumns.name !== false" class="font-medium text-fb-text">{{ row.name }}</td>
              <td v-if="visibleColumns.courseName !== false">{{ row.courseName }}</td>
              <td v-if="visibleColumns.teacher !== false">
                <button
                  v-if="row.teacher_id"
                  type="button"
                  class="text-fb-blue hover:underline"
                  @click.stop="goTeacherFromTable(row.teacher_id)"
                >
                  {{ row.teacher }}
                </button>
                <span v-else>{{ row.teacher }}</span>
              </td>
              <td v-if="visibleColumns.daysText !== false">{{ row.daysText }}</td>
              <td v-if="visibleColumns.trainingDates !== false">{{ row.trainingDates }}</td>
              <td v-if="visibleColumns.weekOfStudy !== false">{{ row.weekOfStudy }}</td>
              <td v-if="visibleColumns.room !== false">{{ row.room }}</td>
              <td v-if="visibleColumns.tagsText !== false">{{ row.tagsText }}</td>
              <td v-if="visibleColumns.students !== false">{{ row.students }}</td>
              <td v-if="visibleColumns.actions !== false" @click.stop>
                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    class="text-sm text-fb-blue hover:underline"
                    @click="openDetailPanel(row.id)"
                  >
                    Open
                  </button>
                  <button
                    type="button"
                    class="text-sm text-fb-blue hover:underline"
                    @click="goStudents(row.id)"
                  >
                    Students
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closePanel" />
      <div class="drawer-panel-fb max-w-lg">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-4">
          <h2 class="text-lg font-semibold text-fb-text">{{ panelTitle }}</h2>
          <button type="button" class="text-fb-icon hover:text-fb-secondary" @click="closePanel">✕</button>
        </div>

        <div v-if="panelLoading" class="flex-1 p-6 text-fb-secondary">Loading…</div>

        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitGroup">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Group name</label>
              <input
                v-model="form.name"
                type="text"
                required
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none read-only:bg-fb-canvas"
              />
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
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Course</label>
              <select
                v-model="form.course_id"
                :disabled="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option value="">— No course —</option>
                <option v-for="course in courses" :key="course.id" :value="course.id">
                  {{ course.name }}
                </option>
              </select>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Teacher</label>
              <select
                v-model="form.teacher_id"
                :disabled="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option value="">— No teacher —</option>
                <option v-for="teacher in teachers" :key="teacher.id" :value="teacher.id">
                  {{ teacher.name }}
                </option>
              </select>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Room</label>
              <select
                v-model="form.room_id"
                :disabled="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option value="">— No room —</option>
                <option v-for="room in filteredRooms" :key="room.id" :value="room.id">
                  {{ room.name }}
                </option>
              </select>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Tags</label>
              <div class="flex flex-wrap gap-2 rounded-lg border border-fb-line p-3">
                <label
                  v-for="tag in tags"
                  :key="tag.id"
                  class="inline-flex items-center gap-2 rounded-md bg-fb-canvas px-2 py-1 text-sm"
                >
                  <input
                    v-model="form.tag_ids"
                    type="checkbox"
                    :value="tag.id"
                    :disabled="isReadOnly"
                    class="rounded border-fb-line text-fb-blue"
                  />
                  {{ tag.name }}
                </label>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">Days</label>
                <select
                  v-model="form.days"
                  :disabled="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
                >
                  <option v-for="option in DAYS_OPTIONS" :key="option.value" :value="option.value">
                    {{ option.label }}
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
                  <option v-for="option in STATUS_FORM_OPTIONS" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">Start time</label>
                <input
                  v-model="form.lesson_start_time"
                  type="time"
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">End time</label>
                <input
                  v-model="form.lesson_end_time"
                  type="time"
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas"
                />
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">Training start</label>
                <input
                  v-model="form.group_start_date"
                  type="date"
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-fb-secondary">Training end</label>
                <input
                  v-model="form.group_end_date"
                  type="date"
                  :readonly="isReadOnly"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas"
                />
              </div>
            </div>

            <div v-if="detailGroup?.teacher_id" class="rounded-lg border border-fb-line bg-fb-canvas px-4 py-3 text-sm">
              <span class="text-fb-secondary">Teacher: </span>
              <span class="font-medium text-fb-text">{{ detailGroup.teacher }}</span>
              <button type="button" class="ml-3 text-fb-blue hover:underline" @click="goTeacher(detailGroup)">
                Open teacher →
              </button>
            </div>

            <div v-if="detailGroup?.students?.length" class="rounded-lg border border-fb-line p-4">
              <div class="mb-3 flex items-center justify-between">
                <h3 class="text-sm font-semibold text-fb-secondary">
                  Students ({{ detailGroup.students.length }})
                </h3>
                <button
                  type="button"
                  class="text-sm font-medium text-fb-blue hover:underline"
                  @click="goStudents(detailGroup.id)"
                >
                  All students →
                </button>
              </div>
              <ul class="divide-y divide-fb-line">
                <li
                  v-for="student in detailGroup.students"
                  :key="student.id"
                  class="flex items-center justify-between py-2 text-sm"
                >
                  <button
                    type="button"
                    class="text-left font-medium text-fb-blue hover:underline"
                    @click="goStudent(student.id)"
                  >
                    {{ student.full_name }}
                  </button>
                  <span class="text-fb-secondary">{{ student.status_label }}</span>
                </li>
              </ul>
            </div>

            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>

          <div class="flex flex-wrap gap-2 border-t border-fb-line px-6 py-4">
            <template v-if="isReadOnly">
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
                @click="deleteGroup"
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
                {{ saving ? 'Saving…' : editingGroup ? 'Save' : 'Create' }}
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
  </div>
</template>
