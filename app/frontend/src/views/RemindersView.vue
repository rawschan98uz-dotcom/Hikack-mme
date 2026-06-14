<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { hasCreateFlag, routeWithoutCreate } from '../utils/crossLinks';
import { useAuthStore } from '../stores/auth';

interface Assignee {
  id: number;
  name: string;
}

interface ReminderRow {
  id: number;
  title: string;
  details: string;
  due_date: string;
  status: string;
  status_label: string;
  assigned_to_id: number | null;
  assigned_to: string;
  created_at: string;
}

interface ReminderPayload {
  items: ReminderRow[];
  buckets: Record<'overdue' | 'today' | 'future', ReminderRow[]>;
}

type ReminderTab = 'overdue' | 'today' | 'future';

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const loading = ref(true);
const saving = ref(false);
const completing = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const activeTab = ref<ReminderTab>('today');
const buckets = ref<ReminderPayload['buckets']>({ overdue: [], today: [], future: [] });
const assignees = ref<Assignee[]>([]);
const editingReminder = ref<ReminderRow | null>(null);
const detailReminder = ref<ReminderRow | null>(null);

const tabs: { key: ReminderTab; label: string }[] = [
  { key: 'overdue', label: 'Overdue' },
  { key: 'today', label: 'Today' },
  { key: 'future', label: 'Future' },
];

const form = reactive({
  title: '',
  details: '',
  due_date: new Date().toISOString().slice(0, 10),
  assigned_to_id: '' as number | '',
});

const panelTitle = computed(() => {
  if (editingReminder.value) return 'Edit reminder';
  if (detailReminder.value) return 'Reminder details';
  return 'Add reminder';
});

const isReadOnly = computed(() => Boolean(detailReminder.value && !editingReminder.value));
const rows = computed(() => buckets.value[activeTab.value] ?? []);

function resetForm() {
  form.title = '';
  form.details = '';
  form.due_date = new Date().toISOString().slice(0, 10);
  form.assigned_to_id = auth.user?.id ?? '';
  formError.value = '';
  editingReminder.value = null;
  detailReminder.value = null;
}

function fillForm(reminder: ReminderRow) {
  form.title = reminder.title;
  form.details = reminder.details;
  form.due_date = reminder.due_date;
  form.assigned_to_id = reminder.assigned_to_id ?? '';
}

async function loadReminders() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<ReminderPayload>>('/reminders');
    buckets.value = data.data.buckets;
    if (!buckets.value[activeTab.value]?.length) {
      const firstNonEmpty = tabs.find((tab) => buckets.value[tab.key].length);
      if (firstNonEmpty) {
        activeTab.value = firstNonEmpty.key;
      }
    }
  } finally {
    loading.value = false;
  }
}

async function loadAssignees() {
  const { data } = await client.get<ApiEnvelope<Assignee[]>>('/user', {
    params: { user_type: 'staff' },
  });
  assignees.value = data.data;
  if (!form.assigned_to_id && auth.user?.id) {
    form.assigned_to_id = auth.user.id;
  }
}

function openCreatePanel() {
  resetForm();
  showPanel.value = true;
}

async function openDetailPanel(reminderId: number) {
  resetForm();
  showPanel.value = true;
  panelLoading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<ReminderRow>>(`/reminders/${reminderId}`);
    detailReminder.value = data.data;
    fillForm(data.data);
  } finally {
    panelLoading.value = false;
  }
}

function startEdit() {
  if (!detailReminder.value) return;
  editingReminder.value = detailReminder.value;
}

function closePanel() {
  showPanel.value = false;
  resetForm();
}

function buildPayload() {
  return {
    title: form.title.trim(),
    details: form.details.trim(),
    due_date: form.due_date,
    assigned_to_id: form.assigned_to_id === '' ? null : form.assigned_to_id,
  };
}

async function submitReminder() {
  formError.value = '';
  if (!form.title.trim()) {
    formError.value = 'Enter a title';
    return;
  }
  if (!form.due_date) {
    formError.value = 'Select a due date';
    return;
  }

  saving.value = true;
  try {
    const payload = buildPayload();
    if (editingReminder.value) {
      await client.patch(`/reminders/${editingReminder.value.id}`, payload);
    } else {
      await client.post('/reminders', payload);
    }
    closePanel();
    await loadReminders();
  } catch {
    formError.value = editingReminder.value
      ? 'Could not update reminder'
      : 'Could not create reminder';
  } finally {
    saving.value = false;
  }
}

