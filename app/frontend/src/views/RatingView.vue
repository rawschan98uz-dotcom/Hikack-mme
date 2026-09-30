<script setup lang="ts">
import { todayIso } from '../utils/dates';
import { computed, onMounted, reactive, ref , watch} from 'vue';
import { useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { useAuthStore } from '../stores/auth';
import { groupRoute, studentRoute, teacherRoute } from '../utils/crossLinks';
import { downloadCsv } from '../utils/csvExport';

interface Branch {
  id: number;
  name: string;
}

interface GroupOption {
  id: number;
  name: string;
  branch_id: number;
  course_id?: number | null;
  teacher_id?: number | null;
}

interface TeacherOption {
  id: number;
  name: string;
}

interface CourseOption {
  id: number;
  name: string;
}

/** One student of a group as the grading sheet sees them today (GET /scores/sheet). */
interface SheetStudent {
  student_id: number;
  name: string;
  last_grade: number | null;
  /** false = absent today in the attendance, or in a freeze: no grade today */
  can_grade: boolean;
  reason_label: string;
}

interface LessonDate {
  date: string;
  label: string;
}

interface SheetPayload {
  date: string | null;
  lesson_dates: LessonDate[];
  students: SheetStudent[];
}

/** Every grade of a student; the rating shows only the latest one. */
interface HistoryRow {
  id: number;
  date: string;
  group: string;
  course: string;
  grade: number;
  graded_by: string;
  corrected: boolean;
  corrected_at: string | null;
  corrected_by: string;
}

interface RatingSummary {
  total: number;
  avg_grade: number;
  passed_count: number;
  failed_count: number;
  pass_rate: number;
  pass_score: number;
  max_scale: number;
}

interface RatingRow {
  id: number;
  no: number;
  rank_in_group: number;
  student_id: number;
  name: string;
  group_id: number;
  group: string;
  course_id: number | null;
  course: string;
  teacher_id: number | null;
  teacher: string;
  branch_id: number;
  branch: string;
  grade: number;
  rank: number;
  is_passed: boolean;
  pass_score: number;
  max_scale: number;
  updated_at: string;
}

interface GroupScoreRow {
  group_id: number;
  group_name: string;
  branch_id: number;
  branch_name: string;
  course_id: number | null;
  course_name: string;
  teacher_id: number | null;
  teacher_name: string;
  enrolled_count: number;
  graded_count: number;
  passed_count: number;
  avg_grade: number;
  pass_rate: number;
  pass_score: number;
  max_scale: number;
  rank: number;
}

interface BulkStudentItem {
  student_id: number;
  student_name: string;
  /** '' = not graded (nothing is saved for this student) */
  grade: number | '';
  last_grade: number | null;
  can_grade: boolean;
  reason_label: string;
}

const router = useRouter();

const rows = ref<RatingRow[]>([]);
const groupScores = ref<GroupScoreRow[]>([]);
const summary = ref<RatingSummary>({
  total: 0,
  avg_grade: 0,
  passed_count: 0,
  failed_count: 0,
  pass_rate: 0,
  pass_score: 70,
  max_scale: 100,
});

const branches = ref<Branch[]>([]);
const groups = ref<GroupOption[]>([]);
const teachers = ref<TeacherOption[]>([]);
const courses = ref<CourseOption[]>([]);
/** Students of the group chosen in "Add grade" (only that group, loaded after picking it). */
const panelStudents = ref<SheetStudent[]>([]);
const panelStudentsLoading = ref(false);
/** The lesson the grade is for: one of the group's lessons of the last 7 days (newest by default). */
const panelDate = ref('');
const panelLessonDates = ref<LessonDate[]>([]);
const history = ref<HistoryRow[]>([]);

const loading = ref(true);
const groupsLoading = ref(false);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const activeTab = ref<'table' | 'groups' | 'analytics'>('table');
const editingScore = ref<RatingRow | null>(null);
const detailScore = ref<RatingRow | null>(null);

// Bulk modal state
const showBulkModal = ref(false);
const bulkGroupId = ref<number | ''>('');
const bulkStudents = ref<BulkStudentItem[]>([]);
const bulkLoading = ref(false);
const bulkSaving = ref(false);
const bulkError = ref('');
const bulkDate = ref('');
const bulkLessonDates = ref<LessonDate[]>([]);

const filters = reactive({
  branch_id: '',
  group_id: '',
  teacher_id: '',
  course_id: '',
  status: '', // '' | 'passed' | 'failed' | 'top10'
  q: '',
});

const form = reactive({
  student_id: '' as number | '',
  group_id: '' as number | '',
  /** '' until the teacher types it (0 is a real grade, not "not graded") */
  grade: '' as number | '',
});

const panelTitle = computed(() => {
  if (editingScore.value) return 'Edit grade';
  if (detailScore.value) return 'Rating details';
  return 'Add grade';
});

const isReadOnly = computed(() => Boolean(detailScore.value && !editingScore.value));

const maxGrade = computed(() => {
  const highest = Math.max(...rows.value.map((row) => row.grade), 1);
  return Math.max(highest, summary.value.max_scale);
});

const topThree = computed(() => rows.value.slice(0, 3));

/** "Add grade": the students of the chosen group, loaded for that group only. */
async function loadPanelStudents(keepDate = false) {
  panelStudents.value = [];
  form.student_id = '';
  if (!keepDate) {
    panelDate.value = '';
    panelLessonDates.value = [];
  }
  if (!form.group_id) return;
  panelStudentsLoading.value = true;
  try {
    const params: Record<string, string | number> = { group_id: form.group_id };
    if (panelDate.value) params.date = panelDate.value;
    const { data } = await client.get<ApiEnvelope<SheetPayload>>('/scores/sheet', { params });
    panelLessonDates.value = data.data.lesson_dates;
    panelDate.value = data.data.date ?? '';
    panelStudents.value = data.data.students;
  } catch {
    formError.value = 'Не удалось загрузить учеников группы';
  } finally {
    panelStudentsLoading.value = false;
  }
}

// Analytics brackets
const brackets = computed(() => {
  const max = summary.value.max_scale || 100;
  const pass = summary.value.pass_score || 70;
  const tier1Threshold = max * 0.9;
  const tier2Threshold = max * 0.75;

  let tier1 = 0; // >= 90%
  let tier2 = 0; // 75-89%
  let tier3 = 0; // pass to 74%
  let tier4 = 0; // < pass

  rows.value.forEach((r) => {
    if (r.grade >= tier1Threshold) tier1++;
    else if (r.grade >= tier2Threshold) tier2++;
    else if (r.grade >= pass) tier3++;
    else tier4++;
  });

  const total = rows.value.length || 1;
  return [
    { label: `Excellent (≥ ${Math.round(tier1Threshold)})`, count: tier1, percent: Math.round((tier1 / total) * 100), color: 'bg-emerald-500' },
    { label: `Good (${Math.round(tier2Threshold)}–${Math.round(tier1Threshold) - 1})`, count: tier2, percent: Math.round((tier2 / total) * 100), color: 'bg-blue-500' },
    { label: `Passing (${pass}–${Math.round(tier2Threshold) - 1})`, count: tier3, percent: Math.round((tier3 / total) * 100), color: 'bg-amber-500' },
    { label: `Needs Attention (< ${pass})`, count: tier4, percent: Math.round((tier4 / total) * 100), color: 'bg-red-500' },
  ];
});

function resetForm() {
  form.student_id = '';
  // The teacher picks the group first; then only its students are listed
  form.group_id = '';
  form.grade = '';
  formError.value = '';
  editingScore.value = null;
  detailScore.value = null;
  panelStudents.value = [];
  panelDate.value = '';
  panelLessonDates.value = [];
  history.value = [];
}

function fillForm(score: RatingRow) {
  form.student_id = score.student_id;
  form.group_id = score.group_id;
  form.grade = score.grade;
}

async function loadRating() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.branch_id) params.branch_id = filters.branch_id;
    if (filters.group_id) params.group_id = filters.group_id;
    if (filters.teacher_id) params.teacher_id = filters.teacher_id;
    if (filters.course_id) params.course_id = filters.course_id;
    if (filters.status) params.status = filters.status;
    if (filters.q.trim()) params.q = filters.q.trim();

    const { data } = await client.get<ApiEnvelope<any>>('/scores/branch', { params });
    if (data.data && Array.isArray(data.data)) {
      rows.value = data.data;
    } else if (data.data && data.data.rows) {
      rows.value = data.data.rows;
      if (data.data.summary) {
        summary.value = data.data.summary;
      }
    } else {
      rows.value = [];
    }
  } finally {
    loading.value = false;
  }
}

