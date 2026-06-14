<script setup lang="ts">
const milestones = [
  { status: 'done', title: 'CRM core', detail: 'Leads, students, groups, teachers' },
  { status: 'done', title: 'Finance module', detail: 'Payments, expenses, salaries, debtors' },
  { status: 'done', title: 'Reports', detail: 'Conversion, attendance, workly, left students' },
  { status: 'progress', title: 'Settings & office', detail: 'Courses, rooms, holidays, archive, staff' },
  { status: 'planned', title: 'Mobile app sync', detail: 'Teacher and parent mobile apps' },
  { status: 'planned', title: 'AI assistant', detail: 'Smart reminders and lead scoring' },
  { status: 'planned', title: 'Integrations hub', detail: 'VoIP, SMS gateways, payment systems' },
];

function statusLabel(status: string) {
  if (status === 'done') return 'Released';
  if (status === 'progress') return 'In progress';
  return 'Planned';
}

function statusClass(status: string) {
  if (status === 'done') return 'bg-emerald-50 text-emerald-700';
  if (status === 'progress') return 'bg-fb-hover text-fb-blue';
  return 'bg-fb-canvas text-fb-secondary';
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-fb-text">Roadmap</h1>
      <a
        href="https://modme.uz"
        target="_blank"
        rel="noopener noreferrer"
        class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:opacity-90"
      >
        modme.uz →
      </a>
    </div>

    <p class="max-w-2xl text-sm text-fb-secondary">
      Product roadmap for ModMe platform features. Local clone mirrors implemented modules;
      upcoming items follow the official ModMe release plan.
    </p>

    <div class="space-y-3">
      <article
        v-for="(item, index) in milestones"
        :key="item.title"
        class="flex gap-4 rounded-xl border border-fb-line bg-fb-card p-5"
      >
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-fb-canvas text-sm font-semibold text-fb-secondary">
          {{ index + 1 }}
        </div>
        <div class="min-w-0 flex-1">
          <div class="mb-1 flex flex-wrap items-center gap-2">
            <h2 class="font-semibold text-fb-text">{{ item.title }}</h2>
            <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="statusClass(item.status)">
              {{ statusLabel(item.status) }}
            </span>
          </div>
          <p class="text-sm text-fb-secondary">{{ item.detail }}</p>
        </div>
      </article>
    </div>
  </div>
</template>
