<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import { hasCreateFlag, routeWithoutCreate } from '../utils/crossLinks';
import CourseLevelBadge from '../components/CourseLevelBadge.vue';
import {
  buildCourseCardDisplay,
  courseCodeHint,
  isValidCourseCode,
  normalizeCourseCode,
  type CefrLevel,
} from '../utils/courseLevel';

interface CourseRow {
  id: number;
  name: string;
  code: string;
  price: number;
  lesson_duration: number;
  course_duration: number;
  description: string;
  level: CefrLevel | null;
  levelColor: string;
  starCount: number;
  cardTitle: string;
  badgeLabel: string;
  watermarkLabel: string;
  priceText: string;
}

const route = useRoute();
const router = useRouter();

const rows = ref<CourseRow[]>([]);
const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const showPanel = ref(false);
const panelLoading = ref(false);
const formError = ref('');
const editingCourse = ref<CourseRow | null>(null);

const lessonDurations = [45, 60, 90, 120];

const form = reactive({
  name: '',
  code: '',
  lesson_duration: 90,
  course_duration: 12,
  price: '',
  description: '',
});

function formatPrice(value: number) {
  return `${value.toLocaleString('en-US').replace(/,/g, ' ')} UZS`;
}

function enrichCourse(course: {
  id: number;
  name: string;
  code: string;
  price: number;
  lesson_duration: number;
  course_duration: number;
  description: string;
}): CourseRow {
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
    priceText: formatPrice(course.price),
  };
}

function resetForm() {
  form.name = '';
  form.code = '';
  form.lesson_duration = 90;
  form.course_duration = 12;
  form.price = '';
  form.description = '';
  formError.value = '';
  editingCourse.value = null;
}

function fillForm(course: { name: string; code: string; lesson_duration: number; course_duration: number; price: number; description: string }) {
  form.name = course.name;
  form.code = course.code;
  form.lesson_duration = course.lesson_duration;
  form.course_duration = course.course_duration;
  form.price = String(course.price);
  form.description = course.description;
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
    const { data } = await client.get<ApiEnvelope<{
      id: number;
      name: string;
      code: string;
      price: number;
      lesson_duration: number;
      course_duration: number;
      description: string;
    }>>(`/courses/${id}`);
    editingCourse.value = enrichCourse(data.data);
    fillForm(data.data);
  } finally {
    panelLoading.value = false;
  }
}

async function deleteCourse() {
  if (!editingCourse.value || !window.confirm('Delete this course?')) return;
  deleting.value = true;
  try {
    await client.delete(`/courses/${editingCourse.value.id}`);
    closePanel();
    await loadCourses();
  } finally {
    deleting.value = false;
  }
}

async function loadCourses() {
  const { data } = await client.get<ApiEnvelope<CourseRow[]>>('/courses');
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
    formError.value = 'Enter course name';
    return;
  }
  if (!isValidCourseCode(form.code)) {
    formError.value = `Enter a valid Code Course (${courseCodeHint()})`;
    return;
  }

  saving.value = true;
  try {
    const payload = {
      name: form.name.trim(),
      code: normalizeCourseCode(form.code),
      lesson_duration: form.lesson_duration,
      course_duration: Number(form.course_duration) || 12,
      price: Number(String(form.price).replace(/\s/g, '')) || 0,
      description: form.description.trim(),
    };
    if (editingCourse.value) {
      await client.patch(`/courses/${editingCourse.value.id}`, payload);
    } else {
      await client.post('/courses', payload);
    }
    await loadCourses();
    closePanel();
  } catch {
    formError.value = 'Could not save course';
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="!mb-0 text-[28px] font-normal text-fb-secondary">Courses</h1>
      <button
        type="button"
        class="px-6 py-2.5 rounded-full bg-fb-blue text-white text-[14px] font-semibold tracking-wide hover:opacity-90"
        @click="openPanel"
      >
        ADD NEW
      </button>
    </div>

    <div v-if="loading" class="py-16 text-center text-fb-secondary text-[16px]">Loading…</div>
    <div
      v-else-if="!rows.length"
      class="py-16 text-center text-fb-icon text-[16px]"
    >
      No courses yet. Click ADD NEW to add one.
    </div>
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
              {{ row.priceText }}
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
            {{ editingCourse ? 'Edit course' : 'Add New Item' }}
          </h2>
          <button
            type="button"
            class="text-fb-icon hover:text-fb-secondary text-2xl leading-none"
            @click="closePanel"
          >
            ×
          </button>
        </div>

        <form class="flex-1 overflow-y-auto px-6 py-6 space-y-5" @submit.prevent="saveCourse">
          <div v-if="panelLoading" class="text-fb-secondary">Loading…</div>
          <template v-else>
          <div>
            <label class="block text-[15px] font-medium text-fb-secondary mb-2">Name</label>
            <input
              v-model="form.name"
              type="text"
              placeholder="English B2"
              class="w-full h-11 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
            />
          </div>

          <div>
            <label class="block text-[15px] font-medium text-fb-secondary mb-2">Code Course</label>
            <input
              v-model="form.code"
              type="text"
              placeholder="b2"
              required
              class="w-full h-11 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
            />
            <p class="mt-1.5 text-[13px] text-fb-icon">
              {{ courseCodeHint() }}. This code sets the card color and label.
            </p>
          </div>

          <div>
            <label class="block text-[15px] font-medium text-fb-secondary mb-2">Lesson duration</label>
            <select
              v-model.number="form.lesson_duration"
              class="w-full h-11 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue bg-fb-card"
            >
              <option v-for="mins in lessonDurations" :key="mins" :value="mins">
                {{ mins }} minutes
              </option>
            </select>
          </div>

          <div>
            <label class="block text-[15px] font-medium text-fb-secondary mb-2">Course duration (month)</label>
            <input
              v-model.number="form.course_duration"
              type="number"
              min="1"
              class="w-full h-11 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
            />
          </div>

          <div>
            <label class="block text-[15px] font-medium text-fb-secondary mb-2">Price</label>
            <input
              v-model="form.price"
              type="text"
              inputmode="numeric"
              class="w-full h-11 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
            />
          </div>

          <div>
            <label class="block text-[15px] font-medium text-fb-secondary mb-2">Description</label>
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
              {{ saving ? 'Saving…' : 'Save' }}
            </button>
            <button
              v-if="editingCourse"
              type="button"
              class="rounded-full border border-red-300 px-6 py-3 text-[16px] text-fb-danger"
              :disabled="deleting"
              @click="deleteCourse"
            >
              Delete
            </button>
          </div>
          </template>
        </form>
      </aside>
    </div>
  </div>
</template>