async function loadGroupScores() {
  groupsLoading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.branch_id) params.branch_id = filters.branch_id;
    if (filters.course_id) params.course_id = filters.course_id;
    if (filters.teacher_id) params.teacher_id = filters.teacher_id;

    const { data } = await client.get<ApiEnvelope<GroupScoreRow[]>>('/scores/groups', { params });
    groupScores.value = data.data || [];
  } finally {
    groupsLoading.value = false;
  }
}

// A teacher works only with own groups: no branch / teacher / course filters and no export
const auth = useAuthStore();
const isTeacher = computed(() => auth.role === 'teacher');

async function loadOptions() {
  // Teachers may not read the teacher and course lists; asking for them made the whole
  // Promise.all fail, so "Add grade" and the grading sheet had empty group/student lists.
  const empty = { data: { data: [] as never[] } };
  const [branchRes, groupRes, teacherRes, courseRes] = await Promise.all([
    isTeacher.value ? Promise.resolve(empty) : client.get<ApiEnvelope<Branch[]>>('/branch'),
    client.get<ApiEnvelope<GroupOption[]>>('/groups'),
    isTeacher.value ? Promise.resolve(empty) : client.get<ApiEnvelope<TeacherOption[]>>('/user', { params: { user_type: 'teacher' } }),
    isTeacher.value ? Promise.resolve(empty) : client.get<ApiEnvelope<CourseOption[]>>('/courses'),
  ]);

  branches.value = branchRes.data.data;
  groups.value = groupRes.data.data.map((group) => ({
    id: group.id,
    name: group.name,
    branch_id: group.branch_id,
    course_id: group.course_id,
    teacher_id: group.teacher_id,
  }));
  teachers.value = teacherRes.data.data.map((t) => ({ id: t.id, name: t.name }));
  courses.value = courseRes.data.data.map((c) => ({ id: c.id, name: c.name }));
}

function resetFilters() {
  filters.branch_id = '';
  filters.group_id = '';
  filters.teacher_id = '';
  filters.course_id = '';
  filters.status = '';
  filters.q = '';
  loadRating();
  if (activeTab.value === 'groups') {
    loadGroupScores();
  }
}

function onTabChange(tab: 'table' | 'groups' | 'analytics') {
  activeTab.value = tab;
  if (tab === 'groups' && !groupScores.value.length) {
    loadGroupScores();
  }
}

function openCreatePanel() {
  resetForm();
  showPanel.value = true;
}

async function openDetailPanel(scoreId: number) {
  resetForm();
  showPanel.value = true;
  panelLoading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<RatingRow>>(`/scores/${scoreId}`);
    detailScore.value = data.data;
    fillForm(data.data);
    await loadHistory(data.data.student_id);
  } finally {
    panelLoading.value = false;
  }
}

/** All grades of the student; the rating itself shows only the latest one. */
async function loadHistory(studentId: number) {
  try {
    const { data } = await client.get<ApiEnvelope<HistoryRow[]>>('/scores/history', { params: { student_id: studentId } });
    history.value = data.data;
  } catch {
    history.value = [];
  }
}

function formatDay(iso: string | null) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

function startEdit() {
  if (!detailScore.value) return;
  editingScore.value = detailScore.value;
}

function closePanel() {
  showPanel.value = false;
  resetForm();
}

async function submitScore() {
  formError.value = '';
  if (!form.student_id || !form.group_id) {
    formError.value = 'Select student and group';
    return;
  }
  const maxScale = summary.value.max_scale || 100;
  if (form.grade === '' || !Number.isInteger(form.grade) || form.grade < 0 || form.grade > maxScale) {
    formError.value = `Оценка — целое число от 0 до ${maxScale}`;
    return;
  }

  saving.value = true;
  try {
    if (editingScore.value) {
      // Only the points can be changed (student and group of a grade are fixed)
      await client.patch(`/scores/${editingScore.value.id}`, { grade: form.grade });
    } else {
      await client.post('/scores/branch', {
        student_id: form.student_id,
        group_id: form.group_id,
        grade: form.grade,
        lesson_date: panelDate.value,
      });
    }
    closePanel();
    await Promise.all([loadRating(), loadGroupScores()]);
  } catch (err: any) {
    formError.value =
      err.response?.data?.message || (editingScore.value ? 'Could not update grade' : 'Could not add grade');
  } finally {
    saving.value = false;
  }
}

async function deleteScore() {
  if (!detailScore.value) return;
  if (!window.confirm(`Delete grade for ${detailScore.value.name}?`)) return;

  deleting.value = true;
  try {
    await client.delete(`/scores/${detailScore.value.id}`);
    closePanel();
    await Promise.all([loadRating(), loadGroupScores()]);
  } catch {
    window.alert('Could not delete grade');
  } finally {
    deleting.value = false;
  }
}