async function completeReminder(reminder: ReminderRow) {
  completing.value = true;
  try {
    await client.post(`/reminders/${reminder.id}/complete`);
    closePanel();
    await loadReminders();
  } catch {
    window.alert('Could not complete reminder');
  } finally {
    completing.value = false;
  }
}

async function deleteReminder() {
  if (!detailReminder.value) return;
  if (!window.confirm(`Delete "${detailReminder.value.title}"?`)) return;

  deleting.value = true;
  try {
    await client.delete(`/reminders/${detailReminder.value.id}`);
    closePanel();
    await loadReminders();
  } catch {
    window.alert('Could not delete reminder');
  } finally {
    deleting.value = false;
  }
}

function statusClass(status: string) {
  if (status === 'overdue') return 'bg-red-50 text-fb-danger';
  if (status === 'today') return 'bg-fb-hover text-fb-blue';
  return 'bg-fb-canvas text-fb-secondary';
}

function maybeCreateFromRoute() {
  if (!hasCreateFlag(route.query) || showPanel.value) return;
  openCreatePanel();
  router.replace(routeWithoutCreate(route));
}

watch(
  () => route.query.create,
  () => {
    maybeCreateFromRoute();
  },
);

onMounted(async () => {
  try {
    await Promise.all([loadAssignees(), loadReminders()]);
    maybeCreateFromRoute();
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-fb-text">Reminders</h1>
      <button
        type="button"
        class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:bg-fb-blue-dark"
        @click="openCreatePanel"
      >
        ADD NEW
      </button>
    </div>

    <div class="flex gap-2 border-b border-fb-line">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="-mb-px border-b-2 px-4 py-2 text-sm transition-colors"
        :class="activeTab === tab.key
          ? 'border-fb-blue font-medium text-fb-blue'
          : 'border-transparent text-fb-secondary hover:text-fb-secondary'"
        @click="activeTab = tab.key"
      >
        {{ tab.label }} ({{ buckets[tab.key]?.length ?? 0 }})
      </button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
      <div v-else-if="!rows.length" class="p-8 text-center text-fb-icon">
        No reminders in this tab
      </div>
      <table v-else class="w-full text-base">
        <thead class="border-b border-fb-line bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Title</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Details</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Due date</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Status</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">Assigned to</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            class="cursor-pointer border-b border-fb-line hover:bg-fb-hover/40"
            @click="openDetailPanel(row.id)"
          >
            <td class="px-5 py-4 font-medium text-fb-text">{{ row.title }}</td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.details || '—' }}</td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.due_date }}</td>
            <td class="px-5 py-4">
              <span class="rounded-full px-2 py-0.5 text-xs capitalize" :class="statusClass(row.status)">
                {{ row.status_label }}
              </span>
            </td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.assigned_to }}</td>
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

        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitReminder">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Title</label>
              <input
                v-model="form.title"
                type="text"
                required
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Details</label>
              <textarea
                v-model="form.details"
                rows="4"
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Due date</label>
              <input
                v-model="form.due_date"
                type="date"
                required
                :readonly="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 read-only:bg-fb-canvas focus:border-fb-blue focus:outline-none"
              />
            </div>

            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Assigned to</label>
              <select
                v-model="form.assigned_to_id"
                :disabled="isReadOnly"
                class="w-full rounded-lg border border-fb-line px-3 py-2 disabled:bg-fb-canvas"
              >
                <option value="">— Unassigned —</option>
                <option v-for="person in assignees" :key="person.id" :value="person.id">
                  {{ person.name }}
                </option>
              </select>
            </div>

            <div
              v-if="detailReminder"
              class="rounded-lg border border-fb-line bg-fb-canvas px-4 py-3 text-sm text-fb-secondary"
            >
              Status:
              <span
                class="ml-2 rounded-full px-2 py-0.5 text-xs capitalize"
                :class="statusClass(detailReminder.status)"
              >
                {{ detailReminder.status_label }}
              </span>
            </div>

            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>

          <div class="flex flex-wrap gap-2 border-t border-fb-line px-6 py-4">
            <template v-if="isReadOnly && detailReminder">
              <button
                type="button"
                class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white hover:opacity-90"
                @click="startEdit"
              >
                Edit
              </button>
              <button
                type="button"
                class="rounded-lg border border-emerald-300 px-5 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
                :disabled="completing"
                @click="completeReminder(detailReminder)"
              >
                Task done
              </button>
              <button
                type="button"
                class="rounded-lg border border-red-300 px-5 py-2 text-sm font-medium text-fb-danger hover:bg-red-50 disabled:opacity-50"
                :disabled="deleting"
                @click="deleteReminder"
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
                {{ saving ? 'Saving…' : editingReminder ? 'Save' : 'Create' }}
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
