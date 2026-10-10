<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue';
import { formatMoney } from '../utils/money';
import SkeletonBlock from '../components/SkeletonBlock.vue';
import EmptyState from '../components/EmptyState.vue';
import { useRoute, useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { useAuthStore } from '../stores/auth';
import { hasCreateFlag, routeWithoutCreate } from '../utils/crossLinks';
import { todayIso } from '../utils/dates';
import { t } from '../i18n';
import { confirmDialog, toast } from '../ui/feedback';
import { apiErrorMessage } from '../utils/apiError';
import CourseLevelBadge from '../components/CourseLevelBadge.vue';
import {
  buildCourseCardDisplay,
  courseCodeHint,
  isValidCourseCode,
  normalizeCourseCode,
  type CefrLevel,
} from '../utils/courseLevel';

// One record of the price history: "from this day the course costs X"
interface PriceRecord {
  id: number;
  price: number;
  valid_from: string;
  is_first: boolean;
  is_current: boolean;
  is_future: boolean;
  created_by: string;
}

interface CourseData {
  id: number;
  name: string;
  code: string;
  price: number;
  next_price?: { price: number; valid_from: string } | null;
  price_history?: PriceRecord[];
  lesson_duration: number;
  course_duration: number;
  description: string;
}

interface CourseRow {
  id: number;
  name: string;
  code: string;
  price: number;
  next_price?: { price: number; valid_from: string } | null;
  lesson_duration: number;
  course_duration: number;
  description: string;
  level: CefrLevel | null;
  levelColor: string;
  starCount: number;
  cardTitle: string;
  badgeLabel: string;
  watermarkLabel: string;
}

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const rows = ref<CourseRow[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingCourse = ref<CourseRow | null>(null);
// Price history of the course in the panel; only the CEO changes prices
const priceHistory = ref<PriceRecord[]>([]);
const priceEdit = reactive({ id: 0, price: '', valid_from: '', saving: false, error: '' });

const lessonDurations = [45, 60, 90, 120];

const form = reactive({
  name: '',
  code: '',
  lesson_duration: 90,
  course_duration: 12,
  price: '',
  price_from: todayIso(),
  description: '',
});

function formatPrice(value: number) {
  return formatMoney(value);
}

function formatDay(iso: string) {
  const [year, month, day] = iso.split('-');
  return `${day}.${month}.${year}`;
}

function parsePrice(text: string | number) {
  return Number(String(text).replace(/\s/g, '')) || 0;
}

function enrichCourse(course: CourseData): CourseRow {
  const display = buildCourseCardDisplay(course.code);
  return {
    ...course,
    code: display.code,
    level: display.level,
    levelColor: display.levelColor,
    starCount: display.starCount,
    cardTitle: display.cardTitle,
    badgeLabel: display.badgeLabel,
    watermarkLabel: display.watermarkLabel,
  };
}

function resetForm() {
  form.name = '';
  form.code = '';
  form.lesson_duration = 90;
  form.course_duration = 12;
  form.price = '';
  form.price_from = todayIso();
  form.description = '';
  formError.value = '';
  editingCourse.value = null;
  priceHistory.value = [];
  priceEdit.id = 0;
}

function fillForm(course: CourseData) {
  form.name = course.name;
  form.code = course.code;
  form.lesson_duration = course.lesson_duration;
  form.course_duration = course.course_duration;
  form.price = String(course.price);
  form.price_from = todayIso();
  form.description = course.description;
  priceHistory.value = course.price_history ?? [];
}

function startPriceEdit(record: PriceRecord) {
  priceEdit.id = record.id;
  priceEdit.price = String(record.price);
  priceEdit.valid_from = record.valid_from;
  priceEdit.error = '';
}

// The server answers with the whole course: the panel and the cards show the new state at once
async function applyCourse(course: CourseData) {
  editingCourse.value = enrichCourse(course);
  form.price = String(course.price);
  priceHistory.value = course.price_history ?? [];
  await loadCourses();
}

async function savePriceEdit() {
  if (!editingCourse.value) return;
  priceEdit.saving = true;
  priceEdit.error = '';
  try {
    const { data } = await client.patch<ApiEnvelope<CourseData>>(
      `/courses/${editingCourse.value.id}/prices/${priceEdit.id}`,
      { price: parsePrice(priceEdit.price), valid_from: priceEdit.valid_from },
    );
    priceEdit.id = 0;
    await applyCourse(data.data);
    toast.success(t('courses.priceFixed'));
  } catch (err: unknown) {
    priceEdit.error = apiErrorMessage(err, t('courses.priceFixFailed'));
  } finally {
    priceEdit.saving = false;
  }
}

async function deletePriceRecord(record: PriceRecord) {
  if (!editingCourse.value) return;
  const ok = await confirmDialog({
    title: t('courses.deletePriceConfirm', { price: formatPrice(record.price), date: formatDay(record.valid_from) }),
    message: t('courses.deletePriceHint'),
    danger: true,
  });
  if (!ok || !editingCourse.value) return;
  try {
    const { data } = await client.delete<ApiEnvelope<CourseData>>(
      `/courses/${editingCourse.value.id}/prices/${record.id}`,
    );
    await applyCourse(data.data);
    toast.success(t('courses.priceDeleted'));
  } catch (err: unknown) {
    toast.error(apiErrorMessage(err, t('courses.priceDeleteFailed')));
  }
}

function openPanel() {
  resetForm();
  showPanel.value = true;
}

function closePanel() {
  showPanel.value = false;
  resetForm();
}

async function openCourse(id: number) {
  resetForm();
  showPanel.value = true;
  panelLoading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<CourseData>>(`/courses/${id}`);
    editingCourse.value = enrichCourse(data.data);
    fillForm(data.data);
  } finally {
    panelLoading.value = false;
  }
}

async function deleteCourse() {
  if (!editingCourse.value) return;
  const ok = await confirmDialog({
    title: t('courses.deleteConfirm', { name: editingCourse.value.name }),
    message: t('confirm.cannotUndo'),
    danger: true,
  });
  if (!ok || !editingCourse.value) return;
  deleting.value = true;
  try {
    await client.delete(`/courses/${editingCourse.value.id}`);
    closePanel();
    toast.success(t('toast.deleted'));
    await loadCourses();
  } catch (err: unknown) {
    formError.value = apiErrorMessage(err, t('courses.deleteFailed'));
  } finally {
    deleting.value = false;
  }
}

async function loadCourses() {
  const { data } = await client.get<ApiEnvelope<CourseData[]>>('/courses');
  rows.value = data.data.map(enrichCourse);
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

onMounted(async () => {
  try {
    await loadCourses();
    maybeCreateFromRoute();
  } finally {
    loading.value = false;
  }
});

async function saveCourse() {
  formError.value = '';
  if (!form.name.trim()) {
    formError.value = t('courses.nameRequired');
    return;
  }
  // A course keeps the code it already has (old ones may not fit the rule): only a new code is checked
  const codeUnchanged = Boolean(editingCourse.value) && normalizeCourseCode(form.code) === editingCourse.value?.code;
  if (!codeUnchanged && !isValidCourseCode(form.code)) {
    formError.value = t('courses.codeInvalid', { hint: courseCodeHint() });
    return;
  }

  saving.value = true;
  try {
    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      code: normalizeCourseCode(form.code),
      lesson_duration: form.lesson_duration,
      course_duration: Number(form.course_duration) || 12,
      price: parsePrice(form.price),
      description: form.description.trim(),
    };
    const wasEditing = Boolean(editingCourse.value);
    if (editingCourse.value) {
      // A new price never rewrites the past: it starts on the chosen day
      if (auth.isCeo && form.price_from) payload.price_from = form.price_from;
      await client.patch(`/courses/${editingCourse.value.id}`, payload);
    } else {
      await client.post('/courses', payload);
    }
    await loadCourses();
    closePanel();
    toast.success(wasEditing ? t('toast.saved') : t('courses.created'));
  } catch (err: unknown) {
    formError.value = apiErrorMessage(err, t('errors.saveFailed'));
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="!mb-0 text-[28px] font-normal text-fb-secondary">{{ t('nav.courses') }}</h1>
      <button
        type="button"
        class="px-6 py-2.5 rounded-full bg-fb-blue text-white text-[14px] font-semibold tracking-wide hover:opacity-90"
        @click="openPanel"
      >
        {{ t('common.addNew') }}
      </button>
    </div>

    <SkeletonBlock v-if="loading" variant="cards" :rows="6" />
    <EmptyState
      v-else-if="!rows.length"
      icon="courses"
      :title="t('courses.emptyTitle')"
      :hint="t('courses.emptyHint')"
      :action-label="t('courses.addFirst')"
      @action="openPanel"
    />
    <div v-else class="mx-auto w-[90%]">
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        <article
          v-for="row in rows"
          :key="row.id"
          class="w-full cursor-pointer overflow-hidden rounded-xl border border-fb-line bg-fb-card shadow-fb-card transition-all hover:ring-2 hover:ring-fb-blue/40"
          @click="openCourse(row.id)"
        >
          <div class="aspect-square bg-fb-canvas p-2.5">
            <CourseLevelBadge
              :label="row.badgeLabel"
              :color="row.levelColor"
              :star-count="row.starCount"
            />
          </div>

          <div class="px-3.5 pb-3.5 pt-2.5">
            <h3 class="mb-1 truncate text-[15px] font-semibold text-fb-text">
              {{ row.cardTitle }}
            </h3>
            <p class="truncate text-[13px] text-fb-icon">
              {{ formatPrice(row.price) }}
            </p>
            <p v-if="row.next_price" class="truncate text-[12px] text-amber-700">
              {{ t('courses.fromDate', { date: formatDay(row.next_price.valid_from) }) }} — {{ formatPrice(row.next_price.price) }}
            </p>
          </div>
        </article>
      </div>
    </div>

    <!-- Right drawer: Add New Item -->
    <div v-if="showPanel" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closePanel" />
      <aside class="drawer-panel-fb max-w-md h-full">
        <div class="px-6 py-5 border-b border-fb-line flex items-center justify-between">
          <h2 class="text-[22px] font-semibold text-fb-text">
            {{ editingCourse ? t('courses.editTitle') : t('courses.addTitle') }}
          </h2>
          <button
            type="button"
            class="text-fb-icon hover:text-fb-secondary text-2xl leading-none"
            :aria-label="t('common.close')"
            @click="closePanel"
          >
            ×
          </button>
        </div>

        <form class="flex-1 overflow-y-auto px-6 py-6 space-y-5" @submit.prevent="saveCourse">
          <SkeletonBlock v-if="panelLoading" variant="lines" :rows="6" />
          <template v-else>
          <div>
            <label class="block text-[15px] font-medium text-fb-secondary mb-2">{{ t('common.name') }}</label>
            <input
              v-model="form.name"
              type="text"
              placeholder="English B2"
              class="w-full h-11 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
            />
          </div>

          <div>
            <label class="block text-[15px] font-medium text-fb-secondary mb-2">{{ t('courses.code') }}</label>
            <input
              v-model="form.code"
              type="text"
              placeholder="b2"
              required
              class="w-full h-11 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
            />
            <p class="mt-1.5 text-[13px] text-fb-icon">
              {{ courseCodeHint() }}. {{ t('courses.codeCardHint') }}
            </p>
          </div>

          <div>
            <label class="block text-[15px] font-medium text-fb-secondary mb-2">{{ t('courses.lessonDuration') }}</label>
            <select
              v-model.number="form.lesson_duration"
              class="w-full h-11 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue bg-fb-card"
            >
              <option v-for="mins in lessonDurations" :key="mins" :value="mins">
                {{ t('courses.minutes', { count: mins }) }}
              </option>
            </select>
          </div>

          <div>
            <label class="block text-[15px] font-medium text-fb-secondary mb-2">{{ t('courses.courseDuration') }}</label>
            <input
              v-model.number="form.course_duration"
              type="number"
              min="1"
              class="w-full h-11 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
            />
          </div>

          <div>
            <label class="block text-[15px] font-medium text-fb-secondary mb-2">{{ t('common.price') }}</label>
            <input
              v-model="form.price"
              type="text"
              inputmode="numeric"
              :readonly="Boolean(editingCourse) && !auth.isCeo"
              class="w-full h-11 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue read-only:bg-fb-canvas"
            />
            <p v-if="editingCourse && !auth.isCeo" class="mt-1.5 text-[13px] text-fb-icon">
              {{ t('courses.onlyCeoPrice') }}
            </p>
          </div>

          <template v-if="editingCourse">
            <div v-if="auth.isCeo">
              <label class="block text-[15px] font-medium text-fb-secondary mb-2">{{ t('courses.newPriceFrom') }}</label>
              <input
                v-model="form.price_from"
                type="date"
                class="w-full h-11 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
              />
              <p class="mt-1.5 text-[13px] text-fb-icon">
                {{ t('courses.newPriceHint') }}
              </p>
            </div>

            <div v-if="priceHistory.length">
              <label class="block text-[15px] font-medium text-fb-secondary mb-2">{{ t('courses.priceHistory') }}</label>
              <ul class="divide-y divide-fb-line rounded-lg border border-fb-line text-[14px]">
                <li v-for="record in priceHistory" :key="record.id" class="px-3 py-2.5">
                  <div v-if="priceEdit.id !== record.id" class="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span class="text-fb-secondary">
                      {{ record.is_first ? t('courses.fromStart') : t('courses.fromDate', { date: formatDay(record.valid_from) }) }}
                    </span>
                    <span class="font-semibold text-fb-text">{{ formatPrice(record.price) }}</span>
                    <span v-if="record.is_current" class="rounded-full bg-emerald-100 px-2 py-0.5 text-[12px] text-emerald-800">{{ t('courses.now') }}</span>
                    <span v-else-if="record.is_future" class="rounded-full bg-amber-100 px-2 py-0.5 text-[12px] text-amber-800">{{ t('courses.planned') }}</span>
                    <span v-if="record.created_by" class="text-[12px] text-fb-icon">{{ record.created_by }}</span>
                    <span v-if="auth.isCeo" class="ml-auto flex gap-3">
                      <button type="button" class="text-fb-blue hover:underline" @click="startPriceEdit(record)">{{ t('courses.fix') }}</button>
                      <button
                        v-if="priceHistory.length > 1"
                        type="button"
                        class="text-fb-danger hover:underline"
                        @click="deletePriceRecord(record)"
                      >
                        {{ t('common.delete') }}
                      </button>
                    </span>
                  </div>
                  <div v-else class="space-y-2">
                    <div class="flex gap-2">
                      <input
                        v-model="priceEdit.price"
                        type="text"
                        inputmode="numeric"
                        class="h-10 w-1/2 rounded-lg border border-fb-line px-3 focus:outline-none focus:border-fb-blue"
                      />
                      <input
                        v-model="priceEdit.valid_from"
                        type="date"
                        class="h-10 w-1/2 rounded-lg border border-fb-line px-3 focus:outline-none focus:border-fb-blue"
                      />
                    </div>
                    <p v-if="record.is_first" class="text-[12px] text-fb-icon">
                      {{ t('courses.firstPriceHint') }}
                    </p>
                    <p v-if="priceEdit.error" class="text-[13px] text-fb-danger">{{ priceEdit.error }}</p>
                    <div class="flex gap-3">
                      <button
                        type="button"
                        class="rounded-full bg-fb-blue px-4 py-1.5 text-white disabled:opacity-60"
                        :disabled="priceEdit.saving"
                        @click="savePriceEdit"
                      >
                        {{ priceEdit.saving ? t('common.saving') : t('courses.saveFix') }}
                      </button>
                      <button type="button" class="text-fb-secondary hover:underline" @click="priceEdit.id = 0">{{ t('common.cancel') }}</button>
                    </div>
                  </div>
                </li>
              </ul>
            </div>
          </template>

          <div>
            <label class="block text-[15px] font-medium text-fb-secondary mb-2">{{ t('common.description') }}</label>
            <textarea
              v-model="form.description"
              rows="5"
              class="w-full px-4 py-3 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue resize-y"
            />
          </div>

          <p v-if="formError" class="text-fb-danger text-[15px]">{{ formError }}</p>

          <div class="flex flex-wrap gap-3">
            <button
              type="submit"
              class="px-8 py-3 rounded-full bg-fb-blue text-white text-[16px] font-semibold hover:opacity-90 disabled:opacity-60"
              :disabled="saving"
            >
              {{ saving ? t('common.saving') : t('common.save') }}
            </button>
            <button
              v-if="editingCourse && auth.isCeo"
              type="button"
              class="rounded-full border border-red-300 px-6 py-3 text-[16px] text-fb-danger"
              :disabled="deleting"
              @click="deleteCourse"
            >
              {{ t('common.delete') }}
            </button>
          </div>
          </template>
        </form>
      </aside>
    </div>
  </div>
</template>