// Bulk Group Grading Modal
async function openBulkModal(preselectedGroupId?: number) {
  showBulkModal.value = true;
  bulkGroupId.value = preselectedGroupId || (groups.value[0]?.id ?? '');
  bulkDate.value = '';
  bulkError.value = '';
  await loadBulkStudents();
}

/** The group changed: back to its newest lesson. */
function onBulkGroupChange() {
  bulkDate.value = '';
  loadBulkStudents();
}

async function loadBulkStudents() {
  if (!bulkGroupId.value) {
    bulkStudents.value = [];
    return;
  }
  bulkLoading.value = true;
  bulkError.value = '';
  try {
    // Only students who study in the group; absent that day / frozen come with can_grade = false
    const params: Record<string, string | number> = { group_id: bulkGroupId.value };
    if (bulkDate.value) params.date = bulkDate.value;
    const { data } = await client.get<ApiEnvelope<SheetPayload>>('/scores/sheet', { params });
    bulkLessonDates.value = data.data.lesson_dates;
    bulkDate.value = data.data.date ?? '';
    bulkStudents.value = data.data.students.map((st) => ({
      student_id: st.student_id,
      student_name: st.name,
      grade: '',
      last_grade: st.last_grade,
      can_grade: st.can_grade,
      reason_label: st.reason_label,
    }));
  } catch {
    bulkError.value = 'Failed to load group students';
  } finally {
    bulkLoading.value = false;
  }
}

async function submitBulkScores() {
  if (!bulkGroupId.value) return;
  const maxScale = summary.value.max_scale || 100;
  // Empty box = not graded: only the typed grades are sent
  const graded = bulkStudents.value.filter((s) => s.can_grade && s.grade !== '');
  if (!graded.length) {
    bulkError.value = 'Не введено ни одной оценки.';
    return;
  }
  const wrong = graded.find((s) => !Number.isInteger(s.grade) || Number(s.grade) < 0 || Number(s.grade) > maxScale);
  if (wrong) {
    bulkError.value = `${wrong.student_name}: оценка — целое число от 0 до ${maxScale}`;
    return;
  }
  bulkSaving.value = true;
  bulkError.value = '';
  try {
    const payload = {
      group_id: bulkGroupId.value,
      lesson_date: bulkDate.value,
      items: graded.map((s) => ({ student_id: s.student_id, grade: s.grade })),
    };
    const { data } = await client.post<ApiEnvelope<{ saved_count: number; skipped?: { reason: string }[] }>>(
      '/scores/bulk',
      payload,
    );
    await Promise.all([loadRating(), loadGroupScores()]);
    const skipped = data.data.skipped ?? [];
    if (skipped.length) {
      // Keep the sheet open and say who was not saved and why
      bulkError.value = `Сохранено: ${data.data.saved_count}. Не сохранено: ${skipped.map((s) => s.reason).join('; ')}`;
      await loadBulkStudents();
    } else {
      showBulkModal.value = false;
    }
  } catch (err: any) {
    bulkError.value = err.response?.data?.message || 'Failed to save group grades';
  } finally {
    bulkSaving.value = false;
  }
}

// CSV Export
function exportRatingCsv() {
  const headers = [
    'Rank',
    'Rank in Group',
    'Student',
    'Group',
    'Course',
    'Teacher',
    'Branch',
    'Grade',
    'Max Scale',
    'Status',
    'Pass Score',
  ];
  const exportRows = rows.value.map((r) => [
    r.no,
    r.rank_in_group || r.rank,
    r.name,
    r.group,
    r.course || '—',
    r.teacher || '—',
    r.branch,
    r.grade,
    summary.value.max_scale,
    r.is_passed ? 'Passed' : 'Needs Retake',
    summary.value.pass_score,
  ]);
  const dateStr = todayIso();
  downloadCsv(`Rating_Report_${dateStr}.csv`, headers, exportRows);
}

function goStudent(score: RatingRow | { student_id: number }) {
  if (isTeacher.value) return; // student cards are not a teacher page
  router.push(studentRoute(score.student_id));
}

function goGroup(score: RatingRow | { group_id: number }) {
  router.push(groupRoute(score.group_id));
}

function goTeacher(teacherId?: number | null) {
  if (teacherId && !isTeacher.value) router.push(teacherRoute(teacherId));
}

function medalClass(no: number) {
  if (no === 1) return 'text-amber-500 font-bold';
  if (no === 2) return 'text-slate-400 font-bold';
  if (no === 3) return 'text-amber-700 font-bold';
  return 'text-fb-secondary';
}

function medalIcon(no: number) {
  if (no === 1) return '🥇';
  if (no === 2) return '🥈';
  if (no === 3) return '🥉';
  return '';
}

onMounted(async () => {
  try {
    await Promise.all([loadOptions(), loadRating(), loadGroupScores()]);
  } finally {
    loading.value = false;
  }
});

let searchDebounce: ReturnType<typeof setTimeout> | null = null;
watch(
  () => filters.q,
  (newQ, oldQ) => {
    if (newQ === oldQ) return;
    if (searchDebounce) clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      loadRating();
    }, 400);
  },
);

</script>

