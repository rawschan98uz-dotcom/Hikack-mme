<script setup lang="ts">
/**
 * Teachers' lessons (reports audit, 2026-09-29): every lesson of the schedule, the ones nobody marked too.
 * Example: Tom had 13 lessons and pressed «Я пришёл» 10 times — the old report showed «Присутствовал 10,
 * Отсутствовал 0»; now it shows 3 «Не отметился», and the office marks them for him (a lesson is paid only when marked).
 */
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { useAuthStore } from '../stores/auth';
import { downloadCsv } from '../utils/csvExport';
import { groupRoute, teacherRoute } from '../utils/crossLinks';
import { currentMonthIso, todayIso } from '../utils/dates';
import { PERM } from '../utils/rbac';

interface Option {
  id: number;
  name: string;
  branch_id?: number;
}

interface LessonRow {
  date: string;
  group_id: number;
  group: string;
  branch: string;
  start_time: string;
  end_time: string;
  locked: boolean;
  record_id: number | null;
  teacher_id: number | null;
  teacher: string;
  status: number | null;
  status_label: string;
  note: string;
  marked_at: string;
}

interface Summary {
  lessons: number;
  present: number;
  late: number;
  absent: number;
  not_marked: number;
}

const MARKS = [
  { value: 1, label: 'Был', cls: 'border-emerald-300 text-emerald-700 hover:bg-emerald-50' },
  { value: 2, label: 'Опоздал', cls: 'border-amber-300 text-amber-700 hover:bg-amber-50' },
  { value: 0, label: 'Не был', cls: 'border-red-300 text-red-700 hover:bg-red-50' },
] as const;

const router = useRouter();
const auth = useAuthStore();
const canWrite = computed(() => auth.can(PERM.TEACHER_ATTENDANCE_WRITE));

const rows = ref<LessonRow[]>([]);
const summary = ref<Summary>({ lessons: 0, present: 0, late: 0, absent: 0, not_marked: 0 });
const branches = ref<Option[]>([]);
const groups = ref<Option[]>([]);
const teachers = ref<Option[]>([]);
const loading = ref(true);
const errorMessage = ref('');
const savingKey = ref('');
/** Who held the lesson: the group's teacher by default, another one for a substitution (owner, 2026-09-29). */
const picked = reactive<Record<string, number | null>>({});

function pickedTeacher(row: LessonRow): number | null {
  return picked[rowKey(row)] ?? row.teacher_id;
}

function teacherName(id: number | null) {
  return teachers.value.find((t) => t.id === id)?.name ?? '';
}
const pageSize = 50;
const currentPage = ref(1);

function monthBounds(month: string) {
  const [y, m] = month.split('-').map(Number);
  const last = new Date(y, m, 0).getDate();
  return { from: `${month}-01`, to: `${month}-${String(last).padStart(2, '0')}` };
}

const filters = reactive({
  month: currentMonthIso(),
  branch_id: '',
  group_id: '',
  teacher_id: '',
  status: '',
});

const filterGroups = computed(() =>
  filters.branch_id ? groups.value.filter((g) => String(g.branch_id) === filters.branch_id) : groups.value,
);

const totalPages = computed(() => Math.max(1, Math.ceil(rows.value.length / pageSize)));
const pageRows = computed(() => rows.value.slice((currentPage.value - 1) * pageSize, currentPage.value * pageSize));

const heldPercent = computed(() => {
  const s = summary.value;
  return s.lessons ? Math.round(((s.present + s.late) / s.lessons) * 100) : 0;
});

function rowKey(row: LessonRow) {
  return `${row.group_id}-${row.date}-${row.record_id ?? 'x'}`;
}

function statusClass(status: number | null) {
  if (status === 1) return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
  if (status === 2) return 'bg-amber-50 text-amber-700 border border-amber-200';
  if (status === 0) return 'bg-red-50 text-fb-danger border border-red-200';
  return 'bg-gray-100 text-gray-600 border border-dashed border-gray-300';
}

function formatDate(iso: string) {
  const [y, m, d] = iso.split('-');
  const weekday = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'][new Date(Number(y), Number(m) - 1, Number(d)).getDay()];
  return `${d}.${m}.${y}, ${weekday}`;
}

