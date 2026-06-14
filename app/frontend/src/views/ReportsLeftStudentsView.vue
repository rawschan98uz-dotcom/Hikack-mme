<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

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

interface LeftStudentRow {
  id: number;
  full_name: string;
  phone: string;
  status: number;
  status_label: string;
  branch_id: number;
  branch: string;
  group_id: number | null;
  group: string;
  balance: number;
  left_at: string;
}

interface Summary {
  left_active: number;
  left_trial: number;
  total: number;
}

interface Payload {
  summary: Summary;
  rows: LeftStudentRow[];
}

const STATUS_OPTIONS = [
  { value: '', label: 'All left' },
  { value: '8', label: 'Left active group' },
  { value: '7', label: 'Left after trial' },
] as const;

const router = useRouter();
const route = useRoute();

const isSettingsView = computed(() => route.path === '/left-students');

const rows = ref<LeftStudentRow[]>([]);
const summary = ref<Summary>({ left_active: 0, left_trial: 0, total: 0 });
const branches = ref<Branch[]>([]);
const groups = ref<GroupOption[]>([]);
const loading = ref(true);

const filters = reactive({
  status: '',
  branch_id: '',
  group_id: '',
  date_from: '',
  date_to: '',
  q: '',
});

const tableRows = computed(() =>
  rows.value.map((row) => ({
    id: row.id,
    full_name: row.full_name,
    phone: row.phone,
    status_label: row.status_label,
    group: row.group,
    group_id: row.group_id,
    branch: row.branch,
    balance: row.balance.toLocaleString(),
    left_at: row.left_at,
  })),
);

async function loadMeta() {
  const [branchRes, groupRes] = await Promise.all([
    client.get<ApiEnvelope<Branch[]>>('/branch'),
    client.get<ApiEnvelope<GroupOption[]>>('/groups'),
  ]);
  branches.value = branchRes.data.data;
  groups.value = groupRes.data.data;
}

async function loadRows() {
  loading.value = true;
  try {
    const params: Record<string, string> = {};
    if (filters.status) params.status = filters.status;
    if (filters.branch_id) params.branch_id = filters.branch_id;
    if (filters.group_id) params.group_id = filters.group_id;
    if (filters.date_from) params.date_from = filters.date_from;
    if (filters.date_to) params.date_to = filters.date_to;
    if (filters.q.trim()) params.q = filters.q.trim();
    const { data } = await client.get<ApiEnvelope<Payload>>('/reports/left-students', { params });
    summary.value = data.data.summary;
    rows.value = data.data.rows;
  } finally {
    loading.value = false;
  }
}

function openStudent(id: number) {
  router.push(studentRoute(id));
}

function openGroup(groupId: number) {
  router.push(groupRoute(groupId));
}

onMounted(async () => {
  await loadMeta();
  await loadRows();
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-[28px] font-normal text-fb-text">Students left the group</h1>
      <router-link
        v-if="!isSettingsView"
        to="/students"
        class="text-sm text-fb-blue hover:underline"
      >
        All students →
      </router-link>
    </div>

    <div v-if="!isSettingsView" class="grid grid-cols-1 gap-3 md:grid-cols-3">
      <div class="rounded-xl border border-fb-line bg-fb-card p-4 text-center">
        <div class="text-2xl font-bold text-fb-text">{{ summary.total }}</div>
        <div class="mt-1 text-sm text-fb-secondary">Total left</div>
      </div>
      <div class="rounded-xl border border-fb-line bg-fb-card p-4 text-center">
        <div class="text-2xl font-bold text-fb-blue">{{ summary.left_active }}</div>
        <div class="mt-1 text-sm text-fb-secondary">Left active group</div>
      </div>
      <div class="rounded-xl border border-fb-line bg-fb-card p-4 text-center">
        <div class="text-2xl font-bold text-amber-600">{{ summary.left_trial }}</div>
        <div class="mt-1 text-sm text-fb-secondary">Left after trial</div>
      </div>
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">Status</label>
        <select v-model="filters.status" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option v-for="opt in STATUS_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">Branch</label>
        <select v-model="filters.branch_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option value="">All</option>
          <option v-for="b in branches" :key="b.id" :value="String(b.id)">{{ b.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">Group</label>
        <select v-model="filters.group_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option value="">All</option>
          <option v-for="g in groups" :key="g.id" :value="String(g.id)">{{ g.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">From</label>
        <input v-model="filters.date_from" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">To</label>
        <input v-model="filters.date_to" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div class="min-w-[180px] flex-1">
        <label class="mb-1 block text-xs text-fb-secondary">Search</label>
        <input v-model="filters.q" type="search" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm" @keydown.enter="loadRows" />
      </div>
      <button type="button" class="rounded-lg border border-fb-line px-4 py-2 text-sm" @click="loadRows">Apply</button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!tableRows.length" class="p-8 text-center text-fb-icon">No students found</div>
      <table v-else class="w-full text-base">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Name</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Phone</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Status</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Group</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Branch</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Balance</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Date</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in tableRows"
            :key="row.id"
            class="cursor-pointer border-b hover:bg-fb-hover/40"
            @click="openStudent(row.id)"
          >
            <td class="px-5 py-4">{{ row.full_name }}</td>
            <td class="px-5 py-4">{{ row.phone }}</td>
            <td class="px-5 py-4">{{ row.status_label }}</td>
            <td class="px-5 py-4">
              <button
                v-if="row.group_id"
                type="button"
                class="text-fb-blue hover:underline"
                @click.stop="openGroup(row.group_id)"
              >
                {{ row.group }}
              </button>
              <span v-else>{{ row.group }}</span>
            </td>
            <td class="px-5 py-4">{{ row.branch }}</td>
            <td class="px-5 py-4">{{ row.balance }}</td>
            <td class="px-5 py-4">{{ row.left_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
