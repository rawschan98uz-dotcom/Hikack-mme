<script setup lang="ts">
import { computed, onMounted, reactive, ref , watch} from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { todayIso } from '../utils/dates';
import { t, type MessageKey } from '../i18n';
import { payMethodLabel } from '../i18n/labels';
import { confirmDialog, toast } from '../ui/feedback';
import { apiErrorMessage } from '../utils/apiError';
import { formatSum } from '../utils/wallet';

interface Branch {
  id: number;
  name: string;
}

type PageArray<T> = T[] & { has_more?: boolean; next_offset?: number | null };

interface Category {
  id: number;
  name: string;
}

interface ExpenseRow {
  id: number;
  date: string;
  branch_id: number | null;
  branch: string;
  category_id: number | null;
  category: string;
  description: string;
  payee: string;
  method: string;
  method_pay: string;
  sum: number;
  amount: number;
  creator: string;
  /** A salary payout: read-only here */
  is_salary_payout?: boolean;
}

const METHODS = [
  { value: 'cash', label: 'payMethod.cash' as MessageKey },
  { value: 'card', label: 'payMethod.card' as MessageKey },
  { value: 'transfer', label: 'payMethod.transfer' as MessageKey },
] as const;

const rows = ref<ExpenseRow[]>([]);
const categories = ref<Category[]>([]);
const branches = ref<Branch[]>([]);
const hasMore = ref(false);
const nextOffset = ref<number | null>(null);
const loadingMore = ref(false);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingRow = ref<ExpenseRow | null>(null);
const detailRow = ref<ExpenseRow | null>(null);

const showCategoriesModal = ref(false);
const newCategoryName = ref('');
const editingCategoryId = ref<number | null>(null);
const editingCategoryName = ref('');
const categoryError = ref('');
const categorySaving = ref(false);

const filters = reactive({ date_from: '', date_to: '', category_id: '', branch_id: '', q: '' });
const form = reactive({
  /** Owner (2026-09-28): every expense has its own date (today by default) and a branch */
  expense_date: todayIso(),
  branch_id: '' as number | '',
  category_id: '' as number | '',
  description: '',
  payee: '',
  method: 'cash' as (typeof METHODS)[number]['value'],
  amount: 0,
});

const isReadOnly = computed(() => Boolean(detailRow.value && !editingRow.value));
const panelTitle = computed(() =>
  editingRow.value ? t('expenses.editTitle') : detailRow.value ? t('expenses.detailTitle') : t('expenses.addTitle'),
);
const tableRows = computed(() =>
  rows.value.map((r) => ({
    id: r.id,
    date: r.date,
    branch: r.branch,
    category: r.category,
    description: r.description || '—',
    payee: r.payee || '—',
    method_pay: payMethodLabel(r.method, r.method_pay),
    sum: formatSum(r.sum),
    creator: r.creator,
  })),
);

function resetForm() {
  form.expense_date = todayIso();
  form.branch_id = branches.value.length === 1 ? branches.value[0].id : '';
  form.category_id = categories.value[0]?.id ?? '';
  form.description = '';
  form.payee = '';
  form.method = 'cash';
  form.amount = 0;
  formError.value = '';
  editingRow.value = null;
  detailRow.value = null;
}

function fillForm(row: ExpenseRow) {
  form.expense_date = row.date;
  form.branch_id = row.branch_id ?? '';
  form.category_id = row.category_id ?? '';
  form.description = row.description;
  form.payee = row.payee;
  form.method = row.method as (typeof METHODS)[number]['value'];
  form.amount = row.sum;
}

async function loadBranches() {
  try {
    const { data } = await client.get<ApiEnvelope<Branch[]>>('/branch');
    branches.value = data.data;
  } catch {
    branches.value = [];
  }
}

async function loadCategories() {
  const { data } = await client.get<ApiEnvelope<Category[]>>('/expense_types');
  categories.value = data.data;
}

async function addCategory() {
  const name = newCategoryName.value.trim();
  if (!name) return;
  categorySaving.value = true;
  categoryError.value = '';
  try {
    await client.post('/expense_types', { name });
    newCategoryName.value = '';
    await loadCategories();
    toast.success(t('toast.created'));
  } catch (err: unknown) {
    categoryError.value = apiErrorMessage(err, t('expenses.categoryCreateFailed'));
  } finally {
    categorySaving.value = false;
  }
}

function startEditCategory(c: Category) {
  editingCategoryId.value = c.id;
  editingCategoryName.value = c.name;
}

async function saveEditCategory(c: Category) {
  const name = editingCategoryName.value.trim();
  if (!name) return;
  categorySaving.value = true;
  categoryError.value = '';
  try {
    await client.patch(`/expense_types/${c.id}`, { name });
    editingCategoryId.value = null;
    await loadCategories();
    toast.success(t('toast.saved'));
  } catch (err: unknown) {
    categoryError.value = apiErrorMessage(err, t('expenses.categoryUpdateFailed'));
  } finally {
    categorySaving.value = false;
  }
}

