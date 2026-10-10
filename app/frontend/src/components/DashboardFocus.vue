<script setup lang="ts">
/**
 * The top of the dashboard for each role: money and debts for the head, the day for the office
 * (lessons, who came, whom to call), own lessons with "Mark attendance" for a teacher.
 * The server sends only the blocks the user may see (api/v1/dashboard_focus.py).
 */
import { computed } from 'vue';
import { useRouter, type RouteLocationRaw } from 'vue-router';

import { t } from '../i18n';
import { useAuthStore } from '../stores/auth';
import { studentRoute } from '../utils/crossLinks';
import { formatMoney } from '../utils/money';
import { canAccessRoute, PERM } from '../utils/rbac';

export interface DashboardFocusData {
  lessons_today: Array<{
    group_id: number;
    name: string;
    time: string;
    course: string | null;
    teacher: string | null;
    room: string | null;
    students: number;
    marked: boolean;
  }>;
  attendance_today: { present: number; late: number; absent: number };
  money?: { today: number; month: number };
  debts?: { count: number; total: number };
  new_leads?: { today: number; week: number };
  call_list?: Array<{ id: number; full_name: string; phone: string; debt_amount: number; overdue_days: number }>;
  trials_today?: Array<{ id: number; full_name: string; phone: string; course: string | null }>;
}

const props = defineProps<{ focus: DashboardFocusData }>();

const router = useRouter();
const auth = useAuthStore();
const isTeacher = computed(() => auth.role === 'teacher');

const markedCount = computed(() => props.focus.lessons_today.filter((l) => l.marked).length);
const cameToday = computed(() => props.focus.attendance_today.present + props.focus.attendance_today.late);
const canMark = computed(() => auth.can(PERM.ATTENDANCE_WRITE));

interface Tile {
  key: string;
  label: string;
  value: string;
  hint?: string;
  tone: 'in' | 'out' | 'plain' | 'warn';
  to?: RouteLocationRaw;
}

const tiles = computed<Tile[]>(() => {
  const f = props.focus;
  const list: Tile[] = [];
  if (f.money) {
    list.push({ key: 'today', label: t('focus.moneyToday'), value: formatMoney(f.money.today), tone: f.money.today > 0 ? 'in' : 'plain', to: '/finance/payments' });
    list.push({ key: 'month', label: t('focus.moneyMonth'), value: formatMoney(f.money.month), tone: f.money.month > 0 ? 'in' : 'plain', to: '/finance/pnl' });
  }
  if (f.debts) {
    list.push({
      key: 'debts',
      label: t('focus.debts'),
      value: formatMoney(f.debts.total),
      hint: t('focus.debtorsCount', { count: f.debts.count }),
      tone: f.debts.total > 0 ? 'out' : 'plain',
      to: '/students/debtors',
    });
  }
  if (!f.money || isTeacher.value) {
    list.push({
      key: 'lessons',
      label: t('focus.lessonsToday'),
      value: String(f.lessons_today.length),
      hint: f.lessons_today.length ? t('focus.markedOf', { marked: markedCount.value, total: f.lessons_today.length }) : undefined,
      tone: markedCount.value < f.lessons_today.length ? 'warn' : 'plain',
    });
    list.push({
      key: 'came',
      label: t('focus.cameToday'),
      value: String(cameToday.value),
      hint: f.attendance_today.absent ? t('focus.absentToday', { count: f.attendance_today.absent }) : undefined,
      tone: 'plain',
    });
  }
  if (f.new_leads) {
    list.push({
      key: 'leads',
      label: t('focus.newLeads'),
      value: String(f.new_leads.today),
      hint: t('focus.leadsWeek', { count: f.new_leads.week }),
      tone: 'plain',
      to: '/leads',
    });
  }
  return list;
});

const TONE: Record<Tile['tone'], string> = {
  in: 'text-emerald-600',
  out: 'text-red-600',
  warn: 'text-amber-600',
  plain: 'text-fb-text',
};

function markRoute(groupId: number): RouteLocationRaw {
  const path = canAccessRoute('/reports/attendance', auth.user?.permissions) && !isTeacher.value ? '/reports/attendance' : '/attendance-reports';
  return { path, query: { group: String(groupId) } };
}

function go(to?: RouteLocationRaw) {
  if (to) void router.push(to);
}

function phoneLink(phone: string) {
  const digits = (phone || '').replace(/\D/g, '');
  return digits.length === 9 ? `tel:+998${digits}` : `tel:${digits}`;
}
</script>

