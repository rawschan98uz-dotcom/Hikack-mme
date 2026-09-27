<script setup lang="ts">
import { onMounted, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

interface TodayLesson {
  group_id: number;
  group: string;
  branch: string;
  room: string;
  start_time: string;
  end_time: string;
  checked_in: boolean;
  status: number | null;
  status_label: string;
  checked_at: string;
}

// Teacher attendance status: 1 = present, 2 = late, 0 = absent (same as backend)
const STATUS_LATE = 2;
const STATUS_ABSENT = 0;

const lessons = ref<TodayLesson[]>([]);
const loading = ref(true);
const busyGroupId = ref<number | null>(null);
const error = ref('');

async function loadToday() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<TodayLesson[]>>('/teacher-attendance/today');
    lessons.value = data.data;
  } catch {
    error.value = 'Не удалось загрузить уроки на сегодня';
  } finally {
    loading.value = false;
  }
}

async function checkIn(lesson: TodayLesson) {
  error.value = '';
  busyGroupId.value = lesson.group_id;
  try {
    await client.post('/teacher-attendance/self-checkin', { group_id: lesson.group_id });
    await loadToday();
  } catch (err: unknown) {
    const data = (err as { response?: { data?: { message?: string } } })?.response?.data;
    error.value = data?.message || 'Не удалось отметиться';
  } finally {
    busyGroupId.value = null;
  }
}

function badgeClass(status: number | null) {
  if (status === STATUS_LATE) return 'bg-amber-100 text-amber-800';
  if (status === STATUS_ABSENT) return 'bg-red-100 text-red-700';
  return 'bg-emerald-100 text-emerald-700';
}

onMounted(loadToday);
</script>

<template>
  <section class="border-b border-fb-line bg-fb-card px-5 py-4">
    <div class="mb-3 flex items-baseline justify-between gap-3">
      <h2 class="text-[15px] font-semibold text-fb-text">Отметка присутствия</h2>
      <span class="text-xs text-fb-secondary">Опоздание — позже 5 минут после начала урока</span>
    </div>

    <div v-if="loading" class="py-3 text-sm text-fb-secondary">Загрузка…</div>
    <div v-else-if="!lessons.length" class="py-3 text-sm text-fb-secondary">Сегодня у вас нет уроков по расписанию.</div>
    <ul v-else class="divide-y divide-fb-line">
      <li v-for="lesson in lessons" :key="lesson.group_id" class="flex flex-wrap items-center justify-between gap-3 py-3">
        <div class="min-w-0">
          <div class="font-medium text-fb-text">{{ lesson.group }}</div>
          <div class="text-xs text-fb-secondary">
            <span v-if="lesson.start_time">{{ lesson.start_time }}<span v-if="lesson.end_time">–{{ lesson.end_time }}</span> · </span>
            {{ lesson.branch }}<span v-if="lesson.room"> · {{ lesson.room }}</span>
          </div>
        </div>
        <span
          v-if="lesson.checked_in"
          class="rounded-full px-3 py-1 text-xs font-semibold"
          :class="badgeClass(lesson.status)"
        >
          {{ lesson.status_label }} · {{ lesson.checked_at }}
        </span>
        <button
          v-else
          type="button"
          class="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          :disabled="busyGroupId === lesson.group_id"
          @click="checkIn(lesson)"
        >
          {{ busyGroupId === lesson.group_id ? 'Отмечаю…' : 'Я пришёл' }}
        </button>
      </li>
    </ul>
    <p v-if="error" class="mt-2 text-sm text-fb-danger">{{ error }}</p>
  </section>
</template>