async function deleteCategory(category: Category) {
  const ok = await confirmDialog({
    title: t('expenses.categoryDeleteConfirm', { name: category.name }),
    message: t('confirm.cannotUndo'),
    danger: true,
  });
  if (!ok) return;
  categorySaving.value = true;
  categoryError.value = '';
  try {
    await client.delete(`/expense_types/${category.id}`);
    await loadCategories();
    toast.success(t('toast.deleted'));
  } catch (err: unknown) {
    categoryError.value = apiErrorMessage(err, t('expenses.categoryDeleteFailed'));
  } finally {
    categorySaving.value = false;
  }
}

function listParams(offset = 0) {
  const params: Record<string, string | number> = { offset };
  if (filters.date_from) params.date_from = filters.date_from;
  if (filters.date_to) params.date_to = filters.date_to;
  if (filters.category_id) params.category_id = filters.category_id;
  if (filters.branch_id) params.branch_id = filters.branch_id;
  if (filters.q.trim()) params.q = filters.q.trim();
  return params;
}

async function loadRows() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<PageArray<ExpenseRow>>>('/expense', { params: listParams() });
    rows.value = [...data.data];
    hasMore.value = Boolean(data.data.has_more);
    nextOffset.value = data.data.next_offset ?? null;
  } finally {
    loading.value = false;
  }
}

/** "Show more": the next 200 (older) expenses. */
async function loadMore() {
  if (nextOffset.value === null) return;
  loadingMore.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<PageArray<ExpenseRow>>>('/expense', {
      params: listParams(nextOffset.value),
    });
    rows.value = [...rows.value, ...data.data];
    hasMore.value = Boolean(data.data.has_more);
    nextOffset.value = data.data.next_offset ?? null;
  } finally {
    loadingMore.value = false;
  }
}

function openCreate() {
  resetForm();
  showPanel.value = true;
}

async function openDetail(id: number) {
  resetForm();
  showPanel.value = true;
  panelLoading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<ExpenseRow>>(`/expense/${id}`);
    detailRow.value = data.data;
    fillForm(data.data);
  } finally {
    panelLoading.value = false;
  }
}

function startEdit() {
  if (detailRow.value) editingRow.value = detailRow.value;
}

function closePanel() {
  showPanel.value = false;
  resetForm();
}

async function submitForm() {
  formError.value = '';
  if (!Number.isInteger(form.amount) || form.amount <= 0) {
    formError.value = t('finance.amountPositive');
    return;
  }
  if (form.branch_id === '') {
    formError.value = t('expenses.branchRequired');
    return;
  }
  if (!form.expense_date || form.expense_date > todayIso()) {
    formError.value = t('expenses.dateNotFuture');
    return;
  }
  saving.value = true;
  try {
    const payload = {
      date: form.expense_date,
      branch_id: form.branch_id,
      category_id: form.category_id === '' ? null : form.category_id,
      description: form.description.trim(),
      payee: form.payee.trim(),
      method: form.method,
      amount: form.amount,
    };
    const wasEditing = Boolean(editingRow.value);
    if (editingRow.value) {
      await client.patch(`/expense/${editingRow.value.id}`, payload);
    } else {
      await client.post('/expense', payload);
    }
    closePanel();
    toast.success(wasEditing ? t('toast.saved') : t('expenses.created', { amount: formatSum(payload.amount) }));
    await loadRows();
  } catch (err: unknown) {
    formError.value = apiErrorMessage(err, t('errors.saveFailed'));
  } finally {
    saving.value = false;
  }
}

async function deleteRow() {
  if (!detailRow.value) return;
  const ok = await confirmDialog({
    title: t('expenses.deleteConfirm', { amount: formatSum(detailRow.value.sum) }),
    message: t('withdraw.deleteHint', { name: detailRow.value.category || detailRow.value.description || '—', date: detailRow.value.date }),
    danger: true,
  });
  if (!ok || !detailRow.value) return;
  deleting.value = true;
  try {
    await client.delete(`/expense/${detailRow.value.id}`);
    closePanel();
    toast.success(t('toast.deleted'));
    await loadRows();
  } catch (err: unknown) {
    // e.g. the month is closed, or it is a salary payout
    toast.error(apiErrorMessage(err, t('expenses.deleteFailed')));
  } finally {
    deleting.value = false;
  }
}

onMounted(async () => {
  await Promise.all([loadCategories(), loadBranches()]);
  await loadRows();
});

let searchDebounce: ReturnType<typeof setTimeout> | null = null;
watch(
  () => filters.q,
  (newQ, oldQ) => {
    if (newQ === oldQ) return;
    if (searchDebounce) clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      loadRows();
    }, 400);
  },
);