<template>
  <section class="border-b border-fb-line px-5 py-5">
    <!-- Big figures of the day -->
    <div class="grid gap-3" :class="tiles.length >= 4 ? 'sm:grid-cols-2 xl:grid-cols-4' : 'sm:grid-cols-2 xl:grid-cols-3'">
      <component
        :is="tile.to ? 'button' : 'div'"
        v-for="tile in tiles"
        :key="tile.key"
        :type="tile.to ? 'button' : undefined"
        class="rounded-xl border border-fb-line bg-fb-canvas px-5 py-4 text-left"
        :class="tile.to ? 'cursor-pointer hover:border-fb-blue/50' : ''"
        @click="go(tile.to)"
      >
        <div class="text-xs font-semibold uppercase tracking-wide text-fb-secondary">{{ tile.label }}</div>
        <div class="mt-1 whitespace-nowrap text-[26px] font-bold leading-tight tabular-nums" :class="TONE[tile.tone]">{{ tile.value }}</div>
        <div v-if="tile.hint" class="mt-0.5 text-sm text-fb-secondary">{{ tile.hint }}</div>
      </component>
    </div>

    <div class="mt-5 grid gap-5" :class="isTeacher ? '' : 'xl:grid-cols-2'">
      <!-- Today's lessons -->
      <div class="rounded-xl border border-fb-line bg-fb-card">
        <div class="flex items-center justify-between border-b border-fb-line px-4 py-3">
          <h2 class="text-[15px] font-semibold text-fb-text">
            {{ isTeacher ? t('focus.myLessonsToday') : t('focus.lessonsToday') }}
          </h2>
          <span v-if="focus.lessons_today.length" class="text-sm text-fb-secondary">
            {{ t('focus.markedOf', { marked: markedCount, total: focus.lessons_today.length }) }}
          </span>
        </div>
        <p v-if="!focus.lessons_today.length" class="px-4 py-6 text-center text-sm text-fb-secondary">{{ t('focus.noLessonsToday') }}</p>
        <ul v-else class="divide-y divide-fb-line">
          <li v-for="lesson in focus.lessons_today" :key="lesson.group_id" class="flex flex-wrap items-center gap-3 px-4 py-3">
            <span class="w-[110px] shrink-0 text-sm font-semibold tabular-nums text-fb-text">{{ lesson.time }}</span>
            <div class="min-w-0 flex-1">
              <div class="truncate text-[15px] font-medium text-fb-text">{{ lesson.name }}</div>
              <div class="truncate text-xs text-fb-secondary">
                {{ [isTeacher ? null : lesson.teacher, lesson.room, t('focus.studentsCount', { count: lesson.students })].filter(Boolean).join(' · ') }}
              </div>
            </div>
            <span
              class="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold"
              :class="lesson.marked ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-800'"
            >
              {{ lesson.marked ? t('focus.marked') : t('focus.notMarked') }}
            </span>
            <button
              v-if="canMark"
              type="button"
              class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold"
              :class="lesson.marked ? 'border border-fb-line text-fb-secondary hover:border-fb-blue hover:text-fb-blue' : 'bg-fb-blue text-white hover:bg-fb-blue-dark'"
              @click="go(markRoute(lesson.group_id))"
            >
              {{ lesson.marked ? t('focus.change') : t('focus.markAttendance') }}
            </button>
          </li>
        </ul>
      </div>

      <!-- Whom to call: debtors who owe longest, trial lessons today -->
      <div v-if="!isTeacher && (focus.call_list || focus.trials_today)" class="rounded-xl border border-fb-line bg-fb-card">
        <div class="border-b border-fb-line px-4 py-3">
          <h2 class="text-[15px] font-semibold text-fb-text">{{ t('focus.whomToCall') }}</h2>
        </div>
        <p
          v-if="!focus.call_list?.length && !focus.trials_today?.length"
          class="px-4 py-6 text-center text-sm text-fb-secondary"
        >
          {{ t('focus.nobodyToCall') }}
        </p>
        <ul class="divide-y divide-fb-line">
          <li
            v-for="row in focus.call_list ?? []"
            :key="`d${row.id}`"
            class="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-fb-hover/40"
            @click="go(studentRoute(row.id))"
          >
            <div class="min-w-0 flex-1">
              <div class="truncate text-[15px] font-medium text-fb-text">{{ row.full_name }}</div>
              <div class="text-xs text-red-600">
                {{ t('students.overdueDays', { count: row.overdue_days }) }}<template v-if="row.debt_amount"> · {{ formatMoney(row.debt_amount) }}</template>
              </div>
            </div>
            <a :href="phoneLink(row.phone)" class="shrink-0 text-sm font-medium text-fb-blue hover:underline" @click.stop>{{ row.phone }}</a>
          </li>
          <li
            v-for="lead in focus.trials_today ?? []"
            :key="`l${lead.id}`"
            class="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-fb-hover/40"
            @click="go({ path: '/leads', query: { stage: 'all', open: String(lead.id) } })"
          >
            <div class="min-w-0 flex-1">
              <div class="truncate text-[15px] font-medium text-fb-text">{{ lead.full_name }}</div>
              <div class="text-xs text-indigo-600">{{ t('focus.trialToday') }}<template v-if="lead.course"> · {{ lead.course }}</template></div>
            </div>
            <a :href="phoneLink(lead.phone)" class="shrink-0 text-sm font-medium text-fb-blue hover:underline" @click.stop>{{ lead.phone }}</a>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