function params(): Record<string, string> {
  const { from, to } = monthBounds(filters.month);
  const p: Record<string, string> = { date_from: from, date_to: to };
  if (filters.branch_id) p.branch_id = filters.branch_id;
  if (filters.group_id) p.group_id = filters.group_id;
  if (filters.teacher_id) p.teacher_id = filters.teacher_id;
  if (filters.status) p.status = filters.status;
  return p;
}

async function loadReport() {
  loading.value = true;
  errorMessage.value = '';
  try {
    const { data } = await client.get<ApiEnvelope<{ summary: Summary; rows: LessonRow[] }>>(
      '/reports/teacher-attendance/lessons',
      { params: params() },
    );
    summary.value = data.data.summary;
    rows.value = data.data.rows;
    currentPage.value = 1;
  } catch (err: any) {
    errorMessage.value = err?.response?.data?.message || 'Не удалось загрузить уроки';
  } finally {
    loading.value = false;
  }
}

function resetFilters() {
  Object.assign(filters, { month: currentMonthIso(), branch_id: '', group_id: '', teacher_id: '', status: '' });
  loadReport();
}

function shiftMonth(delta: number) {
  const [y, m] = filters.month.split('-').map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  filters.month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  loadReport();
}

/** The office marks the lesson for the teacher (or corrects the mark). Closed months are refused by the server. */
async function mark(row: LessonRow, status: number) {
  const teacherId = pickedTeacher(row);
  if (!teacherId) return;
  const teacherChanged = teacherId !== row.teacher_id;
  if (row.status === status && !teacherChanged) return;
  const verb = MARKS.find((m) => m.value === status)?.label ?? '';
  const who = teacherName(teacherId) || row.teacher;
  const substitute = row.record_id && teacherChanged ? ` (вместо ${row.teacher})` : '';
  if (!window.confirm(`${who}${substitute}, группа «${row.group}», ${formatDate(row.date)}: отметить «${verb}»?`)) return;
  savingKey.value = rowKey(row);
  errorMessage.value = '';
  try {
    if (row.record_id) {
      // A mark moved to another teacher = a substitution
      await client.patch(`/reports/teacher-attendance/${row.record_id}`, { status, teacher_id: teacherId });
    } else {
      await client.post('/reports/teacher-attendance', {
        teacher_id: teacherId,
        group_id: row.group_id,
        date: row.date,
        status,
      });
    }
    delete picked[rowKey(row)];
    await loadReport();
  } catch (err: any) {
    errorMessage.value = err?.response?.data?.message || 'Не удалось сохранить отметку';
  } finally {
    savingKey.value = '';
  }
}

function exportCsv() {
  downloadCsv(
    `teacher_lessons_${filters.month}_${todayIso()}.csv`,
    ['Дата', 'Время', 'Группа', 'Филиал', 'Преподаватель', 'Статус', 'Отмечено', 'Заметка'],
    rows.value.map((row) => [
      row.date,
      row.start_time ? `${row.start_time}–${row.end_time}` : '',
      row.group,
      row.branch,
      row.teacher,
      row.status_label,
      row.marked_at,
      row.note,
    ]),
  );
}

async function loadOptions() {
  const [branchRes, groupRes, teacherRes] = await Promise.allSettled([
    client.get<ApiEnvelope<Option[]>>('/branch'),
    client.get<ApiEnvelope<any[]>>('/groups'),
    client.get<ApiEnvelope<Option[]>>('/user', { params: { user_type: 'teacher' } }),
  ]);
  if (branchRes.status === 'fulfilled') branches.value = branchRes.value.data.data;
  if (groupRes.status === 'fulfilled') {
    groups.value = groupRes.value.data.data.map((g) => ({ id: g.id, name: g.name, branch_id: g.branch_id }));
  }
  if (teacherRes.status === 'fulfilled') {
    teachers.value = teacherRes.value.data.data.map((t) => ({ id: t.id, name: t.name }));
  }
}

