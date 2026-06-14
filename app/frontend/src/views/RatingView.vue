<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { groupRoute, studentRoute } from '../utils/crossLinks';

interface Branch {
  id: number;
  name: string;
}

interface GroupOption {
  id: number;
  name: string;
  branch_id: number;
}

interface StudentOption {
  id: number;
  full_name: string;
  group_id: number | null;
}

interface RatingRow {
  id: number;
  no: number;
  student_id: number;
  name: string;
  group_id: number;
  group: string;
  branch_id: number;
  branch: string;
  grade: number;
  rank: number;
  updated_at: string;
}

const router = useRouter();

const rows = ref<RatingRow[]>([]);
const branches = ref<Branch[]>([]);
const groups = ref<GroupOption[]>([]);
const students = ref<StudentOption[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const activeTab = ref<'table' | 'graph'>('table');
const editingScore = ref<RatingRow | null>(null);
const detailScore = ref<RatingRow | null>(null);

const filters = reactive({
  branch_id: '',
  group_id: '',
  q: '',
});

const form = reactive({
  student_id: '' as number | '',
  group_id: '' as number | '',
  grade: 0,
});

const panelTitle = computed(() => {
  if (editingScore.value) return 'Edit grade';
  if (detailScore.value) return 'Rating details';
  return 'Add grade';
});

const isReadOnly = computed(() => Boolean(detailScore.value && !editingScore.value));

const maxGrade = computed(() => Math.max(...rows.value.map((row) => row.grade), 1));

const filteredStudents = computed(() => {
  if (!form.group_id) return students.value;
  return students.value.filter(
    (student) => student.group_id === form.group_id || student.group_id === null,
  );
});

function resetForm() {
  form.student_id = '';
  form.group_id = groups.value[0]?.id ?? '';
  form.grade = 0;
  formError.value = '';
  editingScore.value = null;
  detailScore.value = null;
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
    if (filters.q.trim()) params.q = filters.q.trim();
    const { data } = await client.get<ApiEnvelope<RatingRow[]>>('/scores/branch', { params });
    rows.value = data.data;
  } finally {
    loading.value = false;
  }
}

async function loadOptions() {
  const [branchRes, groupRes, studentRes] = await Promise.all([
    client.get<ApiEnvelope<Branch[]>>('/branch'),
    client.get<ApiEnvelope<GroupOption[]>>('/groups'),
    client.get<ApiEnvelope<{ id: number; full_name: string; group_id?: number | null }[]>>('/students'),
  ]);
  branches.value = branchRes.data.data;
  groups.value = groupRes.data.data.map((group) => ({
    id: group.id,
    name: group.name,
    branch_id: group.branch_id,
  }));
  students.value = studentRes.data.data.map((student) => ({
    id: student.id,
    full_name: student.full_name,
    group_id: student.group_id ?? null,
  }));
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
  } finally {
    panelLoading.value = false;
  }
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
  if (form.grade < 0 || form.grade > 100) {
    formError.value = 'Grade must be between 0 and 100';
    return;
  }

  saving.value = true;
  try {
    const payload = {
      student_id: form.student_id,
      group_id: form.group_id,
      grade: form.grade,
    };
    if (editingScore.value) {
      await client.patch(`/scores/${editingScore.value.id}`, payload);
    } else {
      await client.post('/scores/branch', payload);
    }
    closePanel();
    await loadRating();
  } catch {
    formError.value = editingScore.value ? 'Could not update grade' : 'Could not add grade';
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
    await loadRating();
  } catch {
    window.alert('Could not delete grade');
  } finally {
    deleting.value = false;
  }
}

function goStudent(score: RatingRow) {
  router.push(studentRoute(score.student_id));
}

function goGroup(score: RatingRow) {
  router.push(groupRoute(score.group_id));
}

function medalClass(no: number) {
  if (no === 1) return 'text-amber-500';
  if (no === 2) return 'text-fb-secondary';
  if (no === 3) return 'text-fb-blue-dark';
  return 'text-fb-icon';
}