<template>
  <div class="space-y-6">
    <!-- Header & Action Buttons -->
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-fb-text">Rating & Academic Leaderboard</h1>
        <p class="text-sm text-fb-secondary">
          Student performance, group statistics, and grading reports
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button
          v-if="!isTeacher"
          type="button"
          class="flex items-center gap-1.5 rounded-lg border border-fb-line bg-fb-card px-3.5 py-2 text-sm font-medium text-fb-text shadow-sm hover:border-fb-blue hover:text-fb-blue"
          @click="exportRatingCsv"
        >
          <span>📥</span> Export CSV
        </button>
        <button
          type="button"
          class="flex items-center gap-1.5 rounded-lg border border-emerald-600 bg-emerald-50 px-3.5 py-2 text-sm font-medium text-emerald-700 shadow-sm hover:bg-emerald-100"
          @click="openBulkModal()"
        >
          <span>📝</span> Group Grading Sheet
        </button>
        <button
          type="button"
          class="flex items-center gap-1.5 rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-fb-blue-dark"
          @click="openCreatePanel"
        >
          <span>+</span> Add grade
        </button>
      </div>
    </div>

    <!-- KPI Summary Cards -->
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div class="rounded-xl border border-fb-line bg-fb-card p-4 shadow-sm">
        <div class="flex items-center justify-between">
          <p class="text-xs font-semibold uppercase tracking-wider text-fb-secondary">Total Assessed</p>
          <span class="text-base">🎓</span>
        </div>
        <p class="mt-2 text-2xl font-bold text-fb-text">{{ summary.total }}</p>
        <p class="mt-1 text-xs text-fb-secondary">Rated students in view</p>
      </div>

      <div class="rounded-xl border border-blue-200 bg-blue-50/40 p-4 shadow-sm">
        <div class="flex items-center justify-between">
          <p class="text-xs font-semibold uppercase tracking-wider text-blue-700">Average Grade</p>
          <span class="text-base">📈</span>
        </div>
        <p class="mt-2 text-2xl font-bold text-blue-900">
          {{ summary.avg_grade }} <span class="text-sm font-normal text-blue-600">/ {{ summary.max_scale }}</span>
        </p>
        <div class="mt-1.5 h-1.5 w-full rounded-full bg-blue-100">
          <div
            class="h-1.5 rounded-full bg-blue-600"
            :style="{ width: `${Math.min(100, (summary.avg_grade / (summary.max_scale || 100)) * 100)}%` }"
          />
        </div>
      </div>

      <div class="rounded-xl border border-emerald-200 bg-emerald-50/40 p-4 shadow-sm">
        <div class="flex items-center justify-between">
          <p class="text-xs font-semibold uppercase tracking-wider text-emerald-700">Passed</p>
          <span class="text-base">✅</span>
        </div>
        <p class="mt-2 text-2xl font-bold text-emerald-900">
          {{ summary.passed_count }} <span class="text-sm font-normal text-emerald-600">({{ summary.pass_rate }}%)</span>
        </p>
        <p class="mt-1 text-xs text-emerald-700">Threshold: ≥ {{ summary.pass_score }} pts</p>
      </div>

      <div
        class="rounded-xl border p-4 shadow-sm"
        :class="summary.failed_count > 0 ? 'border-red-200 bg-red-50/40' : 'border-fb-line bg-fb-card'"
      >
        <div class="flex items-center justify-between">
          <p
            class="text-xs font-semibold uppercase tracking-wider"
            :class="summary.failed_count > 0 ? 'text-red-700' : 'text-fb-secondary'"
          >
            Needs Retake
          </p>
          <span class="text-base">⚠️</span>
        </div>
        <p
          class="mt-2 text-2xl font-bold"
          :class="summary.failed_count > 0 ? 'text-red-900' : 'text-fb-text'"
        >
          {{ summary.failed_count }}
        </p>
        <p class="mt-1 text-xs text-fb-secondary">Below passing grade</p>
      </div>
    </div>

    <!-- Top 3 Podium Cards (when records exist) -->
    <div v-if="topThree.length > 0 && !loading" class="rounded-2xl border border-fb-line bg-fb-card p-5 shadow-sm">
      <div class="mb-4 flex items-center justify-between">
        <h2 class="text-base font-bold text-fb-text">🏆 Academic Top Performers</h2>
        <span class="text-xs font-medium text-fb-secondary">Based on current filter</span>
      </div>
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <!-- 1st Place -->
        <div
          v-if="topThree[0]"
          class="relative flex cursor-pointer items-center justify-between rounded-xl border-2 border-amber-400 bg-amber-50/40 p-4 transition-transform hover:-translate-y-0.5 hover:shadow-md"
          @click="openDetailPanel(topThree[0].id)"
        >
          <div class="flex items-center gap-3">
            <span class="text-3xl">🥇</span>
            <div>
              <p class="text-xs font-bold uppercase tracking-wider text-amber-700">1st Place · Champion</p>
              <p class="text-base font-bold text-fb-text">{{ topThree[0].name }}</p>
              <p class="text-xs text-fb-secondary">{{ topThree[0].group }} · {{ topThree[0].branch }}</p>
            </div>
          </div>
          <div class="text-right">
            <span class="text-2xl font-black text-amber-600">{{ topThree[0].grade }}</span>
            <p class="text-[10px] text-fb-secondary">/ {{ topThree[0].max_scale }} pts</p>
          </div>
        </div>

        <!-- 2nd Place -->
        <div
          v-if="topThree[1]"
          class="relative flex cursor-pointer items-center justify-between rounded-xl border border-slate-300 bg-slate-50/60 p-4 transition-transform hover:-translate-y-0.5 hover:shadow-md"
          @click="openDetailPanel(topThree[1].id)"
        >
          <div class="flex items-center gap-3">
            <span class="text-3xl">🥈</span>
            <div>
              <p class="text-xs font-bold uppercase tracking-wider text-slate-600">2nd Place · Runner-up</p>
              <p class="text-base font-bold text-fb-text">{{ topThree[1].name }}</p>
              <p class="text-xs text-fb-secondary">{{ topThree[1].group }} · {{ topThree[1].branch }}</p>
            </div>
          </div>
          <div class="text-right">
            <span class="text-2xl font-black text-slate-700">{{ topThree[1].grade }}</span>
            <p class="text-[10px] text-fb-secondary">/ {{ topThree[1].max_scale }} pts</p>
          </div>
        </div>

        <!-- 3rd Place -->
        <div
          v-if="topThree[2]"
          class="relative flex cursor-pointer items-center justify-between rounded-xl border border-amber-700/30 bg-amber-50/20 p-4 transition-transform hover:-translate-y-0.5 hover:shadow-md"
          @click="openDetailPanel(topThree[2].id)"
        >
          <div class="flex items-center gap-3">
            <span class="text-3xl">🥉</span>
            <div>
              <p class="text-xs font-bold uppercase tracking-wider text-amber-800">3rd Place · Finalist</p>
              <p class="text-base font-bold text-fb-text">{{ topThree[2].name }}</p>
              <p class="text-xs text-fb-secondary">{{ topThree[2].group }} · {{ topThree[2].branch }}</p>
            </div>
          </div>
          <div class="text-right">
            <span class="text-2xl font-black text-amber-800">{{ topThree[2].grade }}</span>
            <p class="text-[10px] text-fb-secondary">/ {{ topThree[2].max_scale }} pts</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Tabs Navigation -->
    <div class="flex gap-4 border-b border-fb-line">
      <button
        type="button"
        class="-mb-px flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-semibold transition-colors"
        :class="activeTab === 'table'
          ? 'border-fb-blue text-fb-blue'
          : 'border-transparent text-fb-secondary hover:text-fb-text'"
        @click="onTabChange('table')"
      >
        <span>👨‍🎓</span> Students Rating
        <span class="rounded-full bg-fb-canvas px-2 py-0.5 text-xs text-fb-secondary">{{ rows.length }}</span>
      </button>

      <button
        type="button"
        class="-mb-px flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-semibold transition-colors"
        :class="activeTab === 'groups'
          ? 'border-fb-blue text-fb-blue'
          : 'border-transparent text-fb-secondary hover:text-fb-text'"
        @click="onTabChange('groups')"
      >
        <span>👥</span> Group Leaderboard
        <span class="rounded-full bg-fb-canvas px-2 py-0.5 text-xs text-fb-secondary">{{ groupScores.length }}</span>
      </button>

      <button
        type="button"
        class="-mb-px flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-semibold transition-colors"
        :class="activeTab === 'analytics'
          ? 'border-fb-blue text-fb-blue'
          : 'border-transparent text-fb-secondary hover:text-fb-text'"
        @click="onTabChange('analytics')"
      >
        <span>📊</span> Grade Distribution
      </button>
    </div>

    <!-- Filter Bar -->
    <div class="rounded-2xl border border-fb-line bg-fb-card p-4 shadow-sm">
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <div v-if="!isTeacher">
          <label class="mb-1 block text-xs font-semibold text-fb-secondary">Branch</label>
          <select
            v-model="filters.branch_id"
            class="w-full rounded-lg border border-fb-line bg-fb-card px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            @change="loadRating(); activeTab === 'groups' && loadGroupScores()"
          >
            <option value="">All branches</option>
            <option v-for="b in branches" :key="b.id" :value="String(b.id)">
              {{ b.name }}
            </option>
          </select>
        </div>

        <div>
          <label class="mb-1 block text-xs font-semibold text-fb-secondary">Group</label>
          <select
            v-model="filters.group_id"
            class="w-full rounded-lg border border-fb-line bg-fb-card px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            @change="loadRating"
          >
            <option value="">All groups</option>
            <option v-for="g in groups" :key="g.id" :value="String(g.id)">
              {{ g.name }}
            </option>
          </select>
        </div>

        <div v-if="!isTeacher">
          <label class="mb-1 block text-xs font-semibold text-fb-secondary">Teacher</label>
          <select
            v-model="filters.teacher_id"
            class="w-full rounded-lg border border-fb-line bg-fb-card px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            @change="loadRating(); activeTab === 'groups' && loadGroupScores()"
          >
            <option value="">All teachers</option>
            <option v-for="t in teachers" :key="t.id" :value="String(t.id)">
              {{ t.name }}
            </option>
          </select>
        </div>

        <div v-if="!isTeacher">
          <label class="mb-1 block text-xs font-semibold text-fb-secondary">Course / Subject</label>
          <select
            v-model="filters.course_id"
            class="w-full rounded-lg border border-fb-line bg-fb-card px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            @change="loadRating(); activeTab === 'groups' && loadGroupScores()"
          >
            <option value="">All courses</option>
            <option v-for="c in courses" :key="c.id" :value="String(c.id)">
              {{ c.name }}
            </option>
          </select>
        </div>

        <div>
          <label class="mb-1 block text-xs font-semibold text-fb-secondary">Status</label>
          <select
            v-model="filters.status"
            class="w-full rounded-lg border border-fb-line bg-fb-card px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
            @change="loadRating"
          >
            <option value="">All statuses</option>
            <option value="passed">✅ Passed (≥ {{ summary.pass_score }})</option>
            <option value="failed">⚠️ Needs Retake (&lt; {{ summary.pass_score }})</option>
            <option value="top10">⭐ Top 10 Only</option>
          </select>
        </div>

        <div>
          <label class="mb-1 block text-xs font-semibold text-fb-secondary">Search</label>
          <div class="flex gap-2">
            <input
              v-model="filters.q"
              type="search"
              placeholder="Student name"
              class="w-full rounded-lg border border-fb-line bg-fb-card px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              @keydown.enter="loadRating"
            />
            <button
              type="button"
              title="Reset filters"
              class="rounded-lg border border-fb-line px-3 py-2 text-xs font-medium text-fb-secondary hover:bg-fb-canvas hover:text-fb-text"
              @click="resetFilters"
            >
              Reset
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 1: Students Table -->
    <div v-if="activeTab === 'table'" class="overflow-hidden rounded-2xl border border-fb-line bg-fb-card shadow-sm">
      <div v-if="loading" class="p-12 text-center text-fb-secondary">
        <div class="inline-block h-6 w-6 animate-spin rounded-full border-2 border-fb-blue border-t-transparent" />
        <p class="mt-2 text-sm">Loading ratings…</p>
      </div>

      <div v-else-if="!rows.length" class="p-12 text-center text-fb-secondary">
        <p class="text-4xl">📋</p>
        <p class="mt-2 text-base font-semibold text-fb-text">No ratings found</p>
        <p class="mt-1 text-sm text-fb-secondary">Try adjusting your filters or add grades for your students.</p>
        <button
          type="button"
          class="mt-4 rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:bg-fb-blue-dark"
          @click="openBulkModal()"
        >
          Open Group Grading Sheet
        </button>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead class="border-b border-fb-line bg-fb-canvas text-xs font-bold uppercase tracking-wider text-fb-secondary">
            <tr>
              <th class="px-5 py-3.5 text-center">Rank</th>
              <th class="px-5 py-3.5">Student</th>
              <th class="px-5 py-3.5">Group & Subject</th>
              <th class="px-5 py-3.5">Teacher</th>
              <th class="px-5 py-3.5">Branch</th>
              <th class="px-5 py-3.5 text-right">Score</th>
              <th class="px-5 py-3.5 text-center">Status</th>
              <th class="px-5 py-3.5 text-center">In-Group Rank</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-fb-line">
            <tr
              v-for="row in rows"
              :key="row.id"
              class="cursor-pointer transition-colors hover:bg-fb-hover/40"
              @click="openDetailPanel(row.id)"
            >
              <!-- Rank -->
              <td class="px-5 py-3.5 text-center">
                <span class="inline-flex items-center justify-center gap-1 font-bold" :class="medalClass(row.no)">
                  <span>{{ medalIcon(row.no) }}</span>
                  <span>#{{ row.no }}</span>
                </span>
              </td>

              <!-- Student -->
              <td class="px-5 py-3.5">
                <div class="flex items-center gap-2">
                  <div class="flex h-8 w-8 items-center justify-center rounded-full bg-fb-canvas font-bold text-fb-blue">
                    {{ row.name.charAt(0) }}
                  </div>
                  <div>
                    <span class="font-semibold text-fb-text hover:text-fb-blue hover:underline">
                      {{ row.name }}
                    </span>
                  </div>
                </div>
              </td>

              <!-- Group & Course -->
              <td class="px-5 py-3.5">
                <span class="font-medium text-fb-text">{{ row.group }}</span>
                <span v-if="row.course" class="ml-1.5 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
                  {{ row.course }}
                </span>
              </td>

              <!-- Teacher -->
              <td class="px-5 py-3.5 text-fb-secondary">
                {{ row.teacher || '—' }}
              </td>

              <!-- Branch -->
              <td class="px-5 py-3.5 text-fb-secondary">
                {{ row.branch }}
              </td>

              <!-- Score -->
              <td class="px-5 py-3.5 text-right">
                <span class="text-base font-extrabold text-fb-blue">{{ row.grade }}</span>
                <span class="text-xs text-fb-secondary"> / {{ row.max_scale }}</span>
              </td>

              <!-- Status -->
              <td class="px-5 py-3.5 text-center">
                <span
                  v-if="row.is_passed"
                  class="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 border border-emerald-200"
                >
                  <span>✓</span> Passed
                </span>
                <span
                  v-else
                  class="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-700 border border-red-200"
                >
                  <span>✕</span> Retake
                </span>
              </td>

              <!-- In-Group Rank -->
              <td class="px-5 py-3.5 text-center text-xs font-medium text-fb-secondary">
                #{{ row.rank_in_group || row.rank }} in group
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 2: Group Leaderboard -->
    <div v-else-if="activeTab === 'groups'" class="overflow-hidden rounded-2xl border border-fb-line bg-fb-card shadow-sm">
      <div v-if="groupsLoading" class="p-12 text-center text-fb-secondary">
        <div class="inline-block h-6 w-6 animate-spin rounded-full border-2 border-fb-blue border-t-transparent" />
        <p class="mt-2 text-sm">Loading group rankings…</p>
      </div>

      <div v-else-if="!groupScores.length" class="p-12 text-center text-fb-secondary">
        <p class="text-4xl">👥</p>
        <p class="mt-2 text-base font-semibold text-fb-text">No group statistics available</p>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead class="border-b border-fb-line bg-fb-canvas text-xs font-bold uppercase tracking-wider text-fb-secondary">
            <tr>
              <th class="px-5 py-3.5 text-center">Group Rank</th>
              <th class="px-5 py-3.5">Group</th>
              <th class="px-5 py-3.5">Course / Subject</th>
              <th class="px-5 py-3.5">Teacher</th>
              <th class="px-5 py-3.5">Branch</th>
              <th class="px-5 py-3.5 text-center">Graded / Enrolled</th>
              <th class="px-5 py-3.5 text-right">Average Score</th>
              <th class="px-5 py-3.5 text-center">Pass Rate</th>
              <th class="px-5 py-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-fb-line">
            <tr
              v-for="grp in groupScores"
              :key="grp.group_id"
              class="transition-colors hover:bg-fb-hover/40"
            >
              <td class="px-5 py-3.5 text-center font-bold" :class="medalClass(grp.rank)">
                {{ medalIcon(grp.rank) }} #{{ grp.rank }}
              </td>

              <td class="px-5 py-3.5">
                <button
                  type="button"
                  class="font-semibold text-fb-text hover:text-fb-blue hover:underline"
                  @click="goGroup({ group_id: grp.group_id })"
                >
                  {{ grp.group_name }}
                </button>
              </td>

              <td class="px-5 py-3.5 text-fb-secondary">
                {{ grp.course_name }}
              </td>

              <td class="px-5 py-3.5">
                <button
                  v-if="grp.teacher_id"
                  type="button"
                  class="text-fb-secondary hover:text-fb-blue hover:underline"
                  @click="goTeacher(grp.teacher_id)"
                >
                  {{ grp.teacher_name }}
                </button>
                <span v-else class="text-fb-secondary">—</span>
              </td>

              <td class="px-5 py-3.5 text-fb-secondary">
                {{ grp.branch_name }}
              </td>

              <td class="px-5 py-3.5 text-center">
                <span class="font-semibold text-fb-text">{{ grp.graded_count }}</span>
                <span class="text-xs text-fb-secondary"> / {{ grp.enrolled_count }} students</span>
              </td>

              <td class="px-5 py-3.5 text-right">
                <span class="text-base font-extrabold text-fb-blue">{{ grp.avg_grade }}</span>
                <span class="text-xs text-fb-secondary"> / {{ grp.max_scale }}</span>
              </td>

              <td class="px-5 py-3.5 text-center">
                <div class="inline-flex flex-col items-center">
                  <span class="text-xs font-bold text-fb-text">{{ grp.pass_rate }}%</span>
                  <div class="mt-1 h-1.5 w-16 rounded-full bg-fb-canvas">
                    <div
                      class="h-1.5 rounded-full"
                      :class="grp.pass_rate >= 75 ? 'bg-emerald-500' : grp.pass_rate >= 50 ? 'bg-amber-500' : 'bg-red-500'"
                      :style="{ width: `${grp.pass_rate}%` }"
                    />
                  </div>
                </div>
              </td>

              <td class="px-5 py-3.5 text-right">
                <button
                  type="button"
                  class="rounded-lg border border-fb-blue bg-blue-50/60 px-3 py-1 text-xs font-semibold text-fb-blue hover:bg-fb-blue hover:text-white transition-colors"
                  @click="openBulkModal(grp.group_id)"
                >
                  📝 Grade Group
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 3: Analytics & Distribution -->
    <div v-else-if="activeTab === 'analytics'" class="space-y-6">
      <!-- Brackets distribution -->
      <div class="rounded-2xl border border-fb-line bg-fb-card p-6 shadow-sm">
        <h2 class="text-base font-bold text-fb-text">📊 Score Tier Breakdown</h2>
        <p class="text-xs text-fb-secondary">Distribution of student performance across score brackets</p>

        <div class="mt-6 space-y-4">
          <div v-for="b in brackets" :key="b.label" class="space-y-1.5">
            <div class="flex items-center justify-between text-sm">
              <span class="font-medium text-fb-text">{{ b.label }}</span>
              <span class="font-semibold text-fb-secondary">{{ b.count }} students ({{ b.percent }}%)</span>
            </div>
            <div class="h-3 w-full rounded-full bg-fb-canvas">
              <div
                class="h-3 rounded-full transition-all duration-500"
                :class="b.color"
                :style="{ width: `${b.percent}%` }"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Ranked Visual Bars -->
      <div class="rounded-2xl border border-fb-line bg-fb-card p-6 shadow-sm">
        <h2 class="text-base font-bold text-fb-text">📈 Individual Student Comparison</h2>
        <p class="text-xs text-fb-secondary">Relative standing against maximum grade scale ({{ summary.max_scale }} pts)</p>

        <div v-if="!rows.length" class="py-8 text-center text-fb-secondary">No data to display</div>
        <div v-else class="mt-6 space-y-3">
          <div
            v-for="row in rows"
            :key="row.id"
            class="grid grid-cols-[180px_1fr_80px] items-center gap-4 text-sm"
          >
            <button
              type="button"
              class="truncate text-left font-medium text-fb-text hover:text-fb-blue"
              @click="openDetailPanel(row.id)"
            >
              {{ row.no }}. {{ row.name }}
            </button>
            <div class="h-3 rounded-full bg-fb-canvas">
              <div
                class="h-3 rounded-full transition-all"
                :class="row.is_passed ? 'bg-fb-blue' : 'bg-red-400'"
                :style="{ width: `${Math.min(100, (row.grade / maxGrade) * 100)}%` }"
              />
            </div>
            <div class="text-right font-bold" :class="row.is_passed ? 'text-fb-blue' : 'text-red-500'">
              {{ row.grade }} pts
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Drawer Panel for Single Score Add / Edit -->
    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/40" @click="closePanel" />
      <div class="drawer-panel-fb max-w-lg shadow-2xl">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-4">
          <div>
            <h2 class="text-lg font-bold text-fb-text">{{ panelTitle }}</h2>
            <p class="text-xs text-fb-secondary">Pass mark: {{ summary.pass_score }} pts / Max: {{ summary.max_scale }} pts</p>
          </div>
          <button type="button" class="text-fb-secondary hover:text-fb-text" @click="closePanel">✕</button>
        </div>

        <div v-if="panelLoading" class="flex-1 p-6 text-fb-secondary">Loading…</div>

        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitScore">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <!-- An existing grade: student and group are fixed, only the points can change -->
            <div v-if="detailScore" class="rounded-lg border border-fb-line bg-fb-canvas px-4 py-3 text-sm">
              <p class="font-semibold text-fb-text">{{ detailScore.name }}</p>
              <p class="text-fb-secondary">{{ detailScore.group }}<span v-if="detailScore.course"> · {{ detailScore.course }}</span></p>
            </div>

            <template v-else>
              <div>
                <label class="mb-1 block text-sm font-semibold text-fb-text">1. Группа</label>
                <select
                  v-model="form.group_id"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
                  @change="loadPanelStudents()"
                >
                  <option value="">Выберите группу</option>
                  <option v-for="group in groups" :key="group.id" :value="group.id">
                    {{ group.name }}
                  </option>
                </select>
              </div>

              <div>
                <label class="mb-1 block text-sm font-semibold text-fb-text">2. Дата урока</label>
                <select
                  v-model="panelDate"
                  :disabled="!form.group_id || !panelLessonDates.length"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm disabled:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                  @change="loadPanelStudents(true)"
                >
                  <option v-if="!form.group_id" value="">Сначала выберите группу</option>
                  <option v-else-if="!panelLessonDates.length" value="">Нет уроков за последние 7 дней</option>
                  <option v-for="d in panelLessonDates" :key="d.date" :value="d.date">{{ d.label }}</option>
                </select>
                <p class="mt-1 text-[11px] text-fb-secondary">
                  Только дни занятий этой группы по расписанию, не дальше 7 дней назад.
                </p>
              </div>

              <div>
                <label class="mb-1 block text-sm font-semibold text-fb-text">3. Ученик</label>
                <select
                  v-model="form.student_id"
                  :disabled="!form.group_id || !panelDate || panelStudentsLoading"
                  class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm disabled:bg-fb-canvas focus:border-fb-blue focus:outline-none"
                >
                  <option value="">
                    {{ !form.group_id ? 'Сначала выберите группу' : panelStudentsLoading ? 'Загрузка…' : 'Выберите ученика' }}
                  </option>
                  <!-- Absent today / frozen: shown, but cannot be picked -->
                  <option
                    v-for="st in panelStudents"
                    :key="st.student_id"
                    :value="st.student_id"
                    :disabled="!st.can_grade"
                  >
                    {{ st.name }}{{ st.can_grade ? '' : ` — ${st.reason_label}` }}
                  </option>
                </select>
              </div>
            </template>

            <div>
              <div class="flex items-center justify-between">
                <label class="mb-1 block text-sm font-semibold text-fb-text">
                  Grade (0 – {{ summary.max_scale }})
                </label>
                <span
                  v-if="form.grade !== ''"
                  class="text-xs font-semibold"
                  :class="form.grade >= summary.pass_score ? 'text-emerald-600' : 'text-red-500'"
                >
                  {{ form.grade >= summary.pass_score ? 'Passed' : 'Needs Retake' }}
                </span>
              </div>
              <input
                v-model.number="form.grade"
                type="number"
                min="0"
                :max="summary.max_scale"
                step="1"
                required
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 text-base font-semibold read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div
              v-if="detailScore"
              class="rounded-xl border border-fb-line bg-fb-canvas p-4 text-sm text-fb-secondary space-y-2"
            >
              <div class="flex items-center justify-between">
                <span>Общий рейтинг:</span>
                <span class="font-bold text-fb-text">№{{ detailScore.no }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span>Место в группе:</span>
                <span class="font-bold text-fb-text">№{{ detailScore.rank_in_group || detailScore.rank }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span>Branch:</span>
                <span class="font-bold text-fb-text">{{ detailScore.branch }}</span>
              </div>
              <div class="mt-3 flex gap-3 border-t border-fb-line pt-3">
                <button type="button" class="text-fb-blue hover:underline" @click="goStudent(detailScore)">
                  Student Profile →
                </button>
                <button type="button" class="text-fb-blue hover:underline" @click="goGroup(detailScore)">
                  Group Page →
                </button>
              </div>
            </div>

            <!-- Every grade of the student; the rating shows only the latest one -->
            <div v-if="detailScore" class="rounded-xl border border-fb-line p-4 text-sm">
              <p class="mb-2 font-semibold text-fb-text">История оценок</p>
              <p v-if="!history.length" class="text-fb-secondary">Пока нет записей</p>
              <ul v-else class="space-y-1.5">
                <li v-for="h in history" :key="h.id" class="flex items-start justify-between gap-3">
                  <span class="text-fb-secondary">
                    {{ formatDay(h.date) }} · {{ h.group }}<span v-if="h.course"> · {{ h.course }}</span>
                    <span v-if="h.corrected" class="block text-[11px] text-amber-700">
                      исправлено {{ formatDay(h.corrected_at) }}<span v-if="h.corrected_by"> ({{ h.corrected_by }})</span>
                    </span>
                  </span>
                  <span class="font-bold text-fb-text">{{ h.grade }}</span>
                </li>
              </ul>
            </div>

            <p v-if="formError" class="text-sm font-medium text-red-500">{{ formError }}</p>
          </div>

          <div class="flex flex-wrap gap-2 border-t border-fb-line px-6 py-4">
            <template v-if="isReadOnly && detailScore">
              <button
                type="button"
                class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-semibold text-white hover:bg-fb-blue-dark"
                @click="startEdit"
              >
                Edit
              </button>
              <button
                type="button"
                class="rounded-lg border border-red-300 px-5 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50"
                :disabled="deleting"
                @click="deleteScore"
              >
                Delete
              </button>
            </template>
            <template v-else>
              <button
                type="submit"
                class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-semibold text-white hover:bg-fb-blue-dark disabled:opacity-50"
                :disabled="saving"
              >
                {{ saving ? 'Saving…' : editingScore ? 'Save Changes' : 'Create Grade' }}
              </button>
            </template>
            <button
              type="button"
              class="rounded-lg border border-fb-line px-5 py-2 text-sm font-semibold text-fb-secondary hover:bg-fb-canvas"
              @click="closePanel"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Bulk Group Grading Modal -->
    <div v-if="showBulkModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/40" @click="showBulkModal = false" />
      <div class="relative flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl border border-fb-line bg-fb-card shadow-2xl">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-4">
          <div>
            <h2 class="text-lg font-bold text-fb-text">📝 Group Grading Sheet</h2>
            <p class="text-xs text-fb-secondary">
              Set or update grades for all students in the selected group simultaneously
            </p>
          </div>
          <button type="button" class="text-fb-secondary hover:text-fb-text" @click="showBulkModal = false">✕</button>
        </div>

        <div class="border-b border-fb-line bg-fb-canvas/50 px-6 py-3">
          <div class="flex flex-wrap items-center gap-3">
            <label class="text-xs font-semibold text-fb-secondary">Select Group:</label>
            <select
              v-model="bulkGroupId"
              class="rounded-lg border border-fb-line bg-fb-card px-3 py-1.5 text-sm font-semibold focus:border-fb-blue focus:outline-none"
              @change="onBulkGroupChange"
            >
              <option v-for="g in groups" :key="g.id" :value="g.id">
                {{ g.name }}
              </option>
            </select>
            <label class="text-xs font-semibold text-fb-secondary">Дата урока:</label>
            <select
              v-model="bulkDate"
              :disabled="!bulkLessonDates.length"
              class="rounded-lg border border-fb-line bg-fb-card px-3 py-1.5 text-sm font-semibold disabled:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              @change="loadBulkStudents"
            >
              <option v-if="!bulkLessonDates.length" value="">нет уроков за 7 дней</option>
              <option v-for="d in bulkLessonDates" :key="d.date" :value="d.date">{{ d.label }}</option>
            </select>
            <span class="text-xs text-fb-secondary">
              (Pass mark: <strong>{{ summary.pass_score }}</strong> / Max scale: <strong>{{ summary.max_scale }}</strong>)
            </span>
          </div>
        </div>

        <div class="flex-1 overflow-y-auto p-6">
          <div v-if="bulkLoading" class="py-12 text-center text-fb-secondary">
            <div class="inline-block h-6 w-6 animate-spin rounded-full border-2 border-fb-blue border-t-transparent" />
            <p class="mt-2 text-sm">Loading group students…</p>
          </div>

          <div v-else-if="!bulkStudents.length" class="py-12 text-center text-fb-secondary">
            <p class="text-3xl">👥</p>
            <p class="mt-2 text-sm font-semibold text-fb-text">No enrolled students in this group</p>
          </div>

          <div v-else class="space-y-3">
            <div class="flex items-center justify-between border-b border-fb-line pb-2 text-xs font-bold uppercase text-fb-secondary">
              <span>Student Name</span>
              <span>Grade (0 – {{ summary.max_scale }})</span>
            </div>

            <div
              v-for="st in bulkStudents"
              :key="st.student_id"
              class="flex items-center justify-between gap-4 rounded-xl border border-fb-line p-3"
              :class="st.can_grade ? 'bg-fb-canvas/30' : 'pointer-events-none select-none bg-fb-canvas opacity-45 grayscale'"
              :title="st.can_grade ? '' : st.reason_label"
            >
              <div class="flex items-center gap-3">
                <div class="flex h-8 w-8 items-center justify-center rounded-full bg-fb-canvas font-bold text-fb-blue">
                  {{ st.student_name.charAt(0) }}
                </div>
                <div>
                  <p class="font-semibold text-fb-text">{{ st.student_name }}</p>
                  <span v-if="!st.can_grade" class="text-[11px] text-fb-secondary">{{ st.reason_label }}</span>
                  <span v-else-if="st.grade === ''" class="text-[11px] text-fb-secondary">
                    Не оценён<span v-if="st.last_grade !== null"> · последняя: {{ st.last_grade }}</span>
                  </span>
                  <span
                    v-else-if="st.grade >= summary.pass_score"
                    class="text-[11px] font-semibold text-emerald-600"
                  >
                    ✓ Pass
                  </span>
                  <span v-else class="text-[11px] font-semibold text-red-500">
                    ✕ Retake
                  </span>
                </div>
              </div>

              <div class="w-32 text-right">
                <!-- No box for a student who is not here today: nobody can grade an absent student -->
                <span v-if="!st.can_grade" class="text-xs font-semibold text-fb-secondary">{{ st.reason_label }}</span>
                <input
                  v-else
                  v-model.number="st.grade"
                  type="number"
                  min="0"
                  :max="summary.max_scale"
                  step="1"
                  placeholder="—"
                  class="w-full rounded-lg border border-fb-line bg-fb-card px-3 py-1.5 text-right font-bold text-fb-text focus:border-fb-blue focus:outline-none"
                />
              </div>
            </div>
          </div>

          <p v-if="bulkError" class="mt-4 text-sm font-medium text-red-500">{{ bulkError }}</p>
        </div>

        <div class="flex items-center justify-between border-t border-fb-line px-6 py-4">
          <span class="text-xs text-fb-secondary">
            {{ bulkStudents.length }} students in sheet
          </span>
          <div class="flex gap-2">
            <button
              type="button"
              class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:bg-fb-canvas"
              @click="showBulkModal = false"
            >
              Cancel
            </button>
            <button
              type="button"
              class="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 disabled:opacity-50"
              :disabled="bulkSaving || !bulkStudents.length"
              @click="submitBulkScores"
            >
              {{ bulkSaving ? 'Saving…' : 'Save All Grades' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
