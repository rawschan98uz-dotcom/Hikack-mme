<script setup lang="ts">
import { todayIso } from '../utils/dates';
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { hasCreateFlag, routeWithoutCreate, studentRoute } from '../utils/crossLinks';
import { onCardsReturn } from '../utils/cardStack';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';

interface Assignee {
  id: number;
  name: string;
  role?: string;
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
  /** Set for automatic reminders about a student (e.g. left without paying). */
  student_id?: number | null;
  /** 'unpaid_leave' = student left without paying (pinned on top, locked until paid). */
  kind?: string;
  resolution?: string;
  locked?: boolean;
  debt_months?: number;
  debt_amount?: number;
  created_at: string;
}

interface ReminderPayload {
  items: ReminderRow[];
  pinned?: ReminderRow[];
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
const pinned = ref<ReminderRow[]>([]);
const assignees = ref<Assignee[]>([]);
const editingReminder = ref<ReminderRow | null>(null);
const detailReminder = ref<ReminderRow | null>(null);

const tabs: { key: ReminderTab; label: string }[] = [
  { key: 'overdue', label: 'Просрочено' },
  { key: 'today', label: 'Сегодня' },
  { key: 'future', label: 'Предстоит' },
];

function getLocalDateStr() {
  return todayIso();
}

const form = reactive({
  title: '',
  details: '',
  due_date: getLocalDateStr(),
  assigned_to_id: '' as number | '',
});

const confirmModal = reactive({
  show: false,
  title: '',
  message: '',
  onConfirm: null as (() => void) | null,
});

const alertModal = reactive({
  show: false,
  message: '',
});

const canWriteReminders = computed(() => auth.can(PERM.REMINDERS_WRITE));

/** Office staff close any reminder they see; a teacher only the ones given to them. */
function canComplete(reminder: ReminderRow) {
  if (reminder.kind === 'unpaid_leave') return canWriteReminders.value;
  return canWriteReminders.value || reminder.assigned_to_id === auth.user?.id;
}

/** The clock counter in the header listens to this. */
function notifyRemindersChanged() {
  window.dispatchEvent(new Event('reminders-changed'));
}

const writeOffModal = reactive({
  show: false,
  reminder: null as ReminderRow | null,
  reason: '',
  error: '',
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
  form.due_date = getLocalDateStr();
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

async function loadReminders(quiet = false) {
  if (!quiet) loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<ReminderPayload>>('/reminders');
    buckets.value = data.data.buckets;
    pinned.value = data.data.pinned ?? [];
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
  // Only people who create reminders need the list (active staff and teachers, never students)
  if (!canWriteReminders.value) return;
  const { data } = await client.get<ApiEnvelope<Assignee[]>>('/reminders/assignees');
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

/**
 * A click opens the window that solves the problem:
 * online money without a course price -> the student's edit form (put them into a group, the копилка counts the months);
 * "left without paying" -> the student's card (take the payment); anything else -> the reminder itself.
 */
function openReminder(row: ReminderRow) {
  if (row.kind === 'online_payment_check' && row.student_id) {
    router.push(studentRoute(row.student_id, { edit: '1' }));
    return;
  }
  if (row.kind === 'unpaid_leave' && row.student_id) {
    router.push(studentRoute(row.student_id));
    return;
  }
  openDetailPanel(row.id);
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
    notifyRemindersChanged();
  } catch (err: any) {
    formError.value =
      err.response?.data?.message ||
      err.response?.data?.error ||
      (editingReminder.value ? 'Could not update reminder' : 'Could not create reminder');
  } finally {
    saving.value = false;
  }
}

function formatMoney(value: number) {
  return Math.round(value).toLocaleString('ru-RU');
}

// CEO only: close a "left without paying" reminder without payment; the reason is kept
function writeOffReminder(reminder: ReminderRow) {
  writeOffModal.reminder = reminder;
  writeOffModal.reason = '';
  writeOffModal.error = '';
  writeOffModal.show = true;
}

async function confirmWriteOff() {
  if (!writeOffModal.reminder) return;
  const reason = writeOffModal.reason.trim();
  if (reason.length < 3) {
    writeOffModal.error = 'Укажите причину (минимум 3 символа).';
    return;
  }
  writeOffModal.show = false;
  await completeReminder(writeOffModal.reminder, reason);
}

async function completeReminder(reminder: ReminderRow, writeOffReason = '') {
  if (reminder.locked && !writeOffReason) return;
  completing.value = true;
  try {
    await client.post(`/reminders/${reminder.id}/complete`, writeOffReason ? { write_off_reason: writeOffReason } : {});
    closePanel();
    await loadReminders();
    notifyRemindersChanged();
  } catch (err: any) {
    alertModal.message =
      err.response?.data?.message ||
      err.response?.data?.error ||
      'Could not complete reminder';
    alertModal.show = true;
  } finally {
    completing.value = false;
  }
}

function requestDeleteReminder() {
  if (!detailReminder.value) return;
  confirmModal.title = 'Delete reminder';
  confirmModal.message = `Are you sure you want to delete "${detailReminder.value.title}"?`;
  confirmModal.onConfirm = executeDeleteReminder;
  confirmModal.show = true;
}

async function executeDeleteReminder() {
  if (!detailReminder.value) return;
  confirmModal.show = false;

  deleting.value = true;
  try {
    await client.delete(`/reminders/${detailReminder.value.id}`);
    closePanel();
    await loadReminders();
    notifyRemindersChanged();
  } catch (err: any) {
    alertModal.message =
      err.response?.data?.message ||
      err.response?.data?.error ||
      'Could not delete reminder';
    alertModal.show = true;
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

// A card opened from here is closed: show fresh data without the "Loading…" blink
onCardsReturn(-1, () => void loadReminders(true));

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
        v-if="canWriteReminders"
        type="button"
        class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:bg-fb-blue-dark"
        @click="openCreatePanel"
      >
        ADD NEW
      </button>
    </div>

    <div v-if="pinned.length" class="rounded-xl border-2 border-rose-300 bg-rose-50 p-4">
      <h2 class="mb-3 text-[15px] font-semibold text-rose-800">
        ⚠️ Ушли, не заплатив — {{ pinned.length }}. Позвоните и решите вопрос.
      </h2>
      <ul class="space-y-2">
        <li
          v-for="item in pinned"
          :key="item.id"
          class="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-rose-200 bg-white px-4 py-3"
        >
          <div class="min-w-0 cursor-pointer" title="Открыть карточку ученика" @click="openReminder(item)">
            <p class="text-sm font-semibold text-fb-text">{{ item.title }}</p>
            <p class="mt-0.5 whitespace-pre-line text-xs text-fb-secondary">{{ item.details }}</p>
            <p v-if="item.locked" class="mt-1 text-xs font-semibold text-rose-700">
              Осталось оплатить: {{ item.debt_months }} мес.<span v-if="item.debt_amount"> (≈ {{ formatMoney(item.debt_amount) }} сум)</span>
            </p>
            <p v-else class="mt-1 text-xs font-semibold text-emerald-700">✓ Долг оплачен — можно закрыть</p>
          </div>
          <div class="flex shrink-0 gap-2">
            <button
              v-if="item.student_id"
              type="button"
              class="rounded-lg border border-fb-line px-3 py-1.5 text-xs font-medium text-fb-blue hover:bg-fb-hover"
              @click="router.push(studentRoute(item.student_id))"
            >
              Открыть ученика
            </button>
            <button
              v-if="auth.isCeo && item.locked"
              type="button"
              class="rounded-lg border border-rose-300 px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100"
              :disabled="completing"
              @click="writeOffReminder(item)"
            >
              Списать долг
            </button>
            <button
              v-if="canWriteReminders"
              type="button"
              class="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-medium text-white"
              :class="item.locked ? 'cursor-not-allowed opacity-35' : 'shadow-md ring-2 ring-rose-300 hover:bg-rose-700'"
              :disabled="item.locked || completing"
              :title="item.locked ? 'Сначала примите оплату в карточке ученика' : 'Долг оплачен — закрыть напоминание'"
              @click="completeReminder(item)"
            >
              Решено
            </button>
          </div>
        </li>
      </ul>
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
            <th class="px-5 py-4" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            class="cursor-pointer border-b border-fb-line hover:bg-fb-hover/40"
            @click="openReminder(row)"
          >
            <td class="px-5 py-4 font-medium text-fb-text">
              {{ row.title }}
              <button
                v-if="row.student_id"
                type="button"
                class="ml-2 text-xs font-medium text-fb-blue hover:underline"
                @click.stop="router.push(studentRoute(row.student_id))"
              >
                Открыть ученика
              </button>
            </td>
            <td class="px-5 py-4 whitespace-pre-line text-fb-secondary">{{ row.details || '—' }}</td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.due_date }}</td>
            <td class="px-5 py-4">
              <span class="rounded-full px-2 py-0.5 text-xs capitalize" :class="statusClass(row.status)">
                {{ row.status_label }}
              </span>
            </td>
            <td class="px-5 py-4 text-fb-secondary">{{ row.assigned_to }}</td>
            <td class="px-5 py-4 text-right">
              <button
                v-if="canComplete(row)"
                type="button"
                class="whitespace-nowrap rounded-lg border border-emerald-300 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
                :disabled="completing"
                @click.stop="completeReminder(row)"
              >
                ✓ Выполнено
              </button>
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

        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitReminder">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Title</label>
              <input
                v-model="form.title"
                type="text"
                required
                maxlength="255"
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
                <option value="">— Общее (видит весь офис) —</option>
                <option
                  v-if="form.assigned_to_id !== '' && !assignees.some((p) => p.id === form.assigned_to_id)"
                  :value="form.assigned_to_id"
                >
                  {{ detailReminder?.assigned_to || '—' }}
                </option>
                <option v-for="person in assignees" :key="person.id" :value="person.id">
                  {{ person.name }}{{ person.role ? ` — ${person.role}` : '' }}
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
              <p v-if="detailReminder.locked" class="w-full text-xs text-rose-700">
                Долг не оплачен: закрыть, изменить или удалить нельзя. Примите оплату в карточке ученика.
              </p>
              <button
                v-if="canWriteReminders"
                type="button"
                class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-35"
                :disabled="detailReminder.locked"
                @click="startEdit"
              >
                Edit
              </button>
              <button
                v-if="canComplete(detailReminder)"
                type="button"
                class="rounded-lg border border-emerald-300 px-5 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-35"
                :disabled="completing || detailReminder.locked"
                @click="completeReminder(detailReminder)"
              >
                Task done
              </button>
              <button
                v-if="auth.isCeo && detailReminder.locked"
                type="button"
                class="rounded-lg border border-rose-300 px-5 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50"
                :disabled="completing"
                @click="writeOffReminder(detailReminder)"
              >
                Списать долг
              </button>
              <button
                v-if="canWriteReminders"
                type="button"
                class="rounded-lg border border-red-300 px-5 py-2 text-sm font-medium text-fb-danger hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-35"
                :disabled="deleting || detailReminder.locked"
                @click="requestDeleteReminder"
              >
                Delete
              </button>
            </template>
            <template v-else>
              <button
                v-if="canWriteReminders"
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

    <!-- Confirm modal -->
    <div v-if="confirmModal.show" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div class="bg-fb-card rounded-2xl shadow-2xl max-w-sm w-full overflow-hidden">
        <div class="px-6 py-4 border-b border-fb-line">
          <h2 class="text-lg font-semibold text-fb-text">{{ confirmModal.title }}</h2>
        </div>
        <div class="px-6 py-5">
          <p class="text-[15px] text-fb-secondary">{{ confirmModal.message }}</p>
        </div>
        <div class="px-6 py-4 border-t border-fb-line flex justify-end gap-3">
          <button
            type="button"
            class="rounded-lg border border-fb-line px-5 py-2 text-sm font-medium text-fb-secondary hover:bg-fb-hover"
            @click="confirmModal.show = false"
          >
            Cancel
          </button>
          <button
            type="button"
            class="rounded-lg bg-fb-danger px-5 py-2 text-sm font-medium text-white hover:opacity-90"
            @click="confirmModal.onConfirm?.()"
          >
            Delete
          </button>
        </div>
      </div>
    </div>

    <!-- Write-off modal (CEO): close a "left without paying" reminder without payment -->
    <div v-if="writeOffModal.show" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div class="w-full max-w-md overflow-hidden rounded-2xl bg-fb-card shadow-2xl">
        <div class="border-b border-fb-line px-6 py-4">
          <h2 class="text-lg font-semibold text-rose-700">Списать долг без оплаты?</h2>
        </div>
        <div class="space-y-3 px-6 py-5">
          <p class="text-[15px] font-medium text-fb-text">{{ writeOffModal.reminder?.title }}</p>
          <p v-if="writeOffModal.reminder?.debt_months" class="text-sm text-fb-secondary">
            Будет списано: {{ writeOffModal.reminder.debt_months }} мес.<span v-if="writeOffModal.reminder.debt_amount">
              (≈ {{ formatMoney(writeOffModal.reminder.debt_amount) }} сум)</span>.
            Долг исчезнет из отчётов, в отчёте «Ушедшие» останется пометка «Списано» с причиной.
          </p>
          <label class="block text-sm font-medium text-fb-secondary">Причина (обязательно)</label>
          <textarea
            v-model="writeOffModal.reason"
            rows="3"
            class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
            placeholder="Например: переехал в другой город, связаться не удалось"
          />
          <p v-if="writeOffModal.error" class="text-sm text-fb-danger">{{ writeOffModal.error }}</p>
        </div>
        <div class="flex justify-end gap-3 border-t border-fb-line px-6 py-4">
          <button
            type="button"
            class="rounded-lg border border-fb-line px-5 py-2 text-sm font-medium text-fb-secondary hover:bg-fb-hover"
            @click="writeOffModal.show = false"
          >
            Отмена
          </button>
          <button
            type="button"
            class="rounded-lg bg-rose-600 px-5 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50"
            :disabled="completing"
            @click="confirmWriteOff"
          >
            Списать
          </button>
        </div>
      </div>
    </div>

    <!-- Alert modal -->
    <div v-if="alertModal.show" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div class="bg-fb-card rounded-2xl shadow-2xl max-w-sm w-full overflow-hidden">
        <div class="px-6 py-4 border-b border-fb-line">
          <h2 class="text-lg font-semibold text-fb-danger">Error</h2>
        </div>
        <div class="px-6 py-5">
          <p class="text-[15px] text-fb-secondary">{{ alertModal.message }}</p>
        </div>
        <div class="px-6 py-4 border-t border-fb-line flex justify-end">
          <button
            type="button"
            class="rounded-lg bg-fb-blue px-6 py-2 text-sm font-medium text-white hover:opacity-90"
            @click="alertModal.show = false"
          >
            OK
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