onMounted(async () => {
  try {
    await Promise.all([loadOptions(), loadRating()]);
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-fb-text">Rating</h1>
      <button
        type="button"
        class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:bg-fb-blue-dark"
        @click="openCreatePanel"
      >
        + Add grade
      </button>
    </div>

    <div class="flex gap-2 border-b border-fb-line">
      <button
        type="button"
        class="-mb-px border-b-2 px-4 py-2 text-sm transition-colors"
        :class="activeTab === 'table'
          ? 'border-fb-blue font-medium text-fb-blue'
          : 'border-transparent text-fb-secondary hover:text-fb-secondary'"
        @click="activeTab = 'table'"
      >
        Table
      </button>
      <button
        type="button"
        class="-mb-px border-b-2 px-4 py-2 text-sm transition-colors"
        :class="activeTab === 'graph'
          ? 'border-fb-blue font-medium text-fb-blue'
          : 'border-transparent text-fb-secondary hover:text-fb-secondary'"
        @click="activeTab = 'graph'"
      >
        Graph
      </button>
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Branch</label>
        <select
          v-model="filters.branch_id"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm"
          @change="loadRating"
        >
          <option value="">All branches</option>
          <option v-for="branch in branches" :key="branch.id" :value="String(branch.id)">
            {{ branch.name }}
          </option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Group</label>
        <select
          v-model="filters.group_id"
          class="rounded-lg border border-fb-line px-3 py-2 text-sm"
          @change="loadRating"
        >
          <option value="">All groups</option>
          <option v-for="group in groups" :key="group.id" :value="String(group.id)">
            {{ group.name }}
          </option>
        </select>
      </div>
      <div class="min-w-[220px] flex-1">
        <label class="mb-1 block text-xs font-medium text-fb-secondary">Search</label>
        <input
          v-model="filters.q"
          type="search"
          placeholder="Student name"
          class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm"
          @keydown.enter="loadRating"
        />
      </div>
      <button
        type="button"
        class="rounded-lg border border-fb-line px-4 py-2 text-sm text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
        @click="loadRating"
      >
        Apply
      </button>
    </div>

    <div v-if="activeTab === 'table'" class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!rows.length" class="p-8 text-center text-fb-icon">No ratings yet</div>
      <table v-else class="w-full text-base">
        <thead class="border-b border-fb-line bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">№</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Name</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Group</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Branch</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Grade</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            class="cursor-pointer border-b border-fb-line hover:bg-fb-hover/40"
            @click="openDetailPanel(row.id)"
          >
            <td class="px-5 py-4 font-semibold" :class="medalClass(row.no)">{{ row.no }}</td>
            <td class="px-5 py-4 font-medium text-fb-text">{{ row.name }}</td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.group }}</td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.branch }}</td>
            <td class="px-5 py-4 font-semibold text-fb-blue">{{ row.grade }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else class="rounded-xl border border-fb-line bg-fb-card p-6">
      <div v-if="loading" class="py-12 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!rows.length" class="py-12 text-center text-fb-icon">No data for graph</div>
      <div v-else class="space-y-4">
        <div
          v-for="row in rows"
          :key="row.id"
          class="grid grid-cols-[140px_1fr_auto] items-center gap-4"
        >
          <button
            type="button"
            class="truncate text-left text-sm font-medium text-fb-text hover:text-fb-blue"
            @click="openDetailPanel(row.id)"
          >
            {{ row.name }}
          </button>
          <div class="h-4 rounded-full bg-fb-canvas">
            <div
              class="h-4 rounded-full bg-fb-blue"
              :style="{ width: `${(row.grade / maxGrade) * 100}%` }"
            />
          </div>
          <span class="w-12 text-right text-sm font-semibold text-fb-secondary">{{ row.grade }}</span>
        </div>
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

        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitScore">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Group</label>
              <select
                v-model="form.group_id"
                :disabled="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option v-for="group in groups" :key="group.id" :value="group.id">
                  {{ group.name }}
                </option>
              </select>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Student</label>
              <select
                v-model="form.student_id"
                :disabled="isReadOnly || Boolean(editingScore)"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option value="">Select student</option>
                <option v-for="student in filteredStudents" :key="student.id" :value="student.id">
                  {{ student.full_name }}
                </option>
              </select>
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Grade (0–100)</label>
              <input
                v-model.number="form.grade"
                type="number"
                min="0"
                max="100"
                step="0.1"
                required
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div
              v-if="detailScore"
              class="rounded-lg border border-fb-line bg-fb-canvas px-4 py-3 text-sm text-fb-secondary"
            >
              Rank #{{ detailScore.no }} in current list · {{ detailScore.branch }}
              <div class="mt-2 flex gap-3">
                <button type="button" class="text-fb-blue hover:underline" @click="goStudent(detailScore)">
                  Students →
                </button>
                <button type="button" class="text-fb-blue hover:underline" @click="goGroup(detailScore)">
                  Groups →
                </button>
              </div>
            </div>

            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>

          <div class="flex flex-wrap gap-2 border-t border-fb-line px-6 py-4">
            <template v-if="isReadOnly && detailScore">
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
                @click="deleteScore"
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
                {{ saving ? 'Saving…' : editingScore ? 'Save' : 'Create' }}
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