</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-fb-text">{{ t('nav.expenses') }}</h1>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
          @click="showCategoriesModal = true"
        >
          {{ t('expenses.manageCategories') }}
        </button>
        <button type="button" class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white" @click="openCreate">
          {{ t('expenses.addTitle') }}
        </button>
      </div>
    </div>

    <div class="flex flex-wrap items-end gap-3 rounded-xl border border-fb-line bg-fb-card p-4">
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">{{ t('common.branch') }}</label>
        <select v-model="filters.branch_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option value="">{{ t('common.all') }}</option>
          <option v-for="b in branches" :key="b.id" :value="String(b.id)">{{ b.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">{{ t('expenses.category') }}</label>
        <select v-model="filters.category_id" class="rounded-lg border border-fb-line px-3 py-2 text-sm">
          <option value="">{{ t('common.all') }}</option>
          <option v-for="c in categories" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">{{ t('common.from') }}</label>
        <input v-model="filters.date_from" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div>
        <label class="mb-1 block text-xs text-fb-secondary">{{ t('common.to') }}</label>
        <input v-model="filters.date_to" type="date" class="rounded-lg border border-fb-line px-3 py-2 text-sm" />
      </div>
      <div class="min-w-[180px] flex-1">
        <label class="mb-1 block text-xs text-fb-secondary">{{ t('common.search') }}</label>
        <input v-model="filters.q" type="search" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm" @keydown.enter="loadRows" />
      </div>
      <button type="button" class="rounded-lg border border-fb-line px-4 py-2 text-sm" @click="loadRows">{{ t('common.apply') }}</button>
    </div>

    <div class="overflow-hidden rounded-xl border border-fb-line bg-fb-card">
      <div v-if="loading" class="p-8 text-center text-fb-secondary">{{ t('common.loading') }}</div>
      <div v-else-if="!tableRows.length" class="p-8 text-center text-fb-icon">{{ t('expenses.empty') }}</div>
      <table v-else class="w-full text-base">
        <thead class="border-b bg-fb-canvas">
          <tr>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.date') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.branch') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('expenses.category') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.description') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('expenses.payee') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('expenses.method') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('common.amount') }}</th>
            <th class="px-5 py-4 text-left font-semibold text-fb-secondary">{{ t('finance.creator') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in tableRows" :key="row.id" class="cursor-pointer border-b hover:bg-fb-hover/40" @click="openDetail(row.id)">
            <td class="px-5 py-4">{{ row.date }}</td>
            <td class="px-5 py-4">{{ row.branch }}</td>
            <td class="px-5 py-4">{{ row.category }}</td>
            <td class="px-5 py-4">{{ row.description }}</td>
            <td class="px-5 py-4">{{ row.payee }}</td>
            <td class="px-5 py-4">{{ row.method_pay }}</td>
            <td class="px-5 py-4 font-semibold text-fb-blue">{{ row.sum }}</td>
            <td class="px-5 py-4">{{ row.creator }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="hasMore" class="border-t border-fb-line p-3 text-center">
        <button
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-blue hover:bg-fb-hover disabled:opacity-50"
          :disabled="loadingMore"
          @click="loadMore"
        >
          {{ loadingMore ? t('common.loading') : t('common.showMore') }}
        </button>
      </div>
    </div>

    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closePanel" />
      <div class="drawer-panel-fb max-w-lg">
        <div class="flex items-center justify-between border-b px-6 py-4">
          <h2 class="text-lg font-semibold">{{ panelTitle }}</h2>
          <button type="button" :aria-label="t('common.close')" @click="closePanel">✕</button>
        </div>
        <div v-if="panelLoading" class="p-6 text-fb-secondary">{{ t('common.loading') }}</div>
        <form v-else class="flex flex-1 flex-col overflow-hidden" @submit.prevent="submitForm">
          <div class="flex-1 space-y-4 overflow-y-auto p-6">
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('expenses.date') }}</label>
              <input
                v-model="form.expense_date"
                type="date"
                :max="todayIso()"
                :readonly="isReadOnly"
                required
                class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas"
              />
              <p v-if="!isReadOnly" class="mt-1 text-[11px] text-fb-secondary">
                {{ t('expenses.dateHint') }}
              </p>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('common.branch') }}</label>
              <select v-model="form.branch_id" :disabled="isReadOnly" required class="w-full rounded-lg border px-3 py-2">
                <option value="">— {{ t('staff.chooseBranch') }} —</option>
                <option v-for="b in branches" :key="b.id" :value="b.id">{{ b.name }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('expenses.category') }}</label>
              <select v-model="form.category_id" :disabled="isReadOnly" class="w-full rounded-lg border px-3 py-2">
                <option value="">— {{ t('expenses.noCategory') }} —</option>
                <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('common.description') }}</label>
              <textarea v-model="form.description" :readonly="isReadOnly" rows="2" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('expenses.payee') }}</label>
              <input v-model="form.payee" :readonly="isReadOnly" class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('expenses.method') }}</label>
              <select v-model="form.method" :disabled="isReadOnly" class="w-full rounded-lg border px-3 py-2">
                <option v-for="m in METHODS" :key="m.value" :value="m.value">{{ t(m.label) }}</option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('common.amount') }}</label>
              <input v-model.number="form.amount" type="number" min="1" step="1" :readonly="isReadOnly" required class="w-full rounded-lg border px-3 py-2 read-only:bg-fb-canvas" />
            </div>
            <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>
          </div>
          <div class="flex gap-2 border-t px-6 py-4">
            <template v-if="isReadOnly && detailRow">
              <!-- A salary payout is changed or cancelled only in "Зарплаты" (payroll and P&L must agree) -->
              <p v-if="detailRow.is_salary_payout" class="self-center text-xs text-fb-secondary">
                {{ t('expenses.salaryPayoutHint') }}
              </p>
              <template v-else>
                <button type="button" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" @click="startEdit">{{ t('common.edit') }}</button>
                <button type="button" class="rounded-lg border border-red-300 px-5 py-2 text-sm text-fb-danger" :disabled="deleting" @click="deleteRow">{{ t('common.delete') }}</button>
              </template>
            </template>
            <button v-else type="submit" class="rounded-lg bg-fb-blue px-5 py-2 text-sm text-white" :disabled="saving">
              {{ saving ? t('common.saving') : editingRow ? t('common.save') : t('common.create') }}
            </button>
            <button type="button" class="rounded-lg border px-5 py-2 text-sm" @click="closePanel">{{ t('common.cancel') }}</button>
          </div>
        </form>
      </div>
    </div>

    <!-- Category Management Modal -->
    <div v-if="showCategoriesModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/40" @click="showCategoriesModal = false" />
      <div class="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <div class="flex items-center justify-between border-b pb-4">
          <h3 class="text-lg font-semibold text-fb-text">{{ t('expenses.categoriesTitle') }}</h3>
          <button type="button" class="text-fb-secondary hover:text-fb-text" :aria-label="t('common.close')" @click="showCategoriesModal = false">✕</button>
        </div>

        <div class="mt-4 space-y-3">
          <!-- Add new category -->
          <form class="flex gap-2" @submit.prevent="addCategory">
            <input
              v-model="newCategoryName"
              type="text"
              :placeholder="t('expenses.newCategoryPlaceholder')"
              class="flex-1 rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              :disabled="categorySaving"
            />
            <button
              type="submit"
              class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:bg-fb-blue-dark disabled:opacity-50"
              :disabled="categorySaving || !newCategoryName.trim()"
            >
              {{ t('common.add') }}
            </button>
          </form>

          <p v-if="categoryError" class="text-xs text-fb-danger">{{ categoryError }}</p>

          <!-- List of categories -->
          <div class="max-h-64 space-y-2 overflow-y-auto pt-2">
            <div
              v-for="c in categories"
              :key="c.id"
              class="flex items-center justify-between rounded-lg border border-fb-line px-3 py-2 text-sm"
            >
              <div v-if="editingCategoryId === c.id" class="flex flex-1 items-center gap-2">
                <input
                  v-model="editingCategoryName"
                  type="text"
                  class="flex-1 rounded border border-fb-blue px-2 py-1 text-sm focus:outline-none"
                  @keydown.enter.prevent="saveEditCategory(c)"
                  @keydown.esc="editingCategoryId = null"
                />
                <button
                  type="button"
                  class="text-xs font-semibold text-fb-blue hover:underline"
                  @click="saveEditCategory(c)"
                >
                  {{ t('common.save') }}
                </button>
                <button
                  type="button"
                  class="text-xs text-fb-secondary hover:underline"
                  @click="editingCategoryId = null"
                >
                  {{ t('common.cancel') }}
                </button>
              </div>
              <template v-else>
                <span class="font-medium text-fb-text">{{ c.name }}</span>
                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    class="text-xs text-fb-blue hover:underline"
                    @click="startEditCategory(c)"
                  >
                    {{ t('common.edit') }}
                  </button>
                  <button
                    type="button"
                    class="text-xs text-fb-danger hover:underline"
                    @click="deleteCategory(c)"
                  >
                    {{ t('common.delete') }}
                  </button>
                </div>
              </template>
            </div>
            <div v-if="!categories.length" class="py-4 text-center text-xs text-fb-secondary">
              {{ t('expenses.noCategories') }}
            </div>
          </div>
        </div>

        <div class="mt-6 flex justify-end border-t pt-4">
          <button
            type="button"
            class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:text-fb-text"
            @click="showCategoriesModal = false"
          >
            {{ t('common.close') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