onMounted(async () => {
  await Promise.all([loadReport(), loadOptions()]);
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold text-fb-text">Посещаемость преподавателей</h1>
        <p class="text-xs text-fb-secondary mt-0.5">
          Все уроки по расписанию. Урок оплачивается учителю, только если он отмечен «Был» или «Опоздал». Если урок провёл другой учитель (замена), выберите его в строке и отметьте.
        </p>
      </div>
      <button
        type="button"
        class="rounded-lg border border-fb-line bg-fb-card px-3.5 py-2 text-sm text-fb-secondary hover:border-fb-blue hover:text-fb-blue transition-colors"
        @click="exportCsv"
      >
        📥 Экспорт CSV
      </button>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Месяц</label>
        <div class="flex items-center gap-1">
          <button type="button" class="rounded-lg border border-fb-line px-2 py-2 text-sm hover:border-fb-blue" @click="shiftMonth(-1)">◀</button>
          <input v-model="filters.month" type="month" class="rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" @change="loadReport" />
          <button type="button" class="rounded-lg border border-fb-line px-2 py-2 text-sm hover:border-fb-blue" @click="shiftMonth(1)">▶</button>
        </div>
      </div>
      <div v-if="branches.length > 1">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Филиал</label>
        <select v-model="filters.branch_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm" @change="filters.group_id = ''; loadReport()">
          <option value="">Все филиалы</option>
          <option v-for="b in branches" :key="b.id" :value="String(b.id)">{{ b.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Группа</label>
        <select v-model="filters.group_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm" @change="loadReport">
          <option value="">Все группы</option>
          <option v-for="g in filterGroups" :key="g.id" :value="String(g.id)">{{ g.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Преподаватель</label>
        <select v-model="filters.teacher_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm" @change="loadReport">
          <option value="">Все преподаватели</option>
          <option v-for="t in teachers" :key="t.id" :value="String(t.id)">{{ t.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Статус</label>
        <select v-model="filters.status" class="rounded-lg border border-fb-line px-3 py-2 text-sm" @change="loadReport">
          <option value="">Все уроки</option>
          <option value="not_marked">Не отметился</option>
          <option value="present">Был</option>
          <option value="late">Опоздал</option>
          <option value="absent">Не был</option>
        </select>
      </div>
      <button type="button" class="rounded-lg border border-fb-line px-4 py-2 text-sm text-fb-secondary hover:text-fb-blue" @click="resetFilters">
        Сбросить
      </button>
    </div>

    <!-- Summary -->
    <div class="grid grid-cols-2 gap-3 md:grid-cols-5">
      <div class="rounded-xl border border-fb-line bg-fb-card p-4 text-center">
        <div class="text-2xl font-bold text-fb-text">{{ summary.lessons }}</div>
        <div class="mt-1 text-xs text-fb-secondary">Уроков по расписанию</div>
      </div>
      <div class="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4 text-center">
        <div class="text-2xl font-bold text-emerald-700">{{ summary.present }}</div>
        <div class="mt-1 text-xs text-fb-secondary">Был</div>
      </div>
      <div class="rounded-xl border border-amber-200 bg-amber-50/50 p-4 text-center">
        <div class="text-2xl font-bold text-amber-700">{{ summary.late }}</div>
        <div class="mt-1 text-xs text-fb-secondary">Опоздал</div>
      </div>
      <div class="rounded-xl border border-red-200 bg-red-50/50 p-4 text-center">
        <div class="text-2xl font-bold text-fb-danger">{{ summary.absent }}</div>
        <div class="mt-1 text-xs text-fb-secondary">Не был</div>
      </div>
      <button
        type="button"
        class="rounded-xl border border-dashed border-gray-400 bg-gray-50 p-4 text-center hover:border-fb-blue"
        title="Показать только неотмеченные уроки"
        @click="filters.status = 'not_marked'; loadReport()"
      >
        <div class="text-2xl font-bold text-gray-700">{{ summary.not_marked }}</div>
        <div class="mt-1 text-xs text-fb-secondary">Не отметился (не оплачивается)</div>
      </button>
    </div>
    <p v-if="summary.lessons" class="text-xs text-fb-secondary">
      Проведено {{ summary.present + summary.late }} из {{ summary.lessons }} уроков ({{ heldPercent }}%). Уроки считаются до сегодняшнего дня.
    </p>

    <div v-if="errorMessage" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-fb-danger">{{ errorMessage }}</div>

    <!-- Lessons -->
    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card shadow-sm">
      <div v-if="loading" class="p-12 text-center text-fb-secondary">Загрузка…</div>
      <div v-else-if="!rows.length" class="p-12 text-center text-sm text-fb-secondary">За этот месяц уроков не найдено.</div>
      <template v-else>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="border-b border-fb-line bg-fb-canvas text-xs uppercase tracking-wider font-semibold text-fb-secondary">
              <tr>
                <th class="px-5 py-3 text-left">Дата</th>
                <th class="px-4 py-3 text-left">Группа</th>
                <th class="px-4 py-3 text-left">Преподаватель</th>
                <th class="px-4 py-3 text-left">Статус</th>
                <th class="px-4 py-3 text-left">Отмечено</th>
                <th v-if="canWrite" class="px-5 py-3 text-right">Кто вёл · отметить за учителя</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-fb-line">
              <tr v-for="row in pageRows" :key="rowKey(row)" class="hover:bg-fb-hover/40">
                <td class="px-5 py-3 whitespace-nowrap">
                  <div class="font-medium text-fb-text">{{ formatDate(row.date) }}</div>
                  <div v-if="row.start_time" class="text-xs text-fb-secondary">{{ row.start_time }}–{{ row.end_time }}</div>
                </td>
                <td class="px-4 py-3">
                  <button type="button" class="font-medium text-fb-blue hover:underline" @click="router.push(groupRoute(row.group_id))">{{ row.group }}</button>
                  <div class="text-xs text-fb-secondary">{{ row.branch }}</div>
                </td>
                <td class="px-4 py-3">
                  <button v-if="row.teacher_id" type="button" class="text-fb-text hover:text-fb-blue hover:underline" @click="router.push(teacherRoute(row.teacher_id))">{{ row.teacher }}</button>
                  <span v-else class="text-fb-secondary">— нет учителя</span>
                </td>
                <td class="px-4 py-3">
                  <span class="rounded-full px-2.5 py-0.5 text-xs font-medium" :class="statusClass(row.status)">{{ row.status_label }}</span>
                  <div v-if="row.note" class="mt-1 text-xs text-fb-secondary">{{ row.note }}</div>
                </td>
                <td class="px-4 py-3 text-xs text-fb-secondary">{{ row.marked_at || '—' }}</td>
                <td v-if="canWrite" class="px-5 py-3 text-right whitespace-nowrap">
                  <span v-if="row.locked" class="text-xs text-fb-secondary" title="Месяц закрыт в «Зарплатах»: отметки не меняются">🔒 месяц закрыт</span>
                  <div v-else class="inline-flex items-center gap-1">
                    <select
                      :value="pickedTeacher(row) ?? ''"
                      class="max-w-[150px] rounded-md border border-fb-line px-1.5 py-1 text-xs"
                      title="Кто вёл урок (для замены выберите другого учителя)"
                      @change="picked[rowKey(row)] = Number(($event.target as HTMLSelectElement).value) || null"
                    >
                      <option value="" disabled>Кто вёл?</option>
                      <option v-if="row.teacher_id && !teachers.some((t) => t.id === row.teacher_id)" :value="row.teacher_id">{{ row.teacher }}</option>
                      <option v-for="t in teachers" :key="t.id" :value="t.id">{{ t.name }}</option>
                    </select>
                    <button
                      v-for="m in MARKS"
                      :key="m.value"
                      type="button"
                      class="rounded-md border px-2 py-1 text-xs font-medium transition-colors disabled:opacity-40"
                      :class="[m.cls, row.status === m.value ? 'ring-2 ring-offset-1 ring-current' : '']"
                      :disabled="savingKey === rowKey(row) || !pickedTeacher(row) || (row.status === m.value && pickedTeacher(row) === row.teacher_id)"
                      @click="mark(row, m.value)"
                    >
                      {{ m.label }}
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="totalPages > 1" class="flex items-center justify-between border-t border-fb-line px-5 py-3">
          <button type="button" class="rounded-lg border border-fb-line px-3 py-1.5 text-xs disabled:opacity-40" :disabled="currentPage <= 1" @click="currentPage--">← Назад</button>
          <span class="text-xs text-fb-secondary">Страница {{ currentPage }} из {{ totalPages }} (всего {{ rows.length }} уроков)</span>
          <button type="button" class="rounded-lg border border-fb-line px-3 py-1.5 text-xs disabled:opacity-40" :disabled="currentPage >= totalPages" @click="currentPage++">Вперед →</button>
        </div>
      </template>
    </div>
  </div>
</template>
